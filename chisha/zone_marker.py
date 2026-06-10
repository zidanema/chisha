"""更新机制 state 侧 schema + 原子文件操作 (纯 stdlib, 无 urllib).

职责分工 (spec §4.2):
  - per-zone marker `.chisha-zone.json`  = **仲裁键** (serve 哪份数据)
  - 全局 `.update-state.json`            = **陈旧度键** (该不该提示更新)
recall 只 lazy-import 本模块的读函数 (read_marker + valid_data_version), 不拉 urllib (热路径零网络依赖)。

版本目录 + 原子 symlink 切换 (Capistrano current 式, spec §4.5): zone 数据落不可变版本目录
`.{zone}.{data_version}.{shortcommit}/`, `{zone}` 是指向它的 symlink; 更新 = 建新版本目录 +
os.rename 原子重指 symlink (POSIX symlink rename 覆盖, 无目录暂缺窗口)。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

MARKER_FILENAME = ".chisha-zone.json"
UPDATE_STATE_FILENAME = ".update-state.json"
MANAGED_BY = "chisha-update"

_DV_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def valid_data_version(v) -> str:
    """data_version 仲裁/陈旧度比较键 (单源, recall+purge+staleness 共用).

    合法且**可解析**的 YYYY-MM-DD 原样返回 (字典序=日期序); 形状不符 / 非真实日历日 (如 9999-99-99) /
    缺 / 非 str → "" (最旧 → install 胜, fail-safe)。挡 producer 漂移 + 假日期 (codex/Claude review)。
    """
    if not isinstance(v, str) or not _DV_RE.match(v):
        return ""
    try:
        _dt.date.fromisoformat(v)
    except ValueError:
        return ""
    return v


# ─── per-zone marker (仲裁键) ───

def write_marker(version_dir: Path, *, zone_id: str, data_version: str,
                 source_commit: str, sha256: dict, fetched_at: str = "") -> None:
    payload = {
        "zone_id": zone_id,
        "data_version": data_version,
        "source_commit": source_commit,
        "sha256": sha256,
        "fetched_at": fetched_at,
        "managed_by": MANAGED_BY,
    }
    (version_dir / MARKER_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_marker(version_dir: Path) -> dict | None:
    """读版本目录里的 marker; 缺/坏 → None. (version_dir 可为 {zone} symlink, 跟随解析)

    仲裁取 data_version: `valid_data_version((read_marker(link) or {}).get("data_version"))` (recall)。"""
    try:
        return json.loads((version_dir / MARKER_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ─── 全局 .update-state.json (陈旧度键) ───

def read_update_state(state_data_dir: Path) -> dict:
    try:
        return json.loads((state_data_dir / UPDATE_STATE_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_update_state(state_data_dir: Path, *, last_checked: str,
                       remote_publish_date: str, source_commit: str) -> None:
    state_data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_checked": last_checked,
        "remote_publish_date": remote_publish_date,
        "source_commit": source_commit,
    }
    tmp = state_data_dir / (UPDATE_STATE_FILENAME + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, state_data_dir / UPDATE_STATE_FILENAME)   # 原子


# ─── 不可变版本目录 + 原子 symlink 切换 (spec §4.5) ───

def _version_dir(state_data_dir: Path, zone: str, data_version: str, source_commit: str) -> Path:
    short = (source_commit or "nocommit")[:7]
    return state_data_dir / f".{zone}.{data_version}.{short}"


def install_version(zone: str, state_data_dir: Path, *, data_version: str,
                    source_commit: str, files: dict[str, bytes], fetched_at: str = "") -> Path:
    """把一代 zone 数据 (restaurants+dishes) 落**不可变版本目录** + marker, 再原子 symlink 切换。

    返回新版本目录路径。旧版本目录不删 (留 purge)。首写无旧 symlink 直接建; 有旧则 os.rename
    覆盖 (POSIX symlink rename 原子, 无目录暂缺窗口)。
    """
    state_data_dir.mkdir(parents=True, exist_ok=True)
    vdir = _version_dir(state_data_dir, zone, data_version, source_commit)
    # 1. 先写**临时目录** (dot 前缀, 同父), 完整后 rename 成最终版本目录 → 版本目录始终完整可读。
    tmp_dir = state_data_dir / f".{zone}.tmp.{os.getpid()}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()
    for fname, data in files.items():
        (tmp_dir / fname).write_bytes(data)
    write_marker(tmp_dir, zone_id=zone, data_version=data_version, source_commit=source_commit,
                 sha256={f: _sha256(b) for f, b in files.items()}, fetched_at=fetched_at)
    # 版本目录**不可变** (codex HIGH 修): 同 (zone,ver,commit) 已在盘 → 复用既有, **绝不 rmtree
    # live 目录** (避免现存 symlink 短暂悬空 + 并发 os.rename ENOTEMPTY 崩溃)。
    if vdir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)   # 丢弃新写的临时目录, 不动 live vdir
    else:
        try:
            os.rename(tmp_dir, vdir)                  # 同父 rename, 原子; 版本目录此刻完整
        except OSError:
            shutil.rmtree(tmp_dir, ignore_errors=True)   # 并发: 另一进程已装同版本 → 丢弃自己的临时目录
    # 2. 原子 symlink 切换: 建临时 symlink → os.rename 覆盖 {zone}。
    link = state_data_dir / zone
    tmp_link = state_data_dir / f".{zone}.link.{os.getpid()}"
    if tmp_link.is_symlink() or tmp_link.exists():
        tmp_link.unlink()
    tmp_link.symlink_to(vdir.name)          # 相对指向 (同目录) → data 目录可整体搬移
    os.rename(tmp_link, link)               # 原子重指 (覆盖旧 symlink, 无暂缺窗口)
    return vdir


# ─── purge superseded (spec §4.7, 四条件 AND) ───

def purge_superseded(state_data_dir: Path, install_zones: dict) -> list[str]:
    """删被取代的版本目录 + (install 胜时) 删整条 state symlink。四条件 AND, 绝不误删自定义 zone。

    四条件 (spec §4.7):
      0. {zone} 是 symlink (类型守卫: 绝不 rmtree 真目录)
      1. zone_id ∈ install_zones (canonical)
      2. 指向的版本目录 marker managed_by == chisha-update
      3. install data_version >= state → install 胜
    """
    if not state_data_dir.is_dir():
        return []
    removed: list[str] = []
    for entry in list(state_data_dir.iterdir()):
        if entry.name.startswith("."):
            continue                              # 版本目录/临时/update-state — 由下方按 zone 关联清
        if not entry.is_symlink():                # cond 0: 类型守卫 (真目录免疫)
            continue
        zone = entry.name
        zinfo = install_zones.get(zone)
        if zinfo is None:                         # cond 1: canonical
            continue
        target = entry.resolve()
        marker = read_marker(entry)
        if not marker or marker.get("managed_by") != MANAGED_BY:   # cond 2
            continue
        # 与 recall 仲裁同一套 dv 键 (codex/Claude review: 两侧必须一致, 否则误判取代关系)。
        state_dv = valid_data_version(marker.get("data_version"))
        install_dv = valid_data_version(zinfo.get("data_version"))
        # 清该 zone 的**旧代**版本目录 (非当前 target) — 任何仲裁结果下都安全 (无 symlink 指向它)。
        for vd in state_data_dir.glob(f".{zone}.*"):
            if vd.is_dir() and vd.resolve() != target:
                vmark = read_marker(vd)
                if vmark and vmark.get("managed_by") == MANAGED_BY:
                    shutil.rmtree(vd, ignore_errors=True)
                    removed.append(vd.name)
        # cond 3: install 胜 → 删 symlink + 当前版本目录 (让 install 接管)。
        if install_dv >= state_dv:
            entry.unlink()
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            removed.append(zone)
    return removed

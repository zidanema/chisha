"""S-05: sandbox layout v1 → v2 migration (narrowed scope).

v2 layout 关键变化:
- ``logs/sandbox/_meta.json`` 新增 (schema_version + migration history)
- Default sid 仍 flat (``logs/sandbox/<rel>``); 非 default sid 走
  ``logs/sandbox/sessions/<sid>/<rel>`` (S-04 ``data_root`` 已实现)
- 老 ``logs/sandbox/<rel>`` 数据保持原地 = default 桶 (零搬运)
- ``--relocate-legacy`` opt-in: 把老数据挪到 ``sessions/_legacy/`` 子树备份

幂等:
- ``_meta.json.schema_version == 2`` + 请求 relocate flag 与 meta 一致 → no-op
- relocate 二次跑: 检测每 artifact (src/dst 状态), 全 settled 视为 satisfied
- collision-safe ``.bak.<utc-ts>`` 后缀, 不复用名字

Codex audit history:
- iter1 (4 BLOCKED): 删 sessions/, 加 relocate_only, ts-suffix bak, fix baseline cmd
- iter2 (1 BLOCKED): relocate_satisfied 派生 (per-artifact 状态判) 而非 bool(relocated)
- iter3: APPROVED
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Optional, TypedDict


SCHEMA_VERSION = 2
_META_REL = "logs/sandbox/_meta.json"
_LEGACY_DIRNAME = "_legacy"

# 老 layout 顶层文件/目录清单 (relocate 时挪它们).
# v5.1 Codex fix #1: 删除 "sessions" — 它是 _legacy 的 parent (sessions/_legacy/),
# 拷自己子孙会 infinite recurse. D-039 recommend sessions 本来就是 default 桶,
# 不需挪. 同理不挪 _meta.json 自身.
_LEGACY_ARTIFACTS: tuple[str, ...] = (
    "state.json",
    "meal_log.jsonl",
    "recommend_log.jsonl",
    "feedback_history.jsonl",
    "long_term_prefs.json",
    "profile.yaml",
    "feedback",         # dir
    "recommend_trace",  # dir
    # NOTE: "sessions" 不在清单 — 是 _legacy parent, 也是 D-039 recommend
    #       sessions dir, 留原地 = default 桶语义.
)


class MigrationResult(TypedDict, total=False):
    status: str          # "already_migrated" | "migrated" | "relocate_only" |
                         # "no_sandbox" | "dry_run"
    schema_version: int
    relocated: list[str]
    skipped: list[str]
    meta_path: str


def meta_path(root: Path) -> Path:
    return root / _META_REL


def read_meta(root: Path) -> Optional[dict]:
    p = meta_path(root)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _atomic_write_meta(root: Path, data: dict) -> None:
    p = meta_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(p)


def _ts_suffix() -> str:
    """UTC timestamp for collision-safe .bak names (Codex fix #3)."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def migrate_to_v2(
    root: Path,
    *,
    dry_run: bool = False,
    relocate_legacy: bool = False,
) -> MigrationResult:
    """One-shot migration. Idempotent. dry-run 仅返回 plan, 不写盘.

    场景 (v5.1 Codex fix #2 + v5.2 fix #1):
    - sandbox 目录不存在: ``no_sandbox``
    - 已 migrated (schema_v2) + 当前请求 relocate flag 与 meta 记录一致: ``already_migrated``
    - 已 migrated (schema_v2) + 请求 ``relocate=True`` 但 meta.relocated_legacy=False:
      ``relocate_only`` (跑 relocate, 更新 meta.relocated_legacy)
    - 未 migrated: write meta (+ 可选 relocate)
    """
    sandbox_dir = root / "logs" / "sandbox"
    if not sandbox_dir.exists():
        return {
            "status": "no_sandbox",
            "schema_version": SCHEMA_VERSION,
            "relocated": [],
            "skipped": [],
            "meta_path": str(meta_path(root)),
        }

    existing = read_meta(root)
    already_v2 = bool(
        existing and existing.get("schema_version") == SCHEMA_VERSION
    )
    already_relocated = bool(existing and existing.get("relocated_legacy"))

    # Codex fix #2: relocate 在 already_v2 但未 relocated 时仍可跑
    if already_v2 and (not relocate_legacy or already_relocated):
        return {
            "status": "already_migrated",
            "schema_version": SCHEMA_VERSION,
            "relocated": [],
            "skipped": [],
            "meta_path": str(meta_path(root)),
        }

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    relocated: list[str] = []
    skipped: list[str] = []

    # v5.2 Codex fix #1: relocate_satisfied 派生 — 跑完后, 每个 artifact 必须
    # (a) 刚被搬走 (in `relocated`), 或 (b) 已在 _legacy (dst.exists()), 或
    # (c) src 完全不存在 + dst 不存在 (从未有过). 三种都满足 → relocate_satisfied.
    relocate_satisfied = False
    if relocate_legacy:
        legacy_dir = sandbox_dir / "sessions" / _LEGACY_DIRNAME
        ts = _ts_suffix()  # 单次跑共用 ts, 多文件 .bak 关联可读
        all_ok = True  # 中途发现 src+dst 同在 (上次跑被打断) 则 False
        for name in _LEGACY_ARTIFACTS:
            src = sandbox_dir / name
            dst = legacy_dir / name
            if not src.exists():
                # src 不在: settled if dst 在 OR 全 absent (从未有过)
                skipped.append(name)
                continue
            # src 在
            if dst.exists():
                # dst 也在: skip (幂等保护), 但 src 还在意味着上次跑被打断;
                # 不重搬, 让 caller 手工解决 (all_ok=False).
                skipped.append(name)
                all_ok = False
                continue
            if dry_run:
                relocated.append(name)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            # Codex fix #3: collision-safe bak 名 (ts 后缀, 不复用)
            bak_name = f"{src.name}.bak.{ts}"
            bak = src.parent / bak_name
            if bak.exists():
                raise RuntimeError(
                    f"backup name collision: {bak} already exists; "
                    f"refusing to overwrite. Inspect manually."
                )
            # copy → bak rename 两步
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            src.rename(bak)
            relocated.append(name)
        # 跑完: 只要无 "src 在 + dst 在" 的中断态, 即视为 satisfied
        relocate_satisfied = all_ok

    if dry_run:
        return {
            "status": "dry_run",
            "schema_version": SCHEMA_VERSION,
            "relocated": relocated,
            "skipped": skipped,
            "meta_path": str(meta_path(root)),
        }

    # v5.1: relocate-only 分支保留原 meta 其他字段, 翻 relocated_legacy
    if already_v2 and relocate_legacy:
        new_meta = dict(existing)  # type: ignore[arg-type]
        # v5.2 Codex fix #1: 用 relocate_satisfied 而非 bool(relocated)
        new_meta["relocated_legacy"] = bool(
            relocate_satisfied or already_relocated
        )
        new_meta["relocated_at"] = now_iso
        _atomic_write_meta(root, new_meta)
        return {
            "status": "relocate_only",
            "schema_version": SCHEMA_VERSION,
            "relocated": relocated,
            "skipped": skipped,
            "meta_path": str(meta_path(root)),
        }

    new_meta_first: dict = {
        "schema_version": SCHEMA_VERSION,
        "created_at": (existing or {}).get("created_at") or now_iso,
        "migrated_at": now_iso,
        "default_layout": "flat",  # 决策: default sid 走 flat 路径
        # v5.2 Codex fix #1: 用 relocate_satisfied
        "relocated_legacy": bool(relocate_legacy and relocate_satisfied),
    }
    if relocate_legacy and (relocated or relocate_satisfied):
        new_meta_first["relocated_at"] = now_iso
    _atomic_write_meta(root, new_meta_first)
    return {
        "status": "migrated",
        "schema_version": SCHEMA_VERSION,
        "relocated": relocated,
        "skipped": skipped,
        "meta_path": str(meta_path(root)),
    }

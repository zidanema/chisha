"""chisha update — 数据 track fetch 编排 (urllib + hashlib, 零新依赖).

R1 (实现期修正 spec §4.3 自指 bug): manifest 在 build 期写出, 那时 dist commit 还不存在, 故
manifest **无法**带自己的 source_commit。改由 GitHub commits API 在 fetch 期拿不可变 main SHA
→ manifest + 数据都 pin /{SHA}/ (硬关 TOCTOU, 避开 manifest 自身 CDN stale)。

recommend 热路径**绝不**调本模块 (运行期零联网; 仅 `chisha update` verb 联网)。
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

OWNER = "zidanema"
REPO = "chisha"
_RAW = "https://raw.githubusercontent.com"
_API = "https://api.github.com"
_ZONE_FILES = ("restaurants.json", "dishes_tagged.json")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")            # commit-pin 强度: 必须完整 40-hex (codex review)
_ZONE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")  # 防 remote zone_id 路径穿越 (codex review)


class UpdateNetworkError(RuntimeError):
    """拉取失败 (超时/连接/HTTP). 文案点明可能需 HTTP(S) 代理或透明 VPN (urllib 不支持纯 SOCKS)."""


class ZoneIntegrityError(RuntimeError):
    """下载字节 sha256 与 manifest 声明不符 → 弃该 zone, state 不变."""


def _http_get(url: str, timeout: int = 8) -> bytes:
    """裸 GET → bytes。urllib 默认吃 http_proxy/https_proxy + macOS 系统代理 (透明 VPN ok)。

    **测试 seam**: 测试 monkeypatch 本函数注入 fixture, 不走真网络。
    """
    req = urllib.request.Request(url, headers={"User-Agent": "chisha-update"})
    if url.startswith(_API):
        req.add_header("Accept", "application/vnd.github.sha")   # commits API 返回裸 SHA
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateNetworkError(
            f"拉取 {url} 失败 ({e}). 大陆需 HTTP(S) 代理或系统级透明 VPN; "
            "urllib 不支持纯 SOCKS 代理 (browser 能通不代表 chisha 能通)."
        ) from e


def resolve_main_sha() -> str:
    """GitHub commits API → main 当前**完整 40-hex** 不可变 SHA (R1: 不从 manifest 自指读).

    强制完整 40-hex (codex review): 短 SHA 不保证唯一 → 削弱 commit-pin 不可变性, 宁可报错重试。
    """
    raw = _http_get(f"{_API}/repos/{OWNER}/{REPO}/commits/main").decode("utf-8").strip()
    # Accept: vnd.github.sha → 裸 40-hex; 兜底兼容 JSON (.sha)。
    sha = raw if _SHA_RE.match(raw.lower()) else ""
    if not sha:
        try:
            sha = str(json.loads(raw).get("sha", "")).lower()
        except ValueError:
            sha = ""
    if not _SHA_RE.match(sha):
        raise UpdateNetworkError(f"commits API 未返回完整 40-hex SHA: {raw[:80]!r}")
    return sha


def fetch_manifest(sha: str) -> dict:
    """拉 manifest@{sha} (不可变) + 写前校验 (validator raise → 调用方 try 包整轮 abort)."""
    from chisha import manifest as mfst
    raw = _http_get(f"{_RAW}/{OWNER}/{REPO}/{sha}/data/manifest.json")
    data = json.loads(raw)
    mfst.validate_payload(data, Path(f"<remote@{sha}>"))   # 不兼容 raise IncompatibleManifestError
    return data


def fetch_zone_files(sha: str, zone: str, *, sha256: dict) -> dict[str, bytes]:
    """commit-pin 下载 zone 两文件 + 逐文件 sha256 校验; 不符 raise ZoneIntegrityError."""
    out: dict[str, bytes] = {}
    for fname in _ZONE_FILES:
        want = (sha256 or {}).get(fname)
        if want is None:
            continue   # manifest 没声明该文件 (如 coming_soon 无 dishes) → 跳过
        data = _http_get(f"{_RAW}/{OWNER}/{REPO}/{sha}/data/{zone}/{fname}")
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            raise ZoneIntegrityError(
                f"{zone}/{fname} sha256 不符 (manifest={want[:12]}… 下载={got[:12]}…); "
                "弃该 zone, state 不变, 稍后重试."
            )
        out[fname] = data
    return out


def run_update(*, state_data_dir: Path, install_zones: dict, today: str,
               dry_run: bool = False) -> dict:
    """编排一轮更新。返回 {updated, skipped, failed, source_commit, remote_publish_date}。

    install_zones: {zone_id: zone_dict(含 data_version+sha256)} = install manifest 的有效来源。
    state marker 若该 zone 已在 state 则优先用 state 的 sha256 比对 (避免重复下载)。
    整轮无致命网络/不兼容错才写 .update-state.json (零下载也写, no-false-nag)。
    """
    from chisha import zone_marker as zm
    sha = resolve_main_sha()
    remote = fetch_manifest(sha)
    remote_zones = {z["zone_id"]: z for z in remote.get("zones", []) if isinstance(z, dict)}
    remote_pub = (remote.get("generated_at") or today)[:10]

    updated, skipped, failed = [], [], []
    for zone_id, rz in remote_zones.items():
        # 防 remote zone_id 路径穿越 (codex review): 非法 id 绝不进 URL / 写盘路径。
        if not isinstance(zone_id, str) or not _ZONE_ID_RE.match(zone_id):
            failed.append(str(zone_id))
            continue
        # 过渡守卫: remote zone 未声明 sha256 (旧 schema-2 dist 尚未 republish) → 无法完整性校验,
        # 不下载不写 (否则会落空版本目录)。新 schema-3 dist 必有 sha256 → 正常流程。
        if not rz.get("sha256"):
            skipped.append(zone_id)
            continue
        # 有效来源 sha256: state marker 优先 (该 zone 已在 state), 否则 install manifest。
        link = state_data_dir / zone_id
        local_m = zm.read_marker(link) if link.exists() else None
        local_sha = (local_m or install_zones.get(zone_id, {})).get("sha256")
        if local_sha and local_sha == rz.get("sha256"):
            skipped.append(zone_id)          # F1: 一致 → skip, 不写 marker (无 orphan)
            continue
        if dry_run:
            updated.append(zone_id)
            continue
        try:
            files = fetch_zone_files(sha, zone_id, sha256=rz.get("sha256") or {})
        except ZoneIntegrityError:
            failed.append(zone_id)            # 弃该 zone, state 不变
            continue
        zm.install_version(zone_id, state_data_dir,
                           data_version=rz.get("data_version") or remote_pub,
                           source_commit=sha, files=files, fetched_at=today)
        updated.append(zone_id)

    if not dry_run:
        zm.purge_superseded(state_data_dir, install_zones)
        # 陈旧度键: 仅当**无 zone 失败**才写 last_checked (codex review: 有 zone 完整性失败时数据
        # 并非真 fresh, 不写 → staleness 继续提醒重试, 不被 14 天静默期掩盖)。
        if not failed:
            zm.write_update_state(state_data_dir, last_checked=today,
                                  remote_publish_date=remote_pub, source_commit=sha)
    return {"updated": updated, "skipped": skipped, "failed": failed,
            "source_commit": sha, "remote_publish_date": remote_pub}

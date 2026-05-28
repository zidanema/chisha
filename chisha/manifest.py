"""D-102 Step3: 数据产物 ↔ 引擎 兼容闸门 (提案 §C).

只读数据 bundle (data/{zone}/*.json) 发布时带一个 bundle 级 `data/manifest.json`。引擎
消费 bundle 前 (recall.load_zone_data 入口 + doctor) 读 manifest 比对: 不兼容 **hard-fail**,
绝不"尽力解析" (D-100 fail-loud)。

版本分层 (§C): manifest 只管"数据产物↔引擎"这一条分发边界, 不取代 PROTOCOL_VERSION /
CANDIDATE_SCHEMA_VERSION / TRACE_SCHEMA_VERSION 等内部层版本。

兼容判定**不用单调 version**, 用 **capability flags** (§C): 产物在 manifest 里声明
`engine_capabilities_required` (要求引擎具备的能力集), 引擎用自己的 `SUPPORTED_ENGINE_CAPABILITIES`
比对 —— 缺能力 = 破坏性变更 hard-fail; 数值小升级 (artifact_version bump 但能力不变) 兼容。

缺 manifest = 未版本化/过渡期 bundle → **warn-allow** (非 incompatible, 没信息可断言);
present-but-incompatible = 已知不兼容 → **hard-fail**。doctor 把"缺 manifest"标为未达分发就绪。

本期**留位不实现** (提案范围红线): integrity hash / 签名 / 来源证明 (manifest 里 integrity=null)。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from chisha import __version__ as ENGINE_VERSION

logger = logging.getLogger(__name__)

# manifest 文件自身 schema 版本 (引擎能解析的 manifest 结构版本上限). manifest 结构变 → bump.
MANIFEST_SCHEMA_VERSION = 1

# 引擎能消费的数据 bundle schema 版本上限 (restaurants/dishes_tagged 结构). bundle 的
# data_schema_version > 此 → 破坏性数据结构变更, 引擎太旧 hard-fail.
SUPPORTED_DATA_SCHEMA_VERSION = 1

# 引擎具备的能力集 (§C capability flags). 产物 manifest 的 engine_capabilities_required
# 必须是它的子集, 否则缺能力 hard-fail. 新增能力 (如 quarantine 分发) 时往这里加。
SUPPORTED_ENGINE_CAPABILITIES: frozenset[str] = frozenset({
    "stable_entity_ids_v1",   # D-099 稳定实体 id (绑 normalized_name_version=1)
    "dish_tag_schema_v3",     # D-037 打标 V3 schema
})

MANIFEST_FILENAME = "manifest.json"


class IncompatibleManifestError(RuntimeError):
    """数据产物与引擎不兼容. 调用方/用户应升级引擎或换匹配的 bundle (不 grandfather)."""


@dataclass
class ManifestStatus:
    status: str                       # ok | missing | (raise 不返回)
    manifest_path: Path
    artifact_version: int | None = None
    data_schema_version: int | None = None


def manifest_path(install_root: Path) -> Path:
    return install_root / "data" / MANIFEST_FILENAME


def _parse_semver(v: str) -> tuple[int, int, int]:
    """'0.1' / '0.1.0' → (0,1,0). 零补齐到 3 段 (防 (0,1) < (0,1,0) 把等价版本误判).
    非法段当 0 (宽松, 比对只用下限)."""
    parts = []
    for part in str(v).split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    parts = (parts + [0, 0, 0])[:3]
    return (parts[0], parts[1], parts[2])


def read_manifest(install_root: Path) -> dict | None:
    """读 data/manifest.json. 不存在返 None (缺 manifest = 过渡期, 调用方决定 warn/fail)."""
    p = manifest_path(install_root)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise IncompatibleManifestError(
            f"data/manifest.json 损坏无法解析: {type(e).__name__}: {e} (不尽力解析, "
            "重新发布 bundle 或 build_manifest)."
        )
    if not isinstance(data, dict):
        raise IncompatibleManifestError("data/manifest.json 顶层非 object.")
    return data


def _validate_manifest_payload(data: dict, mpath: Path) -> ManifestStatus:
    """T-DIST-01 B.5b: 抽出 check_compatibility 内部校验体, 让 user-level resource manifest
    复用同一套 capability flags 比对 (D-102.3 单一权威源)."""
    from chisha.loader import SHOP_NAME_VERSION
    mschema = data.get("manifest_schema_version")
    if not isinstance(mschema, int) or mschema > MANIFEST_SCHEMA_VERSION:
        raise IncompatibleManifestError(
            f"manifest_schema_version={mschema} 引擎只支持 ≤ {MANIFEST_SCHEMA_VERSION} "
            f"({mpath}). 升级 chisha 引擎。"
        )

    # data_schema_version 必填 + int.
    dsv = data.get("data_schema_version")
    if not isinstance(dsv, int):
        raise IncompatibleManifestError(
            f"manifest 缺/非法 data_schema_version={dsv!r} ({mpath}). 已版本化 bundle 必须声明; "
            "重新 build_manifest。"
        )
    if dsv > SUPPORTED_DATA_SCHEMA_VERSION:
        raise IncompatibleManifestError(
            f"bundle data_schema_version={dsv} > 引擎支持 {SUPPORTED_DATA_SCHEMA_VERSION} "
            f"({mpath}). 数据结构破坏性变更, 升级 chisha 引擎。"
        )

    min_engine = data.get("min_engine_version")
    if min_engine and _parse_semver(min_engine) > _parse_semver(ENGINE_VERSION):
        raise IncompatibleManifestError(
            f"bundle 要求引擎 ≥ {min_engine}, 当前引擎 {ENGINE_VERSION} ({mpath}). 升级 chisha。"
        )

    # engine_capabilities_required 必填 + list[str].
    caps_raw = data.get("engine_capabilities_required")
    if not isinstance(caps_raw, list) or not all(isinstance(c, str) for c in caps_raw):
        raise IncompatibleManifestError(
            f"manifest 缺/非法 engine_capabilities_required={caps_raw!r} ({mpath}). "
            "已版本化 bundle 必须声明 (空列表 [] 是合法的 '不要求任何能力' 声明); 重新 build_manifest。"
        )
    required = set(caps_raw)
    missing_caps = required - SUPPORTED_ENGINE_CAPABILITIES
    if missing_caps:
        raise IncompatibleManifestError(
            f"bundle 要求引擎能力 {sorted(missing_caps)} 引擎不具备 "
            f"(支持: {sorted(SUPPORTED_ENGINE_CAPABILITIES)}) ({mpath}). 升级 chisha 引擎。"
        )

    # normalized_name_version 必填 + int.
    nnv = data.get("normalized_name_version")
    if not isinstance(nnv, int):
        raise IncompatibleManifestError(
            f"manifest 缺/非法 normalized_name_version={nnv!r} ({mpath}). 已版本化 bundle 必须声明; "
            "重新 build_manifest。"
        )
    if nnv != SHOP_NAME_VERSION:
        raise IncompatibleManifestError(
            f"bundle normalized_name_version={nnv} != 引擎 SHOP_NAME_VERSION={SHOP_NAME_VERSION} "
            f"({mpath}). 归一化规则漂移会让稳定 id / 反馈错配, 重打标或换匹配 bundle。"
        )

    return ManifestStatus(
        status="ok", manifest_path=mpath,
        artifact_version=data.get("artifact_version"),
        data_schema_version=dsv,
    )


def check_compatibility(install_root: Path) -> ManifestStatus:
    """读 install bundle manifest 比对引擎兼容性。present-incompatible → raise; 缺 → status=missing (warn)。

    比对项 (任一不满足即 IncompatibleManifestError):
    - manifest_schema_version > 引擎支持上限 (引擎太旧, 看不懂新 manifest 结构)
    - min_engine_version > 引擎版本 (引擎太旧, 用不了该 bundle)
    - engine_capabilities_required ⊄ SUPPORTED_ENGINE_CAPABILITIES (引擎缺能力)
    - normalized_name_version != loader.SHOP_NAME_VERSION (D-099 归一化单边漂移)
    """
    mpath = manifest_path(install_root)
    data = read_manifest(install_root)
    if data is None:
        return ManifestStatus(status="missing", manifest_path=mpath)
    return _validate_manifest_payload(data, mpath)


# T-DIST-01 B.5b: user-level resource manifest 校验 (C-d 独立轻量, 复用 capability flags).

def user_resource_manifest_check(state_root_p: Path) -> list[dict]:
    """枚举 state_root/data/{zone} + state_root/methodologies/, 校验各自 manifest.json.

    返回 list of dict, 每项 {kind, name, status, note}:
      - kind: "zone" | "methodology"
      - name: zone/methodology 名 (目录/文件 stem)
      - status: "ok" | "missing_manifest" | "incompatible"
      - note: 详情 (incompatible 时含原因; ok 时空字符串)

    与 install bundle manifest 闸门 (check_compatibility) 复用 _validate_manifest_payload,
    但**不混入**主流程 (D-102.3 CONTRACTS): 主流程 ensure_compatible_once 只检 install,
    user 区由 doctor 单独报告 (失败标 incompatible 但**不**阻塞 recall — user 决定要不要
    清理). recall.load_zone_data 命中 user zone 时, 即便 user manifest 不兼容, 数据本身
    schema 仍走 install bundle 闸门那套引擎兼容性保证 (capability flags 共一套).
    """
    results: list[dict] = []
    # zones
    data_dir = state_root_p / "data"
    if data_dir.is_dir():
        for zone_dir in sorted(data_dir.iterdir(), key=lambda p: p.name):
            if not zone_dir.is_dir():
                continue
            # 只对真实 zone bundle 校验 (有 restaurants.json 才算 zone)
            if not (zone_dir / "restaurants.json").exists():
                continue
            mp = zone_dir / MANIFEST_FILENAME
            if not mp.exists():
                results.append({
                    "kind": "zone", "name": zone_dir.name,
                    "status": "missing_manifest",
                    "note": f"{mp} 缺失 (跑 scripts.build_manifest 生成).",
                })
                continue
            try:
                data = json.loads(mp.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise IncompatibleManifestError(f"{mp} 顶层非 object.")
                _validate_manifest_payload(data, mp)
                results.append({
                    "kind": "zone", "name": zone_dir.name,
                    "status": "ok", "note": "",
                })
            except (OSError, json.JSONDecodeError) as e:
                results.append({
                    "kind": "zone", "name": zone_dir.name,
                    "status": "incompatible",
                    "note": f"manifest 损坏: {type(e).__name__}: {e}",
                })
            except IncompatibleManifestError as e:
                results.append({
                    "kind": "zone", "name": zone_dir.name,
                    "status": "incompatible", "note": str(e),
                })
    # methodologies (单文件无 manifest, 只列存在; 校验在 load_methodology 走 _validate_spec)
    meth_dir = state_root_p / "methodologies"
    if meth_dir.is_dir():
        for p in sorted(meth_dir.iterdir(), key=lambda p: p.name):
            if p.is_file() and p.suffix == ".yaml":
                results.append({
                    "kind": "methodology", "name": p.stem,
                    "status": "present", "note": "校验在 load_methodology 触发.",
                })
    return results


# 进程内只检一次 (per install_root): bundle 运行时不变, 避免每次 load_zone_data 重读 + 日志刷屏。
_checked: set[str] = set()


def ensure_compatible_once(install_root: Path) -> None:
    """recall.load_zone_data 入口调: 首次对该 root 跑 compat check。incompatible → raise;
    缺 manifest → warn 一次放行 (过渡期未版本化 bundle)。"""
    key = str(Path(install_root).resolve())
    if key in _checked:
        return
    st = check_compatibility(install_root)   # incompatible 在此 raise
    if st.status == "missing":
        logger.warning(
            "data/manifest.json 缺失 (%s) — 未版本化 bundle, 放行但未达分发就绪 "
            "(跑 scripts.build_manifest 生成).", st.manifest_path,
        )
    _checked.add(key)

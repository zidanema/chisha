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


def check_compatibility(install_root: Path) -> ManifestStatus:
    """读 manifest 比对引擎兼容性。present-incompatible → raise; 缺 → status=missing (warn)。

    比对项 (任一不满足即 IncompatibleManifestError):
    - manifest_schema_version > 引擎支持上限 (引擎太旧, 看不懂新 manifest 结构)
    - min_engine_version > 引擎版本 (引擎太旧, 用不了该 bundle)
    - engine_capabilities_required ⊄ SUPPORTED_ENGINE_CAPABILITIES (引擎缺能力)
    - normalized_name_version != loader.SHOP_NAME_VERSION (D-099 归一化单边漂移)
    """
    from chisha.loader import SHOP_NAME_VERSION
    mpath = manifest_path(install_root)
    data = read_manifest(install_root)
    if data is None:
        return ManifestStatus(status="missing", manifest_path=mpath)

    mschema = data.get("manifest_schema_version")
    if not isinstance(mschema, int) or mschema > MANIFEST_SCHEMA_VERSION:
        raise IncompatibleManifestError(
            f"manifest_schema_version={mschema} 引擎只支持 ≤ {MANIFEST_SCHEMA_VERSION} "
            f"({mpath}). 升级 chisha 引擎。"
        )

    # data_schema_version 必填 + int: present 的 manifest 是"已版本化 bundle"声明, 缺/非法
    # = malformed → fail-loud, 绝不尽力解析 (Codex review: 防 present-but-underspecified 绕过).
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

    # engine_capabilities_required 必填 + list[str]: present-but-underspecified (字段缺失 /
    # 非 list / 元素非 str) = malformed → fail-loud. 缺字段 → `or []` 会让子集判定恒成立悄悄
    # 放行 (Codex acceptance review P1 洞), 与 dsv/nnv 缺字段同等严格 hard-fail; 字段在但
    # 列空 [] 是合法声明"我不要求任何能力" → 放行.
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

    # normalized_name_version 必填 + int (D-099 稳定 id 命脉): 缺/非法即 malformed → fail-loud
    # (归一化版本无法核对会让稳定 id / 反馈静默错配, 比放行更危险).
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
        data_schema_version=data.get("data_schema_version"),
    )


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

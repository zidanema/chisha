"""D-072 methodology spec 加载 + 校验 + merge.

L0 方法论 (D-070 三层信号模型) 从硬编码 score.py 抽到 yaml spec.
chisha/score.py / recall.py 不动接口 — load_profile 在加载 profile 后调
merge_into_profile, 把 spec defaults 注入 profile (profile 显式值 override),
所有下游代码 like 之前一样从 profile 读.

边界 (D-072 + Codex Round 2):
  - 严格 keyset 校验: 顶层 6 必备字段 + plate_rule/score_weights/cap_rules
    内部 key 拼写错误必 raise (B-1)
  - sensible default 非 silent: profile 缺 methodology 字段 fallback
    harvard_plate, 同时 logger.info 留可观测痕迹 (M-1)
  - soft_rules / extra_rules 非空时 logger.warning 提示这是 V1 死字段
  - merge 后 score.py 读路径不变: profile.plate_rule / profile.scoring_weights
    / profile.recall.per_*_top_k / profile.scoring.unforgivable_discount
"""
from __future__ import annotations

import copy
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_METHODOLOGY = "harvard_plate"
METHODOLOGIES_DIRNAME = "profiles/methodologies"

# 顶层必备字段 (缺失 hard fail)
_REQUIRED_TOP_KEYS = (
    "name", "display_name", "version", "rationale",
    "plate_rule", "score_weights", "cap_rules",
)

# 顶层可选字段 (V1 加载但部分不执行)
_OPTIONAL_TOP_KEYS = (
    "unforgivable_discount", "soft_rules", "extra_rules",
)

# plate_rule / score_weights / cap_rules 内部严格 keyset (Codex B-1)
_PLATE_RULE_KEYS = (
    "must_have_vegetable", "min_vegetable_dishes",
    "min_protein_g", "prefer_oil_level_at_most", "hard_max_oil_level",
)

# 与 chisha.score.V2_DEFAULT_WEIGHTS 一致 (16 维)
_SCORE_WEIGHT_KEYS = (
    "vegetable_floor_pass", "protein_floor_pass", "distance",
    "low_oil", "popularity", "cuisine_preference", "variety_bonus",
    "carb_quality", "processed_meat", "sweet_sauce", "wetness",
    "dish_role_match", "eta", "price", "taste_match", "context_boost",
)

_CAP_RULES_KEYS = (
    "per_restaurant_top_k", "per_brand_top_k",
    "per_cuisine_top_k", "per_food_form_top_k",
)


class MethodologyValidationError(ValueError):
    """spec 校验失败 (顶层字段缺失 / 内部 key 拼写错). Hard fail, 不 silent."""


def _validate_keyset(
    section_name: str,
    actual: dict[str, Any],
    expected: tuple[str, ...],
) -> None:
    actual_keys = set(actual.keys())
    expected_keys = set(expected)
    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys
    msgs = []
    if missing:
        msgs.append(f"missing keys: {sorted(missing)}")
    if extra:
        msgs.append(f"unknown keys (typo?): {sorted(extra)}")
    if msgs:
        raise MethodologyValidationError(
            f"methodology spec.{section_name} keyset mismatch — "
            + "; ".join(msgs)
        )


def _validate_spec(spec: dict[str, Any]) -> None:
    """严格校验 spec 结构. 任何不符 → raise MethodologyValidationError."""
    if not isinstance(spec, dict):
        raise MethodologyValidationError(
            f"methodology spec root must be dict, got {type(spec).__name__}"
        )
    # 顶层必备
    missing_top = [k for k in _REQUIRED_TOP_KEYS if k not in spec]
    if missing_top:
        raise MethodologyValidationError(
            f"methodology spec missing required top keys: {missing_top}"
        )
    # 顶层不允许未知字段 (Codex B-1: 拼写错也算)
    allowed_top = set(_REQUIRED_TOP_KEYS) | set(_OPTIONAL_TOP_KEYS)
    extra_top = [k for k in spec.keys() if k not in allowed_top]
    if extra_top:
        raise MethodologyValidationError(
            f"methodology spec has unknown top keys (typo?): {extra_top}"
        )
    # 子段 keyset 严格
    if not isinstance(spec.get("plate_rule"), dict):
        raise MethodologyValidationError("spec.plate_rule must be dict")
    _validate_keyset("plate_rule", spec["plate_rule"], _PLATE_RULE_KEYS)

    if not isinstance(spec.get("score_weights"), dict):
        raise MethodologyValidationError("spec.score_weights must be dict")
    _validate_keyset("score_weights", spec["score_weights"], _SCORE_WEIGHT_KEYS)

    if not isinstance(spec.get("cap_rules"), dict):
        raise MethodologyValidationError("spec.cap_rules must be dict")
    _validate_keyset("cap_rules", spec["cap_rules"], _CAP_RULES_KEYS)

    # name 与文件名一致是约定, 但不在此校验 (load_methodology 才知道文件名)


def _methodology_path(name: str, root: Path) -> Path:
    return root / METHODOLOGIES_DIRNAME / f"{name}.yaml"


@lru_cache(maxsize=8)
def _load_methodology_cached(
    name: str,
    root_str: str,
    mtime_ns: int,
) -> dict[str, Any]:
    """带 LRU cache 的实际加载. cache key 包含 yaml 文件 mtime_ns (Codex Round 3 M-3):
    yaml 改了后 mtime_ns 变, cache 自然 miss → reload, 不会读旧值.
    """
    root = Path(root_str)
    path = _methodology_path(name, root)
    # 这里 mtime_ns 入参仅用于 cache key 区分, 不重新 stat
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    _validate_spec(raw)
    if raw.get("name") != name:
        raise MethodologyValidationError(
            f"methodology spec name mismatch: file={name!r}, "
            f"spec.name={raw.get('name')!r}"
        )
    if raw.get("soft_rules"):
        logger.warning(
            "methodology spec %s has non-empty soft_rules — V1 加载但不解释执行, "
            "实际规则仍在 score.py 硬编码. 详见 D-072 schema 表.", name,
        )
    if raw.get("extra_rules"):
        logger.warning(
            "methodology spec %s has non-empty extra_rules — V1 不解释 (Phase 1 逃逸口).",
            name,
        )
    return raw


def load_methodology(name: str, root: Path) -> dict[str, Any]:
    """加载并校验 methodology spec. 不存在 raise FileNotFoundError; 校验失败 raise
    MethodologyValidationError. 缓存命中后返回深拷贝 (防调用方就地改污染缓存).

    Codex Round 3 M-3: cache key 包含 yaml mtime_ns, yaml 改后自动失效.
    """
    root_resolved = root.resolve()
    path = _methodology_path(name, root_resolved)
    if not path.exists():
        raise FileNotFoundError(
            f"methodology spec not found: {path} "
            f"(name={name!r}, dir={root_resolved / METHODOLOGIES_DIRNAME})"
        )
    mtime_ns = path.stat().st_mtime_ns
    cached = _load_methodology_cached(name, str(root_resolved), mtime_ns)
    return copy.deepcopy(cached)


def resolve_methodology(profile: dict[str, Any], root: Path) -> dict[str, Any]:
    """从 profile.methodology 字段读名 (缺失 fallback DEFAULT_METHODOLOGY).

    Codex Round 2 M-1: 缺字段时 logger.info 显式打"using default", 留可观测痕迹.
    """
    name = profile.get("methodology")
    if not name:
        logger.info(
            "profile.methodology field missing, falling back to default %r. "
            "建议在 profile.yaml 显式写 `methodology: %s`.",
            DEFAULT_METHODOLOGY, DEFAULT_METHODOLOGY,
        )
        name = DEFAULT_METHODOLOGY
    return load_methodology(name, root)


def merge_into_profile(
    profile: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    """把 spec defaults merge 进 profile, profile 显式值 override (Codex B-spot-2:
    profile 已有 key 必须保留原值, 不被 spec 覆盖).

    具体桥接 (D-072 schema 表):
      - profile.plate_rule          ← {**spec.plate_rule, **profile.plate_rule}
      - profile.scoring_weights     ← {**spec.score_weights, **profile.scoring_weights}
        (注意命名漂移: spec `score_weights`, profile `scoring_weights`)
      - profile.recall              ← {**spec.cap_rules, **profile.recall}
        (per_*_top_k 同名字段)
      - profile.scoring.unforgivable_discount ← profile 优先, 否则 spec
        (Codex B-2: 路径必须 profile.scoring.* 不是 profile.* 顶层)

    其他字段一律不动. 返回 deep-copy 新 dict, 不就地改 profile.
    """
    merged = copy.deepcopy(profile)

    # plate_rule merge
    spec_plate = spec.get("plate_rule") or {}
    profile_plate = merged.get("plate_rule") or {}
    merged["plate_rule"] = {**spec_plate, **profile_plate}

    # scoring_weights merge (spec.score_weights → profile.scoring_weights)
    spec_weights = spec.get("score_weights") or {}
    profile_weights = merged.get("scoring_weights") or {}
    merged["scoring_weights"] = {**spec_weights, **profile_weights}

    # recall (cap_rules 部分) merge — 只 merge per_*_top_k key, 不动其他 recall key
    spec_caps = spec.get("cap_rules") or {}
    profile_recall = merged.get("recall") or {}
    merged_recall = {**profile_recall}
    for k, v in spec_caps.items():
        merged_recall.setdefault(k, v)
    merged["recall"] = merged_recall

    # unforgivable_discount: 路径在 profile.scoring.unforgivable_discount
    if "unforgivable_discount" in spec:
        scoring = merged.get("scoring") or {}
        if "unforgivable_discount" not in scoring:
            scoring["unforgivable_discount"] = spec["unforgivable_discount"]
        merged["scoring"] = scoring

    # methodology 字段持久化 spec.name, 方便下游 (rerank.py) 拿 rationale
    merged["methodology"] = spec.get("name")
    # 缓存 spec dict 供 rerank.py 等下游消费, 不参与打分逻辑
    merged["_methodology_spec"] = spec

    return merged


def apply_methodology(
    profile: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    """便利接口: resolve → merge, 返回 merged profile.

    load_profile / web_api / CLI 一致调这个, 保证三路径不漂移 (D-071 同款约束).
    """
    spec = resolve_methodology(profile, root)
    return merge_into_profile(profile, spec)

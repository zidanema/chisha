"""T-P1a-03 (scaffold 版): Faithful Refine 多 slot schema.

边界 (重要):
  - 本模块只承载 schema 占位 + 安全带 骨架; 下游 (recall/score/rerank) **不消费**.
  - 真正的 LLM prompt 多 slot 解析 + 30-50 条 eval set 留 follow-up.
  - V1 (`refine_intent.RefineIntent`) 共存, 生产 refine 链路仍走 V1.
  - V2 来自 LLM 直接产出或 `from_legacy` 包装 V1.

trace 双存 (brief §4 安全带 #2):
  - raw_text: 用户原文 (字符串)
  - 结构化结果 (V2 dataclass.to_log_dict)
  - raw_understanding: LLM 自述理解 (LLM 失败时填 raw_text 保兜底)

字段空洞 (brief §5):
  - 数据层暂不支持的字段名进 `unsupported_in_recall: list[str]`
  - L1/L2 不消费, 只透传 L3 prompt (本任务不接 L3 prompt, T-P1b-02 narrative 时一起接)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# brief §5: 数据层暂不支持的字段名 (即使 LLM 解析出, L1/L2 也不消费)
DATA_LAYER_UNSUPPORTED_FIELDS: tuple[str, ...] = (
    "constrain.quality_floor",
    "constrain.delivery_only",
    "constrain.max_distance_km",
    "reference",
)


def _empty_redirect() -> dict:
    """brief §4 redirect 块: 全部 list 字段空数组."""
    return {
        "cuisine_want": [],
        "cuisine_avoid": [],
        "cuisine_candidates_expanded": [],  # LLM 推断的同义菜系集合 (本任务不填)
        "ingredient_want": [],
        "ingredient_avoid": [],
        "ingredient_synonyms": [],         # LLM 同义扩展
        "brand_avoid": [],
        "cooking_method_avoid": [],
        "food_form_avoid": [],
    }


@dataclass
class RefineIntentV2:
    """多 slot Faithful Refine schema (brief §4).

    scaffold: 仅占位 + 验证. P1a-03 follow-up 接 LLM prompt 真正产出多 slot.
    """
    redirect: dict = field(default_factory=_empty_redirect)
    constrain: dict = field(default_factory=dict)
    reference: dict | None = None
    reject_previous: bool = False
    raw_understanding: str = ""        # LLM 自述理解, trace 双存用
    raw_text: str = ""                 # 用户原文
    schema_version: str = "2.0"
    # brief §5 数据层不支持的字段名 (透传 L3 但 L1/L2 不消费)
    unsupported_in_recall: list[str] = field(default_factory=list)
    # Codex audit blocker: V1 字段在 V2 schema 没有自然位, 用 legacy_v1 完整保留
    legacy_v1: dict = field(default_factory=dict)

    def is_empty(self) -> bool:
        """所有语义维度均空 → True. raw_text / raw_understanding / schema_version 不算."""
        if self.reject_previous:
            return False
        for v in self.redirect.values():
            if v:
                return False
        for v in self.constrain.values():
            if v not in (None, False, [], "", {}):
                return False
        if self.reference:
            return False
        # legacy_v1 中的语义字段也算
        for k in ("cuisine_want", "cuisine_avoid", "ingredient_want",
                  "ingredient_avoid", "cooking_method", "flavor_tags",
                  "portion", "staple_preference", "price_band"):
            if self.legacy_v1.get(k):
                return False
        return True

    def to_log_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_legacy(cls, intent) -> "RefineIntentV2":
        """无损 V1 → V2 迁移.

        - cuisine_want/avoid + ingredient_want/avoid 拷到 redirect 对应 slot
        - 其他 V1 字段 (cooking_method/flavor_tags/raw_flavor/portion/staple_preference/
          price_band/freeform_note) 完整进 legacy_v1
        - raw_text 同步
        - raw_understanding 默认填 freeform_note (V1 LLM 没分开两个字段)
        - schema_version 强制 "2.0"
        """
        legacy = intent.to_log_dict() if hasattr(intent, "to_log_dict") else {}
        redirect = _empty_redirect()
        redirect["cuisine_want"] = list(legacy.get("cuisine_want", []) or [])
        redirect["cuisine_avoid"] = list(legacy.get("cuisine_avoid", []) or [])
        redirect["ingredient_want"] = list(legacy.get("ingredient_want", []) or [])
        redirect["ingredient_avoid"] = list(legacy.get("ingredient_avoid", []) or [])
        # brief §5: 数据层不支持字段 — 默认全部列入 unsupported_in_recall
        # (V2 真接 LLM 后, 只把实际有值的 slot 列入)
        unsupported = list(DATA_LAYER_UNSUPPORTED_FIELDS)
        return cls(
            redirect=redirect,
            constrain={},
            reference=None,
            reject_previous=False,
            raw_understanding=legacy.get("freeform_note") or "",
            raw_text=legacy.get("raw_text", "") or "",
            schema_version="2.0",
            unsupported_in_recall=unsupported,
            legacy_v1={k: v for k, v in legacy.items()
                       if k not in ("raw_text", "schema_version")},
        )


def validate_v2_schema(d: dict) -> tuple[bool, list[str]]:
    """Shallow 结构校验. 返 (ok, errors).

    检查范围 (Codex audit §3 推荐, 不过度工程):
      - 顶层 dict
      - schema_version == "2.0"
      - redirect 是 dict + 各 slot 是 list[str]
      - constrain 是 dict
      - reference: None 或 dict
      - reject_previous: bool
      - raw_understanding / raw_text: str
      - unsupported_in_recall: list[str]
      - legacy_v1: dict
    不检查内层 enum (那是 LLM prompt 重写时的事).
    """
    errors: list[str] = []
    if not isinstance(d, dict):
        return False, [f"top-level not dict: {type(d).__name__}"]
    sv = d.get("schema_version")
    if sv != "2.0":
        errors.append(f"schema_version != '2.0': {sv!r}")
    redirect = d.get("redirect")
    if not isinstance(redirect, dict):
        errors.append(f"redirect not dict: {type(redirect).__name__}")
    else:
        for k, v in redirect.items():
            if not isinstance(v, list):
                errors.append(f"redirect[{k}] not list: {type(v).__name__}")
            elif any(not isinstance(x, str) for x in v):
                errors.append(f"redirect[{k}] has non-str element")
    if not isinstance(d.get("constrain"), dict):
        errors.append("constrain not dict")
    ref = d.get("reference")
    if ref is not None and not isinstance(ref, dict):
        errors.append(f"reference must be None or dict: {type(ref).__name__}")
    if not isinstance(d.get("reject_previous"), bool):
        errors.append("reject_previous not bool")
    if not isinstance(d.get("raw_understanding", ""), str):
        errors.append("raw_understanding not str")
    if not isinstance(d.get("raw_text", ""), str):
        errors.append("raw_text not str")
    uir = d.get("unsupported_in_recall")
    if uir is not None:
        if not isinstance(uir, list) or any(not isinstance(x, str) for x in uir):
            errors.append("unsupported_in_recall not list[str]")
    legacy = d.get("legacy_v1")
    if legacy is not None and not isinstance(legacy, dict):
        errors.append("legacy_v1 not dict")
    return len(errors) == 0, errors


def extract_refine_intent_v2(
    text: str = "",
    *,
    use_llm: bool | None = None,
    profile_llm: dict | None = None,
) -> RefineIntentV2:
    """安全带 #1: schema 验证 + 失败降级.

    scaffold: 走 V1 parse_refine_intent 然后 from_legacy 包装.
    P1a-03 follow-up: 直接走 LLM 多 slot prompt, 失败时降级到 V1 parse.

    LLM 失败时: 返空 RefineIntentV2 但 raw_text 保留 (brief 安全带 #1 + #2).
    """
    from chisha.refine_intent import parse_refine_intent
    text = (text or "").strip()
    if not text:
        return RefineIntentV2(raw_text="")
    try:
        v1 = parse_refine_intent(text=text, use_llm=use_llm,
                                   profile_llm=profile_llm)
        return RefineIntentV2.from_legacy(v1)
    except Exception:
        # 安全带: V1 parse 失败也不抛, 返空 V2 + raw_text 保留
        return RefineIntentV2(raw_text=text, raw_understanding="")

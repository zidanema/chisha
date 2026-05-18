"""T-P1a-03 (follow-up): Faithful Refine 多 slot schema + LLM 解析层 + 安全带.

边界 (重要):
  - LLM 解析直出 brief §4 多 slot 结构; 解析失败时**降级到 V1 from_legacy**, 永不崩.
  - V1 (`refine_intent.RefineIntent`) 共存, 生产 refine 链路目前仍走 V1 (T-P1a-02
    L1 召回参数改写已消费 V1; 把 V2 真接入生产是 T-P2-01 / T-P2-02 follow-up 的事).
  - 下游 (recall/score/rerank) 当前不消费新 slot (cuisine_candidates_expanded /
    ingredient_synonyms / brand_avoid / cooking_method_avoid / food_form_avoid /
    constrain.* / reference / reject_previous). 本任务只确保 LLM 抽得出来 + trace 双存.

trace 双存 (brief §4 安全带 #2):
  - raw_text: 用户原文
  - 结构化结果 (V2 dataclass.to_log_dict)
  - raw_understanding: LLM 自述理解 (LLM 失败/降级时回填 raw_text 兜底)

字段空洞 (brief §5):
  - LLM 仍输出 constrain.quality_floor / delivery_only / max_distance_km / reference
  - L1/L2 不消费, 只透传 L3 prompt
  - unsupported_in_recall 列出"被填了但下游不读"的字段名
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH_V2 = ROOT / "prompts" / "parse_refine_intent_v2.md"


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
        "cuisine_candidates_expanded": [],
        "ingredient_want": [],
        "ingredient_avoid": [],
        "ingredient_synonyms": [],
        "brand_avoid": [],
        "cooking_method_avoid": [],
        "food_form_avoid": [],
    }


def _empty_constrain() -> dict:
    """brief §4 constrain 块: 全部 None 初始, functional 子 dict 也全 None."""
    return {
        "oil": None,
        "price_max": None,
        "quality_floor": None,
        "delivery_only": None,
        "max_distance_km": None,
        "functional": {
            "low_caffeine": None,
            "low_satiety_drowsy": None,
        },
    }


@dataclass
class RefineIntentV2:
    """多 slot Faithful Refine schema (brief §4).

    LLM 直出 (T-P1a-03 follow-up). 失败时 from_legacy 降级.
    """
    redirect: dict = field(default_factory=_empty_redirect)
    constrain: dict = field(default_factory=_empty_constrain)
    reference: dict | None = None
    reject_previous: bool = False
    raw_understanding: str = ""        # LLM 自述理解, trace 双存用
    raw_text: str = ""                 # 用户原文
    schema_version: str = "2.0"
    unsupported_in_recall: list[str] = field(default_factory=list)
    # V1 字段在 V2 schema 没有自然位的部分进 legacy_v1 (向后兼容)
    legacy_v1: dict = field(default_factory=dict)

    def is_empty(self) -> bool:
        """所有语义维度均空 → True. raw_text / raw_understanding / schema_version 不算."""
        if self.reject_previous:
            return False
        for v in self.redirect.values():
            if v:
                return False
        for k, v in self.constrain.items():
            if k == "functional":
                if isinstance(v, dict) and any(x not in (None, False) for x in v.values()):
                    return False
            elif v not in (None, False, [], "", {}):
                return False
        if self.reference:
            return False
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
        """无损 V1 → V2 迁移. LLM 失败降级时调.

        - cuisine_want/avoid + ingredient_want/avoid 拷到 redirect 对应 slot
        - 其他 V1 字段 (cooking_method/flavor_tags/raw_flavor/portion/staple_preference/
          price_band/freeform_note) 完整进 legacy_v1
        - raw_text 同步
        - raw_understanding 回填 freeform_note (兜底)
        - schema_version 强制 "2.0"
        """
        legacy = intent.to_log_dict() if hasattr(intent, "to_log_dict") else {}
        redirect = _empty_redirect()
        redirect["cuisine_want"] = list(legacy.get("cuisine_want", []) or [])
        redirect["cuisine_avoid"] = list(legacy.get("cuisine_avoid", []) or [])
        redirect["ingredient_want"] = list(legacy.get("ingredient_want", []) or [])
        redirect["ingredient_avoid"] = list(legacy.get("ingredient_avoid", []) or [])
        return cls(
            redirect=redirect,
            constrain=_empty_constrain(),
            reference=None,
            reject_previous=False,
            raw_understanding=legacy.get("freeform_note") or "",
            raw_text=legacy.get("raw_text", "") or "",
            schema_version="2.0",
            unsupported_in_recall=list(DATA_LAYER_UNSUPPORTED_FIELDS),
            legacy_v1={k: v for k, v in legacy.items()
                       if k not in ("raw_text", "schema_version")},
        )


# ─────────────────────────── schema 验证 (安全带 #1) ───────────────────────

def validate_v2_schema(d: dict) -> tuple[bool, list[str]]:
    """Shallow 结构校验. 返 (ok, errors).

    检查范围:
      - 顶层 dict
      - schema_version == "2.0"
      - redirect 是 dict + 各 slot 是 list[str]
      - constrain 是 dict + functional 是 dict
      - reference: None 或 dict
      - reject_previous: bool
      - raw_understanding / raw_text: str
      - unsupported_in_recall: list[str]
      - legacy_v1: dict
    不检查内层 enum (那是 LLM 解析的 best-effort).
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
    constrain = d.get("constrain")
    if not isinstance(constrain, dict):
        errors.append("constrain not dict")
    else:
        functional = constrain.get("functional")
        if functional is not None and not isinstance(functional, dict):
            errors.append("constrain.functional not dict")
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


# ─────────────────────────── 清洗 helpers ─────────────────────────────────

def _clean_str_list(items: Any) -> list[str]:
    """LLM 返回 list 时去 None / 空 / 重复 / strip; 非 list 时返 []."""
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for x in items:
        if x is None:
            continue
        s = str(x).strip()
        if s and s not in out:
            out.append(s)
    return out


def _coerce_bool_or_null(v: Any) -> bool | None:
    """LLM 可能给 'true'/'false' 字符串, 也可能直接 bool/None."""
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes"):
            return True
        if s in ("false", "no"):
            return False
    return None


def _coerce_number_or_null(v: Any) -> float | int | None:
    """price_max / max_distance_km 类字段, 接受 int/float, 字符串可解析数字, 否则 None."""
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    if isinstance(v, str):
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        if m:
            try:
                f = float(m.group(0))
                return int(f) if f.is_integer() else f
            except ValueError:
                return None
    return None


def _coerce_enum_or_null(v: Any, allowed: set[str]) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s in allowed else None


_OIL_VALUES = {"low", "normal"}
_QUALITY_FLOOR_VALUES = {"non_fast_food"}
_REFERENCE_RELATIONS = {"lighter", "similar_but_different_venue", "avoid_pattern"}


def _clean_parsed_to_v2(parsed: dict, *, raw_text: str) -> RefineIntentV2:
    """LLM 返回的 dict → RefineIntentV2 dataclass. 每个 slot 都做防御性清洗.

    任何不符合 schema 的子字段降级到默认值 (空 list / None / False), 不抛.
    """
    redirect_raw = parsed.get("redirect") or {}
    redirect = _empty_redirect()
    for k in redirect.keys():
        redirect[k] = _clean_str_list(redirect_raw.get(k))

    constrain_raw = parsed.get("constrain") or {}
    constrain = _empty_constrain()
    constrain["oil"] = _coerce_enum_or_null(constrain_raw.get("oil"), _OIL_VALUES)
    constrain["price_max"] = _coerce_number_or_null(constrain_raw.get("price_max"))
    constrain["quality_floor"] = _coerce_enum_or_null(
        constrain_raw.get("quality_floor"), _QUALITY_FLOOR_VALUES)
    constrain["delivery_only"] = _coerce_bool_or_null(constrain_raw.get("delivery_only"))
    constrain["max_distance_km"] = _coerce_number_or_null(
        constrain_raw.get("max_distance_km"))
    functional_raw = constrain_raw.get("functional") or {}
    if isinstance(functional_raw, dict):
        constrain["functional"]["low_caffeine"] = _coerce_bool_or_null(
            functional_raw.get("low_caffeine"))
        constrain["functional"]["low_satiety_drowsy"] = _coerce_bool_or_null(
            functional_raw.get("low_satiety_drowsy"))

    reference: dict | None = None
    reference_raw = parsed.get("reference")
    if isinstance(reference_raw, dict):
        rel = _coerce_enum_or_null(reference_raw.get("relation"),
                                     _REFERENCE_RELATIONS)
        if rel is not None:
            ref_id = reference_raw.get("reference_meal_id")
            reference = {
                "reference_meal_id": str(ref_id) if ref_id else None,
                "relation": rel,
            }

    reject_previous = _coerce_bool_or_null(parsed.get("reject_previous")) or False
    raw_understanding = str(parsed.get("raw_understanding") or "").strip()

    return RefineIntentV2(
        redirect=redirect,
        constrain=constrain,
        reference=reference,
        reject_previous=reject_previous,
        raw_understanding=raw_understanding,
        raw_text=raw_text,
        schema_version="2.0",
        unsupported_in_recall=list(DATA_LAYER_UNSUPPORTED_FIELDS),
        legacy_v1={},
    )


# ─────────────────────────── LLM 路径 (安全带核心) ────────────────────────

def _llm_parse_v2(text: str,
                   profile_llm: dict | None = None) -> dict | None:
    """调 LLM 返回 dict, 失败返回 None.

    memory `chisha_llm_call_principles`: L1 抽取低频, 走 text+JSON 路径 (不引入 tool_use).
    memory `chisha_l3_model_refine_intent_sensitivity`: profile.yaml 用 sonnet/opus,
        避免 deepseek-flash 稀释 intent.
    """
    try:
        from chisha.llm_client import call_text
        prompt = PROMPT_PATH_V2.read_text(encoding="utf-8").replace(
            "{INPUT_TEXT}", text
        )
        resp = call_text(prompt, max_tokens=1024, temperature=0.0,
                          json_mode=True, profile_llm=profile_llm)
        out = resp.get("content", "") if isinstance(resp, dict) else ""
        if not out:
            return None
        # 去 markdown 代码块, 提取最外层 {...}
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if not m:
            return None
        return json.loads(m.group(0))
    except Exception as e:
        print(f"  [refine_intent_v2] LLM 失败 "
              f"({type(e).__name__}: {str(e)[:80]}), 降级 V1 from_legacy")
        return None


# ─────────────────────────── 公开入口 ─────────────────────────────────────

def extract_refine_intent_v2(
    text: str = "",
    *,
    use_llm: bool | None = None,
    profile_llm: dict | None = None,
) -> RefineIntentV2:
    """安全带 #1: LLM 多 slot 解析, 失败降级到 V1 from_legacy.

    流程:
      1. text 空 → 返 empty V2 (不调 LLM).
      2. use_llm=False 或 LLM 不可用 → V1 parse → from_legacy.
      3. LLM 调用:
         a. 成功 + JSON 解析成功 + schema validate 通过 → _clean_parsed_to_v2.
         b. LLM 失败 / 坏 JSON / schema 不匹配 → 降级 V1 parse → from_legacy.
            raw_understanding 回填占位 ("LLM 解析失败, 走 V1 兜底").

    LLM 失败时绝不抛, 绝不瞎猜 (brief §4 安全带 #1).
    """
    from chisha.refine_intent import parse_refine_intent

    text = (text or "").strip()
    if not text:
        # 空 text 也回填 raw_understanding 占位 (eval edge-01), trace 双存语义统一.
        return RefineIntentV2(raw_text="", raw_understanding="(空 refine)")

    # use_llm 决策
    if use_llm is None:
        try:
            from chisha.llm_client import has_llm_key
            use_llm = has_llm_key()
        except Exception:
            use_llm = False

    # ─ V1 fallback path ─
    def _fallback_to_legacy(reason: str) -> RefineIntentV2:
        try:
            v1 = parse_refine_intent(text=text, use_llm=False,
                                       profile_llm=profile_llm)
            v2 = RefineIntentV2.from_legacy(v1)
        except Exception:
            v2 = RefineIntentV2(raw_text=text)
        # 安全带: raw_understanding 总是反映降级原因 (raw_text 已经在 raw_text 字段),
        # V1 的 freeform_note 是用户原文重复, 信息冗余且 misleading.
        v2.raw_understanding = reason
        return v2

    if not use_llm:
        return _fallback_to_legacy("LLM 不可用, 走规则兜底")

    parsed = _llm_parse_v2(text, profile_llm=profile_llm)
    if parsed is None:
        return _fallback_to_legacy("LLM 解析失败, 走 V1 兜底")

    # 给 parsed 注入 raw_text / schema_version 后做 schema validate
    parsed.setdefault("schema_version", "2.0")
    parsed.setdefault("raw_text", text)
    # 先做 shape 修正再 validate (LLM 可能少给某字段)
    parsed.setdefault("redirect", _empty_redirect())
    parsed.setdefault("constrain", _empty_constrain())
    parsed.setdefault("reference", None)
    parsed.setdefault("reject_previous", False)
    parsed.setdefault("raw_understanding", "")
    parsed.setdefault("unsupported_in_recall",
                       list(DATA_LAYER_UNSUPPORTED_FIELDS))
    parsed.setdefault("legacy_v1", {})

    ok, errors = validate_v2_schema(parsed)
    if not ok:
        print(f"  [refine_intent_v2] schema validate fail: {errors[:3]}, "
              f"降级 V1")
        return _fallback_to_legacy("LLM schema 不匹配, 走 V1 兜底")

    return _clean_parsed_to_v2(parsed, raw_text=text)

"""T-P1a-03 (scaffold): RefineIntentV2 schema + 安全带 单测."""
from __future__ import annotations

from chisha.refine_intent import RefineIntent, parse_refine_intent
from chisha.refine_intent_v2 import (
    DATA_LAYER_UNSUPPORTED_FIELDS,
    RefineIntentV2,
    extract_refine_intent_v2,
    validate_v2_schema,
)


def test_refine_v2_empty_default():
    v2 = RefineIntentV2()
    assert v2.schema_version == "2.0"
    assert v2.redirect["cuisine_want"] == []
    assert v2.redirect["ingredient_want"] == []
    assert v2.constrain == {}
    assert v2.reference is None
    assert v2.reject_previous is False
    assert v2.raw_text == ""
    assert v2.is_empty() is True


def test_refine_v2_from_legacy_preserves_all_v1_fields():
    """Codex audit blocker: V1 13 字段都要 lossless 进 V2 (redirect + legacy_v1)."""
    v1 = parse_refine_intent("想吃湘菜, 肉多一点, 不要海鲜", use_llm=False)
    assert v1.cuisine_want, "fixture sanity: rule_parse 应识别湘菜"
    v2 = RefineIntentV2.from_legacy(v1)
    # redirect 主要 slot
    assert v2.redirect["cuisine_want"] == v1.cuisine_want
    assert v2.redirect["cuisine_avoid"] == v1.cuisine_avoid
    assert v2.redirect["ingredient_want"] == v1.ingredient_want
    assert v2.redirect["ingredient_avoid"] == v1.ingredient_avoid
    # legacy_v1 完整保留其他 V1 字段
    assert v2.legacy_v1["flavor_tags"] == v1.flavor_tags
    assert v2.legacy_v1["raw_flavor"] == v1.raw_flavor
    assert v2.legacy_v1["portion"] == v1.portion
    assert v2.legacy_v1["staple_preference"] == v1.staple_preference
    assert v2.legacy_v1["price_band"] == v1.price_band
    assert v2.legacy_v1["cooking_method"] == v1.cooking_method
    assert v2.legacy_v1["freeform_note"] == v1.freeform_note
    # raw_text 同步
    assert v2.raw_text == v1.raw_text
    # schema_version 强制 v2
    assert v2.schema_version == "2.0"


def test_refine_v2_unsupported_in_recall_lists_field_voids():
    """brief §5: V2 from_legacy 默认列入 4 个数据层不支持字段."""
    v1 = parse_refine_intent("想吃湘菜", use_llm=False)
    v2 = RefineIntentV2.from_legacy(v1)
    assert "constrain.quality_floor" in v2.unsupported_in_recall
    assert "constrain.delivery_only" in v2.unsupported_in_recall
    assert "constrain.max_distance_km" in v2.unsupported_in_recall
    assert "reference" in v2.unsupported_in_recall
    # 数据层支持的字段不应在列 (e.g. cooking_method_avoid, brand_avoid)
    assert "cooking_method_avoid" not in v2.unsupported_in_recall
    assert "brand_avoid" not in v2.unsupported_in_recall


def test_refine_v2_schema_validation_accepts_valid_v2():
    v2 = RefineIntentV2()
    ok, errors = validate_v2_schema(v2.to_log_dict())
    assert ok, f"empty V2 should validate, errors: {errors}"


def test_refine_v2_schema_validation_rejects_bad_shape():
    """4 个 bad cases."""
    # schema_version 错
    bad1 = RefineIntentV2().to_log_dict()
    bad1["schema_version"] = "1.0"
    ok, errors = validate_v2_schema(bad1)
    assert not ok
    assert any("schema_version" in e for e in errors)

    # redirect 不是 dict
    bad2 = RefineIntentV2().to_log_dict()
    bad2["redirect"] = []
    ok, errors = validate_v2_schema(bad2)
    assert not ok
    assert any("redirect" in e for e in errors)

    # reject_previous 不是 bool
    bad3 = RefineIntentV2().to_log_dict()
    bad3["reject_previous"] = "yes"
    ok, errors = validate_v2_schema(bad3)
    assert not ok
    assert any("reject_previous" in e for e in errors)

    # 顶层不是 dict
    ok, errors = validate_v2_schema("not a dict")  # type: ignore[arg-type]
    assert not ok


def test_extract_v2_empty_text_returns_empty_v2():
    """空 text → 直接 empty V2, 不调 LLM."""
    v2 = extract_refine_intent_v2("")
    assert v2.is_empty()
    assert v2.raw_text == ""


def test_extract_v2_non_empty_text_returns_v2_from_v1():
    """非空 text → 走 V1 parse → from_legacy 包成 V2."""
    v2 = extract_refine_intent_v2("想吃湘菜的肉", use_llm=False)
    assert v2.schema_version == "2.0"
    assert v2.raw_text == "想吃湘菜的肉"
    # V1 rule_parse 应识别"湘菜" + "肉"
    assert v2.redirect["cuisine_want"], "rule_parse 应抓 cuisine_want"
    assert v2.redirect["ingredient_want"], "rule_parse 应抓 ingredient_want"


def test_refine_v2_to_log_dict_includes_required_fields():
    """trace 双存格式: schema_version / raw_understanding / raw_text 都在."""
    v2 = RefineIntentV2(raw_text="x", raw_understanding="LLM 听到了 x")
    d = v2.to_log_dict()
    assert d["schema_version"] == "2.0"
    assert d["raw_text"] == "x"
    assert d["raw_understanding"] == "LLM 听到了 x"
    assert "redirect" in d
    assert "constrain" in d
    assert "unsupported_in_recall" in d


def test_refine_v2_is_empty_ignores_raw_fields():
    """raw_text / raw_understanding 不算语义维度."""
    v2 = RefineIntentV2(raw_text="某些文本", raw_understanding="LLM 自述")
    assert v2.is_empty() is True
    # 但 redirect slot 非空就不是 empty
    v2.redirect["cuisine_want"] = ["湘菜"]
    assert v2.is_empty() is False
    # reset
    v2.redirect["cuisine_want"] = []
    # reject_previous 算
    v2.reject_previous = True
    assert v2.is_empty() is False


def test_v1_caller_still_returns_v1_schema_version():
    """Codex audit 5: parse_refine_intent 仍返 V1 + schema_version='1.0', 不破 V1 路径."""
    v1 = parse_refine_intent("想吃湘菜", use_llm=False)
    assert isinstance(v1, RefineIntent)
    assert v1.schema_version == "1.0"

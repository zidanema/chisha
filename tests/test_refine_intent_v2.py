"""RefineIntentV2 schema + 安全带 单测 (D-094.1 schema 扩展版).

D-094.1 真消费 slot 清单 (13 槽):
  redirect: cuisine_want / cuisine_avoid / cuisine_candidates_expanded /
            ingredient_want / ingredient_avoid / brand_avoid /
            cooking_method_avoid / staple_want / staple_avoid
  constrain: oil ∈ {low,normal,high} | null / price_max (数字) /
             price_band ∈ {cheap,normal,premium} | null / wants_soup (bool)

V1 整模块已退役: 没 from_legacy / legacy_v1 / parse_refine_intent.
LLM 失败/不可用 → empty V2 + raw_understanding 注明原因.
"""
from __future__ import annotations

import json as _json
from unittest.mock import patch

from chisha.refine_intent_v2 import (
    COOKING_METHOD_ENUM,
    RefineIntentV2,
    extract_refine_intent_v2,
    validate_v2_schema,
)


def _empty_redirect_for_test() -> dict:
    return {
        "cuisine_want": [], "cuisine_avoid": [],
        "cuisine_candidates_expanded": [],
        "ingredient_want": [], "ingredient_avoid": [],
        "brand_avoid": [], "cooking_method_avoid": [],
        "staple_want": [], "staple_avoid": [],
    }


def _empty_constrain_for_test() -> dict:
    return {"oil": None, "price_max": None, "price_band": None, "wants_soup": False}


def _fake_llm_resp(content: str) -> dict:
    return {"type": "text", "content": content, "stop_reason": "end_turn",
            "usage": {}, "model": "test", "raw_text": content}


# ─────────────────────────── schema 基本 ───────────────────────────

def test_refine_v2_empty_default():
    v2 = RefineIntentV2()
    assert v2.schema_version == "2.1"
    assert v2.redirect == _empty_redirect_for_test()
    assert v2.constrain == _empty_constrain_for_test()
    assert v2.reference is None
    assert v2.reject_previous is False
    assert v2.raw_text == ""
    assert v2.is_empty() is True


def test_refine_v2_schema_validation_accepts_valid_v2():
    v2 = RefineIntentV2()
    ok, errors = validate_v2_schema(v2.to_log_dict())
    assert ok, f"empty V2 should validate, errors: {errors}"


def test_refine_v2_schema_validation_rejects_bad_shape():
    bad1 = RefineIntentV2().to_log_dict()
    bad1["schema_version"] = "2.0"
    ok, errors = validate_v2_schema(bad1)
    assert not ok and any("schema_version" in e for e in errors)

    bad2 = RefineIntentV2().to_log_dict()
    bad2["redirect"] = []
    ok, errors = validate_v2_schema(bad2)
    assert not ok and any("redirect" in e for e in errors)

    bad3 = RefineIntentV2().to_log_dict()
    bad3["reject_previous"] = "yes"
    ok, errors = validate_v2_schema(bad3)
    assert not ok and any("reject_previous" in e for e in errors)

    ok, errors = validate_v2_schema("not a dict")  # type: ignore[arg-type]
    assert not ok


def test_refine_v2_to_log_dict_excludes_classvar():
    v2 = RefineIntentV2(raw_text="x", raw_understanding="LLM x")
    d = v2.to_log_dict()
    assert d["schema_version"] == "2.1"
    assert d["raw_text"] == "x"
    assert d["raw_understanding"] == "LLM x"
    assert "_METHODOLOGY_BREAK_KEYWORDS" not in d  # ClassVar 不进 asdict


def test_refine_v2_is_empty_ignores_raw_fields():
    v2 = RefineIntentV2(raw_text="文本", raw_understanding="LLM 自述")
    assert v2.is_empty() is True
    v2.redirect["cuisine_want"] = ["湘菜"]
    assert v2.is_empty() is False
    v2.redirect["cuisine_want"] = []
    v2.reject_previous = True
    assert v2.is_empty() is False
    v2.reject_previous = False
    v2.constrain["wants_soup"] = True
    assert v2.is_empty() is False


def test_refine_v2_properties_access():
    """便捷 properties (语义层 alias, 不进 asdict)."""
    v2 = RefineIntentV2(
        redirect={**_empty_redirect_for_test(), "cuisine_want": ["川菜"],
                  "ingredient_want": ["牛肉"], "staple_want": ["米饭"]},
        constrain={"oil": "high", "price_max": 50, "price_band": "cheap",
                   "wants_soup": True},
    )
    assert v2.cuisine_want == ["川菜"]
    assert v2.ingredient_want == ["牛肉"]
    assert v2.staple_want == ["米饭"]
    assert v2.oil == "high"
    assert v2.price_max == 50
    assert v2.price_band == "cheap"
    assert v2.wants_soup is True
    # property 不进 asdict
    d = v2.to_log_dict()
    assert "cuisine_want" not in d  # 在 d["redirect"] 里
    assert "oil" not in d            # 在 d["constrain"] 里


def test_refine_v2_allows_methodology_break():
    v2 = RefineIntentV2(raw_text="今晚就放纵, 给我推炒饭")
    assert v2.allows_methodology_break() is True
    v2 = RefineIntentV2(raw_text="想吃湘菜")
    assert v2.allows_methodology_break() is False


# ─────────────────────────── empty / disabled / LLM None 路径 ───────────────────

def test_extract_v2_empty_text_returns_empty_v2():
    v2 = extract_refine_intent_v2("")
    assert v2.is_empty()
    assert v2.raw_text == ""
    assert v2.raw_understanding == "(空 refine)"


def test_extract_v2_llm_disabled_returns_empty_with_reason():
    """V1 已退役, use_llm=False → empty V2 + raw_understanding 注明."""
    v2 = extract_refine_intent_v2("想吃湘菜", use_llm=False)
    assert v2.raw_text == "想吃湘菜"
    assert v2.is_empty()  # 没有 LLM 抽不出结构化
    assert "LLM 不可用" in v2.raw_understanding


def test_extract_v2_llm_returns_none_falls_back_to_empty():
    """LLM 返 None (调失败) → empty V2 + raw_understanding 注明."""
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=None):
        v2 = extract_refine_intent_v2("想吃湘菜", use_llm=True)
    assert v2.raw_text == "想吃湘菜"
    assert v2.is_empty()
    assert "LLM 解析失败" in v2.raw_understanding


def test_extract_v2_llm_missing_required_key_falls_back_to_empty():
    """LLM 漏必填字段 → empty V2 (不能 setdefault 静默补)."""
    parsed = {"redirect": _empty_redirect_for_test(),
              "constrain": _empty_constrain_for_test(),
              # 漏 raw_understanding
              "schema_version": "2.1"}
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("test", use_llm=True)
    assert v2.is_empty()
    assert "漏必填字段" in v2.raw_understanding


def test_extract_v2_llm_schema_mismatch_falls_back_to_empty():
    """schema validate 失败 → empty V2."""
    parsed = {"redirect": _empty_redirect_for_test(),
              "constrain": _empty_constrain_for_test(),
              "schema_version": "9.9",  # 错版本
              "raw_understanding": "test"}
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("test", use_llm=True)
    assert v2.is_empty()
    assert "schema 不匹配" in v2.raw_understanding


# ─────────────────────────── LLM happy paths ───────────────────────────

def test_extract_v2_llm_happy_path_multi_slot():
    parsed = {
        "redirect": {**_empty_redirect_for_test(), "cuisine_want": ["湖南菜"],
                     "ingredient_want": ["肉"]},
        "constrain": _empty_constrain_for_test(),
        "reference": None, "reject_previous": False,
        "raw_understanding": "想吃湖南菜+肉",
        "schema_version": "2.1",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("想吃湖南菜, 肉多一点", use_llm=True)
    assert v2.redirect["cuisine_want"] == ["湖南菜"]
    assert v2.redirect["ingredient_want"] == ["肉"]
    assert v2.raw_understanding == "想吃湖南菜+肉"
    assert v2.raw_text == "想吃湖南菜, 肉多一点"


def test_extract_v2_oil_enum_coerce_low_normal_high():
    """D-094.1: oil 枚举扩展到 {low, normal, high}."""
    for ok_val in ("low", "normal", "high"):
        parsed = {
            "redirect": _empty_redirect_for_test(),
            "constrain": {**_empty_constrain_for_test(), "oil": ok_val},
            "reference": None, "reject_previous": False,
            "raw_understanding": "test", "schema_version": "2.1",
        }
        with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
            v2 = extract_refine_intent_v2("test", use_llm=True)
        assert v2.constrain["oil"] == ok_val
        assert v2.oil == ok_val
    # 越界值丢弃
    parsed_bad = {
        "redirect": _empty_redirect_for_test(),
        "constrain": {**_empty_constrain_for_test(), "oil": "extra-heavy"},
        "reference": None, "reject_previous": False,
        "raw_understanding": "test", "schema_version": "2.1",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed_bad):
        v2 = extract_refine_intent_v2("test", use_llm=True)
    assert v2.constrain["oil"] is None


def test_extract_v2_wants_soup_bool_coerce():
    """D-094.1: wants_soup 接受 bool / 中文 truthy."""
    for src, expected in (
        (True, True), (False, False),
        ("是", True), ("不要", False), (None, False),
    ):
        parsed = {
            "redirect": _empty_redirect_for_test(),
            "constrain": {**_empty_constrain_for_test(), "wants_soup": src},
            "reference": None, "reject_previous": False,
            "raw_understanding": "test", "schema_version": "2.1",
        }
        with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
            v2 = extract_refine_intent_v2("test", use_llm=True)
        assert v2.constrain["wants_soup"] is expected, f"src={src!r}"


def test_extract_v2_price_band_enum_coerce():
    """D-094.1: price_band ∈ {cheap, normal, premium}."""
    for ok_val in ("cheap", "normal", "premium"):
        parsed = {
            "redirect": _empty_redirect_for_test(),
            "constrain": {**_empty_constrain_for_test(), "price_band": ok_val},
            "reference": None, "reject_previous": False,
            "raw_understanding": "test", "schema_version": "2.1",
        }
        with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
            v2 = extract_refine_intent_v2("test", use_llm=True)
        assert v2.constrain["price_band"] == ok_val
    # 越界值丢
    parsed_bad = {
        "redirect": _empty_redirect_for_test(),
        "constrain": {**_empty_constrain_for_test(), "price_band": "luxe"},
        "reference": None, "reject_previous": False,
        "raw_understanding": "test", "schema_version": "2.1",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed_bad):
        v2 = extract_refine_intent_v2("test", use_llm=True)
    assert v2.constrain["price_band"] is None


def test_extract_v2_staple_want_avoid_passes_through():
    """D-094.1: 主食偏好自由字符串."""
    parsed = {
        "redirect": {**_empty_redirect_for_test(),
                     "staple_want": ["米饭", "粥"], "staple_avoid": ["面"]},
        "constrain": _empty_constrain_for_test(),
        "reference": None, "reject_previous": False,
        "raw_understanding": "想吃米饭/粥, 不要面", "schema_version": "2.1",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("想吃米饭粥, 不要面", use_llm=True)
    assert v2.redirect["staple_want"] == ["米饭", "粥"]
    assert v2.redirect["staple_avoid"] == ["面"]


def test_extract_v2_constrain_coerce_price_max_string_number():
    """price_max 接受字符串数字 ('30 块' → 30)."""
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": {**_empty_constrain_for_test(),
                      "oil": "low", "price_max": "30 块"},
        "reference": None, "reject_previous": False,
        "raw_understanding": "30 块以内", "schema_version": "2.1",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("少油, 30 块以内", use_llm=True)
    assert v2.constrain["oil"] == "low"
    assert v2.constrain["price_max"] == 30


def test_extract_v2_cooking_method_avoid_enum_filter():
    """D-094: cooking_method_avoid 9 类枚举之一, 越界值丢弃."""
    parsed = {
        "redirect": {**_empty_redirect_for_test(),
                     "cooking_method_avoid": ["油炸", "烧烤", "煎", "油腻"]},
        "constrain": _empty_constrain_for_test(),
        "reference": None, "reject_previous": False,
        "raw_understanding": "test", "schema_version": "2.1",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("不要油炸/烧烤/煎/油腻", use_llm=True)
    assert v2.redirect["cooking_method_avoid"] == ["油炸", "煎"]
    assert "烧烤" in v2.raw_understanding
    assert "油腻" in v2.raw_understanding
    assert "丢弃越界" in v2.raw_understanding


def test_cooking_method_enum_constants():
    assert COOKING_METHOD_ENUM == frozenset({
        "油炸", "凉拌", "生", "炖", "炒", "煮", "蒸", "烤", "煎",
    })


def test_extract_v2_brand_avoid_passes_through():
    parsed = {
        "redirect": {**_empty_redirect_for_test(),
                     "brand_avoid": ["萨莉亚", "麦当劳"]},
        "constrain": _empty_constrain_for_test(),
        "reference": None, "reject_previous": False,
        "raw_understanding": "排除萨莉亚和麦当劳", "schema_version": "2.1",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("别给我萨莉亚和麦当劳", use_llm=True)
    assert v2.redirect["brand_avoid"] == ["萨莉亚", "麦当劳"]


def test_extract_v2_cuisine_candidates_expanded_passes_through():
    parsed = {
        "redirect": {**_empty_redirect_for_test(),
                     "cuisine_candidates_expanded": ["川菜", "湘菜", "贵州菜", "重庆菜"]},
        "constrain": _empty_constrain_for_test(),
        "reference": None, "reject_previous": False,
        "raw_understanding": "想吃辣→川/湘/贵/重", "schema_version": "2.1",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("想吃辣的", use_llm=True)
    assert v2.redirect["cuisine_candidates_expanded"] == ["川菜", "湘菜", "贵州菜", "重庆菜"]


def test_extract_v2_reference_relation_only_valid_enum():
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "reference": {"reference_meal_id": "meal-x", "relation": "invalid_rel"},
        "reject_previous": False,
        "raw_understanding": "test", "schema_version": "2.1",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("ref test", use_llm=True)
    assert v2.reference is None


def test_extract_v2_reference_relation_valid_enum_kept():
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "reference": {"reference_meal_id": "meal-2026-05-17-lunch",
                       "relation": "lighter"},
        "reject_previous": False,
        "raw_understanding": "比昨天清淡", "schema_version": "2.1",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("比昨天清淡", use_llm=True)
    assert v2.reference == {"reference_meal_id": "meal-2026-05-17-lunch",
                             "relation": "lighter"}


def test_extract_v2_reference_meal_id_invalid_format_dropped():
    """Codex M9: ref_meal_id 必须 alphanumeric/-/_ len 4-64, 否则设 None."""
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "reference": {"reference_meal_id": "昨天的那一顿", "relation": "lighter"},
        "reject_previous": False,
        "raw_understanding": "比昨天清淡", "schema_version": "2.1",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("比昨天清淡", use_llm=True)
    assert v2.reference == {"reference_meal_id": None, "relation": "lighter"}


def test_extract_v2_llm_call_uses_split_system_user_with_cache():
    """D-095: call_text 必须 system/user 拆 + cache_system=True."""
    captured = {}

    def _capturing_call_text(prompt, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return _fake_llm_resp(_json.dumps({
            "redirect": _empty_redirect_for_test(),
            "constrain": _empty_constrain_for_test(),
            "reference": None, "reject_previous": False,
            "raw_understanding": "test", "schema_version": "2.1",
        }))

    with patch("chisha.llm_client.call_text",
                side_effect=_capturing_call_text):
        extract_refine_intent_v2("用户输入", use_llm=True)

    assert captured["kwargs"].get("cache_system") is True
    assert "system" in captured["kwargs"]
    assert "用户输入" in captured["prompt"]      # user_msg 含 raw text
    assert "{INPUT_TEXT}" not in captured["kwargs"]["system"]  # system 不含模板占位

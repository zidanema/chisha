"""RefineIntentV2 schema + 安全带 单测 (D-094 真兑现版).

D-094 砍 5 字段后, 仍保留的 redirect slot:
  cuisine_want / cuisine_avoid / cuisine_candidates_expanded /
  ingredient_want / ingredient_avoid / brand_avoid / cooking_method_avoid

constrain slot 只保留 L2 真消费的两项: oil, price_max.

D-085 第二句 "字段空洞务实降级" 已废弃 by D-094 → 不再有 unsupported_in_recall.
"""
from __future__ import annotations

from chisha.refine_intent import RefineIntent, parse_refine_intent
from chisha.refine_intent_v2 import (
    COOKING_METHOD_ENUM,
    RefineIntentV2,
    extract_refine_intent_v2,
    validate_v2_schema,
)


def test_refine_v2_empty_default():
    v2 = RefineIntentV2()
    assert v2.schema_version == "2.0"
    assert v2.redirect["cuisine_want"] == []
    assert v2.redirect["ingredient_want"] == []
    assert v2.redirect["brand_avoid"] == []
    assert v2.redirect["cooking_method_avoid"] == []
    assert v2.redirect["cuisine_candidates_expanded"] == []
    # D-094: constrain 只剩 oil + price_max (functional / quality_floor 等已砍)
    assert v2.constrain == {"oil": None, "price_max": None}
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


def test_refine_v2_no_unsupported_in_recall_field():
    """D-094: 已砍 unsupported_in_recall 字段 (D-085 第二句失效).

    V2 dataclass 不再有此属性, to_log_dict 也不包含该 key.
    """
    v2 = RefineIntentV2()
    assert not hasattr(v2, "unsupported_in_recall")
    assert "unsupported_in_recall" not in v2.to_log_dict()


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


# ───────────────────────── follow-up: LLM 路径 + 安全带 ────────────────────

import json as _json
from unittest.mock import patch


def _fake_llm_resp(content: str) -> dict:
    """模拟 call_text 返回 dict."""
    return {"type": "text", "content": content, "stop_reason": "end_turn",
            "usage": {}, "model": "test", "raw_text": content}


def test_extract_v2_llm_happy_path_multi_slot():
    """LLM 返回完整多 slot JSON → 全字段清洗到位 (D-094 slot 清单)."""
    llm_out = _json.dumps({
        "redirect": {
            "cuisine_want": ["湖南菜"],
            "cuisine_avoid": [],
            "cuisine_candidates_expanded": [],
            "ingredient_want": ["肉"],
            "ingredient_avoid": [],
            "brand_avoid": [],
            "cooking_method_avoid": [],
        },
        "constrain": {"oil": None, "price_max": None},
        "reference": None,
        "reject_previous": False,
        "raw_understanding": "想吃湖南菜, 而且要肉量多",
        "schema_version": "2.0",
    })
    with patch("chisha.refine_intent_v2._llm_parse_v2",
                return_value=_json.loads(llm_out)):
        v2 = extract_refine_intent_v2("想吃湖南菜, 肉多一点", use_llm=True)
    assert v2.redirect["cuisine_want"] == ["湖南菜"]
    assert v2.redirect["ingredient_want"] == ["肉"]
    assert v2.raw_understanding == "想吃湖南菜, 而且要肉量多"
    assert v2.raw_text == "想吃湖南菜, 肉多一点"
    # D-094: 已砍字段不应出现在 V2 (即使 LLM 漏给, 框架不补回)
    assert "ingredient_synonyms" not in v2.redirect
    assert "food_form_avoid" not in v2.redirect


def test_extract_v2_constrain_coerce_number():
    """LLM 给 price_max=30, oil='low' → 清洗到位 (D-094 后 constrain 只剩这两项)."""
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": {"oil": "low", "price_max": "30 块"},
        "reference": None, "reject_previous": False,
        "raw_understanding": "少油, 30 块以内",
        "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("少油, 30 块以内", use_llm=True)
    assert v2.constrain["oil"] == "low"
    assert v2.constrain["price_max"] == 30  # 字符串数字提取
    # D-094: constrain 不再有 functional / quality_floor / delivery_only / max_distance_km
    assert set(v2.constrain.keys()) == {"oil", "price_max"}


def test_extract_v2_cooking_method_avoid_enum_filter():
    """D-094: cooking_method_avoid 必须是 9 类枚举之一, 越界值丢弃.

    LLM 偶尔输出"烧烤"/"煎炸"/"油腻" 等非枚举值, 框架在 _clean_parsed_to_v2 丢掉,
    防止 recall.py 拿到无意义字符串做硬过滤.
    """
    parsed = {
        "redirect": {
            "cuisine_want": [], "cuisine_avoid": [],
            "cuisine_candidates_expanded": [],
            "ingredient_want": [], "ingredient_avoid": [],
            "brand_avoid": [],
            # 混合 enum + 越界值: "油炸"/"煎" 留, "烧烤"/"油腻" 丢
            "cooking_method_avoid": ["油炸", "烧烤", "煎", "油腻"],
        },
        "constrain": {"oil": None, "price_max": None},
        "reference": None, "reject_previous": False,
        "raw_understanding": "test",
        "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("不要油炸/烧烤/煎/油腻", use_llm=True)
    assert v2.redirect["cooking_method_avoid"] == ["油炸", "煎"]


def test_cooking_method_enum_constants():
    """D-094: 9 类枚举 (codex audit dishes_tagged.json 实读)."""
    assert COOKING_METHOD_ENUM == frozenset({
        "油炸", "凉拌", "生", "炖", "炒", "煮", "蒸", "烤", "煎",
    })


def test_extract_v2_brand_avoid_passes_through():
    """D-094: brand_avoid 清洗保留 (recall.py 用作 venue 整店硬过滤)."""
    parsed = {
        "redirect": {
            "cuisine_want": [], "cuisine_avoid": [],
            "cuisine_candidates_expanded": [],
            "ingredient_want": [], "ingredient_avoid": [],
            "brand_avoid": ["萨莉亚", "麦当劳＆麦咖啡"],
            "cooking_method_avoid": [],
        },
        "constrain": {"oil": None, "price_max": None},
        "reference": None, "reject_previous": False,
        "raw_understanding": "排除萨莉亚和麦当劳",
        "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("别再给我萨莉亚和麦当劳", use_llm=True)
    assert v2.redirect["brand_avoid"] == ["萨莉亚", "麦当劳＆麦咖啡"]


def test_extract_v2_cuisine_candidates_expanded_passes_through():
    """D-094: cuisine_candidates_expanded 清洗保留 (recall.py 进 bucket_soft)."""
    parsed = {
        "redirect": {
            "cuisine_want": [], "cuisine_avoid": [],
            "cuisine_candidates_expanded": ["川菜", "湘菜", "贵州菜", "重庆菜"],
            "ingredient_want": [], "ingredient_avoid": [],
            "brand_avoid": [], "cooking_method_avoid": [],
        },
        "constrain": {"oil": None, "price_max": None},
        "reference": None, "reject_previous": False,
        "raw_understanding": "想吃辣, 推断为川/湘/贵/重",
        "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("想吃辣的", use_llm=True)
    assert v2.redirect["cuisine_candidates_expanded"] == ["川菜", "湘菜", "贵州菜", "重庆菜"]


def test_extract_v2_reference_relation_only_valid_enum():
    """reference.relation 不在枚举内 → reference 整体 None."""
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "reference": {"reference_meal_id": "m1", "relation": "invalid_rel"},
        "reject_previous": False,
        "raw_understanding": "test", "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("ref test", use_llm=True)
    assert v2.reference is None


def test_extract_v2_reference_relation_valid_enum_kept():
    """Codex M9: ref_meal_id 合法格式 (alphanumeric/-/_ len 4-64) 才保留."""
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "reference": {"reference_meal_id": "meal-2026-05-17-lunch",
                       "relation": "lighter"},
        "reject_previous": False,
        "raw_understanding": "比昨天清淡", "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("比昨天清淡", use_llm=True)
    assert v2.reference == {"reference_meal_id": "meal-2026-05-17-lunch",
                             "relation": "lighter"}


def test_extract_v2_reference_meal_id_invalid_format_dropped():
    """Codex M9: ref_meal_id 是 raw 文本 ("昨天的那一顿") → 设 None, relation 保留."""
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "reference": {"reference_meal_id": "昨天的那一顿",
                       "relation": "lighter"},
        "reject_previous": False,
        "raw_understanding": "比昨天清淡", "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("比昨天清淡", use_llm=True)
    assert v2.reference == {"reference_meal_id": None, "relation": "lighter"}


def test_extract_v2_llm_returns_none_falls_back_to_legacy():
    """安全带 #1: LLM 返 None (调失败) → 走 V1 from_legacy, 不崩."""
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=None):
        v2 = extract_refine_intent_v2("想吃湘菜", use_llm=True)
    assert v2.raw_text == "想吃湘菜"
    assert "V1 兜底" in v2.raw_understanding
    # V1 rule_parse 能识别"湘菜" → 应填到 redirect.cuisine_want
    assert v2.redirect["cuisine_want"]


def test_extract_v2_llm_call_uses_split_system_user_with_cache():
    """D-095: call_text 必须按 system/user 拆调用 + cache_system=True.

    system 含模板固定指令 (不含 INPUT_TEXT), user 含真实用户文本.
    trace_collector 字段同步落实际发给 LLM 的内容.
    """
    captured = {}

    def _capturing_call_text(prompt, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return _fake_llm_resp(_json.dumps({
            "redirect": _empty_redirect_for_test(),
            "constrain": _empty_constrain_for_test(),
            "reference": None, "reject_previous": False,
            "raw_understanding": "ok", "schema_version": "2.0",
        }))

    trace: dict = {}
    with patch("chisha.llm_client.call_text", _capturing_call_text), \
         patch("chisha.llm_client.has_llm_key", return_value=True):
        extract_refine_intent_v2("想吃辣的", use_llm=True, trace_collector=trace)

    kw = captured["kwargs"]
    # 1) cache_system=True 必须开
    assert kw.get("cache_system") is True
    # 2) system 必须存在, 且**不含 {INPUT_TEXT} 占位符** (拆点正确)
    assert kw.get("system"), "system 参数缺失"
    assert "{INPUT_TEXT}" not in kw["system"]
    # 2b) 用户真实文本**不能**漏进 system (否则 ephemeral cache 命中率瓦解)
    assert "想吃辣的" not in kw["system"]
    # 3) user prompt 必须含真实 refine 文本
    assert "想吃辣的" in captured["prompt"]
    assert "{INPUT_TEXT}" not in captured["prompt"]
    # 4) 调用超参不变
    assert kw.get("max_tokens") == 1024
    assert kw.get("temperature") == 0.0
    assert kw.get("json_mode") is True
    # 5) trace 字段 1:1 对齐实际发出的内容
    assert trace["system_prompt_full"] == kw["system"]
    assert trace["user_message_full"] == captured["prompt"]
    assert "{INPUT_TEXT}" not in trace["system_prompt_full"]
    assert "想吃辣的" in trace["user_message_full"]


def test_extract_v2_llm_returns_bad_json_falls_back():
    """安全带: LLM 返坏文本不含 JSON → _llm_parse_v2 返 None → 降级 V1."""
    def _fake_call_text(*args, **kwargs):
        return _fake_llm_resp("这就是一行裸文本, 没有花括号")
    with patch("chisha.llm_client.call_text", _fake_call_text), \
         patch("chisha.llm_client.has_llm_key", return_value=True):
        v2 = extract_refine_intent_v2("想吃日料")
    assert v2.raw_text == "想吃日料"
    assert "V1 兜底" in v2.raw_understanding
    # V1 rule_parse 应识别日料 → cuisine_want
    assert "日料" in v2.redirect["cuisine_want"]


def test_extract_v2_llm_returns_truncated_json_falls_back():
    """安全带: JSON 写一半就截断 → json.loads 抛 → _llm_parse_v2 返 None → 降级."""
    def _fake_call_text(*args, **kwargs):
        return _fake_llm_resp('{"redirect": {"cuisine_want": ["日料"')
    with patch("chisha.llm_client.call_text", _fake_call_text), \
         patch("chisha.llm_client.has_llm_key", return_value=True):
        v2 = extract_refine_intent_v2("想吃日料")
    assert v2.raw_text == "想吃日料"
    assert "V1 兜底" in v2.raw_understanding


def test_extract_v2_llm_schema_mismatch_falls_back():
    """安全带: LLM 返 JSON 但 schema 不符 (redirect 是 list) → 降级."""
    bad = {
        "redirect": ["should be dict not list"],
        "constrain": _empty_constrain_for_test(),
        "reference": None, "reject_previous": False,
        "raw_understanding": "bad shape", "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=bad):
        v2 = extract_refine_intent_v2("想吃辣的", use_llm=True)
    assert "V1 兜底" in v2.raw_understanding
    # V1 rule_parse 应抓到 "辣" 的 flavor (在 legacy_v1)
    assert v2.legacy_v1.get("flavor_tags") or v2.legacy_v1.get("raw_flavor")


def test_extract_v2_llm_call_raises_exception_falls_back():
    """安全带: call_text 直接抛 → _llm_parse_v2 catches → None → 降级."""
    def _boom(*args, **kwargs):
        raise TimeoutError("LLM timeout")
    with patch("chisha.llm_client.call_text", _boom), \
         patch("chisha.llm_client.has_llm_key", return_value=True):
        v2 = extract_refine_intent_v2("想吃湘菜")
    assert v2.raw_text == "想吃湘菜"
    assert v2.redirect["cuisine_want"]  # V1 rule_parse 识别湘菜


def test_extract_v2_partial_llm_output_filled_with_defaults():
    """LLM 只给了 redirect.cuisine_want, 其余字段缺 → 用 default 补足."""
    partial = {
        "redirect": {"cuisine_want": ["粤菜"]},
        "raw_understanding": "想吃粤菜",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=partial):
        v2 = extract_refine_intent_v2("想吃粤菜", use_llm=True)
    assert v2.redirect["cuisine_want"] == ["粤菜"]
    # 其他 slot 全空
    assert v2.redirect["cuisine_avoid"] == []
    assert v2.constrain["oil"] is None
    assert v2.reject_previous is False


def test_extract_v2_use_llm_false_still_returns_legacy_v2():
    """use_llm=False 强制 → 不调 LLM 直接走 V1 from_legacy."""
    v2 = extract_refine_intent_v2("想吃湘菜, 肉多", use_llm=False)
    assert v2.raw_text == "想吃湘菜, 肉多"
    assert v2.redirect["cuisine_want"]  # V1 rule_parse 抓得到
    assert v2.legacy_v1.get("portion") or v2.legacy_v1.get("ingredient_want") or \
        v2.redirect["ingredient_want"]


def test_extract_v2_trace_dual_store_has_three_fields():
    """trace 双存 (安全带 #2): raw_text + 结构化 + raw_understanding 三份都在."""
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "reference": None, "reject_previous": False,
        "raw_understanding": "LLM 听到了想吃辣",
        "schema_version": "2.0",
    }
    parsed["redirect"]["cuisine_candidates_expanded"] = ["川菜", "湘菜"]
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("想吃辣的", use_llm=True)
    d = v2.to_log_dict()
    assert d["raw_text"] == "想吃辣的"
    assert d["raw_understanding"] == "LLM 听到了想吃辣"
    assert d["redirect"]["cuisine_candidates_expanded"] == ["川菜", "湘菜"]
    # 三份都进了 to_log_dict, trace 持久化时一锅写


def test_extract_v2_missing_required_keys_falls_back():
    """Codex H6: LLM 漏 schema_version / redirect / constrain / raw_understanding
    任一必填字段 → 走 V1 兜底 (不 setdefault 静默补)."""
    # 1. 漏 schema_version
    bad_no_sv = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "raw_understanding": "test",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=bad_no_sv):
        v2 = extract_refine_intent_v2("想吃湘菜", use_llm=True)
    assert "schema_version" in v2.raw_understanding or "兜底" in v2.raw_understanding

    # 2. 漏 redirect
    bad_no_redirect = {
        "schema_version": "2.0",
        "constrain": _empty_constrain_for_test(),
        "raw_understanding": "test",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2",
                return_value=bad_no_redirect):
        v2 = extract_refine_intent_v2("想吃湘菜", use_llm=True)
    assert "redirect" in v2.raw_understanding or "兜底" in v2.raw_understanding

    # 3. 漏 raw_understanding (体现"LLM 真理解 schema"的必填)
    bad_no_ru = {
        "schema_version": "2.0",
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=bad_no_ru):
        v2 = extract_refine_intent_v2("想吃湘菜", use_llm=True)
    assert "raw_understanding" in v2.raw_understanding or "兜底" in v2.raw_understanding


def test_clean_str_list_rejects_non_scalar():
    """Codex M6: list 内 dict/list 容器 → 丢弃, 不 str() 强转污染 trace."""
    from chisha.refine_intent_v2 import _clean_str_list
    assert _clean_str_list(["湘菜", {"foo": "bar"}, "川菜", ["nested"]]) == ["湘菜", "川菜"]
    assert _clean_str_list(["a", 1, 2.5, True, None]) == ["a", "1", "2.5", "True"]


def test_coerce_bool_or_null_chinese():
    """Codex M7: 中文是/否/对/不/要/不要 都能映射."""
    from chisha.refine_intent_v2 import _coerce_bool_or_null
    assert _coerce_bool_or_null("是") is True
    assert _coerce_bool_or_null("对") is True
    assert _coerce_bool_or_null("要") is True
    assert _coerce_bool_or_null("否") is False
    assert _coerce_bool_or_null("不") is False
    assert _coerce_bool_or_null("不要") is False
    assert _coerce_bool_or_null("true") is True
    assert _coerce_bool_or_null("false") is False
    assert _coerce_bool_or_null("乱填") is None
    assert _coerce_bool_or_null(None) is None
    assert _coerce_bool_or_null(True) is True


def test_coerce_number_or_null_chinese():
    """Codex M8: 中文数字最小映射 (兜底, prompt 已强制阿拉伯)."""
    from chisha.refine_intent_v2 import _coerce_number_or_null
    # 阿拉伯优先
    assert _coerce_number_or_null("30 块以内") == 30
    assert _coerce_number_or_null("3.5 公里") == 3.5
    # 中文兜底 (必须整串都是中文数字 + 可选单位)
    assert _coerce_number_or_null("三十") == 30
    assert _coerce_number_or_null("三十五块") == 35
    assert _coerce_number_or_null("十") == 10
    assert _coerce_number_or_null("一百") == 100
    # 不识别 → None (helper 兜底就这么粗, 复杂表达式由 prompt 约束 LLM 输阿拉伯)
    assert _coerce_number_or_null("便宜点") is None
    assert _coerce_number_or_null("几十") is None  # 前缀非中文数字, 拒
    assert _coerce_number_or_null("两千") is None  # 千位未支持, 整串不匹配
    assert _coerce_number_or_null(None) is None
    assert _coerce_number_or_null(True) is None  # bool 不算 number


def test_v2_mode_env_off(tmp_path, monkeypatch):
    """Codex H7: CHISHA_REFINE_V2_TRACE=off → V2 不调 LLM, response 给 placeholder."""
    monkeypatch.setenv("CHISHA_REFINE_V2_TRACE", "off")
    # 跳到 refine 入口验证. 不调真 refine (太重), 单测 _v2_mode 即可.
    from chisha.refine import _v2_mode
    assert _v2_mode() == "off"


def test_v2_mode_env_async(monkeypatch):
    """Codex H7: CHISHA_REFINE_V2_TRACE=async → 进 fire-and-forget 分支."""
    monkeypatch.setenv("CHISHA_REFINE_V2_TRACE", "async")
    from chisha.refine import _v2_mode
    assert _v2_mode() == "async"


def test_v2_mode_default_sync(monkeypatch):
    """无 env → sync (兼容老行为, eval / 开发用)."""
    monkeypatch.delenv("CHISHA_REFINE_V2_TRACE", raising=False)
    from chisha.refine import _v2_mode
    assert _v2_mode() == "sync"


def _empty_redirect_for_test() -> dict:
    """test helper, D-094 后 7 个 slot (砍了 ingredient_synonyms + food_form_avoid)."""
    return {
        "cuisine_want": [], "cuisine_avoid": [],
        "cuisine_candidates_expanded": [],
        "ingredient_want": [], "ingredient_avoid": [],
        "brand_avoid": [], "cooking_method_avoid": [],
    }


def _empty_constrain_for_test() -> dict:
    """D-094 后只剩 oil + price_max."""
    return {"oil": None, "price_max": None}


# ─────────────── T-PR-02: T-PR-01 prompt boundary守门 (mocked LLM) ───────────
# 用 mocked `_llm_parse_v2` 模拟 T-PR-01 prompt 期望的"正确 LLM 输出",
# 守 V2 清洗 + schema 接受这些 case 不破. 不调真 LLM, CI 友好.
# 真 LLM prompt 效果由 tests/refine_eval/eval_set.jsonl + scripts/refine_eval_runner.py 守.


def test_refine_v2_prompt_boundary_flavor_conflict():
    """T-PR-01 P0-E3 + spec §What 1: '想吃辣但别太辣' (冲突表达)
    → 对应 slot 全空 + raw_understanding 含冲突短语 (prompt line 144 example).
    """
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "reference": None,
        "reject_previous": False,
        "raw_understanding": "冲突表达: 想吃辣但不要太辣, 不擅自扩展辣味菜系, 交给 L3 把握",
        "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("想吃辣但别太辣", use_llm=True)
    # 冲突表达 → flavor / cuisine_candidates_expanded 等全空 (Faithful Refine 不脑补)
    assert v2.redirect["cuisine_candidates_expanded"] == []
    assert v2.redirect["cuisine_want"] == []
    assert v2.redirect["cuisine_avoid"] == []
    # raw_understanding 含"冲突"短语 (T-PR-01 prompt 改动 P0-E3 守门)
    assert "冲突" in v2.raw_understanding


def test_refine_v2_prompt_boundary_no_pseudo_cuisine_expanded():
    """D-094 第一原则 + spec §What 2: '下午要睡觉' (无明确食物诉求)
    → cuisine_candidates_expanded 应为空 (不脑补"睡前 → 清淡菜").

    旧 functional.low_caffeine 字段已砍, 此 case 改测 cuisine 不脑补.
    """
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "reference": None,
        "reject_previous": False,
        "raw_understanding": "用户提到下午要睡觉, 未明示食物诉求, 不擅自推断菜系",
        "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("下午要睡觉", use_llm=True)
    assert v2.redirect["cuisine_candidates_expanded"] == []
    assert v2.redirect["cuisine_want"] == []


def test_refine_v2_prompt_boundary_brand_avoid_explicit_vs_implicit():
    """D-094 第一原则:
    - '别再给我萨莉亚' (明示 brand) → brand_avoid=['萨莉亚']
    - '今天加班好累' (无关联场景) → brand_avoid=[] (不脑补 brand 偏好)

    旧 delivery_only 字段已砍, 此 case 改测 brand_avoid 第一原则.
    """
    # case 1: 明示
    redirect_explicit = _empty_redirect_for_test()
    redirect_explicit["brand_avoid"] = ["萨莉亚"]
    parsed_explicit = {
        "redirect": redirect_explicit,
        "constrain": _empty_constrain_for_test(),
        "reference": None,
        "reject_previous": False,
        "raw_understanding": "用户明示别再给萨莉亚, 已抽出 brand_avoid",
        "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed_explicit):
        v2 = extract_refine_intent_v2("别再给我萨莉亚", use_llm=True)
    assert v2.redirect["brand_avoid"] == ["萨莉亚"]

    # case 2: 无关联场景陈述, 不脑补
    parsed_implicit = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "reference": None,
        "reject_previous": False,
        "raw_understanding": "用户提到加班场景, 但未表达品牌/菜系诉求, 不擅自推断",
        "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed_implicit):
        v2 = extract_refine_intent_v2("今天加班好累", use_llm=True)
    assert v2.redirect["brand_avoid"] == []


def test_refine_v2_prompt_boundary_subset_reject_keeps_cuisine_avoid():
    """T-PR-01 P1-3 + spec §What 5: '这些广东菜都不想吃, 换湖南菜吧'
    (子类否定 + 换菜系, 非全推翻)
    → reject_previous=False + cuisine_avoid=["广东菜"] + cuisine_want=["湖南菜"].
    Prompt line 72 example 显式要求.
    """
    redirect = _empty_redirect_for_test()
    redirect["cuisine_avoid"] = ["广东菜"]
    redirect["cuisine_want"] = ["湖南菜"]
    parsed = {
        "redirect": redirect,
        "constrain": _empty_constrain_for_test(),
        "reference": None,
        "reject_previous": False,
        "raw_understanding": "用户拒绝了上一轮的广东菜, 换成湖南菜, 子类否定非全推翻",
        "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("这些广东菜都不想吃, 换湖南菜吧", use_llm=True)
    assert v2.reject_previous is False
    assert "广东菜" in v2.redirect["cuisine_avoid"]
    assert "湖南菜" in v2.redirect["cuisine_want"]


def test_refine_v2_prompt_boundary_full_reject_sets_flag():
    """T-PR-01 P1-8 + spec §What 6: '上一组全不要, 重来' (明确推翻)
    → reject_previous=True (LLM 应识别完整重置短语).
    """
    parsed = {
        "redirect": _empty_redirect_for_test(),
        "constrain": _empty_constrain_for_test(),
        "reference": None,
        "reject_previous": True,
        "raw_understanding": "用户明确推翻上一组结果, 要求重新生成",
        "schema_version": "2.0",
    }
    with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):
        v2 = extract_refine_intent_v2("上一组全不要, 重来", use_llm=True)
    assert v2.reject_previous is True

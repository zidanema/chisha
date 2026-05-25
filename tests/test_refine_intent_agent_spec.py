"""T3: D-074 AI-friendly refine intent spec/apply 单测.

覆盖 build_extract_spec (信封) + apply_intent_response (Faithful Refine 守卫),
重点测 raw_text 只来自 CLI 注入、忽略 agent 回传 (codex #5).
"""
from __future__ import annotations

from chisha.agent_protocol import CorrelationId
from chisha.refine_intent_v2 import (
    apply_intent_response,
    build_extract_spec,
)


def _valid_parsed(**overrides) -> dict:
    base = {
        "redirect": {
            "cuisine_want": ["湖南菜"], "cuisine_avoid": [],
            "cuisine_candidates_expanded": [], "ingredient_want": ["肉"],
            "ingredient_avoid": [], "brand_avoid": [],
            "cooking_method_avoid": [], "staple_want": [], "staple_avoid": [],
        },
        "constrain": {"oil": None, "price_max": None, "price_band": None,
                      "wants_soup": False},
        "reference": None,
        "reject_previous": False,
        "raw_understanding": "想吃湖南菜, 肉多",
        "schema_version": "2.1",
    }
    base.update(overrides)
    return base


# ─────────────────────── build_extract_spec ───────────────────────

def test_build_extract_spec_envelope():
    cid = CorrelationId("sid_x", "R2", "extract")
    spec = build_extract_spec("想吃湖南菜肉多点", correlation_id=cid)
    assert spec["operation_kind"] == "extract"
    assert spec["output_mode"] == "text_json"
    assert "tools" not in spec
    assert "json_schema" in spec
    assert spec["correlation_id"] == "sid_x::R2::extract"
    # user message 含原文 + 模板尾
    assert "想吃湖南菜肉多点" in spec["messages"][0]["content"]
    assert "输出 JSON" in spec["messages"][0]["content"]
    # system = prompt 模板头 (含 schema 字段闭包说明)
    assert "字段闭包" in spec["system"]
    # required_validation 明示 raw_text 守卫
    assert any("raw_text" in r for r in spec["required_validation"])


def test_build_extract_spec_json_schema_shape():
    cid = CorrelationId("sid_x", "R2", "extract")
    spec = build_extract_spec("x", correlation_id=cid)
    schema = spec["json_schema"]
    assert schema["properties"]["constrain"]["properties"]["oil"]["enum"]
    assert "cooking_method_avoid" in schema["properties"]["redirect"]["properties"]
    assert "schema_version" in schema["required"]


# ─────────────────────── apply_intent_response ───────────────────────

def test_apply_valid_intent():
    intent, disc = apply_intent_response(_valid_parsed(), raw_text="想吃湖南菜肉多点")
    assert intent.cuisine_want == ["湖南菜"]
    assert intent.ingredient_want == ["肉"]
    assert intent.raw_text == "想吃湖南菜肉多点"
    assert disc["status"] == "ok"
    assert disc["raw_understanding"] == "想吃湖南菜, 肉多"


def test_apply_ignores_agent_raw_text():
    """关键守卫 (codex #5): agent 回传里塞 raw_text, 必须被忽略, 用 CLI 注入的原话."""
    parsed = _valid_parsed(raw_text="AGENT 伪造的原话")
    intent, _ = apply_intent_response(parsed, raw_text="用户真实原话")
    assert intent.raw_text == "用户真实原话"
    assert intent.raw_text != "AGENT 伪造的原话"


def test_apply_parsed_none_falls_back():
    intent, disc = apply_intent_response(None, raw_text="想清淡")
    assert intent.is_empty()
    assert intent.raw_text == "想清淡"
    assert disc["status"] == "fallback"
    assert "解析失败" in disc["reason"]


def test_apply_missing_required_key_falls_back():
    bad = _valid_parsed()
    del bad["constrain"]
    intent, disc = apply_intent_response(bad, raw_text="x")
    assert intent.is_empty()
    assert disc["status"] == "fallback"
    assert "漏必填字段" in disc["reason"]


def test_apply_bad_schema_version_falls_back():
    bad = _valid_parsed(schema_version="1.0")
    intent, disc = apply_intent_response(bad, raw_text="x")
    assert intent.is_empty()
    assert disc["status"] == "fallback"


def test_apply_cooking_method_enum_closure():
    """agent 给越界 cooking_method → chisha 丢弃 (确定性守卫)."""
    parsed = _valid_parsed()
    parsed["redirect"]["cooking_method_avoid"] = ["油炸", "烧烤"]  # 烧烤越界
    intent, _ = apply_intent_response(parsed, raw_text="别油炸别烧烤")
    assert intent.cooking_method_avoid == ["油炸"]
    assert "烧烤" in intent.raw_understanding  # 越界值拼到 raw_understanding 诚实尾巴


def test_apply_non_dict_falls_back():
    intent, disc = apply_intent_response("not a dict", raw_text="x")  # type: ignore[arg-type]
    assert intent.is_empty()
    assert disc["status"] == "fallback"


def test_apply_ignores_nonstr_agent_raw_text(capsys):
    """codex #c 修复: agent 回传非 str raw_text 必须被无条件忽略, 不能让 validate
    失败把本来合法的 intent 误降级."""
    parsed = _valid_parsed(raw_text=12345)  # 非法 raw_text
    intent, disc = apply_intent_response(parsed, raw_text="想吃湖南菜")
    assert disc["status"] == "ok"            # 没被降级
    assert intent.cuisine_want == ["湖南菜"]  # 合法字段保留
    assert intent.raw_text == "想吃湖南菜"     # 用 CLI 注入的原话


def test_apply_disclosure_carries_raw_understanding():
    """设计 §5.4: raw_understanding 当用户可见 disclosure 弹出."""
    parsed = _valid_parsed(raw_understanding="清淡=低油; '那家店'没认出已忽略")
    _, disc = apply_intent_response(parsed, raw_text="清淡点, 那家店")
    assert disc["raw_understanding"] == "清淡=低油; '那家店'没认出已忽略"

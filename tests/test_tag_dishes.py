"""scripts.tag_dishes 单测 (mock LLM 客户端).

只测纯函数 + tag_batch 的重试/容错路径; 不发任何 LLM 请求.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts import tag_dishes


# ---------- extract_json_array ----------

def test_extract_json_array_plain():
    text = '[{"dish_id":"d1","x":1}]'
    assert tag_dishes.extract_json_array(text) == [{"dish_id": "d1", "x": 1}]


def test_extract_json_array_with_code_fence():
    text = '```json\n[{"dish_id":"d1"}]\n```'
    assert tag_dishes.extract_json_array(text) == [{"dish_id": "d1"}]


def test_extract_json_array_with_prose_around():
    text = 'sure thing!\n[{"a":1},{"a":2}]\nthats all'
    assert tag_dishes.extract_json_array(text) == [{"a": 1}, {"a": 2}]


def test_extract_json_array_no_array_raises():
    with pytest.raises(ValueError):
        tag_dishes.extract_json_array("nothing here")


def test_extract_json_array_malformed_raises():
    with pytest.raises(json.JSONDecodeError):
        tag_dishes.extract_json_array('[{"a": 1, ]')


# ---------- validate_record ----------

def _good_record(dish_id="d_001"):
    """v3 (D-032) record: 8 旧字段 + 5 新字段 (dish_role / processed_meat_flag /
    sweet_sauce_level / wetness / grain_type)."""
    return {
        "dish_id": dish_id,
        "canonical_name": "测试",
        "cuisine": "湘菜",
        "main_ingredient_type": "红肉",
        "cooking_method": "煮",
        "oil_level": 3,
        "protein_grams_estimate": 30,
        "vegetable_ratio_estimate": 0.2,
        "is_complete_meal": False,
        "spicy_level": 1,
        "dish_role": "主菜",
        "processed_meat_flag": False,
        "sweet_sauce_level": 0,
        "wetness": 2,
        "grain_type": "无",
        "tags": ["高蛋白"],
    }


def test_validate_record_ok():
    assert tag_dishes.validate_record(_good_record()) == []


def test_validate_record_missing_field():
    r = _good_record()
    del r["oil_level"]
    issues = tag_dishes.validate_record(r)
    assert any("missing" in i for i in issues)


def test_validate_record_oil_level_invalid():
    r = _good_record()
    r["oil_level"] = 9
    issues = tag_dishes.validate_record(r)
    assert any("oil_level" in i for i in issues)


def test_validate_record_spicy_level_invalid():
    r = _good_record()
    r["spicy_level"] = 5
    issues = tag_dishes.validate_record(r)
    assert any("spicy_level" in i for i in issues)


def test_validate_record_veg_ratio_invalid():
    r = _good_record()
    r["vegetable_ratio_estimate"] = 1.5
    issues = tag_dishes.validate_record(r)
    assert any("vegetable_ratio_estimate" in i for i in issues)


# ---------- build_input_payload ----------

def test_build_input_payload_includes_price_and_restaurant():
    rest_by_id = {"r_001": {"name": "测试餐厅", "category": "湘菜"}}
    batch = [{
        "dish_id": "d_001_001",
        "restaurant_id": "r_001",
        "raw_name": "辣椒炒肉",
        "price": 32.0,
        "monthly_sales": 100,
        "category_raw": "热菜",
    }]
    payload = json.loads(tag_dishes.build_input_payload(rest_by_id, batch))
    assert payload[0]["dish_id"] == "d_001_001"
    assert payload[0]["raw_name"] == "辣椒炒肉"
    assert payload[0]["restaurant_name"] == "测试餐厅"
    assert payload[0]["price"] == 32.0  # 关键: 必须把 price 喂给 LLM
    assert payload[0]["category_raw"] == "热菜"


# ---------- tag_batch (mock LLM) ----------

def _llm_response(records):
    """D-047: call_text 改返回 dict."""
    return _llm_response_text(json.dumps(records, ensure_ascii=False))


def _llm_response_text(text: str) -> dict:
    return {
        "type": "text",
        "content": text,
        "stop_reason": "end_turn",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                  "cached_tokens": 0, "cache_write_tokens": 0},
        "model": "test",
        "raw_text": text,
    }


def test_tag_batch_first_attempt_ok(monkeypatch):
    """LLM 一把成功 → tag_batch 返回输入条数对应的 tagged."""
    rest = {"r_001": {"name": "T", "category": "湘菜"}}
    batch = [{
        "dish_id": "d1", "restaurant_id": "r_001", "raw_name": "n1",
        "price": 10, "monthly_sales": 5, "category_raw": "",
    }]
    expected = [_good_record(dish_id="d1")]

    monkeypatch.setattr(tag_dishes, "call_text",
                        lambda *a, **kw: _llm_response(expected))
    monkeypatch.setattr(tag_dishes.time, "sleep", lambda *_: None)

    out = tag_dishes.tag_batch(rest, batch, "PROMPT {INPUT_DISHES_JSON}")
    assert len(out) == 1
    assert out[0]["dish_id"] == "d1"


def test_tag_batch_passes_temperature_zero(monkeypatch):
    """打标必须 temperature=0 (DESIGN §4.1 坑 2)."""
    captured = {}

    def fake_call_text(prompt, **kwargs):
        captured.update(kwargs)
        return _llm_response([_good_record(dish_id="d1")])

    rest = {"r_001": {"name": "T", "category": "湘菜"}}
    batch = [{"dish_id": "d1", "restaurant_id": "r_001", "raw_name": "n",
              "price": 10, "monthly_sales": 0, "category_raw": ""}]

    monkeypatch.setattr(tag_dishes, "call_text", fake_call_text)
    monkeypatch.setattr(tag_dishes.time, "sleep", lambda *_: None)
    tag_dishes.tag_batch(rest, batch, "{INPUT_DISHES_JSON}")
    assert captured.get("temperature") == 0.0


def test_tag_batch_count_mismatch_retries(monkeypatch):
    """LLM 返回条数不对 → 重试; 3 次后失败."""
    rest = {"r_001": {"name": "T", "category": "湘菜"}}
    batch = [{"dish_id": "d1", "restaurant_id": "r_001", "raw_name": "n",
              "price": 10, "monthly_sales": 0, "category_raw": ""}]

    calls = {"n": 0}

    def fake_call_text(*_a, **_kw):
        calls["n"] += 1
        return _llm_response([])  # 永远不对

    monkeypatch.setattr(tag_dishes, "call_text", fake_call_text)
    monkeypatch.setattr(tag_dishes.time, "sleep", lambda *_: None)

    with pytest.raises(RuntimeError):
        tag_dishes.tag_batch(rest, batch, "{INPUT_DISHES_JSON}",
                             max_retries=3)
    assert calls["n"] == 3


def test_tag_batch_recovers_on_second_attempt(monkeypatch):
    """第一次坏 JSON, 第二次成功 → 返回正常."""
    rest = {"r_001": {"name": "T", "category": "湘菜"}}
    batch = [{"dish_id": "d1", "restaurant_id": "r_001", "raw_name": "n",
              "price": 10, "monthly_sales": 0, "category_raw": ""}]

    responses = iter([
        _llm_response_text("garbage no json"),
        _llm_response([_good_record(dish_id="d1")]),
    ])
    monkeypatch.setattr(tag_dishes, "call_text",
                        lambda *a, **kw: next(responses))
    monkeypatch.setattr(tag_dishes.time, "sleep", lambda *_: None)

    out = tag_dishes.tag_batch(rest, batch, "{INPUT_DISHES_JSON}")
    assert out[0]["dish_id"] == "d1"


def test_tag_batch_invalid_record_retries(monkeypatch):
    """第一次返回 oil_level=9, 第二次合法."""
    rest = {"r_001": {"name": "T", "category": "湘菜"}}
    batch = [{"dish_id": "d1", "restaurant_id": "r_001", "raw_name": "n",
              "price": 10, "monthly_sales": 0, "category_raw": ""}]

    bad = _good_record(dish_id="d1")
    bad["oil_level"] = 9
    good = _good_record(dish_id="d1")
    responses = iter([_llm_response([bad]), _llm_response([good])])

    monkeypatch.setattr(tag_dishes, "call_text",
                        lambda *a, **kw: next(responses))
    monkeypatch.setattr(tag_dishes.time, "sleep", lambda *_: None)

    out = tag_dishes.tag_batch(rest, batch, "{INPUT_DISHES_JSON}")
    assert out[0]["oil_level"] == 3


# ---------- merge_into_output ----------

def test_merge_into_output_combines_raw_and_tagged():
    raw_idx = {
        "d1": {
            "dish_id": "d1", "restaurant_id": "r_001",
            "raw_name": "测试菜", "price": 28.5, "monthly_sales": 80,
            "category_raw": "热菜",
        }
    }
    tagged = [_good_record(dish_id="d1")]
    out = tag_dishes.merge_into_output(raw_idx, tagged)
    assert len(out) == 1
    o = out[0]
    assert o["dish_id"] == "d1"
    assert o["restaurant_id"] == "r_001"
    assert o["raw_name"] == "测试菜"
    assert o["price"] == 28.5
    assert o["monthly_sales"] == 80
    assert o["nutrition_profile"]["oil_level"] == 3
    assert o["metadata"]["tag_version"] == "v3"
    assert o["metadata"]["is_available"] is True


def test_merge_into_output_skips_unknown_dish_id(capsys):
    raw_idx = {"d1": {
        "dish_id": "d1", "restaurant_id": "r_001",
        "raw_name": "x", "price": 1, "monthly_sales": 0,
        "category_raw": None,
    }}
    tagged = [_good_record(dish_id="d_ghost")]  # raw 里不存在
    out = tag_dishes.merge_into_output(raw_idx, tagged)
    assert out == []


def test_merge_output_passes_schema(monkeypatch):
    """merge 出的对象必须 100% 通过 chisha.schemas 校验."""
    from chisha.schemas import validate_dishes_tagged
    raw_idx = {"d1": {
        "dish_id": "d1", "restaurant_id": "r_001",
        "raw_name": "测试", "price": 30.0, "monthly_sales": 50,
        "category_raw": None,
    }}
    out = tag_dishes.merge_into_output(raw_idx, [_good_record("d1")])
    validate_dishes_tagged(out)

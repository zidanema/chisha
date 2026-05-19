"""D-089-S1: trace_helpers.py 单元测试.

覆盖四个 helper 的 normal / edge / empty 路径:
- normalize_usage_fields
- serialize_llm_call_trace
- build_l3_trace_from_collector
- build_refine_round_payload
"""
from __future__ import annotations

from chisha.trace_helpers import (
    normalize_usage_fields,
    serialize_llm_call_trace,
    build_l3_trace_from_collector,
    build_refine_round_payload,
)


class TestNormalizeUsageFields:
    def test_provider_naming_to_anthropic_style(self):
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "cached_tokens": 30,
            "cache_write_tokens": 10,
            "cost": 0.001,  # 多余字段不该出现
        }
        out = normalize_usage_fields(usage)
        assert out == {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 30,
            "cache_creation_input_tokens": 10,
        }

    def test_anthropic_style_passthrough(self):
        # anthropic 直连 provider 已经返 Anthropic-style key
        usage = {
            "input_tokens": 200,
            "output_tokens": 80,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 20,
        }
        out = normalize_usage_fields(usage)
        assert out == usage

    def test_none_returns_zeros(self):
        assert normalize_usage_fields(None) == {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }

    def test_empty_dict_returns_zeros(self):
        assert normalize_usage_fields({}) == {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }

    def test_partial_fields_pad_with_zero(self):
        usage = {"prompt_tokens": 100}
        out = normalize_usage_fields(usage)
        assert out["input_tokens"] == 100
        assert out["output_tokens"] == 0
        assert out["cache_read_input_tokens"] == 0
        assert out["cache_creation_input_tokens"] == 0


class TestSerializeLlmCallTrace:
    def test_full_collector(self):
        collector = {
            "system_prompt_full": "You are a recommender.",
            "system_prompt_chars": 21,
            "user_message_full": "Pick 5 dishes." * 10,
            "user_message_chars": 140,
            "raw_response": '{"candidates":[]}',
            "latency_ms": 1234,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "model": "anthropic/claude-sonnet-4.6",
            "resolved_provider": "openrouter",
            "stop_reason": "tool_calls",
            "fallback_reason": None,
            "max_tokens": 2048,
            "temperature": 0.0,
            "validator_errors": None,
        }
        out = serialize_llm_call_trace(collector)
        assert out["system_prompt_full"] == "You are a recommender."
        assert out["system_prompt_chars"] == 21
        assert out["raw_response"] == '{"candidates":[]}'
        assert out["raw_response_chars"] == 17
        assert out["latency_ms"] == 1234
        assert out["usage"]["input_tokens"] == 100
        assert out["usage"]["output_tokens"] == 50
        assert out["model"] == "anthropic/claude-sonnet-4.6"
        assert out["resolved_provider"] == "openrouter"
        assert out["user_message_preview"] == ("Pick 5 dishes." * 10)[:300]

    def test_empty_collector_returns_defaults(self):
        out = serialize_llm_call_trace({})
        assert out["system_prompt_full"] == ""
        assert out["system_prompt_chars"] == 0
        assert out["raw_response"] == ""
        assert out["raw_response_chars"] == 0
        assert out["latency_ms"] is None
        assert out["usage"] == {
            "input_tokens": 0, "output_tokens": 0,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        }

    def test_raw_response_chars_computed_from_body(self):
        out = serialize_llm_call_trace({"raw_response": "x" * 5000})
        assert out["raw_response_chars"] == 5000


class TestBuildL3TraceFromCollector:
    def test_ok_path(self):
        collector = {
            "status": "ok",
            "llm_called": True,
            "config_error": False,
            "used_fallback": False,
            "system_prompt_full": "sys",
            "user_message_full": "usr",
            "raw_response": '{"narrative":"good","candidates":[{}]}',
            "latency_ms": 5000,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "model": "anthropic/claude-sonnet-4.6",
            "resolved_provider": "openrouter",
            "stop_reason": "tool_calls",
            "tool_input": {"narrative": "good", "candidates": [{}]},
            "parsed_candidates": [{"rank": 1}],
            "narrative": "good",
        }
        out = build_l3_trace_from_collector(collector, payload_to_llm={"x": 1}, n_returned=5)
        assert out["status"] == "ok"
        assert out["used"] is True
        assert out["used_fallback"] is False
        assert out["payload_to_llm"] == {"x": 1}
        assert out["n_returned"] == 5
        assert out["narrative"] == "good"
        assert out["tool_input"] == {"narrative": "good", "candidates": [{}]}
        # 继承的 serialize_llm_call_trace 字段
        assert out["system_prompt_full"] == "sys"
        assert out["usage"]["input_tokens"] == 100

    def test_fallback_path_has_fallback_reason_intact(self):
        collector = {
            "status": "fallback",
            "llm_called": False,
            "used_fallback": True,
            "fallback_reason": "OR returned no choices",
        }
        out = build_l3_trace_from_collector(collector, payload_to_llm=None, n_returned=5)
        assert out["status"] == "fallback"
        assert out["used"] is False
        assert out["used_fallback"] is True
        assert out["fallback_reason"] == "OR returned no choices"

    def test_skipped_path(self):
        # 比如 top_combos 为空 -> rerank 直接 skip, llm_called=False
        collector = {"status": "skipped", "llm_called": False, "used_fallback": False}
        out = build_l3_trace_from_collector(collector, payload_to_llm=None, n_returned=0)
        assert out["status"] == "skipped"
        assert out["used"] is False


class TestBuildRefineRoundPayload:
    def test_full_refine_response(self):
        refine_raw = {
            "generated_at": "2026-05-19T12:00:00",
            "refine_intent": {"v1": "stub"},
            "refine_intent_v2": {"redirect": {}, "constrain": {}},
            "narrative": "湘菜重口味方案",
            "candidates": [
                {"restaurant": {"name": "湘颂"}, "dishes": [], "score": 2.5, "kind": "exploit"},
            ],
            "stats": {"n_combos_recalled": 100, "n_combos_after_score": 50},
            "_reference_resolved": None,
            "_subtype_diversified": True,
            "_refine_hard_filter_events": [],
            "_refine_recall_fallback_events": [],
            "l1_trace": {"funnel": []},
            "l2_trace": {"summary": {"n_scored": 50}, "top": []},
            "l3_trace": {"status": "ok"},
            "refine_intent_llm_trace": {"latency_ms": 1500},
        }
        out = build_refine_round_payload(refine_raw, "来点湘菜，重口味的")
        assert out["user_input"] == "来点湘菜，重口味的"
        assert out["label"] == "来点湘菜，重口味的"  # 字符串短，不截
        assert out["narrative"] == "湘菜重口味方案"
        assert out["intent_v2"] == {"redirect": {}, "constrain": {}}
        assert out["subtype_diversified"] is True
        # 关键: l1/l2/l3 都是 refine_raw 真切片, 不是 None
        assert out["l1"] == {"funnel": []}
        assert out["l2"] == {"summary": {"n_scored": 50}, "top": []}
        assert out["l3"] == {"status": "ok"}
        # refine_intent_llm 顶层字段
        assert out["refine_intent_llm"] == {"latency_ms": 1500}
        assert out["kpi"]["top1"] == "湘颂"
        assert out["kpi"]["combos"] == 100
        assert len(out["final"]) == 1
        assert out["final"][0]["rank"] == 1

    def test_label_truncated_at_20(self):
        out = build_refine_round_payload(
            {"candidates": [], "stats": {}}, "a" * 50
        )
        assert out["label"] == "a" * 20

    def test_label_fallback_when_empty(self):
        out = build_refine_round_payload({"candidates": [], "stats": {}}, "")
        assert out["label"] == "追问"
        assert out["user_input"] == ""

    def test_missing_l1_l2_l3_remain_none(self):
        # Stage 2 未完成时 refine_raw 没暴露切片, 应该兜 None 而非 KeyError
        out = build_refine_round_payload(
            {"candidates": [], "stats": {}}, "test"
        )
        assert out["l1"] is None
        assert out["l2"] is None
        assert out["l3"] is None
        assert out["refine_intent_llm"] is None

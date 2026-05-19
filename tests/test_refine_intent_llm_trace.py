"""D-089-S3: refine_intent_v2 LLM call 完整 trace 测试.

_llm_parse_v2 接 trace_collector 后, 必须采集 system_prompt_full / user_message_full
/ raw_response / latency / usage / model 等; 失败时 fallback_reason 填.
通过 mock chisha.llm_client.call_text 跑.
"""
from __future__ import annotations

from unittest.mock import patch

from chisha.refine_intent_v2 import _llm_parse_v2, extract_refine_intent_v2


def _make_v2_response(content: str) -> dict:
    """构造 refine_intent_v2 期望的 text 返回 (非 tool_use, json_mode 路径)."""
    return {
        "type": "text",
        "content": content,
        "stop_reason": "end_turn",
        "usage": {
            "prompt_tokens": 4500,
            "completion_tokens": 200,
            "cached_tokens": 0,
            "cache_write_tokens": 0,
        },
        "model": "anthropic/claude-sonnet-4.6",
        "raw_text": content,
    }


class TestLlmParseV2TraceCollector:
    def test_success_path_fills_full_trace(self):
        collector: dict = {}
        with patch("chisha.llm_client.call_text") as mock_call:
            mock_call.return_value = _make_v2_response('{"redirect": {}, "constrain": {}}')
            result = _llm_parse_v2(
                "来点湘菜",
                profile_llm={"provider": "openrouter", "model": {"openrouter": "anthropic/claude-sonnet-4.6"}},
                trace_collector=collector,
            )
        assert result == {"redirect": {}, "constrain": {}}
        # 核心: D-089 要求的关键字段全在
        assert collector["system_prompt_full"], (
            "system_prompt_full must be filled (parse_refine_intent_v2.md template body)"
        )
        assert collector["system_prompt_chars"] == len(collector["system_prompt_full"])
        assert collector["user_message_full"] == "来点湘菜"
        assert collector["user_message_chars"] == 4
        assert collector["raw_response"] == '{"redirect": {}, "constrain": {}}'
        assert collector["latency_ms"] is not None
        assert collector["latency_ms"] >= 0
        assert collector["model"] == "anthropic/claude-sonnet-4.6"
        assert collector["resolved_provider"] == "openrouter"
        assert collector["stop_reason"] == "end_turn"
        # success 路径不写 fallback_reason; serialize_llm_call_trace 会兜底 None
        assert "fallback_reason" not in collector
        assert collector["max_tokens"] == 1024
        assert collector["temperature"] == 0.0
        assert collector["usage"]["prompt_tokens"] == 4500

    def test_llm_exception_records_fallback_reason(self):
        collector: dict = {}
        with patch("chisha.llm_client.call_text") as mock_call:
            mock_call.side_effect = RuntimeError("network down")
            result = _llm_parse_v2(
                "来点湘菜", trace_collector=collector,
            )
        assert result is None
        assert collector.get("fallback_reason"), (
            "trace_collector.fallback_reason must reflect the exception"
        )
        assert "network down" in collector["fallback_reason"]
        # system_prompt_full 在 call_text 异常前已经赋值 (debug 必须能看到本次用的哪版 prompt)
        assert collector["system_prompt_full"]

    def test_empty_content_records_fallback_reason(self):
        collector: dict = {}
        with patch("chisha.llm_client.call_text") as mock_call:
            mock_call.return_value = _make_v2_response("")
            result = _llm_parse_v2("来点湘菜", trace_collector=collector)
        assert result is None
        assert "返回空" in (collector.get("fallback_reason") or "")
        # latency 已经记录 (call_text 真返了, 只是 content 空)
        assert collector["latency_ms"] is not None
        assert collector["raw_response"] == ""

    def test_no_json_in_content_records_fallback_reason(self):
        collector: dict = {}
        with patch("chisha.llm_client.call_text") as mock_call:
            mock_call.return_value = _make_v2_response("这不是 JSON")
            result = _llm_parse_v2("来点湘菜", trace_collector=collector)
        assert result is None
        assert "无 JSON" in (collector.get("fallback_reason") or "")

    def test_collector_optional_no_crash_without_it(self):
        """trace_collector=None 时函数行为不变 (向后兼容)."""
        with patch("chisha.llm_client.call_text") as mock_call:
            mock_call.return_value = _make_v2_response('{"redirect": {}, "constrain": {}}')
            result = _llm_parse_v2("来点湘菜")  # 无 trace_collector
        assert result == {"redirect": {}, "constrain": {}}


class TestExtractRefineIntentV2WithCollector:
    def test_empty_text_does_not_call_llm_collector_stays_empty(self):
        """边界: 空 refine 直接返 empty V2, 不调 LLM, collector 不该被填."""
        collector: dict = {}
        with patch("chisha.llm_client.call_text") as mock_call:
            v2 = extract_refine_intent_v2("", trace_collector=collector)
        assert v2.raw_text == ""
        # 空文本路径不调 LLM, collector 不应被填 (帮助 web_api 判断 refine_intent_llm = None)
        mock_call.assert_not_called()
        assert collector == {}

    def test_use_llm_false_does_not_call_llm(self):
        """边界: use_llm=False 走 V1 fallback, collector 不被填."""
        collector: dict = {}
        with patch("chisha.llm_client.call_text") as mock_call:
            v2 = extract_refine_intent_v2(
                "来点湘菜", use_llm=False, trace_collector=collector,
            )
        assert v2 is not None
        mock_call.assert_not_called()
        assert collector == {}

    def test_serialize_through_helper_produces_anthropic_usage(self):
        """D-089-S3 end-to-end: collector → serialize_llm_call_trace 后
        usage 必须 normalize 成 Anthropic-style (input_tokens 等)."""
        from chisha.trace_helpers import serialize_llm_call_trace

        collector: dict = {}
        with patch("chisha.llm_client.call_text") as mock_call:
            mock_call.return_value = _make_v2_response('{"redirect": {}, "constrain": {}, "raw_understanding": "x", "schema_version": "2.0"}')
            extract_refine_intent_v2("来点湘菜", trace_collector=collector)

        serialized = serialize_llm_call_trace(collector)
        # usage 字段已经 Anthropic-style
        assert serialized["usage"]["input_tokens"] == 4500
        assert serialized["usage"]["output_tokens"] == 200
        assert "prompt_tokens" not in serialized["usage"]  # 旧 key 不该出现在 final shape

        # raw_response_chars 自动算
        assert serialized["raw_response_chars"] > 0
        # system_prompt_full 透传 (D-089 self-contained 原则)
        assert serialized["system_prompt_full"] == collector["system_prompt_full"]

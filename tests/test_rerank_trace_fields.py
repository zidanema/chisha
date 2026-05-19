"""D-089-S1: R1 主链路 L3 trace 字段完整性测试.

不调真 LLM. 通过 mock call_text 让 rerank.py 跑成功路径 + fallback 路径,
验证 l3_collector / out dict 含 D-089 新增字段:
- system_prompt_full (整段 system prompt body)
- raw_response (provider raw text)
- usage 展开 (input_tokens / output_tokens 等)
- validator_errors

Codex M-3 / D-079 followup: 不直接 mock _RERANK_TOOL 等高层; 用 monkeypatch call_text
返回构造的 dict, 让 rerank 真跑后看 out 形状.
"""
from __future__ import annotations

from unittest.mock import patch


def _make_mock_response(narrative: str = "test narrative") -> dict:
    """构造一个 call_text 的 tool_use 返回, 让 rerank 走 ok 路径."""
    return {
        "type": "tool_use",
        "tool_name": "select_top_candidates",
        "tool_input": {
            "narrative": narrative,
            "candidates": [
                {
                    "rank": 1, "is_explore": False, "combo_index": 0,
                    "fit_score": 0.85, "taste_match": 0.75,
                    "risk_flags": [], "one_line_reason": "test reason",
                },
            ],
        },
        "stop_reason": "tool_calls",
        "usage": {
            "prompt_tokens": 15000,
            "completion_tokens": 800,
            "cached_tokens": 0,
            "cache_write_tokens": 4000,
        },
        "model": "anthropic/claude-sonnet-4.6",
        "raw_text": '{"narrative":"test","candidates":[{}]}',
    }


def _minimal_top_combos() -> list[dict]:
    """rerank 跑不下去的最小输入 (top_combos)."""
    return [
        {
            "restaurant": {"name": "测试餐厅", "id": "r1"},
            "dishes": [{"name": "测试菜", "canonical_name": "测试菜"}],
            "score": 5.0,
            "score_breakdown": {},
            "combo_index": 0,
        },
    ]


def _minimal_profile() -> dict:
    return {
        "llm": {"provider": "openrouter", "model": {"openrouter": "anthropic/claude-sonnet-4.6"}},
        "scoring_weights": {},
        "diversity": {},
        "long_term_prefs": {"boost": {}, "penalty": {}},
    }


def test_rerank_l3_collector_has_system_prompt_full():
    """D-089-S1: rerank 成功路径下 trace_collector 必须含 system_prompt_full body."""
    from chisha import rerank

    collector: dict = {}
    with patch("chisha.llm_client.call_text") as mock_call:
        mock_call.return_value = _make_mock_response()
        result = rerank.rerank(
            _minimal_top_combos(),
            _minimal_profile(),
            context=None,
            meal_log=[],
            n=1, n_explore=0,
            use_llm=True,
            trace_collector=collector,
        )

    assert result, "rerank should return candidates on ok path"
    assert collector.get("status") == "ok"
    # 核心断言: system_prompt body 必须落 (不再仅 chars)
    assert collector.get("system_prompt_full"), (
        "trace_collector must contain system_prompt_full body for self-contained trace"
    )
    assert len(collector["system_prompt_full"]) > 1000, (
        f"system_prompt_full should be the full rerank_system.md content, got "
        f"{len(collector['system_prompt_full'])} chars"
    )
    assert collector.get("system_prompt_chars") == len(collector["system_prompt_full"])


def test_rerank_l3_collector_has_raw_response_and_usage():
    """D-089-S1: raw_response (provider raw text) + usage 字段必须落."""
    from chisha import rerank

    collector: dict = {}
    with patch("chisha.llm_client.call_text") as mock_call:
        mock_call.return_value = _make_mock_response()
        rerank.rerank(
            _minimal_top_combos(),
            _minimal_profile(),
            context=None,
            meal_log=[],
            n=1, n_explore=0,
            use_llm=True,
            trace_collector=collector,
        )

    # raw_response: tool_use 路径用 raw_text (tool_input JSON 字符串)
    assert collector.get("raw_response") == '{"narrative":"test","candidates":[{}]}'
    assert collector.get("raw_response_chars") == 38

    # usage: provider-level naming (会被 trace_helpers normalize 之后再落给前端)
    usage = collector.get("usage")
    assert isinstance(usage, dict)
    assert usage.get("prompt_tokens") == 15000
    assert usage.get("completion_tokens") == 800


def test_rerank_fallback_path_still_collects_system_prompt():
    """D-089-S1: 即使 LLM 调用失败 (fallback), system_prompt_full 也应已采集.

    因为 system_prompt 在调 call_text 前就读了, fallback 不应丢这个证据 — 否则
    用户看不到「fallback 时用的是哪版 prompt」.
    """
    from chisha import rerank

    collector: dict = {}
    with patch("chisha.llm_client.call_text") as mock_call:
        mock_call.side_effect = RuntimeError("simulated provider failure")
        rerank.rerank(
            _minimal_top_combos(),
            _minimal_profile(),
            context=None,
            meal_log=[],
            n=1, n_explore=0,
            use_llm=True,
            trace_collector=collector,
        )

    # fallback 路径: status != "ok", 但 system_prompt_full 已经在 call 前采集
    assert collector.get("status") == "fallback"
    assert collector.get("system_prompt_full"), (
        "system_prompt_full should be captured even on fallback path"
    )
    # fallback_reason 应反映 LLM 调用异常
    assert "simulated provider failure" in (collector.get("fallback_reason") or "")


def test_rerank_skipped_path_when_empty_top_combos():
    """边界: top_combos 空 → rerank 直接 skip (use_llm 即使 True 也不调 LLM).

    collector 应至少 status="skipped", 不该抛.
    """
    from chisha import rerank

    collector: dict = {}
    with patch("chisha.llm_client.call_text") as mock_call:
        mock_call.return_value = _make_mock_response()
        result = rerank.rerank(
            [],  # empty top_combos
            _minimal_profile(),
            context=None,
            meal_log=[],
            n=1, n_explore=0,
            use_llm=True,
            trace_collector=collector,
        )

    assert result == []
    assert collector.get("status") == "skipped"
    # 没调 LLM, mock 也没被触发
    mock_call.assert_not_called()


def test_rerank_use_llm_false_does_not_call_llm():
    """边界: use_llm=False → fallback 路径不调 LLM, trace_collector status 应是 skipped."""
    from chisha import rerank

    collector: dict = {}
    with patch("chisha.llm_client.call_text") as mock_call:
        rerank.rerank(
            _minimal_top_combos(),
            _minimal_profile(),
            context=None,
            meal_log=[],
            n=1, n_explore=0,
            use_llm=False,
            trace_collector=collector,
        )

    mock_call.assert_not_called()
    # status 由 _ensure_collector_filled 兜底 (skipped on use_llm=False)
    assert collector.get("status") in ("skipped", None)
    assert collector.get("llm_called") is False


def test_api_l3_trace_includes_d089_fields_via_build_helper():
    """验证 chisha/api.py:_build_trace 通过 build_l3_trace_from_collector 落新字段.

    用最小 l3_collector + 调 helper, 验证 R1 主链路 trace 出来含 D-089 新字段.
    """
    from chisha.trace_helpers import build_l3_trace_from_collector

    collector = {
        "status": "ok",
        "llm_called": True,
        "config_error": False,
        "used_fallback": False,
        "system_prompt_full": "<full system prompt body>",
        "system_prompt_chars": 24,
        "user_message_full": "<user msg>",
        "user_message_chars": 11,
        "raw_response": '{"x":1}',
        "latency_ms": 5000,
        "usage": {"prompt_tokens": 100, "completion_tokens": 50,
                  "cached_tokens": 10, "cache_write_tokens": 5},
        "model": "anthropic/claude-sonnet-4.6",
        "resolved_provider": "openrouter",
        "stop_reason": "tool_calls",
        "narrative": "test narrative",
        "tool_input": {"x": 1},
        "parsed_candidates": [{"rank": 1}],
    }
    l3_trace = build_l3_trace_from_collector(
        collector, payload_to_llm={"y": 2}, n_returned=5
    )

    # D-089-S1 新字段
    assert l3_trace["system_prompt_full"] == "<full system prompt body>"
    assert l3_trace["raw_response"] == '{"x":1}'
    assert l3_trace["raw_response_chars"] == 7
    # usage 已经 normalize 成 Anthropic-style
    assert l3_trace["usage"]["input_tokens"] == 100
    assert l3_trace["usage"]["output_tokens"] == 50
    assert l3_trace["usage"]["cache_read_input_tokens"] == 10
    assert l3_trace["usage"]["cache_creation_input_tokens"] == 5
    # 业务字段
    assert l3_trace["status"] == "ok"
    assert l3_trace["used"] is True
    assert l3_trace["narrative"] == "test narrative"
    assert l3_trace["n_returned"] == 5
    assert l3_trace["payload_to_llm"] == {"y": 2}

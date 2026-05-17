"""D-085 PR-E E1: chisha/lab_summary 单测.

覆盖:
- _build_summary_inputs 抽 top1 / breakdown top-N / feedback evidence
- _humanize_dim 映射 / 未知 dim fallback
- compute_fingerprint 稳定 + 关键字段变 → 变
- summarize happy path (注入 fake llm)
- summarize fallback: 空 trace / no provider / llm 异常 / 空 content
- _DIM_HINTS 与 score.py 主要维度对齐
"""
from __future__ import annotations

import pytest

from chisha import lab_summary


def _trace_with_top1(
    *,
    dish_names: list[str] | None = None,
    breakdown: dict[str, float] | None = None,
    reason: str = "三菜一汤蛋白质达标",
    refine_applied: bool = False,
    feedback_evidence: dict | None = None,
) -> dict:
    breakdown = breakdown or {
        "low_oil": 0.6, "popularity": 0.3, "cuisine_preference": 0.4,
        "variety_bonus": 0.05,  # 极小, 应被 top-3 截掉
    }
    dish_names = dish_names or ["蒸鸡胸", "蒜蓉菜心", "番茄蛋汤"]
    return {
        "session_id": "sess_test_001",
        "final": [{
            "rank": 1,
            "restaurant": {"name": "西贝莜面村"},
            "dishes": [{"name": n} for n in dish_names],
            "total_price": 78.0,
            "estimated_total_oil": 2.3,
            "estimated_total_protein_g": 42.5,
            "reason_one_line": reason,
            "score": 1.42,
        }],
        "l2": {
            "top": [{
                "rank": 1,
                "breakdown": breakdown,
                "feedback_evidence": feedback_evidence or {},
            }],
        },
        "l3": {"status": "ok"},
        "refine": (
            {"applied": True, "user_input": "想吃清淡的"}
            if refine_applied else {"applied": False}
        ),
        "__frozen": {"meal_type": "lunch", "today": "2026-05-17", "zone": "shenzhen-bay"},
        "__config": {"daily_mood": "neutral"},
    }


# ────────────────────────── _build_summary_inputs

def test_build_inputs_extracts_top1_and_topN_dims():
    inputs = lab_summary._build_summary_inputs(_trace_with_top1())
    assert inputs["restaurant_name"] == "西贝莜面村"
    assert inputs["dish_names"] == ["蒸鸡胸", "蒜蓉菜心", "番茄蛋汤"]
    assert inputs["meal_type"] == "lunch"
    assert inputs["today"] == "2026-05-17"
    assert inputs["daily_mood"] == "neutral"
    # top-3 排序: low_oil(0.6) > cuisine_preference(0.4) > popularity(0.3)
    dims = [d for d, _ in inputs["top_dims"]]
    assert dims == ["low_oil", "cuisine_preference", "popularity"]
    # variety_bonus 0.05 仍 > 0, 但被 top-3 切掉
    assert "variety_bonus" not in dims


def test_build_inputs_drops_zero_and_negative_dims():
    trace = _trace_with_top1(breakdown={
        "low_oil": 0.5,
        "processed_meat": -0.8,  # 负贡献
        "eta": 0.0,              # 零贡献
        "popularity": 0.2,
    })
    inputs = lab_summary._build_summary_inputs(trace)
    dims = [d for d, _ in inputs["top_dims"]]
    assert dims == ["low_oil", "popularity"]


def test_build_inputs_refine_applied_passes_user_input():
    trace = _trace_with_top1(refine_applied=True)
    inputs = lab_summary._build_summary_inputs(trace)
    assert inputs["refine_text"] == "想吃清淡的"


def test_build_inputs_raises_on_empty_final():
    trace = _trace_with_top1()
    trace["final"] = []
    with pytest.raises(lab_summary.SummarizeError) as exc:
        lab_summary._build_summary_inputs(trace)
    assert exc.value.kind == "empty_trace"


def test_feedback_evidence_lines_extraction():
    ev = {
        "feedback_recency": [
            {"restaurant_name": "西贝", "rating": 5, "age_days": 3, "signal": 0.4},
        ],
        "next_meal_calibration": [
            {
                "rules_fired": [
                    {"rule": "low_oil_after_heavy", "contribution": 0.2},
                ],
            },
        ],
        "note_boost": [
            {"kind": "restaurant", "token": "汤鲜", "polarity": "boost",
             "restaurant_name": "西贝"},
            {"kind": "global", "token": "油腻", "polarity": "penalty"},
        ],
    }
    trace = _trace_with_top1(feedback_evidence=ev)
    inputs = lab_summary._build_summary_inputs(trace)
    lines = inputs["feedback_evidence_lines"]
    assert len(lines) == 4
    assert "3 天前给 西贝 打过 5 星" in lines[0]
    assert "low_oil_after_heavy" in lines[1]
    assert "汤鲜" in lines[2] and "加分" in lines[2]
    assert "油腻" in lines[3] and "扣分" in lines[3]


# ────────────────────────── _humanize_dim

def test_humanize_dim_known():
    assert lab_summary._humanize_dim("low_oil") == "油脂等级低"
    assert lab_summary._humanize_dim("intent_cuisine") == "本次 refine 指明的菜系"
    assert lab_summary._humanize_dim("feedback_recency") == "近期反馈 (rating) 强化"


def test_humanize_dim_unknown_fallback():
    # 未知 dim 仅去下划线, 不抛
    assert lab_summary._humanize_dim("some_weird_dim_xyz") == "some weird dim xyz"


def test_dim_hints_cover_score_weights():
    """守门: score.SCORE_WEIGHTS 的主要活权重必须在 _DIM_HINTS 里有人话."""
    from chisha.score import V2_DEFAULT_WEIGHTS
    # 活权重 (排除死分 0.0)
    active = {k for k, v in V2_DEFAULT_WEIGHTS.items() if v != 0.0}
    missing = active - set(lab_summary._DIM_HINTS.keys())
    assert not missing, f"_DIM_HINTS 缺这些活维度: {missing}"


# ────────────────────────── fingerprint

def test_fingerprint_stable_for_same_inputs():
    t1 = _trace_with_top1()
    t2 = _trace_with_top1()
    assert lab_summary.compute_fingerprint(t1) == lab_summary.compute_fingerprint(t2)


def test_fingerprint_changes_on_top1_swap():
    t1 = _trace_with_top1()
    t2 = _trace_with_top1(dish_names=["完全不同的菜"])
    assert lab_summary.compute_fingerprint(t1) != lab_summary.compute_fingerprint(t2)


def test_fingerprint_changes_on_breakdown_shift():
    t1 = _trace_with_top1(breakdown={"low_oil": 0.5, "popularity": 0.4})
    t2 = _trace_with_top1(breakdown={"low_oil": 0.5, "popularity": 0.9})
    assert lab_summary.compute_fingerprint(t1) != lab_summary.compute_fingerprint(t2)


def test_fingerprint_changes_on_l3_reason_shift():
    t1 = _trace_with_top1(reason="蒸菜清淡")
    t2 = _trace_with_top1(reason="完全另一个理由")
    assert lab_summary.compute_fingerprint(t1) != lab_summary.compute_fingerprint(t2)


def test_fingerprint_empty_trace_returns_stable_marker():
    trace = _trace_with_top1()
    trace["final"] = []
    assert lab_summary.compute_fingerprint(trace) == "empty"


# ────────────────────────── summarize happy + fallback

def _fake_llm_ok(text: str = "因为今天天气热, 这家蒸菜清淡省油, 还是你 7 天没点的店."):
    def _call(prompt, **kwargs):
        return {
            "type": "text",
            "content": text,
            "model": kwargs.get("model") or "claude-haiku-4-5-20251001",
            "stop_reason": "end_turn",
        }
    return _call


def test_summarize_happy_path():
    trace = _trace_with_top1()
    out = lab_summary.summarize(trace, llm_call=_fake_llm_ok())
    assert out["fallback"] is False
    assert out["text"].startswith("因为今天天气热")
    assert out["model"] == "claude-haiku-4-5-20251001"
    assert "generated_at" in out and out["generated_at"].endswith("+00:00")
    assert out["fingerprint"] != "empty"


def test_summarize_passes_meal_and_dims_into_prompt():
    """fake_llm 检查 prompt 包含 top1 + meal + 维度. 防 prompt 退化."""
    captured = {}

    def _spy(prompt, **kwargs):
        captured["prompt"] = prompt
        captured["system"] = kwargs.get("system")
        return {"type": "text", "content": "ok", "model": "x"}

    trace = _trace_with_top1(refine_applied=True)
    lab_summary.summarize(trace, llm_call=_spy)
    p = captured["prompt"]
    assert "西贝莜面村" in p
    assert "蒸鸡胸" in p
    assert "午餐" in p
    assert "想吃清淡的" in p
    assert "low_oil" in p  # top1 dim 入 prompt
    assert "营养顾问" in captured["system"]


def test_summarize_fallback_on_empty_trace():
    trace = _trace_with_top1()
    trace["final"] = []
    out = lab_summary.summarize(trace, llm_call=_fake_llm_ok())
    assert out["fallback"] is True
    assert out["error_kind"] == "empty_trace"
    assert out["text"] is None


def test_summarize_fallback_on_no_provider():
    def _raise_no_provider(prompt, **kwargs):
        raise RuntimeError("无可用 LLM provider")

    out = lab_summary.summarize(_trace_with_top1(), llm_call=_raise_no_provider)
    assert out["fallback"] is True
    assert out["error_kind"] == "no_provider"


def test_summarize_fallback_on_llm_arbitrary_exception():
    def _raise(prompt, **kwargs):
        raise ValueError("API 429")

    out = lab_summary.summarize(_trace_with_top1(), llm_call=_raise)
    assert out["fallback"] is True
    assert out["error_kind"] == "llm_error"
    assert "ValueError" in out["error_detail"]


def test_summarize_fallback_on_empty_content():
    def _empty(prompt, **kwargs):
        return {"type": "text", "content": "", "model": "x"}

    out = lab_summary.summarize(_trace_with_top1(), llm_call=_empty)
    assert out["fallback"] is True
    assert out["error_kind"] == "llm_error"


def test_summarize_fallback_on_tool_use_response_shape():
    """provider 返了 tool_use shape 不是 text — 视为异常."""
    def _toolu(prompt, **kwargs):
        return {"type": "tool_use", "tool_name": "x", "tool_input": {}, "model": "x"}

    out = lab_summary.summarize(_trace_with_top1(), llm_call=_toolu)
    assert out["fallback"] is True
    assert out["error_kind"] == "llm_error"

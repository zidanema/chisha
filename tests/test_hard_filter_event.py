"""T-00: trace_store.append_hard_filter_event helper 单测.

helper 校验:
  - category 必须 ∈ L0Category 枚举 ({A_medical, B_identity, C_health, methodology})
  - rule 必须非空字符串
  - dropped_count / kept_count 必须 int >= 0
  - 校验失败 warn + 返 False, 不抛 (best-effort 风格)
  - 校验通过追加到 trace["l1"]["hard_filter_events"]
"""
from __future__ import annotations

from chisha import trace_store


def _empty_trace() -> dict:
    return {"session_id": "sess_test", "l1": {}}


def test_append_normal_event_succeeds() -> None:
    trace = _empty_trace()
    ok = trace_store.append_hard_filter_event(
        trace,
        category="L0_A_medical",
        rule="no_peanut_allergy",
        dropped_count=3,
        kept_count=27,
    )
    assert ok is True
    events = trace["l1"]["hard_filter_events"]
    assert len(events) == 1
    e = events[0]
    assert e["event_type"] == "hard_filter"
    assert e["category"] == "L0_A_medical"
    assert e["rule"] == "no_peanut_allergy"
    assert e["dropped_count"] == 3
    assert e["kept_count"] == 27
    assert e["refine_override"] is False
    assert isinstance(e["timestamp"], float)


def test_append_with_refine_override_c_class() -> None:
    """L0-C 类被 refine 解除 → refine_override=True."""
    trace = _empty_trace()
    ok = trace_store.append_hard_filter_event(
        trace,
        category="L0_C_health",
        rule="oil_level<=medium",
        dropped_count=0,
        kept_count=30,
        refine_override=True,
    )
    assert ok is True
    assert trace["l1"]["hard_filter_events"][0]["refine_override"] is True


def test_append_invalid_category_rejected() -> None:
    trace = _empty_trace()
    ok = trace_store.append_hard_filter_event(
        trace,
        category="L0_X_invented",
        rule="some_rule",
        dropped_count=1,
        kept_count=1,
    )
    assert ok is False
    # trace 没被污染
    assert "hard_filter_events" not in trace["l1"]


def test_append_empty_rule_rejected() -> None:
    trace = _empty_trace()
    ok = trace_store.append_hard_filter_event(
        trace,
        category="L0_A_medical",
        rule="",
        dropped_count=1,
        kept_count=1,
    )
    assert ok is False
    assert "hard_filter_events" not in trace["l1"]


def test_append_negative_count_rejected() -> None:
    trace = _empty_trace()
    ok = trace_store.append_hard_filter_event(
        trace,
        category="L0_B_identity",
        rule="halal_only",
        dropped_count=-1,
        kept_count=5,
    )
    assert ok is False
    assert "hard_filter_events" not in trace["l1"]


def test_append_multiple_events_preserve_order() -> None:
    """同 trace 多次 append 按顺序追加."""
    trace = _empty_trace()
    trace_store.append_hard_filter_event(
        trace, category="L0_A_medical", rule="rule_a", dropped_count=1, kept_count=10
    )
    trace_store.append_hard_filter_event(
        trace, category="L0_C_health", rule="rule_c", dropped_count=2, kept_count=8,
        refine_override=True
    )
    trace_store.append_hard_filter_event(
        trace, category="methodology", rule="rule_m", dropped_count=3, kept_count=5
    )
    events = trace["l1"]["hard_filter_events"]
    assert len(events) == 3
    assert events[0]["rule"] == "rule_a"
    assert events[1]["rule"] == "rule_c"
    assert events[1]["refine_override"] is True
    assert events[2]["rule"] == "rule_m"


def test_append_initializes_l1_dict_if_missing() -> None:
    """trace 完全没 l1 段时, helper 自动 setdefault."""
    trace: dict = {}
    ok = trace_store.append_hard_filter_event(
        trace,
        category="methodology",
        rule="vegetable_ratio>=0.5",
        dropped_count=5,
        kept_count=15,
    )
    assert ok is True
    assert "l1" in trace
    assert len(trace["l1"]["hard_filter_events"]) == 1


def test_append_rejects_bool_counts() -> None:
    """bool 是 int 子类, 必须显式拒绝 (Codex review NOTE)."""
    trace = _empty_trace()
    # dropped_count=True 被静默接受是 bug
    ok = trace_store.append_hard_filter_event(
        trace,
        category="L0_A_medical",
        rule="some",
        dropped_count=True,  # type: ignore[arg-type]
        kept_count=10,
    )
    assert ok is False
    ok2 = trace_store.append_hard_filter_event(
        trace,
        category="L0_A_medical",
        rule="some",
        dropped_count=1,
        kept_count=False,  # type: ignore[arg-type]
    )
    assert ok2 is False
    assert "hard_filter_events" not in trace["l1"]

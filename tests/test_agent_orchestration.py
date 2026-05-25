"""T4: prepare_candidates 共享编排单测 (D-074).

锁定关键契约: R1 (intent=None) 跳过 reference/subtype; refine (传 intent 对象, 即便
is_empty) 仍跑 reference raw_parser — 这是 codex 指出的行为漂移点.
"""
from __future__ import annotations

import datetime as dt

import pytest

from chisha import agent_orchestration as orch
from chisha.refine_intent_v2 import RefineIntentV2


@pytest.fixture
def patched_orch(monkeypatch):
    """mock recall/rank_combos/apply_caps/build_context/fb_signal, 留编排真逻辑."""
    fake_combos = [
        {"restaurant": {"id": f"r{i}", "name": f"店{i}"},
         "dishes": [{"canonical_name": f"d{i}", "cuisine": "湘菜",
                     "nutrition_profile": {"oil_level": 2, "cooking_method": "炒"}}],
         "score": 5.0 - i * 0.1}
        for i in range(8)
    ]
    monkeypatch.setattr(orch, "recall", lambda *a, **kw: list(fake_combos))
    monkeypatch.setattr(orch, "rank_combos", lambda *a, **kw: list(fake_combos))
    monkeypatch.setattr(orch, "apply_caps", lambda ranked, *a, **kw: ranked)

    class _Ctx:
        def to_llm_dict(self): return {}
    monkeypatch.setattr(orch, "build_context", lambda **kw: _Ctx())
    monkeypatch.setattr(orch, "_build_fb_signal", lambda today, root: None)
    return fake_combos


def _call(intent=None, refine_input=None):
    return orch.prepare_candidates(
        profile={"basics": {"office_zone": "test"}},
        rests=[], tagged=[], meal_log=[],
        meal_type="lunch", today=dt.date(2026, 5, 25), root=None,
        refine_input=refine_input, intent=intent,
    )


def test_r1_skips_reference_and_subtype(patched_orch):
    """recommend_meal 路径 (intent=None): 不跑 reference/subtype."""
    prep = _call(intent=None, refine_input=None)
    assert prep.reference_resolved is None
    assert prep.reference_source == "none"
    assert prep.subtype_diversified is False
    assert len(prep.top_k) == 8


def test_refine_empty_intent_still_runs_raw_parser_reference(patched_orch, monkeypatch):
    """codex 漂移点: 传 intent 对象 (即便 is_empty), reference raw_parser 仍生效."""
    seen = {}

    def _fake_apply_reference(ranked, intent, user_input, today, root):
        seen["user_input"] = user_input
        seen["called"] = True
        return ranked, None, "none"

    monkeypatch.setattr(orch, "_apply_reference", _fake_apply_reference)
    empty_intent = RefineIntentV2(raw_text="比昨天清淡点",
                                   raw_understanding="(空)")
    assert empty_intent.is_empty()
    _call(intent=empty_intent, refine_input="比昨天清淡点")
    # is_refine 判定靠 intent is not None, 即便 is_empty 也跑 reference
    assert seen.get("called") is True
    assert seen["user_input"] == "比昨天清淡点"


def test_r1_does_not_run_reference(patched_orch, monkeypatch):
    """intent=None (recommend_meal) 绝不调 _apply_reference."""
    called = {"v": False}
    monkeypatch.setattr(
        orch, "_apply_reference",
        lambda *a, **kw: called.__setitem__("v", True) or (a[0], None, "none"),
    )
    _call(intent=None, refine_input=None)
    assert called["v"] is False


def test_subtype_gated_on_cuisine_want(patched_orch):
    """subtype 多样化只在 cuisine_want 非空时触发."""
    intent_no_cuisine = RefineIntentV2(
        constrain={"oil": "low", "price_max": None, "price_band": None,
                   "wants_soup": False},
        raw_text="清淡", raw_understanding="低油",
    )
    prep = _call(intent=intent_no_cuisine, refine_input="清淡")
    assert prep.subtype_diversified is False


def test_fb_signal_passthrough(patched_orch):
    """显式传 fb_signal 时不重新构建."""
    fake_fb = {"evict_names": {}}
    prep = orch.prepare_candidates(
        profile={"basics": {"office_zone": "test"}},
        rests=[], tagged=[], meal_log=[], meal_type="lunch",
        today=dt.date(2026, 5, 25), root=None, fb_signal=fake_fb,
    )
    assert prep.fb_signal is fake_fb

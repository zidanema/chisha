"""B-001: feedback_recency 短链路单测.

覆盖:
- build_feedback_view 派生 (rating / age_days / 餐厅名 / 时间窗)
- _feedback_single_signal 衰减曲线 (-1 / +1 各 age 段)
- _feedback_aggregate 最强负向优先
- feedback_recency_score 命中 / 无命中 / 餐厅名匹配
- score_combo 仅命中时写 breakdown key (baseline 守门口径)
- rank_combos sentinel 区分 _UNSET vs []
"""
from __future__ import annotations

import datetime as dt
import math

import pytest

from chisha.feedback_store import build_feedback_view
from chisha.score import (
    _UNSET_FEEDBACK_VIEW,
    _feedback_aggregate,
    _feedback_single_signal,
    feedback_recency_score,
    rank_combos,
    score_combo,
)


def _store_with(accepted: dict, feedbacks: dict) -> dict:
    return {"accepted": accepted, "feedbacks": feedbacks, "sessions": {}}


# ─────────────────────── build_feedback_view ───────────────────────


def test_build_feedback_view_empty_store():
    # B-001 v2: 返 dict 形态 {ratings, calibrations, note_tokens}, 全空
    # D-084: + feedback_trace sibling (空骨架, empty=True). 原编号 D-082, 与 main D-082 (Refine 二轮) 冲突, 合并时重号
    v1 = build_feedback_view({}, dt.date(2026, 5, 17))
    assert v1["ratings"] == [] and v1["calibrations"] == [] and v1["note_tokens"] == []
    assert v1["feedback_trace"]["empty"] is True
    v2 = build_feedback_view(
        {"accepted": {}, "feedbacks": {}}, dt.date(2026, 5, 17)
    )
    assert v2["ratings"] == [] and v2["calibrations"] == [] and v2["note_tokens"] == []
    assert v2["feedback_trace"]["empty"] is True


def test_build_feedback_view_basic():
    today = dt.date(2026, 5, 17)
    store = _store_with(
        accepted={
            "s1": {"restaurant_name": "店A", "accepted_at": "2026-05-15T12:00:00+00:00"},
            "s2": {"restaurant_name": "店B", "accepted_at": "2026-05-10T12:00:00+00:00"},
        },
        feedbacks={
            "s1": {"rating": -1, "submitted_at": "2026-05-15T13:00:00+00:00"},
            "s2": {"rating": 1, "submitted_at": "2026-05-10T13:00:00+00:00"},
        },
    )
    view = build_feedback_view(store, today)["ratings"]
    assert len(view) == 2
    # 排序: age 升序
    assert view[0]["restaurant_name"] == "店A"
    assert view[0]["age_days"] == 2
    assert view[0]["rating"] == -1
    assert view[1]["restaurant_name"] == "店B"
    assert view[1]["age_days"] == 7


def test_build_feedback_view_window_zero_keeps_today():
    """Codex nit: window_days=0 应包含当天反馈 (age_days ∈ [0, 0])."""
    today = dt.date(2026, 5, 17)
    store = _store_with(
        accepted={
            "s_today": {"restaurant_name": "今店", "accepted_at": "2026-05-17T12:00:00+00:00"},
            "s_yest": {"restaurant_name": "昨店", "accepted_at": "2026-05-16T12:00:00+00:00"},
        },
        feedbacks={
            "s_today": {"rating": -1, "submitted_at": "2026-05-17T13:00:00+00:00"},
            "s_yest": {"rating": -1, "submitted_at": "2026-05-16T13:00:00+00:00"},
        },
    )
    view = build_feedback_view(store, today, window_days=0)["ratings"]
    assert [v["restaurant_name"] for v in view] == ["今店"]


def test_build_feedback_view_window_filter():
    today = dt.date(2026, 5, 17)
    store = _store_with(
        accepted={
            "s_old": {"restaurant_name": "老店", "accepted_at": "2026-01-01T12:00:00+00:00"},
            "s_new": {"restaurant_name": "新店", "accepted_at": "2026-05-15T12:00:00+00:00"},
        },
        feedbacks={
            "s_old": {"rating": -1, "submitted_at": "2026-01-01T13:00:00+00:00"},
            "s_new": {"rating": -1, "submitted_at": "2026-05-15T13:00:00+00:00"},
        },
    )
    view = build_feedback_view(store, today, window_days=60)["ratings"]
    assert [v["restaurant_name"] for v in view] == ["新店"]


def test_build_feedback_view_skips_zero_rating():
    today = dt.date(2026, 5, 17)
    store = _store_with(
        accepted={
            "s1": {"restaurant_name": "店A", "accepted_at": "2026-05-15T12:00:00+00:00"},
            "s2": {"restaurant_name": "店B", "accepted_at": "2026-05-15T12:00:00+00:00"},
        },
        feedbacks={
            "s1": {"rating": 0, "submitted_at": "2026-05-15T13:00:00+00:00"},
            "s2": {"rating": None, "submitted_at": "2026-05-15T13:00:00+00:00"},
        },
    )
    assert build_feedback_view(store, today)["ratings"] == []


def test_build_feedback_view_skips_missing_name():
    today = dt.date(2026, 5, 17)
    store = _store_with(
        accepted={
            "s1": {"restaurant_name": "", "accepted_at": "2026-05-15T12:00:00+00:00"},
            "s2": {"accepted_at": "2026-05-15T12:00:00+00:00"},  # 完全没 name 字段
        },
        feedbacks={
            "s1": {"rating": -1, "submitted_at": "2026-05-15T13:00:00+00:00"},
            "s2": {"rating": -1, "submitted_at": "2026-05-15T13:00:00+00:00"},
        },
    )
    assert build_feedback_view(store, today)["ratings"] == []


def test_build_feedback_view_falls_back_to_submitted_at():
    today = dt.date(2026, 5, 17)
    store = _store_with(
        accepted={
            "s1": {"restaurant_name": "店A"},  # 没 accepted_at
        },
        feedbacks={
            "s1": {"rating": -1, "submitted_at": "2026-05-14T13:00:00+00:00"},
        },
    )
    view = build_feedback_view(store, today)["ratings"]
    assert view == [{"restaurant_name": "店A", "rating": -1, "age_days": 3}]


# ─────────────────────── single signal 衰减曲线 ───────────────────────


def test_single_signal_negative_age_zero():
    assert _feedback_single_signal(-1, 0) == pytest.approx(-1.5, abs=1e-6)


def test_single_signal_negative_age_7():
    expected = -1.5 * math.exp(-7 / 14.0)
    assert _feedback_single_signal(-1, 7) == pytest.approx(expected, abs=1e-6)
    assert _feedback_single_signal(-1, 7) < -0.9  # sanity


def test_single_signal_negative_age_14():
    expected = -1.5 * math.exp(-1.0)
    assert _feedback_single_signal(-1, 14) == pytest.approx(expected, abs=1e-6)


def test_single_signal_negative_age_60_near_zero():
    # 60 天 → 应衰减到接近 0 (< 0.03 量级)
    assert abs(_feedback_single_signal(-1, 60)) < 0.03


def test_single_signal_positive_cooldown_age_0():
    assert _feedback_single_signal(1, 0) == pytest.approx(-0.7, abs=1e-6)


def test_single_signal_positive_cooldown_age_2():
    # 0-3 天 cooldown 线性 -0.7 → 0; age=2 → -0.7 * (1 - 2/3) = -0.233
    assert _feedback_single_signal(1, 2) == pytest.approx(-0.7 / 3.0, abs=1e-6)


def test_single_signal_positive_boost_age_3():
    # age=3 是 cooldown / boost 分界, 取 boost 起点 +0.25
    assert _feedback_single_signal(1, 3) == pytest.approx(0.25, abs=1e-6)


def test_single_signal_positive_boost_age_10():
    expected = 0.25 * math.exp(-(10 - 3) / 14.0)
    assert _feedback_single_signal(1, 10) == pytest.approx(expected, abs=1e-6)


def test_single_signal_negative_age_negative_returns_zero():
    """防御性: 负 age (理论上 build_feedback_view 已过滤) 应返 0."""
    assert _feedback_single_signal(-1, -1) == 0.0


# ─────────────────────── aggregate 最强负向优先 ───────────────────────


def test_aggregate_empty():
    assert _feedback_aggregate([]) == 0.0


def test_aggregate_neg_only():
    signals = [
        _feedback_single_signal(-1, 5),
        _feedback_single_signal(-1, 30),
    ]
    # min → 最强负向 (age=5)
    expected = min(signals)
    assert _feedback_aggregate(signals) == pytest.approx(expected, abs=1e-6)


def test_aggregate_pos_only():
    signals = [
        _feedback_single_signal(1, 5),
        _feedback_single_signal(1, 10),
    ]
    # max → 最强正向 (age=5)
    expected = max(signals)
    assert _feedback_aggregate(signals) == pytest.approx(expected, abs=1e-6)


def test_aggregate_neg_overrides_pos():
    """关键 Codex 拍板: 远期 -1 + 近期 +1 应该取负向, 不是 mean 抵消."""
    signals = [
        _feedback_single_signal(-1, 30),  # ~-0.20
        _feedback_single_signal(1, 5),    # ~+0.20
    ]
    result = _feedback_aggregate(signals)
    # 有显著负向 → 走 neg 路径 (即便 +1 信号绝对值更大)
    assert result < 0


def test_aggregate_pos_cooldown_treated_as_neg():
    """+1 / age<3 cooldown 产生负值, 也走 neg 路径 (这正是"避连吃"语义)."""
    signals = [
        _feedback_single_signal(1, 1),  # -0.47 (cooldown)
    ]
    result = _feedback_aggregate(signals)
    assert result < 0


def test_aggregate_clamp_low():
    """多条 -1 / age=0 不应超过 clamp 下限 -1.5."""
    signals = [_feedback_single_signal(-1, 0)] * 5
    assert _feedback_aggregate(signals) == pytest.approx(-1.5, abs=1e-6)


def test_aggregate_clamp_high():
    """正向 clamp 上限 +0.25."""
    signals = [_feedback_single_signal(1, 3)] * 5
    assert _feedback_aggregate(signals) == pytest.approx(0.25, abs=1e-6)


# ─────────────────────── feedback_recency_score combo 级 ───────────────────────


def _combo(name: str) -> dict:
    return {"restaurant": {"id": "r1", "name": name}, "dishes": []}


def test_score_empty_view():
    assert feedback_recency_score(_combo("店A"), None) == 0.0
    assert feedback_recency_score(_combo("店A"), []) == 0.0


def test_score_no_match():
    view = [{"restaurant_name": "店B", "rating": -1, "age_days": 1}]
    assert feedback_recency_score(_combo("店A"), view) == 0.0


def test_score_match_negative():
    view = [{"restaurant_name": "店A", "rating": -1, "age_days": 5}]
    expected = -1.5 * math.exp(-5 / 14.0)
    assert feedback_recency_score(_combo("店A"), view) == pytest.approx(expected, abs=1e-6)


def test_score_combo_missing_name():
    combo = {"restaurant": {}, "dishes": []}
    view = [{"restaurant_name": "店A", "rating": -1, "age_days": 1}]
    assert feedback_recency_score(combo, view) == 0.0


# ─────────────────────── score_combo breakdown keyset 守门 ───────────────────────


def _profile() -> dict:
    return {
        "plate_rule": {"min_protein_g": 0, "must_have_vegetable": False},
        "preferences": {},
        "scoring_weights": {},
    }


def _basic_combo(name: str = "店A") -> dict:
    return {
        "restaurant": {"id": "r1", "name": name, "brand": "B", "category": "湘菜"},
        "dishes": [{
            "dish_id": "d1",
            "canonical_name": "菜1",
            "cuisine": "湘菜",
            "monthly_sales": 100,
            "nutrition_profile": {
                "oil_level": 2,
                "main_ingredient_type": "鸡",
                "dish_role": "主菜",
            },
        }],
    }


def test_score_combo_no_feedback_view_keyset_unchanged():
    """关键 baseline 守门: feedback_view=None 时 breakdown 不含 feedback_recency."""
    s, br = score_combo(_basic_combo(), _profile())
    assert "feedback_recency" not in br


def test_score_combo_empty_feedback_view_keyset_unchanged():
    s, br = score_combo(_basic_combo(), _profile(), feedback_view=[])
    assert "feedback_recency" not in br


def test_score_combo_view_no_match_keyset_unchanged():
    """view 非空但餐厅名不匹配 → 仍不写 key."""
    view = [{"restaurant_name": "其他店", "rating": -1, "age_days": 1}]
    s, br = score_combo(_basic_combo("店A"), _profile(), feedback_view=view)
    assert "feedback_recency" not in br


def test_score_combo_view_match_adds_key():
    view = [{"restaurant_name": "店A", "rating": -1, "age_days": 1}]
    s, br = score_combo(_basic_combo("店A"), _profile(), feedback_view=view)
    assert "feedback_recency" in br
    assert br["feedback_recency"] < 0  # 负反馈应扣分


# ─────────────────────── rank_combos sentinel ───────────────────────


def test_rank_combos_default_path_empty_view(tmp_path):
    """默认路径: 没有 store.json → 等价于 feedback_view=[]."""
    combos = [_basic_combo("店A")]
    today = dt.date(2026, 5, 17)
    ranked = rank_combos(combos, _profile(), [], today, root=tmp_path)
    assert "feedback_recency" not in ranked[0]["score_breakdown"]


def test_rank_combos_explicit_view():
    combos = [_basic_combo("店A"), _basic_combo("店B")]
    today = dt.date(2026, 5, 17)
    view = [{"restaurant_name": "店A", "rating": -1, "age_days": 1}]
    ranked = rank_combos(combos, _profile(), [], today, feedback_view=view)
    # 店A 应被扣分排在店B 后面
    assert ranked[0]["restaurant"]["name"] == "店B"
    assert ranked[1]["restaurant"]["name"] == "店A"
    # 店A breakdown 含 key, 店B 不含 (这是 keyset 不变性的精髓: 非命中条目不增字段)
    a_br = next(c["score_breakdown"] for c in ranked if c["restaurant"]["name"] == "店A")
    b_br = next(c["score_breakdown"] for c in ranked if c["restaurant"]["name"] == "店B")
    assert "feedback_recency" in a_br
    assert "feedback_recency" not in b_br


def test_rank_combos_explicit_empty_view_no_key():
    """显式传 [] 应与默认路径行为一致 — 不读 disk, breakdown 不变."""
    combos = [_basic_combo("店A")]
    today = dt.date(2026, 5, 17)
    ranked = rank_combos(combos, _profile(), [], today, feedback_view=[])
    assert "feedback_recency" not in ranked[0]["score_breakdown"]


def test_rank_combos_sentinel_is_distinct_from_empty_list():
    """sentinel 必须 not == [], 防 What-if 路径误进默认分支."""
    assert _UNSET_FEEDBACK_VIEW is not None
    assert _UNSET_FEEDBACK_VIEW != []


# ─────────────────────── 7 天压制 / 35 天回归 (B-001 验收点) ───────────────────────


def test_feedback_signal_significant_in_7_days():
    """rating=-1 / 7 天内信号绝对值应 >= 0.9 (足以压排序)."""
    for age in range(0, 8):
        s = _feedback_single_signal(-1, age)
        assert s <= -0.9, f"age={age}, signal={s}"


def test_feedback_signal_near_zero_after_35_days():
    """rating=-1 / 35 天后信号绝对值 < 0.2 (基本回归)."""
    for age in range(35, 61):
        s = _feedback_single_signal(-1, age)
        assert abs(s) < 0.2, f"age={age}, signal={s}"

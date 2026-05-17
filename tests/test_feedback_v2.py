"""B-001 v2 测试: 4 维 calibration + note + comments[] 短链路.

覆盖:
- feedback_text_extract: 词表 / 否定 / 边界
- build_feedback_view v2 dict shape: ratings / calibrations / note_tokens
- next_meal_calibration_score: 4 维映射 + 跨餐衰减 + clamp + age_days 硬闸
- note_boost_score: restaurant-scope / 全局高频 / 衰减 / clamp
- score_combo 守门: 信号空时不写新 key (baseline keyset 严格不变)
- _feedback_block: 3 段独立 / 任一空跳过
- normalize_feedback_view: v1 list / v2 dict / None 兼容
"""
from __future__ import annotations

import datetime as dt

import pytest

from chisha.feedback_store import build_feedback_view, normalize_feedback_view
from chisha.feedback_text_extract import extract_tokens
from chisha.score import (
    feedback_recency_score,
    next_meal_calibration_score,
    note_boost_score,
    score_combo,
)
from chisha.rerank import _feedback_block


# ─────────────────────── helpers ───────────────────────

def _profile() -> dict:
    return {
        "plate_rule": {
            "must_have_vegetable": True,
            "min_vegetable_dishes": 1,
            "min_protein_g": 20,
            "prefer_oil_level_at_most": 3,
        },
        "scoring_weights": {},  # 用 V2_DEFAULT_WEIGHTS
        "preferences": {},
    }


def _combo(name="灶台", oil=3, n=2, has_carb=False, has_spicy=False,
           cuisine="湘菜", has_soup=False, has_processed=False):
    """构造单 combo. 用于 score 测试."""
    dishes = []
    for i in range(n):
        np_ = {
            "oil_level": oil,
            "protein_grams_estimate": 25,
            "main_ingredient_type": "红肉",
            "spicy_level": 2 if (has_spicy and i == 0) else 0,
            "wetness": 3 if (has_soup and i == 0) else 0,
            "dish_role": "汤" if (has_soup and i == 0) else "主菜",
            "sweet_sauce_level": 0,
            "processed_meat_flag": True if (has_processed and i == 0) else False,
        }
        dishes.append({
            "canonical_name": f"d{i}",
            "cuisine": cuisine,
            "nutrition_profile": np_,
        })
    if has_carb:
        dishes.append({
            "canonical_name": "米饭",
            "cuisine": cuisine,
            "nutrition_profile": {"oil_level": 1, "dish_role": "主食",
                                   "main_ingredient_type": "主食"},
        })
    return {
        "restaurant_name": name,
        "restaurant": {"name": name, "id": "r_x"},
        "dishes": dishes,
    }


def _store(accepted=None, feedbacks=None, sessions=None):
    return {
        "accepted": accepted or {},
        "feedbacks": feedbacks or {},
        "sessions": sessions or {},
    }


# ─────────────────────── feedback_text_extract ───────────────────────

def test_extract_tokens_positive_low_oil():
    out = extract_tokens("这个菜太油了")
    assert "low_oil" in out["boost"]


def test_extract_tokens_negation_drops():
    out = extract_tokens("不太油")
    assert "low_oil" not in out["boost"]
    assert "low_oil" not in out["penalty"]


def test_extract_tokens_spicy_intent_separated():
    # Codex S5 Q4.1 修订: 按意图拆 boost/penalty, 防互相抵消
    # "想吃辣" = 想要更多 spicy → boost only
    boost_only = extract_tokens("想吃辣")
    assert "spicy" in boost_only["boost"]
    assert "spicy" not in boost_only["penalty"]
    # "太辣" = 嫌辣, 想要更少 → penalty only
    penalty_only = extract_tokens("太辣了")
    assert "spicy" in penalty_only["penalty"]
    assert "spicy" not in penalty_only["boost"]


def test_extract_tokens_low_oil_complaint_to_boost():
    # "太油" = 嫌油 → 想要 low_oil → BOOST low_oil
    out = extract_tokens("这家菜太油")
    assert "low_oil" in out["boost"]
    assert "low_oil" not in out["penalty"]


def test_extract_tokens_empty_and_none():
    assert extract_tokens("") == {"boost": set(), "penalty": set(), "raw_matches": []}
    assert extract_tokens(None) == {"boost": set(), "penalty": set(), "raw_matches": []}


def test_extract_tokens_multi():
    out = extract_tokens("加工肉太油")
    assert "low_oil" in out["boost"]
    assert "processed_meat" in out["penalty"]


def test_extract_tokens_processed_meat_aliases():
    for word in ["火腿", "培根", "香肠"]:
        out = extract_tokens(f"这家{word}多")
        assert "processed_meat" in out["penalty"], f"{word} 应命中"


# ─────────────────────── build_feedback_view v2 ───────────────────────

def test_build_view_returns_dict():
    out = build_feedback_view({}, dt.date(2026, 5, 17))
    assert isinstance(out, dict)
    # D-084: 增加 feedback_trace sibling key (派生层因果快照, 给 trace + DAG 用). 原 D-082, 合并时与 main 冲突重号
    assert set(out.keys()) == {"ratings", "calibrations", "note_tokens",
                                "feedback_trace"}
    assert out["ratings"] == []
    assert out["calibrations"] == []
    assert out["note_tokens"] == []
    assert out["feedback_trace"]["empty"] is True


def test_build_view_calibrations_age_meals_window():
    today = dt.date(2026, 5, 17)
    store = _store(
        accepted={
            "s_today": {"restaurant_name": "店A",
                         "accepted_at": "2026-05-17T12:00:00+00:00",
                         "accepted_rank": 1},
            "s_3d": {"restaurant_name": "店B",
                      "accepted_at": "2026-05-14T12:00:00+00:00",
                      "accepted_rank": 1},
            "s_8d": {"restaurant_name": "店C",
                      "accepted_at": "2026-05-09T12:00:00+00:00",
                      "accepted_rank": 1},
        },
        feedbacks={
            "s_today": {"fullness": 0, "rating": -1,
                         "submitted_at": "2026-05-17T13:00:00+00:00"},
            "s_3d": {"oil_calibration": 2,
                      "submitted_at": "2026-05-14T13:00:00+00:00"},
            "s_8d": {"fullness": 2,
                      "submitted_at": "2026-05-09T13:00:00+00:00"},
        },
    )
    cals = build_feedback_view(store, today)["calibrations"]
    # 8d 超 age_days<=7 硬闸, 应被丢
    assert len(cals) == 2
    assert cals[0]["restaurant_name"] == "店A"
    assert cals[1]["restaurant_name"] == "店B"


def test_build_view_note_tokens_window_14d():
    today = dt.date(2026, 5, 17)
    store = _store(
        accepted={
            "s_recent": {"restaurant_name": "店A",
                          "accepted_at": "2026-05-15T12:00:00+00:00"},
            "s_old": {"restaurant_name": "店B",
                       "accepted_at": "2026-05-01T12:00:00+00:00"},
        },
        feedbacks={
            "s_recent": {"note": "太油了",
                          "submitted_at": "2026-05-15T13:00:00+00:00"},
            "s_old": {"note": "太油了",
                       "submitted_at": "2026-05-01T13:00:00+00:00"},
        },
    )
    notes = build_feedback_view(store, today)["note_tokens"]
    # 16 天前的丢
    assert [n["restaurant_name"] for n in notes] == ["店A"]
    assert "low_oil" in notes[0]["boost"]
    assert notes[0]["source"] == "note"


def test_build_view_comments_use_own_created_at():
    """Codex Q5: comments[] 用每条 comment 自己的 created_at, 不用 feedback submitted_at."""
    today = dt.date(2026, 5, 17)
    store = _store(
        accepted={
            "s1": {"restaurant_name": "店A",
                    "accepted_at": "2026-05-01T12:00:00+00:00"},
        },
        feedbacks={
            "s1": {
                "submitted_at": "2026-05-01T13:00:00+00:00",  # 16 天前
                "comments": [
                    {"text": "太油", "created_at": "2026-05-16T08:00:00+00:00"},  # 1 天前
                    {"text": "太辣", "created_at": "2026-05-01T15:00:00+00:00"},  # 16 天前丢
                ],
            },
        },
    )
    notes = build_feedback_view(store, today)["note_tokens"]
    sources = [(n["source"], n["age_days"]) for n in notes]
    assert ("comment", 1) in sources
    assert all(age <= 14 for _, age in sources)


def test_build_view_last_meal_cuisine_from_sessions():
    today = dt.date(2026, 5, 17)
    store = _store(
        accepted={
            "s1": {"restaurant_name": "店A",
                    "accepted_at": "2026-05-16T12:00:00+00:00",
                    "accepted_rank": 1},
        },
        feedbacks={
            "s1": {"reason_match": 0,
                    "submitted_at": "2026-05-16T13:00:00+00:00"},
        },
        sessions={
            "s1": {"candidates": [{"dishes": [{"cuisine": "湘菜"}]}]},
        },
    )
    cals = build_feedback_view(store, today)["calibrations"]
    assert cals[0]["last_meal_cuisine"] == "湘菜"


def test_build_view_calibrations_max_3():
    today = dt.date(2026, 5, 17)
    accepted = {
        f"s{i}": {"restaurant_name": f"店{i}",
                   "accepted_at": f"2026-05-{17-i:02d}T12:00:00+00:00",
                   "accepted_rank": 1}
        for i in range(5)
    }
    feedbacks = {
        f"s{i}": {"fullness": 0, "submitted_at": f"2026-05-{17-i:02d}T13:00:00+00:00"}
        for i in range(5)
    }
    cals = build_feedback_view(_store(accepted, feedbacks), today)["calibrations"]
    assert len(cals) == 3  # 最近 3 餐


# ─────────────────────── normalize_feedback_view ───────────────────────

def test_normalize_v1_list_to_v2_dict():
    # v1 老 fixture
    v1 = [{"restaurant_name": "店", "rating": -1, "age_days": 3}]
    out = normalize_feedback_view(v1)
    assert out["ratings"] == v1
    assert out["calibrations"] == []
    assert out["note_tokens"] == []


def test_normalize_dict_passthrough():
    v2 = {"ratings": [], "calibrations": [{"x": 1}], "note_tokens": []}
    out = normalize_feedback_view(v2)
    assert out["calibrations"] == [{"x": 1}]


def test_normalize_none_returns_empty():
    out = normalize_feedback_view(None)
    # D-084: 增加 feedback_trace sibling (空骨架, empty=True). 原 D-082, 与 main 冲突重号
    assert out["ratings"] == []
    assert out["calibrations"] == []
    assert out["note_tokens"] == []
    assert out["feedback_trace"]["empty"] is True


# ─────────────────────── feedback_recency_score 兼容 v2 dict ───────────────────────

def test_feedback_recency_accepts_v2_dict():
    view = {"ratings": [{"restaurant_name": "灶台", "rating": -1, "age_days": 0}],
            "calibrations": [], "note_tokens": []}
    s = feedback_recency_score(_combo("灶台"), view)
    assert s == pytest.approx(-1.5)


def test_feedback_recency_accepts_v1_list_still():
    """B-001 v1 老 fixture / 老 frozen trace 仍可用."""
    view = [{"restaurant_name": "灶台", "rating": -1, "age_days": 0}]
    s = feedback_recency_score(_combo("灶台"), view)
    assert s == pytest.approx(-1.5)


# ─────────────────────── next_meal_calibration_score ───────────────────────

def test_calibration_empty_returns_zero():
    s = next_meal_calibration_score(_combo(), {"ratings": [], "calibrations": [],
                                                 "note_tokens": []}, _profile())
    assert s == 0.0


def test_calibration_fullness_0_boosts_protein_rich():
    """fullness=0 + combo 满足 protein_floor + 多菜 → +"""
    view = {"ratings": [], "note_tokens": [],
            "calibrations": [{"fullness": 0, "age_days": 0,
                               "oil_calibration": None, "reason_match": None,
                               "repurchase_intent": None,
                               "last_meal_cuisine": None,
                               "restaurant_name": "x"}]}
    big = _combo(n=3)  # 3 dishes, all protein 25g
    s = next_meal_calibration_score(big, view, _profile())
    assert s > 0  # protein_floor_ok + n>=3


def test_calibration_oil_2_penalizes_high_oil():
    view = {"ratings": [], "note_tokens": [],
            "calibrations": [{"oil_calibration": 2, "age_days": 0,
                               "fullness": None, "reason_match": None,
                               "repurchase_intent": None,
                               "last_meal_cuisine": None,
                               "restaurant_name": "x"}]}
    oily = _combo(oil=5)
    s = next_meal_calibration_score(oily, view, _profile())
    assert s == pytest.approx(-0.5)


def test_calibration_oil_2_boosts_low_oil():
    view = {"ratings": [], "note_tokens": [],
            "calibrations": [{"oil_calibration": 2, "age_days": 0,
                               "fullness": None, "reason_match": None,
                               "repurchase_intent": None,
                               "last_meal_cuisine": None,
                               "restaurant_name": "x"}]}
    light = _combo(oil=2)
    s = next_meal_calibration_score(light, view, _profile())
    assert s == pytest.approx(0.5)


def test_calibration_age_meals_decay():
    """age_meals=1 应取一半权重. Codex S5 Q4.2: 显式 age_meals 字段."""
    cal0 = {"oil_calibration": 2, "age_days": 0, "age_meals": 0,
             "fullness": None, "reason_match": None,
             "repurchase_intent": None,
             "last_meal_cuisine": None, "restaurant_name": "x"}
    cal1 = dict(cal0, age_meals=1)
    view0 = {"ratings": [], "note_tokens": [], "calibrations": [cal0]}
    view1 = {"ratings": [], "note_tokens": [], "calibrations": [cal0, cal1]}
    oily = _combo(oil=5)
    s0 = next_meal_calibration_score(oily, view0, _profile())
    s1 = next_meal_calibration_score(oily, view1, _profile())
    # s1 = -0.5 (age_meals=0) + -0.5*0.5 (age_meals=1) = -0.75
    assert s0 == pytest.approx(-0.5)
    assert s1 == pytest.approx(-0.75)


def test_calibration_age_days_hard_limit():
    """Codex Q1: age_days>7 即使在 calibrations[] 里也丢."""
    view = {"ratings": [], "note_tokens": [],
            "calibrations": [{"oil_calibration": 2, "age_days": 10,
                               "fullness": None, "reason_match": None,
                               "repurchase_intent": None,
                               "last_meal_cuisine": None,
                               "restaurant_name": "x"}]}
    s = next_meal_calibration_score(_combo(oil=5), view, _profile())
    assert s == 0.0


def test_calibration_reason_match_needs_cuisine():
    """reason_match=0 + last_meal_cuisine=湘菜 + combo=日式 → +0.2"""
    view = {"ratings": [], "note_tokens": [],
            "calibrations": [{"reason_match": 0, "age_days": 0,
                               "last_meal_cuisine": "湘菜",
                               "oil_calibration": None, "fullness": None,
                               "repurchase_intent": None,
                               "restaurant_name": "x"}]}
    different = _combo(cuisine="日式")
    same = _combo(cuisine="湘菜")
    assert next_meal_calibration_score(different, view, _profile()) == pytest.approx(0.2)
    # 同 cuisine 不加分
    assert next_meal_calibration_score(same, view, _profile()) == 0.0


def test_calibration_repurchase_intent_noop():
    """Codex 共识: repurchase_intent v2 短链路 no-op."""
    view = {"ratings": [], "note_tokens": [],
            "calibrations": [{"repurchase_intent": 2, "age_days": 0,
                               "oil_calibration": None, "fullness": None,
                               "reason_match": None,
                               "last_meal_cuisine": None,
                               "restaurant_name": "x"}]}
    s = next_meal_calibration_score(_combo(), view, _profile())
    assert s == 0.0


def test_calibration_clamp_upper():
    """多正向信号叠加, clamp 到 +1.0."""
    cals = [
        {"oil_calibration": 2, "fullness": 0, "age_days": 0,
         "reason_match": None, "repurchase_intent": None,
         "last_meal_cuisine": None, "restaurant_name": "x"},
    ]
    view = {"ratings": [], "note_tokens": [], "calibrations": cals}
    big_light = _combo(oil=2, n=4)  # +0.5 (oil) +0.4 (protein) +0.3 (n>=3)
    s = next_meal_calibration_score(big_light, view, _profile())
    assert s <= 1.0  # clamp 上限
    assert s > 0.9


# ─────────────────────── note_boost_score ───────────────────────

def test_note_boost_empty_returns_zero():
    s = note_boost_score(_combo(),
                          {"ratings": [], "calibrations": [], "note_tokens": []},
                          _profile())
    assert s == 0.0


def test_note_boost_restaurant_scope_penalty_hits():
    """灶台 note '太油' → 灶台高油 combo 应被扣."""
    view = {"ratings": [], "calibrations": [],
            "note_tokens": [{"restaurant_name": "灶台", "age_days": 0,
                              "boost": ["low_oil"], "penalty": [],
                              "raw_text": "太油", "source": "note"}]}
    oily = _combo("灶台", oil=5)
    # boost low_oil + combo 反命中 (oil>=4) → -0.5 * 1.0 = -0.5
    assert note_boost_score(oily, view, _profile()) == pytest.approx(-0.5)


def test_note_boost_restaurant_scope_other_restaurant_immune():
    view = {"ratings": [], "calibrations": [],
            "note_tokens": [{"restaurant_name": "灶台", "age_days": 0,
                              "boost": ["low_oil"], "penalty": [],
                              "raw_text": "太油", "source": "note"}]}
    other = _combo("别家", oil=5)
    assert note_boost_score(other, view, _profile()) == 0.0


def test_note_boost_global_frequency():
    """同 token 在不同餐厅命中 ≥2 次 → 弱影响所有 combo."""
    view = {"ratings": [], "calibrations": [],
            "note_tokens": [
                {"restaurant_name": "A", "age_days": 0,
                 "boost": ["low_oil"], "penalty": [],
                 "raw_text": "太油", "source": "note"},
                {"restaurant_name": "B", "age_days": 1,
                 "boost": ["low_oil"], "penalty": [],
                 "raw_text": "油大", "source": "note"},
            ]}
    other_oily = _combo("C", oil=5)
    s = note_boost_score(other_oily, view, _profile())
    # 全局 low_oil ×2 + age_min=0 → decay=1.0, m=-1 → -0.2
    assert s == pytest.approx(-0.2)


def test_note_boost_decay():
    view_old = {"ratings": [], "calibrations": [],
                "note_tokens": [{"restaurant_name": "灶台", "age_days": 7,
                                  "boost": ["low_oil"], "penalty": [],
                                  "raw_text": "", "source": "note"}]}
    oily = _combo("灶台", oil=5)
    import math
    expected = -0.5 * math.exp(-7 / 7.0)  # decay = 1/e
    assert note_boost_score(oily, view_old, _profile()) == pytest.approx(expected)


def test_note_boost_clamp():
    """大量同向信号 clamp 到 ±1.0."""
    notes = [{"restaurant_name": "灶台", "age_days": 0,
              "boost": ["low_oil"], "penalty": [],
              "raw_text": "", "source": "note"}] * 5  # 5 条全 -0.5 → -2.5
    view = {"ratings": [], "calibrations": [], "note_tokens": notes}
    oily = _combo("灶台", oil=5)
    s = note_boost_score(oily, view, _profile())
    assert s == pytest.approx(-1.0)


# ─────────────────────── score_combo 守门 ───────────────────────

def test_score_combo_baseline_keyset_when_view_empty():
    """B-001 v2 baseline 守门: view 空时 next_meal_calibration / note_boost 不写 key."""
    view: dict = {"ratings": [], "calibrations": [], "note_tokens": []}
    _, br = score_combo(_combo(), _profile(), [], dt.date(2026, 5, 17),
                         feedback_view=view)
    assert "next_meal_calibration" not in br
    assert "note_boost" not in br
    assert "feedback_recency" not in br  # v1 守门一并验


def test_score_combo_writes_calibration_key_when_signal():
    view = {"ratings": [], "note_tokens": [],
            "calibrations": [{"oil_calibration": 2, "age_days": 0,
                               "fullness": None, "reason_match": None,
                               "repurchase_intent": None,
                               "last_meal_cuisine": None,
                               "restaurant_name": "x"}]}
    _, br = score_combo(_combo(oil=5), _profile(), [], dt.date(2026, 5, 17),
                         feedback_view=view)
    assert "next_meal_calibration" in br
    assert br["next_meal_calibration"] < 0


def test_score_combo_writes_note_key_when_signal():
    view = {"ratings": [], "calibrations": [],
            "note_tokens": [{"restaurant_name": "灶台", "age_days": 0,
                              "boost": ["low_oil"], "penalty": [],
                              "raw_text": "", "source": "note"}]}
    _, br = score_combo(_combo("灶台", oil=5), _profile(), [],
                         dt.date(2026, 5, 17), feedback_view=view)
    assert "note_boost" in br
    assert br["note_boost"] < 0


# ─────────────────────── _feedback_block prompt 渲染 ───────────────────────

def test_feedback_block_all_empty_returns_none():
    out = _feedback_block({"ratings": [], "calibrations": [], "note_tokens": []})
    assert out is None


def test_feedback_block_recent_section_only():
    view = {"ratings": [{"restaurant_name": "灶台", "rating": -1, "age_days": 3}],
            "calibrations": [], "note_tokens": []}
    out = _feedback_block(view)
    assert "[FEEDBACK_RECENT]" in out
    assert "[LAST_MEAL_SIGNAL]" not in out
    assert "[NOTE_HINTS]" not in out


def test_feedback_block_calibration_section():
    view = {"ratings": [], "note_tokens": [],
            "calibrations": [{"restaurant_name": "灶台", "age_days": 1,
                               "fullness": 0, "oil_calibration": 2,
                               "reason_match": None, "repurchase_intent": None,
                               "last_meal_cuisine": None}]}
    out = _feedback_block(view)
    assert "[LAST_MEAL_SIGNAL]" in out
    assert "太油" in out
    assert "饱腹感不够" in out


def test_feedback_block_note_section():
    view = {"ratings": [], "calibrations": [],
            "note_tokens": [{"restaurant_name": "灶台", "age_days": 2,
                              "boost": ["low_oil"], "penalty": [],
                              "raw_text": "太油了", "source": "note"}]}
    out = _feedback_block(view)
    assert "[NOTE_HINTS]" in out
    assert "low_oil" in out
    assert "灶台" in out


def test_feedback_block_v1_list_back_compat():
    """老 frozen trace (list shape) 仍能渲染."""
    v1 = [{"restaurant_name": "灶台", "rating": -1, "age_days": 3}]
    out = _feedback_block(v1)
    assert "[FEEDBACK_RECENT]" in out


# ─────────────────────── Codex S5 修订专项 ───────────────────────

def test_build_view_age_meals_explicit_field():
    """Codex S5 Q4.2/Q4.5: cal 必须带显式 age_meals 字段, 不靠 enumerate."""
    today = dt.date(2026, 5, 17)
    store = _store(
        accepted={
            f"s{i}": {"restaurant_name": f"店{i}",
                       "accepted_at": f"2026-05-{17-i:02d}T12:00:00+00:00",
                       "accepted_rank": 1}
            for i in range(3)
        },
        feedbacks={
            f"s{i}": {"fullness": 0,
                       "submitted_at": f"2026-05-{17-i:02d}T13:00:00+00:00"}
            for i in range(3)
        },
    )
    cals = build_feedback_view(store, today)["calibrations"]
    # 最新在前, age_meals=0,1,2
    assert [c["age_meals"] for c in cals] == [0, 1, 2]
    # 内部字段 _when_dt_iso 不暴露
    assert all("_when_dt_iso" not in c for c in cals)


def test_build_view_same_day_two_meals_distinct_age_meals():
    """Codex S5 Q4.2 必改: 同日午/晚餐 datetime 区分, 不漂."""
    today = dt.date(2026, 5, 17)
    store = _store(
        accepted={
            "s_lunch": {"restaurant_name": "午", "accepted_rank": 1,
                         "accepted_at": "2026-05-17T12:00:00+00:00"},
            "s_dinner": {"restaurant_name": "晚", "accepted_rank": 1,
                          "accepted_at": "2026-05-17T19:00:00+00:00"},
        },
        feedbacks={
            "s_lunch": {"fullness": 2,
                         "submitted_at": "2026-05-17T13:00:00+00:00"},
            "s_dinner": {"fullness": 0,
                          "submitted_at": "2026-05-17T20:00:00+00:00"},
        },
    )
    cals = build_feedback_view(store, today)["calibrations"]
    # 晚餐更近 → age_meals=0
    assert cals[0]["restaurant_name"] == "晚"
    assert cals[0]["age_meals"] == 0
    assert cals[1]["restaurant_name"] == "午"
    assert cals[1]["age_meals"] == 1


def test_note_boost_global_freq_dedup_by_restaurant():
    """Codex S5 Q4.3 必改: 同餐厅多条 note/comment 触发同 token 只算 1 次."""
    # 4 条 note 全部来自店A, low_oil token → 频次按 restaurant=1, 不到 ≥2, 不应触发全局
    view = {"ratings": [], "calibrations": [],
            "note_tokens": [
                {"restaurant_name": "店A", "age_days": i,
                 "boost": ["low_oil"], "penalty": [],
                 "raw_text": "油", "source": "note"}
                for i in range(4)
            ]}
    # combo 是别家 (店B), 餐厅级不命中, 全局也不应命中
    other_oily = _combo("店B", oil=5)
    assert note_boost_score(other_oily, view, _profile()) == 0.0


def test_note_boost_global_freq_dedup_2_restaurants():
    """跨 2 餐厅同 token → 全局触发."""
    view = {"ratings": [], "calibrations": [],
            "note_tokens": [
                {"restaurant_name": "店A", "age_days": 0,
                 "boost": ["low_oil"], "penalty": [],
                 "raw_text": "", "source": "note"},
                {"restaurant_name": "店A", "age_days": 1,
                 "boost": ["low_oil"], "penalty": [],
                 "raw_text": "", "source": "comment"},
                {"restaurant_name": "店B", "age_days": 0,
                 "boost": ["low_oil"], "penalty": [],
                 "raw_text": "", "source": "note"},
            ]}
    other_oily = _combo("店C", oil=5)
    # 2 unique 餐厅 ≥2 → 触发, m=-1 (反命中), decay=1, signal = -0.2
    assert note_boost_score(other_oily, view, _profile()) == pytest.approx(-0.2)


def test_calibration_fullness_tightened_threshold():
    """Codex S5 Q6 收紧: protein 必须 >= 1.5x floor (而非简单 floor_pass)."""
    profile = _profile()  # min_protein_g=20
    view = {"ratings": [], "note_tokens": [],
            "calibrations": [{"fullness": 0, "age_days": 0, "age_meals": 0,
                               "oil_calibration": None, "reason_match": None,
                               "repurchase_intent": None,
                               "last_meal_cuisine": None, "restaurant_name": "x"}]}
    # 刚好 25g (达 floor 但不到 1.5×=30g) — fullness 不触发 protein boost
    just_floor = _combo(n=1)  # 25g 一道
    # 加蔬菜让它 plate_rule pass, 但 protein 总只 25
    just_floor['dishes'].append({
        'canonical_name':'素','cuisine':'湘菜',
        'nutrition_profile':{'oil_level':2,'protein_grams_estimate':0,
                              'main_ingredient_type':'纯素','dish_role':'配菜'}
    })
    s_just = next_meal_calibration_score(just_floor, view, profile)
    # 远超 floor 60g — 触发
    big = _combo(n=3)  # 25g × 3 = 75 >= 30
    s_big = next_meal_calibration_score(big, view, profile)
    assert s_just < s_big  # tightened threshold 让大蛋白拿更多 boost


def test_feedback_block_three_sections_together():
    view = {
        "ratings": [{"restaurant_name": "A", "rating": -1, "age_days": 1}],
        "calibrations": [{"restaurant_name": "B", "age_days": 0,
                           "oil_calibration": 2, "fullness": None,
                           "reason_match": None, "repurchase_intent": None,
                           "last_meal_cuisine": None}],
        "note_tokens": [{"restaurant_name": "C", "age_days": 1,
                          "boost": ["low_oil"], "penalty": [],
                          "raw_text": "油", "source": "note"}],
    }
    out = _feedback_block(view)
    assert "[FEEDBACK_RECENT]" in out
    assert "[LAST_MEAL_SIGNAL]" in out
    assert "[NOTE_HINTS]" in out

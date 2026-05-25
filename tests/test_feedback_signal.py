"""B-001 / D-098: feedback_signal.py 信号构建单测.

覆盖: 组合C极性 + Q-B 冲突规则, 线性衰减边界, 餐厅级累积 / 菜品级弱+累积,
recall 剔除清单, 降级 (无 session 冷存 / rank 越界), 无反馈 → 空 dict (0-diff).
"""
from __future__ import annotations

import datetime as dt

from chisha.feedback_signal import (
    BOOST,
    MILD_NEG,
    NEUTRAL,
    STRONG_NEG,
    _decay_factor,
    _polarity,
    build_feedback_signal,
    evicted_restaurant_ids,
)

TODAY = dt.date(2026, 5, 25)


def _iso(days_ago: int) -> str:
    d = TODAY - dt.timedelta(days=days_ago)
    return dt.datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=dt.timezone.utc).isoformat()


def _store(sid: str, *, rating, repurchase, days_ago, rid="r1",
           dish_ids=("d1", "d2"), rank=1, with_session=True):
    fb = {
        "session_id": sid,
        "rating": rating,
        "repurchase_intent": repurchase,
        "accepted_rank": rank,
        "submitted_at": _iso(days_ago),
    }
    store = {"accepted": {}, "feedbacks": {sid: fb}, "sessions": {}}
    if with_session:
        store["sessions"][sid] = {
            "candidates": [
                {"rank": rank, "restaurant": {"id": rid},
                 "dishes": [{"dish_id": x} for x in dish_ids]}
            ] * rank  # 保证 candidates[rank-1] 存在
        }
    return store


# ─────────────────────── _polarity (组合C + Q-B)
def test_polarity_strong_neg():
    assert _polarity(-1, 0) == STRONG_NEG


def test_polarity_boost_double_positive():
    assert _polarity(1, 2) == BOOST


def test_polarity_repurchase2_overrides_bad_rating():
    # 难吃但想再吃 → 不抑制 (repurchase 为准)
    assert _polarity(-1, 2) == NEUTRAL


def test_polarity_repurchase0_overrides_good_rating():
    # 好吃但不想再吃 → mild 抑制 (repurchase 为准)
    assert _polarity(1, 0) == MILD_NEG


def test_polarity_rating_drives_when_repurchase_neutral():
    assert _polarity(-1, 1) == MILD_NEG
    assert _polarity(-1, None) == MILD_NEG


def test_polarity_good_rating_alone_not_boost():
    # rating==1 但非双正 → 保守不 boost
    assert _polarity(1, 1) == NEUTRAL
    assert _polarity(1, None) == NEUTRAL


# ─────────────────────── _decay_factor
def test_decay_neg_full_window():
    assert _decay_factor(STRONG_NEG, 0) == 1.0
    assert _decay_factor(STRONG_NEG, 30) == 1.0


def test_decay_neg_linear_midpoint():
    assert _decay_factor(STRONG_NEG, 45) == 0.5


def test_decay_neg_expired():
    assert _decay_factor(STRONG_NEG, 61) == 0.0


def test_decay_boost_cooldown_zero():
    assert _decay_factor(BOOST, 5) == 0.0


def test_decay_boost_active_window():
    assert _decay_factor(BOOST, 15) == 1.0


def test_decay_future_timestamp_zero():
    assert _decay_factor(STRONG_NEG, -3) == 0.0


# ─────────────────────── build_feedback_signal
def test_empty_store_returns_empty_maps():
    sig = build_feedback_signal({"feedbacks": {}, "sessions": {}, "accepted": {}}, TODAY)
    assert sig == {"restaurant": {}, "dish": {}, "recall_evict": {}, "evict_names": {}}


def test_strong_neg_restaurant_and_evict():
    store = _store("s1", rating=-1, repurchase=0, days_ago=5, rid="r9")
    # 给 cold-store candidate 一个店名, 验 evict_names 透传
    store["sessions"]["s1"]["candidates"][0]["restaurant"]["name"] = "差评小馆"
    sig = build_feedback_signal(store, TODAY)
    assert sig["restaurant"]["r9"] == -1.0
    assert sig["recall_evict"]["r9"] == 25  # 30 - 5
    assert sig["evict_names"]["r9"] == "差评小馆"
    assert "r9" in evicted_restaurant_ids(sig)
    # 菜品级弱 (= -1.0 * DISH_ACCUM_UNIT 0.4)
    assert sig["dish"]["d1"] == -0.4


def test_mild_neg_no_evict_names():
    # mild_neg 不进 recall_evict / evict_names
    store = _store("s1", rating=-1, repurchase=1, days_ago=2, rid="r5")
    sig = build_feedback_signal(store, TODAY)
    assert sig["evict_names"] == {}


def test_mild_neg_no_evict():
    store = _store("s1", rating=-1, repurchase=1, days_ago=2, rid="r5")
    sig = build_feedback_signal(store, TODAY)
    assert sig["restaurant"]["r5"] == -0.6
    assert "r5" not in sig["recall_evict"]


def test_boost_active():
    store = _store("s1", rating=1, repurchase=2, days_ago=15, rid="r3")
    sig = build_feedback_signal(store, TODAY)
    assert sig["restaurant"]["r3"] == 0.3  # BOOST base (弱), 非对称 < |neg|
    assert sig["recall_evict"] == {}


def test_neutral_feedback_skipped():
    store = _store("s1", rating=-1, repurchase=2, days_ago=3)
    sig = build_feedback_signal(store, TODAY)
    assert sig == {"restaurant": {}, "dish": {}, "recall_evict": {}, "evict_names": {}}


def test_expired_feedback_skipped():
    store = _store("s1", rating=-1, repurchase=0, days_ago=90, rid="r1")
    sig = build_feedback_signal(store, TODAY)
    assert sig["restaurant"] == {}
    assert sig["recall_evict"] == {}


def test_restaurant_accumulation_clamped():
    # 同店两次强负 → clamp 到 -1.0 (不会 -2.0)
    store = {
        "accepted": {}, "sessions": {}, "feedbacks": {
            "s1": {"session_id": "s1", "rating": -1, "repurchase_intent": 0,
                   "accepted_rank": 1, "submitted_at": _iso(3)},
            "s2": {"session_id": "s2", "rating": -1, "repurchase_intent": 0,
                   "accepted_rank": 1, "submitted_at": _iso(10)},
        }
    }
    cand = {"candidates": [{"rank": 1, "restaurant": {"id": "rX"},
                            "dishes": [{"dish_id": "dA"}]}]}
    store["sessions"]["s1"] = cand
    store["sessions"]["s2"] = cand
    sig = build_feedback_signal(store, TODAY)
    assert sig["restaurant"]["rX"] == -1.0
    # evict 取最大剩余天数 (3 天前那条 → 27)
    assert sig["recall_evict"]["rX"] == 27


def test_dish_cross_combo_accumulation():
    # 同一 dish 在两个不同店的差评 combo 出现 → 跨 combo 累积 (单次弱)
    store = {
        "accepted": {}, "sessions": {}, "feedbacks": {
            "s1": {"session_id": "s1", "rating": -1, "repurchase_intent": 0,
                   "accepted_rank": 1, "submitted_at": _iso(3)},
            "s2": {"session_id": "s2", "rating": -1, "repurchase_intent": 0,
                   "accepted_rank": 1, "submitted_at": _iso(3)},
        }
    }
    store["sessions"]["s1"] = {"candidates": [{"rank": 1, "restaurant": {"id": "rA"},
                                               "dishes": [{"dish_id": "shared"}]}]}
    store["sessions"]["s2"] = {"candidates": [{"rank": 1, "restaurant": {"id": "rB"},
                                               "dishes": [{"dish_id": "shared"}]}]}
    sig = build_feedback_signal(store, TODAY)
    # 单次 -0.4, 两次累加 → -0.8 (弱信号累积成较强)
    assert abs(sig["dish"]["shared"] - (-0.8)) < 1e-9


def test_degrade_no_session_cold_store():
    store = _store("s1", rating=-1, repurchase=0, days_ago=2, with_session=False)
    sig = build_feedback_signal(store, TODAY)
    assert sig == {"restaurant": {}, "dish": {}, "recall_evict": {}, "evict_names": {}}


def test_degrade_rank_out_of_range():
    store = _store("s1", rating=-1, repurchase=0, days_ago=2, rank=1)
    # 篡改 rank 越界
    store["feedbacks"]["s1"]["accepted_rank"] = 99
    sig = build_feedback_signal(store, TODAY)
    assert sig == {"restaurant": {}, "dish": {}, "recall_evict": {}, "evict_names": {}}


def test_degrade_bad_timestamp():
    store = _store("s1", rating=-1, repurchase=0, days_ago=2)
    store["feedbacks"]["s1"]["submitted_at"] = "not-a-date"
    sig = build_feedback_signal(store, TODAY)
    assert sig == {"restaurant": {}, "dish": {}, "recall_evict": {}, "evict_names": {}}


# ─────────────────────── score 消费: feedback_recency_bonus (T-FB-02)
def _combo(rid, dish_ids):
    return {"restaurant": {"id": rid},
            "dishes": [{"dish_id": x} for x in dish_ids]}


def _full_combo(rid, dish_ids):
    """带完整 nutrition_profile 的 combo, 供 score_combo / rank_combos 集成测试."""
    np_ = {"main_ingredient_type": "白肉", "cooking_method": "炒", "oil_level": 2,
           "spicy_level": 0, "wetness": 1, "dish_role": "主菜",
           "sweet_sauce_level": 0, "processed_meat_flag": False,
           "protein_grams_estimate": 20, "vegetable_ratio_estimate": 0.0,
           "is_complete_meal": False, "grain_type": None}
    return {"restaurant": {"id": rid, "name": rid, "distance_m": 1000,
                           "delivery_eta_min": 30},
            "dishes": [{"dish_id": x, "canonical_name": x, "raw_name": x,
                        "restaurant_id": rid, "cuisine": "其他", "price": 20.0,
                        "monthly_sales": 100, "nutrition_profile": dict(np_),
                        "metadata": {"is_available": True}} for x in dish_ids]}


def test_bonus_none_signal_zero():
    from chisha.score import feedback_recency_bonus
    assert feedback_recency_bonus(_combo("r1", ["d1"]), None) == 0.0


def test_bonus_no_feedback_for_restaurant_zero():
    from chisha.score import feedback_recency_bonus
    sig = {"restaurant": {"rX": -1.0}, "dish": {}, "recall_evict": {}}
    assert feedback_recency_bonus(_combo("rOther", ["d9"]), sig) == 0.0


def test_bonus_restaurant_plus_dish():
    from chisha.score import feedback_recency_bonus, FEEDBACK_DISH_SUBWEIGHT
    sig = {"restaurant": {"rA": -1.0}, "dish": {"d1": -0.4}, "recall_evict": {}}
    # combo rA, 2 dishes (d1 命中, d2 无) → dish 均值 = -0.4/2 = -0.2
    bonus = feedback_recency_bonus(_combo("rA", ["d1", "d2"]), sig)
    assert abs(bonus - (-1.0 + FEEDBACK_DISH_SUBWEIGHT * -0.2)) < 1e-9


def test_score_combo_gating_zero_diff(basic_profile):
    # fb_signal=None → feedback_recency 维 = 0 (对无反馈 combo 0-diff)
    from chisha.score import score_combo
    _, br_none = score_combo(_full_combo("r1", ["d1"]), basic_profile, fb_signal=None)
    assert br_none["feedback_recency"] == 0.0


def test_rank_combos_explicit_none_disables(basic_profile):
    # 显式传 feedback_signal_override=None → 不读 store, feedback_recency 全 0
    from chisha.score import rank_combos
    ranked = rank_combos([_full_combo("r1", ["d1"])], basic_profile,
                         feedback_signal_override=None)
    assert ranked[0]["score_breakdown"]["feedback_recency"] == 0.0


def test_rank_combos_override_applies(basic_profile):
    from chisha.score import rank_combos, V2_DEFAULT_WEIGHTS
    sig = {"restaurant": {"rNeg": -1.0}, "dish": {}, "recall_evict": {}}
    ranked = rank_combos([_full_combo("rNeg", ["d1"])], basic_profile,
                         feedback_signal_override=sig)
    expect = -1.0 * V2_DEFAULT_WEIGHTS["feedback_recency"]
    assert abs(ranked[0]["score_breakdown"]["feedback_recency"] - expect) < 1e-9


# ─────────────────────── recall 强负剔除 (T-FB-03)
def test_recall_evicts_strong_neg_restaurant(basic_profile):
    from chisha.recall import recall
    from tests.conftest import make_dish, make_restaurant
    r_bad = make_restaurant("r_bad", name="差评店")
    r_ok = make_restaurant("r_ok", name="正常店")
    dishes = [
        make_dish(dish_id="b1", restaurant_id="r_bad",
                  main_ingredient_type="红肉", protein_grams_estimate=30),
        make_dish(dish_id="b2", restaurant_id="r_bad",
                  main_ingredient_type="纯素", vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3),
        make_dish(dish_id="o1", restaurant_id="r_ok",
                  main_ingredient_type="红肉", protein_grams_estimate=30),
        make_dish(dish_id="o2", restaurant_id="r_ok",
                  main_ingredient_type="纯素", vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3),
    ]
    # 无信号 → 两家都召回
    base = recall(basic_profile, [r_bad, r_ok], dishes, [])
    base_rids = {c["restaurant"]["id"] for c in base}
    assert {"r_bad", "r_ok"} <= base_rids

    # 强负剔除 r_bad → 只剩 r_ok
    sig = {"restaurant": {"r_bad": -1.0}, "dish": {},
           "recall_evict": {"r_bad": 25}}
    evicted = recall(basic_profile, [r_bad, r_ok], dishes, [], feedback_signal=sig)
    evicted_rids = {c["restaurant"]["id"] for c in evicted}
    assert "r_bad" not in evicted_rids
    assert "r_ok" in evicted_rids


# ─────────────────────── rerank narrative 避开块 (T-FB-05, 名字 list 驱动)
def test_avoided_block_none_when_empty():
    from chisha.rerank import _feedback_avoided_block
    assert _feedback_avoided_block(None) is None
    assert _feedback_avoided_block([]) is None


def test_avoided_block_lists_evicted_names():
    from chisha.rerank import _feedback_avoided_block
    block = _feedback_avoided_block(["差评小馆", "难吃居"])
    assert block is not None
    assert "差评小馆" in block and "难吃居" in block
    assert "FEEDBACK_AVOIDED" in block


def test_build_user_message_includes_avoided(basic_profile):
    from chisha.rerank import build_user_message
    msg = build_user_message([], basic_profile, None, n=5, n_explore=2,
                             feedback_avoided_names=["差评小馆"])
    assert "FEEDBACK_AVOIDED" in msg
    assert "差评小馆" in msg
    # 未传时不含该段 (0-diff prompt)
    msg2 = build_user_message([], basic_profile, None, n=5, n_explore=2)
    assert "FEEDBACK_AVOIDED" not in msg2


def test_recall_evicted_out_only_would_appear(basic_profile):
    # Codex BLOCKER 修复: feedback_evicted_out 只含"过了其它所有过滤、本会出现、
    # 仅因强负反馈被剔除"的店. 跨 zone / 不在候选域的店不入 (narrative 忠实归因).
    from chisha.recall import recall
    from tests.conftest import make_dish, make_restaurant
    r_bad = make_restaurant("r_bad", name="差评店")
    dishes = [
        make_dish(dish_id="b1", restaurant_id="r_bad",
                  main_ingredient_type="红肉", protein_grams_estimate=30),
        make_dish(dish_id="b2", restaurant_id="r_bad",
                  main_ingredient_type="纯素", vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3),
    ]
    # 信号含一个在 zone 的强负店 (r_bad) + 一个不在本次数据里的店 (r_ghost)
    sig = {"restaurant": {"r_bad": -1.0, "r_ghost": -1.0}, "dish": {},
           "recall_evict": {"r_bad": 25, "r_ghost": 25},
           "evict_names": {"r_bad": "差评店", "r_ghost": "幽灵店"}}
    captured: set[str] = set()
    out = recall(basic_profile, [r_bad], dishes, [],
                 feedback_signal=sig, feedback_evicted_out=captured)
    # r_bad 本会出现 (有合格菜) 且被 feedback 剔除 → 入 captured; r_ghost 不在数据 → 不入
    assert captured == {"r_bad"}
    assert all(c["restaurant"]["id"] != "r_bad" for c in out)


def test_recall_evicted_out_excludes_no_combo_restaurant(basic_profile):
    # Codex BLOCKER 再修复: 强负店有 surviving dish 但因价格超限组不成最终 combo →
    # 本就不会出现 → 不入 feedback_evicted_out (不能归因给 feedback).
    import copy
    from chisha.recall import recall
    from tests.conftest import make_dish, make_restaurant
    profile = copy.deepcopy(basic_profile)
    profile["price_range"] = {"hard_max_lunch": 30, "hard_max_dinner": 30}
    r_bad = make_restaurant("r_bad", name="贵价差评店")
    dishes = [
        make_dish(dish_id="b1", restaurant_id="r_bad", price=200.0,
                  main_ingredient_type="红肉", protein_grams_estimate=30),
        make_dish(dish_id="b2", restaurant_id="r_bad", price=200.0,
                  main_ingredient_type="纯素", vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3),
    ]
    sig = {"restaurant": {"r_bad": -1.0}, "dish": {},
           "recall_evict": {"r_bad": 25}, "evict_names": {"r_bad": "贵价差评店"}}
    captured: set[str] = set()
    recall(profile, [r_bad], dishes, [], meal_type="lunch",
           feedback_signal=sig, feedback_evicted_out=captured)
    # combo 总价 400 > hard_max 30 → 无最终 combo → 不归因给 feedback
    assert captured == set()


def test_recall_expired_evict_not_filtered(basic_profile):
    # recall_evict 剩余天数 <= 0 → 不剔除 (已过 30 天窗口)
    from chisha.recall import recall
    from tests.conftest import make_dish, make_restaurant
    r_bad = make_restaurant("r_bad", name="差评店")
    dishes = [
        make_dish(dish_id="b1", restaurant_id="r_bad",
                  main_ingredient_type="红肉", protein_grams_estimate=30),
        make_dish(dish_id="b2", restaurant_id="r_bad",
                  main_ingredient_type="纯素", vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3),
    ]
    sig = {"restaurant": {}, "dish": {}, "recall_evict": {"r_bad": 0}}
    out = recall(basic_profile, [r_bad], dishes, [], feedback_signal=sig)
    assert any(c["restaurant"]["id"] == "r_bad" for c in out)

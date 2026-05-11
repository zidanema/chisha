"""V2 score 维度单测 (D-033 5 新字段 + 履约 + taste_match + context_boost).

V1 行为见 tests/test_score.py.
"""
from __future__ import annotations

import datetime as dt

import pytest

from chisha.context import ContextSnapshot
from chisha.score import (
    V2_DEFAULT_WEIGHTS,
    carb_quality_score,
    context_boost,
    dish_role_match_bonus,
    distance_penalty,
    eta_penalty,
    price_penalty,
    processed_meat_penalty,
    score_combo,
    sweet_sauce_penalty,
    soup_or_broth_bonus,
    taste_match_bonus,
)
from tests.conftest import make_dish, make_restaurant


def _combo(dishes, restaurant=None):
    return {"dishes": dishes,
            "restaurant": restaurant or make_restaurant()}


# ─────────────────────── carb_quality
def test_carb_quality_whole_grain_positive():
    c = _combo([make_dish(dish_role="主食", grain_type="糙米")])
    assert carb_quality_score(c) == 1.0


def test_carb_quality_refined_negative():
    c = _combo([make_dish(dish_role="主食", grain_type="白米")])
    assert carb_quality_score(c) == -1.0


def test_carb_quality_no_carb_zero():
    c = _combo([make_dish(dish_role="主菜", grain_type="无")])
    assert carb_quality_score(c) == 0.0


def test_carb_quality_mixed():
    c = _combo([
        make_dish(dish_id="d1", dish_role="主食", grain_type="全麦"),
        make_dish(dish_id="d2", dish_role="主食", grain_type="白米"),
    ])
    assert carb_quality_score(c) == 0.0  # +1 - 1


# ─────────────────────── processed_meat
def test_processed_meat_main_dish_full_penalty():
    c = _combo([make_dish(dish_role="主菜", processed_meat_flag=True,
                           canonical_name="蟹柳火腿饭团")])
    assert processed_meat_penalty(c) == 1.0


def test_processed_meat_side_dish_half_penalty():
    c = _combo([make_dish(dish_role="配菜", processed_meat_flag=True)])
    assert processed_meat_penalty(c) == 0.5


def test_processed_meat_clean_zero():
    c = _combo([make_dish(processed_meat_flag=False)])
    assert processed_meat_penalty(c) == 0.0


# ─────────────────────── sweet_sauce
def test_sweet_sauce_high():
    c = _combo([make_dish(sweet_sauce_level="high")])
    assert sweet_sauce_penalty(c) == 1.0


def test_sweet_sauce_mid():
    c = _combo([make_dish(sweet_sauce_level="mid")])
    assert sweet_sauce_penalty(c) == 0.5


def test_sweet_sauce_low_zero():
    c = _combo([make_dish(sweet_sauce_level="low")])
    assert sweet_sauce_penalty(c) == 0.0


# ─────────────────────── soup_or_broth
def test_soup_or_broth_present():
    c = _combo([make_dish(soup_or_broth_flag=True,
                           canonical_name="潮汕牛肉汤")])
    assert soup_or_broth_bonus(c) == 1.0


def test_soup_or_broth_absent():
    c = _combo([make_dish(soup_or_broth_flag=False)])
    assert soup_or_broth_bonus(c) == 0.0


# ─────────────────────── dish_role_match
def test_dish_role_full_combo():
    c = _combo([
        make_dish(dish_id="d1", dish_role="主菜"),
        make_dish(dish_id="d2", dish_role="配菜"),
        make_dish(dish_id="d3", dish_role="主食"),
    ])
    assert dish_role_match_bonus(c) == 1.0


def test_dish_role_2_of_3():
    c = _combo([
        make_dish(dish_id="d1", dish_role="主菜"),
        make_dish(dish_id="d2", dish_role="配菜"),
    ])
    assert dish_role_match_bonus(c) == 0.5


def test_dish_role_single():
    c = _combo([make_dish(dish_role="主菜")])
    assert dish_role_match_bonus(c) == 0.0


# ─────────────────────── 履约 penalty
def test_distance_penalty_within_threshold():
    profile = {"delivery_constraints": {"prefer_distance_m": 1500}}
    c = _combo([make_dish()], restaurant=make_restaurant())  # default 500m
    assert distance_penalty(c, profile) == 0.0


def test_distance_penalty_over_threshold():
    profile = {"delivery_constraints": {"prefer_distance_m": 1000}}
    rest = make_restaurant()
    rest["distance_m"] = 2500   # 超 1500m
    c = _combo([make_dish()], restaurant=rest)
    assert 0 < distance_penalty(c, profile) <= 1.0


def test_distance_penalty_no_config():
    profile = {}  # 没 delivery_constraints
    c = _combo([make_dish()])
    assert distance_penalty(c, profile) == 0.0


def test_eta_penalty_over():
    profile = {"delivery_constraints": {"max_delivery_eta_min": 30}}
    rest = make_restaurant()
    rest["delivery_eta_min"] = 60
    c = _combo([make_dish()], restaurant=rest)
    assert eta_penalty(c, profile) == 1.0


def test_price_penalty_lunch():
    profile = {"price_range": {"lunch_max": 40}}
    c = _combo([make_dish(price=30), make_dish(price=30)])  # 60 总价
    assert 0 < price_penalty(c, profile, meal_type="lunch") <= 1.0


def test_price_penalty_within_lunch_cap():
    profile = {"price_range": {"lunch_max": 60}}
    c = _combo([make_dish(price=30), make_dish(price=20)])  # 50 总价
    assert price_penalty(c, profile, meal_type="lunch") == 0.0


# ─────────────────────── taste_match
def test_taste_match_no_hints_zero():
    c = _combo([make_dish(soup_or_broth_flag=True)])
    assert taste_match_bonus(c, None) == 0.0


def test_taste_match_soup_boost():
    c = _combo([make_dish(soup_or_broth_flag=True)])
    hints = {"boost": ["soup_or_broth"], "penalty": []}
    assert taste_match_bonus(c, hints) == 0.5


def test_taste_match_sweet_penalty():
    c = _combo([make_dish(sweet_sauce_level="high")])
    hints = {"boost": [], "penalty": ["sweet_sauce"]}
    assert taste_match_bonus(c, hints) == -0.5


# ─────────────────────── context_boost
def _ctx(daily_mood):
    return ContextSnapshot(
        meal_type="lunch", zone="shenzhen-bay",
        now=dt.datetime(2026, 5, 13, 11, 25), weekday=2,
        last_meal=None, recent_3d_cuisines={}, recent_3d_ingredients={},
        last_feedback=None, daily_mood=daily_mood, refine_input=None,
    )


def test_context_boost_no_context():
    c = _combo([make_dish(soup_or_broth_flag=True)])
    assert context_boost(c, None) == 0.0


def test_context_boost_neutral():
    c = _combo([make_dish(soup_or_broth_flag=True)])
    ctx = _ctx("neutral")
    assert context_boost(c, ctx) == 0.0


def test_context_boost_want_soup_with_soup():
    c = _combo([make_dish(soup_or_broth_flag=True)])
    assert context_boost(c, _ctx("want_soup")) == 0.5


def test_context_boost_want_soup_without_soup():
    c = _combo([make_dish(soup_or_broth_flag=False)])
    assert context_boost(c, _ctx("want_soup")) == 0.0


def test_context_boost_want_light_low_oil():
    c = _combo([make_dish(oil_level=2)])
    assert context_boost(c, _ctx("want_light")) == 0.3


def test_context_boost_want_light_high_oil_negative():
    c = _combo([make_dish(oil_level=4)])
    assert context_boost(c, _ctx("want_light")) == -0.3


def test_context_boost_low_carb_with_carb_dish():
    c = _combo([make_dish(dish_role="主食", grain_type="白米")])
    assert context_boost(c, _ctx("low_carb")) == -0.3


def test_context_boost_want_clean_processed():
    c = _combo([make_dish(processed_meat_flag=True, dish_role="主菜")])
    assert context_boost(c, _ctx("want_clean")) == -0.4


def test_context_boost_want_indulgent_too_light():
    c = _combo([make_dish(oil_level=1)])
    assert context_boost(c, _ctx("want_indulgent")) == -0.2


# ─────────────────────── score_combo 集成
def test_score_combo_v2_breakdown_includes_new_keys(basic_profile):
    c = _combo([make_dish(main_ingredient_type="纯素",
                           vegetable_ratio_estimate=0.9,
                           protein_grams_estimate=5,
                           dish_role="配菜"),
                 make_dish(main_ingredient_type="红肉",
                           protein_grams_estimate=30, oil_level=2,
                           dish_role="主菜")])
    s, br = score_combo(c, basic_profile)
    # V2 新增维度都在 breakdown 里
    for key in ["carb_quality", "processed_meat", "sweet_sauce",
                "soup_or_broth", "dish_role_match", "distance",
                "eta", "price", "taste_match", "context_boost"]:
        assert key in br, f"V2 维度 {key!r} 应在 breakdown"


def test_score_combo_processed_meat_lowers_total(basic_profile):
    """同样 combo, processed_meat=True 比 False 总分更低."""
    base_dish = make_dish(main_ingredient_type="红肉",
                          protein_grams_estimate=30, oil_level=2,
                          dish_role="主菜")
    veg = make_dish(dish_id="dv", main_ingredient_type="纯素",
                    vegetable_ratio_estimate=0.95, dish_role="配菜")
    clean_combo = _combo([dict(base_dish), veg])
    bad_dish = make_dish(main_ingredient_type="红肉",
                         protein_grams_estimate=30, oil_level=2,
                         dish_role="主菜", processed_meat_flag=True,
                         canonical_name="蟹柳饭团")
    bad_combo = _combo([bad_dish, veg])
    s_clean, _ = score_combo(clean_combo, basic_profile)
    s_bad, _ = score_combo(bad_combo, basic_profile)
    assert s_bad < s_clean


def test_score_combo_soup_boost_with_context(basic_profile):
    """同 combo, daily_mood=want_soup 且含汤水 → 更高分."""
    soup = make_dish(soup_or_broth_flag=True, dish_role="主菜",
                     protein_grams_estimate=30)
    veg = make_dish(dish_id="dv", main_ingredient_type="纯素",
                    vegetable_ratio_estimate=0.9, dish_role="配菜")
    c = _combo([soup, veg])
    s_no_ctx, _ = score_combo(c, basic_profile)
    s_with_ctx, _ = score_combo(c, basic_profile, context=_ctx("want_soup"))
    assert s_with_ctx > s_no_ctx


def test_v2_default_weights_complete():
    """V2_DEFAULT_WEIGHTS 必须覆盖所有 V2 维度."""
    expected_keys = {
        "vegetable_floor_pass", "protein_floor_pass", "low_oil",
        "popularity", "cuisine_preference", "variety_bonus",
        "carb_quality", "processed_meat", "sweet_sauce",
        "soup_or_broth", "dish_role_match",
        "distance", "eta", "price",
        "taste_match", "context_boost",
    }
    assert expected_keys.issubset(V2_DEFAULT_WEIGHTS.keys())

"""V2 score 维度单测 (D-033 5 新字段 + 履约 + taste_match + context_boost).

V1 行为见 tests/test_score.py.
"""
from __future__ import annotations

import datetime as dt

import pytest

from chisha.context import ContextSnapshot
from chisha.score import (
    V2_DEFAULT_WEIGHTS,
    apply_caps,
    apply_unforgivable_penalty,
    attach_popularity_ranks,
    cap_per_cuisine,
    cap_per_food_form,
    cap_per_restaurant,
    carb_quality_score,
    combo_food_form,
    context_boost,
    dish_role_match_bonus,
    distance_penalty,
    eta_penalty,
    extract_static_taste_hints,
    infer_food_form,
    popularity_score,
    price_penalty,
    processed_meat_penalty,
    rank_combos,
    resolve_cap_k,
    resolve_caps,
    score_combo,
    sweet_sauce_penalty,
    variety_bonus_score,
    wetness_bonus,
    taste_match_bonus,
)
from tests.conftest import make_dish, make_restaurant


def _combo(dishes, restaurant=None):
    return {"dishes": dishes,
            "restaurant": restaurant or make_restaurant()}


# ─────────────────────── carb_quality
def test_carb_quality_whole_grain_positive():
    c = _combo([make_dish(dish_role="主食", grain_type="糙米杂粮")])
    assert carb_quality_score(c) == 1.0


def test_carb_quality_refined_negative():
    c = _combo([make_dish(dish_role="主食", grain_type="白米")])
    assert carb_quality_score(c) == -1.0


def test_carb_quality_no_carb_zero():
    c = _combo([make_dish(dish_role="主菜", grain_type="无")])
    assert carb_quality_score(c) == 0.0


def test_carb_quality_mixed():
    c = _combo([
        make_dish(dish_id="d1", dish_role="主食", grain_type="全麦面"),
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
    c = _combo([make_dish(sweet_sauce_level=3)])
    assert sweet_sauce_penalty(c) == 1.0


def test_sweet_sauce_mid():
    c = _combo([make_dish(sweet_sauce_level=2)])
    assert sweet_sauce_penalty(c) == 0.5


def test_sweet_sauce_low_zero():
    c = _combo([make_dish(sweet_sauce_level=0)])
    assert sweet_sauce_penalty(c) == 0.0


# ─────────────────────── soup_or_broth
def test_soup_or_broth_present():
    c = _combo([make_dish(wetness=3,
                           canonical_name="潮汕牛肉汤")])
    assert wetness_bonus(c) == 1.0


def test_soup_or_broth_absent():
    c = _combo([make_dish(wetness=1)])
    assert wetness_bonus(c) == 0.0


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
    profile = {"delivery_constraints": {"prefer_max_eta_min": 30}}
    rest = make_restaurant()
    rest["delivery_eta_min"] = 60
    c = _combo([make_dish()], restaurant=rest)
    assert eta_penalty(c, profile) == 1.0


def test_price_penalty_lunch():
    profile = {"price_range": {"prefer_max_lunch": 40}}
    c = _combo([make_dish(price=30), make_dish(price=30)])  # 60 总价
    assert 0 < price_penalty(c, profile, meal_type="lunch") <= 1.0


def test_price_penalty_within_lunch_cap():
    profile = {"price_range": {"prefer_max_lunch": 60}}
    c = _combo([make_dish(price=30), make_dish(price=20)])  # 50 总价
    assert price_penalty(c, profile, meal_type="lunch") == 0.0


# ─────────────────────── taste_match
def test_taste_match_no_hints_zero():
    c = _combo([make_dish(wetness=3)])
    assert taste_match_bonus(c, None) == 0.0


def test_taste_match_soup_boost():
    c = _combo([make_dish(wetness=3)])
    hints = {"boost": ["wetness"], "penalty": []}
    assert taste_match_bonus(c, hints) == 0.5


def test_taste_match_sweet_penalty():
    c = _combo([make_dish(sweet_sauce_level=3)])
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
    """D-071: 没 context (None) → 0; 季节默认 mood 兜底已废 (D-043 → D-071)."""
    c = _combo([make_dish(wetness=3)])
    # 任意月份均应返回 0 (季节兜底已删, 不再生效)
    assert context_boost(c, None, today=dt.date(2026, 4, 15)) == 0.0
    assert context_boost(c, None, today=dt.date(2026, 7, 15)) == 0.0
    assert context_boost(c, None, today=dt.date(2026, 1, 15)) == 0.0


def test_context_boost_neutral():
    c = _combo([make_dish(wetness=3)])
    ctx = _ctx("neutral")
    assert context_boost(c, ctx) == 0.0


def test_context_boost_want_soup_with_soup():
    c = _combo([make_dish(wetness=3)])
    assert context_boost(c, _ctx("want_soup")) == 0.5


def test_context_boost_want_soup_without_soup():
    c = _combo([make_dish(wetness=1)])
    assert context_boost(c, _ctx("want_soup")) == 0.0


# ─────────────────────── D-071: 已废 mood 分支 deprecated-behavior 断言
# Codex Round 1 Q6: 用显式 assert 0.0 锁定 want_light / want_clean /
# want_indulgent / low_carb 不再被识别, 防未来 refactor 悄悄复活.

def test_context_boost_want_light_deprecated():
    """D-071: want_light 分支已删, 任何油位 combo 都应返回 0."""
    assert context_boost(_combo([make_dish(oil_level=2)]), _ctx("want_light")) == 0.0
    assert context_boost(_combo([make_dish(oil_level=4)]), _ctx("want_light")) == 0.0


def test_context_boost_low_carb_deprecated():
    """D-071: low_carb 分支已删, 含主食 combo 不再被扣分."""
    c = _combo([make_dish(dish_role="主食", grain_type="白米")])
    assert context_boost(c, _ctx("low_carb")) == 0.0


def test_context_boost_want_clean_deprecated():
    """D-071: want_clean 分支已删, 加工肉 combo 不再被扣分 (走 processed_meat 主维度)."""
    c = _combo([make_dish(processed_meat_flag=True, dish_role="主菜")])
    assert context_boost(c, _ctx("want_clean")) == 0.0


def test_context_boost_want_indulgent_deprecated():
    """D-071: want_indulgent 分支已删, 低油 combo 不再被微扣."""
    c = _combo([make_dish(oil_level=1)])
    assert context_boost(c, _ctx("want_indulgent")) == 0.0


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
                "wetness", "dish_role_match", "distance",
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
    soup = make_dish(wetness=3, dish_role="主菜",
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
        "wetness", "dish_role_match",
        "distance", "eta", "price",
        "taste_match", "context_boost",
    }
    assert expected_keys.issubset(V2_DEFAULT_WEIGHTS.keys())


# ─────────────────────── D-042: 粥已移出 GRAIN_GOOD
def test_carb_quality_porridge_no_bonus():
    """D-042: '粥' 不应再计入 GRAIN_GOOD (精制白米煮, 汤水价值由 wetness 覆盖)."""
    c = _combo([make_dish(dish_role="主食", grain_type="粥")])
    assert carb_quality_score(c) == 0.0  # 不加分也不扣分


def test_carb_quality_brown_rice_still_positive():
    """糙米杂粮仍然 +1, 避免误删."""
    c = _combo([make_dish(dish_role="主食", grain_type="糙米杂粮")])
    assert carb_quality_score(c) == 1.0


# ─────────────────────── D-042/D-043: cuisine_preference 默认权重
def test_cuisine_preference_default_weight_lowered():
    """D-042 0.5→0.2; D-043 微调到 0.3 (软偏好, 仍远低于营养主权重)."""
    assert V2_DEFAULT_WEIGHTS["cuisine_preference"] == 0.3


def test_d043_dead_dimensions_zeroed():
    """D-043: vegetable/protein floor pass / distance 权重砍 0."""
    assert V2_DEFAULT_WEIGHTS["vegetable_floor_pass"] == 0.0
    assert V2_DEFAULT_WEIGHTS["protein_floor_pass"] == 0.0
    assert V2_DEFAULT_WEIGHTS["distance"] == 0.0


# ─────────────────────── D-042: cap_per_restaurant
def _ranked_combo(rid: str, score: float, name: str | None = None) -> dict:
    """构造一个最简 ranked-style combo dict, 仅含 cap 函数需要的字段."""
    return {
        "restaurant": {"id": rid, "name": name or f"店{rid}"},
        "dishes": [],
        "score": score,
    }


def test_cap_per_restaurant_basic():
    """每家保留前 k=3, 其余下放到尾部, 不丢任何 combo."""
    ranked = [_ranked_combo("r1", 5.0 - i * 0.1) for i in range(5)] + \
             [_ranked_combo("r2", 4.0 - i * 0.1) for i in range(2)]
    out = cap_per_restaurant(ranked, k=3)
    # 总数不变
    assert len(out) == len(ranked)
    # head: r1×3 + r2×2 (按 ranked 顺序)
    head_rids = [(c["restaurant"]["id"]) for c in out[:5]]
    assert head_rids == ["r1", "r1", "r1", "r2", "r2"]
    # tail: r1 剩余 2 条 (按 ranked 顺序保留)
    tail_rids = [(c["restaurant"]["id"]) for c in out[5:]]
    assert tail_rids == ["r1", "r1"]


def test_cap_per_restaurant_k0_passthrough():
    """k=0 → 不 cap, 原序返回."""
    ranked = [_ranked_combo("r1", 5.0), _ranked_combo("r1", 4.0)]
    out = cap_per_restaurant(ranked, k=0)
    assert [id(c) for c in out] == [id(c) for c in ranked]


def test_cap_per_restaurant_fallback_to_name():
    """restaurant 无 id 时 fallback 用 name 去重, 不应 crash."""
    ranked = [
        {"restaurant": {"name": "甲店"}, "score": 5.0},
        {"restaurant": {"name": "甲店"}, "score": 4.5},
        {"restaurant": {"name": "乙店"}, "score": 4.0},
    ]
    out = cap_per_restaurant(ranked, k=1)
    head_names = [c["restaurant"].get("name") for c in out[:2]]
    assert head_names == ["甲店", "乙店"]


def test_cap_per_restaurant_anonymous_combos_not_aggregated():
    """D-042 review fix: restaurant 无 id 也无 name → 不和其他匿名条聚合, 直接入 head."""
    ranked = [
        {"restaurant": {}, "score": 5.0},        # 完全匿名
        {"restaurant": {}, "score": 4.9},        # 完全匿名
        {"restaurant": None, "score": 4.8},      # restaurant=None
        _ranked_combo("r1", 4.7),
        _ranked_combo("r1", 4.6),
        _ranked_combo("r1", 4.5),
        _ranked_combo("r1", 4.4),                # 这条应被踢到 tail (r1 已 3 条)
    ]
    out = cap_per_restaurant(ranked, k=3)
    # 总数不变
    assert len(out) == len(ranked)
    # 3 个匿名 combo 全部留在 head (不互相挤占)
    head_scores = [c.get("score") for c in out[:6]]
    assert head_scores == [5.0, 4.9, 4.8, 4.7, 4.6, 4.5]
    # tail 只剩 r1 第 4 条
    assert len(out) - 6 == 1
    assert out[-1]["score"] == 4.4


def test_cap_per_restaurant_negative_k_treated_as_passthrough():
    """k<0 视为 k<=0 passthrough, 不应改变顺序."""
    ranked = [_ranked_combo("r1", 5.0), _ranked_combo("r1", 4.0)]
    out = cap_per_restaurant(ranked, k=-1)
    assert [id(c) for c in out] == [id(c) for c in ranked]


# ─────────────────────── resolve_cap_k
def test_resolve_cap_k_default():
    assert resolve_cap_k({}) == 3
    assert resolve_cap_k(None) == 3


def test_resolve_cap_k_from_profile():
    p = {"recall": {"per_restaurant_top_k": 5}}
    assert resolve_cap_k(p) == 5


def test_resolve_cap_k_zero_passes_through():
    """k=0 是 cap_per_restaurant 的合法 passthrough 信号, resolve 不应吞掉它."""
    p = {"recall": {"per_restaurant_top_k": 0}}
    assert resolve_cap_k(p) == 0


def test_resolve_cap_k_invalid_falls_back():
    assert resolve_cap_k({"recall": {"per_restaurant_top_k": "bad"}}) == 3
    assert resolve_cap_k({"recall": {"per_restaurant_top_k": -1}}) == 3
    assert resolve_cap_k({"recall": None}) == 3


def test_cap_per_restaurant_preserves_relative_order():
    """同店多 combo 在 head 内仍按原 ranked 顺序."""
    ranked = [
        _ranked_combo("r1", 5.0, name="combo-a"),
        _ranked_combo("r2", 4.9),
        _ranked_combo("r1", 4.8, name="combo-b"),
        _ranked_combo("r1", 4.7, name="combo-c"),
        _ranked_combo("r1", 4.6, name="combo-d"),
    ]
    out = cap_per_restaurant(ranked, k=2)
    # head: r1(combo-a) → r2 → r1(combo-b); tail: r1(combo-c) → r1(combo-d)
    assert out[0]["restaurant"]["name"] == "combo-a"
    assert out[1]["restaurant"]["id"] == "r2"
    assert out[2]["restaurant"]["name"] == "combo-b"
    assert out[3]["restaurant"]["name"] == "combo-c"
    assert out[4]["restaurant"]["name"] == "combo-d"


# ─────────────────────── D-043: food_form 推断
def test_food_form_porridge():
    d = make_dish(canonical_name="潮汕海鲜砂锅粥", cooking_method="炖煮")
    assert infer_food_form(d) == "粥"


def test_food_form_soup():
    d = make_dish(canonical_name="牛肉汤", cooking_method="炖煮")
    assert infer_food_form(d) == "汤"


def test_food_form_rice():
    d = make_dish(canonical_name="番茄牛肉饭", cooking_method="煎炒")
    assert infer_food_form(d) == "饭"


def test_food_form_noodle():
    d = make_dish(canonical_name="酸辣牛肉粉", cooking_method="炖煮")
    assert infer_food_form(d) == "面"  # 粉/面/粿条统称


def test_food_form_unknown():
    d = make_dish(canonical_name="神秘菜", cooking_method="清蒸")
    # "清蒸" 命中 "蒸"
    assert infer_food_form(d) == "蒸"


def test_combo_food_form_picks_main():
    """combo 含多 dish 时取主菜形态."""
    main = make_dish(dish_id="m1", canonical_name="牛肉汤", dish_role="主菜",
                      cooking_method="炖煮")
    side = make_dish(dish_id="s1", canonical_name="凉拌黄瓜", dish_role="配菜",
                      cooking_method="凉拌")
    c = _combo([main, side])
    assert combo_food_form(c) == "汤"


# ─────────────────────── D-043: cap_per_cuisine / cap_per_food_form / apply_caps
def _cuisine_combo(rid: str, cuisine: str, score: float) -> dict:
    return {
        "restaurant": {"id": rid, "name": f"店{rid}"},
        "dishes": [{"cuisine": cuisine, "canonical_name": "X",
                    "nutrition_profile": {}}],
        "score": score,
    }


def test_cap_per_cuisine_basic():
    ranked = [_cuisine_combo(f"r{i}", "潮汕", 5.0 - i * 0.1) for i in range(8)] + \
             [_cuisine_combo("r9", "湘菜", 3.0)]
    out = cap_per_cuisine(ranked, cap=3)
    head = out[:4]
    # 潮汕只留前 3, 湘菜 1
    head_cuisines = [c["dishes"][0]["cuisine"] for c in head]
    assert head_cuisines.count("潮汕") == 3
    assert head_cuisines.count("湘菜") == 1
    # 总数不变
    assert len(out) == len(ranked)


def test_cap_per_food_form_basic():
    def porridge(rid, score):
        return {
            "restaurant": {"id": rid, "name": f"店{rid}"},
            "dishes": [{"canonical_name": "潮汕粥", "nutrition_profile": {"dish_role": "主菜"}}],
            "score": score,
        }
    def soup(rid, score):
        return {
            "restaurant": {"id": rid, "name": f"店{rid}"},
            "dishes": [{"canonical_name": "牛肉汤", "nutrition_profile": {"dish_role": "主菜"}}],
            "score": score,
        }
    ranked = [porridge(f"p{i}", 5.0 - i * 0.1) for i in range(10)] + \
             [soup("s1", 3.0)]
    out = cap_per_food_form(ranked, cap=4)
    head = out[:5]
    forms = [combo_food_form(c) for c in head]
    assert forms.count("粥") == 4
    assert forms.count("汤") == 1


def test_apply_caps_chains_all_three():
    """三层 cap 串联: restaurant + cuisine + food_form (D-049 后 head-only)."""
    ranked = []
    # 5 家潮汕粥店, 每家 4 个 combo
    for r in range(5):
        for k in range(4):
            ranked.append({
                "restaurant": {"id": f"r{r}", "name": f"潮汕粥店{r}"},
                "dishes": [{"cuisine": "潮汕", "canonical_name": "海鲜粥",
                            "nutrition_profile": {"dish_role": "主菜"}}],
                "score": 5.0 - r * 0.1 - k * 0.01,
            })
    profile = {"recall": {"per_restaurant_top_k": 2, "per_cuisine_top_k": 5,
                           "per_food_form_top_k": 4}}
    out = apply_caps(ranked, profile)
    # 每店 ≤ 2, 单菜系 ≤ 5, 单形态 ≤ 4 → 实际取最严的 food_form=4
    assert len(out) <= 4
    # D-049: 输出严格等于 head, 不再含 tail (验证有 demote 发生 → 输出 < 输入)
    assert len(out) < len(ranked)


# ─────────────────────── D-043/D-045: resolve_caps
def test_resolve_caps_defaults():
    out = resolve_caps({})
    assert out == {"restaurant": 3, "brand": 2, "cuisine": 6, "food_form": 8}


def test_resolve_caps_from_profile():
    p = {"recall": {"per_restaurant_top_k": 2, "per_brand_top_k": 1,
                     "per_cuisine_top_k": 4, "per_food_form_top_k": 6}}
    assert resolve_caps(p) == {"restaurant": 2, "brand": 1, "cuisine": 4, "food_form": 6}


def test_resolve_caps_invalid_falls_back():
    p = {"recall": {"per_restaurant_top_k": "bad", "per_brand_top_k": "x",
                     "per_cuisine_top_k": -1}}
    out = resolve_caps(p)
    assert out["restaurant"] == 3
    assert out["brand"] == 2
    assert out["cuisine"] == 6
    assert out["food_form"] == 8


# ─────────────────────── D-045: brand cap (连锁分店去重)
def test_apply_caps_brand_cap_dedupes_chain_stores():
    """同品牌不同分店应被 brand cap 限制, 即使每家分店 rid 不同."""
    def _c(rid, brand, cuisine, name="菜"):
        return {
            "restaurant": {"id": rid, "name": rid, "brand": brand},
            "dishes": [make_dish(canonical_name=name, cuisine=cuisine)],
            "score": 1.0,
        }
    # Super Model 三家分店 + 一家其他, brand cap=2 应只放行前 2 家 Super Model
    ranked = [
        _c("r_222", "Super Model 超模厨房", "轻食健康"),
        _c("r_219", "Super Model 超模厨房", "轻食健康"),
        _c("r_220", "Super Model 超模厨房", "轻食健康"),
        _c("r_018", "醉湘楼", "湘菜"),
    ]
    profile = {"recall": {"per_brand_top_k": 2,
                          "per_restaurant_top_k": 10,
                          "per_cuisine_top_k": 10,
                          "per_food_form_top_k": 10}}
    out = apply_caps(ranked, profile)
    # D-049 head-only: 输出 3 条 (2 个 Super Model + 1 个 醉湘楼), r_220 被丢弃
    assert len(out) == 3
    out_brands = [c["restaurant"]["brand"] for c in out]
    assert out_brands.count("Super Model 超模厨房") == 2
    assert "醉湘楼" in out_brands
    # r_220 (第 3 家 Super Model 分店) 被 brand cap=2 丢弃, 不再出现
    out_rids = {c["restaurant"]["id"] for c in out}
    assert "r_220" not in out_rids


def test_apply_caps_brand_cap_falls_back_to_rid_when_brand_missing():
    """brand 字段缺失时回退到 rid (单店即单品牌, 不应过度合并)."""
    def _c(rid, cuisine):
        return {
            "restaurant": {"id": rid, "name": rid},  # 无 brand
            "dishes": [make_dish(cuisine=cuisine)],
            "score": 1.0,
        }
    ranked = [_c("r_001", "湘菜"), _c("r_002", "湘菜"), _c("r_003", "湘菜")]
    profile = {"recall": {"per_brand_top_k": 1, "per_restaurant_top_k": 10,
                          "per_cuisine_top_k": 10, "per_food_form_top_k": 10}}
    out = apply_caps(ranked, profile)
    # brand 回退 rid, 三家不同 rid → 都过 brand cap
    assert [c["restaurant"]["id"] for c in out[:3]] == ["r_001", "r_002", "r_003"]


# ─────────────────────── D-043: variety_bonus 连续函数
def test_variety_bonus_unseen_full_score():
    """从未吃过 main_ingredient → 1.0."""
    c = _combo([make_dish(main_ingredient_type="红肉")])
    assert variety_bonus_score(c, meal_log=[]) == 1.0


def test_variety_bonus_recently_eaten_zero():
    """今天吃过同 main_ingredient → 0.0."""
    today = dt.date(2026, 5, 13)
    c = _combo([make_dish(main_ingredient_type="红肉")])
    log = [{"timestamp": "2026-05-13T12:00:00",
            "dishes": [{"main_ingredient_type": "红肉"}]}]
    assert variety_bonus_score(c, meal_log=log, today=today) == 0.0


def test_variety_bonus_continuous_gradient():
    """距离 days 天 → 满分; 中间天数线性插值."""
    today = dt.date(2026, 5, 13)
    c = _combo([make_dish(main_ingredient_type="白肉")])
    log_3d = [{"timestamp": "2026-05-10T12:00:00",
                "dishes": [{"main_ingredient_type": "白肉"}]}]
    # 3 天前吃, days=7 → 3/7 ≈ 0.43
    score = variety_bonus_score(c, meal_log=log_3d, today=today, days=7)
    assert 0.4 < score < 0.5


# ─────────────────────── D-043: rank-based popularity
def test_attach_popularity_ranks_assigns_percentile():
    combos = [
        {"dishes": [{"monthly_sales": 100}]},
        {"dishes": [{"monthly_sales": 500}]},
        {"dishes": [{"monthly_sales": 50}]},
    ]
    attach_popularity_ranks(combos)
    # 销量 500 应该 percentile 最高 (1.0)
    pcts = [c["_popularity_rank"] for c in combos]
    assert pcts[1] == 1.0
    assert pcts[0] > pcts[2]


def test_popularity_score_reads_rank():
    c = {"dishes": [{"monthly_sales": 10}], "_popularity_rank": 0.75}
    assert popularity_score(c) == 0.75


def test_popularity_score_fallback_when_no_rank():
    """没 attach 时 fallback 到 log10."""
    c = {"dishes": [{"monthly_sales": 1000}]}
    score = popularity_score(c)
    assert score > 0


# ─────────────────────── D-043: extract_static_taste_hints
def test_extract_static_taste_hints_from_description():
    """taste_description 含'清淡'+'汤' → boost=[low_oil, wetness]."""
    p = {"taste_description": "喜欢清淡少油，汤水比较好"}
    hints = extract_static_taste_hints(p)
    assert hints is not None
    assert "low_oil" in hints["boost"]
    assert "wetness" in hints["boost"]


def test_extract_static_taste_hints_explicit_tags_win():
    """显式 taste_boost_tags 优先于 description 抽."""
    p = {
        "taste_description": "随便",
        "taste_boost_tags": ["wetness"],
        "taste_penalty_tags": ["sweet_sauce"],
    }
    hints = extract_static_taste_hints(p)
    assert hints == {"boost": ["wetness"], "penalty": ["sweet_sauce"]}


def test_extract_static_taste_hints_empty_returns_none():
    assert extract_static_taste_hints({}) is None
    assert extract_static_taste_hints({"taste_description": ""}) is None
    assert extract_static_taste_hints(None) is None


# ─────────────────────── D-071: infer_default_mood deprecated 断言
# Codex Round 1 Q6 + MAJOR (delete tests 替换为 deprecated-behavior 断言).

def test_infer_default_mood_removed():
    """D-071: D-043 季节默认 mood 兜底已删 — 方法论 baseline 已固化, 不需季节猜测."""
    import chisha.score as score_mod
    assert not hasattr(score_mod, "infer_default_mood"), (
        "infer_default_mood 已被 D-071 删除, 不应再存在"
    )
    assert not hasattr(score_mod, "DEFAULT_MOOD_CONFIDENCE"), (
        "DEFAULT_MOOD_CONFIDENCE 已被 D-071 删除"
    )


def test_context_boost_no_seasonal_fallback():
    """D-071: 没 mood 时不再按季节兜底, 任意季节都返回 0."""
    c = _combo([make_dish(oil_level=1)])
    # 夏季 (7 月) 原本会 want_light 兜底, 现在应 0
    assert context_boost(c, context=None, today=dt.date(2026, 7, 15)) == 0.0
    # 冬季 (1 月) 原本会 want_indulgent 兜底, 现在应 0
    assert context_boost(c, context=None, today=dt.date(2026, 1, 15)) == 0.0


# ─────────────────────── D-043: apply_unforgivable_penalty
def test_unforgivable_two_processed_meat():
    """两个 processed_meat dish 触发 *0.5 discount."""
    c = _combo([
        make_dish(dish_id="d1", processed_meat_flag=True),
        make_dish(dish_id="d2", processed_meat_flag=True),
    ])
    assert apply_unforgivable_penalty(score=4.0, combo=c) == 2.0


def test_unforgivable_sweet_plus_processed():
    """重甜 + 加工肉 同时 → 折扣."""
    c = _combo([
        make_dish(dish_id="d1", sweet_sauce_level=3),
        make_dish(dish_id="d2", processed_meat_flag=True),
    ])
    assert apply_unforgivable_penalty(score=4.0, combo=c) == 2.0


def test_unforgivable_no_trigger():
    """单独一个 processed_meat 不触发."""
    c = _combo([make_dish(processed_meat_flag=True)])
    assert apply_unforgivable_penalty(score=4.0, combo=c) == 4.0


def test_unforgivable_configurable_discount():
    """profile.scoring.unforgivable_discount 可配."""
    c = _combo([
        make_dish(dish_id="d1", processed_meat_flag=True),
        make_dish(dish_id="d2", processed_meat_flag=True),
    ])
    p = {"scoring": {"unforgivable_discount": 0.3}}
    assert apply_unforgivable_penalty(score=10.0, combo=c, profile=p) == 3.0


# ─────────────────────── D-043: rank_combos 端到端 (popularity + hints + caps 一体)
def test_rank_combos_attaches_popularity(basic_profile):
    """rank_combos 入口应 attach _popularity_rank 到每个 combo."""
    combos = [
        {
            "restaurant": make_restaurant(),
            "dishes": [make_dish(monthly_sales=500, dish_role="主菜",
                                  main_ingredient_type="红肉",
                                  vegetable_ratio_estimate=0.8)],
        },
        {
            "restaurant": make_restaurant(rid="r2", name="b"),
            "dishes": [make_dish(monthly_sales=50, dish_role="主菜",
                                  main_ingredient_type="白肉",
                                  vegetable_ratio_estimate=0.8)],
        },
    ]
    out = rank_combos(combos, basic_profile)
    for c in out:
        assert "_popularity_rank" in c


# ─────────────────────── D-043 Codex review fix: apply_caps 三层同时约束
def test_apply_caps_satisfies_all_three_simultaneously():
    """Codex BLOCKER 修复 + 二审加强 + D-049 head-only: 输出每条都同时满足三层约束.

    D-049 前: apply_caps 返回 head + tail, 测试要"找 head 长度"再断言 head 段.
    D-049 后: 输出 == head, 直接对整个 out 断言每层约束.
    """
    ranked = []
    for r in range(5):
        for k in range(4):
            ranked.append({
                "restaurant": {"id": f"chao_{r}", "name": f"潮汕店{r}"},
                "dishes": [{"cuisine": "潮汕", "canonical_name": "海鲜砂锅粥",
                            "nutrition_profile": {"dish_role": "主菜"}}],
                "score": 5.0 - r * 0.1 - k * 0.01,
            })
    for i in range(5):
        ranked.append({
            "restaurant": {"id": f"xiang_{i}", "name": f"湘菜店{i}"},
            "dishes": [{"cuisine": "湘菜", "canonical_name": "辣椒炒肉",
                        "nutrition_profile": {"dish_role": "主菜",
                                              "cooking_method": "煎炒"}}],
            "score": 3.0 - i * 0.1,
        })
    profile = {"recall": {"per_restaurant_top_k": 2,
                           "per_cuisine_top_k": 5,
                           "per_food_form_top_k": 4}}
    out = apply_caps(ranked, profile)

    # D-049: 整个 out 严格满足三层 cap (无 tail 段需要分离)
    from collections import Counter
    rest_cnt = Counter(c["restaurant"]["id"] for c in out)
    cui_cnt = Counter(c["dishes"][0]["cuisine"] for c in out)
    form_cnt = Counter(combo_food_form(c) for c in out)
    assert all(v <= 2 for v in rest_cnt.values()), \
        f"restaurant cap=2 违反: {rest_cnt}"
    assert all(v <= 5 for v in cui_cnt.values()), \
        f"cuisine cap=5 违反: {cui_cnt}"
    assert all(v <= 4 for v in form_cnt.values()), \
        f"food_form cap=4 违反: {form_cnt}"

    # cap 真的生效: 必有 demote 发生 (输出比输入少)
    assert len(out) < len(ranked), "apply_caps 没有任何 demote, cap 没生效"


def test_apply_caps_regression_against_naive_chain():
    """D-049 重写: 直接 catch 'cap 串联会让 demote 的条复活' 这个 BUG.

    构造: 5 条潮汕粥 + 5 条潮汕汤 (同 cuisine 但不同 food_form), 每条独立餐厅.
    cap: r=10 (松) / c=2 (严) / f=2 (严).

    ## 单遍正确实现 (head-only) 的输出
    走 ranked 顺序 [粥*5, 汤*5]:
      - 粥1: c=1 f=1 r=1 → head
      - 粥2: c=2 f=2 r=1 → head
      - 粥3: c=3 已超 c cap=2 → 丢弃
      - 粥4, 粥5: → 丢弃
      - 汤1: c=3 (cuisine 累计) 已超 → 丢弃!
      - 汤2-5: → 丢弃
    输出: [粥1, 粥2], 长度 2, 全是粥.

    ## 朴素串联 (cap_r → cap_c → cap_f) head-only 的输出
      - cap_r=10: head=[粥1..5, 汤1..5]
      - cap_c=2: 在上一步基础上 c cap → head=[粥1, 粥2]
      - cap_f=2: 再走一遍 — 汤的 form 累计是空的, 汤1, 汤2 重新进 head!
        → head = [粥1, 粥2, 汤1, 汤2] (head-only 模式下)
    输出长度 4, 含汤.

    ## 关键区分点
    单遍正确: len(out)=2 且全是粥
    朴素串联: len(out)=4 且含汤
    """
    ranked = []
    # 5 条潮汕粥
    for r in range(5):
        ranked.append({
            "restaurant": {"id": f"zhou_{r}", "name": f"粥店{r}"},
            "dishes": [{"cuisine": "潮汕", "canonical_name": f"番薯粥{r}",
                        "nutrition_profile": {"dish_role": "主菜"}}],
            "score": 5.0 - r * 0.001,
        })
    # 5 条潮汕汤 (同 cuisine, 不同 food_form)
    for r in range(5):
        ranked.append({
            "restaurant": {"id": f"tang_{r}", "name": f"汤店{r}"},
            "dishes": [{"cuisine": "潮汕", "canonical_name": f"牛肉汤{r}",
                        "nutrition_profile": {"dish_role": "主菜",
                                              "cooking_method": "炖煮"}}],
            "score": 4.0 - r * 0.001,
        })
    profile = {"recall": {"per_restaurant_top_k": 10,
                           "per_cuisine_top_k": 2,
                           "per_food_form_top_k": 2}}
    out = apply_caps(ranked, profile)
    # ---- 关键区分断言 ----
    # 单遍正确: 长度 2 (粥1, 粥2). 串联 bug: 长度 4 (粥1, 粥2, 汤1, 汤2).
    assert len(out) == 2, (
        f"head-only 单遍实现下应只剩 2 条 (粥1+粥2, cuisine cap=2 截止), "
        f"实际 {len(out)} 条. 若 >2, 说明串联 bug 让 cap_c demote 的汤"
        f"在 cap_f 步骤又复活到 head."
    )
    # 全是粥, 不含汤 (汤都被 cuisine cap 在累计阶段挡住)
    names = [c["dishes"][0]["canonical_name"] for c in out]
    assert all("粥" in n for n in names), \
        f"head 段应全是粥, 实际 {names}"
    # 附加: 严格满足 c cap=2 f cap=2
    from collections import Counter
    forms = Counter(combo_food_form(c) for c in out)
    cuis = Counter(c["dishes"][0]["cuisine"] for c in out)
    assert forms["粥"] == 2  # head 全是粥
    assert cuis["潮汕"] == 2  # cuisine cap 严格满


def test_rank_combos_end_to_end_root_closes_feedback_loop(tmp_path, monkeypatch):
    """Codex 二审 WARN 修复: 端到端验证 rank_combos(root=...) 透传到 load_runtime_hints.

    不 mock 底层, 直接走完整 rank_combos 路径: 用 tmp root 写反馈 → rank_combos
    传同一 tmp root 读 → taste_match 命中, 证明 root 闭合.
    """
    from chisha.long_term_prefs import append_feedback
    import datetime as dt2
    # 写 3 条"想喝汤" feedback 到 tmp_path
    for i in range(3):
        append_feedback(
            chips=["想喝汤"], rating_taste=4,
            timestamp=dt2.datetime(2026, 5, 13 - i),
            root=tmp_path,
        )
    # 让 long_term_prefs 默认 path 解析到 tmp_path
    # 但这里我们走 rank_combos(root=tmp_path), 内部应当透传, 不需要 monkeypatch
    profile = {
        "basics": {}, "plate_rule": {"min_protein_g": 0, "must_have_vegetable": False},
        "preferences": {}, "scoring_weights": {"taste_match": 1.0},
    }
    combo = {
        "restaurant": make_restaurant(),
        "dishes": [make_dish(wetness=3, dish_role="主菜",
                              vegetable_ratio_estimate=0.8, spicy_level=0,
                              oil_level=5)],  # 排除 low_oil 干扰
    }
    out = rank_combos([combo], profile, today=dt2.date(2026, 5, 13),
                       root=tmp_path)
    br = out[0]["score_breakdown"]
    # taste_match 必须 > 0 (wetness boost 命中, 来自 tmp_path 反馈)
    assert br["taste_match"] > 0.0


def test_rank_combos_default_root_does_not_pick_up_custom_root_feedback(
    tmp_path, monkeypatch
):
    """端到端验证: rank_combos 默认 root 不会读到 tmp_path 写入的反馈."""
    from chisha.long_term_prefs import append_feedback
    import datetime as dt2
    # 在 tmp_path 写 (默认根读不到)
    for i in range(3):
        append_feedback(
            chips=["想喝汤"], rating_taste=4,
            timestamp=dt2.datetime(2026, 5, 13 - i),
            root=tmp_path,
        )
    # monkeypatch 默认根指向另一个空目录, 避免污染真实 data/
    other = tmp_path / "other_root"
    other.mkdir()
    from chisha import long_term_prefs as ltp
    monkeypatch.setattr(
        ltp, "_default_history_path",
        lambda root=None: (root or other) / "data" / "feedback_history.jsonl",
    )
    profile = {
        "basics": {}, "plate_rule": {"min_protein_g": 0, "must_have_vegetable": False},
        "preferences": {}, "scoring_weights": {"taste_match": 1.0},
    }
    combo = {
        "restaurant": make_restaurant(),
        "dishes": [make_dish(wetness=3, dish_role="主菜",
                              vegetable_ratio_estimate=0.8, spicy_level=0,
                              oil_level=5)],
    }
    # rank_combos 不传 root → 走 monkeypatched 默认根 (other, 空目录) → 读不到 hint
    out = rank_combos([combo], profile, today=dt2.date(2026, 5, 13))
    br = out[0]["score_breakdown"]
    # taste_match 应为 0 (没读到任何 hints)
    assert br["taste_match"] == 0.0


def test_apply_caps_cap_zero_means_no_cap():
    """cap=0 表示该层不做约束."""
    ranked = [
        {"restaurant": {"id": f"r{i}"}, "dishes": [{"cuisine": "x",
         "canonical_name": "y", "nutrition_profile": {}}], "score": 1.0}
        for i in range(5)
    ]
    profile = {"recall": {"per_restaurant_top_k": 0,
                           "per_cuisine_top_k": 0,
                           "per_food_form_top_k": 0}}
    out = apply_caps(ranked, profile)
    # 全部留在 head (顺序不变)
    assert [c["restaurant"]["id"] for c in out] == \
           [c["restaurant"]["id"] for c in ranked]


# ─────────────────────── D-043 Codex review fix: unforgivable_penalty 对负分
def test_unforgivable_penalty_negative_score_goes_more_negative():
    """Codex BLOCKER 修复: 负分 combo 触发后必须更负, 不是变大."""
    c = _combo([
        make_dish(dish_id="d1", processed_meat_flag=True),
        make_dish(dish_id="d2", processed_meat_flag=True),
    ])
    # 负分场景: -1.0 触发后应该 < -1.0
    out = apply_unforgivable_penalty(score=-1.0, combo=c)
    assert out < -1.0
    # 零分场景: 0 触发后应该 < 0
    out0 = apply_unforgivable_penalty(score=0.0, combo=c)
    assert out0 < 0


def test_unforgivable_penalty_positive_score_halved():
    """正分场景仍走 0.5 折扣 (向后兼容)."""
    c = _combo([
        make_dish(dish_id="d1", processed_meat_flag=True),
        make_dish(dish_id="d2", processed_meat_flag=True),
    ])
    assert apply_unforgivable_penalty(score=4.0, combo=c) == 2.0


# ─────────────────────── D-043 Codex review fix: food_form 误伤词
def test_food_form_powder_steamed_not_noodle():
    """'粉蒸肉' 含'粉'但实际是'蒸', 不应误归为'面'."""
    d = make_dish(canonical_name="粉蒸排骨", cooking_method="清蒸")
    assert infer_food_form(d) == "蒸"


def test_food_form_stewed_rice_not_soup():
    """'卤肉饭'/'炖牛肉饭' cooking_method 可能是炖煮但形态是饭."""
    d1 = make_dish(canonical_name="台式卤肉饭", cooking_method="炖煮")
    assert infer_food_form(d1) == "饭"
    d2 = make_dish(canonical_name="番茄炖牛肉饭", cooking_method="炖煮")
    assert infer_food_form(d2) == "饭"


def test_food_form_powder_noodle_still_noodle():
    """普通'米粉/汤粉/炒粉' 仍归'面' (粉指粉条/米粉)."""
    d1 = make_dish(canonical_name="酸辣牛肉粉", cooking_method="炖煮")
    assert infer_food_form(d1) == "面"
    d2 = make_dish(canonical_name="桂林米粉", cooking_method="炖煮")
    assert infer_food_form(d2) == "面"


# ─────────────────────── D-043 Codex review fix: hints 三源合并
def test_rank_combos_merges_explicit_static_runtime_hints(basic_profile, tmp_path,
                                                            monkeypatch):
    """Codex MAJOR 修复: 显式 taste_hints 也要 merge static + runtime, 不再短路.

    设计: combo 命中 wetness 但 oil 高 → 显式 hints 不含 wetness → 只有 runtime
    含 wetness 时 taste_match 才能命中. 这样断言确切证明 runtime hints 合并生效.
    """
    from chisha.long_term_prefs import append_feedback
    import datetime as dt2
    for i in range(3):
        append_feedback(
            chips=["想喝汤"], rating_taste=4,
            timestamp=dt2.datetime(2026, 5, 13 - i),
            root=tmp_path,
        )
    # monkey-patch _default_history_path 让 long_term_prefs 读 tmp_path
    from chisha import long_term_prefs as ltp
    monkeypatch.setattr(
        ltp, "_default_history_path",
        lambda root=None: tmp_path / "data" / "feedback_history.jsonl"
    )
    basic_profile.pop("taste_description", None)  # 排除 static 干扰
    # 显式 hints 不含 wetness (只含 spicy penalty, 与 wetness 无关)
    explicit = {"boost": [], "penalty": ["spicy"]}
    # combo: wetness=3 命中, oil=5 重油 (low_oil 不会命中), 不辣
    combo = {
        "restaurant": make_restaurant(),
        "dishes": [make_dish(wetness=3, oil_level=5, spicy_level=0,
                              dish_role="主菜", vegetable_ratio_estimate=0.8)],
    }
    out = rank_combos([combo], basic_profile, today=dt2.date(2026, 5, 13),
                       taste_hints=explicit)
    br = out[0]["score_breakdown"]
    # 必须 > 0: 因为 runtime hints 注入了 wetness boost, combo wetness=3 → +0.5 × 0.4
    assert br["taste_match"] > 0.0


def test_rank_combos_explicit_hints_alone_does_not_short_circuit():
    """没 runtime + 没 static + 显式 hints 仍正常工作 (不破坏老路径)."""
    import datetime as dt2
    from chisha import long_term_prefs as ltp

    # 用 monkeypatch 在 test fixture 里隔离; 此处用 root 不存在的临时路径
    # rank_combos 内部 try/except 包了 load_runtime_hints, 不会 crash
    explicit = {"boost": ["wetness"], "penalty": []}
    profile = {
        "basics": {}, "plate_rule": {"min_protein_g": 0, "must_have_vegetable": False},
        "preferences": {}, "scoring_weights": {"taste_match": 1.0},
    }
    combo = {
        "restaurant": make_restaurant(),
        "dishes": [make_dish(wetness=3, dish_role="主菜",
                              vegetable_ratio_estimate=0.8)],
    }
    out = rank_combos([combo], profile, today=dt2.date(2026, 5, 13),
                       taste_hints=explicit)
    br = out[0]["score_breakdown"]
    assert br["taste_match"] > 0.0

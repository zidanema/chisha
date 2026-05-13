"""D-041 硬过滤 / 灵活 combo / 双层约束 测试.

Codex review 提的 8 个测试 (audit-after-fix).
"""
from __future__ import annotations

import datetime as dt
import pytest

from chisha.debug_recommend import _traced_hard_filter
from chisha.recall import (
    build_combos_for_restaurant,
    combo_price_filter,
    combo_total_price,
    compute_extra_banned_restaurants,
    hard_filter,
)
from tests.conftest import make_dish, make_restaurant


# ─────────────────────────── #1 price=None 不崩
def test_combo_price_filter_price_none_does_not_crash(basic_profile):
    """dish.price=None 时 combo_price_filter 应该用 0 处理, 不 TypeError."""
    profile = {**basic_profile,
               "price_range": {"hard_max_lunch": 50, "hard_max_dinner": 50}}
    d1 = make_dish(dish_id="d1", price=None)            # 缺价
    d2 = make_dish(dish_id="d2", price=30)
    combo = {"restaurant": make_restaurant(), "dishes": [d1, d2]}
    out = combo_price_filter([combo], profile, meal_type="lunch")
    # 总价 = 0 + 30 = 30 ≤ 50, 应该保留
    assert len(out) == 1
    # combo_total_price 也要不崩
    assert combo_total_price(combo) == 30


# ─────────────────────────── #2 refine 应用 hard_max_lunch
def test_refine_applies_hard_price_cap(tmp_path):
    """refine 二轮也要用 combo_price_filter; state.meal_type 必须传给 recall."""
    from chisha.refine import refine
    from chisha.session import create_session, save_session

    rests = [{**make_restaurant(rid="r1", name="贵店"), "category": "湘菜"}]
    dishes = [
        make_dish(dish_id="d1", restaurant_id="r1",
                  raw_name="贵肉", canonical_name="贵肉",
                  cuisine="湘菜", main_ingredient_type="红肉",
                  oil_level=2, protein_grams_estimate=30, price=80,
                  monthly_sales=200, dish_role="主菜"),
        make_dish(dish_id="d2", restaurant_id="r1",
                  raw_name="贵菜", canonical_name="贵菜",
                  cuisine="湘菜", main_ingredient_type="纯素",
                  oil_level=2, vegetable_ratio_estimate=0.9,
                  protein_grams_estimate=3, price=60,
                  monthly_sales=180, dish_role="配菜"),
    ]
    profile = {
        "basics": {"office_zone": "test", "zones": {"lunch": "test"}},
        "taste_description": "",
        "preferences": {"liked_cuisines": [], "disliked_cuisines": [],
                         "avoid_dishes": [], "spicy_tolerance": 3},
        "plate_rule": {"must_have_vegetable": True, "min_vegetable_dishes": 1,
                        "min_protein_g": 25, "prefer_oil_level_at_most": 3,
                        "hard_max_oil_level": 5},
        "diversity": {"no_same_restaurant_within_days": 7,
                       "no_same_main_ingredient_within_days": 3},
        "recall": {"per_restaurant_max": 5, "min_monthly_sales": 0},
        # combo 总价 80+60=140, > hard_max_lunch=100
        "price_range": {"hard_max_lunch": 100},
    }
    sid = "sid_refine_price"
    s = create_session(sid, "lunch", "test")
    save_session(s, tmp_path)
    out = refine(sid, "不重要", profile, rests, dishes, [],
                 root=tmp_path, today=dt.date(2026, 5, 13), use_llm=False)
    # 仅有的 combo 总价超 hard_max_lunch, 应被 ban → 0 candidates
    assert out["candidates"] == []


# ─────────────────────────── #3 max_dishes_per_combo=0 返回空
def test_build_combos_max_dishes_zero_returns_empty(basic_profile):
    profile = {**basic_profile,
               "recall": {**basic_profile["recall"],
                          "max_dishes_per_combo": 0}}
    dishes = [
        make_dish(dish_id="d1", main_ingredient_type="红肉",
                  protein_grams_estimate=30, is_complete_meal=True,
                  vegetable_ratio_estimate=0.7),
        make_dish(dish_id="d2", main_ingredient_type="纯素",
                  vegetable_ratio_estimate=0.95, protein_grams_estimate=3),
    ]
    combos = build_combos_for_restaurant(dishes, profile, per_rest_max=10)
    assert combos == []


# ─────────────────────────── #4 combo 去重顺序无关
def test_build_combos_dedup_order_insensitive(basic_profile):
    """同一组 dish_id (顺序不同) 只保留一个 combo."""
    profile = {**basic_profile,
               "recall": {"per_restaurant_max": 999,
                          "min_monthly_sales": 0,
                          "max_protein_per_combo": 2,
                          "max_veg_per_combo": 2,
                          "max_carb_per_combo": 1,
                          "max_dishes_per_combo": 4}}
    dishes = [
        make_dish(dish_id="d_p1", canonical_name="肉1",
                  main_ingredient_type="红肉",
                  protein_grams_estimate=30, monthly_sales=100),
        make_dish(dish_id="d_v1", canonical_name="菜1",
                  main_ingredient_type="纯素",
                  vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3, monthly_sales=100),
    ]
    combos = build_combos_for_restaurant(dishes, profile, per_rest_max=999)
    # 顺序不同的同 ID 组合应被合并; 不会出现 (p1,v1) 和 (v1,p1) 两份
    keys = [frozenset(d["dish_id"] for d in c) for c in combos]
    assert len(keys) == len(set(keys))


# ─────────────────────────── #5 ETA 缺失 (=-1) 不算 banned
def test_compute_extra_banned_restaurants_eta_missing_not_banned():
    rests = [
        {**make_restaurant(rid="r_ok", name="正常店"), "delivery_eta_min": 20},
        {**make_restaurant(rid="r_missing", name="无ETA店"),
         "delivery_eta_min": -1},          # 缺数据
        {**make_restaurant(rid="r_slow", name="慢店"), "delivery_eta_min": 80},
    ]
    profile = {"delivery_constraints": {"hard_max_eta_min": 30},
               "preferences": {}}
    banned = compute_extra_banned_restaurants(rests, profile)
    assert banned == {"r_slow"}           # 缺失值不卡, 只卡显式超限


# ─────────────────────────── #6 大小写敏感性契约
def test_hard_filter_case_sensitivity_contract(basic_profile):
    """avoid_dishes 严格大小写敏感: 'CocaCola' 不会被 'cocacola' 模糊命中.

    中文场景默认无影响, 仅文档化 Latin 字符的契约.
    """
    profile = {**basic_profile,
               "preferences": {**basic_profile["preferences"],
                               "avoid_dishes": ["coca"]}}
    dishes = [
        make_dish(dish_id="d_lower", canonical_name="cocacola"),
        make_dish(dish_id="d_upper", canonical_name="CocaCola"),
    ]
    kept, dropped = hard_filter(dishes, profile, set())
    kept_ids = {d["dish_id"] for d in kept}
    # 小写命中, 大写漏过 (契约: 不做 normalize)
    assert "d_lower" not in kept_ids
    assert "d_upper" in kept_ids


# ─────────────────────────── #7 三个新黑名单
def test_hard_filter_all_new_blacklists(basic_profile):
    profile = {**basic_profile,
               "preferences": {**basic_profile["preferences"],
                               "avoid_main_ingredients": ["海鲜"],
                               "avoid_cooking_methods": ["油炸"],
                               "banned_cuisines": ["饮品甜品"]}}
    dishes = [
        make_dish(dish_id="d_seafood", main_ingredient_type="海鲜",
                  protein_grams_estimate=30, monthly_sales=100),
        make_dish(dish_id="d_fried", cooking_method="油炸",
                  main_ingredient_type="白肉",
                  protein_grams_estimate=20, monthly_sales=100),
        make_dish(dish_id="d_sweet", cuisine="饮品甜品",
                  main_ingredient_type="主食",
                  protein_grams_estimate=5, monthly_sales=100),
        make_dish(dish_id="d_ok", main_ingredient_type="红肉",
                  cooking_method="炒", cuisine="湘菜",
                  protein_grams_estimate=30, monthly_sales=100),
    ]
    kept, dropped = hard_filter(dishes, profile, set())
    kept_ids = {d["dish_id"] for d in kept}
    assert kept_ids == {"d_ok"}
    dropped_reasons = {d["dish_id"]: d["reason"] for d in dropped}
    assert "海鲜" in dropped_reasons["d_seafood"]
    assert "油炸" in dropped_reasons["d_fried"]
    assert "饮品甜品" in dropped_reasons["d_sweet"]


# ─────────────────────────── #8 traced == production
def test_traced_vs_production_hard_filter_identical(basic_profile):
    """_traced_hard_filter 是 hard_filter 的薄包装, 保留集必须一致."""
    profile = {**basic_profile,
               "preferences": {**basic_profile["preferences"],
                               "avoid_dishes": ["红烧"],
                               "avoid_main_ingredients": ["海鲜"],
                               "avoid_cooking_methods": ["油炸"],
                               "banned_cuisines": ["饮品甜品"]}}
    dishes = [
        make_dish(dish_id="d1", canonical_name="红烧肉",
                  main_ingredient_type="红肉",
                  protein_grams_estimate=30, monthly_sales=100),
        make_dish(dish_id="d2", main_ingredient_type="海鲜",
                  protein_grams_estimate=30, monthly_sales=100),
        make_dish(dish_id="d3", cooking_method="油炸",
                  main_ingredient_type="白肉",
                  protein_grams_estimate=20, monthly_sales=100),
        make_dish(dish_id="d4", cuisine="饮品甜品",
                  main_ingredient_type="主食",
                  protein_grams_estimate=5, monthly_sales=100),
        make_dish(dish_id="d5", restaurant_id="r_eta_ban",
                  main_ingredient_type="红肉",
                  protein_grams_estimate=30, monthly_sales=100),
        make_dish(dish_id="d_ok", main_ingredient_type="红肉",
                  cooking_method="炒", cuisine="湘菜",
                  protein_grams_estimate=30, monthly_sales=100),
    ]
    eta_ban = {"r_eta_ban"}
    # 生产路径: 把 ETA banned 合并到 avoid_restaurant_ids
    prod_kept, _ = hard_filter(dishes, profile, eta_ban)
    # 调试路径: ETA banned 显式标记
    traced_kept, traced_dropped = _traced_hard_filter(
        dishes, profile, set(), banned_rests_by_eta=eta_ban
    )
    assert {d["dish_id"] for d in prod_kept} == {d["dish_id"] for d in traced_kept}
    # 调试路径还要带上人类可读 reason
    eta_dropped = next((x for x in traced_dropped if x["dish_id"] == "d5"), None)
    assert eta_dropped and "ETA" in eta_dropped["reason"]

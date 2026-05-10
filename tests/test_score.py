"""score.py 单测."""
from tests.conftest import make_dish, make_restaurant
from chisha.score import (
    vegetable_floor_score,
    protein_floor_score,
    low_oil_score,
    popularity_score,
    cuisine_preference_score,
    score_combo,
    rank_combos,
    diversify_top,
)


def _combo(dishes, rest=None):
    return {
        "restaurant": rest or make_restaurant(),
        "dishes": dishes,
    }


def test_vegetable_floor_pass(basic_profile):
    veg_combo = _combo([make_dish(main_ingredient_type="纯素",
                                   vegetable_ratio_estimate=0.95)])
    no_veg_combo = _combo([make_dish(main_ingredient_type="红肉",
                                      vegetable_ratio_estimate=0.1)])
    assert vegetable_floor_score(veg_combo, basic_profile) == 1.0
    assert vegetable_floor_score(no_veg_combo, basic_profile) == 0.0


def test_protein_floor_pass(basic_profile):
    high_p = _combo([make_dish(protein_grams_estimate=30)])
    low_p = _combo([make_dish(protein_grams_estimate=10)])
    assert protein_floor_score(high_p, basic_profile) == 1.0
    assert protein_floor_score(low_p, basic_profile) == 0.0


def test_low_oil_score(basic_profile):
    low = _combo([make_dish(oil_level=1)])
    medium = _combo([make_dish(oil_level=3)])
    high = _combo([make_dish(oil_level=5)])
    assert low_oil_score(low, basic_profile) > low_oil_score(medium, basic_profile)
    assert low_oil_score(medium, basic_profile) > low_oil_score(high, basic_profile)


def test_popularity_score():
    s_low = popularity_score(_combo([make_dish(monthly_sales=1)]))
    s_high = popularity_score(_combo([make_dish(monthly_sales=1000)]))
    assert s_high > s_low
    assert popularity_score(_combo([make_dish(monthly_sales=0)])) == 0.0


def test_cuisine_preference_score(basic_profile):
    liked = _combo([make_dish(cuisine="湘菜")])
    disliked = _combo([make_dish(cuisine="饮品甜品")])
    neutral = _combo([make_dish(cuisine="韩式")])
    assert cuisine_preference_score(liked, basic_profile) == 1.0
    assert cuisine_preference_score(disliked, basic_profile) == -1.0
    assert cuisine_preference_score(neutral, basic_profile) == 0.0


def test_score_combo_breakdown_keys(basic_profile):
    c = _combo([make_dish(main_ingredient_type="纯素",
                           vegetable_ratio_estimate=0.95,
                           protein_grams_estimate=3),
                make_dish(main_ingredient_type="红肉",
                           protein_grams_estimate=30, oil_level=2)])
    s, br = score_combo(c, basic_profile)
    assert "vegetable_floor_pass" in br
    assert "protein_floor_pass" in br
    assert "low_oil" in br
    assert "popularity" in br
    assert "cuisine_preference" in br
    assert s > 0


def test_rank_combos_orders_descending(basic_profile):
    c_good = _combo([
        make_dish(dish_id="g1", cuisine="湘菜",
                  main_ingredient_type="纯素",
                  vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3, oil_level=1),
        make_dish(dish_id="g2", cuisine="湘菜",
                  main_ingredient_type="红肉",
                  protein_grams_estimate=30, oil_level=2),
    ])
    c_bad = _combo([
        make_dish(dish_id="b1", cuisine="饮品甜品",
                  main_ingredient_type="红肉",
                  protein_grams_estimate=10, oil_level=5,
                  vegetable_ratio_estimate=0.1),
    ])
    ranked = rank_combos([c_bad, c_good], basic_profile)
    assert ranked[0]["dishes"][0]["dish_id"] == "g1"
    assert ranked[0]["score"] > ranked[1]["score"]


def test_diversify_top_brand_dedup():
    """同 brand 多家分店, top N 只取 1 家."""
    rest_a1 = make_restaurant("r_001", name="A 店", brand="A")
    rest_a2 = make_restaurant("r_002", name="A 店分店", brand="A")
    rest_b = make_restaurant("r_003", name="B 店", brand="B")
    rest_c = make_restaurant("r_004", name="C 店", brand="C")
    ranked = [
        {**_combo([make_dish(cuisine="湘菜")], rest_a1), "score": 5.0},
        {**_combo([make_dish(cuisine="湘菜")], rest_a2), "score": 4.9},
        {**_combo([make_dish(cuisine="川菜")], rest_b),  "score": 4.8},
        {**_combo([make_dish(cuisine="潮汕")], rest_c),  "score": 4.7},
    ]
    top = diversify_top(ranked, n=3, max_per_brand=1, max_per_cuisine=2)
    brands = {c["restaurant"]["brand"] for c in top}
    assert brands == {"A", "B", "C"}


def test_diversify_top_cuisine_dedup():
    """同菜系 ≤ max_per_cuisine."""
    ranked = [
        {**_combo([make_dish(cuisine="湘菜")],
                  make_restaurant("r_001", brand="A")), "score": 5.0},
        {**_combo([make_dish(cuisine="湘菜")],
                  make_restaurant("r_002", brand="B")), "score": 4.9},
        {**_combo([make_dish(cuisine="湘菜")],
                  make_restaurant("r_003", brand="C")), "score": 4.8},
        {**_combo([make_dish(cuisine="川菜")],
                  make_restaurant("r_004", brand="D")), "score": 4.5},
    ]
    top = diversify_top(ranked, n=3, max_per_brand=1, max_per_cuisine=2)
    cuisines = [c["dishes"][0]["cuisine"] for c in top]
    assert cuisines.count("湘菜") <= 2

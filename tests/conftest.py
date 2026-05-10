"""共享 pytest fixtures."""
import datetime as dt
import pytest


def make_dish(
    dish_id: str = "d_001_001",
    restaurant_id: str = "r_001",
    raw_name: str = "测试菜",
    canonical_name: str | None = None,
    price: float = 30.0,
    monthly_sales: int = 100,
    cuisine: str = "湘菜",
    main_ingredient_type: str = "红肉",
    cooking_method: str = "煮",
    oil_level: int = 2,
    protein_grams_estimate: int = 30,
    vegetable_ratio_estimate: float = 0.2,
    is_complete_meal: bool = False,
    spicy_level: int = 1,
    tags: list[str] | None = None,
    is_available: bool = True,
) -> dict:
    return {
        "dish_id": dish_id,
        "restaurant_id": restaurant_id,
        "raw_name": raw_name,
        "canonical_name": canonical_name or raw_name,
        "price": price,
        "monthly_sales": monthly_sales,
        "cuisine": cuisine,
        "nutrition_profile": {
            "main_ingredient_type": main_ingredient_type,
            "cooking_method": cooking_method,
            "oil_level": oil_level,
            "protein_grams_estimate": protein_grams_estimate,
            "vegetable_ratio_estimate": vegetable_ratio_estimate,
            "is_complete_meal": is_complete_meal,
            "spicy_level": spicy_level,
            "tags": tags or [],
        },
        "metadata": {
            "tagged_at": "2026-05-11T00:00:00",
            "tag_version": "test",
            "is_available": is_available,
        },
    }


def make_restaurant(
    rid: str = "r_001",
    name: str = "测试餐厅",
    brand: str | None = None,
    category: str = "湘菜",
    rating: float = 4.5,
    monthly_orders: int = 500,
) -> dict:
    return {
        "id": rid,
        "name": name,
        "brand": brand or name,
        "category": category,
        "city": "深圳",
        "office_zone": "test",
        "rating": rating,
        "monthly_orders": monthly_orders,
        "distance_m": 500,
        "delivery_eta_min": 20,
        "delivery_fee": 3.0,
        "min_order": 20.0,
    }


@pytest.fixture
def basic_profile():
    return {
        "basics": {"name": "test", "city": "深圳", "office_zone": "test"},
        "plate_rule": {
            "must_have_vegetable": True,
            "min_vegetable_dishes": 1,
            "min_protein_g": 25,
            "prefer_oil_level_at_most": 3,
            "hard_max_oil_level": 5,
        },
        "preferences": {
            "liked_cuisines": ["湘菜", "潮汕"],
            "disliked_cuisines": ["饮品甜品"],
            "avoid_dishes": ["红烧肉"],
            "spicy_tolerance": 2,
        },
        "diversity": {
            "no_same_restaurant_within_days": 7,
            "no_same_main_ingredient_within_days": 3,
        },
        "recall": {"top_n": 100, "per_restaurant_max": 3,
                   "min_monthly_sales": 10},
        "scoring_weights": {
            "vegetable_floor_pass": 1.0,
            "protein_floor_pass": 1.0,
            "low_oil": 0.8,
            "popularity": 0.4,
            "cuisine_preference": 0.5,
            "variety_bonus": 0.3,
        },
    }

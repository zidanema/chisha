"""chisha/schemas.py 单测 (v3, D-032).

NOTE (Session 1 → Session 2 协调):
v3 加了 5 字段 (dish_role/processed_meat_flag/sweet_sauce_level/wetness/grain_type),
全部 required. 本文件不依赖 tests/conftest.make_dish, 直接构造 v3 dict, 因为
conftest.make_dish 的字段命名是 Session 2 在 schema 定稿前预设的, 与 v3 不一致
(wetness → wetness; sweet_sauce_level str→int; grain_type "糙米"→"糙米杂粮").
Session 2 git pull 到 v3 schema 后会同步调 conftest.
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from chisha.schemas import (
    COOKING_METHODS,
    CUISINES,
    DISH_ROLES,
    GRAIN_TYPES,
    INGREDIENT_TYPES,
    DishTagged,
    NutritionProfile,
    validate_dishes_tagged,
)

ROOT = Path(__file__).resolve().parent.parent


def _v3_nutrition(**overrides) -> dict:
    base = {
        "main_ingredient_type": "红肉",
        "cooking_method": "煮",
        "oil_level": 2,
        "protein_grams_estimate": 30,
        "vegetable_ratio_estimate": 0.2,
        "is_complete_meal": False,
        "spicy_level": 1,
        "dish_role": "主菜",
        "processed_meat_flag": False,
        "sweet_sauce_level": 0,
        "wetness": 2,
        "grain_type": "无",
        "tags": [],
    }
    base.update(overrides)
    return base


def _v3_dish(**overrides) -> dict:
    nutrition = overrides.pop("nutrition_profile", None) or _v3_nutrition()
    base = {
        "dish_id": "d_001_001",
        "restaurant_id": "r_001",
        "raw_name": "测试菜",
        "canonical_name": "测试菜",
        "price": 30.0,
        "monthly_sales": 100,
        "cuisine": "湘菜",
        "nutrition_profile": nutrition,
        "metadata": {
            "tagged_at": "2026-05-11T00:00:00",
            "tag_version": "v3",
            "is_available": True,
        },
    }
    base.update(overrides)
    return base


def test_minimal_dish_passes():
    DishTagged.model_validate(_v3_dish())


def test_oil_level_out_of_range():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(nutrition_profile=_v3_nutrition(oil_level=6)))


def test_oil_level_zero_rejected():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(nutrition_profile=_v3_nutrition(oil_level=0)))


def test_spicy_level_out_of_range():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(nutrition_profile=_v3_nutrition(spicy_level=4)))


def test_spicy_level_negative_rejected():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(nutrition_profile=_v3_nutrition(spicy_level=-1)))


def test_vegetable_ratio_above_one():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(vegetable_ratio_estimate=1.5)))


def test_vegetable_ratio_negative():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(vegetable_ratio_estimate=-0.1)))


def test_protein_negative_rejected():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(protein_grams_estimate=-1)))


def test_unknown_cuisine_rejected():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(cuisine="俄罗斯菜"))


def test_unknown_ingredient_rejected():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(main_ingredient_type="昆虫")))


def test_unknown_cooking_method_rejected():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(cooking_method="冻干")))


def test_extra_field_rejected_on_dish():
    d = _v3_dish()
    d["unexpected"] = "x"
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_extra_field_rejected_on_nutrition():
    d = _v3_dish()
    d["nutrition_profile"]["fat_grams"] = 10
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_missing_field_rejected():
    d = _v3_dish()
    del d["nutrition_profile"]["oil_level"]
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_negative_price_rejected():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(price=-1.0))


def test_validate_dishes_tagged_batch():
    items = [_v3_dish(dish_id=f"d_{i:03d}") for i in range(3)]
    out = validate_dishes_tagged(items)
    assert len(out) == 3
    assert all(isinstance(o, DishTagged) for o in out)


# ─── v3 新字段枚举 / 范围校验 ─────────────────────────────

def test_dish_role_unknown_rejected():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(dish_role="主厨推荐")))


def test_dish_role_all_values_pass():
    for role in DISH_ROLES:
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(dish_role=role)))


def test_grain_type_unknown_rejected():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(grain_type="燕麦")))  # 应为 粗粮


def test_grain_type_all_values_pass():
    for gt in GRAIN_TYPES:
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(grain_type=gt)))


def test_sweet_sauce_level_must_be_int():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(sweet_sauce_level="mid")))


def test_sweet_sauce_level_out_of_range():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(sweet_sauce_level=4)))


def test_wetness_out_of_range_low():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(wetness=0)))


def test_wetness_out_of_range_high():
    with pytest.raises(ValidationError):
        DishTagged.model_validate(_v3_dish(
            nutrition_profile=_v3_nutrition(wetness=4)))


def test_real_home_passes_schema():
    """sanity: 真实 v3 数据全量过 schema. v3 重打前 skip (旧 v2 缺 5 字段)."""
    src = ROOT / "data" / "home" / "dishes_tagged.json"
    if not src.exists():
        pytest.skip("dishes_tagged.json missing")
    records = json.loads(src.read_text(encoding="utf-8"))
    if not records or records[0].get("metadata", {}).get("tag_version") != "v3":
        pytest.skip("v3 重打未完成 (现有数据是旧 tag_version)")
    validate_dishes_tagged(records)


def test_nutrition_profile_standalone():
    """NutritionProfile 单独可用 (v3 13 字段)."""
    NutritionProfile.model_validate(_v3_nutrition())


def test_const_sets_nonempty():
    assert "湘菜" in CUISINES
    assert "红肉" in INGREDIENT_TYPES
    assert "煮" in COOKING_METHODS
    assert "主菜" in DISH_ROLES
    assert "白米" in GRAIN_TYPES

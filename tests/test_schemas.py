"""chisha/schemas.py 单测."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from chisha.schemas import (
    COOKING_METHODS,
    CUISINES,
    INGREDIENT_TYPES,
    DishTagged,
    NutritionProfile,
    validate_dishes_tagged,
)
from tests.conftest import make_dish

ROOT = Path(__file__).resolve().parent.parent


def test_minimal_dish_passes():
    d = make_dish()
    DishTagged.model_validate(d)


def test_oil_level_out_of_range():
    d = make_dish(oil_level=6)
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_oil_level_zero_rejected():
    d = make_dish(oil_level=0)
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_spicy_level_out_of_range():
    d = make_dish(spicy_level=4)
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_spicy_level_negative_rejected():
    d = make_dish(spicy_level=-1)
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_vegetable_ratio_above_one():
    d = make_dish(vegetable_ratio_estimate=1.5)
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_vegetable_ratio_negative():
    d = make_dish(vegetable_ratio_estimate=-0.1)
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_protein_negative_rejected():
    d = make_dish(protein_grams_estimate=-1)
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_unknown_cuisine_rejected():
    d = make_dish(cuisine="俄罗斯菜")
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_unknown_ingredient_rejected():
    d = make_dish(main_ingredient_type="昆虫")
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_unknown_cooking_method_rejected():
    d = make_dish(cooking_method="冻干")
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_extra_field_rejected_on_dish():
    d = make_dish()
    d["unexpected"] = "x"
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_extra_field_rejected_on_nutrition():
    d = make_dish()
    d["nutrition_profile"]["fat_grams"] = 10
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_missing_field_rejected():
    d = make_dish()
    del d["nutrition_profile"]["oil_level"]
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_negative_price_rejected():
    d = make_dish(price=-1.0)
    with pytest.raises(ValidationError):
        DishTagged.model_validate(d)


def test_validate_dishes_tagged_batch():
    items = [make_dish(dish_id=f"d_{i:03d}") for i in range(3)]
    out = validate_dishes_tagged(items)
    assert len(out) == 3
    assert all(isinstance(o, DishTagged) for o in out)


def test_real_home_passes_schema():
    """sanity: 真实数据全量过 schema."""
    src = ROOT / "data" / "home" / "dishes_tagged.json"
    if not src.exists():
        pytest.skip("dishes_tagged.json missing")
    records = json.loads(src.read_text(encoding="utf-8"))
    assert len(records) > 0
    validate_dishes_tagged(records)


def test_nutrition_profile_standalone():
    """NutritionProfile 单独可用 (允许嵌套测试)."""
    NutritionProfile.model_validate({
        "main_ingredient_type": "红肉",
        "cooking_method": "煮",
        "oil_level": 2,
        "protein_grams_estimate": 30,
        "vegetable_ratio_estimate": 0.2,
        "is_complete_meal": False,
        "spicy_level": 1,
        "tags": [],
    })


def test_const_sets_nonempty():
    assert "湘菜" in CUISINES
    assert "红肉" in INGREDIENT_TYPES
    assert "煮" in COOKING_METHODS

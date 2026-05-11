"""dish_tagged / restaurant pydantic schemas (DESIGN §5.2).

打标产出 (data/{zone}/dishes_tagged.json) 必须每条通过 ``DishTagged`` 校验。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# 严格对齐 DESIGN §5.2 cuisine 枚举 (16 项, 不要扩展)
CUISINES = {
    "湘菜", "川菜", "粤菜", "潮汕", "东北", "西北", "江浙", "鲁菜",
    "日式", "韩式", "西式", "东南亚", "快餐", "小吃", "汤粥", "其他",
}

INGREDIENT_TYPES = {
    "红肉", "白肉", "海鲜", "蛋", "豆制品", "纯素", "主食", "汤", "其他",
}

COOKING_METHODS = {
    "蒸", "煮", "烤", "炒", "炖", "油炸", "凉拌", "生", "煎",
}


class NutritionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_ingredient_type: str
    cooking_method: str
    oil_level: int = Field(ge=1, le=5)
    protein_grams_estimate: int = Field(ge=0)
    vegetable_ratio_estimate: float = Field(ge=0.0, le=1.0)
    is_complete_meal: bool
    spicy_level: int = Field(ge=0, le=3)
    tags: list[str] = Field(default_factory=list)

    @field_validator("main_ingredient_type")
    @classmethod
    def _check_ingredient(cls, v: str) -> str:
        if v not in INGREDIENT_TYPES:
            raise ValueError(
                f"main_ingredient_type {v!r} not in {sorted(INGREDIENT_TYPES)}"
            )
        return v

    @field_validator("cooking_method")
    @classmethod
    def _check_cooking(cls, v: str) -> str:
        if v not in COOKING_METHODS:
            raise ValueError(
                f"cooking_method {v!r} not in {sorted(COOKING_METHODS)}"
            )
        return v


class DishMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tagged_at: str
    tag_version: str
    is_available: bool = True


class DishTagged(BaseModel):
    """data/{zone}/dishes_tagged.json 单条记录 schema."""

    model_config = ConfigDict(extra="forbid")

    dish_id: str
    restaurant_id: str
    raw_name: str
    canonical_name: str
    price: float = Field(ge=0)
    monthly_sales: int = Field(ge=0)
    cuisine: str
    nutrition_profile: NutritionProfile
    metadata: DishMetadata

    @field_validator("cuisine")
    @classmethod
    def _check_cuisine(cls, v: str) -> str:
        if v not in CUISINES:
            raise ValueError(f"cuisine {v!r} not in {sorted(CUISINES)}")
        return v


def validate_dishes_tagged(records: list[dict[str, Any]]) -> list[DishTagged]:
    """全量校验 dishes_tagged.json 内容；任何一条不合法直接抛 ValidationError."""
    return [DishTagged.model_validate(r) for r in records]

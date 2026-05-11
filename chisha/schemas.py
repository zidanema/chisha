"""dish_tagged / restaurant pydantic schemas (DESIGN §5.2).

打标产出 (data/{zone}/dishes_tagged.json) 必须每条通过 ``DishTagged`` 校验。

v3 (D-032) 新增 5 字段: dish_role / processed_meat_flag / sweet_sauce_level
/ wetness / grain_type. 旧 v1 / v2-promptfix 数据无这 5 字段, 在校验前
需要全量重打成 v3 (见 scripts/tag_via_api.py).
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

# v3 新增 (D-032)
DISH_ROLES = {
    "主菜", "主食", "配菜", "汤", "小食", "饮品", "套餐",
}

GRAIN_TYPES = {
    "白米", "糙米杂粮", "精制面", "全麦面", "粗粮", "粥", "无",
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
    # v3 新增 5 字段 (D-032). 旧 v1 / v2 数据需 v3 prompt 全量重打.
    dish_role: str
    processed_meat_flag: bool
    sweet_sauce_level: int = Field(ge=0, le=3)
    wetness: int = Field(ge=1, le=3)
    grain_type: str
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

    @field_validator("dish_role")
    @classmethod
    def _check_dish_role(cls, v: str) -> str:
        if v not in DISH_ROLES:
            raise ValueError(f"dish_role {v!r} not in {sorted(DISH_ROLES)}")
        return v

    @field_validator("grain_type")
    @classmethod
    def _check_grain_type(cls, v: str) -> str:
        if v not in GRAIN_TYPES:
            raise ValueError(f"grain_type {v!r} not in {sorted(GRAIN_TYPES)}")
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

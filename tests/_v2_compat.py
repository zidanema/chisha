"""V1 RefineIntent → V2 兼容 helper (测试用).

D-096 V1 退役后, 老测试仍以 V1 kwargs (cuisine_want / flavor_tags / staple_preference / portion)
构造 intent. 这里把 V1 kwargs 映射到 V2 dataclass, 避免每个测试重写.

新测试应直接构造 RefineIntentV2, 不要走这个 shim.
"""
from __future__ import annotations

from chisha.refine_intent_v2 import RefineIntentV2


def make_v1_compat_intent(
    *,
    cuisine_want: list[str] | None = None,
    cuisine_avoid: list[str] | None = None,
    ingredient_want: list[str] | None = None,
    ingredient_avoid: list[str] | None = None,
    flavor_tags: list[str] | None = None,
    portion: list[str] | None = None,
    staple_preference: str | None = None,
    staple_want: list[str] | None = None,
    staple_avoid: list[str] | None = None,
    price_band: str | None = None,
    raw_text: str = "",
    cuisine_candidates_expanded: list[str] | None = None,
    brand_avoid: list[str] | None = None,
    cooking_method_avoid: list[str] | None = None,
) -> RefineIntentV2:
    """把 V1 kwargs 映射到 V2 RefineIntentV2 dataclass.

    映射规则 (跟 D-094.1 schema 对齐):
      - flavor_tags=heavy → constrain.oil="high"
      - flavor_tags=light → constrain.oil="low"
      - flavor_tags=soup → constrain.wants_soup=True
      - staple_preference=want_rice → staple_want=["米饭"]
      - staple_preference=want_noodle → staple_want=["面"]
      - staple_preference=avoid_staple → staple_avoid=["米饭", "面"]
      - portion (more_meat/less_carb/...): V1 已砍, 无映射 (相关测试已删/改).
    """
    redirect = {
        "cuisine_want": cuisine_want or [],
        "cuisine_avoid": cuisine_avoid or [],
        "cuisine_candidates_expanded": cuisine_candidates_expanded or [],
        "ingredient_want": ingredient_want or [],
        "ingredient_avoid": ingredient_avoid or [],
        "brand_avoid": brand_avoid or [],
        "cooking_method_avoid": cooking_method_avoid or [],
        "staple_want": staple_want or [],
        "staple_avoid": staple_avoid or [],
    }
    constrain = {
        "oil": None,
        "price_max": None,
        "price_band": price_band,
        "wants_soup": False,
    }
    for tag in (flavor_tags or []):
        if tag == "heavy":
            constrain["oil"] = "high"
        elif tag == "light":
            constrain["oil"] = "low"
        elif tag == "soup":
            constrain["wants_soup"] = True
    if staple_preference == "want_rice":
        redirect["staple_want"] = ["米饭"]
    elif staple_preference == "want_noodle":
        redirect["staple_want"] = ["面"]
    elif staple_preference == "avoid_staple":
        redirect["staple_avoid"] = ["米饭", "面"]
    return RefineIntentV2(redirect=redirect, constrain=constrain, raw_text=raw_text)

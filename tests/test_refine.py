"""refine.py 单测.

end-to-end refine 跑通需要召回数据, 这里用 fixture 构造小型 zone 数据.
"""
from __future__ import annotations

import datetime as dt

import pytest

from chisha.refine import chips_to_taste_hints, refine
from chisha.session import create_session, save_session
from tests.conftest import make_dish, make_restaurant


# ─────────────────────── chips_to_taste_hints
def test_chips_to_hints_soup():
    hints = chips_to_taste_hints(["想喝汤"])
    assert "wetness" in hints["boost"]


def test_chips_to_hints_too_oily_means_low_oil_boost():
    """'太油' chip 应转成 boost low_oil (用户想 low_oil)."""
    hints = chips_to_taste_hints(["太油"])
    assert "low_oil" in hints["boost"]
    assert "low_oil" not in hints["penalty"]


def test_chips_to_hints_sweet_penalty():
    hints = chips_to_taste_hints(["太甜"])
    assert "sweet_sauce" in hints["penalty"]


def test_chips_to_hints_processed_meat_penalty():
    hints = chips_to_taste_hints(["加工肉太多"])
    assert "processed_meat" in hints["penalty"]


def test_chips_to_hints_unknown_chip_ignored():
    hints = chips_to_taste_hints(["送慢", "拒签"])
    # 这些 chip 不映射到 taste 维度
    assert hints["boost"] == []
    assert hints["penalty"] == []


def test_chips_to_hints_multiple():
    hints = chips_to_taste_hints(["想喝汤", "太油", "加工肉太多"])
    assert "wetness" in hints["boost"]
    assert "low_oil" in hints["boost"]
    assert "processed_meat" in hints["penalty"]


# ─────────────────────── refine end-to-end
@pytest.fixture
def small_profile():
    return {
        "basics": {"office_zone": "test", "zones": {"lunch": "test"}},
        "taste_description": "喜欢汤水, 不要油焖",
        "preferences": {
            "liked_cuisines": ["潮汕"],
            "disliked_cuisines": [],
            "avoid_dishes": [],
            "spicy_tolerance": 2,
        },
        "plate_rule": {"must_have_vegetable": True, "min_vegetable_dishes": 1,
                        "min_protein_g": 25, "prefer_oil_level_at_most": 3,
                        "hard_max_oil_level": 5},
        "diversity": {"no_same_restaurant_within_days": 7,
                       "no_same_main_ingredient_within_days": 3},
        "recall": {"top_n": 100, "per_restaurant_max": 3,
                    "min_monthly_sales": 10},
    }


@pytest.fixture
def tiny_zone():
    """3 家店 x 各几道菜, 足够 recall 出几个 combo."""
    rests = [
        {**make_restaurant(rid="r1", name="潮汕汤店"),
         "office_zone": "test", "category": "潮汕"},
        {**make_restaurant(rid="r2", name="湘菜店"),
         "office_zone": "test", "category": "湘菜"},
        {**make_restaurant(rid="r3", name="日式店"),
         "office_zone": "test", "category": "日式"},
    ]
    dishes = [
        # r1 潮汕: 汤水牛肉 + 蔬菜
        make_dish(dish_id="d1_1", restaurant_id="r1",
                  raw_name="潮汕牛肉汤", canonical_name="潮汕牛肉汤",
                  cuisine="潮汕", main_ingredient_type="红肉",
                  oil_level=2, protein_grams_estimate=35,
                  vegetable_ratio_estimate=0.1, wetness=3,
                  dish_role="主菜", monthly_sales=200),
        make_dish(dish_id="d1_2", restaurant_id="r1",
                  raw_name="蒜蓉空心菜", canonical_name="蒜蓉空心菜",
                  cuisine="潮汕", main_ingredient_type="纯素",
                  oil_level=2, vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3, dish_role="配菜",
                  monthly_sales=180),
        # r2 湘菜: 重口炒肉 + 蔬菜
        make_dish(dish_id="d2_1", restaurant_id="r2",
                  raw_name="辣椒炒肉", canonical_name="辣椒炒肉",
                  cuisine="湘菜", main_ingredient_type="白肉",
                  oil_level=4, protein_grams_estimate=30,
                  vegetable_ratio_estimate=0.2, dish_role="主菜",
                  monthly_sales=150),
        make_dish(dish_id="d2_2", restaurant_id="r2",
                  raw_name="炒油麦", canonical_name="炒油麦菜",
                  cuisine="湘菜", main_ingredient_type="纯素",
                  oil_level=3, vegetable_ratio_estimate=0.9,
                  protein_grams_estimate=3, dish_role="配菜",
                  monthly_sales=100),
        # r3 日式: 拉面 (主食重)
        make_dish(dish_id="d3_1", restaurant_id="r3",
                  raw_name="豚骨拉面", canonical_name="豚骨拉面",
                  cuisine="日式", main_ingredient_type="主食",
                  oil_level=3, protein_grams_estimate=20,
                  vegetable_ratio_estimate=0.1, is_complete_meal=True,
                  dish_role="主食", grain_type="精制面",
                  monthly_sales=300),
        make_dish(dish_id="d3_2", restaurant_id="r3",
                  raw_name="日式沙拉", canonical_name="日式沙拉",
                  cuisine="日式", main_ingredient_type="纯素",
                  oil_level=1, vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=5, dish_role="配菜",
                  monthly_sales=80),
    ]
    return rests, dishes


def test_refine_session_not_found_raises(tmp_path, small_profile, tiny_zone):
    rests, dishes = tiny_zone
    with pytest.raises(FileNotFoundError):
        refine(
            session_id="nope",
            user_input="想喝汤",
            profile=small_profile,
            rests=rests,
            tagged=dishes,
            meal_log=[],
            root=tmp_path,
            today=dt.date(2026, 5, 13),
            use_llm=False,
        )


def test_refine_increments_round(tmp_path, small_profile, tiny_zone):
    """refine 后 session.round + 1, refine_history 增长."""
    rests, dishes = tiny_zone
    sid = "sid_refine_test"
    s = create_session(sid, "lunch", "test")
    save_session(s, tmp_path)

    out = refine(
        session_id=sid,
        user_input="想喝汤别给我面",
        profile=small_profile,
        rests=rests,
        tagged=dishes,
        meal_log=[],
        root=tmp_path,
        today=dt.date(2026, 5, 13),
        use_llm=False,
    )
    assert out["session_id"] == sid
    assert out["round"] == 2
    assert out["refine_input"] == "想喝汤别给我面"
    assert "candidates" in out
    # taste_hints 应反映 chips
    assert "wetness" in out["taste_hints"]["boost"]


def test_refine_no_explore(tmp_path, small_profile, tiny_zone):
    """refine 时 candidates 不应包含 is_explore=True."""
    rests, dishes = tiny_zone
    sid = "sid_refine_no_explore"
    s = create_session(sid, "lunch", "test")
    save_session(s, tmp_path)
    out = refine(sid, "想清淡", small_profile, rests, dishes, [],
                  root=tmp_path, today=dt.date(2026, 5, 13), use_llm=False)
    explore = [c for c in out["candidates"] if c.get("is_explore")]
    assert len(explore) == 0


def test_refine_persists_session(tmp_path, small_profile, tiny_zone):
    """refine 后 session 文件应被更新."""
    from chisha.session import load_session
    rests, dishes = tiny_zone
    sid = "sid_persist"
    s = create_session(sid, "lunch", "test")
    save_session(s, tmp_path)
    refine(sid, "太油", small_profile, rests, dishes, [],
            root=tmp_path, today=dt.date(2026, 5, 13), use_llm=False)
    reloaded = load_session(sid, tmp_path)
    assert reloaded.round == 2
    assert "太油" in reloaded.refine_history
    assert len(reloaded.last_candidates) > 0


def test_refine_parsed_feedback_attached(tmp_path, small_profile, tiny_zone):
    rests, dishes = tiny_zone
    sid = "sid_parsed"
    s = create_session(sid, "lunch", "test")
    save_session(s, tmp_path)
    out = refine(sid, "太油了, 想喝汤", small_profile, rests, dishes, [],
                  root=tmp_path, today=dt.date(2026, 5, 13), use_llm=False)
    pf = out["parsed_feedback"]
    assert "太油" in pf["chips"]
    assert "想喝汤" in pf["chips"]

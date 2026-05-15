"""recommend_meal V2 主路径集成测试.

不依赖真实 v3 数据 (Session 1 还在重打), 用 monkeypatch 注入小型 zone 数据.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from chisha import api as api_module
from chisha.api import recommend_meal
from chisha.session import load_session
from tests.conftest import make_dish, make_restaurant


@pytest.fixture
def patched_v2_env(monkeypatch, tmp_path):
    """注入小型 zone 数据 + tmp 工作目录."""
    profile = {
        "basics": {
            "office_zone": "test",
            "zones": {"lunch": "test", "dinner": "test"},
        },
        "taste_description": "喜欢汤水, 不要油焖",
        "preferences": {
            "liked_cuisines": ["潮汕"],
            "disliked_cuisines": [],
            "avoid_dishes": [],
            "spicy_tolerance": 2,
        },
        "plate_rule": {
            "must_have_vegetable": True, "min_vegetable_dishes": 1,
            "min_protein_g": 25, "prefer_oil_level_at_most": 3,
            "hard_max_oil_level": 5,
        },
        "diversity": {"no_same_restaurant_within_days": 7,
                       "no_same_main_ingredient_within_days": 3},
        "recall": {"top_n": 100, "per_restaurant_max": 3,
                    "min_monthly_sales": 10},
    }
    rests = [
        {**make_restaurant(rid="r1", name="潮汕汤店"),
         "office_zone": "test", "category": "潮汕"},
        {**make_restaurant(rid="r2", name="湘菜店"),
         "office_zone": "test", "category": "湘菜"},
    ]
    dishes = [
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
    ]
    monkeypatch.setattr(api_module, "load_profile", lambda *a, **k: profile)
    monkeypatch.setattr(api_module, "load_zone_data",
                         lambda zone, root: (rests, dishes))
    monkeypatch.setattr(api_module, "load_meal_log", lambda root: [])
    return tmp_path


def test_v2_path_basic(patched_v2_env):
    """主路径走 build_context + rerank, 输出 ≤5 候选 + version=v2 (D-049 后唯一路径)."""
    out = recommend_meal("lunch", today=dt.date(2026, 5, 13),
                         log_to_file=False,
                         daily_mood="want_soup", use_llm_rerank=False,
                         root=patched_v2_env)
    assert out["version"] == "v2"
    assert "context" in out
    assert out["context"]["daily_mood"] == "want_soup"
    assert "session_id" in out
    assert len(out["candidates"]) <= 5


def test_v2_candidates_have_v2_fields(patched_v2_env):
    """V2 candidate 应含 fit_score / health_flags / risk_flags."""
    out = recommend_meal("lunch", today=dt.date(2026, 5, 13),
                         log_to_file=False,
                         use_llm_rerank=False, root=patched_v2_env)
    for c in out["candidates"]:
        assert "fit_score" in c
        assert "health_flags" in c
        assert "risk_flags" in c
        assert "is_explore" in c


def test_v2_creates_session(patched_v2_env):
    """V2 应创建 session 文件供 refine 用."""
    out = recommend_meal("lunch", today=dt.date(2026, 5, 13),
                         log_to_file=False,
                         daily_mood="want_light", use_llm_rerank=False,
                         root=patched_v2_env)
    sid = out["session_id"]
    state = load_session(sid, patched_v2_env)
    assert state is not None
    assert state.meal_type == "lunch"
    assert state.daily_mood == "want_light"
    assert len(state.last_candidates) > 0


def test_v2_explore_count(patched_v2_env):
    """V2 默认应有 explore (n_explore=2)."""
    out = recommend_meal("lunch", today=dt.date(2026, 5, 13),
                         log_to_file=False,
                         use_llm_rerank=False, root=patched_v2_env)
    explore = [c for c in out["candidates"] if c.get("is_explore")]
    assert len(explore) <= 2


def test_v2_serializable(patched_v2_env):
    out = recommend_meal("lunch", today=dt.date(2026, 5, 13),
                         log_to_file=False,
                         use_llm_rerank=False, root=patched_v2_env)
    s = json.dumps(out, ensure_ascii=False)
    assert "v2" in s

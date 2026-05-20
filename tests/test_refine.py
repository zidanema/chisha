"""refine 主流程单测 (D-073 v2 重写).

砍掉的旧 D-035 chips_to_taste_hints 测试 (refine 端不再产 chip).
砍掉的旧 D-071 mood inference 测试 (单独文件已删).

保留:
  - refine session 生命周期 (round++, history, persists)
  - refine_intent 字段携带 (取代 parsed_feedback)
  - refine 不出 explore (refine=True → n_explore=0)
"""
from __future__ import annotations

import datetime as dt

import pytest

from chisha.refine import refine
from chisha.session import create_session, save_session
from tests.conftest import make_dish, make_restaurant


@pytest.fixture
def small_profile():
    return {
        "basics": {"name": "测试", "city": "test",
                    "zones": {"lunch": "test", "dinner": "test"},
                    "office_zone": "test"},
        "plate_rule": {
            "must_have_vegetable": True,
            "min_vegetable_dishes": 1,
            "min_protein_g": 0,
            "prefer_oil_level_at_most": 3,
            "hard_max_oil_level": 5,
        },
        "preferences": {
            "liked_cuisines": [], "disliked_cuisines": [],
            "banned_cuisines": [],
            "avoid_dishes": [], "avoid_main_ingredients": [],
            "avoid_cooking_methods": [], "avoid_restaurants": [],
            "spicy_tolerance": 3,
        },
        "delivery_constraints": {"hard_max_eta_min": 45, "prefer_max_eta_min": 30},
        "price_range": {"hard_max_lunch": 200, "hard_max_dinner": 200,
                        "prefer_max_lunch": 100, "prefer_max_dinner": 100},
        "diversity": {"no_same_restaurant_within_days": 7,
                      "no_same_main_ingredient_within_days": 3},
        "recall": {"per_restaurant_max": 5, "per_restaurant_top_k": 3,
                   "per_brand_top_k": 2, "per_cuisine_top_k": 6,
                   "per_food_form_top_k": 8, "min_monthly_sales": 0,
                   "max_dishes_per_combo": 3, "max_protein_per_combo": 1,
                   "max_veg_per_combo": 1, "max_carb_per_combo": 1},
        "scoring_weights": {
            "low_oil": 0.5, "popularity": 0.4, "cuisine_preference": 0.3,
            "variety_bonus": 0.5, "carb_quality": 0.6, "processed_meat": 1.0,
            "sweet_sauce": 0.7, "wetness": 0.5, "dish_role_match": 0.3,
            "intent_cuisine": 0.20, "intent_ingredient": 0.10, "intent_flavor": 0.10,
        },
        "taste_description": "",
    }


@pytest.fixture
def tiny_zone():
    rests = [
        make_restaurant("r_1", "湖南老灶台"),
        make_restaurant("r_2", "日料一番"),
    ]
    dishes = [
        make_dish("d_1", "r_1", "酸辣椒炒肉", cuisine="湘菜",
                  main_ingredient_type="红肉", vegetable_ratio_estimate=0.0, spicy_level=2),
        make_dish("d_2", "r_1", "清炒时蔬", cuisine="湘菜",
                  main_ingredient_type="纯素", vegetable_ratio_estimate=0.8, spicy_level=0),
        make_dish("d_3", "r_2", "三文鱼刺身", cuisine="日式",
                  main_ingredient_type="海鲜", vegetable_ratio_estimate=0.0, spicy_level=0),
        make_dish("d_4", "r_2", "海带沙拉", cuisine="日式",
                  main_ingredient_type="纯素", vegetable_ratio_estimate=0.8, spicy_level=0),
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
    # D-073: refine_intent 取代 parsed_feedback/taste_hints
    assert "refine_intent" in out
    assert "soup" in out["refine_intent"]["flavor_tags"]


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


def test_refine_intent_attached(tmp_path, small_profile, tiny_zone):
    """D-073: refine 输出携带结构化 refine_intent."""
    rests, dishes = tiny_zone
    sid = "sid_intent"
    s = create_session(sid, "lunch", "test")
    save_session(s, tmp_path)
    out = refine(sid, "想吃湘菜, 肉多一点", small_profile, rests, dishes, [],
                  root=tmp_path, today=dt.date(2026, 5, 13), use_llm=False)
    intent = out["refine_intent"]
    # rule_parse fallback 应能抓到 cuisine + portion
    assert "湖南菜" in intent["cuisine_want"]
    assert "more_meat" in intent["portion"]


def test_refine_intent_v2_attached(tmp_path, small_profile, tiny_zone):
    """T-P1a-03 follow-up: refine 输出携带 V2 多 slot trace 双存."""
    rests, dishes = tiny_zone
    sid = "sid_intent_v2"
    s = create_session(sid, "lunch", "test")
    save_session(s, tmp_path)
    out = refine(sid, "想吃湘菜, 肉多一点", small_profile, rests, dishes, [],
                  root=tmp_path, today=dt.date(2026, 5, 13), use_llm=False)
    # 1. response 携带 refine_intent_v2 字段
    assert "refine_intent_v2" in out
    v2 = out["refine_intent_v2"]
    # 2. trace 双存三份 都在
    assert v2["schema_version"] == "2.0"
    assert v2["raw_text"] == "想吃湘菜, 肉多一点"
    assert v2["raw_understanding"]   # 非空 (use_llm=False 走 V1 兜底, raw_understanding 填降级原因)
    # 3. redirect.cuisine_want 从 V1 from_legacy 同步 (rule_parse 抓"湘菜"→"湖南菜")
    assert "湖南菜" in v2["redirect"]["cuisine_want"]
    # 4. D-094: unsupported_in_recall 字段已砍, 不再出现 (D-085 第二句失效)
    assert "unsupported_in_recall" not in v2
    # 5. V1 字段保留 (legacy_v1)
    assert v2["legacy_v1"].get("portion") == ["more_meat"]


def test_refine_avoid_hard_filter(tmp_path, small_profile, tiny_zone):
    """D-073: cuisine_avoid 硬过滤, 二轮候选不含目标菜系."""
    rests, dishes = tiny_zone
    sid = "sid_avoid"
    s = create_session(sid, "lunch", "test")
    save_session(s, tmp_path)
    out = refine(sid, "不要日料, 想吃湘菜", small_profile, rests, dishes, [],
                  root=tmp_path, today=dt.date(2026, 5, 13), use_llm=False)
    # candidates 全部不该是 日式 cuisine
    cuisines = []
    for c in out["candidates"]:
        for d in c.get("dishes", []):
            cuisines.append(d.get("cuisine"))
    assert "日式" not in cuisines


# D-078.2 Codex S2 FIX-NOW: refine 二轮必须 root 透传到 rerank, 否则
# sandbox 启用时 _profile_block 走默认 (project root 兜底), L1 行为信号
# 在 refine 链路静默缺失 / 跨 worktree 串数据.
def test_refine_passes_root_to_rerank(tmp_path, small_profile, tiny_zone, monkeypatch):
    """守门: refine() 调用 rerank() 必须显式传 root=root (与 api.recommend_meal 对齐)."""
    rests, dishes = tiny_zone
    sid = "sid_root_thread"
    s = create_session(sid, "lunch", "test")
    save_session(s, tmp_path)

    captured: dict = {}
    from chisha import refine as refine_module

    original = refine_module.rerank

    def spy_rerank(*args, **kwargs):
        captured["root"] = kwargs.get("root")
        captured["called"] = True
        return original(*args, **kwargs)

    monkeypatch.setattr(refine_module, "rerank", spy_rerank)

    refine(sid, "想喝汤", small_profile, rests, dishes, [],
            root=tmp_path, today=dt.date(2026, 5, 13), use_llm=False)

    assert captured.get("called"), "rerank 必须被 refine 调用"
    assert captured["root"] == tmp_path, (
        "refine 必须把 root 透传给 rerank, 否则 _profile_block 读不到正确"
        "long_term_prefs.json (sandbox / multi-worktree 串数据)"
    )

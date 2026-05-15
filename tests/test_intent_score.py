"""D-073: intent_match_bonus + health_guardrail + recall intent 单测.

覆盖:
  - cuisine 命中 (exact / soft / 别名归一)
  - ingredient 命中 (广义 + 具体)
  - flavor (spicy 走 profile.spicy_tolerance / soup / light / heavy)
  - portion / staple_preference / price_band 经 ingredient 通道
  - health_guardrail (高油 / unforgivable penalty 触发 × 0.4)
  - Codex §5 spicy_tolerance 边界 (>tolerance 不命中, ==target 满分, <target 半分)
  - recall 三桶 + cuisine_avoid 硬过滤
"""
from __future__ import annotations

import pytest

from chisha.refine_intent import RefineIntent
from chisha.score import (
    cuisine_exact_match, cuisine_soft_match, contains_ingredient,
    normalize_cuisine, intent_match_bonus, health_guardrail,
    score_combo, rank_combos,
)
from chisha.recall import recall, _apply_intent_buckets


# ─────────────────────────── helpers ───────────────────────────


def _dish(name="测试菜", cuisine="湘菜", oil=2, spicy=0, wetness=1,
           main_type="红肉", role="主菜", price=20.0, sweet=0,
           processed=False, grain=None, complete=False, veg_ratio=0.0,
           protein=20):
    np_ = {
        "main_ingredient_type": main_type,
        "cooking_method": "炒",
        "oil_level": oil,
        "spicy_level": spicy,
        "wetness": wetness,
        "dish_role": role,
        "sweet_sauce_level": sweet,
        "processed_meat_flag": processed,
        "protein_grams_estimate": protein,
        "vegetable_ratio_estimate": veg_ratio,
        "is_complete_meal": complete,
        "grain_type": grain,
    }
    return {
        "dish_id": f"d_{name}",
        "restaurant_id": "r_1",
        "canonical_name": name,
        "raw_name": name,
        "cuisine": cuisine,
        "price": price,
        "monthly_sales": 100,
        "nutrition_profile": np_,
        "metadata": {"is_available": True},
    }


def _combo(dishes, rest_name="湖南老灶台", brand=None, distance_m=1000,
            eta=20):
    return {
        "restaurant": {
            "id": "r_1", "name": rest_name, "brand": brand or rest_name,
            "distance_m": distance_m, "delivery_eta_min": eta,
        },
        "dishes": dishes,
    }


# ─────────────────────────── normalize_cuisine ───────────────────────────


def test_normalize_cuisine_aliases():
    """用户表达的 cuisine 名 → 数据中的标准名."""
    assert normalize_cuisine("湖南菜") == "湘菜"
    assert normalize_cuisine("湘菜") == "湘菜"
    assert normalize_cuisine("湖南料理") == "湘菜"
    assert normalize_cuisine("日料") == "日式"
    assert normalize_cuisine("粤菜") == "粤菜"
    assert normalize_cuisine("不存在的菜系") is None
    assert normalize_cuisine("") is None


# ─────────────────────────── cuisine match ───────────────────────────


def test_cuisine_exact_match():
    combo = _combo([_dish(cuisine="湘菜")])
    assert cuisine_exact_match(combo, ["湖南菜"]) is True
    assert cuisine_exact_match(combo, ["湘菜"]) is True
    assert cuisine_exact_match(combo, ["粤菜"]) is False
    assert cuisine_exact_match(combo, []) is False


def test_cuisine_soft_match():
    """店名含目标词 → 软命中."""
    combo = _combo([_dish(cuisine="其他", name="家常炒肉")], rest_name="湖南老灶台")
    assert cuisine_soft_match(combo, ["湖南菜"]) is True


# ─────────────────────────── ingredient ───────────────────────────


def test_contains_ingredient_broad():
    """广义词: 肉 → main_ingredient_type ∈ {红肉, 白肉}."""
    combo = _combo([_dish(main_type="红肉")])
    assert contains_ingredient(combo, "肉") is True
    combo2 = _combo([_dish(main_type="纯素")])
    assert contains_ingredient(combo2, "肉") is False


def test_contains_ingredient_specific():
    """具体词: 牛肉 → canonical_name 子串."""
    combo = _combo([_dish(name="酸辣椒炒牛肉")])
    assert contains_ingredient(combo, "牛肉") is True


# ─────────────────────────── intent_match_bonus ───────────────────────────


def test_intent_match_cuisine_exact():
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 2}}
    combo = _combo([_dish(cuisine="湘菜")])
    intent = RefineIntent(cuisine_want=["湖南菜"])
    parts = intent_match_bonus(combo, intent, profile)
    assert parts["cuisine"] == 1.0
    assert parts["ingredient"] == 0.0
    assert parts["flavor"] == 0.0


def test_intent_match_cuisine_soft():
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 2}}
    combo = _combo([_dish(cuisine="其他", name="家常菜")], rest_name="湘味坊")
    intent = RefineIntent(cuisine_want=["湘菜"])
    parts = intent_match_bonus(combo, intent, profile)
    assert parts["cuisine"] == 0.6


def test_intent_match_ingredient():
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 2}}
    combo = _combo([_dish(main_type="红肉")])
    intent = RefineIntent(ingredient_want=["肉"])
    parts = intent_match_bonus(combo, intent, profile)
    assert parts["ingredient"] == pytest.approx(0.4)


def test_intent_match_spicy_target():
    """Codex §5: spicy_level == min(tolerance, 2) → 满分 0.5."""
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 2}}
    # target = min(2, 2) = 2
    combo = _combo([_dish(spicy=2)])
    intent = RefineIntent(flavor_tags=["spicy"])
    parts = intent_match_bonus(combo, intent, profile)
    assert parts["flavor"] == pytest.approx(0.5)


def test_intent_match_spicy_below_target():
    """Codex §5: 1 <= spicy_level < target → 半分."""
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 3}}
    # target = min(3, 2) = 2; spicy=1 < target → 0.25
    combo = _combo([_dish(spicy=1)])
    intent = RefineIntent(flavor_tags=["spicy"])
    parts = intent_match_bonus(combo, intent, profile)
    assert parts["flavor"] == pytest.approx(0.25)


def test_intent_match_spicy_zero():
    """spicy_level == 0 → 不加分 (用户想吃辣但 combo 完全不辣)."""
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 2}}
    combo = _combo([_dish(spicy=0)])
    intent = RefineIntent(flavor_tags=["spicy"])
    parts = intent_match_bonus(combo, intent, profile)
    assert parts["flavor"] == 0.0


def test_intent_match_spicy_low_tolerance():
    """Codex §5: 用户 spicy_tolerance=1 + 想吃辣 → target=1, spicy=1 满分."""
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 1}}
    combo = _combo([_dish(spicy=1)])
    intent = RefineIntent(flavor_tags=["spicy"])
    parts = intent_match_bonus(combo, intent, profile)
    # target = min(1, 2) = 1; spicy=1 == target → 0.5
    assert parts["flavor"] == pytest.approx(0.5)


def test_intent_match_soup():
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 2}}
    combo = _combo([_dish(wetness=3)])  # 高 wetness → soup_or_broth 命中
    intent = RefineIntent(flavor_tags=["soup"])
    parts = intent_match_bonus(combo, intent, profile)
    assert parts["flavor"] == pytest.approx(0.5)


def test_intent_match_light():
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 2}}
    combo = _combo([_dish(oil=1), _dish(oil=2, name="清炒时蔬")])
    intent = RefineIntent(flavor_tags=["light"])
    parts = intent_match_bonus(combo, intent, profile)
    assert parts["flavor"] == pytest.approx(0.5)


# ─────────────────────────── portion / staple / price ────────────


def test_intent_match_more_meat():
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 2}}
    combo = _combo([_dish(main_type="红肉"), _dish(main_type="白肉")])
    intent = RefineIntent(portion=["more_meat"])
    parts = intent_match_bonus(combo, intent, profile)
    assert parts["ingredient"] >= 0.4  # 多肉 boost


def test_intent_match_avoid_staple():
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 2}}
    combo_no_carb = _combo([_dish(role="主菜"), _dish(role="配菜")])
    combo_with_carb = _combo([_dish(role="主菜"), _dish(role="主食", main_type="主食")])
    intent = RefineIntent(staple_preference="avoid_staple")
    p1 = intent_match_bonus(combo_no_carb, intent, profile)
    p2 = intent_match_bonus(combo_with_carb, intent, profile)
    assert p1["ingredient"] > p2["ingredient"]


def test_intent_match_price_cheap():
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 2}}
    combo = _combo([_dish(price=15.0), _dish(price=20.0, name="蔬菜")])
    intent = RefineIntent(price_band="cheap")
    parts = intent_match_bonus(combo, intent, profile)
    # total=35, <=40 → 命中
    assert parts["cuisine"] > 0  # price_band 经 cuisine 通道


# ─────────────────────────── health_guardrail ───────────────────────────


def test_health_guardrail_high_oil():
    """oil_avg > prefer + 1 → 0.4 折."""
    profile = {"plate_rule": {"prefer_oil_level_at_most": 2}}
    combo = _combo([_dish(oil=5), _dish(oil=5, name="另一菜")])
    assert health_guardrail(combo, profile) == 0.4


def test_health_guardrail_safe():
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3}}
    combo = _combo([_dish(oil=2)])
    assert health_guardrail(combo, profile) == 1.0


def test_health_guardrail_unforgivable_sweet_processed():
    """sweet>=3 + processed → 触发."""
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3}}
    combo = _combo([_dish(sweet=3), _dish(processed=True, name="火腿")])
    assert health_guardrail(combo, profile) == 0.4


def test_intent_match_guardrail_applied():
    """高油 combo + intent 命中 → 加分 × 0.4."""
    profile = {"plate_rule": {"prefer_oil_level_at_most": 2},
               "preferences": {"spicy_tolerance": 2}}
    combo = _combo([_dish(cuisine="湘菜", oil=5), _dish(oil=5, name="另一菜")])
    intent = RefineIntent(cuisine_want=["湖南菜"])
    parts = intent_match_bonus(combo, intent, profile)
    # 原本 cuisine_exact = 1.0, 触发 guardrail → 1.0 × 0.4 = 0.4
    assert parts["cuisine"] == pytest.approx(0.4)


# ─────────────────────────── intent=None 不影响 ───────────────────────


def test_intent_none_no_effect():
    profile = {"plate_rule": {"prefer_oil_level_at_most": 3},
               "preferences": {"spicy_tolerance": 2}}
    combo = _combo([_dish()])
    parts = intent_match_bonus(combo, None, profile)
    assert parts == {"cuisine": 0.0, "ingredient": 0.0, "flavor": 0.0}


def test_score_combo_intent_breakdown():
    """score_combo 带 intent → breakdown 含 intent_cuisine/ingredient/flavor."""
    profile = {
        "plate_rule": {"prefer_oil_level_at_most": 3, "min_protein_g": 0},
        "preferences": {"spicy_tolerance": 2, "liked_cuisines": [], "disliked_cuisines": []},
        "scoring_weights": {"intent_cuisine": 0.2},
    }
    combo = _combo([_dish(cuisine="湘菜")])
    intent = RefineIntent(cuisine_want=["湖南菜"])
    s, br = score_combo(combo, profile, intent=intent)
    assert "intent_cuisine" in br
    # 1.0 × 0.2
    assert br["intent_cuisine"] == pytest.approx(0.2)


# ─────────────────────────── recall 三桶 ───────────────────────────


def test_apply_intent_buckets_avoid_hard_filter():
    """cuisine_avoid 硬过滤."""
    combos = [
        _combo([_dish(cuisine="日式")]),
        _combo([_dish(cuisine="湘菜")]),
        _combo([_dish(cuisine="粤菜")]),
    ]
    intent = RefineIntent(cuisine_avoid=["日料"])
    out = _apply_intent_buckets(combos, intent, n=5)
    cuisines_in_out = [c["dishes"][0]["cuisine"] for c in out]
    assert "日式" not in cuisines_in_out
    assert "湘菜" in cuisines_in_out


def test_apply_intent_buckets_ingredient_avoid():
    """ingredient_avoid 硬过滤."""
    combos = [
        _combo([_dish(name="香菜炒肉")]),
        _combo([_dish(name="清炒时蔬")]),
    ]
    intent = RefineIntent(ingredient_avoid=["香菜"])
    out = _apply_intent_buckets(combos, intent, n=5)
    assert len(out) == 1
    assert "香菜" not in out[0]["dishes"][0]["canonical_name"]


def test_apply_intent_buckets_exact_priority():
    """exact 命中桶优先排前面."""
    combos = [
        _combo([_dish(cuisine="粤菜", name="粤菜")], rest_name="粤A"),
        _combo([_dish(cuisine="湘菜", name="湘菜1")], rest_name="湖南A"),
        _combo([_dish(cuisine="日式", name="日料")], rest_name="日A"),
        _combo([_dish(cuisine="湘菜", name="湘菜2")], rest_name="湖南B"),
    ]
    intent = RefineIntent(cuisine_want=["湖南菜"])
    out = _apply_intent_buckets(combos, intent, n=5)
    # 前 2 条都是湘菜
    assert out[0]["dishes"][0]["cuisine"] == "湘菜"
    assert out[1]["dishes"][0]["cuisine"] == "湘菜"


def test_apply_intent_buckets_fallback_on_low_count():
    """Q1: exact < 阈值 → 回落全集 (不严过滤)."""
    combos = [
        _combo([_dish(cuisine="湘菜")], rest_name="湖南A"),  # 唯一一个 exact
        _combo([_dish(cuisine="日式")], rest_name="日A"),
        _combo([_dish(cuisine="粤菜")], rest_name="粤A"),
    ]
    intent = RefineIntent(cuisine_want=["湖南菜"])
    out = _apply_intent_buckets(combos, intent, n=5)
    # 阈值 max(5*2, 60*0.15)=10, 我们只有 1 个 exact, 远 < 阈值 → 回落全集
    # 所有 3 个 combo 都保留 (avoid 没设)
    assert len(out) == 3
    # exact 仍在前
    assert out[0]["dishes"][0]["cuisine"] == "湘菜"


# ─────────────── Codex P1-4: combo generation 截断前排序锁定 ───────────────


def test_intent_aware_combo_sort_prevents_truncation():
    """D-073 Codex §2 核心: intent 命中菜在 dish 池排序里有 boost,
    避免被 sales-only 排序的 [:6] 截断扔掉.

    场景: 一家店有 7 个红肉 dish, 6 热门 (销量 100-600) + 1 冷门湘菜牛肉 (销量 10).
    不带 intent 时: 冷门湘菜 = rank #7, 被 proteins[:6] 截掉, combo 不含它.
    带 intent (cuisine_want=湖南菜): 湘菜 dish 加 intent_score 2.0 × 1.5 = 3.0,
                                   总排序键远超 sales/1000=0.6, 进 proteins[:6].
    """
    from chisha.recall import build_combos_for_restaurant

    profile = {
        "plate_rule": {"must_have_vegetable": False, "min_vegetable_dishes": 0,
                       "min_protein_g": 0},
        "recall": {"max_dishes_per_combo": 2, "max_protein_per_combo": 1,
                   "max_veg_per_combo": 1, "max_carb_per_combo": 0},
    }

    # 6 个热门红肉 (非湘菜, 销量高)
    proteins_hot = [
        _dish(name=f"热门红肉{i}", cuisine="粤菜", main_type="红肉",
              role="主菜", veg_ratio=0.0)
        for i in range(6)
    ]
    for i, p in enumerate(proteins_hot):
        p["monthly_sales"] = 600 - i * 100   # 600, 500, ..., 100

    # 1 个冷门湘菜牛肉 (intent 目标, 销量极低)
    rare_xiang = _dish(name="冷门湘菜牛肉", cuisine="湘菜",
                       main_type="红肉", role="主菜", veg_ratio=0.0)
    rare_xiang["monthly_sales"] = 10
    rare_xiang["dish_id"] = "d_rare_xiang"

    veg = _dish(name="蔬菜", main_type="纯素", role="配菜", veg_ratio=0.9)
    veg["dish_id"] = "d_veg"

    rest_dishes = proteins_hot + [rare_xiang, veg]

    # 不带 intent: 冷门湘菜在 protein 排序末尾, [:6] 截掉
    combos_no_intent = build_combos_for_restaurant(rest_dishes, profile,
                                                     per_rest_max=20)
    has_xiang_no_intent = any(
        any("湘菜" in d.get("canonical_name", "") for d in combo)
        for combo in combos_no_intent
    )
    assert not has_xiang_no_intent, \
        "不带 intent 时冷门湘菜被销量排序截掉, 验证 baseline"

    # 带 intent: 湘菜 dish 加 intent_score, 跳进 [:6]
    intent = RefineIntent(cuisine_want=["湖南菜"], ingredient_want=["牛肉"])
    combos_with_intent = build_combos_for_restaurant(rest_dishes, profile,
                                                       per_rest_max=20,
                                                       intent=intent)
    has_xiang_with_intent = any(
        any("湘菜" in d.get("canonical_name", "") for d in combo)
        for combo in combos_with_intent
    )
    assert has_xiang_with_intent, \
        "带 intent 时冷门湘菜被 intent_score 顶进 protein 池, 应该出现在 combo 里"


def test_intent_aware_combo_sort_negative_avoid():
    """cuisine_avoid 命中的 dish, intent_score 给 -5.0, 排到末尾."""
    from chisha.recall import _intent_dish_score

    avoid_dish = _dish(cuisine="日式", name="三文鱼", main_type="海鲜")
    intent = RefineIntent(cuisine_avoid=["日料"])
    score = _intent_dish_score(avoid_dish, intent)
    assert score <= -5.0, f"avoid 命中应该给极低分, 实测 {score}"


def test_intent_aware_combo_sort_no_intent_returns_zero():
    """intent=None 时 _intent_dish_score 返回 0, 不影响排序."""
    from chisha.recall import _intent_dish_score
    d = _dish()
    assert _intent_dish_score(d, None) == 0.0


# ─────────────── Codex P0-2: contains_ingredient 牛肉 ≠ 白肉 ───────────────


def test_contains_ingredient_beef_does_not_match_chicken():
    """Codex P0-2 修订: "牛肉" 不能命中白肉 (鸡肉 dish)."""
    combo = _combo([_dish(main_type="白肉", name="清蒸鸡")])
    assert contains_ingredient(combo, "牛肉") is False


def test_contains_ingredient_chicken_does_not_match_redmeat():
    """Codex P0-2 修订: "鸡肉" 不能命中红肉."""
    combo = _combo([_dish(main_type="红肉", name="梅菜扣肉")])
    assert contains_ingredient(combo, "鸡肉") is False


def test_contains_ingredient_beef_matches_by_name():
    """具体食材子串命中菜名 (正向)."""
    combo = _combo([_dish(main_type="红肉", name="酸辣椒炒牛肉")])
    assert contains_ingredient(combo, "牛肉") is True


def test_contains_ingredient_beef_fallback_to_redmeat():
    """菜名不含'牛肉'但 main_ingredient=红肉, '牛' 走 PROTEIN_KEYWORDS fallback."""
    combo = _combo([_dish(main_type="红肉", name="夫妻肺片")])
    # "牛" 在 "牛肉" 中, _PROTEIN_KEYWORDS_TO_MTYPE["牛"]=红肉, 命中
    assert contains_ingredient(combo, "牛肉") is True


# ─────────────── Codex P1-2: cuisine_soft_match 单字白名单 ───────────────


def test_cuisine_soft_match_one_char_blocked():
    """Codex P1-2 修订: bare 单字不再裸匹配, 避免 "西"→"广西米粉"."""
    combo = _combo([_dish(cuisine="其他", name="米粉")], rest_name="广西米粉店")
    # 用户说 "西餐" → bare="西", 不应命中 "广西米粉店"
    assert cuisine_soft_match(combo, ["西餐"]) is False


def test_cuisine_soft_match_one_char_whitelist():
    """白名单 1 字简称 (粤式/湘味/川味) 仍能匹配整词."""
    combo = _combo([_dish(cuisine="其他", name="家常菜")], rest_name="粤式茶餐厅")
    # 用户说 "粤菜" → bare="粤" → 白名单 "粤式" startswith "粤" 且 "粤式" in haystack
    assert cuisine_soft_match(combo, ["粤菜"]) is True

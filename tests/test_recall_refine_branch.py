"""T-P1a-02: L1 召回参数 refine 分支 + ingredient_want 反查 + 三级回落.

覆盖:
  - intent=None / is_empty → 旧行为不变 (baseline 0 diff 子项)
  - intent 非空 → per_rest_max = refine_per_restaurant_max (默认 5)
  - ingredient_want 走反查回到候选池
  - 反查不绕开 L0-A allergy / L0-B identity (medical safety)
  - 三级回落 trace 事件 level=1/2/3
  - per_rest_max=5 + brand cap=2 仍正确卡 (apply_caps 不被打破)
"""
from __future__ import annotations

import datetime as dt

from chisha.recall import recall, _ingredient_want_reverse_lookup
from tests._v2_compat import make_v1_compat_intent as RefineIntent



def _make_dish(dish_id, name, *, restaurant_id="r1",
               main_ingredient_type="红肉", oil_level=2,
               protein_grams_estimate=30, vegetable_ratio_estimate=0.0,
               processed_meat_flag=False, sales=100):
    return {
        "dish_id": dish_id,
        "canonical_name": name,
        "raw_name": name,
        "restaurant_id": restaurant_id,
        "monthly_sales": sales,
        "cuisine": "潮汕",
        "nutrition_profile": {
            "main_ingredient_type": main_ingredient_type,
            "cooking_method": "煮",
            "oil_level": oil_level,
            "protein_grams_estimate": protein_grams_estimate,
            "vegetable_ratio_estimate": vegetable_ratio_estimate,
            "is_complete_meal": False,
            "spicy_level": 0,
            "processed_meat_flag": processed_meat_flag,
            "sweet_sauce_level": 0,
            "wetness": 1,
            "dish_role": "主菜" if main_ingredient_type in ("红肉", "白肉",
                                                              "海鲜") else "配菜",
            "tags": [],
            "grain_type": "无",
        },
    }


def _make_veg_dish(dish_id, name, *, restaurant_id="r1"):
    return _make_dish(dish_id, name, restaurant_id=restaurant_id,
                       main_ingredient_type="纯素", protein_grams_estimate=3,
                       vegetable_ratio_estimate=0.95)


def _make_rest(rid, name="店", brand=None):
    return {
        "id": rid,
        "name": name,
        "office_zone": "test",
        "category": "潮汕",
        "distance_m": 500,
        "delivery_eta_min": 20,
        "monthly_orders": 500,
        "rating": 4.5,
        "brand": brand or name,
    }


def _make_profile(*, allergies=None, dietary_law=None,
                   per_restaurant_max=3, refine_per_restaurant_max=5):
    p: dict = {
        "preferences": {"avoid_dishes": [], "avoid_main_ingredients": [],
                         "avoid_cooking_methods": [], "banned_cuisines": [],
                         "spicy_tolerance": 5},
        "plate_rule": {"must_have_vegetable": True, "min_vegetable_dishes": 1,
                       "min_protein_g": 0, "hard_max_oil_level": 5},
        "recall": {"per_restaurant_max": per_restaurant_max,
                   "refine_per_restaurant_max": refine_per_restaurant_max,
                   "min_monthly_sales": 0,
                   "max_protein_per_combo": 4, "max_veg_per_combo": 2,
                   "max_carb_per_combo": 1, "max_dishes_per_combo": 4},
        "diversity": {"no_same_restaurant_within_days": 7,
                       "no_same_main_ingredient_within_days": 3},
        "delivery_constraints": {"hard_max_eta_min": 60},
    }
    if allergies is not None or dietary_law is not None:
        p["l0_constraints"] = {
            "medical": {"allergies": allergies or []},
            "identity": {"dietary_law": dietary_law},
        }
    return p


# ────────────────────────── per_rest_max 分支


def test_recall_empty_intent_no_extra_branch():
    """intent=None → 走默认 per_rest_max, ingredient 反查不触发, fallback events 不写."""
    dishes = [_make_dish(f"d{i}", f"红烧肉{i}") for i in range(8)] + \
             [_make_veg_dish("d_veg", "炒油麦菜")]
    rests = [_make_rest("r1", "潮汕汤店")]
    p = _make_profile(per_restaurant_max=3)
    events: list[dict] = []
    out = recall(p, rests, dishes, recall_fallback_events=events)
    # 默认 per_rest_max=3 → combo 数 ≤ 3
    assert len(out) <= 3
    # intent=None → 不进 _apply_intent_buckets → 不写事件
    assert events == []


def test_recall_with_intent_uses_refine_per_rest_max():
    """intent 非空 → per_rest_max=5 让一家餐厅出 5 个 combo (严格 == 5).

    Codex review #6 修订: 收紧断言到 == 5 而非 ≤ 5.
    """
    # 10 道肉 + 1 道菜, 让 combo 候选数充足
    dishes = [_make_dish(f"d{i}", f"红烧肉{i}", protein_grams_estimate=30)
              for i in range(10)] + \
             [_make_veg_dish("d_veg", "炒油麦菜")]
    rests = [_make_rest("r1", "潮汕汤店")]
    p = _make_profile(per_restaurant_max=3, refine_per_restaurant_max=5)
    intent = RefineIntent(cuisine_want=["潮汕"], raw_text="想吃潮汕")
    events: list[dict] = []
    out = recall(p, rests, dishes, intent=intent,
                 recall_fallback_events=events)
    # refine 模式 per_rest_max=5: build_combos 输出 == 5 (combo 池足够)
    # 与 default per_rest_max=3 形成对比 (test_recall_empty_intent ≤ 3)
    assert len(out) == 5, f"refine 应出 5 combo, 实出 {len(out)}"
    # 三级回落事件写入
    assert len(events) == 1
    assert events[0]["event_type"] == "recall_fallback"
    # timestamp 是 isoformat 字符串 (Codex review #5: 不用 time.time())
    assert isinstance(events[0]["timestamp"], str)
    assert "T" in events[0]["timestamp"]  # ISO 8601 sanity


# ────────────────────────── ingredient_want 反查


def test_ingredient_want_reverse_lookup_pulls_in_dishes():
    """ingredient_want=['肉'] → 含'肉'菜被反查回候选, 即便 hard_filter 后不在主池."""
    # 多餐厅: r1 主要走主流程, r2 仅靠反查回来
    dishes_in_main = [_make_dish("d_a", "牛肉饭",
                                   main_ingredient_type="红肉",
                                   restaurant_id="r1"),
                       _make_veg_dish("d_av", "油麦菜",
                                       restaurant_id="r1")]
    extra_dish = _make_dish("d_b", "猪肉小炒", restaurant_id="r2",
                              main_ingredient_type="红肉")
    all_dishes = dishes_in_main + [extra_dish,
                                     _make_veg_dish("d_bv", "炒空心菜",
                                                     restaurant_id="r2")]
    p = _make_profile()
    avoid_rests: set[str] = set()
    intent = RefineIntent(ingredient_want=["肉"], raw_text="想吃肉")
    extras = _ingredient_want_reverse_lookup(all_dishes, intent, p, avoid_rests)
    extra_ids = {d["dish_id"] for d in extras}
    assert "d_a" in extra_ids
    assert "d_b" in extra_ids


def test_ingredient_want_reverse_lookup_respects_l0_a():
    """profile.allergies=['花生'] → 反查不能让"花生酱面"回到池子."""
    dishes = [
        _make_dish("d_peanut", "花生酱面", main_ingredient_type="主食"),
        _make_dish("d_pork", "红烧肉"),
    ]
    p = _make_profile(allergies=["花生"])
    avoid_rests: set[str] = set()
    intent = RefineIntent(ingredient_want=["肉", "花生"],
                           raw_text="想吃肉和花生")
    extras = _ingredient_want_reverse_lookup(dishes, intent, p, avoid_rests)
    extra_ids = {d["dish_id"] for d in extras}
    assert "d_peanut" not in extra_ids, "L0-A 必须穿透 ingredient_want"
    assert "d_pork" in extra_ids


def test_ingredient_want_reverse_lookup_respects_l0_b():
    """dietary_law=vegetarian → 反查不能让 红肉 菜回到池子."""
    dishes = [
        _make_dish("d_pork", "红烧肉", main_ingredient_type="红肉"),
        _make_veg_dish("d_veg_meat_named", "素肉炒饭"),  # 名字含"肉"但是纯素
    ]
    p = _make_profile(dietary_law="vegetarian")
    avoid_rests: set[str] = set()
    intent = RefineIntent(ingredient_want=["肉"], raw_text="想吃肉")
    extras = _ingredient_want_reverse_lookup(dishes, intent, p, avoid_rests)
    extra_ids = {d["dish_id"] for d in extras}
    assert "d_pork" not in extra_ids, "L0-B vegetarian 必须穿透 ingredient_want"
    assert "d_veg_meat_named" in extra_ids  # 纯素被允许


def test_ingredient_want_reverse_lookup_empty_no_op():
    """ingredient_want=[] → 反查 noop."""
    p = _make_profile()
    intent = RefineIntent(cuisine_want=["潮汕"], raw_text="想吃潮汕")
    extras = _ingredient_want_reverse_lookup([], intent, p, set())
    assert extras == []


# ────────────────────────── 三级回落 (level 1/2/3 trace)


def _build_combos_fixture(n_exact: int, n_soft: int, n_rest: int):
    """生成 fixture: n_exact 个 cuisine=湘菜 (exact), n_soft 个名字含'肉' (soft),
    n_rest 个其他.
    """
    from chisha.recall import _apply_intent_buckets
    combos = []
    # exact: cuisine=湘菜
    for i in range(n_exact):
        combos.append({
            "restaurant": {"id": f"re{i}", "name": f"湘菜{i}",
                            "brand": f"湘菜{i}"},
            "dishes": [{"dish_id": f"de{i}", "canonical_name": f"湘菜{i}",
                         "raw_name": f"湘菜{i}", "cuisine": "湘菜",
                         "nutrition_profile": {"main_ingredient_type": "红肉"}}],
        })
    # soft: 别的 cuisine, 名字含"肉" (ingredient 命中)
    for i in range(n_soft):
        combos.append({
            "restaurant": {"id": f"rs{i}", "name": f"店{i}",
                            "brand": f"店{i}"},
            "dishes": [{"dish_id": f"ds{i}", "canonical_name": f"红烧肉{i}",
                         "raw_name": f"红烧肉{i}", "cuisine": "潮汕",
                         "nutrition_profile": {"main_ingredient_type": "红肉"}}],
        })
    # rest: 完全无关
    for i in range(n_rest):
        combos.append({
            "restaurant": {"id": f"rr{i}", "name": f"日{i}",
                            "brand": f"日{i}"},
            "dishes": [{"dish_id": f"dr{i}", "canonical_name": f"寿司{i}",
                         "raw_name": f"寿司{i}", "cuisine": "日料",
                         "nutrition_profile": {"main_ingredient_type": "海鲜"}}],
        })
    return combos


def test_recall_fallback_level1_floor_met():
    """exact + soft ≥ 30 → level 1."""
    from chisha.recall import _apply_intent_buckets
    combos = _build_combos_fixture(n_exact=30, n_soft=5, n_rest=10)
    intent = RefineIntent(cuisine_want=["湘菜"], ingredient_want=["肉"],
                           raw_text="想吃湘菜的肉")
    events: list[dict] = []
    out = _apply_intent_buckets(combos, intent, n=5,
                                  recall_fallback_events=events)
    assert len(events) == 1
    assert events[0]["level"] == 1
    assert events[0]["intent_hit_count"] >= 30


def test_recall_fallback_level2_below_floor():
    """10 ≤ intent_hit < 30 → level 2."""
    from chisha.recall import _apply_intent_buckets
    combos = _build_combos_fixture(n_exact=12, n_soft=3, n_rest=10)
    intent = RefineIntent(cuisine_want=["湘菜"], ingredient_want=["肉"],
                           raw_text="想吃湘菜的肉")
    events: list[dict] = []
    _apply_intent_buckets(combos, intent, n=5,
                            recall_fallback_events=events)
    assert events[0]["level"] == 2
    assert 10 <= events[0]["intent_hit_count"] < 30


def test_recall_fallback_level3_below_10():
    """intent_hit < 10 → level 3."""
    from chisha.recall import _apply_intent_buckets
    combos = _build_combos_fixture(n_exact=2, n_soft=3, n_rest=20)
    intent = RefineIntent(cuisine_want=["湘菜"], ingredient_want=["肉"],
                           raw_text="想吃湘菜的肉")
    events: list[dict] = []
    _apply_intent_buckets(combos, intent, n=5,
                            recall_fallback_events=events)
    assert events[0]["level"] == 3
    assert events[0]["intent_hit_count"] < 10


def test_recall_fallback_event_not_written_when_list_is_none():
    """recall_fallback_events=None → 不写事件, 内部跑通."""
    from chisha.recall import _apply_intent_buckets
    combos = _build_combos_fixture(n_exact=5, n_soft=5, n_rest=5)
    intent = RefineIntent(cuisine_want=["湘菜"], raw_text="x")
    out = _apply_intent_buckets(combos, intent, n=5)
    assert isinstance(out, list)


# ────────────────────────── brand cap interaction


def test_per_rest_max_5_brand_cap_still_applies():
    """refine 模式 per_rest_max=5 让 1 餐厅 5 combo,
    apply_caps brand cap=2 仍会卡到 2 同品牌.
    """
    from chisha.score import apply_caps
    # 5 个 combo 同品牌 + 各种 dish
    combos = [
        {"restaurant": {"id": f"r{i}", "brand": "same_brand", "name": "X"},
         "dishes": [{"dish_id": f"d{i}", "cuisine": "潮汕",
                      "nutrition_profile": {"main_ingredient_type": "红肉"}}],
         "score_breakdown": {}, "fit_score": 1.0 - i * 0.01,
         "food_form": "饭", "cap_keys": {"restaurant": f"r{i}",
                                         "brand": "same_brand",
                                         "cuisine": "潮汕"}}
        for i in range(5)
    ]
    profile = _make_profile()
    capped = apply_caps(combos, profile)
    brands = [c["restaurant"]["brand"] for c in capped]
    # brand cap=2 (默认), 即使 per_rest_max 改了, brand cap 仍生效
    assert brands.count("same_brand") <= 2


# ────────────────────────── D-094: cooking_method_avoid 硬过滤


def test_d094_cooking_method_avoid_filters_dish_in_combo():
    """combo 内任一 dish 命中 cooking_method_avoid → 整个 combo 弃."""
    from chisha.recall import _apply_intent_buckets
    combos = [
        {  # 含 1 道油炸 → 应弃
            "restaurant": {"id": "r1", "name": "店1", "brand": "b1"},
            "dishes": [
                {"dish_id": "d1a", "canonical_name": "炸鸡", "raw_name": "炸鸡",
                 "cuisine": "湘菜",
                 "nutrition_profile": {"cooking_method": "油炸",
                                        "main_ingredient_type": "白肉"}},
                {"dish_id": "d1b", "canonical_name": "青菜", "raw_name": "青菜",
                 "cuisine": "湘菜",
                 "nutrition_profile": {"cooking_method": "炒",
                                        "main_ingredient_type": "蔬菜"}},
            ],
        },
        {  # 全炒 → 应留
            "restaurant": {"id": "r2", "name": "店2", "brand": "b2"},
            "dishes": [
                {"dish_id": "d2a", "canonical_name": "炒牛肉", "raw_name": "炒牛肉",
                 "cuisine": "湘菜",
                 "nutrition_profile": {"cooking_method": "炒",
                                        "main_ingredient_type": "红肉"}},
            ],
        },
    ]
    intent = RefineIntent(cooking_method_avoid=["油炸"], raw_text="不要油炸")
    out = _apply_intent_buckets(combos, intent, n=5)
    assert len(out) == 1
    assert out[0]["restaurant"]["id"] == "r2"


def test_d094_cooking_method_avoid_multi_method():
    """cooking_method_avoid=['油炸','烤'] → 含任一即弃."""
    from chisha.recall import _apply_intent_buckets
    combos = [
        {"restaurant": {"id": "ra", "name": "X", "brand": "ba"},
         "dishes": [{"dish_id": "da", "canonical_name": "煎饺", "raw_name": "煎饺",
                      "cuisine": "粤菜",
                      "nutrition_profile": {"cooking_method": "煎",
                                             "main_ingredient_type": "白肉"}}]},
        {"restaurant": {"id": "rb", "name": "Y", "brand": "bb"},
         "dishes": [{"dish_id": "db", "canonical_name": "烤鸭", "raw_name": "烤鸭",
                      "cuisine": "粤菜",
                      "nutrition_profile": {"cooking_method": "烤",
                                             "main_ingredient_type": "白肉"}}]},
        {"restaurant": {"id": "rc", "name": "Z", "brand": "bc"},
         "dishes": [{"dish_id": "dc", "canonical_name": "炸鸡", "raw_name": "炸鸡",
                      "cuisine": "粤菜",
                      "nutrition_profile": {"cooking_method": "油炸",
                                             "main_ingredient_type": "白肉"}}]},
    ]
    intent = RefineIntent(cooking_method_avoid=["油炸", "烤"], raw_text="不要油炸不要烤")
    out = _apply_intent_buckets(combos, intent, n=5)
    # 烤 + 油炸 都被弃, 煎留下
    ids = {c["restaurant"]["id"] for c in out}
    assert ids == {"ra"}


# ────────────────────────── D-094: cuisine_candidates_expanded → bucket_soft


def test_d094_cuisine_expanded_routes_to_bucket_soft():
    """cuisine_want=[], expanded=['川菜'] → 川菜 combos 进 bucket_soft (优先), 其他进 rest."""
    from chisha.recall import _apply_intent_buckets
    combos = [
        {"restaurant": {"id": f"rc{i}", "name": f"川店{i}", "brand": f"b{i}"},
         "dishes": [{"dish_id": f"dc{i}", "canonical_name": f"川菜{i}",
                      "raw_name": f"川菜{i}", "cuisine": "川菜",
                      "nutrition_profile": {"cooking_method": "炒",
                                             "main_ingredient_type": "红肉"}}]}
        for i in range(3)
    ] + [
        {"restaurant": {"id": f"rj{i}", "name": f"日店{i}", "brand": f"jb{i}"},
         "dishes": [{"dish_id": f"dj{i}", "canonical_name": f"寿司{i}",
                      "raw_name": f"寿司{i}", "cuisine": "日料",
                      "nutrition_profile": {"cooking_method": "生",
                                             "main_ingredient_type": "海鲜"}}]}
        for i in range(3)
    ]
    intent = RefineIntent(cuisine_candidates_expanded=["川菜"], raw_text="想吃辣")
    out = _apply_intent_buckets(combos, intent, n=5)
    # bucket_soft + bucket_rest 拼合, 川菜 (soft) 应排在前
    top3_ids = {c["restaurant"]["id"] for c in out[:3]}
    assert all(rid.startswith("rc") for rid in top3_ids)


def test_d094_cuisine_want_beats_expanded_when_both_present():
    """cuisine_want=['湘菜'], expanded=['川菜'] → 湘菜进 exact (顶层), 川菜进 soft."""
    from chisha.recall import _apply_intent_buckets
    combos = [
        {"restaurant": {"id": "rxiang", "name": "湘店", "brand": "bx"},
         "dishes": [{"dish_id": "dx", "canonical_name": "辣椒炒肉",
                      "raw_name": "辣椒炒肉", "cuisine": "湘菜",
                      "nutrition_profile": {"cooking_method": "炒",
                                             "main_ingredient_type": "红肉"}}]},
        {"restaurant": {"id": "rchuan", "name": "川店", "brand": "bc"},
         "dishes": [{"dish_id": "dc", "canonical_name": "麻婆豆腐",
                      "raw_name": "麻婆豆腐", "cuisine": "川菜",
                      "nutrition_profile": {"cooking_method": "煮",
                                             "main_ingredient_type": "蔬菜"}}]},
        {"restaurant": {"id": "rjp", "name": "日店", "brand": "bj"},
         "dishes": [{"dish_id": "dj", "canonical_name": "寿司",
                      "raw_name": "寿司", "cuisine": "日料",
                      "nutrition_profile": {"cooking_method": "生",
                                             "main_ingredient_type": "海鲜"}}]},
    ]
    intent = RefineIntent(cuisine_want=["湘菜"],
                            cuisine_candidates_expanded=["川菜"],
                            raw_text="湘菜或者辣的")
    out = _apply_intent_buckets(combos, intent, n=5)
    # 湘菜 exact 优先, 川菜 soft 第二, 日料 rest 第三
    assert out[0]["restaurant"]["id"] == "rxiang"
    assert out[1]["restaurant"]["id"] == "rchuan"
    assert out[2]["restaurant"]["id"] == "rjp"


def test_d094_cuisine_expanded_only_no_want_no_ingredient_still_buckets():
    """`if not cuisine_want and not ingredient_want: return combos` 早退 gate
    要也认 cuisine_candidates_expanded — 不然 expanded 单字段 refine 不进桶.
    """
    from chisha.recall import _apply_intent_buckets
    combos = [
        {"restaurant": {"id": "rc", "name": "川店", "brand": "bc"},
         "dishes": [{"dish_id": "dc", "canonical_name": "麻婆豆腐",
                      "raw_name": "麻婆豆腐", "cuisine": "川菜",
                      "nutrition_profile": {"cooking_method": "煮",
                                             "main_ingredient_type": "蔬菜"}}]},
        {"restaurant": {"id": "rj", "name": "日店", "brand": "bj"},
         "dishes": [{"dish_id": "dj", "canonical_name": "寿司",
                      "raw_name": "寿司", "cuisine": "日料",
                      "nutrition_profile": {"cooking_method": "生",
                                             "main_ingredient_type": "海鲜"}}]},
    ]
    intent = RefineIntent(cuisine_candidates_expanded=["川菜"], raw_text="想吃辣")
    events: list[dict] = []
    out = _apply_intent_buckets(combos, intent, n=5,
                                  recall_fallback_events=events)
    # 进桶了: 川菜在 bucket_soft, 日料在 rest, 顺序应是川菜在前
    assert out[0]["restaurant"]["id"] == "rc"
    # events 写到了 (说明走了三级回落分支, 不是早退)
    assert len(events) == 1


# ────────────────────────── D-094: brand_avoid venue 整店硬过滤


def test_d094_brand_avoid_excludes_whole_venue():
    """recall() 顶层: brand_avoid 命中的 venue 整店剔除 (含其所有 dish)."""
    dishes = [
        _make_dish("d_sal_1", "意面1", restaurant_id="r_sal"),
        _make_dish("d_sal_2", "披萨1", restaurant_id="r_sal"),
        _make_veg_dish("d_sal_v", "沙拉", restaurant_id="r_sal"),
        _make_dish("d_ok_1", "红烧肉", restaurant_id="r_ok"),
        _make_veg_dish("d_ok_v", "炒青菜", restaurant_id="r_ok"),
    ]
    rests = [
        _make_rest("r_sal", "萨莉亚南山店", brand="萨莉亚"),
        _make_rest("r_ok", "湘菜馆", brand="湘菜馆"),
    ]
    p = _make_profile()
    intent = RefineIntent(brand_avoid=["萨莉亚"], raw_text="别再给我萨莉亚")
    out = recall(p, rests, dishes, intent=intent)
    # 萨莉亚整店应剔除, 出现的 combo 都不该来自 r_sal
    venues = {c["restaurant"]["id"] for c in out}
    assert "r_sal" not in venues
    assert venues == {"r_ok"} if venues else True


def test_d094_brand_avoid_empty_intent_no_effect():
    """空 brand_avoid → 不影响召回 (baseline 行为)."""
    dishes = [
        _make_dish("d1", "红烧肉", restaurant_id="r1"),
        _make_veg_dish("d1v", "炒青菜", restaurant_id="r1"),
    ]
    rests = [_make_rest("r1", "湘菜馆", brand="湘菜馆")]
    p = _make_profile()
    intent = RefineIntent(brand_avoid=[], cuisine_want=["潮汕"], raw_text="x")
    out = recall(p, rests, dishes, intent=intent)
    # brand_avoid 空 → r1 仍正常召回
    assert len(out) >= 1
    assert all(c["restaurant"]["id"] == "r1" for c in out)


def test_d094_brand_avoid_substring_match_composite_brand():
    """codex review block: brand 子串匹配, 用户 '麦当劳' 命中复合品牌 '麦当劳＆麦咖啡'.
    实数据有 '麦当劳＆麦咖啡' / '肯德基宅急送' 这种复合 brand, exact 集合命中会漏过滤.
    """
    dishes = [
        _make_dish("d_mc_1", "巨无霸", restaurant_id="r_mc"),
        _make_veg_dish("d_mc_v", "沙拉", restaurant_id="r_mc"),
        _make_dish("d_ok_1", "红烧肉", restaurant_id="r_ok"),
        _make_veg_dish("d_ok_v", "炒青菜", restaurant_id="r_ok"),
    ]
    rests = [
        _make_rest("r_mc", "麦当劳南山", brand="麦当劳＆麦咖啡"),
        _make_rest("r_ok", "湘菜馆", brand="湘菜馆"),
    ]
    p = _make_profile()
    # 用户文本抽出的是裸名 "麦当劳", 子串匹配命中 "麦当劳＆麦咖啡"
    intent = RefineIntent(brand_avoid=["麦当劳"], raw_text="别给我麦当劳")
    out = recall(p, rests, dishes, intent=intent)
    venues = {c["restaurant"]["id"] for c in out}
    assert "r_mc" not in venues, "麦当劳＆麦咖啡 应被 '麦当劳' 子串过滤"


def test_d094_avoid_filter_dropped_recorded_in_event():
    """codex Q2 nit: recall_fallback_event 加 avoid_filter_dropped 字段, 区分
    "L1 命中本来就少" vs "硬过滤后剩余少". 测 cooking_method_avoid 弃 N 个 combo
    后, event["avoid_filter_dropped"] == N.
    """
    from chisha.recall import _apply_intent_buckets
    # 3 个 combo, 2 个含 油炸, 1 个含 炒
    combos = [
        {"restaurant": {"id": f"r{i}", "name": f"店{i}", "brand": f"b{i}"},
         "dishes": [{"dish_id": f"d{i}", "canonical_name": f"炸鸡{i}",
                      "raw_name": f"炸鸡{i}", "cuisine": "湘菜",
                      "nutrition_profile": {"cooking_method": "油炸",
                                             "main_ingredient_type": "白肉"}}]}
        for i in range(2)
    ] + [
        {"restaurant": {"id": "r_ok", "name": "店ok", "brand": "b_ok"},
         "dishes": [{"dish_id": "d_ok", "canonical_name": "炒青菜",
                      "raw_name": "炒青菜", "cuisine": "湘菜",
                      "nutrition_profile": {"cooking_method": "炒",
                                             "main_ingredient_type": "蔬菜"}}]}
    ]
    intent = RefineIntent(cuisine_want=["湘菜"],
                            cooking_method_avoid=["油炸"],
                            raw_text="湘菜不要油炸")
    events: list[dict] = []
    out = _apply_intent_buckets(combos, intent, n=5,
                                  recall_fallback_events=events)
    # 2 个油炸应被弃, 1 个炒留下
    assert len(out) == 1
    # event 记下了 2 个被 avoid 过滤
    assert events[0]["avoid_filter_dropped"] == 2


def test_d094_cuisine_want_expanded_no_double_score():
    """codex review block: cuisine_want=['川菜'] + expanded=['川菜','湘菜']
    时, 川菜 dish 不应被双重加分 (cuisine_want 已给 2.0, expanded 不能再 +1.0).
    """
    from chisha.recall import _intent_dish_score
    chuan_dish = {
        "canonical_name": "麻婆豆腐", "raw_name": "麻婆豆腐",
        "cuisine": "川菜",
        "nutrition_profile": {"main_ingredient_type": "蔬菜"},
        "monthly_sales": 100,
    }
    # only want — expect 2.0
    intent_want_only = RefineIntent(cuisine_want=["川菜"], raw_text="想吃川菜")
    s_want = _intent_dish_score(chuan_dish, intent_want_only)
    # both want + expanded covering same cuisine — expect still 2.0 (no double)
    intent_overlap = RefineIntent(cuisine_want=["川菜"],
                                    cuisine_candidates_expanded=["川菜", "湘菜"],
                                    raw_text="想吃川菜或辣的")
    s_overlap = _intent_dish_score(chuan_dish, intent_overlap)
    assert s_want == s_overlap == 2.0
    # only expanded (want 空) — expect 1.0
    intent_exp_only = RefineIntent(cuisine_candidates_expanded=["川菜"],
                                      raw_text="想吃辣")
    s_exp = _intent_dish_score(chuan_dish, intent_exp_only)
    assert s_exp == 1.0

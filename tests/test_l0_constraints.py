"""T-P1a-01: L0 三分判定 (medical/identity/health) + refine 解除政策单测.

覆盖:
  - L0-A 医学过敏: profile 配 allergies, 含敏感词菜被 drop
  - L0-B 身份伦理 vegetarian / halal (halal 保留羊肉/牛肉,只 ban 猪肉关键词)
  - L0-C refine 明确表达可解除 methodology
  - methodology break 关键词字典样本
  - 空 profile 无任何约束 → 行为完全不变
"""
from __future__ import annotations

from chisha.l0_constraints import (
    L0Constraints,
    dish_violates_l0_a,
    dish_violates_l0_b,
    load_l0_constraints,
    make_hard_filter_event,
)
from chisha.refine_intent_v2 import RefineIntentV2 as RefineIntent
from chisha.recall import (
    hard_filter,
    combo_passes_plate_rule,
)


def _make_dish(dish_id="d_1", name="炒油麦菜", raw_name=None, *,
               main_ingredient_type="纯素", oil_level=2,
               protein_grams_estimate=3, vegetable_ratio_estimate=0.9,
               processed_meat_flag=False, restaurant_id="r1",
               spicy_level=0, sweet_sauce_level=0, monthly_sales=100):
    return {
        "dish_id": dish_id,
        "canonical_name": name,
        "raw_name": raw_name or name,
        "restaurant_id": restaurant_id,
        "monthly_sales": monthly_sales,
        "cuisine": "潮汕",
        "nutrition_profile": {
            "main_ingredient_type": main_ingredient_type,
            "cooking_method": "煮",
            "oil_level": oil_level,
            "protein_grams_estimate": protein_grams_estimate,
            "vegetable_ratio_estimate": vegetable_ratio_estimate,
            "is_complete_meal": False,
            "spicy_level": spicy_level,
            "processed_meat_flag": processed_meat_flag,
            "sweet_sauce_level": sweet_sauce_level,
            "wetness": 1,
            "dish_role": "主菜",
            "tags": [],
            "grain_type": "无",
        },
    }


def _make_profile(
    *,
    allergies: list[str] | None = None,
    dietary_law: str | None = None,
) -> dict:
    p: dict = {
        "preferences": {"avoid_dishes": [], "avoid_main_ingredients": [],
                         "avoid_cooking_methods": [], "banned_cuisines": [],
                         "spicy_tolerance": 5},
        "plate_rule": {"must_have_vegetable": True, "min_vegetable_dishes": 1,
                       "min_protein_g": 25, "hard_max_oil_level": 5},
        "recall": {"min_monthly_sales": 0},
    }
    if allergies is not None or dietary_law is not None:
        p["l0_constraints"] = {
            "medical": {"allergies": allergies or []},
            "identity": {"dietary_law": dietary_law},
        }
    return p


# ────────────────────────── load_l0_constraints


def test_load_l0_empty_profile_returns_empty():
    """profile 完全无 l0_constraints 段 → 空 L0Constraints."""
    p = _make_profile()
    c = load_l0_constraints(p)
    assert c.is_empty()
    assert c.medical_allergies == []
    assert c.dietary_law is None


def test_load_l0_allergies_normalized():
    p = _make_profile(allergies=["花生", "  海鲜 ", "", None])  # type: ignore[list-item]
    c = load_l0_constraints(p)
    assert c.medical_allergies == ["花生", "海鲜"]


def test_load_l0_unknown_dietary_law_falls_back_none():
    """未知 dietary_law 保守降级到 None, 不抛."""
    p = _make_profile(dietary_law="weird_law")
    assert load_l0_constraints(p).dietary_law is None


# ────────────────────────── L0-A 医学过敏


def test_l0_a_drops_dish_with_allergy_substring():
    """profile.allergies=['花生'] → '花生酱面' 菜被 drop, trace event 写入."""
    dishes = [
        _make_dish("d_peanut", "花生酱面", main_ingredient_type="主食"),
        _make_dish("d_ok", "炒油麦菜"),
    ]
    p = _make_profile(allergies=["花生"])
    events: list[dict] = []
    kept, dropped = hard_filter(dishes, p, set(), hard_filter_events=events)
    kept_ids = {d["dish_id"] for d in kept}
    assert "d_peanut" not in kept_ids
    assert "d_ok" in kept_ids
    # event 写入
    assert len(events) == 1
    e = events[0]
    assert e["category"] == "L0_A_medical"
    assert e["rule"] == "allergy:花生"
    assert e["dropped_count"] == 1


def test_l0_a_no_constraint_no_event():
    """空 allergies → 不写 event, 不影响 kept."""
    dishes = [_make_dish("d_1", "花生酱面", main_ingredient_type="主食")]
    p = _make_profile()
    events: list[dict] = []
    kept, _ = hard_filter(dishes, p, set(), hard_filter_events=events)
    assert len(kept) == 1
    assert events == []


# ────────────────────────── L0-B 身份伦理


def test_l0_b_vegetarian_bans_meat():
    """dietary_law='vegetarian' → 红肉/白肉/海鲜全 drop."""
    dishes = [
        _make_dish("d_pork", "红烧肉", main_ingredient_type="红肉"),
        _make_dish("d_chicken", "宫保鸡丁", main_ingredient_type="白肉"),
        _make_dish("d_fish", "清蒸鱼", main_ingredient_type="海鲜"),
        _make_dish("d_egg", "番茄炒蛋", main_ingredient_type="蛋"),
        _make_dish("d_veg", "炒油麦菜", main_ingredient_type="纯素"),
    ]
    p = _make_profile(dietary_law="vegetarian")
    events: list[dict] = []
    kept, _ = hard_filter(dishes, p, set(), hard_filter_events=events)
    kept_ids = {d["dish_id"] for d in kept}
    assert kept_ids == {"d_egg", "d_veg"}
    # 3 个不同 rule → 3 个 event
    assert len(events) == 3
    rules = {e["rule"] for e in events}
    assert "vegetarian_ban_红肉" in rules
    assert "vegetarian_ban_白肉" in rules
    assert "vegetarian_ban_海鲜" in rules


def test_l0_b_halal_preserves_lamb_beef():
    """Codex blocker #2 防线: halal 不 ban 羊肉串/牛肉串, 只 ban 猪肉/培根/叉烧."""
    dishes = [
        _make_dish("d_lamb", "红柳羊肉串", main_ingredient_type="红肉"),
        _make_dish("d_beef", "炭烤牛肉串", main_ingredient_type="红肉"),
        _make_dish("d_pork", "红烧猪肉", main_ingredient_type="红肉"),
        _make_dish("d_bacon", "培根意面", main_ingredient_type="主食",
                   processed_meat_flag=True),
        # Codex review blocker #2 续: 叉烧 / 火腿肠 / 香肠 都应 ban
        _make_dish("d_charsiu", "叉烧螺蛳粉", main_ingredient_type="红肉"),
        _make_dish("d_sausage", "蒜香烤香肠", main_ingredient_type="红肉"),
        # Codex re-review #1: 白切鸡是清真合规, 不应被 ban (此前 keyword 含 "白切" 误伤)
        _make_dish("d_chicken_white", "白切鸡", main_ingredient_type="白肉"),
    ]
    p = _make_profile(dietary_law="halal")
    events: list[dict] = []
    kept, _ = hard_filter(dishes, p, set(), hard_filter_events=events)
    kept_ids = {d["dish_id"] for d in kept}
    assert "d_lamb" in kept_ids
    assert "d_beef" in kept_ids
    assert "d_pork" not in kept_ids
    assert "d_bacon" not in kept_ids
    assert "d_charsiu" not in kept_ids, "叉烧螺蛳粉 必须被 halal ban"
    assert "d_sausage" not in kept_ids, "香肠 必须被 halal ban"
    assert "d_chicken_white" in kept_ids, "白切鸡 不应被 halal ban (清真合规)"


def test_l0_b_halal_processed_meat_flag():
    """halal: processed_meat_flag=True 直接 ban (即便菜名不含猪)."""
    dishes = [
        _make_dish("d_ham", "火腿三明治", main_ingredient_type="白肉",
                   processed_meat_flag=True),
    ]
    p = _make_profile(dietary_law="halal")
    events: list[dict] = []
    kept, _ = hard_filter(dishes, p, set(), hard_filter_events=events)
    assert kept == []
    assert events
    assert events[0]["rule"] == "halal_processed_meat"


# ────────────────────────── L0-C refine 解除


def test_l0_c_default_methodology_enforced():
    """空 refine → plate_rule 严格生效."""
    combo_no_veg = [
        _make_dish("d_p", "宫保鸡丁", main_ingredient_type="白肉",
                   protein_grams_estimate=30, vegetable_ratio_estimate=0.1),
    ]
    profile = {"plate_rule": {"must_have_vegetable": True,
                                "min_vegetable_dishes": 1,
                                "min_protein_g": 25}}
    assert combo_passes_plate_rule(combo_no_veg, profile) is False


def test_l0_c_refine_break_relaxes_plate_rule():
    """refine 文本 '今晚就放纵' → combo 通过, 即便无蔬菜."""
    combo_no_veg = [
        _make_dish("d_p", "宫保鸡丁", main_ingredient_type="白肉",
                   protein_grams_estimate=30, vegetable_ratio_estimate=0.1),
    ]
    profile = {"plate_rule": {"must_have_vegetable": True,
                                "min_vegetable_dishes": 1,
                                "min_protein_g": 25}}
    intent = RefineIntent(raw_text="今晚就放纵, 给我推炒饭")
    assert combo_passes_plate_rule(combo_no_veg, profile, intent=intent) is True


def test_methodology_break_does_not_relax_l0_a():
    """refine 解除只放开 L0-C, L0-A 过敏仍生效."""
    dishes = [_make_dish("d_peanut", "花生酱面")]
    p = _make_profile(allergies=["花生"])
    intent = RefineIntent(raw_text="今晚就放纵, 不管热量")
    # 注: hard_filter 不直接接 intent (L0-C 解除在 combo 层), L0-A 永不可破
    kept, _ = hard_filter(dishes, p, set())
    assert kept == []  # 仍然被过滤


# ────────────────────────── methodology break 关键词


def test_methodology_break_keyword_positive_samples():
    pos = [
        "今晚就放纵, 给我推个红烧肉",
        "破戒模式, 一次性吃个痛快",
        "无所谓, 随便推",
        "今天放飞, 别管热量",
        "今晚不管那么多",
        "别管那么多, 想吃啥推啥",
        "今天就这样, 来个炸鸡",
        "今晚就吃点重口的",
    ]
    for text in pos:
        intent = RefineIntent(raw_text=text)
        assert intent.allows_methodology_break() is True, f"误判 negative: {text}"


def test_methodology_break_keyword_negative_samples():
    neg = [
        "想吃湘菜",                      # 中性偏好
        "肉多一点",                      # 量级表达
        "便宜一点",                      # 价格表达
        "想喝汤",                       # flavor 表达
        "想吃辣的",                      # flavor
        "",                            # 空
        "别太油",                       # constrain, 不是破戒
    ]
    for text in neg:
        intent = RefineIntent(raw_text=text)
        assert intent.allows_methodology_break() is False, f"误判 positive: {text}"


# ────────────────────────── hard_filter_event 构造 helper


def test_make_hard_filter_event_basic():
    e = make_hard_filter_event(
        category="L0_A_medical",
        rule="allergy:花生",
        dropped_count=2,
        kept_count=10,
        refine_override=False,
    )
    assert e["event_type"] == "hard_filter"
    assert e["category"] == "L0_A_medical"
    assert e["rule"] == "allergy:花生"
    assert e["dropped_count"] == 2
    assert e["kept_count"] == 10
    assert e["refine_override"] is False
    assert isinstance(e["timestamp"], float)

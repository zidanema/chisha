"""D-090: refine L2 frozen snapshot 守门测试.

从 logs/recommend_trace/20260519_dinner_8ebd901c10364405/rounds/R2.json 冻结的
60 个 L2 候选 + 顶层 intent (V1 legacy), 重建 combo, 跑 rank_combos, 断言:
  - top-5 cuisine="湘菜" 计数 ≥ 4 (改前实测=2)
  - top-1 intent_cuisine breakdown ≥ 1.0 (改后, 旧权重 0.5)

CONTRACTS: 改 score.py 时若 break 本测试, 必须 D-090.x 修订并更新断言.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chisha.recall import load_meal_log, load_profile, load_zone_data
from chisha.refine_intent_v2 import RefineIntentV2
def RefineIntent(*, cuisine_want=None, cuisine_avoid=None, ingredient_want=None,
                 ingredient_avoid=None, flavor_tags=None, portion=None,
                 staple_preference=None, staple_want=None, staple_avoid=None,
                 price_band=None, raw_text="", cuisine_candidates_expanded=None,
                 brand_avoid=None, cooking_method_avoid=None) -> RefineIntentV2:
    """V1-compat helper: 把 V1 kwargs 映射到 V2 schema."""
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
    constrain = {"oil": None, "price_max": None, "price_band": price_band,
                 "wants_soup": False}
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

from chisha.score import rank_combos


ROOT = Path(__file__).resolve().parents[1]
TRACE_PATH = (
    ROOT / "logs/recommend_trace/20260519_dinner_8ebd901c10364405/rounds/R2.json"
)


def _build_combos_from_trace(trace: dict, root: Path) -> list[dict]:
    """从 trace 的 l2.top 字段 + 原始 data 重建 combo list."""
    rests, tagged = load_zone_data(trace.get("__zone", "shenzhen-bay"), root)
    rest_by_id = {r["id"]: r for r in rests}
    dish_by_id = {d["dish_id"]: d for d in tagged}

    combos = []
    for entry in trace["l2"]["top"]:
        rid = entry["restaurant_id"]
        if rid not in rest_by_id:
            continue
        dish_ids = [d["dish_id"] for d in entry.get("dishes") or []]
        dishes = [dish_by_id[did] for did in dish_ids if did in dish_by_id]
        if not dishes:
            continue
        combos.append({
            "restaurant": rest_by_id[rid],
            "dishes": dishes,
        })
    return combos


def _intent_from_trace(trace: dict) -> RefineIntent:
    """从 trace 顶层 'intent' (legacy V1 dict) 重建 RefineIntent."""
    raw = trace.get("intent") or {}
    return RefineIntent(
        cuisine_want=list(raw.get("cuisine_want") or []),
        cuisine_avoid=list(raw.get("cuisine_avoid") or []),
        ingredient_want=list(raw.get("ingredient_want") or []),
        ingredient_avoid=list(raw.get("ingredient_avoid") or []),
        cooking_method=list(raw.get("cooking_method") or []),
        flavor_tags=list(raw.get("flavor_tags") or []),
        raw_flavor=list(raw.get("raw_flavor") or []),
        portion=list(raw.get("portion") or []),
        staple_preference=raw.get("staple_preference"),
        price_band=raw.get("price_band"),
        freeform_note=raw.get("freeform_note") or "",
        raw_text=raw.get("raw_text") or "",
    )


@pytest.fixture(scope="module")
def trace_payload():
    if not TRACE_PATH.exists():
        pytest.skip(f"frozen trace not found: {TRACE_PATH}")
    return json.loads(TRACE_PATH.read_text(encoding="utf-8"))


def test_r2_refine_top5_cuisine_distribution(trace_payload):
    """改后 R2「湘菜+重口+牛肉鸡肉」L2 top-5 湘菜数 ≥ 4 (改前=2).

    Faithful Refine 第一原则: 用户明确表达 cuisine_want=湘菜, top-5 必须主导湘菜.
    """
    profile = load_profile(ROOT / "profile.yaml")
    meal_log = load_meal_log(ROOT)
    combos = _build_combos_from_trace(trace_payload, ROOT)
    assert len(combos) >= 20, f"trace 重建 combo 数过少: {len(combos)}"

    intent = _intent_from_trace(trace_payload)
    assert intent.cuisine_want, "trace intent 缺 cuisine_want"
    assert "heavy" in intent.flavor_tags, "trace intent 缺 heavy flavor_tag"

    ranked = rank_combos(
        combos, profile, meal_log=meal_log,
        meal_type="dinner", intent=intent,
    )
    top5 = ranked[:5]
    xiang_count = sum(
        1 for c in top5
        if any(d.get("cuisine") == "湘菜" for d in c["dishes"])
    )
    assert xiang_count >= 4, (
        f"D-090 验收失败: top-5 湘菜数={xiang_count} < 4. "
        f"top-5 cuisines={[c['dishes'][0].get('cuisine') for c in top5]}"
    )


def test_r2_refine_intent_cuisine_weight_active(trace_payload):
    """改后湘菜命中的 combo intent_cuisine breakdown ≥ 1.0 (旧权重 0.5)."""
    profile = load_profile(ROOT / "profile.yaml")
    meal_log = load_meal_log(ROOT)
    combos = _build_combos_from_trace(trace_payload, ROOT)
    intent = _intent_from_trace(trace_payload)

    ranked = rank_combos(
        combos, profile, meal_log=meal_log,
        meal_type="dinner", intent=intent,
    )
    xiang_combos = [
        c for c in ranked[:10]
        if any(d.get("cuisine") == "湘菜" for d in c["dishes"])
    ]
    assert xiang_combos, "top-10 无湘菜"
    top_xiang = xiang_combos[0]
    intent_cuisine_part = (top_xiang.get("score_breakdown") or {}).get("intent_cuisine", 0.0)
    assert intent_cuisine_part >= 1.0, (
        f"D-090 验收失败: top-1 湘菜 intent_cuisine breakdown={intent_cuisine_part} < 1.0"
    )


def test_r2_phase2_heavy_low_oil_weight_reduced(trace_payload):
    """D-091 phase-2: refine 含 heavy flavor → low_oil weight ×0.3 (实际 weight = 0.5 × 0.3 = 0.15).

    验证: R2 trace heavy 触发时, top-1 湘菜 combo 的 low_oil breakdown
    = low_oil_score × 0.15 (不再是 × 0.5).
    """
    from chisha.score import _build_refine_weight_overlay, low_oil_score

    profile = load_profile(ROOT / "profile.yaml")
    meal_log = load_meal_log(ROOT)
    combos = _build_combos_from_trace(trace_payload, ROOT)
    intent = _intent_from_trace(trace_payload)
    assert "heavy" in intent.flavor_tags

    overlay = _build_refine_weight_overlay(intent)
    assert overlay.get("low_oil") == 0.3, f"heavy flavor 应触发 low_oil ×0.3, 实际 {overlay}"

    ranked = rank_combos(
        combos, profile, meal_log=meal_log,
        meal_type="dinner", intent=intent,
    )
    top1 = ranked[0]
    expected_low_oil_part = low_oil_score(top1, profile) * 0.5 * 0.3  # base 0.5 × overlay 0.3
    actual = (top1.get("score_breakdown") or {}).get("low_oil", 0.0)
    assert abs(actual - expected_low_oil_part) < 1e-6, (
        f"phase-2 low_oil weight 衰减失效: actual={actual} expected={expected_low_oil_part}"
    )


def test_r2_phase2_cuisine_want_preference_reduced(trace_payload):
    """D-091 phase-2: cuisine_want 非空 → cuisine_preference weight ×0.5 (= 0.3 × 0.5 = 0.15)."""
    from chisha.score import _build_refine_weight_overlay, cuisine_preference_score

    profile = load_profile(ROOT / "profile.yaml")
    meal_log = load_meal_log(ROOT)
    combos = _build_combos_from_trace(trace_payload, ROOT)
    intent = _intent_from_trace(trace_payload)
    assert intent.cuisine_want

    overlay = _build_refine_weight_overlay(intent)
    assert overlay.get("cuisine_preference") == 0.5, (
        f"cuisine_want 非空应触发 cuisine_preference ×0.5, 实际 {overlay}"
    )

    ranked = rank_combos(
        combos, profile, meal_log=meal_log,
        meal_type="dinner", intent=intent,
    )
    # 找一个 cuisine_preference_score != 0 的 combo 验证 breakdown
    for c in ranked[:20]:
        raw_cp = cuisine_preference_score(c, profile)
        actual_cp = (c.get("score_breakdown") or {}).get("cuisine_preference", 0.0)
        if abs(raw_cp) > 0:
            expected = raw_cp * 0.3 * 0.5  # base 0.3 × overlay 0.5
            assert abs(actual_cp - expected) < 1e-6, (
                f"phase-2 cuisine_preference 衰减失效: raw={raw_cp} actual={actual_cp} expected={expected}"
            )
            return
    pytest.skip("trace top-20 内无 cuisine_preference != 0 的 combo")


def test_r2_heavy_flavor_guardrail_exemption(trace_payload):
    """改后 R2 含 heavy flavor → 高油湘菜 (oil_level=4) intent_parts 不被 ×0.4."""
    from chisha.score import intent_match_bonus

    profile = load_profile(ROOT / "profile.yaml")
    combos = _build_combos_from_trace(trace_payload, ROOT)
    intent = _intent_from_trace(trace_payload)

    # 找一个湘菜 + avg oil > prefer+1 的 combo (湖南血鸭等)
    prefer_oil = profile["plate_rule"].get("prefer_oil_level_at_most", 3)
    target = None
    for c in combos:
        cuisines = {d.get("cuisine") for d in c["dishes"]}
        if "湘菜" not in cuisines:
            continue
        oils = [d.get("nutrition_profile", {}).get("oil_level", 3)
                for d in c["dishes"]]
        avg = sum(oils) / max(1, len(oils))
        if avg > prefer_oil + 1:
            target = c
            break

    if target is None:
        pytest.skip("trace 中无高油湘菜 combo 可验证 guardrail 豁免")

    parts = intent_match_bonus(target, intent, profile)
    # 豁免后 cuisine 命中应 ≥ 0.6 (soft match) 或 1.0 (exact); 未豁免会 ×0.4 → ≤ 0.4
    assert parts["cuisine"] >= 0.6, (
        f"heavy flavor guardrail 豁免失效: cuisine part={parts['cuisine']}"
    )

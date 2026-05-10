"""打分: combo → 分数. V1 不引入 personal_offsets/learned_profile."""
from __future__ import annotations

import datetime as dt
import math
from typing import Any


def vegetable_floor_score(combo: dict, profile: dict) -> float:
    """达标 1.0, 不达标 0 (combo_passes_plate_rule 已经在召回过滤过, 此处恒 1)."""
    pr = profile["plate_rule"]
    if not pr.get("must_have_vegetable", True):
        return 1.0
    from chisha.recall import is_vegetable_dish
    n = sum(1 for d in combo["dishes"] if is_vegetable_dish(d))
    return 1.0 if n >= pr.get("min_vegetable_dishes", 1) else 0.0


def protein_floor_score(combo: dict, profile: dict) -> float:
    total = sum(
        d.get("nutrition_profile", {}).get("protein_grams_estimate", 0)
        for d in combo["dishes"]
    )
    floor = profile["plate_rule"].get("min_protein_g", 0)
    return 1.0 if total >= floor else 0.0


def low_oil_score(combo: dict, profile: dict) -> float:
    """油脂越低分越高. prefer_oil_level_at_most 之上线性扣分."""
    prefer = profile["plate_rule"].get("prefer_oil_level_at_most", 3)
    # combo 平均油脂
    oils = [
        d.get("nutrition_profile", {}).get("oil_level", 3)
        for d in combo["dishes"]
    ]
    avg = sum(oils) / max(1, len(oils))
    if avg <= prefer:
        # avg 越小, 分数越接近 1.0; avg=1 时 score=1.0, avg=prefer 时 score=0.5
        return max(0.5, 1.0 - 0.125 * (avg - 1))
    # 超过 prefer 线性扣分: avg=prefer+1 → 0.3, avg=5 (prefer=3) → -0.2
    return max(-0.5, 0.5 - 0.25 * (avg - prefer))


def popularity_score(combo: dict) -> float:
    """log(monthly_sales) 归一. 单菜销量越高分越高."""
    sales = [d.get("monthly_sales", 0) for d in combo["dishes"]]
    avg = sum(sales) / max(1, len(sales))
    if avg <= 0:
        return 0.0
    # log10(1) = 0, log10(1000) = 3, 归一到 [0, 1]
    return min(1.0, math.log10(1 + avg) / 3.0)


def cuisine_preference_score(combo: dict, profile: dict) -> float:
    liked = set(profile["preferences"].get("liked_cuisines", []))
    disliked = set(profile["preferences"].get("disliked_cuisines", []))
    cuisines = {d.get("cuisine", "") for d in combo["dishes"]}
    s = 0.0
    if cuisines & liked:
        s += 1.0
    if cuisines & disliked:
        s -= 1.0
    return s


def variety_bonus_score(
    combo: dict,
    meal_log: list[dict],
    today: dt.date | None = None,
    days: int = 3,
) -> float:
    """combo 的主蛋白 / 烹饪方式 与最近 N 天不同, +0.5; 否则 0."""
    today = today or dt.date.today()
    recent_ingrs: set[str] = set()
    recent_methods: set[str] = set()
    for log in meal_log or []:
        try:
            ts = dt.datetime.fromisoformat(log["timestamp"]).date()
        except Exception:
            continue
        if (today - ts).days > days:
            continue
        for x in log.get("dishes", []):
            if x.get("main_ingredient_type"):
                recent_ingrs.add(x["main_ingredient_type"])
            if x.get("cooking_method"):
                recent_methods.add(x["cooking_method"])
    combo_ingrs = {
        d.get("nutrition_profile", {}).get("main_ingredient_type", "")
        for d in combo["dishes"]
    }
    combo_methods = {
        d.get("nutrition_profile", {}).get("cooking_method", "")
        for d in combo["dishes"]
    }
    novel = (combo_ingrs - recent_ingrs) | (combo_methods - recent_methods)
    return 0.5 if novel else 0.0


def score_combo(
    combo: dict,
    profile: dict,
    meal_log: list[dict] | None = None,
    today: dt.date | None = None,
) -> tuple[float, dict[str, float]]:
    """计算 combo 综合分. 返回 (score, breakdown)."""
    w = profile.get("scoring_weights", {})
    parts = {
        "vegetable_floor_pass": vegetable_floor_score(combo, profile)
            * w.get("vegetable_floor_pass", 1.0),
        "protein_floor_pass": protein_floor_score(combo, profile)
            * w.get("protein_floor_pass", 1.0),
        "low_oil": low_oil_score(combo, profile) * w.get("low_oil", 0.8),
        "popularity": popularity_score(combo) * w.get("popularity", 0.4),
        "cuisine_preference": cuisine_preference_score(combo, profile)
            * w.get("cuisine_preference", 0.5),
        "variety_bonus": variety_bonus_score(combo, meal_log or [], today)
            * w.get("variety_bonus", 0.3),
    }
    return sum(parts.values()), parts


def rank_combos(
    combos: list[dict],
    profile: dict,
    meal_log: list[dict] | None = None,
    today: dt.date | None = None,
) -> list[dict]:
    """对 combos 打分排序, 返回带 score/breakdown 的列表 (降序)."""
    scored = []
    for c in combos:
        s, br = score_combo(c, profile, meal_log, today)
        scored.append({**c, "score": s, "score_breakdown": br})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def diversify_top(
    ranked: list[dict],
    n: int,
    max_per_brand: int = 1,
    max_per_cuisine: int = 2,
) -> list[dict]:
    """Top N 选择时强制品牌/菜系多样性, 避免 top 3 都来自同一连锁."""
    out = []
    used_brand: dict[str, int] = {}
    used_cuisine: dict[str, int] = {}
    for c in ranked:
        if len(out) >= n:
            break
        brand = c["restaurant"].get("brand") or c["restaurant"]["name"]
        if used_brand.get(brand, 0) >= max_per_brand:
            continue
        # combo 的"代表菜系" = 第一道菜的 cuisine
        cuisine = c["dishes"][0].get("cuisine", "")
        if used_cuisine.get(cuisine, 0) >= max_per_cuisine:
            continue
        out.append(c)
        used_brand[brand] = used_brand.get(brand, 0) + 1
        used_cuisine[cuisine] = used_cuisine.get(cuisine, 0) + 1
    # 如果多样性约束太严没凑够 n, 放宽再补
    if len(out) < n:
        existing_keys = {id(c) for c in out}
        for c in ranked:
            if len(out) >= n:
                break
            if id(c) in existing_keys:
                continue
            out.append(c)
    return out


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from chisha.recall import (
        load_profile, load_zone_data, load_meal_log, recall
    )
    root = Path(__file__).resolve().parent.parent
    profile = load_profile(root / "profile.yaml")
    meal = sys.argv[1] if len(sys.argv) > 1 else "lunch"
    zones = profile.get("basics", {}).get("zones") or {}
    zone = zones.get(meal) or profile["basics"]["office_zone"]
    rests, tagged = load_zone_data(zone, root)
    log = load_meal_log(root)
    cs = recall(profile, rests, tagged, log)
    ranked = rank_combos(cs, profile, log)
    top = diversify_top(ranked, 3)
    print(f"召回 {len(cs)} → 打分排序 → 多样性 top 3:\n")
    for i, c in enumerate(top, 1):
        names = [d["canonical_name"] for d in c["dishes"]]
        print(f"#{i} [score={c['score']:.2f}] {c['restaurant']['name']}")
        print(f"    dishes: {names}")
        print(f"    breakdown: {c['score_breakdown']}")

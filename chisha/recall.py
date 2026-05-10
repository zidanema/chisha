"""召回：规则过滤 + 弱约束三件套校验 + 组合策略 → top N 候选.

完整流程见 DESIGN §5.6。V1 不引入个性化项 (D-024)。
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from itertools import product
from pathlib import Path
from typing import Any

import json
import yaml


def load_profile(path: str | Path = "profile.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_zone_data(zone: str, root: Path) -> tuple[list[dict], list[dict]]:
    """读 restaurants + dishes_tagged."""
    base = root / "data" / zone
    rests = json.loads((base / "restaurants.json").read_text(encoding="utf-8"))
    tagged = json.loads((base / "dishes_tagged.json").read_text(encoding="utf-8"))
    return rests, tagged


def load_meal_log(root: Path) -> list[dict]:
    """读 meal_log.jsonl，不存在返回空."""
    p = root / "logs" / "meal_log.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def hard_filter(
    dishes: list[dict],
    profile: dict,
    avoid_restaurant_ids: set[str],
) -> list[dict]:
    """硬过滤 (DESIGN §5.6 召回-2)."""
    avoid_dish_names = set(profile["preferences"].get("avoid_dishes", []))
    spicy_max = profile["preferences"].get("spicy_tolerance", 3)
    hard_max_oil = profile["plate_rule"].get("hard_max_oil_level", 5)
    min_sales = profile.get("recall", {}).get("min_monthly_sales", 0)
    out = []
    for d in dishes:
        if d.get("restaurant_id") in avoid_restaurant_ids:
            continue
        if d.get("canonical_name") in avoid_dish_names:
            continue
        np = d.get("nutrition_profile", {})
        if np.get("spicy_level", 0) > spicy_max:
            continue
        if np.get("oil_level", 0) > hard_max_oil:
            continue
        if d.get("monthly_sales", 0) < min_sales:
            continue
        if not d.get("metadata", {}).get("is_available", True):
            continue
        out.append(d)
    return out


def diversity_filter(
    dishes: list[dict],
    meal_log: list[dict],
    profile: dict,
    today: dt.date | None = None,
) -> tuple[list[dict], set[str]]:
    """基于 meal_log 的多样性过滤. 返回 (filtered_dishes, recently_eaten_restaurant_ids)."""
    today = today or dt.date.today()
    no_rest_days = profile["diversity"].get("no_same_restaurant_within_days", 7)
    no_ingr_days = profile["diversity"].get(
        "no_same_main_ingredient_within_days", 3
    )

    recent_rests: set[str] = set()
    recent_ingrs: set[str] = set()
    for log in meal_log:
        try:
            ts = dt.datetime.fromisoformat(log["timestamp"]).date()
        except Exception:
            continue
        delta = (today - ts).days
        if delta <= no_rest_days:
            recent_rests.add(log.get("restaurant_id", ""))
        if delta <= no_ingr_days:
            for x in log.get("dishes", []):
                ing = x.get("main_ingredient_type")
                if ing:
                    recent_ingrs.add(ing)

    out = []
    for d in dishes:
        if d.get("restaurant_id") in recent_rests:
            continue
        ing = d.get("nutrition_profile", {}).get("main_ingredient_type")
        # 蛋白类（红肉/白肉/海鲜/豆制品）才走 ingredient 多样性
        if ing in ("红肉", "白肉", "海鲜", "豆制品") and ing in recent_ingrs:
            continue
        out.append(d)
    return out, recent_rests


def is_vegetable_dish(d: dict) -> bool:
    """是否算蔬菜菜品 (vegetable_ratio_estimate ≥ 0.6 或 main_ingredient_type=纯素)."""
    np = d.get("nutrition_profile", {})
    if np.get("main_ingredient_type") == "纯素":
        return True
    return np.get("vegetable_ratio_estimate", 0) >= 0.6


def is_protein_dish(d: dict) -> bool:
    np = d.get("nutrition_profile", {})
    if np.get("main_ingredient_type") in ("红肉", "白肉", "海鲜", "蛋", "豆制品"):
        return True
    return np.get("protein_grams_estimate", 0) >= 15


def is_carb_dish(d: dict) -> bool:
    np = d.get("nutrition_profile", {})
    return np.get("main_ingredient_type") == "主食"


def is_complete_meal(d: dict) -> bool:
    return d.get("nutrition_profile", {}).get("is_complete_meal", False)


def combo_passes_plate_rule(combo_dishes: list[dict], profile: dict) -> bool:
    """弱约束三件套校验 (D-023)."""
    pr = profile["plate_rule"]
    has_veg = sum(1 for d in combo_dishes if is_vegetable_dish(d))
    if pr.get("must_have_vegetable", True):
        if has_veg < pr.get("min_vegetable_dishes", 1):
            return False
    total_protein = sum(
        d.get("nutrition_profile", {}).get("protein_grams_estimate", 0)
        for d in combo_dishes
    )
    if total_protein < pr.get("min_protein_g", 0):
        return False
    return True


def build_combos_for_restaurant(
    rest_dishes: list[dict],
    profile: dict,
    per_rest_max: int,
) -> list[list[dict]]:
    """单家餐厅内构建若干 combo (路线 A complete_meal + 路线 B 蛋白×蔬菜×主食)."""
    combos: list[list[dict]] = []

    # 路线 A: 完整套餐单菜（如盖饭 / 套餐），可选配 1 道蔬菜补强
    completes = [d for d in rest_dishes if is_complete_meal(d)]
    vegs = [d for d in rest_dishes if is_vegetable_dish(d)]
    proteins = [d for d in rest_dishes if is_protein_dish(d)]
    carbs = [d for d in rest_dishes if is_carb_dish(d)]

    for cm in completes[:5]:
        # 单 complete_meal
        if combo_passes_plate_rule([cm], profile):
            combos.append([cm])
        # complete_meal + 1 道蔬菜
        for v in vegs[:2]:
            if v["dish_id"] == cm["dish_id"]:
                continue
            c = [cm, v]
            if combo_passes_plate_rule(c, profile):
                combos.append(c)

    # 路线 B: 蛋白 × 蔬菜 ×（主食可选）
    for p in proteins[:5]:
        for v in vegs[:3]:
            if v["dish_id"] == p["dish_id"]:
                continue
            base = [p, v]
            if combo_passes_plate_rule(base, profile):
                combos.append(base)
            for c in carbs[:2]:
                if c["dish_id"] in (p["dish_id"], v["dish_id"]):
                    continue
                ext = [p, v, c]
                if combo_passes_plate_rule(ext, profile):
                    combos.append(ext)

    # 去重 (按 dish_id 集合)
    seen: set[frozenset] = set()
    uniq = []
    for c in combos:
        key = frozenset(d["dish_id"] for d in c)
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq[:per_rest_max]


def recall(
    profile: dict,
    restaurants: list[dict],
    dishes_tagged: list[dict],
    meal_log: list[dict] | None = None,
    today: dt.date | None = None,
) -> list[dict]:
    """主入口. 返回候选 combos: [{restaurant, dishes, meta}, ...].

    返回未排序的候选池, 由 score.py 排序.
    """
    meal_log = meal_log or []

    # 1. 多样性过滤先算被禁餐厅
    _, avoid_rests = diversity_filter([], meal_log, profile, today=today)

    # 2. 硬过滤 dishes
    dishes = hard_filter(dishes_tagged, profile, avoid_rests)

    # 3. 多样性过滤 dishes (主蛋白)
    dishes, _ = diversity_filter(dishes, meal_log, profile, today=today)

    # 4. 按 restaurant 分桶
    by_rest: dict[str, list[dict]] = defaultdict(list)
    for d in dishes:
        by_rest[d["restaurant_id"]].append(d)

    rest_idx = {r["id"]: r for r in restaurants}
    per_rest_max = profile.get("recall", {}).get("per_restaurant_max", 3)

    # 5. 每家餐厅生成 combos
    combos: list[dict] = []
    for rid, rest_dishes in by_rest.items():
        if rid not in rest_idx:
            continue
        rcombos = build_combos_for_restaurant(
            rest_dishes, profile, per_rest_max
        )
        for cd in rcombos:
            combos.append({
                "restaurant": rest_idx[rid],
                "dishes": cd,
            })
    return combos


if __name__ == "__main__":
    import sys
    root = Path(__file__).resolve().parent.parent
    profile = load_profile(root / "profile.yaml")
    zone = profile["basics"]["office_zone"]
    rests, tagged = load_zone_data(zone, root)
    log = load_meal_log(root)
    cs = recall(profile, rests, tagged, log)
    print(f"候选 combo 数: {len(cs)}")
    for c in cs[:5]:
        print(f"  {c['restaurant']['name']} | "
              f"{[d['canonical_name'] for d in c['dishes']]}")

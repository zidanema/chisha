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


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


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


def compute_extra_banned_restaurants(
    restaurants: list[dict],
    profile: dict,
) -> set[str]:
    """根据 profile 算出"非历史性"被 ban 的餐厅集合 (D-041).

    来源:
      1. delivery_constraints.hard_max_eta_min: ETA 超上限的餐厅
      2. preferences.avoid_restaurants: 餐厅名/品牌模糊匹配
    """
    banned: set[str] = set()
    dc = profile.get("delivery_constraints") or {}
    hard_eta = dc.get("hard_max_eta_min")
    avoid_names = [a for a in (profile.get("preferences") or {})
                   .get("avoid_restaurants", []) if a]
    for r in restaurants:
        eta = r.get("delivery_eta_min", -1)
        if hard_eta and eta and eta > 0 and eta > hard_eta:
            banned.add(r["id"])
            continue
        name = (r.get("name") or "") + " " + (r.get("brand") or "")
        if any(a in name for a in avoid_names):
            banned.add(r["id"])
    return banned


def combo_total_price(combo: dict) -> float:
    """combo 总价 (单菜 price=None 安全求和)."""
    return sum(dish_price(d) for d in combo.get("dishes", []))


def combo_price_filter(
    combos: list[dict],
    profile: dict,
    meal_type: str | None,
) -> list[dict]:
    """combo 总价过滤 (D-041): 超 price_range.hard_max_{lunch,dinner} 直接 ban."""
    pr = profile.get("price_range") or {}
    cap = None
    if meal_type == "lunch":
        cap = pr.get("hard_max_lunch")
    elif meal_type == "dinner":
        cap = pr.get("hard_max_dinner")
    if not cap:
        return combos
    return [c for c in combos if combo_total_price(c) <= cap]


def dish_price(d: dict) -> float:
    """安全读取菜价: price 为 None / 缺失 时返回 0."""
    p = d.get("price")
    return float(p) if p is not None else 0.0


def hard_filter(
    dishes: list[dict],
    profile: dict,
    avoid_restaurant_ids: set[str] | None = None,
    rest_ban_reasons: dict[str, str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """硬过滤 (DESIGN §5.6 召回-2 + D-041).

    Returns (kept, dropped). dropped 每项: {dish_id, name, restaurant_id, reason}.

    Args:
      avoid_restaurant_ids: 被 ban 的餐厅 id 集合 (向后兼容入口);
        每个 rid 默认 reason="餐厅被 ban".
      rest_ban_reasons: 优先级更高, 把 rid → 具体原因字符串. 调用方传入,
        让 trace 看清楚是 ETA/avoid_name/diversity/旧入口 哪种.

    其它逻辑:
      - 销量缺失 (=0) 视为"无信息"不卡; 显式 >0 且 < min_sales 才卡.
      - P1 字段黑名单 (D-041): main_ingredient / cooking_method / cuisine.
    """
    avoid_restaurant_ids = avoid_restaurant_ids or set()
    rest_ban_reasons = rest_ban_reasons or {}
    prefs = profile.get("preferences") or {}
    avoid_dish_names = [a for a in prefs.get("avoid_dishes", []) if a]
    avoid_ingr = set(prefs.get("avoid_main_ingredients", []) or [])
    avoid_methods = set(prefs.get("avoid_cooking_methods", []) or [])
    banned_cuisines = set(prefs.get("banned_cuisines", []) or [])
    # D-043: processed_meat / sweet_sauce 三档处理 — 这里是 L1 硬过滤档
    banned_processed_meat = bool(prefs.get("banned_processed_meat", False))
    banned_sweet_3 = bool(prefs.get("banned_sweet_sauce_level_3", False))
    spicy_max = prefs.get("spicy_tolerance", 3)
    hard_max_oil = profile["plate_rule"].get("hard_max_oil_level", 5)
    min_sales = profile.get("recall", {}).get("min_monthly_sales", 0)
    kept: list[dict] = []
    dropped: list[dict] = []
    for d in dishes:
        np = d.get("nutrition_profile") or {}
        name = d.get("canonical_name") or ""
        rid = d.get("restaurant_id")
        reason: str | None = None
        matched_avoid = next((a for a in avoid_dish_names if a in name), None)
        sales = d.get("monthly_sales", 0)
        if rid in rest_ban_reasons:
            reason = rest_ban_reasons[rid]
        elif rid in avoid_restaurant_ids:
            reason = "餐厅被 ban"
        elif matched_avoid:
            reason = f"命中 avoid_dishes: {matched_avoid}"
        elif np.get("spicy_level", 0) > spicy_max:
            reason = f"辣度 {np.get('spicy_level')} > 上限 {spicy_max}"
        elif np.get("oil_level", 0) > hard_max_oil:
            reason = f"油 {np.get('oil_level')} > hard_max_oil {hard_max_oil}"
        elif avoid_ingr and np.get("main_ingredient_type") in avoid_ingr:
            reason = (
                f"主蛋白在 avoid_main_ingredients: "
                f"{np.get('main_ingredient_type')}"
            )
        elif avoid_methods and np.get("cooking_method") in avoid_methods:
            reason = (
                f"烹饪方式在 avoid_cooking_methods: "
                f"{np.get('cooking_method')}"
            )
        elif banned_cuisines and d.get("cuisine") in banned_cuisines:
            reason = f"菜系在 banned_cuisines: {d.get('cuisine')}"
        elif banned_processed_meat and np.get("processed_meat_flag"):
            reason = "命中 banned_processed_meat (用户禁忌)"
        elif banned_sweet_3 and _safe_int(np.get("sweet_sauce_level"), 0) >= 3:
            reason = f"sweet_sauce_level={np.get('sweet_sauce_level')} 命中 banned_sweet_sauce_level_3"
        elif sales and sales > 0 and sales < min_sales:
            reason = f"月销 {sales} < {min_sales}"
        elif not (d.get("metadata") or {}).get("is_available", True):
            reason = "is_available=False"
        if reason:
            dropped.append({
                "dish_id": d.get("dish_id"),
                "name": name,
                "restaurant_id": rid,
                "reason": reason,
            })
        else:
            kept.append(d)
    return kept, dropped


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
    """单家餐厅内构建若干 combo.

    设计原则 (D-040):
      - combo 阶段只过营养合规 (弱约束三件套 plate_rule)
      - 数量上限 (几个蛋白/几个蔬菜/总菜数) 由 profile.recall.* 显式注入
      - 价格/距离等约束推迟到打分/排序阶段

    路线:
      A. 完整套餐 (complete_meal) 单菜 / +1 蔬菜
      B. 灵活组合: n_p 蛋白 × n_v 蔬菜 × n_c 主食
         其中 n_p ∈ [1, max_protein], n_v ∈ [1, max_veg], n_c ∈ [0, max_carb]
         且 n_p + n_v + n_c ∈ [1, max_dishes]
    """
    from itertools import combinations as _comb

    rcfg = profile.get("recall", {}) or {}
    max_p = rcfg.get("max_protein_per_combo", 2)
    max_v = rcfg.get("max_veg_per_combo", 2)
    max_c = rcfg.get("max_carb_per_combo", 1)
    max_n = rcfg.get("max_dishes_per_combo", 4)

    completes = [d for d in rest_dishes if is_complete_meal(d)]
    vegs = [d for d in rest_dishes if is_vegetable_dish(d)]
    proteins = [d for d in rest_dishes if is_protein_dish(d)]
    carbs = [d for d in rest_dishes if is_carb_dish(d)]

    # 各池按月销降序, [:N] 取热门的 (避免组合爆炸)
    proteins = sorted(proteins, key=lambda x: -x.get("monthly_sales", 0))[:6]
    vegs = sorted(vegs, key=lambda x: -x.get("monthly_sales", 0))[:5]
    carbs = sorted(carbs, key=lambda x: -x.get("monthly_sales", 0))[:3]
    completes = sorted(completes, key=lambda x: -x.get("monthly_sales", 0))[:5]

    combos: list[list[dict]] = []
    if max_n <= 0:
        return combos

    # 路线 A: 完整套餐 (盖饭/套餐)，可选 +1 蔬菜
    for cm in completes:
        if 1 <= max_n and combo_passes_plate_rule([cm], profile):
            combos.append([cm])
        if max_n < 2:
            continue
        for v in vegs[:3]:
            if v["dish_id"] == cm["dish_id"]:
                continue
            c = [cm, v]
            if combo_passes_plate_rule(c, profile):
                combos.append(c)

    # 路线 B: 灵活蛋白 × 蔬菜 × 主食
    for n_p in range(1, max_p + 1):
        if n_p > len(proteins):
            break
        for n_v in range(1, max_v + 1):
            if n_v > len(vegs):
                break
            for n_c in range(0, max_c + 1):
                if n_c > len(carbs):
                    break
                if n_p + n_v + n_c > max_n:
                    continue
                for p_set in _comb(proteins, n_p):
                    p_ids = {d["dish_id"] for d in p_set}
                    for v_set in _comb(vegs, n_v):
                        v_ids = {d["dish_id"] for d in v_set}
                        if p_ids & v_ids:
                            continue
                        if n_c == 0:
                            dishes = list(p_set) + list(v_set)
                            if combo_passes_plate_rule(dishes, profile):
                                combos.append(dishes)
                            continue
                        for c_set in _comb(carbs, n_c):
                            c_ids = {d["dish_id"] for d in c_set}
                            if c_ids & (p_ids | v_ids):
                                continue
                            dishes = list(p_set) + list(v_set) + list(c_set)
                            if combo_passes_plate_rule(dishes, profile):
                                combos.append(dishes)

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
    meal_type: str | None = None,
) -> list[dict]:
    """主入口. 返回候选 combos: [{restaurant, dishes, meta}, ...].

    meal_type 传入则启用 combo 总价硬过滤 (D-041).
    """
    meal_log = meal_log or []

    # 1. 多样性过滤先算"近期已吃"被禁餐厅
    _, diversity_avoid = diversity_filter([], meal_log, profile, today=today)
    # 1b. P0 硬约束: ETA + 餐厅黑名单
    extra_banned = compute_extra_banned_restaurants(restaurants, profile)
    avoid_rests = diversity_avoid | extra_banned

    # 2. 硬过滤 dishes (含 P1 三个黑名单)
    dishes, _ = hard_filter(dishes_tagged, profile, avoid_rests)

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

    # 6. combo 总价硬过滤 (D-041)
    combos = combo_price_filter(combos, profile, meal_type)
    return combos


if __name__ == "__main__":
    import sys
    root = Path(__file__).resolve().parent.parent
    profile = load_profile(root / "profile.yaml")
    meal = sys.argv[1] if len(sys.argv) > 1 else "lunch"
    zones = profile.get("basics", {}).get("zones") or {}
    zone = zones.get(meal) or profile["basics"]["office_zone"]
    rests, tagged = load_zone_data(zone, root)
    log = load_meal_log(root)
    cs = recall(profile, rests, tagged, log)
    print(f"[{meal} @ {zone}] 候选 combo 数: {len(cs)}")
    for c in cs[:5]:
        print(f"  {c['restaurant']['name']} | "
              f"{[d['canonical_name'] for d in c['dishes']]}")

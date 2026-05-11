"""打分: combo → 分数.

V1: 6 维 (vegetable_floor / protein_floor / low_oil / popularity /
       cuisine_preference / variety_bonus).
V2 ([D-033](docs/DECISIONS.md#d-033)): 加 ~10 个维度
       - 5 新字段 (carb_quality / processed_meat / sweet_sauce / soup_broth / dish_role)
       - 履约 (distance / eta / price)
       - taste_match (taste_description 进决策, 由 LLM 反馈解析员提示)
       - context_boost (D-034 ContextSnapshot 软调权)
新维度向下兼容: combo dish 缺字段时返回 0; profile 没配权重时用 V2_DEFAULT_WEIGHTS.
V1 不传 context / taste_hints, 行为不变.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from chisha.context import ContextSnapshot


# V2 默认权重 (profile.scoring_weights 缺字段时用)
V2_DEFAULT_WEIGHTS: dict[str, float] = {
    # V1 维度
    "vegetable_floor_pass": 1.0,
    "protein_floor_pass": 1.0,
    "low_oil": 0.8,
    "popularity": 0.4,
    "cuisine_preference": 0.5,
    "variety_bonus": 0.3,
    # V2 新维度
    "carb_quality": 0.6,
    "processed_meat": 1.0,    # 取负后扣分
    "sweet_sauce": 0.7,        # 取负后扣分
    "wetness": 0.5,            # 命中"想喝汤"等汤水偏好
    "dish_role_match": 0.4,
    "distance": 0.3,           # 取负后扣分
    "eta": 0.4,                # 取负后扣分
    "price": 0.5,              # 取负后扣分
    "taste_match": 0.6,
    "context_boost": 0.4,
}


# 5 个新字段的字面量 (与 chisha/schemas.py / D-032 v3 prompt 输出对齐)
GRAIN_GOOD = {"糙米杂粮", "全麦面", "粗粮", "粥"}
GRAIN_BAD = {"白米", "精制面"}
DISH_ROLE_MAIN = "主菜"
DISH_ROLE_VEG = "配菜"
DISH_ROLE_SOUP = "汤"
DISH_ROLE_CARB = "主食"
DISH_ROLE_COMBO = "套餐"   # 套餐通常自带主菜+主食 (按完整餐处理)


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


def carb_quality_score(combo: dict) -> float:
    """combo 主食质量: 全谷物 +1, 精制 -1, 无主食 0. 按 dish 求和裁到 [-1, 1]."""
    s = 0.0
    for d in combo["dishes"]:
        np_ = d.get("nutrition_profile", {})
        if np_.get("dish_role") != DISH_ROLE_CARB:
            continue
        gt = np_.get("grain_type") or ""
        if gt in GRAIN_GOOD:
            s += 1.0
        elif gt in GRAIN_BAD:
            s -= 1.0
    return max(-1.0, min(1.0, s))


def processed_meat_penalty(combo: dict) -> float:
    """combo 内任一主菜含 processed_meat_flag → 1.0, 配菜含 → 0.5, 否则 0."""
    p = 0.0
    for d in combo["dishes"]:
        np_ = d.get("nutrition_profile", {})
        if not np_.get("processed_meat_flag"):
            continue
        if np_.get("dish_role") == DISH_ROLE_MAIN:
            p += 1.0
        else:
            p += 0.5
    return min(1.5, p)


def sweet_sauce_penalty(combo: dict) -> float:
    """sweet_sauce_level (int 0-3): >=3 全扣 1.0, ==2 扣 0.5, <=1 不扣.

    v3 schema 用 int (D-032). 旧字符串 token 兼容仅给 fallback 不报错.
    """
    p = 0.0
    for d in combo["dishes"]:
        np_ = d.get("nutrition_profile", {})
        lvl = np_.get("sweet_sauce_level")
        if lvl is None:
            continue
        # v3 主路径: int 0-3
        try:
            lvl_int = int(lvl)
        except (TypeError, ValueError):
            continue
        if lvl_int >= 3:
            p += 1.0
        elif lvl_int == 2:
            p += 0.5
    return min(1.5, p)


def wetness_bonus(combo: dict) -> float:
    """wetness (int 1-3): combo 含 wetness>=3 → 1.0; 仅含 wetness=2 → 0.5; 否则 0.

    wetness=3 = 可喝汤底 (粿条汤/酸菜鱼); =2 = 卤水浸泡 (关东煮); =1 = 干 (干煸/凉拌).
    """
    best = 0.0
    for d in combo["dishes"]:
        np_ = d.get("nutrition_profile", {})
        w = np_.get("wetness")
        if w is None:
            continue
        try:
            w_int = int(w)
        except (TypeError, ValueError):
            continue
        if w_int >= 3:
            return 1.0
        if w_int == 2 and best < 0.5:
            best = 0.5
    return best


# 兼容老命名的别名 (旧测试或外部调用方可能用)
soup_or_broth_bonus = wetness_bonus


def dish_role_match_bonus(combo: dict) -> float:
    """combo 结构合理度.

    一道菜 dish_role=套餐 → 视为主菜+主食组合 (返回 0.5 起步; 含配菜 → 1.0).
    其他: 主菜+配菜+主食 = 1.0; 主菜+配菜 / 主菜+主食 = 0.5; 单菜 = 0.
    缺 dish_role 字段时全部按 主菜 处理.
    """
    roles: set[str] = set()
    for d in combo["dishes"]:
        np_ = d.get("nutrition_profile", {})
        roles.add(np_.get("dish_role") or DISH_ROLE_MAIN)
    # 套餐展开为 主菜+主食 等价覆盖
    if DISH_ROLE_COMBO in roles:
        roles.update({DISH_ROLE_MAIN, DISH_ROLE_CARB})
    coverage = len({DISH_ROLE_MAIN, DISH_ROLE_VEG, DISH_ROLE_CARB} & roles)
    if coverage >= 3:
        return 1.0
    if coverage == 2:
        return 0.5
    return 0.0


def distance_penalty(combo: dict, profile: dict) -> float:
    """餐厅距离 > prefer_distance_m 时线性扣分 (0-1).

    profile.delivery_constraints.prefer_distance_m 缺失则不扣 (返回 0).
    """
    prefer = (profile.get("delivery_constraints") or {}).get("prefer_distance_m")
    if not prefer:
        return 0.0
    d = (combo.get("restaurant") or {}).get("distance_m", -1)
    if d <= 0 or d <= prefer:
        return 0.0
    return min(1.0, (d - prefer) / max(1, prefer))


def eta_penalty(combo: dict, profile: dict) -> float:
    """餐厅 delivery_eta_min > max_delivery_eta_min 时线性扣分 (0-1)."""
    cap = (profile.get("delivery_constraints") or {}).get("max_delivery_eta_min")
    if not cap:
        return 0.0
    eta = (combo.get("restaurant") or {}).get("delivery_eta_min", -1)
    if eta <= 0 or eta <= cap:
        return 0.0
    return min(1.0, (eta - cap) / max(1, cap))


def price_penalty(combo: dict, profile: dict, meal_type: str | None = None) -> float:
    """combo 总价超 price_range.{lunch,dinner}_max 线性扣分 (0-1)."""
    pr = profile.get("price_range") or {}
    cap = None
    if meal_type == "lunch":
        cap = pr.get("lunch_max")
    elif meal_type == "dinner":
        cap = pr.get("dinner_max")
    else:
        cap = pr.get("lunch_max") or pr.get("dinner_max")
    if not cap:
        return 0.0
    total = sum(d.get("price", 0) for d in combo["dishes"])
    if total <= cap:
        return 0.0
    return min(1.0, (total - cap) / max(1, cap))


def taste_match_bonus(combo: dict, taste_hints: dict | None) -> float:
    """taste_description 进决策的占位接口.

    taste_hints 由 LLM 反馈解析员产出 (V2.x), 形如:
        {"boost": ["soup_or_broth", "low_oil"],
         "penalty": ["sweet_sauce", "processed_meat"]}
    返回正数 = boost, 负数 = penalty, 范围 [-1, 1].
    无 hints 时返回 0 (V1 不变).

    本轮先做接口占位, 实际 hint 派发实现等 LLM 反馈解析员上线.
    """
    if not taste_hints:
        return 0.0
    boost = set(taste_hints.get("boost") or [])
    penalty = set(taste_hints.get("penalty") or [])
    s = 0.0
    # 接受 wetness / soup_or_broth 两个别名 (旧调用方兼容)
    if ({"wetness", "soup_or_broth"} & boost) and wetness_bonus(combo) > 0:
        s += 0.5
    if "low_oil" in boost:
        oils = [d.get("nutrition_profile", {}).get("oil_level", 3)
                for d in combo["dishes"]]
        avg = sum(oils) / max(1, len(oils))
        if avg <= 2:
            s += 0.5
    if "sweet_sauce" in penalty and sweet_sauce_penalty(combo) > 0:
        s -= 0.5
    if "processed_meat" in penalty and processed_meat_penalty(combo) > 0:
        s -= 0.5
    # V2 P1 扩展: refine 反馈映射出的更多维度
    if "carb_heavy" in penalty:
        # combo 含 dish_role=主食 的菜数 >= 1 时扣
        carb_n = sum(
            1 for d in combo["dishes"]
            if (d.get("nutrition_profile") or {}).get("dish_role") == DISH_ROLE_CARB
        )
        if carb_n >= 1:
            s -= 0.5
    if "spicy" in penalty:
        spicies = [d.get("nutrition_profile", {}).get("spicy_level", 0)
                    for d in combo["dishes"]]
        if max(spicies, default=0) >= 2:
            s -= 0.5
    return max(-1.0, min(1.0, s))


def context_boost(combo: dict, context: "ContextSnapshot | None") -> float:
    """ContextSnapshot 软调权 (D-034).

    daily_mood 命中: want_soup → +0.5 if combo 有汤水
                     want_light → +0.3 if 平均 oil <= 2; -0.3 if oil >= 4
                     low_carb → -0.3 if combo 含主食 dish
                     want_clean → -0.4 if 含 processed_meat
                     want_indulgent → -0.2 if 油很低 (太清淡不解馋)
    无 context 或 daily_mood=None → 0.
    """
    if context is None or context.daily_mood is None:
        return 0.0
    mood = context.daily_mood
    s = 0.0
    has_wet = wetness_bonus(combo) > 0
    oils = [d.get("nutrition_profile", {}).get("oil_level", 3)
            for d in combo["dishes"]]
    avg_oil = sum(oils) / max(1, len(oils))
    has_carb_dish = any(
        (d.get("nutrition_profile") or {}).get("dish_role") == DISH_ROLE_CARB
        for d in combo["dishes"]
    )
    has_processed = processed_meat_penalty(combo) > 0
    if mood == "want_soup" and has_wet:
        s += 0.5
    elif mood == "want_light":
        s += 0.3 if avg_oil <= 2 else (-0.3 if avg_oil >= 4 else 0.0)
    elif mood == "low_carb" and has_carb_dish:
        s -= 0.3
    elif mood == "want_clean" and has_processed:
        s -= 0.4
    elif mood == "want_indulgent" and avg_oil <= 2:
        s -= 0.2
    return max(-1.0, min(1.0, s))


def score_combo(
    combo: dict,
    profile: dict,
    meal_log: list[dict] | None = None,
    today: dt.date | None = None,
    context: "ContextSnapshot | None" = None,
    taste_hints: dict | None = None,
    meal_type: str | None = None,
) -> tuple[float, dict[str, float]]:
    """计算 combo 综合分. 返回 (score, breakdown).

    V1 行为: 不传 context/taste_hints/meal_type 时, 仍只用 6 维 + V2 维度
            (V2 维度数据缺时返回 0, 不影响结果).
    V2 行为: 传 context + taste_hints + meal_type 时, 全 ~12 维生效.
    """
    w = profile.get("scoring_weights") or {}

    def _w(key: str) -> float:
        return float(w.get(key, V2_DEFAULT_WEIGHTS.get(key, 0.0)))

    parts = {
        # V1 维度
        "vegetable_floor_pass": vegetable_floor_score(combo, profile)
            * _w("vegetable_floor_pass"),
        "protein_floor_pass": protein_floor_score(combo, profile)
            * _w("protein_floor_pass"),
        "low_oil": low_oil_score(combo, profile) * _w("low_oil"),
        "popularity": popularity_score(combo) * _w("popularity"),
        "cuisine_preference": cuisine_preference_score(combo, profile)
            * _w("cuisine_preference"),
        "variety_bonus": variety_bonus_score(combo, meal_log or [], today)
            * _w("variety_bonus"),
        # V2 营养字段
        "carb_quality": carb_quality_score(combo) * _w("carb_quality"),
        "processed_meat": -processed_meat_penalty(combo) * _w("processed_meat"),
        "sweet_sauce": -sweet_sauce_penalty(combo) * _w("sweet_sauce"),
        "wetness": wetness_bonus(combo) * _w("wetness"),
        "dish_role_match": dish_role_match_bonus(combo) * _w("dish_role_match"),
        # V2 履约
        "distance": -distance_penalty(combo, profile) * _w("distance"),
        "eta": -eta_penalty(combo, profile) * _w("eta"),
        "price": -price_penalty(combo, profile, meal_type) * _w("price"),
        # V2 偏好/情境
        "taste_match": taste_match_bonus(combo, taste_hints) * _w("taste_match"),
        "context_boost": context_boost(combo, context) * _w("context_boost"),
    }
    return sum(parts.values()), parts


def rank_combos(
    combos: list[dict],
    profile: dict,
    meal_log: list[dict] | None = None,
    today: dt.date | None = None,
    context: "ContextSnapshot | None" = None,
    taste_hints: dict | None = None,
    meal_type: str | None = None,
) -> list[dict]:
    """对 combos 打分排序, 返回带 score/breakdown 的列表 (降序)."""
    scored = []
    for c in combos:
        s, br = score_combo(c, profile, meal_log, today,
                            context=context, taste_hints=taste_hints,
                            meal_type=meal_type)
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

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


# V2 默认权重 (profile.scoring_weights 缺字段时用).
# D-043: 死分维度权重砍 0 (vegetable/protein floor 已被 L1 强制, distance 没数据).
#         taste_match 从 0.6 调到 0.4 (Codex 共识: 先看实测 std 再升权).
#         context_boost 从 0.4 调到 0.25 (低置信弱先验).
V2_DEFAULT_WEIGHTS: dict[str, float] = {
    # ── 死分 (D-043 砍 0, 保留 key 让 profile 兼容) ──
    "vegetable_floor_pass": 0.0,     # L1 已强制
    "protein_floor_pass": 0.0,       # L1 已强制
    "distance": 0.0,                 # 外卖只看 ETA, 没数据
    # ── 活权重 ──
    "low_oil": 0.5,
    "popularity": 0.4,
    "cuisine_preference": 0.3,
    "variety_bonus": 0.5,            # 改活成连续函数后区分度提升
    "carb_quality": 0.6,
    "processed_meat": 1.0,           # 取负
    "sweet_sauce": 0.7,              # 取负
    "wetness": 0.5,
    "dish_role_match": 0.3,
    "eta": 0.4,                      # 取负
    "price": 0.5,                    # 取负
    "taste_match": 0.4,              # D-043: 启用兜底 hints 后变活, 起始 0.4
    "context_boost": 0.25,           # D-043: 默认 mood 低置信
}


# 5 个新字段的字面量 (与 chisha/schemas.py / D-032 v3 prompt 输出对齐)
# 注: "粥" 本质是精制白米煮的, 营养上不属于全谷物;
# 它的"清爽/汤水"价值已经由 wetness_bonus 维度覆盖, 不在 carb_quality 重复加分.
GRAIN_GOOD = {"糙米杂粮", "全麦面", "粗粮"}
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


def _combo_avg_sales(combo: dict) -> float:
    sales = [d.get("monthly_sales", 0) or 0 for d in combo["dishes"]]
    return sum(sales) / max(1, len(sales))


def popularity_score(combo: dict) -> float:
    """D-043: rank-based percentile (combo._popularity_rank 由 rank_combos 预填).

    Note: percentile 是在 attach_popularity_ranks 被调用时所有传入 combos 内排的
    (即一次 rank_combos 调用看到的全部 candidates), 不是"top30 内", 见 attach_popularity_ranks.
    若没预填 rank → fallback 用 log10 归一 (兼容直接调 score_combo 的单元测试).
    Returns: 0~1 percentile, combo 销量在全候选中越靠前分越高.
    """
    pct = combo.get("_popularity_rank")
    if pct is not None:
        try:
            return max(0.0, min(1.0, float(pct)))
        except (TypeError, ValueError):
            pass
    # fallback: log10 归一
    avg = _combo_avg_sales(combo)
    if avg <= 0:
        return 0.0
    return min(1.0, math.log10(1 + avg) / 3.0)


def attach_popularity_ranks(combos: list[dict]) -> None:
    """D-043: 给 combos 标 _popularity_rank (top30 内 percentile, 0~1).

    rank-based: 销量越高的 combo percentile 越接近 1.0; 同销量给同 rank.
    就地修改 combos, 不返回. rank_combos 入口调用.
    """
    if not combos:
        return
    pairs = [(i, _combo_avg_sales(c)) for i, c in enumerate(combos)]
    # 按销量降序; 销量相同保持原 index 顺序 (稳定排序)
    pairs.sort(key=lambda x: -x[1])
    n = len(pairs)
    # 同销量并列同 rank, percentile = 1 - rank/n
    last_sales: float | None = None
    last_pct: float = 1.0
    for new_rank, (orig_i, sales) in enumerate(pairs):
        if sales != last_sales:
            # 新 rank 段
            last_pct = 1.0 - new_rank / max(1, n)
            last_sales = sales
        combos[orig_i]["_popularity_rank"] = round(last_pct, 4)


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
    days: int = 7,
) -> float:
    """D-043: combo 的主蛋白与最近吃过的距离, 连续函数 (取代 D-033 的 0/0.5 二值).

    规则:
      - combo 含 N 种 main_ingredient_type, 每种找"上次吃这种距今天数"
      - 距离 d 天 → 单种新鲜度 = min(1, d/days)
      - 从未吃过 → 1.0
      - combo 取最大新鲜度 (有一种新鲜就够给分)
    Args:
      days: 完全新鲜的天数门槛 (默认 7). 距离 ≥ days 给满分 1.0.
    """
    today = today or dt.date.today()
    # 收集每个 main_ingredient_type 最近一次出现日期
    last_seen: dict[str, dt.date] = {}
    for log in meal_log or []:
        try:
            ts = dt.datetime.fromisoformat(log["timestamp"]).date()
        except Exception:
            continue
        if (today - ts).days < 0:
            continue
        for x in log.get("dishes", []):
            ing = x.get("main_ingredient_type")
            if not ing:
                continue
            prev = last_seen.get(ing)
            if prev is None or ts > prev:
                last_seen[ing] = ts
    combo_ingrs = {
        d.get("nutrition_profile", {}).get("main_ingredient_type", "")
        for d in combo["dishes"]
        if d.get("nutrition_profile", {}).get("main_ingredient_type")
    }
    if not combo_ingrs:
        return 0.0
    best = 0.0
    for ing in combo_ingrs:
        last = last_seen.get(ing)
        if last is None:
            # 从未吃过 → 最大新鲜度
            best = 1.0
            break
        gap = max(0, (today - last).days)
        freshness = min(1.0, gap / max(1, days))
        if freshness > best:
            best = freshness
    return best


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
    """餐厅 delivery_eta_min > prefer_max_eta_min 时线性扣分 (0-1)."""
    dc = profile.get("delivery_constraints") or {}
    # 新名 prefer_max_eta_min; 老名 max_delivery_eta_min (D-041 重命名前的兼容入口)
    cap = dc.get("prefer_max_eta_min") or dc.get("max_delivery_eta_min")
    if not cap:
        return 0.0
    eta = (combo.get("restaurant") or {}).get("delivery_eta_min", -1)
    if eta <= 0 or eta <= cap:
        return 0.0
    return min(1.0, (eta - cap) / max(1, cap))


def price_penalty(combo: dict, profile: dict, meal_type: str | None = None) -> float:
    """combo 总价超 price_range.prefer_max_{lunch,dinner} 时线性扣分 (0-1)."""
    from chisha.recall import dish_price
    pr = profile.get("price_range") or {}
    cap = None
    if meal_type == "lunch":
        cap = pr.get("prefer_max_lunch") or pr.get("lunch_max")
    elif meal_type == "dinner":
        cap = pr.get("prefer_max_dinner") or pr.get("dinner_max")
    else:
        cap = (pr.get("prefer_max_lunch") or pr.get("lunch_max")
               or pr.get("prefer_max_dinner") or pr.get("dinner_max"))
    if not cap:
        return 0.0
    total = sum(dish_price(d) for d in combo["dishes"])
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


def context_boost(combo: dict, context: "ContextSnapshot | None",
                   today: dt.date | None = None) -> float:
    """ContextSnapshot 软调权 (D-071 后只剩 want_soup 一条规则).

    D-071 推翻 D-034/D-043: 砍 want_light / low_carb / want_clean / want_indulgent
    四条 mood 规则 (方法论 baseline 已固化, 不该 session 级再调; 详见 D-070 三层信号模型);
    砍季节默认 mood 兜底 (`infer_default_mood`).

    保留 want_soup 一条: combo 含汤水 → +0.5 (汤羹供给不足 zone 下 L3 推不稳,
    用结构化 wetness 字段做 L2 确定性加分通道).

    注: 此函数刻意保留为独立维度而非合并进 wetness_bonus, 作为未来 L0
    methodology spec (D-072) soft_rules 的接口位 — 不要再加新 mood 分支.
    """
    mood: str | None = None
    if context is not None and context.daily_mood is not None:
        mood = context.daily_mood
    if mood != "want_soup":
        return 0.0
    if wetness_bonus(combo) > 0:
        return 0.5
    return 0.0


# ─────────────────────── D-043: 兜底信号 (D-071 季节兜底已废) ───────────────────────
# 原则: 缺数据 ≠ 无信号. taste_match 没 hints 时从 profile 静态抽.
#
# D-071: D-043 季节默认 mood 兜底 (`infer_default_mood`) 已废 — 方法论 baseline
# 已固化, 不需季节猜测 (详见 D-070 定位收敛). context_boost 没 mood 时直接返 0.

# taste_description 中常见关键词 → boost/penalty token 映射
_TASTE_KW_TO_BOOST = {
    "清淡": "low_oil", "少油": "low_oil", "不油": "low_oil",
    "汤": "wetness", "汤水": "wetness", "想喝": "wetness",
    "粗粮": "carb_quality", "糙米": "carb_quality", "全谷": "carb_quality",
}
_TASTE_KW_TO_PENALTY = {
    "甜": "sweet_sauce", "糖": "sweet_sauce", "酱浓": "sweet_sauce",
    "加工肉": "processed_meat", "火腿": "processed_meat", "腊": "processed_meat",
    "辣": "spicy", "不能辣": "spicy",
    "重碳水": "carb_heavy", "少主食": "carb_heavy",
}


def extract_static_taste_hints(profile: dict | None) -> dict | None:
    """D-043: 从 profile.taste_description / preferences 抽兜底 taste_hints.

    优先级:
      1. profile.taste_boost_tags / taste_penalty_tags (用户/离线工具固化)
      2. profile.taste_description 关键词扫描 (规则词典)
    返回 None 表示无兜底, score_combo 走原 0 路径.
    """
    if not profile:
        return None
    explicit_boost = list(profile.get("taste_boost_tags") or [])
    explicit_penalty = list(profile.get("taste_penalty_tags") or [])
    if explicit_boost or explicit_penalty:
        return {"boost": explicit_boost, "penalty": explicit_penalty}
    desc = profile.get("taste_description") or ""
    if not desc:
        return None
    boost: set[str] = set()
    penalty: set[str] = set()
    for kw, tok in _TASTE_KW_TO_BOOST.items():
        if kw in desc:
            boost.add(tok)
    for kw, tok in _TASTE_KW_TO_PENALTY.items():
        if kw in desc:
            penalty.add(tok)
    if not boost and not penalty:
        return None
    return {"boost": sorted(boost), "penalty": sorted(penalty)}


# ─────────────────────── D-043: 不可补偿惩罚 ───────────────────────

def apply_unforgivable_penalty(
    score: float,
    combo: dict,
    profile: dict | None = None,
) -> float:
    """D-043: 极强 penalty 不参与加权和补偿, 直接打折.

    触发条件 (任一):
      - combo 同时含 sweet_sauce_level≥3 dish 与 processed_meat_flag dish
      - combo 含 2 个或更多 processed_meat_flag dish (一餐多加工肉)
      - sweet_sauce_level=3 且 wetness=3 (重甜重浓汤, 通常意味浓汤勾芡)
    可在 profile.scoring.unforgivable.discount 配比例 (默认 0.5).
    """
    dishes = combo.get("dishes") or []
    sweet_hits = sum(
        1 for d in dishes
        if _safe_int((d.get("nutrition_profile") or {}).get("sweet_sauce_level"), 0) >= 3
    )
    proc_hits = sum(
        1 for d in dishes
        if (d.get("nutrition_profile") or {}).get("processed_meat_flag")
    )
    wet_hits = sum(
        1 for d in dishes
        if _safe_int((d.get("nutrition_profile") or {}).get("wetness"), 0) >= 3
    )
    triggered = (
        (sweet_hits >= 1 and proc_hits >= 1)
        or proc_hits >= 2
        or (sweet_hits >= 1 and wet_hits >= 1)
    )
    if not triggered:
        return score
    discount = 0.5
    try:
        discount = float(((profile or {}).get("scoring") or {}).get("unforgivable_discount", 0.5))
    except (TypeError, ValueError):
        pass
    # Codex review 修复: 单纯 score * discount 对负分 score 反向"奖励"
    # (-1.0 * 0.5 = -0.5 比原值大). 取 min(乘性折扣, 减常数) 保证任何 score
    # 触发后都严格更小, 实现"一票否决"语义.
    return min(score * discount, score - 1.0)


def _safe_int(v, default: int) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


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
        "context_boost": context_boost(combo, context, today=today) * _w("context_boost"),
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
    root=None,
) -> list[dict]:
    """对 combos 打分排序, 返回带 score/breakdown 的列表 (降序).

    D-043: 入口先 attach_popularity_ranks (rank-based popularity),
    把 D-043 default mood/taste hints 兜底信号注入 context/hints.
    Args:
      root: 项目根 (透传给 long_term_prefs.load_runtime_hints,
        让 refine 写入和 rank_combos 读取共用同一份 feedback_history.jsonl).
        Codex 二审修复: 之前 refine 写 root, rank_combos 读默认根, 闭环不合拢.
    """
    # D-043: rank-based popularity, 就地修改 combos (加 _popularity_rank)
    attach_popularity_ranks(combos)
    # D-043: taste_hints 始终合并 static (profile) + runtime (反馈闭环) + 显式传入
    # Codex review 修复: 之前显式 taste_hints 时直接跳过 static/runtime, refine
    # 二轮调用就丢了长期偏好兜底, 现在三源合并 (并集).
    from chisha.long_term_prefs import load_runtime_hints, merge_hints
    static_hints = extract_static_taste_hints(profile)
    try:
        runtime_hints = load_runtime_hints(today=today, root=root)
    except Exception:
        runtime_hints = None
    effective_hints = merge_hints(static_hints, runtime_hints, taste_hints)
    scored = []
    for c in combos:
        s, br = score_combo(c, profile, meal_log, today,
                            context=context, taste_hints=effective_hints,
                            meal_type=meal_type)
        s = apply_unforgivable_penalty(s, c, profile)
        scored.append({**c, "score": s, "score_breakdown": br})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def _safe_cap(raw: object, default: int) -> int:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return v if v >= 0 else default


def resolve_cap_k(profile: dict | None, default: int = 3) -> int:
    """统一 L2 per-restaurant cap K 读取入口 (D-042).

    优先 profile.recall.per_restaurant_top_k, 缺失/非法回退 default.
    API/refine/debug 三个路径都走这条, 避免行为漂移.
    """
    rcfg = (profile or {}).get("recall") or {}
    return _safe_cap(rcfg.get("per_restaurant_top_k", default), default)


def resolve_caps(profile: dict | None) -> dict[str, int]:
    """L2 cap 配置统一入口 (D-043 三层 + D-045 brand 层).

    Returns:
        {"restaurant": int, "brand": int, "cuisine": int, "food_form": int}

    brand 层防连锁分店扎榜: Super Model 有 r_222/r_219/r_220 三家分店,
    restaurant 层各 cap=3 时品牌总量上限 9, 体感被同品牌刷屏. brand 层
    取 profile.recall.per_brand_top_k (默认 2), 比 restaurant 紧一档.
    """
    rcfg = (profile or {}).get("recall") or {}
    return {
        "restaurant": _safe_cap(rcfg.get("per_restaurant_top_k", 3), 3),
        "brand": _safe_cap(rcfg.get("per_brand_top_k", 2), 2),
        "cuisine": _safe_cap(rcfg.get("per_cuisine_top_k", 6), 6),
        "food_form": _safe_cap(rcfg.get("per_food_form_top_k", 8), 8),
    }


def apply_caps(
    ranked: list[dict],
    profile: dict | None,
) -> list[dict]:
    """D-043 三层 cap + D-045 brand 层 + D-049 head-only:
    restaurant + brand + cuisine + food_form 同时满足.

    Codex review 修复: 之前是串联调用三个单层 cap, 后层会把前层 demote 的 tail
    重新纳入 head, 导致约束失效. 现在一次遍历同时维护四个计数器, head 必须
    同时满足全部四层约束.

    D-049: 仅返回 head, 不再拼接 tail. 之前 `return head + tail` 让 L3
    输入 topK 切到 tail 段, 造成同品牌候选刷屏 (实测 Super Model top60 占 8 条).
    现在 brand cap 真正生效, L3 仅在同品牌 ≤2 个变体内做菜品组合择优.

    cap=0 表示该层不做约束. brand 缺失回退到 rid (单店即单品牌).
    """
    caps = resolve_caps(profile)
    cap_r = caps["restaurant"]
    cap_b = caps["brand"]
    cap_c = caps["cuisine"]
    cap_f = caps["food_form"]
    head: list[dict] = []
    cnt_r: dict[str, int] = {}
    cnt_b: dict[str, int] = {}
    cnt_c: dict[str, int] = {}
    cnt_f: dict[str, int] = {}
    for c in ranked:
        rest = c.get("restaurant") or {}
        rid = rest.get("id") or rest.get("name")
        brand = rest.get("brand") or rid
        dishes = c.get("dishes") or []
        cui = dishes[0].get("cuisine") if dishes else None
        form = combo_food_form(c)
        # 任一层 cap 已满 → 丢弃 (D-049: 不再保留 tail)
        if cap_r > 0 and rid and cnt_r.get(rid, 0) >= cap_r:
            continue
        if cap_b > 0 and brand and cnt_b.get(brand, 0) >= cap_b:
            continue
        if cap_c > 0 and cui and cnt_c.get(cui, 0) >= cap_c:
            continue
        if cap_f > 0 and form and cnt_f.get(form, 0) >= cap_f:
            continue
        head.append(c)
        if rid:
            cnt_r[rid] = cnt_r.get(rid, 0) + 1
        if brand:
            cnt_b[brand] = cnt_b.get(brand, 0) + 1
        if cui:
            cnt_c[cui] = cnt_c.get(cui, 0) + 1
        if form:
            cnt_f[form] = cnt_f.get(form, 0) + 1
    return head


# ─────────────────────── D-043: food_form 规则推断 ───────────────────────
#
# food_form (形态) 与 cuisine (菜系) / main_ingredient_type (主蛋白) 正交,
# 描述"吃的形状"维度. "潮汕粥/砂锅粥/艇仔粥"在 main_ingredient 上差异大,
# 但 food_form 都是"粥"; 多样性约束在 cuisine 上看不出, 必须看 food_form.
#
# 规则推断: 不重打标, 从 canonical_name + cooking_method 命中关键词.
# 顺序敏感 (粥优先于汤, 凉拌优先于拌等). 推断失败 → "其他".

# 顺序敏感: 先匹配精确形态名词 (粥/饭/面/汤), 再 cooking_method 兜底
# Codex review 修复:
#   - "粉蒸/粉煎" 这里 "粉" 是粉末调料, 形态主体是"蒸"/"煎", 不能误归为"面"
#   - "炖牛肉饭"/"卤肉饭" 等 cooking_method=炖煮 但形态主体是"饭", 必须早于"汤"规则
_FOOD_FORM_RULES = [
    ("粥",   lambda name, method: "粥" in name or "糜" in name),
    # 优先剔除"粉蒸/粉煎"误归
    ("蒸",   lambda name, method: "粉蒸" in name),
    ("煎",   lambda name, method: "粉煎" in name),
    # 精确"饭/盖饭/便当"必须先于 "汤" (method=炖煮 触发)
    ("饭",   lambda name, method: any(k in name for k in ("饭", "盖浇", "便当", "套餐", "锅巴"))),
    # 面/粉/粿条/米线/意面 — 注意 "粉" 限定与汤/拌/炒/干等组合, 避免误捕"粉蒸"
    ("面",   lambda name, method: any(k in name for k in ("面", "粉条", "粉丝", "粿条", "米线",
                                                            "意大利", "意面"))
                                  or (("粉" in name)
                                       and ("粉蒸" not in name)
                                       and ("粉煎" not in name))),
    ("汤",   lambda name, method: any(k in name for k in ("汤", "羹", "煲", "炖盅", "牛杂"))
                                  or method == "炖煮"),
    ("凉拌", lambda name, method: any(k in name for k in ("凉拌", "凉菜", "沙拉")) or method == "凉拌"),
    ("烤",   lambda name, method: any(k in name for k in ("烤", "焗")) or method in ("烧烤", "烤")),
    ("油炸", lambda name, method: any(k in name for k in ("炸", "脆")) or method == "油炸"),
    ("蒸",   lambda name, method: "蒸" in name or method == "清蒸"),
    ("煎",   lambda name, method: any(k in name for k in ("煎", "饺", "锅贴", "肠粉")) or method == "煎炒"),
    ("炒",   lambda name, method: method in ("煎炒", "炒") or "炒" in name),
    ("卤水", lambda name, method: any(k in name for k in ("卤", "酱", "扣"))),
]


def infer_food_form(dish: dict) -> str:
    """从 canonical_name + cooking_method 推断 food_form, 失败 → '其他'."""
    name = dish.get("canonical_name") or dish.get("raw_name") or ""
    np_ = dish.get("nutrition_profile") or {}
    method = np_.get("cooking_method") or ""
    for form, predicate in _FOOD_FORM_RULES:
        try:
            if predicate(name, method):
                return form
        except Exception:
            continue
    return "其他"


def combo_food_form(combo: dict) -> str:
    """combo 的代表 food_form: 优先取主菜的, 否则取第一道菜的."""
    dishes = combo.get("dishes") or []
    if not dishes:
        return "其他"
    # 主菜优先
    for d in dishes:
        np_ = d.get("nutrition_profile") or {}
        if np_.get("dish_role") == DISH_ROLE_MAIN:
            return infer_food_form(d)
    return infer_food_form(dishes[0])


def cap_per_restaurant(
    ranked: list[dict],
    k: int = 3,
) -> list[dict]:
    """每家餐厅最多保留 k 个 combo (按 ranked 顺序优先).

    L2 排序后插入的"软去重": 同一家分数相近的 combo 容易扎堆 top30,
    挤掉真正多样的候选; cap 后保留每家最高分的 k 条, 其余按全局分数顺位下放.
    返回新列表 (不就地改 ranked).
    Args:
      ranked: rank_combos 输出 (已按 score 降序).
      k: 单家保留上限 (推荐 3, 兼顾"主力菜 + 蔬菜变体"几种组合); k<=0 直接 passthrough.
    边界:
      restaurant 无 id 也无 name 时, 用 id(combo) 作为 sentinel, 不参与跨条聚合.
    """
    if k <= 0:
        return list(ranked)
    top: list[dict] = []
    tail: list[dict] = []
    seen: dict[str, int] = {}
    for c in ranked:
        rest = c.get("restaurant") or {}
        rid = rest.get("id") or rest.get("name")
        if not rid:
            # 匿名 combo: 不和其他匿名条聚合, 直接放 head
            top.append(c)
            continue
        if seen.get(rid, 0) < k:
            top.append(c)
            seen[rid] = seen.get(rid, 0) + 1
        else:
            tail.append(c)
    return top + tail


def _cap_by_key(
    ranked: list[dict],
    key_fn,
    cap: int,
) -> list[dict]:
    """通用 cap: 按 key_fn 提取分组键, 每组最多 cap 条进 head, 其余 tail.

    key_fn(combo) → str | None. None 表示该 combo 不参与聚合 (匿名), 直接入 head.
    """
    if cap <= 0:
        return list(ranked)
    head: list[dict] = []
    tail: list[dict] = []
    seen: dict[str, int] = {}
    for c in ranked:
        key = key_fn(c)
        if not key:
            head.append(c)
            continue
        if seen.get(key, 0) < cap:
            head.append(c)
            seen[key] = seen.get(key, 0) + 1
        else:
            tail.append(c)
    return head + tail


def cap_per_cuisine(
    ranked: list[dict],
    cap: int = 6,
) -> list[dict]:
    """D-043: 每菜系最多保留 cap 条 (按 ranked 顺序).

    潮汕菜系往往因为 wetness/popular 等维度全员命中, 容易扎堆 top30;
    cap_per_cuisine 让 top30 内菜系分布更均匀, 不挤占其他菜系空间.
    菜系取 combo['dishes'][0].cuisine; combo 无菜系 → 不聚合 (直接 head).
    """
    def _cuisine_key(c: dict) -> str | None:
        dishes = c.get("dishes") or []
        if not dishes:
            return None
        return dishes[0].get("cuisine") or None
    return _cap_by_key(ranked, _cuisine_key, cap)


def cap_per_food_form(
    ranked: list[dict],
    cap: int = 8,
) -> list[dict]:
    """D-043: 每 food_form (粥/汤/拌/...) 最多保留 cap 条.

    与 cap_per_cuisine 互补: 潮汕粥/砂锅粥/艇仔粥 在 cuisine 上可能不同,
    但 food_form 都是"粥", 形态高度同质. 这一层去重保证 top30 不全是"汤汤水水".
    """
    return _cap_by_key(ranked, combo_food_form, cap)


def diversify_top(
    ranked: list[dict],
    n: int,
    max_per_brand: int = 1,
    max_per_cuisine: int = 2,
) -> list[dict]:
    """Top N 选择时强制品牌/菜系多样性, 避免 top 3 都来自同一连锁.

    D-049: 仅 rerank fallback 路径使用 (V2 主路径走 LLM + _enforce_brand_unique).
    max_per_brand=1 与 LLM 路径出口 brand 去重对齐, 保证 fallback 输出口径一致.
    """
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

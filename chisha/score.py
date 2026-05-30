"""打分: combo → 分数.

活维度清单以 V2_DEFAULT_WEIGHTS + score_combo 的 parts dict 为权威。
combo dish 缺字段时该维返回 0; profile 没配权重时用 V2_DEFAULT_WEIGHTS。
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
    # ── D-092: 5 死维度 (vegetable_floor_pass / protein_floor_pass / distance / wetness / context_boost)
    #          已从 V2_DEFAULT + parts dict 移除.
    # ── 活权重 ──
    "low_oil": 0.5,
    "popularity": 0.4,
    "cuisine_preference": 0.3,
    "variety_bonus": 0.5,            # 改活成连续函数后区分度提升
    "carb_quality": 0.6,
    "processed_meat": 1.0,           # 取负
    "sweet_sauce": 0.7,              # 取负
    "dish_role_match": 0.3,
    "eta": 0.4,                      # 取负
    "price": 0.5,                    # 取负
    "taste_match": 0.4,              # D-043: 启用兜底 hints 后变活, 起始 0.4
    # ── D-073: refine 意图三档 (Codex §3 拆分; 2026-05-16 实测校准) ──
    # 初始 0.20 实测 intent 加分被 popularity 单维压过, 校准到 0.50 让用户意图 >
    # 长期偏好 (cuisine_preference 0.30). 健康 guardrail × 0.4 仍保留兜底.
    # D-090 (2026-05-19): 实测 R2 trace「湘菜+重口+牛肉鸡肉」L2 top-5 仅 2 家湘菜, 主要靠
    # L3 硬拉. intent 三维满分合计 0.8 vs 健康罚分维度 weight 合计 3.3, 信号被淹没.
    # phase-1: 提权重 ×2~×4 + health_guardrail slot-aware 松绑 (heavy flavor → 油触发豁免).
    "intent_cuisine": 1.00,      # D-090: 0.50 → 1.00 (×2)
    "intent_ingredient": 0.50,   # D-090: 0.20 → 0.50 (×2.5)
    "intent_flavor": 0.40,       # D-090: 0.10 → 0.40 (×4, 让 heavy/spicy/light 真正生效)
    # ── B-001 / D-098: 短链路反馈即时生效 (差评强压 / 好评弱升) ──
    # T-FB-07 top5 cutoff margin 法标定 = 1.5: 实测 shenzhen-bay 真实数据 top1=2.65 /
    # top5 cutoff=2.40 (margin 0.25 极密). mild_neg (base -0.6) × 1.5 = -0.9 把 top1
    # 压到 1.75 << cutoff → 稳出 top5 (余量 3.6×); 好评 boost (base +0.3) × 1.5 = +0.45
    # 温和上托 (弱 boost). feedback_recency_bonus 已 gating (无反馈→0), 对无反馈
    # combo 0-diff (baseline_l2_snapshot 守门).
    "feedback_recency": 1.5,
}


# 5 个新字段的字面量 (与 chisha/schemas.py / D-032 v3 prompt 输出对齐)
# 注: "粥" 本质是精制白米煮的, 营养上不属于全谷物;
# 它的"清爽/汤水"价值已经由 wetness_bonus 维度覆盖, 不在 carb_quality 重复加分.
GRAIN_GOOD = {"糙米杂粮", "全麦面", "粗粮"}
GRAIN_BAD = {"白米", "精制面"}
DISH_ROLE_MAIN = "主菜"
DISH_ROLE_VEG = "配菜"
DISH_ROLE_CARB = "主食"
DISH_ROLE_COMBO = "套餐"   # 套餐通常自带主菜+主食 (按完整餐处理)


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
    # D-076.1: spicy / sweet_sauce 双向 (positive 信号扩, 与对应 penalty 镜像).
    # 阈值用 max() 不用 avg() 因偏好辣的人在意有没有一道够辣的 (anchor combo),
    # 不是整桌辣度均值. 同理 sweet_sauce.
    if "spicy" in boost:
        spicies = [d.get("nutrition_profile", {}).get("spicy_level", 0)
                    for d in combo["dishes"]]
        if max(spicies, default=0) >= 2:
            s += 0.5
    if "sweet_sauce" in boost and sweet_sauce_penalty(combo) > 0:
        # sweet_sauce_penalty 内部判定 sweet_sauce_level > 0 的菜数. boost 复用此 helper.
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
    # D-076.1: boost 和 penalty 同时含同一 token 是矛盾, 净效果 0 (上面两个分支
    # 分别 +0.5/-0.5 自然抵消). L1 prompt 规则 5 已禁此情形 (penalty 优先).
    return max(-1.0, min(1.0, s))


# B-001 / D-098: 菜品级相对餐厅级的子权重 (§8.5 归因噪声处理). 餐厅级归因干净 (主),
# 菜品级弱 (辅) → penalty 量纲显著 < 餐厅级. 二者叠加进同一 feedback_recency 维度.
FEEDBACK_DISH_SUBWEIGHT = 0.3


def feedback_recency_bonus(combo: dict, fb_signal: dict | None) -> float:
    """B-001 / D-098 短链路: 近期反馈对该 combo 的 recency-weighted 加/扣分.

    fb_signal 由 feedback_signal.build_feedback_signal 单次构建 (§8.1, api 起点),
    形如 {"restaurant": {rid: w}, "dish": {dish_id: w}, "recall_evict": {...}}.
    餐厅级 (主, 归因干净) + 菜品级 (辅, 弱, 跨 combo 累积) 叠加. 菜品级取 combo 内
    反馈菜的均值 (而非和, 防 combo 菜数膨胀量纲; 单道命中被天然稀释 = 归因不确定性).
    实际打分量纲由 score_combo 的 _w("feedback_recency") 标定.

    fb_signal=None / 该 restaurant 无近期反馈 + combo 内无反馈菜 → 0 → 对无反馈
    combo 0-diff (mirror taste_match/intent gating, baseline_l2_snapshot 守门).
    """
    if not fb_signal:
        return 0.0
    rest_map = fb_signal.get("restaurant") or {}
    dish_map = fb_signal.get("dish") or {}
    rid = (combo.get("restaurant") or {}).get("id")
    rest_w = rest_map.get(rid, 0.0) if rid else 0.0
    dishes = combo.get("dishes") or []
    dish_ws = [dish_map.get(d.get("dish_id"), 0.0) for d in dishes if d.get("dish_id")]
    dish_term = (sum(dish_ws) / len(dish_ws)) if dish_ws else 0.0
    return rest_w + FEEDBACK_DISH_SUBWEIGHT * dish_term


# ─────────────────────── D-073: cuisine/ingredient match helpers ───────────────────────
#
# 数据 cuisine 字段值: 湘菜/粤菜/川菜/潮汕/小吃/快餐/西式/江浙/日式/西北/东北/韩式/汤粥/东南亚/其他
# 用户表达可能用别名 ("湖南菜"="湘菜", "粤式"="粤菜", "日料"="日式" 等), 需归一.

CUISINE_ALIASES: dict[str, str] = {
    # → 数据中实际 cuisine 值
    "湖南菜": "湘菜", "湘菜": "湘菜", "湖南料理": "湘菜",
    "广东菜": "粤菜", "粤式": "粤菜", "粤菜": "粤菜",
    "四川菜": "川菜", "川渝": "川菜", "川菜": "川菜",
    "日料": "日式", "日本菜": "日式", "日式": "日式",
    "上海菜": "江浙", "沪菜": "江浙", "杭帮菜": "江浙",
    "江浙菜": "江浙", "江浙": "江浙", "浙菜": "江浙",
    "韩国料理": "韩式", "韩餐": "韩式", "韩式": "韩式",
    "潮州菜": "潮汕", "潮汕菜": "潮汕", "潮汕": "潮汕",
    "西餐": "西式", "西式料理": "西式", "西式": "西式",
    "东北菜": "东北", "东北": "东北",
    "西北菜": "西北", "新疆菜": "西北", "西北": "西北",
    "东南亚菜": "东南亚", "东南亚": "东南亚",
    "粥": "汤粥", "汤粥": "汤粥",
}


def normalize_cuisine(name: str) -> str | None:
    """用户输入 cuisine 名 → 数据 cuisine 字段值. 未知返回 None."""
    if not name:
        return None
    return CUISINE_ALIASES.get(name.strip())


def cuisine_exact_match(combo: dict, cuisine_want: list[str]) -> bool:
    """combo 中有 dish.cuisine ∈ (cuisine_want 归一后) 即命中."""
    if not cuisine_want:
        return False
    targets: set[str] = set()
    for c in cuisine_want:
        n = normalize_cuisine(c)
        if n:
            targets.add(n)
    if not targets:
        return False
    return any(d.get("cuisine") in targets for d in combo.get("dishes") or [])


def cuisine_soft_match(combo: dict, cuisine_want: list[str]) -> bool:
    """店名 或 菜名 包含目标 cuisine 字面子串 → 软命中 (用于 exact 未中但相关).

    匹配策略 (从严到宽):
      1. 原词命中: "湖南菜" in "湖南菜馆"
      2. 去"菜"后缀命中: "湖南" in "湖南老灶台"
      3. 同义词 (经 normalize_cuisine) 命中: "粤菜" → "粤" in "粤式甜品"
    """
    if not cuisine_want:
        return False
    rest = combo.get("restaurant") or {}
    haystack = (rest.get("name") or "") + " " + (rest.get("brand") or "")
    for d in combo.get("dishes") or []:
        haystack += " " + (d.get("canonical_name") or "")

    # Codex P1-2 修订: bare 至少 2 字才匹配, 避免 "粤"→"粤A" / "西"→"广西米粉"
    # 1 字裸匹配通过白名单 (用户高频简称 + 边界语义)
    _ONE_CHAR_WHITELIST = {"粤式", "湘味", "川味", "潮汕"}

    for c in cuisine_want:
        if not c:
            continue
        # 1. 原词命中 (>= 2 字)
        if len(c) >= 2 and c in haystack:
            return True
        # 2. 去"菜"/"料理"后缀, 仅 2 字以上的 bare 才做子串匹配
        bare = c.rstrip("菜").replace("料理", "").replace("菜系", "").strip()
        if bare and len(bare) >= 2 and bare in haystack:
            return True
        # 3. 1 字 bare 走白名单 (例: "粤菜" → bare="粤" 不直接 in, 但 "粤式" 整词在 haystack)
        if bare and len(bare) == 1:
            for ww in _ONE_CHAR_WHITELIST:
                if ww.startswith(bare) and ww in haystack:
                    return True
        # 4. 归一后再尝试 (粤菜/粤式/广东菜 等)
        norm = normalize_cuisine(c)
        if norm and norm != c:
            bare_norm = norm.rstrip("菜").strip()
            if bare_norm and len(bare_norm) >= 2 and bare_norm in haystack:
                return True
    return False


# 食材匹配: 用户说 "牛肉" → 看 canonical_name 是否含; 用户说 "肉" → main_ingredient_type ∈ {红肉,白肉}
_INGREDIENT_BROAD: dict[str, set[str]] = {
    "肉": {"红肉", "白肉"},
    "海鲜": {"海鲜"},
    "鱼": {"海鲜"},
    "虾": {"海鲜"},
    "鸡": {"白肉"},
    "鸡肉": {"白肉"},
    "牛": {"红肉"},
    "猪": {"红肉"},
    "羊": {"红肉"},
    "蛋": {"蛋"},
    "豆": {"豆制品"},
    "豆制品": {"豆制品"},
    "素": {"纯素"},
    "蔬菜": {"纯素"},
}


# 具体蛋白关键词 → main_ingredient_type 类别 (Codex P0-2 修订, 取代旧的 _INGREDIENT_BROAD 子串遍历).
# 旧逻辑里 "牛肉" 含 "肉" → _INGREDIENT_BROAD["肉"]={"红肉","白肉"} → 白肉也命中, 食材意图泛化过度.
# 现在: 具体食材词必须命中精确蛋白关键词才走 main_ingredient 兜底, 且只匹配单一类别.
_PROTEIN_KEYWORDS_TO_MTYPE: dict[str, str] = {
    "牛": "红肉", "猪": "红肉", "羊": "红肉",
    "鸡": "白肉", "鸭": "白肉",
    "鱼": "海鲜", "虾": "海鲜", "蟹": "海鲜", "贝": "海鲜",
}


def contains_ingredient(combo: dict, ingredient: str) -> bool:
    """combo 是否含目标食材.

    两条路径:
      1. 广义词 (肉/海鲜/纯素/蛋/豆制品/...) → _INGREDIENT_BROAD 命中 main_ingredient_type
      2. 具体词 (牛肉/鸡肉/虾/...):
         a. 菜名子串命中 (优先)
         b. 提取精确蛋白关键词 (牛/鸡/虾/鱼...) → main_ingredient_type 单类匹配

    Codex P0-2 修订: 不再遍历 _INGREDIENT_BROAD.items() 做"子串包含"判断,
    避免 "牛肉" 误命中白肉、"鸡肉" 误命中红肉. _PROTEIN_KEYWORDS_TO_MTYPE 是
    单一映射, 一个关键词对应一个 main_ingredient 类别.
    """
    if not ingredient:
        return False
    ing = ingredient.strip()
    # 路径 1: 广义词 (整词命中)
    broad = _INGREDIENT_BROAD.get(ing)
    if broad:
        for d in combo.get("dishes") or []:
            np_ = d.get("nutrition_profile") or {}
            if np_.get("main_ingredient_type") in broad:
                return True
        return False
    # 路径 2a: 具体词菜名子串
    for d in combo.get("dishes") or []:
        name = d.get("canonical_name") or ""
        if ing in name:
            return True
    # 路径 2b: 具体词中包含精确蛋白关键词 → 单一类别匹配
    matched_mtypes: set[str] = set()
    for kw, mtype in _PROTEIN_KEYWORDS_TO_MTYPE.items():
        if kw in ing:
            matched_mtypes.add(mtype)
    if matched_mtypes:
        for d in combo.get("dishes") or []:
            np_ = d.get("nutrition_profile") or {}
            if np_.get("main_ingredient_type") in matched_mtypes:
                return True
    return False


# ─────────────────────── D-073: intent_match_bonus + health_guardrail ─────

def health_guardrail(combo: dict, profile: dict, intent=None) -> float:
    """触发健康风险时, intent 加分打折. 返回乘子 ∈ {0.4, 1.0}.

    触发条件 (任一):
      - oil_avg > prefer_oil_level_at_most + 1
      - apply_unforgivable_penalty 也会触发 (sweet/processed_meat/wetness 组合)

    Codex review §3: 防止"全是麻辣火锅"——intent 服从健康约束.

    D-090.1 (D-094.1 修正案): slot-aware 松绑触发字段从 V1 flavor_tags="heavy"
    切换到 V2 constrain.oil="high" (用户明确要重口/下饭/够味). intent=None 时行为与旧 API 完全一致.
    """
    # slot-aware 信号 (R1 路径 intent=None 时全 False, 行为与旧 API 一致)
    oil_exempt = (getattr(intent, "oil", None) == "high") if intent else False

    prefer_oil = profile["plate_rule"].get("prefer_oil_level_at_most", 3)
    oils = [
        d.get("nutrition_profile", {}).get("oil_level", 3)
        for d in combo.get("dishes") or []
    ]
    oil_avg = sum(oils) / max(1, len(oils))
    if oil_avg > prefer_oil + 1 and not oil_exempt:
        return 0.4
    # unforgivable penalty 共享触发条件
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
    if ((sweet_hits >= 1 and proc_hits >= 1)
        or proc_hits >= 2
        or (sweet_hits >= 1 and wet_hits >= 1)):
        return 0.4
    return 1.0


def _resolve_price_band(intent) -> str | None:
    """D-094.1: V2 price 优先级 = price_max 数字优先 (更精确) > price_band 文本兜底.

    spec T-FR-V1-RETIRE §41: price_max 是数字、更精确, 两者共存时数字赢;
    仅当 price_max 缺失/非法才回落到 explicit price_band (模糊文本).

    price_max 推 band 阈值 (跟 V1 cheap/normal/premium 经验值一致):
      <= 30 → cheap, <= 80 → normal, > 80 → premium.
    """
    if intent is None:
        return None
    pm = getattr(intent, "price_max", None)
    if pm is not None:
        try:
            pmf: float | None = float(pm)
        except (TypeError, ValueError):
            pmf = None
        if pmf is not None:
            if pmf <= 30:
                return "cheap"
            if pmf <= 80:
                return "normal"
            return "premium"
    pb = getattr(intent, "price_band", None)
    if pb in {"cheap", "normal", "premium"}:
        return pb
    return None


def _build_refine_weight_overlay(intent) -> dict[str, float]:
    """D-091 phase-2: refine 模式下按 explicit slot 给 score weight 加 multiplier.

    返回 dict[dim_name → multiplier]. 缺省 dim multiplier = 1.0 (不变).
    intent=None 时返回空 dict → score_combo 走 baseline 权重 → R1 0-diff 守门.

    D-094.1 修正案: 触发字段切 V2:
      - V2 constrain.oil == "high" → low_oil ×0.3 (替代 V1 flavor_tags="heavy")
      - V2 staple_want 非空 → carb_quality ×0.0 (替代 V1 staple_preference ∈ {want_rice, want_noodle})
      - V2 price_band == cheap (or price_max 推 cheap) → price ×1.5
      - V2 price_band == premium (or price_max 推 premium) → price ×0.0
      - cuisine_want 非空 → cuisine_preference ×0.5 (refine 优先于画像)
      - 已砍: sweet → sweet_sauce ×0.3 (V2 不再 explicit sweet 信号; 走 narrative)
    """
    if intent is None:
        return {}
    mult: dict[str, float] = {}
    if getattr(intent, "oil", None) == "high":
        mult["low_oil"] = 0.3
    if getattr(intent, "staple_want", None):
        mult["carb_quality"] = 0.0
    pb = _resolve_price_band(intent)
    if pb == "cheap":
        mult["price"] = 1.5
    elif pb == "premium":
        mult["price"] = 0.0
    if getattr(intent, "cuisine_want", None):
        mult["cuisine_preference"] = 0.5
    return mult


# D-094.1: staple (主食) 判定 — score bonus + recall staple_avoid 硬过滤共用.
# codex review YELLOW: 短 token "面" 子串会误命中 "面包/面筋", 必须先按 grain_type
# 过滤 (dish 是真主食) 再做子串. grain_type ∈ 主食类 或 dish_role=主食 才算.
_STAPLE_GRAIN_TYPES = {"精制面", "全麦面", "白米", "糙米杂粮"}


def dish_is_staple(d: dict) -> bool:
    np_ = d.get("nutrition_profile") or {}
    if np_.get("grain_type") in _STAPLE_GRAIN_TYPES:
        return True
    # dish_role=主食 兜底 (主食类目但 grain_type 缺标)
    if np_.get("dish_role") == DISH_ROLE_CARB:
        return True
    return False


def intent_match_bonus(
    combo: dict,
    intent,  # RefineIntent | None (避免循环 import, 鸭子类型)
    profile: dict,
) -> dict[str, float]:
    """D-073: 结构化意图匹配, 返回三档拆解 {'cuisine', 'ingredient', 'flavor'}, 各 ∈ [0, 1].

    Codex review §3: 拆三档而非单一权重, 让健康/多样性维度保留发言权.
    Codex review §5: spicy 走 profile.spicy_tolerance, 不能覆盖 profile.
    Codex review §3: 健康 guardrail 触发 → 全部 × 0.4.
    """
    out = {"cuisine": 0.0, "ingredient": 0.0, "flavor": 0.0}
    if intent is None:
        return out

    # 1. cuisine (exact 1.0 / soft 0.6)
    if getattr(intent, "cuisine_want", None):
        if cuisine_exact_match(combo, intent.cuisine_want):
            out["cuisine"] = 1.0
        elif cuisine_soft_match(combo, intent.cuisine_want):
            out["cuisine"] = 0.6

    # 2. ingredient (per item 0.4, 上限 1.0)
    if getattr(intent, "ingredient_want", None):
        hit = sum(1 for ing in intent.ingredient_want
                  if contains_ingredient(combo, ing))
        out["ingredient"] = min(1.0, hit * 0.4)

    # 3. flavor (D-094.1: V2 oil / wants_soup 替代 V1 flavor_tags)
    flavor_score = 0.0
    oil = getattr(intent, "oil", None)

    if getattr(intent, "wants_soup", False) and wetness_bonus(combo) > 0:
        flavor_score += 0.5

    if oil == "low":
        oils = [d.get("nutrition_profile", {}).get("oil_level", 3)
                for d in combo.get("dishes") or []]
        if oils and (sum(oils) / len(oils)) <= 2:
            flavor_score += 0.5

    if oil == "high":
        oils = [d.get("nutrition_profile", {}).get("oil_level", 3)
                for d in combo.get("dishes") or []]
        if oils and (sum(oils) / len(oils)) >= 3:
            flavor_score += 0.3

    out["flavor"] = min(1.0, flavor_score)

    # 4. staple_want (D-094.1 新增, 替代 V1 staple_preference + portion).
    # staple_avoid 不在这里: avoid 语义跟 cuisine_avoid/ingredient_avoid 一致, 走 recall
    # 硬过滤 (intent_match_bonus 是 [0,1] 正向加分, 表达不了 demote — 见 BLOCK 修复).
    staple_want = getattr(intent, "staple_want", None) or []
    if staple_want:
        has_want = any(
            dish_is_staple(d) and any(
                s and s in (d.get("canonical_name") or "") for s in staple_want
            )
            for d in combo.get("dishes") or []
        )
        if has_want:
            out["ingredient"] = min(1.0, out["ingredient"] + 0.3)

    # 7. 健康 guardrail (Codex §3) + slot-aware 松绑 (D-090)
    guard = health_guardrail(combo, profile, intent=intent)
    if guard < 1.0:
        for k in out:
            out[k] *= guard

    return out


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
    intent=None,  # D-073: RefineIntent | None
    fb_signal: dict | None = None,  # B-001/D-098: 短链路反馈信号, None→feedback_recency 维 0
) -> tuple[float, dict[str, float]]:
    """计算 combo 综合分. 返回 (score, breakdown).

    实际生效维度 = 下方 parts dict (权威源)。
    传 taste_hints/meal_type 时对应维度参与打分, 不传则该维为 0。
    传 intent (refine 二轮) 时 intent_* 三档加分生效。
    传 fb_signal (短链路反馈) 时 feedback_recency 维生效 (None→0)。
    context 参数现为 no-op (仅保留 API 兼容, 不进任何打分项)。
    """
    w = profile.get("scoring_weights") or {}
    # D-091 phase-2: refine 模式下按 explicit slot 动态调权重 (R1 intent=None 时 multiplier 全 1.0 → 0-diff)
    overlay_mult = _build_refine_weight_overlay(intent)

    def _w(key: str) -> float:
        base = float(w.get(key, V2_DEFAULT_WEIGHTS.get(key, 0.0)))
        return base * overlay_mult.get(key, 1.0)

    intent_parts = intent_match_bonus(combo, intent, profile)

    parts = {
        # D-092: 删 5 死维度 (vegetable_floor_pass / protein_floor_pass /
        # distance / wetness / context_boost), 详见 D-092 决策.
        # V1 维度
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
        "dish_role_match": dish_role_match_bonus(combo) * _w("dish_role_match"),
        # V2 履约
        "eta": -eta_penalty(combo, profile) * _w("eta"),
        "price": -price_penalty(combo, profile, meal_type) * _w("price"),
        # V2 偏好/情境
        "taste_match": taste_match_bonus(combo, taste_hints) * _w("taste_match"),
        # D-073 refine 意图 (intent=None 时全 0)
        "intent_cuisine": intent_parts["cuisine"] * _w("intent_cuisine"),
        "intent_ingredient": intent_parts["ingredient"] * _w("intent_ingredient"),
        "intent_flavor": intent_parts["flavor"] * _w("intent_flavor"),
        # B-001/D-098 短链路反馈 (fb_signal=None / 无近期反馈 → 0)
        "feedback_recency": feedback_recency_bonus(combo, fb_signal)
            * _w("feedback_recency"),
    }
    return sum(parts.values()), parts


# D-079 Codex BLOCKER #4/#8: 区分 "未传 override" 与 "传了 None (= 当时无 prefs)".
# sentinel object 让 l1_prefs_override=None 也走 override 路径 (不读 live prefs).
_UNSET_L1_PREFS = object()


def rank_combos(
    combos: list[dict],
    profile: dict,
    meal_log: list[dict] | None = None,
    today: dt.date | None = None,
    context: "ContextSnapshot | None" = None,
    taste_hints: dict | None = None,
    meal_type: str | None = None,
    root=None,
    intent=None,  # D-073: RefineIntent | None, refine 二轮启用
    *,
    l1_prefs_override=_UNSET_L1_PREFS,  # D-079: 不传=load_prefs(root); 显式 dict 或 None=用之 (含 None 表示当时无 prefs)
    feedback_signal_override=None,  # B-001/D-098: 调用方显式注入 (api/refine 单次构建 §8.1 / What-if 冻结值); None=无反馈. rank_combos 自身不读 store.
) -> list[dict]:
    """对 combos 打分排序, 返回带 score/breakdown 的列表 (降序).

    D-043 → D-076 PR-0.7 切换:
    runtime_hints 来源从 long_term_prefs.load_runtime_hints (D-043 旧 chip 频次)
    切换到 l1_prefs.load_prefs (D-076 LLM 抽取产物).

    等价性约束 (D-072.1 baseline 守门):
    - prefs.json 不存在 + jsonl 不存在 → 旧/新均 None ✓
    - prefs.json 不存在 + jsonl 存在 → 语义改变 ⚠️ 调用方必须先跑
      scripts/bootstrap_l1_from_legacy.py 兜底
    - prefs.json 存在 → 走 LLM 抽取产物 (旧 jsonl 不再被读)

    D-079 (Codex #1 + sentinel 修订): l1_prefs_override 注入 — What-if 重跑时
    传入冻结的 prefs snapshot 替代 load_prefs(root). 显式传 None 表示"当时无
    prefs (= load_prefs 返 None)", 也不读 runtime state.
    不传 → 走 load_prefs(root), 生产链路向后兼容.

    Args:
      root: 项目根 (透传给 l1_prefs.load_prefs).
        Codex Q3 修复: 三态等价性必须由 bootstrap 脚本保证.
      l1_prefs_override: 不传=load_prefs(root) 路径; 显式 dict 或 None=用之
        (Codex BLOCKER #4/#8: None 当时无 prefs, 严禁 fallback 到 live).
    """
    # D-043: rank-based popularity, 就地修改 combos (加 _popularity_rank)
    attach_popularity_ranks(combos)
    # D-043 → D-076: taste_hints 始终合并 static (profile) + runtime (L1 LLM 抽取
    # 产物) + 显式传入. 旧 D-043 jsonl 频次聚合在 PR-0.7 后不再被读, 走 l1_prefs.
    from chisha.l1_prefs import load_prefs, to_runtime_hints
    from chisha.long_term_prefs import merge_hints
    static_hints = extract_static_taste_hints(profile)
    try:
        # D-079: override 优先 (含 None), 不读 runtime state 防 What-if 漂移
        if l1_prefs_override is _UNSET_L1_PREFS:
            prefs = load_prefs(root=root)
        else:
            prefs = l1_prefs_override
        runtime_hints = to_runtime_hints(prefs)
    except Exception:
        runtime_hints = None
    effective_hints = merge_hints(static_hints, runtime_hints, taste_hints)

    # B-001/D-098: 短链路反馈信号由调用方显式注入 (api/refine 单次构建 §8.1; What-if
    # 传冻结值; baseline/standalone 不传→None). rank_combos 自身不读 store — 防 debug/
    # standalone 链路 L2 live-build 与 L1/trace 不一致 (Codex review should-fix).
    fb_signal = feedback_signal_override

    scored = []
    for c in combos:
        s, br = score_combo(c, profile, meal_log, today,
                            context=context, taste_hints=effective_hints,
                            meal_type=meal_type, intent=intent, fb_signal=fb_signal)
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
    intent=None,  # D-073 followup: RefineIntent | None, 用户明确 cuisine_want 时免 cuisine cap
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

    refine intent 例外 (D-073 followup, 「换日料」bug):
      用户在 refine 显式 cuisine_want 时, 目标菜系免 cuisine + brand + food_form
      三层 cap. 实测「换日料」: 数据里日式仅 5 个 brand, brand cap=2 把候选压到
      10 个上限, 与"原则派想吃 X 就给 X"语义冲突.
      仅保留 restaurant cap (防单店连刷一页), 其他多样性约束在目标菜系内全部放开.
    """
    caps = resolve_caps(profile)
    cap_r = caps["restaurant"]
    cap_b = caps["brand"]
    cap_c = caps["cuisine"]
    cap_f = caps["food_form"]
    # 目标菜系免 cuisine + brand + food_form cap (与计数口径一致, 都看 dishes[0].cuisine)
    exempt_cuisines: set[str] = set()
    if intent is not None:
        for c in (getattr(intent, "cuisine_want", None) or []):
            n = normalize_cuisine(c)
            if n:
                exempt_cuisines.add(n)
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
        is_exempt = bool(cui and cui in exempt_cuisines)
        # 任一层 cap 已满 → 丢弃 (D-049: 不再保留 tail)
        if cap_r > 0 and rid and cnt_r.get(rid, 0) >= cap_r:
            continue
        if cap_b > 0 and brand and not is_exempt \
                and cnt_b.get(brand, 0) >= cap_b:
            continue
        if cap_c > 0 and cui and not is_exempt \
                and cnt_c.get(cui, 0) >= cap_c:
            continue
        if cap_f > 0 and form and not is_exempt \
                and cnt_f.get(form, 0) >= cap_f:
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
    from chisha.install_root import install_root  # T-DIST-01 B.1
    root = install_root()
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

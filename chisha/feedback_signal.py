"""B-001 / D-098: 反馈短链路信号构建 (实时 / 餐厅·菜品级 / 带衰减).

第一原则 (D-098 Responsive Feedback): 用户每一次 👍/👎 必须在下一次推荐就被可感知
地响应; "差评不生效" = 信任崩塌. 本模块是短链路的信号源, 补 L1 慢链路
(l1_extractor LLM 抽取 → l1_prefs → score.taste_match) 的缺口 — 二者独立互补:
短链路实时压"差评的那家店/那道菜", L1 慢链路负责泛化成长期口味结论.

分层 (mirror l1_prefs.py): 本模块只**构建**信号 dict; 打分消费 (feedback_recency
维度 + feedback_recency_bonus 组合器) 在 score.py; recall 剔除在 recall.py;
narrative 透传在 rerank.py. 单次构建一个内存对象, 由 recall/score/L3/trace 共享
同一引用 (api.recommend_meal 起点构建), 严禁各自读盘重算 (§8.1 硬约束 + D-079).

数据地基 (§1 v2, feedback_store 自包含, 无需 JOIN meal_log):
    feedback_store.feedbacks[sid] = {rating, repurchase_intent, accepted_rank,
                                     submitted_at, ...}
    feedback_store.sessions[sid]  = 冷存完整 RecommendResponse, 含
                                    candidates[].restaurant.id + candidates[].dishes[].dish_id
    accepted_rank → candidates[rank-1] → restaurant_id (干净归因) + dish_id 列表 (弱/累积)

为什么不走 meal_log JOIN: meal_log.jsonl 落盘丢弃 dish_id (只留 main_ingredient_type
+ canonical_name), 且 canonical_name 非唯一 → 无法当菜品身份键 (§1 v2 已验证).

信号源 = 组合 C + Q-B 冲突规则 (§8.4 / §8.5, repurchase_intent 编码 0=no/1=neutral/2=yes):
    强负 (strong_neg) = rating==-1 且 repurchase==0  → score 强压 + recall 30 天剔除
    boost            = rating==1 且 repurchase==2   (双正才升, 保守防误 boost)
    repurchase==2    → 不抑制 (即便 rating==-1, "难吃但想再吃" → repurchase 为准)
    repurchase==0    → mild_neg (即便 rating==1, repurchase 为准)
    repurchase 1/缺  → 听 rating (-1=mild_neg, 1=neutral 不 boost)
    不违反 D-063~065: 决策层并列消费两个原始字段 (非改写成同一字段语义);
    F-008 落地前组合信号不外推为长期口味结论.

衰减 (§8.4 线性, 可解释可调):
    差评 (strong/mild_neg): 0-30d 强抑制(1.0) / 30-60d 线性衰减 / >60d 无
    好评 (boost):          0-7d cooldown(0, recall 已防连吃) / 7-30d 弱 boost(1.0)
                           / 30-60d 线性衰减 / >60d 无
    days_ago 由调用方传入的 today (走 clock.today(root), D-077) 算, 禁裸 dt.date.today.

降级 (§1, 不报错):
    - sessions[sid] 缺 cold-store 完整响应 (老数据/未存) → 无法拿 restaurant_id/dish_id
      (accepted[sid] 只存 restaurant_name 非 id, 非稳定打分键) → 跳过该反馈.
    - accepted_rank 缺失 / 越界 / candidate 结构异常 → 跳过该反馈.
    - 无反馈 / 全部已衰减 → 返回空 dict (gating 0-diff 前提, mirror l1_prefs load_prefs→None).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any


# ---- 极性常量 ----
STRONG_NEG = "strong_neg"
MILD_NEG = "mild_neg"
BOOST = "boost"
NEUTRAL = "neutral"

# ---- 衰减窗口 (天) ----
NEG_FULL_DAYS = 30        # 差评强抑制窗口
NEG_DECAY_END_DAYS = 60   # 差评线性衰减终点
BOOST_COOLDOWN_DAYS = 7   # 好评 cooldown (recall 已处理连吃多样性)
BOOST_FULL_END_DAYS = 30  # 好评弱 boost 窗口终点
BOOST_DECAY_END_DAYS = 60 # 好评衰减终点
EVICT_WINDOW_DAYS = 30    # 强负 recall 剔除窗口 (§2.3 / §8.5 Q-A)

# ---- 极性基础权重 (归一化 [-1, 1], 实际打分量纲由 score.V2_DEFAULT_WEIGHTS
#      ["feedback_recency"] 标定, T-FB-07 top5 cutoff margin 法) ----
# 非对称设计 (§8.4): 差评强压 (信任刚需), 好评弱升 (BOOST 显著 < |NEG|; 且 recall
# 0-7d cooldown 已防连吃). 实际打分量纲 = base × score.V2_DEFAULT_WEIGHTS["feedback_recency"].
_BASE_WEIGHT: dict[str, float] = {
    STRONG_NEG: -1.0,
    MILD_NEG: -0.6,
    BOOST: 0.3,
    NEUTRAL: 0.0,
}

# 单次反馈对 combo 内每道菜的弱权重单位 (§8.5 归因噪声处理): 反馈是餐级 (rating 对
# 整个 combo), 无法精确归因到"哪道难吃" → 单次只给弱权重, 同一 dish_id 跨多个差评
# combo 反复出现才累积成强信号 (重复证据自洽抵消单次归因噪声). 餐厅级是主 (归因干净)、
# 菜品级是辅 (此处 < 1 → 单次弱; 跨 combo 累加后 clamp).
DISH_ACCUM_UNIT = 0.4


def _polarity(rating: Any, repurchase: Any) -> str:
    """组合 C + Q-B 冲突规则 → 极性. repurchase 优先于 rating (冲突时)."""
    r = rating
    p = repurchase
    # 双负 → 强负
    if r == -1 and p == 0:
        return STRONG_NEG
    # 双正 → boost (保守)
    if r == 1 and p == 2:
        return BOOST
    # 冲突 / 单信号: repurchase 为准 (Q-B)
    if p == 2:        # 想再吃 → 不抑制 (即便 rating==-1)
        return NEUTRAL
    if p == 0:        # 不想再吃 → mild 抑制 (即便 rating==1)
        return MILD_NEG
    # repurchase 1/None → 听 rating
    if r == -1:
        return MILD_NEG
    return NEUTRAL    # rating==1 但非双正 → 保守不 boost


def _decay_factor(polarity: str, days_ago: int) -> float:
    """线性衰减系数 ∈ [0, 1]. days_ago < 0 (未来时间戳脏数据) → 0."""
    if days_ago < 0:
        return 0.0
    if polarity in (STRONG_NEG, MILD_NEG):
        if days_ago <= NEG_FULL_DAYS:
            return 1.0
        if days_ago <= NEG_DECAY_END_DAYS:
            return (NEG_DECAY_END_DAYS - days_ago) / (
                NEG_DECAY_END_DAYS - NEG_FULL_DAYS
            )
        return 0.0
    if polarity == BOOST:
        if days_ago <= BOOST_COOLDOWN_DAYS:
            return 0.0  # cooldown: recall 已防连吃, 不重复 boost
        if days_ago <= BOOST_FULL_END_DAYS:
            return 1.0
        if days_ago <= BOOST_DECAY_END_DAYS:
            return (BOOST_DECAY_END_DAYS - days_ago) / (
                BOOST_DECAY_END_DAYS - BOOST_FULL_END_DAYS
            )
        return 0.0
    return 0.0


def _submitted_date(submitted_at: Any) -> dt.date | None:
    """ISO 时间戳 → date. 解析失败 → None (跳过该反馈, 不报错)."""
    if not isinstance(submitted_at, str):
        return None
    try:
        return dt.datetime.fromisoformat(submitted_at).date()
    except ValueError:
        return None


def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


def _resolve_combo(
    store: dict, sid: str, fb: dict
) -> tuple[str, str, list[str]] | None:
    """经 accepted_rank 定位 cold-store combo → (restaurant_id, restaurant_name, [dish_id, ...]).

    restaurant_name 供 narrative 透传 (T-FB-05): 被剔除的店已不在候选里, 名字只能
    从 cold-store candidate 取. 降级返回 None (调用方跳过): 无 session 冷存 /
    rank 缺失越界 / 结构异常.
    """
    sessions = store.get("sessions") or {}
    resp = sessions.get(sid)
    if not isinstance(resp, dict):
        return None  # 无 cold-store 完整响应 → 跳过 (accepted 只有 name 非 id)
    candidates = resp.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None

    rank = fb.get("accepted_rank")
    if rank is None:
        accepted = (store.get("accepted") or {}).get(sid) or {}
        rank = accepted.get("accepted_rank")
    if not isinstance(rank, int) or rank < 1 or rank > len(candidates):
        return None

    cand = candidates[rank - 1]
    if not isinstance(cand, dict):
        return None
    rest = cand.get("restaurant") or {}
    rid = rest.get("id")
    if not rid:
        return None
    rname = rest.get("name") or rid
    dish_ids = [
        d.get("dish_id")
        for d in (cand.get("dishes") or [])
        if isinstance(d, dict) and d.get("dish_id")
    ]
    return rid, rname, dish_ids


def _feedback_contrib(fb, sid: str, feedback_store: dict, today: dt.date):
    """单条反馈 → (rid, rname, dish_ids, contrib, dish_unit, evict_remaining|None) 或 None.

    封装极性/日期/衰减/combo 定位 + 贡献值与剔除剩余天数计算; 跨条累积留给调用方。
    任一守门不过 (非 dict / NEUTRAL / 无日期 / decay 0 / 未定位) → None (跳过)。
    """
    if not isinstance(fb, dict):
        return None
    polarity = _polarity(fb.get("rating"), fb.get("repurchase_intent"))
    if polarity == NEUTRAL:
        return None
    submitted = _submitted_date(fb.get("submitted_at"))
    if submitted is None:
        return None
    days_ago = (today - submitted).days
    decay = _decay_factor(polarity, days_ago)
    if decay == 0.0:
        return None
    resolved = _resolve_combo(feedback_store, sid, fb)
    if resolved is None:
        return None
    rid, rname, dish_ids = resolved
    contrib = _BASE_WEIGHT[polarity] * decay
    dish_unit = contrib * DISH_ACCUM_UNIT
    evict_remaining = (
        EVICT_WINDOW_DAYS - days_ago
        if polarity == STRONG_NEG and days_ago < EVICT_WINDOW_DAYS
        else None
    )
    return rid, rname, dish_ids, contrib, dish_unit, evict_remaining


def build_feedback_signal(
    feedback_store: dict, today: dt.date, *, root: Path | None = None
) -> dict:
    """构建短链路反馈信号 (餐厅级 + 菜品级 recency-weighted + recall 剔除清单).

    Args:
        feedback_store: load_store() 返回的 dict (feedbacks/sessions/accepted).
        today: clock.today(root) (D-077 硬约束), 用于算 days_ago 衰减.
        root: 保留参数, 与 What-if 注入 / 调用点对称 (信号全部派生自传入 store + today).

    Returns:
        {
          "restaurant": {rid: w∈[-1,1]},     # 主, 归因干净 (累积 clamp)
          "dish": {dish_id: w∈[-1,1]},        # 辅, 弱 (跨 combo 累积抵消归因噪声)
          "recall_evict": {rid: remaining_days},  # 强负 → recall 剔除清单 (remaining>0)
          "evict_names": {rid: restaurant_name}   # 强负店名, 供 narrative 忠实透传 (T-FB-05)
        }
        无反馈 / 全衰减 → 四个 map 均空 (gating 0-diff 前提).
    """
    # 先累积 raw 和 (不逐条 clamp), 最后统一 clamp — 否则混合正负反馈结果会依赖
    # dict 遍历顺序 (Codex review: per-iter clamp 在跨 cap 边界时丢信息且顺序敏感).
    rest_raw: dict[str, float] = {}
    dish_raw: dict[str, float] = {}
    recall_evict: dict[str, int] = {}
    evict_names: dict[str, str] = {}

    if not isinstance(feedback_store, dict):
        return {"restaurant": {}, "dish": {}, "recall_evict": {}, "evict_names": {}}

    feedbacks = feedback_store.get("feedbacks") or {}
    for sid, fb in feedbacks.items():
        one = _feedback_contrib(fb, sid, feedback_store, today)
        if one is None:
            continue
        rid, rname, dish_ids, contrib, dish_unit, evict_remaining = one
        # 餐厅级: 累积 raw (同店多次反馈叠加, 末尾统一 clamp)
        rest_raw[rid] = rest_raw.get(rid, 0.0) + contrib
        # 菜品级: 单次弱权重, 跨 combo 累积 raw
        for did in dish_ids:
            dish_raw[did] = dish_raw.get(did, 0.0) + dish_unit
        # recall 剔除: 仅强负, 剩余天数取最大
        if evict_remaining is not None:
            recall_evict[rid] = max(recall_evict.get(rid, 0), evict_remaining)
            evict_names[rid] = rname

    # 统一 clamp + 剔除衰减/抵消后为 0 的项 (保持空 dict 0-diff 语义). 排序输出
    # 稳定 (NIT: 防 prompt / snapshot 文本随 dict 插入顺序漂移).
    restaurant = {k: _clamp(rest_raw[k]) for k in sorted(rest_raw)
                  if _clamp(rest_raw[k]) != 0.0}
    dish = {k: _clamp(dish_raw[k]) for k in sorted(dish_raw)
            if _clamp(dish_raw[k]) != 0.0}
    evict_names = {k: evict_names[k] for k in sorted(evict_names) if k in recall_evict}
    recall_evict = {k: recall_evict[k] for k in sorted(recall_evict)}
    return {"restaurant": restaurant, "dish": dish,
            "recall_evict": recall_evict, "evict_names": evict_names}


def evicted_restaurant_ids(fb_signal: dict | None) -> set[str]:
    """recall 用: 当前仍处于强负剔除窗口的 restaurant id 集合 (remaining_days>0)."""
    if not fb_signal:
        return set()
    evict = fb_signal.get("recall_evict") or {}
    return {rid for rid, days in evict.items() if isinstance(days, int) and days > 0}

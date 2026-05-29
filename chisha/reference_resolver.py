"""T-P2-01: refine reference 块 resolver + 比较器.

支持的"相对表达":
  - 时间引用: "昨天" / "上次" / "上周三" / "上周午饭" / "今早"
  - relation 比较器:
    - "lighter" (更清淡): 降油 / 降辣 / 降甜
    - "similar_but_different_venue" (相似换家): 同 cuisine 主体, restaurant_id 必须变

边界:
  - resolver 只读 trace_store, 不引入新 LLM 调用 (brief §10 P2-01 不做)
  - 解析失败 / 找不到历史 → 返 None, 让上游降级到非 reference 路径
  - 字段空洞: brief §5 reference 在 RefineIntentV2 schema 有占位但 L1/L2 暂不消费;
    本模块产出的 ResolvedReference 用作上游"软重排" 数据, 不强制硬过滤

接入:
  - refine path 拿 RefineIntentV2.reference / V1 freeform_note 走 parse_reference_text
  - resolve_reference 返 ResolvedReference (含历史 combos) 给 L3 prompt 上下文
  - apply_relation 给 L3 之前的 candidates 做软重排
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ────────────────────────── data shapes


@dataclass
class ReferenceQuery:
    """parse_reference_text 的输出. 用作 resolve_reference 的查询."""
    raw_text: str
    relation: str  # "lighter" / "similar_but_different_venue" / "similar" / "unknown"
    days_back: int | None = None   # "昨天"=1, "前天"=2, "上周三"=按 weekday
    meal_hint: str | None = None   # "lunch" / "dinner" / None


@dataclass
class ResolvedReference:
    """resolve_reference 返回. 指向历史会话 + 解析关系."""
    base_session_id: str
    base_meal_type: str
    base_started_at: str           # ISO 字符串
    base_combos: list[dict]        # 历史 final 5 (来自 trace["final"])
    relation: str
    raw_text: str
    notes: list[str] = field(default_factory=list)  # 解析过程提示, debug 用


# ────────────────────────── parse layer


# 关系词典 (substring 命中即触发)
_LIGHTER_KEYWORDS: tuple[str, ...] = (
    "清淡", "更清淡", "比.*清淡", "少油", "更轻", "清爽一点"
)
_DIFF_VENUE_KEYWORDS: tuple[str, ...] = (
    "换一家", "换家", "不一样的店", "别的店", "别家", "换个店",
    "类似但不一样", "差不多但换", "和上次那家差不多但换"
)
_SIMILAR_KEYWORDS: tuple[str, ...] = (
    "一样", "差不多", "和那次类似", "重复那顿",
)
# 时间引用
_DAYS_BACK_PATTERNS: tuple[tuple[str, int], ...] = (
    ("前天", 2),
    ("昨天", 1),
    ("昨晚", 1),
    ("今天早上", 0),
    ("今早", 0),
    ("早些时候", 0),
)
_WEEKDAYS = {
    "周一": 0, "礼拜一": 0, "上周一": 0,
    "周二": 1, "礼拜二": 1, "上周二": 1,
    "周三": 2, "礼拜三": 2, "上周三": 2,
    "周四": 3, "礼拜四": 3, "上周四": 3,
    "周五": 4, "礼拜五": 4, "上周五": 4,
    "周六": 5, "礼拜六": 5, "上周六": 5,
    "周日": 6, "周天": 6, "礼拜天": 6, "上周日": 6,
}
_MEAL_HINTS: tuple[tuple[str, str], ...] = (
    ("午饭", "lunch"), ("中饭", "lunch"), ("午餐", "lunch"),
    ("晚饭", "dinner"), ("夜宵", "dinner"), ("晚餐", "dinner"),
    ("早饭", "lunch"),  # 我们没有 breakfast meal_type, 用 lunch 兜底 (brief 未指定)
)


def parse_reference_text(text: str) -> ReferenceQuery | None:
    """从 refine 自由文本中解析 reference 表达. 命中返 ReferenceQuery, 否则 None.

    简单 substring 模式, 不引入 LLM. 多 slot LLM 抽取 (T-P1a-03 follow-up) 走完
    后, RefineIntentV2.reference 可直接绕过本 parse 走 resolve.
    """
    if not text:
        return None
    relation = _detect_relation(text)
    if relation == "unknown" and not _has_time_reference(text):
        # 既无时间词也无关系词, 不是 reference 表达
        return None
    days_back = _extract_days_back(text)
    meal_hint = _extract_meal_hint(text)
    if days_back is None and meal_hint is None and relation == "unknown":
        return None
    return ReferenceQuery(
        raw_text=text.strip(),
        relation=relation,
        days_back=days_back,
        meal_hint=meal_hint,
    )


def _detect_relation(text: str) -> str:
    # 优先级: lighter > diff_venue > similar > unknown
    for kw in _LIGHTER_KEYWORDS:
        if re.search(kw, text):
            return "lighter"
    for kw in _DIFF_VENUE_KEYWORDS:
        if kw in text:
            return "similar_but_different_venue"
    for kw in _SIMILAR_KEYWORDS:
        if kw in text:
            return "similar"
    return "unknown"


def _has_time_reference(text: str) -> bool:
    for kw, _ in _DAYS_BACK_PATTERNS:
        if kw in text:
            return True
    for kw in _WEEKDAYS:
        if kw in text:
            return True
    if "上次" in text or "上一次" in text or "上回" in text:
        return True
    return False


def _extract_days_back(text: str) -> int | None:
    """简单 substring 优先级: 前天 > 昨天 > 上周 X > 上次 → None (走最近)."""
    for kw, days in _DAYS_BACK_PATTERNS:
        if kw in text:
            return days
    # 上周 X: 算从今天向前的天数 — 此处不直接算 (resolve 时按 weekday 找)
    for kw in _WEEKDAYS:
        if kw in text:
            return -1  # sentinel: 按 weekday 查最近
    if "上次" in text or "上一次" in text or "上回" in text:
        return -2  # sentinel: 取 list 中最近一条
    return None


def _extract_meal_hint(text: str) -> str | None:
    for kw, meal in _MEAL_HINTS:
        if kw in text:
            return meal
    return None


# ────────────────────────── resolve layer


def _load_base_final(trace_store, sid: str, root: Optional[Path]):
    """读历史 session 的 final combos + meal_type, v2/v3 布局通吃。

    D-104 债务修复: resolve_reference 旧用 read_trace (只读平铺 v2 单文件), 对 refine 后
    迁成 v3 目录的 session 返 None → 引用解析不到。这里 v3 优先 (read_meta + 最新已发布
    round 的 final), v2 回退 read_trace。session 完全不可读返 (None, None) 让上游降级。

    返 (final_combos | None, frozen_meal_type | None)。
    """
    meta = trace_store.read_meta(sid, root=root)
    if meta is not None:
        latest = meta.get("latest_round") or "R1"
        rd = trace_store.read_round_full(sid, latest, root=root)
        if rd is None:
            return None, None
        return (rd.get("final") or []), meta.get("meal_type")
    base_trace = trace_store.read_trace(sid, root=root)
    if base_trace is None:
        return None, None
    return (base_trace.get("final") or []), base_trace.get("__frozen", {}).get("meal_type")


def resolve_reference(
    query: ReferenceQuery,
    *,
    today: dt.date,
    root: Optional[Path] = None,
) -> ResolvedReference | None:
    """从 trace_store 查找匹配的历史会话.

    策略:
      - days_back > 0: 找当天向前 days_back 天的 session, meal_hint 匹配
      - days_back == -1 (weekday sentinel): 找最近一周内最近 weekday 命中
      - days_back == -2 (上次 sentinel): list_traces 取最近一条 (meal_hint 优先)
      - days_back is None + meal_hint: 仅按 meal_hint 找最近一条
      - 没匹配返 None
    """
    from chisha import trace_store

    # D-104 债务修复: 用 v3-aware lister, 否则 refine 后迁成 v3 目录的 session 发现不到。
    items, _ = trace_store.list_traces_v3(root=root, limit=100)
    if not items:
        return None
    # 解析 weekday 引用: 用 raw_text 重做一次
    target_weekday: int | None = None
    if query.days_back == -1:
        for kw, wd in _WEEKDAYS.items():
            if kw in query.raw_text:
                target_weekday = wd
                break

    def _started_date(it: dict) -> dt.date | None:
        s = it.get("started_at")
        if not s:
            return None
        try:
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except Exception:
            return None

    notes: list[str] = []
    chosen: dict | None = None

    if query.days_back == -2:
        # 上次: 第一条匹配 meal_hint
        for it in items:
            if query.meal_hint and it.get("meal_type") != query.meal_hint:
                continue
            chosen = it
            break
        if chosen is None and items:
            chosen = items[0]  # 完全 fallback
            notes.append("no meal_hint match, used most recent trace")
    elif query.days_back is not None and query.days_back >= 0:
        target_date = today - dt.timedelta(days=query.days_back)
        for it in items:
            if _started_date(it) == target_date:
                if query.meal_hint and it.get("meal_type") != query.meal_hint:
                    continue
                chosen = it
                break
        if chosen is None:
            notes.append(f"no trace on {target_date.isoformat()}")
    elif target_weekday is not None:
        # 最近一周内 weekday 命中
        for d in range(1, 8):
            cand_date = today - dt.timedelta(days=d)
            if cand_date.weekday() != target_weekday:
                continue
            for it in items:
                if _started_date(it) == cand_date:
                    if query.meal_hint and it.get("meal_type") != query.meal_hint:
                        continue
                    chosen = it
                    break
            if chosen:
                break
    elif query.meal_hint:
        for it in items:
            if it.get("meal_type") == query.meal_hint:
                chosen = it
                break

    if chosen is None:
        return None

    sid = chosen["session_id"]
    try:
        base_combos, frozen_meal = _load_base_final(trace_store, sid, root)
    except Exception:
        return None
    if base_combos is None:
        return None

    return ResolvedReference(
        base_session_id=sid,
        base_meal_type=chosen.get("meal_type") or frozen_meal or "",
        base_started_at=chosen.get("started_at") or "",
        base_combos=base_combos,
        relation=query.relation,
        raw_text=query.raw_text,
        notes=notes,
    )


# ────────────────────────── comparator layer


def apply_relation(
    candidates: list[dict],
    resolved: ResolvedReference,
) -> list[dict]:
    """根据 resolved.relation 软重排 candidates.

    返回新列表 (不修改原对象). 不抛, 找不到匹配时原样返.

    支持:
      - lighter: 按 combo avg_oil 升序 (低油在前). 油值缺失时排末.
      - similar_but_different_venue: 同 cuisine 主体, 但 restaurant_id 必须不同
        于 resolved.base_combos 的 restaurant. 命中保留, 否则排末.
      - similar: 同 cuisine, 同/不同店都行 (优先权重在 score 阶段)
      - unknown / 其他: 原样返
    """
    if not candidates:
        return candidates
    rel = resolved.relation

    if rel == "lighter":
        def _avg_oil(c: dict) -> float:
            dishes = c.get("dishes") or []
            ols = [d.get("nutrition_profile", {}).get("oil_level")
                   for d in dishes]
            ols = [x for x in ols if isinstance(x, (int, float))]
            if not ols:
                return 99.0  # 排末
            return sum(ols) / len(ols)
        return sorted(candidates, key=_avg_oil)

    if rel == "similar_but_different_venue":
        base_rest_ids = set()
        for bc in resolved.base_combos:
            rid = (bc.get("restaurant") or {}).get("id")
            if rid:
                base_rest_ids.add(rid)
        # 不在 base_rest_ids 的优先
        def _key(c: dict) -> tuple[int, ...]:
            rid = (c.get("restaurant") or {}).get("id")
            return (1 if rid in base_rest_ids else 0,)
        return sorted(candidates, key=_key)

    if rel == "similar":
        # 拿 base 主 cuisine
        base_cuisines: set[str] = set()
        for bc in resolved.base_combos:
            for d in (bc.get("dishes") or []):
                cu = d.get("cuisine")
                if cu:
                    base_cuisines.add(cu)
                    break
        if not base_cuisines:
            return candidates
        def _is_similar(c: dict) -> int:
            for d in (c.get("dishes") or []):
                if d.get("cuisine") in base_cuisines:
                    return 0
            return 1
        return sorted(candidates, key=_is_similar)

    return candidates

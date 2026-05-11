"""Context 注入层 (D-034).

每次推荐前生成 ContextSnapshot, 用作 L3 score 软调权 + L4 LLM rerank 的输入.
不做硬过滤, 不做选择 — 只是把"今天的情境"结构化打包.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Any


# 当日开场 1 问的可选值. None = 用户没回答 / 跳过.
DAILY_MOODS = {
    "want_light",        # 今天想清淡
    "want_indulgent",    # 今天想爽
    "want_soup",         # 今天想喝汤
    "low_carb",          # 今天主食少
    "want_clean",        # 今天不要加工 / 重口
    "neutral",           # 默认 / 跳过
}


@dataclass
class LastMeal:
    date: str                       # YYYY-MM-DD
    meal_type: str                  # lunch | dinner
    cuisine: str | None
    main_ingredient_type: str | None
    dish_names: list[str] = field(default_factory=list)


@dataclass
class FeedbackSummary:
    date: str
    chips: list[str] = field(default_factory=list)        # ["太油", "想喝汤"]
    rating_taste: int | None = None                       # 1-5
    rating_satisfaction: int | None = None                # 1-5
    want_again: bool | None = None
    note: str = ""


@dataclass
class ContextSnapshot:
    meal_type: str
    zone: str
    now: dt.datetime
    weekday: int                          # 0=Mon, 6=Sun
    last_meal: LastMeal | None
    recent_3d_cuisines: dict[str, int]    # {"川菜": 2, "湘菜": 1}
    recent_3d_ingredients: dict[str, int] # {"红肉": 3, "白肉": 1}
    last_feedback: FeedbackSummary | None
    daily_mood: str | None                # 见 DAILY_MOODS
    refine_input: str | None              # refine 二轮用户自然语言

    def to_llm_dict(self) -> dict[str, Any]:
        """LLM rerank prompt 用的扁平 dict, 去掉 dt 类型."""
        d = asdict(self)
        d["now"] = self.now.isoformat()
        return d


def _resolve_zone(profile: dict, meal_type: str) -> str:
    zones = profile.get("basics", {}).get("zones") or {}
    if meal_type in zones:
        return zones[meal_type]
    return profile["basics"]["office_zone"]


def _parse_log_date(entry: dict) -> dt.date:
    ts = entry.get("timestamp") or entry.get("date")
    if isinstance(ts, dt.date) and not isinstance(ts, dt.datetime):
        return ts
    if isinstance(ts, dt.datetime):
        return ts.date()
    if isinstance(ts, str):
        # 容忍 "2026-05-12" / "2026-05-12T12:15:00"
        return dt.date.fromisoformat(ts[:10])
    raise ValueError(f"无法解析 meal_log 日期: {entry!r}")


def _parse_log_datetime(entry: dict) -> dt.datetime:
    """精确到秒, 用于"最近一条"排序; 仅有日期时按当天 00:00:00."""
    ts = entry.get("timestamp") or entry.get("date")
    if isinstance(ts, dt.datetime):
        return ts
    if isinstance(ts, dt.date):
        return dt.datetime.combine(ts, dt.time())
    if isinstance(ts, str):
        return dt.datetime.fromisoformat(ts) if "T" in ts else dt.datetime.combine(
            dt.date.fromisoformat(ts), dt.time()
        )
    raise ValueError(f"无法解析 meal_log 时间: {entry!r}")


def _extract_last_meal(meal_log: list[dict], today: dt.date) -> LastMeal | None:
    """取 today 之前最近一条 meal_log."""
    candidates: list[tuple[dt.datetime, dict]] = []
    for e in meal_log:
        try:
            ts = _parse_log_datetime(e)
        except ValueError:
            continue
        if ts.date() < today:
            candidates.append((ts, e))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    ts, e = candidates[0]
    d = ts.date()
    cuisine = e.get("cuisine")
    main_ing = e.get("main_ingredient_type")
    # 兼容 V1 schema (dishes 列表)
    if not cuisine and e.get("dishes"):
        first = e["dishes"][0]
        cuisine = first.get("cuisine")
        main_ing = first.get("main_ingredient_type")
    dish_names = [d.get("canonical_name", "") for d in e.get("dishes", []) if d.get("canonical_name")]
    return LastMeal(
        date=d.isoformat(),
        meal_type=e.get("meal_type", ""),
        cuisine=cuisine,
        main_ingredient_type=main_ing,
        dish_names=dish_names,
    )


def _aggregate_recent(
    meal_log: list[dict],
    today: dt.date,
    days: int = 3,
) -> tuple[dict[str, int], dict[str, int]]:
    """聚合最近 N 天的 cuisine / main_ingredient_type 分布."""
    cutoff = today - dt.timedelta(days=days)
    cuisines: Counter[str] = Counter()
    ingredients: Counter[str] = Counter()
    for e in meal_log:
        try:
            d = _parse_log_date(e)
        except ValueError:
            continue
        if not (cutoff <= d < today):
            continue
        # 顶层字段优先, 退化到 dishes[0]
        c = e.get("cuisine")
        i = e.get("main_ingredient_type")
        if e.get("dishes"):
            for dish in e["dishes"]:
                if dish.get("cuisine"):
                    cuisines[dish["cuisine"]] += 1
                if dish.get("main_ingredient_type"):
                    ingredients[dish["main_ingredient_type"]] += 1
        else:
            if c:
                cuisines[c] += 1
            if i:
                ingredients[i] += 1
    return dict(cuisines), dict(ingredients)


def _extract_last_feedback(meal_log: list[dict], today: dt.date) -> FeedbackSummary | None:
    """取最近一条带 feedback 的 meal_log."""
    for e in sorted(
        (e for e in meal_log if e.get("feedback")),
        key=lambda x: _parse_log_datetime(x),
        reverse=True,
    ):
        try:
            d = _parse_log_date(e)
        except ValueError:
            continue
        if d >= today:
            continue
        fb = e["feedback"]
        return FeedbackSummary(
            date=d.isoformat(),
            chips=list(fb.get("chips") or []),
            rating_taste=fb.get("rating_taste"),
            rating_satisfaction=fb.get("rating_satisfaction"),
            want_again=fb.get("want_again"),
            note=fb.get("note", ""),
        )
    return None


def build_context(
    profile: dict,
    meal_log: list[dict],
    meal_type: str,
    today: dt.date | dt.datetime,
    daily_mood: str | None = None,
    refine_input: str | None = None,
    now: dt.datetime | None = None,
) -> ContextSnapshot:
    """生成本次推荐的 ContextSnapshot.

    Args:
        profile: 用户 profile (含 basics.zones).
        meal_log: 最近的 meal_log 条目 (jsonl 解析后的 list).
        meal_type: lunch | dinner.
        today: 当日, date 或 datetime 都可.
        daily_mood: 当日开场 1 问的回答, 见 DAILY_MOODS.
        refine_input: refine 二轮的用户自然语言, None=首轮.
        now: 注入当前时间, 默认 dt.datetime.now (便于测试 mock).
    """
    if daily_mood is not None and daily_mood not in DAILY_MOODS:
        raise ValueError(
            f"daily_mood 必须是 {sorted(DAILY_MOODS)} 之一, 收到 {daily_mood!r}"
        )
    today_d = today.date() if isinstance(today, dt.datetime) else today
    now = now or dt.datetime.now()
    cuisines, ingredients = _aggregate_recent(meal_log, today_d, days=3)
    return ContextSnapshot(
        meal_type=meal_type,
        zone=_resolve_zone(profile, meal_type),
        now=now,
        weekday=today_d.weekday(),
        last_meal=_extract_last_meal(meal_log, today_d),
        recent_3d_cuisines=cuisines,
        recent_3d_ingredients=ingredients,
        last_feedback=_extract_last_feedback(meal_log, today_d),
        daily_mood=daily_mood,
        refine_input=refine_input,
    )

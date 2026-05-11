"""context.py 单测."""
from __future__ import annotations

import datetime as dt

import pytest

from chisha.context import (
    DAILY_MOODS,
    ContextSnapshot,
    FeedbackSummary,
    LastMeal,
    build_context,
)


@pytest.fixture
def profile_with_zones():
    return {
        "basics": {
            "name": "test",
            "city": "深圳",
            "office_zone": "shenzhen-bay",
            "zones": {"lunch": "shenzhen-bay", "dinner": "home"},
        }
    }


@pytest.fixture
def empty_log():
    return []


@pytest.fixture
def rich_log():
    """3 天 meal_log: 周一川菜 / 周二湘菜 / 周三川菜+反馈."""
    return [
        {
            "timestamp": "2026-05-11T12:15:00",   # 周一
            "meal_type": "lunch",
            "cuisine": "川菜",
            "main_ingredient_type": "红肉",
            "dishes": [{"canonical_name": "水煮牛肉", "cuisine": "川菜",
                        "main_ingredient_type": "红肉"}],
        },
        {
            "timestamp": "2026-05-12T12:00:00",   # 周二
            "meal_type": "lunch",
            "cuisine": "湘菜",
            "main_ingredient_type": "白肉",
            "dishes": [{"canonical_name": "辣椒炒肉", "cuisine": "湘菜",
                        "main_ingredient_type": "白肉"}],
        },
        {
            "timestamp": "2026-05-12T18:30:00",   # 周二晚
            "meal_type": "dinner",
            "cuisine": "川菜",
            "main_ingredient_type": "海鲜",
            "dishes": [{"canonical_name": "酸菜鱼", "cuisine": "川菜",
                        "main_ingredient_type": "海鲜"}],
            "feedback": {
                "chips": ["太油"],
                "rating_taste": 3,
                "rating_satisfaction": 2,
                "want_again": False,
                "note": "明天想清淡点",
            },
        },
    ]


def test_zone_resolution_lunch(profile_with_zones, empty_log):
    ctx = build_context(profile_with_zones, empty_log, "lunch",
                        today=dt.date(2026, 5, 13))
    assert ctx.zone == "shenzhen-bay"


def test_zone_resolution_dinner(profile_with_zones, empty_log):
    ctx = build_context(profile_with_zones, empty_log, "dinner",
                        today=dt.date(2026, 5, 13))
    assert ctx.zone == "home"


def test_zone_fallback_to_office_zone(empty_log):
    profile_no_zones = {"basics": {"office_zone": "shenzhen-bay"}}
    ctx = build_context(profile_no_zones, empty_log, "lunch",
                        today=dt.date(2026, 5, 13))
    assert ctx.zone == "shenzhen-bay"


def test_empty_log_clean(profile_with_zones, empty_log):
    ctx = build_context(profile_with_zones, empty_log, "lunch",
                        today=dt.date(2026, 5, 13))
    assert ctx.last_meal is None
    assert ctx.recent_3d_cuisines == {}
    assert ctx.recent_3d_ingredients == {}
    assert ctx.last_feedback is None


def test_last_meal_extracted(profile_with_zones, rich_log):
    ctx = build_context(profile_with_zones, rich_log, "lunch",
                        today=dt.date(2026, 5, 13))
    assert ctx.last_meal is not None
    # 最近一条是周二晚 (酸菜鱼)
    assert ctx.last_meal.date == "2026-05-12"
    assert ctx.last_meal.meal_type == "dinner"
    assert ctx.last_meal.cuisine == "川菜"
    assert "酸菜鱼" in ctx.last_meal.dish_names


def test_recent_3d_aggregation(profile_with_zones, rich_log):
    ctx = build_context(profile_with_zones, rich_log, "lunch",
                        today=dt.date(2026, 5, 13))
    # 3 天窗口 (5/10, 5/11, 5/12) 内: 川菜x2 + 湘菜x1
    assert ctx.recent_3d_cuisines.get("川菜") == 2
    assert ctx.recent_3d_cuisines.get("湘菜") == 1
    assert ctx.recent_3d_ingredients.get("红肉") == 1
    assert ctx.recent_3d_ingredients.get("白肉") == 1
    assert ctx.recent_3d_ingredients.get("海鲜") == 1


def test_recent_3d_excludes_today(profile_with_zones):
    """today 当天的记录不应进入 recent_3d (今天还没吃)."""
    log = [{
        "timestamp": "2026-05-13T12:00:00",
        "meal_type": "lunch",
        "cuisine": "川菜",
        "dishes": [{"cuisine": "川菜"}],
    }]
    ctx = build_context({"basics": {"office_zone": "x"}}, log, "lunch",
                        today=dt.date(2026, 5, 13))
    assert ctx.recent_3d_cuisines == {}
    assert ctx.last_meal is None


def test_recent_3d_window_4days_ago_excluded(profile_with_zones):
    """4 天前的不应进入 3 天窗口."""
    log = [{
        "timestamp": "2026-05-09T12:00:00",  # 5 天前
        "meal_type": "lunch",
        "cuisine": "川菜",
        "dishes": [{"cuisine": "川菜"}],
    }]
    ctx = build_context(profile_with_zones, log, "lunch",
                        today=dt.date(2026, 5, 13))
    assert ctx.recent_3d_cuisines == {}


def test_last_feedback_extracted(profile_with_zones, rich_log):
    ctx = build_context(profile_with_zones, rich_log, "lunch",
                        today=dt.date(2026, 5, 13))
    assert ctx.last_feedback is not None
    assert ctx.last_feedback.date == "2026-05-12"
    assert "太油" in ctx.last_feedback.chips
    assert ctx.last_feedback.rating_taste == 3
    assert ctx.last_feedback.want_again is False


def test_daily_mood_validation(profile_with_zones, empty_log):
    for mood in DAILY_MOODS:
        ctx = build_context(profile_with_zones, empty_log, "lunch",
                            today=dt.date(2026, 5, 13), daily_mood=mood)
        assert ctx.daily_mood == mood


def test_daily_mood_invalid_raises(profile_with_zones, empty_log):
    with pytest.raises(ValueError, match="daily_mood"):
        build_context(profile_with_zones, empty_log, "lunch",
                      today=dt.date(2026, 5, 13), daily_mood="想吃辣")


def test_refine_input_passthrough(profile_with_zones, empty_log):
    ctx = build_context(profile_with_zones, empty_log, "lunch",
                        today=dt.date(2026, 5, 13),
                        refine_input="今天想喝汤别给我面")
    assert ctx.refine_input == "今天想喝汤别给我面"


def test_weekday_correct(profile_with_zones, empty_log):
    # 2026-05-13 是周三
    ctx = build_context(profile_with_zones, empty_log, "lunch",
                        today=dt.date(2026, 5, 13))
    assert ctx.weekday == 2


def test_to_llm_dict_serializable(profile_with_zones, rich_log):
    ctx = build_context(profile_with_zones, rich_log, "lunch",
                        today=dt.date(2026, 5, 13),
                        daily_mood="want_light",
                        now=dt.datetime(2026, 5, 13, 11, 25))
    d = ctx.to_llm_dict()
    import json
    s = json.dumps(d, ensure_ascii=False)   # 不该抛
    assert "want_light" in s
    assert "shenzhen-bay" in s


def test_today_as_datetime_works(profile_with_zones, empty_log):
    """today 传 datetime 也应 work."""
    ctx = build_context(profile_with_zones, empty_log, "lunch",
                        today=dt.datetime(2026, 5, 13, 11, 25))
    assert ctx.weekday == 2

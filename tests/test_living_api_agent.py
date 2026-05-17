"""D-085 PR-C: Living API agent-ready 参数.

覆盖:
- meal_hint 新参数 (agent 首选语义) 通过
- meal_type 老别名仍兼容 (apps/web 不破)
- 同时传 → meal_hint 优先
- at_time 可选, YYYY-MM-DD / ISO datetime / null
- 非法 meal_hint / at_time → 400
- JSON 响应自闭包 (含 session_id + candidates, 无隐含上下文)
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def living_app(tmp_path: Path, monkeypatch):
    """挂 api_living router, ROOT 隔离, mock recommend_meal 验入参."""
    from chisha import api_living

    monkeypatch.setattr(api_living, "ROOT", tmp_path)

    captured: dict = {}

    def fake_recommend(**kwargs):
        captured.update(kwargs)
        return {
            "session_id": "sid_test_001",
            "meal_type": kwargs.get("meal_type"),
            "zone": "shenzhen-bay",
            "round": 1,
            "version": "v2",
            "generated_at": "2026-05-17T12:00:00+00:00",
            "context": {},
            "stats": {"n_returned": 5},
            "candidates": [],
        }

    monkeypatch.setattr(api_living, "recommend_meal", fake_recommend)
    monkeypatch.setattr(api_living, "_remember_session_safe", lambda sid, out: None)

    app = FastAPI()
    app.include_router(api_living.router)
    return app, captured


# ─────────────────────── meal_hint
def test_meal_hint_lunch(living_app):
    app, captured = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend", params={"meal_hint": "lunch"})
        assert r.status_code == 200
        assert captured["meal_type"] == "lunch"
        assert captured["today"] is None
        body = r.json()
        assert body["session_id"] == "sid_test_001"


def test_meal_hint_dinner(living_app):
    app, captured = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend", params={"meal_hint": "dinner"})
        assert r.status_code == 200
        assert captured["meal_type"] == "dinner"


def test_meal_hint_invalid_400(living_app):
    app, _ = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend", params={"meal_hint": "breakfast"})
        assert r.status_code == 400
        assert "meal_hint" in r.text


# ─────────────────────── meal_type backward compat (apps/web 用)
def test_meal_type_legacy_alias(living_app):
    app, captured = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend", params={"meal_type": "lunch"})
        assert r.status_code == 200
        assert captured["meal_type"] == "lunch"


def test_no_meal_default_lunch(living_app):
    """不传任何 meal_* → 默认 lunch (与重构前行为一致)."""
    app, captured = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend")
        assert r.status_code == 200
        assert captured["meal_type"] == "lunch"


def test_meal_hint_overrides_meal_type_when_both(living_app):
    """同时传 → meal_hint 优先 (新参数优先于老 alias)."""
    app, captured = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend",
                   params={"meal_hint": "dinner", "meal_type": "lunch"})
        assert r.status_code == 200
        assert captured["meal_type"] == "dinner"


# ─────────────────────── at_time
def test_at_time_iso_date(living_app):
    app, captured = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend",
                   params={"meal_hint": "lunch", "at_time": "2026-06-15"})
        assert r.status_code == 200
        assert captured["today"] == dt.date(2026, 6, 15)


def test_at_time_iso_datetime(living_app):
    app, captured = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend",
                   params={"meal_hint": "lunch", "at_time": "2026-06-15T12:34:56+00:00"})
        assert r.status_code == 200
        assert captured["today"] == dt.date(2026, 6, 15)


def test_at_time_zulu_datetime(living_app):
    app, captured = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend",
                   params={"meal_hint": "lunch", "at_time": "2026-06-15T08:30:00Z"})
        assert r.status_code == 200
        assert captured["today"] == dt.date(2026, 6, 15)


def test_at_time_invalid_400(living_app):
    app, _ = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend",
                   params={"meal_hint": "lunch", "at_time": "tomorrow-ish"})
        assert r.status_code == 400
        assert "at_time" in r.text


# ─────────────────────── mood
def test_mood_passthrough(living_app):
    app, captured = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend",
                   params={"meal_hint": "lunch", "mood": "want_soup"})
        assert r.status_code == 200
        assert captured["daily_mood"] == "want_soup"


def test_mood_neutral_becomes_none(living_app):
    """neutral 视为 None, 与 mock-free 推荐链路一致."""
    app, captured = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend",
                   params={"meal_hint": "lunch", "mood": "neutral"})
        assert r.status_code == 200
        assert captured["daily_mood"] is None


# ─────────────────────── invariant 1: JSON 自闭包
def test_response_is_json_self_contained(living_app):
    app, _ = living_app
    with TestClient(app) as c:
        r = c.get("/api/recommend", params={"meal_hint": "lunch"})
        body = r.json()
        # 必含字段 (Agent 一次响应即可决策)
        for key in (
            "session_id", "meal_type", "zone", "round", "version",
            "generated_at", "stats", "candidates",
        ):
            assert key in body, f"agent-ready 响应缺字段: {key}"

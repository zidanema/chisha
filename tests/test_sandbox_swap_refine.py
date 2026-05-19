"""S-06c: /sandbox/sessions/{sid}/{swap,refine} 端点契约.

全程 ?mock_recommend=1, 不调 LLM/refine_session.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_sandbox(tmp_path: Path, monkeypatch):
    from chisha import web_api
    monkeypatch.setattr(web_api, "ROOT", tmp_path)
    monkeypatch.setattr(web_api, "PROFILE_PATH", tmp_path / "profile.yaml")
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: True)
    (tmp_path / "profile.yaml").write_text(
        "methodology: harvard_plate\nbasics: {office_zone: shenzhen-bay}\nllm: {provider: auto}\n",
        encoding="utf-8",
    )
    web_api._JOB_TABLE.clear()
    app = FastAPI()
    app.include_router(web_api.router)
    return app, tmp_path


def _bootstrap(c: TestClient, sid: str = "s1"):
    c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
    c.post("/api/sandbox/sessions", json={"sid": sid, "days": 7})
    c.post(f"/api/sandbox/sessions/{sid}/recs?mock_recommend=1", json={})


# ────────────────────────── /swap


def test_swap_keeps_meal_idx_mock(app_with_sandbox):
    """swap 不推进 meal_idx, 不动 history; last_recs 覆盖."""
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        old_last = json.loads((root / "logs/sandbox/sessions/s1/last_recs.json").read_text(encoding="utf-8"))
        old_sid = old_last["recommend_session_id"]
        r = c.post("/api/sandbox/sessions/s1/swap?mock_recommend=1", json={"exclude_ids": []})
    assert r.status_code == 200
    body = r.json()
    assert len(body["currentRecs"]) == 5
    assert body["recommend_session_id"] != old_sid   # 新 mock id
    # state 不变
    state = json.loads((root / "logs/sandbox/sessions/s1/state.json").read_text(encoding="utf-8"))
    assert state["current_meal_idx"] == 0
    # history 仍空
    assert not (root / "logs/sandbox/sessions/s1/history.json").exists()


def test_swap_excludes_filtered(app_with_sandbox):
    """exclude_ids 过滤掉指定 mock_rec_1."""
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        r = c.post(
            "/api/sandbox/sessions/s1/swap?mock_recommend=1",
            json={"exclude_ids": ["mock_rec_1", "mock_rec_2"]},
        )
    assert r.status_code == 200
    body = r.json()
    ids = [rec["id"] for rec in body["currentRecs"]]
    assert "mock_rec_1" not in ids
    assert "mock_rec_2" not in ids
    assert len(body["currentRecs"]) == 3


def test_swap_no_last_recs_404(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        # 不调 /recs
        r = c.post("/api/sandbox/sessions/s1/swap?mock_recommend=1", json={"exclude_ids": []})
    assert r.status_code == 404


def test_swap_disabled_409(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        c.post("/api/sandbox/disable")
        r = c.post("/api/sandbox/sessions/s1/swap?mock_recommend=1", json={"exclude_ids": []})
    assert r.status_code == 409


# ────────────────────────── /refine


def test_refine_writes_applied_refine_mock(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        r = c.post(
            "/api/sandbox/sessions/s1/refine?mock_recommend=1",
            json={"text": "想吃辣"},
        )
    assert r.status_code == 200
    body = r.json()
    assert len(body["currentRecs"]) == 5
    assert body["activeRules"]["refine"][0]["label"] == "想吃辣"
    assert body["activeRules"]["refine"][0]["sinceRound"] >= 2
    assert body["activeRules"]["blacklist"] == []
    # 落盘
    last = json.loads((root / "logs/sandbox/sessions/s1/last_recs.json").read_text(encoding="utf-8"))
    assert last["applied_refine"]["label"] == "想吃辣"


def test_refine_intent_in_recs(app_with_sandbox):
    """mock refine: intent 写入 text[:8]."""
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        r = c.post(
            "/api/sandbox/sessions/s1/refine?mock_recommend=1",
            json={"text": "今天想吃肉"},
        )
    body = r.json()
    for rec in body["currentRecs"]:
        assert rec["intent"] == "今天想吃肉"   # 前 8 char


def test_refine_then_advance_clears_recs(app_with_sandbox):
    """refine 后 eat → last_recs 删 → 下次 /recs 取的 applied_refine 为 None."""
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        c.post(
            "/api/sandbox/sessions/s1/refine?mock_recommend=1",
            json={"text": "想吃辣"},
        )
        c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 1})
        # 下顿 /recs
        r = c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
    body = r.json()
    assert body["applied_refine"] is None
    last = json.loads((root / "logs/sandbox/sessions/s1/last_recs.json").read_text(encoding="utf-8"))
    assert last["applied_refine"] is None


def test_refine_text_empty_422(app_with_sandbox):
    """text 必须非空."""
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        r = c.post(
            "/api/sandbox/sessions/s1/refine?mock_recommend=1",
            json={"text": ""},
        )
    assert r.status_code == 422


def test_refine_no_last_recs_404(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        r = c.post(
            "/api/sandbox/sessions/s1/refine?mock_recommend=1",
            json={"text": "想吃辣"},
        )
    assert r.status_code == 404


def test_refine_disabled_409(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        c.post("/api/sandbox/disable")
        r = c.post(
            "/api/sandbox/sessions/s1/refine?mock_recommend=1",
            json={"text": "想吃辣"},
        )
    assert r.status_code == 409

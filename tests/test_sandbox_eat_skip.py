"""S-06c: /sandbox/sessions/{sid}/{recs,eat,skip,jobs} 端点契约 + 异步.

全程 ?mock_recommend=1, 不调 LLM. 真实 LLM 路径靠 S-08 联调手测.
"""
from __future__ import annotations

import json
import time
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
    # 清 in-memory job table 避免测试间污染
    web_api._JOB_TABLE.clear()
    app = FastAPI()
    app.include_router(web_api.router)
    return app, tmp_path


def _bootstrap_session(c: TestClient, sid: str = "s1", days: int = 7) -> dict:
    """init + create s1 桶 (含 seeded state.json)."""
    c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
    r = c.post("/api/sandbox/sessions", json={"sid": sid, "days": days})
    assert r.status_code == 201, r.text
    return r.json()


# ────────────────────────── /recs


def test_recs_writes_last_recs_mock(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        r = c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["currentRecs"]) == 5
    assert data["meal_idx"] == 0
    assert data["recommend_session_id"].startswith("mock_")
    # last_recs.json 落盘
    last_p = root / "logs/sandbox/sessions/s1/last_recs.json"
    assert last_p.exists()
    saved = json.loads(last_p.read_text(encoding="utf-8"))
    assert saved["is_mock"] is True
    assert len(saved["currentRecs"]) == 5


def test_recs_meal_type_derives_from_idx(app_with_sandbox):
    app, root = app_with_sandbox
    # idx=1 → dinner
    with TestClient(app) as c:
        _bootstrap_session(c)
        # 手工把 state.current_meal_idx 改到 1
        state_p = root / "logs/sandbox/sessions/s1/state.json"
        s = json.loads(state_p.read_text(encoding="utf-8"))
        s["current_meal_idx"] = 1
        state_p.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
        r = c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
    assert r.status_code == 200
    assert r.json()["meal_idx"] == 1


def test_recs_disabled_sandbox_409(app_with_sandbox):
    """sandbox 整体 disable → 409."""
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        c.post("/api/sandbox/disable")
        r = c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
    assert r.status_code == 409


def test_recs_unknown_sid_404(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        r = c.post("/api/sandbox/sessions/ghost/recs?mock_recommend=1", json={})
    assert r.status_code == 404


# ────────────────────────── /eat


def test_eat_advances_and_starts_job(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
        r = c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "running"
    assert body["meal_idx_eaten"] == 0
    assert body["new_meal_idx"] == 1
    assert "job_id" in body
    # state 推进
    state = json.loads((root / "logs/sandbox/sessions/s1/state.json").read_text(encoding="utf-8"))
    assert state["current_meal_idx"] == 1
    # history 落盘
    history = json.loads((root / "logs/sandbox/sessions/s1/history.json").read_text(encoding="utf-8"))
    assert history[0]["state"] == "eat"
    assert history[0]["idx"] == 0
    assert history[0]["rank"] == 1
    # meal_to_trace 落盘
    m2t = json.loads((root / "logs/sandbox/sessions/s1/meal_to_trace.json").read_text(encoding="utf-8"))
    assert "0" in m2t
    # last_recs.json 已删
    assert not (root / "logs/sandbox/sessions/s1/last_recs.json").exists()


def test_eat_job_completes_to_done(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
        r = c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 1})
        job_id = r.json()["job_id"]
        # TestClient with 块退出会 join BG tasks; 但 BG 通过 background_tasks.add_task
        # 在 response 返回后跑, 退出 with 时已完成.
    # 退出 with 后 poll job
    with TestClient(app) as c2:
        r2 = c2.get(f"/api/sandbox/sessions/s1/jobs/{job_id}")
    assert r2.status_code == 200
    info = r2.json()
    assert info["status"] == "done", info
    assert "decision" in info["result"]
    # decision 文件落盘
    decision_p = root / "logs/sandbox/sessions/s1/decisions/0.json"
    assert decision_p.exists()
    d = json.loads(decision_p.read_text(encoding="utf-8"))
    assert d["when"] == "D1 午"
    assert d["pick"].startswith("蓉香记")


def test_eat_invalid_rank_400(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
        r = c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 99})
    # Pydantic ge/le check → 422; FastAPI 自带
    assert r.status_code in (400, 422)


def test_eat_no_last_recs_404(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        r = c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 1})
    assert r.status_code == 404


def test_eat_disabled_sandbox_409(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
        c.post("/api/sandbox/disable")
        r = c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 1})
    assert r.status_code == 409


# ────────────────────────── /skip


def test_skip_synchronous(app_with_sandbox):
    """skip 不启 BG task, decision 同步落盘."""
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        r = c.post("/api/sandbox/sessions/s1/skip", json={"reason": "social"})
    assert r.status_code == 200
    body = r.json()
    assert body["meal_idx_skipped"] == 0
    assert body["new_meal_idx"] == 1
    assert body["decision"]["pick"] == "(跳过)"
    # decision 文件存在
    assert (root / "logs/sandbox/sessions/s1/decisions/0.json").exists()
    # history
    history = json.loads((root / "logs/sandbox/sessions/s1/history.json").read_text(encoding="utf-8"))
    assert history[0]["state"] == "skip"
    assert history[0]["reason"] == "social"


def test_skip_invalid_reason_422(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        r = c.post("/api/sandbox/sessions/s1/skip", json={"reason": "bogus"})
    assert r.status_code == 422


def test_skip_no_reason_ok(app_with_sandbox):
    """reason 为 None 也合法."""
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        r = c.post("/api/sandbox/sessions/s1/skip", json={})
    assert r.status_code == 200


# ────────────────────────── full 14 顿 + done sentinel


def test_full_14_meals_mock(app_with_sandbox):
    """循环 14 顿 mock /recs + /eat, 第 15 次 raise done."""
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c, days=7)  # 14 meals
        for i in range(14):
            r1 = c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
            assert r1.status_code == 200, f"recs idx={i}: {r1.text}"
            r2 = c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 1})
            assert r2.status_code == 200, f"eat idx={i}: {r2.text}"
        # 14 顿吃完, current_meal_idx == 14 == total → done sentinel
        state = json.loads((root / "logs/sandbox/sessions/s1/state.json").read_text(encoding="utf-8"))
        assert state["current_meal_idx"] == 14
        # 第 15 次 /recs → 409
        r3 = c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
        assert r3.status_code == 409


# ────────────────────────── /jobs


def test_jobs_unknown_404(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        r = c.get("/api/sandbox/sessions/s1/jobs/ghost")
    assert r.status_code == 404


def test_jobs_localhost_only(app_with_sandbox, monkeypatch):
    app, _ = app_with_sandbox
    from chisha import web_api
    with TestClient(app) as c:
        _bootstrap_session(c)
        c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
        r1 = c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 1})
        job_id = r1.json()["job_id"]
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: False)
    with TestClient(app) as c:
        r = c.get(f"/api/sandbox/sessions/s1/jobs/{job_id}")
    assert r.status_code == 403


# ────────────────────────── concurrent sid isolation


def test_eat_concurrent_sids_isolated(app_with_sandbox):
    """两个 sid 独立 advance, history / meal_to_trace 不串."""
    app, root = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        c.post("/api/sandbox/sessions", json={"sid": "s2"})
        # s1 吃 3 顿
        for _ in range(3):
            c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
            c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 1})
        # s2 吃 1 顿
        c.post("/api/sandbox/sessions/s2/recs?mock_recommend=1", json={})
        c.post("/api/sandbox/sessions/s2/eat", json={"rec_rank": 2})
    s1_state = json.loads((root / "logs/sandbox/sessions/s1/state.json").read_text(encoding="utf-8"))
    s2_state = json.loads((root / "logs/sandbox/sessions/s2/state.json").read_text(encoding="utf-8"))
    assert s1_state["current_meal_idx"] == 3
    assert s2_state["current_meal_idx"] == 1
    s1_history = json.loads((root / "logs/sandbox/sessions/s1/history.json").read_text(encoding="utf-8"))
    s2_history = json.loads((root / "logs/sandbox/sessions/s2/history.json").read_text(encoding="utf-8"))
    assert len(s1_history) == 3
    assert len(s2_history) == 1
    assert s2_history[0]["rank"] == 2   # s2 选了 rank=2 不是 s1 的 rank=1


# ────────────────────────── default sid pass-through


def test_eat_default_sid_works(app_with_sandbox):
    """sid='_default' 走 flat default 桶."""
    app, root = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        # default 桶用 init 创的 state.json (含 current_meal_idx? 现有 init 不写, 需要 fallback)
        # init() 不写 current_meal_idx — 用 .get 默认 0; OK
        # 但 default state 也没 total_meals — _ensure_not_done .get(...,14) 兜底
        c.post("/api/sandbox/sessions/_default/recs?mock_recommend=1", json={})
        r = c.post("/api/sandbox/sessions/_default/eat", json={"rec_rank": 1})
    assert r.status_code == 200, r.text
    assert (root / "logs/sandbox/history.json").exists()


# ────────────────────────── /eat failure: BG task ContextVar wrap


def test_eat_bg_task_decision_uses_mock_picked(app_with_sandbox):
    """eat rec_rank=2 (海记) → decision.pick = '海记...'."""
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap_session(c)
        c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
        r = c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 2})
        job_id = r.json()["job_id"]
    with TestClient(app) as c2:
        r2 = c2.get(f"/api/sandbox/sessions/s1/jobs/{job_id}")
    info = r2.json()
    assert info["status"] == "done"
    assert "海记" in info["result"]["decision"]["pick"]

"""D-077 PR-1c: /api/sandbox/* 端点单测.

覆盖:
- init / advance / reset / disable / state / inspect 5+1 端点
- localhost 鉴权 (非 localhost 403)
- copy_real_data=True 拷贝 prod 数据
- advance 触发异步 L1 抽取 (fake LLM, 验证 state.last_l1_extraction 写入)
- inspect 返回 prefs + 最近反馈 + meal_log
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
    """注入 ROOT 指向 tmp_path. 默认 _is_localhost=True (TestClient)."""
    from chisha import web_api
    monkeypatch.setattr(web_api, "ROOT", tmp_path)
    monkeypatch.setattr(web_api, "PROFILE_PATH", tmp_path / "profile.yaml")
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: True)
    monkeypatch.delenv("CHISHA_ADMIN_TOKEN", raising=False)
    # prod profile.yaml
    (tmp_path / "profile.yaml").write_text(
        "methodology: harvard_plate\nbasics: {office_zone: shenzhen-bay}\nllm: {provider: auto}\n",
        encoding="utf-8",
    )
    app = FastAPI()
    app.include_router(web_api.router)
    return app, tmp_path


# ─────────────────────── 鉴权
def test_sandbox_endpoints_reject_non_localhost(app_with_sandbox, monkeypatch):
    app, _ = app_with_sandbox
    from chisha import web_api
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: False)
    with TestClient(app) as c:
        assert c.post("/api/sandbox/init", json={}).status_code == 403
        assert c.post("/api/sandbox/advance", json={}).status_code == 403
        assert c.post("/api/sandbox/reset").status_code == 403
        assert c.get("/api/sandbox/state").status_code == 403
        assert c.get("/api/sandbox/inspect").status_code == 403


# ─────────────────────── init
def test_init_default_start_date(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        r = c.post("/api/sandbox/init", json={})
        assert r.status_code == 200
        s = r.json()
        assert s["enabled"] is True
        assert s["day_index"] == 1


def test_init_explicit_start_date(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        r = c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        assert r.status_code == 200
        assert r.json()["current_date"] == "2026-05-20"


def test_init_copy_real_data(app_with_sandbox):
    app, root = app_with_sandbox
    # prod 准备数据
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "long_term_prefs.json").write_text(
        '{"boost": ["wetness"], "penalty": [], "version": 1}',
        encoding="utf-8",
    )
    with TestClient(app) as c:
        r = c.post("/api/sandbox/init",
                    json={"start_date": "2026-05-20", "copy_real_data": True})
        assert r.status_code == 200
    # sandbox 副本存在
    sandbox_prefs = root / "logs" / "sandbox" / "long_term_prefs.json"
    assert sandbox_prefs.exists()
    assert "wetness" in sandbox_prefs.read_text(encoding="utf-8")


# ─────────────────────── advance
def test_advance_increments_day(app_with_sandbox, monkeypatch):
    app, root = app_with_sandbox
    # 不真的调 LLM, mock extract_and_save 不报错
    from chisha import l1_extractor
    monkeypatch.setattr(
        l1_extractor, "extract_and_save",
        lambda *a, **kw: {"boost": [], "penalty": [], "based_on_meals": 0},
    )
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.post("/api/sandbox/advance", json={"days": 3})
        assert r.status_code == 200
        s = r.json()
        assert s["current_date"] == "2026-05-23"
        assert s["day_index"] == 4


def test_advance_without_init_400(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        r = c.post("/api/sandbox/advance", json={"days": 1})
        assert r.status_code == 400


def test_advance_triggers_l1_extraction(app_with_sandbox, monkeypatch):
    app, root = app_with_sandbox
    calls = []

    def fake_extract(store, profile, **kw):
        calls.append(("called", kw.get("root")))
        return {"boost": ["low_oil"], "penalty": [],
                "based_on_meals": 5, "extracted_at": "2026-05-21T00:00:00"}

    from chisha import l1_extractor
    monkeypatch.setattr(l1_extractor, "extract_and_save", fake_extract)

    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/advance", json={"days": 1})

    # 等异步抽取完成
    time.sleep(0.3)
    assert len(calls) >= 1

    # state 应该有 last_l1_extraction
    with TestClient(app) as c:
        s = c.get("/api/sandbox/state").json()
    assert s.get("last_l1_extraction", {}).get("status") == "ok"


# ─────────────────────── reset / disable
def test_reset_clears_data(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/reset")
        assert c.get("/api/sandbox/state").json()["enabled"] is False


def test_disable_preserves_data(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/disable")
        s = c.get("/api/sandbox/state").json()
        assert s["enabled"] is False
        # state 文件还在
        assert (root / "logs" / "sandbox" / "state.json").exists()


# ─────────────────────── state / inspect
def test_state_when_disabled(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        r = c.get("/api/sandbox/state")
        assert r.status_code == 200
        assert r.json() == {"enabled": False}


def test_inspect_when_disabled(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        r = c.get("/api/sandbox/inspect")
        assert r.status_code == 200
        assert r.json() == {"enabled": False}


def test_inspect_enabled_returns_data(app_with_sandbox, monkeypatch):
    app, root = app_with_sandbox
    # 写一份 prefs 到 sandbox path
    sandbox_prefs_dir = root / "logs" / "sandbox"
    sandbox_prefs_dir.mkdir(parents=True, exist_ok=True)
    (sandbox_prefs_dir / "long_term_prefs.json").write_text(
        '{"boost": ["low_oil"], "penalty": [], "version": 1,'
        ' "based_on_meals": 5}',
        encoding="utf-8",
    )
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.get("/api/sandbox/inspect")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    assert data["long_term_prefs"]["boost"] == ["low_oil"]
    assert "state" in data

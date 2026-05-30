"""S-06a: /api/sandbox/inspect 三态.

| state | 触发条件 | 返回 |
| no-layout | not has_sandbox_meta + not is_enabled | enabled=F, has_layout=F, sessions=[] |
| layout-disabled | has_sandbox_meta + not is_enabled | enabled=F, has_layout=T, sessions=[...] |
| layout-enabled | is_enabled | 原 snapshot + has_layout=T + sessions=[...] |
"""
from __future__ import annotations

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
    app = FastAPI()
    app.include_router(web_api.router)
    return app, tmp_path


def test_no_layout(app_with_sandbox):
    """全新 tmp_root → 无 _meta.json + 无 state → no-layout."""
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        r = c.get("/api/sandbox/inspect")
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "has_layout": False, "sessions": []}


def test_layout_disabled_after_init_disable(app_with_sandbox):
    """v2 修订 B: init → disable. _meta.json 由 init 写入, disable 不删 → layout-disabled."""
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/disable")
        r = c.get("/api/sandbox/inspect")
    data = r.json()
    assert data["enabled"] is False
    assert data["has_layout"] is True
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["sid"] == "_default"


def test_layout_disabled_with_non_default(app_with_sandbox):
    """init + create s1 + disable → sessions 含 default + s1."""
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        c.post("/api/sandbox/disable")
        r = c.get("/api/sandbox/inspect")
    data = r.json()
    assert data["enabled"] is False
    assert data["has_layout"] is True
    sids = [s["sid"] for s in data["sessions"]]
    assert sids == ["_default", "s1"]


def test_layout_enabled(app_with_sandbox):
    """init → GET → 既有 enabled:True snapshot + 新字段 has_layout/sessions."""
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.get("/api/sandbox/inspect")
    data = r.json()
    assert data["enabled"] is True
    assert data["has_layout"] is True
    assert "sessions" in data
    assert data["sessions"][0]["sid"] == "_default"
    # 老字段保留
    assert "state" in data
    assert "long_term_prefs_raw" in data


def test_layout_enabled_with_non_default_sessions(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        c.post("/api/sandbox/sessions", json={"sid": "s2"})
        r = c.get("/api/sandbox/inspect")
    data = r.json()
    assert data["enabled"] is True
    sids = [s["sid"] for s in data["sessions"]]
    assert sids == ["_default", "s1", "s2"]


def test_inspect_localhost_only(tmp_path: Path, monkeypatch):
    from chisha import web_api
    monkeypatch.setattr(web_api, "ROOT", tmp_path)
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: False)
    app = FastAPI()
    app.include_router(web_api.router)
    with TestClient(app) as c:
        assert c.get("/api/sandbox/inspect").status_code == 403

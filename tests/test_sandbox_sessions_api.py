"""S-06a: sandbox sessions CRUD 端点契约测试.

覆盖:
- list (含 mixed-namespace discriminator)
- create (含 reserved / invalid / no-layout / existing 失败)
- delete (含 default forbid / non-existent)
- rename (含 collision / same-sid / default forbid)
- localhost gate
- D-039 default-bucket recommend-session 文件不被混入 / 不被破坏
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


# ────────────────────────── list


def test_list_empty_sandbox(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        r = c.get("/api/sandbox/sessions")
    assert r.status_code == 200
    data = r.json()
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["sid"] == "_default"
    assert data["sessions"][0]["is_default"] is True
    assert data["sessions"][0]["created_at"] is None
    assert data["sessions"][0]["size_bytes"] == 0
    assert data["sessions"][0]["has_state"] is False


def test_list_with_layout(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        c.post("/api/sandbox/sessions", json={"sid": "s2"})
        r = c.get("/api/sandbox/sessions")
    assert r.status_code == 200
    data = r.json()
    sids = [s["sid"] for s in data["sessions"]]
    assert sids == ["_default", "s1", "s2"]
    assert data["sessions"][0]["is_default"] is True
    assert data["sessions"][1]["is_default"] is False


def test_list_mixed_namespace(app_with_sandbox):
    """v2 修订 A: logs/sandbox/sessions/ 下混合命名空间:
    - {uuid}.json (D-039 default 桶) → 跳
    - _legacy/ (S-05 备份) → 跳
    - bad/sid 不合法 char → 跳
    - s1/ → 返
    """
    app, root = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
    # 手工建 D-039 .json + _legacy/
    ssdir = root / "logs" / "sandbox" / "sessions"
    (ssdir / "abc-1234.json").write_text("{}", encoding="utf-8")
    (ssdir / "_legacy").mkdir(exist_ok=True)
    # 非法 sid 目录名 (含 / 不可能, 用 . 模拟)
    (ssdir / "bad.name").mkdir(exist_ok=True)
    with TestClient(app) as c:
        r = c.get("/api/sandbox/sessions")
    sids = [s["sid"] for s in r.json()["sessions"]]
    assert sids == ["_default", "s1"]


def test_init_then_create_session_ok(app_with_sandbox):
    """v2 修订 B: init 已 ensure _meta.json, POST /sessions 不再 400."""
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.post("/api/sandbox/sessions", json={"sid": "s1"})
    assert r.status_code == 201
    assert r.json()["sid"] == "s1"


def test_d039_default_sessions_untouched(app_with_sandbox):
    """v2 修订: 创/改/删 s1 后, default 桶 D-039 {uuid}.json 不动."""
    app, root = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
    # 手工建 D-039 文件
    d039 = root / "logs" / "sandbox" / "sessions" / "abc-1234.json"
    d039.parent.mkdir(parents=True, exist_ok=True)
    d039.write_text('{"meal":"lunch"}', encoding="utf-8")
    mtime0 = d039.stat().st_mtime_ns
    content0 = d039.read_text()
    with TestClient(app) as c:
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        c.post("/api/sandbox/sessions/s1/rename", json={"new_sid": "s1b"})
        c.delete("/api/sandbox/sessions/s1b")
    assert d039.exists()
    assert d039.read_text() == content0
    assert d039.stat().st_mtime_ns == mtime0


# ────────────────────────── create


def test_create_ok(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.post("/api/sandbox/sessions", json={"sid": "s1"})
    assert r.status_code == 201
    assert (root / "logs" / "sandbox" / "sessions" / "s1").is_dir()


def test_create_reserved_default(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.post("/api/sandbox/sessions", json={"sid": "_default"})
    assert r.status_code == 400


def test_create_reserved_legacy(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.post("/api/sandbox/sessions", json={"sid": "_legacy"})
    assert r.status_code == 400


def test_create_invalid_charset(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        # / 字符
        assert c.post("/api/sandbox/sessions", json={"sid": "foo/bar"}).status_code == 400
        # < 字符
        assert c.post("/api/sandbox/sessions", json={"sid": "<script>"}).status_code in (400, 422)
        # 超长 (65 chars)
        assert c.post("/api/sandbox/sessions", json={"sid": "a" * 65}).status_code in (400, 422)


def test_create_no_layout(app_with_sandbox):
    """layout 未建 (无 init, 无 _meta.json) → 400."""
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        # 不 init
        r = c.post("/api/sandbox/sessions", json={"sid": "s1"})
    assert r.status_code == 400
    assert "init" in r.text.lower() or "layout" in r.text.lower()


def test_create_existing(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        r = c.post("/api/sandbox/sessions", json={"sid": "s1"})
    assert r.status_code == 409


# ────────────────────────── delete


def test_delete_ok(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        r = c.delete("/api/sandbox/sessions/s1")
    assert r.status_code == 200
    assert not (root / "logs" / "sandbox" / "sessions" / "s1").exists()


def test_delete_default_forbid(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.delete("/api/sandbox/sessions/_default")
    assert r.status_code == 400


def test_delete_nonexistent(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.delete("/api/sandbox/sessions/neverwas")
    assert r.status_code == 404


# ────────────────────────── rename


def test_rename_ok(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        r = c.post("/api/sandbox/sessions/s1/rename", json={"new_sid": "s1b"})
    assert r.status_code == 200
    assert r.json()["sid"] == "s1b"
    assert not (root / "logs" / "sandbox" / "sessions" / "s1").exists()
    assert (root / "logs" / "sandbox" / "sessions" / "s1b").is_dir()


def test_rename_default_forbid(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        # old=_default
        r1 = c.post("/api/sandbox/sessions/_default/rename", json={"new_sid": "s1"})
        assert r1.status_code == 400
        # new=_default
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        r2 = c.post("/api/sandbox/sessions/s1/rename", json={"new_sid": "_default"})
        assert r2.status_code == 400


def test_rename_collision(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        c.post("/api/sandbox/sessions", json={"sid": "s2"})
        r = c.post("/api/sandbox/sessions/s1/rename", json={"new_sid": "s2"})
    assert r.status_code == 409


def test_rename_same_sid(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        r = c.post("/api/sandbox/sessions/s1/rename", json={"new_sid": "s1"})
    assert r.status_code == 400


# ────────────────────────── localhost gate


def test_localhost_reject(tmp_path: Path, monkeypatch):
    from chisha import web_api
    monkeypatch.setattr(web_api, "ROOT", tmp_path)
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: False)
    app = FastAPI()
    app.include_router(web_api.router)
    with TestClient(app) as c:
        assert c.get("/api/sandbox/sessions").status_code == 403
        assert c.post("/api/sandbox/sessions", json={"sid": "s1"}).status_code == 403
        assert c.delete("/api/sandbox/sessions/s1").status_code == 403
        assert c.post(
            "/api/sandbox/sessions/s1/rename", json={"new_sid": "s2"}
        ).status_code == 403

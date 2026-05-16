"""D-076 PR-0.9: /api/long_term_prefs/refresh 端点单测.

覆盖:
- localhost 鉴权 (LAN 拒)
- admin token (设了 env 时校验)
- force_run_without_llm=True 走 bootstrap
- LLM 抽取失败时 503
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_isolated_root(tmp_path: Path, monkeypatch):
    """注入 ROOT 指向 tmp_path, 避免污染真实仓库 data/."""
    from chisha import web_api
    # ROOT 是模块级常量, monkeypatch
    monkeypatch.setattr(web_api, "ROOT", tmp_path)
    monkeypatch.setattr(web_api, "PROFILE_PATH",
                         tmp_path / "profile.yaml")
    # 写一个最小 profile.yaml
    (tmp_path / "profile.yaml").write_text(
        "methodology: harvard_plate\nbasics: {office_zone: shenzhen-bay}\n",
        encoding="utf-8",
    )
    # 默认禁用 admin token
    monkeypatch.delenv("CHISHA_ADMIN_TOKEN", raising=False)

    app = FastAPI()
    app.include_router(web_api.router)
    return app


def test_refresh_rejects_non_localhost(app_with_isolated_root, monkeypatch):
    """非 localhost client.host → 403."""
    from chisha import web_api

    # 用 TestClient 时 client.host 默认是 "testclient", 不在 localhost 集合
    with TestClient(app_with_isolated_root) as c:
        r = c.post("/api/long_term_prefs/refresh",
                    json={"force_run_without_llm": True})
        assert r.status_code == 403
        assert "localhost-only" in r.text


def test_refresh_localhost_with_bootstrap(app_with_isolated_root, monkeypatch):
    """localhost + force_run_without_llm=True → 走 bootstrap, 不调 LLM."""
    # monkey-patch _is_localhost 返回 True (TestClient 模拟 localhost)
    from chisha import web_api
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: True)

    with TestClient(app_with_isolated_root) as c:
        r = c.post("/api/long_term_prefs/refresh",
                    json={"force_run_without_llm": True})
        assert r.status_code == 200
        data = r.json()
        assert "boost" in data
        assert "penalty" in data
        assert data.get("path") == "bootstrap_no_llm"


def test_refresh_admin_token_required_when_env_set(
    app_with_isolated_root, monkeypatch
):
    """env CHISHA_ADMIN_TOKEN 设了 → 必须传 X-Admin-Token, 不匹配 401."""
    from chisha import web_api
    monkeypatch.setenv("CHISHA_ADMIN_TOKEN", "secret-xyz")
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: True)

    with TestClient(app_with_isolated_root) as c:
        # 不带 token
        r = c.post("/api/long_term_prefs/refresh",
                    json={"force_run_without_llm": True})
        assert r.status_code == 401

        # 带错 token
        r = c.post("/api/long_term_prefs/refresh",
                    json={"force_run_without_llm": True},
                    headers={"X-Admin-Token": "wrong"})
        assert r.status_code == 401

        # 带对 token
        r = c.post("/api/long_term_prefs/refresh",
                    json={"force_run_without_llm": True},
                    headers={"X-Admin-Token": "secret-xyz"})
        assert r.status_code == 200


def test_refresh_llm_failure_returns_503(app_with_isolated_root, monkeypatch):
    """LLM extract_and_save 抛 RuntimeError → 端点返回 503."""
    from chisha import web_api
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: True)

    def fake_extract_and_save(*args, **kwargs):
        raise RuntimeError("L1 extract 失败 (尝试 2 次)")

    import chisha.l1_extractor as l1e
    monkeypatch.setattr(l1e, "extract_and_save", fake_extract_and_save)

    with TestClient(app_with_isolated_root) as c:
        r = c.post("/api/long_term_prefs/refresh", json={})
        assert r.status_code == 503
        assert "L1 extract" in r.text

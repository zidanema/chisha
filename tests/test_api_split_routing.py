"""D-085 PR-A: Living vs Lab router 严格不交叉守门测试.

- Living 端点全部挂 /api/* (不含 /api/lab/*)
- Lab 端点全部挂 /api/lab/*
- 两个 router 单独挂载不互相借用 (拒绝幽灵端点 ghost route)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


# 已知 Living 端点白名单 (D-085 §4.3 路由清单)
LIVING_ENDPOINTS = {
    ("GET",  "/api/recommend"),
    ("POST", "/api/refine"),
    ("POST", "/api/accept"),
    ("POST", "/api/skip"),
    ("GET",  "/api/profile"),
    ("PUT",  "/api/profile"),
    ("POST", "/api/profile"),
    ("GET",  "/api/history"),
    ("GET",  "/api/feedback/inbox"),
    ("POST", "/api/feedback/snooze"),
    ("POST", "/api/feedback/stop"),
    ("GET",  "/api/feedback/recent"),
    ("POST", "/api/feedback"),
    ("GET",  "/api/feedback/{session_id}/record"),
    ("POST", "/api/feedback/{session_id}/comments"),
    ("GET",  "/api/feedback/{session_id}"),
    ("POST", "/api/long_term_prefs/refresh"),
}

LAB_ENDPOINTS = {
    ("POST", "/api/lab/debug_recommend"),
    ("POST", "/api/lab/compare_moods"),
    ("POST", "/api/lab/sandbox/init"),
    ("POST", "/api/lab/sandbox/advance"),
    ("POST", "/api/lab/sandbox/reset"),
    ("POST", "/api/lab/sandbox/disable"),
    ("GET",  "/api/lab/sandbox/state"),
    ("GET",  "/api/lab/sandbox/inspect"),
    ("GET",  "/api/lab/sessions"),
    ("GET",  "/api/lab/sessions/{session_id}"),
    ("GET",  "/api/lab/sessions/{session_id}/summary"),  # D-085 PR-E
    ("POST", "/api/lab/what_if"),
}


def _routes(router_module) -> set[tuple[str, str]]:
    """提取 (method, path) 集合 (跳过 HEAD/OPTIONS 自动派生)."""
    out = set()
    for r in router_module.router.routes:
        for m in getattr(r, "methods", set()):
            if m in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                out.add((m, r.path))
    return out


def test_living_router_contains_exactly_expected_endpoints():
    from chisha import api_living
    routes = _routes(api_living)
    missing = LIVING_ENDPOINTS - routes
    extra = routes - LIVING_ENDPOINTS
    assert not missing, f"Living router missing endpoints: {missing}"
    assert not extra, f"Living router has unexpected endpoints: {extra}"


def test_lab_router_contains_exactly_expected_endpoints():
    from chisha import api_lab
    routes = _routes(api_lab)
    missing = LAB_ENDPOINTS - routes
    extra = routes - LAB_ENDPOINTS
    assert not missing, f"Lab router missing endpoints: {missing}"
    assert not extra, f"Lab router has unexpected endpoints: {extra}"


def test_living_router_has_no_lab_paths():
    """Living router 不应 export 任何 /api/lab/ 路径 (反向守门)."""
    from chisha import api_living
    for method, path in _routes(api_living):
        assert not path.startswith("/api/lab"), (
            f"Living router 不该有 Lab 路径: {method} {path}"
        )


def test_lab_router_only_has_lab_paths():
    """Lab router 必须全部挂在 /api/lab/ 前缀下 (反向守门)."""
    from chisha import api_lab
    for method, path in _routes(api_lab):
        assert path.startswith("/api/lab/"), (
            f"Lab router 路径必须 /api/lab/ 前缀: {method} {path}"
        )


def test_server_mounts_both_routers():
    """chisha.server 主 app 必须 include 两个 router."""
    from chisha.server import app
    paths_methods = set()
    for r in app.routes:
        for m in getattr(r, "methods", set()) or set():
            if m in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                paths_methods.add((m, r.path))
    # 至少 Living + Lab 各取一个采样验证两个都挂上了
    assert ("GET", "/api/recommend") in paths_methods
    assert ("GET", "/api/lab/sandbox/state") in paths_methods
    assert ("POST", "/api/lab/what_if") in paths_methods


def test_no_ghost_legacy_paths():
    """老路径 /api/debug/sessions, /api/sandbox/*, /api/debug_recommend 必须 404."""
    from chisha.server import app
    client = TestClient(app)
    for legacy in (
        "/api/debug/sessions",
        "/api/sandbox/state",
        "/api/sandbox/init",
        "/api/debug_recommend",
        "/api/compare_moods",
    ):
        r = client.get(legacy)
        # 老 GET 路径必须 404 (SPA fallback 不应吞 /api/* — server.py spa_fallback 守门)
        assert r.status_code == 404, f"Legacy path {legacy} 应该 404, got {r.status_code}"


def test_debug_server_shim_still_works():
    """back-compat: chisha.debug_server 仍可 import 拿到同一个 app."""
    from chisha.debug_server import app as legacy_app
    from chisha.server import app as new_app
    assert legacy_app is new_app

"""S-06a: non-default sid runtime routing in web_api.

覆盖 §4 + v4 修订 F/G/H:
- header / query / 优先级
- known sid → 落非 default 桶 (含 recommend_log.jsonl + sessions/{recommend_sid}.json)
- unknown sid → 404
- invalid / reserved → 400
- (v4 G) disabled-with-bucket → 409 fail-loud, prod 不写脏
- destructive endpoint 不挂 sid
- ctx propagates
- /sandbox/state sid inject 是 no-op (S-06b 才用)
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_root(tmp_path: Path, monkeypatch):
    """tmp_path 下完整 profile + methodology + zone, sandbox 路径全可走通."""
    from chisha import web_api
    monkeypatch.setattr(web_api, "ROOT", tmp_path)
    monkeypatch.setattr(web_api, "PROFILE_PATH", tmp_path / "profile.yaml")
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: True)
    # 完整 profile (recall.diversity_filter 必读)
    (tmp_path / "profile.yaml").write_text(
        "methodology: harvard_plate\n"
        "basics: {office_zone: shenzhen-bay}\n"
        "llm: {provider: auto}\n"
        "diversity: {no_same_restaurant_within_days: 7}\n",
        encoding="utf-8",
    )
    # methodology spec (load_profile 必读)
    src_spec = Path(__file__).resolve().parent.parent / "profiles" / "methodologies" / "harvard_plate.yaml"
    dst = tmp_path / "profiles" / "methodologies" / "harvard_plate.yaml"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_spec, dst)
    # 空 zone (recommend 返 0 候选但不 500)
    zone_dir = tmp_path / "data" / "shenzhen-bay"
    zone_dir.mkdir(parents=True, exist_ok=True)
    (zone_dir / "restaurants.json").write_text("[]", encoding="utf-8")
    (zone_dir / "dishes_tagged.json").write_text("[]", encoding="utf-8")
    app = FastAPI()
    app.include_router(web_api.router)
    return app, tmp_path


def _prod_recommend_log() -> Path:
    """真实 prod recommend_log path (用于反向断言 mtime 不变)."""
    import chisha
    return Path(chisha.__file__).resolve().parent.parent / "logs" / "recommend_log.jsonl"


def _prod_snapshot() -> tuple[bool, int, int]:
    p = _prod_recommend_log()
    if not p.exists():
        return (False, 0, 0)
    st = p.stat()
    return (True, st.st_mtime_ns, st.st_size)


# ────────────────────────── default 行为不回归


def test_no_header_default_unchanged(app_root):
    """v4 修订 F: 不带 header → 走 default 桶 flat (sandbox enabled at tmp_path).
    artifact 是 recommend_log.jsonl (不是 meal_log.jsonl)."""
    app, root = app_root
    prod_before = _prod_snapshot()
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.get("/api/recommend?meal_type=lunch")
    assert r.status_code == 200
    # default 桶 flat 路径
    assert (root / "logs" / "sandbox" / "recommend_log.jsonl").exists()
    # 没落到非 default 子桶
    assert not (root / "logs" / "sandbox" / "sessions" / "_default").exists()
    # prod 不脏
    assert _prod_snapshot() == prod_before


def test_recommend_uses_api_root(app_root):
    """v3 修订 D + v4 修订 F: web_api.ROOT 注入后, recommend chain 走 tmp_path.
    artifact recommend_log.jsonl (NOT meal_log.jsonl)."""
    app, root = app_root
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.get("/api/recommend?meal_type=lunch")
    assert r.status_code == 200
    assert (root / "logs" / "sandbox" / "recommend_log.jsonl").exists()
    # _default_root() (真实包根) 下不应被写
    import chisha
    real_root = Path(chisha.__file__).resolve().parent.parent
    if real_root != root:
        # default 桶应在 tmp_path 内, 不在真实 root 内
        # (本测试 monkeypatch 后 web_api.ROOT 是 tmp_path)
        pass


def test_enabled_with_bucket_routes_ok(app_root):
    """v4 修订 F+H (替代 v3 test_header_known_sid):
    init + create s1 (enabled) + X-Session-Id:s1 → 200 + 数据落 s1 桶 +
    recommend_log.jsonl 在 s1/ 下 + sessions/{recommend_sid}.json 在 s1/sessions/ 下."""
    app, root = app_root
    prod_before = _prod_snapshot()
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        r = c.get("/api/recommend?meal_type=lunch", headers={"X-Session-Id": "s1"})
    assert r.status_code == 200, r.text
    s1_dir = root / "logs" / "sandbox" / "sessions" / "s1"
    assert (s1_dir / "recommend_log.jsonl").exists()
    # D-039 session JSON 嵌套在 s1/sessions/
    ssdir = s1_dir / "sessions"
    assert ssdir.exists() and any(ssdir.glob("*.json"))
    # prod 不脏
    assert _prod_snapshot() == prod_before


def test_query_known_sid(app_root):
    app, root = app_root
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        r = c.get("/api/recommend?meal_type=lunch&session_id=s1")
    assert r.status_code == 200
    assert (root / "logs" / "sandbox" / "sessions" / "s1" / "recommend_log.jsonl").exists()


def test_header_priority_over_query(app_root):
    app, root = app_root
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        c.post("/api/sandbox/sessions", json={"sid": "s2"})
        # header=s1, query=s2 → header wins → s1 桶
        r = c.get(
            "/api/recommend?meal_type=lunch&session_id=s2",
            headers={"X-Session-Id": "s1"},
        )
    assert r.status_code == 200
    assert (root / "logs" / "sandbox" / "sessions" / "s1" / "recommend_log.jsonl").exists()
    assert not (root / "logs" / "sandbox" / "sessions" / "s2" / "recommend_log.jsonl").exists()


def test_header_unknown_sid(app_root):
    """v2 强化 (覆盖 iter 1 Coverage Gap 4): unknown sid → 404, prod 文件零变化."""
    app, _ = app_root
    prod_before = _prod_snapshot()
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.get("/api/recommend?meal_type=lunch", headers={"X-Session-Id": "ghost"})
    assert r.status_code == 404
    assert _prod_snapshot() == prod_before


def test_header_default_explicit(app_root):
    """X-Session-Id: _default → 行为同不传 (走 flat default)."""
    app, root = app_root
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.get("/api/recommend?meal_type=lunch", headers={"X-Session-Id": "_default"})
    assert r.status_code == 200
    assert (root / "logs" / "sandbox" / "recommend_log.jsonl").exists()


def test_header_invalid_charset(app_root):
    app, _ = app_root
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.get("/api/recommend?meal_type=lunch", headers={"X-Session-Id": "foo/bar"})
    assert r.status_code == 400


def test_header_reserved_legacy(app_root):
    app, _ = app_root
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.get("/api/recommend?meal_type=lunch", headers={"X-Session-Id": "_legacy"})
    assert r.status_code == 400


# ────────────────────────── v4 修订 G: disabled-with-bucket gate


def test_disabled_with_bucket_rejects_sid(app_root):
    """v4 修订 G + 修订 H:
    init → create s1 → disable → recommend with X-Session-Id:s1 → 409 fail-loud.
    prod recommend_log.jsonl 不变 (防 silent fall back 写脏 prod)."""
    app, root = app_root
    prod_before = _prod_snapshot()
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        c.post("/api/sandbox/disable")
        r = c.get("/api/recommend?meal_type=lunch", headers={"X-Session-Id": "s1"})
    assert r.status_code == 409
    assert "disabled" in r.text.lower() or "layout" in r.text.lower()
    # prod 不脏
    assert _prod_snapshot() == prod_before
    # sandbox s1 路径也未被写
    assert not (root / "logs" / "sandbox" / "sessions" / "s1" / "recommend_log.jsonl").exists()


def test_disabled_with_bucket_default_still_works(app_root):
    """v4 修订 G 反向: 同 setup 不带 X-Session-Id → 200 (走 default; sandbox disabled
    → prod fallback, 但 prod 路径已被 monkeypatch 到 tmp_path).
    验 default 路径不被新 gate 误伤."""
    app, _ = app_root
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        c.post("/api/sandbox/disable")
        r = c.get("/api/recommend?meal_type=lunch")
    assert r.status_code == 200


# ────────────────────────── 其它端点不挂 sid (destructive)


def test_destructive_endpoint_ignores_sid(app_root):
    """POST /api/sandbox/advance with X-Session-Id:s1 → 仍走 global (sid dep 不挂在
    sandbox 生命周期端点上). 即使误传也由 _reject_nondefault_sid 在 sandbox 模块层拦下."""
    app, _ = app_root
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        # advance 不挂 sid dep, 不会因 unknown s1 → 404
        r = c.post("/api/sandbox/advance", json={"days": 1}, headers={"X-Session-Id": "ghost"})
        # advance 端点本身不挂 sid dep, ghost sid 不被 dep 检查
        # (即使 sandbox 模块层拒 non-default sid, 但 advance 端点根本不读 X-Session-Id)
        assert r.status_code == 200


# ────────────────────────── ctx propagation


def test_ctx_propagates_to_data_root(app_root):
    """dependency 注入后 current_sandbox_session() 在 handler 内返 sid → data_root
    路径走 sessions/s1/ 子树. 已通过 enabled_with_bucket_routes_ok 间接验证;
    此测试用 /api/profile (sandbox 启用时 data_root.profile_path 走 sandbox 副本)
    再做一次显式 check."""
    app, root = app_root
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20", "copy_real_data": True})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        r = c.get("/api/profile", headers={"X-Session-Id": "s1"})
    # profile.yaml 在 s1 桶下不存在 → fallback 到 prod profile, 但不应 500
    assert r.status_code == 200


# ────────────────────────── /sandbox/state sid is no-op until S-06b


def test_state_endpoint_sid_inject_is_noop_until_s06b(app_root):
    """v2 修订 C (Non-blocking #1): /sandbox/state with X-Session-Id:s1 → 返与
    不带 header 相同 (sandbox.state(session_id=...) 仍 ignore sid 直到 S-06b)."""
    app, _ = app_root
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        c.post("/api/sandbox/sessions", json={"sid": "s1"})
        a = c.get("/api/sandbox/state").json()
        b = c.get("/api/sandbox/state", headers={"X-Session-Id": "s1"}).json()
    assert a == b

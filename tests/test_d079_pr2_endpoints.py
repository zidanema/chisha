"""D-079 PR-2: /api/debug/* 端点 happy path + failure matrix.

覆盖:
- GET /api/debug/sessions: 200 列表 + corrupt_count, 400 非法 source/meal_type
- GET /api/debug/sessions/{sid}: 200 单条 + feedback, 404 缺失, 409 schema, 500 corrupt
- POST /api/debug/what_if: 200 happy path, 404 base 不存在, 400 overrides 非法 / source
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chisha import api as api_module
from chisha import data_root, trace_store, web_api
from chisha.api import recommend_meal
from tests.conftest import make_dish, make_restaurant


@pytest.fixture
def app_root(tmp_path: Path, monkeypatch):
    """完整 TestClient: localhost bypass + ROOT 隔离 + 测试 fixture profile/zone."""
    profile = {
        "basics": {"office_zone": "test", "zones": {"lunch": "test", "dinner": "test"}},
        "taste_description": "喜欢汤水",
        "preferences": {
            "liked_cuisines": ["潮汕"], "disliked_cuisines": [],
            "avoid_dishes": [], "spicy_tolerance": 2,
        },
        "plate_rule": {
            "must_have_vegetable": True, "min_vegetable_dishes": 1,
            "min_protein_g": 25, "prefer_oil_level_at_most": 3, "hard_max_oil_level": 5,
        },
        "diversity": {"no_same_restaurant_within_days": 7,
                       "no_same_main_ingredient_within_days": 3},
        "recall": {"top_n": 100, "per_restaurant_max": 3, "min_monthly_sales": 10},
    }
    rests = [
        {**make_restaurant(rid="r1", name="潮汕汤店"),
         "office_zone": "test", "category": "潮汕"},
        {**make_restaurant(rid="r2", name="湘菜店"),
         "office_zone": "test", "category": "湘菜"},
    ]
    dishes = [
        make_dish(dish_id="d1_1", restaurant_id="r1", raw_name="潮汕牛肉汤",
                  canonical_name="潮汕牛肉汤", cuisine="潮汕",
                  main_ingredient_type="红肉", oil_level=2, protein_grams_estimate=35,
                  vegetable_ratio_estimate=0.1, wetness=3, dish_role="主菜",
                  monthly_sales=200),
        make_dish(dish_id="d1_2", restaurant_id="r1", raw_name="蒜蓉空心菜",
                  canonical_name="蒜蓉空心菜", cuisine="潮汕",
                  main_ingredient_type="纯素", oil_level=2,
                  vegetable_ratio_estimate=0.95, protein_grams_estimate=3,
                  dish_role="配菜", monthly_sales=180),
        make_dish(dish_id="d2_1", restaurant_id="r2", raw_name="辣椒炒肉",
                  canonical_name="辣椒炒肉", cuisine="湘菜",
                  main_ingredient_type="白肉", oil_level=4, protein_grams_estimate=30,
                  vegetable_ratio_estimate=0.2, dish_role="主菜", monthly_sales=150),
        make_dish(dish_id="d2_2", restaurant_id="r2", raw_name="炒油麦",
                  canonical_name="炒油麦菜", cuisine="湘菜",
                  main_ingredient_type="纯素", oil_level=3,
                  vegetable_ratio_estimate=0.9, protein_grams_estimate=3,
                  dish_role="配菜", monthly_sales=100),
    ]
    monkeypatch.setattr(api_module, "load_profile", lambda *a, **k: profile)
    monkeypatch.setattr(api_module, "load_zone_data",
                         lambda zone, root: (rests, dishes))
    monkeypatch.setattr(api_module, "load_meal_log", lambda root: [])

    monkeypatch.setattr(web_api, "ROOT", tmp_path)
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: True)

    app = FastAPI()
    app.include_router(web_api.router)
    return app, tmp_path


def _seed_trace(root: Path) -> str:
    """跑一次 recommend_meal, 返写盘的 sid."""
    out = recommend_meal(
        "lunch", today=dt.date(2026, 5, 13), log_to_file=False,
        use_llm_rerank=False, root=root,
    )
    return out["session_id"]


# ────────────────────────── GET /api/debug/sessions

def test_list_sessions_happy_path(app_root):
    app, root = app_root
    sid = _seed_trace(root)
    with TestClient(app) as c:
        r = c.get("/api/debug/sessions")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "items" in body and "corrupt_count" in body
        assert body["corrupt_count"] == 0
        sids = [it["session_id"] for it in body["items"]]
        assert sid in sids
        # 字段完整
        item = next(it for it in body["items"] if it["session_id"] == sid)
        assert item["meal_type"] == "lunch"
        assert item["source"] == "production"
        assert "top1_summary" in item
        assert "feedback" in item  # 即便 None 也存在


def test_list_sessions_filter_meal_type(app_root):
    app, root = app_root
    _seed_trace(root)
    with TestClient(app) as c:
        r = c.get("/api/debug/sessions", params={"meal_type": "dinner"})
        assert r.status_code == 200
        assert r.json()["items"] == []  # seed 是 lunch
        r = c.get("/api/debug/sessions", params={"meal_type": "lunch"})
        assert len(r.json()["items"]) >= 1


def test_list_sessions_400_invalid_source(app_root):
    app, _ = app_root
    with TestClient(app) as c:
        r = c.get("/api/debug/sessions", params={"source": "what_if_preview"})
        assert r.status_code == 400
        assert "production" in r.json()["detail"]


def test_list_sessions_400_invalid_meal_type(app_root):
    app, _ = app_root
    with TestClient(app) as c:
        r = c.get("/api/debug/sessions", params={"meal_type": "brunch"})
        assert r.status_code == 400


def test_list_sessions_corrupt_count(app_root):
    """损坏的 trace 跳过 + 计数, 不阻断列表."""
    app, root = app_root
    sid = _seed_trace(root)
    # 直接写一个非 JSON 文件
    bad = data_root.recommend_trace_dir(root) / "sess_lunch_99999999_999999_dead.json"
    bad.write_text("not json {{{", encoding="utf-8")
    with TestClient(app) as c:
        r = c.get("/api/debug/sessions")
        assert r.status_code == 200
        body = r.json()
        assert body["corrupt_count"] >= 1
        # 损坏的不在 items 里, 但好的 sid 还在
        sids = [it["session_id"] for it in body["items"]]
        assert sid in sids


# ────────────────────────── GET /api/debug/sessions/{sid}

def test_get_session_happy_path(app_root):
    app, root = app_root
    sid = _seed_trace(root)
    with TestClient(app) as c:
        r = c.get(f"/api/debug/sessions/{sid}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_id"] == sid
        assert body["__source"] == "production"
        assert body["__version"] == trace_store.TRACE_SCHEMA_VERSION
        assert "__frozen" in body
        assert "__feedback" in body  # None 也存在
        # frozen 子字段
        f = body["__frozen"]
        assert "today" in f and "ctx" in f and "l1_combos" in f
        assert "restaurants" in f and "dishes" in f
        assert "l1_prefs_snapshot" in f and "l2_meal_log_view" in f


def test_get_session_404(app_root):
    app, _ = app_root
    with TestClient(app) as c:
        r = c.get("/api/debug/sessions/nonexistent_sid_xyz")
        assert r.status_code == 404


def test_get_session_409_version_mismatch(app_root):
    app, root = app_root
    sid = _seed_trace(root)
    trace = trace_store.read_trace(sid, root=root)
    trace["__version"] = 999
    trace_store.write_trace(sid, trace, root=root)
    # write_trace 会自动 set __version=1, 所以直接写文件绕过
    p = data_root.recommend_trace_dir(root) / f"{sid}.json"
    obj = json.loads(p.read_text(encoding="utf-8"))
    obj["__version"] = 999
    p.write_text(json.dumps(obj), encoding="utf-8")
    with TestClient(app) as c:
        r = c.get(f"/api/debug/sessions/{sid}")
        assert r.status_code == 409
        assert "version mismatch" in r.json()["detail"].lower()


def test_get_session_500_corrupt(app_root):
    app, root = app_root
    sid = "sess_lunch_corrupt_test"
    p = data_root.recommend_trace_dir(root)
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{sid}.json").write_text("garbage{{{", encoding="utf-8")
    with TestClient(app) as c:
        r = c.get(f"/api/debug/sessions/{sid}")
        assert r.status_code == 500
        assert "corrupt" in r.json()["detail"].lower()


# ────────────────────────── POST /api/debug/what_if

def test_what_if_happy_path(app_root):
    app, root = app_root
    sid = _seed_trace(root)
    with TestClient(app) as c:
        r = c.post("/api/debug/what_if", json={
            "base_session_id": sid,
            "overrides": {},
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["__source"] == "what_if_preview"
        assert body["__parent_session_id"] == sid
        assert body["__llm_called"] is False
        assert len(body["final"]) >= 1


def test_what_if_404_base_missing(app_root):
    app, _ = app_root
    with TestClient(app) as c:
        r = c.post("/api/debug/what_if", json={
            "base_session_id": "does_not_exist",
            "overrides": {},
        })
        assert r.status_code == 404


def test_what_if_400_extra_overrides(app_root):
    """pydantic extra='forbid' 拦未知字段."""
    app, root = app_root
    sid = _seed_trace(root)
    with TestClient(app) as c:
        r = c.post("/api/debug/what_if", json={
            "base_session_id": sid,
            "overrides": {"hack_frozen_today": "2099-01-01"},
        })
        assert r.status_code == 422  # pydantic 422, 不是 400 (FastAPI 默认行为)
        # 422 也是合法拒绝, 关键是不让请求过


def test_what_if_overrides_type_validation(app_root):
    """pydantic 类型校验拦非法类型."""
    app, root = app_root
    sid = _seed_trace(root)
    with TestClient(app) as c:
        r = c.post("/api/debug/what_if", json={
            "base_session_id": sid,
            "overrides": {"n_return": "five"},
        })
        assert r.status_code == 422


def test_get_session_legacy_no_frozen(app_root):
    """Codex PR-2 DEFER #6: 老 trace (合法 __version 但无 __frozen) Replay 仍可访问."""
    app, root = app_root
    # 手写一个 pre-D079 形态的 trace (version 1 但无 __frozen, l2/l3 仍有)
    legacy_sid = "sess_lunch_legacy_20240101_120000_0000"
    legacy = {
        "__version": trace_store.TRACE_SCHEMA_VERSION,
        "__source": "production",
        "session_id": legacy_sid,
        "started_at": "2024-01-01T12:00:00+00:00",
        "l1": {"summary": "legacy"},
        "l2": {"summary": {"n_scored": 0}},
        "l3": {"status": "skipped"},
        "final": [],
    }
    trace_store.write_trace(legacy_sid, legacy, root=root)
    with TestClient(app) as c:
        r = c.get(f"/api/debug/sessions/{legacy_sid}")
        assert r.status_code == 200, r.text
        # __frozen 缺失也能返
        body = r.json()
        assert body["session_id"] == legacy_sid
        # __feedback 仍 attach
        assert "__feedback" in body


def test_what_if_400_legacy_no_frozen(app_root):
    """老 trace 无 __frozen → What-if 显式返 400 (而非 5xx 内部错)."""
    app, root = app_root
    legacy_sid = "sess_lunch_nofrozen_20240101"
    legacy = {
        "__version": trace_store.TRACE_SCHEMA_VERSION,
        "__source": "production",
        "session_id": legacy_sid,
        "started_at": "2024-01-01T12:00:00+00:00",
        "l1": {}, "l2": {}, "l3": {}, "final": [],
    }
    trace_store.write_trace(legacy_sid, legacy, root=root)
    with TestClient(app) as c:
        r = c.post("/api/debug/what_if", json={
            "base_session_id": legacy_sid, "overrides": {},
        })
        assert r.status_code == 400
        detail = r.json()["detail"].lower()
        assert "frozen" in detail or "pre-d079" in detail


def test_what_if_with_profile_overrides(app_root):
    """profile_overrides deep_merge 能跑通."""
    app, root = app_root
    sid = _seed_trace(root)
    with TestClient(app) as c:
        r = c.post("/api/debug/what_if", json={
            "base_session_id": sid,
            "overrides": {
                "profile_overrides": {"scoring_weights": {"distance": 5.0}},
            },
        })
        assert r.status_code == 200
        body = r.json()
        assert body["__config"]["profile_overrides"] == {
            "scoring_weights": {"distance": 5.0}
        }


# ────────────────────────── T-00: v1 trace 端点级兼容


def _write_raw_v1_trace_for_endpoint(root: Path, sid: str) -> None:
    """绕过 write_trace 落 __version=1 的最小 trace (模拟 bump 前历史)."""
    p = data_root.recommend_trace_dir(root)
    p.mkdir(parents=True, exist_ok=True)
    trace = {
        "__version": 1,
        "__source": "production",
        "session_id": sid,
        "started_at": "2026-05-01T12:00:00+00:00",
        "l1": {"summary": {}},
        "l2": {"summary": {"n_scored": 0}},
        "l3": {"status": "skipped"},
        "final": [],
    }
    (p / f"{sid}.json").write_text(json.dumps(trace, ensure_ascii=False),
                                     encoding="utf-8")


def test_get_session_detail_accepts_v1_trace_after_bump(app_root):
    """T-00 bump 1→2 后, v=1 旧 trace 通过 /api/debug/sessions/{sid} 仍能访问.

    Codex audit 重点防线: read_trace 接受 v=1 + on-read migration 注空 hard_filter_events.
    """
    app, root = app_root
    sid = "sess_v1_endpoint_detail_20240101"
    _write_raw_v1_trace_for_endpoint(root, sid)
    with TestClient(app) as c:
        r = c.get(f"/api/debug/sessions/{sid}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_id"] == sid
        # __version 字段保留磁盘原值 (不被 normalizer 修改)
        assert body["__version"] == 1
        # hard_filter_events 被 on-read migration 注入空数组
        assert body["l1"].get("hard_filter_events") == []


def test_list_sessions_includes_v1_after_bump(app_root):
    """T-00 bump 1→2 后, Sidebar (/api/debug/sessions) 必须仍能列出 v=1 trace.

    Codex audit blocker #1: list_traces 单独做版本门控, 必须同步接受 v=1.
    """
    app, root = app_root
    v1_sid = "sess_v1_listing_20240101"
    _write_raw_v1_trace_for_endpoint(root, v1_sid)
    # 再种一条 v=2 trace 走 write_trace
    v2_sid = _seed_trace(root)
    with TestClient(app) as c:
        r = c.get("/api/debug/sessions")
        assert r.status_code == 200, r.text
        body = r.json()
        sids = {item["session_id"] for item in body.get("items", [])}
        assert v1_sid in sids
        assert v2_sid in sids


# ────────────────────────── T-P1a-01: hard_filter_events 位置守门


def test_fresh_trace_has_hard_filter_events_at_l1(app_root):
    """T-P1a-01: production recommend 出来的 trace, l1.hard_filter_events 在 T-00 schema 位置.

    位置守约: trace["l1"]["hard_filter_events"], 不是根级.
    """
    app, root = app_root
    sid = _seed_trace(root)
    trace = trace_store.read_trace(sid, root=root)
    assert trace is not None
    assert "hard_filter_events" in trace.get("l1", {}), \
        "T-00 contract violation: hard_filter_events 必须在 trace['l1'] 下"
    assert "hard_filter_events" not in trace, \
        "T-00 contract violation: hard_filter_events 不应在 trace 根级"
    # 当前 profile 无 l0_constraints + 无 refine → 数组应为空
    assert trace["l1"]["hard_filter_events"] == []

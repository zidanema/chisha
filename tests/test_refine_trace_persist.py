"""D-079 PR-4: /api/refine 持久化 trace.refine 字段 + missing/corrupt 分支.

DESIGN §3.5:
  - read_trace 返 None (base trace 缺失, 首轮 best-effort 失败) → warn + 不持久化
  - read_trace 抛 TraceCorrupt → error log + 同上不持久化
  - 任何情况下 refine 自身响应不阻断 (best-effort)

测试策略: 直接打 FastAPI router, 用 monkeypatch 把 refine_session + load_session
mock 掉 (refine 主链路 D-073 自带测试), 只关注 trace 落盘分支.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_root(tmp_path: Path, monkeypatch):
    from chisha import web_api, trace_store

    # web_api 把 ROOT 写死成模块常量, 测试时 monkeypatch.
    monkeypatch.setattr(web_api, "ROOT", tmp_path)
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: True)

    # mock refine_session 返回最小 candidates payload (避免拉真 zone/profile).
    def _fake_refine_session(**kwargs):
        return {
            "session_id": kwargs["session_id"],
            "meal_type": "lunch",
            "zone": "shenzhen-bay",
            "round": 2,
            "generated_at": "2026-05-16T12:34:56+00:00",
            "refine_input": kwargs.get("user_input", ""),
            "refine_intent": {"cuisine_want": "湘菜"},
            "stats": {
                "n_dishes_total": 100,
                "n_combos_recalled": 60,
                "n_combos_after_score": 40,
                "n_returned": 5,
            },
            "candidates": [
                {
                    "restaurant": {"name": "锅二爷", "id": "r_1"},
                    "dishes": [{"name": "番茄牛腩饭"}, {"name": "凉拌木耳"}],
                    "rank": 1,
                    "score": 8.42,
                },
            ],
        }

    monkeypatch.setattr(web_api, "refine_session", _fake_refine_session)

    # mock load_session 让 session 总存在
    class _Sess:
        meal_type = "lunch"
        zone = "shenzhen-bay"
        daily_mood = None

    def _fake_load_session(sid, root, **kw):
        return _Sess()

    # refine 端点内部 from chisha.session import load_session — patch 模块本身
    import chisha.session as session_mod
    monkeypatch.setattr(session_mod, "load_session", _fake_load_session)

    # mock 数据加载 (zone + meal_log + profile), 避免读真盘
    monkeypatch.setattr(web_api, "load_zone_data", lambda zone, root: ([], []))
    monkeypatch.setattr(web_api, "load_meal_log", lambda root: [])
    monkeypatch.setattr(web_api, "load_profile", lambda path, root: {"llm": {}})
    monkeypatch.setattr(web_api, "_remember_session_safe", lambda sid, out: None)
    monkeypatch.setattr(web_api, "_profile_path", lambda: tmp_path / "profile.yaml")

    # mock build_context (refine 端点 inline import) → 简单 stub
    from chisha import context as ctx_mod

    class _Ctx:
        def to_llm_dict(self):
            return {}

    monkeypatch.setattr(ctx_mod, "build_context", lambda **kw: _Ctx())
    # clock.today 也 inline import, 走 sandbox.is_enabled 路径 — 给个固定日期
    from chisha import clock as clock_mod
    import datetime as _dt
    monkeypatch.setattr(clock_mod, "today",
                        lambda *args, **kw: _dt.date(2026, 5, 16))

    # mock format_v2_candidate (web_api 用它包候选 — 我们的 mock candidate 是 dict)
    monkeypatch.setattr(web_api, "format_v2_candidate", lambda i, c: c)

    app = FastAPI()
    app.include_router(web_api.router)
    return app, tmp_path, trace_store


def _post_refine(client: TestClient, sid: str) -> Any:
    return client.post(
        "/api/refine",
        json={"session_id": sid, "refine_text": "想吃湖南菜, 肉多一点"},
    )


def _write_base_trace(trace_store, root: Path, sid: str) -> Path:
    """落一条最小合法 base trace, 让 refine 可以 merge."""
    base = {
        "__version": trace_store.TRACE_SCHEMA_VERSION,
        "__source": "production",
        "__parent_session_id": None,
        "__llm_called": False,
        "__frozen": {"meal_type": "lunch", "zone": "shenzhen-bay"},
        "__config": {
            "use_llm_rerank": None, "n_return": 5, "n_explore": 2,
            "daily_mood": None, "refine_text": None, "profile_overrides": None,
        },
        "session_id": sid,
        "started_at": "2026-05-16T12:00:00+00:00",
        "total_latency_ms": 1000,
        "ctx_latency_ms": 10, "recall_latency_ms": 30,
        "score_latency_ms": 50, "rerank_latency_ms": 800,
        "final_latency_ms": 110,
        "l1": {"summary": {"n_combos": 0}},
        "l2": {"summary": {}, "top": []},
        "l3": {"used": False, "n_returned": 5, "status": "fallback",
                "model": None, "resolved_provider": None,
                "raw_response": "", "raw_response_chars": 0,
                "tool_input": None, "stop_reason": None,
                "fallback_reason": None, "parsed_candidates": None,
                "payload_to_llm": None, "used_fallback": True},
        "final": [],
        "refine": {"applied": False},
    }
    assert trace_store.write_trace(sid, base, root=root) is True
    p = trace_store.data_root.recommend_trace_dir(root) / f"{sid}.json"
    assert p.exists()
    return p


def test_refine_merges_into_base_trace(app_with_root):
    """正常路径: base trace 存在 → refine 把 refine 字段 merge 进同一文件."""
    app, root, trace_store = app_with_root
    sid = "sess_refine_ok_01"
    _write_base_trace(trace_store, root, sid)

    client = TestClient(app)
    r = _post_refine(client, sid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == sid
    assert body["round"] == 2

    # trace 文件被更新, refine.applied = True + user_input 透传 + 同 sid 不分裂
    p = trace_store.data_root.recommend_trace_dir(root) / f"{sid}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["refine"]["applied"] is True
    assert data["refine"]["user_input"] == "想吃湖南菜, 肉多一点"
    assert data["refine"]["round"] == 2
    assert data["refine"]["intent"] == {"cuisine_want": "湘菜"}
    assert data["__config"]["refine_text"] == "想吃湖南菜, 肉多一点"
    # 不创 refine-only 孤儿: 只有这一个 trace 文件
    files = list(trace_store.data_root.recommend_trace_dir(root).glob("*.json"))
    assert len(files) == 1


def test_refine_base_trace_falls_through_new_fields(app_with_root, monkeypatch):
    """Codex H1: base_trace["refine"] 必须含 reference_resolved/subtype_diversified/narrative.

    用真 raw 字段 mock _fake_refine_session 返回, 验证 web_api 真把这些字段
    merge 进 base_trace["refine"] (不能只看 response 顶层).
    """
    app, root, trace_store = app_with_root
    sid = "sess_refine_new_fields_04"
    _write_base_trace(trace_store, root, sid)

    # 重新覆盖 refine_session, 带 _reference_resolved / _subtype_diversified / narrative
    from chisha import web_api as web_api_mod

    def _refine_with_fields(**kwargs):
        return {
            "session_id": kwargs["session_id"],
            "meal_type": "lunch", "zone": "shenzhen-bay", "round": 2,
            "generated_at": "2026-05-16T12:34:56+00:00",
            "refine_input": kwargs.get("user_input", ""),
            "refine_intent": {"cuisine_want": "湘菜"},
            "refine_intent_v2": {"schema_version": "2.0",
                                   "raw_text": "比昨天清淡"},
            "stats": {"n_dishes_total": 10, "n_combos_recalled": 10,
                       "n_combos_after_score": 10, "n_returned": 5},
            "candidates": [],
            "narrative": "mock-narrative-for-trace",
            "_reference_resolved": {
                "relation": "lighter", "raw_text": "比昨天清淡",
                "base_session_id": "sess-base", "base_meal_type": "lunch",
                "base_started_at": "", "n_base_combos": 1,
                "notes": [], "source": "v2_intent",
            },
            "_subtype_diversified": True,
            "_refine_hard_filter_events": [],
            "_refine_recall_fallback_events": [],
        }
    monkeypatch.setattr(web_api_mod, "refine_session", _refine_with_fields)

    client = TestClient(app)
    r = _post_refine(client, sid)
    assert r.status_code == 200, r.text

    p = trace_store.data_root.recommend_trace_dir(root) / f"{sid}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    refine_blob = data["refine"]
    assert refine_blob["narrative"] == "mock-narrative-for-trace"
    assert refine_blob["subtype_diversified"] is True
    rr = refine_blob["reference_resolved"]
    assert rr is not None
    assert rr["relation"] == "lighter"
    assert rr["source"] == "v2_intent"
    assert rr["base_session_id"] == "sess-base"
    assert refine_blob["intent_v2"]["schema_version"] == "2.0"


def test_refine_with_missing_base_trace_warns_not_persists(app_with_root, caplog):
    """base trace 缺失 (首轮 best-effort 失败): refine 仍返 200, 但不创 orphan trace."""
    app, root, trace_store = app_with_root
    sid = "sess_refine_no_base_02"
    # 不 _write_base_trace; trace_dir 为空

    client = TestClient(app)
    with caplog.at_level("WARNING"):
        r = _post_refine(client, sid)
    assert r.status_code == 200, r.text

    # 没有 orphan trace 被创出来
    d = trace_store.data_root.recommend_trace_dir(root)
    if d.exists():
        assert list(d.glob("*.json")) == []

    # warn 日志包含 sid
    assert any(sid in rec.message and "missing" in rec.message
                for rec in caplog.records)


def test_refine_with_corrupt_base_trace_warns_not_persists(app_with_root, caplog):
    """base trace 损坏: refine 仍返 200, 不覆盖 (损坏文件已被备份)."""
    app, root, trace_store = app_with_root
    sid = "sess_refine_corrupt_03"
    d = trace_store.data_root.recommend_trace_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}.json"
    p.write_text("{not json", encoding="utf-8")

    client = TestClient(app)
    with caplog.at_level("ERROR"):
        r = _post_refine(client, sid)
    assert r.status_code == 200, r.text

    # 原文件被 read_trace 备份到 .corrupt.*.bak (TraceCorrupt 行为, D-066/067 一致)
    # refine 走 error 分支 → 不重新写一个 trace
    assert not p.exists(), "corrupt file should have been renamed to .bak"
    healthy = [pp for pp in d.glob("*.json") if pp.is_file()]
    assert healthy == [], "refine must not create a fresh trace on corrupt base"

    assert any(sid in rec.message and "corrupt" in rec.message
                for rec in caplog.records)

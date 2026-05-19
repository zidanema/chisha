"""D-079 PR-4 + D-087 v3: /api/refine 持久化分支.

D-087 v3 改造:
  - refine 写盘不再 merge 进 base_trace["refine"], 改 append 新 round 到 v3 trace
    ({sid}/rounds/R{n}.json + 更新 {sid}/meta.json)
  - v2 单文件 base trace 在 append_round 内部自动 migrate v2 → v3
  - 缺/损坏 base trace 仍是 best-effort warn + 不创 orphan, refine response 不阻断

测试策略同 D-079: monkeypatch refine_session + load_session, 只验落盘形状.
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


def test_refine_appends_v3_round(app_with_root):
    """D-087: refine 走 append_round, 落 {sid}/rounds/R2.json + 更新 meta."""
    app, root, trace_store = app_with_root
    sid = "sess_refine_ok_01"
    _write_base_trace(trace_store, root, sid)

    client = TestClient(app)
    r = _post_refine(client, sid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == sid
    assert body["round"] == 2

    d = trace_store.data_root.recommend_trace_dir(root)
    # 自动 migrate: v2 单文件 rename → .migrated_v2; v3 dir 出现
    assert (d / f"{sid}.json.migrated_v2").exists()
    assert not (d / f"{sid}.json").exists()
    assert (d / sid / "meta.json").exists()
    assert (d / sid / "rounds" / "R1.json").exists()
    assert (d / sid / "rounds" / "R2.json").exists()

    meta = json.loads((d / sid / "meta.json").read_text("utf-8"))
    assert meta["round_ids"] == ["R1", "R2"]
    assert meta["latest_round"] == "R2"
    assert meta["refine_count"] == 1

    r2 = json.loads((d / sid / "rounds" / "R2.json").read_text("utf-8"))
    assert r2["user_input"] == "想吃湖南菜, 肉多一点"
    assert r2["intent"] == {"cuisine_want": "湘菜"}


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

    # D-087: round R2 文件应含 intent_v2 / reference_resolved / subtype_diversified / narrative
    d = trace_store.data_root.recommend_trace_dir(root)
    r2 = json.loads((d / sid / "rounds" / "R2.json").read_text("utf-8"))
    assert r2["narrative"] == "mock-narrative-for-trace"
    assert r2["subtype_diversified"] is True
    rr = r2["reference_resolved"]
    assert rr is not None
    assert rr["relation"] == "lighter"
    assert rr["source"] == "v2_intent"
    assert rr["base_session_id"] == "sess-base"
    assert r2["intent_v2"]["schema_version"] == "2.0"


def test_refine_with_missing_base_trace_warns_not_persists(app_with_root, caplog):
    """D-087: base trace 缺失 → append_round 返 None, refine 仍 200, 无 orphan."""
    app, root, trace_store = app_with_root
    sid = "sess_refine_no_base_02"
    # 不 _write_base_trace; trace_dir 为空

    client = TestClient(app)
    with caplog.at_level("WARNING"):
        r = _post_refine(client, sid)
    assert r.status_code == 200, r.text

    # 没有 orphan trace 被创: 无 v2 单文件, 无 v3 dir
    d = trace_store.data_root.recommend_trace_dir(root)
    if d.exists():
        assert list(d.glob("*.json")) == []
        assert not (d / sid).exists(), "must not create orphan v3 dir"

    # warn 日志包含 sid + "skip persist"
    assert any(sid in rec.message and "skip persist" in rec.message
                for rec in caplog.records)


def test_refine_round_persists_full_l1_l2_l3_trace_slices(tmp_path, monkeypatch):
    """D-089-S2/S4: refine round 必须落完整 L1/L2/L3 + refine_intent_llm 切片.

    监督性测试 — fixture 用扩展的 _fake_refine_session 返回 l1_trace/l2_trace/
    l3_trace/refine_intent_llm_trace, 验证 build_refine_round_payload 把它们
    1:1 落到 R2.json (而不是写成 None stub).
    """
    from chisha import web_api, trace_store

    monkeypatch.setattr(web_api, "ROOT", tmp_path)
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: True)

    def _fake_refine_session_with_full_slices(**kwargs):
        return {
            "session_id": kwargs["session_id"],
            "meal_type": "lunch",
            "zone": "shenzhen-bay",
            "round": 2,
            "generated_at": "2026-05-19T12:34:56+00:00",
            "refine_input": kwargs.get("user_input", ""),
            "refine_intent": {"cuisine_want": "湘菜"},
            "refine_intent_v2": {"redirect": {}, "constrain": {}},
            "narrative": "test narrative",
            "stats": {"n_dishes_total": 100, "n_combos_recalled": 60,
                       "n_combos_after_score": 40, "n_returned": 5},
            "candidates": [{"restaurant": {"name": "湘颂", "id": "r1"},
                            "dishes": [{"name": "辣子鸡"}], "rank": 1, "score": 8.4}],
            "_reference_resolved": None,
            "_subtype_diversified": True,
            "_refine_hard_filter_events": [],
            "_refine_recall_fallback_events": [],
            # D-089-S2: refine 暴露完整切片
            "l1_trace": {"summary": {"n_combos": 60}, "hard_filter_events": []},
            "l2_trace": {"summary": {"n_scored": 40, "score_min": 1.0,
                                       "score_max": 9.0}, "top": []},
            "l3_trace": {
                "status": "ok", "used": True, "model": "anthropic/claude-sonnet-4.6",
                "resolved_provider": "openrouter",
                "system_prompt_full": "rerank system prompt body...",
                "system_prompt_chars": 4757,
                "user_message_full": "user message...",
                "user_message_chars": 100,
                "raw_response": '{"candidates":[]}',
                "raw_response_chars": 17,
                "latency_ms": 5000,
                "usage": {"input_tokens": 100, "output_tokens": 50,
                          "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0},
                "narrative": "test", "tool_input": {},
                "parsed_candidates": [{"rank": 1}],
                "n_returned": 5, "used_fallback": False,
            },
            "refine_intent_llm_trace": {
                "system_prompt_full": "parse_refine_intent_v2.md...",
                "system_prompt_chars": 9000,
                "user_message_full": "想吃湖南菜",
                "user_message_chars": 5,
                "raw_response": '{"redirect":{}}',
                "raw_response_chars": 14,
                "latency_ms": 1500,
                "usage": {"input_tokens": 4000, "output_tokens": 50,
                          "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0},
                "model": "anthropic/claude-sonnet-4.6",
                "resolved_provider": "openrouter",
                "stop_reason": "end_turn", "fallback_reason": None,
            },
            "total_latency_ms": 6500,
        }

    monkeypatch.setattr(web_api, "refine_session",
                        _fake_refine_session_with_full_slices)

    class _Sess:
        meal_type = "lunch"
        zone = "shenzhen-bay"
        daily_mood = None
    import chisha.session as session_mod
    monkeypatch.setattr(session_mod, "load_session", lambda *a, **kw: _Sess())
    monkeypatch.setattr(web_api, "load_zone_data", lambda zone, root: ([], []))
    monkeypatch.setattr(web_api, "load_meal_log", lambda root: [])
    monkeypatch.setattr(web_api, "load_profile", lambda path, root: {"llm": {}})
    monkeypatch.setattr(web_api, "_remember_session_safe", lambda sid, out: None)
    monkeypatch.setattr(web_api, "_profile_path", lambda: tmp_path / "p.yaml")
    monkeypatch.setattr(web_api, "format_v2_candidate", lambda i, c: c)
    from chisha import context as ctx_mod

    class _Ctx:
        def to_llm_dict(self):
            return {}
    monkeypatch.setattr(ctx_mod, "build_context", lambda **kw: _Ctx())
    from chisha import clock as clock_mod
    import datetime as _dt
    monkeypatch.setattr(clock_mod, "today",
                        lambda *args, **kw: _dt.date(2026, 5, 19))

    app = FastAPI()
    app.include_router(web_api.router)

    sid = "sess_d089_full_slices"
    _write_base_trace(trace_store, tmp_path, sid)
    client = TestClient(app)
    r = client.post("/api/refine",
                    json={"session_id": sid, "refine_text": "想吃湘菜"})
    assert r.status_code == 200, r.text

    d = trace_store.data_root.recommend_trace_dir(tmp_path)
    r2 = json.loads((d / sid / "rounds" / "R2.json").read_text("utf-8"))

    # D-089 核心断言: R2 round 必须含完整切片 (不是 None stub)
    assert r2["l1"] is not None, "R2.l1 must be persisted (not None)"
    assert r2["l2"] is not None, "R2.l2 must be persisted (not None)"
    assert r2["l3"] is not None, "R2.l3 must be persisted (not None)"
    assert r2["refine_intent_llm"] is not None, (
        "R2.refine_intent_llm must be persisted"
    )

    # L3 关键字段:trace 自包含原则
    assert r2["l3"]["system_prompt_full"] == "rerank system prompt body..."
    assert r2["l3"]["system_prompt_chars"] == 4757
    assert r2["l3"]["status"] == "ok"
    assert r2["l3"]["latency_ms"] == 5000
    assert r2["l3"]["usage"]["input_tokens"] == 100

    # refine_intent_llm 完整 trace
    ri = r2["refine_intent_llm"]
    assert ri["system_prompt_chars"] == 9000
    assert ri["user_message_full"] == "想吃湖南菜"
    assert ri["raw_response"] == '{"redirect":{}}'
    assert ri["latency_ms"] == 1500
    assert ri["model"] == "anthropic/claude-sonnet-4.6"

    # kpi.latency_ms 从 refine_raw.total_latency_ms 来 (不再硬编 0)
    assert r2["kpi"]["latency_ms"] == 6500


def test_refine_with_corrupt_base_trace_warns_not_persists(app_with_root, caplog):
    """D-087: 损坏 v2 base → migrate_v2_to_v3 失败, append_round 返 None.

    v2 文件本身保留 (不再走 read_trace TraceCorrupt 备份路径), 由用户/ops 手工处理.
    """
    app, root, trace_store = app_with_root
    sid = "sess_refine_corrupt_03"
    d = trace_store.data_root.recommend_trace_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}.json"
    p.write_text("{not json", encoding="utf-8")

    client = TestClient(app)
    with caplog.at_level("WARNING"):
        r = _post_refine(client, sid)
    assert r.status_code == 200, r.text

    # append_round 内部 migrate_v2_to_v3 fail (json 解析报错), 返 False;
    # 损坏文件原位保留 (不再被 silently rename). 也没有 v3 dir 被部分创建.
    assert p.exists(), "corrupt v2 file should remain in place"
    assert not (d / sid).exists(), "no partial v3 dir should be created"

    assert any(sid in rec.message and "skip persist" in rec.message
                for rec in caplog.records)

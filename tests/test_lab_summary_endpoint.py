"""D-085 PR-E E2: /api/lab/sessions/{sid}/summary 端点单测.

覆盖:
- happy path: cache miss → 调 fake LLM → 写回 trace __summary → 二访 cache hit
- fingerprint 变化 (修 trace 输入字段) → cache 失效, 重算
- 404 trace 不存在
- 500 trace 损坏
- 409 schema 版本不匹配
- fallback fail-closed: LLM 抛 → 200 + fallback=true (不抛 500), 不写盘
- what-if preview trace 不写盘 (但仍能生成摘要)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from chisha import api_lab, data_root, lab_summary, trace_store


def _make_trace(sid: str, *, source: str = "production",
                breakdown: dict | None = None) -> dict:
    return {
        "session_id": sid,
        "started_at": "2026-05-17T12:00:00+00:00",
        "__frozen": {"meal_type": "lunch", "today": "2026-05-17", "zone": "shenzhen-bay"},
        "__config": {"daily_mood": "neutral"},
        "__source": source,
        "l3": {"status": "ok"},
        "l2": {"top": [{
            "rank": 1,
            "breakdown": breakdown or {"low_oil": 0.6, "popularity": 0.3},
        }]},
        "refine": {"applied": False},
        "total_latency_ms": 1234,
        "final": [{
            "rank": 1,
            "restaurant": {"name": "西贝莜面村"},
            "dishes": [{"name": "蒸鸡胸"}, {"name": "蒜蓉菜心"}],
            "total_price": 78.0,
            "estimated_total_oil": 2.3,
            "estimated_total_protein_g": 42.5,
            "reason_one_line": "蒸菜清淡",
            "score": 1.42,
        }],
    }


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api_lab, "ROOT", tmp_path)
    monkeypatch.setattr(api_lab, "_is_localhost", lambda req: True)

    app = FastAPI()
    app.include_router(api_lab.router)
    with TestClient(app) as c:
        yield c, tmp_path


def _fake_summarize_ok(text: str = "蒸菜清淡, 油脂低, 命中你 7 天没点的店"):
    """patch lab_summary.summarize 返成功 dict (避开真 LLM)."""
    def _impl(trace, **kwargs):
        return {
            "text": text,
            "model": "claude-haiku-4-5-fake",
            "generated_at": "2026-05-17T18:00:00+00:00",
            "fingerprint": lab_summary.compute_fingerprint(trace),
            "fallback": False,
        }
    return _impl


def _fake_summarize_fallback(kind: str = "no_provider", detail: str = "无 key"):
    def _impl(trace, **kwargs):
        return {
            "text": None,
            "fallback": True,
            "error_kind": kind,
            "error_detail": detail,
        }
    return _impl


# ────────────────────────── happy path + cache

def test_summary_cache_miss_then_hit(client, monkeypatch):
    c, root = client
    sid = "sess_001"
    trace_store.write_trace(sid, _make_trace(sid), root=root)

    call_count = {"n": 0}
    real_summarize = _fake_summarize_ok()

    def _spy(trace, **kwargs):
        call_count["n"] += 1
        return real_summarize(trace, **kwargs)

    monkeypatch.setattr(lab_summary, "summarize", _spy)

    # 首访 — miss, 调 LLM
    r1 = c.get(f"/api/lab/sessions/{sid}/summary")
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1["fallback"] is False
    assert j1["cached"] is False
    assert "蒸菜清淡" in j1["text"]
    assert call_count["n"] == 1

    # 二访 — hit, 不调 LLM
    r2 = c.get(f"/api/lab/sessions/{sid}/summary")
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["cached"] is True
    assert j2["text"] == j1["text"]
    assert call_count["n"] == 1, "cache hit 不应再次调 LLM"

    # 验 trace 文件落了 __summary
    raw = trace_store.read_trace(sid, root=root)
    assert raw is not None
    assert raw["__summary"]["fingerprint"] == j1["fingerprint"]


def test_summary_cache_invalidates_on_fingerprint_change(client, monkeypatch):
    c, root = client
    sid = "sess_fp"
    trace_store.write_trace(sid, _make_trace(sid), root=root)

    call_count = {"n": 0}
    real_summarize = _fake_summarize_ok()

    def _spy(trace, **kwargs):
        call_count["n"] += 1
        return real_summarize(trace, **kwargs)

    monkeypatch.setattr(lab_summary, "summarize", _spy)

    r1 = c.get(f"/api/lab/sessions/{sid}/summary")
    assert r1.status_code == 200
    fp1 = r1.json()["fingerprint"]
    assert call_count["n"] == 1

    # 改一个会影响 fingerprint 的字段 (top1 dishes), 重写盘
    mutated = _make_trace(sid)
    mutated["final"][0]["dishes"] = [{"name": "完全不同的菜"}]
    # 保留 __summary stale 字段 (模拟旧缓存)
    mutated["__summary"] = trace_store.read_trace(sid, root=root)["__summary"]
    trace_store.write_trace(sid, mutated, root=root)

    r2 = c.get(f"/api/lab/sessions/{sid}/summary")
    assert r2.status_code == 200
    assert r2.json()["cached"] is False
    assert r2.json()["fingerprint"] != fp1
    assert call_count["n"] == 2, "fingerprint 变化必须重算"


# ────────────────────────── 404 / 409 / 500

def test_summary_404_when_trace_missing(client):
    c, _ = client
    r = c.get("/api/lab/sessions/nonexistent_sid/summary")
    assert r.status_code == 404


def test_summary_500_on_corrupt_trace(client):
    c, root = client
    sid = "sess_corrupt"
    # 直接写一个 broken json 到 prod trace 目录
    d = data_root.recommend_trace_prod_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.json").write_text("{not json", encoding="utf-8")

    r = c.get(f"/api/lab/sessions/{sid}/summary")
    assert r.status_code == 500
    assert "corrupt" in r.json()["detail"].lower()


def test_summary_409_on_schema_version_mismatch(client):
    c, root = client
    sid = "sess_v_old"
    d = data_root.recommend_trace_prod_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    # 写一个未知 version
    (d / f"{sid}.json").write_text(
        json.dumps({"__version": 999, "session_id": sid}), encoding="utf-8"
    )

    r = c.get(f"/api/lab/sessions/{sid}/summary")
    assert r.status_code == 409


# ────────────────────────── fallback fail-closed

def test_summary_fallback_returns_200_not_500(client, monkeypatch):
    c, root = client
    sid = "sess_fb"
    trace_store.write_trace(sid, _make_trace(sid), root=root)

    monkeypatch.setattr(
        lab_summary, "summarize",
        _fake_summarize_fallback("no_provider", "无可用 LLM"),
    )

    r = c.get(f"/api/lab/sessions/{sid}/summary")
    assert r.status_code == 200  # NOT 500
    j = r.json()
    assert j["fallback"] is True
    assert j["error_kind"] == "no_provider"
    assert j["text"] is None

    # 不写盘
    raw = trace_store.read_trace(sid, root=root)
    assert raw is not None
    assert "__summary" not in raw


def test_summary_fallback_can_retry_after_recovery(client, monkeypatch):
    """fallback 不写盘 → provider 恢复后下次请求重新调 LLM 命中."""
    c, root = client
    sid = "sess_recover"
    trace_store.write_trace(sid, _make_trace(sid), root=root)

    monkeypatch.setattr(
        lab_summary, "summarize",
        _fake_summarize_fallback("llm_error", "API 429"),
    )
    r1 = c.get(f"/api/lab/sessions/{sid}/summary")
    assert r1.json()["fallback"] is True

    # 切回成功
    monkeypatch.setattr(lab_summary, "summarize", _fake_summarize_ok())
    r2 = c.get(f"/api/lab/sessions/{sid}/summary")
    assert r2.status_code == 200
    assert r2.json()["fallback"] is False
    assert r2.json()["cached"] is False  # 上次没写盘 → miss


# ────────────────────────── what-if preview

def test_summary_for_what_if_preview_does_not_persist(client, monkeypatch):
    """what-if trace 即便在 prod 目录里 (测试场景), 也不写 __summary 回去."""
    c, root = client
    sid = "sess_whatif"
    trace_store.write_trace(
        sid, _make_trace(sid, source="what_if_preview"), root=root
    )
    monkeypatch.setattr(lab_summary, "summarize", _fake_summarize_ok())

    r = c.get(f"/api/lab/sessions/{sid}/summary")
    assert r.status_code == 200
    assert r.json()["fallback"] is False
    assert r.json()["text"] is not None

    # 不写盘
    raw = trace_store.read_trace(sid, root=root)
    assert "__summary" not in raw

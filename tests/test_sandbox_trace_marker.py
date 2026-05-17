"""D-085 PR-B: sandbox trace marker 守门.

invariant 4 (refactor_living_lab.md §7):
- write_trace 写入 is_sandbox top-level boolean (来自 sandbox.is_enabled(root))
- list_traces 默认 include_sandbox=False 只扫 prod 目录
- include_sandbox=True 时扫 prod + sandbox 双目录合并
- 老 trace (缺 is_sandbox 字段) → 读侧默认 False
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chisha import data_root, sandbox, trace_store


def _make_trace(sid: str) -> dict:
    return {
        "session_id": sid,
        "started_at": "2026-05-17T12:00:00+00:00",
        "__frozen": {"meal_type": "lunch", "zone": "shenzhen-bay"},
        "l3": {"status": "ok"},
        "total_latency_ms": 1234,
        "final": [{
            "restaurant": {"name": "店X"},
            "dishes": [{"name": "菜A"}, {"name": "菜B"}],
        }],
    }


def test_write_trace_marks_is_sandbox_when_sandbox_enabled(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_path)
    sandbox.init(start_date="2026-05-20", root=tmp_path)

    sid = "test_sb_001"
    assert trace_store.write_trace(sid, _make_trace(sid), root=tmp_path) is True

    # trace 落在 sandbox 目录
    sandbox_path = data_root.recommend_trace_sandbox_dir(tmp_path) / f"{sid}.json"
    assert sandbox_path.exists()
    data = json.loads(sandbox_path.read_text(encoding="utf-8"))
    assert data["is_sandbox"] is True


def test_write_trace_marks_is_sandbox_false_when_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_path)
    # 不 init sandbox

    sid = "test_prod_001"
    assert trace_store.write_trace(sid, _make_trace(sid), root=tmp_path) is True

    prod_path = data_root.recommend_trace_prod_dir(tmp_path) / f"{sid}.json"
    assert prod_path.exists()
    data = json.loads(prod_path.read_text(encoding="utf-8"))
    assert data["is_sandbox"] is False


def test_list_traces_default_excludes_sandbox(tmp_path: Path, monkeypatch):
    """默认 include_sandbox=False → 只看 prod 目录."""
    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_path)

    # 写一条 prod trace
    trace_store.write_trace("sid_prod", _make_trace("sid_prod"), root=tmp_path)

    # 启用 sandbox 再写一条
    sandbox.init(start_date="2026-05-20", root=tmp_path)
    trace_store.write_trace("sid_sb", _make_trace("sid_sb"), root=tmp_path)

    # 默认 list 只看 prod
    items, _ = trace_store.list_traces(root=tmp_path, limit=30)
    sids = [it["session_id"] for it in items]
    assert "sid_prod" in sids
    assert "sid_sb" not in sids
    assert all(it["is_sandbox"] is False for it in items)


def test_list_traces_include_sandbox_merges_both(tmp_path: Path, monkeypatch):
    """include_sandbox=True → 两个目录合并, items 带 is_sandbox 区分."""
    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_path)

    trace_store.write_trace("sid_prod", _make_trace("sid_prod"), root=tmp_path)
    sandbox.init(start_date="2026-05-20", root=tmp_path)
    trace_store.write_trace("sid_sb", _make_trace("sid_sb"), root=tmp_path)

    items, _ = trace_store.list_traces(
        root=tmp_path, limit=30, include_sandbox=True
    )
    sids_to_flag = {it["session_id"]: it["is_sandbox"] for it in items}
    assert sids_to_flag.get("sid_prod") is False
    assert sids_to_flag.get("sid_sb") is True


def test_list_traces_legacy_no_is_sandbox_defaults_false(tmp_path: Path, monkeypatch):
    """老 trace 缺 is_sandbox 字段 → 读侧 items.is_sandbox=False."""
    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_path)
    prod_dir = data_root.recommend_trace_prod_dir(tmp_path)
    prod_dir.mkdir(parents=True, exist_ok=True)

    legacy_trace = _make_trace("legacy_sid")
    legacy_trace["__version"] = trace_store.TRACE_SCHEMA_VERSION
    # 不写 is_sandbox 字段
    (prod_dir / "legacy_sid.json").write_text(
        json.dumps(legacy_trace, ensure_ascii=False), encoding="utf-8"
    )

    items, _ = trace_store.list_traces(root=tmp_path, limit=30)
    legacy = next(it for it in items if it["session_id"] == "legacy_sid")
    assert legacy["is_sandbox"] is False


def test_living_recommend_writes_prod_even_when_sandbox_enabled(
    tmp_path: Path, monkeypatch
):
    """D-085 Codex BLOCKER 修复: Lab 已开 sandbox 时, Living /api/recommend
    必须仍走 prod 数据落盘. 否则 agent 调 Living 会被 Lab 的 sandbox 状态污染.

    覆盖路径: Living dependency _force_prod_data 包住整个请求, sandbox.is_enabled()
    返 False → data_root.recommend_log_path / trace_dir / profile_path 全走 prod.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from chisha import api_living, data_root

    # 让 sandbox._project_root 指向 tmp_path 以测试隔离 state
    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(api_living, "ROOT", tmp_path)
    monkeypatch.setattr(api_living, "PROFILE_PATH", tmp_path / "profile.yaml")
    # mock recommend_meal 验证调用时 sandbox.is_enabled() 是否返 False
    sandbox_state_during_call: list[bool] = []

    def fake_recommend(**kwargs):
        sandbox_state_during_call.append(sandbox.is_enabled(tmp_path))
        return {
            "session_id": "sid_leak_test",
            "meal_type": kwargs.get("meal_type"),
            "zone": "shenzhen-bay", "round": 1, "version": "v2",
            "generated_at": "2026-05-17T12:00:00+00:00",
            "context": {}, "stats": {"n_returned": 0}, "candidates": [],
        }

    monkeypatch.setattr(api_living, "recommend_meal", fake_recommend)
    monkeypatch.setattr(api_living, "_remember_session_safe",
                         lambda sid, out: None)

    # 真的开 sandbox state (磁盘上 enabled=True)
    sandbox.init(start_date="2026-05-20", root=tmp_path)
    assert sandbox.is_enabled(tmp_path) is True  # 全局确实开了

    app = FastAPI()
    app.include_router(api_living.router)
    with TestClient(app) as c:
        r = c.get("/api/recommend", params={"meal_hint": "lunch"})
        assert r.status_code == 200, r.text

    # 关键断言: recommend_meal 调用期间 is_enabled 必须返 False
    assert sandbox_state_during_call == [False], (
        f"Living /api/recommend 必须强制 prod 数据, 但调用时 sandbox.is_enabled() "
        f"= {sandbox_state_during_call} (期望 [False])"
    )

    # 退出请求后 is_enabled 恢复 True (thread-local 干净清理)
    assert sandbox.is_enabled(tmp_path) is True


def test_living_force_disabled_also_kills_virtual_clock(tmp_path, monkeypatch):
    """D-085 Codex re-review 第二轮 BLOCKER 修复: force_disabled 不仅要关
    存储路径 (data_root), 还要关虚拟时钟 (sandbox.current_date 等), 否则
    Lab 已 advance 虚拟日期 → Living recommend 会用 sandbox 虚拟日做 today,
    污染 cooldown / variety_bonus / meal_log timestamp.
    """
    import datetime as dt
    from chisha import clock

    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_path)
    sandbox.init(start_date="2030-01-15", root=tmp_path)  # 远未来日期

    # 全局 enabled → 虚拟时钟生效
    assert sandbox.is_enabled(tmp_path) is True
    assert sandbox.current_date(tmp_path) == dt.date(2030, 1, 15)
    assert clock.today(tmp_path) == dt.date(2030, 1, 15)

    # force_disabled 内 — 全部回到真实
    with sandbox.force_disabled():
        assert sandbox.is_enabled(tmp_path) is False
        assert sandbox.current_date(tmp_path) is None
        assert sandbox.current_datetime(tmp_path) is None
        assert sandbox.current_datetime_utc(tmp_path) is None
        # clock.today fallback 走真实 today, 不是 2030-01-15
        assert clock.today(tmp_path) == dt.date.today()

    # 退出 with 后恢复虚拟时钟
    assert sandbox.is_enabled(tmp_path) is True
    assert sandbox.current_date(tmp_path) == dt.date(2030, 1, 15)


def test_read_trace_finds_prod_even_when_sandbox_enabled(tmp_path: Path, monkeypatch):
    """D-085 smoke 实测发现的 bug: read_trace 用 data_root.recommend_trace_dir
    跟 sandbox.is_enabled 全局状态走 → Lab 启 sandbox 时单条读 Living 写的
    prod trace 404. 修法: read_trace 跨 prod + sandbox 双目录查找.
    """
    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_path)

    # 写一条 prod trace (sandbox 未启)
    trace_store.write_trace("sid_prod", _make_trace("sid_prod"), root=tmp_path)
    assert (data_root.recommend_trace_prod_dir(tmp_path) / "sid_prod.json").exists()

    # 启 sandbox 后再写一条 sandbox trace
    sandbox.init(start_date="2030-01-15", root=tmp_path)
    trace_store.write_trace("sid_sb", _make_trace("sid_sb"), root=tmp_path)
    assert (data_root.recommend_trace_sandbox_dir(tmp_path) / "sid_sb.json").exists()

    # 即便 sandbox 启用, read_trace 仍应找到 prod trace
    assert sandbox.is_enabled(tmp_path) is True
    prod = trace_store.read_trace("sid_prod", root=tmp_path)
    assert prod is not None, "read_trace 必须跨 prod+sandbox 找到 prod trace"
    assert prod["session_id"] == "sid_prod"
    assert prod["is_sandbox"] is False

    # sandbox trace 也能找到
    sb = trace_store.read_trace("sid_sb", root=tmp_path)
    assert sb is not None
    assert sb["is_sandbox"] is True


def test_lab_sessions_endpoint_exposes_include_sandbox(tmp_path: Path, monkeypatch):
    """/api/lab/sessions 端点 include_sandbox=true 时返回 sandbox trace."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from chisha import api_lab

    monkeypatch.setattr(api_lab, "ROOT", tmp_path)
    monkeypatch.setattr(api_lab, "_is_localhost", lambda req: True)
    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_path)

    trace_store.write_trace("sid_prod", _make_trace("sid_prod"), root=tmp_path)
    sandbox.init(start_date="2026-05-20", root=tmp_path)
    trace_store.write_trace("sid_sb", _make_trace("sid_sb"), root=tmp_path)

    app = FastAPI()
    app.include_router(api_lab.router)
    with TestClient(app) as c:
        # 默认 → 只 prod
        r = c.get("/api/lab/sessions")
        assert r.status_code == 200
        sids = [it["session_id"] for it in r.json()["items"]]
        assert "sid_prod" in sids
        assert "sid_sb" not in sids

        # 显式打开 → 两个都有
        r2 = c.get("/api/lab/sessions", params={"include_sandbox": "true"})
        assert r2.status_code == 200
        sids2 = [it["session_id"] for it in r2.json()["items"]]
        assert "sid_prod" in sids2
        assert "sid_sb" in sids2

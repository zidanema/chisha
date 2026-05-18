"""D-079 PR-1: trace_store 模块单测.

覆盖:
- write/read roundtrip
- 写失败不抛 (best-effort)
- sandbox 隔离 (prod 写不进 sandbox 反之亦然)
- 损坏 JSON fail-closed (备份 .corrupt.{ts}.bak + 抛 TraceCorrupt)
- schema __version 不匹配抛 TraceVersionMismatch
- list_traces 跳过损坏并返 corrupt_count
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chisha import trace_store


def _minimal_trace(sid: str = "sess_test") -> dict:
    return {
        "session_id": sid,
        "started_at": "2026-05-16T12:00:00+00:00",
        "total_latency_ms": 100,
        "l1": {"summary": {}, "meal": "lunch"},
        "l2": {"summary": {}, "top": []},
        "l3": {"used": False, "status": "skipped"},
        "final": [],
        "refine": {"applied": False},
        "__source": "production",
        "__parent_session_id": None,
        "__llm_called": False,
        "__frozen": {"ctx": {}, "today": "2026-05-16"},
        "__config": {"use_llm_rerank": None},
    }


def test_write_read_roundtrip(tmp_path: Path) -> None:
    trace = _minimal_trace("sess_lunch_001")
    ok = trace_store.write_trace("sess_lunch_001", trace, root=tmp_path)
    assert ok
    got = trace_store.read_trace("sess_lunch_001", root=tmp_path)
    assert got is not None
    assert got["session_id"] == "sess_lunch_001"
    assert got["__version"] == trace_store.TRACE_SCHEMA_VERSION


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert trace_store.read_trace("nonexistent", root=tmp_path) is None


def test_invalid_session_id_rejected(tmp_path: Path) -> None:
    trace = _minimal_trace()
    # 路径反注入
    assert not trace_store.write_trace("../escape", trace, root=tmp_path)
    assert not trace_store.write_trace("a/b", trace, root=tmp_path)
    assert not trace_store.write_trace("", trace, root=tmp_path)


def test_write_failure_does_not_raise(tmp_path: Path, monkeypatch) -> None:
    """写盘失败 (e.g. 路径权限) 必须返 False, 不抛, 不阻断 recommend."""
    trace = _minimal_trace()

    # monkeypatch Path.replace 抛 OSError 模拟磁盘满
    original_replace = Path.replace

    def boom(self, target):
        raise OSError("disk full simulation")

    monkeypatch.setattr(Path, "replace", boom)
    try:
        ok = trace_store.write_trace("sess_x", trace, root=tmp_path)
        assert ok is False
    finally:
        monkeypatch.setattr(Path, "replace", original_replace)


def test_corruption_fail_closed(tmp_path: Path) -> None:
    """JSON 损坏 → 抛 TraceCorrupt + 备份 .corrupt.{ts}.bak (同 feedback_store MED-3)."""
    d = trace_store.data_root.recommend_trace_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "sess_broken.json"
    p.write_text("not json {{", encoding="utf-8")
    with pytest.raises(trace_store.TraceCorrupt) as exc_info:
        trace_store.read_trace("sess_broken", root=tmp_path)
    assert "corrupt" in str(exc_info.value).lower()
    # 原文件已被 rename 走
    assert not p.exists()
    backups = list(d.glob("sess_broken.json.corrupt.*.bak"))
    assert len(backups) == 1


def test_version_mismatch_raises(tmp_path: Path) -> None:
    """__version 不识别抛 TraceVersionMismatch (调用方决定 409)."""
    trace = _minimal_trace()
    # 写入后手改 version
    trace_store.write_trace("sess_v9", trace, root=tmp_path)
    p = trace_store.data_root.recommend_trace_dir(tmp_path) / "sess_v9.json"
    data = json.loads(p.read_text())
    data["__version"] = 99
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(trace_store.TraceVersionMismatch) as exc_info:
        trace_store.read_trace("sess_v9", root=tmp_path)
    assert exc_info.value.found == 99
    assert exc_info.value.expected == trace_store.TRACE_SCHEMA_VERSION


def test_list_traces_skips_corrupt_with_count(tmp_path: Path) -> None:
    """list 跳过损坏并返 corrupt_count, 不抛."""
    # 1 OK
    trace_store.write_trace("sess_a", _minimal_trace("sess_a"), root=tmp_path)
    # 1 OK
    trace_store.write_trace("sess_b", _minimal_trace("sess_b"), root=tmp_path)
    # 2 corrupt (1 broken JSON, 1 顶层非 dict)
    d = trace_store.data_root.recommend_trace_dir(tmp_path)
    (d / "sess_bad1.json").write_text("garbage", encoding="utf-8")
    (d / "sess_bad2.json").write_text("[1, 2, 3]", encoding="utf-8")

    items, corrupt_count = trace_store.list_traces(root=tmp_path)
    sids = {it["session_id"] for it in items}
    assert "sess_a" in sids
    assert "sess_b" in sids
    assert corrupt_count == 2


def test_list_traces_filters_meal_type(tmp_path: Path) -> None:
    t1 = _minimal_trace("sess_lunch_1")
    t1["__frozen"]["meal_type"] = "lunch"
    t2 = _minimal_trace("sess_dinner_1")
    t2["__frozen"]["meal_type"] = "dinner"
    trace_store.write_trace("sess_lunch_1", t1, root=tmp_path)
    trace_store.write_trace("sess_dinner_1", t2, root=tmp_path)
    items, _ = trace_store.list_traces(root=tmp_path, meal_type="lunch")
    sids = {it["session_id"] for it in items}
    assert "sess_lunch_1" in sids
    assert "sess_dinner_1" not in sids


def test_sandbox_isolation(tmp_path: Path) -> None:
    """sandbox 启用时 trace 写 logs/sandbox/recommend_trace/, prod 读不到."""
    from chisha import sandbox

    # 不启用 sandbox 写一条 → 写在 prod
    trace_store.write_trace("sess_prod_only", _minimal_trace("sess_prod_only"), root=tmp_path)
    prod_path = tmp_path / "logs" / "recommend_trace" / "sess_prod_only.json"
    assert prod_path.exists()

    # 启用 sandbox 后写 → 写在 sandbox, prod 不变
    sandbox.init(root=tmp_path)
    try:
        assert sandbox.is_enabled(tmp_path)
        trace_store.write_trace("sess_sandbox_only", _minimal_trace("sess_sandbox_only"),
                                  root=tmp_path)
        sb_path = tmp_path / "logs" / "sandbox" / "recommend_trace" / "sess_sandbox_only.json"
        assert sb_path.exists()
        # prod 不变
        assert not (tmp_path / "logs" / "recommend_trace" / "sess_sandbox_only.json").exists()

        # sandbox list 不含 prod trace
        items, _ = trace_store.list_traces(root=tmp_path)
        sids = {it["session_id"] for it in items}
        assert "sess_sandbox_only" in sids
        assert "sess_prod_only" not in sids
    finally:
        sandbox.disable(root=tmp_path)

    # 关 sandbox 后 list 又回 prod
    items, _ = trace_store.list_traces(root=tmp_path)
    sids = {it["session_id"] for it in items}
    assert "sess_prod_only" in sids
    assert "sess_sandbox_only" not in sids


def test_normal_trace_size_no_truncation(tmp_path: Path) -> None:
    """日常 trace (远小于 50MB sanity bound) 不应触发任何裁剪.

    用户决策: 不省空间 (D-079 PR-1 收尾). 5MB 以下的 raw 直接写盘,
    保留全量内容. 只有意外/恶意超 50MB 时才走 _truncate_for_size 防失控.
    """
    trace = _minimal_trace("sess_normal")
    # 2MB raw — 远小于 50MB sanity bound
    raw_2mb = "x" * (2 * 1024 * 1024)
    trace["l3"]["raw_response"] = raw_2mb
    ok = trace_store.write_trace("sess_normal", trace, root=tmp_path)
    assert ok
    got = trace_store.read_trace("sess_normal", root=tmp_path)
    assert got is not None
    # 2MB 远小于 50MB, 应原样保留, 不应包含截断标记
    assert got["l3"]["raw_response"] == raw_2mb


def test_truncation_only_kicks_in_at_sanity_bound(tmp_path: Path, monkeypatch) -> None:
    """裁剪仅在超 MAX_TRACE_BYTES (50MB) 时触发, 防失控用.

    用 monkeypatch 临时把 MAX 调小到 100KB 验证裁剪逻辑可工作.
    """
    monkeypatch.setattr(trace_store, "MAX_TRACE_BYTES", 100 * 1024)
    trace = _minimal_trace("sess_huge")
    # 200KB raw — 在 monkeypatched MAX (100KB) 之上, 应触发裁剪
    trace["l3"]["raw_response"] = "y" * (200 * 1024)
    ok = trace_store.write_trace("sess_huge", trace, root=tmp_path)
    assert ok
    got = trace_store.read_trace("sess_huge", root=tmp_path)
    assert got is not None
    raw = got["l3"]["raw_response"]
    assert "truncated" in raw
    assert len(raw) < 50 * 1024


# ────────────────────────── T-00: v1 → v2 backward compat


def _write_raw_v1_trace(tmp_path: Path, sid: str, extra: dict | None = None) -> Path:
    """绕过 write_trace 直接落 __version=1 的 trace, 模拟 bump 前历史数据."""
    d = trace_store.data_root.recommend_trace_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}.json"
    trace = _minimal_trace(sid)
    trace["__version"] = 1
    # 模拟 v1 没有 l1.hard_filter_events 字段
    trace["l1"] = {"summary": {}, "meal": "lunch"}
    if extra:
        trace.update(extra)
    p.write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")
    return p


def test_read_v1_trace_migrates_to_v2_shape(tmp_path: Path) -> None:
    """v=1 trace 仍可读, read_trace 注入空 hard_filter_events 让 caller 看到 v=2 shape."""
    _write_raw_v1_trace(tmp_path, "sess_v1")
    got = trace_store.read_trace("sess_v1", root=tmp_path)
    assert got is not None
    # __version 字段保留原值 (不修磁盘 source-of-truth)
    assert got["__version"] == 1
    # l1.hard_filter_events 已被 on-read 注入
    assert got["l1"]["hard_filter_events"] == []


def test_read_v1_does_not_write_back_to_disk(tmp_path: Path) -> None:
    """on-read migration 不写回磁盘, v=1 磁盘文件保持 v=1."""
    p = _write_raw_v1_trace(tmp_path, "sess_v1_no_writeback")
    trace_store.read_trace("sess_v1_no_writeback", root=tmp_path)
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["__version"] == 1
    assert "hard_filter_events" not in on_disk.get("l1", {})


def test_v2_trace_roundtrip_with_hard_filter_events(tmp_path: Path) -> None:
    """v=2 write + read 看到 hard_filter_events 字段且保留事件内容."""
    trace = _minimal_trace("sess_v2_events")
    trace_store.append_hard_filter_event(
        trace,
        category="L0_A_medical",
        rule="no_peanut_allergy",
        dropped_count=3,
        kept_count=27,
        refine_override=False,
    )
    ok = trace_store.write_trace("sess_v2_events", trace, root=tmp_path)
    assert ok
    got = trace_store.read_trace("sess_v2_events", root=tmp_path)
    assert got is not None
    # D-087: TRACE_SCHEMA_VERSION 升 v3 后, write_trace 总落 v=3.
    # 旧 v=2 测试改成断言 == TRACE_SCHEMA_VERSION (动态), 表达 "当前最新版".
    assert got["__version"] == trace_store.TRACE_SCHEMA_VERSION
    events = got["l1"]["hard_filter_events"]
    assert len(events) == 1
    assert events[0]["category"] == "L0_A_medical"
    assert events[0]["rule"] == "no_peanut_allergy"
    assert events[0]["dropped_count"] == 3
    assert events[0]["kept_count"] == 27
    assert events[0]["refine_override"] is False


def test_v99_unknown_version_still_rejected(tmp_path: Path) -> None:
    """ACCEPTED_TRACE_VERSIONS = {1, 2} 外的版本仍抛 TraceVersionMismatch."""
    trace = _minimal_trace()
    trace_store.write_trace("sess_v99", trace, root=tmp_path)
    p = trace_store.data_root.recommend_trace_dir(tmp_path) / "sess_v99.json"
    data = json.loads(p.read_text())
    data["__version"] = 99
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(trace_store.TraceVersionMismatch) as exc_info:
        trace_store.read_trace("sess_v99", root=tmp_path)
    assert exc_info.value.found == 99


def test_list_traces_includes_v1_after_bump(tmp_path: Path) -> None:
    """Codex audit 找出的盲点: list_traces 必须列出 v=1 历史 trace.

    Sidebar (`/api/debug/sessions`) 走 list_traces, 漏改会让旧 trace 消失.
    """
    # 一条 v=1 (写绕过 write_trace)
    _write_raw_v1_trace(tmp_path, "sess_v1_list")
    # 一条 v=2 (走 write_trace 自动落当前版本)
    trace_store.write_trace("sess_v2_list", _minimal_trace("sess_v2_list"), root=tmp_path)

    items, corrupt_count = trace_store.list_traces(root=tmp_path)
    sids = {it["session_id"] for it in items}
    assert "sess_v1_list" in sids
    assert "sess_v2_list" in sids
    assert corrupt_count == 0


def test_list_traces_still_skips_unknown_version(tmp_path: Path) -> None:
    """v=99 仍被 list_traces 静默跳过 (不算 corrupt)."""
    _write_raw_v1_trace(tmp_path, "sess_v_unknown",
                        extra={"__version": 99})
    items, corrupt_count = trace_store.list_traces(root=tmp_path)
    sids = {it["session_id"] for it in items}
    assert "sess_v_unknown" not in sids
    assert corrupt_count == 0  # 版本不识别不算 corrupt


def test_fresh_write_v2_trace_has_hard_filter_events(tmp_path: Path) -> None:
    """Codex review blocker #1 防线: write_trace 出去的 v2 trace 必含 hard_filter_events.

    api._build_trace / debug_recommend._build_l1_trace 不主动 init 时 write_trace 兜底.
    """
    trace = {
        "session_id": "sess_fresh_v2",
        "started_at": "2026-05-16T12:00:00+00:00",
        "l1": {"summary": {}, "meal": "lunch"},
        "l2": {"summary": {}},
        "l3": {"used": False, "status": "skipped"},
        "final": [],
    }
    ok = trace_store.write_trace("sess_fresh_v2", trace, root=tmp_path)
    assert ok
    got = trace_store.read_trace("sess_fresh_v2", root=tmp_path)
    assert got is not None
    # D-087: write_trace 现在落 v=3 (最新). 用动态常量避免再次 schema bump 漏改.
    assert got["__version"] == trace_store.TRACE_SCHEMA_VERSION
    assert got["l1"]["hard_filter_events"] == []


def test_fresh_write_preserves_existing_hard_filter_events(tmp_path: Path) -> None:
    """write_trace 兜底不能覆盖上游已 append 的事件."""
    trace = {
        "session_id": "sess_preserves",
        "started_at": "2026-05-16T12:00:00+00:00",
        "l1": {"summary": {}, "meal": "lunch", "hard_filter_events": [
            {"event_type": "hard_filter", "category": "L0_A_medical",
             "rule": "no_peanut", "dropped_count": 1, "kept_count": 9,
             "refine_override": False, "timestamp": 1234.5},
        ]},
        "l2": {}, "l3": {}, "final": [],
    }
    trace_store.write_trace("sess_preserves", trace, root=tmp_path)
    got = trace_store.read_trace("sess_preserves", root=tmp_path)
    assert got is not None
    events = got["l1"]["hard_filter_events"]
    assert len(events) == 1
    assert events[0]["rule"] == "no_peanut"

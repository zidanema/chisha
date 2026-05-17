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
    """D-085 (revised from D-077): sandbox 启用时 trace 写 logs/sandbox/
    recommend_trace/. list_traces 默认 include_sandbox=False 只看 prod, 不再
    跟 sandbox.is_enabled 全局状态走 (invariant 4).
    """
    from chisha import sandbox

    # 不启用 sandbox 写一条 → 写在 prod, is_sandbox=False
    trace_store.write_trace("sess_prod_only", _minimal_trace("sess_prod_only"), root=tmp_path)
    prod_path = tmp_path / "logs" / "recommend_trace" / "sess_prod_only.json"
    assert prod_path.exists()

    # 启用 sandbox 后写 → 物理写到 sandbox 目录, prod 目录不变, trace.is_sandbox=True
    sandbox.init(root=tmp_path)
    try:
        assert sandbox.is_enabled(tmp_path)
        trace_store.write_trace("sess_sandbox_only", _minimal_trace("sess_sandbox_only"),
                                  root=tmp_path)
        sb_path = tmp_path / "logs" / "sandbox" / "recommend_trace" / "sess_sandbox_only.json"
        assert sb_path.exists()
        assert not (tmp_path / "logs" / "recommend_trace" / "sess_sandbox_only.json").exists()

        # D-085: 默认 list 不混 sandbox — 即便 sandbox 启用, 默认看到的还是 prod
        items, _ = trace_store.list_traces(root=tmp_path)
        sids = {it["session_id"] for it in items}
        assert "sess_prod_only" in sids
        assert "sess_sandbox_only" not in sids

        # include_sandbox=True 才能看到 sandbox trace
        items_all, _ = trace_store.list_traces(root=tmp_path, include_sandbox=True)
        sids_all = {it["session_id"] for it in items_all}
        assert "sess_prod_only" in sids_all
        assert "sess_sandbox_only" in sids_all
    finally:
        sandbox.disable(root=tmp_path)

    # 关 sandbox 后 list 仍只看 prod
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

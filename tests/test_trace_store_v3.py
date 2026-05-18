"""D-087 trace_store v3 单测.

覆盖:
- migrate_v2_to_v3: v2 单文件 → {sid}/meta.json + rounds/R1.json + v2 rename .migrated_v2
- append_round: lock + 服务端签发 round_id (R1/R2/.../R{n}, 永不重号)
- read_trace_v3_view: v3 + v2 fallback 都能给 {meta, rounds[stub]}
- read_round_full: v3 任意 round, v2 fallback 仅 R1
- list_traces_v3: 扫 v3 目录 + v2 单文件混排
- lock_meta 互斥: 串行化 append_round (无并发漏号)
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from chisha import trace_store


def _v2_minimal(sid: str) -> dict:
    return {
        "__version": 2,
        "__source": "production",
        "session_id": sid,
        "started_at": "2026-05-18T12:00:00",
        "total_latency_ms": 2500,
        "ctx_latency_ms": 14,
        "__frozen": {"meal_type": "lunch", "zone": "shenzhen-bay"},
        "l1": {"meal": "lunch", "funnel": [{"value": 1200}]},
        "l2": {"candidates_to_l3": 60},
        "l3": {"status": "ok"},
        "final": [{
            "restaurant": {"name": "X 餐厅"},
            "dishes": [{"name": "青菜"}, {"name": "米"}],
        }],
        "refine": {"applied": False},
    }


def _round_payload(label: str, user_input: str) -> dict:
    return {
        "started_at": "2026-05-18T12:36:00",
        "label": label,
        "user_input": user_input,
        "intent_v2": {"redirect": {"cuisine_want": ["汤"]}},
        "narrative": "用户要汤",
        "kpi": {"combos": 1180, "l2_top": 60, "top1": "Y 餐厅", "latency_ms": 2300},
        "l1": None, "l2": None, "l3": {"status": "ok"}, "final": [],
    }


def _setup_v2(tmp_path: Path, sid: str) -> Path:
    trace_dir = tmp_path / "logs" / "recommend_trace"
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / f"{sid}.json").write_text(
        json.dumps(_v2_minimal(sid)), encoding="utf-8",
    )
    return trace_dir


def test_migrate_v2_to_v3(tmp_path):
    sid = "sess_001"
    trace_dir = _setup_v2(tmp_path, sid)
    assert not trace_store.is_v3_trace(sid, root=tmp_path)
    assert trace_store.has_v2_trace(sid, root=tmp_path)

    assert trace_store.migrate_v2_to_v3(sid, root=tmp_path) is True
    assert trace_store.is_v3_trace(sid, root=tmp_path)
    assert (trace_dir / sid / "meta.json").exists()
    assert (trace_dir / sid / "rounds" / "R1.json").exists()
    # v2 文件被 rename 保留 (.migrated_v2)
    assert not (trace_dir / f"{sid}.json").exists()
    assert (trace_dir / f"{sid}.json.migrated_v2").exists()


def test_migrate_idempotent(tmp_path):
    sid = "sess_002"
    _setup_v2(tmp_path, sid)
    assert trace_store.migrate_v2_to_v3(sid, root=tmp_path) is True
    # 再次调用应也返 True (已经是 v3, 直接 noop)
    assert trace_store.migrate_v2_to_v3(sid, root=tmp_path) is True


def test_append_round_assigns_sequential_ids(tmp_path):
    sid = "sess_003"
    _setup_v2(tmp_path, sid)
    rid1 = trace_store.append_round(sid, _round_payload("a", "a"), root=tmp_path)
    rid2 = trace_store.append_round(sid, _round_payload("b", "b"), root=tmp_path)
    rid3 = trace_store.append_round(sid, _round_payload("c", "c"), root=tmp_path)
    assert rid1 == "R2"
    assert rid2 == "R3"
    assert rid3 == "R4"
    meta = trace_store.read_meta(sid, root=tmp_path)
    assert meta["round_ids"] == ["R1", "R2", "R3", "R4"]
    assert meta["latest_round"] == "R4"
    assert meta["refine_count"] == 3


def test_append_round_refuses_orphan(tmp_path):
    """没有 base trace (v2 / v3) 时, append_round 应返 None 而非创孤儿."""
    sid = "sess_orphan"
    (tmp_path / "logs" / "recommend_trace").mkdir(parents=True)
    rid = trace_store.append_round(sid, _round_payload("x", "x"), root=tmp_path)
    assert rid is None


def test_read_trace_v3_view_on_v2(tmp_path):
    """v2 单文件 trace 走 read_trace_v3_view 应在内存升 v3 view (不写回)."""
    sid = "sess_004"
    trace_dir = _setup_v2(tmp_path, sid)
    view = trace_store.read_trace_v3_view(sid, root=tmp_path)
    assert view is not None
    assert view["meta"]["session_id"] == sid
    assert len(view["rounds"]) == 1
    assert view["rounds"][0]["id"] == "R1"
    # 没有写回: v3 文件仍不存在
    assert not (trace_dir / sid / "meta.json").exists()
    assert (trace_dir / f"{sid}.json").exists()


def test_read_trace_v3_view_on_v3(tmp_path):
    sid = "sess_005"
    _setup_v2(tmp_path, sid)
    trace_store.append_round(sid, _round_payload("追问1", "追问1"), root=tmp_path)
    view = trace_store.read_trace_v3_view(sid, root=tmp_path)
    assert len(view["rounds"]) == 2
    assert [r["id"] for r in view["rounds"]] == ["R1", "R2"]
    # stub 不应含 l1/l2/l3/final body
    assert "l1" not in view["rounds"][0]
    assert "intent_v2" in view["rounds"][1]


def test_read_round_full_v3_and_v2(tmp_path):
    sid = "sess_006"
    _setup_v2(tmp_path, sid)
    # v2: read_round_full R1 应能从 v2 单文件构造
    r1 = trace_store.read_round_full(sid, "R1", root=tmp_path)
    assert r1 is not None
    assert r1["id"] == "R1"
    assert r1["l1"] is not None
    # v2: R2 不存在
    r2_v2 = trace_store.read_round_full(sid, "R2", root=tmp_path)
    assert r2_v2 is None
    # 触发迁移 + append R2
    trace_store.append_round(sid, _round_payload("R2", "R2"), root=tmp_path)
    r1_v3 = trace_store.read_round_full(sid, "R1", root=tmp_path)
    assert r1_v3["l1"] is not None
    r2_v3 = trace_store.read_round_full(sid, "R2", root=tmp_path)
    assert r2_v3["user_input"] == "R2"


def test_list_traces_v3_mixed_layouts(tmp_path):
    """v3 + v2 混排, 按 mtime 排序."""
    sid_v3 = "sess_v3_only"
    sid_v2 = "sess_v2_only"
    _setup_v2(tmp_path, sid_v3)
    _setup_v2(tmp_path, sid_v2)
    # 把 sid_v3 升 v3
    trace_store.append_round(sid_v3, _round_payload("R2", "R2"), root=tmp_path)
    items, corrupt = trace_store.list_traces_v3(root=tmp_path)
    sids = {it["session_id"] for it in items}
    assert sids == {sid_v3, sid_v2}
    assert corrupt == 0
    # v3 一项 round_ids = ["R1", "R2"]
    v3_item = next(it for it in items if it["session_id"] == sid_v3)
    assert v3_item["round_ids"] == ["R1", "R2"]
    assert v3_item["refine_count"] == 1
    # v2 一项 round_ids = ["R1"]
    v2_item = next(it for it in items if it["session_id"] == sid_v2)
    assert v2_item["round_ids"] == ["R1"]
    assert v2_item["refine_count"] == 0


def test_lock_meta_serializes_appends(tmp_path):
    """并发 append_round 应被 lock_meta 串行化, round_ids 必须连续递增, 无重号."""
    sid = "sess_concurrent"
    _setup_v2(tmp_path, sid)

    errors: list[Exception] = []
    rids: list[str] = []
    lock = threading.Lock()

    def worker(i: int):
        try:
            rid = trace_store.append_round(
                sid, _round_payload(f"t{i}", f"t{i}"), root=tmp_path,
            )
            with lock:
                rids.append(rid)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors, f"unexpected errors: {errors}"
    # 全部 8 个线程都成功签出 round
    assert len(rids) == 8
    # round_ids 应该是 R2..R9 (R1 是 migrate 出来的), 集合等于 {R2..R9}, 无重号
    assert set(rids) == {f"R{i}" for i in range(2, 10)}
    meta = trace_store.read_meta(sid, root=tmp_path)
    assert meta["round_ids"] == [f"R{i}" for i in range(1, 10)]
    assert meta["refine_count"] == 8

    # Codex M2: 读全部 R2..R9.json, 确认每个线程 payload 落盘 (user_input 唯一对应一个 round file).
    seen_inputs: list[str] = []
    for rid in [f"R{i}" for i in range(2, 10)]:
        rdata = trace_store.read_round(sid, rid, root=tmp_path)
        assert rdata is not None, f"{rid} missing"
        seen_inputs.append(rdata["user_input"])
    # 8 个 worker 的 user_input = t0..t7, 全在, 无重复
    assert sorted(seen_inputs) == sorted([f"t{i}" for i in range(8)])


def test_append_round_on_corrupt_v2_preserves_original(tmp_path):
    """Codex M1: corrupt v2 文件遇 append_round → 不写盘, 原文件原地不动, 无 sid 目录被创建."""
    sid = "sess_corrupt"
    trace_dir = tmp_path / "logs" / "recommend_trace"
    trace_dir.mkdir(parents=True, exist_ok=True)
    v2_path = trace_dir / f"{sid}.json"
    corrupt_bytes = b'{"__version": 2, "session_id": "sess_corrupt" '  # 不闭合
    v2_path.write_bytes(corrupt_bytes)
    original_size = v2_path.stat().st_size

    rid = trace_store.append_round(
        sid, _round_payload("追问", "测试"), root=tmp_path,
    )
    assert rid is None
    # 原 v2 文件原地不动
    assert v2_path.exists()
    assert v2_path.read_bytes() == corrupt_bytes
    assert v2_path.stat().st_size == original_size
    # 没创出 {sid}/ 目录 (lock 文件在父目录, 不会污染 sid 路径)
    assert not (trace_dir / sid).exists()

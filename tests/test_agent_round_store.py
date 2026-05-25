"""T5: agent_round_store 协议 round 状态机 + 幂等单测 (D-074)."""
from __future__ import annotations

import pytest

from chisha import agent_round_store as rs


@pytest.fixture
def root(tmp_path):
    return tmp_path


def _meta():
    return {"meal_type": "lunch", "zone": "shenzhen-bay",
            "today": "2026-05-25", "daily_mood": None, "refine_input": "辣点"}


# ─────────────────────── pending → resolved ───────────────────────

def test_create_pending_then_resolve(root):
    rs.create_pending("sid1", round_id="R1", correlation_id="sid1::R1::extract",
                      extract_spec={"operation_kind": "extract"}, meta=_meta(), root=root)
    cur = rs.read_round("sid1", root)
    assert cur["status"] == "pending"
    assert cur["operation"] == "extract"

    rs.advance_to_resolved("sid1", correlation_id="sid1::R1::rerank",
                           rerank_spec={"operation_kind": "rerank"},
                           intent={"redirect": {}}, root=root)
    cur = rs.read_round("sid1", root)
    assert cur["status"] == "resolved"
    assert cur["operation"] == "rerank"
    assert cur["rerank_spec"]["operation_kind"] == "rerank"


def test_create_resolved_no_context(root):
    rs.create_resolved("sid2", round_id="R1", correlation_id="sid2::R1::rerank",
                       rerank_spec={"operation_kind": "rerank"}, intent=None,
                       frozen=_meta(), root=root)
    cur = rs.read_round("sid2", root)
    assert cur["status"] == "resolved"
    assert cur["intent"] is None


# ─────────────────────── 幂等 ───────────────────────

def test_create_pending_idempotent_same_correlation(root):
    a = rs.create_pending("sid3", round_id="R1", correlation_id="sid3::R1::extract",
                          extract_spec={"x": 1}, meta=_meta(), root=root)
    b = rs.create_pending("sid3", round_id="R1", correlation_id="sid3::R1::extract",
                          extract_spec={"x": 1}, meta=_meta(), root=root)
    assert a["created_at"] == b["created_at"]  # 返已存, 不重建


def test_advance_idempotent_same_correlation(root):
    rs.create_pending("sid4", round_id="R1", correlation_id="sid4::R1::extract",
                      extract_spec={}, meta=_meta(), root=root)
    rs.advance_to_resolved("sid4", correlation_id="sid4::R1::rerank",
                           rerank_spec={"v": 1}, intent=None, root=root)
    # 重试同 correlation → 幂等返已存, 不报错
    again = rs.advance_to_resolved("sid4", correlation_id="sid4::R1::rerank",
                                   rerank_spec={"v": 999}, intent=None, root=root)
    assert again["rerank_spec"]["v"] == 1  # 不被覆盖


# ─────────────────────── 状态非法转移 ───────────────────────

def test_double_start_rejected(root):
    rs.create_pending("sid5", round_id="R1", correlation_id="sid5::R1::extract",
                      extract_spec={}, meta=_meta(), root=root)
    with pytest.raises(rs.RoundStateError):
        rs.create_pending("sid5", round_id="R1", correlation_id="sid5::R2::extract",
                          extract_spec={}, meta=_meta(), root=root)


def test_resolve_without_pending_rejected(root):
    with pytest.raises(rs.RoundStateError):
        rs.advance_to_resolved("nope", correlation_id="nope::R1::rerank",
                               rerank_spec={}, intent=None, root=root)


def test_require_resolved_rejects_pending(root):
    rs.create_pending("sid6", round_id="R1", correlation_id="sid6::R1::extract",
                      extract_spec={}, meta=_meta(), root=root)
    with pytest.raises(rs.RoundStateError):
        rs.require_resolved("sid6", root)


def test_require_resolved_ok(root):
    rs.create_resolved("sid7", round_id="R1", correlation_id="sid7::R1::rerank",
                       rerank_spec={"ok": 1}, intent=None, frozen=_meta(), root=root)
    cur = rs.require_resolved("sid7", root)
    assert cur["rerank_spec"]["ok"] == 1


# ─────────────────────── clear + 隔离 ───────────────────────

def test_clear_round(root):
    rs.create_resolved("sid8", round_id="R1", correlation_id="sid8::R1::rerank",
                       rerank_spec={}, intent=None, frozen=_meta(), root=root)
    rs.clear_round("sid8", root)
    assert rs.read_round("sid8", root) is None


def test_isolation_from_trace_round_index(root):
    """codex #2: in-flight 状态存独立目录, 不进 recommend_trace 可见索引."""
    from chisha import data_root
    rs.create_pending("sid9", round_id="R1", correlation_id="sid9::R1::extract",
                      extract_spec={}, meta=_meta(), root=root)
    # agent_round_dir 与 recommend_trace_dir 是不同目录
    assert data_root.agent_round_dir(root) != data_root.recommend_trace_dir(root)
    # recommend_trace 目录里没有 sid9 (未发布)
    trace_dir = data_root.recommend_trace_dir(root)
    assert not (trace_dir / "sid9.json").exists()
    assert not (trace_dir / "sid9").exists()


def test_can_transition():
    assert rs.can_transition("pending", "resolved")
    assert not rs.can_transition("resolved", "pending")
    assert not rs.can_transition("resolved", "ready")

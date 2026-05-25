"""T6: choose 幂等写协议单测 (D-074)."""
from __future__ import annotations

import json

import pytest

from chisha import agent_choose, feedback_store
from chisha.data_root import meal_log_path


@pytest.fixture
def root(tmp_path):
    return tmp_path


def _accept(root, sid="s1", card_id="c_0_r1", rank=1):
    return agent_choose.record_choice(
        root, sid=sid, card_id=card_id, action="accept",
        meal_type="lunch", restaurant_id="r1", restaurant_name="店1",
        summary="店1 · 番茄牛腩", dishes=[{"main_ingredient_type": "牛肉",
                                          "canonical_name": "番茄牛腩"}],
        accepted_rank=rank, zone="shenzhen-bay", combo_index=0,
    )


def _meal_log_lines(root):
    p = meal_log_path(root)
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


# ─────────────────────── accept 双写 ───────────────────────

def test_accept_writes_both(root):
    out = _accept(root)
    assert out["accept_written"] is True
    assert out["meal_log_written"] is True
    # feedback_store
    store = feedback_store.load_store(root)
    acc = store["accepted"]["s1"]
    assert acc["accepted_rank"] == 1
    assert acc["choice_key"] == "s1::R1::c_0_r1::accept"
    # meal_log
    lines = _meal_log_lines(root)
    assert len(lines) == 1
    assert lines[0]["choice_key"] == "s1::R1::c_0_r1::accept"
    assert lines[0]["candidate_id"] == "c_0_r1"


def test_accept_rerun_idempotent(root):
    _accept(root)
    out2 = _accept(root)
    # 重跑: 两写都已完成 → 不重写
    assert out2["accept_written"] is False
    assert out2["meal_log_written"] is False
    assert out2["already_complete"] is True
    # meal_log 仍只有 1 行 (没重复 append)
    assert len(_meal_log_lines(root)) == 1


def test_accept_partial_failure_rerun_fills_gap(root):
    """部分失败 (feedback 写成, meal_log 没写) → 重跑只补 meal_log (设计 §6)."""
    # 先只写 feedback (模拟 meal_log 写失败前中断)
    feedback_store.record_accept(root, "s2", candidate_rank=1, meal_type="lunch",
                                 restaurant_name="店2", summary="x",
                                 choice_key="s2::R1::c_0_r2::accept")
    assert len(_meal_log_lines(root)) == 0
    # 重跑 record_choice: feedback 已有 choice_key → 跳过; meal_log 缺 → 补写
    out = agent_choose.record_choice(
        root, sid="s2", card_id="c_0_r2", action="accept", meal_type="lunch",
        restaurant_id="r2", restaurant_name="店2", summary="x",
        dishes=[{"main_ingredient_type": "鸡肉", "canonical_name": "鸡"}],
        accepted_rank=1,
    )
    assert out["accept_written"] is False    # feedback 已完成, 不重写
    assert out["meal_log_written"] is True   # 补缺
    assert len(_meal_log_lines(root)) == 1


def test_different_card_id_not_deduped(root):
    """不同 card_id = 不同 choice_key → 各自独立写 (改主意选另一张卡)."""
    _accept(root, card_id="c_0_r1", rank=1)
    out2 = _accept(root, card_id="c_1_r2", rank=2)
    assert out2["accept_written"] is True
    # 注意: feedback accepted[sid] 被覆盖 (按 sid), 但 meal_log 应有 2 行
    assert len(_meal_log_lines(root)) == 2


# ─────────────────────── skip ───────────────────────

def test_skip_writes_feedback_only(root):
    out = agent_choose.record_choice(
        root, sid="s3", card_id="c_0_r1", action="skip", meal_type="lunch",
        skip_reason="没胃口",
    )
    assert out["skip_written"] is True
    assert out["meal_log_written"] is False
    store = feedback_store.load_store(root)
    acc = store["accepted"]["s3"]
    assert acc["skipped"] is True
    assert acc["choice_key"] == "s3::R1::c_0_r1::skip"
    # skip 不写 meal_log
    assert len(_meal_log_lines(root)) == 0


def test_skip_rerun_idempotent(root):
    agent_choose.record_choice(root, sid="s4", card_id="c_0_r1", action="skip",
                               meal_type="lunch")
    out2 = agent_choose.record_choice(root, sid="s4", card_id="c_0_r1",
                                      action="skip", meal_type="lunch")
    assert out2["skip_written"] is False
    assert out2["already_complete"] is True


def test_invalid_action_rejected(root):
    with pytest.raises(ValueError):
        agent_choose.record_choice(root, sid="s5", card_id="c", action="maybe",  # type: ignore[arg-type]
                                   meal_type="lunch")

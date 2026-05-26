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


def test_same_sid_rechoose_supersedes(root):
    """F3: 同 sid 改选另一张卡 → 覆盖 (一餐至多一条 accept, 以最后选的为准).

    旧行为 (D-074 T6 初版) 是各自独立双写 → 一餐两条 meal_log 污染 diversity
    cooldown. F3 改为 upsert: 改选覆盖, meal_log 单条反映用户最终吃的.
    """
    _accept(root, card_id="c_0_r1", rank=1)
    out2 = _accept(root, card_id="c_1_r2", rank=2)
    assert out2["accept_written"] is True
    assert out2["superseded"] is False
    lines = _meal_log_lines(root)
    assert len(lines) == 1                          # 覆盖, 不双写
    assert lines[0]["candidate_id"] == "c_1_r2"     # 最新选择
    # feedback accepted[sid] 也是最新卡
    store = feedback_store.load_store(root)
    assert store["accepted"]["s1"]["choice_key"] == "s1::R1::c_1_r2::accept"


def test_stale_round_accept_rejected(root):
    """F3 顺序保护 (codex): 旧轮 accept 延迟到达, 不覆盖已写的更高轮选择."""
    # R2 先 accept (更高轮 = 用户最终在 refine 后的选择)
    agent_choose.record_choice(
        root, sid="s9", card_id="cB", action="accept", round_id="R2",
        meal_type="lunch", restaurant_id="rB", restaurant_name="B店",
        dishes=[{"main_ingredient_type": "鸡肉"}], accepted_rank=1,
        zone="z", combo_index=0,
    )
    # R1 旧轮 accept 延迟到达 → 拒绝回写 (meal_log + feedback 都不动)
    out = agent_choose.record_choice(
        root, sid="s9", card_id="cA", action="accept", round_id="R1",
        meal_type="lunch", restaurant_id="rA", restaurant_name="A店",
        dishes=[{"main_ingredient_type": "牛肉"}], accepted_rank=1,
        zone="z", combo_index=0,
    )
    assert out["superseded"] is True
    assert out["meal_log_written"] is False
    assert out["accept_written"] is False           # feedback 也不回写翻转
    lines = _meal_log_lines(root)
    assert len(lines) == 1
    assert lines[0]["candidate_id"] == "cB"          # 保留更高轮
    store = feedback_store.load_store(root)
    assert store["accepted"]["s9"]["choice_key"] == "s9::R2::cB::accept"


def test_stale_round_retry_does_not_flip_feedback(root):
    """F3 顺序保护 (codex diff review): R1 accept → R2 skip → R1 accept retry
    不能把 R2 skip 翻转回 R1 accept (meal_log 幂等挡不住 feedback 翻转, 故守护下沉)."""
    agent_choose.record_choice(
        root, sid="s10", card_id="cA", action="accept", round_id="R1",
        meal_type="lunch", restaurant_id="rA", restaurant_name="A店",
        dishes=[{"main_ingredient_type": "牛肉"}], accepted_rank=1, zone="z",
        combo_index=0,
    )
    # R2 skip: 用户改主意说这餐不吃了
    agent_choose.record_choice(
        root, sid="s10", card_id="cB", action="skip", round_id="R2",
        meal_type="lunch", skip_reason="不吃了",
    )
    store = feedback_store.load_store(root)
    assert store["accepted"]["s10"]["skipped"] is True
    # R1 accept retry (旧轮延迟到达) → 拒绝, 不翻转 skip
    out = agent_choose.record_choice(
        root, sid="s10", card_id="cA", action="accept", round_id="R1",
        meal_type="lunch", restaurant_id="rA", restaurant_name="A店",
        dishes=[{"main_ingredient_type": "牛肉"}], accepted_rank=1, zone="z",
        combo_index=0,
    )
    assert out["superseded"] is True
    assert out["accept_written"] is False
    store = feedback_store.load_store(root)
    assert store["accepted"]["s10"]["skipped"] is True            # R2 skip 保留
    assert store["accepted"]["s10"]["choice_key"] == "s10::R2::cB::skip"


def test_meal_log_seq_blocks_stale_skip_after_partial_write(root):
    """F3 (codex diff review): accept 两步写间崩溃 — meal_log 写了 R2, feedback 还停
    在 R1. 随后旧轮 R1 skip 到达, stale 守护锚定 meal_log 最高轮 (非只看 feedback),
    拒绝翻转."""
    from chisha.recall import upsert_meal_log_accept
    _accept(root, sid="s11", card_id="cA", rank=1)   # R1 accept (meal_log + feedback)
    # 模拟 R2 accept 部分写: 只落 meal_log (feedback 写前崩溃)
    upsert_meal_log_accept(
        root, "s11", round_id="R2", meal_type="lunch", restaurant_id="rB",
        restaurant_name="B店", dishes=[], accepted_rank=1, zone="z",
        combo_index=0, choice_key="s11::R2::cB::accept",
    )
    # 旧轮 R1 skip 到达 → meal_log 最高 R2 > R1 → stale, 不翻转 feedback
    out = agent_choose.record_choice(
        root, sid="s11", card_id="cA", action="skip", round_id="R1",
        meal_type="lunch", skip_reason="x",
    )
    assert out["superseded"] is True
    assert out["skip_written"] is False
    store = feedback_store.load_store(root)
    assert store["accepted"]["s11"]["choice_key"] == "s11::R1::cA::accept"
    assert store["accepted"]["s11"].get("skipped") in (False, None)


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

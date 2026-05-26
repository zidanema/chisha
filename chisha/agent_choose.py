"""D-074 T6: choose 幂等写协议 (accept / skip).

设计 §6: choose accept 幂等键 = choice_key=(sid, card_id, accept). feedback_store
与 meal_log 两写**都带这个键且各自幂等** (已有该键则跳过); choose 整体可重跑 ——
部分失败 (一写成一写败) 后重跑只补缺的那写, 不靠回滚. skip 同理 (仅 feedback_store).

codex #4: 两次查重 + 两次落盘由**同一跨进程锁**包住, 否则并发 retry 仍可能重复
append meal_log. 单用户低频几乎撞不上, 但锁成本极低值得做.
"""
from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any, Iterator, Literal

from chisha import feedback_store
from chisha.recall import (
    _round_seq_from_choice_key,
    meal_log_max_accept_round_seq,
    upsert_meal_log_accept,
)

logger = logging.getLogger(__name__)

ChooseAction = Literal["accept", "skip"]


def make_choice_key(sid: str, round_id: str, card_id: str, action: str) -> str:
    """codex #c: 加 round_id — card_id (c_{idx}_{rid}) 无 round 成分, 跨 refine 轮可重名,
    不带 round 会把不同轮的不同卡折叠成同一选择."""
    return f"{sid}::{round_id}::{card_id}::{action}"


def _lock_path(sid: str, root: Path | None) -> Path:
    from chisha import data_root
    return data_root.agent_round_dir(root) / f".choose-lock-{sid}"


@contextlib.contextmanager
def _choose_lock(sid: str, root: Path | None) -> Iterator[None]:
    """跨进程 flock, 包住 feedback + meal_log 两写的查重 + 落盘 (codex #4)."""
    import fcntl
    if "/" in sid or ".." in sid or not sid:
        raise ValueError(f"invalid session_id: {sid!r}")
    lp = _lock_path(sid, root)
    lp.parent.mkdir(parents=True, exist_ok=True)
    with open(lp, "a+") as fp:
        fcntl.flock(fp, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fp, fcntl.LOCK_UN)


def record_choice(
    root: Path,
    *,
    sid: str,
    card_id: str,
    action: ChooseAction,
    meal_type: str,
    round_id: str = "R1",
    restaurant_id: str = "",
    restaurant_name: str = "",
    summary: str = "",
    dishes: list[dict] | None = None,
    accepted_rank: int | None = None,
    zone: str | None = None,
    combo_index: int | None = None,
    skip_reason: str | None = None,
) -> dict[str, Any]:
    """幂等记录用户选择. action ∈ {accept, skip}.

    accept: feedback_store.record_accept + meal_log append (各自按 choice_key 幂等).
    skip:   feedback_store.record_skip (按 choice_key 幂等), 不写 meal_log.

    choice_key=(sid, round_id, card_id, action) — 含 round 防跨 refine 轮串卡 (codex #c).
    返回审计 dict: {choice_key, action, accept_written, skip_written,
                   meal_log_written, already_complete}.
    重跑只补缺 (已写的不重写) — 用户/agent retry 安全.
    """
    if action not in ("accept", "skip"):
        raise ValueError(f"invalid action: {action!r} (需 accept|skip)")
    choice_key = make_choice_key(sid, round_id, card_id, action)
    out: dict[str, Any] = {
        "choice_key": choice_key, "action": action,
        "accept_written": False, "skip_written": False,
        "meal_log_written": False, "superseded": False, "already_complete": False,
    }

    with _choose_lock(sid, root):
        store = feedback_store.load_store(root)
        existing = (store.get("accepted") or {}).get(sid) or {}
        # feedback_store 幂等: 同一 choice_key 已记录 → 跳过该写
        fb_done = existing.get("choice_key") == choice_key

        # 顺序保护 (codex diff review): meal_log 幂等只挡 meal_log 重写, feedback 写路径
        # 须同等守护. 否则 `R1 accept → R2 skip → R1 accept retry` 会因 fb_done=False 把
        # R2 skip 翻转回 R1 accept. 锚定 max(meal_log 最高 accept 轮, feedback 轮) —
        # meal_log 是顺序真源 (D-078), 且 accept 两步写 (meal_log→feedback) 间崩溃后
        # feedback 会落后, 只看 feedback 会漏判. 当前轮 < 已记录最高轮 → 旧轮, 拒绝回写.
        cur_seq = _round_seq_from_choice_key(choice_key)
        existing_fb_key = existing.get("choice_key")
        fb_seq = _round_seq_from_choice_key(existing_fb_key) if existing_fb_key else 0
        prior_seq = max(fb_seq, meal_log_max_accept_round_seq(root, sid))
        stale_round = prior_seq > 0 and not fb_done and cur_seq < prior_seq

        if action == "accept":
            if stale_round:
                # 旧轮 accept 延迟到达, 已有更高轮选择 — meal_log + feedback 都不动.
                out["superseded"] = True
                out["already_complete"] = False
                return out
            # F3: meal_log 是顺序真源 (D-078: diversity cooldown source-of-truth).
            # upsert 做"一 sid 一 accept + 跨轮覆盖 + 旧轮延迟到达拒绝回写"的顺序保护.
            ml_res = upsert_meal_log_accept(
                root, sid, round_id=round_id, meal_type=meal_type,
                restaurant_id=restaurant_id, restaurant_name=restaurant_name,
                dishes=dishes or [], zone=zone, accepted_rank=accepted_rank,
                combo_index=combo_index, candidate_id=card_id, choice_key=choice_key,
            )
            out["meal_log_written"] = ml_res["written"]
            out["superseded"] = ml_res["superseded"]
            if ml_res["superseded"]:
                out["already_complete"] = False
            else:
                if not fb_done:
                    feedback_store.record_accept(
                        root, sid,
                        candidate_rank=accepted_rank if accepted_rank is not None else -1,
                        meal_type=meal_type, restaurant_name=restaurant_name,
                        summary=summary, choice_key=choice_key,
                    )
                    out["accept_written"] = True
                out["already_complete"] = (
                    not out["accept_written"] and not out["meal_log_written"]
                )
        else:  # skip
            if stale_round:
                out["superseded"] = True
                out["already_complete"] = False
            elif not fb_done:
                feedback_store.record_skip(root, sid, reason=skip_reason,
                                           choice_key=choice_key)
                out["skip_written"] = True
                out["already_complete"] = False
            else:
                out["already_complete"] = True

    return out

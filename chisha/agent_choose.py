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
from chisha.recall import append_meal_log_entry, meal_log_choice_keys

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
        "meal_log_written": False, "already_complete": False,
    }

    with _choose_lock(sid, root):
        store = feedback_store.load_store(root)
        existing = (store.get("accepted") or {}).get(sid) or {}
        # feedback_store 幂等: 同一 choice_key 已记录 → 跳过该写
        fb_done = existing.get("choice_key") == choice_key

        if action == "accept":
            if not fb_done:
                feedback_store.record_accept(
                    root, sid,
                    candidate_rank=accepted_rank if accepted_rank is not None else -1,
                    meal_type=meal_type, restaurant_name=restaurant_name,
                    summary=summary, choice_key=choice_key,
                )
                out["accept_written"] = True
            # meal_log 幂等: 扫已写 choice_key (D-078: meal_log 是 diversity cooldown
            # source-of-truth, accept 必写; 与 record_accept 同等级别).
            ml_keys = meal_log_choice_keys(root)
            if choice_key not in ml_keys:
                append_meal_log_entry(
                    root, sid, meal_type=meal_type,
                    restaurant_id=restaurant_id, restaurant_name=restaurant_name,
                    dishes=dishes or [], zone=zone, accepted_rank=accepted_rank,
                    combo_index=combo_index, candidate_id=card_id,
                    choice_key=choice_key,
                )
                out["meal_log_written"] = True
            out["already_complete"] = (
                not out["accept_written"] and not out["meal_log_written"]
            )
        else:  # skip
            if not fb_done:
                feedback_store.record_skip(root, sid, reason=skip_reason,
                                           choice_key=choice_key)
                out["skip_written"] = True
            out["already_complete"] = not out["skip_written"]

    return out

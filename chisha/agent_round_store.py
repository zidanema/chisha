"""D-074 T5: AI-friendly 协议 round 状态机 + 幂等 (in-flight, 与可见 trace 索引隔离).

CLI 三步 (start → resolve-intent → apply-rerank) 是独立进程, 中间协议状态必须落盘
让下一步读取继续. 本 store 保存"进行中的协议 round" (pending / resolved).
(P1 后宿主走单 verb `continue`, 三步 verb 降为 `continue` 内部 delegate 的 legacy 路径.)

**核心隔离 (codex #2)**: pending/resolved 状态**绝不进** trace_store 的
round_ids / latest_round (list_traces_v3 + debug-ui 的可见索引). 只有 apply-rerank
成功后, 调用方才走 trace_store.append_round / write_trace 发布 ready round 进可见索引,
然后 clear() 本 store. 防未完成 round 污染列表 / debug-ui 默认切到半成品.

状态机 (设计 §3):
  - 有 context: start → pending (发 extract spec) → resolve-intent → resolved (发 rerank spec)
  - 无 context: start → resolved (内部一步: prepare + 发 rerank spec, intent 空)
  - apply-rerank: resolved → (发布 trace + clear). ready 不落本 store.

幂等 (设计 §3): 每 sid 至多一个 in-flight round (Phase 0 单用户串行). 每步幂等键 =
correlation_id=(rid, round, operation). 重试同 correlation_id 的 operation → 返回已存
结果, 不重算/不重复推进状态.

Phase 0 简化: 每 sid 单 JSON 文件 + flock 串行化. 多 round (refine) 用 round_id 区分,
但同一时刻每 sid 只 1 个 in-flight (上一个 apply-rerank 发布并 clear 后才起下一个).
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any, Iterator, Literal, Optional

from chisha import data_root

logger = logging.getLogger(__name__)

ROUND_STORE_VERSION = 1
RoundStatus = Literal["pending", "resolved"]

# 合法状态转移 (publish=apply-rerank 成功后 caller clear, 不在本 store 留 ready 态)
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"resolved"},     # resolve-intent
    "resolved": set(),           # apply-rerank → 发布后 clear, 无后继态
}


class RoundStateError(RuntimeError):
    """协议 round 状态非法转移 / 缺失. 调用方决定如何回报 agent."""


def _store_path(sid: str, root: Optional[Path] = None) -> Path:
    if "/" in sid or ".." in sid or not sid:
        raise ValueError(f"invalid session_id: {sid!r}")
    return data_root.agent_round_dir(root) / f"{sid}.json"


def _lock_path(sid: str, root: Optional[Path] = None) -> Path:
    return data_root.agent_round_dir(root) / f".lock-{sid}"


@contextlib.contextmanager
def lock_round(sid: str, root: Optional[Path] = None) -> Iterator[None]:
    """fcntl.flock 跨进程互斥, 包住 read→mutate→write (CLI 三步可能并发重试)."""
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


def read_round(sid: str, root: Optional[Path] = None) -> Optional[dict]:
    """读 in-flight round. 不存在返 None. 损坏 → warn + 返 None (best-effort, 重起一轮)."""
    p = _store_path(sid, root)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception as e:
        logger.warning("agent_round read failed for %s: %s: %s",
                       sid, type(e).__name__, e)
        return None


def _write_round(sid: str, data: dict, root: Optional[Path] = None) -> None:
    """原子写 (tmp + rename). 调用方应在 lock_round 内调用."""
    data["__version"] = ROUND_STORE_VERSION
    p = _store_path(sid, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".json.tmp.{os.getpid()}.{secrets.token_hex(4)}")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def clear_round(sid: str, root: Optional[Path] = None) -> None:
    """apply-rerank 发布 trace 后清除 in-flight 状态 (best-effort)."""
    p = _store_path(sid, root)
    try:
        if p.exists():
            p.unlink()
    except Exception as e:
        logger.warning("agent_round clear failed for %s: %s", sid, e)


def _now_iso() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat()


def create_pending(
    sid: str,
    *,
    round_id: str,
    correlation_id: str,
    extract_spec: dict,
    meta: dict,
    root: Optional[Path] = None,
) -> dict:
    """start (有 context): 建 pending round, 存 extract spec + meta. 等 resolve-intent.

    幂等: 已存在同 sid 的 round → 若 correlation 匹配且仍 pending 返已存 (重试),
    否则 RoundStateError (sid 已有未完成 round, 不覆盖).

    codex #d: read-decide-write 全程持 lock_round (跨进程互斥).
    """
    with lock_round(sid, root):
        existing = read_round(sid, root)
        if existing is not None:
            if (existing.get("status") == "pending"
                    and existing.get("correlation_id") == correlation_id):
                return existing   # 幂等重试
            raise RoundStateError(
                f"sid {sid} 已有未完成 round (status={existing.get('status')}), "
                f"不可重复 start"
            )
        data = {
            "__version": ROUND_STORE_VERSION,
            "recommendation_id": sid,
            "round_id": round_id,
            "status": "pending",
            "operation": "extract",          # 当前等待 agent 执行的 operation
            "correlation_id": correlation_id,
            "extract_spec": extract_spec,
            "rerank_spec": None,
            "intent": None,
            "prepared": None,
            "frozen": meta,                  # meal_type/zone/today/daily_mood/refine_input/...
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        _write_round(sid, data, root)
        return data


def create_resolved(
    sid: str,
    *,
    round_id: str,
    correlation_id: str,
    rerank_spec: dict,
    intent: dict | None,
    frozen: dict,
    prepared: dict | None = None,
    root: Optional[Path] = None,
) -> dict:
    """无 context start: 直接建 resolved round (intent 空, 已 prepare + 发 rerank spec).

    prepared (codex #a): 持久化 top_k + ctx_dict + feedback_avoided_names + latencies,
    apply-rerank 用持久化 top_k 映射 agent 回传 (不重跑 prepare_candidates → 不会因
    meal_log/profile 在 resolve→apply 间变化而 combo_index 映射漂移).

    幂等: 已存在同 correlation 的 resolved → 返已存. 全程持 lock_round.
    """
    with lock_round(sid, root):
        existing = read_round(sid, root)
        if existing is not None:
            if (existing.get("status") == "resolved"
                    and existing.get("correlation_id") == correlation_id):
                return existing
            raise RoundStateError(
                f"sid {sid} 已有未完成 round (status={existing.get('status')})"
            )
        data = {
            "__version": ROUND_STORE_VERSION,
            "recommendation_id": sid,
            "round_id": round_id,
            "status": "resolved",
            "operation": "rerank",
            "correlation_id": correlation_id,
            "extract_spec": None,
            "rerank_spec": rerank_spec,
            "intent": intent,
            "prepared": prepared,
            "frozen": frozen,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        _write_round(sid, data, root)
        return data


def advance_to_resolved(
    sid: str,
    *,
    correlation_id: str,
    rerank_spec: dict,
    intent: dict | None,
    prepared: dict | None = None,
    frozen_update: dict | None = None,
    root: Optional[Path] = None,
) -> dict:
    """resolve-intent: pending → resolved. 存 rerank spec + resolved intent + prepared.

    幂等: 已是 resolved 且 correlation 匹配 → 返已存 (重试不重复推进).
    非 pending 起步 → RoundStateError. 全程持 lock_round (codex #d).
    """
    with lock_round(sid, root):
        cur = read_round(sid, root)
        if cur is None:
            raise RoundStateError(f"sid {sid} 无 in-flight round, 不能 resolve-intent")
        if cur.get("status") == "resolved" and cur.get("correlation_id") == correlation_id:
            return cur   # 幂等重试
        if cur.get("status") != "pending":
            raise RoundStateError(
                f"sid {sid} round 状态 {cur.get('status')!r} 不可 →resolved "
                f"(仅 pending 可推进)"
            )
        cur["status"] = "resolved"
        cur["operation"] = "rerank"
        cur["correlation_id"] = correlation_id
        cur["rerank_spec"] = rerank_spec
        cur["intent"] = intent
        cur["prepared"] = prepared
        if frozen_update:
            cur["frozen"] = {**(cur.get("frozen") or {}), **frozen_update}
        cur["updated_at"] = _now_iso()
        _write_round(sid, cur, root)
        return cur


def require_resolved(sid: str, root: Optional[Path] = None) -> dict:
    """apply-rerank 前置: round 必须存在且 resolved. 否则 RoundStateError."""
    cur = read_round(sid, root)
    if cur is None:
        raise RoundStateError(f"sid {sid} 无 in-flight round, 不能 apply-rerank")
    if cur.get("status") != "resolved":
        raise RoundStateError(
            f"sid {sid} round 状态 {cur.get('status')!r}, 需 resolved 才能 apply-rerank"
        )
    return cur


def can_transition(frm: str, to: str) -> bool:
    return to in _VALID_TRANSITIONS.get(frm, set())

"""V1.1 反馈系统单文件落盘 (D-066/D-067).

存储位置: logs/feedback/store.json
结构:
{
  "accepted": {
    "<session_id>": {
      "session_id": str,
      "accepted_rank": int,
      "accepted_at": iso,                 # accepted 时间
      "meal_type": "lunch" | "dinner",
      "restaurant_name": str,
      "summary": str,
      "snoozed_until": iso | null,        # D-060 软关闭 24h
      "stopped": bool,                    # D-060 硬关闭
      "skipped": bool,                    # D-054 这餐没吃, 不参与 inbox
      "skip_reason": str | null
    }
  },
  "feedbacks": {
    "<session_id>": FeedbackRecord        # payload + submitted_at + comments[]
  },
  "sessions": {
    "<session_id>": RecommendResponse     # 反馈页要回放 5 候选, 这里冷存一份
  }
}

简化策略 (D-066/D-067 + 单用户场景):
- 全量 rewrite, 无 lock (单用户单进程, FastAPI sync 端点 → 无并发)
- 落盘失败不抛, 上游降级 (best-effort, recommend 链路不能被反馈断掉)
- inbox/recent/snooze 等读路径派生自 accepted + feedbacks, 不冗余存
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
import threading
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()
_STORE_REL = "logs/feedback/store.json"


def _store_path(root: Path) -> Path:
    """D-077 PR-1b: 走 data_root.feedback_store_path, sandbox 落 logs/sandbox/feedback/."""
    from chisha import data_root
    return data_root.feedback_store_path(root)


def _empty_store() -> dict:
    return {"accepted": {}, "feedbacks": {}, "sessions": {}}


class StoreCorruptError(RuntimeError):
    """store.json 损坏. 调用方应当 raise 5xx, 不允许静默清空."""


def load_store(root: Path) -> dict:
    """读 store. 不存在 → 空 store; 损坏 → 重命名为 .corrupt.{ts}.bak + 抛错.

    Codex review MED-3: 之前的 except Exception → _empty_store() 会让下次写盘
    把所有历史反馈数据覆盖掉。fail-closed 让上游 5xx, 让用户/运维知道。
    """
    p = _store_path(root)
    if not p.exists():
        return _empty_store()
    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except Exception as e:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = p.with_suffix(f".json.corrupt.{ts}.bak")
        try:
            p.rename(backup)
        except Exception:
            # rename 失败也保留信息, 抛错让上游决定
            backup = p
        raise StoreCorruptError(
            f"feedback store corrupt, moved to {backup.name}: "
            f"{type(e).__name__}: {e}"
        ) from e
    if not isinstance(data, dict):
        raise StoreCorruptError(f"feedback store root must be dict, got {type(data).__name__}")
    # 兜底缺字段 (合法的部分老 store)
    for k in ("accepted", "feedbacks", "sessions"):
        data.setdefault(k, {})
    return data


def save_store(root: Path, data: dict) -> None:
    p = _store_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(p)


def _now_iso() -> str:
    from chisha import clock
    return clock.now_utc().isoformat()


# ---------- 写路径 ----------

def remember_session(root: Path, session_id: str, payload: dict) -> None:
    """Phase B 反馈页要回放 5 候选, 把 recommend 响应整包冷存."""
    with _LOCK:
        data = load_store(root)
        data["sessions"][session_id] = payload
        save_store(root, data)


def record_accept(
    root: Path,
    session_id: str,
    candidate_rank: int,
    meal_type: str,
    restaurant_name: str,
    summary: str,
    choice_key: str | None = None,
) -> None:
    with _LOCK:
        data = load_store(root)
        data["accepted"][session_id] = {
            "session_id": session_id,
            "accepted_rank": candidate_rank,
            "accepted_at": _now_iso(),
            "meal_type": meal_type,
            "restaurant_name": restaurant_name,
            "summary": summary,
            "snoozed_until": None,
            "stopped": False,
            "skipped": False,
            "skip_reason": None,
            # D-074 T6: choose 幂等键 (sid::card_id::accept). agent_choose 据此判重.
            "choice_key": choice_key,
        }
        save_store(root, data)


def record_skip(root: Path, session_id: str, reason: str | None,
                choice_key: str | None = None) -> None:
    """D-054: skip 不入 acceptedQueue (用户压根没吃这餐).

    语义: 如果该 session 已 accept (用户先点了再说没吃) → 标 skipped + reason
          否则建一个 skipped=true 占位, 让前端 inbox 不再展示。
    """
    with _LOCK:
        data = load_store(root)
        item = data["accepted"].get(session_id)
        if item is None:
            data["accepted"][session_id] = {
                "session_id": session_id,
                "accepted_rank": None,
                "accepted_at": _now_iso(),
                "meal_type": None,
                "restaurant_name": "",
                "summary": "",
                "snoozed_until": None,
                "stopped": True,        # 不再弹 banner
                "skipped": True,
                "skip_reason": reason,
                # D-074 T6: choose 幂等键 (sid::card_id::skip).
                "choice_key": choice_key,
            }
        else:
            item["skipped"] = True
            item["skip_reason"] = reason
            item["stopped"] = True
            item["choice_key"] = choice_key
        save_store(root, data)


def set_snooze(root: Path, session_id: str, hours: int = 24) -> None:
    with _LOCK:
        data = load_store(root)
        item = data["accepted"].get(session_id)
        if item:
            from chisha import clock
            until = clock.now_utc() + dt.timedelta(hours=hours)
            item["snoozed_until"] = until.isoformat()
            save_store(root, data)


def set_stop(root: Path, session_id: str) -> None:
    with _LOCK:
        data = load_store(root)
        item = data["accepted"].get(session_id)
        if item:
            item["stopped"] = True
            save_store(root, data)


def record_feedback(root: Path, payload: dict) -> dict:
    """提交 / 覆盖 feedback. comments[] 保留 (D-067)."""
    sid = payload["session_id"]
    with _LOCK:
        data = load_store(root)
        existing = data["feedbacks"].get(sid) or {}
        record = {
            **payload,
            "submitted_at": _now_iso(),
            "comments": existing.get("comments") or [],
        }
        data["feedbacks"][sid] = record
        save_store(root, data)
        return record


def append_comment(root: Path, session_id: str, text: str) -> dict | None:
    """D-067 append-only 备注. 没有 feedback 时返回 None."""
    with _LOCK:
        data = load_store(root)
        fb = data["feedbacks"].get(session_id)
        if not fb:
            return None
        # Codex review LOW: 同毫秒多次 append 会撞 ID, 加 4-hex 随机后缀
        ms = int(dt.datetime.now().timestamp() * 1000)
        comment = {
            "id": f"cmt_{ms}_{secrets.token_hex(2)}",
            "text": text,
            "created_at": _now_iso(),
        }
        fb.setdefault("comments", []).append(comment)
        save_store(root, data)
        return comment


# ---------- 读路径 (派生) ----------

def _is_snoozed_now(snoozed_until: str | None) -> bool:
    """Codex review LOW: fromisoformat 不带 tz → 与 aware utcnow 比较会 TypeError.
    统一 normalize: naive 视为 UTC, aware 转 UTC.
    """
    if not snoozed_until:
        return False
    try:
        until = dt.datetime.fromisoformat(snoozed_until)
    except ValueError:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=dt.timezone.utc)
    else:
        until = until.astimezone(dt.timezone.utc)
    from chisha import clock
    return clock.now_utc() < until


def inbox_items(data: dict, include_snoozed: bool = True) -> list[dict]:
    """派生 inbox: 未反馈 + 未 stopped + 未 skipped, 按 accepted_at 倒序."""
    items: list[dict] = []
    for sid, item in data["accepted"].items():
        if item.get("stopped") or item.get("skipped"):
            continue
        if sid in data["feedbacks"]:
            continue
        snoozed = _is_snoozed_now(item.get("snoozed_until"))
        if snoozed and not include_snoozed:
            continue
        items.append({
            "session_id": sid,
            "meal_type": item.get("meal_type") or "lunch",
            "restaurant_name": item.get("restaurant_name") or "",
            "summary": item.get("summary") or "",
            "accepted_at": item["accepted_at"],
            "snoozed": snoozed,
            "stopped": False,
        })
    items.sort(key=lambda x: x["accepted_at"], reverse=True)
    return items


def recent_feedback_items(data: dict, limit: int = 6) -> list[dict]:
    out: list[dict] = []
    for sid, fb in data["feedbacks"].items():
        accepted = data["accepted"].get(sid) or {}
        out.append({
            "session_id": sid,
            "meal_type": accepted.get("meal_type") or "lunch",
            "restaurant_name": accepted.get("restaurant_name") or "（都没吃）",
            "accepted_at": accepted.get("accepted_at") or fb.get("submitted_at"),
            "submitted_at": fb["submitted_at"],
            "rating": fb.get("rating"),
            "accepted_rank": fb.get("accepted_rank"),
        })
    out.sort(key=lambda x: x["submitted_at"], reverse=True)
    return out[:limit]


def get_session_record(root: Path, session_id: str) -> dict | None:
    """反馈页头部要回放 5 候选 — 从 sessions[] 拉. 没存 → None."""
    data = load_store(root)
    return data["sessions"].get(session_id)


def get_accepted(data: dict, session_id: str) -> dict | None:
    return data["accepted"].get(session_id)


def get_feedback_record(data: dict, session_id: str) -> dict | None:
    return data["feedbacks"].get(session_id)

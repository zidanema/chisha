"""推荐 session 状态管理 (D-033 V2.1).

每次 recommend_meal 创建一个 session, 24h TTL, 落本地 sessions/{session_id}.json.
refine_recommendation 通过 session_id 找回上次的 candidates + context + round 数.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


DEFAULT_TTL_HOURS = 24
SESSIONS_DIRNAME = "sessions"


@dataclass
class SessionState:
    session_id: str
    meal_type: str
    zone: str
    created_at: str                          # iso datetime
    round: int = 1                           # 1=首轮, 2+=refine
    last_candidates: list[dict] = field(default_factory=list)  # 上轮输出
    daily_mood: str | None = None
    refine_history: list[str] = field(default_factory=list)    # 累积 refine_input

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionState":
        return cls(
            session_id=d["session_id"],
            meal_type=d["meal_type"],
            zone=d["zone"],
            created_at=d["created_at"],
            round=d.get("round", 1),
            last_candidates=d.get("last_candidates") or [],
            daily_mood=d.get("daily_mood"),
            refine_history=list(d.get("refine_history") or []),
        )


def _sessions_dir(root: Path) -> Path:
    p = root / SESSIONS_DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _session_path(root: Path, session_id: str) -> Path:
    return _sessions_dir(root) / f"{session_id}.json"


def create_session(
    session_id: str,
    meal_type: str,
    zone: str,
    daily_mood: str | None = None,
    now: dt.datetime | None = None,
) -> SessionState:
    return SessionState(
        session_id=session_id,
        meal_type=meal_type,
        zone=zone,
        created_at=(now or dt.datetime.now()).isoformat(timespec="seconds"),
        round=1,
        last_candidates=[],
        daily_mood=daily_mood,
        refine_history=[],
    )


def save_session(state: SessionState, root: Path) -> Path:
    path = _session_path(root, state.session_id)
    path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_session(
    session_id: str,
    root: Path,
    check_expiry: bool = True,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    now: dt.datetime | None = None,
) -> SessionState | None:
    """读取 session. 默认 check_expiry=True 时, 过期返回 None.

    Args:
        check_expiry: True 时过期 session 视为 None (与 refine 文档语义一致).
                      False 时返回原始 state (debug / cleanup_expired 内部用).
    """
    path = _session_path(root, session_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    state = SessionState.from_dict(data)
    if check_expiry and is_expired(state, ttl_hours=ttl_hours, now=now):
        return None
    return state


def is_expired(state: SessionState, ttl_hours: int = DEFAULT_TTL_HOURS,
               now: dt.datetime | None = None) -> bool:
    try:
        created = dt.datetime.fromisoformat(state.created_at)
    except ValueError:
        return True
    now = now or dt.datetime.now()
    return (now - created).total_seconds() > ttl_hours * 3600


def cleanup_expired(root: Path, ttl_hours: int = DEFAULT_TTL_HOURS,
                    now: dt.datetime | None = None) -> int:
    """清理过期 session 文件, 返回删除数. 走 raw read, 不走 load_session 的 expiry 短路."""
    n = 0
    for p in _sessions_dir(root).glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            state = SessionState.from_dict(data)
        except Exception:
            continue
        if is_expired(state, ttl_hours, now):
            p.unlink()
            n += 1
    return n

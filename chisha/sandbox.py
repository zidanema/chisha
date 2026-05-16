"""D-074: Sandbox time-travel 模式 · state 管理 + 虚拟时钟.

设计 (志丹拍板):
- 真实交互优先: sandbox 是 user web 的 mode, 不是 CLI 替代
- 行为完全一致: 真实端点 / 真实 L3 LLM, 不阉割
- 仅在两处与 prod 隔离: (a) 数据落盘根 (b) 虚拟时钟
- 沉淀可见: inspect 端点暴露 L1 prefs
- 一键回到干净状态: reset 不留痕

State 落盘: logs/sandbox/state.json
{
  "enabled": true,
  "current_date": "2026-05-18",
  "day_index": 1,
  "started_at_real": "2026-05-16T15:00:00",
  "started_at_virtual": "2026-05-18",
  "last_l1_extraction": {                    # PR-1c 由 advance 写入
    "at": "2026-05-18T08:00:00",
    "status": "ok" | "failed" | "pending",
    "based_on_meals": int,
    "error": str | None
  }
}

并发:
- 单用户单进程, FastAPI sync 端点, 不会并发
- 但多 tab 可能并发 advance/reset, 走 threading.Lock 防 race

设计约束:
- sandbox 关闭时 current_date()/current_datetime() 返 None, clock.* 降级到真实时间
- profile.yaml 在 sandbox 内不动 (拷贝到 logs/sandbox/profile.yaml 由 PR-1b 实现)
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any


_STATE_REL = "logs/sandbox/state.json"
_SANDBOX_DIR_REL = "logs/sandbox"

# 线程锁: 单进程内防 advance / reset 并发互写
_STATE_LOCK = threading.Lock()


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _state_path(root: Path | None = None) -> Path:
    return (root or _project_root()) / _STATE_REL


def _sandbox_dir(root: Path | None = None) -> Path:
    return (root or _project_root()) / _SANDBOX_DIR_REL


def state(root: Path | None = None) -> dict:
    """读 state. 未 init / 文件不存在 / 已 reset → {enabled: False}.

    损坏 → 视为 disabled (派生数据 fail-open, 与 l1_prefs 风格一致)
    """
    p = _state_path(root)
    if not p.exists():
        return {"enabled": False}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False}
    if not isinstance(data, dict):
        return {"enabled": False}
    return data


def is_enabled(root: Path | None = None) -> bool:
    return bool(state(root).get("enabled"))


def current_date(root: Path | None = None) -> dt.date | None:
    s = state(root)
    if not s.get("enabled"):
        return None
    raw = s.get("current_date")
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def current_datetime(root: Path | None = None) -> dt.datetime | None:
    """虚拟 datetime: 取 sandbox date + 真实 wall-clock 时分秒.

    设计: 沙盒推进按"日"为粒度, 时分秒沿用真机, 让 snooze (24h)、session
    TTL (24h) 等小时级行为仍可观察 (用户点 advance 后立即推荐, datetime
    的 hour 部分相对真实时间不变, 但 date 部分已跳到虚拟日).

    Returns: aware datetime (local naive 兼容旧 dt.datetime.now() 行为) 或 None.
    """
    d = current_date(root)
    if d is None:
        return None
    now_real = dt.datetime.now()
    return dt.datetime.combine(d, now_real.time())


def current_datetime_utc(root: Path | None = None) -> dt.datetime | None:
    """虚拟 UTC datetime: 沙盒 date + 真实 UTC 时分秒. aware tz=UTC."""
    d = current_date(root)
    if d is None:
        return None
    now_utc = dt.datetime.now(dt.timezone.utc)
    return dt.datetime.combine(d, now_utc.time(), tzinfo=dt.timezone.utc)


def _now_real_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def init(
    start_date: dt.date | str | None = None,
    *,
    root: Path | None = None,
    copy_real_data: bool = False,
) -> dict:
    """开启 sandbox 模式. start_date 默认 = 真实 today.

    copy_real_data=True 时由 PR-1b 的 data_root 帮忙拷贝 prod 数据到
    sandbox root; 本模块只管 state, 不操作业务数据.

    返回新 state.
    """
    if isinstance(start_date, str):
        start_date = dt.date.fromisoformat(start_date)
    start_date = start_date or dt.date.today()

    with _STATE_LOCK:
        sandbox_dir = _sandbox_dir(root)
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        new_state = {
            "enabled": True,
            "current_date": start_date.isoformat(),
            "day_index": 1,
            "started_at_real": _now_real_iso(),
            "started_at_virtual": start_date.isoformat(),
            "copy_real_data": copy_real_data,
            "last_l1_extraction": None,
        }
        _state_path(root).write_text(
            json.dumps(new_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return new_state


def advance(days: int = 1, *, root: Path | None = None) -> dict:
    """虚拟时钟前进 N 天. sandbox 必须已 enabled, 否则抛 RuntimeError.

    不直接触发 L1 抽取 (PR-1c 在 web 端点层做异步 trigger). 本函数纯 state.
    """
    if days < 1:
        raise ValueError(f"days must be >= 1, got {days}")
    with _STATE_LOCK:
        s = state(root)
        if not s.get("enabled"):
            raise RuntimeError("sandbox not enabled; call init() first")
        cur = dt.date.fromisoformat(s["current_date"])
        new_date = cur + dt.timedelta(days=days)
        s["current_date"] = new_date.isoformat()
        s["day_index"] = int(s.get("day_index", 1)) + days
        s["last_advance_at_real"] = _now_real_iso()
        _state_path(root).write_text(
            json.dumps(s, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return s


def reset(*, root: Path | None = None) -> dict:
    """删 sandbox 全部数据 + state. prod 数据零风险.

    清理 logs/sandbox/ 整个目录 (含 state + 所有派生 meal_log / feedback /
    prefs / sessions).
    """
    import shutil
    with _STATE_LOCK:
        d = _sandbox_dir(root)
        if d.exists():
            shutil.rmtree(d)
        return {"ok": True, "reset_at": _now_real_iso()}


def disable(*, root: Path | None = None) -> dict:
    """退出 sandbox 但保留数据 (与 reset 区分). state.enabled=False, 文件保留."""
    with _STATE_LOCK:
        s = state(root)
        if not s.get("enabled"):
            return s
        s["enabled"] = False
        s["disabled_at_real"] = _now_real_iso()
        _state_path(root).write_text(
            json.dumps(s, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return s


def record_l1_extraction(
    status: str,
    *,
    based_on_meals: int | None = None,
    error: str | None = None,
    root: Path | None = None,
) -> None:
    """PR-1c 端点用: advance 后异步抽取完成时落 last_l1_extraction 字段.

    status ∈ {"pending", "ok", "failed", "skipped"}.
    """
    with _STATE_LOCK:
        s = state(root)
        if not s.get("enabled"):
            return  # 已关闭, 不写
        s["last_l1_extraction"] = {
            "at": _now_real_iso(),
            "status": status,
            "based_on_meals": based_on_meals,
            "error": error,
        }
        _state_path(root).write_text(
            json.dumps(s, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

"""D-077: 时间抽象层 · sandbox 启用时走虚拟时钟, 否则真实时间.

替换原则:
- 业务时间 (推荐 today / session ttl / snooze 24h / V1.1 反馈 submitted_at)
  → 走 clock.* (虚拟时钟生效)
- 运行时观测 (LLM latency / CLI tmp 清理 / corrupt backup 时间戳 / comment id 毫秒)
  → 保留 time.time() / dt.datetime.now(), 不注入

调用约定:
- clock.today() — 业务"今天"
- clock.now() — 业务 datetime (naive, 复刻 dt.datetime.now())
- clock.now_utc() — 业务 UTC datetime (aware, tz=UTC)

S-04: 透 ContextVar sandbox sid → sandbox.current_date/datetime/datetime_utc.
S-04 阶段 sandbox.* 仍读单 state.json (忽略 sid), 行为完全等同 D-077.
S-05 拆 sessions/{sid}/state.json 时 clock 调用点零修改.

未来扩展: 沙盒按小时推进时, current_datetime() 实现可换成"date + 沙盒指定时间"
而不是"date + 真机 wall-clock 时间".
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

from chisha import sandbox
from chisha.sandbox_context import current_sandbox_session


def today(root: Optional[Path] = None) -> dt.date:
    """业务"今天". sandbox 启用时返虚拟 date, 否则真实 today."""
    sid = current_sandbox_session()
    virtual = sandbox.current_date(root, session_id=sid)
    return virtual if virtual is not None else dt.date.today()


def now(root: Optional[Path] = None) -> dt.datetime:
    """业务 datetime (naive). 与 dt.datetime.now() 兼容."""
    sid = current_sandbox_session()
    virtual = sandbox.current_datetime(root, session_id=sid)
    return virtual if virtual is not None else dt.datetime.now()


def now_utc(root: Optional[Path] = None) -> dt.datetime:
    """业务 UTC datetime (aware, tz=UTC). 与 dt.datetime.now(tz=UTC) 兼容."""
    sid = current_sandbox_session()
    virtual = sandbox.current_datetime_utc(root, session_id=sid)
    return virtual if virtual is not None else dt.datetime.now(dt.timezone.utc)

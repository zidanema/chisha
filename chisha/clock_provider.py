"""D-104 Step2: ambient clock-provider 单例 (agent-only core 叶子, state_root 层级).

clock.py 经此 provider 取业务时间。默认 RealClockProvider == 真实时间 (复刻旧
clock 的 None-fallback 分支, 行为 0-diff)。sandbox 是 extras: 它一被 import 就把
VirtualClockProvider 注册进来 (见 sandbox.py 尾部)。

核心铁律: 本模块零 chisha 依赖 → core 经 clock 取时间时永不 import sandbox。
override hook (set/reset) 用 token/restore 模式, 供 extras 注册 + 测试显式隔离。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional, Protocol


class ClockProvider(Protocol):
    """业务时钟接口。root 必须保留 (sandbox 虚拟时钟按 root 解析 state.json)。"""

    def today(self, root: Optional[Path]) -> dt.date: ...
    def now(self, root: Optional[Path]) -> dt.datetime: ...
    def now_utc(self, root: Optional[Path]) -> dt.datetime: ...


class RealClockProvider:
    """0-diff 默认: 真实时间 (== 旧 clock sandbox-disabled 分支)。"""

    def today(self, root: Optional[Path] = None) -> dt.date:
        return dt.date.today()

    def now(self, root: Optional[Path] = None) -> dt.datetime:
        return dt.datetime.now()

    def now_utc(self, root: Optional[Path] = None) -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc)


_provider: ClockProvider = RealClockProvider()


def get_clock_provider() -> ClockProvider:
    return _provider


def set_clock_provider(provider: ClockProvider) -> ClockProvider:
    """注册 provider, 返回旧值 (token/restore: extras 注册 / 测试隔离)。"""
    global _provider
    prev = _provider
    _provider = provider
    return prev


def reset_clock_provider() -> None:
    """恢复默认 RealClockProvider (测试隔离用)。"""
    global _provider
    _provider = RealClockProvider()

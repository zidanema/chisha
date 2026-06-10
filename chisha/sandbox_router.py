"""D-104 Step3: ambient sandbox-router 单例 (agent-only core 叶子, state_root 层级).

data_root 经此判断"是否路由到 sandbox 数据区"。默认 _DefaultSandboxRouter 返 False
(== prod / agent: agent_cli 在 sandbox 启用时本就拒绝运行, 见 agent_cli._guard_scope)。
sandbox 是 extras: 一被 import 就注册 RealSandboxRouter (见 sandbox.py 尾部)。

核心铁律: 本模块零 chisha 依赖 → core 经 data_root 解析路径时永不 import sandbox。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol


class SandboxRouter(Protocol):
    def is_enabled(self, root: Optional[Path]) -> bool: ...


class _DefaultSandboxRouter:
    """0-diff 默认: sandbox 不存在 (prod / slim agent core)。"""

    def is_enabled(self, root: Optional[Path] = None) -> bool:
        return False


_router: SandboxRouter = _DefaultSandboxRouter()


def get_sandbox_router() -> SandboxRouter:
    return _router


def set_sandbox_router(router: SandboxRouter) -> SandboxRouter:
    """注册 router, 返回旧值 (token/restore: extras 注册 / 测试隔离)。"""
    global _router
    prev = _router
    _router = router
    return prev


def reset_sandbox_router() -> None:
    """恢复默认 _DefaultSandboxRouter (测试隔离用)。"""
    global _router
    _router = _DefaultSandboxRouter()

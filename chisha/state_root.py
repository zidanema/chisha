"""D-102 Step2: install_root / state_root 二分的 state 侧解析 (单一权威源).

提案 §B: 引擎 + 只读数据 (install_root) 与 用户 state (profile/历史/反馈/logs/sandbox)
二分。state 默认落 `~/.chisha/` (host-agnostic, 活过 plugin update), 不再与代码包同目录。

为什么独立成模块 (无 chisha 依赖): `data_root` 与 `sandbox` 两个收口点都要解析 state
根, 但 data_root 已 import sandbox → 解析逻辑放任一处都会循环 import。本模块零 chisha
依赖, 两者都 import 它。

解析规则 (`resolve`):
1. env `CHISHA_STATE_ROOT` 最高优先 (测试 / 多 worktree 显式隔离, 提案 §B)。
2. 显式非 None 且**非包目录**的 root → 用它 (测试传 tmp_path / worktree 传自身路径)。
3. 否则 (root=None 或 root==包目录, 即生产跑在装好的包上) → `default_state_root()`。

为什么用"root==包目录"判生产: 生产 web_api 把包目录 (Path(__file__).parent.parent)
当 root 一路下传; 这是"跑在已安装引擎上"的可靠信号。测试传 tmp_path (≠包目录) → 命中
规则 2 落 tmp, 36 个测试隔离不变。worktree 隔离走 env (规则 1)。
"""
from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """引擎包目录 (install_root)。chisha/ 下所有模块解析到同一结果。"""
    return Path(__file__).resolve().parent.parent


def default_state_root() -> Path:
    """无显式 root 时 state 的落点。

    D-102 Step2 Commit A (本提交): 仍 = 包目录 → 行为保持 (0-diff plumbing)。
    Commit B 翻成 `~/.chisha/` (host-agnostic) 并配套迁移。env 永远最高优先。
    """
    env = os.environ.get("CHISHA_STATE_ROOT")
    if env:
        return Path(env).expanduser()
    return project_root()


def resolve(root: "Path | str | None") -> Path:
    """解析 state 根 (见模块 docstring 三条规则)。"""
    env = os.environ.get("CHISHA_STATE_ROOT")
    if env:
        return Path(env).expanduser()
    if root is not None:
        rp = Path(root)
        if rp.resolve() != project_root().resolve():
            return rp
        # root == 包目录 → 生产, 落 default
    return default_state_root()

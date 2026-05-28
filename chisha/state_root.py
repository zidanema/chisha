"""D-102 Step2 / T-DIST-01 B.1: state_root = user-owned writable root 单一权威源.

state_root 持用户 state (profile / 历史 / 反馈 / logs / sandbox / methodologies user
overlay), 与 install_root (引擎 + 只读 prompts/profiles/data) 对偶, 默认落 `~/.chisha/`
(host-agnostic, 活过 plugin update)。

子目录 (D-102.2 实施 + T-DIST-01 B.5b 留位):
  - `profile.yaml` — 用户 profile (唯一活源)
  - `logs/` — recommend_log / agent_rounds / sandbox sessions
  - `data/` — 用户覆盖 zone bundle (B.5b user-level loader, 撞名 fail-loud)
  - `methodologies/` — 用户自定 methodology overlay (B.5b 留位)
  - `.state_manifest.json` — 迁移完成 marker

零 chisha 依赖 (与 install_root 同款): `data_root` 与 `sandbox` 两个收口点都要解析
state 根, 但 data_root 已 import sandbox → 解析逻辑放任一处都会循环 import。本模块
+ install_root 都是零 chisha 依赖叶子模块, 其他都 import 它们。

解析规则 (`resolve`):
1. env `CHISHA_STATE_ROOT` 最高优先 (测试 / 多 worktree 显式隔离, 提案 §B)。
2. 显式非 None 且**非包目录** (= `install_root()`) 的 root → 用它 (测试传 tmp_path /
   worktree 传自身路径)。
3. 否则 (root=None 或 root==install_root, 即生产跑在装好的包上) → `default_state_root()`。

为什么用"root==install_root"判生产: 生产 web_api / cli 把 install_root() 当 root 一路
下传; 这是"跑在已安装引擎上"的可靠信号。测试传 tmp_path (≠install_root) → 命中规则
2 落 tmp, 测试隔离不变。worktree 隔离走 env (规则 1)。
"""
from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """T-DIST-01 B.1: alias to `install_root.install_root()` (单一权威源).

    历史名保留向后兼容. 实际语义: install root (引擎 + 只读资源, 见 install_root.py).
    state 解析里只用来比对 "root==包目录?"判生产。
    """
    from chisha.install_root import install_root
    return install_root()


def default_state_root() -> Path:
    """无显式 root 时 state 的落点 = `~/.chisha/` (host-agnostic, 活过 plugin update)。

    D-102 Step2 Commit B: 从包目录翻到 `~/.chisha/`。配套 `state_migrate` 把 repo 内旧
    state 一次性搬过来 (复制保留 repo 作回滚)。env `CHISHA_STATE_ROOT` 永远最高优先
    (测试 / 多 worktree 隔离)。
    """
    env = os.environ.get("CHISHA_STATE_ROOT")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".chisha"


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

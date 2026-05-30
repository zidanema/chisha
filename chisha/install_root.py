"""T-DIST-01 B.1 / D-102.2: install_root 单一权威源.

install_root = 包资源根 (含 prompts/, profiles/, data/), 与 state_root (~/.chisha/,
用户可写) 对偶. 改前读 CONTRACTS「install/state root 二分」段.

布局 (dev / 形态B bundle 统一走 sibling 布局): prompts/ profiles/ data/ 与 chisha/ 同级,
install_root = chisha/ 包目录的父级。
  - dev: repo root (chisha/ 同级) 含 prompts/ profiles/ data/。
  - 形态B bundle: bundle 根 (chisha/ 同级) 含 prompts/ profiles/ data/, build_skill_bundle 复刻 dev 同级布局。
  (D-105.1 退役的 wheel 旧布局曾 force-include 这些目录进 chisha/ 包内, 已不再产出。)

零 chisha 依赖 (与 state_root 同款): 多个模块 import 它, 不能反向. 改前看
[CONTRACTS.md 「install/state root 二分」段].
"""
from __future__ import annotations

from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent  # chisha/

# 测试 / fixture 注入用. 业务代码严禁调 _set_install_root_for_test.
_OVERRIDE: Path | None = None


def install_root() -> Path:
    """Return install root holding prompts/, profiles/, data/."""
    if _OVERRIDE is not None:
        return _OVERRIDE
    # dev / 形态B bundle: prompts/ 等与 chisha/ 同级 → install_root = 包目录父级.
    return _PKG_DIR.parent


def _set_install_root_for_test(root: Path | None) -> None:
    """fixture-only override. 业务代码不许调."""
    global _OVERRIDE
    _OVERRIDE = root

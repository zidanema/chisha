"""T-DIST-01 B.1 / D-102.2: install_root 单一权威源.

install_root = 包资源根 (含 prompts/, profiles/, data/), 与 state_root (~/.chisha/,
用户可写) 对偶. 改前读 CONTRACTS「install/state root 二分」段.

布局兼容 (dev + wheel 双形态):
  - dev: repo root 含 prompts/ profiles/ data/ (chisha/ 同级), install_root = repo root.
  - wheel: hatch force-include 把上述目录复制到 chisha/prompts/ chisha/profiles/
    chisha/data/ (site-packages/chisha/), install_root = chisha/ 包目录.

检测顺序: 优先 chisha/<resource>/ 存在则用包目录 (wheel), 否则 fallback 到包目录
父级 (dev). 改 force-include 源布局必须同步更新这里 (`prompts` 探测目录).

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
    # wheel: chisha/prompts 存在 → 包目录就是 install_root.
    if (_PKG_DIR / "prompts").is_dir():
        return _PKG_DIR
    # dev: chisha/ 同级 (repo root) 才有 prompts/.
    return _PKG_DIR.parent


def _set_install_root_for_test(root: Path | None) -> None:
    """fixture-only override. 业务代码不许调."""
    global _OVERRIDE
    _OVERRIDE = root

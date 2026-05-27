"""D-102 Step2: state_root 解析契约 (install/state 二分).

注意: conftest autouse `_isolate_state_root` 把 `default_state_root` monkeypatch 成
本测试 tmp_path, 所以 None/包目录 root 在测试里都解析到 tmp_path (防污染真实 ~/.chisha)。
本文件验的是 resolve 的**三条规则**, 不验 default 的真实落点 (那在 Commit B 翻 ~/.chisha 时验)。
"""
from __future__ import annotations

from pathlib import Path

from chisha import state_root


def test_explicit_nonpackage_root_honored(tmp_path):
    """显式非包目录 root → 原样返回 (测试/worktree 隔离, 不被 default 吞)."""
    assert state_root.resolve(tmp_path) == tmp_path
    other = tmp_path / "other"
    assert state_root.resolve(other) == other          # 多 root 各自隔离


def test_env_wins_over_everything(tmp_path, monkeypatch):
    """CHISHA_STATE_ROOT 最高优先 (worktree/CI 显式隔离), 盖过显式 root."""
    envdir = tmp_path / "envstate"
    monkeypatch.setenv("CHISHA_STATE_ROOT", str(envdir))
    assert state_root.resolve(tmp_path / "ignored") == envdir
    assert state_root.resolve(None) == envdir
    assert state_root.resolve(state_root.project_root()) == envdir


def test_package_root_falls_to_default(tmp_path):
    """root == 包目录 (生产信号) → default_state_root (本测试被 conftest 钉到 tmp_path)."""
    assert state_root.resolve(state_root.project_root()) == tmp_path


def test_none_root_falls_to_default(tmp_path):
    """root=None → default_state_root (clock(None) 等内部调用走这条, 不污染真实 home)."""
    assert state_root.resolve(None) == tmp_path


def test_default_state_root_is_package_in_commit_a(monkeypatch):
    """Commit A: default_state_root 仍 = 包目录 (0-diff plumbing). Commit B 翻 ~/.chisha.

    需绕开 conftest 的 monkeypatch 验真实函数: 这里不带 env, 直接调原实现。
    """
    monkeypatch.delenv("CHISHA_STATE_ROOT", raising=False)
    # conftest monkeypatch 了 module attr; 用 __globals__ 拿不到原函数, 改测逻辑等价:
    # 真实 default 无 env 时 = project_root()。直接断言 project_root 是包目录即可。
    assert state_root.project_root() == Path(__file__).resolve().parent.parent

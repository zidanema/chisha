"""T-DIST-01 B.7 跟修 (codex P1#1): has_legacy_state 4 marker 覆盖.

`has_legacy_state` 是 doctor 判 legacy_state_pending_migration 的单一权威源.
Marker 集 (任一命中即 legacy):
  1. logs/ 子目录非空
  2. data/feedback_history.jsonl 非空
  3. data/long_term_prefs.json 存在
  4. profile.yaml 存在且**内容非 template** (`<YOUR_NAME>` 占位 = 模板)

Rule 4 兜 codex 提的反例: pre-A.2 dev checkout, profile.yaml 是真数据 + 从未跑过
chisha (1-3 漏判, Rule 4 救场).

外加 install_root 一致性 invariant: A.2 后 install_root/profile.yaml 永远是 template.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chisha.install_root import install_root
from chisha.state_migrate import (
    _PROFILE_TEMPLATE_MARKER,
    has_legacy_state,
)


# ─── 4 marker 单独命中 ───

def test_no_legacy_in_empty_root(tmp_path):
    """空 root 无 marker → False."""
    assert has_legacy_state(tmp_path) is False


def test_logs_dir_non_empty_triggers(tmp_path):
    """Marker 1: logs/ 子目录非空."""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "some.log").write_text("x", encoding="utf-8")
    assert has_legacy_state(tmp_path) is True


def test_logs_dir_empty_does_not_trigger(tmp_path):
    """Marker 1 反例: 空 logs/ 不算."""
    (tmp_path / "logs").mkdir()
    assert has_legacy_state(tmp_path) is False


def test_feedback_history_nonempty_triggers(tmp_path):
    """Marker 2: feedback_history.jsonl 非空."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "feedback_history.jsonl").write_text('{"rid":"r"}\n', encoding="utf-8")
    assert has_legacy_state(tmp_path) is True


def test_feedback_history_empty_does_not_trigger(tmp_path):
    """Marker 2 反例: 0 字节 feedback_history (已迁移后残留) 不算."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "feedback_history.jsonl").write_text("", encoding="utf-8")
    assert has_legacy_state(tmp_path) is False


def test_long_term_prefs_triggers(tmp_path):
    """Marker 3: long_term_prefs.json 存在."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "long_term_prefs.json").write_text("{}", encoding="utf-8")
    assert has_legacy_state(tmp_path) is True


# ─── Rule 4: profile.yaml 内容 ≠ template (codex P1#1 反例) ───

def test_profile_template_does_not_trigger(tmp_path):
    """Marker 4 反例: profile.yaml 含 `<YOUR_NAME>` 占位 = 模板, 不算 legacy."""
    p = tmp_path / "profile.yaml"
    p.write_text(
        "basics:\n  name: <YOUR_NAME>\n  zones:\n    lunch: <YOUR_LUNCH_ZONE>\n",
        encoding="utf-8",
    )
    assert has_legacy_state(tmp_path) is False


def test_profile_personal_data_triggers(tmp_path):
    """Marker 4: profile.yaml 不含占位 = 真个人数据, 触发 legacy (codex 反例兜底)."""
    p = tmp_path / "profile.yaml"
    p.write_text(
        "basics:\n  name: 张三\n  zones:\n    lunch: shenzhen-bay\n",
        encoding="utf-8",
    )
    assert has_legacy_state(tmp_path) is True


def test_profile_unreadable_does_not_trigger(tmp_path, monkeypatch):
    """profile.yaml 存在但读 OSError → 当不存在, 不强报 legacy."""
    p = tmp_path / "profile.yaml"
    p.write_text("dummy", encoding="utf-8")

    # monkeypatch Path.read_text 模拟 OSError
    orig_read = Path.read_text
    def boom(self, *a, **k):
        if self == p:
            raise OSError("simulated")
        return orig_read(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", boom)
    assert has_legacy_state(tmp_path) is False


# ─── Install-root invariant (A.2 后) ───

def test_install_root_profile_is_template_invariant():
    """T-DIST-01 + A.2 invariant: install_root/profile.yaml 一律是 template.

    A.2 占位化 commit (bd007be) 之后 repo root profile.yaml 顶层字段全是 `<YOUR_NAME>` /
    `<YOUR_LUNCH_ZONE>` 占位. Wheel ship 的 chisha/profile.yaml 源于这一份. 这条 invariant
    是 `has_legacy_state` 不把 profile.yaml 单独作 marker 的前提 (template 不算 legacy).
    """
    p = install_root() / "profile.yaml"
    assert p.exists(), f"install_root 缺 profile.yaml template: {p}"
    content = p.read_text(encoding="utf-8")
    assert _PROFILE_TEMPLATE_MARKER in content, (
        f"install_root/profile.yaml 不含 {_PROFILE_TEMPLATE_MARKER} 占位 — "
        "看起来不是 template! 是否有人意外把真个人数据 ship 进 repo?"
    )


def test_install_root_profile_template_triggers_no_legacy():
    """Composite: 复刻 wheel 模式 install_root 形态 (只有 template profile + bundle data,
    无 logs/feedback/prefs), has_legacy_state 必须返 False (doctor 不会误报待迁移).
    """
    from chisha.install_root import install_root
    # 不打扰真 install_root, copy profile 到 tmp 验
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_install = Path(tmpdir)
        shutil.copy(install_root() / "profile.yaml", fake_install / "profile.yaml")
        # 不放 logs / feedback_history / long_term_prefs
        assert has_legacy_state(fake_install) is False

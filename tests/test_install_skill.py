"""T-DIST-01 B.3+B.4: SKILL.md 内容同步 + `chisha install-skill` 落盘.

测试覆盖:
- SKILL.md 模板内含新 `chisha agent <verb>` (不再有 legacy `uv run python -m chisha.agent_cli`)
- SKILL.md 含 `chisha doctor` (不是旧 `uv run python ... doctor`)
- SKILL.md 含 'How to install' 段 + transport URL
- init_skill 写 user-level ~/.claude (临时 HOME 注入), --force 才覆盖
- `chisha install-skill` 整链路跑通 (subprocess + 临时 HOME)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chisha import agent_skill_init


def test_skill_md_uses_new_chisha_agent_verbs():
    """plan B.3 step 1: 所有 `uv run python -m chisha.agent_cli <verb>` 必须改 `chisha agent <verb>`."""
    md = agent_skill_init._claude_code_skill_md()
    # legacy 字符串完全消失
    assert "uv run python -m chisha.agent_cli" not in md, (
        "SKILL.md 还含 legacy uv run python -m chisha.agent_cli 路径"
    )
    # 新路径出现 (start / resolve-intent / apply-rerank / choose 都改了)
    assert "chisha agent start" in md
    assert "chisha agent resolve-intent" in md
    assert "chisha agent apply-rerank" in md
    assert "chisha agent choose" in md
    # doctor 不带 'agent' 子命令 (顶层 `chisha doctor`)
    assert "chisha doctor" in md


def test_skill_md_has_install_section():
    """plan B.3 step 1: 加 'How to install' 段 + transport URL."""
    md = agent_skill_init._claude_code_skill_md()
    assert "uv tool install git+https://github.com/zidanema/chisha.git" in md
    assert "chisha onboard" in md


def test_init_skill_writes_user_level_by_default(tmp_path, monkeypatch):
    """B.4: 默认 dest = ~/.claude/skills/chisha-meal/ (Path.home() 注入)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    rc = agent_skill_init.init_skill("claude-code", root=tmp_path)
    assert rc == 0
    target = tmp_path / ".claude" / "skills" / "chisha-meal" / "SKILL.md"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "chisha agent start" in content
    assert "uv tool install git+" in content


def test_init_skill_exists_without_force(tmp_path, monkeypatch):
    """B.4: 已存在 SKILL.md 时返 EXISTS 错, 非 0 退出."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # first run OK
    rc1 = agent_skill_init.init_skill("claude-code", root=tmp_path)
    assert rc1 == 0
    # second run (no force) — EXISTS
    rc2 = agent_skill_init.init_skill("claude-code", root=tmp_path)
    assert rc2 != 0


def test_init_skill_force_overwrites(tmp_path, monkeypatch):
    """B.4: --force 覆盖."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    rc1 = agent_skill_init.init_skill("claude-code", root=tmp_path)
    assert rc1 == 0
    rc2 = agent_skill_init.init_skill("claude-code", root=tmp_path, force=True)
    assert rc2 == 0


def test_chisha_install_skill_via_subprocess(tmp_path, monkeypatch):
    """B.4 e2e: `chisha install-skill` subprocess + 临时 HOME 写出 SKILL.md."""
    env = dict(os.environ, HOME=str(tmp_path), CHISHA_SUPPRESS_LEGACY_TIP="1")
    r = subprocess.run(
        [sys.executable, "-m", "chisha.cli", "install-skill"],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, f"stderr={r.stderr}\nstdout={r.stdout}"
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    skill_path = Path(payload["path"])
    assert skill_path.is_relative_to(tmp_path), (
        f"skill 落在临时 HOME 外: {skill_path}"
    )
    assert skill_path.read_text(encoding="utf-8").startswith("---")

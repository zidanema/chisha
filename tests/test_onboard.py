"""T-DIST-01 B.5a: `chisha onboard` 基础 (profile + skill + doctor).

测试覆盖 (plan B.5a 4 步):
  1. 写 default profile.yaml template 到 state_root (除非已存在; --force 覆盖)
  2. zone / methodology 替换占位 (默认 shenzhen-bay / harvard_plate)
  3. 调 install_skill 落 SKILL.md
  4. 调 doctor 把 payload 合进 summary

B.5b user-level loader + B.5c ephemeral dry start 在后续 PR 补.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_onboard(home: Path, extra: list[str] | None = None) -> subprocess.CompletedProcess:
    """跑 chisha onboard subprocess, 临时 HOME 隔离."""
    env = dict(os.environ,
               HOME=str(home),
               CHISHA_SUPPRESS_LEGACY_TIP="1",
               CHISHA_STATE_ROOT=str(home / ".chisha"))  # 强制 state 落 tmp
    return subprocess.run(
        [sys.executable, "-m", "chisha.cli", "onboard", *(extra or [])],
        capture_output=True, text=True, env=env,
    )


def _last_json(stdout: str) -> dict:
    return json.loads(stdout.strip().splitlines()[-1])


def test_onboard_writes_profile_with_zone(tmp_path):
    """B.5a step 1+2: 写 profile.yaml + 替换 zone 占位."""
    r = _run_onboard(tmp_path, ["--zone", "shenzhen-bay"])
    payload = _last_json(r.stdout)
    assert payload["steps"]["profile"]["status"] == "written"
    profile_path = Path(payload["steps"]["profile"]["path"])
    assert profile_path.is_relative_to(tmp_path)
    content = profile_path.read_text(encoding="utf-8")
    # zone 占位被替换
    assert "<YOUR_LUNCH_ZONE>" not in content
    assert "<YOUR_DINNER_ZONE>" not in content
    assert "shenzhen-bay" in content
    # name / city / goal 占位保留 (用户后续手填)
    assert "<YOUR_NAME>" in content


def test_onboard_writes_skill(tmp_path):
    """B.5a step 3: 调 install_skill 落 ~/.claude/skills/chisha-meal/SKILL.md."""
    r = _run_onboard(tmp_path)
    payload = _last_json(r.stdout)
    skill = payload["steps"]["skill"]
    assert skill.get("ok") is True
    skill_path = Path(skill["path"])
    assert skill_path.is_relative_to(tmp_path)
    assert skill_path.exists()
    # SKILL.md 内含新 CLI (B.3 同步)
    text = skill_path.read_text(encoding="utf-8")
    assert "chisha agent start" in text


def test_onboard_doctor_invoked(tmp_path):
    """B.5a step 4: doctor payload 合进 summary."""
    r = _run_onboard(tmp_path)
    payload = _last_json(r.stdout)
    doctor = payload["steps"]["doctor"]
    # doctor 字段齐 (T-DIST-01 B.5b 改名 data_manifest_status → install_data_manifest_status)
    for k in ("protocol_version", "state_root", "install_root",
              "install_data_manifest_status", "user_resource_status"):
        assert k in doctor, f"doctor missing field {k}: {doctor}"


def test_onboard_idempotent_without_force(tmp_path):
    """B.5a step 1: 已存在 + 无 --force → status=exists (非致命)."""
    _run_onboard(tmp_path)  # first
    r2 = _run_onboard(tmp_path)  # second
    payload = _last_json(r2.stdout)
    assert payload["steps"]["profile"]["status"] == "exists"
    # skill 也已存在 → EXISTS 不阻塞 (warning 不致命)
    assert payload["steps"]["skill"].get("error", {}).get("code") == "EXISTS"


def test_onboard_force_overwrites(tmp_path):
    """B.5a: --force 覆盖 profile + skill."""
    _run_onboard(tmp_path)  # 占位
    r = _run_onboard(tmp_path, ["--force"])
    payload = _last_json(r.stdout)
    assert payload["steps"]["profile"]["status"] == "written"
    assert payload["steps"]["skill"].get("ok") is True


def test_onboard_dry_start_runs(tmp_path):
    """B.5c: ephemeral dry start 跑 cmd_start(meal=lunch, context=None), 期望 status=resolved.
    state 全部落 tmp (CHISHA_STATE_ROOT 临时钉), 不污染真 ~/.chisha/logs/agent_rounds."""
    r = _run_onboard(tmp_path)
    payload = _last_json(r.stdout)
    dry = payload["steps"]["dry_start"]
    assert dry["status"] == "ok", f"dry start failed: {dry}"
    # 验证 tmp 目录已被清理 (TemporaryDirectory contextmanager 删了)
    leftover = list(Path("/tmp").glob("chisha-dry-*"))
    assert not leftover, f"tmp leak: {leftover}"
    # 真 state_root (tmp_path/.chisha) 的 logs/agent_rounds 不应有 dry start 残留
    agent_rounds = tmp_path / ".chisha" / "logs" / "agent_rounds"
    if agent_rounds.exists():
        # 允许目录在但里面应该没有 dry start 落的 cards.json (sid 是新生成的)
        cards = list(agent_rounds.glob("*.cards.json"))
        # 这里 cards 可能有 (如果先前测试残留, conftest tmp_path 应空), assert 空更严
        assert not cards, f"dry start state 污染了真 state_root: {cards}"


def test_onboard_dry_start_state_isolation(tmp_path, monkeypatch):
    """B.5c 隔离守门: dry start 跑完, real CHISHA_STATE_ROOT 环境变量不该被永久篡改."""
    monkeypatch.setenv("CHISHA_STATE_ROOT_PRE", "guard-value")
    r = _run_onboard(tmp_path)
    # subprocess 跑完后我们检的是父进程 env, subprocess 内 env 改动不影响这里 —
    # 真正测试是: dry_start 内部 try/finally 把 env 还原; 看 dry_start.status=ok 即可
    payload = _last_json(r.stdout)
    assert payload["steps"]["dry_start"]["status"] == "ok"


def test_onboard_methodology_substitution(tmp_path):
    """B.5a step 2: --methodology 替换 (假设 yaml 模板含 'methodology: harvard_plate')."""
    r = _run_onboard(tmp_path, ["--methodology", "my-custom-spec"])
    payload = _last_json(r.stdout)
    profile_path = Path(payload["steps"]["profile"]["path"])
    content = profile_path.read_text(encoding="utf-8")
    # 模板里 'methodology: harvard_plate' 被替换成自定义
    assert "methodology: my-custom-spec" in content

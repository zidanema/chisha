"""T-DIST-01 B.2: chisha 顶层 CLI subprocess 测试.

测试覆盖 (plan B.2 step 4):
- (a) `chisha agent doctor` stdout 等价于 legacy `python -m chisha.agent_cli doctor`
- (b) legacy stderr 含 tip, stdout 不含
- (c) `chisha methodology schema` 报 NOT_IMPLEMENTED 非零退出
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


def _run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    """跑 python -m argv, 收 stdout/stderr/exit."""
    env = dict(os.environ)
    return subprocess.run(
        [sys.executable, "-m", *argv],
        capture_output=True, text=True, env=env, **kwargs,
    )


def _strip_doctor_volatile(payload: dict) -> dict:
    """去掉非确定字段, 让两条路径等价对比."""
    drop = {"state_root", "install_root", "root", "engine_version",
            "manifest_path"}
    return {k: v for k, v in payload.items() if k not in drop}


def test_cli_agent_doctor_equivalent_to_legacy():
    """(a) `chisha agent doctor` stdout 等价于 legacy `python -m chisha.agent_cli doctor`."""
    # 抑制 legacy tip (走 env), 让 stdout JSON 干净;
    # 两条路径都设 CHISHA_SUPPRESS_LEGACY_TIP, 防 cli.agent 内部也走 agent_cli __main__ 路径
    env = dict(os.environ, CHISHA_SUPPRESS_LEGACY_TIP="1")
    legacy = subprocess.run(
        [sys.executable, "-m", "chisha.agent_cli", "doctor"],
        capture_output=True, text=True, env=env,
    )
    new = subprocess.run(
        [sys.executable, "-m", "chisha.cli", "agent", "doctor"],
        capture_output=True, text=True, env=env,
    )
    # 两路退出码相同 (都是 doctor 自身判定)
    assert legacy.returncode == new.returncode, (
        f"exit mismatch legacy={legacy.returncode} new={new.returncode}\n"
        f"legacy.stderr={legacy.stderr}\nnew.stderr={new.stderr}"
    )
    # stdout 是 JSON, 比关键字段
    legacy_obj = json.loads(legacy.stdout.strip().splitlines()[-1])
    new_obj = json.loads(new.stdout.strip().splitlines()[-1])
    assert _strip_doctor_volatile(legacy_obj) == _strip_doctor_volatile(new_obj), (
        f"doctor payload mismatch\nlegacy={legacy_obj}\nnew={new_obj}"
    )


def test_legacy_stderr_has_tip_stdout_does_not():
    """(b) legacy `python -m chisha.agent_cli` stderr 含 tip 字符串, stdout 不含."""
    env = dict(os.environ)
    env.pop("CHISHA_SUPPRESS_LEGACY_TIP", None)  # 显式不抑制
    r = subprocess.run(
        [sys.executable, "-m", "chisha.agent_cli", "doctor"],
        capture_output=True, text=True, env=env,
    )
    # tip 整句标识 (避免误命中 doctor JSON 的 `legacy_state_pending_migration` 字段名)
    assert "[chisha] tip:" in r.stderr, f"expected legacy tip in stderr, got: {r.stderr!r}"
    assert "chisha eat" in r.stderr
    # stdout 必须是干净 JSON, 不含 tip 整句
    assert "[chisha] tip:" not in r.stdout
    # stdout 应是有效 JSON
    last = r.stdout.strip().splitlines()[-1]
    json.loads(last)  # 不抛即 OK


def test_cli_agent_path_emits_deprecation_tip():
    """P1: `chisha agent` 现为 deprecated → stderr 出 deprecation tip (推扁平 verb), stdout 干净."""
    env = dict(os.environ)
    env.pop("CHISHA_SUPPRESS_LEGACY_TIP", None)
    r = subprocess.run(
        [sys.executable, "-m", "chisha.cli", "agent", "doctor"],
        capture_output=True, text=True, env=env,
    )
    assert "[chisha] tip:" in r.stderr, f"expected deprecation tip in stderr, got: {r.stderr!r}"
    assert "deprecated" in r.stderr
    # stdout 必须干净 JSON, 不含 tip
    assert "[chisha] tip:" not in r.stdout
    json.loads(r.stdout.strip().splitlines()[-1])


def test_flat_verbs_dispatch(monkeypatch):
    """P1: 扁平 chisha eat/continue/choose 正确翻译到 agent_cli handler (in-process, 不碰真实 state)."""
    from chisha import agent_cli, cli
    captured: dict = {}
    monkeypatch.setattr(agent_cli, "cmd_start", lambda ns: captured.update(start=ns) or 0)
    monkeypatch.setattr(agent_cli, "cmd_continue", lambda ns: captured.update(cont=ns) or 0)
    monkeypatch.setattr(agent_cli, "cmd_choose", lambda ns: captured.update(choose=ns) or 0)

    assert cli.main(["eat", "lunch", "--context", "辣", "--from", "rid1"]) == 0
    assert captured["start"].meal == "lunch"
    assert captured["start"].context == "辣"
    assert captured["start"].from_id == "rid1"
    assert captured["start"].scope == "production"

    assert cli.main(["continue", "--id", "rid1", "--result", "{}",
                     "--step", "rid1::R1::rerank"]) == 0
    assert captured["cont"].id == "rid1"
    assert captured["cont"].result == "{}"
    assert captured["cont"].step == "rid1::R1::rerank"

    assert cli.main(["choose", "--id", "rid1", "--card", "c1", "--action", "accept"]) == 0
    assert captured["choose"].card == "c1" and captured["choose"].action == "accept"


def test_skills_add_dispatches_to_install(monkeypatch):
    """P1: `chisha skills add --force` = install-skill rename."""
    from chisha import cli
    captured: dict = {}
    monkeypatch.setattr(cli, "cmd_install_skill",
                        lambda args: captured.update(force=args.force) or 0)
    assert cli.main(["skills", "add", "--force"]) == 0
    assert captured["force"] is True


def test_methodology_schema_not_implemented():
    """(c) `chisha methodology schema` 报 NOT_IMPLEMENTED 非零退出."""
    r = _run(["chisha.cli", "methodology", "schema"])
    assert r.returncode != 0, f"expected non-zero exit, got {r.returncode}"
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["error"] == "NOT_IMPLEMENTED"


def test_methodology_template_not_implemented():
    r = _run(["chisha.cli", "methodology", "template"])
    assert r.returncode != 0
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert payload["error"] == "NOT_IMPLEMENTED"


def test_methodology_validate_not_implemented():
    r = _run(["chisha.cli", "methodology", "validate"])
    assert r.returncode != 0
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert payload["error"] == "NOT_IMPLEMENTED"

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
    assert "chisha agent" in r.stderr
    # stdout 必须是干净 JSON, 不含 tip 整句
    assert "[chisha] tip:" not in r.stdout
    # stdout 应是有效 JSON
    last = r.stdout.strip().splitlines()[-1]
    json.loads(last)  # 不抛即 OK


def test_cli_path_no_legacy_tip():
    """补 (b): 新路径 `chisha agent doctor` 不应触发 legacy tip."""
    env = dict(os.environ)
    env.pop("CHISHA_SUPPRESS_LEGACY_TIP", None)
    r = subprocess.run(
        [sys.executable, "-m", "chisha.cli", "agent", "doctor"],
        capture_output=True, text=True, env=env,
    )
    assert "[chisha] tip:" not in r.stderr, f"unexpected legacy tip in new-path stderr: {r.stderr!r}"


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

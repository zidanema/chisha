"""tests/test_claude_code_cli.py — claude_code_cli provider 单测 (D-047).

不调真 subprocess; 用 mock 覆盖关键路径.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_cli_cache():
    """每个测试独立 cache, 防互染."""
    from chisha.llm_providers import claude_code_cli as cc
    cc.reset_cli_check_cache()
    yield
    cc.reset_cli_check_cache()


def _make_proc(returncode=0, stdout="", stderr=""):
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def _make_popen(returncode=0, stdout="", stderr=""):
    """构造 mock Popen 实例, communicate() 返回 (stdout, stderr)."""
    p = MagicMock()
    p.returncode = returncode
    p.communicate.return_value = (stdout, stderr)
    return p


_GOOD_OUT = json.dumps({
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": '{"candidates":[{"rank":1}]}',
    "duration_api_ms": 12345,
    "total_cost_usd": 0.05,
    "usage": {"output_tokens": 250},
})


def _patch_cli_available():
    return patch(
        "chisha.llm_providers.claude_code_cli._check_cli",
        return_value=True,
    )


# ====================== _check_cli ======================

def test_check_cli_no_claude_binary():
    from chisha.llm_providers import claude_code_cli as cc
    with patch("chisha.llm_providers.claude_code_cli.shutil.which",
                return_value=None):
        assert cc.is_available() is False


def test_check_cli_logged_in():
    from chisha.llm_providers import claude_code_cli as cc
    with patch("chisha.llm_providers.claude_code_cli.shutil.which",
                return_value="/bin/claude"), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(
            returncode=0,
            stdout=json.dumps({
                "loggedIn": True,
                "apiProvider": "firstParty",
                "subscriptionType": "max",
            }),
        )
        assert cc.is_available() is True


def test_check_cli_not_logged_in():
    from chisha.llm_providers import claude_code_cli as cc
    with patch("chisha.llm_providers.claude_code_cli.shutil.which",
                return_value="/bin/claude"), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(
            returncode=0,
            stdout=json.dumps({"loggedIn": False, "apiProvider": "firstParty"}),
        )
        assert cc.is_available() is False


def test_check_cli_not_first_party():
    """API key 模式登录 → 不算订阅"""
    from chisha.llm_providers import claude_code_cli as cc
    with patch("chisha.llm_providers.claude_code_cli.shutil.which",
                return_value="/bin/claude"), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(
            returncode=0,
            stdout=json.dumps({
                "loggedIn": True, "apiProvider": "anthropic_api",
            }),
        )
        assert cc.is_available() is False


def test_check_cli_caches_result():
    """两次调用只跑一次 subprocess"""
    from chisha.llm_providers import claude_code_cli as cc
    with patch("chisha.llm_providers.claude_code_cli.shutil.which",
                return_value="/bin/claude"), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(
            returncode=0,
            stdout=json.dumps({
                "loggedIn": True, "apiProvider": "firstParty",
            }),
        )
        cc.is_available()
        cc.is_available()
        cc.is_available()
        assert mr.call_count == 1


def test_check_cli_auth_status_timeout_returns_false():
    from chisha.llm_providers import claude_code_cli as cc
    with patch("chisha.llm_providers.claude_code_cli.shutil.which",
                return_value="/bin/claude"), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.side_effect = subprocess.TimeoutExpired("claude auth status", 5)
        assert cc.is_available() is False


def test_check_cli_invalid_json_returns_false():
    from chisha.llm_providers import claude_code_cli as cc
    with patch("chisha.llm_providers.claude_code_cli.shutil.which",
                return_value="/bin/claude"), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(returncode=0, stdout="not json")
        assert cc.is_available() is False


# ====================== call() — 成功路径 ======================


def test_call_success_returns_result_string():
    """D-047: call() 现在返回 dict (统一 LLM 接口), content 字段是原 result 文本."""
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=_GOOD_OUT)
        out = cc.call("ping", system="you are echo", model="sonnet")
        assert isinstance(out, dict)
        assert out["type"] == "text"
        assert out["content"] == '{"candidates":[{"rank":1}]}'
        assert out["raw_text"] == '{"candidates":[{"rank":1}]}'
        assert out["model"] == "sonnet"


def test_call_includes_all_required_flags():
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=_GOOD_OUT)
        cc.call("ping", system="sys body", model="sonnet", effort="low")
        cmd = mp.call_args.args[0]
        # 10 个隔离 flag (来自 Codex review)
        assert "-p" in cmd
        assert "--model" in cmd and "sonnet" in cmd
        assert "--effort" in cmd and "low" in cmd
        assert "--output-format" in cmd and "json" in cmd
        assert "--disable-slash-commands" in cmd
        assert "--setting-sources" in cmd
        assert "--strict-mcp-config" in cmd
        assert "--no-session-persistence" in cmd
        assert "--tools" in cmd
        assert "--input-format" in cmd and "text" in cmd
        assert "--system-prompt-file" in cmd
        # system 内容不进 argv (确认走文件)
        # system body 短 + 仅出现一次, 而 argv 里只该有"sys body"作为字符串的话会出现 0 次
        assert all("sys body" not in a for a in cmd)


def test_call_passes_user_via_stdin():
    """user prompt 走 stdin 不进 argv"""
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp_inst = _make_popen(returncode=0, stdout=_GOOD_OUT)
        mp.return_value = mp_inst
        cc.call("USER_PROMPT_CONTENT", system="sys", model="sonnet")
        # communicate(input=...) 接收 user
        assert mp_inst.communicate.call_args.kwargs["input"] == "USER_PROMPT_CONTENT"
        cmd = mp.call_args.args[0]
        assert "USER_PROMPT_CONTENT" not in cmd


def test_call_cwd_is_private_tmp_dir(tmp_path, monkeypatch):
    """cwd 在私有 tmp 目录, 不在项目根"""
    from chisha.llm_providers import claude_code_cli as cc
    monkeypatch.setattr(cc, "_TMP_DIR", tmp_path)
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=_GOOD_OUT)
        cc.call("p", system="s")
        cwd = mp.call_args.kwargs["cwd"]
        assert cwd == str(tmp_path)


def test_call_filters_claude_prefix_env(monkeypatch):
    """传给 subprocess 的 env 不含 CLAUDE_* 全部变量"""
    from chisha.llm_providers import claude_code_cli as cc
    monkeypatch.setenv("CLAUDE_CODE_SIMPLE", "1")
    monkeypatch.setenv("CLAUDE_FOO", "bar")
    monkeypatch.setenv("PATH", "/usr/bin")
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=_GOOD_OUT)
        cc.call("p")
        env = mp.call_args.kwargs["env"]
        assert "CLAUDE_CODE_SIMPLE" not in env
        assert "CLAUDE_FOO" not in env
        assert "PATH" in env


def test_call_filters_llm_credential_env(monkeypatch):
    """ANTHROPIC_API_KEY / OPENROUTER_API_KEY 不能传给 claude 子进程,
    否则订阅路径会被劫持到付费 API (Codex review P1#1)."""
    from chisha.llm_providers import claude_code_cli as cc
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-leak-anth")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-leak-or")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "should-also-strip")
    monkeypatch.setenv("PATH", "/usr/bin")
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=_GOOD_OUT)
        cc.call("p")
        env = mp.call_args.kwargs["env"]
        assert "ANTHROPIC_API_KEY" not in env
        assert "OPENROUTER_API_KEY" not in env
        assert "ANTHROPIC_AUTH_TOKEN" not in env
        assert "PATH" in env


def test_call_sets_pdeathsig_preexec(monkeypatch):
    """preexec_fn 应设置 PR_SET_PDEATHSIG, 让 Linux 在父被 SIGKILL 时
    自动杀子进程 (Codex review P1#2). 仅 Linux 生效, 其他平台不强求."""
    import sys
    if sys.platform != "linux":
        pytest.skip("PR_SET_PDEATHSIG 仅 Linux")
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=_GOOD_OUT)
        cc.call("p", system="s")
        preexec = mp.call_args.kwargs.get("preexec_fn")
        assert preexec is not None, "应设 preexec_fn 用 prctl"


# ====================== _check_cli TTL ======================


def test_check_cli_does_not_cache_negative_result(monkeypatch):
    """negative result 不缓存, 下次重试 (Codex review P2#3).

    transient timeout 不应永久标记不可用.
    """
    from chisha.llm_providers import claude_code_cli as cc
    monkeypatch.setattr("chisha.llm_providers.claude_code_cli.shutil.which",
                         lambda _: "/bin/claude")
    call_count = {"n": 0}

    def _fake_run(*a, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise subprocess.TimeoutExpired("claude", 5)
        return _make_proc(
            returncode=0,
            stdout=json.dumps({"loggedIn": True, "apiProvider": "firstParty"}),
        )

    monkeypatch.setattr(
        "chisha.llm_providers.claude_code_cli.subprocess.run", _fake_run
    )
    assert cc.is_available() is False  # 第一次 timeout
    assert cc.is_available() is True   # 第二次成功
    assert call_count["n"] == 2, "negative result 不应缓存"


def test_check_cli_positive_result_has_ttl(monkeypatch):
    """positive 缓存有 TTL, 过期后重新查 (防 revoked token)."""
    from chisha.llm_providers import claude_code_cli as cc
    import time as _t
    monkeypatch.setattr("chisha.llm_providers.claude_code_cli.shutil.which",
                         lambda _: "/bin/claude")
    monkeypatch.setattr(
        "chisha.llm_providers.claude_code_cli._POSITIVE_TTL_SEC", 0.1
    )
    call_count = {"n": 0}

    def _fake_run(*a, **kw):
        call_count["n"] += 1
        return _make_proc(
            returncode=0,
            stdout=json.dumps({"loggedIn": True, "apiProvider": "firstParty"}),
        )

    monkeypatch.setattr(
        "chisha.llm_providers.claude_code_cli.subprocess.run", _fake_run
    )
    cc.is_available()
    cc.is_available()
    assert call_count["n"] == 1, "TTL 内复用 cache"
    _t.sleep(0.15)
    cc.is_available()
    assert call_count["n"] == 2, "TTL 后重查"


def test_call_uses_new_session_for_orphan_safety():
    """Popen start_new_session=True 防 orphan"""
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=_GOOD_OUT)
        cc.call("p", system="s")
        assert mp.call_args.kwargs.get("start_new_session") is True


def test_call_passes_effort_low_default():
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=_GOOD_OUT)
        cc.call("p", system="s")
        cmd = mp.call_args.args[0]
        i = cmd.index("--effort")
        assert cmd[i + 1] == "low"


# ====================== call() — 失败路径 ======================


def test_call_non_zero_exit_raises():
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=2, stdout="", stderr="boom!")
        with pytest.raises(cc.CCCLIError, match="boom"):
            cc.call("p", system="s")


def test_call_no_json_in_stdout_raises():
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout="plain text no json")
        with pytest.raises(cc.CCCLIError, match="无 JSON"):
            cc.call("p")


def test_call_is_error_true_raises():
    from chisha.llm_providers import claude_code_cli as cc
    bad = json.dumps({
        "type": "result", "is_error": True, "result": "API overloaded",
    })
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=bad)
        with pytest.raises(cc.CCCLIError, match="is_error"):
            cc.call("p")


def test_call_timeout_raises():
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp_inst = MagicMock()
        mp_inst.pid = 99999
        mp_inst.communicate.side_effect = [
            subprocess.TimeoutExpired("claude", 180),
            ("", ""),  # cleanup communicate
        ]
        mp.return_value = mp_inst
        with pytest.raises(cc.CCCLIError, match="超时"):
            cc.call("p", timeout_sec=180)


def test_call_unavailable_raises():
    from chisha.llm_providers import claude_code_cli as cc
    with patch("chisha.llm_providers.claude_code_cli._check_cli",
                return_value=False):
        with pytest.raises(cc.CCCLIError, match="不可用"):
            cc.call("p")


def test_call_malformed_json_raises():
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout="{not valid json")
        with pytest.raises(cc.CCCLIError):
            cc.call("p")


# ====================== call() — 临时文件 ======================


def test_call_cleans_up_temp_file(tmp_path, monkeypatch):
    """成功路径后 system tmp file 被删"""
    from chisha.llm_providers import claude_code_cli as cc
    monkeypatch.setattr(cc, "_TMP_DIR", tmp_path)
    captured = []
    real_named = tempfile.NamedTemporaryFile

    def _capture(*a, **kw):
        f = real_named(*a, **kw)
        captured.append(f.name)
        return f

    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.tempfile.NamedTemporaryFile",
                side_effect=_capture), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=_GOOD_OUT)
        cc.call("p", system="sys body")
    assert len(captured) == 1
    assert not os.path.exists(captured[0])


def test_call_cleans_up_temp_file_on_error(tmp_path, monkeypatch):
    """失败路径仍清理 tmp"""
    from chisha.llm_providers import claude_code_cli as cc
    monkeypatch.setattr(cc, "_TMP_DIR", tmp_path)
    captured = []
    real_named = tempfile.NamedTemporaryFile

    def _capture(*a, **kw):
        f = real_named(*a, **kw)
        captured.append(f.name)
        return f

    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.tempfile.NamedTemporaryFile",
                side_effect=_capture), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=1, stdout="", stderr="boom")
        with pytest.raises(cc.CCCLIError):
            cc.call("p", system="sys")
    assert captured and not os.path.exists(captured[0])


def test_concurrent_calls_have_unique_tmp_files(tmp_path, monkeypatch):
    """并发调用时, 每次拿到唯一的 tmp 文件路径 (顺序模拟)"""
    from chisha.llm_providers import claude_code_cli as cc
    monkeypatch.setattr(cc, "_TMP_DIR", tmp_path)
    captured = []
    real_named = tempfile.NamedTemporaryFile

    def _capture(*a, **kw):
        f = real_named(*a, **kw)
        captured.append(f.name)
        return f

    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.tempfile.NamedTemporaryFile",
                side_effect=_capture), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=_GOOD_OUT)
        for i in range(3):
            cc.call(f"p{i}", system=f"sys body {i}")
    assert len(captured) == 3
    assert len(set(captured)) == 3, "tmp 文件名应全部唯一"


def test_sweep_stale_tmp_files(tmp_path, monkeypatch):
    """启动 sweep 清掉 >1h 残留, 不删 fresh 的"""
    import time as _t
    from chisha.llm_providers import claude_code_cli as cc
    monkeypatch.setattr(cc, "_TMP_DIR", tmp_path)
    old = tmp_path / "chisha_sys_old.md"
    new = tmp_path / "chisha_sys_new.md"
    other = tmp_path / "other.md"
    old.write_text("old")
    new.write_text("new")
    other.write_text("o")
    long_ago = _t.time() - 7200
    os.utime(old, (long_ago, long_ago))
    cc._sweep_stale_tmp_files()
    assert not old.exists()
    assert new.exists()
    assert other.exists(), "只清 chisha_sys_ 前缀, 不动别人"


def test_tmp_file_has_restrictive_permissions(tmp_path, monkeypatch):
    """tmp 文件 0600 + 目录 0700"""
    from chisha.llm_providers import claude_code_cli as cc
    monkeypatch.setattr(cc, "_TMP_DIR", tmp_path)
    seen_paths = []

    def _capture_chmod(path, mode, **_kwargs):
        seen_paths.append((path, mode))

    real_named = tempfile.NamedTemporaryFile

    def _capture(*a, **kw):
        f = real_named(*a, **kw)
        return f

    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.tempfile.NamedTemporaryFile",
                side_effect=_capture), \
         patch("chisha.llm_providers.claude_code_cli.os.chmod",
                side_effect=_capture_chmod), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp.return_value = _make_popen(returncode=0, stdout=_GOOD_OUT)
        cc.call("p", system="sys")
    # 至少有一次 chmod 0o600 在临时文件上
    assert any(mode == 0o600 for _, mode in seen_paths)

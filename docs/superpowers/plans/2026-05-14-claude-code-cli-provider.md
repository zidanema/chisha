# Claude Code CLI Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 chisha 推荐链路的 LLM 调用支持本机 Claude Code 订阅额度，三 provider 通过 profile.yaml + 环境变量切换。

**Architecture:** 把 `llm_client.py` 拆成路由层 + `chisha/llm_providers/` 子包（anthropic_api / openrouter / claude_code_cli 三个文件）。新 provider 用 subprocess 调 `claude -p` 并加 7 个 flag 隔离 Claude Code 默认行为。

**Tech Stack:** Python 3.11 + subprocess + tempfile + pytest + claude CLI 2.1.141

**Spec:** `docs/superpowers/specs/2026-05-14-claude-code-cli-provider-design.md`

---

## File Structure

**New:**
- `chisha/llm_providers/__init__.py`
- `chisha/llm_providers/anthropic_api.py` — 抽自现 `llm_client._call_anthropic`
- `chisha/llm_providers/openrouter.py` — 抽自现 `llm_client._call_openrouter`
- `chisha/llm_providers/claude_code_cli.py` — 新 provider，全部新代码
- `tests/test_llm_provider_selection.py` — provider 路由单测
- `tests/test_claude_code_cli.py` — CLI provider 单测（mock subprocess）
- `tests/integration/test_claude_code_cli_e2e.py` — e2e（opt-in，需 CLI + 订阅）
- `tests/integration/__init__.py` — 空文件，让 pytest 识别

**Modified:**
- `chisha/llm_client.py` — 重构为薄路由层
- `chisha/rerank.py` — `_llm_rerank` 传 `profile_llm` 给 `call_text`
- `chisha/reason.py` — 同上（如有调用）
- `chisha/api.py` 或 `chisha/recommend.py` — 在调用 rerank/reason 时把 profile.llm 透传
- `profile.yaml` — 新增 `llm` 段（默认 `provider: auto`）
- `pyproject.toml` — pytest marker 注册（如尚无）

**Self-Review note:** 本次工作量约 ~400 行新代码 + ~50 行 diff。先单测后实现，每个 commit 跑全测。

---

## Task 1: 设 pytest marker + integration 目录

**Files:**
- Create: `tests/integration/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: 看现有 pyproject.toml**

Run: `cat pyproject.toml | head -50`

- [ ] **Step 2: 新增 pytest marker**

在 `pyproject.toml` 找到（或新增） `[tool.pytest.ini_options]` 段，加：

```toml
[tool.pytest.ini_options]
markers = [
    "requires_claude_cli: tests that need claude CLI + Max subscription (opt-in, skipped in CI)",
]
```

- [ ] **Step 3: 建 integration 目录**

```bash
mkdir -p tests/integration
touch tests/integration/__init__.py
```

- [ ] **Step 4: 验证 marker 注册**

Run: `uv run pytest --markers | grep requires_claude_cli`
Expected: 打印 `@pytest.mark.requires_claude_cli: ...`

- [ ] **Step 5: Commit**

```bash
git add tests/integration/__init__.py pyproject.toml
git commit -m "chore: add pytest marker requires_claude_cli + integration dir"
```

---

## Task 2: 抽 anthropic_api provider（先把现有代码搬一份）

**Files:**
- Create: `chisha/llm_providers/__init__.py`
- Create: `chisha/llm_providers/anthropic_api.py`

- [ ] **Step 1: 看现有 llm_client._call_anthropic**

Run: `sed -n '70,92p' chisha/llm_client.py`
确认 `_call_anthropic` 的实现细节（cache_system 处理 ephemeral cache_control）。

- [ ] **Step 2: 写 anthropic_api provider**

`chisha/llm_providers/__init__.py`:
```python
"""LLM provider implementations: anthropic_api / openrouter / claude_code_cli."""
```

`chisha/llm_providers/anthropic_api.py`:
```python
"""Anthropic 直连 (ANTHROPIC_API_KEY) provider."""
from __future__ import annotations

_DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicProviderError(Exception):
    """Anthropic provider 调用失败"""


def call(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    cache_system: bool = False,
) -> str:
    import anthropic
    client = anthropic.Anthropic()
    kwargs: dict = dict(
        model=model or _DEFAULT_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        if cache_system:
            kwargs["system"] = [{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }]
        else:
            kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return resp.content[0].text


def is_available() -> bool:
    import os
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
```

- [ ] **Step 3: 跑全测确认未破坏现状**

Run: `uv run pytest tests/ -x -q`
Expected: 全过（此时还没有人调 anthropic_api.call，只是文件存在）

- [ ] **Step 4: Commit**

```bash
git add chisha/llm_providers/__init__.py chisha/llm_providers/anthropic_api.py
git commit -m "refactor(llm): split anthropic_api provider to subpackage (D-047 prep)"
```

---

## Task 3: 抽 openrouter provider

**Files:**
- Create: `chisha/llm_providers/openrouter.py`

- [ ] **Step 1: 看现有 _call_openrouter**

Run: `sed -n '94,117p' chisha/llm_client.py`

- [ ] **Step 2: 写 openrouter provider**

`chisha/llm_providers/openrouter.py`:
```python
"""OpenRouter (OPENROUTER_API_KEY) provider."""
from __future__ import annotations

_DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"


class OpenRouterProviderError(Exception):
    pass


def call(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    cache_system: bool = False,    # 忽略, OR 自管 cache
) -> str:
    import os
    from openai import OpenAI
    base_url = os.environ.get(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"], base_url=base_url
    )
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(
        model=model or _DEFAULT_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        extra_headers={
            "HTTP-Referer": "https://github.com/chisha-private",
            "X-Title": "chisha recommend",
        },
    )
    return resp.choices[0].message.content or ""


def is_available() -> bool:
    import os
    return bool(os.environ.get("OPENROUTER_API_KEY"))
```

- [ ] **Step 3: 跑全测**

Run: `uv run pytest tests/ -x -q`
Expected: 全过

- [ ] **Step 4: Commit**

```bash
git add chisha/llm_providers/openrouter.py
git commit -m "refactor(llm): split openrouter provider to subpackage (D-047 prep)"
```

---

## Task 4: 写 claude_code_cli provider 单测（红）

**Files:**
- Create: `tests/test_claude_code_cli.py`

- [ ] **Step 1: 写单测文件**

```python
"""tests/test_claude_code_cli.py — claude_code_cli provider 单测.

不调真 subprocess; 用 mock 覆盖关键路径.
"""
from __future__ import annotations

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest


# === 用 fixture autouse 清掉模块级 cache, 防测试间互染 ===

@pytest.fixture(autouse=True)
def _reset_cli_cache():
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


# === _check_cli ===

def test_check_cli_no_claude_binary():
    """which 找不到 claude → 不可用"""
    from chisha.llm_providers import claude_code_cli as cc
    with patch("chisha.llm_providers.claude_code_cli.shutil.which", return_value=None):
        assert cc.is_available() is False


def test_check_cli_logged_in():
    """auth status 显示 loggedIn + firstParty → 可用"""
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
            stdout=json.dumps({"loggedIn": True, "apiProvider": "anthropic_api"}),
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
            stdout=json.dumps({"loggedIn": True, "apiProvider": "firstParty"}),
        )
        cc.is_available()
        cc.is_available()
        cc.is_available()
        assert mr.call_count == 1   # auth status 只跑一次


# === call() 路径 ===

_GOOD_OUT = json.dumps({
    "type": "result", "subtype": "success", "is_error": False,
    "result": '{"candidates":[{"rank":1}]}',
    "duration_api_ms": 12345,
    "total_cost_usd": 0.05,
    "usage": {"output_tokens": 250},
})


def _patch_cli_available():
    """返回一个 context manager 让 is_available=True"""
    from unittest.mock import patch
    return patch(
        "chisha.llm_providers.claude_code_cli._check_cli",
        return_value=True,
    )


def test_call_success_returns_result_string():
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(returncode=0, stdout=_GOOD_OUT + "\n")
        out = cc.call("ping", system="you are echo", model="sonnet")
        assert out == '{"candidates":[{"rank":1}]}'


def test_call_includes_all_required_flags():
    """命令拼接含 7 个必加 flag"""
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(returncode=0, stdout=_GOOD_OUT)
        cc.call("ping", system="sys", model="sonnet", effort="low")
        cmd = mr.call_args.args[0]
        assert "-p" in cmd
        assert "--effort" in cmd and "low" in cmd
        assert "--output-format" in cmd and "json" in cmd
        assert "--disable-slash-commands" in cmd
        assert "--setting-sources" in cmd and "" in cmd
        assert "--no-session-persistence" in cmd
        assert "--tools" in cmd
        assert "--input-format" in cmd and "text" in cmd
        assert "--system-prompt-file" in cmd
        # system 内容不进 argv
        assert "sys" not in [c for c in cmd if len(c) < 50]


def test_call_passes_user_via_stdin():
    """user prompt 走 stdin 不进 argv"""
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(returncode=0, stdout=_GOOD_OUT)
        cc.call("USER_PROMPT_CONTENT", system="sys", model="sonnet")
        # subprocess.run input= kwarg
        assert mr.call_args.kwargs["input"] == "USER_PROMPT_CONTENT"
        # user 内容不进 argv
        cmd = mr.call_args.args[0]
        assert "USER_PROMPT_CONTENT" not in cmd


def test_call_cwd_is_tmp():
    """cwd=/tmp 防读项目 CLAUDE.md"""
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(returncode=0, stdout=_GOOD_OUT)
        cc.call("p", system="s")
        assert mr.call_args.kwargs["cwd"] == "/tmp"


def test_call_filters_claude_code_env():
    """传给 subprocess 的 env 不含 CLAUDE_CODE_* 变量"""
    from chisha.llm_providers import claude_code_cli as cc
    import os
    with _patch_cli_available(), \
         patch.dict(os.environ, {"CLAUDE_CODE_SIMPLE": "1", "PATH": "/usr/bin"},
                     clear=False), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(returncode=0, stdout=_GOOD_OUT)
        cc.call("p")
        env = mr.call_args.kwargs["env"]
        assert "CLAUDE_CODE_SIMPLE" not in env
        assert "PATH" in env


def test_call_non_zero_exit_raises():
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(returncode=2, stdout="", stderr="boom!")
        with pytest.raises(cc.CCCLIError, match="boom"):
            cc.call("p", system="s")


def test_call_no_json_in_stdout_raises():
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(returncode=0, stdout="plain text no json")
        with pytest.raises(cc.CCCLIError, match="无 JSON"):
            cc.call("p")


def test_call_is_error_true_raises():
    from chisha.llm_providers import claude_code_cli as cc
    bad = json.dumps({
        "type": "result", "is_error": True, "result": "API overloaded",
    })
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(returncode=0, stdout=bad)
        with pytest.raises(cc.CCCLIError, match="is_error"):
            cc.call("p")


def test_call_timeout_raises():
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.side_effect = subprocess.TimeoutExpired("claude", 180)
        with pytest.raises(cc.CCCLIError, match="超时"):
            cc.call("p", timeout_sec=180)


def test_call_cleans_up_temp_file():
    """成功路径后 system tmp file 被删"""
    import os
    from chisha.llm_providers import claude_code_cli as cc
    captured_tmp = []

    real_named = __import__("tempfile").NamedTemporaryFile
    def _capture_named(*a, **kw):
        f = real_named(*a, **kw)
        captured_tmp.append(f.name)
        return f

    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.tempfile.NamedTemporaryFile",
                side_effect=_capture_named), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(returncode=0, stdout=_GOOD_OUT)
        cc.call("p", system="sys body")
        assert len(captured_tmp) == 1
        assert not os.path.exists(captured_tmp[0])


def test_call_cleans_up_temp_file_on_error():
    """失败路径仍清理 tmp"""
    import os
    from chisha.llm_providers import claude_code_cli as cc
    captured = []
    real_named = __import__("tempfile").NamedTemporaryFile
    def _capture(*a, **kw):
        f = real_named(*a, **kw); captured.append(f.name); return f
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.tempfile.NamedTemporaryFile",
                side_effect=_capture), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.run") as mr:
        mr.return_value = _make_proc(returncode=1, stderr="boom")
        with pytest.raises(cc.CCCLIError):
            cc.call("p", system="sys")
        assert captured and not os.path.exists(captured[0])


def test_call_unavailable_raises():
    """is_available=False 时直接 raise"""
    from chisha.llm_providers import claude_code_cli as cc
    with patch("chisha.llm_providers.claude_code_cli._check_cli",
                return_value=False):
        with pytest.raises(cc.CCCLIError, match="不可用"):
            cc.call("p")


def test_call_strict_mcp_flag_present():
    """命令含 --strict-mcp-config 防 MCP server 配置泄漏"""
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp_inst = MagicMock()
        mp_inst.returncode = 0
        mp_inst.communicate.return_value = (_GOOD_OUT, "")
        mp.return_value = mp_inst
        cc.call("p", system="s")
        cmd = mp.call_args.args[0]
        assert "--strict-mcp-config" in cmd


def test_call_uses_new_session_for_orphan_safety():
    """Popen start_new_session=True 防 orphan"""
    from chisha.llm_providers import claude_code_cli as cc
    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp_inst = MagicMock()
        mp_inst.returncode = 0
        mp_inst.communicate.return_value = (_GOOD_OUT, "")
        mp.return_value = mp_inst
        cc.call("p", system="s")
        assert mp.call_args.kwargs.get("start_new_session") is True


def test_concurrent_calls_have_unique_tmp_files(tmp_path, monkeypatch):
    """并发调用时, 每次拿到唯一的 tmp 文件路径"""
    from chisha.llm_providers import claude_code_cli as cc
    monkeypatch.setattr(cc, "_TMP_DIR", tmp_path)
    captured = []
    real_named = __import__("tempfile").NamedTemporaryFile

    def _capture(*a, **kw):
        f = real_named(*a, **kw)
        captured.append(f.name)
        return f

    with _patch_cli_available(), \
         patch("chisha.llm_providers.claude_code_cli.tempfile.NamedTemporaryFile",
                side_effect=_capture), \
         patch("chisha.llm_providers.claude_code_cli.subprocess.Popen") as mp:
        mp_inst = MagicMock()
        mp_inst.returncode = 0
        mp_inst.communicate.return_value = (_GOOD_OUT, "")
        mp.return_value = mp_inst
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
    old.write_text("old"); new.write_text("new"); other.write_text("o")
    # 把 old 设成 2h 前
    long_ago = _t.time() - 7200
    os.utime(old, (long_ago, long_ago))
    cc._sweep_stale_tmp_files()
    assert not old.exists()
    assert new.exists()
    assert other.exists(), "只清 chisha_sys_ 前缀, 不动别人"
```

- [ ] **Step 2: 跑测确认红**

Run: `uv run pytest tests/test_claude_code_cli.py -x -q 2>&1 | tail -20`
Expected: ImportError 或 module not found `chisha.llm_providers.claude_code_cli`

---

## Task 5: 实现 claude_code_cli provider（让 Task 4 单测绿）

**Files:**
- Create: `chisha/llm_providers/claude_code_cli.py`

⚠️ **Codex review 修正后版本**：用 Popen + start_new_session 防 orphan、私有 tmp 目录、启动 sweep 老文件、`--strict-mcp-config` 加固隔离。

- [ ] **Step 1: 实现 provider**

```python
"""Claude Code CLI subprocess provider (D-047).

复用本机 Claude Code 订阅额度调 LLM. 通过 `claude -p` 子进程实现.
关键设计 (见 docs/superpowers/specs/2026-05-14-claude-code-cli-provider-design.md §3):
- 10 个 flag 隔离 Claude Code 默认行为 (含 --strict-mcp-config)
- system 通过 --system-prompt-file 私有临时文件传, user 通过 stdin
- effort=low 防 extended thinking 拖长延迟
- cwd 用本地私有目录 + 过滤 CLAUDE_CODE_* env 防污染
- Popen(start_new_session=True) 防父进程被杀时子进程 orphan
- 启动 sweep ~/.cache/chisha/llm_tmp/ 里 >1h 的残留文件
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional


_DEFAULT_MODEL = "sonnet"
_DEFAULT_TIMEOUT = 180      # N=60 实测 60s, 留 3x buffer
_DEFAULT_EFFORT = "low"

# 私有临时目录: 0700, 用户级, 防止 /tmp 全局可见
_TMP_DIR = Path(os.environ.get("XDG_CACHE_HOME") or
                Path.home() / ".cache") / "chisha" / "llm_tmp"
_TMP_PREFIX = "chisha_sys_"
_TMP_STALE_SEC = 3600       # >1h 的残留文件清掉


class CCCLIError(Exception):
    """Claude Code CLI 调用失败"""


# 进程级 cache: claude auth status 调用一次 ~500ms, 不重复
_cli_check_cache: Optional[bool] = None


def _ensure_tmp_dir() -> Path:
    """确保私有 tmp 目录存在 + 0700 权限."""
    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _TMP_DIR.chmod(0o700)
    except OSError:
        pass
    return _TMP_DIR


def _sweep_stale_tmp_files() -> None:
    """清掉 >1h 的残留 chisha_sys_*.md (上次 SIGKILL 留下的)."""
    try:
        if not _TMP_DIR.exists():
            return
        cutoff = time.time() - _TMP_STALE_SEC
        for p in _TMP_DIR.glob(f"{_TMP_PREFIX}*.md"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except OSError:
                pass
    except OSError:
        pass


def _check_cli() -> bool:
    """检查 claude CLI 是否可用 + 订阅登录态."""
    global _cli_check_cache
    if _cli_check_cache is not None:
        return _cli_check_cache
    bin_path = shutil.which("claude")
    if not bin_path:
        _cli_check_cache = False
        return False
    try:
        r = subprocess.run(
            [bin_path, "auth", "status"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            _cli_check_cache = False
            return False
        info = json.loads(r.stdout)
        ok = (
            bool(info.get("loggedIn"))
            and info.get("apiProvider") == "firstParty"
        )
        _cli_check_cache = ok
        return ok
    except (subprocess.TimeoutExpired, subprocess.SubprocessError,
            json.JSONDecodeError, OSError):
        _cli_check_cache = False
        return False


def reset_cli_check_cache() -> None:
    """测试用, 清掉模块级 cache."""
    global _cli_check_cache
    _cli_check_cache = None


def is_available() -> bool:
    return _check_cli()


def _run_with_session_isolation(
    cmd: list[str], *, input_text: str, env: dict, cwd: str, timeout: int,
) -> subprocess.CompletedProcess:
    """Popen + start_new_session 等价于 subprocess.run, 但子进程在独立 session.

    父进程被信号杀时, 子进程不会成 orphan 继续吃 CPU. 超时主动 terminate ->
    kill 整个进程组.
    """
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        start_new_session=True,    # 关键: 子进程在新 session, 收不到父的 SIGINT
    )
    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        # 终止整个 session (含可能 spawn 的孙进程)
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            stdout, stderr = proc.communicate()
        raise
    return subprocess.CompletedProcess(
        cmd, proc.returncode, stdout, stderr,
    )


def call(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 4096,     # 兼容签名, CLI 不支持
    temperature: float = 0.0,   # 同上
    cache_system: bool = False, # 同上, CLI 自管 prompt cache
    timeout_sec: int = _DEFAULT_TIMEOUT,
    effort: str = _DEFAULT_EFFORT,
) -> str:
    """通过 claude -p 子进程调 LLM, 返回纯文本输出."""
    if not _check_cli():
        raise CCCLIError(
            "claude CLI 不可用或未登录订阅. "
            "运行 `claude auth login` 后重试."
        )

    bin_path = shutil.which("claude")
    tmp_dir = _ensure_tmp_dir()
    _sweep_stale_tmp_files()

    sys_tmp_path: Optional[str] = None
    if system:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False,
            prefix=_TMP_PREFIX, dir=str(tmp_dir),
            encoding="utf-8",
        )
        tmp.write(system)
        tmp.close()
        os.chmod(tmp.name, 0o600)
        sys_tmp_path = tmp.name

    try:
        cmd = [
            bin_path, "-p",
            "--model", model or _DEFAULT_MODEL,
            "--effort", effort,
            "--output-format", "json",
            "--disable-slash-commands",
            "--setting-sources", "",
            "--strict-mcp-config",     # 不读默认 MCP server 配置
            "--no-session-persistence",
            "--tools", "",
            "--input-format", "text",
        ]
        if sys_tmp_path:
            cmd += ["--system-prompt-file", sys_tmp_path]

        # 过滤 CLAUDE_* 全部变量, 避免父进程 CLAUDE_CODE_SIMPLE / CLAUDE_xxx 干扰
        env = {k: v for k, v in os.environ.items()
                if not k.startswith("CLAUDE_")}

        t0 = time.time()
        try:
            proc = _run_with_session_isolation(
                cmd, input_text=prompt, env=env,
                cwd=str(tmp_dir),    # cwd 在私有 tmp 防读项目 CLAUDE.md
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            raise CCCLIError(f"claude 子进程超时 {timeout_sec}s")
        elapsed = time.time() - t0

        if proc.returncode != 0:
            stderr = (proc.stderr or "")[:300]
            raise CCCLIError(
                f"claude exit={proc.returncode} stderr={stderr}"
            )

        result_line = next(
            (l for l in proc.stdout.splitlines() if l.lstrip().startswith("{")),
            None,
        )
        if not result_line:
            raise CCCLIError(
                f"claude 输出无 JSON: {(proc.stdout or '')[:300]}"
            )
        try:
            data = json.loads(result_line)
        except json.JSONDecodeError as e:
            raise CCCLIError(f"claude 输出 JSON 解析失败: {e}") from e
        if data.get("is_error"):
            raise CCCLIError(
                f"claude is_error=True: {str(data.get('result',''))[:300]}"
            )

        usage = data.get("usage") or {}
        print(
            f"  [llm cc-cli] elapsed={elapsed:.1f}s "
            f"api_ms={data.get('duration_api_ms','?')} "
            f"out_tok={usage.get('output_tokens','?')} "
            f"cost_equiv=${data.get('total_cost_usd', 0):.4f}"
        )

        return data.get("result", "")

    finally:
        if sys_tmp_path:
            try:
                os.unlink(sys_tmp_path)
            except OSError:
                pass
```

- [ ] **Step 2: 跑单测**

Run: `uv run pytest tests/test_claude_code_cli.py -x -q`
Expected: 全过

- [ ] **Step 3: 跑全测确认未破坏老路径**

Run: `uv run pytest tests/ -x -q`
Expected: 全过

- [ ] **Step 4: Commit**

```bash
git add chisha/llm_providers/claude_code_cli.py tests/test_claude_code_cli.py
git commit -m "feat(llm): add claude_code_cli provider via subprocess (D-047)"
```

---

## Task 6: 写 provider routing 单测（红）

**Files:**
- Create: `tests/test_llm_provider_selection.py`

- [ ] **Step 1: 写测试**

```python
"""tests/test_llm_provider_selection.py — provider 路由逻辑."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


@pytest.fixture
def _clean_env(monkeypatch):
    """清掉关键 env 变量, 每个测试独立."""
    for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "CHISHA_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    yield monkeypatch


# === _resolve_provider 优先级 ===

def test_env_override_wins(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("CHISHA_LLM_PROVIDER", "openrouter")
    _clean_env.setenv("OPENROUTER_API_KEY", "sk-or")
    p = _resolve_provider({"provider": "anthropic"})
    assert p == "openrouter"


def test_invalid_env_raises(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("CHISHA_LLM_PROVIDER", "foo")
    with pytest.raises(ValueError, match="CHISHA_LLM_PROVIDER"):
        _resolve_provider(None)


def test_env_empty_string_treated_as_unset(_clean_env):
    """CHISHA_LLM_PROVIDER='' 不应触发 ValueError, 应当 fallback 到 auto."""
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("CHISHA_LLM_PROVIDER", "")
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk")
    assert _resolve_provider(None) == "anthropic"


def test_env_whitespace_only_treated_as_unset(_clean_env):
    """CHISHA_LLM_PROVIDER='   ' 同空"""
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("CHISHA_LLM_PROVIDER", "   ")
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk")
    assert _resolve_provider(None) == "anthropic"


def test_env_explicit_but_unavailable_raises(_clean_env):
    """显式选 openrouter 但没 OPENROUTER_API_KEY → RuntimeError 不是 silent fallback"""
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("CHISHA_LLM_PROVIDER", "openrouter")
    with pytest.raises(RuntimeError, match="不可用"):
        _resolve_provider(None)


def test_profile_explicit_but_unavailable_raises(_clean_env):
    """profile.llm.provider=anthropic 但无 ANTHROPIC_API_KEY → RuntimeError"""
    from chisha.llm_client import _resolve_provider
    with pytest.raises(RuntimeError, match="不可用"):
        _resolve_provider({"provider": "anthropic"})


def test_profile_explicit(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("OPENROUTER_API_KEY", "sk-or")
    p = _resolve_provider({"provider": "openrouter"})
    assert p == "openrouter"


def test_profile_invalid_raises(_clean_env):
    from chisha.llm_client import _resolve_provider
    with pytest.raises(ValueError, match="profile.llm.provider"):
        _resolve_provider({"provider": "deepseek"})


def test_auto_anthropic_wins_when_key_present(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk-fake")
    assert _resolve_provider({"provider": "auto"}) == "anthropic"


def test_auto_falls_to_claude_code_cli_when_no_key(_clean_env):
    from chisha.llm_client import _resolve_provider
    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=True):
        assert _resolve_provider({"provider": "auto"}) == "claude_code_cli"


def test_auto_falls_to_openrouter_when_no_cli(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("OPENROUTER_API_KEY", "sk-or-fake")
    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=False):
        assert _resolve_provider({"provider": "auto"}) == "openrouter"


def test_auto_all_unavailable_raises(_clean_env):
    from chisha.llm_client import _resolve_provider
    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=False):
        with pytest.raises(RuntimeError, match="无可用 LLM provider"):
            _resolve_provider({"provider": "auto"})


def test_no_profile_treated_as_auto(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk-x")
    assert _resolve_provider(None) == "anthropic"


# === _resolve_model 优先级 ===

def test_model_explicit_wins():
    from chisha.llm_client import _resolve_model
    profile = {"model": {"anthropic": "from-profile"}}
    assert _resolve_model("anthropic", "explicit", profile) == "explicit"


def test_model_from_profile():
    from chisha.llm_client import _resolve_model
    profile = {"model": {"anthropic": "from-profile"}}
    assert _resolve_model("anthropic", None, profile) == "from-profile"


def test_model_default_when_none():
    from chisha.llm_client import _resolve_model
    assert _resolve_model("anthropic", None, None) is None
    assert _resolve_model("anthropic", None, {}) is None


# === call_text 路由 ===

def test_call_text_routes_to_anthropic(_clean_env):
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk-fake")
    from chisha import llm_client
    with patch("chisha.llm_providers.anthropic_api.call",
                return_value="ANTHROPIC_REPLY") as m:
        out = llm_client.call_text("p", system="s")
        assert out == "ANTHROPIC_REPLY"
        assert m.call_count == 1


def test_call_text_routes_to_claude_code_cli(_clean_env):
    from chisha import llm_client
    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=True), \
         patch("chisha.llm_providers.claude_code_cli.call",
                return_value="CC_REPLY") as m:
        out = llm_client.call_text("p", system="s",
                                     profile_llm={"provider": "auto"})
        assert out == "CC_REPLY"
        assert m.call_count == 1


def test_call_text_passes_model_kwarg(_clean_env):
    """显式 model 参数优先级最高, 透传到 provider"""
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk")
    from chisha import llm_client
    with patch("chisha.llm_providers.anthropic_api.call") as m:
        m.return_value = "x"
        llm_client.call_text("p", model="claude-opus-4-7",
                              profile_llm={"model": {"anthropic": "ignored"}})
        assert m.call_args.kwargs["model"] == "claude-opus-4-7"


def test_has_llm_key_truthy(_clean_env):
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk")
    from chisha import llm_client
    assert llm_client.has_llm_key() is True


def test_has_llm_key_false(_clean_env):
    from chisha import llm_client
    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=False):
        assert llm_client.has_llm_key() is False
```

- [ ] **Step 2: 跑测确认红**

Run: `uv run pytest tests/test_llm_provider_selection.py -x -q 2>&1 | tail -10`
Expected: AttributeError / ImportError, 因为 `_resolve_provider` 等函数还没实现

---

## Task 7: 重构 llm_client.py 让 Task 6 单测绿

**Files:**
- Modify: `chisha/llm_client.py`

- [ ] **Step 1: 重写 llm_client.py**

⚠️ Codex review 修正后版本：空 env 处理、显式 provider 可用性校验、observability 日志。

```python
"""LLM 调用入口 (D-047).

provider 路由 + 选择策略:
- env CHISHA_LLM_PROVIDER 强制 > profile.llm.provider 显式 > auto-detect
- auto 顺序: ANTHROPIC_API_KEY > claude_code_cli 订阅 > OPENROUTER_API_KEY
- 显式选定 provider 时也检查可用性, 不可用直接 RuntimeError 给清晰错误

具体 provider 实现见 chisha/llm_providers/.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

from chisha.llm_providers import anthropic_api, claude_code_cli, openrouter


_PROVIDER_NAMES = {"anthropic", "openrouter", "claude_code_cli"}


def _is_available(provider: str) -> bool:
    return {
        "anthropic": anthropic_api.is_available,
        "openrouter": openrouter.is_available,
        "claude_code_cli": claude_code_cli.is_available,
    }[provider]()


def _resolve_provider(profile_llm: Optional[dict]) -> str:
    """决定走哪个 provider. 优先级 env > profile > auto.

    显式选定 (env/profile) 时检查可用性, 不可用直接 RuntimeError 给清晰错误.
    """
    # 1. 环境变量强制 (空白当 unset)
    env_raw = os.environ.get("CHISHA_LLM_PROVIDER") or ""
    env_val = env_raw.strip()
    if env_val:
        if env_val not in _PROVIDER_NAMES:
            raise ValueError(
                f"未知 CHISHA_LLM_PROVIDER={env_val!r}, "
                f"合法值: {sorted(_PROVIDER_NAMES)}"
            )
        if not _is_available(env_val):
            raise RuntimeError(
                f"CHISHA_LLM_PROVIDER={env_val} 但该 provider 不可用 "
                f"(缺 API key 或 CLI 未登录)"
            )
        return env_val

    # 2. profile 配置
    if profile_llm:
        pv = (profile_llm.get("provider") or "auto").strip()
        if pv and pv != "auto":
            if pv not in _PROVIDER_NAMES:
                raise ValueError(
                    f"未知 profile.llm.provider={pv!r}, "
                    f"合法值: {sorted(_PROVIDER_NAMES)} 或 'auto'"
                )
            if not _is_available(pv):
                raise RuntimeError(
                    f"profile.llm.provider={pv} 但该 provider 不可用 "
                    f"(缺 API key 或 CLI 未登录)"
                )
            return pv

    # 3. auto-detect
    if anthropic_api.is_available():
        return "anthropic"
    if claude_code_cli.is_available():
        return "claude_code_cli"
    if openrouter.is_available():
        return "openrouter"
    raise RuntimeError(
        "无可用 LLM provider. 选项: "
        "(1) 设 ANTHROPIC_API_KEY (2) 装 + 登录 Claude Code (claude auth login) "
        "(3) 设 OPENROUTER_API_KEY"
    )


def _resolve_model(provider: str, model: Optional[str],
                    profile_llm: Optional[dict]) -> Optional[str]:
    """显式 model > profile.model.<provider> > None (provider 用自己默认)."""
    if model:
        return model
    if profile_llm:
        m = (profile_llm.get("model") or {}).get(provider)
        if m:
            return m
    return None


_DISPATCH = {
    "anthropic": anthropic_api.call,
    "openrouter": openrouter.call,
    "claude_code_cli": claude_code_cli.call,
}


def call_text(
    prompt: str,
    *,
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: Optional[str] = None,
    cache_system: bool = False,
    profile_llm: Optional[dict] = None,
) -> str:
    """单次 LLM 调用入口."""
    provider = _resolve_provider(profile_llm)
    final_model = _resolve_model(provider, model, profile_llm)
    # observability: 让用户看见实际走哪路, 防止 .env 残留 key 偷偷打掉订阅
    print(f"  [llm] provider={provider} model={final_model or '(default)'}")
    return _DISPATCH[provider](
        prompt,
        system=system,
        model=final_model,
        max_tokens=max_tokens,
        temperature=temperature,
        cache_system=cache_system,
    )


def has_llm_key() -> bool:
    """兼容老 API: 是否有任何可用 provider."""
    try:
        _resolve_provider(None)
        return True
    except RuntimeError:
        return False
```

- [ ] **Step 2: 跑 routing 单测**

Run: `uv run pytest tests/test_llm_provider_selection.py -x -q`
Expected: 全过

- [ ] **Step 3: 跑全测**

Run: `uv run pytest tests/ -x -q`
Expected: 全过

- [ ] **Step 4: Commit**

```bash
git add chisha/llm_client.py tests/test_llm_provider_selection.py
git commit -m "refactor(llm): thin routing layer + provider selection (D-047)"
```

---

## Task 8: rerank.py / reason.py 调用点传 profile_llm

**Files:**
- Modify: `chisha/rerank.py`
- Modify: `chisha/reason.py`（如有 LLM 调用）
- Modify: `chisha/api.py` 或 V2 主路径文件

- [ ] **Step 1: 找 rerank.py 里的 call_text 调用**

Run: `grep -n 'call_text\|from chisha.llm_client' chisha/rerank.py`
当前在 `_llm_rerank()` 函数, ~530 行

- [ ] **Step 2: 改 _llm_rerank 签名加 profile_llm**

在 `chisha/rerank.py` 找到 `_llm_rerank` 定义：

旧:
```python
def _llm_rerank(top_combos: list[dict], profile: dict,
                context: "ContextSnapshot | None", n: int, n_explore: int,
                model: str | None = None,
                n_max: int = 5) -> list[dict] | None:
```

新（加 `profile_llm` 提取）：
```python
def _llm_rerank(top_combos: list[dict], profile: dict,
                context: "ContextSnapshot | None", n: int, n_explore: int,
                model: str | None = None,
                n_max: int = 5) -> list[dict] | None:
    """调 LLM 返回 list of candidate dict, 失败返回 None (上游 fallback).

    D-047: 透传 profile.llm 段给 llm_client, 支持 provider 切换.
    """
    try:
        from chisha.llm_client import call_text
        system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        user_msg = build_user_message(top_combos, profile, context,
                                       n=n, n_explore=n_explore)
        kwargs: dict[str, Any] = {
            "max_tokens": 2048, "temperature": 0.0,
            "system": system_prompt, "cache_system": True,
            "profile_llm": profile.get("llm"),   # ⭐ 新增
        }
        if model:
            kwargs["model"] = model
        out = call_text(user_msg, **kwargs)
        # ... 后续保持不变
```

- [ ] **Step 3: 同样改 reason.py（如有 call_text 调用）**

Run: `grep -rn 'call_text\|from chisha.llm_client' chisha/ --include='*.py'`

对所有 `call_text(...)` 调用，从 `profile` 提取 `profile.get("llm")` 并加 `profile_llm=` kwarg。

- [ ] **Step 4: 跑相关单测**

Run: `uv run pytest tests/test_rerank.py tests/test_reason.py -x -q`
Expected: 全过（profile 单测里如果没有 `llm` 段, `profile.get("llm")` 返回 None，行为不变）

- [ ] **Step 5: 跑全测**

Run: `uv run pytest tests/ -x -q`
Expected: 全过

- [ ] **Step 6: Commit**

```bash
git add chisha/rerank.py chisha/reason.py
git commit -m "feat(llm): pass profile.llm through rerank/reason to provider router (D-047)"
```

---

## Task 9: profile.yaml 加 llm 段 + 文档

**Files:**
- Modify: `profile.yaml`
- Create or Modify: `docs/DECISIONS.md`（D-047 条目）
- Modify: `docs/ROADMAP.md`（"当前状态" 加一行）

- [ ] **Step 1: profile.yaml 顶层加 llm 段**

```yaml
# === LLM 调用配置 (D-047) ===
llm:
  # provider 选择: auto | claude_code_cli | anthropic | openrouter
  # auto-detect 优先级: ANTHROPIC_API_KEY > claude_code_cli 订阅 > OPENROUTER_API_KEY
  # 环境变量 CHISHA_LLM_PROVIDER 可强制覆盖
  provider: auto

  # 各 provider 用哪个 model (可选, 不写用 provider 默认)
  model:
    claude_code_cli: sonnet
    anthropic: claude-sonnet-4-6
    openrouter: anthropic/claude-sonnet-4.6
```

- [ ] **Step 2: 在 docs/DECISIONS.md 末尾加 D-047**

```markdown
## D-047 — LLM Provider 抽象 + Claude Code CLI 路径

**日期**: 2026-05-14
**状态**: 已实施

**背景**: 自用阶段每天 1-2 次推荐, 用 ANTHROPIC_API_KEY 月成本 ¥20-100,
而本机已有 Max 订阅. 让 chisha 复用订阅额度调 LLM, 同时保留 API key /
OpenRouter 路径供未来分发用户使用.

**方案**: subprocess 调 `claude -p`, 7 个隔离 flag (--effort low /
--tools "" / --disable-slash-commands / --setting-sources "" /
--no-session-persistence / --system-prompt-file / --input-format text),
cwd='/tmp' 防 CLAUDE.md 污染, env 过滤 CLAUDE_CODE_* 防干扰.

**架构**: chisha/llm_providers/ 子包, 三 provider 统一签名;
chisha/llm_client.py 成薄路由层; profile.yaml `llm` 段控制 + 环境变量
`CHISHA_LLM_PROVIDER` 强制覆盖.

**实测**: N=60 sonnet effort=low 端到端 60s, 输出结构正确;
订阅消耗 1 message 配额/次. 详见 spec:
docs/superpowers/specs/2026-05-14-claude-code-cli-provider-design.md
```

- [ ] **Step 3: docs/ROADMAP.md "当前状态" 段加一行**

在合适位置加: `- **LLM Provider 抽象 + Claude Code 订阅路径**（[D-047](DECISIONS.md#d-047)，2026-05-14）：三 provider 通过 profile.yaml + env 切换, 自用走订阅省钱.`

- [ ] **Step 4: 跑 e2e 三组对照**

```bash
# 1. 默认（订阅）
CHISHA_LLM_PROVIDER=claude_code_cli uv run python -c "
from chisha.debug_recommend import debug_recommend
t = debug_recommend(meal_type='lunch', use_llm_rerank=True)
print('final:', [c['combo_index'] for c in t['final']['candidates']])
print('fallback?', t['l3_rerank'].get('used_fallback'))
"

# 2. OpenRouter (如有 key)
# CHISHA_LLM_PROVIDER=openrouter ... 同上

# 3. Anthropic (如有 key)
# CHISHA_LLM_PROVIDER=anthropic ... 同上
```

记录:
- 三组都拿到 5 条 candidates
- combo_index 都合法
- 三组 top-3 jaccard ≥ 0.5

- [ ] **Step 5: Commit**

```bash
git add profile.yaml docs/DECISIONS.md docs/ROADMAP.md
git commit -m "docs(D-047): record LLM provider abstraction + Claude Code CLI path"
```

---

## Task 10: 集成测试 (opt-in)

**Files:**
- Create: `tests/integration/test_claude_code_cli_e2e.py`

- [ ] **Step 1: 写 e2e 测试 (跳过 if CLI 不可用)**

```python
"""集成测试: 需本机 claude CLI + Max 订阅, 不在 CI 跑."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.requires_claude_cli


@pytest.fixture(scope="module")
def _skip_if_no_cli():
    from chisha.llm_providers import claude_code_cli as cc
    cc.reset_cli_check_cache()
    if not cc.is_available():
        pytest.skip("claude CLI 不可用或未登录订阅")


def test_ping_echo(_skip_if_no_cli):
    """最简 ping: system='你是回声机' + user 'hello' → 含 'hello'"""
    from chisha.llm_providers import claude_code_cli as cc
    out = cc.call(
        "hello",
        system="你是回声机, 用户说什么你重复什么, 不要加任何修饰",
        model="sonnet", timeout_sec=60,
    )
    assert "hello" in out.lower()


def test_real_rerank_end_to_end(_skip_if_no_cli):
    """真跑 N=10 rerank → 解析为 valid JSON."""
    import datetime as dt
    import json
    import re
    from pathlib import Path

    from chisha.debug_recommend import _build_l1_trace, ROOT
    from chisha.rerank import build_user_message, SYSTEM_PROMPT_PATH
    from chisha.recall import (
        load_profile, load_zone_data, load_meal_log,
    )
    from chisha.context import build_context
    from chisha.score import rank_combos, apply_caps
    from chisha.llm_providers import claude_code_cli as cc

    profile = load_profile(ROOT / "profile.yaml")
    zone = profile["basics"]["zones"].get(
        "lunch", profile["basics"]["office_zone"]
    )
    rests, tagged = load_zone_data(zone, ROOT)
    meal_log = load_meal_log(ROOT)
    today = dt.date.today()
    _, combos = _build_l1_trace(
        profile, rests, tagged, meal_log, today, meal_type="lunch"
    )
    ctx = build_context(profile, meal_log, "lunch", today)
    ranked_raw = rank_combos(
        combos, profile, meal_log, today,
        context=ctx, meal_type="lunch", root=ROOT,
    )
    ranked = apply_caps(ranked_raw, profile)
    top10 = ranked[:10]

    sys_text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    user_msg = build_user_message(top10, profile, ctx, n=5, n_explore=2)

    out = cc.call(
        user_msg, system=sys_text, model="sonnet",
        timeout_sec=180,
    )
    m = re.search(r"\{.*\}", out, re.DOTALL)
    assert m, f"未找到 JSON, 实际: {out[:300]}"
    data = json.loads(m.group(0))
    cands = data.get("candidates")
    assert isinstance(cands, list)
    assert len(cands) == 5
    for c in cands:
        assert "combo_index" in c
        assert 0 <= c["combo_index"] < 10
```

- [ ] **Step 2: 跑（含 marker）**

Run: `uv run pytest tests/integration/ -m requires_claude_cli -v`
Expected: 2 passed (本机环境)

- [ ] **Step 3: 跑默认全测（应跳过 integration）**

Run: `uv run pytest tests/ -q`
Expected: 全过且 integration 跳过（"X deselected"）

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_claude_code_cli_e2e.py
git commit -m "test(D-047): integration test for claude_code_cli e2e (opt-in)"
```

---

## Task 11: 拆删 llm_client_openrouter.py (如还存在)

**Files:**
- Maybe delete: `chisha/llm_client_openrouter.py`

- [ ] **Step 1: 看是否还被引用**

Run: `grep -rn 'llm_client_openrouter' chisha/ tests/ scripts/`

- [ ] **Step 2: 如无引用, 删除**

```bash
git rm chisha/llm_client_openrouter.py 2>/dev/null || true
```

- [ ] **Step 3: Commit (如有删除)**

```bash
git commit -m "chore: remove obsolete chisha/llm_client_openrouter.py (D-047)"
```

---

## Self-Review Checklist

After 完成上面 11 个 task：

- [ ] 跑全测 `uv run pytest tests/ -q` 全过
- [ ] 跑 integration `uv run pytest tests/integration -m requires_claude_cli` 本机过
- [ ] 手动 e2e 三 provider 对照（Task 9 Step 4）
- [ ] `grep -rn 'os.environ.get("ANTHROPIC_API_KEY"\|os.environ.get("OPENROUTER_API_KEY"' chisha/` — 只应在 anthropic_api.py / openrouter.py 各一处
- [ ] `grep -rn '_call_anthropic\|_call_openrouter' chisha/` — 应已无残留
- [ ] 临时文件命名 prefix=`chisha_sys_` 不会和别人冲突
- [ ] CCCLIError 信息截断到 300 字符
- [ ] `_check_cli` 缓存到模块级, 测试用 `reset_cli_check_cache()` 清

如发现 spec 里有 task 没覆盖的需求, 补 task 修复.

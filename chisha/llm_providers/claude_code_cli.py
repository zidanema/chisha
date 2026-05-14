"""Claude Code CLI subprocess provider (D-047).

复用本机 Claude Code 订阅额度调 LLM. 通过 `claude -p` 子进程实现.
关键设计 (见 docs/superpowers/specs/2026-05-14-claude-code-cli-provider-design.md §3):
- 10 个 flag 隔离 Claude Code 默认行为 (含 --strict-mcp-config)
- system 通过 --system-prompt-file 私有临时文件传, user 通过 stdin
- effort=low 防 extended thinking 拖长延迟
- cwd 用本地私有目录 + 过滤 CLAUDE_* env 防污染
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
_DEFAULT_TIMEOUT = 180       # N=60 实测 60s, 留 3x buffer
_DEFAULT_EFFORT = "low"

# 私有临时目录: 0700, 用户级, 防止 /tmp 全局可见
_TMP_DIR = Path(os.environ.get("XDG_CACHE_HOME") or
                Path.home() / ".cache") / "chisha" / "llm_tmp"
_TMP_PREFIX = "chisha_sys_"
_TMP_STALE_SEC = 3600        # >1h 的残留文件清掉

# 必须从子进程 env 里清掉的"会让 Claude Code 走付费 API 而非订阅"的变量
# Codex review P1#1: ANTHROPIC_API_KEY 存在时 Claude Code 优先走 API, 订阅被劫持
_BLOCKED_ENV_PREFIXES = ("CLAUDE_", "ANTHROPIC_")
_BLOCKED_ENV_EXACT = {
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
}

# auth status 正向 cache TTL (Codex review P2#3): 防 revoked token 永久 stale
_POSITIVE_TTL_SEC = 300      # 5 min


class CCCLIError(Exception):
    """Claude Code CLI 调用失败"""


# 进程级 cache: (result, expiry_ts) — 仅缓存正向, 负向永不缓存
_cli_check_cache: Optional[tuple] = None


def _ensure_tmp_dir() -> Path:
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
    """检查 claude CLI 是否可用 + 订阅登录态.

    Codex review P2#3:
    - 仅缓存"可用"的正向结果, 有 TTL (_POSITIVE_TTL_SEC)
    - 不缓存"不可用"的负向结果, 下次再探, 防 transient timeout 永久标记 stale
    """
    global _cli_check_cache
    # 正向 cache 命中 + 未过期
    if _cli_check_cache is not None:
        result, expiry = _cli_check_cache
        if time.time() < expiry:
            return result
    bin_path = shutil.which("claude")
    if not bin_path:
        return False  # 不缓存负向
    try:
        r = subprocess.run(
            [bin_path, "auth", "status"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return False  # 不缓存负向
        info = json.loads(r.stdout)
        ok = (
            bool(info.get("loggedIn"))
            and info.get("apiProvider") == "firstParty"
        )
        if ok:
            _cli_check_cache = (True, time.time() + _POSITIVE_TTL_SEC)
            return True
        return False  # 不缓存负向
    except (subprocess.TimeoutExpired, subprocess.SubprocessError,
            json.JSONDecodeError, OSError):
        return False  # 不缓存负向


def reset_cli_check_cache() -> None:
    """测试用, 清掉模块级 cache."""
    global _cli_check_cache
    _cli_check_cache = None


def is_available() -> bool:
    return _check_cli()


def _pdeathsig_preexec() -> None:
    """Linux 专属: 让 kernel 在父进程死时给子进程发 SIGTERM.

    Codex review P1#2: start_new_session 把子进程从父的 session 分离,
    parent SIGKILL 时子会变 orphan. prctl(PR_SET_PDEATHSIG, SIGTERM)
    确保 kernel 主动杀子.
    """
    import sys
    if sys.platform != "linux":
        return
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        # PR_SET_PDEATHSIG = 1, signal = 15 (SIGTERM)
        libc.prctl(1, 15, 0, 0, 0)
    except (OSError, AttributeError):
        pass


def _run_with_session_isolation(
    cmd: list, *, input_text: str, env: dict, cwd: str, timeout: int,
) -> subprocess.CompletedProcess:
    """Popen + start_new_session 等价于 subprocess.run, 但子进程在独立 session.

    父进程被信号杀时, 子进程不会成 orphan 继续吃 CPU. 超时主动 terminate ->
    kill 整个进程组.

    Codex review P1#2: 加 preexec_fn 用 prctl PR_SET_PDEATHSIG, 让 Linux
    kernel 在父被 SIGKILL 时也能杀子.
    """
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        start_new_session=True,
        preexec_fn=_pdeathsig_preexec,
    )
    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        # 终止整个 session (含可能 spawn 的孙进程)
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            stdout, stderr = proc.communicate()
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def call(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    # ⚠️ max_tokens 在 CLI 路径不生效 (D-048 MAJOR 1, Codex review).
    # claude -p 子进程没有 max_tokens 协议参数, 这个值只是 API 兼容签名占位.
    # 防 inline CoT 失控的真实兜底是 timeout_sec (默认 180s), 超时后子进程
    # SIGKILL, 上游 _run_llm_rerank 接住 subprocess.TimeoutExpired 走 fallback.
    max_tokens: int = 4096,
    temperature: float = 0.0,  # 同上, CLI 不接受
    cache_system: bool = False,  # 同上, CLI 自管 prompt cache
    json_mode: bool = False,   # 同上, CLI 不接受
    tools: Optional[list] = None,
    tool_choice: Optional[dict] = None,
    timeout_sec: int = _DEFAULT_TIMEOUT,
    effort: str = _DEFAULT_EFFORT,
) -> dict:
    """通过 claude -p 子进程调 LLM, 返回 dict (D-047 接口).

    Args:
        prompt: user message (走 stdin)
        system: system prompt (走 --system-prompt-file 临时文件)
        model: 'sonnet' / 'opus' / 'claude-sonnet-4-6' 等
        timeout_sec: 子进程超时 (默认 180s). **这是 CLI 路径唯一的输出长度兜底**,
            max_tokens 在 CLI 不生效 (D-048 MAJOR 1).
        effort: extended thinking 强度, low/medium/high/xhigh/max
        tools / tool_choice: CLI 不支持原生 tool_use, 传入会抛
            NotImplementedError. 调用方应改走 anthropic / openrouter.
        max_tokens / temperature / cache_system / json_mode: CLI 不支持, 静默忽略.

    Returns:
        dict, 字段: type="text", content, stop_reason, usage, model, raw_text
    """
    if tools or tool_choice:
        raise NotImplementedError(
            "claude_code_cli provider 不支持 tools/tool_choice 强制 schema. "
            "调用方应切到 anthropic 或 openrouter provider (D-047)."
        )
    _ = json_mode  # 兼容签名, 静默忽略
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
        try:
            os.chmod(tmp.name, 0o600)
        except OSError:
            pass
        sys_tmp_path = tmp.name

    try:
        cmd = [
            bin_path, "-p",
            "--model", model or _DEFAULT_MODEL,
            "--effort", effort,
            "--output-format", "json",
            "--disable-slash-commands",
            "--setting-sources", "",
            "--strict-mcp-config",  # 不读默认 MCP server 配置
            "--no-session-persistence",
            "--tools", "",
            "--input-format", "text",
        ]
        if sys_tmp_path:
            cmd += ["--system-prompt-file", sys_tmp_path]

        # 过滤 CLAUDE_* / ANTHROPIC_* / OPENROUTER_* 等会让 Claude Code 走
        # 付费 API 而非订阅 OAuth 的变量 (Codex review P1#1).
        env = {
            k: v for k, v in os.environ.items()
            if not any(k.startswith(p) for p in _BLOCKED_ENV_PREFIXES)
            and k not in _BLOCKED_ENV_EXACT
        }

        t0 = time.time()
        try:
            proc = _run_with_session_isolation(
                cmd, input_text=prompt, env=env,
                cwd=str(tmp_dir),  # cwd 在私有 tmp 防读项目 CLAUDE.md
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

        text = data.get("result", "") or ""
        return {
            "type": "text",
            "content": text,
            "stop_reason": "stop",
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0) or 0,
                "completion_tokens": usage.get("output_tokens", 0) or 0,
                "cached_tokens": usage.get("cache_read_input_tokens", 0) or 0,
                "cache_write_tokens": usage.get("cache_creation_input_tokens", 0) or 0,
                "cost": data.get("total_cost_usd", 0) or 0,
            },
            "model": model or _DEFAULT_MODEL,
            "raw_text": text,
        }

    finally:
        if sys_tmp_path:
            try:
                os.unlink(sys_tmp_path)
            except OSError:
                pass

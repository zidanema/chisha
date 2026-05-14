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


class CCCLIError(Exception):
    """Claude Code CLI 调用失败"""


# 进程级 cache: claude auth status 调用一次 ~500ms, 不重复
_cli_check_cache: Optional[bool] = None


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
    cmd: list, *, input_text: str, env: dict, cwd: str, timeout: int,
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
        start_new_session=True,  # 关键: 子进程在新 session
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
    max_tokens: int = 4096,    # 兼容签名, CLI 不直接支持
    temperature: float = 0.0,  # 同上
    cache_system: bool = False,  # 同上, CLI 自管 prompt cache
    timeout_sec: int = _DEFAULT_TIMEOUT,
    effort: str = _DEFAULT_EFFORT,
) -> str:
    """通过 claude -p 子进程调 LLM, 返回纯文本输出.

    Args:
        prompt: user message (走 stdin)
        system: system prompt (走 --system-prompt-file 临时文件)
        model: 'sonnet' / 'opus' / 'claude-sonnet-4-6' 等
        timeout_sec: 子进程超时 (默认 180s)
        effort: extended thinking 强度, low/medium/high/xhigh/max
    """
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

        # 过滤 CLAUDE_* 全部变量
        env = {k: v for k, v in os.environ.items()
                if not k.startswith("CLAUDE_")}

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

        return data.get("result", "")

    finally:
        if sys_tmp_path:
            try:
                os.unlink(sys_tmp_path)
            except OSError:
                pass

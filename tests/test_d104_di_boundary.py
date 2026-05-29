"""D-104 Step2/3: agent-only core 不依赖 sandbox 的 import 边界回归 + provider 注册.

核心不变量 (此前无测试覆盖, 是整个解耦的护栏):
- import agent core 入口闭包后, chisha.sandbox 不在 sys.modules (core→extras 解耦);
- 不 import sandbox 时 ambient provider 是 Real/Default (0-diff 默认);
- sandbox (extras) 一被 import 就注册 VirtualClock + RealSandboxRouter;
- slim core (sandbox 不可 import) 下 agent_cli guard 优雅降级, 不崩。

全用子进程跑: 保证 import 状态干净 (本测试进程可能已被别的测试 import 过 sandbox)。
"""
import subprocess
import sys

CORE_ENTRYPOINTS = [
    "chisha.agent_cli", "chisha.agent_orchestration", "chisha.recall",
    "chisha.score", "chisha.rerank", "chisha.refine_intent_v2",
    "chisha.clock", "chisha.data_root", "chisha.core_api_helpers",
    "chisha.api", "chisha.trace_store",
]


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True)


# D-104 总边界: import agent core 闭包后, 这些 extras / 重依赖都不许进 sys.modules
# (Step0 重依赖 + Step2/3 sandbox + Step4 自调 LLM + debug/web 一网打尽; Step5 smoke 同款)。
FORBIDDEN_IN_CORE = [
    "chisha.sandbox", "chisha.llm_client", "chisha.llm_client_openrouter",
    "chisha.web_api", "chisha.debug_recommend", "chisha.debug_server",
    "fastapi", "uvicorn", "anthropic", "openai", "pandas",
]


def test_core_import_closure_excludes_extras_and_heavy_deps():
    """import 全部 agent core 入口后, sandbox / 自调LLM / web/debug / 重依赖都不在
    sys.modules —— 这是整个 D-104 解耦的护栏 (未来谁加了顶层 import 立刻红)。"""
    code = (
        "import sys, importlib\n"
        f"for m in {CORE_ENTRYPOINTS!r}:\n"
        "    importlib.import_module(m)\n"
        f"forbidden = {FORBIDDEN_IN_CORE!r}\n"
        "leak = sorted(m for m in forbidden if m in sys.modules)\n"
        "assert not leak, f'BOUNDARY VIOLATION: core 拉入了 {leak}'\n"
        "print('OK')\n"
    )
    r = _run(code)
    assert r.returncode == 0, f"边界破坏:\n{r.stdout}\n{r.stderr}"


def test_core_defaults_are_real_clock_and_default_router():
    """不 import sandbox 时 provider 是 Real/Default (0-diff 默认)。"""
    code = (
        "import importlib\n"
        "for m in ['chisha.clock', 'chisha.data_root']:\n"
        "    importlib.import_module(m)\n"
        "from chisha import clock_provider, sandbox_router\n"
        "assert type(clock_provider.get_clock_provider()).__name__ == 'RealClockProvider'\n"
        "assert type(sandbox_router.get_sandbox_router()).__name__ == '_DefaultSandboxRouter'\n"
        "print('OK')\n"
    )
    r = _run(code)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"


def test_importing_sandbox_registers_providers():
    """import sandbox (extras) → core provider 切换为 Virtual/Real。"""
    code = (
        "import chisha.sandbox  # noqa\n"
        "from chisha import clock_provider, sandbox_router\n"
        "assert type(clock_provider.get_clock_provider()).__name__ == '_VirtualClockProvider'\n"
        "assert type(sandbox_router.get_sandbox_router()).__name__ == '_RealSandboxRouter'\n"
        "print('OK')\n"
    )
    r = _run(code)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"


def test_guard_scope_degrades_when_sandbox_unimportable():
    """slim core: sandbox 不可 import → _guard_scope 当未启用, 不抛 (Codex fork=A)。"""
    code = (
        "import sys\n"
        "sys.modules['chisha.sandbox'] = None  # 模拟 slim core: sandbox 物理缺席\n"
        "from chisha import agent_cli\n"
        "from pathlib import Path\n"
        "agent_cli._guard_scope(Path('/tmp'), 'production')  # 不应抛\n"
        "print('OK')\n"
    )
    r = _run(code)
    assert r.returncode == 0, f"guard 未优雅降级:\n{r.stdout}\n{r.stderr}"


def test_run_llm_rerank_degrades_when_llm_client_unimportable():
    """slim core: llm_client (anthropic/openai SDK) 不可 import → _run_llm_rerank 退
    fallback (status='fallback', 非 config_error), 不崩 (D-104 Step4 guard)。"""
    code = (
        "import sys\n"
        "sys.modules['chisha.llm_client'] = None  # 模拟 slim core: LLM SDK extras 缺席\n"
        "from chisha.rerank import _run_llm_rerank\n"
        "res = _run_llm_rerank([], {}, None, n=1, n_explore=0)\n"
        "assert res['status'] == 'fallback', res\n"
        "assert res['config_error'] is False, res\n"
        "print('OK')\n"
    )
    r = _run(code)
    assert r.returncode == 0, f"rerank guard 未降级:\n{r.stdout}\n{r.stderr}"

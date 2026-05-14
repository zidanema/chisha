# Claude Code CLI Provider 设计文档

> 任务：让 chisha 推荐链路的 LLM 调用支持复用本机 Claude Code 订阅额度，避免必须配 ANTHROPIC_API_KEY / OPENROUTER_API_KEY。三 provider 通过配置切换。
> 日期：2026-05-14
> 状态：设计阶段（待 Codex review 收敛）

---

## 1. 目标

**核心诉求**：
1. 默认情况下，本机有 Claude Code CLI + 已登录订阅 → 自动用订阅调 LLM
2. 配置可显式切到 Anthropic API key / OpenRouter 路径（未来分发给没订阅的用户）
3. 不污染当前推荐链路的输出质量（精排员 prompt 不被 Claude Code 内置 system 干扰）
4. 实施工作量可控，不动 rerank.py / reason.py 的业务逻辑，只动 llm_client.py

**非目标**：
- 不支持本机 Ollama / vLLM 等自部署模型
- 不破解 Claude Code OAuth token 直连 Anthropic API（违反 ToS 灰区）
- 不重写 reason.py（V1 路径），先只覆盖 rerank.py（V2 路径）和 reason.py 调用点

---

## 2. Codex review 修正（2026-05-14）

经过 Codex 一轮 review 后补充：

| Codex 反馈 | 修正点 |
|---|---|
| (1) 实际是 10 个 flag 不是 7 个；`--bare` 跳过 CLAUDE.md 但和 OAuth 互斥 → 必须证明 CLAUDE.md 不会泄漏 | 改写文档统一为 "10 个 flag"；测试用真假 `~/.claude/CLAUDE.md` + 项目 `CLAUDE.md` 验证不泄漏；加 `--strict-mcp-config` |
| (2) `CHISHA_LLM_PROVIDER=""` 当成 unset；空白只在 strip 后被识别 → 不一致 | 显式：`env_val = os.environ.get(...) or ""` ; `if env_val.strip(): ...` 否则按 unset 处理 |
| (2) profile 显式 provider 不检查可用性 → 失败时错误不清晰 | provider 解析后立刻调 `is_available()` 检测，不可用则 RuntimeError 给清晰错误 |
| (2) `.env` 残留旧 API key 会"偷偷"打掉订阅检测 | auto-detect 顺序文档化告警；新增"可观测性"：每次 call_text 打 `[llm] provider=X model=Y` 日志，让用户看到实际走哪路 |
| (3) `finally` 清理在 SIGKILL/crash 时失效 → 残留文件 | 启动时 sweep 老的 `chisha_sys_*.md` 文件（>1h）；用私有目录 `~/.cache/chisha/llm_tmp/` 0700 权限 |
| (4) 父进程被信号杀时子进程可能成 orphan | 用 `Popen(start_new_session=True)` + 显式 terminate / kill；不能用 `subprocess.run` 一把梭 |
| (5) Isolation 测试太浅 | 加真实 CLI 集成测试：fake `~/.claude/CLAUDE.md` / 项目 `CLAUDE.md` / hooks settings 验证不影响输出 |
| (5) env edge cases 缺 | 加 `""` / `"  "` / stale `.env` / 显式 provider 缺 key 多组 case |
| (5) 并发 case 缺 | 加并发调用单测：唯一临时文件、无 cache 互染 |

---

## 3. 调研事实（2026-05-14 本机实测）

### 3.1 环境状态
- Claude Code CLI: 2.1.141（`/root/.nvm/versions/node/v22.22.0/bin/claude`）
- 登录态: Max 订阅, OAuth claude.ai, firstParty provider
- `claude auth status --json` 可程序化检测

### 2.2 关键 CLI flag 验证（共 7 个必加 flag）

| Flag | 必加原因 | 实测影响 |
|---|---|---|
| `-p` / `--print` | 非交互式 prompt-and-exit | basic |
| `--output-format json` | 拿结构化结果，含 usage / cost / duration / model | basic |
| `--model sonnet`（或 `opus`） | 指定模型，订阅版接受 alias 或 `claude-sonnet-4-6` 全名 | basic |
| `--effort low` | **关键**：Claude Code 默认 effort 触发 extended thinking, N=60 推理时间 200s+；改 low 后 60s | 推理时长 -70% |
| `--tools ""` | 禁内置工具描述，砍掉 ~10k tokens 注入 prompt | cache_creation 12k → 1.8k |
| `--disable-slash-commands` | 禁 skill auto-injection，防全局 skill（如 superpowers）干扰 prompt | 防污染 |
| `--setting-sources ""` | 不读 user/project/local settings.json，防 hook 副作用 | 防污染 |
| `--no-session-persistence` | 不写 session 文件到磁盘 | 隔离 |
| `--system-prompt-file <path>` | **关键**：替代 `--system-prompt` inline；inline 超 4k 时 argv 异常；file 形态稳定 | 兼容性 |
| `--input-format text` + stdin | user message 走 stdin 而不是 argv，避免 argv 长度问题 | 兼容性 |

### 2.3 实测 N=60 完整 e2e 数据

```
cmd: claude -p --model sonnet --effort low --output-format json \
     --disable-slash-commands --setting-sources "" --no-session-persistence \
     --tools "" --system-prompt-file <rerank_system.md> \
     --input-format text <<< <user_msg>

real_time: 60.9s
api_ms: 61149ms
usage: input=3, cache_read=15930, output=3391
  注: cache_read 15930 = system_prompt + user_msg 整个走 Claude prompt cache（1h ephemeral）
  注: output 3391 包含 extended thinking (~3100 tokens) + actual JSON (~250 tokens)
cost_usd: $0.067 (但订阅用户实际消耗 1 message 配额, 不付 token 费)
output 质量: 5 条 candidates 结构正确, exploit 3 + explore 2, reason 具体有对比
```

### 2.4 隐藏陷阱（已验证）

| 陷阱 | 现象 | 规避手段 |
|---|---|---|
| Claude Code 内置 system prompt 注入 | 默认 prompt 含工具描述 + agent identity ~10k tokens | `--tools ""` 砍工具描述, 剩 ~1.8k 不可砍 |
| Skill auto-injection (e.g. superpowers) | 全局 skill 会嫁接强制指令 | `--disable-slash-commands` |
| CLAUDE.md auto-discovery | 读 cwd 和 ~/.claude/CLAUDE.md，把用户人格设定带进 | `cwd='/tmp'` + `--setting-sources ""` 双保险 |
| auto-mode 分类器（haiku） | 每次调用先跑 haiku 分类，长 CJK 内容易慢 | 实测 effort low 后单次完整 60s 可接受 |
| extended thinking 默认开 | medium effort 让 N=60 推理 200s+ | `--effort low`, JSON 输出仍正确 |
| argv 超过 ~8k chars 异常 | `--system-prompt <4k 字符>` + 长 user argv 整体 hang | system 用 `--system-prompt-file`, user 用 stdin |
| Session 文件污染 | 每次调用写 `~/.claude/projects/.../sessions/` | `--no-session-persistence` |
| `--bare` 不读 OAuth | bare 模式必须 ANTHROPIC_API_KEY，订阅失效 | 不能用 bare |
| `--dangerously-skip-permissions` 在 root 下被拒 | 用 `--permission-mode bypassPermissions` 不行 | 不用此 flag，靠 `--tools ""` 自然无权限决策 |

### 2.5 Rate limit / 配额估算

- Max 订阅: 5h 滚动窗口，具体 message 数官方不公开
- 自用一天 2-4 次推荐 + refine ≈ 5-10 messages，远低于上限
- 接 OpenClaw 多人后需重估（不在本次范围）

---

## 3. 方案设计

### 3.1 整体架构

新增 `chisha/llm_providers/` 目录，把现在挤在 `llm_client.py` 里的三个 provider 拆开：

```
chisha/
├── llm_client.py              # 对外入口 + provider routing
└── llm_providers/
    ├── __init__.py
    ├── anthropic_api.py       # ANTHROPIC_API_KEY 路径（原 _call_anthropic）
    ├── openrouter.py          # OPENROUTER_API_KEY 路径（原 _call_openrouter）
    └── claude_code_cli.py     # ⭐ 新增：subprocess 调 claude -p
```

每个 provider 暴露统一签名：

```python
def call(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    cache_system: bool = False,    # provider 内部自行决定如何 cache
) -> str:
    """返回 LLM 文本输出. 错误抛 LLMProviderError."""
```

### 3.2 Provider 选择策略

**配置方式**：profile.yaml 新增 `llm` 段（也可被环境变量覆盖）：

```yaml
llm:
  # 显式选定 provider. 不写或 "auto" 时按下面 fallback 顺序自动选
  provider: auto                # auto | claude_code_cli | anthropic | openrouter

  # 各 provider 模型(可选, 不写用各自默认)
  model:
    claude_code_cli: sonnet     # 订阅版只能用 alias
    anthropic: claude-sonnet-4-6
    openrouter: anthropic/claude-sonnet-4.6
```

**环境变量优先级**（高 → 低）：
1. `CHISHA_LLM_PROVIDER=<name>` — 显式强制 provider
2. profile.yaml `llm.provider`（非 auto 时）
3. auto-detect：
   - 有 `ANTHROPIC_API_KEY` → anthropic（保留原行为优先级，因为这是"显式声明用 API 调"的信号；适合跑 eval）
   - claude CLI 可用 + 已登录订阅 → claude_code_cli
   - 有 `OPENROUTER_API_KEY` → openrouter
   - 全无 → raise

**自动检测逻辑**（`_detect_claude_code_cli`）：
```python
def _detect_claude_code_cli() -> bool:
    if not shutil.which("claude"):
        return False
    try:
        r = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return False
        info = json.loads(r.stdout)
        return bool(info.get("loggedIn")) and info.get("apiProvider") == "firstParty"
    except Exception:
        return False
```

⚠️ auto-detect 检测开销 ~500ms（`claude auth status` 启动 node 进程）。**缓存到 module-level**，进程内只检一次。

### 3.3 claude_code_cli provider 详细实现

```python
"""chisha/llm_providers/claude_code_cli.py — Claude Code CLI subprocess provider.

复用本机 Claude Code 订阅额度调 LLM. 通过 `claude -p` 子进程实现.
关键设计:
- 7 个 flag 隔离 Claude Code 默认行为 (见 spec §2.4)
- system 通过临时文件传 (--system-prompt-file), user 通过 stdin
- 临时文件用 tempfile + 自动清理
- cwd='/tmp' 避免读 chisha 项目的 CLAUDE.md
"""
import json, os, shutil, subprocess, tempfile, time
from pathlib import Path


CLAUDE_BIN = shutil.which("claude") or "claude"
_DEFAULT_MODEL = "sonnet"
_DEFAULT_TIMEOUT = 180  # N=60 实测 60s, 留 3x 缓冲


class CCCLIError(Exception):
    """Claude Code CLI 调用失败"""


def call(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,        # 兼容签名, CLI 不直接支持 max_tokens, 忽略
    temperature: float = 0.0,      # 同上, CLI 不暴露 temperature
    cache_system: bool = False,    # 同上, 订阅 cache 自动管理
    timeout_sec: int = _DEFAULT_TIMEOUT,
    effort: str = "low",
) -> str:
    if not _check_cli():
        raise CCCLIError("claude CLI 不可用或未登录订阅")

    # system_prompt 走临时文件
    sys_tmp = None
    if system:
        sys_tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False,
            prefix="chisha_sys_", encoding="utf-8",
        )
        sys_tmp.write(system)
        sys_tmp.close()

    try:
        cmd = [
            CLAUDE_BIN, "-p",
            "--model", model or _DEFAULT_MODEL,
            "--effort", effort,
            "--output-format", "json",
            "--disable-slash-commands",
            "--setting-sources", "",
            "--no-session-persistence",
            "--tools", "",
            "--input-format", "text",
        ]
        if sys_tmp:
            cmd += ["--system-prompt-file", sys_tmp.name]

        # cwd='/tmp' 防读 chisha 的 CLAUDE.md; env 清掉 CLAUDE_CODE_* 干扰
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_")}

        t0 = time.time()
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            cwd="/tmp", env=env, timeout=timeout_sec,
        )
        elapsed = time.time() - t0

        if proc.returncode != 0:
            raise CCCLIError(
                f"claude exit={proc.returncode} stderr={proc.stderr[:300]}"
            )

        # stdout 第一行 JSON 是 result; 后续可能有 trailing newlines
        result_line = next(
            (l for l in proc.stdout.splitlines() if l.startswith("{")),
            None,
        )
        if not result_line:
            raise CCCLIError(f"claude 输出无 JSON: {proc.stdout[:300]}")
        data = json.loads(result_line)
        if data.get("is_error"):
            raise CCCLIError(
                f"claude is_error=True: {data.get('result','?')[:300]}"
            )

        # 可选: 打印观测信息 (cost / tokens / 延迟)
        usage = data.get("usage") or {}
        print(
            f"  [llm cc-cli] elapsed={elapsed:.1f}s "
            f"api_ms={data.get('duration_api_ms','?')} "
            f"cost_usd={data.get('total_cost_usd', 0):.4f} "
            f"out_tok={usage.get('output_tokens','?')}"
        )

        return data.get("result", "")

    except subprocess.TimeoutExpired:
        raise CCCLIError(f"claude 超时 {timeout_sec}s")
    finally:
        if sys_tmp:
            try: os.unlink(sys_tmp.name)
            except OSError: pass


_cli_check_cache: bool | None = None


def _check_cli() -> bool:
    global _cli_check_cache
    if _cli_check_cache is not None:
        return _cli_check_cache
    if not shutil.which("claude"):
        _cli_check_cache = False
        return False
    try:
        r = subprocess.run(
            [CLAUDE_BIN, "auth", "status"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            _cli_check_cache = False
            return False
        info = json.loads(r.stdout)
        _cli_check_cache = (
            bool(info.get("loggedIn")) and info.get("apiProvider") == "firstParty"
        )
        return _cli_check_cache
    except Exception:
        _cli_check_cache = False
        return False


def reset_cli_check_cache() -> None:
    """测试用: 清掉单进程 cache."""
    global _cli_check_cache
    _cli_check_cache = None


def is_available() -> bool:
    return _check_cli()
```

### 3.4 llm_client.py 重构

`call_text()` 改为薄路由层：

```python
"""chisha/llm_client.py — LLM 调用统一入口. provider 选择 + 路由."""
import os
from pathlib import Path
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

from chisha.llm_providers import anthropic_api, openrouter, claude_code_cli


# === provider 选择 ===

_PROVIDER_NAMES = {"anthropic", "openrouter", "claude_code_cli"}


def _resolve_provider(profile_llm: dict | None = None) -> str:
    """返回最终用哪个 provider. 优先级: env > profile > auto."""
    # 1. 环境变量强制
    env = os.environ.get("CHISHA_LLM_PROVIDER")
    if env:
        env = env.strip()
        if env not in _PROVIDER_NAMES:
            raise ValueError(f"未知 CHISHA_LLM_PROVIDER={env}")
        return env

    # 2. profile 配置
    if profile_llm:
        p = (profile_llm.get("provider") or "auto").strip()
        if p != "auto":
            if p not in _PROVIDER_NAMES:
                raise ValueError(f"未知 profile.llm.provider={p}")
            return p

    # 3. auto-detect
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if claude_code_cli.is_available():
        return "claude_code_cli"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    raise RuntimeError(
        "无可用 LLM provider: 设 ANTHROPIC_API_KEY / OPENROUTER_API_KEY, "
        "或安装并登录 Claude Code (claude auth login)"
    )


def _resolve_model(provider: str, model: str | None,
                    profile_llm: dict | None) -> str | None:
    """显式 model 参数 > profile.model.<provider> > provider 默认."""
    if model:
        return model
    if profile_llm:
        m = (profile_llm.get("model") or {}).get(provider)
        if m:
            return m
    return None


def call_text(
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: str | None = None,
    cache_system: bool = False,
    profile_llm: dict | None = None,
) -> str:
    """LLM 调用入口."""
    provider = _resolve_provider(profile_llm)
    final_model = _resolve_model(provider, model, profile_llm)
    impl = {
        "anthropic": anthropic_api.call,
        "openrouter": openrouter.call,
        "claude_code_cli": claude_code_cli.call,
    }[provider]
    return impl(
        prompt, system=system, model=final_model,
        max_tokens=max_tokens, temperature=temperature,
        cache_system=cache_system,
    )


def has_llm_key() -> bool:
    """兼容老 API: 是否有任何 provider 可用."""
    try:
        _resolve_provider(None)
        return True
    except RuntimeError:
        return False
```

### 3.5 调用方改动（最小化）

`rerank.py` 调 `call_text()` 的地方加一个 kwarg：

```python
# rerank.py _llm_rerank() 内
from chisha.llm_client import call_text

profile_llm = profile.get("llm")     # 顶层 profile.yaml.llm 段
out = call_text(
    user_msg,
    system=system_prompt, cache_system=True,
    max_tokens=2048, temperature=0.0,
    model=model,
    profile_llm=profile_llm,         # ⭐ 新增
)
```

`rerank()` 的 `model` 参数保留（显式覆盖优先级最高）；调用栈往上 `_recommend_meal_v2 → rerank` 把 profile 透传下来。

`reason.py`（V1 reason 写作路径）同理。

### 3.6 profile.yaml 配置示例

```yaml
# 默认配置 (auto-detect)
llm:
  provider: auto

# 用户场景 A: 自用本机, Max 订阅
# (不写也行, auto 会选到 claude_code_cli 因为我没 ANTHROPIC_API_KEY)

# 用户场景 B: 跑 eval, 想精确计费
llm:
  provider: anthropic
  model:
    anthropic: claude-sonnet-4-6

# 用户场景 C: 分发给没订阅的用户, 走 OpenRouter
llm:
  provider: openrouter
  model:
    openrouter: anthropic/claude-sonnet-4.6
```

---

## 4. 测试设计

### 4.1 单测（pytest, 无网络）

**`tests/test_llm_provider_selection.py`** — provider 路由逻辑：

| 测试 | 输入 | 期望 |
|---|---|---|
| env override 强制 | `CHISHA_LLM_PROVIDER=openrouter` + profile=anthropic | resolve → openrouter |
| profile 选择 | profile.llm.provider=anthropic, 无 env | resolve → anthropic |
| profile=auto + 有 ANTHROPIC_API_KEY | env=ANTHROPIC_API_KEY | resolve → anthropic |
| profile=auto + 无 key + CLI 可用 | mock is_available=True | resolve → claude_code_cli |
| profile=auto + 无 key + 无 CLI + OPENROUTER | mock is_available=False, OPENROUTER_API_KEY | resolve → openrouter |
| 全无可用 | 全 mock 失败 | RuntimeError |
| 无效 provider 名 | CHISHA_LLM_PROVIDER=foo | ValueError |
| model 优先级 | 显式 model="m1", profile.model.anthropic="m2" | 显式 "m1" 胜 |

**`tests/test_claude_code_cli.py`** — claude_code_cli provider 行为（subprocess mock）：

| 测试 | mock subprocess.run | 期望 |
|---|---|---|
| 成功调用 | returncode=0, stdout 含 valid JSON result | 返回 result 字符串 |
| 非零 exit | returncode=2, stderr="boom" | CCCLIError 含 stderr |
| 输出无 JSON | stdout="plain text" | CCCLIError |
| is_error=True 在 JSON 里 | result.is_error=True | CCCLIError |
| 超时 | TimeoutExpired | CCCLIError 含 timeout |
| 临时文件清理 | 调用后看 tmp 文件不存在 | 文件已删 |
| 命令拼接 | mock 截获 cmd | 含全部 7 个 flag |
| `_check_cli` cache | 第二次调用无 subprocess | 用 cache |

### 4.2 集成测试（需 claude CLI + 订阅, opt-in）

**`tests/integration/test_claude_code_cli_e2e.py`** — 用 pytest marker 标注 `@pytest.mark.requires_claude_cli`，CI 跳过，本机手动跑：

| 测试 | 内容 |
|---|---|
| 短 ping | "回声测试" 输入 → 含"回声测试"字样的回复 |
| 真 rerank 调用 | 用 fixture top10 combos 跑 build_user_message + claude_code_cli.call → 解析为 valid JSON candidates list |
| effort 控制 | model=sonnet, effort=low → duration < 90s（N=10 时） |

### 4.3 e2e 验证

跑 `python -m chisha.cli recommend lunch`（或 debug_server）三组对照：
1. `CHISHA_LLM_PROVIDER=claude_code_cli` — 复用订阅
2. `CHISHA_LLM_PROVIDER=anthropic` + 有 ANTHROPIC_API_KEY — 直连
3. `CHISHA_LLM_PROVIDER=openrouter` + 有 OPENROUTER_API_KEY — OR

每组验证：
- 5 条 candidates 出来
- combo_index 全部合法
- exploit/explore 段位正确
- 落点 metric 正常打印
- 三组输出在"top-3 集合"上 Jaccard ≥ 0.5（粗略一致性）

### 4.4 性能基线

记录到 `docs/DECISIONS.md` D-047 里：
- claude_code_cli N=60 effort low 单次延迟（实测 60s）
- anthropic API N=60 单次延迟（应 < 15s, 没有 thinking）
- 两者输出质量是否有可感差异

---

## 5. 安全检查项（Codex review 重点）

| 项 | 检查 |
|---|---|
| 命令注入 | `subprocess.run(cmd_list, ...)` 用 list 形式，所有变量参数 (model/effort) 进 list 而非字符串拼接。**system / user 内容不进 argv**，避免 shell 解析 |
| 临时文件泄露 | `tempfile.NamedTemporaryFile(delete=False)` + `finally: os.unlink()`；不写 sensitive 内容（system prompt 是 chisha 公开 prompt, OK） |
| 环境变量污染 | 显式过滤 `CLAUDE_CODE_*` 环境变量；不传 `ANTHROPIC_API_KEY`（订阅路径不需要） |
| API key 误用 | claude_code_cli 不读 ANTHROPIC_API_KEY，否则可能被 Claude Code 默认走 API key 而不是 OAuth |
| Rate limit 处理 | claude CLI 自身处理 rate limit 报错（stderr）；我们的 wrapper 把 stderr 包进 CCCLIError，上层 rerank.py 已有 fallback 到规则路径 |
| 错误信息泄露 | CCCLIError 截断 stderr 到 300 字符，避免泄露 |
| concurrent safety | OpenClaw 和 Claude Code 都用 `~/.claude/`，并发调用可能冲突。本期：自用阶段单进程，不并发，OK；接入 OpenClaw 时单独验证 |
| timeout 默认 | 180s 给 N=60 留 3x buffer；超时清理临时文件 |
| 缓存正确性 | `_check_cli` 模块级 cache，进程重启失效。测试时用 `reset_cli_check_cache()` 清掉 |

---

## 6. 实施步骤（高层 — 详细见 plan.md）

1. 写单测 → 跑 → 红
2. 实现 `claude_code_cli.py` provider
3. 实现 `llm_providers/anthropic_api.py` + `openrouter.py`（抽 `llm_client.py` 已有代码）
4. 重构 `llm_client.py` 为薄路由层
5. 加 profile.yaml `llm` 段 + 文档
6. rerank.py / reason.py 调用点传 `profile_llm`
7. 跑全测 + e2e 三组对照
8. Codex review + 修
9. 提交 D-047

---

## 7. 失败模式 & fallback 链路

每个 provider 失败时（CCCLIError / API timeout / quota exceeded）：
1. `llm_client.call_text()` 不做 cross-provider fallback —— 保持 fail-fast，让上层决策
2. `rerank.py` 的 `_llm_rerank()` 已有 try/except → 落入 `fallback_rerank()` 规则路径
3. 错误信息打印到 stderr，方便 debug，但不阻塞推荐主流程

不做 cross-provider fallback 的原因：
- 配置语义清晰（"我说要用订阅就用订阅，挂了就规则兜底"）
- 否则"我配 openrouter 但实际跑订阅"会让 cost 追踪混乱
- 用户场景 B（跑 eval）不希望被悄悄切到便宜模型导致数据不可比

---

## 8. 已知遗留 / 后续工作

1. **订阅 rate limit 监测**：自用阶段不会撞上限；接 OpenClaw 后需加 metric
2. **effort 配置化**：当前硬编 `low`，未来如果想 explore "high effort 是否质量更好" 可加 `llm.effort` 字段
3. **多 provider 并行 eval**：rerank_eval (D-046 路线图里的) 可以一次跑三 provider 对比；先把基础设施搭好
4. **Phase 2 SDK 注入点**（D-038 计划）：当 chisha 被外部 agent 当 Skill 调用时，agent 传自己的 LLM closure 覆盖默认 — 这次不动，但抽象保留扩展点

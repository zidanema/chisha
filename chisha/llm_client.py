"""LLM 调用入口 (D-047).

provider 路由 + 选择策略:
- env CHISHA_LLM_PROVIDER 强制 > profile.llm.provider 显式 > auto-detect
- auto 顺序: ANTHROPIC_API_KEY > claude_code_cli 订阅 > OPENROUTER_API_KEY
- 显式选定 (env/profile) 时检查可用性, 不可用直接 RuntimeError 给清晰错误

D-047 接口:
- call_text 返回 dict (而非 str, 破坏性变更). 字段:
  - type ∈ {"text", "tool_use"}
  - text 时: content / stop_reason / usage / model / raw_text
  - tool_use 时: tool_name / tool_input / stop_reason / usage / model / raw_text
- 加 tools / tool_choice / json_mode 参数支持 forced schema. 仅 anthropic
  / openrouter 两个 provider 真支持 tool_use; claude_code_cli 走 text 路径,
  传 tools 会抛 NotImplementedError.
- OR provider lock: order=Anthropic + allow_fallbacks=False 防 Bedrock 路由
  (不加 require_parameters, opus+tools 会触发 404).

具体 provider 实现见 chisha/llm_providers/.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from chisha.install_root import install_root as _install_root  # T-DIST-01 B.1
_REPO_ROOT = _install_root()
# dev: repo root .env; wheel: chisha/ 包内无 .env, load_dotenv 静默 no-op (走环境变量).
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
    """决定走哪个 provider. env > profile > auto.

    显式选定 (env/profile) 时检查可用性, 不可用直接 RuntimeError.
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
        pv_raw = profile_llm.get("provider") or "auto"
        pv = pv_raw.strip()
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


_PROVIDER_MODULES = {
    "anthropic": anthropic_api,
    "openrouter": openrouter,
    "claude_code_cli": claude_code_cli,
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
    json_mode: bool = False,
    tools: Optional[list[dict]] = None,
    tool_choice: Optional[dict] = None,
) -> dict:
    """单次 LLM 调用, 返回 dict (D-047 破坏性变更).

    Args:
        prompt: user 消息
        model: 显式 model 覆盖 (优先级最高)
        system / cache_system / max_tokens / temperature: 透传 provider
        profile_llm: 从 profile.yaml 读到的 'llm' 段
        json_mode: True 时启用 response_format json_object (OR) — 实测 OR 上
            "accepted but not enforced", 真正强制 JSON 输出请用 tools + tool_choice.
        tools: tool schema 列表, 见 anthropic / OR 文档.
        tool_choice: 强制特定 tool 调用, 例如 {"type":"tool","name":"X"}
            (Anthropic 原生格式), provider 内部会自动转 OR 的 OpenAI 格式.
            注意: forced tool_choice 与 extended thinking 不兼容.

    Returns:
        dict, 字段:
        - type: "text" | "tool_use"
        - text 时: content, stop_reason, usage, model, raw_text
        - tool_use 时: tool_name, tool_input, stop_reason, usage, model, raw_text
    """
    provider = _resolve_provider(profile_llm)
    final_model = _resolve_model(provider, model, profile_llm)
    # observability: 让用户看见实际走哪路, 防止 .env 残留 key 偷偷打掉订阅
    print(f"  [llm] provider={provider} model={final_model or '(default)'}")
    # 动态属性查找, 让 unittest.mock.patch(模块.call) 能生效
    return _PROVIDER_MODULES[provider].call(
        prompt,
        system=system,
        model=final_model,
        max_tokens=max_tokens,
        temperature=temperature,
        cache_system=cache_system,
        json_mode=json_mode,
        tools=tools,
        tool_choice=tool_choice,
    )


def has_llm_key() -> bool:
    """兼容老 API: 是否有任何可用 provider."""
    try:
        _resolve_provider(None)
        return True
    except RuntimeError:
        return False

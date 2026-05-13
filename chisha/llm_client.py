"""LLM 抽象 (Phase 1 of D-038).

provider auto-detect:
- 有 ANTHROPIC_API_KEY → Anthropic 直连 (claude-sonnet-4-6)
- 否则有 OPENROUTER_API_KEY → OpenRouter (anthropic/claude-sonnet-4.6)
- 都没有 → 调用方 try/except 接住, 退化到 rule fallback

调用方 (reason.py / rerank.py) 不感知 provider, 只调 call_text(prompt, ...).

未来 Phase 2 (chisha 被外部 agent 当 Skill 调用时): recommend_meal 加
llm_call: Callable | None 注入点, agent 传自己的 LLM closure 覆盖默认。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# .env load (与 llm_client_openrouter 同源)
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")


# Anthropic 直连模型 (短名)
_ANTHROPIC_MODEL = "claude-sonnet-4-6"
# OpenRouter 模型 (命名空间形式)
_OPENROUTER_MODEL = "anthropic/claude-sonnet-4.6"


def _has_anthropic_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _has_openrouter_key() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def call_text(
    prompt: str,
    *,
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: Optional[str] = None,
    cache_system: bool = False,
) -> str:
    """单次 LLM 调用, 返回纯文本.

    Args:
        model: 显式覆盖. None 时按 provider 取默认 (Anthropic short / OR 命名空间).
        cache_system: True 时把 system block 打上 ephemeral cache_control
            (Anthropic prompt caching). 仅 Anthropic 直连真正生效, OpenRouter
            兼容路径忽略 (它的 cache 由 OR 自行管理, 用 system 作前缀已经足够).
    """
    if _has_anthropic_key():
        return _call_anthropic(prompt, model=model or _ANTHROPIC_MODEL,
                                max_tokens=max_tokens, temperature=temperature,
                                system=system, cache_system=cache_system)
    if _has_openrouter_key():
        return _call_openrouter(prompt, model=model or _OPENROUTER_MODEL,
                                 max_tokens=max_tokens, temperature=temperature,
                                 system=system)
    raise RuntimeError(
        "未配置 ANTHROPIC_API_KEY 或 OPENROUTER_API_KEY, 无法调 LLM"
    )


def _call_anthropic(prompt: str, *, model: str, max_tokens: int,
                    temperature: float, system: Optional[str],
                    cache_system: bool = False) -> str:
    import anthropic
    client = anthropic.Anthropic()
    kwargs: dict = dict(
        model=model,
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


def _call_openrouter(prompt: str, *, model: str, max_tokens: int,
                      temperature: float, system: Optional[str]) -> str:
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
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        extra_headers={
            "HTTP-Referer": "https://github.com/chisha-private",
            "X-Title": "chisha recommend",
        },
    )
    return resp.choices[0].message.content or ""


def has_llm_key() -> bool:
    """供调用方决定是否走 LLM (代替原来直接 os.environ 检查 ANTHROPIC)."""
    return _has_anthropic_key() or _has_openrouter_key()

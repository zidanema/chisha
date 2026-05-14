"""OpenRouter (OPENROUTER_API_KEY) provider (D-047)."""
from __future__ import annotations

import os
from typing import Optional


_DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"


class OpenRouterProviderError(Exception):
    """OpenRouter provider 调用失败"""


def call(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    cache_system: bool = False,  # OR 自管 cache, 忽略
) -> str:
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
    return bool(os.environ.get("OPENROUTER_API_KEY"))

"""Anthropic 直连 (ANTHROPIC_API_KEY) provider (D-047)."""
from __future__ import annotations

import os
from typing import Optional


_DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicProviderError(Exception):
    """Anthropic provider 调用失败"""


def call(
    prompt: str,
    *,
    system: Optional[str] = None,
    model: Optional[str] = None,
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
    return bool(os.environ.get("ANTHROPIC_API_KEY"))

"""LLM 抽象（V1 只支持 Anthropic）."""
from __future__ import annotations

import os
from typing import Optional

import anthropic


_DEFAULT_MODEL = "claude-sonnet-4-6"


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def call_text(
    prompt: str,
    *,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: Optional[str] = None,
) -> str:
    """单次 LLM 调用，返回纯文本."""
    client = _client()
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return resp.content[0].text

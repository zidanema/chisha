"""Anthropic 直连 (ANTHROPIC_API_KEY) provider (D-047).

D-047 接口: call() 返回 dict, 见 chisha.llm_client.call_text docstring.
支持 tools / tool_choice / cache_system.
"""
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
    json_mode: bool = False,
    tools: Optional[list[dict]] = None,
    tool_choice: Optional[dict] = None,
) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    final_model = model or _DEFAULT_MODEL
    kwargs: dict = dict(
        model=final_model,
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
    if tools:
        kwargs["tools"] = [_to_anthropic_tool(t) for t in tools]
        if tool_choice:
            kwargs["tool_choice"] = _to_anthropic_tool_choice(tool_choice)
    # json_mode 在 Anthropic 直连暂不真启用 (output_config shape 跨版本不稳),
    # 调用方应改用 tools + tool_choice 强制 schema. 见 D-047.
    _ = json_mode
    resp = client.messages.create(**kwargs)
    return _parse_response(resp, model=final_model)


def is_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# ─────────────────────────── adapters ───────────────────────────

def _to_anthropic_tool(t: dict) -> dict:
    """OpenAI 格式 -> Anthropic 原生格式."""
    if "input_schema" in t:
        return t  # already anthropic
    fn = t.get("function", {})
    return {
        "name": fn.get("name", t.get("name", "")),
        "description": fn.get("description", ""),
        "input_schema": fn.get("parameters", {}),
    }


def _to_anthropic_tool_choice(c: dict) -> dict:
    """OpenAI -> Anthropic tool_choice 格式."""
    if c.get("type") == "function":
        return {"type": "tool", "name": c["function"]["name"]}
    return c


# ─────────────────────────── parser ───────────────────────────

def _parse_response(resp, *, model: str) -> dict:
    """Anthropic SDK Message -> 统一 dict (text / tool_use)."""
    stop = resp.stop_reason
    usage = {
        "prompt_tokens": resp.usage.input_tokens,
        "completion_tokens": resp.usage.output_tokens,
        "cached_tokens": getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
    }
    # 找 tool_use block (forced 模式下应该是唯一 content block)
    for block in resp.content:
        if block.type == "tool_use":
            return {
                "type": "tool_use",
                "tool_name": block.name,
                "tool_input": block.input,
                "stop_reason": stop,
                "usage": usage,
                "model": model,
                "raw_text": "",
            }
    # 否则取第一个 text block
    text = ""
    for block in resp.content:
        if block.type == "text":
            text = block.text
            break
    return {
        "type": "text",
        "content": text,
        "stop_reason": stop,
        "usage": usage,
        "model": model,
        "raw_text": text,
    }

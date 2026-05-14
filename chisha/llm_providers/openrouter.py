"""OpenRouter (OPENROUTER_API_KEY) provider (D-047).

D-047 接口: call() 返回 dict, 见 chisha.llm_client.call_text docstring.
支持 tools / tool_choice / cache_system (在 anthropic/* 路由透传 ephemeral).

OR provider lock (避免被路由到 Bedrock / Google 不支持 tool_use 的 endpoint):
- order=["Anthropic"]
- allow_fallbacks=False
**不加 require_parameters=True** — 实测 opus+tools 组合下会触发 404
"No endpoints found" (OR 路由元数据滞后, 误判 Anthropic 不支持).
"""
from __future__ import annotations

import json
import os
from typing import Optional


_DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"

_OR_PROVIDER_LOCK = {
    "order": ["Anthropic"],
    "allow_fallbacks": False,
}


class OpenRouterProviderError(Exception):
    """OpenRouter provider 调用失败"""


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
    from openai import OpenAI

    base_url = os.environ.get(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"], base_url=base_url
    )
    final_model = model or _DEFAULT_MODEL
    messages: list[dict] = []
    if system:
        if cache_system:
            # D-047 V5 实测: OR 转发 anthropic/* 时透传 system content 数组里
            # cache_control, Anthropic ephemeral cache 真生效 (二次调用 cached=3844).
            messages.append({"role": "system", "content": [{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }]})
        else:
            messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    kwargs: dict = dict(
        model=final_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        extra_headers={
            "HTTP-Referer": "https://github.com/chisha-private",
            "X-Title": "chisha recommend",
        },
        extra_body={"provider": _OR_PROVIDER_LOCK},
    )
    if json_mode and not tools:
        kwargs["response_format"] = {"type": "json_object"}
    if tools:
        kwargs["tools"] = [_to_openai_tool(t) for t in tools]
        if tool_choice:
            kwargs["tool_choice"] = _to_openai_tool_choice(tool_choice)
    resp = client.chat.completions.create(**kwargs)
    return _parse_response(resp, model=final_model)


def is_available() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


# ─────────────────────────── adapters ───────────────────────────

def _to_openai_tool(t: dict) -> dict:
    """Anthropic -> OpenAI tool 格式."""
    if t.get("type") == "function":
        return t  # already openai
    return {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t["input_schema"],
        },
    }


def _to_openai_tool_choice(c: dict) -> dict:
    """Anthropic -> OpenAI tool_choice 格式."""
    if c.get("type") == "tool":
        return {"type": "function", "function": {"name": c["name"]}}
    return c


# ─────────────────────────── parser ───────────────────────────

def _parse_response(resp, *, model: str) -> dict:
    """OpenAI SDK ChatCompletion (走 OR) -> 统一 dict."""
    choice = resp.choices[0]
    msg = choice.message
    finish = choice.finish_reason
    u = resp.usage.model_dump() if hasattr(resp.usage, "model_dump") else dict(resp.usage)
    pdetails = u.get("prompt_tokens_details", {}) or {}
    usage = {
        "prompt_tokens": u.get("prompt_tokens", 0),
        "completion_tokens": u.get("completion_tokens", 0),
        "cached_tokens": pdetails.get("cached_tokens", 0) or 0,
        "cache_write_tokens": pdetails.get("cache_write_tokens", 0) or 0,
        "cost": u.get("cost", 0),
    }
    # tool_calls 优先
    if msg.tool_calls:
        tc = msg.tool_calls[0]
        try:
            tool_input = json.loads(tc.function.arguments)
        except Exception:
            tool_input = None
        return {
            "type": "tool_use",
            "tool_name": tc.function.name,
            "tool_input": tool_input,
            "stop_reason": finish,  # OR 通常是 "tool_calls" 或 "stop"
            "usage": usage,
            "model": model,
            "raw_text": tc.function.arguments or "",
        }
    text = msg.content or ""
    return {
        "type": "text",
        "content": text,
        "stop_reason": finish,
        "usage": usage,
        "model": model,
        "raw_text": text,
    }

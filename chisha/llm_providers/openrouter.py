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
            "HTTP-Referer": "https://github.com/zidanema/chisha",
            "X-Title": "chisha recommend",
        },
    )
    # provider lock 只对 anthropic/* 生效 — 强制走 Anthropic 自家 endpoint 防被
    # 路由到 Bedrock/Google 等不支持 tool_use 的 endpoint. 用 deepseek/* 等其他
    # 厂商 model 时上这个 lock 会 "No endpoints found", 走 OR 默认路由即可.
    if final_model.startswith("anthropic/"):
        kwargs["extra_body"] = {"provider": _OR_PROVIDER_LOCK}
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

def _dump_or_error(resp) -> str:
    """挖出 OR 异常返回里能解释根因的字段, 返回 JSON 字符串供 fallback_reason 引用.

    OR 在上游报错时常见 shape:
      {"error": {"message": "...", "code": "...", "metadata": {...}}}
    OpenAI SDK 会把这些非 ChatCompletion schema 字段塞到 BaseModel.model_extra.
    """
    payload: dict = {}
    for attr in ("error", "model_extra"):
        v = getattr(resp, attr, None)
        if v:
            payload[attr] = v if isinstance(v, dict) else str(v)
    try:
        full = resp.model_dump(exclude_none=False)
        # 只截前 400 字符以防 raw_text 过长撑爆 fallback_reason
        payload["raw"] = full
    except Exception:
        payload["raw"] = str(resp)[:500]
    return json.dumps(payload, ensure_ascii=False, default=str)[:400]


def _parse_response(resp, *, model: str) -> dict:
    """OpenAI SDK ChatCompletion (走 OR) -> 统一 dict.

    D-089-S6 fix: OR 在上游 provider 报错 / 限流 / 路由失败时, SDK 不抛异常,
    而是返回一个 choices=None 的 ChatCompletion 对象 (top-level 带 error 字段).
    必须显式检查并把 OR 真实错误暴露成 OpenRouterProviderError, 让上游
    rerank fallback_reason 能看到 "OR returned no choices: <error>",
    而不是吞成无意义的 "TypeError: NoneType subscript".
    """
    # D-089-S6 fix: OR 在上游 provider 报错 / 限流 / 路由失败时, SDK 不抛异常,
    # 而是返回一个 choices=None (或 usage=None) 的 ChatCompletion 对象, top-level
    # 带 error 字段. 必须显式 raise OpenRouterProviderError 让上游 fallback_reason
    # 看到 "OR returned no choices: <error>", 而不是吞成无意义的 "TypeError".
    if not getattr(resp, "choices", None):
        raise OpenRouterProviderError(
            f"OR returned no choices (model={model}): {_dump_or_error(resp)}"
        )
    choice = resp.choices[0]
    msg = choice.message
    finish = choice.finish_reason
    # usage 可能 None (某些 OR 异常返回路径会丢 usage). 不 raise — 这是 soft signal,
    # 不影响业务结果, 落 0 兜底; 但通过 fallback_reason 链路也能感知.
    u_obj = getattr(resp, "usage", None)
    if u_obj is None:
        u = {}
    elif hasattr(u_obj, "model_dump"):
        u = u_obj.model_dump()
    else:
        try:
            u = dict(u_obj)
        except Exception:
            u = {}
    pdetails = u.get("prompt_tokens_details") or {}
    if not isinstance(pdetails, dict):
        pdetails = {}
    usage = {
        "prompt_tokens": u.get("prompt_tokens", 0) or 0,
        "completion_tokens": u.get("completion_tokens", 0) or 0,
        "cached_tokens": pdetails.get("cached_tokens", 0) or 0,
        "cache_write_tokens": pdetails.get("cache_write_tokens", 0) or 0,
        "cost": u.get("cost", 0) or 0,
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
            # finish_reason 可能是 "tool_calls" (主流) 或 "stop" (某些路由
            # 在 forced tool_choice 下返回, D-048 MAJOR 5). 真信号在 type +
            # tool_name + tool_input, rerank.py 不再硬断言 stop string.
            "stop_reason": finish,
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

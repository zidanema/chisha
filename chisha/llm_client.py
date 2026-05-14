"""LLM 抽象 (Phase 1 of D-038, D-047 加 tool_use 强制 schema 路径).

provider auto-detect:
- 有 ANTHROPIC_API_KEY → Anthropic 直连 (claude-sonnet-4-6)
- 否则有 OPENROUTER_API_KEY → OpenRouter (anthropic/claude-sonnet-4.6)
- 都没有 → 调用方 try/except 接住, 退化到 rule fallback

调用方 (reason.py / rerank.py / feedback.py) 不感知 provider, 只调 call_text(prompt, ...).

D-047 接口变化:
- call_text 返回 dict 而不是 str. 老调用取 ret["content"], rerank 取 ret["tool_input"].
- 加 tools / tool_choice / cache_system_or_path 三个参数支持 forced schema.
- OR 调用强制 provider.order=Anthropic + require_parameters=True 防 Bedrock 等
  不支持 tool_use 的 provider 路由.

未来 Phase 2 (chisha 被外部 agent 当 Skill 调用时): recommend_meal 加
llm_call: Callable | None 注入点, agent 传自己的 LLM closure 覆盖默认。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# .env load (与 llm_client_openrouter 同源)
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")


# Anthropic 直连模型 (短名)
_ANTHROPIC_MODEL = "claude-sonnet-4-6"
# OpenRouter 模型 (命名空间形式)
_OPENROUTER_MODEL = "anthropic/claude-sonnet-4.6"

# D-047: OR provider 强制锁 Anthropic 直路, 防止路由到 Bedrock/Google 等.
# allow_fallbacks=False + order=["Anthropic"] 已经足够 — 只走 Anthropic provider,
# 失败也不退化到其他.
# **不要加 require_parameters=True**: 实测在 anthropic/claude-opus-4.7 +
# tools + tool_choice 组合下会触发 OR "No endpoints found" 404 (OR 路由元数据
# 滞后, 误判 Anthropic 不支持). 我们用 tool_use 强约束本身已经强制 schema, 不
# 需要 require_parameters 这层保险.
_OR_PROVIDER_LOCK = {
    "order": ["Anthropic"],
    "allow_fallbacks": False,
}


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
    json_mode: bool = False,
    tools: Optional[list[dict]] = None,
    tool_choice: Optional[dict] = None,
) -> dict:
    """单次 LLM 调用, 返回 dict.

    D-047 接口: 返回 {"type": "text"|"tool_use", ...}, 字段:
    - type: "text" 时有 content / stop_reason
    - type: "tool_use" 时有 tool_name / tool_input / stop_reason
    - 公共字段: usage (含 prompt/completion/cached tokens), model, raw_text (兜底)

    Args:
        model: 显式覆盖. None 时按 provider 取默认 (Anthropic short / OR 命名空间).
        cache_system: True 时把 system block 打上 ephemeral cache_control
            (Anthropic prompt caching). D-047 实测在 OR Anthropic 直路也生效
            (V5 实测: 二次调用 cached=3844 tokens, cost 省 23%).
        json_mode: True 时启用 response_format json_object (OR) 或 output_config
            (Anthropic 直连). 实测 OR 上是 "accepted but not enforced", 真正强制
            JSON 输出请用 tools + tool_choice (D-047 推荐路径).
        tools: tool schema 列表, 见 anthropic / OR 文档.
        tool_choice: 强制特定 tool 调用, 例如 {"type":"function","function":{"name":"X"}}
            (OR) 或 {"type":"tool","name":"X"} (Anthropic 直连).
            注意: forced tool_choice 与 extended thinking 不兼容, 不要同时启用.
    """
    if _has_anthropic_key():
        return _call_anthropic(prompt, model=model or _ANTHROPIC_MODEL,
                                max_tokens=max_tokens, temperature=temperature,
                                system=system, cache_system=cache_system,
                                json_mode=json_mode,
                                tools=tools, tool_choice=tool_choice)
    if _has_openrouter_key():
        return _call_openrouter(prompt, model=model or _OPENROUTER_MODEL,
                                 max_tokens=max_tokens, temperature=temperature,
                                 system=system, cache_system=cache_system,
                                 json_mode=json_mode,
                                 tools=tools, tool_choice=tool_choice)
    raise RuntimeError(
        "未配置 ANTHROPIC_API_KEY 或 OPENROUTER_API_KEY, 无法调 LLM"
    )


def _call_anthropic(prompt: str, *, model: str, max_tokens: int,
                    temperature: float, system: Optional[str],
                    cache_system: bool = False,
                    json_mode: bool = False,
                    tools: Optional[list[dict]] = None,
                    tool_choice: Optional[dict] = None) -> dict:
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
    if tools:
        # Anthropic 原生 tools 字段格式: [{"name":..., "description":..., "input_schema":...}]
        # 调用方传的可能是 OR 的 OpenAI 格式 {"type":"function","function":{...}}, 自动适配
        kwargs["tools"] = [_to_anthropic_tool(t) for t in tools]
        if tool_choice:
            kwargs["tool_choice"] = _to_anthropic_tool_choice(tool_choice)
    # json_mode 在 Anthropic 直连暂不真实启用 (output_config 字段 shape 跨版本不稳),
    # 调用方应改用 tools + tool_choice 强制 schema. 见 D-047 §2.1.
    _ = json_mode
    resp = client.messages.create(**kwargs)
    return _parse_anthropic_response(resp, model=model)


def _call_openrouter(prompt: str, *, model: str, max_tokens: int,
                      temperature: float, system: Optional[str],
                      cache_system: bool = False,
                      json_mode: bool = False,
                      tools: Optional[list[dict]] = None,
                      tool_choice: Optional[dict] = None) -> dict:
    from openai import OpenAI
    base_url = os.environ.get(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"], base_url=base_url
    )
    messages: list[dict] = []
    if system:
        if cache_system:
            # D-047 V5 实测: OR 转发 anthropic/* 时透传 system content 数组里的
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
        model=model,
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
        # OR 接受 OpenAI 格式 tools/tool_choice; 调用方若传 anthropic 原生格式
        # ({"name", "input_schema"}), 自动适配
        kwargs["tools"] = [_to_openai_tool(t) for t in tools]
        if tool_choice:
            kwargs["tool_choice"] = _to_openai_tool_choice(tool_choice)
    resp = client.chat.completions.create(**kwargs)
    return _parse_openrouter_response(resp, model=model)


# ---------------------------------------------------------------- adapters ---

def _to_anthropic_tool(t: dict) -> dict:
    """OpenAI -> Anthropic tool format."""
    if "input_schema" in t:
        return t  # already anthropic
    fn = t.get("function", {})
    return {
        "name": fn.get("name", t.get("name", "")),
        "description": fn.get("description", ""),
        "input_schema": fn.get("parameters", {}),
    }


def _to_openai_tool(t: dict) -> dict:
    """Anthropic -> OpenAI tool format."""
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


def _to_anthropic_tool_choice(c: dict) -> dict:
    """OpenAI -> Anthropic tool_choice format."""
    if c.get("type") == "function":
        return {"type": "tool", "name": c["function"]["name"]}
    return c


def _to_openai_tool_choice(c: dict) -> dict:
    """Anthropic -> OpenAI tool_choice format."""
    if c.get("type") == "tool":
        return {"type": "function", "function": {"name": c["name"]}}
    return c


# ---------------------------------------------------------------- parsers ---

def _parse_anthropic_response(resp, model: str) -> dict:
    """Anthropic SDK Message -> 统一 dict."""
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


def _parse_openrouter_response(resp, model: str) -> dict:
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


def has_llm_key() -> bool:
    """供调用方决定是否走 LLM (代替原来直接 os.environ 检查 ANTHROPIC)."""
    return _has_anthropic_key() or _has_openrouter_key()

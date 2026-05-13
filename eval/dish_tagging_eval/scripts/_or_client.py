"""OpenRouter 客户端封装 - 共用给 dual_pipeline / run_eval."""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

import httpx
from dotenv import load_dotenv

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    _HAS_TENACITY = True
except ImportError:
    _HAS_TENACITY = False

    # 简化版重试 decorator: 3 次尝试, 指数退避 2-60s
    def retry(reraise=True, stop=None, wait=None, retry=None):  # noqa
        def deco(fn):
            async def wrapped(*args, **kwargs):
                last_exc = None
                for attempt in range(3):
                    try:
                        return await fn(*args, **kwargs)
                    except Exception as e:
                        last_exc = e
                        if attempt < 2:
                            await asyncio.sleep(min(60, 2 * (2 ** attempt)))
                if last_exc:
                    raise last_exc
            return wrapped
        return deco
    def stop_after_attempt(*a, **k): return None
    def wait_exponential(*a, **k): return None
    def retry_if_exception_type(*a, **k): return None

# 从仓根 .env 加载
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")

if not API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY not set; check .env")


class ORError(Exception):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception_type((httpx.HTTPError, ORError, json.JSONDecodeError)),
)
async def call_model(
    client: httpx.AsyncClient,
    model_id: str,
    prompt_text: str,
    *,
    reasoning_enabled: bool = False,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """单次调用 OpenRouter chat/completions, 返回 {content, latency_ms, usage, cost}."""
    body: dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": 0,
    }
    # 默认关闭 reasoning (打标任务不需要 long CoT, 且 reasoning 把答案放 reasoning_details
    # 字段会导致 content=null 解析失败).
    if not reasoning_enabled:
        # OpenRouter 统一参数: reasoning.enabled=false 或 effort=none
        body["reasoning"] = {"enabled": False}
    t0 = time.time()
    r = await client.post(
        f"{BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/chisha-eval",
            "X-Title": "chisha-dish-tagging-eval",
        },
        json=body,
        timeout=timeout,
    )
    latency_ms = int((time.time() - t0) * 1000)
    if r.status_code >= 400:
        # 5xx + 429 retry, 4xx 其他直接不重试
        if r.status_code in (429, 500, 502, 503, 504):
            raise ORError(f"HTTP {r.status_code}: {r.text[:200]}")
        raise ORError(f"HTTP {r.status_code} (no-retry): {r.text[:400]}")
    data = r.json()
    if "error" in data:
        raise ORError(f"API error: {data['error']}")
    choice = data["choices"][0]
    msg = choice.get("message", {}) or {}
    content = msg.get("content") or ""
    # Fallback: 部分模型 (kimi/glm 等) 把答案放 reasoning_details / reasoning
    if not content:
        details = msg.get("reasoning_details") or []
        for d in details:
            t = d.get("text") if isinstance(d, dict) else None
            if t:
                content += t
        if not content:
            r = msg.get("reasoning")
            if isinstance(r, str):
                content = r
    usage = data.get("usage", {}) or {}
    cost = float(usage.get("cost", 0.0))
    return {
        "content": content,
        "latency_ms": latency_ms,
        "input_tokens": int(usage.get("prompt_tokens", 0)),
        "output_tokens": int(usage.get("completion_tokens", 0)),
        "cost_usd": cost,
        "finish_reason": choice.get("finish_reason"),
    }


_JSON_ARRAY_RE = re.compile(r"\[\s*\{.*\}\s*\]", re.S)


def parse_json_array(text: str) -> list[dict[str, Any]] | None:
    """从模型输出抽 JSON 数组. 容忍 ```json ... ``` 包裹和前后说明文字."""
    if not text:
        return None
    # 去掉 markdown fence
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", s, re.S)
    if fence:
        s = fence.group(1).strip()
    # 尝试直接 parse
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return v
    except json.JSONDecodeError:
        pass
    # 抓第一个 [...] 块
    m = _JSON_ARRAY_RE.search(s)
    if m:
        try:
            v = json.loads(m.group(0))
            if isinstance(v, list):
                return v
        except json.JSONDecodeError:
            return None
    return None


def build_prompt(template: str, dishes_batch: list[dict[str, Any]]) -> str:
    """把 batch 替换进 {INPUT_DISHES_JSON}."""
    inputs_only = []
    for d in dishes_batch:
        keys = ("dish_id", "raw_name", "restaurant_name",
                "restaurant_category_raw", "category_raw", "price")
        inputs_only.append({k: d.get(k) for k in keys})
    return template.replace("{INPUT_DISHES_JSON}", json.dumps(inputs_only, ensure_ascii=False))


REQUIRED_FIELDS = [
    "dish_id", "canonical_name", "cuisine", "main_ingredient_type", "cooking_method",
    "oil_level", "protein_grams_estimate", "vegetable_ratio_estimate",
    "is_complete_meal", "spicy_level", "dish_role", "processed_meat_flag",
    "sweet_sauce_level", "wetness", "grain_type", "tags",
]


def validate_record(rec: dict[str, Any]) -> tuple[bool, list[str]]:
    """单条 15 字段齐 + 类型基本对."""
    errs = []
    for f in REQUIRED_FIELDS:
        if f not in rec:
            errs.append(f"missing:{f}")
    if errs:
        return False, errs
    if rec.get("sweet_sauce_level") not in (0, 1, 2, 3):
        errs.append("sweet_sauce_level out of [0,3]")
    if not isinstance(rec.get("processed_meat_flag"), bool):
        errs.append("processed_meat_flag not bool")
    if rec.get("dish_role") not in ("主菜", "主食", "配菜", "汤", "小食", "饮品", "套餐"):
        errs.append(f"dish_role invalid: {rec.get('dish_role')}")
    if rec.get("wetness") not in (1, 2, 3):
        errs.append(f"wetness invalid: {rec.get('wetness')}")
    if not isinstance(rec.get("tags"), list):
        errs.append("tags not list")
    return (not errs), errs

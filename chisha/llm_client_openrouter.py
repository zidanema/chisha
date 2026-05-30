"""OpenRouter (or any OpenAI 兼容 endpoint) 的薄封装.

为什么单独一个 file:
- 旧 chisha/llm_client.py 走 Anthropic 直连, 仍由 reason / 推荐链路使用; 不动它
- 这个 file 专给 v3 全量打标用 (tag_via_api.py 走 OpenRouter)
- 走 OpenAI Python SDK + base_url=OpenRouter, 模型名按 OR 命名空间
  (deepseek/deepseek-v4-flash / anthropic/claude-sonnet-4.6 / anthropic/claude-opus-4.5 等)

环境变量 (从 .env load):
- OPENROUTER_API_KEY (必需)
- OPENROUTER_BASE_URL (可选, 默认 https://openrouter.ai/api/v1)
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

# dev: repo root .env; wheel: chisha/ 包内无 .env, load_dotenv 静默 no-op (走环境变量).
from chisha.install_root import install_root as _install_root  # T-DIST-01 B.1
_REPO_ROOT = _install_root()
load_dotenv(_REPO_ROOT / ".env")

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
# 2026-05-12 D-037: bulk 默认从 sonnet-4.5 切到 deepseek-v4-flash
# 依据: eval/dish_tagging_eval 171 条 dual-model golden 横评
#   - field acc 88.9% (距 sonnet-4.6 冠军 -0.5pp)
#   - 100万条预估 $100 (sonnet-4.6 $4572, 便宜 45x)
# 高准确率要求的样本仍可用 --model anthropic/claude-sonnet-4.6 显式覆盖
DEFAULT_BULK_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_AUDIT_MODEL = "anthropic/claude-opus-4.5"


def _client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY 未设置 (放进项目根 .env: OPENROUTER_API_KEY=sk-or-v1-...)"
        )
    base_url = os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)
    return OpenAI(api_key=api_key, base_url=base_url)


def call_text(
    prompt: str,
    *,
    model: str = DEFAULT_BULK_MODEL,
    max_tokens: int = 8192,
    temperature: float = 0.0,
    system: Optional[str] = None,
    extra_headers: Optional[dict] = None,
) -> str:
    """单次调用, 返回 assistant text. 失败由调用方 (tag_via_api retry) 接住."""
    client = _client()
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    headers = {
        # OpenRouter 推荐 (用于排行榜/统计, 不影响调用)
        "HTTP-Referer": "https://github.com/chisha-private",
        "X-Title": "chisha tag_via_api",
    }
    if extra_headers:
        headers.update(extra_headers)

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        extra_headers=headers,
    )
    return resp.choices[0].message.content or ""

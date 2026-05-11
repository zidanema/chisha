"""探测 OpenRouter 单账号并发上限.

跑 N 个完全相同的极小请求(1-token), 测:
- 多少并发触发 429
- 实际成功 RPS

跑一次 30 并发的 burst, 用最便宜的 Haiku 控制成本 (~$0.001).
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _or_client import API_KEY, BASE_URL  # noqa: E402

MODEL = "anthropic/claude-haiku-4.5"
N_REQUESTS = 30
BURST_CONCURRENCY = 30


async def ping(client: httpx.AsyncClient, idx: int) -> dict:
    t0 = time.time()
    try:
        r = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": MODEL, "messages": [{"role": "user", "content": "say ok"}],
                  "max_tokens": 4, "temperature": 0,
                  "reasoning": {"enabled": False}},
            timeout=60,
        )
        return {"idx": idx, "status": r.status_code, "lat_ms": int((time.time()-t0)*1000),
                "ratelimit_remaining": r.headers.get("x-ratelimit-remaining"),
                "ratelimit_reset": r.headers.get("x-ratelimit-reset"),
                "err": r.text[:120] if r.status_code >= 400 else None}
    except Exception as e:
        return {"idx": idx, "status": "EXC", "lat_ms": int((time.time()-t0)*1000),
                "err": repr(e)[:120]}


async def main() -> int:
    sem = asyncio.Semaphore(BURST_CONCURRENCY)

    async def bounded(client, i):
        async with sem:
            return await ping(client, i)

    print(f"[probe] burst={N_REQUESTS} requests, concurrency={BURST_CONCURRENCY}, model={MODEL}")
    t_total0 = time.time()
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[bounded(client, i) for i in range(N_REQUESTS)])
    elapsed = time.time() - t_total0
    n_ok = sum(1 for r in results if r["status"] == 200)
    n_429 = sum(1 for r in results if r["status"] == 429)
    n_5xx = sum(1 for r in results if isinstance(r["status"], int) and r["status"] >= 500)
    n_exc = sum(1 for r in results if r["status"] == "EXC")
    lats = sorted([r["lat_ms"] for r in results if r["status"] == 200])
    print(f"[probe] elapsed={elapsed:.1f}s, ok={n_ok}, 429={n_429}, 5xx={n_5xx}, exc={n_exc}")
    if lats:
        print(f"[probe] success lat: min={lats[0]}ms p50={lats[len(lats)//2]}ms p95={lats[int(len(lats)*0.95)]}ms max={lats[-1]}ms")
    if n_429 > 0:
        print(f"[probe] 429 hit ! 触发了 rate limit, 建议 concurrency≤ {BURST_CONCURRENCY - n_429}")
    else:
        print(f"[probe] 0 个 429, concurrency={BURST_CONCURRENCY} 安全")
    # 看最后一个 200 响应的 ratelimit headers
    last_ok = next((r for r in results if r["status"] == 200), None)
    if last_ok:
        print(f"[probe] header ratelimit_remaining={last_ok.get('ratelimit_remaining')}, reset={last_ok.get('ratelimit_reset')}")
    return 0 if n_429 == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

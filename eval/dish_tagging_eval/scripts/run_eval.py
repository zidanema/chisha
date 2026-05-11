"""跑全部候选模型 × 全部 150 条 golden, 写 results/{alias}.jsonl."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _or_client import build_prompt, call_model, parse_json_array  # noqa: E402

PROMPT_PATH = ROOT / "prompts" / "tag_dishes_v3_draft.md"
GOLDEN_PATH = ROOT / "data" / "golden_set.jsonl"
RESULTS_DIR = ROOT / "results"
CONFIG_PATH = ROOT / "config.yaml"


def load_golden() -> list[dict]:
    out = []
    for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


async def call_one_batch(client, sem, prompt_template, model_id, batch, *, reasoning_enabled,
                         timeout_s):
    """跑一个 batch, 返回 list of per-dish records (含 predicted/raw_response/cost/...)."""
    inputs_only = [d["input"] for d in batch]
    prompt = build_prompt(prompt_template, inputs_only)
    async with sem:
        retry_count = 0
        meta = None
        parsed = None
        for attempt in range(3):
            try:
                meta = await call_model(client, model_id, prompt,
                                         reasoning_enabled=reasoning_enabled, timeout=timeout_s)
                parsed = parse_json_array(meta["content"])
                if parsed is not None and isinstance(parsed, list):
                    break
                # parse failed but no exception, count as retry
            except Exception as e:
                meta = {"content": "", "latency_ms": 0, "input_tokens": 0,
                        "output_tokens": 0, "cost_usd": 0.0, "finish_reason": "error",
                        "_error": str(e)}
            retry_count += 1
        out = []
        by_id = {}
        if parsed is not None:
            for rec in parsed:
                did = rec.get("dish_id")
                if did:
                    by_id[did] = rec
        for d in batch:
            did = d["dish_id"]
            pred = by_id.get(did)
            json_valid = pred is not None and all(k in pred for k in (
                "canonical_name", "cuisine", "main_ingredient_type", "cooking_method",
                "oil_level", "protein_grams_estimate", "vegetable_ratio_estimate",
                "is_complete_meal", "spicy_level", "dish_role", "processed_meat_flag",
                "sweet_sauce_level", "wetness", "grain_type", "tags",
            ))
            out.append({
                "dish_id": did,
                "model": model_id,
                "predicted": pred,
                "raw_response": (meta or {}).get("content", "")[:2000],
                "latency_ms": (meta or {}).get("latency_ms", 0),
                "input_tokens": (meta or {}).get("input_tokens", 0) // max(1, len(batch)),
                "output_tokens": (meta or {}).get("output_tokens", 0) // max(1, len(batch)),
                "cost_usd": (meta or {}).get("cost_usd", 0.0) / max(1, len(batch)),
                "json_valid": json_valid,
                "retry_count": retry_count,
                "batch_size": len(batch),
                "_batch_total_cost": (meta or {}).get("cost_usd", 0.0),
                "_batch_total_in_tok": (meta or {}).get("input_tokens", 0),
                "_batch_total_out_tok": (meta or {}).get("output_tokens", 0),
            })
        return out


async def run_one_model(alias: str, model_id: str, prompt_template: str, golden: list[dict],
                        *, batch_size, concurrency, reasoning_enabled, timeout_s,
                        budget_remaining: float) -> tuple[list[dict], float]:
    batches = [golden[i:i+batch_size] for i in range(0, len(golden), batch_size)]
    sem = asyncio.Semaphore(concurrency)
    all_records: list[dict] = []
    total_cost = 0.0
    seen_batch_costs = set()  # 避免重复计费
    async with httpx.AsyncClient() as client:
        tasks = [call_one_batch(client, sem, prompt_template, model_id, b,
                                reasoning_enabled=reasoning_enabled, timeout_s=timeout_s)
                 for b in batches]
        for coro in asyncio.as_completed(tasks):
            recs = await coro
            if recs:
                batch_cost = recs[0].get("_batch_total_cost", 0.0)
                key = (recs[0]["dish_id"], batch_cost)
                if key not in seen_batch_costs:
                    total_cost += batch_cost
                    seen_batch_costs.add(key)
            all_records.extend(recs)
            if total_cost > budget_remaining:
                print(f"  [BUDGET] {alias} hit remaining budget=${budget_remaining:.4f}, stop", flush=True)
                break
    # 整理 by dish_id, 确保 150 条覆盖(失败的占位)
    by_id = {r["dish_id"]: r for r in all_records}
    final = []
    for d in golden:
        did = d["dish_id"]
        if did in by_id:
            final.append(by_id[did])
        else:
            final.append({
                "dish_id": did, "model": model_id, "predicted": None,
                "raw_response": "", "latency_ms": 0,
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                "json_valid": False, "retry_count": 3, "batch_size": batch_size,
            })
    return final, total_cost


async def main(argv: list[str]) -> int:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    if not GOLDEN_PATH.exists():
        print("ERROR: golden_set.jsonl missing, run build_golden_set.py first", flush=True)
        return 2
    golden = load_golden()
    print(f"[eval] {len(golden)} golden samples, models={list(cfg['models'].keys())}", flush=True)

    # CLI: --only=alias1,alias2 跑指定模型; --smoke 只跑前 10 条
    only = None
    smoke = False
    for a in argv:
        if a.startswith("--only="):
            only = set(a.split("=", 1)[1].split(","))
        elif a == "--smoke":
            smoke = True
    if smoke:
        golden = golden[:10]
        print(f"[eval] smoke mode: {len(golden)} samples", flush=True)

    budget = float(cfg.get("budget_usd", 15.0))
    spent_total = 0.0
    failures = {}
    for alias, info in cfg["models"].items():
        if only and alias not in only:
            continue
        out_path = RESULTS_DIR / f"{alias}.jsonl"
        if out_path.exists() and not smoke and "--force" not in argv:
            existing = [ln for ln in out_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if len(existing) >= len(golden):
                print(f"[eval] {alias} already done ({len(existing)} rows), skip", flush=True)
                continue
        remaining = budget - spent_total
        if remaining <= 0:
            print(f"[eval] BUDGET exhausted, skip {alias}", flush=True)
            failures[alias] = "budget_exhausted"
            continue
        print(f"[eval] === {alias} ({info['id']}), budget remaining=${remaining:.4f} ===", flush=True)
        try:
            recs, cost = await run_one_model(
                alias, info["id"], prompt_template, golden,
                batch_size=cfg["batch_size"], concurrency=cfg["concurrency"],
                reasoning_enabled=cfg.get("reasoning_enabled", False),
                timeout_s=cfg.get("request_timeout_s", 120),
                budget_remaining=remaining,
            )
            spent_total += cost
            with out_path.open("w", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n_valid = sum(1 for r in recs if r["json_valid"])
            print(f"[eval] {alias}: {n_valid}/{len(recs)} JSON valid, cost=${cost:.4f}", flush=True)
        except Exception as e:
            print(f"[eval] {alias} FATAL: {e}", flush=True)
            failures[alias] = str(e)

    print(f"[eval] DONE. total_cost=${spent_total:.4f}, failures={failures}", flush=True)
    (RESULTS_DIR / "_run_summary.json").write_text(
        json.dumps({"spent_total_usd": spent_total, "failures": failures,
                    "n_samples": len(golden)}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))

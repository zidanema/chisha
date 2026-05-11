"""跑全部候选模型 × 全部 golden, 写 results/{alias}.jsonl.

关键设计 (2026-05-12 提速重构):
- **跨模型 + 跨 batch 全局并发池** (sem=cfg.concurrency, 默认 20):
  把 (model × batch) 所有任务推到一个池, 谁先空谁先跑.
  自然让快模型先完成释放容量, 慢模型(deepseek-pro/flash)不阻塞快模型.
- **实时进度**: 每个 batch 完成立即打印, 不等 model 全部完成
- **rate-limit 探测**: 跑前若 OPENROUTER_API_KEY 没 probe 过, 建议先跑 probe_rate_limit.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
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


REQUIRED_FIELDS = (
    "canonical_name", "cuisine", "main_ingredient_type", "cooking_method",
    "oil_level", "protein_grams_estimate", "vegetable_ratio_estimate",
    "is_complete_meal", "spicy_level", "dish_role", "processed_meat_flag",
    "sweet_sauce_level", "wetness", "grain_type", "tags",
)


def load_golden() -> list[dict]:
    return [json.loads(ln) for ln in GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]


async def run_one_batch(client, sem, prompt_template, alias, model_id, batch, *,
                        reasoning_enabled, timeout_s, max_retries=2):
    """单 batch 调用, 返回 (alias, records, batch_meta).

    每个 record 含: dish_id, model, predicted, raw_response, latency_ms,
    input_tokens, output_tokens, cost_usd, json_valid, retry_count, batch_size.
    """
    inputs_only = [d["input"] for d in batch]
    prompt = build_prompt(prompt_template, inputs_only)
    async with sem:
        retry_count = 0
        meta = None
        parsed = None
        last_err = None
        for _ in range(max_retries + 1):
            try:
                meta = await call_model(client, model_id, prompt,
                                        reasoning_enabled=reasoning_enabled,
                                        timeout=timeout_s)
                parsed = parse_json_array(meta["content"])
                if parsed is not None and isinstance(parsed, list):
                    break
                last_err = "parse_failed"
            except Exception as e:
                last_err = repr(e)[:200]
                meta = {"content": "", "latency_ms": 0, "input_tokens": 0,
                        "output_tokens": 0, "cost_usd": 0.0, "finish_reason": "error"}
            retry_count += 1
        out = []
        by_id = {}
        if parsed is not None:
            for rec in parsed:
                did = rec.get("dish_id")
                if did:
                    by_id[did] = rec
        n_in = (meta or {}).get("input_tokens", 0)
        n_out = (meta or {}).get("output_tokens", 0)
        cost = (meta or {}).get("cost_usd", 0.0)
        lat = (meta or {}).get("latency_ms", 0)
        for d in batch:
            did = d["dish_id"]
            pred = by_id.get(did)
            json_valid = pred is not None and all(k in pred for k in REQUIRED_FIELDS)
            out.append({
                "dish_id": did,
                "model": model_id,
                "predicted": pred,
                "raw_response": (meta or {}).get("content", "")[:2000],
                "latency_ms": lat,
                "input_tokens": n_in // max(1, len(batch)),
                "output_tokens": n_out // max(1, len(batch)),
                "cost_usd": cost / max(1, len(batch)),
                "json_valid": json_valid,
                "retry_count": retry_count,
                "batch_size": len(batch),
                "_batch_total_cost": cost,
                "_batch_total_in_tok": n_in,
                "_batch_total_out_tok": n_out,
                "_batch_last_err": last_err if not json_valid else None,
            })
        return alias, out, {"cost": cost, "latency_ms": lat, "retry": retry_count,
                            "n_valid": sum(1 for r in out if r["json_valid"]),
                            "n": len(out)}


async def main(argv: list[str]) -> int:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    if not GOLDEN_PATH.exists():
        print("ERROR: golden_set.jsonl missing", flush=True)
        return 2
    golden = load_golden()

    # CLI 参数
    only = None
    smoke = False
    force = False
    concurrency_override = None
    for a in argv:
        if a.startswith("--only="):
            only = set(a.split("=", 1)[1].split(","))
        elif a == "--smoke":
            smoke = True
        elif a == "--force":
            force = True
        elif a.startswith("--concurrency="):
            concurrency_override = int(a.split("=", 1)[1])
    if smoke:
        golden = golden[:10]

    models_cfg = {a: i for a, i in cfg["models"].items() if not only or a in only}
    batch_size = int(cfg.get("batch_size", 20))
    concurrency = concurrency_override or int(cfg.get("concurrency", 20))
    budget = float(cfg.get("budget_usd", 15.0))
    timeout_s = float(cfg.get("request_timeout_s", 180))
    reasoning_enabled = bool(cfg.get("reasoning_enabled", False))
    max_retries = int(cfg.get("max_retries", 2))

    # skip 已完成的模型 (results 行数 >= golden 数量, 非 force)
    pending = {}
    for alias, info in models_cfg.items():
        out_path = RESULTS_DIR / f"{alias}.jsonl"
        if not force and not smoke and out_path.exists():
            existing = [ln for ln in out_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if len(existing) >= len(golden):
                print(f"[eval] skip {alias} (already {len(existing)} rows)", flush=True)
                continue
        pending[alias] = info

    if not pending:
        print("[eval] nothing to run", flush=True)
        return 0

    # 构造 (alias, model_id, batch) 任务列表
    batches = [golden[i:i+batch_size] for i in range(0, len(golden), batch_size)]
    task_specs = []
    for alias, info in pending.items():
        for bi, batch in enumerate(batches):
            task_specs.append((alias, info["id"], bi, batch))

    n_total_tasks = len(task_specs)
    print(f"[eval] golden={len(golden)} batches/model={len(batches)} models={len(pending)} "
          f"total_tasks={n_total_tasks} concurrency={concurrency}", flush=True)
    print(f"[eval] pending models: {list(pending.keys())}", flush=True)

    sem = asyncio.Semaphore(concurrency)
    spent = 0.0
    progress = {a: {"done": 0, "valid": 0, "cost": 0.0, "lat_max_ms": 0} for a in pending}
    results_by_alias = {a: [] for a in pending}
    n_done = 0
    t_run0 = time.time()

    abort_flag = {"v": False, "reason": ""}

    async def runner(client):
        nonlocal n_done, spent
        tasks = [asyncio.create_task(
            run_one_batch(client, sem, prompt_template, alias, mid, batch,
                          reasoning_enabled=reasoning_enabled, timeout_s=timeout_s,
                          max_retries=max_retries))
                 for (alias, mid, bi, batch) in task_specs]
        for fut in asyncio.as_completed(tasks):
            alias, recs, m = await fut
            results_by_alias[alias].extend(recs)
            spent += m["cost"]
            progress[alias]["done"] += m["n"]
            progress[alias]["valid"] += m["n_valid"]
            progress[alias]["cost"] += m["cost"]
            if m["latency_ms"] > progress[alias]["lat_max_ms"]:
                progress[alias]["lat_max_ms"] = m["latency_ms"]
            n_done += 1
            elapsed = time.time() - t_run0
            print(f"[eval] [{n_done:>3}/{n_total_tasks}] {alias:<16} "
                  f"+{m['n_valid']}/{m['n']}  lat={m['latency_ms']/1000:.1f}s  "
                  f"cost=${m['cost']:.4f}  | model_total={progress[alias]['done']}/{len(golden)} "
                  f"valid={progress[alias]['valid']} cost=${progress[alias]['cost']:.4f} "
                  f"| elapsed={elapsed:.0f}s spent_all=${spent:.4f}", flush=True)
            if spent > budget:
                abort_flag["v"] = True
                abort_flag["reason"] = f"budget_exceeded:${spent:.2f}>{budget}"
                print(f"[eval] BUDGET EXCEEDED, cancelling remaining...", flush=True)
                for t in tasks:
                    if not t.done():
                        t.cancel()
                break

    async with httpx.AsyncClient() as client:
        try:
            await runner(client)
        except asyncio.CancelledError:
            pass

    # 落盘: 每个模型一份完整 result, 缺失的占位
    for alias in pending:
        recs = results_by_alias[alias]
        by_id = {r["dish_id"]: r for r in recs}
        final = []
        model_id = pending[alias]["id"]
        for d in golden:
            did = d["dish_id"]
            if did in by_id:
                final.append(by_id[did])
            else:
                final.append({
                    "dish_id": did, "model": model_id, "predicted": None,
                    "raw_response": "", "latency_ms": 0,
                    "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                    "json_valid": False, "retry_count": max_retries + 1,
                    "batch_size": batch_size,
                    "_batch_total_cost": 0.0, "_batch_total_in_tok": 0,
                    "_batch_total_out_tok": 0, "_batch_last_err": "missing",
                })
        out_path = RESULTS_DIR / f"{alias}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for r in final:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        n_valid = sum(1 for r in final if r["json_valid"])
        print(f"[eval] write {out_path.name}: {n_valid}/{len(final)} valid, "
              f"cost=${progress[alias]['cost']:.4f}", flush=True)

    elapsed = time.time() - t_run0
    print(f"[eval] DONE in {elapsed:.0f}s ({elapsed/60:.1f}min)  "
          f"total_cost=${spent:.4f}  abort={abort_flag['reason'] or 'none'}", flush=True)
    (RESULTS_DIR / "_run_summary.json").write_text(json.dumps({
        "elapsed_s": elapsed, "spent_total_usd": spent,
        "abort_reason": abort_flag["reason"],
        "n_samples": len(golden), "concurrency": concurrency,
        "batch_size": batch_size,
        "models": list(pending.keys()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))

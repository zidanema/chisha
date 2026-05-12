"""[DEPRECATED 2026-05-12, D-036] 旧版 150 条 golden set 构造脚本.

已被 dual_pipeline.py (Opus 4.7 + Codex GPT-5.4 共创, 171 条) 取代,
原因: 单 LLM (Sonnet) 自评自打存在循环论证偏置, 详见 docs/DECISIONS.md D-036。

仍保留:
- ANCHOR_EXPECTED / 旧 dish_inputs.py 供 dish_inputs_v2.py 继承
- anchor_violations() 校验函数被 dual_pipeline.py 复用

仅在需要重建 v1 baseline (data/golden_set.v1.jsonl) 时执行。生产用 dual_pipeline.py。

原 docstring:
- 前 10 条 anchor: 直接用已知 expected (从 prompt 文件抽出)
- 后 140 条: 调 Sonnet 4.6 跑 expected, 自动锚点校验, 不过的重跑 1 次
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _or_client import (  # noqa: E402
    build_prompt, call_model, parse_json_array, validate_record,
)
from dish_inputs import ANCHOR_10, ANCHOR_EXPECTED, CANDIDATES  # noqa: E402

PROMPT_PATH = ROOT / "prompts" / "tag_dishes_v3_draft.md"
OUT_PATH = ROOT / "data" / "golden_set.jsonl"
SONNET_ID = "anthropic/claude-sonnet-4.6"
BATCH = 10
MAX_CONCURRENT = 5


def anchor_violations(raw_name: str, exp: dict) -> list[str]:
    """对一条 expected 跑反直觉锚点自检. 返回违反列表(空 = 通过)."""
    v = []
    n = raw_name
    # sweet_sauce_level: 红烧/糖醋/照烧/京酱/拔丝 → ≥2
    if any(k in n for k in ("红烧", "糖醋", "照烧", "京酱", "拔丝", "无锡酱")):
        if exp.get("sweet_sauce_level", 0) < 2:
            v.append(f"sweet_sauce_level<2 for '{n}'")
    if "蜜汁" in n or "蜂蜜" in n:
        if exp.get("sweet_sauce_level", 0) < 2:
            v.append(f"sweet_sauce_level<2 for honey '{n}'")
    # processed_meat_flag: 叉烧/烧鸭/烧鹅 且无"腊" → false
    if any(k in n for k in ("叉烧", "烧鸭", "烧鹅", "烧腊", "卤水", "白切鸡")) and "腊" not in n and "肠" not in n:
        if exp.get("processed_meat_flag") is True:
            v.append(f"processed_meat_flag=true for fresh-roast '{n}'")
    # 腊肠/培根/午餐肉/蟹柳/火腿肠/热狗 → true
    if any(k in n for k in ("腊肠", "培根", "午餐肉", "蟹柳", "火腿肠", "热狗")):
        if exp.get("processed_meat_flag") is False:
            v.append(f"processed_meat_flag=false for processed '{n}'")
    # dish_role: 套餐/+饭/+饮料/+主食/+汤/拼盘 → 套餐
    if any(k in n for k in ("套餐", "+饭", "+饮料", "+主食", "+汤", "+小菜", "拼盘")):
        if exp.get("dish_role") != "套餐":
            v.append(f"dish_role!=套餐 for '{n}'")
    # 米粉/河粉/粿条/肠粉 → grain_type=白米
    if any(k in n for k in ("米粉", "河粉", "粿条", "肠粉", "螺蛳粉", "桂林米粉", "云南米线")):
        if exp.get("grain_type") != "白米":
            v.append(f"grain_type!=白米 for rice-noodle '{n}'")
    return v


async def call_batch(client: httpx.AsyncClient, sem: asyncio.Semaphore,
                     prompt_template: str, batch: list[dict]) -> tuple[list[dict] | None, dict]:
    """一次 batch 调用, 返回 (parsed_list, meta)."""
    async with sem:
        prompt = build_prompt(prompt_template, batch)
        try:
            res = await call_model(client, SONNET_ID, prompt, reasoning_enabled=False)
        except Exception as e:
            return None, {"error": str(e), "cost": 0.0}
        parsed = parse_json_array(res["content"])
        meta = {
            "cost": res["cost_usd"],
            "latency_ms": res["latency_ms"],
            "input_tokens": res["input_tokens"],
            "output_tokens": res["output_tokens"],
            "raw": res["content"][:1000],
        }
        return parsed, meta


async def main() -> int:
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 已知 anchor 直接拼成 golden 记录
    golden: dict[str, dict] = {}
    for a in ANCHOR_10:
        did = a["dish_id"]
        exp = dict(ANCHOR_EXPECTED[did])
        exp["dish_id"] = did
        violations = anchor_violations(a["raw_name"], exp)
        anchor_notes_map = {
            "d001": "纯叶菜 vegetable_ratio>=0.9, dish_role=配菜",
            "d002": "川菜辣度2, oil>=5",
            "d003": "饺=主食+精制面+is_complete_meal=true",
            "d004": "米粉类 grain_type=白米, wetness=3",
            "d005": "红烧→sweet_sauce>=2",
            "d006": "关东煮 wetness=2(非3), 蟹柳→processed=true, dish_role=小食",
            "d007": "西式蛋白碗 is_complete_meal=true, grain=粗粮",
            "d008": "纯汤 wetness=3, dish_role=汤",
            "d009": "粤式烧腊套餐: processed=false, sweet=2, dish_role=套餐",
            "d010": "非食物兜底: 调料归小食",
        }
        golden[did] = {
            "dish_id": did,
            "input": {k: a[k] for k in ("dish_id", "raw_name", "restaurant_name",
                                         "restaurant_category_raw", "category_raw", "price")},
            "expected": exp,
            "category_tag": a["category_tag"],
            "anchor_notes": anchor_notes_map.get(did, ""),
            "needs_review": bool(violations),
            "anchor_violations": violations,
        }

    # 140 候选 → batch 调 Sonnet
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    batches = [CANDIDATES[i:i+BATCH] for i in range(0, len(CANDIDATES), BATCH)]
    total_cost = 0.0
    results_by_id: dict[str, dict] = {}

    async with httpx.AsyncClient() as client:
        # Round 1
        tasks = [call_batch(client, sem, prompt_template, b) for b in batches]
        print(f"[golden] round1: {len(batches)} batches", flush=True)
        outs = await asyncio.gather(*tasks)
        for batch, (parsed, meta) in zip(batches, outs):
            total_cost += meta.get("cost", 0.0)
            if parsed is None:
                print(f"[golden] WARN batch failed: {[d['dish_id'] for d in batch]}: {meta.get('error') or 'parse_err'}", flush=True)
                continue
            for rec in parsed:
                did = rec.get("dish_id")
                if did:
                    results_by_id[did] = rec

        # 评估 violations + 缺失, 找 redo 列表
        redo_ids = set()
        for cand in CANDIDATES:
            did = cand["dish_id"]
            rec = results_by_id.get(did)
            if rec is None:
                redo_ids.add(did)
                continue
            ok, errs = validate_record(rec)
            viols = anchor_violations(cand["raw_name"], rec)
            if not ok or viols:
                redo_ids.add(did)

        print(f"[golden] round1 cost=${total_cost:.4f}, redo={len(redo_ids)}", flush=True)

        # Round 2: 只重跑 violation 的 batch
        if redo_ids:
            redo_cands = [c for c in CANDIDATES if c["dish_id"] in redo_ids]
            redo_batches = [redo_cands[i:i+BATCH] for i in range(0, len(redo_cands), BATCH)]
            tasks2 = [call_batch(client, sem, prompt_template, b) for b in redo_batches]
            print(f"[golden] round2: {len(redo_batches)} batches", flush=True)
            outs2 = await asyncio.gather(*tasks2)
            for batch, (parsed, meta) in zip(redo_batches, outs2):
                total_cost += meta.get("cost", 0.0)
                if parsed is None:
                    continue
                for rec in parsed:
                    did = rec.get("dish_id")
                    if did:
                        results_by_id[did] = rec

    # 写出 golden
    anchor_notes_default = ""
    n_review = 0
    for cand in CANDIDATES:
        did = cand["dish_id"]
        rec = results_by_id.get(did)
        if rec is None:
            # 整个失败,占位让流程不卡
            rec = {f: None for f in (
                "canonical_name","cuisine","main_ingredient_type","cooking_method","oil_level",
                "protein_grams_estimate","vegetable_ratio_estimate","is_complete_meal",
                "spicy_level","dish_role","processed_meat_flag","sweet_sauce_level",
                "wetness","grain_type","tags",
            )}
            rec["dish_id"] = did
            rec["tags"] = []
            violations = ["FAILED_GENERATION"]
        else:
            rec.setdefault("dish_id", did)
            violations = anchor_violations(cand["raw_name"], rec)
        ok, errs = validate_record(rec)
        needs_review = (not ok) or bool(violations)
        if needs_review:
            n_review += 1
        golden[did] = {
            "dish_id": did,
            "input": {k: cand[k] for k in ("dish_id", "raw_name", "restaurant_name",
                                            "restaurant_category_raw", "category_raw", "price")},
            "expected": rec,
            "category_tag": cand["category_tag"],
            "anchor_notes": "",
            "needs_review": needs_review,
            "anchor_violations": violations + ([f"validate:{e}" for e in errs] if errs else []),
        }

    # 按 dish_id 升序输出
    ordered = sorted(golden.values(), key=lambda x: int(x["dish_id"][1:]))
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for rec in ordered:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[golden] wrote {len(ordered)} → {OUT_PATH}", flush=True)
    print(f"[golden] needs_review={n_review}, total_cost=${total_cost:.4f}", flush=True)
    if n_review > 15:
        print(f"[golden] WARN needs_review={n_review} > 15", flush=True)
    return 0 if len(ordered) == 150 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

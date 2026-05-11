"""读 golden_set + 各模型 results, 按字段评分, 写 score_summary.json."""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = ROOT / "data" / "golden_set.jsonl"
RESULTS_DIR = ROOT / "results"
OUT_PATH = ROOT / "score_summary.json"

STRING_FIELDS = ["canonical_name", "cuisine", "main_ingredient_type", "cooking_method",
                 "dish_role", "grain_type"]
INT_FIELDS = ["oil_level", "spicy_level", "sweet_sauce_level", "wetness"]
BOOL_FIELDS = ["is_complete_meal", "processed_meat_flag"]
TOL_FIELDS = {"protein_grams_estimate": 5, "vegetable_ratio_estimate": 0.1}
ALL_FIELDS = STRING_FIELDS + INT_FIELDS + BOOL_FIELDS + list(TOL_FIELDS.keys()) + ["tags"]

KEY4 = ["sweet_sauce_level", "processed_meat_flag", "dish_role", "grain_type"]


def field_correct(field: str, expected, predicted) -> bool:
    if predicted is None or expected is None:
        return False
    if field == "tags":
        if not isinstance(expected, list) or not isinstance(predicted, list):
            return False
        e = {str(x).strip() for x in expected}
        p = {str(x).strip() for x in predicted}
        if not e and not p:
            return True
        if not e or not p:
            return False
        inter = len(e & p)
        union = len(e | p)
        if union == 0:
            return True
        return (inter / union) >= 0.5
    if field == "protein_grams_estimate":
        try:
            return abs(float(expected) - float(predicted)) <= 5.0
        except (TypeError, ValueError):
            return False
    if field == "vegetable_ratio_estimate":
        try:
            return abs(float(expected) - float(predicted)) <= 0.1
        except (TypeError, ValueError):
            return False
    if field in INT_FIELDS:
        try:
            return int(expected) == int(predicted)
        except (TypeError, ValueError):
            return False
    if field in BOOL_FIELDS:
        return bool(expected) == bool(predicted)
    # string
    try:
        return str(expected).strip() == str(predicted).strip()
    except Exception:
        return False


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, math.ceil(0.95 * len(s)) - 1)
    return s[k]


def score_one_model(alias: str, model_id: str, golden: list[dict], results: list[dict]) -> dict:
    res_by_id = {r["dish_id"]: r for r in results}
    field_correct_counts = {f: 0 for f in ALL_FIELDS}
    field_eval_counts = {f: 0 for f in ALL_FIELDS}
    by_cat: dict[str, dict] = defaultdict(lambda: {"n": 0, "n_all_correct": 0,
                                                    "field_correct": defaultdict(int),
                                                    "field_evaluated": defaultdict(int)})
    key4_correct = {f: 0 for f in KEY4}
    key4_evaluated = {f: 0 for f in KEY4}
    n_total = len(golden)
    n_evaluated = 0
    n_all_correct = 0
    n_json_valid = 0
    costs = []
    latencies = []
    in_tokens_total = 0
    out_tokens_total = 0
    retries = 0
    errors_for_sampling = []  # (dish_id, expected, predicted, wrong_fields)

    for g in golden:
        did = g["dish_id"]
        exp = g["expected"]
        cat = g.get("category_tag", "unknown")
        r = res_by_id.get(did)
        if r is None:
            continue
        pred = r.get("predicted")
        # 计费 / 延迟 / token 不依赖 JSON valid (失败也算成本)
        costs.append(float(r.get("cost_usd", 0.0)))
        latencies.append(int(r.get("latency_ms", 0)))
        in_tokens_total += int(r.get("input_tokens", 0))
        out_tokens_total += int(r.get("output_tokens", 0))
        retries += int(r.get("retry_count", 0))
        if r.get("json_valid"):
            n_json_valid += 1
        if pred is None:
            continue
        n_evaluated += 1
        by_cat[cat]["n"] += 1
        all_ok = True
        wrong = []
        for f in ALL_FIELDS:
            e = exp.get(f)
            p = pred.get(f)
            if e is None and f not in ("tags",):
                continue  # golden 本身没值就不评
            field_eval_counts[f] += 1
            by_cat[cat]["field_evaluated"][f] += 1
            if field_correct(f, e, p):
                field_correct_counts[f] += 1
                by_cat[cat]["field_correct"][f] += 1
            else:
                all_ok = False
                wrong.append({"field": f, "expected": e, "predicted": p})
            if f in KEY4:
                key4_evaluated[f] += 1
                if field_correct(f, e, p):
                    key4_correct[f] += 1
        if all_ok:
            n_all_correct += 1
            by_cat[cat]["n_all_correct"] += 1
        elif len(errors_for_sampling) < 30:
            errors_for_sampling.append({
                "dish_id": did,
                "raw_name": g["input"]["raw_name"],
                "category_tag": cat,
                "wrong_fields": wrong[:8],
                "expected": exp,
                "predicted": pred,
            })

    def safe_div(a, b):
        return (a / b) if b else 0.0

    field_acc = {f: safe_div(field_correct_counts[f], field_eval_counts[f]) for f in ALL_FIELDS}
    micro_total_correct = sum(field_correct_counts.values())
    micro_total_eval = sum(field_eval_counts.values())
    by_cat_out = {}
    for cat, agg in by_cat.items():
        by_cat_out[cat] = {
            "n": agg["n"],
            "all_correct_rate": safe_div(agg["n_all_correct"], agg["n"]),
            "field_accuracy": {f: safe_div(agg["field_correct"][f], agg["field_evaluated"][f])
                                for f in ALL_FIELDS if agg["field_evaluated"][f] > 0},
        }
    return {
        "model_id_actual": model_id,
        "n_total": n_total,
        "n_evaluated": n_evaluated,
        "field_accuracy": field_acc,
        "field_accuracy_micro": safe_div(micro_total_correct, micro_total_eval),
        "json_valid_rate": safe_div(n_json_valid, n_total),
        "all_fields_correct_rate": safe_div(n_all_correct, n_evaluated),
        "by_category": by_cat_out,
        "key_4_fields": {f: safe_div(key4_correct[f], key4_evaluated[f]) for f in KEY4},
        "cost_usd_total": sum(costs),
        "avg_latency_ms": int(statistics.mean(latencies)) if latencies else 0,
        "p95_latency_ms": int(p95(latencies)),
        "input_tokens_total": in_tokens_total,
        "output_tokens_total": out_tokens_total,
        "retries_total": retries,
        "estimated_1M_cost_usd": (sum(costs) / max(1, n_total)) * 1_000_000,
        "error_samples": errors_for_sampling,
    }


def main() -> int:
    golden = load_jsonl(GOLDEN_PATH)
    summary: dict = {"n_golden": len(golden), "models": {}, "errors": []}
    # 读 config 顺序保持一致
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    for alias, info in cfg["models"].items():
        path = RESULTS_DIR / f"{alias}.jsonl"
        if not path.exists():
            summary["errors"].append(f"missing results: {alias}")
            continue
        results = load_jsonl(path)
        summary["models"][alias] = score_one_model(alias, info["id"], golden, results)
    OUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=float),
                        encoding="utf-8")
    print(f"[score] wrote {OUT_PATH}, models={list(summary['models'].keys())}", flush=True)
    # 简要打印
    print(f"{'alias':<16} {'field_acc':>10} {'all_corr':>10} {'json_ok':>10} {'cost':>10}")
    for alias, s in summary["models"].items():
        print(f"{alias:<16} {s['field_accuracy_micro']:>10.3f} {s['all_fields_correct_rate']:>10.3f} "
              f"{s['json_valid_rate']:>10.3f} {s['cost_usd_total']:>10.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

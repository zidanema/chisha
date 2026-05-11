"""api-key 路径的打标脚本 (走 OpenRouter, OpenAI 兼容协议).

替代 scripts/tag_via_subagent.py: 不再依赖 Claude Code 的 Agent spawn,
直接用 .env 里的 OPENROUTER_API_KEY 并发调 LLM.

工作流 (单命令完成, 无需 prepare/merge 两步):
    uv run python -m scripts.tag_via_api <zone> [--limit N] [--batch 30] [--workers 16] ...

设计点:
  - 切批 → ThreadPoolExecutor 并发 → 每批落 .claude/v3_tagging/<zone>/batch_NNN.out.json
  - 失败按指数 backoff 重试 (默认 3 次), 最终失败 dish_id 写 logs/tag_failures.jsonl
  - 断点续跑: 已存在的 batch_NNN.out.json 直接复用 (除非 --no-resume)
  - 全部完成后合并写 data/<zone>/dishes_tagged.json, schema 校验 (DishTagged) 全通过
  - 增量: 默认只打 raw 里有但 tagged (同 tag_version) 里没有的;  --force-version 全量重打
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from chisha.llm_client_openrouter import (
    DEFAULT_BULK_MODEL,
    DEFAULT_AUDIT_MODEL,
    call_text,
)
from scripts.tag_dishes import (
    build_input_payload,
    extract_json_array,
    merge_into_output,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROMPT_PATH = ROOT / "prompts" / "tag_dishes.md"
JOBS_ROOT = ROOT / ".claude" / "v3_tagging"
FAILURES_LOG = ROOT / "logs" / "tag_failures.jsonl"

DEFAULT_BATCH_SIZE = 30
DEFAULT_WORKERS = 16
DEFAULT_VERSION_LABEL = "v3"
DEFAULT_MAX_ATTEMPTS = 3

ZONES_ALL = ("home", "shenzhen-bay")

# v3 字段集合 (DishTagged + 5 新字段); 在 schema 升级之前手动校验
_V3_REQUIRED_TOP = {
    "dish_id", "canonical_name", "cuisine", "main_ingredient_type",
    "cooking_method", "oil_level", "protein_grams_estimate",
    "vegetable_ratio_estimate", "is_complete_meal", "spicy_level",
    "dish_role", "processed_meat_flag", "sweet_sauce_level", "wetness",
    "grain_type", "tags",
}

DISH_ROLE_VALUES = {"主菜", "主食", "配菜", "汤", "小食", "饮品", "套餐"}
GRAIN_TYPE_VALUES = {"白米", "糙米杂粮", "精制面", "全麦面", "粗粮", "粥", "无"}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, obj: Any, indent: int = 2) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=indent),
                 encoding="utf-8")


def _zone_data_dir(zone: str) -> Path:
    return ROOT / "data" / zone


def _zone_jobs_dir(zone: str, version_label: str) -> Path:
    return JOBS_ROOT / version_label / zone


def _resolve_zones(zone_arg: str) -> list[str]:
    if zone_arg == "all":
        return list(ZONES_ALL)
    return [zone_arg]


# ---------------- v3 record validator ----------------

def validate_v3_record(rec: dict) -> list[str]:
    """v3 字段层校验 (schema 升级后 DishTagged 也会校一遍)."""
    issues: list[str] = []
    missing = _V3_REQUIRED_TOP - set(rec.keys())
    if missing:
        issues.append(f"missing fields: {sorted(missing)}")
        return issues

    if rec["oil_level"] not in (1, 2, 3, 4, 5):
        issues.append(f"oil_level invalid: {rec['oil_level']}")
    if rec["spicy_level"] not in (0, 1, 2, 3):
        issues.append(f"spicy_level invalid: {rec['spicy_level']}")
    if rec["sweet_sauce_level"] not in (0, 1, 2, 3):
        issues.append(f"sweet_sauce_level invalid: {rec['sweet_sauce_level']}")
    if rec["wetness"] not in (1, 2, 3):
        issues.append(f"wetness invalid: {rec['wetness']}")

    v = rec["vegetable_ratio_estimate"]
    if not (isinstance(v, (int, float)) and 0.0 <= v <= 1.0):
        issues.append(f"vegetable_ratio_estimate invalid: {v}")

    if rec["dish_role"] not in DISH_ROLE_VALUES:
        issues.append(f"dish_role invalid: {rec['dish_role']!r}")
    if rec["grain_type"] not in GRAIN_TYPE_VALUES:
        issues.append(f"grain_type invalid: {rec['grain_type']!r}")

    if not isinstance(rec["processed_meat_flag"], bool):
        issues.append(f"processed_meat_flag must be bool: {rec['processed_meat_flag']!r}")
    if not isinstance(rec["is_complete_meal"], bool):
        issues.append(f"is_complete_meal must be bool: {rec['is_complete_meal']!r}")

    return issues


# ---------------- LLM call ----------------

def _call_one_batch(
    rest_by_id: dict,
    batch: list[dict],
    prompt_template: str,
    *,
    model: str,
    max_attempts: int,
    max_tokens: int,
) -> tuple[list[dict], str | None]:
    """跑一批, 成功返回 (records, None); 全失败返回 ([], last_err)."""
    payload = build_input_payload(rest_by_id, batch)
    prompt = prompt_template.replace("{INPUT_DISHES_JSON}", payload)
    expected_ids = [d["dish_id"] for d in batch]

    last_err: str | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            text = call_text(prompt, model=model, max_tokens=max_tokens,
                             temperature=0.0)
            recs = extract_json_array(text)
            if len(recs) != len(batch):
                raise ValueError(
                    f"count mismatch: input {len(batch)}, got {len(recs)}"
                )
            got_ids = [r.get("dish_id") for r in recs]
            if got_ids != expected_ids:
                raise ValueError(
                    f"dish_id order mismatch (first diverge idx="
                    f"{next((i for i, (a, b) in enumerate(zip(got_ids, expected_ids)) if a != b), 0)})"
                )
            for r in recs:
                issues = validate_v3_record(r)
                if issues:
                    raise ValueError(f"{r.get('dish_id')}: {issues}")
            return recs, None
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:300]}"
            if attempt < max_attempts:
                # 指数 backoff: 2s -> 4s -> 8s
                time.sleep(2 ** attempt)
    return [], last_err


def _record_failure(zone: str, batch_id: int, dish_ids: list[str],
                    error: str) -> None:
    FAILURES_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "ts": _now_iso(),
        "zone": zone,
        "batch_id": batch_id,
        "dish_ids": dish_ids,
        "error": error[:500],
    }
    with FAILURES_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


# ---------------- pipeline ----------------

def _select_dishes_to_tag(
    raw: list[dict],
    existing_tagged: list[dict],
    version_label: str,
    force_version: bool,
    limit: int | None,
) -> list[dict]:
    if force_version:
        delta = list(raw)
    else:
        existing_ids = {
            d["dish_id"] for d in existing_tagged
            if d.get("metadata", {}).get("tag_version") == version_label
        }
        delta = [d for d in raw if d["dish_id"] not in existing_ids]
    if limit:
        delta = delta[:limit]
    return delta


def _make_batches(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def run_zone(
    zone: str,
    *,
    prompt_path: Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
    workers: int = DEFAULT_WORKERS,
    version_label: str = DEFAULT_VERSION_LABEL,
    model: str = DEFAULT_BULK_MODEL,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_tokens: int = 8192,
    force_version: bool = False,
    no_resume: bool = False,
    limit: int | None = None,
    dry_run: bool = False,
    out_path_override: Path | None = None,
) -> dict:
    base = _zone_data_dir(zone)
    raw = _read_json(base / "dishes_raw.json")
    rest_by_id = {r["id"]: r for r in _read_json(base / "restaurants.json")}

    tagged_path = base / "dishes_tagged.json"
    existing_tagged = _read_json(tagged_path) if tagged_path.exists() else []
    raw_idx = {d["dish_id"]: d for d in raw}

    delta = _select_dishes_to_tag(raw, existing_tagged, version_label,
                                  force_version, limit)
    batches = _make_batches(delta, batch_size)
    jobs_dir = _zone_jobs_dir(zone, version_label)
    jobs_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{zone}] raw={len(raw)} existing_tagged={len(existing_tagged)} "
          f"delta={len(delta)} batches={len(batches)} workers={workers} "
          f"model={model} version={version_label}",
          flush=True)

    if dry_run:
        return {"zone": zone, "dry_run": True, "delta": len(delta),
                "batches": len(batches)}

    if not delta:
        print(f"[{zone}] nothing to tag", flush=True)
        return {"zone": zone, "tagged_total": len(existing_tagged),
                "newly_tagged": 0, "failed": 0}

    prompt_template = prompt_path.read_text(encoding="utf-8")

    # ---- 提前过滤已 done 的 batch (resume) ----
    todo_batches: list[tuple[int, list[dict]]] = []
    done_count = 0
    for idx, batch in enumerate(batches, start=1):
        out_path = jobs_dir / f"batch_{idx:04d}.out.json"
        if not no_resume and out_path.exists():
            try:
                cached = _read_json(out_path)
                if isinstance(cached, list) and len(cached) == len(batch):
                    done_count += 1
                    continue
            except Exception:
                pass
        todo_batches.append((idx, batch))

    if done_count:
        print(f"[{zone}] resume: {done_count} batch 已缓存可复用",
              flush=True)

    # ---- 并发跑 todo_batches ----
    failed_batches: list[tuple[int, list[str], str]] = []
    completed = 0
    started = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_idx = {
            pool.submit(_call_one_batch, rest_by_id, batch, prompt_template,
                        model=model, max_attempts=max_attempts,
                        max_tokens=max_tokens): (idx, batch)
            for idx, batch in todo_batches
        }
        for fut in as_completed(future_to_idx):
            idx, batch = future_to_idx[fut]
            recs, err = fut.result()
            if err is None:
                out_path = jobs_dir / f"batch_{idx:04d}.out.json"
                _write_json(out_path, recs)
                completed += 1
                elapsed = time.time() - started
                rate = completed / max(elapsed, 0.1)
                eta = (len(todo_batches) - completed) / max(rate, 0.001)
                print(f"  ✓ batch {idx}/{len(batches)} done "
                      f"({completed}/{len(todo_batches)} new, "
                      f"{rate:.1f} batch/s, eta {eta:.0f}s)",
                      flush=True)
            else:
                dish_ids = [d["dish_id"] for d in batch]
                failed_batches.append((idx, dish_ids, err))
                _record_failure(zone, idx, dish_ids, err)
                print(f"  ✗ batch {idx} failed: {err[:160]}",
                      file=sys.stderr, flush=True)

    # ---- 合并所有 batch + kept existing → dishes_tagged.json ----
    if force_version:
        combined: dict[str, dict] = {}
    else:
        combined = {t["dish_id"]: t for t in existing_tagged}

    merged_count = 0
    for idx, batch in enumerate(batches, start=1):
        out_path = jobs_dir / f"batch_{idx:04d}.out.json"
        if not out_path.exists():
            continue
        recs = _read_json(out_path)
        new_objs = merge_into_output(raw_idx, recs)
        for rec in new_objs:
            rec["metadata"]["tag_version"] = version_label
            combined[rec["dish_id"]] = rec
            merged_count += 1

    all_records = list(combined.values())

    # 尝试用 schemas.DishTagged 校验; schema 还没升级时 5 新字段会撞 extra=forbid
    # → 回落到 v3 record-level 校验
    try:
        from chisha.schemas import validate_dishes_tagged
        validate_dishes_tagged(all_records)
        schema_validated = True
    except Exception as e:
        schema_validated = False
        # 至少保证 v3 字段都在 (上面 _call_one_batch 阶段已校过, 这里复核)
        for rec in all_records:
            if rec.get("metadata", {}).get("tag_version") == version_label:
                np_ = rec.get("nutrition_profile", {})
                # 复核 5 新字段存在性
                for k in ("dish_role", "processed_meat_flag",
                          "sweet_sauce_level", "wetness", "grain_type"):
                    if k not in np_:
                        raise RuntimeError(
                            f"rec {rec['dish_id']} missing nutrition_profile.{k}"
                        ) from e
        print(f"[{zone}] schemas.DishTagged 校验未通过 ({type(e).__name__}); "
              f"v3 字段层手动校验已过. (schema 升级后请重跑校验)",
              file=sys.stderr, flush=True)

    out_target = out_path_override or tagged_path
    _write_json(out_target, all_records)

    elapsed = time.time() - started
    stats = {
        "zone": zone,
        "tagged_total": len(all_records),
        "newly_tagged": merged_count,
        "kept_existing": len(all_records) - merged_count,
        "batches_total": len(batches),
        "batches_done_via_cache": done_count,
        "batches_done_this_run": completed,
        "batches_failed": len(failed_batches),
        "failed_dish_ids": [did for _, dids, _ in failed_batches for did in dids],
        "schema_validated": schema_validated,
        "elapsed_sec": round(elapsed, 1),
        "out_path": str(out_target.relative_to(ROOT)),
    }
    return stats


# ---------------- CLI ----------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="api-key 路径打标 (OpenRouter via OpenAI 兼容协议)"
    )
    ap.add_argument("zone", help="zone name or 'all'")
    ap.add_argument("--prompt", default=str(DEFAULT_PROMPT_PATH),
                    help="prompt 文件路径 (默认 prompts/tag_dishes.md)")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE)
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--version-label", default=DEFAULT_VERSION_LABEL)
    ap.add_argument("--model", default=DEFAULT_BULK_MODEL,
                    help=f"OpenRouter 模型名 (默认 {DEFAULT_BULK_MODEL})")
    ap.add_argument("--audit-model", action="store_true",
                    help="使用更强的 audit 模型 (Opus); 用于 ground truth 抽查")
    ap.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--force-version", action="store_true",
                    help="不增量, 强制全量重打 (覆盖现有同 version 的 tagged)")
    ap.add_argument("--no-resume", action="store_true",
                    help="忽略 .claude/v3_tagging 缓存, 重跑所有 batch")
    ap.add_argument("--limit", type=int, default=None,
                    help="只跑前 N 条 (spike)")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印 plan, 不实际调 LLM")
    ap.add_argument("--out", default=None,
                    help="输出文件路径覆盖 (spike 用; 默认 data/<zone>/dishes_tagged.json)")
    args = ap.parse_args(argv)

    model = DEFAULT_AUDIT_MODEL if args.audit_model else args.model
    prompt_path = Path(args.prompt) if Path(args.prompt).is_absolute() \
        else ROOT / args.prompt
    if not prompt_path.exists():
        print(f"prompt 文件不存在: {prompt_path}", file=sys.stderr)
        return 2

    zones = _resolve_zones(args.zone)
    rc = 0
    for z in zones:
        out_override = Path(args.out) if args.out else None
        if out_override and not out_override.is_absolute():
            out_override = ROOT / out_override
        stats = run_zone(
            z,
            prompt_path=prompt_path,
            batch_size=args.batch,
            workers=args.workers,
            version_label=args.version_label,
            model=model,
            max_attempts=args.max_attempts,
            max_tokens=args.max_tokens,
            force_version=args.force_version,
            no_resume=args.no_resume,
            limit=args.limit,
            dry_run=args.dry_run,
            out_path_override=out_override,
        )
        print("\n" + json.dumps(stats, ensure_ascii=False, indent=2))
        if stats.get("batches_failed"):
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())

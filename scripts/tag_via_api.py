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
from chisha.loader import ingest_in_progress
from scripts.tag_dishes import (
    build_input_payload,
    extract_json_array,
    merge_into_output,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROMPT_PATH = ROOT / "prompts" / "tag_dishes.md"
JOBS_ROOT = ROOT / ".claude" / "v3_tagging"
FAILURES_LOG = ROOT / "logs" / "tag_failures.jsonl"

# batch=30/workers=16 实测对 deepseek-flash 会截断 (输出超 8192 token) + 限流 (空响应),
# home 重采实测 24/28 batch 挂; 降到 15/8 后 56 batch 0 失败 (D-101). refresh_from_collector
# 不显式传参, 依赖这两个默认 → 默认必须是稳定值。
DEFAULT_BATCH_SIZE = 15
DEFAULT_WORKERS = 8
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
    skip_ids: set[str] | None = None,
) -> list[dict]:
    if force_version:
        delta = list(raw)
    else:
        existing_ids = {
            d["dish_id"] for d in existing_tagged
            if d.get("metadata", {}).get("tag_version") == version_label
        }
        # skip_ids = 上次被 schema 越界隔离的 dish_id: temperature=0 重打多半同样越界,
        # 不重选可省 LLM + 破"重选→重隔离"循环 (Codex P1-A). --force-version 强制全打则不跳。
        skip_ids = skip_ids or set()
        delta = [d for d in raw
                 if d["dish_id"] not in existing_ids and d["dish_id"] not in skip_ids]
    if limit:
        delta = delta[:limit]
    return delta


def _make_batches(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


# raw 侧字段 (价格/销量/原名), 复用旧标签时刷新这些; cuisine/nutrition_profile 是 LLM 标签不动
_RAW_REFRESH_FIELDS = ("raw_name", "price", "monthly_sales")


def _rebuild_active(existing_tagged: list[dict],
                    raw_idx: dict[str, dict]) -> dict[str, dict]:
    """以当前 raw 重建活动 tagged (D-099.3):
    - 删 raw 中已消失的 dish_id (下架菜)
    - 复用旧营养/菜系标签, 但刷新 price/sales/raw_name 等 raw 字段
    返回 {dish_id: record}, 仅含 raw 里还存在的菜。
    """
    active: dict[str, dict] = {}
    for t in existing_tagged:
        did = t.get("dish_id")
        rd = raw_idx.get(did)
        if rd is None:
            continue  # prune: raw 里已没有这道菜
        rec = dict(t)
        for f in _RAW_REFRESH_FIELDS:
            if f in rd:
                rec[f] = rd[f]
        active[did] = rec
    return active


def _partition_valid(
    zone: str, all_records: list[dict]
) -> tuple[list[dict], list[dict]]:
    """逐条 DishTagged 校验, 拆成 (valid, bad). validate_dishes_tagged 纯 per-record,
    所以按单条 model_validate 拆分等价无遗漏。

    bad 记录 = 单条违规 (LLM 越界, 如非菜品漏网 → cooking_method='其他'). 全部逐条响亮告警,
    绝不静默吞 (codex BLOCK#5). 调用方把 valid 写 active、bad 写 quarantine: 一条越界不再
    阻塞整 zone 发布 (Codex 设计 review C), 但脏数据绝不进 live recall。"""
    from chisha.schemas import DishTagged
    valid: list[dict] = []
    bad: list[dict] = []
    for rec in all_records:
        try:
            DishTagged.model_validate(rec)
            valid.append(rec)
        except Exception as e:
            first = next((ln for ln in str(e).splitlines()[1:] if ln.strip()),
                         type(e).__name__)
            rec = dict(rec)
            rec["_quarantine_reason"] = first.strip()
            bad.append(rec)
    if bad:
        print(f"[{zone}] ✗ DishTagged 越界 {len(bad)} 条 → 隔离 (active 不收, valid {len(valid)} 条照发):",
              file=sys.stderr, flush=True)
        for rec in bad[:50]:
            print(f"    {rec.get('dish_id','<no-id>')} ({rec.get('raw_name','')!r}): "
                  f"{rec['_quarantine_reason']}", file=sys.stderr, flush=True)
        if len(bad) > 50:
            print(f"    ... 另有 {len(bad)-50} 条", file=sys.stderr, flush=True)
    return valid, bad


def _finalize_write(zone: str, all_records: list[dict], version_label: str,
                    tagged_path: Path, out_path_override: Path | None,
                    raw_idx: dict) -> tuple[Path, int, int]:
    """记录级隔离写盘 (Codex 设计 review C): valid → active dishes_tagged.json,
    越界 bad → `dishes_tagged.quarantine.json` (具名 + reason, 供人工/重打), 不静默丢。
    一条 LLM 越界不再 stage 整 zone (旧 all-or-nothing 会让 1 道脏菜阻塞全部发布);
    active 仍恒为 schema-valid (脏数据不进 live recall, 守住 BLOCK#5 安全不变量)。

    quarantine 文件**持久化合并** (Codex P1-A): 本轮 bad ∪ 旧隔离中 dish_id 仍在 raw 的条目
    (被 _select skip 不重打 → 本轮 all_records 不含它们, 不能因此从 quarantine 消失 → 否则
    下轮又重选成循环)。dish_id 不在 raw 的旧隔离 (已下架) 则清掉。
    返回 (写入路径, active 写入数, 当前隔离总数)."""
    valid, bad = _partition_valid(zone, all_records)
    if out_path_override:  # spike 模式: 写全集到指定位置 (供检视, 不动 active/不隔离)
        _write_json(out_path_override, all_records)
        return out_path_override, len(all_records), len(bad)
    _write_json(tagged_path, valid)
    valid_ids = {r["dish_id"] for r in valid}
    quarantine = tagged_path.with_suffix(".quarantine.json")
    merged: dict[str, dict] = {}
    if quarantine.exists():  # 留住仍在 raw 的旧隔离 (本轮被 skip 不重打的)
        for r in _read_json(quarantine):
            if r.get("dish_id") in raw_idx:
                merged[r["dish_id"]] = r
    for r in bad:  # 本轮新越界覆盖
        merged[r["dish_id"]] = r
    # 本轮成功进 active 的 (如 --force-version 重打后过校验) 必须出隔离, 否则既在 active 又在
    # quarantine + 下轮被 skip_ids 误跳 (Codex re-review Issue 1)。
    merged = {did: rec for did, rec in merged.items() if did not in valid_ids}
    if merged:
        _write_json(quarantine, list(merged.values()))
        print(f"[{zone}] 隔离共 {len(merged)} 条 (本轮新增 {len(bad)}) 写 {quarantine.name}; "
              f"active 收 {len(valid)} 条 valid。", file=sys.stderr, flush=True)
    else:
        quarantine.unlink(missing_ok=True)  # 无任何隔离 → 清掉过期文件, 防误读
    tagged_path.with_suffix(".staged.json").unlink(missing_ok=True)  # 退役旧 all-or-nothing staged
    return tagged_path, len(valid), len(merged)


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
    if ingest_in_progress(base):
        raise RuntimeError(
            f"[{zone}] 检测到 .ingest_lock (loader 发布中或上次未完成): "
            f"restaurants.json/dishes_raw.json 可能跨代混合, 拒绝打标。"
            f"请重跑 `python -m chisha.loader` 完成发布后再 tag。")
    raw = _read_json(base / "dishes_raw.json")
    rest_by_id = {r["id"]: r for r in _read_json(base / "restaurants.json")}

    tagged_path = base / "dishes_tagged.json"
    existing_tagged = _read_json(tagged_path) if tagged_path.exists() else []
    raw_idx = {d["dish_id"]: d for d in raw}

    # 上次隔离的越界菜 (非菜漏网): 默认不重选 (省 LLM + 破重隔离循环, Codex P1-A); force 时仍打。
    q_path = tagged_path.with_suffix(".quarantine.json")
    quarantined_ids = ({d["dish_id"] for d in _read_json(q_path)}
                       if q_path.exists() else set())
    delta = _select_dishes_to_tag(raw, existing_tagged, version_label,
                                  force_version, limit, skip_ids=quarantined_ids)
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
        # 无新菜也要重建活动集: 删消失菜 + 刷新 raw 字段 (D-099.3), 不能直接 bail
        active = _rebuild_active(existing_tagged, raw_idx)
        all_records = list(active.values())
        pruned = sum(1 for t in existing_tagged if t.get("dish_id") not in raw_idx)
        out_target, active_count, quarantined = _finalize_write(
            zone, all_records, version_label, tagged_path, out_path_override, raw_idx)
        print(f"[{zone}] 无新菜; 已重建活动集 (prune {pruned} 下架菜 + 刷新 raw 字段)",
              flush=True)
        return {"zone": zone, "tagged_total": active_count,
                "newly_tagged": 0, "pruned": pruned, "failed": 0,
                "quarantined_invalid": quarantined,
                "schema_validated": quarantined == 0,
                "out_path": str(out_target)}

    prompt_template = prompt_path.read_text(encoding="utf-8")

    # ---- 提前过滤已 done 的 batch (resume) ----
    todo_batches: list[tuple[int, list[dict]]] = []
    done_count = 0
    for idx, batch in enumerate(batches, start=1):
        out_path = jobs_dir / f"batch_{idx:04d}.out.json"
        if not no_resume and out_path.exists():
            try:
                cached = _read_json(out_path)
                # 缓存复用须绑精确有序 dish_id 清单 (非仅长度): 重采后批内菜变了就重跑 (D-099.3)
                if (isinstance(cached, list)
                        and [r.get("dish_id") for r in cached]
                        == [d["dish_id"] for d in batch]):
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

    # ---- 重建活动集 (prune 下架菜 + 刷新 raw) + 合并新 batch → dishes_tagged.json ----
    if force_version:
        combined: dict[str, dict] = {}
    else:
        combined = _rebuild_active(existing_tagged, raw_idx)

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
    out_target, active_count, quarantined = _finalize_write(
        zone, all_records, version_label, tagged_path, out_path_override, raw_idx)

    elapsed = time.time() - started
    stats = {
        "zone": zone,
        "tagged_total": active_count,  # 实际进 active 的 valid 数
        "newly_tagged": merged_count,
        "kept_existing": len(all_records) - merged_count,
        "batches_total": len(batches),
        "batches_done_via_cache": done_count,
        "batches_done_this_run": completed,
        "batches_failed": len(failed_batches),
        "failed_dish_ids": [did for _, dids, _ in failed_batches for did in dids],
        "quarantined_invalid": quarantined,
        "schema_validated": quarantined == 0,  # active 恒 valid; 此标=零越界隔离
        "elapsed_sec": round(elapsed, 1),
        "out_path": (str(out_target.relative_to(ROOT))
                     if out_target.is_relative_to(ROOT)
                     else str(out_target)),
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
        # 非零退出**仅**给真·batch 失败 (LLM 空/截断 → 需重试, 上层应 halt 重跑)。
        # quarantine (单条 schema 越界, 多是非菜漏网) 是 **degraded-success**: active 恒 valid,
        # 越界菜已写 quarantine 文件 + 跳过下次 delta (见 _select_dishes_to_tag), 不该阻塞编排器
        # 后续 backfill/validate (D-101 "一条越界不阻塞整 zone" 的编排器层兑现, Codex diff review P1-A)。
        if stats.get("batches_failed"):
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())

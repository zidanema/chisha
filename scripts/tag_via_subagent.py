"""subagent 路径的打标编排脚本 (无 LLM API key 场景).

工作流:
  1. uv run python -m scripts.tag_via_subagent prepare <zone>
     → 计算 delta = dishes_raw - dishes_tagged
     → 切批 50 条 / 批, 写 .claude/tag_jobs/<zone>/batch_NNN.in.json
     → 写 .claude/tag_jobs/<zone>/manifest.json

  2. 主会话 (Claude Code) 用 Agent tool spawn N 个 general-purpose subagent
     每个 subagent 读 batch_NNN.in.json + prompts/tag_dishes.md 规则
     → 写 batch_NNN.out.json

  3. uv run python -m scripts.tag_via_subagent merge <zone>
     → 读所有 batch_NNN.out.json
     → 过 chisha.schemas.DishTagged 校验
     → join raw 字段 (restaurant_id / raw_name / price / monthly_sales) + metadata
     → 合并到 data/<zone>/dishes_tagged.json
     → 更新 manifest 状态机 (pending → done / failed)
     → attempts == 3 仍失败的 dish_id 写 logs/tag_failures.jsonl

  4. uv run python -m scripts.tag_via_subagent status <zone>
     → 打印每批状态 + 进度

CLI flags:
  --batch N            每批菜品数 (默认 50, DESIGN §3.5 上限)
  --force-version      把现有 tagged 当 stale, 全部重打 (覆盖增量逻辑)
  --prune-stale        清理 dishes_raw 已删的 tagged 记录
  --version-label STR  打标版本号 (默认 v1-claude-code)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from chisha.schemas import validate_dishes_tagged
from scripts.tag_dishes import (
    build_input_payload,
    extract_json_array,
    merge_into_output,
    validate_record,
)

ROOT = Path(__file__).resolve().parent.parent
JOBS_ROOT = ROOT / ".claude" / "tag_jobs"
FAILURES_LOG = ROOT / "logs" / "tag_failures.jsonl"

MAX_ATTEMPTS = 3
DEFAULT_VERSION_LABEL = "v1-claude-code"
# subagent 路径默认 50 条/批 (DESIGN §3.5 上限). 主会话单 message 并发 16 个
# subagent → 单轮 16*50=800 条菜. 9000 条菜约 11-12 轮.
DEFAULT_BATCH_SIZE = 50
ZONES_ALL = ("home", "shenzhen-bay")


# ---------------- IO helpers ----------------

def _zone_data_dir(zone: str) -> Path:
    return ROOT / "data" / zone


def _zone_jobs_dir(zone: str) -> Path:
    return JOBS_ROOT / zone


def _manifest_path(zone: str) -> Path:
    return _zone_jobs_dir(zone) / "manifest.json"


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, obj: Any, indent: int = 2) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=indent),
                 encoding="utf-8")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _resolve_zones(zone_arg: str) -> list[str]:
    if zone_arg == "all":
        return list(ZONES_ALL)
    return [zone_arg]


# ---------------- prepare ----------------

def _build_batches(
    dishes_to_tag: list[dict],
    batch_size: int,
) -> list[list[dict]]:
    return [dishes_to_tag[i:i + batch_size]
            for i in range(0, len(dishes_to_tag), batch_size)]


def prepare_zone(
    zone: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    force_version: bool = False,
    prune_stale: bool = False,
    version_label: str = DEFAULT_VERSION_LABEL,
) -> dict:
    """切批 + 写 manifest. 返回新 manifest dict.

    增量逻辑:
      delta = dishes_raw 的 dish_id - dishes_tagged 已有的 dish_id (满足 tag_version 一致)
      --force-version: delta = 全部 dishes_raw (现有 tagged 视为 stale)
    """
    base = _zone_data_dir(zone)
    raw = _read_json(base / "dishes_raw.json")
    raw_by_id = {d["dish_id"]: d for d in raw}

    tagged_path = base / "dishes_tagged.json"
    existing_tagged = _read_json(tagged_path) if tagged_path.exists() else []
    # 增量跳过判定: 必须 dish_id 已有 + tag_version 与目标一致
    # 不同 version 的旧 tagged 视为 stale, 自动进 delta (无需 --force-version)
    existing_ids = {
        d["dish_id"] for d in existing_tagged
        if d.get("metadata", {}).get("tag_version") == version_label
    }

    if force_version:
        # 把所有现有 tagged 视为待重打
        delta_dishes = list(raw)
        stale_kept = []
    else:
        # 仅打标 raw 里有但 tagged (同 version) 里没有的
        delta_dishes = [d for d in raw if d["dish_id"] not in existing_ids]
        # raw 有 / tagged 有 → 保留 (除非 prune_stale)
        if prune_stale:
            stale_kept = [t for t in existing_tagged
                          if t["dish_id"] in raw_by_id]
        else:
            stale_kept = list(existing_tagged)

    batches_raw = _build_batches(delta_dishes, batch_size)

    jobs_dir = _zone_jobs_dir(zone)
    # 清理旧 manifest / 旧 batch 文件 (重新 prepare)
    if jobs_dir.exists():
        for f in jobs_dir.glob("batch_*.in.json"):
            f.unlink()
        for f in jobs_dir.glob("batch_*.out.json"):
            f.unlink()
    jobs_dir.mkdir(parents=True, exist_ok=True)

    # 写每批 .in.json
    rest_path = base / "restaurants.json"
    rest_by_id = {r["id"]: r for r in _read_json(rest_path)}

    manifest_batches = []
    for idx, batch in enumerate(batches_raw, start=1):
        in_path = jobs_dir / f"batch_{idx:03d}.in.json"
        out_path = jobs_dir / f"batch_{idx:03d}.out.json"
        # build_input_payload 返回 JSON string, 这里直接复用其语义但解开成 list
        items_str = build_input_payload(rest_by_id, batch)
        items = json.loads(items_str)
        _write_json(in_path, items)
        manifest_batches.append({
            "id": idx,
            "in_path": str(in_path.relative_to(ROOT)),
            "out_path": str(out_path.relative_to(ROOT)),
            "dish_ids": [d["dish_id"] for d in batch],
            "status": "pending",
            "attempts": 0,
            "last_error": None,
            "completed_at": None,
        })

    manifest = {
        "zone": zone,
        "batch_size": batch_size,
        "version_label": version_label,
        "force_version": force_version,
        "prune_stale": prune_stale,
        "created_at": _now_iso(),
        "stats": {
            "raw_total": len(raw),
            "existing_tagged_total": len(existing_tagged),
            "delta_to_tag": len(delta_dishes),
            "batches": len(batches_raw),
        },
        "kept_tagged_count": len(stale_kept),
        "batches": manifest_batches,
    }
    _write_json(_manifest_path(zone), manifest)
    # 同时保留 (force=False 路径) 的 stale_kept 给 merge 阶段无缝接续
    _write_json(jobs_dir / "kept_tagged.json", stale_kept)
    return manifest


# ---------------- merge ----------------

def _parse_subagent_output(text_or_obj: Any) -> list[dict]:
    """subagent 写入的 .out.json 应是 JSON array (DishTagged 字段子集).

    若 subagent 不小心把 LLM 文本 (带 ```json fence 或前后说明) 写进去, 兜底解析.
    """
    if isinstance(text_or_obj, list):
        return text_or_obj
    if isinstance(text_or_obj, str):
        return extract_json_array(text_or_obj)
    raise ValueError(f"unsupported out content type: {type(text_or_obj)}")


def _validate_subagent_batch(
    records: list[dict],
    expected_dish_ids: list[str],
) -> list[str]:
    """校验 subagent 输出 (返回 issues list, 空 = OK)."""
    issues: list[str] = []
    if len(records) != len(expected_dish_ids):
        issues.append(
            f"count mismatch: expected {len(expected_dish_ids)}, "
            f"got {len(records)}"
        )
        return issues  # 数量不对就别校验后面了
    got_ids = [r.get("dish_id") for r in records]
    if got_ids != expected_dish_ids:
        issues.append(
            f"dish_id order mismatch (first diverge at "
            f"{next((i for i, (a, b) in enumerate(zip(got_ids, expected_dish_ids)) if a != b), 0)})"
        )
    for r in records:
        per = validate_record(r)
        if per:
            issues.append(f"{r.get('dish_id')}: {per}")
    return issues


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


def merge_zone(
    zone: str,
) -> dict:
    """读所有 .out.json → schema 校验 → 合并 → 更新 manifest.

    幂等设计: 每次 merge 都从 manifest 里所有 done 批 + 新到达的 out 文件
    重建 combined, 写回 dishes_tagged.json. 多次跑 merge 结果一致.

    返回最终统计.
    """
    manifest = _read_json(_manifest_path(zone))
    version_label = manifest["version_label"]
    base = _zone_data_dir(zone)
    jobs_dir = _zone_jobs_dir(zone)

    raw_by_id = {d["dish_id"]: d for d in _read_json(base / "dishes_raw.json")}
    kept_tagged = _read_json(jobs_dir / "kept_tagged.json") \
        if (jobs_dir / "kept_tagged.json").exists() else []

    # ---- 步骤 1: 处理新到达的 out 文件, 更新 manifest 状态机 ----
    # 已 done 不重处理 (幂等); 已 failed 不再重试 (避免反复 attempts++ + 写重复 failure log)
    newly_done_this_run = 0
    for b in manifest["batches"]:
        if b["status"] in ("done", "failed"):
            continue
        out_path = ROOT / b["out_path"]
        if not out_path.exists():
            continue  # subagent 还没跑这批

        # 解析
        try:
            content = _read_json(out_path)
            recs = _parse_subagent_output(content)
        except Exception as e:
            b["attempts"] += 1
            b["last_error"] = f"parse: {e}"
            if b["attempts"] >= MAX_ATTEMPTS:
                b["status"] = "failed"
                _record_failure(zone, b["id"], b["dish_ids"], b["last_error"])
            continue

        # 校验
        issues = _validate_subagent_batch(recs, b["dish_ids"])
        if issues:
            b["attempts"] += 1
            b["last_error"] = "; ".join(issues)[:500]
            if b["attempts"] >= MAX_ATTEMPTS:
                b["status"] = "failed"
                _record_failure(zone, b["id"], b["dish_ids"], b["last_error"])
            continue

        b["status"] = "done"
        b["completed_at"] = _now_iso()
        b["last_error"] = None
        newly_done_this_run += 1

    # ---- 步骤 2: 幂等重建 combined ----
    if manifest.get("force_version"):
        combined: dict[str, dict] = {}
    else:
        combined = {t["dish_id"]: t for t in kept_tagged}

    for b in manifest["batches"]:
        if b["status"] != "done":
            continue
        out_path = ROOT / b["out_path"]
        recs = _parse_subagent_output(_read_json(out_path))
        merged = merge_into_output(raw_by_id, recs)
        for rec in merged:
            rec["metadata"]["tag_version"] = version_label
            combined[rec["dish_id"]] = rec

    all_records = list(combined.values())
    validate_dishes_tagged(all_records)

    out_path = base / "dishes_tagged.json"
    _write_json(out_path, all_records)
    _write_json(_manifest_path(zone), manifest)

    kept_count = len(kept_tagged) if not manifest.get("force_version") else 0
    done_count = sum(1 for b in manifest["batches"] if b["status"] == "done")
    new_count = len(all_records) - kept_count
    stats = {
        "zone": zone,
        "tagged_total": len(all_records),
        "newly_tagged": new_count,
        "kept_existing": kept_count,
        "newly_done_this_run": newly_done_this_run,
        "pending_batches": sum(
            1 for b in manifest["batches"] if b["status"] == "pending"
        ),
        "done_batches": done_count,
        "failed_batches": sum(
            1 for b in manifest["batches"] if b["status"] == "failed"
        ),
        "failed_dish_ids": [
            did for b in manifest["batches"] if b["status"] == "failed"
            for did in b["dish_ids"]
        ],
    }
    return stats


# ---------------- status ----------------

def status_zone(zone: str) -> dict:
    mp = _manifest_path(zone)
    if not mp.exists():
        return {"zone": zone, "manifest_exists": False}
    manifest = _read_json(mp)
    counts = {"pending": 0, "done": 0, "failed": 0}
    for b in manifest["batches"]:
        counts[b["status"]] = counts.get(b["status"], 0) + 1
    return {
        "zone": zone,
        "manifest_exists": True,
        "batches_total": len(manifest["batches"]),
        "stats": manifest["stats"],
        "by_status": counts,
        "version_label": manifest["version_label"],
        "force_version": manifest.get("force_version", False),
    }


# ---------------- CLI ----------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _add_zone(p: argparse.ArgumentParser) -> None:
        p.add_argument("zone", help="zone name or 'all'")

    p_prep = sub.add_parser("prepare")
    _add_zone(p_prep)
    p_prep.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE)
    p_prep.add_argument("--force-version", action="store_true")
    p_prep.add_argument("--prune-stale", action="store_true")
    p_prep.add_argument("--version-label", default=DEFAULT_VERSION_LABEL)

    p_merge = sub.add_parser("merge")
    _add_zone(p_merge)

    p_status = sub.add_parser("status")
    _add_zone(p_status)

    args = ap.parse_args(argv)
    zones = _resolve_zones(args.zone)

    if args.cmd == "prepare":
        for z in zones:
            m = prepare_zone(
                z,
                batch_size=args.batch,
                force_version=args.force_version,
                prune_stale=args.prune_stale,
                version_label=args.version_label,
            )
            print(f"[prepare {z}] delta={m['stats']['delta_to_tag']} "
                  f"batches={m['stats']['batches']} "
                  f"(raw={m['stats']['raw_total']}, "
                  f"existing_tagged={m['stats']['existing_tagged_total']})")
    elif args.cmd == "merge":
        for z in zones:
            s = merge_zone(z)
            print(f"[merge {z}] tagged_total={s['tagged_total']} "
                  f"new={s['newly_tagged']} kept={s['kept_existing']} "
                  f"done={s['done_batches']} pending={s['pending_batches']} "
                  f"failed={s['failed_batches']}")
            if s["failed_dish_ids"]:
                print(f"  failed dish_ids "
                      f"({len(s['failed_dish_ids'])}): "
                      f"{s['failed_dish_ids'][:10]}...")
    elif args.cmd == "status":
        for z in zones:
            s = status_zone(z)
            print(json.dumps(s, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

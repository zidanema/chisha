"""一次性迁移: 旧位置 id (r_NNN/d_NNN_MMM) → 稳定哈希 id (D-099).

把旧 dishes_tagged 的营养/菜系标签按 (新 rid, 新 dish_id) 重映射到新 id, 免重打 22k+8k 菜。
feedback store / meal_log 已空 → 不迁 runtime log, 迁移只剩"标签重映射"。

流程 (codex pressure-test 收敛的 7 步):
1. ingest 前把旧 data/<zone>/{restaurants,dishes_raw,dishes_tagged}.json 快照到不可变备份。
2. 跑新 loader (write_normalized) → 新 active raw + quarantine (冲突菜不进 active raw)。
3. 对旧 tagged 用与新 loader 完全相同的 rid/alias 规则算新 dish_id。
4. 按新 dish_id 建 legacy 标签索引; 同一新 dish_id 收到多条**不同** label payload → ambiguous。
5. 仅对当前 active raw 中存在 (且非 quarantine, 即没进 active raw) 的 dish_id 复用标签。
6. ambiguous 的不自动迁移, 报告, 留给 tag_via_api 增量重打。
7. price/sales/raw_name 来自新 raw; 旧记录只贡献 cuisine + nutrition_profile + canonical_name。

用法:
    # 先单独跑一次 loader 让它写冲突报告并 block (不发布); 审阅后把冲突 key 加进
    #   data/<zone>/conflicts_ack.json 再跑本脚本 (本脚本会重新跑 loader 发布)。
    uv run python -m scripts.migrate_stable_ids all [--dry-run]
    # 迁移后跑 tag_via_api 增量补缺:  uv run python -m scripts.tag_via_api all
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

from chisha.loader import (
    dish_id_for, load_aliases, write_normalized, normalize, load_raw,
    ingest_in_progress, _resolve_rid,
)

ROOT = Path(__file__).resolve().parent.parent
ZONES_ALL = ("shenzhen-bay", "home")
# 旧 tagged 里属于 LLM 标签的字段 (迁移复用); 其余 raw 字段从新 raw 刷新
_LABEL_FIELDS = ("canonical_name", "cuisine", "nutrition_profile", "metadata")


def _read(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _label_payload(rec: dict) -> dict:
    """LLM 标签部分 (用于判等; metadata 里 tag_version 等保留, 但不参与判等)."""
    return {
        "canonical_name": rec.get("canonical_name"),
        "cuisine": rec.get("cuisine"),
        "nutrition_profile": rec.get("nutrition_profile"),
    }


def _payload_key(rec: dict) -> str:
    return json.dumps(_label_payload(rec), ensure_ascii=False, sort_keys=True)


def build_legacy_index(old_tagged: list[dict], old_rid_to_name: dict[str, str],
                       aliases: dict[str, str]) -> tuple[dict[str, dict], list[str], int]:
    """旧 tagged → 新 dish_id 的 legacy 标签索引。
    同一新 dish_id 收到多条**不同** payload (旧重复店标签不一致) → ambiguous, 不猜不复用。
    返回 (legacy{new_did:rec}, ambiguous[new_did...], skipped_no_old_name)."""
    by_new_did: dict[str, list[dict]] = {}
    skipped = 0
    for t in old_tagged:
        old_name = old_rid_to_name.get(t.get("restaurant_id"))
        if not old_name:
            skipped += 1
            continue
        new_rid = _resolve_rid(old_name, aliases)
        try:
            new_did = dish_id_for(new_rid, t.get("raw_name", ""))
        except ValueError:
            continue  # 旧菜名归一化后空, 跳过
        by_new_did.setdefault(new_did, []).append(t)
    ambiguous: list[str] = []
    legacy: dict[str, dict] = {}
    for new_did, recs in by_new_did.items():
        if len({_payload_key(r) for r in recs}) > 1:
            ambiguous.append(new_did)
            continue
        legacy[new_did] = recs[0]
    return legacy, ambiguous, skipped


def seed_record(src: dict, rd: dict) -> dict:
    """复用旧标签 (cuisine/nutrition/canonical) + 刷新 raw 字段 + is_available=True (在 active raw=上架)."""
    rec = {k: src.get(k) for k in _LABEL_FIELDS}
    rec["dish_id"] = rd["dish_id"]
    rec["restaurant_id"] = rd["restaurant_id"]
    rec["raw_name"] = rd["raw_name"]
    rec["price"] = rd["price"]
    rec["monthly_sales"] = rd["monthly_sales"]
    meta = dict(src.get("metadata") or {})
    meta["is_available"] = True  # 不沿用旧下架状态 (codex BLOCK#4)
    rec["metadata"] = meta
    return rec


def migrate_zone(zone: str, snapshot_root: Path, *, dry_run: bool) -> dict:
    base = ROOT / "data" / zone
    if ingest_in_progress(base):
        return {"zone": zone, "aborted": True,
                "reason": "检测到 .ingest_lock (上次 loader 发布未完成); "
                          "先重跑 loader 收尾再迁移"}
    aliases = load_aliases(ROOT / "data" / "aliases.json")

    # --- 1. 快照旧数据 (在 loader 覆盖 active 之前) ---
    snap = snapshot_root / zone
    snap.mkdir(parents=True, exist_ok=True)
    old_rest_path = base / "restaurants.json"
    old_tagged_path = base / "dishes_tagged.json"
    for fn in ("restaurants.json", "dishes_raw.json", "dishes_tagged.json"):
        src = base / fn
        if src.exists():
            shutil.copy2(src, snap / fn)
    old_restaurants = _read(snap / "restaurants.json")
    old_tagged = _read(snap / "dishes_tagged.json") if (snap / "dishes_tagged.json").exists() else []
    old_rid_to_name = {r["id"]: r["name"] for r in old_restaurants}

    # --- 2. 算新 active 集 (normalize 的 dishes 已剔冲突, 与发布结果一致) ---
    #     dry_run 只在内存算, 绝不写 active; 非 dry_run 才 write_normalized 发布。
    raw_path = (Path.home() / "waimai_data" / "output" /
                ("office_restaurants.json" if zone == "shenzhen-bay"
                 else "home_restaurants.json"))
    raw = load_raw(raw_path)
    _, new_raw, _conflicts = normalize(raw, office_zone=zone, aliases=aliases)
    new_raw_idx = {d["dish_id"]: d for d in new_raw}
    new_ids = set(new_raw_idx)
    if not dry_run:
        stats = write_normalized(raw_path, base, zone)
        if not stats["published"]:
            return {"zone": zone, "aborted": True,
                    "reason": f"loader 未发布 ({stats['unacknowledged']} 未确认冲突); "
                              f"先审阅 dish_id_conflicts.json 并 ack 再迁移",
                    "loader": stats}

    # --- 3+4. 旧 tagged → 新 dish_id, 建 legacy 索引 (多 payload 不一致 → ambiguous) ---
    legacy, ambiguous, skipped_no_name = build_legacy_index(
        old_tagged, old_rid_to_name, aliases)

    # --- 5+6+7. 仅对 active raw 中存在的 dish_id 复用; 刷新 raw 字段 + is_available ---
    seeded: list[dict] = []
    for new_did in new_ids:
        src = legacy.get(new_did)
        if src is None:
            continue  # 无旧标签可复用 → 留 tag_via_api 增量打
        seeded.append(seed_record(src, new_raw_idx[new_did]))

    needs_tagging = len(new_ids) - len(seeded)
    result = {
        "zone": zone,
        "old_tagged": len(old_tagged),
        "new_active_dishes": len(new_ids),
        "seeded_from_legacy": len(seeded),
        "ambiguous_skipped": len(ambiguous),
        "skipped_no_old_name": skipped_no_name,
        "needs_tagging_after": needs_tagging,
        "snapshot": str(snap.relative_to(ROOT)),
        "dry_run": dry_run,
    }
    if not dry_run:
        # 重排字段顺序贴近原 schema (dish_id/restaurant_id/raw_name 在前)
        ordered = [{
            "dish_id": r["dish_id"], "restaurant_id": r["restaurant_id"],
            "raw_name": r["raw_name"], "canonical_name": r.get("canonical_name"),
            "price": r["price"], "monthly_sales": r["monthly_sales"],
            "cuisine": r.get("cuisine"), "nutrition_profile": r.get("nutrition_profile"),
            "metadata": r.get("metadata"),
        } for r in seeded]
        _write(old_tagged_path, ordered)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="一次性稳定 id 迁移 (D-099)")
    ap.add_argument("zone", help="zone name or 'all'")
    ap.add_argument("--dry-run", action="store_true",
                    help="只算不写 dishes_tagged (但仍会跑 loader 发布 active raw)")
    args = ap.parse_args(argv)

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot_root = ROOT / "data" / f"_migration_snapshot_{ts}"
    zones = list(ZONES_ALL) if args.zone == "all" else [args.zone]

    rc = 0
    for z in zones:
        res = migrate_zone(z, snapshot_root, dry_run=args.dry_run)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        if res.get("aborted"):
            rc = 3
    print(f"\n快照: {snapshot_root.relative_to(ROOT)} (不可变备份, 可手动删)")
    print("下一步: uv run python -m scripts.tag_via_api all  # 增量补 needs_tagging")
    return rc


if __name__ == "__main__":
    sys.exit(main())

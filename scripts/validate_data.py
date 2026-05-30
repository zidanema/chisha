"""数据完整性校验: schema + 引用完整性 + 唯一性 + 打标进度.

检查项 (失败用 ✗, 警告用 [warn]):
  1. dishes_tagged.json 每条过 DishTagged schema
  2. restaurants.id 唯一; dishes_raw/tagged 的 dish_id 唯一
  3. 引用完整性: 每条 dish.restaurant_id ∈ restaurants.id
  4. 反向: 没有 raw 菜的店 (collector 漏抓菜单?) / 没有 tagged 菜的店 ([warn])
  5. tagged ⊄ raw 的 stale 残留 (打标后 raw 又删了菜)
  6. 打标进度报告 (coverage %)

用法:
    uv run python -m scripts.validate_data            # 默认 all zone
    uv run python -m scripts.validate_data home
    uv run python -m scripts.validate_data --strict   # warning 也算 fail (CI 用)

exit code: 0 = OK; 1 = 有 hard 失败; --strict 下 warning 也返 1.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from chisha.schemas import validate_dishes_tagged
from scripts._common import (
    ZONES_ALL,
    read_json as _read_json,
    resolve_zones as _resolve_zones,
)

ROOT = Path(__file__).resolve().parent.parent


def check_zone(zone: str) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings). errors 非空即 hard 失败."""
    base = ROOT / "data" / zone
    errors: list[str] = []
    warnings: list[str] = []

    rests_path = base / "restaurants.json"
    raw_path = base / "dishes_raw.json"
    tagged_path = base / "dishes_tagged.json"

    if not rests_path.exists():
        return [f"missing: {rests_path.relative_to(ROOT)}"], []
    if not raw_path.exists():
        return [f"missing: {raw_path.relative_to(ROOT)}"], []

    rests = _read_json(rests_path)
    raw = _read_json(raw_path)
    tagged = _read_json(tagged_path) if tagged_path.exists() else []

    # 1. schema check
    if tagged:
        try:
            validate_dishes_tagged(tagged)
        except Exception as e:
            errors.append(f"schema fail on dishes_tagged.json: "
                          f"{type(e).__name__}: {str(e)[:300]}")

    # 2. uniqueness
    rest_ids = [r["id"] for r in rests]
    dup_rests = [k for k, v in Counter(rest_ids).items() if v > 1]
    if dup_rests:
        errors.append(f"duplicate restaurant_id: {dup_rests[:5]}")

    raw_dish_ids = [d["dish_id"] for d in raw]
    dup_raw = [k for k, v in Counter(raw_dish_ids).items() if v > 1]
    if dup_raw:
        errors.append(f"duplicate dish_id in dishes_raw: "
                      f"{dup_raw[:5]} ({len(dup_raw)} total)")

    tagged_dish_ids = [d["dish_id"] for d in tagged]
    dup_tag = [k for k, v in Counter(tagged_dish_ids).items() if v > 1]
    if dup_tag:
        errors.append(f"duplicate dish_id in dishes_tagged: "
                      f"{dup_tag[:5]} ({len(dup_tag)} total)")

    # 3. 引用完整性: dish.restaurant_id 必须在 restaurants 里
    rest_id_set = set(rest_ids)
    orphan_raw_rids = sorted({
        d["restaurant_id"] for d in raw
        if d["restaurant_id"] not in rest_id_set
    })
    if orphan_raw_rids:
        errors.append(f"raw dishes reference {len(orphan_raw_rids)} unknown "
                      f"restaurant_id(s): {orphan_raw_rids[:5]}")

    orphan_tag_rids = sorted({
        d["restaurant_id"] for d in tagged
        if d["restaurant_id"] not in rest_id_set
    })
    if orphan_tag_rids:
        errors.append(f"tagged dishes reference {len(orphan_tag_rids)} "
                      f"unknown restaurant_id(s): {orphan_tag_rids[:5]}")

    # 4. 反向: 餐厅没有任何菜
    rest_with_raw = {d["restaurant_id"] for d in raw}
    dead_in_raw = sorted(rest_id_set - rest_with_raw)
    if dead_in_raw:
        # raw 都没菜是 collector 抓菜单失败, 算 error
        errors.append(f"{len(dead_in_raw)} restaurant(s) have 0 raw dishes "
                      f"(collector dropped menu?): {dead_in_raw[:5]}")

    if tagged:
        rest_with_tag = {d["restaurant_id"] for d in tagged}
        dead_in_tag = sorted(rest_id_set - rest_with_tag)
        # tag 没菜可能是 pre-filter 全过滤 (无可消费菜), warning 即可
        if dead_in_tag:
            warnings.append(f"{len(dead_in_tag)} restaurant(s) have 0 tagged "
                            f"dishes (all pre-filtered?): {dead_in_tag[:5]}")

    # 5. stale tagged: tagged 里出现 raw 已删的 dish_id
    raw_dish_id_set = set(raw_dish_ids)
    tagged_dish_id_set = set(tagged_dish_ids)
    stale_tag = sorted(tagged_dish_id_set - raw_dish_id_set)
    if stale_tag:
        warnings.append(f"{len(stale_tag)} tagged dish(es) not in raw "
                        f"(stale, run tag_via_subagent prepare --prune-stale): "
                        f"{stale_tag[:5]}")

    # 6. raw_menu_count vs 实际 raw dish 数 (店级对账)
    raw_count_by_rest: dict[str, int] = Counter(d["restaurant_id"] for d in raw)
    menu_count_mismatch = []
    for r in rests:
        declared = r.get("raw_menu_count", 0) or 0
        actual = raw_count_by_rest.get(r["id"], 0)
        # 只在 declared > 0 且差异 >20% 时报 (collector 偶尔少抓 1-2 道菜可接受)
        if declared > 0 and actual > 0:
            diff_ratio = abs(declared - actual) / declared
            if diff_ratio > 0.2:
                menu_count_mismatch.append(
                    f"{r['id']} {r['name'][:20]}: declared={declared} actual={actual}"
                )
    if menu_count_mismatch:
        warnings.append(f"{len(menu_count_mismatch)} restaurant(s) raw_menu_count "
                        f"vs actual mismatch >20%: {menu_count_mismatch[:3]}")

    # 7. 打标覆盖率报告
    coverage = (
        len(tagged_dish_id_set & raw_dish_id_set) / len(raw_dish_id_set)
        if raw_dish_id_set else 0.0
    )

    # ---- 打印摘要 ----
    print(f"\n[{zone}]")
    print(f"  restaurants:    {len(rests)}")
    print(f"  dishes_raw:     {len(raw)}")
    print(f"  dishes_tagged:  {len(tagged)} "
          f"({coverage*100:.1f}% of raw)")
    print(f"  untagged:       {len(raw_dish_id_set - tagged_dish_id_set)}")
    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("zone", nargs="?", default="all",
                    help="zone name or 'all' (default: all)")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors (for CI)")
    args = ap.parse_args()

    zones = _resolve_zones(args.zone)

    all_errors: dict[str, list[str]] = {}
    all_warnings: dict[str, list[str]] = {}
    for z in zones:
        try:
            errs, warns = check_zone(z)
        except Exception as e:
            errs, warns = [f"check_zone crashed: {type(e).__name__}: {e}"], []
        if errs:
            all_errors[z] = errs
        if warns:
            all_warnings[z] = warns

    print()
    for z, warns in all_warnings.items():
        for w in warns:
            print(f"  [warn] [{z}] {w}")
    for z, errs in all_errors.items():
        for e in errs:
            print(f"  ✗ [{z}] {e}")

    n_err = sum(len(v) for v in all_errors.values())
    n_warn = sum(len(v) for v in all_warnings.values())
    print()
    if n_err:
        print(f"✗ FAIL: {n_err} error(s), {n_warn} warning(s) across "
              f"{len(zones)} zone(s)")
        return 1
    if n_warn and args.strict:
        print(f"✗ FAIL (--strict): {n_warn} warning(s)")
        return 1
    if n_warn:
        print(f"✓ OK with {n_warn} warning(s)")
    else:
        print(f"✓ OK across {len(zones)} zone(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

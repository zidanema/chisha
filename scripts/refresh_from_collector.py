"""collector → chisha 重消费编排 + 跨 zone 采址污染哨兵 (B3, D3/D5).

串 preflight(契约校验 + 指纹哨兵) → loader(发布) → tag → backfill → validate;
任一步失败非 0 退出。collector label → chisha zone 映射 (D5, 消费端语义) 内置于此。

时序 (Codex 设计 review Q6): 校验 raw → 哨兵 → publish → tag/backfill → validate。
哨兵必须在 write_normalized 替换 active 文件**之前**跑, 否则污染已发布拦不住。

用法:
  uv run python -m scripts.refresh_from_collector                  # 自动探测 + 全链路
  uv run python -m scripts.refresh_from_collector --labels office  # 只刷 office
  uv run python -m scripts.refresh_from_collector --skip-tag       # 只跑 preflight+哨兵+loader (调试/省 LLM)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from chisha.collector_contract import ContractViolation
from chisha.loader import (
    backfill_restaurant_category,
    load_raw,
    normalize_shop_name_v1,
    restaurant_rid,
    write_normalized,
)

# D5: collector label → chisha zone (消费端语义, producer 不该拥有此映射)。
ZONE_MAP = {"office": "shenzhen-bay", "home": "home"}

DEFAULT_COLLECTOR_OUTPUT = os.path.expanduser("~/waimai_data/output")
CHISHA_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = CHISHA_ROOT / "data"

# D3 指纹哨兵阈值 (区分"正常跨 zone 同店共享 rid, D-099.2 允许" vs "G 式全量克隆")。
HARD_FAIL_MIN_SHARED = 30
HARD_FAIL_RID_SHARE_RATE = 0.80
HARD_FAIL_DIST_EQ_RATE = 0.80
WARN_MIN_SHARED = 20
WARN_DIST_EQ_RATE = 0.50


class SentinelError(Exception):
    """跨 zone 指纹哨兵 hard-fail (疑似采址污染 / 全量克隆, 如断裂点 G)。"""


# ============================================================
# 指纹哨兵 (纯函数, 可单测)
# ============================================================
def _rids(raw: dict) -> set[str]:
    """raw → 去重 rid 集 (跳过归一化后空名)。"""
    return {restaurant_rid(r["name"]) for r in raw.get("restaurants", [])
            if normalize_shop_name_v1(r.get("name", ""))}


def _rid_to_distance(raw: dict) -> dict[str, str]:
    """rid → 代表 distance 字符串 (同 rid 多行取首个非空)。"""
    out: dict[str, str] = {}
    for r in raw.get("restaurants", []):
        if not normalize_shop_name_v1(r.get("name", "")):
            continue
        rid = restaurant_rid(r["name"])
        dist = (r.get("distance") or "").strip()
        if rid not in out or (not out[rid] and dist):
            out[rid] = dist
    return out


def cross_zone_fingerprint(label_a: str, raw_a: dict,
                           label_b: str, raw_b: dict) -> dict:
    """两 zone 指纹: 共享 rid / rid 共享率 / distance 逐字相同率 / label 是否不同 → verdict.

    - rid 共享率分母 = min(两 zone 去重 rid 数) (Codex Q3: 检测"较小 zone 被整体克隆")。
    - distance 相同率只在两边均有非空 distance 的共享 rid 上算 (Codex Q3: 否则双缺被误判相同)。
    """
    rids_a, rids_b = _rids(raw_a), _rids(raw_b)
    shared = rids_a & rids_b
    shared_n = len(shared)
    denom = min(len(rids_a), len(rids_b)) or 1
    rid_share_rate = shared_n / denom

    da, db = _rid_to_distance(raw_a), _rid_to_distance(raw_b)
    both = [rid for rid in shared if da.get(rid) and db.get(rid)]
    eq = sum(1 for rid in both if da[rid] == db[rid])
    dist_eq_rate = (eq / len(both)) if both else 0.0

    labels_differ = (raw_a.get("location", {}).get("label")
                     != raw_b.get("location", {}).get("label"))

    verdict = "ok"
    if shared_n >= WARN_MIN_SHARED and dist_eq_rate >= WARN_DIST_EQ_RATE:
        verdict = "warn"
    if (shared_n >= HARD_FAIL_MIN_SHARED
            and rid_share_rate >= HARD_FAIL_RID_SHARE_RATE
            and dist_eq_rate >= HARD_FAIL_DIST_EQ_RATE
            and labels_differ):
        verdict = "hard_fail"

    return {
        "labels": [label_a, label_b],
        "shared": shared_n,
        "rid_share_rate": round(rid_share_rate, 3),
        "distance_equal_rate": round(dist_eq_rate, 3),
        "distance_compared": len(both),
        "labels_differ": labels_differ,
        "verdict": verdict,
    }


def run_sentinel(raws: dict[str, dict]) -> list[dict]:
    """对所有 zone 两两跑哨兵; 任一 hard_fail → raise SentinelError。<2 zone → 返回空 (跳过)。"""
    labels = sorted(raws)
    results: list[dict] = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            results.append(cross_zone_fingerprint(
                labels[i], raws[labels[i]], labels[j], raws[labels[j]]))
    hard = [r for r in results if r["verdict"] == "hard_fail"]
    if hard:
        raise SentinelError(
            "跨 zone 指纹哨兵 hard-fail (疑似采址污染 / 全量克隆, 如断裂点 G):\n"
            + "\n".join(str(r) for r in hard))
    return results


# ============================================================
# 编排
# ============================================================
def _run_subprocess(args: list[str], desc: str) -> None:
    print(f"[refresh] {desc}: {' '.join(args)}", flush=True)
    r = subprocess.run(args)
    if r.returncode != 0:
        print(f"[refresh] {desc} 失败 (exit {r.returncode})", file=sys.stderr)
        sys.exit(r.returncode)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="collector→chisha 重消费编排 + 跨 zone 采址污染哨兵")
    ap.add_argument("--collector-output", default=DEFAULT_COLLECTOR_OUTPUT,
                    help=f"collector output 目录 (默认 {DEFAULT_COLLECTOR_OUTPUT})")
    ap.add_argument("--labels", nargs="*", default=None,
                    help="要刷的 collector label (默认: 自动探测 output 里存在的)")
    ap.add_argument("--skip-tag", action="store_true",
                    help="只跑 preflight+哨兵+loader, 跳过 tag/backfill/validate (调试/省 LLM)")
    args = ap.parse_args(argv)

    out_root = Path(args.collector_output)
    labels = args.labels or [lbl for lbl in ZONE_MAP
                             if (out_root / f"{lbl}_restaurants.json").exists()]
    if not labels:
        print(f"[refresh] {out_root} 下无 collector 输出, 无事可做", file=sys.stderr)
        return 1
    bad = [lbl for lbl in labels if lbl not in ZONE_MAP]
    if bad:
        print(f"[refresh] 未知 label {bad} (已知: {sorted(ZONE_MAP)})", file=sys.stderr)
        return 1

    # 1. preflight 契约校验 (load_raw 窄契约 + 版本断言) —— 校验后才能跑哨兵 (Q6)
    raws: dict[str, dict] = {}
    for lbl in labels:
        path = out_root / f"{lbl}_restaurants.json"
        try:
            raws[lbl] = load_raw(path)
        except ContractViolation as e:
            print(f"[refresh] {lbl} 契约校验失败:\n{e}", file=sys.stderr)
            return 2
        print(f"[refresh] {lbl}: 契约 OK, {len(raws[lbl].get('restaurants', []))} 店",
              flush=True)

    # 2. 指纹哨兵 (在 publish 之前)
    try:
        fps = run_sentinel(raws)
    except SentinelError as e:
        print(f"[refresh] {e}", file=sys.stderr)
        return 3
    for fp in fps:
        tag = "⚠ WARN" if fp["verdict"] == "warn" else "ok"
        print(f"[refresh] 哨兵 {fp['labels']}: shared={fp['shared']} "
              f"rid_share={fp['rid_share_rate']} dist_eq={fp['distance_equal_rate']}"
              f"(n={fp['distance_compared']}) → {tag}", flush=True)
    if len(labels) < 2:
        print("[refresh] ⚠ 仅 1 个 zone present, 跳过跨 zone 哨兵 "
              "(重采另一 zone 后才能比对采址污染)", flush=True)

    # 3a. 先 publish 全部 zone (cheap + local; 任一未发布即 fail-fast,
    #     避免某 zone publish 失败时另一 zone 已白烧昂贵的 LLM tag —— Codex S-2 分两轮)
    for lbl in labels:
        zone = ZONE_MAP[lbl]
        out_dir = DATA_DIR / zone
        path = out_root / f"{lbl}_restaurants.json"
        stats = write_normalized(path, out_dir, zone)
        if not stats["published"]:
            print(f"[refresh] {zone} 未发布: {stats['unacknowledged']} 个未确认冲突, "
                  f"审阅 {out_dir}/dish_id_conflicts.json 后把 key 加进 "
                  f"{out_dir}/conflicts_ack.json 再重跑", file=sys.stderr)
            return 4
        print(f"[refresh] {zone}: 发布 {stats['restaurants']} 店 / "
              f"{stats['dishes']} 菜 ({stats['quarantined']} 隔离)", flush=True)

    if args.skip_tag:
        print("[refresh] --skip-tag: 跳过 tag/backfill/validate", flush=True)
        print("[refresh] ✓ 完成 (preflight + 哨兵 + 发布)", flush=True)
        return 0

    # 3b. 全部 publish 成功后, 再逐 zone tag (昂贵 LLM) + backfill
    for lbl in labels:
        zone = ZONE_MAP[lbl]
        out_dir = DATA_DIR / zone
        _run_subprocess([sys.executable, "-m", "scripts.tag_via_api", zone],
                        f"{zone} 打标")
        n = backfill_restaurant_category(out_dir / "restaurants.json",
                                         out_dir / "dishes_tagged.json")
        print(f"[refresh] {zone}: 回填 {n} 店 category", flush=True)

    # 4. validate (subprocess —— validate_data.main() 不收 argv, Codex Q5)
    _run_subprocess([sys.executable, "-m", "scripts.validate_data"], "校验")
    print("[refresh] ✓ 全部完成", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

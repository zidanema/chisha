"""D-072.1 严格回归比对: tmp/baseline_traces/ vs tmp/baseline_traces_after/.

Codex Round 2 blindspot-1 要求明确断言层级:
  - top60 combo 顺序完全一致 (rname + dish_ids 签名)
  - 每个 combo 的 16 维 breakdown |delta| < 1e-6
  - 总 score |delta| < 1e-6

任何 diff → exit 1 + 详细报错. 全过 → exit 0.

用法:
  uv run python -m scripts.compare_traces
  uv run python -m scripts.compare_traces --before-dir tmp/X --after-dir tmp/Y
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EPSILON = 1e-6


def diff_combo(idx: int, before: dict, after: dict) -> list[str]:
    """对比单个 combo 签名. 返回 diff 消息列表 (空 = 一致)."""
    msgs: list[str] = []
    # 餐厅签名: rname + dish_ids 必须 100% 一致
    if before.get("rname") != after.get("rname"):
        msgs.append(
            f"  combo[{idx}] rname 不一致: {before.get('rname')!r} → {after.get('rname')!r}"
        )
    if before.get("dish_ids") != after.get("dish_ids"):
        msgs.append(
            f"  combo[{idx}] dish_ids 不一致: {before.get('dish_ids')} → {after.get('dish_ids')}"
        )
    # 总 score 浮点 |delta| < eps
    score_delta = abs(float(before.get("score", 0)) - float(after.get("score", 0)))
    if score_delta >= EPSILON:
        msgs.append(
            f"  combo[{idx}] score |delta|={score_delta:.9f} >= {EPSILON} "
            f"({before.get('score')} → {after.get('score')})"
        )
    # breakdown 每维 |delta| < eps
    before_br = before.get("breakdown") or {}
    after_br = after.get("breakdown") or {}
    all_keys = set(before_br) | set(after_br)
    for k in sorted(all_keys):
        if k not in before_br:
            msgs.append(f"  combo[{idx}] breakdown 新增 key {k!r}")
            continue
        if k not in after_br:
            msgs.append(f"  combo[{idx}] breakdown 缺失 key {k!r}")
            continue
        d = abs(float(before_br[k]) - float(after_br[k]))
        if d >= EPSILON:
            msgs.append(
                f"  combo[{idx}] breakdown.{k} |delta|={d:.9f} >= {EPSILON} "
                f"({before_br[k]} → {after_br[k]})"
            )
    return msgs


def compare_snapshot(before_path: Path, after_path: Path) -> tuple[bool, list[str]]:
    before = json.loads(before_path.read_text(encoding="utf-8"))
    after = json.loads(after_path.read_text(encoding="utf-8"))
    msgs: list[str] = []
    # 元信息一致
    for k in ("meal_type", "zone", "today", "daily_mood",
              "n_combos_recalled", "n_ranked", "n_after_caps"):
        if before.get(k) != after.get(k):
            msgs.append(f"  meta.{k} 不一致: {before.get(k)!r} → {after.get(k)!r}")
    before_combos = before.get("top_combos") or []
    after_combos = after.get("top_combos") or []
    if len(before_combos) != len(after_combos):
        msgs.append(
            f"  top_combos 长度不一致: {len(before_combos)} → {len(after_combos)}"
        )
    n = min(len(before_combos), len(after_combos))
    for i in range(n):
        msgs.extend(diff_combo(i, before_combos[i], after_combos[i]))
    return (len(msgs) == 0, msgs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before-dir", default="tmp/baseline_traces")
    ap.add_argument("--after-dir", default="tmp/baseline_traces_after")
    args = ap.parse_args()

    root = Path(".").resolve()
    before_dir = root / args.before_dir
    after_dir = root / args.after_dir

    if not before_dir.exists():
        print(f"[fail] before-dir 不存在: {before_dir}")
        sys.exit(2)
    if not after_dir.exists():
        print(f"[fail] after-dir 不存在: {after_dir}")
        sys.exit(2)

    before_files = sorted(p.name for p in before_dir.glob("snap_*.json"))
    after_files = sorted(p.name for p in after_dir.glob("snap_*.json"))
    if before_files != after_files:
        print("[fail] before/after 文件集合不一致:")
        print(f"  before only: {set(before_files) - set(after_files)}")
        print(f"  after only:  {set(after_files) - set(before_files)}")
        sys.exit(1)

    any_fail = False
    for name in before_files:
        ok, msgs = compare_snapshot(before_dir / name, after_dir / name)
        if ok:
            print(f"[ok] {name}")
        else:
            any_fail = True
            print(f"[FAIL] {name}")
            for m in msgs[:30]:
                print(m)
            if len(msgs) > 30:
                print(f"  ... and {len(msgs) - 30} more diffs")

    if any_fail:
        print("\n回归 fail — 重构有 bug, 必须找到漏的规则补 spec. 不允许 commit.")
        sys.exit(1)
    print("\n回归通过 ✓ — 重构前后 L2 trace 0 diff")
    sys.exit(0)


if __name__ == "__main__":
    main()

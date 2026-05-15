"""D-072 重构基线快照: 跑 recall + rank_combos + apply_caps, 保存 top L3_INPUT_TOP_K
combo 的 score + breakdown + 餐厅+菜品签名, 供重构后回放对照.

不打 LLM (确定性), 不写 session, 不动数据.
固定 today 防 variety_bonus 漂移.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from chisha.context import build_context
from chisha.recall import (
    load_meal_log,
    load_profile,
    load_zone_data,
    recall,
)
from chisha.rerank import L3_INPUT_TOP_K
from chisha.score import apply_caps, rank_combos


def combo_signature(c: dict) -> dict:
    """combo → 紧凑签名 (id + name + dish names + score + breakdown).

    Codex Round 3 BLOCKER B-1 修复: score / breakdown 必须存原始 float, **不能 round**.
    round 到 6 位会把 <5e-7 的真实回归差异量化吞掉, 让"0 diff"成为假阳性.
    compare_traces.py 在比较阶段用 EPSILON=1e-6 即可.
    """
    rest = c.get("restaurant") or {}
    return {
        "rid": rest.get("id"),
        "rname": rest.get("name"),
        "brand": rest.get("brand"),
        "dish_ids": [d.get("dish_id") for d in c.get("dishes", [])],
        "dish_names": [d.get("canonical_name") for d in c.get("dishes", [])],
        "score": float(c.get("score", 0.0)),
        "breakdown": {k: float(v)
                       for k, v in (c.get("score_breakdown") or {}).items()},
    }


def snapshot(
    meal_type: str,
    zone: str,
    today: dt.date,
    daily_mood: str | None,
    root: Path,
) -> dict:
    profile = load_profile(root / "profile.yaml")
    rests, tagged = load_zone_data(zone, root)
    meal_log = load_meal_log(root)
    combos = recall(profile, rests, tagged, meal_log, today, meal_type=meal_type)
    ctx = build_context(
        profile=profile,
        meal_log=meal_log,
        meal_type=meal_type,
        today=today,
        daily_mood=daily_mood,
    )
    ranked = rank_combos(combos, profile, meal_log, today,
                         context=ctx, meal_type=meal_type, root=root)
    capped = apply_caps(ranked, profile)
    top = capped[:L3_INPUT_TOP_K]
    return {
        "meal_type": meal_type,
        "zone": zone,
        "today": today.isoformat(),
        "daily_mood": daily_mood,
        "n_combos_recalled": len(combos),
        "n_ranked": len(ranked),
        "n_after_caps": len(capped),
        "top_topk_size": L3_INPUT_TOP_K,
        "top_combos": [combo_signature(c) for c in top],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="tmp/baseline_traces")
    ap.add_argument("--today", default="2026-05-15")
    args = ap.parse_args()

    root = Path(".").resolve()
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    today = dt.date.fromisoformat(args.today)

    profile = load_profile(root / "profile.yaml")
    zones = profile.get("basics", {}).get("zones") or {}

    # 跑 (lunch, dinner) × (None, want_soup) — profile.basics.zones 当前两餐
    # 都是 shenzhen-bay, 实际 4 个快照 (注释 m-1 修正: 不是 8 个).
    cases = []
    for meal in ("lunch", "dinner"):
        zone = zones.get(meal) or profile["basics"]["office_zone"]
        for mood in (None, "want_soup"):
            cases.append((meal, zone, mood))

    for meal, zone, mood in cases:
        snap = snapshot(meal, zone, today, mood, root)
        tag = mood or "neutral"
        out = out_dir / f"snap_{meal}_{zone}_{tag}.json"
        out.write_text(json.dumps(snap, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"[ok] {out.name} — top {len(snap['top_combos'])}, "
              f"top1 {snap['top_combos'][0]['rname']!r} "
              f"score={snap['top_combos'][0]['score']:.6f}")


if __name__ == "__main__":
    main()

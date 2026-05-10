"""空跑测试: 跑 N 次 recommend_meal, 输出汇总.

用法:
    uv run python -m scripts.dry_run [--n 5] [--meal lunch|dinner|both]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

from chisha.api import recommend_meal


def render_one(out: dict):
    print(f"\n=== session {out['session_id']} ({out['meal_type']}) ===")
    print(f"召回: {out['stats']['n_combos_recalled']} combos | "
          f"打标菜数: {out['stats']['n_dishes_total']}")
    for c in out["candidates"]:
        rest = c["restaurant"]
        dish_names = ", ".join(d["canonical_name"] for d in c["dishes"])
        print(f"\n  #{c['rank']} score={c['score']:.2f}  "
              f"{rest['name']}  ({rest.get('distance_m', '?')}m)")
        print(f"     {dish_names}")
        print(f"     ¥{c['total_price']} | "
              f"oil={c['estimated_total_oil']} | "
              f"protein={c['estimated_total_protein_g']}g | "
              f"veg_dishes={c['vegetable_dish_count']}")
        print(f"     💬 {c['reason_one_line']}")


def summarize(outs: list[dict]):
    rest_counter = Counter()
    cuisine_counter = Counter()
    veg_ok = 0
    protein_ok = 0
    total_picks = 0
    for o in outs:
        for c in o["candidates"]:
            total_picks += 1
            rest_counter[c["restaurant"]["name"]] += 1
            for d in c["dishes"]:
                # 通过 dish 的 cuisine? 这里没存, 只算商家
                pass
            if c["vegetable_dish_count"] >= 1:
                veg_ok += 1
            if c["estimated_total_protein_g"] >= 25:
                protein_ok += 1
    print("\n=== 汇总 ===")
    print(f"总推荐: {total_picks}")
    print(f"蔬菜达标: {veg_ok}/{total_picks} "
          f"({100*veg_ok/max(1,total_picks):.0f}%)")
    print(f"蛋白达标: {protein_ok}/{total_picks} "
          f"({100*protein_ok/max(1,total_picks):.0f}%)")
    print(f"商家分布: {dict(rest_counter)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--meal", default="lunch", choices=["lunch", "dinner", "both"])
    args = ap.parse_args()

    meals = ["lunch", "dinner"] if args.meal == "both" else [args.meal]
    outs = []
    for i in range(args.n):
        for m in meals:
            o = recommend_meal(m, log_to_file=False)
            render_one(o)
            outs.append(o)
    summarize(outs)


if __name__ == "__main__":
    main()

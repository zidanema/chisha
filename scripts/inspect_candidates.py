"""召回 100 抽查脚本: 跑一次召回, 输出每个 combo 的判断要点.

用法: uv run python -m scripts.inspect_candidates [--limit 100]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from chisha.recall import (
    load_profile, load_zone_data, load_meal_log, recall
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    profile = load_profile(root / "profile.yaml")
    zone = profile["basics"]["office_zone"]
    rests, tagged = load_zone_data(zone, root)
    log = load_meal_log(root)

    combos = recall(profile, rests, tagged, log)
    print(f"召回 {len(combos)} 个 combo (tagged dishes={len(tagged)})\n")

    for i, c in enumerate(combos[: args.limit], 1):
        rest = c["restaurant"]
        ds = c["dishes"]
        names = " + ".join(d["canonical_name"] for d in ds)
        cuisines = list({d.get("cuisine", "") for d in ds})
        avg_oil = sum(d["nutrition_profile"]["oil_level"] for d in ds) / len(ds)
        total_p = sum(d["nutrition_profile"]["protein_grams_estimate"] for d in ds)
        veg_n = sum(
            1 for d in ds
            if d["nutrition_profile"]["main_ingredient_type"] == "纯素"
            or d["nutrition_profile"]["vegetable_ratio_estimate"] >= 0.6
        )
        flags = []
        if veg_n < 1:
            flags.append("⚠ 无蔬菜")
        if total_p < profile["plate_rule"].get("min_protein_g", 25):
            flags.append(f"⚠ 蛋白不足 {total_p}g")
        if avg_oil > 4:
            flags.append(f"⚠ 油重 {avg_oil:.1f}")
        flag_s = " ".join(flags) if flags else "OK"
        print(f"#{i:3d} [{flag_s}] {rest['name']} | {cuisines}")
        print(f"      {names}")
        print(f"      oil={avg_oil:.1f}, protein={total_p}g, veg={veg_n}")


if __name__ == "__main__":
    main()

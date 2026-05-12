"""100 候选合理性扫描 (V1 验收门: ROADMAP §抽查标准).

跑 recall + V2 打分, 取 top 100 / random 50 两批候选, 检查:
- 弱约束三件套 (D-023): veg ≥ 1, protein ≥ 25g, oil_avg ≤ 3
- avoid_dishes / disliked_cuisines / spicy_tolerance 命中检查
- 销量缺失分布
- 商家分布 (是否被少数连锁霸榜)
- 单菜异常 (蛋白 0 / 油 5 等)

输出: 控制台总览 + logs/audit/recall_audit_{meal}.md 让你逐条扫读
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chisha.context import build_context
from chisha.recall import (
    load_meal_log,
    load_profile,
    load_zone_data,
    recall,
)
from chisha.score import rank_combos


def check_combo(combo: dict, profile: dict) -> dict:
    """单 combo 体检 — 返回 flags dict, 空表示完美."""
    flags: list[str] = []
    dishes = combo["dishes"]
    pr = profile["plate_rule"]
    prefs = profile["preferences"]

    # 弱约束三件套
    veg_count = sum(
        1 for d in dishes
        if d["nutrition_profile"].get("main_ingredient_type") == "纯素"
        or d["nutrition_profile"].get("vegetable_ratio_estimate", 0) >= 0.6
    )
    if veg_count < pr.get("min_vegetable_dishes", 1):
        flags.append(f"VEG<{pr.get('min_vegetable_dishes',1)} (实={veg_count})")

    total_protein = sum(
        d["nutrition_profile"].get("protein_grams_estimate", 0) for d in dishes
    )
    if total_protein < pr.get("min_protein_g", 25):
        flags.append(f"PROT<{pr.get('min_protein_g',25)}g (实={total_protein}g)")

    avg_oil = sum(d["nutrition_profile"].get("oil_level", 0) for d in dishes) / max(1, len(dishes))
    if avg_oil > pr.get("prefer_oil_level_at_most", 3):
        flags.append(f"OIL>{pr.get('prefer_oil_level_at_most',3)} (实={avg_oil:.1f})")

    # 硬约束兜底 (硬过滤应该已经过滤了, 这里再防一下)
    avoid_dish = set(prefs.get("avoid_dishes", []))
    for d in dishes:
        if d.get("canonical_name") in avoid_dish:
            flags.append(f"AVOID命中: {d['canonical_name']}")

    disliked = set(prefs.get("disliked_cuisines", []))
    cuisines = {d.get("cuisine") for d in dishes}
    if cuisines & disliked:
        flags.append(f"不喜菜系: {cuisines & disliked}")

    spicy_max = prefs.get("spicy_tolerance", 3)
    for d in dishes:
        sl = d["nutrition_profile"].get("spicy_level", 0)
        if sl > spicy_max:
            flags.append(f"过辣: {d['canonical_name']}({sl})")

    # 单菜异常
    for d in dishes:
        np = d["nutrition_profile"]
        if np.get("protein_grams_estimate", 0) == 0 and np.get("dish_role") in ("主菜", "套餐"):
            flags.append(f"主菜0蛋白: {d['canonical_name']}")
        if np.get("oil_level", 0) >= 5:
            flags.append(f"油5级: {d['canonical_name']}")

    return {
        "veg_count": veg_count,
        "total_protein": total_protein,
        "avg_oil": round(avg_oil, 1),
        "flags": flags,
        "n_dishes": len(dishes),
    }


def audit(meal: str = "lunch") -> dict:
    profile = load_profile(ROOT / "profile.yaml")
    zones = profile.get("basics", {}).get("zones") or {}
    zone = zones.get(meal) or profile["basics"]["office_zone"]
    rests, tagged = load_zone_data(zone, ROOT)
    meal_log = load_meal_log(ROOT)
    today = dt.date.today()

    print(f"\n=== Audit {meal} @ {zone} ===")
    print(f"  数据: {len(rests)} 店 / {len(tagged)} 菜")

    ctx = build_context(profile, meal_log, meal, today, daily_mood=None)
    combos = recall(profile, rests, tagged, meal_log, today)
    ranked = rank_combos(combos, profile, meal_log, today, context=ctx, meal_type=meal)
    print(f"  recall = {len(combos)} combos")

    # 取 top 50 + 随机 50 (中段抽样, 避免只看 top 优等生)
    top_50 = ranked[:50]
    if len(ranked) > 100:
        mid_50 = random.sample(ranked[50:], min(50, len(ranked) - 50))
    else:
        mid_50 = ranked[50:]
    samples = top_50 + mid_50
    print(f"  审查 sample = {len(samples)} (top50 + mid50)")

    # 体检每条
    audits = []
    for i, c in enumerate(samples):
        a = check_combo(c, profile)
        a["rank"] = i + 1
        a["score"] = round(c["score"], 3)
        a["rest_name"] = c["restaurant"]["name"]
        a["rest_id"] = c["restaurant"]["id"]
        a["distance_m"] = c["restaurant"].get("distance_m", -1)
        a["dishes"] = [d["canonical_name"] for d in c["dishes"]]
        a["cuisines"] = list({d.get("cuisine") for d in c["dishes"]})
        a["dish_roles"] = [d["nutrition_profile"].get("dish_role") for d in c["dishes"]]
        audits.append(a)

    # 聚合统计
    n = len(audits)
    n_flagged = sum(1 for a in audits if a["flags"])
    pass_rate = (n - n_flagged) / n if n else 0
    brand_dist = Counter(a["rest_name"] for a in audits)
    cuisine_dist = Counter(c for a in audits for c in a["cuisines"])
    flag_types = Counter()
    for a in audits:
        for f in a["flags"]:
            flag_types[f.split(":")[0].split("(")[0].strip()] += 1

    print(f"\n  ✓ pass rate: {pass_rate*100:.1f}% ({n - n_flagged}/{n})")
    print(f"  ✗ flagged:   {n_flagged} 条")
    if flag_types:
        print(f"  flag 类型分布:")
        for ft, cnt in flag_types.most_common():
            print(f"    {ft}: {cnt}")
    print(f"  top 5 商家集中度:")
    for name, cnt in brand_dist.most_common(5):
        print(f"    {cnt:3d} × {name[:30]}")
    print(f"  top 5 菜系覆盖:")
    for c, cnt in cuisine_dist.most_common(5):
        print(f"    {cnt:3d} × {c}")

    # 写 markdown 让用户逐条扫
    audit_dir = ROOT / "logs" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    md_path = audit_dir / f"recall_audit_{meal}.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write(f"# Recall 100 候选合理性扫描 - {meal} @ {zone}\n\n")
        f.write(f"**数据**: {len(rests)} 店 / {len(tagged)} 菜  \n")
        f.write(f"**Recall**: {len(combos)} combos  \n")
        f.write(f"**Audit sample**: {n} (top 50 + 随机 mid 50)  \n")
        f.write(f"**Pass rate**: {pass_rate*100:.1f}% ({n - n_flagged}/{n})  \n\n")
        if flag_types:
            f.write("## Flag 类型\n\n")
            for ft, cnt in flag_types.most_common():
                f.write(f"- {ft}: {cnt}\n")
            f.write("\n")
        f.write("## 商家分布\n\n| 出现次数 | 商家 |\n|---:|---|\n")
        for name, cnt in brand_dist.most_common(15):
            f.write(f"| {cnt} | {name} |\n")
        f.write("\n## 菜系分布\n\n| 出现次数 | 菜系 |\n|---:|---|\n")
        for c, cnt in cuisine_dist.most_common():
            f.write(f"| {cnt} | {c} |\n")
        f.write("\n## 候选明细 (top 50)\n\n")
        f.write("| rank | score | 商家 | 菜 | 油 | 蛋白 | 蔬菜数 | flags |\n")
        f.write("|---:|---:|---|---|---:|---:|---:|---|\n")
        for a in audits[:50]:
            dishes_str = " + ".join(a["dishes"])
            flags_str = ", ".join(a["flags"]) if a["flags"] else "✓"
            f.write(
                f"| {a['rank']} | {a['score']} | {a['rest_name'][:18]} | "
                f"{dishes_str[:60]} | {a['avg_oil']} | {a['total_protein']}g | "
                f"{a['veg_count']} | {flags_str} |\n"
            )
        f.write("\n## 候选明细 (mid 50, 随机)\n\n")
        f.write("| rank | score | 商家 | 菜 | 油 | 蛋白 | 蔬菜数 | flags |\n")
        f.write("|---:|---:|---|---|---:|---:|---:|---|\n")
        for a in audits[50:]:
            dishes_str = " + ".join(a["dishes"])
            flags_str = ", ".join(a["flags"]) if a["flags"] else "✓"
            f.write(
                f"| {a['rank']} | {a['score']} | {a['rest_name'][:18]} | "
                f"{dishes_str[:60]} | {a['avg_oil']} | {a['total_protein']}g | "
                f"{a['veg_count']} | {flags_str} |\n"
            )

    print(f"\n  详细明细写入: {md_path.relative_to(ROOT)}")
    return {
        "meal": meal,
        "zone": zone,
        "n_audited": n,
        "pass_rate": pass_rate,
        "n_flagged": n_flagged,
        "brand_top_share": brand_dist.most_common(1)[0][1] / n if brand_dist else 0,
        "md_path": str(md_path.relative_to(ROOT)),
    }


if __name__ == "__main__":
    random.seed(20260512)
    summary = []
    for meal in ("lunch", "dinner"):
        summary.append(audit(meal))
    print("\n=== 汇总 ===")
    for s in summary:
        share = s["brand_top_share"] * 100
        print(
            f"  {s['meal']:6s} pass={s['pass_rate']*100:5.1f}% "
            f"flagged={s['n_flagged']:2d} 头牌商家占比={share:.0f}% → {s['md_path']}"
        )

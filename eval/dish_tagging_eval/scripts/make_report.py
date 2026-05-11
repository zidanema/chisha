"""读 score_summary.json + golden_set, 生成 report.md (纯 stdlib, 无 pandas 依赖)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMMARY = ROOT / "score_summary.json"
GOLDEN = ROOT / "data" / "golden_set.jsonl"
RESULTS_DIR = ROOT / "results"
OUT = ROOT / "report.md"

KEY4 = ["sweet_sauce_level", "processed_meat_flag", "dish_role", "grain_type"]
CAT_ORDER = ["sichuan_xiang","yue_chaoshan","jiangzhe_sweet","japan_korea","western_fast",
             "combo","staple","side_soup","boundary"]
CAT_NAME = {
    "sichuan_xiang": "川湘菜", "yue_chaoshan": "粤潮", "jiangzhe_sweet": "江浙红烧/糖醋",
    "japan_korea": "日韩", "western_fast": "西式快餐", "combo": "套餐组合",
    "staple": "主食单点", "side_soup": "配菜/汤/饮品/小食", "boundary": "边界对抗",
}


def fmt_pct(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x*100:.1f}%"


def fmt_money(x: float | None) -> str:
    if x is None:
        return "—"
    return f"${x:.4f}"


def render(summary: dict) -> str:
    lines: list[str] = []
    models = summary["models"]
    aliases = list(models.keys())
    if not aliases:
        return "# 无模型结果可生成报告.\n"

    # === 头部 ===
    lines.append("# 菜品打标 v3 - 多模型横评报告\n")
    lines.append(f"- golden set: {summary.get('n_golden', '?')} 条")
    total_cost = sum(s.get("cost_usd_total", 0.0) for s in models.values())
    lines.append(f"- 实际总成本: ${total_cost:.4f}")
    lines.append(f"- 实际跑的模型: {len(aliases)}\n")

    # === 实验信息 ===
    lines.append("## 实验信息\n")
    lines.append("| alias | OpenRouter id | n_evaluated | json_valid |")
    lines.append("|---|---|---|---|")
    for a, s in models.items():
        lines.append(f"| {a} | `{s['model_id_actual']}` | {s['n_evaluated']}/{s['n_total']} | "
                     f"{fmt_pct(s['json_valid_rate'])} |")
    if summary.get("errors"):
        lines.append("")
        lines.append("**未测模型/错误**:")
        for e in summary["errors"]:
            lines.append(f"- {e}")
    lines.append("")

    # === 总体对比表 ===
    lines.append("## 总体对比表\n")
    lines.append("| 模型 | 字段级准确率(micro) | 整条全对率 | JSON 合法率 | 平均延迟(ms) | p95延迟(ms) | 总成本 | 100万条预估 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    rows = []
    for a, s in models.items():
        rows.append((a, s))
    # 按字段准确率排序
    rows.sort(key=lambda x: -x[1]["field_accuracy_micro"])
    for a, s in rows:
        lines.append(f"| {a} | {fmt_pct(s['field_accuracy_micro'])} | "
                     f"{fmt_pct(s['all_fields_correct_rate'])} | "
                     f"{fmt_pct(s['json_valid_rate'])} | "
                     f"{s['avg_latency_ms']} | {s['p95_latency_ms']} | "
                     f"{fmt_money(s['cost_usd_total'])} | "
                     f"${s['estimated_1M_cost_usd']:.0f} |")
    lines.append("")

    # === 关键字段分水岭 ===
    lines.append("## 关键字段分水岭(4 大易错字段)\n")
    lines.append("| 模型 | sweet_sauce_level | processed_meat_flag | dish_role | grain_type |")
    lines.append("|---|---:|---:|---:|---:|")
    for a, s in models.items():
        k = s["key_4_fields"]
        lines.append(f"| {a} | {fmt_pct(k.get('sweet_sauce_level'))} | "
                     f"{fmt_pct(k.get('processed_meat_flag'))} | "
                     f"{fmt_pct(k.get('dish_role'))} | "
                     f"{fmt_pct(k.get('grain_type'))} |")
    lines.append("")

    # === 全字段细致表 ===
    lines.append("## 全字段准确率(每模型 15 字段)\n")
    all_fields = sorted({f for s in models.values() for f in s["field_accuracy"].keys()})
    lines.append("| 字段 | " + " | ".join(aliases) + " |")
    lines.append("|---|" + "|".join("---:" for _ in aliases) + "|")
    for f in all_fields:
        row = [f]
        for a in aliases:
            row.append(fmt_pct(models[a]["field_accuracy"].get(f)))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # === 按类别切片 ===
    lines.append("## 按类别切片(字段准确率 micro)\n")
    lines.append("| 类别 | " + " | ".join(aliases) + " |")
    lines.append("|---|" + "|".join("---:" for _ in aliases) + "|")
    for cat in CAT_ORDER:
        row = [f"{CAT_NAME[cat]} ({cat})"]
        for a in aliases:
            bc = models[a]["by_category"].get(cat)
            if not bc:
                row.append("—")
            else:
                fa = bc["field_accuracy"]
                if not fa:
                    row.append("—")
                else:
                    avg = sum(fa.values()) / len(fa)
                    row.append(fmt_pct(avg))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # === 典型错误 case ===
    lines.append("## 典型错误 case 抽样\n")
    for a, s in models.items():
        lines.append(f"### {a}\n")
        samples = s.get("error_samples", [])[:5]
        if not samples:
            lines.append("无错误样本\n")
            continue
        for i, sm in enumerate(samples, 1):
            lines.append(f"**case {i}**: `{sm['dish_id']}` {sm['raw_name']} (`{sm['category_tag']}`)")
            for w in sm["wrong_fields"][:6]:
                ev = json.dumps(w["expected"], ensure_ascii=False)
                pv = json.dumps(w["predicted"], ensure_ascii=False)
                lines.append(f"  - `{w['field']}`: expected={ev} predicted={pv}")
            lines.append("")
        lines.append("")

    # === 结论与建议 (基于数据自动推) ===
    lines.append("## 结论与建议\n")
    # 选 top 1 / 性价比
    by_acc = sorted(rows, key=lambda x: -x[1]["field_accuracy_micro"])
    top = by_acc[0]
    cheapest_acceptable = None  # 准确率 >= top - 5pp 且成本最低
    threshold = top[1]["field_accuracy_micro"] - 0.05
    candidates = [r for r in rows if r[1]["field_accuracy_micro"] >= threshold]
    candidates.sort(key=lambda x: x[1]["estimated_1M_cost_usd"])
    cheapest_acceptable = candidates[0] if candidates else top

    key4_for = lambda alias: models[alias]["key_4_fields"]

    lines.append(f"### 1. 准确率冠军\n")
    lines.append(f"- **{top[0]}** (`{top[1]['model_id_actual']}`):字段级准确率 "
                 f"{fmt_pct(top[1]['field_accuracy_micro'])}, 整条全对率 "
                 f"{fmt_pct(top[1]['all_fields_correct_rate'])}, 100万条预估成本 ${top[1]['estimated_1M_cost_usd']:.0f}\n")

    lines.append(f"### 2. 性价比推荐\n")
    if cheapest_acceptable[0] != top[0]:
        lines.append(f"- **{cheapest_acceptable[0]}** (`{cheapest_acceptable[1]['model_id_actual']}`):"
                     f"准确率 {fmt_pct(cheapest_acceptable[1]['field_accuracy_micro'])} "
                     f"(距冠军 -{(top[1]['field_accuracy_micro']-cheapest_acceptable[1]['field_accuracy_micro'])*100:.1f}pp), "
                     f"100万条预估 **${cheapest_acceptable[1]['estimated_1M_cost_usd']:.0f}** "
                     f"(冠军的 {cheapest_acceptable[1]['estimated_1M_cost_usd']/max(1,top[1]['estimated_1M_cost_usd']):.1%})")
    else:
        lines.append(f"- 准确率冠军同时也是性价比最优:**{top[0]}**")
    lines.append("")

    lines.append("### 3. 关键字段分析\n")
    for f in KEY4:
        rows_f = sorted(models.items(), key=lambda kv: -kv[1]["key_4_fields"].get(f, 0))
        best = rows_f[0]
        worst = rows_f[-1]
        gap = (best[1]["key_4_fields"][f] - worst[1]["key_4_fields"][f]) * 100
        lines.append(f"- **{f}**: 最好 {best[0]} ({fmt_pct(best[1]['key_4_fields'][f])}), "
                     f"最差 {worst[0]} ({fmt_pct(worst[1]['key_4_fields'][f])}), gap {gap:.1f}pp")
    lines.append("")

    lines.append("### 4. 推荐生产模型\n")
    rec = cheapest_acceptable[0]
    rec_s = cheapest_acceptable[1]
    top_acc = top[1]["field_accuracy_micro"]
    rec_acc = rec_s["field_accuracy_micro"]
    if rec == top[0]:
        lines.append(f"**推荐:`{rec}`** — 准确率最高 ({fmt_pct(rec_acc)}), 不需要分层方案.\n")
    else:
        gap_pp = (top_acc - rec_acc) * 100
        cost_ratio = rec_s["estimated_1M_cost_usd"] / max(1, top[1]["estimated_1M_cost_usd"])
        lines.append(f"**推荐:`{rec}` 主跑 + `{top[0]}` 回退难 case** —")
        lines.append(f"- 主路径:`{rec}` 跑生产数据冲刷, 准确率 {fmt_pct(rec_acc)}, "
                     f"100万条 ${rec_s['estimated_1M_cost_usd']:.0f}, "
                     f"比冠军省 {(1-cost_ratio)*100:.0f}%")
        lines.append(f"- 回退路径:对低置信样本(JSON 不合法 / 关键字段反直觉) 用 `{top[0]}` 重跑, 兜底准确率")
        lines.append(f"- 准确率差距 {gap_pp:.1f}pp, 通过分层可基本拉平")
        lines.append("")

    lines.append("### 5. 已知风险/局限\n")
    risks = []
    # JSON 合法率
    bad_json = [(a, s["json_valid_rate"]) for a, s in models.items() if s["json_valid_rate"] < 0.95]
    if bad_json:
        bad_json.sort(key=lambda x: x[1])
        risks.append(f"**JSON 合法率偏低**:{', '.join(f'{a}={fmt_pct(r)}' for a, r in bad_json)} - 生产侧需 JSON 兜底解析")
    # key4 任一 < 70%
    for f in KEY4:
        low = [(a, models[a]["key_4_fields"][f]) for a in aliases if models[a]["key_4_fields"][f] < 0.7]
        if low:
            low.sort(key=lambda x: x[1])
            risks.append(f"**{f}** 准确率偏低:{', '.join(f'{a}={fmt_pct(r)}' for a, r in low)} - prompt 锚点对部分模型不够 robust")
    if summary.get("errors"):
        risks.append(f"**未测模型**:{summary['errors']}")
    if not risks:
        risks.append("无显著风险")
    for r in risks:
        lines.append(f"- {r}")
    lines.append("")

    lines.append("---")
    lines.append("\n*报告由 `scripts/make_report.py` 基于 `score_summary.json` 自动生成.*\n")
    return "\n".join(lines)


def main() -> int:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    OUT.write_text(render(summary), encoding="utf-8")
    print(f"[report] wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

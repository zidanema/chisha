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
    lines.append("| 模型 | 字段准确率 | 整条全对率 | JSON 合法率 | batch_p95(s) | 总成本 | 100万条预估 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    rows = []
    for a, s in models.items():
        rows.append((a, s))
    rows.sort(key=lambda x: -x[1]["field_accuracy_micro"])
    for a, s in rows:
        lines.append(f"| {a} | {fmt_pct(s['field_accuracy_micro'])} | "
                     f"{fmt_pct(s['all_fields_correct_rate'])} | "
                     f"{fmt_pct(s['json_valid_rate'])} | "
                     f"{s['p95_batch_latency_ms']/1000:.1f} | "
                     f"{fmt_money(s['cost_usd_total'])} | "
                     f"${s['estimated_1M_cost_usd']:.0f} |")
    lines.append("")

    # === 吞吐与生产部署成本 ===
    lines.append("## 吞吐与生产部署预估\n")
    lines.append("> batch=20, concurrency=10(经验上 OpenRouter 单账号 rate limit 内的安全值).\n"
                 "> p95 batch latency 来自评测实测,用于做时间预估(保守口径).\n")
    lines.append("| 模型 | 单请求吞吐(条/秒) | concurrency=10 吞吐(条/秒) | 跑 1万条耗时 | 跑 10万条耗时 | 1万条成本 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    # 时间格式化
    def fmt_dur(s):
        if s < 60: return f"{s:.0f}s"
        if s < 3600: return f"{s/60:.1f}min"
        return f"{s/3600:.1f}h"
    rows_by_acc = sorted(rows, key=lambda x: -x[1]["field_accuracy_micro"])
    for a, s in rows_by_acc:
        cost_per = s["cost_usd_total"] / max(1, s["n_total"])
        cost_10k = cost_per * 10000
        lines.append(f"| {a} | {s['throughput_per_req_per_s']:.2f} | "
                     f"{s['throughput_rows_per_s_at_concurrency10']:.1f} | "
                     f"{fmt_dur(s['est_10k_seconds_at_concurrency10'])} | "
                     f"{fmt_dur(s['est_100k_seconds_at_concurrency10'])} | "
                     f"${cost_10k:.2f} |")
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

    # === 结论与建议 (三维度: 准确率 + 成本 + 吞吐) ===
    lines.append("## 结论与建议\n")
    by_acc = sorted(rows, key=lambda x: -x[1]["field_accuracy_micro"])
    top = by_acc[0]
    # 性价比候选: 准确率 ≥ top - 5pp 的里, 综合 (100万条成本) + (10万条耗时) 排序
    # 权重: cost 0.7 + time 0.3 — 生产打标核心看长期成本, 单条延迟次要(可隔夜跑)
    threshold = top[1]["field_accuracy_micro"] - 0.05
    cands = [r for r in rows if r[1]["field_accuracy_micro"] >= threshold]
    if cands:
        max_cost = max(c[1]["estimated_1M_cost_usd"] for c in cands)
        max_time = max(c[1]["est_100k_seconds_at_concurrency10"] for c in cands)
        for c in cands:
            cn = c[1]["estimated_1M_cost_usd"] / max(1, max_cost)
            tn = c[1]["est_100k_seconds_at_concurrency10"] / max(1, max_time)
            c[1]["_combined"] = 0.7 * cn + 0.3 * tn
        cands.sort(key=lambda x: x[1]["_combined"])
        cheapest_acceptable = cands[0]
    else:
        cheapest_acceptable = top
    # 速度冠军 (吞吐最大)
    by_speed = sorted(rows, key=lambda x: -x[1]["throughput_rows_per_s_at_concurrency10"])
    speed_top = by_speed[0]

    lines.append("### 1. 三维度并列冠军\n")
    lines.append(f"- **准确率冠军**:`{top[0]}` — 字段 {fmt_pct(top[1]['field_accuracy_micro'])}, "
                 f"整条全对 {fmt_pct(top[1]['all_fields_correct_rate'])}")
    cheapest_by_cost = min(rows, key=lambda x: x[1]['estimated_1M_cost_usd'])
    lines.append(f"- **成本冠军**:`{cheapest_by_cost[0]}` — 100万条预估 ${cheapest_by_cost[1]['estimated_1M_cost_usd']:.0f}")
    lines.append(f"- **吞吐冠军**:`{speed_top[0]}` — concurrency=10 下 "
                 f"{speed_top[1]['throughput_rows_per_s_at_concurrency10']:.1f} 条/秒, "
                 f"跑 10 万条仅需 ~{(speed_top[1]['est_100k_seconds_at_concurrency10']/60):.0f}min\n")

    lines.append("### 2. 关键字段分水岭\n")
    for f in KEY4:
        rows_f = sorted(models.items(), key=lambda kv: -kv[1]["key_4_fields"].get(f, 0))
        best = rows_f[0]
        worst = rows_f[-1]
        gap = (best[1]["key_4_fields"][f] - worst[1]["key_4_fields"][f]) * 100
        lines.append(f"- **{f}**: 最好 `{best[0]}` ({fmt_pct(best[1]['key_4_fields'][f])}), "
                     f"最差 `{worst[0]}` ({fmt_pct(worst[1]['key_4_fields'][f])}), gap {gap:.1f}pp")
    lines.append("")

    lines.append("### 3. 推荐生产模型 (按数据量与时间窗口)\n")
    lines.append("生产场景的选型不能只看准确率/成本,**吞吐(完成时间)同等关键**——便宜但跑得慢的模型,几万条数据可能跑一整天.\n")
    lines.append("| 场景 | 推荐 | 理由 |")
    lines.append("|---|---|---|")
    # 场景分桶
    def hours(sec): return sec / 3600
    # 1万条 (小批冲刷)
    for_10k = sorted(rows, key=lambda x: (-x[1]['field_accuracy_micro'],
                                           x[1]['est_10k_seconds_at_concurrency10']))[0]
    cost_10k_for = lambda s: (s['cost_usd_total']/s['n_total']) * 10000
    lines.append(f"| 数据量 ≤ 1万 / 时间敏感 | **`{top[0]}`** | "
                 f"准确率最高 ({fmt_pct(top[1]['field_accuracy_micro'])}), "
                 f"1万条 ${cost_10k_for(top[1]):.1f} / "
                 f"{fmt_dur(top[1]['est_10k_seconds_at_concurrency10'])}; "
                 f"贵但快, 小批量首选 |")
    # 性价比均衡 (cheapest_acceptable = 综合 cost+time 归一化最优, 准确率 >= top-5pp)
    # 这一档 = 生产打标默认模型 (见 chisha/llm_client_openrouter.py DEFAULT_BULK_MODEL)
    bulk_alias = cheapest_acceptable[0]
    bulk_s = cheapest_acceptable[1]
    if bulk_alias != top[0]:
        lines.append(f"| 数据量 1万-10万 / 性价比均衡 ⭐ **(生产打标默认)** | **`{bulk_alias}`** | "
                     f"字段准确率 {fmt_pct(bulk_s['field_accuracy_micro'])}(距冠军 "
                     f"-{(top[1]['field_accuracy_micro']-bulk_s['field_accuracy_micro'])*100:.1f}pp), "
                     f"吞吐 {bulk_s['throughput_rows_per_s_at_concurrency10']:.1f} 条/秒, "
                     f"100万条 ${bulk_s['estimated_1M_cost_usd']:.0f} ({bulk_s['estimated_1M_cost_usd']/top[1]['estimated_1M_cost_usd']*100:.1f}% 冠军成本), "
                     f"10万条 {fmt_dur(bulk_s['est_100k_seconds_at_concurrency10'])} |")
    # 极致省钱: cheapest_by_cost, 若与 bulk 不同则单列
    if cheapest_by_cost[0] not in (top[0], bulk_alias):
        cb_s = cheapest_by_cost[1]
        lines.append(f"| 数据量 ≥ 10万 / 时间不敏感 | **`{cheapest_by_cost[0]}`** | "
                     f"100万条仅 ${cb_s['estimated_1M_cost_usd']:.0f} (冠军的 "
                     f"{cb_s['estimated_1M_cost_usd']/top[1]['estimated_1M_cost_usd']*100:.1f}%), "
                     f"10万条 {fmt_dur(cb_s['est_100k_seconds_at_concurrency10'])}, "
                     f"准确率 {fmt_pct(cb_s['field_accuracy_micro'])} |")
    lines.append("")

    lines.append("### 4. 是否分层方案?\n")
    # 准确率 gap > 3pp 且成本 gap > 5 倍, 推荐分层
    rec = cheapest_acceptable[0]
    rec_s = cheapest_acceptable[1]
    top_acc = top[1]["field_accuracy_micro"]
    rec_acc = rec_s["field_accuracy_micro"]
    gap_pp = (top_acc - rec_acc) * 100
    if rec != top[0] and gap_pp >= 3:
        cost_ratio = top[1]["estimated_1M_cost_usd"] / max(1, rec_s["estimated_1M_cost_usd"])
        lines.append(f"**建议分层**:`{rec}` 主跑 + `{top[0]}` 回退低置信样本.")
        lines.append(f"- 主路径:`{rec}` 跑生产数据冲刷, 准确率 {fmt_pct(rec_acc)}, 跑 10万条 ${cost_10k_for(rec_s)*10:.0f} / {fmt_dur(rec_s['est_100k_seconds_at_concurrency10'])}")
        lines.append(f"- 回退路径:对 JSON 不合法 / 关键字段反直觉(`sweet_sauce_level<2` 但触发词命中, `processed_meat_flag=true` 但烧腊命名 等)的样本, 用 `{top[0]}` 重跑")
        lines.append(f"- 准确率 gap {gap_pp:.1f}pp 通过分层可拉平到接近 `{top[0]}` 水平")
        lines.append("")
    else:
        lines.append(f"**不分层**:`{rec}` 已经接近 top ({fmt_pct(rec_acc)} vs {fmt_pct(top_acc)}, gap {gap_pp:.1f}pp), "
                     f"分层带来的边际收益不大.")
        lines.append("")

    lines.append("### 5. 最终决策 (基于本次实测)\n")
    rec_lines = []
    rec_lines.append(f"- **生产打标默认 → `{bulk_alias}`** (`chisha/llm_client_openrouter.py:DEFAULT_BULK_MODEL`): "
                     f"准确率 {fmt_pct(bulk_s['field_accuracy_micro'])}, 100万条 ${bulk_s['estimated_1M_cost_usd']:.0f}, "
                     f"距冠军 -{(top_acc-bulk_s['field_accuracy_micro'])*100:.1f}pp 性价比最优")
    rec_lines.append(f"- 如果**只跑一次几千条 → `{top[0]}`**:准确率最高 {fmt_pct(top_acc)} + 速度最快档 + 一次性成本可接受")
    if cheapest_by_cost[0] not in (top[0], bulk_alias):
        cb_s = cheapest_by_cost[1]
        rec_lines.append(f"- 如果**几十万条 + 离线异步 + 极致省钱 → `{cheapest_by_cost[0]}`**:成本 ${cb_s['estimated_1M_cost_usd']:.0f}/100万条, 但要忍受 {fmt_dur(cb_s['est_100k_seconds_at_concurrency10'])}/10万条的耗时")
    for x in rec_lines: lines.append(x)
    lines.append("")

    lines.append("### 6. 已知风险/局限\n")
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

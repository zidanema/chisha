"""生成单文件 HTML 报告 (含 Chart.js, 离线 / 双击可看).

读 score_summary.json + golden_set.jsonl + results/*.jsonl, 输出 report.html.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMMARY_PATH = ROOT / "score_summary.json"
GOLDEN_PATH = ROOT / "data" / "golden_set.jsonl"
RESULTS_DIR = ROOT / "results"
OUT = ROOT / "report.html"

KEY4 = ["sweet_sauce_level", "processed_meat_flag", "dish_role", "grain_type"]
CAT_ORDER = ["sichuan_xiang","yue_chaoshan","jiangzhe_sweet","japan_korea",
             "western_fast","combo","staple","side_soup","boundary"]
CAT_NAME = {
    "sichuan_xiang": "川湘菜", "yue_chaoshan": "粤潮", "jiangzhe_sweet": "江浙红烧/糖醋",
    "japan_korea": "日韩", "western_fast": "西式快餐", "combo": "套餐组合",
    "staple": "主食单点", "side_soup": "配菜/汤/饮品", "boundary": "边界对抗",
}
# 字段中文名
FIELD_LABEL = {
    "canonical_name": "菜品名", "cuisine": "菜系", "main_ingredient_type": "主料",
    "cooking_method": "烹饪方式", "oil_level": "油度", "protein_grams_estimate": "蛋白估算",
    "vegetable_ratio_estimate": "蔬菜占比", "is_complete_meal": "完整一餐",
    "spicy_level": "辣度", "dish_role": "拼餐角色", "processed_meat_flag": "加工肉",
    "sweet_sauce_level": "甜酱度", "wetness": "湿度", "grain_type": "主食类型",
    "tags": "标签",
}
# 给 6 个常见模型分配稳定颜色
COLOR_MAP = {
    "sonnet-4.6": "#a855f7", "haiku-4.5": "#06b6d4", "deepseek-pro": "#f97316",
    "deepseek-flash": "#facc15", "kimi-k2.6": "#10b981", "glm-4.6": "#ec4899",
}
FALLBACK_COLORS = ["#6366f1", "#ef4444", "#14b8a6", "#84cc16", "#8b5cf6", "#f43f5e"]


def color_for(alias: str, idx: int) -> str:
    return COLOR_MAP.get(alias, FALLBACK_COLORS[idx % len(FALLBACK_COLORS)])


def fmt_dur_s(s: float) -> str:
    if s < 60: return f"{s:.0f}s"
    if s < 3600: return f"{s/60:.1f}min"
    return f"{s/3600:.1f}h"


def load_golden() -> list[dict]:
    if not GOLDEN_PATH.exists():
        return []
    return [json.loads(ln) for ln in GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]


def build_payload(summary: dict, golden: list[dict]) -> dict:
    """把 summary 转成前端友好的 payload (含每模型详情 + 错误样本)."""
    models = summary.get("models", {})
    aliases = list(models.keys())
    # 错误样本对每模型最多 30 条
    payload = {
        "n_golden": summary.get("n_golden", len(golden)),
        "aliases": aliases,
        "colors": {a: color_for(a, i) for i, a in enumerate(aliases)},
        "models": {},
        "categories": CAT_ORDER,
        "category_names": CAT_NAME,
        "field_labels": FIELD_LABEL,
        "key4": KEY4,
        "errors": summary.get("errors", []),
        "total_cost": sum(m.get("cost_usd_total", 0.0) for m in models.values()),
    }
    for a, m in models.items():
        cost_per = m["cost_usd_total"] / max(1, m["n_total"])
        payload["models"][a] = {
            "model_id_actual": m["model_id_actual"],
            "n_total": m["n_total"],
            "n_evaluated": m["n_evaluated"],
            "field_accuracy": m["field_accuracy"],
            "field_accuracy_micro": m["field_accuracy_micro"],
            "json_valid_rate": m["json_valid_rate"],
            "all_fields_correct_rate": m["all_fields_correct_rate"],
            "by_category": {
                c: {"all_correct_rate": v["all_correct_rate"],
                    "field_acc_avg": (sum(v["field_accuracy"].values()) / len(v["field_accuracy"]))
                                       if v["field_accuracy"] else 0,
                    "n": v["n"]}
                for c, v in m["by_category"].items()
            },
            "key_4_fields": m["key_4_fields"],
            "cost_usd_total": m["cost_usd_total"],
            "cost_per_row": cost_per,
            "estimated_1M_cost_usd": m["estimated_1M_cost_usd"],
            "estimated_10k_cost_usd": cost_per * 10000,
            "avg_latency_ms": m["avg_latency_ms"],
            "p95_latency_ms": m["p95_latency_ms"],
            "avg_batch_latency_ms": m.get("avg_batch_latency_ms", 0),
            "p95_batch_latency_ms": m.get("p95_batch_latency_ms", 0),
            "batch_size": m.get("batch_size", 20),
            "throughput_per_req_per_s": m.get("throughput_per_req_per_s", 0),
            "throughput_rows_per_s_at_concurrency10": m.get("throughput_rows_per_s_at_concurrency10", 0),
            "est_10k_seconds_at_concurrency10": m.get("est_10k_seconds_at_concurrency10", 0),
            "est_100k_seconds_at_concurrency10": m.get("est_100k_seconds_at_concurrency10", 0),
            "error_samples": m.get("error_samples", [])[:30],
        }
    # 推荐
    rows = sorted(models.items(), key=lambda kv: -kv[1]["field_accuracy_micro"])
    payload["recommend"] = {
        "top_accuracy": rows[0][0] if rows else None,
        "cheapest": min(models.items(), key=lambda kv: kv[1]["estimated_1M_cost_usd"])[0] if models else None,
        "fastest": max(models.items(),
                       key=lambda kv: kv[1].get("throughput_rows_per_s_at_concurrency10", 0))[0]
                   if models else None,
    }
    return payload


HTML_TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>菜品打标 v3 - 多模型横评报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0f172a; --panel: #1e293b; --panel2: #334155; --text: #e2e8f0;
    --muted: #94a3b8; --accent: #38bdf8; --good: #10b981; --bad: #ef4444;
    --warn: #f59e0b;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC",
         "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }
  header { padding: 32px 48px 24px; border-bottom: 1px solid var(--panel2); }
  header h1 { margin: 0; font-size: 28px; font-weight: 600; }
  header .sub { color: var(--muted); margin-top: 6px; font-size: 14px; }
  main { padding: 24px 48px 80px; max-width: 1400px; margin: 0 auto; }
  .grid { display: grid; gap: 20px; }
  .grid-2 { grid-template-columns: 1fr 1fr; }
  .grid-3 { grid-template-columns: repeat(3, 1fr); }
  .grid-4 { grid-template-columns: repeat(4, 1fr); }
  @media (max-width: 1000px) { .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; } }
  .card { background: var(--panel); border-radius: 12px; padding: 20px;
          border: 1px solid var(--panel2); }
  .card h2 { font-size: 18px; margin: 0 0 12px; font-weight: 600; }
  .card h3 { font-size: 15px; margin: 16px 0 8px; font-weight: 600; color: var(--muted); }
  .stat { display: flex; flex-direction: column; gap: 4px; padding: 16px;
          background: var(--panel); border-radius: 12px; border: 1px solid var(--panel2); }
  .stat .label { color: var(--muted); font-size: 12px; text-transform: uppercase;
                 letter-spacing: 0.05em; }
  .stat .value { font-size: 24px; font-weight: 600; }
  .stat .value.good { color: var(--good); }
  .stat .sub { font-size: 12px; color: var(--muted); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--panel2); }
  th { background: rgba(255,255,255,0.04); font-weight: 600; color: var(--muted);
       position: sticky; top: 0; cursor: pointer; user-select: none; }
  th.sorted-asc::after { content: " ▲"; color: var(--accent); }
  th.sorted-desc::after { content: " ▼"; color: var(--accent); }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .pct { font-weight: 600; }
  .pct.gt95 { color: var(--good); }
  .pct.gt90 { color: #4ade80; }
  .pct.gt80 { color: var(--warn); }
  .pct.lt80 { color: var(--bad); }
  .chart-box { position: relative; height: 320px; }
  .chart-box.tall { height: 480px; }
  .heatmap { display: grid; gap: 1px; background: var(--panel2); border-radius: 8px;
             overflow: hidden; font-size: 12px; }
  .heatmap-cell { padding: 6px 8px; background: var(--panel); text-align: center;
                  font-variant-numeric: tabular-nums; }
  .heatmap-cell.head { background: var(--panel2); font-weight: 600; color: var(--muted); }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px;
           font-weight: 600; }
  .badge.win { background: rgba(16, 185, 129, 0.2); color: var(--good); }
  .badge.cheap { background: rgba(56, 189, 248, 0.2); color: var(--accent); }
  .badge.fast { background: rgba(245, 158, 11, 0.2); color: var(--warn); }
  details { background: var(--panel); border: 1px solid var(--panel2); border-radius: 8px;
            padding: 12px 16px; margin-bottom: 12px; }
  summary { cursor: pointer; font-weight: 600; }
  .err-case { margin-top: 12px; padding: 10px 12px; background: rgba(0,0,0,0.2);
              border-left: 3px solid var(--bad); border-radius: 4px; font-size: 13px; }
  .err-field { display: flex; gap: 8px; padding: 2px 0; font-family: ui-monospace, monospace; }
  .err-field .k { color: var(--accent); min-width: 180px; }
  .err-field .ex { color: var(--good); }
  .err-field .pr { color: var(--bad); }
  .toolbar { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  select, input[type="text"] {
    background: var(--panel); color: var(--text); border: 1px solid var(--panel2);
    border-radius: 6px; padding: 6px 10px; font-size: 13px;
  }
  .legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; color: var(--muted); margin-top: 12px; }
  .legend-item { display: flex; align-items: center; gap: 6px; }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .reco { padding: 16px; background: linear-gradient(135deg, rgba(56, 189, 248, 0.1), rgba(168, 85, 247, 0.1));
          border-radius: 12px; border: 1px solid var(--accent); margin-bottom: 16px; }
  .reco strong { color: var(--accent); }
  code { background: rgba(255,255,255,0.08); padding: 1px 6px; border-radius: 4px;
         font-family: ui-monospace, monospace; font-size: 12px; }
  .small { font-size: 11px; color: var(--muted); }
</style>
</head>
<body>
<header>
  <h1>菜品打标 v3 多模型横评</h1>
  <div class="sub" id="header-sub">loading…</div>
</header>
<main>

  <section class="card reco">
    <h2>📌 一句话推荐</h2>
    <div id="reco-content"></div>
  </section>

  <section class="grid grid-4" style="margin-bottom: 20px;">
    <div class="stat"><span class="label">Golden 样本</span><span class="value" id="stat-golden">—</span></div>
    <div class="stat"><span class="label">候选模型</span><span class="value" id="stat-models">—</span></div>
    <div class="stat"><span class="label">实际总成本</span><span class="value" id="stat-cost">—</span></div>
    <div class="stat"><span class="label">字段准确率冠军</span><span class="value good" id="stat-top">—</span><span class="sub" id="stat-top-sub"></span></div>
  </section>

  <section class="card" style="margin-bottom: 20px;">
    <h2>① 总体对比</h2>
    <p class="small">点击表头排序;字段准确率按 micro 平均(每条所有字段加权);"100万条预估" 按平均单条成本外推.</p>
    <div style="overflow-x: auto;">
      <table id="overall-table"></table>
    </div>
  </section>

  <section class="grid grid-2" style="margin-bottom: 20px;">
    <div class="card">
      <h2>② 准确率 × 成本 × 吞吐 散点图</h2>
      <p class="small">右上角(高准确率、高吞吐)+ 气泡小(低成本) = 最优.</p>
      <div class="chart-box tall"><canvas id="scatter"></canvas></div>
    </div>
    <div class="card">
      <h2>③ 4 大易错字段雷达图</h2>
      <p class="small">spec 预期的分水岭字段(prompt 锚点最易出错). 越外层越准.</p>
      <div class="chart-box tall"><canvas id="radar"></canvas></div>
    </div>
  </section>

  <section class="card" style="margin-bottom: 20px;">
    <h2>④ 15 字段全表 (柱状图)</h2>
    <p class="small">每个字段每模型的准确率. 用于看哪些字段是模型公敌(全军覆没) vs 模型分水岭.</p>
    <div class="chart-box tall"><canvas id="fields"></canvas></div>
  </section>

  <section class="grid grid-2" style="margin-bottom: 20px;">
    <div class="card">
      <h2>⑤ 按类别切片 (热力图)</h2>
      <p class="small">9 个类别 × N 模型. 颜色越绿表示该模型在该类别表现越好.</p>
      <div id="heatmap"></div>
    </div>
    <div class="card">
      <h2>⑥ 跑大批数据耗时 (concurrency=10)</h2>
      <p class="small">单请求实测 p95 latency 外推. 真实生产可能更快(concurrency=20+).</p>
      <div class="chart-box"><canvas id="throughput"></canvas></div>
    </div>
  </section>

  <section class="card" style="margin-bottom: 20px;">
    <h2>⑦ 典型错误 case</h2>
    <div class="toolbar">
      <select id="err-model"><option value="">所有模型</option></select>
      <select id="err-field"><option value="">所有字段</option></select>
      <input type="text" id="err-search" placeholder="搜索菜名">
    </div>
    <div id="err-list"></div>
  </section>

  <section class="card" style="margin-bottom: 20px;">
    <h2>⑧ 生产部署建议</h2>
    <div id="prod-table"></div>
  </section>

</main>

<script>
const PAYLOAD = __PAYLOAD__;
const pct = v => (v == null ? "—" : (v * 100).toFixed(1) + "%");
const pctClass = v => v == null ? "" : (v >= 0.95 ? "gt95" : v >= 0.90 ? "gt90" : v >= 0.80 ? "gt80" : "lt80");
const fmtMoney = v => v == null ? "—" : "$" + v.toFixed(v < 1 ? 4 : 2);
const fmtInt = v => v == null ? "—" : Math.round(v).toLocaleString();
const fmtDur = s => s < 60 ? `${s.toFixed(0)}s` : s < 3600 ? `${(s/60).toFixed(1)}min` : `${(s/3600).toFixed(1)}h`;

document.getElementById("header-sub").innerHTML =
  `golden=${PAYLOAD.n_golden} · 模型=${PAYLOAD.aliases.length} · 实际开销=$${PAYLOAD.total_cost.toFixed(4)}`;

// === stat cards ===
const top = PAYLOAD.recommend.top_accuracy;
const topM = PAYLOAD.models[top];
document.getElementById("stat-golden").textContent = PAYLOAD.n_golden;
document.getElementById("stat-models").textContent = PAYLOAD.aliases.length;
document.getElementById("stat-cost").textContent = "$" + PAYLOAD.total_cost.toFixed(4);
document.getElementById("stat-top").textContent = top || "—";
document.getElementById("stat-top-sub").textContent = topM ? `字段准确率 ${pct(topM.field_accuracy_micro)}` : "";

// === 一句话推荐 ===
const reco = PAYLOAD.recommend;
const topModel = PAYLOAD.models[reco.top_accuracy];
const cheapModel = PAYLOAD.models[reco.cheapest];
const fastModel = PAYLOAD.models[reco.fastest];
const recoEl = document.getElementById("reco-content");
const fastestCostPerRow = fastModel ? fastModel.cost_per_row : 0;
recoEl.innerHTML = `
  <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-top: 8px;">
    <div>
      <span class="badge win">准确率王</span>
      <div style="font-size: 18px; font-weight: 600; margin-top: 6px;">${reco.top_accuracy}</div>
      <div class="small">字段 ${pct(topModel?.field_accuracy_micro)} · 整条全对 ${pct(topModel?.all_fields_correct_rate)}</div>
      <div class="small">1万条 ~${fmtMoney(topModel?.estimated_10k_cost_usd)} / ${fmtDur(topModel?.est_10k_seconds_at_concurrency10)}</div>
    </div>
    <div>
      <span class="badge fast">吞吐王</span>
      <div style="font-size: 18px; font-weight: 600; margin-top: 6px;">${reco.fastest}</div>
      <div class="small">${(fastModel?.throughput_rows_per_s_at_concurrency10 || 0).toFixed(1)} 条/秒 (concurrency=10)</div>
      <div class="small">10万条 ~${fmtDur(fastModel?.est_100k_seconds_at_concurrency10)}</div>
    </div>
    <div>
      <span class="badge cheap">成本王</span>
      <div style="font-size: 18px; font-weight: 600; margin-top: 6px;">${reco.cheapest}</div>
      <div class="small">100万条 ~${fmtMoney(cheapModel?.estimated_1M_cost_usd)}</div>
      <div class="small">准确率 ${pct(cheapModel?.field_accuracy_micro)}</div>
    </div>
  </div>
`;

// === overall table (可排序) ===
const overallCols = [
  { key: "alias", label: "模型", fmt: v => v, sort: "str" },
  { key: "field_accuracy_micro", label: "字段准确率", fmt: pct, sort: "num", cls: "num pct" },
  { key: "all_fields_correct_rate", label: "整条全对", fmt: pct, sort: "num", cls: "num pct" },
  { key: "json_valid_rate", label: "JSON 合法率", fmt: pct, sort: "num", cls: "num pct" },
  { key: "p95_batch_latency_ms", label: "p95 batch (s)", fmt: v => (v/1000).toFixed(1), sort: "num", cls: "num" },
  { key: "throughput_rows_per_s_at_concurrency10", label: "吞吐(条/秒@c=10)", fmt: v => v.toFixed(1), sort: "num", cls: "num" },
  { key: "cost_usd_total", label: "测试成本", fmt: fmtMoney, sort: "num", cls: "num" },
  { key: "estimated_1M_cost_usd", label: "100万预估", fmt: v => "$" + Math.round(v), sort: "num", cls: "num" },
];

function buildOverallTable() {
  const tbl = document.getElementById("overall-table");
  const thead = document.createElement("thead");
  const trH = document.createElement("tr");
  overallCols.forEach((c, i) => {
    const th = document.createElement("th");
    th.textContent = c.label;
    if (c.cls && c.cls.includes("num")) th.classList.add("num");
    th.addEventListener("click", () => sortBy(i));
    trH.appendChild(th);
  });
  thead.appendChild(trH);
  tbl.appendChild(thead);
  const tbody = document.createElement("tbody");
  tbody.id = "overall-tbody";
  tbl.appendChild(tbody);
  state.sortIdx = 1; state.sortDir = -1;
  renderOverall();
}

const state = { sortIdx: 1, sortDir: -1 };

function rowsForOverall() {
  return PAYLOAD.aliases.map(a => {
    const m = PAYLOAD.models[a];
    return {
      alias: a,
      field_accuracy_micro: m.field_accuracy_micro,
      all_fields_correct_rate: m.all_fields_correct_rate,
      json_valid_rate: m.json_valid_rate,
      p95_batch_latency_ms: m.p95_batch_latency_ms,
      throughput_rows_per_s_at_concurrency10: m.throughput_rows_per_s_at_concurrency10,
      cost_usd_total: m.cost_usd_total,
      estimated_1M_cost_usd: m.estimated_1M_cost_usd,
    };
  });
}
function sortBy(i) {
  if (state.sortIdx === i) state.sortDir = -state.sortDir;
  else { state.sortIdx = i; state.sortDir = -1; }
  renderOverall();
}
function renderOverall() {
  const tbody = document.getElementById("overall-tbody");
  tbody.innerHTML = "";
  const rows = rowsForOverall();
  const col = overallCols[state.sortIdx];
  rows.sort((a, b) => {
    const av = a[col.key], bv = b[col.key];
    if (av == null) return 1;
    if (bv == null) return -1;
    if (col.sort === "num") return (av - bv) * state.sortDir;
    return String(av).localeCompare(String(bv)) * state.sortDir;
  });
  document.querySelectorAll("#overall-table th").forEach((th, i) => {
    th.classList.remove("sorted-asc", "sorted-desc");
    if (i === state.sortIdx) th.classList.add(state.sortDir === 1 ? "sorted-asc" : "sorted-desc");
  });
  rows.forEach(r => {
    const tr = document.createElement("tr");
    overallCols.forEach(c => {
      const td = document.createElement("td");
      const v = r[c.key];
      td.textContent = c.fmt(v);
      if (c.cls) td.className = c.cls;
      if (c.cls && c.cls.includes("pct")) td.classList.add(pctClass(v));
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

// === scatter ===
function drawScatter() {
  const data = PAYLOAD.aliases.map(a => {
    const m = PAYLOAD.models[a];
    return {
      label: a,
      data: [{
        x: m.estimated_1M_cost_usd,
        y: m.field_accuracy_micro * 100,
        r: Math.max(6, Math.min(40, m.throughput_rows_per_s_at_concurrency10 * 6 + 6)),
      }],
      backgroundColor: PAYLOAD.colors[a] + "cc",
      borderColor: PAYLOAD.colors[a],
      borderWidth: 2,
    };
  });
  new Chart(document.getElementById("scatter"), {
    type: "bubble",
    data: { datasets: data },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#e2e8f0" } },
        tooltip: { callbacks: { label: ctx => {
          const a = ctx.dataset.label;
          const m = PAYLOAD.models[a];
          return [
            `${a}`,
            `字段准确率: ${pct(m.field_accuracy_micro)}`,
            `100万成本: $${Math.round(m.estimated_1M_cost_usd)}`,
            `吞吐: ${m.throughput_rows_per_s_at_concurrency10.toFixed(1)} 条/秒`,
          ];
        }}}
      },
      scales: {
        x: { type: "logarithmic", title: { display: true, text: "100万条预估成本 ($, 对数轴)", color: "#94a3b8" },
             ticks: { color: "#94a3b8" }, grid: { color: "#334155" } },
        y: { title: { display: true, text: "字段准确率 (%)", color: "#94a3b8" },
             ticks: { color: "#94a3b8" }, grid: { color: "#334155" }, min: 80, max: 100 },
      }
    }
  });
}

// === radar (4 key fields) ===
function drawRadar() {
  const labels = PAYLOAD.key4.map(f => PAYLOAD.field_labels[f] || f);
  const datasets = PAYLOAD.aliases.map(a => {
    const m = PAYLOAD.models[a];
    return {
      label: a,
      data: PAYLOAD.key4.map(f => (m.key_4_fields[f] || 0) * 100),
      borderColor: PAYLOAD.colors[a],
      backgroundColor: PAYLOAD.colors[a] + "33",
      pointBackgroundColor: PAYLOAD.colors[a],
      borderWidth: 2,
    };
  });
  new Chart(document.getElementById("radar"), {
    type: "radar",
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#e2e8f0" } } },
      scales: { r: {
        min: 70, max: 100,
        ticks: { color: "#94a3b8", backdropColor: "transparent" },
        grid: { color: "#334155" }, angleLines: { color: "#334155" },
        pointLabels: { color: "#e2e8f0", font: { size: 12 } }
      } }
    }
  });
}

// === fields bar ===
function drawFields() {
  const fieldKeys = Object.keys(PAYLOAD.models[PAYLOAD.aliases[0]].field_accuracy).sort();
  const labels = fieldKeys.map(f => PAYLOAD.field_labels[f] || f);
  const datasets = PAYLOAD.aliases.map(a => {
    const m = PAYLOAD.models[a];
    return {
      label: a,
      data: fieldKeys.map(f => (m.field_accuracy[f] || 0) * 100),
      backgroundColor: PAYLOAD.colors[a],
    };
  });
  new Chart(document.getElementById("fields"), {
    type: "bar",
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#e2e8f0" } } },
      scales: {
        x: { ticks: { color: "#e2e8f0" }, grid: { color: "#334155" } },
        y: { min: 60, max: 100, ticks: { color: "#94a3b8" }, grid: { color: "#334155" },
             title: { display: true, text: "准确率 (%)", color: "#94a3b8" } }
      }
    }
  });
}

// === heatmap ===
function drawHeatmap() {
  const el = document.getElementById("heatmap");
  const aliases = PAYLOAD.aliases;
  const cats = PAYLOAD.categories;
  el.style.gridTemplateColumns = `120px repeat(${aliases.length}, 1fr)`;
  const cells = [`<div class="heatmap-cell head">类别</div>`];
  aliases.forEach(a => cells.push(`<div class="heatmap-cell head">${a}</div>`));
  cats.forEach(c => {
    cells.push(`<div class="heatmap-cell head" style="text-align:left;">${PAYLOAD.category_names[c] || c}</div>`);
    aliases.forEach(a => {
      const v = PAYLOAD.models[a].by_category[c]?.field_acc_avg ?? null;
      if (v == null) { cells.push(`<div class="heatmap-cell">—</div>`); return; }
      // 颜色: 80%↓ 红, 95%↑ 绿
      const t = Math.max(0, Math.min(1, (v - 0.80) / 0.15));
      const hue = t * 130;  // 0=red, 130=green-cyan
      const lightness = 22 + t * 12;
      cells.push(`<div class="heatmap-cell" style="background: hsl(${hue}, 60%, ${lightness}%)">${pct(v)}</div>`);
    });
  });
  el.innerHTML = cells.join("");
  el.className = "heatmap";
}

// === throughput bar ===
function drawThroughput() {
  const aliases = PAYLOAD.aliases;
  new Chart(document.getElementById("throughput"), {
    type: "bar",
    data: {
      labels: aliases,
      datasets: [{
        label: "10万条耗时 (小时)",
        data: aliases.map(a => PAYLOAD.models[a].est_100k_seconds_at_concurrency10 / 3600),
        backgroundColor: aliases.map(a => PAYLOAD.colors[a]),
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#e2e8f0" }, grid: { color: "#334155" } },
        y: { type: "logarithmic", ticks: { color: "#94a3b8" }, grid: { color: "#334155" },
             title: { display: true, text: "小时 (对数轴)", color: "#94a3b8" } }
      }
    }
  });
}

// === errors ===
function buildErrorList() {
  const modelSel = document.getElementById("err-model");
  PAYLOAD.aliases.forEach(a => {
    const opt = document.createElement("option");
    opt.value = a; opt.textContent = a;
    modelSel.appendChild(opt);
  });
  const allFields = new Set();
  PAYLOAD.aliases.forEach(a => {
    PAYLOAD.models[a].error_samples.forEach(e => {
      (e.wrong_fields || []).forEach(w => allFields.add(w.field));
    });
  });
  const fldSel = document.getElementById("err-field");
  Array.from(allFields).sort().forEach(f => {
    const opt = document.createElement("option");
    opt.value = f; opt.textContent = PAYLOAD.field_labels[f] || f;
    fldSel.appendChild(opt);
  });
  ["err-model","err-field","err-search"].forEach(id => {
    document.getElementById(id).addEventListener("input", renderErrors);
  });
  renderErrors();
}

function renderErrors() {
  const mFilter = document.getElementById("err-model").value;
  const fFilter = document.getElementById("err-field").value;
  const sFilter = document.getElementById("err-search").value.trim().toLowerCase();
  const out = document.getElementById("err-list");
  const blocks = [];
  PAYLOAD.aliases.forEach(a => {
    if (mFilter && a !== mFilter) return;
    const samples = PAYLOAD.models[a].error_samples.filter(s => {
      if (sFilter && !(s.raw_name || "").toLowerCase().includes(sFilter)) return false;
      if (fFilter && !(s.wrong_fields || []).some(w => w.field === fFilter)) return false;
      return true;
    });
    if (samples.length === 0) return;
    const cases = samples.slice(0, 10).map((s, i) => {
      const fields = (s.wrong_fields || []).map(w => `
        <div class="err-field">
          <span class="k">${PAYLOAD.field_labels[w.field] || w.field}</span>
          <span class="ex">expected=${JSON.stringify(w.expected)}</span>
          <span class="pr">predicted=${JSON.stringify(w.predicted)}</span>
        </div>`).join("");
      return `
        <div class="err-case">
          <strong>${s.dish_id} · ${s.raw_name}</strong>
          <span class="small">(${PAYLOAD.category_names[s.category_tag] || s.category_tag})</span>
          ${fields}
        </div>`;
    }).join("");
    blocks.push(`
      <details ${mFilter ? "open" : ""}>
        <summary>${a} <span class="small">(${samples.length} 个错误)</span></summary>
        ${cases}
      </details>
    `);
  });
  out.innerHTML = blocks.length ? blocks.join("") : `<p class="small">无匹配</p>`;
}

// === 生产建议表 ===
function buildProdTable() {
  const m = PAYLOAD.models;
  const top = m[PAYLOAD.recommend.top_accuracy];
  const haiku = Object.values(m).find(x => x.model_id_actual.includes("haiku")) ||
                m[PAYLOAD.aliases[1]];
  const cheap = m[PAYLOAD.recommend.cheapest];
  const tbl = `
    <table>
      <thead><tr><th>场景</th><th>推荐</th><th>1万条耗时</th><th>1万条成本</th><th>10万条耗时</th><th>准确率</th></tr></thead>
      <tbody>
        <tr><td>≤ 1万 / 时间敏感</td>
            <td><code>${PAYLOAD.recommend.top_accuracy}</code></td>
            <td class="num">${fmtDur(top.est_10k_seconds_at_concurrency10)}</td>
            <td class="num">${fmtMoney(top.estimated_10k_cost_usd)}</td>
            <td class="num">${fmtDur(top.est_100k_seconds_at_concurrency10)}</td>
            <td class="num pct ${pctClass(top.field_accuracy_micro)}">${pct(top.field_accuracy_micro)}</td></tr>
        <tr><td>1万-10万 / 吞吐优先</td>
            <td><code>${PAYLOAD.recommend.fastest}</code></td>
            <td class="num">${fmtDur(m[PAYLOAD.recommend.fastest].est_10k_seconds_at_concurrency10)}</td>
            <td class="num">${fmtMoney(m[PAYLOAD.recommend.fastest].estimated_10k_cost_usd)}</td>
            <td class="num">${fmtDur(m[PAYLOAD.recommend.fastest].est_100k_seconds_at_concurrency10)}</td>
            <td class="num pct ${pctClass(m[PAYLOAD.recommend.fastest].field_accuracy_micro)}">${pct(m[PAYLOAD.recommend.fastest].field_accuracy_micro)}</td></tr>
        <tr><td>≥ 10万 / 极致省钱(离线)</td>
            <td><code>${PAYLOAD.recommend.cheapest}</code></td>
            <td class="num">${fmtDur(cheap.est_10k_seconds_at_concurrency10)}</td>
            <td class="num">${fmtMoney(cheap.estimated_10k_cost_usd)}</td>
            <td class="num">${fmtDur(cheap.est_100k_seconds_at_concurrency10)}</td>
            <td class="num pct ${pctClass(cheap.field_accuracy_micro)}">${pct(cheap.field_accuracy_micro)}</td></tr>
      </tbody>
    </table>
    <p class="small" style="margin-top:12px;">分层建议:若主跑模型字段准确率 < 95%,可对 <b>JSON 不合法 / 关键 4 字段反直觉</b> 的样本用 <code>${PAYLOAD.recommend.top_accuracy}</code> 兜底, 拉准确率到接近冠军.</p>
  `;
  document.getElementById("prod-table").innerHTML = tbl;
}

// === init ===
buildOverallTable();
drawScatter();
drawRadar();
drawFields();
drawHeatmap();
drawThroughput();
buildErrorList();
buildProdTable();
</script>
</body>
</html>
"""


def main() -> int:
    if not SUMMARY_PATH.exists():
        print("ERROR: score_summary.json missing (run score.py first)", flush=True)
        return 2
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    golden = load_golden()
    payload = build_payload(summary, golden)
    payload_json = json.dumps(payload, ensure_ascii=False, default=float)
    # 不用 .replace 一次性 — payload 巨大且含 $1 等, 用 placeholder split
    html_out = HTML_TPL.replace("__PAYLOAD__", payload_json)
    OUT.write_text(html_out, encoding="utf-8")
    print(f"[report-html] wrote {OUT}  ({OUT.stat().st_size // 1024} KB)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

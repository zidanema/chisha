// Workflow A mocks — TS port of chisha-debug/project/wa-mock.jsx + wa-rounds-mock.jsx.
// Phase 1: 视觉验证用. Phase 2b: 真后端 GET /api/traces + /api/trace/{id}/round/{rid} 替代.
//
// 与原设计稿差异:
//   - intent 字段集改成 V2 schema (refine_intent_v2.RefineIntentV2), 不用原 V1 12 字段
//   - round 数据走 React props 下传, 不再 window.MOCK swap

import { MOCK_SESSION } from "./session";
import type { FinalRow, L1Trace, L2Combo, L2KPI, L2Trace, L3Trace,
  RoundIntentV2, RoundRecord, TraceMeta, WaTrace } from "../types/trace";

// ─── TraceBrowser fixtures: 38 traces 跨多日 ────────────────
const REST_POOL = [
  "椰客椰子鸡 (科兴店)", "Wagas (深圳湾店)", "汤先生 (后海店)",
  "西少爷肉夹馍 (深圳湾店)", "真功夫 (科兴店)", "嘉禾一品 (海岸城店)",
  "和府捞面 (科技园店)", "南城香 (深圳湾店)", "云海肴 (深圳湾店)",
  "新元素 (科技园店)", "Element Fresh (深圳湾店)", "霸蛮米粉 (后海店)",
  "蛙小侠 (海岸城店)", "外婆家 (海岸城店)", "西贝莜面村 (海岸城店)",
  "鸡公煲·小山 (科兴店)", "井格老灶火锅 (海岸城店)", "太二酸菜鱼 (深圳湾店)",
];

function pad(n: number): string { return n < 10 ? "0" + n : "" + n; }
function dateBack(daysAgo: number): string {
  const base = new Date(2026, 4, 16);  // 2026-05-16
  base.setDate(base.getDate() - daysAgo);
  return `${base.getFullYear()}-${pad(base.getMonth() + 1)}-${pad(base.getDate())}`;
}

let _seed = 7;
function rnd(): number { _seed = (_seed * 9301 + 49297) % 233280; return _seed / 233280; }

function buildTraceList(): TraceMeta[] {
  const out: TraceMeta[] = [];
  for (let i = 0; i < 38; i++) {
    const daysAgo = Math.floor(i / 2);
    const isLunch = i % 2 === 0;
    const hour = isLunch ? 11 + Math.floor(rnd() * 2) : 18 + Math.floor(rnd() * 2);
    const minute = Math.floor(rnd() * 60);
    const rest = REST_POOL[Math.floor(rnd() * REST_POOL.length)];
    const refineCount = rnd() < 0.45 ? 1 + Math.floor(rnd() * 4) : 0;
    const sourceSandbox = rnd() < 0.18;
    const fbRand = rnd();
    let feedback: TraceMeta["feedback"] = null;
    if (fbRand < 0.25) feedback = { type: "accepted", rank: 1 + Math.floor(rnd() * 5) };
    else if (fbRand < 0.45) feedback = { type: "rated", count: 1 + Math.floor(rnd() * 5) };
    else if (fbRand < 0.5) feedback = { type: "stopped" };
    const statusRand = rnd();
    const status: TraceMeta["status"] =
      statusRand < 0.85 ? "ok" : statusRand < 0.95 ? "fallback" : "warn";
    out.push({
      id: `sess_${String(i).padStart(4, "0")}_${["a7","b3","c1","d8","e5"][i % 5]}${pad(Math.floor(rnd() * 99))}`,
      date: dateBack(daysAgo),
      time: `${pad(hour)}:${pad(minute)}`,
      daysAgo, meal: isLunch ? "lunch" : "dinner",
      finalTop1: rest,
      refineCount, latestRound: refineCount > 0 ? `R${1 + refineCount}` : "R1",
      source: sourceSandbox ? "sandbox" : "real",
      sandboxDay: sourceSandbox ? Math.floor(rnd() * 14) : null,
      feedback, status,
      latency_ms: 1800 + Math.floor(rnd() * 1500),
    });
  }
  // 第一条 = 今天 12:04 的 active trace (匹配 MOCK_SESSION)
  out[0] = {
    ...out[0],
    id: MOCK_SESSION.session_id,
    date: "2026-05-16", time: "12:04",
    daysAgo: 0, meal: "lunch",
    finalTop1: "椰客椰子鸡 (科兴店)",
    refineCount: 3, latestRound: "R4",
    source: "real", sandboxDay: null,
    feedback: { type: "accepted", rank: 1 },
    status: "ok",
    latency_ms: MOCK_SESSION.total_latency_ms,
  };
  return out;
}

export const MOCK_TRACES: TraceMeta[] = buildTraceList();

// ─── Per-round full data (active trace 的 4 round) ──────────
// 基线 = MOCK_SESSION (R1); R2/R3/R4 在基线上做小幅 mutation 模拟 refine 链路.

function deepClone<T>(o: T): T { return JSON.parse(JSON.stringify(o)); }

function liftToTop(combos: L2Combo[], restName: string): L2Combo[] {
  const i = combos.findIndex((c) => c.restaurant === restName);
  if (i < 0) return combos;
  const c = combos[i];
  combos.splice(i, 1);
  combos.unshift({ ...c, total_score: c.total_score + 0.2 });
  combos.forEach((c, j) => (c.rank = j + 1));
  return combos;
}

function dropMatching(
  combos: L2Combo[],
  predicate: (c: L2Combo) => boolean,
  count: number,
): L2Combo[] {
  let removed = 0;
  return combos.filter((c) => {
    if (removed >= count) return true;
    if (predicate(c)) { removed++; return false; }
    return true;
  });
}

// ─── R1 = MOCK_SESSION 原值 ────────────────────────────────
const R1_INTENT: RoundIntentV2 | null = null;   // 首轮无 refine_intent

// ─── R2 · "换一组" — novelty 重排 ─────────────────────────
const R2 = (() => {
  const L1: L1Trace = deepClone(MOCK_SESSION.l1);
  L1.restaurant_bans = [
    { rest: "椰客椰子鸡 (科兴店)", reason: "novelty 排除",
      detail: "R1 已采纳 + 24h 内 cooldown", count: 1 },
    ...MOCK_SESSION.l1.restaurant_bans.slice(0, 5),
  ];
  L1.ban_reason_agg = [
    { reason: "novelty cooldown (R1 已采纳)", count: 1 },
    { reason: "ETA 超限 (>45min)", count: 47 },
    { reason: "近 7 天吃过", count: 24 },
    { reason: "avoid_restaurants 命中", count: 18 },
    { reason: "价格异常 / 缺品类", count: 14 },
  ];
  L1.top_restaurants = MOCK_SESSION.l1.top_restaurants.slice().reverse().slice(0, 20);

  const L2_COMBOS = liftToTop(deepClone(MOCK_SESSION.l2.combos), "汤先生 (后海店)");
  const L2_KPI: L2KPI = {
    ...MOCK_SESSION.l2.kpi,
    score_min: L2_COMBOS[L2_COMBOS.length - 1].total_score.toFixed(3),
    score_max: L2_COMBOS[0].total_score.toFixed(3),
    restaurants_before_cap: 78, restaurants_after_cap: 33,
  };
  const L2: L2Trace = { ...MOCK_SESSION.l2, combos: L2_COMBOS, kpi: L2_KPI };

  const L3: L3Trace = deepClone(MOCK_SESSION.l3);
  L3.latency_ms = 2104;
  L3.input_tokens = 4912;
  L3.output_tokens = 588;
  L3.cache_read_input_tokens = 4124;
  if (L3.raw_response_blocks[0]?.type === "text") {
    L3.raw_response_blocks[0].text =
`用户 R2 = "换一组"，触发 novelty 强约束：上一轮 top1 (椰客椰子鸡) 进入 24h cooldown.
- 新 top 候选：cmb_005 汤先生 (低脂合菜 + 杂粮饭，最近 14d 未吃) — 作 exploit #1
- cmb_002 Wagas 深圳湾店保留 (蛋白 60g) — exploit #2
- cmb_017 椰客椰子鸡【后海店】不同门店，未触发 cooldown — exploit #3 (替代被 cooldown 的科兴店)
- explore：cmb_028 新元素藜麦碗 (用户从未吃过) + cmb_034 真功夫海带排骨汤
约束 check：novelty cooldown ✓ / 同店 ≤ 1 ✓`;
  }

  const FINAL: FinalRow[] = deepClone(MOCK_SESSION.final);
  FINAL[0] = { ...FINAL[0], rank: 1, kind: "exploit", combo_id: "cmb_005",
    restaurant: "汤先生 (后海店)", distance_km: 2.1, eta_min: 31, total_price: 52,
    score: 1.272, fit_score: 0.79,
    dishes: [{ name: "番茄牛尾汤套餐", price: 38 }, { name: "杂粮饭", price: 14 }],
    reason: "低脂合菜 + 杂粮饭，每份 30g 蛋白；R1 椰客刚吃过，换一家。" };
  FINAL[1] = { ...FINAL[1], rank: 2, kind: "exploit", combo_id: "cmb_017",
    restaurant: "椰客椰子鸡 (后海店)", distance_km: 2.4, eta_min: 28, total_price: 88,
    score: 1.162, fit_score: 0.77,
    dishes: [{ name: "椰子鸡汤锅 (单人)", price: 68 }, { name: "凉拌秋葵", price: 20 }],
    reason: "同样的椰子汤底，换后海店，避开 24h cooldown." };
  FINAL[2] = { ...FINAL[2], rank: 3, restaurant: "Wagas (深圳湾店)" };
  FINAL[3] = { ...FINAL[3], rank: 4, kind: "explore", combo_id: "cmb_028",
    restaurant: "新元素 (科技园店)", distance_km: 1.1, eta_min: 23, total_price: 62,
    score: 1.014, fit_score: 0.71,
    dishes: [{ name: "藜麦牛腩碗", price: 48 }, { name: "罗勒鸡汤", price: 14 }],
    reason: "藜麦杂粮 + 罗勒鸡汤，从未吃过的轻食." };
  FINAL[4] = { ...FINAL[4], rank: 5, restaurant: "真功夫 (科兴店)" };

  const intent: RoundIntentV2 = {
    redirect: { cuisine_want: [], cuisine_avoid: [], ingredient_want: [],
      ingredient_avoid: ["加工肉", "动物内脏"], brand_avoid: [] },
    constrain: { oil: null, price_max: 80, functional: {} },
    reject_previous: true,
    raw_understanding: "用户要求轮换；不点名拒绝具体餐厅，触发 novelty 提权.",
    raw_text: "换一组，这几个我都吃过",
    schema_version: "2.0",
  };
  return { L1, L2, L3, FINAL, intent };
})();

// ─── R3 · "想喝汤，别给我面食和米饭" ──────────────────────
const R3 = (() => {
  const L1: L1Trace = deepClone(MOCK_SESSION.l1);
  L1.funnel = deepClone(MOCK_SESSION.l1.funnel);
  L1.funnel[1].value = 4128;  L1.funnel[1].dropped = 6995;
  L1.funnel[2].value = 2702;  L1.funnel[2].dropped = 1426;
  L1.funnel[4].value = 1741;
  L1.funnel[5].value = 1180;  L1.funnel[5].dropped = 561;
  L1.funnel[6].value = 1180;
  L1.dish_drops = [
    { reason: "grain_type = noodle (refine penalty)", count: 412, layer: "hard" },
    { reason: "grain_type = rice (refine penalty)",   count: 318, layer: "hard" },
    { reason: "restaurant = 西少爷 (用户点名拒绝)",     count: 18,  layer: "hard" },
    { reason: "price > budget (单菜 > ¥45)",          count: 2148, layer: "hard" },
    { reason: "oil_level = high (规则: 减脂)",          count: 1937, layer: "hard" },
    { reason: "main_ingredient_type = 加工肉 (avoid)", count: 1024, layer: "hard" },
    { reason: "wetness = dry & 已是干 (多样性)",        count: 728, layer: "diversity" },
    { reason: "combo 总价 > ¥80 (上限)",               count: 561, layer: "price" },
  ];
  L1.restaurant_bans = [
    { rest: "西少爷肉夹馍 (深圳湾店)", reason: "用户点名拒绝", detail: "refine: '西少爷那个不要了'", count: 1 },
    { rest: "和府捞面 (科技园店)", reason: "全部 combo grain:noodle", detail: "all 14 combos penalty=-0.30", count: 14 },
    { rest: "霸蛮米粉 (后海店)", reason: "全部 combo grain:noodle", detail: "all 11 combos penalty=-0.30", count: 11 },
    ...MOCK_SESSION.l1.restaurant_bans.slice(0, 4),
  ];
  L1.ban_reason_agg = [
    { reason: "grain penalty (noodle / rice)", count: 730 },
    { reason: "ETA 超限 (>45min)", count: 47 },
    { reason: "近 7 天吃过", count: 23 },
    { reason: "avoid_restaurants 命中", count: 18 },
  ];

  const L2_COMBOS = dropMatching(
    deepClone(MOCK_SESSION.l2.combos),
    (c) => /和府|霸蛮|西少爷|桂林米粉/.test(c.restaurant), 6,
  );
  L2_COMBOS.forEach((c, j) => (c.rank = j + 1));
  const L2: L2Trace = {
    ...MOCK_SESSION.l2,
    combos: L2_COMBOS,
    kpi: { ...MOCK_SESSION.l2.kpi, restaurants_before_cap: 71, restaurants_after_cap: 28 },
  };

  const L3: L3Trace = deepClone(MOCK_SESSION.l3);
  L3.latency_ms = 2310;
  if (L3.raw_response_blocks[0]?.type === "text") {
    L3.raw_response_blocks[0].text =
`用户 R3 = "想喝汤，别给我面食和米饭，西少爷那个不要了".
- 强约束：grain:noodle / rice penalty -0.30 / -0.18；西少爷 -1.0
- soup 类 boost +0.22；wetness:wet +0.18
- 新 top 候选：cmb_001 椰客椰子鸡 重回 #1 (椰子汤底 + 无主食)
- cmb_034 真功夫海带排骨汤 + 杂粮饭 — 注：杂粮非面/非饭，符合
- cmb_017 椰客椰子鸡 (后海店) + 凉拌秋葵 — exploit #2
- explore：cmb_011 云海肴汽锅鸡 (云南汽锅 wet ✓) + cmb_038 蛙小侠酸菜鱼 (鱼 + 汤底)`;
  }
  const FINAL: FinalRow[] = deepClone(MOCK_SESSION.final);

  const intent: RoundIntentV2 = {
    redirect: { ingredient_want: ["鱼", "禽"], ingredient_avoid: ["加工肉", "动物内脏"],
      brand_avoid: ["西少爷肉夹馍"], food_form_avoid: ["面", "米饭"] },
    constrain: { oil: null, price_max: 80, functional: {} },
    raw_understanding: "明确想要汤水类；主食拒面与米；点名拒绝西少爷.",
    raw_text: "想喝汤，别给我面食和米饭",
    schema_version: "2.0",
  };
  return { L1, L2, L3, FINAL, intent };
})();

// ─── R4 · "别要重的，太油了" ─────────────────────────────
const R4 = (() => {
  const L1: L1Trace = deepClone(MOCK_SESSION.l1);
  L1.funnel = deepClone(MOCK_SESSION.l1.funnel);
  L1.funnel[1].value = 3784;  L1.funnel[1].dropped = 7339;
  L1.funnel[2].value = 2486;  L1.funnel[2].dropped = 1298;
  L1.funnel[4].value = 1684;
  L1.funnel[5].value = 1142;  L1.funnel[5].dropped = 542;
  L1.funnel[6].value = 1142;
  L1.dish_drops = [
    { reason: "oil_level >= mid (refine: '别要重的')", count: 1284, layer: "hard" },
    { reason: "cuisine = 川 / 湘 (refine penalty)",    count: 642,  layer: "hard" },
    { reason: "cook = 油炸 (refine avoid)",            count: 384,  layer: "hard" },
    { reason: "grain_type = noodle / rice (累计)",      count: 730,  layer: "hard" },
    { reason: "restaurant = 西少爷 (累计)",             count: 18,   layer: "hard" },
    { reason: "price > budget (单菜 > ¥45)",          count: 2148, layer: "hard" },
    { reason: "main_ingredient_type = 加工肉 (avoid)", count: 1024, layer: "hard" },
    { reason: "combo 总价 > ¥80 (上限)",               count: 542,  layer: "price" },
  ];
  L1.restaurant_bans = [
    { rest: "井格老灶火锅 (海岸城店)", reason: "全部 combo 重油重辣", detail: "all 12 combos oil=high", count: 12 },
    { rest: "太二酸菜鱼 (深圳湾店)", reason: "cuisine = 川 (refine)", detail: "all 9 combos cuisine penalty", count: 9 },
    { rest: "外婆家 (海岸城店)", reason: "≥3 道 mid+ oil", detail: "9/12 combos mid+", count: 9 },
    { rest: "西少爷肉夹馍 (深圳湾店)", reason: "累计点名拒绝", detail: "from R3", count: 1 },
    ...MOCK_SESSION.l1.restaurant_bans.slice(0, 3),
  ];
  L1.ban_reason_agg = [
    { reason: "重油 / 重辣 (refine)", count: 1668 },
    { reason: "grain penalty (累计)", count: 730 },
    { reason: "ETA 超限 (>45min)", count: 47 },
    { reason: "近 7 天吃过", count: 23 },
  ];

  const L2_COMBOS = dropMatching(
    deepClone(MOCK_SESSION.l2.combos),
    (c) => /井格|太二|外婆家|和府|霸蛮|西少爷/.test(c.restaurant), 10,
  );
  L2_COMBOS.forEach((c, j) => (c.rank = j + 1));
  const L2: L2Trace = {
    ...MOCK_SESSION.l2,
    combos: L2_COMBOS,
    kpi: { ...MOCK_SESSION.l2.kpi, restaurants_before_cap: 62, restaurants_after_cap: 24 },
  };

  const L3: L3Trace = deepClone(MOCK_SESSION.l3);
  L3.latency_ms = 2208;
  if (L3.raw_response_blocks[0]?.type === "text") {
    L3.raw_response_blocks[0].text =
`用户 R4 = "再来一轮，别要重的，太油了". 累计约束：
- soup + 无面/饭 (R3 继承)
- 新增：oil_level >= mid 全部 ban；川/湘菜系 ban；油炸 cook ban
- 候选都偏清淡：cmb_001 椰子鸡 (low oil) — exploit #1 不变
- cmb_011 云海肴汽锅鸡 — exploit #2 (清汤 + 蒸法)
- cmb_028 Element Fresh 三文鱼藜麦碗 — exploit #3 (生蒸 + low oil)
- 上一轮的 cmb_038 蛙小侠 (川味酸菜) 在此轮被剔除`;
  }

  const FINAL: FinalRow[] = deepClone(MOCK_SESSION.final);
  const intent: RoundIntentV2 = {
    redirect: {
      cuisine_avoid: ["川菜", "湘菜"],
      ingredient_want: ["鱼", "禽"], ingredient_avoid: ["加工肉", "动物内脏", "油炸"],
      brand_avoid: ["西少爷肉夹馍"],
      cooking_method_avoid: ["油炸", "干煸", "重煎"],
      food_form_avoid: ["面", "米饭"],
    },
    constrain: { oil: "low", price_max: 80, functional: {} },
    raw_understanding: "用户加强清淡偏好；累计：汤 + 清淡 + 拒重油重辣.",
    raw_text: "再来一轮，别要重的，太油了",
    schema_version: "2.0",
  };
  return { L1, L2, L3, FINAL, intent };
})();

// ─── 组装 active trace 的 4 round ───────────────────────────
export const ACTIVE_TRACE_ROUNDS: RoundRecord[] = [
  {
    id: "R1", label: "原始", started_at: "12:04",
    user_input: null, intent_v2: R1_INTENT,
    kpi: { combos: 1207, l2_top: 60, top1: "椰客椰子鸡 (科兴店)", latency_ms: 2841 },
    diff: null,
    l1: MOCK_SESSION.l1, l2: MOCK_SESSION.l2, l3: MOCK_SESSION.l3, final: MOCK_SESSION.final,
  },
  {
    id: "R2", label: "换一组", started_at: "12:06",
    user_input: "换一组，这几个我都吃过", intent_v2: R2.intent,
    kpi: { combos: 1207, l2_top: 60, top1: "汤先生 (后海店)", latency_ms: 2104 },
    diff: { vs: "R1", in: 4, out: 4, up: 1, down: 0 },
    l1: R2.L1, l2: R2.L2, l3: R2.L3, final: R2.FINAL,
  },
  {
    id: "R3", label: "想喝汤", started_at: "12:09",
    user_input: "想喝汤，别给我面食和米饭", intent_v2: R3.intent,
    kpi: { combos: 1180, l2_top: 60, top1: "椰客椰子鸡 (科兴店)", latency_ms: 2310 },
    diff: { vs: "R2", in: 3, out: 3, up: 2, down: 1 },
    l1: R3.L1, l2: R3.L2, l3: R3.L3, final: R3.FINAL,
  },
  {
    id: "R4", label: "别要重的", started_at: "12:12",
    user_input: "再来一轮，别要重的，太油了", intent_v2: R4.intent,
    kpi: { combos: 1142, l2_top: 60, top1: "椰客椰子鸡 (科兴店)", latency_ms: 2208 },
    diff: { vs: "R3", in: 2, out: 2, up: 1, down: 2 },
    l1: R4.L1, l2: R4.L2, l3: R4.L3, final: R4.FINAL,
  },
];

// 完整 active trace
export const ACTIVE_WA_TRACE: WaTrace = {
  meta: MOCK_TRACES[0],
  rounds: ACTIVE_TRACE_ROUNDS,
};

// 给非 active trace 用的兜底 single-round 数据 (mock 用)
export function makeSingleRoundTrace(meta: TraceMeta): WaTrace {
  return {
    meta,
    rounds: [{
      id: "R1", label: "原始", started_at: meta.time,
      user_input: null, intent_v2: null,
      kpi: { combos: 1200, l2_top: 60, top1: meta.finalTop1, latency_ms: meta.latency_ms },
      diff: null,
      l1: MOCK_SESSION.l1, l2: MOCK_SESSION.l2, l3: MOCK_SESSION.l3, final: MOCK_SESSION.final,
    }],
  };
}

// 按 trace id 查 — Phase 2b 替换成后端 fetch.
export function getMockTrace(traceId: string): WaTrace {
  if (traceId === ACTIVE_WA_TRACE.meta.id) return ACTIVE_WA_TRACE;
  const meta = MOCK_TRACES.find((t) => t.id === traceId);
  if (!meta) return ACTIVE_WA_TRACE;
  return makeSingleRoundTrace(meta);
}

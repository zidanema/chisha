// wa-mock.jsx — extends window.MOCK with multi-trace + multi-round refine fixtures

(function () {
  // ── A1 fixtures: ~40 traces with varied properties ──────────
  const REST_POOL = [
    "椰客椰子鸡 (科兴店)", "Wagas (深圳湾店)", "汤先生 (后海店)",
    "西少爷肉夹馍 (深圳湾店)", "真功夫 (科兴店)", "嘉禾一品 (海岸城店)",
    "和府捞面 (科技园店)", "南城香 (深圳湾店)", "云海肴 (深圳湾店)",
    "新元素 (科技园店)", "Element Fresh (深圳湾店)", "霸蛮米粉 (后海店)",
    "蛙小侠 (海岸城店)", "外婆家 (海岸城店)", "西贝莜面村 (海岸城店)",
    "鸡公煲·小山 (科兴店)", "井格老灶火锅 (海岸城店)", "太二酸菜鱼 (深圳湾店)",
  ];

  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  // generate a date string going back N days from 2026-05-16
  function dateBack(daysAgo) {
    const base = new Date(2026, 4, 16);
    base.setDate(base.getDate() - daysAgo);
    return base.getFullYear() + "-" + pad(base.getMonth() + 1) + "-" + pad(base.getDate());
  }

  const TRACES = [];
  let seed = 7;
  function rnd() { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; }

  for (let i = 0; i < 38; i++) {
    const daysAgo = Math.floor(i / 2);
    const isLunch = i % 2 === 0;
    const hour = isLunch ? 11 + Math.floor(rnd() * 2) : 18 + Math.floor(rnd() * 2);
    const minute = Math.floor(rnd() * 60);
    const rest = REST_POOL[Math.floor(rnd() * REST_POOL.length)];
    const refineCount = rnd() < 0.45 ? 1 + Math.floor(rnd() * 4) : 0; // 0..4 extra rounds
    const sourceSandbox = rnd() < 0.18;
    const fbRand = rnd();
    let feedback = null;
    if (fbRand < 0.25) feedback = { type: "accepted", rank: 1 + Math.floor(rnd() * 5) };
    else if (fbRand < 0.45) feedback = { type: "rated", count: 1 + Math.floor(rnd() * 5) };
    else if (fbRand < 0.5) feedback = { type: "stopped" };
    const statusRand = rnd();
    const status = statusRand < 0.85 ? "ok" : statusRand < 0.95 ? "fallback" : "warn";

    TRACES.push({
      id: `sess_${String(i).padStart(4, "0")}_${["a7","b3","c1","d8","e5"][i % 5]}${pad(Math.floor(rnd() * 99))}`,
      date: dateBack(daysAgo),
      time: `${pad(hour)}:${pad(minute)}`,
      daysAgo,
      meal: isLunch ? "lunch" : "dinner",
      finalTop1: rest,
      refineCount, // number of additional rounds R2/R3/...; total rounds = 1 + refineCount
      latestRound: refineCount > 0 ? `R${1 + refineCount}` : "R1",
      source: sourceSandbox ? "sandbox" : "real",
      sandboxDay: sourceSandbox ? Math.floor(rnd() * 14) : null,
      feedback,
      status,
      latency_ms: 1800 + Math.floor(rnd() * 1500),
    });
  }

  // Mark first one as "今天最新" (matches existing single mock trace context)
  TRACES[0] = {
    ...TRACES[0],
    id: window.MOCK.session_id,
    date: "2026-05-16",
    time: "12:04",
    daysAgo: 0,
    meal: "lunch",
    finalTop1: "椰客椰子鸡 (科兴店)",
    refineCount: 3, // R1 + R2 + R3 + R4
    latestRound: "R4",
    source: "real",
    sandboxDay: null,
    feedback: { type: "accepted", rank: 1 },
    status: "ok",
    latency_ms: window.MOCK.total_latency_ms,
  };

  // ── A3 fixtures: 4 rounds of refine for the active trace ────
  // Each round has user_text, parsed intent (12 fields), kpi
  const ROUNDS = [
    {
      id: "R1",
      label: "原始",
      time: "12:04",
      user_text: null,                // first round has no refine text
      intent: {
        cuisine_want: [], cuisine_avoid: [],
        ingredient_want: [], ingredient_avoid: ["加工肉", "动物内脏"],
        taste_want: [], taste_avoid: [],
        cook_want: ["steamed", "boiled", "stewed", "cold-mix"],
        portion: null,
        grain_pref: null,
        price_band: "≤80",
        raw_taste: "减脂控油 · 高蛋白 (profile)",
        freeform_note: null,
      },
      kpi: { combos: 1207, l2_top: 60, top1: "椰客椰子鸡 (科兴店)", latency_ms: 2841 },
      diff: null,
    },
    {
      id: "R2",
      label: "换一组",
      time: "12:06",
      user_text: "换一组，这几个我都吃过",
      intent: {
        cuisine_want: [], cuisine_avoid: [],
        ingredient_want: [], ingredient_avoid: ["加工肉", "动物内脏"],
        taste_want: [], taste_avoid: [],
        cook_want: [],
        portion: null,
        grain_pref: null,
        price_band: "≤80",
        raw_taste: null,
        freeform_note: "用户要求轮换；不点名拒绝具体餐厅，触发 novelty 提权。",
      },
      kpi: { combos: 1207, l2_top: 60, top1: "汤先生 (后海店)", latency_ms: 2104 },
      diff: { vs: "R1", in: 4, out: 4, up: 1, down: 0 },
    },
    {
      id: "R3",
      label: "想喝汤",
      time: "12:09",
      user_text: "想喝汤，别给我面食和米饭",
      intent: {
        cuisine_want: [], cuisine_avoid: [],
        ingredient_want: ["鱼", "禽"], ingredient_avoid: ["加工肉", "动物内脏"],
        taste_want: ["汤水", "wet"], taste_avoid: [],
        cook_want: ["soup", "stewed"],
        portion: null,
        grain_pref: "无主食或杂粮",
        price_band: "≤80",
        raw_taste: null,
        freeform_note: "明确想要汤水类；主食拒面与米。",
      },
      kpi: { combos: 1180, l2_top: 60, top1: "椰客椰子鸡 (科兴店)", latency_ms: 2310 },
      diff: { vs: "R2", in: 3, out: 3, up: 2, down: 1 },
    },
    {
      id: "R4",
      label: "别要重的",
      time: "12:12",
      user_text: "再来一轮，别要重的，太油了",
      intent: {
        cuisine_want: [], cuisine_avoid: ["川菜", "湘菜"],
        ingredient_want: ["鱼", "禽"], ingredient_avoid: ["加工肉", "动物内脏", "油炸"],
        taste_want: ["汤水", "清淡"], taste_avoid: ["重油", "重辣"],
        cook_want: ["soup", "steamed", "boiled"],
        portion: null,
        grain_pref: "无主食或杂粮",
        price_band: "≤80",
        raw_taste: null,
        freeform_note: "用户加强清淡偏好；累计：汤 + 清淡 + 拒重油重辣。",
      },
      kpi: { combos: 1142, l2_top: 60, top1: "椰客椰子鸡 (科兴店)", latency_ms: 2208 },
      diff: { vs: "R3", in: 2, out: 2, up: 1, down: 2 },
    },
  ];

  window.WA_MOCK = { TRACES, ROUNDS };
})();

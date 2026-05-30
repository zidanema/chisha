// Mock session — dev-only offline fallback.
// Deterministic (seeded RNG) so render output matches the canvas pixel-for-pixel.

import type {
  ComboDish,
  L1Trace,
  L2Combo,
  L2KPI,
  L2Trace,
  L2Weight,
  L3Trace,
  RefineTrace,
  RunHistoryRow,
  Session,
  FinalRow,
} from "../types/trace";

const SESSION_ID = "sess_2026-05-16_12-04-37_a7f1";
const STARTED_AT = "2026-05-16 12:04:37.218";
const TOTAL_LATENCY_MS = 2841;

const L1_FUNNEL: L1Trace["funnel"] = [
  { stage: "raw_dishes", label: "全量菜", value: 11123, kind: "dish", dropped: 0 },
  { stage: "hard_filter_dishes", label: "硬过滤后菜", value: 4286, kind: "dish", dropped: 6837 },
  { stage: "diversity_dishes", label: "多样性后菜", value: 2914, kind: "dish", dropped: 1372 },
  { stage: "combo_restaurants", label: "出 combo 餐厅", value: 137, kind: "rest", dropped: 102 },
  { stage: "raw_combos", label: "Combo 总数 (价格前)", value: 1842, kind: "combo", dropped: 0 },
  { stage: "price_filtered", label: "价格过滤后 Combo", value: 1207, kind: "combo", dropped: 635 },
  { stage: "final_combos", label: "最终 Combo (送 L2)", value: 1207, kind: "combo", dropped: 0 },
];

const L1: L1Trace = {
  area: "深圳湾办公区",
  meal: "lunch",
  raw_dishes: 11123,
  raw_restaurants: 239,
  funnel: L1_FUNNEL,
  restaurant_bans: [
    { rest: "海底捞 (深圳湾店)", reason: "ETA 超限", detail: "estimated 71min > cap 45min", count: 1 },
    { rest: "南京大牌档", reason: "ETA 超限", detail: "estimated 58min > cap 45min", count: 1 },
    { rest: "Wagas (科技园店)", reason: "近 7 天吃过", detail: "last 2026-05-13 lunch", count: 1 },
    { rest: "麦当劳 (深圳湾店)", reason: "avoid_restaurants", detail: "matched: 麦当劳", count: 1 },
    { rest: "肯德基 (T3 店)", reason: "avoid_restaurants", detail: "matched: 肯德基", count: 1 },
    { rest: "猪脚饭·李记 (科兴店)", reason: "ETA 超限", detail: "estimated 51min > cap 45min", count: 1 },
    { rest: "Tims 咖啡 (后海店)", reason: "近 7 天吃过", detail: "last 2026-05-14 lunch", count: 1 },
    { rest: "胖哥俩 (海岸城店)", reason: "价格异常", detail: "min combo ¥248 > budget ¥80", count: 1 },
  ],
  ban_reason_agg: [
    { reason: "ETA 超限 (>45min)", count: 47 },
    { reason: "avoid_restaurants 命中", count: 18 },
    { reason: "近 7 天吃过", count: 23 },
    { reason: "价格异常 / 缺品类", count: 14 },
  ],
  dish_drops: [
    { reason: "price > budget (单菜 > ¥45)", count: 2148, layer: "hard" },
    { reason: "oil_level = high (规则: 减脂)", count: 1937, layer: "hard" },
    { reason: "main_ingredient_type = 加工肉 (avoid)", count: 1024, layer: "hard" },
    { reason: "protein_g < 12 (高蛋白下限)", count: 814, layer: "hard" },
    { reason: "sweet_sauce_level = high", count: 542, layer: "hard" },
    { reason: "wetness = dry & 已是干 (多样性)", count: 728, layer: "diversity" },
    { reason: "main_ingredient_type 重复 > 3 (多样性)", count: 644, layer: "diversity" },
    { reason: "combo 总价 > ¥80 (上限)", count: 635, layer: "price" },
  ],
  top_restaurants: [
    { name: "西少爷肉夹馍 (深圳湾店)", combos: 38 },
    { name: "和府捞面 (科技园店)", combos: 34 },
    { name: "南城香 (深圳湾店)", combos: 31 },
    { name: "鸡公煲·小山 (科兴店)", combos: 29 },
    { name: "霸蛮米粉 (后海店)", combos: 27 },
    { name: "嘉禾一品 (海岸城店)", combos: 26 },
    { name: "外婆家 (海岸城店)", combos: 24 },
    { name: "Wagas (深圳湾店)", combos: 22 },
    { name: "小杨生煎 (后海店)", combos: 21 },
    { name: "真功夫 (科兴店)", combos: 20 },
    { name: "云海肴 (深圳湾店)", combos: 19 },
    { name: "井格老灶火锅 (海岸城店)", combos: 18 },
    { name: "新元素 (科技园店)", combos: 17 },
    { name: "Element Fresh (深圳湾店)", combos: 16 },
    { name: "汤先生 (后海店)", combos: 15 },
    { name: "蛙小侠 (海岸城店)", combos: 14 },
    { name: "椰客椰子鸡 (科兴店)", combos: 14 },
    { name: "桂林米粉·廖记 (深圳湾店)", combos: 13 },
    { name: "西贝莜面村 (海岸城店)", combos: 13 },
    { name: "太二酸菜鱼 (深圳湾店)", combos: 12 },
  ],
  latency_ms: 194,
};

const L2_WEIGHTS: L2Weight[] = [
  { key: "fit_diet", label: "fit_diet", w: 0.18 },
  { key: "protein_density", label: "protein_dens", w: 0.14 },
  { key: "oil_penalty", label: "oil_penalty", w: -0.12 },
  { key: "variety_bonus", label: "variety", w: 0.1 },
  { key: "novelty", label: "novelty", w: 0.08 },
  { key: "price_fit", label: "price_fit", w: 0.07 },
  { key: "eta_score", label: "eta", w: 0.06 },
  { key: "wetness_balance", label: "wetness_bal", w: 0.05 },
  { key: "grain_match", label: "grain", w: 0.05 },
  { key: "sweet_pen", label: "sweet_pen", w: -0.04 },
  { key: "processed_pen", label: "processed_pen", w: -0.06 },
  { key: "history_decay", label: "hist_decay", w: 0.04 },
  { key: "explore_bonus", label: "explore", w: 0.03 },
];

const RESTAURANTS = [
  "西少爷肉夹馍 (深圳湾店)", "和府捞面 (科技园店)", "南城香 (深圳湾店)",
  "鸡公煲·小山 (科兴店)", "霸蛮米粉 (后海店)", "嘉禾一品 (海岸城店)",
  "外婆家 (海岸城店)", "Wagas (深圳湾店)", "小杨生煎 (后海店)",
  "真功夫 (科兴店)", "云海肴 (深圳湾店)", "井格老灶火锅 (海岸城店)",
  "新元素 (科技园店)", "Element Fresh (深圳湾店)", "汤先生 (后海店)",
  "蛙小侠 (海岸城店)", "椰客椰子鸡 (科兴店)", "太二酸菜鱼 (深圳湾店)",
  "西贝莜面村 (海岸城店)", "桂林米粉·廖记 (深圳湾店)",
];

const DISHES_BY_REST: Record<string, ComboDish[]> = {
  "Wagas (深圳湾店)": [
    { name: "Mediterranean Quinoa Bowl", price: 58, oil: "low", spicy: "none", protein_g: 28,
      cook: "boiled", main: "grain+leaf", role: "main", wetness: "mid", sweet: "low", grain: "quinoa" },
    { name: "烟熏三文鱼牛油果", price: 78, oil: "low", spicy: "none", protein_g: 32,
      cook: "smoked", main: "fish", role: "side", wetness: "mid", sweet: "none", grain: "none" },
  ],
  "椰客椰子鸡 (科兴店)": [
    { name: "椰子鸡汤锅 (单人)", price: 68, oil: "low", spicy: "low", protein_g: 36,
      cook: "soup", main: "poultry", role: "main", wetness: "wet", sweet: "low", grain: "none" },
    { name: "凉拌木耳", price: 22, oil: "low", spicy: "low", protein_g: 4,
      cook: "cold-mix", main: "fungi", role: "side", wetness: "mid", sweet: "low", grain: "none" },
  ],
  "西少爷肉夹馍 (深圳湾店)": [
    { name: "腊汁肉夹馍", price: 18, oil: "mid", spicy: "low", protein_g: 22,
      cook: "stewed", main: "pork", role: "main", wetness: "dry", sweet: "low", grain: "wheat" },
    { name: "凉皮 (微辣)", price: 16, oil: "low", spicy: "mid", protein_g: 7,
      cook: "cold-mix", main: "noodle", role: "side", wetness: "wet", sweet: "low", grain: "rice" },
    { name: "冰峰汽水", price: 6, oil: "none", spicy: "none", protein_g: 0,
      cook: "raw", main: "drink", role: "drink", wetness: "wet", sweet: "high", grain: "none" },
  ],
};

// Deterministic LCG (seed=42)
function makeRand(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

function buildCombos(): L2Combo[] {
  const r = makeRand(42);
  const combos: L2Combo[] = [];
  for (let i = 0; i < 60; i++) {
    const restIdx = Math.floor(r() * RESTAURANTS.length);
    const rest = RESTAURANTS[restIdx];
    const scores: Record<string, number> = {};
    let total = 0;
    for (const { key, w } of L2_WEIGHTS) {
      const s = Math.round((r() * 1.4 - 0.2) * 100) / 100;
      scores[key] = s;
      total += s * w;
    }
    const boost = ((60 - i) / 60) * 0.35;
    total += boost;
    const dishes = DISHES_BY_REST[rest] || [
      { name: "招牌套餐 A", price: 28 + Math.floor(r() * 20), oil: "mid", spicy: "low", protein_g: 24,
        cook: "stir-fried", main: "poultry", role: "main", wetness: "mid", sweet: "low", grain: "rice" },
      { name: "时蔬一份", price: 12, oil: "low", spicy: "none", protein_g: 6,
        cook: "stir-fried", main: "leaf", role: "side", wetness: "mid", sweet: "none", grain: "none" },
    ];
    const totalPrice = dishes.reduce((a, b) => a + b.price, 0);
    combos.push({
      combo_id: `cmb_${String(i + 1).padStart(3, "0")}`,
      restaurant: rest,
      rank: i + 1,
      total_score: Math.round(total * 1000) / 1000,
      fit_score: Math.round((0.4 + r() * 0.5) * 100) / 100,
      eta_min: 18 + Math.floor(r() * 22),
      distance_km: Math.round((0.4 + r() * 2.8) * 10) / 10,
      total_price: totalPrice,
      dishes,
      breakdown: scores,
    });
  }
  combos.sort((a, b) => b.total_score - a.total_score);
  combos.forEach((c, i) => { c.rank = i + 1; });
  return combos;
}

const L2_COMBOS = buildCombos();

const L2_KPI: L2KPI = {
  score_min: Math.min(...L2_COMBOS.map((c) => c.total_score)).toFixed(3),
  score_max: Math.max(...L2_COMBOS.map((c) => c.total_score)).toFixed(3),
  cap_k: 4,
  per_brand_top_k: 3,
  per_restaurant_cap_k: 3,
  restaurants_before_cap: 84,
  restaurants_after_cap: 31,
  max_combos_one_rest_before: 11,
  max_combos_one_rest_after: 3,
};

const L2: L2Trace = {
  weights: L2_WEIGHTS,
  combos: L2_COMBOS,
  kpi: L2_KPI,
  latency_ms: 38,
  candidates_to_l3: 60,
  combos_before_l2: L1_FUNNEL[L1_FUNNEL.length - 1]?.value ?? 0,
};

const L3_SYSTEM_PROMPT = `<system>
你是「今天吃点啥」的外卖推荐排序助手。

输入：60 个候选 combo (餐厅 + 2-3 道菜)，已经过 L1 召回 + L2 V2 打分。
任务：从中挑出 5 个推荐给用户，并为每个写一句中文推荐理由 (≤ 28 字)。

约束：
1. 5 个里：3 个为 exploit (排名靠前 + 与用户历史口味重合)，2 个为 explore (略偏离用户常吃但符合饮食方法论)。
2. 同一餐厅最多 1 个。
3. 油等级 high 的不要选。
4. 加工肉 (火腿/培根/午餐肉) 不要选。
5. 推荐理由必须落到具体食材或做法，不要空话。

请通过工具 \`emit_recommendations\` 输出结果，schema 严格遵守。

<!-- ⚡ cache_control: ephemeral, type=text -->
</system>

用户偏好快照 (profile snapshot):
{
  "diet": ["减脂控油", "高蛋白"],
  "protein_floor_g": 22,
  "oil_avoid": ["high"],
  "avoid_ingredients": ["加工肉", "动物内脏"],
  "preferred_cook": ["steamed", "boiled", "stewed", "cold-mix"],
  "budget_per_meal": 80,
  "recent_7d_restaurants": ["Wagas (科技园店)", "Tims 咖啡 (后海店)"],
  "taste_hints": { "boost": [], "penalty": [] }
}`;

const L3_USER_MESSAGE = `今天午餐 · 深圳湾办公区 · 已 L2 排序的 60 个候选 (按 total_score 降序)：

[1] cmb_001 · 椰客椰子鸡 (科兴店) · score=1.187 · fit=0.78 · ETA=22 · ¥90
  - 椰子鸡汤锅 (单人) · ¥68 · low油 · 36g蛋白 · soup · wet
  - 凉拌木耳 · ¥22 · low油 · 4g蛋白 · cold-mix
[2] cmb_002 · Wagas (深圳湾店) · score=1.142 · fit=0.81 · ETA=25 · ¥136
  - Mediterranean Quinoa Bowl · ¥58 · low油 · 28g蛋白 · boiled
  - 烟熏三文鱼牛油果 · ¥78 · low油 · 32g蛋白 · smoked
[3] cmb_003 · 西少爷肉夹馍 (深圳湾店) · score=1.108 · fit=0.74 · ETA=20 · ¥40
  - 腊汁肉夹馍 · ¥18 · mid油 · 22g蛋白 · stewed
  - 凉皮 (微辣) · ¥16 · low油 · 7g蛋白 · cold-mix
  - 冰峰汽水 · ¥6 · none油 · 0g蛋白 · raw
[4] cmb_004 · 嘉禾一品 (海岸城店) · score=1.094 · fit=0.71 · ETA=28 · ¥48
  - 皮蛋瘦肉粥 · ¥18 · low油 · 16g蛋白 · soup
  - 黄金小馒头 · ¥12 · low油 · 6g蛋白 · steamed
[5] cmb_005 · 汤先生 (后海店) · score=1.072 · fit=0.79 · ETA=31 · ¥52
  ...
... (省略 [6] - [60]，每条同样格式)

请按工具 schema 输出 top 5，2 explore 必须覆盖至少 1 个 "wet/汤水" 类菜。`;

const L3_THINKING = `用户饮食方法论 = 减脂控油 + 高蛋白 (protein_floor 22g)。L2 top 5 中:
- cmb_001 椰子鸡汤: 36g 蛋白 + soup + wet, 完美 exploit
- cmb_002 Wagas: 60g 总蛋白 + quinoa, 但 Wagas 科技园店在 7d 内吃过, 深圳湾店不算重复, 可作 exploit
- cmb_003 西少爷: 肉夹馍蛋白 22g 刚卡到 floor, 凉皮蛋白偏低, 总 29g 略低; 但用户最近没吃过陕西菜, 可作 explore
- 需要再补 1 个 explore: 找 wet/汤类。cmb_017 椰客椰子鸡另一家 — 同店不行。换 cmb_028 云海肴鸡丝凉面太干。
- cmb_034 真功夫海带排骨汤: 蛋白 30g, wet, 用户最近 14d 没吃, 选作 explore (汤类)。
- 第 3 exploit: cmb_005 汤先生 (低脂高蛋白合菜), 79 fit 高, ETA 31 略长但可接受。
最终: 001 (exploit) / 002 (exploit) / 005 (exploit) / 003 (explore) / 034 (explore)。
约束 check: 同店 ≤ 1 ✓ / 油 high ✗ 无 ✓ / 加工肉 ✗ 无 ✓ / explore 至少 1 wet ✓ (034 汤)`;

const L3: L3Trace = {
  status: "ok",
  resolved_provider: "anthropic",
  model: "claude-opus-4-7",
  latency_ms: 2148,
  input_tokens: 4824,
  output_tokens: 612,
  cache_read_input_tokens: 3974,
  cache_creation_input_tokens: 0,
  system_prompt_chars: 6210,
  user_message_chars: 8412,
  stop_reason: "tool_use",
  max_tokens: 2048,
  temperature: 0.2,
  candidates_returned: 5,
  fallback_chain: [
    { step: 1, name: "anthropic / claude-opus-4-7", status: "ok",
      meta: "latency 2148ms · 4824 in · 612 out · cache hit 3974", error: null },
  ],
  system_prompt: L3_SYSTEM_PROMPT,
  user_message: L3_USER_MESSAGE,
  tool_input: {
    name: "emit_recommendations",
    description: "Emit 5 reranked combos with a one-line reason each.",
    input_schema: {
      type: "object",
      required: ["recommendations"],
      properties: {
        recommendations: {
          type: "array",
          minItems: 5,
          maxItems: 5,
          items: {
            type: "object",
            required: ["combo_id", "kind", "reason"],
            properties: {
              combo_id: { type: "string", pattern: "^cmb_[0-9]{3}$" },
              kind: { type: "string", enum: ["exploit", "explore"] },
              reason: { type: "string", maxLength: 60, minLength: 6 },
            },
          },
        },
      },
    },
  },
  raw_response_blocks: [
    { type: "thinking", text: L3_THINKING },
    {
      type: "tool_use",
      id: "toolu_01H7Q9pXjK4F2dN3rT8gV5mY",
      name: "emit_recommendations",
      input: {
        recommendations: [
          { combo_id: "cmb_001", kind: "exploit", reason: "椰子汤底打底，鸡腿肉 36g 蛋白；wet + low 油，今天对口。" },
          { combo_id: "cmb_002", kind: "exploit", reason: "quinoa 杂粮 + 烟熏三文鱼，蛋白 60g，深圳湾店不算 7d 重复。" },
          { combo_id: "cmb_005", kind: "exploit", reason: "低脂合菜 + 杂粮饭，每份 30g 蛋白，热量稳。" },
          { combo_id: "cmb_003", kind: "explore", reason: "陕西小馆，腊汁肉 + 凉皮微辣，最近没吃，换个口味。" },
          { combo_id: "cmb_034", kind: "explore", reason: "海带排骨汤补液 + 杂粮饭，wet/低油，今天偏热想喝汤。" },
        ],
      },
    },
  ],
  validator_errors: null,
};

export const L3_FALLBACK_EXAMPLE: L3Trace = {
  ...L3,
  status: "fallback",
  resolved_provider: "openrouter",
  model: "anthropic/claude-sonnet-4-5",
  latency_ms: 5732,
  fallback_reason: "anthropic primary 调用返回 529 overloaded_error;retry-after 1.2s 后仍失败,已切换 openrouter sonnet 完成",
  fallback_chain: [
    { step: 1, name: "anthropic / claude-opus-4-7", status: "error",
      meta: "529 overloaded_error · latency 1024ms", error: "Overloaded" },
    { step: 2, name: "anthropic / claude-sonnet-4-5", status: "error",
      meta: "529 overloaded_error · latency 980ms", error: "Overloaded" },
    { step: 3, name: "openrouter / claude-sonnet-4-5", status: "ok",
      meta: "latency 5732ms · 4824 in · 587 out · cache miss", error: null },
  ],
};

const FINAL: FinalRow[] = [
  { rank: 1, kind: "exploit", combo_id: "cmb_001", restaurant: "椰客椰子鸡 (科兴店)",
    distance_km: 1.4, eta_min: 22, total_price: 90, score: 1.187, fit_score: 0.78,
    dishes: [{ name: "椰子鸡汤锅 (单人)", price: 68 }, { name: "凉拌木耳", price: 22 }],
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, wetness_ok: true,
                    processed_meat: false, sweet_sauce: false },
    risk_flags: [],
    reason: "椰子汤底打底，鸡腿肉 36g 蛋白;wet + low 油,今天对口。" },
  { rank: 2, kind: "exploit", combo_id: "cmb_002", restaurant: "Wagas (深圳湾店)",
    distance_km: 0.6, eta_min: 25, total_price: 136, score: 1.142, fit_score: 0.81,
    dishes: [{ name: "Mediterranean Quinoa Bowl", price: 58 }, { name: "烟熏三文鱼牛油果", price: 78 }],
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, wetness_ok: true,
                    processed_meat: false, sweet_sauce: false },
    risk_flags: ["price_above_avg"],
    reason: "quinoa 杂粮 + 烟熏三文鱼,蛋白 60g,深圳湾店不算 7d 重复。" },
  { rank: 3, kind: "exploit", combo_id: "cmb_005", restaurant: "汤先生 (后海店)",
    distance_km: 2.1, eta_min: 31, total_price: 52, score: 1.072, fit_score: 0.79,
    dishes: [{ name: "番茄牛尾汤套餐", price: 38 }, { name: "杂粮饭", price: 14 }],
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, wetness_ok: true,
                    processed_meat: false, sweet_sauce: false },
    risk_flags: ["eta_long"],
    reason: "低脂合菜 + 杂粮饭,每份 30g 蛋白,热量稳。" },
  { rank: 4, kind: "explore", combo_id: "cmb_003", restaurant: "西少爷肉夹馍 (深圳湾店)",
    distance_km: 0.9, eta_min: 20, total_price: 40, score: 1.108, fit_score: 0.74,
    dishes: [{ name: "腊汁肉夹馍", price: 18 }, { name: "凉皮 (微辣)", price: 16 }, { name: "冰峰汽水", price: 6 }],
    health_flags: { veg_ok: false, protein_ok: true, oil_ok: true, wetness_ok: false,
                    processed_meat: false, sweet_sauce: true },
    risk_flags: ["sweet_drink"],
    reason: "陕西小馆,腊汁肉 + 凉皮微辣,最近没吃,换个口味。" },
  { rank: 5, kind: "explore", combo_id: "cmb_034", restaurant: "真功夫 (科兴店)",
    distance_km: 1.7, eta_min: 24, total_price: 46, score: 0.984, fit_score: 0.69,
    dishes: [{ name: "海带排骨汤", price: 28 }, { name: "杂粮饭", price: 12 }, { name: "凉拌秋葵", price: 6 }],
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, wetness_ok: true,
                    processed_meat: false, sweet_sauce: false },
    risk_flags: [],
    reason: "海带排骨汤补液 + 杂粮饭,wet/低油,今天偏热想喝汤。" },
];

const REFINE: RefineTrace = {
  parent_session: SESSION_ID,
  refine_session: "sess_2026-05-16_12-06-12_a7f1_r1",
  user_text: "想喝汤，别给我面食和米饭，西少爷那个不要了。",
  parse_feedback: {
    llm_call: { model: "claude-haiku-4-5", latency_ms: 412,
                input_tokens: 312, output_tokens: 84, cache_read_input_tokens: 184 },
    chips_hit: ["want_soup", "avoid_noodle", "avoid_rice", "avoid_specific_restaurant"],
    note: "用户明确表达想喝汤；同时拒绝面食/米饭主食；点名拒绝西少爷肉夹馍。",
    rating_taste: null,
    want_again: false,
  },
  chips_to_taste_hints: {
    boost: {
      wetness: { wet: 0.18, soup: 0.22 },
      main_ingredient_type: { fish: 0.08, poultry: 0.06 },
    },
    penalty: {
      grain_type: { noodle: -0.30, rice: -0.18, wheat: -0.12 },
      restaurant: { "西少爷肉夹馍": -1.0 },
    },
  },
  infer_refine_mood: {
    triggered: true,
    hits: [
      { keyword: "想喝汤", direction: "+", target: "want_soup" },
      { keyword: "别给我面", direction: "-", target: "want_noodle" },
    ],
    resolved_mood: { want_soup: 0.85, want_noodle: -0.60 },
  },
  diff: {
    new_in_top5: ["cmb_034 海带排骨汤 (真功夫)", "cmb_017 椰子鸡汤+蒸饺 (椰客后海店)"],
    dropped_from_top5: ["cmb_002 Wagas (Mediterranean Quinoa)", "cmb_003 西少爷肉夹馍"],
    moved_up: [{ id: "cmb_001", from: 1, to: 1 }, { id: "cmb_005", from: 3, to: 2 }],
    moved_down: [],
  },
  summary_kpi: {
    explore_n: 0,
    total_latency_ms: 2310,
    candidates_returned: 5,
    diff_top5: 2,
  },
};

export const RUN_HISTORY: RunHistoryRow[] = [
  { id: "sess_a7f1", title: "lunch · 深圳湾", time: "12:04", status: "ok", latency: 2841 },
  { id: "sess_a7f0", title: "lunch · 深圳湾", time: "12:01", status: "fallback", latency: 6210 },
  { id: "sess_a7ef", title: "dinner · 家附近", time: "昨 19:32", status: "ok", latency: 2510 },
  { id: "sess_a7ee", title: "lunch · 深圳湾", time: "昨 12:18", status: "ok", latency: 2620 },
  { id: "sess_a7ed", title: "lunch refine · 深圳湾", time: "昨 12:21", status: "ok", latency: 2310 },
  { id: "sess_a7ec", title: "dinner · 家附近", time: "前 19:08", status: "warn", latency: 4520 },
  { id: "sess_a7eb", title: "lunch · 深圳湾", time: "前 11:54", status: "ok", latency: 2402 },
];

export const MOCK_SESSION: Session = {
  session_id: SESSION_ID,
  started_at: STARTED_AT,
  total_latency_ms: TOTAL_LATENCY_MS,
  ctx_latency_ms: 14,
  final_latency_ms: 18,
  l1: L1,
  l2: L2,
  l3: L3,
  final: FINAL,
  refine: REFINE,
};

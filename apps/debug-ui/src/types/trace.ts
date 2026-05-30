// Trace type definitions — backend response shape consumed via a thin adapter.

export type Meal = "lunch" | "dinner";

export type FunnelStageKind = "dish" | "rest" | "combo";

export type FunnelStage = {
  stage: string;
  label: string;
  value: number;
  kind: FunnelStageKind;
  dropped: number;
};

export type RestaurantBan = {
  rest: string;
  reason: string;
  detail: string;
  count: number;
};

export type DishDrop = {
  reason: string;
  count: number;
  layer: "hard" | "diversity" | "price";
};

export type L1Trace = {
  area: string;
  meal: Meal;
  raw_dishes: number;
  raw_restaurants: number;
  funnel: FunnelStage[];
  restaurant_bans: RestaurantBan[];
  ban_reason_agg: { reason: string; count: number }[];
  dish_drops: DishDrop[];
  top_restaurants: { name: string; combos: number }[];
  latency_ms: number;
};

export type L2Weight = { key: string; label: string; w: number };

export type ComboDish = {
  name: string;
  price: number;
  oil: string;
  spicy: string;
  protein_g: number;
  cook: string;
  main: string;
  role: string;
  wetness: string;
  sweet: string;
  grain: string;
};

export type L2Combo = {
  combo_id: string;
  restaurant: string;
  rank: number;
  total_score: number;
  fit_score: number;
  eta_min: number;
  distance_km: number;
  total_price: number;
  dishes: ComboDish[];
  breakdown: Record<string, number>;
};

export type L2KPI = {
  score_min: string;
  score_max: string;
  cap_k: number;
  per_brand_top_k: number;
  per_restaurant_cap_k: number;
  restaurants_before_cap: number;
  restaurants_after_cap: number;
  max_combos_one_rest_before: number;
  max_combos_one_rest_after: number;
};

export type L2Trace = {
  weights: L2Weight[];
  combos: L2Combo[];
  kpi: L2KPI;
  latency_ms: number;
  candidates_to_l3: number;
  combos_before_l2: number;
};

// D-089-S5b: "no_data" 替代 "skipped" 兜底 — 之前 makeEmptyL3 用 "skipped"
// 容易让人误以为是业务跳过, 实际是 round 根本没存 L3 切片. "skipped" 保留给
// backend 真业务跳过路径 (top_combos 为空 -> rerank 直接 skip).
export type L3Status = "ok" | "fallback" | "config_error" | "skipped" | "no_data";

export type FallbackChainStep = {
  step: number;
  name: string;
  status: "ok" | "error";
  meta: string;
  error: string | null;
};

export type ThinkingBlock = { type: "thinking"; text: string };
export type ToolUseBlock = {
  type: "tool_use";
  id: string;
  name: string;
  input: unknown;
};
export type TextBlock = { type: "text"; text: string };

export type ResponseBlock = ThinkingBlock | ToolUseBlock | TextBlock;

export type L3Trace = {
  status: L3Status;
  resolved_provider: string;
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens: number;
  cache_creation_input_tokens: number;
  system_prompt_chars: number;
  user_message_chars: number;
  stop_reason: string;
  max_tokens: number;
  temperature: number;
  candidates_returned: number;
  fallback_chain: FallbackChainStep[];
  fallback_reason?: string;
  system_prompt: string;
  user_message: string;
  tool_input: {
    name: string;
    description: string;
    input_schema: unknown;
  };
  raw_response_blocks: ResponseBlock[];
  validator_errors: string[] | null;
};

export type FinalRow = {
  rank: number;
  kind: "exploit" | "explore";
  combo_id: string;
  restaurant: string;
  distance_km: number;
  eta_min: number;
  total_price: number;
  score: number;
  fit_score: number;
  dishes: { name: string; price: number }[];
  health_flags: {
    veg_ok: boolean;
    protein_ok: boolean;
    oil_ok: boolean;
    wetness_ok: boolean;
    processed_meat: boolean;
    sweet_sauce: boolean;
  };
  risk_flags: string[];
  reason: string;
};

// D-079 PR-3.1 (Codex FIX-NOW #2): backend trace.refine 携带 D-073 RefineIntent
// 结构化字段, traceToSession 必须 1:1 映射, 不能丢. PanelRefine 会读这些字段
// 展示 intent 命中详情.
export type RefineIntentLite = {
  cuisine_want?: string | string[] | null;
  cuisine_avoid?: string | string[] | null;
  flavor_want?: string | string[] | null;
  flavor_avoid?: string | string[] | null;
  ingredient_want?: string | string[] | null;
  ingredient_avoid?: string | string[] | null;
  // 其它字段 RefineIntent 后续扩展时也透传 (open schema)
  [k: string]: unknown;
};

export type RefineTrace = {
  parent_session: string;
  refine_session: string;
  user_text: string;
  // D-079 PR-3.1 新增: 后端 trace.refine 透传字段 (backend RefineIntent + stats)
  intent?: RefineIntentLite | null;
  n_combos_recalled?: number | null;
  n_after_l2?: number | null;
  candidate_ids?: string[];
  ts?: string;
  parse_feedback: {
    llm_call: {
      model: string;
      latency_ms: number;
      input_tokens: number;
      output_tokens: number;
      cache_read_input_tokens: number;
    };
    chips_hit: string[];
    note: string;
    rating_taste: number | null;
    want_again: boolean;
  };
  chips_to_taste_hints: {
    boost: Record<string, Record<string, number>>;
    penalty: Record<string, Record<string, number>>;
  };
  infer_refine_mood: {
    triggered: boolean;
    hits: { keyword: string; direction: "+" | "-"; target: string }[];
    resolved_mood: Record<string, number>;
  };
  diff: {
    new_in_top5: string[];
    dropped_from_top5: string[];
    moved_up: { id: string; from: number; to: number }[];
    moved_down: { id: string; from: number; to: number }[];
  };
  summary_kpi: {
    explore_n: number;
    total_latency_ms: number;
    candidates_returned: number;
    diff_top5: number;
  };
};

export type Session = {
  session_id: string;
  started_at: string;
  total_latency_ms: number;
  ctx_latency_ms: number;
  final_latency_ms: number;
  l1: L1Trace;
  l2: L2Trace;
  l3: L3Trace;
  final: FinalRow[];
  refine: RefineTrace;
};

// ═══════════════════════════════════════════════════════════════════
// Workflow A · 分析 trace 类型 (D-086+)
// ═══════════════════════════════════════════════════════════════════

// V2.1 RefineIntent schema (chisha/refine_intent_v2.py: RefineIntentV2).
// D-094.1: schema 9→13 槽 (加 staple_want/avoid + oil="high" + wants_soup + price_band).
// D-096: V1 已退役, schema_version 强制 "2.1".
// open-schema: 后端 V2 schema 扩字段时自动透传, 前端按 intent_schema descriptor 渲染.
export type RoundIntentV2 = {
  redirect?: {
    cuisine_want?: string[];
    cuisine_avoid?: string[];
    cuisine_candidates_expanded?: string[];
    ingredient_want?: string[];
    ingredient_avoid?: string[];
    brand_avoid?: string[];
    cooking_method_avoid?: string[];
    // D-094.1: 主食偏好自由字符串
    staple_want?: string[];
    staple_avoid?: string[];
  };
  constrain?: {
    // D-094.1: oil 枚举扩 {low, normal, high} ("high" 替代 V1 heavy + 触发 D-090.1 油豁免)
    oil?: "low" | "normal" | "high" | null;
    price_max?: number | null;
    // D-094.1: 模糊文本兜底, price_max 优先
    price_band?: "cheap" | "normal" | "premium" | null;
    // D-094.1: 想喝汤/粥 (L2 真打分)
    wants_soup?: boolean;
  };
  reference?: { round?: string; pick?: string } | null;
  reject_previous?: boolean;
  raw_understanding?: string;
  raw_text?: string;
  schema_version?: string;
  // 后端将来扩字段 — open schema
  [key: string]: unknown;
};

// D-089-S5a: 通用单次 LLM call view-model (跟 backend BackendLlmCallTrace 对齐).
// 用于 R2+ round.refine_intent_llm; 未来扩展 L1 LLM 抽取 trace 也复用.
export type LlmCallTrace = {
  system_prompt_full: string;
  system_prompt_chars: number;
  user_message_full: string;
  user_message_chars: number;
  user_message_preview: string;
  raw_response: string;
  raw_response_chars: number;
  latency_ms: number | null;
  model: string | null;
  resolved_provider: string | null;
  stop_reason: string | null;
  fallback_reason: string | null;
  max_tokens: number | null;
  temperature: number | null;
  usage: {
    input_tokens: number;
    output_tokens: number;
    cache_read_input_tokens: number;
    cache_creation_input_tokens: number;
  };
  validator_errors?: string[] | null;
};

// 单 round 对应的完整 pipeline 数据 + intent + 与上一轮的 diff 摘要.
export type RoundRecord = {
  id: string;                  // "R1" / "R2" / ...
  label: string;               // "原始" / "换一组" / 用户自命名 (后端可能无)
  started_at: string;          // ISO 或 "HH:MM" 简化形式
  user_input: string | null;   // R1 = null
  intent_v2: RoundIntentV2 | null; // R1 = null (静态来自 profile)
  kpi: {
    combos: number;            // L1 出 combo 数
    l2_top: number;            // L2 top60 = candidates_to_l3
    top1: string;              // final[0] 餐厅名
    latency_ms: number;
  };
  diff: {
    vs: string;                // 上一轮 round id
    in: number;                // final 新进
    out: number;               // final 踢出
    up: number;                // 位次上升
    down: number;              // 位次下降
  } | null;
  l1: L1Trace;
  l2: L2Trace;
  l3: L3Trace;
  final: FinalRow[];
  // D-089-S5a: R2+ refine round 含意图解析 LLM call 完整 trace.
  // R1 主链路 / R2 没启用 sync v2 / LLM 调用失败时为 null.
  refine_intent_llm?: LlmCallTrace | null;
  // zero-state 骨架等无完整切片的兜底场景标 __partial=true,
  // LookupDrawer 据此警告用户该 round 反查不可信.
  __partial?: boolean;
};

// TraceBrowser 单行 meta (来自 backend GET /api/traces 单条).
export type TraceFeedback = {
  type: "accepted" | "rated" | "stopped";
  rank?: number;               // accepted 用
  restaurant_name?: string;    // accepted 用, D-088 (B4)
  count?: number;              // rated 用 (heart count)
};

export type TraceMeta = {
  id: string;
  date: string;                // YYYY-MM-DD
  time: string;                // HH:MM
  daysAgo: number;
  meal: Meal;
  finalTop1: string;
  refineCount: number;         // = len(rounds) - 1
  latestRound: string;         // "R{1+refineCount}"
  source: "real" | "sandbox";
  sandboxDay?: number | null;
  feedback: TraceFeedback | null;
  status: "ok" | "fallback" | "warn";
  latency_ms: number;
};

// 完整 Workflow A trace = meta + rounds 数组.
export type WaTrace = {
  meta: TraceMeta;
  rounds: RoundRecord[];
};

// Intent schema descriptor (Phase 2a 来自 GET /api/intent_schema).
export type IntentFieldDescriptor = {
  key: string;                 // 唯一 ID, 例: "redirect.cuisine_want"
  label: string;               // 中文标签
  tone: "want" | "avoid" | "neutral";
  group: "redirect" | "constrain" | "meta" | "other";
  slot_path: string[];         // ["redirect", "cuisine_want"]
  scalar?: boolean;            // true = 单值 (constrain.oil), false = 数组 (redirect.cuisine_want)
  freeform?: boolean;          // true = 长文本 (raw_understanding)
};

// Trace type definitions — reverse-engineered from design/mock.jsx.
// Phase 2 will swap this with backend response shape via a thin adapter.

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

export type L3Status = "ok" | "fallback" | "config_error" | "skipped";

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

export type RunStatus = "ok" | "fallback" | "warn";

export type FeedbackBadge = {
  accepted: boolean;
  accepted_rank: number | null;
  rating: number | null;
  stopped: boolean;
  feedback_submitted: boolean;
};

export type RunHistoryRow = {
  id: string;
  title: string;
  time: string;
  status: RunStatus;
  latency: number;
  meal?: Meal;
  area?: string;
  // D-079: 后端 backed row 才有 feedback badge (localStorage fallback 永远 null).
  feedback?: FeedbackBadge | null;
  // D-079: backend-backed 行允许 fetch trace 详情走 /api/debug/sessions/{sid}.
  source?: "backend" | "local";
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

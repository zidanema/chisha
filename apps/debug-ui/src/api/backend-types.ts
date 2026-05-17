// Raw shapes returned by chisha.debug_server (FastAPI on :8765).
// These mirror what `chisha.debug_recommend.debug_recommend()` returns
// at chisha/debug_recommend.py:640 — do NOT mix with frontend view-model
// types in ../types/trace.ts. The adapter (adapter.ts) bridges the two.

export type BackendDishDrop = {
  dish_id: string;
  reason: string;
  // 后端还带原始菜品字段, 但 trace 只需要 reason 聚合, 这里只声明用到的.
  [key: string]: unknown;
};

export type BackendL1Recall = {
  summary: {
    total_dishes: number;
    total_restaurants: number;
    n_banned_rests_by_eta: number;
    n_banned_rests_by_name: number;
    n_diversity_avoid_rests: number;
    after_hard_filter: number;
    after_diversity_filter: number;
    n_restaurants_with_combos: number;
    n_combos_before_price_filter: number;
    n_combos_dropped_by_price: number;
    n_combos: number;
    n_avoid_rests: number;
  };
  params: Record<string, unknown>;
  dropped_hard: BackendDishDrop[];
  dropped_diversity: BackendDishDrop[];
  dropped_by_price: unknown[];
  dropped_hard_by_reason: Record<string, number>;
  dropped_diversity_by_reason: Record<string, number>;
  banned_restaurants: Array<{
    restaurant_id?: string;
    restaurant_name?: string;
    name?: string;
    reason: string;
    detail?: string;
    [key: string]: unknown;
  }>;
  per_restaurant: Array<{
    restaurant_name?: string;
    name?: string;
    n_combos: number;
    [key: string]: unknown;
  }>;
};

// chisha/score.py 约定 level 字段是 1..N 数字 (不是 string).
// oil 1..5 / sweet 0..3 / wetness 1..3 / spicy 0..N. main_ingredient_type /
// cooking_method / grain_type 是中文字符串.
export type BackendL2Dish = {
  dish_id: string;
  name: string;
  price: number;
  main_ingredient_type?: string;
  cooking_method?: string;
  oil_level?: number | string;
  spicy_level?: number | string;
  dish_role?: string;
  processed_meat_flag?: boolean;
  sweet_sauce_level?: number | string;
  wetness?: number | string;
  grain_type?: string;
  protein_g?: number;
  vegetable_ratio?: number;
};

// D-083 PR-1: feedback_evidence sibling on each L2 combo. Not in breakdown
// (breakdown is numeric-only; this is list of attribution objects per dim).
// Source: chisha/score.py:1436-1572 rank_combos.
export type BackendFeedbackEvidence = {
  feedback_recency?: Array<{
    restaurant_name: string;
    rating: number;
    age_days: number;
    signal: number;
  }>;
  next_meal_calibration?: Array<{
    session_id: string | null;
    restaurant_name: string | null;
    age_meals: number;
    age_days: number | null;
    weight: number;
    rules_fired: Array<{ rule: string; contribution: number }>;
  }>;
  note_boost?: Array<
    | {
        kind: "restaurant";
        token: string;
        polarity: "boost" | "penalty";
        restaurant_name: string;
        age_days: number;
        decay: number;
        match: number;
        contribution: number;
        subkind?: string;
      }
    | {
        kind: "global";
        token: string;
        polarity: "boost" | "penalty";
        freq: number;
        age_days: number;
        decay: number;
        match: number;
        contribution: number;
        subkind?: string;
      }
  >;
};

export type BackendL2Combo = {
  rank: number;
  combo_index: number;
  signature: string;
  restaurant_id: string;
  restaurant_name: string;
  cuisine?: string;
  distance_m: number;
  eta_min: number;
  total_price: number;
  dishes: BackendL2Dish[];
  score: number;
  breakdown: Record<string, number>;
  feedback_evidence?: BackendFeedbackEvidence;  // D-083 PR-1
};

// D-083 PR-1: feedback_view_snapshot top-level. Source: chisha/api.py:491-539,
// chisha/feedback_store.py:552-712. Optional because pre-D-083 v1 traces lack it
// (LEGACY_TRACE_SCHEMA_VERSIONS={1} read path falls back to empty skeleton).
export type BackendFeedbackViewSnapshot = {
  today: string | null;
  windows: { ratings: number; calibrations: number; note_tokens: number };
  rating_signals: Array<{
    session_id?: string;
    restaurant_name: string;
    rating: number;
    age_days: number;
    signal: number;
    factors: { peak: number; tau: number | null; stage: string };
  }>;
  calibration_rules: Array<{
    session_id: string;
    restaurant_name: string;
    age_meals: number;
    age_days: number;
    weight: number;
    last_meal_cuisine: string | null;
    triggers: Array<{ field: string; value: number | null; desc: string }>;
  }>;
  note_breakdown: Array<{
    session_id?: string;
    restaurant_name: string;
    age_days: number;
    decay: number;
    boost: string[];
    penalty: string[];
    raw_text: string;
    source: "note" | "comment";
  }>;
  global_token_freq: {
    boost: Record<string, number>;
    penalty: Record<string, number>;
  };
  global_active_tokens: { boost: string[]; penalty: string[] };
  empty: boolean;
};

export type BackendL2Score = {
  summary: {
    n_scored: number;
    score_min: number;
    score_max: number;
    score_range: number;
    weights: Record<string, number>;
    caps: { restaurant: number; brand: number; cuisine?: number; food_form?: number };
    topk_unique_restaurants_before_cap: number;
    topk_unique_restaurants_after_cap: number;
    topk_max_per_restaurant_before_cap: number;
    topk_max_per_restaurant_after_cap: number;
    topk_unique_brands_before_cap: number;
    topk_unique_brands_after_cap: number;
    topk_max_per_brand_before_cap: number;
    topk_max_per_brand_after_cap: number;
    topk_window: number;
    per_restaurant_cap_k: number;
    dim_stats_topk: Record<string, { min: number; max: number; mean: number; std: number }>;
  };
  top: BackendL2Combo[];
};

export type BackendL3Llm = {
  status: "ok" | "fallback" | "config_error" | null;
  config_error: boolean;
  resolved_provider: string | null;
  used: boolean;
  model: string | null;
  system_prompt_chars: number;
  system_prompt_full: string;
  user_message_chars: number;
  user_message_preview: string;
  user_message_full: string;
  raw_response: string;
  raw_response_chars: number;
  tool_input: unknown;
  stop_reason: string | null;
  parsed_candidates: unknown;
  fallback_reason: string | null;
  latency_ms: number | null;
  usage: {
    input_tokens?: number;
    output_tokens?: number;
    cache_read_input_tokens?: number;
    cache_creation_input_tokens?: number;
  } | null;
  max_tokens: number;
  temperature: number;
};

export type BackendL3Rerank = {
  llm: BackendL3Llm | { used: false; skipped_reason: string };
  payload_to_llm: unknown;
  n_returned: number;
};

export type BackendFinalRow = {
  rank: number;
  combo_index: number;
  is_explore: boolean;
  signature: string;
  restaurant: { id?: string; name?: string; distance_m?: number; eta_min?: number };
  dishes: Array<{ dish_id?: string; name?: string; price?: number;
                   main_ingredient_type?: string; oil_level?: string }>;
  total_price: number;
  score: number;
  fit_score: number | null;
  health_flags: Record<string, boolean>;
  risk_flags: string[];
  taste_match: unknown;
  one_line_reason: string;
};

export type BackendConfig = {
  meal_type: string;
  zone: string;
  today: string;
  daily_mood: string | null;
  version: string;
  use_llm_rerank: boolean;
  fallback_used: boolean;
  profile_overrides: Record<string, unknown>;
};

export type BackendMatchedDish = {
  dish_id: string;
  name: string;
  restaurant_id: string;
  restaurant_name: string | null;
  price?: number;
  nutrition_profile?: {
    // level 字段是 backend 数字 (1..N), 但可能在某些 schema 路径上是 string.
    oil_level?: number | string | null;
    spicy_level?: number | string | null;
    protein_grams_estimate?: number | null;
    main_ingredient_type?: string | null;
    cooking_method?: string | null;
    wetness?: number | string | null;
    grain_type?: string | null;
    processed_meat_flag?: boolean | null;
    sweet_sauce_level?: number | string | null;
    vegetable_ratio_estimate?: number | null;
  };
  stage:
    | "passed_recall"
    | "dropped_hard_filter"
    | "dropped_diversity_filter"
    | "unknown";
  reason: string | null;
};

export type BackendMatchedCombo = {
  rank: number;
  score: number;
  signature: string;
  breakdown: Record<string, number>;
};

export type BackendTargetTrace = {
  query: { restaurant_name?: string; dish_names?: string[] };
  matched_dishes: BackendMatchedDish[];
  matched_combos_in_ranked: BackendMatchedCombo[];
  in_final: boolean;
};

export type BackendDebugRecommend = {
  config: BackendConfig;
  context: Record<string, unknown>;
  l1_recall: BackendL1Recall;
  l2_score: BackendL2Score;
  l3_rerank: BackendL3Rerank;
  final: BackendFinalRow[];
  target_trace: BackendTargetTrace | null;
  // D-083 PR-1: debug_recommend.py:758 顶层 feedback_view_snapshot.
  // Optional 兼容老 chisha 后端 (旧版本不写此字段).
  feedback_view_snapshot?: BackendFeedbackViewSnapshot;
};

export type BackendDebugRecommendReq = {
  meal_type?: string;
  today?: string;
  use_llm_rerank?: boolean | null;
  profile_overrides?: Record<string, unknown> | null;
  daily_mood?: string | null;
  trace_target?: { restaurant_name: string; dish_names: string[] } | null;
  n_return?: number;
  n_explore?: number;
};

// ---------- D-079: /api/debug/* trace replay endpoints ----------

export type BackendFeedbackLink = {
  accepted: boolean;
  accepted_rank: number | null;
  accepted_at: string | null;
  stopped: boolean;
  feedback_submitted: boolean;
  rating: number | null;
  feedback_record?: unknown;
};

export type BackendSessionMeta = {
  session_id: string;
  started_at: string;
  meal_type: "lunch" | "dinner" | string;
  zone: string;
  top1_summary: string;
  total_latency_ms: number;
  l3_status: string;
  source: "production" | "what_if_preview" | string;
  feedback?: BackendFeedbackLink | null;
};

export type BackendSessionsResp = {
  items: BackendSessionMeta[];
  corrupt_count: number;
};

// trace.l3 in production trace is flat (different from BackendL3Llm shape).
export type BackendTraceL3 = {
  used: boolean;
  status: "ok" | "fallback" | "config_error" | "skipped" | null | string;
  model: string | null;
  resolved_provider: string | null;
  raw_response: string;
  raw_response_chars: number;
  system_prompt_chars?: number;
  user_message_chars?: number;
  user_message_full?: string;
  tool_input: unknown;
  stop_reason: string | null;
  fallback_reason: string | null;
  parsed_candidates: unknown;
  payload_to_llm: unknown;
  n_returned: number;
  used_fallback: boolean;
  // optional new fields (not always present, but adapter tolerates).
  // D-079 followup: usage shape 是 provider 统一后的 OpenAI 风格
  // (prompt_tokens/completion_tokens/cached_tokens/cache_write_tokens, 见
  // chisha/llm_providers/*.py); adapter.wrapTraceL3 做字段名映射到前端的
  // Anthropic 命名 (input_tokens/cache_read_input_tokens) — 两种命名都兼容.
  latency_ms?: number;
  usage?: {
    // OpenAI 风格 (provider 实际返回)
    prompt_tokens?: number;
    completion_tokens?: number;
    cached_tokens?: number;
    cache_write_tokens?: number;
    cost?: number;
    // Anthropic 风格 (兼容老 trace)
    input_tokens?: number;
    output_tokens?: number;
    cache_read_input_tokens?: number;
    cache_creation_input_tokens?: number;
  };
  max_tokens?: number;
  temperature?: number;
};

export type BackendTraceRefine = {
  applied: boolean;
  user_input?: string;
  intent?: unknown;
  round?: number;
  n_combos_recalled?: number;
  n_after_l2?: number;
  n_returned?: number;
  candidate_ids?: string[];
  ts?: string;
};

export type BackendDebugTrace = {
  __version: number;
  __source: "production" | "what_if_preview" | string;
  __parent_session_id: string | null;
  __llm_called: boolean;
  __frozen: {
    ctx: Record<string, unknown>;
    today: string;
    meal_type: "lunch" | "dinner" | string;
    zone: string;
    profile_snapshot: Record<string, unknown>;
    l1_combos: Array<{ restaurant_id: string; dish_ids: string[] }>;
    restaurants: Record<string, Record<string, unknown>>;
    dishes: Record<string, Record<string, unknown>>;
    l1_prefs_snapshot: unknown;
    l2_meal_log_view: unknown[];
  };
  __config: {
    use_llm_rerank: boolean | null;
    n_return: number;
    n_explore: number;
    daily_mood: string | null;
    refine_text: string | null;
    profile_overrides: Record<string, unknown> | null;
  };
  __feedback?: BackendFeedbackLink | null;
  session_id: string;
  started_at: string;
  total_latency_ms: number;
  ctx_latency_ms: number;
  recall_latency_ms: number;
  score_latency_ms: number;
  rerank_latency_ms: number;
  final_latency_ms: number;
  l1: BackendL1Recall;
  l2: BackendL2Score;
  l3: BackendTraceL3;
  final: BackendFinalRow[];
  refine: BackendTraceRefine;
  // D-083 PR-1: 顶层 feedback_view_snapshot. 老 v1 trace 无此字段, 读侧空骨架兜底.
  feedback_view_snapshot?: BackendFeedbackViewSnapshot;
};

export type BackendWhatIfOverrides = {
  n_return?: number | null;
  n_explore?: number | null;
  use_llm_rerank?: boolean | null;
  profile_overrides?: Record<string, unknown> | null;
};

export type BackendWhatIfReq = {
  base_session_id: string;
  overrides: BackendWhatIfOverrides;
};

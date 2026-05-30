// types.ts — backend-shape mirrors. Keep in sync with the Python schema
// (chisha/recommend/*, debug_server.py); see docs/api.md §5 for the contract.

export type MealType = "lunch" | "dinner";

// D-071/D-073: mood picker 已下线, V1.2 前端 input 类型只用 "neutral".
// 前端发出的 mood 一律 neutral; UI 类型 (LABELS / FIXED_MOOD / recommend args) 用此.
export type Mood = "neutral";

// 后端 schema 仍接受历史枚举 (旧 session / debug 调用方可能仍带), response
// 字段 (HistoryItem.mood / context.daily_mood) 用此宽类型兜底, 防运行时不匹配.
export type MoodResponse =
  | Mood
  | "want_clean"
  | "want_indulgent"
  | "want_light"
  | "want_soup"
  | "low_carb";

export type ZoneId =
  | "shenzhen-bay"
  | "home"
  | "futian-cbd"
  | "other";

export type IngredientKind =
  | "红肉"
  | "白肉"
  | "海鲜"
  | "蛋"
  | "豆制品"
  | "纯素"
  | "主食";

export interface Dish {
  dish_id: string;
  canonical_name: string;
  price: number;
  main_ingredient_type: IngredientKind;
  oil_level: number;
}

export interface RestaurantRef {
  id: string;
  name: string;
  distance_m: number;
  eta_min: number;
}

export interface HealthFlags {
  veg_ok: boolean;
  protein_ok: boolean;
  oil_ok: boolean;
  processed_meat: boolean;
  sweet_sauce: boolean;
  wetness: boolean;
}

export interface Candidate {
  id: string;
  rank: number;
  is_explore: boolean;
  summary: string;
  restaurant: RestaurantRef;
  dishes: Dish[];
  total_price: number;
  vegetable_dish_count: number;
  estimated_total_oil: number;
  estimated_total_protein_g: number;
  score: number;
  fit_score: number | null;
  taste_match: number | null;
  reason_one_line: string;
  health_flags: HealthFlags;
  risk_flags: string[];
  // 后端历史枚举 (D-071/D-073 后 L2 不再用), 类型保持 string key 放宽兼容
  mood_affinity?: Partial<Record<string, number>>;
}

export interface RecommendResponse {
  session_id: string;
  meal_type: MealType;
  zone: ZoneId;
  round: number;
  version: string;
  generated_at: string;
  context: {
    meal_type: MealType;
    zone: ZoneId;
    now: string;
    weekday: number;
    last_meal: unknown;
    recent_3d_cuisines: Record<string, number>;
    recent_3d_ingredients: Record<string, number>;
    last_feedback: unknown;
    daily_mood: MoodResponse;
    refine_input: string | null;
  };
  stats: {
    n_dishes_total: number;
    n_combos_recalled: number;
    n_combos_after_score: number;
    n_returned: number;
  };
  candidates: Candidate[];
  status_bar?: StatusBarPayload;
  // T-P1b-02: L3 narrative ("为什么推这 5 道" ≤ 50 字)
  // 空字符串 = LLM 路径未生成 (fallback / 旧 trace), 前端不渲染
  narrative?: string;
}

// ── T-P1b-01 顶部 always-on 状态条 ────────────────────────────────────────────
// 后端 chisha/status_bar.py:build_status_bar() 派生; 三态:
//   - baseline: override_events 为空, 仅展示 active_methodology + l0_protections
//   - l0_a/b_block: 永久保护触发, 不可破
//   - l0_c_relaxed: refine 解除 methodology (破戒模式)
export type OverrideEventKind = "l0_a_block" | "l0_b_block" | "l0_c_relaxed";

export interface OverrideEvent {
  kind: OverrideEventKind;
  term: string | null;
  dropped_count: number;
  message: string;
}

export interface StatusBarPayload {
  active_methodology: {
    labels: string[];
  };
  l0_protections: {
    allergies: string[];
    dietary_law: "vegetarian" | "halal" | null;
  };
  override_events: OverrideEvent[];
}

// ── Banner / accept queue (V1.1 D-060) ──────────────────────────────────────
// Inbox-style entry; the prototype's "single last_unfed" shape is gone.
// `snoozed`/`stopped` are derived in mock from per-item timestamps.
export interface UnfedSession {
  session_id: string;
  meal_type: MealType;
  restaurant_name: string;
  summary: string;
  accepted_at: string;
  snoozed: boolean;
  stopped: boolean;
}

// ── Feedback page payload ────────────────────────────────────────────────────
export interface FeedbackSession {
  session_id: string;
  meal_type: MealType;
  accepted_at: string;
  accepted_rank: number | null;
  candidates: Candidate[];
}

// V1.1 schema (D-063/062/063/064).
export type DimVal = 0 | 1 | 2 | null;        // 0=low / 1=mid / 2=high
export type GutVal = -1 | 0 | 1 | null;       // 难吃 / 普通 / 好吃
export type FeedbackVariant = "progressive" | "not-eaten";

export interface FeedbackPayload {
  session_id: string;
  accepted_rank: number | null;
  rating: GutVal;
  reason_match: DimVal;
  fullness: DimVal;
  oil_calibration: DimVal;
  repurchase_intent: DimVal;
  note: string;
  variant: FeedbackVariant;
}

export interface FeedbackComment {
  id: string;
  text: string;
  created_at: string; // ISO8601
}

export interface FeedbackRecord extends FeedbackPayload {
  submitted_at: string; // ISO8601
  comments: FeedbackComment[];
}

// Inbox row shape for `/feedback` list (待反馈 / 暂缓 / 已反馈)
export interface RecentFeedback {
  session_id: string;
  meal_type: MealType;
  restaurant_name: string;
  accepted_at: string;
  submitted_at: string;
  rating: GutVal;
  accepted_rank: number | null;
}

// ── History ──────────────────────────────────────────────────────────────────
export interface HistoryItem {
  session_id: string;
  meal_type: MealType;
  generated_at: string;
  accepted_rank: number | null;
  candidates_summary: string[];
  mood: MoodResponse;
}

// ── Skip-meal (D-054) ────────────────────────────────────────────────────────
export type SkipReason =
  | "cafeteria"
  | "brought"
  | "outside"
  | "social"
  | "none_fit"
  | "not_hungry"
  | null;

// ── Profile (mirrors profile.yaml) ───────────────────────────────────────────
export interface Profile {
  basics: {
    name: string;
    city: string;
    goal: string;
    zones: { lunch: ZoneId; dinner: ZoneId };
  };
  plate_rule: {
    must_have_vegetable: boolean;
    min_vegetable_dishes: number;
    min_protein_g: number;
    prefer_oil_level_at_most: number;
    hard_max_oil_level: number;
  };
  taste_description: string;
  preferences: {
    liked_cuisines: string[];
    disliked_cuisines: string[];
    banned_cuisines: string[];
    banned_processed_meat: boolean;
    banned_sweet_sauce_level_3: boolean;
    avoid_dishes: string[];
    avoid_main_ingredients: string[];
    avoid_cooking_methods: string[];
    avoid_restaurants: string[];
    spicy_tolerance: 0 | 1 | 2 | 3;
  };
  delivery_constraints: {
    hard_max_eta_min: number;
    prefer_max_eta_min: number;
  };
  price_range: {
    hard_max_lunch: number;
    hard_max_dinner: number;
    prefer_max_lunch: number;
    prefer_max_dinner: number;
  };
  meal_trigger_time: {
    lunch: string;
    dinner: string;
    weekend: boolean;
  };
  llm: {
    provider: "auto" | "claude_code_cli" | "anthropic" | "openrouter";
    model: {
      claude_code_cli: string;
      anthropic: string;
      openrouter: string;
    };
  };
}

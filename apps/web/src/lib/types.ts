// types.ts — backend-shape mirrors. Keep in sync with the Python schema
// (chisha/recommend/*, debug_server.py); see docs/api.md §5 for the contract.

export type MealType = "lunch" | "dinner";

export type Mood =
  | "neutral"
  | "want_clean"
  | "want_indulgent"
  | "want_light"
  | "want_soup"
  | "low_carb";

export type ZoneId =
  | "shenzhen-bay"
  | "home"
  | "futian-cbd"
  | "beijing-zgc"
  | "shanghai-xhh"
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
  fit_score: number;
  taste_match: number;
  reason_one_line: string;
  health_flags: HealthFlags;
  risk_flags: string[];
  mood_affinity?: Partial<Record<Mood, number>>;
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
    daily_mood: Mood;
    refine_input: string | null;
  };
  stats: {
    n_dishes_total: number;
    n_combos_recalled: number;
    n_combos_after_score: number;
    n_returned: number;
  };
  candidates: Candidate[];
}

// ── Banner / accept queue (V1.1 D-058) ──────────────────────────────────────
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

// V1.1 schema (D-061/062/063/064). Old `rating_taste/rating_satisfaction/chips`
// removed — the legacy 5-star double-axis form is gone.
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
  quick?: boolean;
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
  mood: Mood;
}

// ── Skip-meal (D-052) ────────────────────────────────────────────────────────
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

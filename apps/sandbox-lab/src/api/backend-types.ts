// S-08: Backend dict shapes (直接对应 FastAPI 返 JSON).
// 命名约定: Backend* 前缀, 跟前端视图 type (sandbox.ts) 区分.
// adapter.ts 负责 backend → 前端 view-model 转换.

export interface BackendSandboxSessionMeta {
  sid: string;
  is_default: boolean;
  created_at: string | null;
  size_bytes: number;
  has_state: boolean;
}

export interface BackendSessionsListResp {
  sessions: BackendSandboxSessionMeta[];
}

export interface BackendSessionMetaFull {
  sid: string;
  name: string;
  days: number;
  seed: number;
  profile: string;
  origin: string;  // "blank" | "real_snapshot" | string
  status: string;  // "running" | "done"
  lastUsed: string;
  currentMealIdx: number;
  totalMeals: number;
  branchFrom: string | null;
}

export interface BackendSandboxClock {
  idx: number;
  day: number;
  slot: string;  // "lunch" | "dinner"
  total: number;
}

// History entry — backend dict 不带 day/slot/score/flags/altScores
export interface BackendHistoryEntry {
  idx: number;
  state: "eat" | "skip";
  dish?: string;
  session_id?: string | null;
  accepted_at?: string | null;
  rank?: number;
  reason?: string | null;
}

// Rec — backend format_v2_to_rec 输出, 跟前端 Rec 字段一致 (extra: id)
export interface BackendRec {
  rank: number;
  name: string;
  venue: string;
  dishes: string[];
  price: number;
  l2: number;
  l3: number;
  boost: number;
  intent: string;
  l1Hits: string[];
  explore: boolean;
  conflict: { rule: string; reason: string } | null;
  meta: { eta: string; dist: string; protein: number; oil: string };
  why: string;
  id?: string;
}

// Decision — backend build_decision 输出, 跟前端 Decision 完全对齐
export interface BackendDecision {
  when: string;
  pick: string;
  rank: number | "—";
  l3: number | "—";
  diff: Array<{
    kind: "add" | "rm" | "up" | "dn" | "ttl";
    field: string;
    from?: string;
    to?: string;
    value?: string;
    delta?: string;
  }>;
  implications: Array<{ field: string; text: string }>;
}

export interface BackendActiveRule {
  label: string;
  sinceRound: number;
  sessionId: string;
}

export interface BackendFullSnapshot {
  meta: BackendSessionMetaFull;
  clock: BackendSandboxClock;
  history: BackendHistoryEntry[];
  currentRecs: BackendRec[];
  lastDecision: BackendDecision | null;
  activeRules: { refine: BackendActiveRule[]; blacklist: BackendActiveRule[] };
  taste: unknown[];
  keywords: unknown[];
  recent: string[];
  fatigue: unknown[];
}

// ── POST resps ──

export interface BackendRecsResp {
  currentRecs: BackendRec[];
  recommend_session_id: string;
  applied_refine: BackendActiveRule | null;
  meal_idx: number;
}

export interface BackendEatResp {
  job_id: string;
  status: string;  // "running"
  new_meal_idx: number;
  meal_idx_eaten: number;
}

export interface BackendSkipResp {
  new_meal_idx: number;
  meal_idx_skipped: number;
  decision: BackendDecision;
}

export interface BackendSwapResp {
  currentRecs: BackendRec[];
  recommend_session_id: string;
}

export interface BackendRefineResp {
  currentRecs: BackendRec[];
  recommend_session_id: string;
  activeRules: { refine: BackendActiveRule[]; blacklist: BackendActiveRule[] };
}

// Job 状态: backend 实际值 "pending" | "running" | "done" | "failed" | "cancelled_by_rollback"
export interface BackendJobInfo {
  status: "pending" | "running" | "done" | "failed" | "cancelled_by_rollback";
  sid: string | null;
  meal_idx: number;
  started_at: string;
  ended_at?: string;
  result?: { decision: BackendDecision; meal_idx: number };
  error?: string;
}

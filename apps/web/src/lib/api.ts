// api.ts — production HTTP client (D-051 backend on port 8765).
// Shape MUST match docs/api.md §5. The mock implementation in mockApi.ts
// satisfies the same `ChishaApi` interface so swaps are transparent.

import type {
  Candidate,
  FeedbackPayload,
  FeedbackRecord,
  FeedbackSession,
  HistoryItem,
  MealType,
  Mood,
  Profile,
  RecentFeedback,
  RecommendResponse,
  SkipReason,
  UnfedSession,
} from "./types";
import * as mock from "./mockApi";

export interface ChishaApi {
  recommend(args: { meal_type?: MealType; mood?: Mood }): Promise<RecommendResponse>;
  refine(args: {
    session_id: string;
    refine_text: string;
    meal_type?: MealType;
    mood?: Mood;
    round?: number;
    excludeIds?: string[];
  }): Promise<RecommendResponse>;
  accept(args: {
    session_id: string;
    candidate_rank: number;
    candidate: Candidate;
  }): Promise<{ deeplink_url: string }>;
  skipMeal(args: { session_id: string; reason: SkipReason }): Promise<{ ok: true }>;
  // 待反馈 session 列表 (按时间倒序, 取首条即最新待反馈)。
  inbox(args?: { include_snoozed?: boolean }): Promise<{ items: UnfedSession[] }>;
  snoozeFeedback(args: { session_id: string }): Promise<{ ok: true }>;
  stopFeedback(args: { session_id: string }): Promise<{ ok: true }>;
  recentFeedbacks(args?: { limit?: number }): Promise<{ items: RecentFeedback[] }>;
  getFeedbackSession(args: { session_id: string }): Promise<FeedbackSession>;
  getFeedback(args: { session_id: string }): Promise<FeedbackRecord | null>;
  feedback(payload: FeedbackPayload): Promise<{ ok: true }>;
  appendFeedbackComment(args: {
    session_id: string;
    text: string;
  }): Promise<{ ok: true } | { ok: false; error: string }>;
  getProfile(): Promise<Profile>;
  putProfile(profile: Profile): Promise<{ ok: true }>;
  history(args?: { days?: number }): Promise<{ items: HistoryItem[] }>;
}

// ── Real-fetch implementation ────────────────────────────────────────────────
// Endpoints are proxied through Vite (vite.config.ts → 127.0.0.1:8765) in dev.
// In production deployment, served from the same FastAPI app under /api/*.

async function jpost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

async function jget<T>(path: string, query?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }
  const res = await fetch(url.pathname + url.search);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

const real: ChishaApi = {
  recommend: ({ meal_type = "lunch", mood = "neutral" } = {}) =>
    jget("/api/recommend", { meal_type, mood }),
  refine: (args) => jpost("/api/refine", args),
  accept: (args) => jpost("/api/accept", args),
  skipMeal: (args) => jpost("/api/skip", args),
  inbox: ({ include_snoozed = true } = {}) =>
    jget("/api/feedback/inbox", { include_snoozed: include_snoozed ? 1 : 0 }),
  snoozeFeedback: (args) => jpost("/api/feedback/snooze", args),
  stopFeedback: (args) => jpost("/api/feedback/stop", args),
  recentFeedbacks: ({ limit = 6 } = {}) => jget("/api/feedback/recent", { limit }),
  getFeedbackSession: ({ session_id }) => jget(`/api/feedback/${session_id}`),
  getFeedback: ({ session_id }) => jget(`/api/feedback/${session_id}/record`),
  feedback: (p) => jpost("/api/feedback", p),
  appendFeedbackComment: ({ session_id, text }) =>
    jpost(`/api/feedback/${session_id}/comments`, { text }),
  getProfile: () => jget("/api/profile"),
  putProfile: (p) => jpost("/api/profile", p),
  history: ({ days = 7 } = {}) => jget("/api/history", { days }),
};

// ── Dispatcher ────────────────────────────────────────────────────────────────
// Default = real fetch (backend stable since D-069/D-073).
// Explicit `VITE_USE_MOCK=1` opts back into the mock store for offline UI work.
const useMock = (import.meta.env.VITE_USE_MOCK ?? "0") === "1";

export const api: ChishaApi = useMock ? mock.api : real;
export const isMock = useMock;

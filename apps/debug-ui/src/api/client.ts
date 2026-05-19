// Thin fetch wrappers. ALL backend rename / shape coercion happens in adapter.ts.

import type {
  BackendDebugTrace,
  BackendSessionsResp,
} from "./backend-types";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.name = "ApiError";
  }
}

async function fetchJson<T>(input: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(input, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
    });
  } catch (err) {
    // Network error / DNS / refused — backend offline.
    throw new ApiError(0, "NETWORK", err instanceof Error ? err.message : String(err));
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? body?.message ?? detail;
    } catch {
      // body not JSON, ignore
    }
    throw new ApiError(res.status, `HTTP_${res.status}`, String(detail));
  }
  return (await res.json()) as T;
}

export type ProfileResponse = Record<string, unknown>;

export function getProfile(): Promise<ProfileResponse> {
  return fetchJson<ProfileResponse>("/api/profile");
}

// ---------- D-079: trace replay (read-only) ----------
// 注: D-087 后写入路径全删 (postDebugRecommend / postWhatIf). 这两个 GET 端点
// 保留, 让 useWaTrace 在 v3 endpoint 出 500 时 fallback 走老 sessions 列表.

export function fetchSessions(params: {
  limit?: number;
  meal_type?: "lunch" | "dinner" | null;
} = {}): Promise<BackendSessionsResp> {
  const q = new URLSearchParams();
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.meal_type) q.set("meal_type", params.meal_type);
  const qs = q.toString();
  return fetchJson<BackendSessionsResp>(
    `/api/debug/sessions${qs ? `?${qs}` : ""}`,
  );
}

export function fetchSession(sid: string): Promise<BackendDebugTrace> {
  return fetchJson<BackendDebugTrace>(
    `/api/debug/sessions/${encodeURIComponent(sid)}`,
  );
}

// ---------- D-087 Workflow A: 4 个新 read-only endpoint ----------

import type { IntentFieldDescriptor, TraceMeta } from "../types/trace";

// Backend rounds 字段不含 l1/l2/l3/final body (stub).
export type BackendRoundStub = {
  id: string;
  label?: string | null;
  started_at?: string | null;
  user_input?: string | null;
  intent_v2?: unknown;
  narrative?: string | null;
  kpi?: {
    combos?: number;
    l2_top?: number;
    top1?: string;
    latency_ms?: number;
  };
  diff?: {
    vs: string; in: number; out: number; up: number; down: number;
  } | null;
};

export type BackendTraceDetail = {
  meta: BackendTraceMeta;
  rounds: BackendRoundStub[];
};

export type BackendTraceMeta = {
  session_id?: string;
  started_at?: string | null;
  meal_type?: string | null;
  zone?: string | null;
  top1_summary?: string | null;
  total_latency_ms?: number | null;
  l3_status?: string | null;
  round_ids?: string[];
  latest_round?: string;
  refine_count?: number;
  __source?: string;
  feedback?: { type: string; rank?: number; count?: number } | null;
};

export type BackendRoundFull = BackendRoundStub & {
  l1?: unknown;
  l2?: unknown;
  l3?: unknown;
  final?: unknown;
  __frozen?: unknown;
  // D-089-S5a: R2+ refine round 含意图解析 LLM call 完整 trace
  // (refine_intent_v2._llm_parse_v2 输出, serialize_llm_call_trace 序列化).
  // R1 主链路无此字段 (R1 没有 refine intent 解析步骤).
  refine_intent_llm?: import("./backend-types").BackendLlmCallTrace | null;
};

export function fetchTraces(params: {
  limit?: number;
  meal_type?: "lunch" | "dinner" | null;
} = {}): Promise<TraceMeta[]> {
  const q = new URLSearchParams();
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.meal_type) q.set("meal_type", params.meal_type);
  const qs = q.toString();
  return fetchJson<TraceMeta[]>(`/api/traces${qs ? `?${qs}` : ""}`);
}

export function fetchTraceDetail(sid: string): Promise<BackendTraceDetail> {
  return fetchJson<BackendTraceDetail>(
    `/api/trace/${encodeURIComponent(sid)}`,
  );
}

export function fetchRoundFull(
  sid: string, roundId: string,
): Promise<BackendRoundFull> {
  return fetchJson<BackendRoundFull>(
    `/api/trace/${encodeURIComponent(sid)}/round/${encodeURIComponent(roundId)}`,
  );
}

export function fetchIntentSchema(): Promise<IntentFieldDescriptor[]> {
  return fetchJson<IntentFieldDescriptor[]>("/api/intent_schema");
}

// Thin fetch wrappers. ALL backend rename / shape coercion happens in adapter.ts.

import type {
  BackendDebugRecommend,
  BackendDebugRecommendReq,
  BackendDebugTrace,
  BackendSessionsResp,
  BackendWhatIfReq,
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

export function postDebugRecommend(
  req: BackendDebugRecommendReq,
): Promise<BackendDebugRecommend> {
  return fetchJson<BackendDebugRecommend>("/api/lab/debug_recommend", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export type ProfileResponse = Record<string, unknown>;

export function getProfile(): Promise<ProfileResponse> {
  return fetchJson<ProfileResponse>("/api/profile");
}

// ---------- D-079: trace replay ----------

export function fetchSessions(params: {
  limit?: number;
  meal_type?: "lunch" | "dinner" | null;
} = {}): Promise<BackendSessionsResp> {
  const q = new URLSearchParams();
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.meal_type) q.set("meal_type", params.meal_type);
  const qs = q.toString();
  return fetchJson<BackendSessionsResp>(
    `/api/lab/sessions${qs ? `?${qs}` : ""}`,
  );
}

export function fetchSession(sid: string): Promise<BackendDebugTrace> {
  return fetchJson<BackendDebugTrace>(
    `/api/lab/sessions/${encodeURIComponent(sid)}`,
  );
}

export function postWhatIf(req: BackendWhatIfReq): Promise<BackendDebugTrace> {
  return fetchJson<BackendDebugTrace>("/api/lab/what_if", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// D-082: 触发 refine. 后端 /api/refine 同 session 二轮, 返 RecommendResponse 形状
// (debug-ui 不消费, 触发完直接 refetch trace 拿 round2). 调用方 await 后调
// fetchSession(sid) 取更新过的 trace.
export function postRefine(
  sessionId: string,
  refineText: string,
): Promise<unknown> {
  return fetchJson<unknown>("/api/refine", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, refine_text: refineText }),
  });
}


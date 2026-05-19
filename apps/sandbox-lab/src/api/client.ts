// S-08: Thin fetch wrappers. shape coercion 在 adapter.ts.
// 默认 mock_recommend=1; ?real=1 query 关闭, 仅作用于 /recs /swap /refine.

import type {
  BackendEatResp,
  BackendFullSnapshot,
  BackendJobInfo,
  BackendRecsResp,
  BackendRefineResp,
  BackendSandboxSessionMeta,
  BackendSessionsListResp,
  BackendSkipResp,
  BackendSwapResp,
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
    throw new ApiError(0, "NETWORK", err instanceof Error ? err.message : String(err));
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? body?.message ?? detail;
    } catch {
      // body not JSON
    }
    throw new ApiError(res.status, `HTTP_${res.status}`, String(detail));
  }
  return (await res.json()) as T;
}


// `?real=1` 关 mock; 默认带 mock_recommend=1 (S-08 §6 acceptance default)
function isRealMode(): boolean {
  if (typeof window === "undefined") return false;
  const sp = new URLSearchParams(window.location.search);
  return sp.get("real") === "1";
}


function withMock(path: string): string {
  // 仅 /recs /swap /refine 接受 mock_recommend
  if (isRealMode()) return path;
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}mock_recommend=1`;
}


// ── GET ──

export async function pingBackend(): Promise<boolean> {
  try {
    const res = await fetch("/api/sandbox/sessions");
    return res.ok;
  } catch {
    return false;
  }
}


export function listSessions(): Promise<BackendSessionsListResp> {
  return fetchJson<BackendSessionsListResp>("/api/sandbox/sessions");
}


export function getFullSnapshot(sid: string): Promise<BackendFullSnapshot> {
  return fetchJson<BackendFullSnapshot>(
    `/api/sandbox/sessions/${encodeURIComponent(sid)}`,
  );
}


export function getJob(sid: string, jobId: string): Promise<BackendJobInfo> {
  return fetchJson<BackendJobInfo>(
    `/api/sandbox/sessions/${encodeURIComponent(sid)}/jobs/${encodeURIComponent(jobId)}`,
  );
}


// ── POST ──

export function createSession(
  sid: string,
  days = 7,
): Promise<BackendSandboxSessionMeta> {
  return fetchJson<BackendSandboxSessionMeta>("/api/sandbox/sessions", {
    method: "POST",
    body: JSON.stringify({ sid, days }),
  });
}


export function postRecs(
  sid: string,
  opts: { meal_type?: "lunch" | "dinner" | null } = {},
): Promise<BackendRecsResp> {
  return fetchJson<BackendRecsResp>(
    withMock(`/api/sandbox/sessions/${encodeURIComponent(sid)}/recs`),
    {
      method: "POST",
      body: JSON.stringify({ meal_type: opts.meal_type ?? null }),
    },
  );
}


export function postEat(sid: string, recRank: number): Promise<BackendEatResp> {
  return fetchJson<BackendEatResp>(
    `/api/sandbox/sessions/${encodeURIComponent(sid)}/eat`,
    {
      method: "POST",
      body: JSON.stringify({ rec_rank: recRank }),
    },
  );
}


export function postSkip(
  sid: string,
  reason: string | null = null,
): Promise<BackendSkipResp> {
  return fetchJson<BackendSkipResp>(
    `/api/sandbox/sessions/${encodeURIComponent(sid)}/skip`,
    {
      method: "POST",
      body: JSON.stringify({ reason }),
    },
  );
}


export function postSwap(
  sid: string,
  excludeIds: string[] = [],
): Promise<BackendSwapResp> {
  return fetchJson<BackendSwapResp>(
    withMock(`/api/sandbox/sessions/${encodeURIComponent(sid)}/swap`),
    {
      method: "POST",
      body: JSON.stringify({ exclude_ids: excludeIds }),
    },
  );
}


export function postRefine(sid: string, text: string): Promise<BackendRefineResp> {
  return fetchJson<BackendRefineResp>(
    withMock(`/api/sandbox/sessions/${encodeURIComponent(sid)}/refine`),
    {
      method: "POST",
      body: JSON.stringify({ text }),
    },
  );
}


export function postRollback(
  sid: string,
  mealIdx: number,
): Promise<BackendFullSnapshot> {
  return fetchJson<BackendFullSnapshot>(
    `/api/sandbox/sessions/${encodeURIComponent(sid)}/rollback`,
    {
      method: "POST",
      body: JSON.stringify({ meal_idx: mealIdx }),
    },
  );
}


export function postBranch(
  sid: string,
  fromMealIdx: number,
  name: string,
): Promise<BackendSandboxSessionMeta> {
  return fetchJson<BackendSandboxSessionMeta>(
    `/api/sandbox/sessions/${encodeURIComponent(sid)}/branch`,
    {
      method: "POST",
      body: JSON.stringify({ from_meal_idx: fromMealIdx, name }),
    },
  );
}

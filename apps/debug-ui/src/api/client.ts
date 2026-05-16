// Thin fetch wrappers. ALL backend rename / shape coercion happens in adapter.ts.

import type { BackendDebugRecommend, BackendDebugRecommendReq } from "./backend-types";

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
  return fetchJson<BackendDebugRecommend>("/api/debug_recommend", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export type ProfileResponse = Record<string, unknown>;

export function getProfile(): Promise<ProfileResponse> {
  return fetchJson<ProfileResponse>("/api/profile");
}

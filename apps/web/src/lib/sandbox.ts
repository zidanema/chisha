// D-077 PR-1d: sandbox time-travel API client.
//
// 与 chisha/web_api.py:/api/sandbox/* 端点契约保持一致.
// localhost-only (后端拒绝非 127.0.0.1), 不走 mock — sandbox 是真实交互模式.

export interface SandboxState {
  enabled: boolean;
  current_date?: string;
  day_index?: number;
  started_at_real?: string;
  started_at_virtual?: string;
  copy_real_data?: boolean;
  last_l1_extraction?: {
    at: string;
    status: "pending" | "ok" | "failed" | "skipped";
    based_on_meals: number | null;
    error: string | null;
  } | null;
  disabled_at_real?: string;
  last_advance_at_real?: string;
}

export interface LongTermPrefs {
  version?: number;
  extracted_at?: string;
  based_on_days?: number;
  based_on_meals?: number;
  boost: string[];
  penalty: string[];
  signals_not_scored?: Record<string, unknown>;
  evidence?: Array<{
    token?: string;
    rationale?: string;
    from_meals?: string[];
    source?: string;
  }>;
  regularities_freetext?: string[];
  bootstrap_from_legacy?: boolean;
  skipped_extraction?: boolean;
}

export interface SandboxInspect {
  enabled: boolean;
  state?: SandboxState;
  long_term_prefs?: LongTermPrefs | null;
  feedbacks_recent?: Array<Record<string, unknown>>;
  feedbacks_total?: number;
  meal_log_recent?: Array<Record<string, unknown>>;
  accepted_count?: number;
}

async function jpost<T>(path: string, body: unknown = {}): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${path}: ${text || res.statusText}`);
  }
  return res.json();
}

async function jget<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${path}: ${text || res.statusText}`);
  }
  return res.json();
}

export const sandboxApi = {
  init: (args: { start_date?: string; copy_real_data?: boolean } = {}) =>
    jpost<SandboxState>("/api/sandbox/init", args),

  advance: (args: { days?: number } = {}) =>
    jpost<SandboxState>("/api/sandbox/advance", args),

  reset: () => jpost<{ ok: boolean; reset_at: string }>("/api/sandbox/reset"),

  disable: () => jpost<SandboxState>("/api/sandbox/disable"),

  state: () => jget<SandboxState>("/api/sandbox/state"),

  inspect: () => jget<SandboxInspect>("/api/sandbox/inspect"),

  refreshPrefs: (args: { force_run_without_llm?: boolean; window_days?: number } = {}) =>
    jpost<LongTermPrefs & { path?: string }>("/api/long_term_prefs/refresh", args),
};

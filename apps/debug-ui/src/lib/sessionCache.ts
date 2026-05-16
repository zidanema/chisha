// Session history cache. Stops backend persistence from being on Phase 2's
// critical path. Phase 7 may replace this with /api/sessions on the server.

import type { Meal, RunHistoryRow, Session } from "../types/trace";

export type StoredRunConfig = {
  meal: Meal;
  today: string;
  llmAuto: boolean;
  profileOverride: string;  // raw textarea content, may be empty/invalid
};

const HISTORY_KEY = "chisha:run-history";
const PAYLOAD_KEY_PREFIX = "chisha:session:";
const CONFIG_KEY_PREFIX = "chisha:config:";
// 一次 trace ~358KB JSON × 2 (UTF-16) ≈ 700KB / 条. localStorage 配额各浏览器:
// Chrome/Firefox 5-10MB, Safari/iOS 硬限 5MB. 留余量给 theme/config/其他 key,
// 5 条上限保证 5×700KB=3.5MB << 5MB iOS 配额 (Codex final PR review).
const MAX_ITEMS = 5;

type StoredHistoryRow = RunHistoryRow & { stored_at: number };

function readHistory(): StoredHistoryRow[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as StoredHistoryRow[]) : [];
  } catch {
    return [];
  }
}

function pruneOrphanPayloads(keepIds: Set<string>): void {
  // 历史被裁剪后, 把不再引用的 chisha:session:* + chisha:config:* 都删掉.
  try {
    const orphans: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (!k) continue;
      if (k.startsWith(PAYLOAD_KEY_PREFIX)) {
        const id = k.slice(PAYLOAD_KEY_PREFIX.length);
        if (!keepIds.has(id)) orphans.push(k);
      } else if (k.startsWith(CONFIG_KEY_PREFIX)) {
        const id = k.slice(CONFIG_KEY_PREFIX.length);
        if (!keepIds.has(id)) orphans.push(k);
      }
    }
    for (const k of orphans) localStorage.removeItem(k);
  } catch {
    // best-effort
  }
}

function writeHistory(rows: StoredHistoryRow[]): void {
  const capped = rows.slice(0, MAX_ITEMS);
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(capped));
  } catch {
    // quota — silently drop oldest by next put
  }
  pruneOrphanPayloads(new Set(capped.map((r) => r.id)));
}

function shortId(): string {
  return Math.random().toString(36).slice(2, 8);
}

export function makeSessionId(when = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const d = `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}`;
  const t = `${pad(when.getHours())}-${pad(when.getMinutes())}-${pad(when.getSeconds())}`;
  return `sess_${d}_${t}_${shortId()}`;
}

export function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const sameYesterday =
    d.getFullYear() === yesterday.getFullYear() &&
    d.getMonth() === yesterday.getMonth() &&
    d.getDate() === yesterday.getDate();
  const pad = (n: number) => String(n).padStart(2, "0");
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (sameDay) return hm;
  if (sameYesterday) return `昨 ${hm}`;
  return `前 ${hm}`;
}

export function rememberSession(session: Session, area: string, config?: StoredRunConfig): void {
  const row: StoredHistoryRow = {
    id: session.session_id,
    title: `${session.l1.meal} · ${area}`,
    time: formatRelativeTime(session.started_at),
    status: session.l3.status === "fallback"
      ? "fallback"
      : session.l3.status === "config_error"
        ? "warn"
        : "ok",
    latency: session.total_latency_ms,
    meal: session.l1.meal,
    area,
    stored_at: Date.now(),
  };
  const existing = readHistory().filter((r) => r.id !== row.id);
  // writeHistory will also prune orphan payloads for any id that drops off MAX_ITEMS.
  writeHistory([row, ...existing]);
  try {
    localStorage.setItem(PAYLOAD_KEY_PREFIX + session.session_id, JSON.stringify(session));
  } catch {
    // Quota likely — drop history-only payload writes. Row metadata still saved.
  }
  if (config) {
    try {
      localStorage.setItem(
        CONFIG_KEY_PREFIX + session.session_id, JSON.stringify(config),
      );
    } catch {
      // best-effort
    }
  }
}

export function loadConfig(id: string): StoredRunConfig | null {
  try {
    const raw = localStorage.getItem(CONFIG_KEY_PREFIX + id);
    return raw ? (JSON.parse(raw) as StoredRunConfig) : null;
  } catch {
    return null;
  }
}

export function listSessions(): RunHistoryRow[] {
  return readHistory().map(({ stored_at: _omit, ...row }) => row);
}

export function loadSession(id: string): Session | null {
  try {
    const raw = localStorage.getItem(PAYLOAD_KEY_PREFIX + id);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

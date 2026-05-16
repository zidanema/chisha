import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, postDebugRecommend } from "../api/client";
import { backendToSession } from "../api/adapter";
import { pushToast } from "../components/Toaster";
import { zoneLabel } from "../constants/zones";
import { listSessions, loadSession as loadCachedSession, makeSessionId, rememberSession } from "../lib/sessionCache";
import type { StoredRunConfig } from "../lib/sessionCache";
import { MOCK_SESSION } from "../mocks/session";
import type { Meal, RunHistoryRow, Session } from "../types/trace";

export type RunStatus = "idle" | "loading" | "ok" | "error" | "offline";

export type RunArgs = {
  meal: Meal;
  today: string;          // YYYY-MM-DD
  llmAuto: boolean;
  profileOverride: Record<string, unknown> | null;
  // Raw textarea content for "replay run" preservation (separate from the
  // parsed override sent to backend).
  profileOverrideRaw: string;
};

export type UseSession = {
  session: Session;
  status: RunStatus;
  error: string | null;
  history: RunHistoryRow[];
  activeSessionId: string;
  setActiveSessionId: (id: string) => void;
  runMain: (args: RunArgs) => Promise<void>;
  refreshHistory: () => void;
};

const INITIAL_HISTORY_FALLBACK: RunHistoryRow[] = [
  // Dev convenience: when nothing cached yet, show the canonical mock row
  // so the sidebar isn't empty on first load.
  { id: MOCK_SESSION.session_id, title: "lunch · 深圳湾 (mock)",
    time: "—", status: "ok", latency: MOCK_SESSION.total_latency_ms },
];

export function useSession(): UseSession {
  const cachedHistory = listSessions();
  const initialHistory = cachedHistory.length > 0 ? cachedHistory : INITIAL_HISTORY_FALLBACK;
  const initialActive = initialHistory[0]?.id ?? MOCK_SESSION.session_id;
  const initialSession =
    (initialActive !== MOCK_SESSION.session_id && loadCachedSession(initialActive)) ||
    MOCK_SESSION;

  const [session, setSession] = useState<Session>(initialSession);
  const [status, setStatus] = useState<RunStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<RunHistoryRow[]>(initialHistory);
  const [activeSessionId, setActiveSessionIdState] = useState<string>(initialActive);
  // Race guard: if user fires Run twice fast, ignore the stale fetch result.
  const runSeqRef = useRef(0);

  const refreshHistory = useCallback(() => {
    const fresh = listSessions();
    setHistory(fresh.length > 0 ? fresh : INITIAL_HISTORY_FALLBACK);
  }, []);

  const setActiveSessionId = useCallback((id: string) => {
    setActiveSessionIdState(id);
    if (id === MOCK_SESSION.session_id) {
      setSession(MOCK_SESSION);
      return;
    }
    const cached = loadCachedSession(id);
    if (cached) {
      setSession(cached);
    }
  }, []);

  const runMain = useCallback(async (args: RunArgs) => {
    const seq = ++runSeqRef.current;
    setStatus("loading");
    setError(null);
    const startedAt = new Date().toISOString();
    const t0 = performance.now();
    const newId = makeSessionId();
    try {
      const raw = await postDebugRecommend({
        meal_type: args.meal,
        today: args.today,
        use_llm_rerank: args.llmAuto ? null : false,
        profile_overrides: args.profileOverride,
      });
      if (seq !== runSeqRef.current) return; // stale
      const total = Math.round(performance.now() - t0);
      const fresh = backendToSession(raw, {
        sessionId: newId,
        startedAt,
        totalLatencyMs: total,
      });
      const area = zoneLabel(raw.config.zone);
      const cfg: StoredRunConfig = {
        meal: args.meal,
        today: args.today,
        llmAuto: args.llmAuto,
        profileOverride: args.profileOverrideRaw,
      };
      rememberSession(fresh, area, cfg);
      setSession(fresh);
      setActiveSessionIdState(newId);
      refreshHistory();
      setStatus("ok");
    } catch (err) {
      if (seq !== runSeqRef.current) return; // stale
      const apiErr = err instanceof ApiError ? err : null;
      const msg = apiErr?.message ?? (err instanceof Error ? err.message : String(err));
      if (apiErr?.code === "NETWORK") {
        setStatus("offline");
        setError("后端 :8765 不可达 — 显示 mock 数据。请确认 debug_server 已起。");
        pushToast({
          kind: "warn",
          title: "后端 offline · 显示 mock",
          detail: "uv run python -m chisha.debug_server",
        });
        // Keep current session (mock).
      } else {
        setStatus("error");
        setError(msg);
        pushToast({
          kind: "error",
          title: `推荐失败 ${apiErr?.status ?? ""}`.trim(),
          detail: msg.slice(0, 200),
        });
      }
    }
  }, [refreshHistory]);

  // Refresh history on window focus (catch out-of-band cache changes).
  useEffect(() => {
    const onFocus = () => refreshHistory();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshHistory]);

  return {
    session,
    status,
    error,
    history,
    activeSessionId,
    setActiveSessionId,
    runMain,
    refreshHistory,
  };
}

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchSession,
  fetchSessions,
  postDebugRecommend,
  postRefine,
} from "../api/client";
import { backendToSession, traceToSession } from "../api/adapter";
import { pushToast } from "../components/Toaster";
import { zoneLabel } from "../constants/zones";
import {
  formatRelativeTime,
  listSessions,
  loadSession as loadCachedSession,
  makeSessionId,
  rememberSession,
} from "../lib/sessionCache";
import type { StoredRunConfig } from "../lib/sessionCache";
import type {
  FeedbackBadge,
  Meal,
  RunHistoryRow,
  Session,
} from "../types/trace";

export type RunStatus = "idle" | "loading" | "ok" | "error" | "offline";

export type RunArgs = {
  meal: Meal;
  today: string;          // YYYY-MM-DD
  llmAuto: boolean;
  profileOverride: Record<string, unknown> | null;
  // Raw textarea content for "replay run" preservation (separate from the
  // parsed override sent to backend).
  profileOverrideRaw: string;
  // D-079: Live 模式 (默认 false). Live 走 /api/debug_recommend (永不写盘);
  // 非 Live 也走同端点 — 真实生产 trace 由 apps/web 用户视图写盘.
  live?: boolean;
};

export type UseSession = {
  // null = 还没有任何 trace 可显示 (trace_store 空 + 没跑过 Live).
  // 真实数据驱动: 不再有 mock 兜底.
  session: Session | null;
  status: RunStatus;
  error: string | null;
  history: RunHistoryRow[];
  activeSessionId: string | null;
  setActiveSessionId: (id: string) => void;
  runMain: (args: RunArgs) => Promise<Session | null>;
  // D-082: 对 active session 触发 refine, 然后 refetch trace 拿 round2.
  // 返 fresh session (含 round2) 或 null (失败).
  runRefine: (refineText: string) => Promise<Session | null>;
  refreshHistory: () => void;
  backendOnline: boolean;        // /api/debug/sessions 成功响应过 ⇒ true
  corruptCount: number;          // 后端 list 跳过的损坏 trace 数
  loadBackendSession: (sid: string) => Promise<Session | null>;
  setActiveSessionLive: (session: Session, area: string) => void;
};

function badgeFromBackend(
  fb: { accepted: boolean; accepted_rank: number | null;
        rating: number | null; stopped: boolean;
        feedback_submitted: boolean } | null | undefined,
): FeedbackBadge | null {
  if (!fb) return null;
  return {
    accepted: !!fb.accepted,
    accepted_rank: fb.accepted_rank,
    rating: fb.rating,
    stopped: !!fb.stopped,
    feedback_submitted: !!fb.feedback_submitted,
  };
}

function backendRowToHistory(item: {
  session_id: string;
  started_at: string;
  meal_type: string;
  zone: string;
  top1_summary: string;
  total_latency_ms: number;
  l3_status: string;
  feedback?: {
    accepted: boolean;
    accepted_rank: number | null;
    rating: number | null;
    stopped: boolean;
    feedback_submitted: boolean;
  } | null;
  refine_applied?: boolean;
  refine_round?: number | null;
  refine_user_input?: string | null;
  has_round2?: boolean;
}): RunHistoryRow {
  const status: "ok" | "fallback" | "warn" =
    item.l3_status === "fallback" ? "fallback" :
    item.l3_status === "config_error" ? "warn" :
    "ok";
  return {
    id: item.session_id,
    title: `${item.meal_type} · ${zoneLabel(item.zone)}`,
    time: formatRelativeTime(item.started_at),
    status,
    latency: item.total_latency_ms,
    meal: item.meal_type === "dinner" ? "dinner" : "lunch",
    area: zoneLabel(item.zone),
    feedback: badgeFromBackend(item.feedback ?? null),
    source: "backend",
    refine: item.refine_applied
      ? {
          applied: true,
          round: item.refine_round ?? null,
          user_input: item.refine_user_input ?? null,
          has_round2: !!item.has_round2,
        }
      : null,
  };
}

export function useSession(): UseSession {
  const cachedHistory = listSessions();
  const initialActive = cachedHistory[0]?.id ?? null;
  const initialSession = initialActive ? loadCachedSession(initialActive) : null;

  const [session, setSession] = useState<Session | null>(initialSession);
  const [status, setStatus] = useState<RunStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<RunHistoryRow[]>(cachedHistory);
  const [activeSessionId, setActiveSessionIdState] = useState<string | null>(initialActive);
  const [backendOnline, setBackendOnline] = useState<boolean>(false);
  const [corruptCount, setCorruptCount] = useState<number>(0);
  // session payload cache for backend rows (so 二次点击不再 fetch)
  const backendSessionCacheRef = useRef<Map<string, Session>>(new Map());
  // Race guard
  const runSeqRef = useRef(0);
  const sessionFetchSeqRef = useRef(0);
  const activeSessionIdRef = useRef<string | null>(initialActive);
  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  const refreshHistory = useCallback(() => {
    // Off-line fall-through: localStorage 缓存(真实跑过的 session, 不是 mock).
    if (backendOnline) return;
    setHistory(listSessions());
  }, [backendOnline]);

  // D-079: 进入页面 fetch 后端 list. 后端是单一可信源 (DESIGN §8.2).
  // 成功 → 用后端列表替换 history; 失败 → 保留 localStorage 离线缓存.
  const hydrateFromBackend = useCallback(async () => {
    try {
      const resp = await fetchSessions({ limit: 30 });
      const rows = resp.items.map(backendRowToHistory);
      setHistory(rows);
      setBackendOnline(true);
      setCorruptCount(resp.corrupt_count);
      // hydrate 完成回填 active sid 对应的 trace.
      //   - active sid 在 backend rows 里 → fetch 该 trace
      //   - active sid 不在 (localStorage 残留 / 旧 URL) → 切到 rows[0]
      //   - 没 active sid 且有 rows → 默认选最新一条
      // 总原则: backend online 时 backend 是单一可信源 (DESIGN §8.2),
      //         localStorage 不能盖过 backend.
      const inBackend = rows.find((r) => r.id === activeSessionIdRef.current);
      const activeRow = inBackend ?? rows[0];
      if (activeRow && !backendSessionCacheRef.current.has(activeRow.id)) {
        const seq = ++sessionFetchSeqRef.current;
        try {
          const trace = await fetchSession(activeRow.id);
          if (seq !== sessionFetchSeqRef.current) return;
          const s = traceToSession(trace);
          backendSessionCacheRef.current.set(activeRow.id, s);
          // 仅当用户当前 active 是这条 (或没显式选 / localStorage 残留)
          // 时才 setSession + 同步 sid.
          const cur = activeSessionIdRef.current;
          const shouldAdopt = cur === activeRow.id || cur == null || !inBackend;
          if (shouldAdopt) {
            setSession(s);
            if (cur !== activeRow.id) {
              activeSessionIdRef.current = activeRow.id;
              setActiveSessionIdState(activeRow.id);
            }
          }
        } catch {
          // hydrate 阶段失败不阻断列表渲染
        }
      }
    } catch (err) {
      setBackendOnline(false);
      const apiErr = err instanceof ApiError ? err : null;
      if (apiErr?.code === "NETWORK") {
        pushToast({
          kind: "warn",
          title: "后端不可达 · 用 localStorage 离线缓存",
          detail: "uv run python -m chisha.debug_server",
        });
      }
    }
  }, []);

  useEffect(() => {
    void hydrateFromBackend();
  }, [hydrateFromBackend]);

  const loadBackendSession = useCallback(async (sid: string): Promise<Session | null> => {
    const cached = backendSessionCacheRef.current.get(sid);
    if (cached) return cached;
    const seq = ++sessionFetchSeqRef.current;
    try {
      const trace = await fetchSession(sid);
      if (seq !== sessionFetchSeqRef.current) return null;
      const s = traceToSession(trace);
      backendSessionCacheRef.current.set(sid, s);
      return s;
    } catch (err) {
      if (seq !== sessionFetchSeqRef.current) return null;
      const apiErr = err instanceof ApiError ? err : null;
      pushToast({
        kind: "error",
        title: `trace 读取失败 ${apiErr?.status ?? ""}`.trim(),
        detail: apiErr?.message ?? String(err),
      });
      return null;
    }
  }, []);

  const setActiveSessionId = useCallback((id: string) => {
    activeSessionIdRef.current = id;
    ++sessionFetchSeqRef.current;
    setActiveSessionIdState(id);
    const row = history.find((h) => h.id === id);
    if (row?.source === "backend") {
      const cached = backendSessionCacheRef.current.get(id);
      if (cached) {
        setSession(cached);
        return;
      }
      void loadBackendSession(id).then((s) => {
        if (s) setSession(s);
      });
      return;
    }
    const localCached = loadCachedSession(id);
    if (localCached) setSession(localCached);
    else setSession(null);
  }, [history, loadBackendSession]);

  const setActiveSessionLive = useCallback((s: Session, _area: string) => {
    activeSessionIdRef.current = s.session_id;
    ++sessionFetchSeqRef.current;
    setSession(s);
    setActiveSessionIdState(s.session_id);
  }, []);

  const runMain = useCallback(async (args: RunArgs): Promise<Session | null> => {
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
      if (seq !== runSeqRef.current) return null; // stale
      const total = Math.round(performance.now() - t0);
      const fresh = backendToSession(raw, {
        sessionId: newId,
        startedAt,
        totalLatencyMs: total,
      });
      const area = zoneLabel(raw.config.zone);
      // D-079: 仅非 Live 模式落 localStorage. Live = 永不写盘, 不污染历史.
      if (!args.live) {
        const cfg: StoredRunConfig = {
          meal: args.meal,
          today: args.today,
          llmAuto: args.llmAuto,
          profileOverride: args.profileOverrideRaw,
        };
        rememberSession(fresh, area, cfg);
      }
      activeSessionIdRef.current = newId;
      ++sessionFetchSeqRef.current;
      setSession(fresh);
      setActiveSessionIdState(newId);
      if (backendOnline) {
        void hydrateFromBackend();
      } else if (!args.live) {
        refreshHistory();
      }
      setStatus("ok");
      return fresh;
    } catch (err) {
      if (seq !== runSeqRef.current) return null;
      const apiErr = err instanceof ApiError ? err : null;
      const msg = apiErr?.message ?? (err instanceof Error ? err.message : String(err));
      if (apiErr?.code === "NETWORK") {
        setStatus("offline");
        setError("后端不可达 — 请确认 debug_server 已起.");
        pushToast({
          kind: "warn",
          title: "后端 offline",
          detail: "uv run python -m chisha.debug_server",
        });
      } else {
        setStatus("error");
        setError(msg);
        pushToast({
          kind: "error",
          title: `推荐失败 ${apiErr?.status ?? ""}`.trim(),
          detail: msg.slice(0, 200),
        });
      }
      return null;
    }
  }, [backendOnline, hydrateFromBackend, refreshHistory]);

  const runRefine = useCallback(async (refineText: string): Promise<Session | null> => {
    const sid = activeSessionIdRef.current;
    if (!sid) {
      pushToast({ kind: "warn", title: "无 active session", detail: "先选一条 history 或跑一次 Live" });
      return null;
    }
    setStatus("loading");
    setError(null);
    try {
      await postRefine(sid, refineText);
      // refetch trace — 后端已经把 round2 写进同一文件.
      backendSessionCacheRef.current.delete(sid);
      const trace = await fetchSession(sid);
      const fresh = traceToSession(trace);
      backendSessionCacheRef.current.set(sid, fresh);
      setSession(fresh);
      setStatus("ok");
      pushToast({
        kind: "ok",
        title: `refine round 完成`,
        detail: fresh.round2
          ? `round2 ${fresh.round2.final.length} 候选 · ${fresh.round2.total_latency_ms}ms`
          : "(trace 已更新)",
      });
      return fresh;
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : null;
      const msg = apiErr?.message ?? (err instanceof Error ? err.message : String(err));
      setStatus("error");
      setError(msg);
      pushToast({
        kind: "error",
        title: `refine 失败 ${apiErr?.status ?? ""}`.trim(),
        detail: msg.slice(0, 200),
      });
      return null;
    }
  }, []);

  useEffect(() => {
    const onFocus = () => {
      if (backendOnline) {
        void hydrateFromBackend();
      } else {
        refreshHistory();
      }
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [backendOnline, hydrateFromBackend, refreshHistory]);

  return {
    session,
    status,
    error,
    history,
    activeSessionId,
    setActiveSessionId,
    runMain,
    runRefine,
    refreshHistory,
    backendOnline,
    corruptCount,
    loadBackendSession,
    setActiveSessionLive,
  };
}

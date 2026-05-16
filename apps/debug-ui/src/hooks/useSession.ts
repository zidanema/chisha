import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchSession,
  fetchSessions,
  postDebugRecommend,
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
import { MOCK_SESSION } from "../mocks/session";
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
  session: Session;
  status: RunStatus;
  error: string | null;
  history: RunHistoryRow[];
  activeSessionId: string;
  setActiveSessionId: (id: string) => void;
  // D-079 PR-3.1 (Codex NIT): runMain 返回 fresh session 让调用方派生 banner
  // 状态等, 避免 await 后直接读 liveSession state 拿 stale closure.
  runMain: (args: RunArgs) => Promise<Session | null>;
  refreshHistory: () => void;
  // D-079 新增:
  backendOnline: boolean;        // /api/debug/sessions 成功响应过 ⇒ true
  corruptCount: number;          // 后端 list 跳过的损坏 trace 数
  loadBackendSession: (sid: string) => Promise<Session | null>;
  setActiveSessionLive: (session: Session, area: string) => void;
};

const INITIAL_HISTORY_FALLBACK: RunHistoryRow[] = [
  { id: MOCK_SESSION.session_id, title: "lunch · 深圳湾 (mock)",
    time: "—", status: "ok", latency: MOCK_SESSION.total_latency_ms,
    source: "local" },
];

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
  };
}

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
  const [backendOnline, setBackendOnline] = useState<boolean>(false);
  const [corruptCount, setCorruptCount] = useState<number>(0);
  // session payload cache for backend rows (so 二次点击不再 fetch)
  const backendSessionCacheRef = useRef<Map<string, Session>>(new Map());
  // Race guard
  const runSeqRef = useRef(0);
  // Codex FIX-NOW #1: 异步 trace fetch race guard + active sid 反向追踪
  // (避免 hydrate 用 closure 里的旧 activeSessionId).
  const sessionFetchSeqRef = useRef(0);
  const activeSessionIdRef = useRef<string>(initialActive);
  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  const refreshHistory = useCallback(() => {
    // Replaced on mount by backend list. Off-line fall-through still uses cache.
    if (backendOnline) return;
    const fresh = listSessions();
    setHistory(fresh.length > 0 ? fresh : INITIAL_HISTORY_FALLBACK);
  }, [backendOnline]);

  // D-079: 进入页面 fetch 后端 list. 后端是单一可信源 (DESIGN §8.2).
  // 成功 → 用后端列表替换 history; 失败 → 保留 localStorage 离线缓存 + banner.
  // Codex review FIX-NOW #1: hydrate 成功后, 如果当前 activeSessionId 在 backend
  // rows 里, 主动 fetch 该 trace (URL ?sid=xxx 首次打开场景 / 后续 refresh 同理).
  const hydrateFromBackend = useCallback(async () => {
    try {
      const resp = await fetchSessions({ limit: 30 });
      const rows = resp.items.map(backendRowToHistory);
      setHistory(rows.length > 0 ? rows : INITIAL_HISTORY_FALLBACK);
      setBackendOnline(true);
      setCorruptCount(resp.corrupt_count);
      // hydrate 完成回填 active sid 对应的 trace (URL ?sid= 首次场景)
      const activeRow = rows.find((r) => r.id === activeSessionIdRef.current);
      if (activeRow && !backendSessionCacheRef.current.has(activeRow.id)) {
        const seq = ++sessionFetchSeqRef.current;
        try {
          const trace = await fetchSession(activeRow.id);
          if (seq !== sessionFetchSeqRef.current) return; // 被更新的 active 抢占
          const s = traceToSession(trace);
          backendSessionCacheRef.current.set(activeRow.id, s);
          // 仅当用户当前 active 还是这条时才 setSession (race guard)
          if (activeSessionIdRef.current === activeRow.id) setSession(s);
        } catch {
          // hydrate 阶段失败不阻断列表渲染, 用户点击行时再次走 loadBackendSession
        }
      }
    } catch (err) {
      // 离线/降级: 保留 localStorage 缓存作为 fallback (style §8.2)
      setBackendOnline(false);
      const apiErr = err instanceof ApiError ? err : null;
      if (apiErr?.code === "NETWORK") {
        pushToast({
          kind: "warn",
          title: "后端 :8765 不可达 · 用 localStorage 离线缓存",
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
      if (seq !== sessionFetchSeqRef.current) return null; // 被更新的 fetch 抢占
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
    // Codex round-2 ISSUE 修补: useEffect 同步 activeSessionIdRef 有一帧延迟,
    // 切 sid 时如果 hydrate 旧 fetch 此刻返回, race-guard 会用 stale ref 通过
    // 检查覆盖新 session. 这里同步写 ref + bump seq 强制旧 fetch 失效.
    activeSessionIdRef.current = id;
    ++sessionFetchSeqRef.current;
    setActiveSessionIdState(id);
    if (id === MOCK_SESSION.session_id) {
      setSession(MOCK_SESSION);
      return;
    }
    // backend row → 异步 fetch (本地 cache 命中则同步)
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
  }, [history, loadBackendSession]);

  const setActiveSessionLive = useCallback((s: Session, _area: string) => {
    // 同 setActiveSessionId — 同步写 ref + bump seq 防 race.
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
      // 同步更新 ref + bump seq, 让 hydrate 旧 fetch 失效 (Codex round-2 修补)
      activeSessionIdRef.current = newId;
      ++sessionFetchSeqRef.current;
      setSession(fresh);
      setActiveSessionIdState(newId);
      // 后端在线 → 重新拉 list 拿最新 trace; 否则用 localStorage.
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
        setError("后端 :8765 不可达 — 显示 mock 数据。请确认 debug_server 已起。");
        pushToast({
          kind: "warn",
          title: "后端 offline · 显示 mock",
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

  // Refresh history on window focus.
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
    refreshHistory,
    backendOnline,
    corruptCount,
    loadBackendSession,
    setActiveSessionLive,
  };
}

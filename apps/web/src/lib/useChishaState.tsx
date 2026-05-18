// App-level shared state. The prototype kept home / unfed / toast in App so that
// nav-ing to /profile and back preserved the active session. We keep the same
// shape via context — pages stay unmounted-friendly.

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { Candidate, MealType, Mood, RecommendResponse, SkipReason, StatusBarPayload, UnfedSession } from "./types";
import type { RefineHistoryEntry } from "@/components/RefineCrumb";
import { api, isMock } from "./api";
import { sandboxApi, type SandboxState } from "./sandbox";

interface SessionState {
  session_id: string;
  candidates: Candidate[];
  round: number;
  history: RecommendResponse[];
}

export interface HomeState {
  meal: MealType;
  mood: Mood;
  session: SessionState | null;
  loading: boolean;
  refineHistory: RefineHistoryEntry[];
  detailCandidate: Candidate | null;
  pickedRank: number | null;
  skipped: boolean;
  skipReason: SkipReason;
  // T-P1b-01: 后端 /api/recommend & /api/refine 返回的状态条 payload.
  // null = 尚未拉取过 (initial 或 server 旧版本不带 status_bar).
  statusBar: StatusBarPayload | null;
}

interface ToastState {
  msg: string;
  tone: "default" | "good";
}

interface ChishaCtx {
  home: HomeState;
  setHome: (patch: Partial<HomeState>) => void;
  // V1.1: inbox-style list. NavBar 角标 + banner 都从这里读。
  inbox: UnfedSession[];
  refreshInbox: () => Promise<void>;
  toast: ToastState;
  showToast: (msg: string, tone?: ToastState["tone"]) => void;
  // D-077 PR-1d fix: sandbox state 提升到 context, ProfilePage init/disable 后
  // 能通知顶层 SandboxBar 重渲染. 原来 App.tsx Shell 私有 state, ProfilePage 改
  // 不到 → 启用沙盒后 SandboxBar 不出现 (要硬刷整页).
  sandboxState: SandboxState;
  refreshSandbox: () => Promise<void>;
}

const Ctx = createContext<ChishaCtx | null>(null);

function detectAutoMeal(): MealType {
  const h = new Date().getHours();
  return h >= 11 && h < 15 ? "lunch" : "dinner";
}

export function ChishaProvider({ children }: { children: React.ReactNode }) {
  const [home, setHomeState] = useState<HomeState>({
    meal: detectAutoMeal(),
    mood: "neutral",
    session: null,
    loading: false,
    refineHistory: [],
    detailCandidate: null,
    pickedRank: null,
    skipped: false,
    skipReason: null,
    statusBar: null,
  });
  const setHome = useCallback(
    (patch: Partial<HomeState>) => setHomeState((p) => ({ ...p, ...patch })),
    []
  );

  const [inbox, setInbox] = useState<UnfedSession[]>([]);
  const refreshInbox = useCallback(async () => {
    const r = await api.inbox({ include_snoozed: true });
    setInbox(r.items);
  }, []);
  useEffect(() => {
    void refreshInbox();
  }, [refreshInbox]);

  const [sandboxState, setSandboxState] = useState<SandboxState>({ enabled: false });
  const refreshSandbox = useCallback(async () => {
    if (isMock) return;
    try {
      const s = await sandboxApi.state();
      setSandboxState(s);
    } catch {
      setSandboxState({ enabled: false });
    }
  }, []);
  useEffect(() => {
    void refreshSandbox();
  }, [refreshSandbox]);

  const [toast, setToast] = useState<ToastState>({ msg: "", tone: "default" });
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((msg: string, tone: ToastState["tone"] = "default") => {
    setToast({ msg, tone });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(
      () => setToast({ msg: "", tone: "default" }),
      2400
    );
  }, []);

  return (
    <Ctx.Provider value={{ home, setHome, inbox, refreshInbox, toast, showToast, sandboxState, refreshSandbox }}>
      {children}
    </Ctx.Provider>
  );
}

export function useChisha(): ChishaCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useChisha must be inside <ChishaProvider>");
  return c;
}

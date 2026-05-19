// S-03: sandbox-lab 交互状态机 (前端 mock).
// 所有数据走本地 React state, 不接后端. S-08 联调时替换内部 state 操作为 fetch.
//
// State model (v2 修订 A): per-session map {sid → SessionInternalState}.
// 切 session 时不 reset 字段, 而是切 map key. branch 写新 sid + 老 sid 不动.

import { useCallback, useMemo, useState } from "react";
import {
  ACTIVE_RULES,
  BLACKLIST,
  CURRENT_IDX,
  CURRENT_RECS,
  FATIGUE,
  HISTORY,
  KEYWORDS,
  LAST_DECISION,
  RECENT,
  SESSIONS,
  TASTE,
  TOTAL_MEALS,
  buildDecisionMock,
  buildSkipDecisionMock,
  expandHistoryForDoneSession,
  freshRecsForMeal,
} from "../mocks/sbxMocks";
import type {
  BannerEntry,
  Clock,
  ConfirmKind,
  Decision,
  Meal,
  Rec,
  SessionMeta,
} from "../types/sandbox";


interface SessionInternalState {
  history: Meal[];
  currentMealIdx: number;
  currentRecs: Rec[];
  lastDecision: Decision | null;
}


function initialSessionStates(): Map<string, SessionInternalState> {
  const m = new Map<string, SessionInternalState>();
  for (const sess of SESSIONS) {
    const total = sess.days * 2;
    if (sess.status === "done") {
      m.set(sess.id, {
        history: expandHistoryForDoneSession(total),
        currentMealIdx: total,
        currentRecs: [],
        lastDecision: null,
      });
    } else {
      // running session — mock HISTORY (前 4) + CURRENT_RECS + LAST_DECISION
      m.set(sess.id, {
        history: [...HISTORY],
        currentMealIdx: CURRENT_IDX,
        currentRecs: CURRENT_RECS,
        lastDecision: LAST_DECISION,
      });
    }
  }
  return m;
}


export interface UseSandboxOptions {
  initialState?: {
    modal?: "summary" | "confirm-rollback" | "confirm-branch" | "refine";
    reviewIdx?: number;
  };
}


export interface UseSandboxResult {
  // store
  sessions: SessionMeta[];
  activeSessionId: string;
  clock: Clock;
  currentMealIdx: number;
  totalMeals: number;
  history: Meal[];
  currentRecs: Rec[];
  lastDecision: Decision | null;
  // S-02 视图所需附加静态 mock (不进 session map, 切 session 共用)
  taste: typeof TASTE;
  keywords: typeof KEYWORDS;
  activeRules: typeof ACTIVE_RULES;
  blacklist: typeof BLACKLIST;
  recent: typeof RECENT;
  fatigue: typeof FATIGUE;
  // 回顾模式
  selectedCellIdx: number | null;
  isInReviewMode: boolean;
  reviewMeal: Meal | null;
  // banners
  transientBanners: BannerEntry[];
  derivedBanners: BannerEntry[];
  banners: BannerEntry[];
  // modals
  summaryOpen: boolean;
  confirmKind: ConfirmKind | null;
  confirmMeal: Meal | null;
  refineModalOpen: boolean;
  // done state
  isDone: boolean;

  // actions
  setActiveSessionId(id: string): void;
  handleEat(rec: Rec): void;
  handleSkip(): void;
  handleSwap(): void;
  handleRefine(text: string): void;
  selectCell(idx: number | null): void;
  handleRollback(idx: number): void;
  handleBranch(fromIdx: number, name: string): void;
  openSummary(): void;
  closeSummary(): void;
  openConfirm(kind: ConfirmKind): void;
  closeConfirm(): void;
  openRefineModal(): void;
  closeRefineModal(): void;
  dismissTransient(id: string): void;
}


export function useSandbox(opts: UseSandboxOptions = {}): UseSandboxResult {
  const [sessions, setSessions] = useState<SessionMeta[]>([...SESSIONS]);
  const [activeSessionId, setActiveSessionId] = useState<string>(SESSIONS[0].id);
  const [sessionStates, setSessionStates] = useState<Map<string, SessionInternalState>>(
    initialSessionStates,
  );
  const [selectedCellIdx, setSelectedCellIdx] = useState<number | null>(
    opts.initialState?.reviewIdx ?? null,
  );
  const [transientBanners, setTransientBanners] = useState<BannerEntry[]>([]);

  const initialModal = opts.initialState?.modal;
  const [summaryOpen, setSummaryOpen] = useState<boolean>(initialModal === "summary");
  const [confirmKind, setConfirmKind] = useState<ConfirmKind | null>(
    initialModal === "confirm-rollback" ? "rollback"
      : initialModal === "confirm-branch" ? "branch"
        : null,
  );
  const [refineModalOpen, setRefineModalOpen] = useState<boolean>(initialModal === "refine");

  // 活动 session 派生
  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? sessions[0];
  const activeState = sessionStates.get(activeSession.id) ?? sessionStates.get(SESSIONS[0].id)!;
  const totalMeals = activeSession.days * 2;
  const currentMealIdx = activeState.currentMealIdx;
  const history = activeState.history;
  const currentRecs = activeState.currentRecs;
  const lastDecision = activeState.lastDecision;
  const isDone = currentMealIdx >= totalMeals;

  const clock: Clock = useMemo(() => {
    // done 状态用 totalMeals-1 派生 day/slot 展示, 但 idx 保留 currentMealIdx
    const displayIdx = isDone ? totalMeals - 1 : currentMealIdx;
    return {
      idx: currentMealIdx,
      day: Math.floor(displayIdx / 2) + 1,
      slot: displayIdx % 2 === 0 ? "午" : "晚",
      total: totalMeals,
    };
  }, [currentMealIdx, totalMeals, isDone]);

  // 回顾模式判定: selectedCellIdx 已设且不等于 current
  const isInReviewMode = selectedCellIdx !== null && selectedCellIdx !== currentMealIdx;
  const reviewMeal: Meal | null = isInReviewMode
    ? history.find((h) => h.idx === selectedCellIdx) ?? null
    : null;
  const confirmMeal: Meal | null = selectedCellIdx !== null
    ? history.find((h) => h.idx === selectedCellIdx) ?? null
    : null;

  // ── 派生 banners (v2 修订 B: 全 dismissable=false, 不进 dismiss filter)
  const derivedBanners: BannerEntry[] = useMemo(() => {
    const out: BannerEntry[] = [];
    if (isInReviewMode && reviewMeal) {
      out.push({
        id: "review_mode",
        level: "review",
        title: `回顾模式 · D${reviewMeal.day}${reviewMeal.slot}`,
        detail: "Esc 退出 · 此为只读快照",
        dismissable: false,
      });
    }
    if (isDone && !isInReviewMode) {
      out.push({
        id: `done_${activeSessionId}`,
        level: "info",
        title: "Session 完成 ✓",
        detail: `${totalMeals}/${totalMeals} 顿全部完成, 可分支或回滚`,
        dismissable: false,
      });
    }
    if (!isInReviewMode && !isDone) {
      const conflictRec = currentRecs.find((r) => r.conflict);
      if (conflictRec && conflictRec.conflict) {
        out.push({
          id: "refine_conflict",
          level: "warn",
          title: "Refine 冲突",
          detail: `推荐 #${conflictRec.rank} ${conflictRec.name} 违反 active refine '${conflictRec.conflict.rule}'`,
          dismissable: false,
        });
      }
    }
    return out;
  }, [isInReviewMode, reviewMeal, isDone, currentRecs, activeSessionId, totalMeals]);

  const banners: BannerEntry[] = useMemo(
    () => [...derivedBanners, ...transientBanners],
    [derivedBanners, transientBanners],
  );

  // ── session state mutate helper
  const updateSessionState = useCallback(
    (sid: string, mut: (prev: SessionInternalState) => SessionInternalState) => {
      setSessionStates((prev) => {
        const next = new Map(prev);
        const cur = prev.get(sid);
        if (cur) next.set(sid, mut(cur));
        return next;
      });
    },
    [],
  );

  // ── actions
  const handleEat = useCallback(
    (rec: Rec) => {
      if (isDone) return;
      const sid = activeSessionId;
      const oldIdx = currentMealIdx;
      const oldClock: Clock = {
        idx: oldIdx,
        day: Math.floor(oldIdx / 2) + 1,
        slot: oldIdx % 2 === 0 ? "午" : "晚",
        total: totalMeals,
      };
      const newIdx = oldIdx + 1;
      updateSessionState(sid, (prev) => ({
        history: [
          ...prev.history,
          {
            idx: oldIdx,
            day: oldClock.day,
            slot: oldClock.slot,
            state: "eat",
            dish: rec.name,
            score: rec.l3,
            flags: rec.conflict ? ["conflict"] : [],
            altScores: prev.currentRecs.map((r) => ({
              name: r.name,
              score: r.l3,
              picked: r.rank === rec.rank,
            })),
          },
        ],
        currentMealIdx: newIdx,
        currentRecs: newIdx >= totalMeals ? [] : freshRecsForMeal(newIdx, sid),
        lastDecision: buildDecisionMock(rec, oldClock),
      }));
      setTransientBanners([]);
      setSelectedCellIdx(null);
    },
    [isDone, activeSessionId, currentMealIdx, totalMeals, updateSessionState],
  );

  const handleSkip = useCallback(() => {
    if (isDone) return;
    const sid = activeSessionId;
    const oldIdx = currentMealIdx;
    const oldClock: Clock = {
      idx: oldIdx,
      day: Math.floor(oldIdx / 2) + 1,
      slot: oldIdx % 2 === 0 ? "午" : "晚",
      total: totalMeals,
    };
    const newIdx = oldIdx + 1;
    updateSessionState(sid, (prev) => ({
      history: [
        ...prev.history,
        {
          idx: oldIdx,
          day: oldClock.day,
          slot: oldClock.slot,
          state: "skip",
          dish: "—",
          score: null,
          flags: [],
          altScores: [],
        },
      ],
      currentMealIdx: newIdx,
      currentRecs: newIdx >= totalMeals ? [] : freshRecsForMeal(newIdx, sid),
      lastDecision: buildSkipDecisionMock(oldClock),
    }));
    setTransientBanners([]);
    setSelectedCellIdx(null);
  }, [isDone, activeSessionId, currentMealIdx, totalMeals, updateSessionState]);

  const handleSwap = useCallback(() => {
    if (isDone) return;
    const sid = activeSessionId;
    updateSessionState(sid, (prev) => ({
      ...prev,
      currentRecs: freshRecsForMeal(prev.currentMealIdx, sid),
    }));
    setTransientBanners((prev) => [
      ...prev.filter((b) => !b.id.startsWith("swap_")),
      {
        id: `swap_${Date.now()}`,
        level: "info",
        title: "已换一组",
        detail: "新拉了 5 条 (mock)",
        dismissable: true,
      },
    ]);
  }, [isDone, activeSessionId, updateSessionState]);

  const handleRefine = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      if (isDone) return;
      const sid = activeSessionId;
      const intentText = trimmed.slice(0, 8);
      updateSessionState(sid, (prev) => ({
        ...prev,
        currentRecs: freshRecsForMeal(prev.currentMealIdx, sid).map((r) => ({
          ...r,
          intent: intentText,
        })),
      }));
      setTransientBanners((prev) => [
        ...prev.filter((b) => !b.id.startsWith("refine_")),
        {
          id: `refine_${Date.now()}`,
          level: "info",
          title: "Refine 已应用",
          detail: `本轮内 "${trimmed}"; 下顿自动清`,
          dismissable: true,
        },
      ]);
    },
    [isDone, activeSessionId, updateSessionState],
  );

  const selectCell = useCallback(
    (idx: number | null) => {
      if (idx === null) {
        setSelectedCellIdx(null);
        return;
      }
      if (idx === currentMealIdx) {
        setSelectedCellIdx(null);   // 当前 cell 不进 review
        return;
      }
      setSelectedCellIdx(idx);
    },
    [currentMealIdx],
  );

  const handleRollback = useCallback(
    (targetIdx: number) => {
      const sid = activeSessionId;
      updateSessionState(sid, (prev) => ({
        history: prev.history.filter((h) => h.idx < targetIdx),
        currentMealIdx: targetIdx,
        currentRecs: targetIdx >= totalMeals ? [] : freshRecsForMeal(targetIdx, sid),
        lastDecision: null,
      }));
      setSelectedCellIdx(null);
      setTransientBanners((prev) => [
        ...prev,
        {
          id: `rollback_${Date.now()}`,
          level: "warn",
          title: "已回滚",
          detail: `session 已截到 idx=${targetIdx} 之前`,
          dismissable: true,
        },
      ]);
    },
    [activeSessionId, totalMeals, updateSessionState],
  );

  const handleBranch = useCallback(
    (fromIdx: number, name: string) => {
      const oldSid = activeSessionId;
      const newSid = `${oldSid}_branch_${Math.random().toString(36).slice(2, 8)}`;
      const oldSess = sessions.find((s) => s.id === oldSid) ?? sessions[0];
      const oldState = sessionStates.get(oldSid);
      if (!oldState) return;
      const branchHistory = oldState.history.filter((h) => h.idx < fromIdx);
      const newSession: SessionMeta = {
        id: newSid,
        name: `branch · ${name || "未命名"}`,
        days: oldSess.days,
        seed: oldSess.seed,
        profile: oldSess.profile,
        origin: oldSess.origin,
        status: "running",
        lastUsed: "刚刚",
      };
      const newState: SessionInternalState = {
        history: branchHistory,
        currentMealIdx: fromIdx,
        currentRecs: fromIdx >= oldSess.days * 2 ? [] : freshRecsForMeal(fromIdx, newSid),
        lastDecision: null,
      };
      setSessions((prev) => [...prev, newSession]);
      setSessionStates((prev) => {
        const next = new Map(prev);
        next.set(newSid, newState);
        return next;
      });
      setActiveSessionId(newSid);
      setSelectedCellIdx(null);
      setTransientBanners((prev) => [
        ...prev,
        {
          id: `branch_${Date.now()}`,
          level: "info",
          title: "已分支",
          detail: `从 idx=${fromIdx} 派生新 session "${name || "未命名"}"`,
          dismissable: true,
        },
      ]);
    },
    [activeSessionId, sessions, sessionStates],
  );

  const openSummary = useCallback(() => setSummaryOpen(true), []);
  const closeSummary = useCallback(() => setSummaryOpen(false), []);
  const openConfirm = useCallback((kind: ConfirmKind) => setConfirmKind(kind), []);
  const closeConfirm = useCallback(() => setConfirmKind(null), []);
  const openRefineModal = useCallback(() => setRefineModalOpen(true), []);
  const closeRefineModal = useCallback(() => setRefineModalOpen(false), []);
  const dismissTransient = useCallback((id: string) => {
    setTransientBanners((prev) => prev.filter((b) => b.id !== id));
  }, []);

  return {
    sessions,
    activeSessionId,
    clock,
    currentMealIdx,
    totalMeals,
    history,
    currentRecs,
    lastDecision,
    taste: TASTE,
    keywords: KEYWORDS,
    activeRules: ACTIVE_RULES,
    blacklist: BLACKLIST,
    recent: RECENT,
    fatigue: FATIGUE,
    selectedCellIdx,
    isInReviewMode,
    reviewMeal,
    transientBanners,
    derivedBanners,
    banners,
    summaryOpen,
    confirmKind,
    confirmMeal,
    refineModalOpen,
    isDone,
    setActiveSessionId,
    handleEat,
    handleSkip,
    handleSwap,
    handleRefine,
    selectCell,
    handleRollback,
    handleBranch,
    openSummary,
    closeSummary,
    openConfirm,
    closeConfirm,
    openRefineModal,
    closeRefineModal,
    dismissTransient,
  };
}

// Keep TOTAL_MEALS export accessible (was inlined; helps any future caller).
export const __DEFAULT_TOTAL_MEALS__ = TOTAL_MEALS;

// S-03: sandbox-lab 交互状态机 (前端 mock).
// S-08: backend ping → online 走 fetch (mock_recommend=1 by default), offline 保留 S-03 mock.
//
// State model (v2 修订 A): per-session map {sid → SessionInternalState}.
// 切 session 时不 reset 字段, 而是切 map key. branch 写新 sid + 老 sid 不动.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  backendFullSnapshotToStore,
  backendJobToStatus,
  backendMetaToSessionMeta,
  backendRecToFrontend,
} from "../api/adapter";
import {
  createSession,
  getFullSnapshot,
  getJob,
  listSessions,
  pingBackend,
  postBranch,
  postEat,
  postRecs,
  postRefine,
  postRollback,
  postSkip,
  postSwap,
} from "../api/client";
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
  totalMeals?: number;  // S-08: backend snapshot 带 totalMeals, 覆盖 SESSIONS.days*2
}


type PollingState =
  | { action: "eat"; jobId: string; sid: string; startedAt: number }
  | null;


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
  // S-08: 联调相关
  backendOnline: boolean | null;  // null = pinging
  polling: PollingState;
  apiError: string | null;

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
  dismissApiError(): void;
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

  // S-08: backend wiring state
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [polling, setPolling] = useState<PollingState>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  // S-08 P2 fix: 防 skip / swap / refine 期间 double-click 重复 POST (eat 已经
  // 通过 polling state 自带防重, 但 skip/swap/refine 是同步 fetch 期间没有锁).
  const inFlightRef = useRef<boolean>(false);
  const activeSidRef = useRef<string>(activeSessionId);
  useEffect(() => { activeSidRef.current = activeSessionId; }, [activeSessionId]);

  // 活动 session 派生
  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? sessions[0];
  const activeState = sessionStates.get(activeSession.id) ?? sessionStates.get(SESSIONS[0].id)!;
  const totalMeals = activeState.totalMeals ?? activeSession.days * 2;
  const currentMealIdx = activeState.currentMealIdx;
  const history = activeState.history;
  const currentRecs = activeState.currentRecs;
  const lastDecision = activeState.lastDecision;
  const isDone = currentMealIdx >= totalMeals;

  const clock: Clock = useMemo(() => {
    const displayIdx = isDone ? totalMeals - 1 : currentMealIdx;
    return {
      idx: currentMealIdx,
      day: Math.floor(displayIdx / 2) + 1,
      slot: displayIdx % 2 === 0 ? "午" : "晚",
      total: totalMeals,
    };
  }, [currentMealIdx, totalMeals, isDone]);

  const isInReviewMode = selectedCellIdx !== null && selectedCellIdx !== currentMealIdx;
  const reviewMeal: Meal | null = isInReviewMode
    ? history.find((h) => h.idx === selectedCellIdx) ?? null
    : null;
  const confirmMeal: Meal | null = selectedCellIdx !== null
    ? history.find((h) => h.idx === selectedCellIdx) ?? null
    : null;

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

  // ── S-08 backend helpers ──

  // Apply a backend FullSnapshot into session map + meta list. If currentRecs is
  // empty and session not done, fetch /recs to populate (post-advance/rollback/branch/init).
  const applySnapshot = useCallback(
    async (sid: string, snapPiece: ReturnType<typeof backendFullSnapshotToStore>): Promise<void> => {
      let recs = snapPiece.currentRecs;
      const cur = snapPiece.clock.idx;
      const total = snapPiece.clock.total;
      const sessIsDone = cur >= total;
      if (recs.length === 0 && !sessIsDone) {
        try {
          const recsResp = await postRecs(sid);
          recs = (recsResp.currentRecs || []).map(backendRecToFrontend);
        } catch (e) {
          // Soft fail: 让用户能看到空状态而不是 crash
          // eslint-disable-next-line no-console
          console.warn("postRecs after advance failed:", e);
        }
      }
      setSessions((prev) => {
        const idx = prev.findIndex((s) => s.id === sid);
        if (idx === -1) return [...prev, snapPiece.meta];
        const next = [...prev];
        next[idx] = snapPiece.meta;
        return next;
      });
      setSessionStates((prev) => {
        const next = new Map(prev);
        next.set(sid, {
          history: snapPiece.history,
          currentMealIdx: snapPiece.clock.idx,
          currentRecs: recs,
          lastDecision: snapPiece.lastDecision,
          totalMeals: snapPiece.clock.total,
        });
        return next;
      });
    },
    [],
  );

  // boot: ping + listSessions + ensure non-default active session
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const online = await pingBackend();
      if (cancelled) return;
      if (!online) {
        setBackendOnline(false);
        return;
      }
      // P2 fix (iter 5): 不要先 setBackendOnline(true) 再 await bootstrap.
      // bootstrap 失败 (例如 backend 缺 sandbox init) 时, 会留 backendOnline=true
      // + mock sessions, 后续 action 走 online 分支 → mock sid → 4xx 重复. 改成
      // bootstrap 成功后才标 online.
      try {
        const listResp = await listSessions();
        if (cancelled) return;
        // Find first non-default session w/ state (rollback/branch reject _default)
        let activeSid = listResp.sessions
          .filter((s) => !s.is_default && s.has_state)
          .map((s) => s.sid)[0];
        if (!activeSid) {
          // auto-create e2e session
          const newMeta = await createSession("s08_e2e", 7).catch((e) => {
            if (e?.status === 409) {
              // already exists — list again
              return null;
            }
            throw e;
          });
          if (newMeta) {
            activeSid = newMeta.sid;
          } else {
            activeSid = "s08_e2e";
          }
          if (cancelled) return;
        }
        // Build session list from backend (replace SESSIONS mock entries)
        const candidateSids = listResp.sessions
          .filter((s) => !s.is_default)
          .map((s) => s.sid);
        const allSids = candidateSids.includes(activeSid)
          ? candidateSids
          : [activeSid, ...candidateSids];
        const snapshots = await Promise.all(
          allSids.map((sid) =>
            getFullSnapshot(sid).then(
              (snap) => ({ sid, snap }),
              (err) => ({ sid, err }),
            ),
          ),
        );
        if (cancelled) return;
        const builtSessions: SessionMeta[] = [];
        const builtStates = new Map<string, SessionInternalState>();
        for (const item of snapshots) {
          if ("err" in item) continue;
          const piece = backendFullSnapshotToStore(item.snap);
          builtSessions.push(piece.meta);
          builtStates.set(item.sid, {
            history: piece.history,
            currentMealIdx: piece.clock.idx,
            currentRecs: piece.currentRecs,
            lastDecision: piece.lastDecision,
            totalMeals: piece.clock.total,
          });
        }
        if (builtSessions.length > 0) {
          setSessions(builtSessions);
          setSessionStates(builtStates);
          setActiveSessionId(activeSid);
          // Ensure recs on the chosen active sid
          const snapForActive = snapshots.find((s) => "snap" in s && s.sid === activeSid);
          if (snapForActive && "snap" in snapForActive) {
            await applySnapshot(activeSid, backendFullSnapshotToStore(snapForActive.snap));
          }
          // bootstrap 成功 — 此时才标 online
          if (!cancelled) setBackendOnline(true);
        } else {
          // 拿不到任何 session snapshot, 退回 mock 模式
          setBackendOnline(false);
        }
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn("backend boot failed:", e);
        setApiError(e instanceof Error ? e.message : String(e));
        setBackendOnline(false);  // P2 fix iter 5: bootstrap 失败 → 走 mock
      }
    })();
    return () => { cancelled = true; };
  }, [applySnapshot]);

  // polling effect for eat job
  useEffect(() => {
    if (!polling) return;
    let stopped = false;
    const tick = async () => {
      try {
        const info = await getJob(polling.sid, polling.jobId);
        if (stopped) return;
        // P2 fix (iter 3): 不 early-return 切 session; 仍把 done snapshot 应用到
        // polling.sid 的 store. applySnapshot 按 sid 写 sessionStates, 切 session
        // 不影响. UI 当前不在该 sid 也无所谓 — 切回时数据已正确.
        const st = backendJobToStatus(info);
        if (st === "done") {
          // P1 fix (iter 2): 先 fetch + applySnapshot, 最后才 setPolling(null).
          // 之前先 setPolling(null) 会触发 effect cleanup (stopped=true), 后续 await 被丢弃.
          const snap = await getFullSnapshot(polling.sid);
          if (stopped) return;
          await applySnapshot(polling.sid, backendFullSnapshotToStore(snap));
          if (stopped) return;
          setPolling(null);
        } else if (st === "failed" || st === "cancelled") {
          setPolling(null);
          setApiError(
            st === "cancelled"
              ? "回滚已取消进行中的 eat 任务"
              : `eat job failed: ${info.error ?? "unknown"}`,
          );
        }
      } catch (e) {
        if (stopped) return;
        setPolling(null);
        setApiError(`poll job failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    };
    // first tick immediately, then interval
    void tick();
    const iv = window.setInterval(tick, 1500);
    return () => {
      stopped = true;
      window.clearInterval(iv);
    };
  }, [polling, applySnapshot]);

  // ── actions
  const handleEat = useCallback(
    (rec: Rec) => {
      if (isDone) return;
      const sid = activeSessionId;

      if (backendOnline) {
        if (inFlightRef.current || polling) return;   // P2 fix: 防重复 click
        inFlightRef.current = true;
        // online path: POST /eat + start polling
        (async () => {
          try {
            const resp = await postEat(sid, rec.rank);
            setPolling({
              action: "eat",
              jobId: resp.job_id,
              sid,
              startedAt: Date.now(),
            });
            setSelectedCellIdx(null);
          } catch (e) {
            setApiError(`eat failed: ${e instanceof Error ? e.message : String(e)}`);
          } finally {
            inFlightRef.current = false;
          }
        })();
        return;
      }

      // offline mock path (S-03 行为)
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
    [isDone, activeSessionId, backendOnline, currentMealIdx, totalMeals, updateSessionState],
  );

  const handleSkip = useCallback(() => {
    if (isDone) return;
    const sid = activeSessionId;

    if (backendOnline) {
      if (inFlightRef.current) return;   // P2 fix: 防重复 click
      inFlightRef.current = true;
      (async () => {
        try {
          await postSkip(sid);
          const snap = await getFullSnapshot(sid);
          await applySnapshot(sid, backendFullSnapshotToStore(snap));
          setTransientBanners([]);
          setSelectedCellIdx(null);
        } catch (e) {
          setApiError(`skip failed: ${e instanceof Error ? e.message : String(e)}`);
        } finally {
          inFlightRef.current = false;
        }
      })();
      return;
    }

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
  }, [isDone, activeSessionId, backendOnline, currentMealIdx, totalMeals, updateSessionState, applySnapshot]);

  const handleSwap = useCallback(() => {
    if (isDone) return;
    const sid = activeSessionId;

    if (backendOnline) {
      if (inFlightRef.current) return;   // P2 fix: 防重复 click
      inFlightRef.current = true;
      // P2 fix: exclude 当前可见 5 条的 backend id (mock_recs 真按 id 过滤)
      const excludeIds = currentRecs
        .map((r) => (r as Rec & { _backendId?: string })._backendId)
        .filter((id): id is string => typeof id === "string" && id.length > 0);
      (async () => {
        try {
          const resp = await postSwap(sid, excludeIds);
          const recs = (resp.currentRecs || []).map(backendRecToFrontend);
          updateSessionState(sid, (prev) => ({
            ...prev,
            currentRecs: recs,
          }));
          setTransientBanners((prev) => [
            ...prev.filter((b) => !b.id.startsWith("swap_")),
            {
              id: `swap_${Date.now()}`,
              level: "info",
              title: "已换一组",
              detail: `新拉了 ${recs.length} 条`,
              dismissable: true,
            },
          ]);
        } catch (e) {
          setApiError(`swap failed: ${e instanceof Error ? e.message : String(e)}`);
        } finally {
          inFlightRef.current = false;
        }
      })();
      return;
    }

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
  }, [isDone, activeSessionId, backendOnline, currentRecs, updateSessionState]);

  const handleRefine = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      if (isDone) return;
      const sid = activeSessionId;

      if (backendOnline) {
        if (inFlightRef.current) return;   // P2 fix: 防重复 click
        inFlightRef.current = true;
        (async () => {
          try {
            const resp = await postRefine(sid, trimmed);
            const recs = (resp.currentRecs || []).map(backendRecToFrontend);
            updateSessionState(sid, (prev) => ({
              ...prev,
              currentRecs: recs,
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
          } catch (e) {
            setApiError(`refine failed: ${e instanceof Error ? e.message : String(e)}`);
          } finally {
            inFlightRef.current = false;
          }
        })();
        return;
      }

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
    [isDone, activeSessionId, backendOnline, updateSessionState],
  );

  const selectCell = useCallback(
    (idx: number | null) => {
      if (idx === null) {
        setSelectedCellIdx(null);
        return;
      }
      if (idx === currentMealIdx) {
        setSelectedCellIdx(null);
        return;
      }
      setSelectedCellIdx(idx);
    },
    [currentMealIdx],
  );

  const handleRollback = useCallback(
    (targetIdx: number) => {
      const sid = activeSessionId;

      if (backendOnline) {
        // P2 fix (iter 6): 不要在 await 前清 polling. 否则 rollback 失败 (例如
        // 409 L1 lock 冲突) 之后 polling 已被清掉, BG 仍可能完成 advance, 但
        // 前端没人再 getJob → snapshot 失同步. 先发请求, 成功后才清 polling.
        const savedPolling = polling;
        (async () => {
          try {
            const snap = await postRollback(sid, targetIdx);
            // rollback 成功 — backend 已 cancel_by_rollback 该 job, 清前端 polling
            setPolling(null);
            await applySnapshot(sid, backendFullSnapshotToStore(snap));
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
          } catch (e) {
            // rollback 失败 — 保留原 polling 让 useEffect 继续追 job
            void savedPolling;  // explicit: 没 setPolling(null) 即保留
            setApiError(`rollback failed: ${e instanceof Error ? e.message : String(e)}`);
          }
        })();
        return;
      }

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
    [activeSessionId, backendOnline, totalMeals, updateSessionState, applySnapshot],
  );

  const handleBranch = useCallback(
    (fromIdx: number, name: string) => {
      const oldSid = activeSessionId;

      if (backendOnline) {
        // P2 fix (iter 7): 不 pre-clear polling. branch 失败 (op lock 409 etc.)
        // 后 polling 不该丢. 切别的 session 也不该把 polling 拿走 — polling.sid
        // 守门已在 effect 内. branch 成功后, 切 active 到 new sid 自然让 polling
        // 仍指 oldSid (eat 在 oldSid), 不冲突.
        // P2 fix (iter 2): backend branch 要 from_meal_idx < currentMealIdx.
        // TopBar "新 session" 入口传 currentMealIdx → 必须夹回 [0, cur-1] 范围.
        // 若 cur == 0 (新桶未推进), 不能 branch — 改 fallback 用 createSession.
        const cur = currentMealIdx;
        if (cur <= 0) {
          (async () => {
            try {
              const newSid = `sbx_${Date.now().toString(36)}`;
              const meta = await createSession(newSid, 7);
              const snap = await getFullSnapshot(meta.sid);
              await applySnapshot(meta.sid, backendFullSnapshotToStore(snap));
              setActiveSessionId(meta.sid);
              setSelectedCellIdx(null);
              setTransientBanners((prev) => [
                ...prev,
                {
                  id: `branch_${Date.now()}`,
                  level: "info",
                  title: "已创建新 session",
                  detail: `(branch 需 cur>0, fallback createSession)`,
                  dismissable: true,
                },
              ]);
            } catch (e) {
              setApiError(`new session failed: ${e instanceof Error ? e.message : String(e)}`);
            }
          })();
          return;
        }
        const safeFromIdx = Math.min(fromIdx, cur - 1);
        (async () => {
          try {
            const meta = await postBranch(oldSid, safeFromIdx, name || "未命名");
            const snap = await getFullSnapshot(meta.sid);
            await applySnapshot(meta.sid, backendFullSnapshotToStore(snap));
            setActiveSessionId(meta.sid);
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
          } catch (e) {
            setApiError(`branch failed: ${e instanceof Error ? e.message : String(e)}`);
          }
        })();
        return;
      }

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
    [activeSessionId, backendOnline, currentMealIdx, sessions, sessionStates, applySnapshot],
  );

  // Suppress unused warnings for adapter helpers when offline-only path runs
  void backendMetaToSessionMeta;

  // P2 fix (iter 2): online 模式切 session 时, 如果目标 session 的 currentRecs
  // 在 boot 时 cache 是空 (后端 last_recs.json 缺), 触发 ensureRecs 拉一次.
  // offline 模式直接走 setState.
  const setActiveSessionIdWithEnsure = useCallback(
    (id: string) => {
      setActiveSessionId(id);
      if (!backendOnline) return;
      const st = sessionStates.get(id);
      if (!st) return;
      const sessIsDone = st.currentMealIdx >= (st.totalMeals ?? totalMeals);
      if (st.currentRecs.length > 0 || sessIsDone) return;
      (async () => {
        try {
          const recsResp = await postRecs(id);
          const recs = (recsResp.currentRecs || []).map(backendRecToFrontend);
          updateSessionState(id, (prev) => ({ ...prev, currentRecs: recs }));
        } catch (e) {
          // soft fail
          // eslint-disable-next-line no-console
          console.warn("ensureRecs on session switch failed:", e);
        }
      })();
    },
    [backendOnline, sessionStates, totalMeals, updateSessionState],
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
  const dismissApiError = useCallback(() => setApiError(null), []);

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
    backendOnline,
    polling,
    apiError,
    setActiveSessionId: setActiveSessionIdWithEnsure,
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
    dismissApiError,
  };
}

// Keep TOTAL_MEALS export accessible (was inlined; helps any future caller).
export const __DEFAULT_TOTAL_MEALS__ = TOTAL_MEALS;

// S-08: backend dict → 前端 view-model.
// activeRules 后端字段暂不接入前端 (RightCol 用内置 MOCK).

import type {
  BackendDecision,
  BackendFullSnapshot,
  BackendHistoryEntry,
  BackendJobInfo,
  BackendRec,
  BackendSessionMetaFull,
} from "./backend-types";
import type {
  Clock,
  Decision,
  Meal,
  Rec,
  SessionMeta,
} from "../types/sandbox";


// ── slot ──
export function backendSlotToFrontend(slot: string): "午" | "晚" {
  return slot === "dinner" ? "晚" : "午";
}


// ── origin ──
export function backendOriginToFrontend(
  origin: string | null | undefined,
): "真实快照" | "空白" {
  if (!origin) return "空白";
  if (origin === "blank") return "空白";
  return "真实快照";
}


// ── status ──
function backendStatusToFrontend(status: string): "running" | "done" {
  return status === "done" ? "done" : "running";
}


// ── SessionMeta (list view entry + snapshot 合体) ──
export function backendMetaToSessionMeta(
  bm: BackendSessionMetaFull,
  fallback?: { lastUsed?: string },
): SessionMeta {
  return {
    id: bm.sid,
    name: bm.name || bm.sid,
    days: bm.days,
    seed: bm.seed || 0,
    profile: bm.profile || "profile@v2",
    origin: backendOriginToFrontend(bm.origin),
    status: backendStatusToFrontend(bm.status),
    lastUsed: bm.lastUsed || fallback?.lastUsed || "",
  };
}


// ── Clock ──
export function backendClockToFrontend(
  bc: BackendFullSnapshot["clock"],
): Clock {
  return {
    idx: bc.idx,
    day: bc.day,
    slot: backendSlotToFrontend(bc.slot),
    total: bc.total,
  };
}


// ── History entry ──
export function backendHistoryToMeal(h: BackendHistoryEntry): Meal {
  const day = Math.floor(h.idx / 2) + 1;
  const slot: "午" | "晚" = h.idx % 2 === 0 ? "午" : "晚";
  const state = h.state === "skip" ? "skip" : "eat";
  const dish = state === "skip" ? "—" : (h.dish || "—");
  return {
    idx: h.idx,
    day,
    slot,
    state,
    dish,
    score: null,
    flags: [],
    altScores: [],
  };
}


// ── Rec (backend → frontend, 字段对齐, 仅 default 兜底) ──
// 保留 backend id 作为 (rec as RecWithId)._backendId 给 swap exclude_ids 用. 前端
// Rec interface 没 id 字段, 用 symbol-like prefix 字段贴上, TS 视为 extra prop.
export function backendRecToFrontend(c: BackendRec): Rec & { _backendId?: string } {
  return {
    rank: c.rank,
    name: c.name,
    venue: c.venue || "",
    dishes: c.dishes || [],
    price: c.price,
    l2: c.l2,
    l3: c.l3,
    boost: c.boost,
    intent: c.intent,
    l1Hits: c.l1Hits || [],
    explore: !!c.explore,
    conflict: c.conflict ?? null,
    meta: c.meta,
    why: c.why || "",
    _backendId: c.id || undefined,
  };
}


// ── Decision ──
export function backendDecisionToFrontend(d: BackendDecision): Decision {
  return {
    when: d.when,
    pick: d.pick,
    rank: d.rank,
    l3: d.l3,
    diff: d.diff.map((x) => ({
      kind: x.kind,
      field: x.field,
      from: x.from,
      to: x.to,
      value: x.value,
      delta: x.delta,
    })),
    implications: d.implications,
  };
}


// ── FullSnapshot → store (活动 session 的派生数据) ──
export interface SnapshotStorePiece {
  meta: SessionMeta;
  clock: Clock;
  history: Meal[];
  currentRecs: Rec[];
  lastDecision: Decision | null;
  // S-09: trace 跳转所需
  mealToTrace: Record<string, string>;
  currentTraceId: string | null;
  // 注: activeRules 故意不导出 (RightCol 维持 MOCK, S-08 不接)
}


export function backendFullSnapshotToStore(
  snap: BackendFullSnapshot,
): SnapshotStorePiece {
  return {
    meta: backendMetaToSessionMeta(snap.meta),
    clock: backendClockToFrontend(snap.clock),
    history: (snap.history || []).map(backendHistoryToMeal),
    currentRecs: (snap.currentRecs || []).map(backendRecToFrontend),
    lastDecision: snap.lastDecision
      ? backendDecisionToFrontend(snap.lastDecision)
      : null,
    // S-09: || null 防空串 (Iter 4 #2): backend `_` 兜底是 None 但若 last_recs 存空字符串
    // 也要 falsy-collapse
    mealToTrace: snap.mealToTrace || {},
    currentTraceId: snap.currentTraceId || null,
  };
}


// ── Job status mapping ──
export type FrontendJobStatus = "running" | "done" | "failed" | "cancelled";


export function backendJobToStatus(j: BackendJobInfo): FrontendJobStatus {
  if (j.status === "done") return "done";
  if (j.status === "failed") return "failed";
  if (j.status === "cancelled_by_rollback") return "cancelled";
  // "pending" / "running" → running
  return "running";
}

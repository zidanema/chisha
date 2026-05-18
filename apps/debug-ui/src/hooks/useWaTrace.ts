// Workflow A 中央数据 hook: list traces + lazy fetch trace detail/round + LRU cache.
// Backend offline → fallback 到 waMocks; 后端在线 → 真数据.
//
// LRU: 按字节数 ≤ 50MB 淘汰 (Codex 推荐). 单 round 5MB × 10 cache 足够典型工作流.

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchIntentSchema, fetchRoundFull, fetchTraceDetail, fetchTraces } from "../api/client";
import type { BackendRoundFull, BackendRoundStub, BackendTraceDetail } from "../api/client";
import { traceToSession } from "../api/adapter";
import type { BackendDebugTrace } from "../api/backend-types";
import { pushToast } from "../components/Toaster";
import { ACTIVE_WA_TRACE, MOCK_TRACES, getMockTrace } from "../mocks/waMocks";
import type { IntentFieldDescriptor, RoundRecord, TraceMeta, WaTrace } from "../types/trace";

const LRU_MAX_BYTES = 50 * 1024 * 1024;

class RoundLRU {
  private map = new Map<string, { data: RoundRecord; bytes: number }>();
  private totalBytes = 0;
  private maxBytes = LRU_MAX_BYTES;

  get(key: string): RoundRecord | undefined {
    const v = this.map.get(key);
    if (!v) return undefined;
    // touch — move to end as most-recently-used
    this.map.delete(key);
    this.map.set(key, v);
    return v.data;
  }

  set(key: string, data: RoundRecord) {
    let bytes = 0;
    try { bytes = JSON.stringify(data).length; } catch { bytes = 0; }
    const prev = this.map.get(key);
    if (prev) {
      this.totalBytes -= prev.bytes;
      this.map.delete(key);
    }
    this.map.set(key, { data, bytes });
    this.totalBytes += bytes;
    // evict oldest until under cap (always keep at least 1)
    while (this.totalBytes > this.maxBytes && this.map.size > 1) {
      const oldestKey = this.map.keys().next().value;
      if (oldestKey === undefined) break;
      const oldestVal = this.map.get(oldestKey);
      if (oldestVal) {
        this.totalBytes -= oldestVal.bytes;
        this.map.delete(oldestKey);
      }
    }
  }

  clear() { this.map.clear(); this.totalBytes = 0; }
}

// ─── 后端 → 前端 round 形状转换 ─────────────────────────────────
function stubToRound(stub: BackendRoundStub, fallback?: WaTrace): RoundRecord {
  return {
    id: stub.id,
    label: stub.label || (stub.id === "R1" ? "原始" : "追问"),
    started_at: displayTime(stub.started_at) || (fallback?.meta.time ?? ""),
    user_input: stub.user_input ?? null,
    intent_v2: (stub.intent_v2 as RoundRecord["intent_v2"]) ?? null,
    kpi: {
      combos: stub.kpi?.combos ?? 0,
      l2_top: stub.kpi?.l2_top ?? 0,
      top1: stub.kpi?.top1 ?? "",
      latency_ms: stub.kpi?.latency_ms ?? 0,
    },
    diff: stub.diff ?? null,
    // stub 无 body — 用 mock R1 兜底, 让 panel 仍能渲染 (Phase 2a R2+ refine
    // 不存完整 trace 切片, 后续 task 扩展). __partial 标记: LookupDrawer 据此警告
    // 用户当前反查跑在 mock 数据上不可信 (Codex H3 fix).
    l1: ACTIVE_WA_TRACE.rounds[0].l1,
    l2: ACTIVE_WA_TRACE.rounds[0].l2,
    l3: ACTIVE_WA_TRACE.rounds[0].l3,
    final: ACTIVE_WA_TRACE.rounds[0].final,
    __partial: true,
  };
}

function fullToRound(full: BackendRoundFull, fallback?: WaTrace): RoundRecord {
  const base = stubToRound(full, fallback);
  // 后端 full payload 的 l1/l2/l3/final 是原始 backend trace shape (api.py 产),
  // panel 期望前端 view-model shape (mocks/session.ts 的 L1Trace/L2Trace/...).
  // 走 traceToSession 复用既有 adapter (D-079 PR-3 的成果), 把 backend 形状映射
  // 成 Session, 再拆出 l1/l2/l3/final 灌进 RoundRecord.
  // null body (Phase 2a R2+ refine 还没存完整切片) → 保留 fallback mock.
  if (!full.l1 || !full.l2 || !full.l3 || !full.final) {
    return base;
  }
  try {
    const synthBackendTrace: BackendDebugTrace = {
      session_id: full.id || "round",
      started_at: full.started_at || "",
      total_latency_ms: (full as { total_latency_ms?: number }).total_latency_ms ?? 0,
      ctx_latency_ms: (full as { ctx_latency_ms?: number }).ctx_latency_ms ?? 0,
      recall_latency_ms: (full as { recall_latency_ms?: number }).recall_latency_ms ?? 0,
      score_latency_ms: (full as { score_latency_ms?: number }).score_latency_ms ?? 0,
      rerank_latency_ms: (full as { rerank_latency_ms?: number }).rerank_latency_ms ?? 0,
      final_latency_ms: (full as { final_latency_ms?: number }).final_latency_ms ?? 0,
      __frozen: (full.__frozen as BackendDebugTrace["__frozen"]) ?? undefined,
      l1: full.l1 as BackendDebugTrace["l1"],
      l2: full.l2 as BackendDebugTrace["l2"],
      l3: full.l3 as BackendDebugTrace["l3"],
      final: full.final as BackendDebugTrace["final"],
      refine: { applied: false } as BackendDebugTrace["refine"],
      __version: 3,
      __source: "production",
      __parent_session_id: null,
      __llm_called: true,
      __config: {} as BackendDebugTrace["__config"],
    };
    const sess = traceToSession(synthBackendTrace);
    return { ...base, l1: sess.l1, l2: sess.l2, l3: sess.l3, final: sess.final, __partial: false };
  } catch (e) {
    // 后端 trace shape 异常时 fallback 到 stub (panel 仍能渲染 mock)
    console.warn("[useWaTrace] traceToSession adapter failed, using stub:", e);
    return base;
  }
}

function displayTime(iso: string | null | undefined): string {
  if (!iso) return "";
  // 接受 "2026-05-18T12:34:56" / "2026-05-18 12:34:56" / "HH:MM"
  if (/^\d{2}:\d{2}/.test(iso)) return iso.slice(0, 5);
  const sep = iso.includes("T") ? "T" : iso.includes(" ") ? " " : null;
  if (!sep) return iso;
  const [, hms] = iso.split(sep);
  return (hms || "").slice(0, 5);
}

function assembleTraceFromDetail(detail: BackendTraceDetail): WaTrace {
  const meta: TraceMeta = {
    id: detail.meta.session_id ?? "",
    date: (detail.meta.started_at ?? "").split(/[ T]/)[0] || "",
    time: displayTime(detail.meta.started_at),
    daysAgo: 0,    // 设由 /api/traces TraceMeta 给; detail.meta 没这个字段, 让 caller 覆盖
    meal: (detail.meta.meal_type === "dinner" ? "dinner" : "lunch"),
    finalTop1: (detail.meta.top1_summary ?? "").split(" · ")[0] || "",
    refineCount: detail.meta.refine_count ?? 0,
    latestRound: detail.meta.latest_round ?? "R1",
    source: detail.meta.__source === "sandbox" ? "sandbox" : "real",
    sandboxDay: null,
    feedback: (detail.meta.feedback as TraceMeta["feedback"]) ?? null,
    status: detail.meta.l3_status === "fallback" ? "fallback"
          : (detail.meta.l3_status === "config_error" || detail.meta.l3_status === "warn") ? "warn"
          : "ok",
    latency_ms: detail.meta.total_latency_ms ?? 0,
  };
  const rounds = detail.rounds.map((r) => stubToRound(r));
  return { meta, rounds };
}

// ─── 主 hook ──────────────────────────────────────────────────
export type UseWaTrace = {
  traces: TraceMeta[];
  activeTraceId: string;
  setActiveTraceId: (id: string) => void;
  activeTrace: WaTrace;
  /** 取某 round 的完整 body (LRU cached, lazy fetch). 返 null = 还在 fetch. */
  getRoundFull: (roundId: string) => RoundRecord | null;
  intentSchema: IntentFieldDescriptor[] | null;
  backendOnline: boolean;
};

export function useWaTrace(): UseWaTrace {
  const [traces, setTraces] = useState<TraceMeta[]>(MOCK_TRACES);
  const [activeTraceId, setActiveTraceIdState] = useState<string>(ACTIVE_WA_TRACE.meta.id);
  const [activeTrace, setActiveTrace] = useState<WaTrace>(ACTIVE_WA_TRACE);
  const [intentSchema, setIntentSchema] = useState<IntentFieldDescriptor[] | null>(null);
  const [backendOnline, setBackendOnline] = useState<boolean>(false);
  const lruRef = useRef<RoundLRU>(new RoundLRU());
  const inflightRef = useRef<Set<string>>(new Set());
  // forces re-render when LRU updates (cheap counter)
  const [tick, setTick] = useState(0);

  // 初次挂载: fetch traces + intent schema
  useEffect(() => {
    void (async () => {
      try {
        const list = await fetchTraces({ limit: 50 });
        if (list.length > 0) {
          setTraces(list);
          setBackendOnline(true);
          // 切到 backend 第一条 (mock active 通常不在 backend list 里, 404 没意义)
          if (!list.find((t) => t.id === activeTraceId)) {
            setActiveTraceIdState(list[0].id);
          }
        }
      } catch (err) {
        const apiErr = err instanceof ApiError ? err : null;
        if (apiErr?.code === "NETWORK") {
          pushToast({
            kind: "warn",
            title: "后端 :8765 不可达 · 走 mock",
            detail: "uv run python -m chisha.debug_server",
          });
        }
        // 保留 MOCK_TRACES, backend offline
      }
      try {
        const sch = await fetchIntentSchema();
        if (sch.length > 0) setIntentSchema(sch);
      } catch {
        // intent schema 失败不阻断, IntentStrip 会 fallback INTENT_SCHEMA 常量
      }
    })();
  }, []);

  // active trace 变化: 拉 detail (含 rounds stub)
  useEffect(() => {
    if (!backendOnline) {
      // 用 mock fallback
      setActiveTrace(getMockTrace(activeTraceId));
      return;
    }
    void (async () => {
      try {
        const detail = await fetchTraceDetail(activeTraceId);
        const wa = assembleTraceFromDetail(detail);
        // daysAgo 用 list 的 (detail meta 不算 daysAgo)
        const listMeta = traces.find((t) => t.id === activeTraceId);
        if (listMeta) {
          wa.meta = { ...wa.meta, daysAgo: listMeta.daysAgo, date: listMeta.date,
                      time: listMeta.time };
        }
        setActiveTrace(wa);
        lruRef.current.clear();  // 切 trace 清缓存
      } catch (err) {
        const apiErr = err instanceof ApiError ? err : null;
        pushToast({
          kind: "error",
          title: `trace 读失败 ${apiErr?.status ?? ""}`.trim(),
          detail: apiErr?.message ?? String(err),
        });
        setActiveTrace(getMockTrace(activeTraceId));
      }
    })();
  }, [activeTraceId, backendOnline]);

  const setActiveTraceId = useCallback((id: string) => {
    setActiveTraceIdState(id);
  }, []);

  const getRoundFull = useCallback((roundId: string): RoundRecord | null => {
    const cacheKey = `${activeTraceId}::${roundId}`;
    const cached = lruRef.current.get(cacheKey);
    if (cached) return cached;
    // 从 activeTrace.rounds 找 stub (作为渲染兜底, 同步)
    const stubRound = activeTrace.rounds.find((r) => r.id === roundId) || null;
    if (!backendOnline) {
      // mock 模式: stub 即完整 (mock 数据 mocks/waMocks.ts 直接含 l1/l2/l3/final)
      if (stubRound) {
        lruRef.current.set(cacheKey, stubRound);
        return stubRound;
      }
      return null;
    }
    // backend 模式: async fetch + cache
    if (!inflightRef.current.has(cacheKey)) {
      inflightRef.current.add(cacheKey);
      void (async () => {
        try {
          const full = await fetchRoundFull(activeTraceId, roundId);
          const rec = fullToRound(full, activeTrace);
          lruRef.current.set(cacheKey, rec);
          setTick((t) => t + 1);
        } catch (err) {
          const apiErr = err instanceof ApiError ? err : null;
          pushToast({
            kind: "warn",
            title: `round ${roundId} 读失败 ${apiErr?.status ?? ""}`.trim(),
            detail: apiErr?.message ?? String(err),
          });
        } finally {
          inflightRef.current.delete(cacheKey);
        }
      })();
    }
    // 同步先返 stub (panel 兜底渲染), 等 fetch 完 setTick 重 render 再返 full
    return stubRound;
  }, [activeTraceId, activeTrace, backendOnline, tick]);

  return {
    traces,
    activeTraceId,
    setActiveTraceId,
    activeTrace,
    getRoundFull,
    intentSchema,
    backendOnline,
  };
}

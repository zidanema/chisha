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

// D-088 (B3): 替代原 mock-R1 兜底. stub 无 body 时, 灌零骨架而不是用 R1 mock —
// 否则用户切到 R2 在 fetch resolve 前会看见 R1 的 11k combo 等假数据,
// 完全误导. 字段全填零让 panel 内部 .map/.length 安全 (空数组).
function makeEmptyL1(): RoundRecord["l1"] {
  return {
    area: "", meal: "lunch", raw_dishes: 0, raw_restaurants: 0,
    funnel: [], restaurant_bans: [], ban_reason_agg: [],
    dish_drops: [], top_restaurants: [], latency_ms: 0,
  };
}
function makeEmptyL2(): RoundRecord["l2"] {
  return {
    weights: [], combos: [],
    kpi: {
      score_min: "0", score_max: "0", cap_k: 0,
      per_brand_top_k: 0, per_restaurant_cap_k: 0,
      restaurants_before_cap: 0, restaurants_after_cap: 0,
      max_combos_one_rest_before: 0, max_combos_one_rest_after: 0,
    },
    latency_ms: 0, candidates_to_l3: 0, combos_before_l2: 0,
  };
}
function makeEmptyL3(): RoundRecord["l3"] {
  // D-089-S5b: status: "skipped" → "no_data" — 之前 "skipped" 容易让人误以为是
  // 业务跳过 (LLM 关闭 / top_combos 为空), 实际是 round 根本没存 L3 切片.
  // 现在 D-089-S2 之后 refine round 也存完整切片, 这个兜底几乎不会触发,
  // 但保留兜底语义清晰 ("no_data" = 数据缺失, 跟业务的 "skipped" 区分).
  return {
    status: "no_data", resolved_provider: "—", model: "—",
    latency_ms: 0, input_tokens: 0, output_tokens: 0,
    cache_read_input_tokens: 0, cache_creation_input_tokens: 0,
    system_prompt_chars: 0, user_message_chars: 0,
    stop_reason: "—", max_tokens: 0, temperature: 0,
    candidates_returned: 0, fallback_chain: [],
    system_prompt: "", user_message: "",
    tool_input: { name: "", description: "", input_schema: {} },
    raw_response_blocks: [], validator_errors: null,
  };
}

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
    // D-088 (B3): zero-state — fullToRound resolve 后才有真数据
    l1: makeEmptyL1(),
    l2: makeEmptyL2(),
    l3: makeEmptyL3(),
    final: [],
    __partial: true,
  };
}

function fullToRound(full: BackendRoundFull, fallback?: WaTrace): RoundRecord {
  const base = stubToRound(full, fallback);
  // D-089-S5a: refine_intent_llm 顶层字段直接透传 (BackendLlmCallTrace 已经是
  // view-model 对齐 shape, 不需要 adapter 转换).
  const refineIntentLlm = (full.refine_intent_llm ?? null) as RoundRecord["refine_intent_llm"];
  // 后端 full payload 的 l1/l2/l3/final 是原始 backend trace shape (api.py 产),
  // panel 期望前端 view-model shape (mocks/session.ts 的 L1Trace/L2Trace/...).
  // 走 traceToSession 复用既有 adapter (D-079 PR-3 的成果), 把 backend 形状映射
  // 成 Session, 再拆出 l1/l2/l3/final 灌进 RoundRecord.
  // D-089-S2 之后 refine round 也含完整切片; null body 兜底保留 (老 trace 兼容).
  if (!full.l1 || !full.l2 || !full.l3 || !full.final) {
    return { ...base, refine_intent_llm: refineIntentLlm };
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
    return {
      ...base,
      l1: sess.l1, l2: sess.l2, l3: sess.l3, final: sess.final,
      refine_intent_llm: refineIntentLlm,
      __partial: false,
    };
  } catch (e) {
    // 后端 trace shape 异常时 fallback 到 stub (panel 仍能渲染 mock)
    console.warn("[useWaTrace] traceToSession adapter failed, using stub:", e);
    return { ...base, refine_intent_llm: refineIntentLlm };
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
  // D-088: ref 持久化 activeTraceId, 让 detail fetch 的异步 callback 能 stale-check
  // 自己的请求, 防止用户快切 trace 时早请求覆盖晚请求的状态.
  const activeTraceIdRef = useRef(activeTraceId);
  useEffect(() => { activeTraceIdRef.current = activeTraceId; }, [activeTraceId]);
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

  // active trace 变化: 拉 detail (含 rounds stub).
  // D-088: success + catch 两路都加 stale guard (myId vs activeTraceIdRef.current),
  // 防快切 trace 时早 fetch 的回调覆盖晚 fetch 的状态.
  useEffect(() => {
    if (!backendOnline) {
      // 用 mock fallback
      setActiveTrace(getMockTrace(activeTraceId));
      return;
    }
    const myId = activeTraceId;
    let cancelled = false;
    void (async () => {
      try {
        const detail = await fetchTraceDetail(myId);
        if (cancelled || myId !== activeTraceIdRef.current) return;
        const wa = assembleTraceFromDetail(detail);
        // daysAgo 用 list 的 (detail meta 不算 daysAgo)
        const listMeta = traces.find((t) => t.id === myId);
        if (listMeta) {
          wa.meta = { ...wa.meta, daysAgo: listMeta.daysAgo, date: listMeta.date,
                      time: listMeta.time };
        }
        setActiveTrace(wa);
        lruRef.current.clear();  // 切 trace 清缓存
      } catch (err) {
        if (cancelled || myId !== activeTraceIdRef.current) return;
        const apiErr = err instanceof ApiError ? err : null;
        pushToast({
          kind: "error",
          title: `trace 读失败 ${apiErr?.status ?? ""}`.trim(),
          detail: apiErr?.message ?? String(err),
        });
        setActiveTrace(getMockTrace(myId));
      }
    })();
    return () => { cancelled = true; };
  }, [activeTraceId, backendOnline]);

  // D-088 (B5): 5s 轮询 /api/traces, 让用户端新产生的 trace 自动浮上来.
  // 仅 backendOnline 时启动. cancelled flag 防 StrictMode dev 双 mount /
  // unmount 时未完成请求漏判 setState (effect 清理把 cancelled 置 true,
  // 在 setTraces 前检查丢弃 stale 响应). 失败 silent — backend 临时 5xx 不响铃.
  useEffect(() => {
    if (!backendOnline) return;
    let cancelled = false;
    const handle = setInterval(() => {
      void (async () => {
        try {
          const list = await fetchTraces({ limit: 50 });
          if (cancelled) return;
          if (list.length > 0) setTraces(list);
        } catch { /* silent */ }
      })();
    }, 5000);
    return () => { cancelled = true; clearInterval(handle); };
  }, [backendOnline]);

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
    // D-088 (B6 fix): 两道 stale guard, 防 mock→backend 切换瞬间打错 round id.
    // (a) activeTraceId 已切但 activeTrace state 还是上一条 (mock or 上一 trace) →
    //     拿 mock 的 R4 去打新 trace 必 404.
    // (b) activeTrace 已同步到新 trace, 但 target/activeRound 还停在旧值 (R4),
    //     而新 trace.rounds 只有 [R1] → stubRound 找不到, 这种 roundId 也别打.
    if (activeTrace.meta.id !== activeTraceId) {
      return null;
    }
    if (!stubRound) {
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

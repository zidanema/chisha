// backend → frontend Session adapter.
// PURE function. No fetch, no side effects.
// All shape divergence between chisha.debug_recommend output and the
// view-model Session lives here so panels stay data-in.

import type {
  BackendDebugRecommend,
  BackendDebugTrace,
  BackendL1Recall,
  BackendL2Combo,
  BackendL2Score,
  BackendL3Llm,
  BackendL3Rerank,
  BackendFinalRow,
  BackendTraceL3,
} from "./backend-types";
import { labelForDim } from "../constants/labels";
import { zoneLabel } from "../constants/zones";
import type {
  ComboDish,
  FinalRow,
  FunnelStage,
  L1Trace,
  L2Combo,
  L2KPI,
  L2Trace,
  L2Weight,
  L3Trace,
  Meal,
  ResponseBlock,
  Session,
} from "../types/trace";

function synthFunnel(l1: BackendL1Recall): FunnelStage[] {
  const s = l1.summary;
  return [
    { stage: "raw_dishes", label: "全量菜", value: s.total_dishes,
      kind: "dish", dropped: 0 },
    { stage: "hard_filter_dishes", label: "硬过滤后菜", value: s.after_hard_filter,
      kind: "dish", dropped: Math.max(0, s.total_dishes - s.after_hard_filter) },
    { stage: "diversity_dishes", label: "多样性后菜", value: s.after_diversity_filter,
      kind: "dish",
      dropped: Math.max(0, s.after_hard_filter - s.after_diversity_filter) },
    { stage: "combo_restaurants", label: "出 combo 餐厅",
      value: s.n_restaurants_with_combos, kind: "rest",
      dropped: Math.max(0, s.total_restaurants - s.n_restaurants_with_combos) },
    { stage: "raw_combos", label: "Combo 总数 (价格前)",
      value: s.n_combos_before_price_filter, kind: "combo", dropped: 0 },
    { stage: "price_filtered", label: "价格过滤后 Combo",
      value: s.n_combos, kind: "combo", dropped: s.n_combos_dropped_by_price },
    { stage: "final_combos", label: "最终 Combo (送 L2)",
      value: s.n_combos, kind: "combo", dropped: 0 },
  ];
}

function classifyDropLayer(reason: string): "hard" | "diversity" | "price" {
  const lower = reason.toLowerCase();
  if (lower.includes("price") || lower.includes("价格") || lower.includes("¥") ||
      lower.includes("budget")) return "price";
  if (lower.includes("多样") || lower.includes("diversity") ||
      lower.includes("重复")) return "diversity";
  return "hard";
}

function adaptL1(l1: BackendL1Recall, area: string, meal: Meal,
                 latencyMs: number = 0): L1Trace {
  const dishDrops: { reason: string; count: number; layer: "hard" | "diversity" | "price" }[] = [];
  for (const [reason, count] of Object.entries(l1.dropped_hard_by_reason)) {
    dishDrops.push({ reason, count, layer: classifyDropLayer(reason) });
  }
  for (const [reason, count] of Object.entries(l1.dropped_diversity_by_reason)) {
    dishDrops.push({ reason, count, layer: "diversity" });
  }
  if (l1.summary.n_combos_dropped_by_price > 0) {
    dishDrops.push({
      reason: "combo 总价 > budget (价格层)",
      count: l1.summary.n_combos_dropped_by_price,
      layer: "price",
    });
  }
  dishDrops.sort((a, b) => b.count - a.count);

  const restaurant_bans = (l1.banned_restaurants ?? []).map((b) => ({
    rest: b.restaurant_name ?? b.name ?? String(b.restaurant_id ?? "—"),
    reason: b.reason,
    detail: b.detail ?? b.reason,
    count: 1,
  }));

  const top_restaurants = (l1.per_restaurant ?? [])
    .slice(0, 20)
    .map((r) => ({ name: r.restaurant_name ?? r.name ?? "—", combos: r.n_combos }));

  const banAggMap = new Map<string, number>();
  for (const b of restaurant_bans) {
    banAggMap.set(b.reason, (banAggMap.get(b.reason) ?? 0) + b.count);
  }
  const ban_reason_agg = Array.from(banAggMap.entries())
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count);

  return {
    area,
    meal,
    raw_dishes: l1.summary.total_dishes,
    raw_restaurants: l1.summary.total_restaurants,
    funnel: synthFunnel(l1),
    restaurant_bans,
    ban_reason_agg,
    dish_drops: dishDrops,
    top_restaurants,
    // D-079: 后端 trace 顶层有 recall_latency_ms; debug_recommend 老链路没此值,
    // 默认 0 (DagHeader 显示 "0ms" 而非 undefined).
    latency_ms: latencyMs,
  };
}

// 把 backend dish (扁平字段, 数字 level) 转为 frontend ComboDish (中文 label).
// Source: chisha/score.py 约定 — oil/spicy/wetness/sweet 是 1..N 数字, 不是 string.
function adaptComboDish(d: BackendL2Combo["dishes"][number]): ComboDish {
  return {
    name: d.name,
    price: d.price,
    oil: labelForDim("oil_level", d.oil_level),
    spicy: labelForDim("spicy_level", d.spicy_level),
    protein_g: d.protein_g ?? 0,
    cook: d.cooking_method ?? "—",
    main: d.main_ingredient_type ?? "—",
    role: d.dish_role ?? "main",
    wetness: labelForDim("wetness", d.wetness),
    sweet: labelForDim("sweet_sauce_level", d.sweet_sauce_level),
    grain: d.grain_type ?? "none",
  };
}

function adaptL2Combo(c: BackendL2Combo): L2Combo {
  return {
    combo_id: `cmb_${String(c.rank).padStart(3, "0")}`,
    restaurant: c.restaurant_name,
    rank: c.rank,
    total_score: c.score,
    fit_score: c.breakdown?.fit_diet ?? 0,
    eta_min: c.eta_min,
    distance_km: c.distance_m >= 0 ? Math.round((c.distance_m / 100)) / 10 : 0,
    total_price: c.total_price,
    dishes: c.dishes.map(adaptComboDish),
    breakdown: c.breakdown,
  };
}

// Canonical dim ordering for the heatmap. Matches profile.yaml:148-166
// scoring_weights insertion order. Dims not in DIM_ORDER but present in
// the backend response get appended at the end so we don't silently drop them.
const DIM_ORDER: string[] = [
  "vegetable_floor_pass", "protein_floor_pass", "distance",
  "low_oil", "popularity", "cuisine_preference",
  "variety_bonus", "carb_quality", "processed_meat",
  "sweet_sauce", "wetness", "dish_role_match",
  "eta", "price", "taste_match", "context_boost",
];

function adaptL2Weights(weightsDict: Record<string, number>): L2Weight[] {
  const seen = new Set<string>();
  const ordered: L2Weight[] = [];
  for (const key of DIM_ORDER) {
    if (key in weightsDict) {
      ordered.push({ key, label: key, w: weightsDict[key] });
      seen.add(key);
    }
  }
  // Append any backend dim not in DIM_ORDER (defensive against profile schema drift).
  for (const [key, w] of Object.entries(weightsDict)) {
    if (!seen.has(key)) ordered.push({ key, label: key, w });
  }
  return ordered;
}

function adaptL2KPI(l2: BackendL2Score): L2KPI {
  const s = l2.summary;
  return {
    score_min: s.score_min.toFixed(3),
    score_max: s.score_max.toFixed(3),
    cap_k: s.caps.restaurant ?? s.per_restaurant_cap_k,
    per_brand_top_k: s.caps.brand ?? 3,
    per_restaurant_cap_k: s.per_restaurant_cap_k,
    restaurants_before_cap: s.topk_unique_restaurants_before_cap,
    restaurants_after_cap: s.topk_unique_restaurants_after_cap,
    max_combos_one_rest_before: s.topk_max_per_restaurant_before_cap,
    max_combos_one_rest_after: s.topk_max_per_restaurant_after_cap,
  };
}

function adaptL2(l2: BackendL2Score, combosBeforeL2: number,
                 latencyMs: number = 0): L2Trace {
  return {
    weights: adaptL2Weights(l2.summary.weights),
    combos: l2.top.map(adaptL2Combo),
    kpi: adaptL2KPI(l2),
    // D-079: 从 trace.score_latency_ms 传; debug_recommend 链路缺时为 0.
    latency_ms: latencyMs,
    candidates_to_l3: l2.summary.topk_window,
    combos_before_l2: combosBeforeL2,
  };
}

function isLiveL3(llm: BackendL3Rerank["llm"]): llm is BackendL3Llm {
  return "status" in llm;
}

function adaptL3(l3: BackendL3Rerank): L3Trace {
  if (!isLiveL3(l3.llm)) {
    // L3 skipped: provide a typed shell so the panel can render the "skipped" state.
    return {
      status: "skipped",
      resolved_provider: "—",
      model: "—",
      latency_ms: 0,
      input_tokens: 0,
      output_tokens: 0,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 0,
      system_prompt_chars: 0,
      user_message_chars: 0,
      stop_reason: "—",
      max_tokens: 0,
      temperature: 0,
      candidates_returned: l3.n_returned,
      fallback_chain: [],
      system_prompt: "",
      user_message: "",
      tool_input: { name: "", description: "", input_schema: {} },
      raw_response_blocks: [],
      validator_errors: null,
    };
  }

  const llm = l3.llm;
  const status = llm.status ?? (llm.used ? "ok" : "fallback");
  const fallbackChain: L3Trace["fallback_chain"] = [];
  if (llm.fallback_reason) {
    fallbackChain.push({
      step: 1,
      name: `${llm.resolved_provider ?? "?"} / ${llm.model ?? "?"}`,
      status: "error",
      meta: llm.fallback_reason,
      error: llm.fallback_reason,
    });
  } else {
    fallbackChain.push({
      step: 1,
      name: `${llm.resolved_provider ?? "?"} / ${llm.model ?? "?"}`,
      status: "ok",
      meta: `latency ${llm.latency_ms ?? "?"}ms`,
      error: null,
    });
  }

  // Build content blocks from raw_response text + tool_input.
  // Backend doesn't store structured thinking/tool_use blocks separately;
  // we'd need to parse SSE chunks (out of scope for Phase 2).
  const blocks: ResponseBlock[] = [];
  if (llm.raw_response) {
    blocks.push({ type: "text", text: llm.raw_response });
  }
  if (llm.tool_input) {
    blocks.push({
      type: "tool_use",
      id: "toolu_live",
      name: "emit_recommendations",
      input: llm.tool_input,
    });
  }

  const usage = llm.usage ?? {};
  const toolInputSchema = (llm.tool_input as { input_schema?: unknown } | null)?.input_schema;

  return {
    status,
    resolved_provider: llm.resolved_provider ?? "—",
    model: llm.model ?? "—",
    latency_ms: llm.latency_ms ?? 0,
    input_tokens: usage.input_tokens ?? 0,
    output_tokens: usage.output_tokens ?? 0,
    cache_read_input_tokens: usage.cache_read_input_tokens ?? 0,
    cache_creation_input_tokens: usage.cache_creation_input_tokens ?? 0,
    system_prompt_chars: llm.system_prompt_chars,
    user_message_chars: llm.user_message_chars,
    stop_reason: llm.stop_reason ?? "—",
    max_tokens: llm.max_tokens,
    temperature: llm.temperature,
    candidates_returned: l3.n_returned,
    fallback_chain: fallbackChain,
    fallback_reason: llm.fallback_reason ?? undefined,
    system_prompt: llm.system_prompt_full,
    user_message: llm.user_message_full,
    tool_input: {
      name: "emit_recommendations",
      description: "Emit reranked combos with one-line reasons.",
      input_schema: toolInputSchema ?? {},
    },
    raw_response_blocks: blocks,
    validator_errors: null,
  };
}

function adaptFinal(rows: BackendFinalRow[]): FinalRow[] {
  return rows.map((c) => ({
    rank: c.rank,
    kind: c.is_explore ? "explore" : "exploit",
    // D-079 followup: combo_index < 0 时 (老 What-if rehydrate / 部分 fallback
    // 路径漏填) 用 rank 兜底, 保证 5 行 cmb_xxx 互不重复, 避免 React duplicate
    // key. 后端已在 fallback_rerank 补 setdefault(combo_index, i), 此处是前端
    // 防御性 fallback, 别真的让前端崩.
    combo_id: c.combo_index != null && c.combo_index >= 0
      ? `cmb_${String(c.combo_index + 1).padStart(3, "0")}`
      : `cmb_r${String(c.rank).padStart(3, "0")}`,
    restaurant: c.restaurant?.name ?? "—",
    distance_km: c.restaurant?.distance_m != null && c.restaurant.distance_m >= 0
      ? Math.round((c.restaurant.distance_m / 100)) / 10 : 0,
    eta_min: c.restaurant?.eta_min ?? 0,
    total_price: c.total_price,
    score: c.score,
    fit_score: c.fit_score ?? 0,
    dishes: c.dishes.map((d) => ({ name: d.name ?? "—", price: d.price ?? 0 })),
    health_flags: {
      veg_ok: !!c.health_flags?.veg_ok,
      protein_ok: !!c.health_flags?.protein_ok,
      oil_ok: !!c.health_flags?.oil_ok,
      wetness_ok: !!c.health_flags?.wetness_ok,
      processed_meat: !!c.health_flags?.processed_meat,
      sweet_sauce: !!c.health_flags?.sweet_sauce,
    },
    risk_flags: c.risk_flags ?? [],
    reason: c.one_line_reason ?? "",
  }));
}

export type AdaptOptions = {
  sessionId: string;
  startedAt: string;       // ISO or human time, frontend formats further
  totalLatencyMs: number;  // measured on client around the fetch
};

// Production trace.l3 is flat; debug_recommend's l3_rerank wraps under .llm.
// Wrap so we can reuse adaptL3 without duplicating field maps.
// D-079 followup: rerankLatencyFallback 是 trace 顶层 rerank_latency_ms, 旧 trace
// 的 trace.l3.latency_ms 是 None (写盘漏字段, 已修但历史 trace 仍存在), 这时用
// 顶层 rerank_latency_ms 兜底, 让 DagHeader 不显示 0ms.
function wrapTraceL3(l3: BackendTraceL3,
                     rerankLatencyFallback: number = 0): BackendL3Rerank {
  if (!l3.used) {
    return {
      llm: { used: false, skipped_reason: l3.fallback_reason ?? "skipped" },
      payload_to_llm: l3.payload_to_llm,
      n_returned: l3.n_returned,
    };
  }
  // D-079 followup: 把 provider 统一后的 OpenAI 风格 usage (prompt_tokens 等)
  // 映射成前端 view-model 的 Anthropic 风格 (input_tokens 等). 语义差异:
  //   - Anthropic: input_tokens = prompt 总 tokens (含 cache 部分),
  //     cache_read_input_tokens 是其中命中 cache 的 tokens; billable = 二者之差.
  //   - OpenAI (provider 内部统一后): prompt_tokens 是 *扣除 cache 后的 billable*,
  //     cached_tokens 是 cache 命中部分; 总 prompt size = prompt_tokens + cached_tokens.
  // DagHeader 的 cache_hit% = cache_read / input_tokens 必须基于"总 prompt size",
  // 否则 cached_tokens / billable_prompt 会爆 100%+ (实测 56450%).
  // 老 trace 已是 Anthropic 命名时, input_tokens 直接是 raw 总数, 不做加法.
  const rawUsage = l3.usage ?? null;
  const usage = rawUsage
    ? (() => {
        const cacheRead =
          rawUsage.cache_read_input_tokens ?? rawUsage.cached_tokens ?? 0;
        const cacheCreate =
          rawUsage.cache_creation_input_tokens
          ?? rawUsage.cache_write_tokens ?? 0;
        // Anthropic 风格直接拿 input_tokens; OpenAI 风格需要加回 cached_tokens
        // 才能得到 prompt 总 size.
        const inputTotal =
          rawUsage.input_tokens
          ?? ((rawUsage.prompt_tokens ?? 0) + (rawUsage.cached_tokens ?? 0));
        return {
          input_tokens: inputTotal,
          output_tokens:
            rawUsage.output_tokens ?? rawUsage.completion_tokens ?? 0,
          cache_read_input_tokens: cacheRead,
          cache_creation_input_tokens: cacheCreate,
        };
      })()
    : null;
  const llm: BackendL3Llm = {
    status: (l3.status as BackendL3Llm["status"]) ?? "ok",
    config_error: l3.status === "config_error",
    resolved_provider: l3.resolved_provider,
    used: true,
    model: l3.model,
    system_prompt_chars: l3.system_prompt_chars ?? 0,
    system_prompt_full: "",
    user_message_chars: l3.user_message_chars ?? 0,
    user_message_preview: "",
    user_message_full: l3.user_message_full ?? "",
    raw_response: l3.raw_response ?? "",
    raw_response_chars: l3.raw_response_chars ?? 0,
    tool_input: l3.tool_input,
    stop_reason: l3.stop_reason,
    parsed_candidates: l3.parsed_candidates,
    fallback_reason: l3.fallback_reason,
    latency_ms: l3.latency_ms ?? rerankLatencyFallback,
    usage,
    max_tokens: l3.max_tokens ?? 0,
    temperature: l3.temperature ?? 0,
  };
  return { llm, payload_to_llm: l3.payload_to_llm, n_returned: l3.n_returned };
}

// Backend production trace → frontend Session (Replay / What-if 结果展示).
export function traceToSession(trace: BackendDebugTrace): Session {
  const meal: Meal = trace.__frozen?.meal_type === "dinner" ? "dinner" : "lunch";
  const area = zoneLabel(trace.__frozen?.zone ?? "");
  return {
    session_id: trace.session_id,
    started_at: trace.started_at,
    total_latency_ms: trace.total_latency_ms,
    ctx_latency_ms: trace.ctx_latency_ms,
    final_latency_ms: trace.final_latency_ms,
    l1: adaptL1(trace.l1, area, meal, trace.recall_latency_ms ?? 0),
    l2: adaptL2(trace.l2, trace.l1.summary.n_combos, trace.score_latency_ms ?? 0),
    l3: adaptL3(wrapTraceL3(trace.l3, trace.rerank_latency_ms ?? 0)),
    final: adaptFinal(trace.final),
    refine: {
      parent_session: trace.session_id,
      refine_session: trace.refine?.applied ? trace.session_id : "—",
      user_text: trace.refine?.user_input ?? "",
      // D-079 PR-3.1 (Codex FIX-NOW #2): 透传后端 trace.refine 全字段, 不丢.
      intent: (trace.refine?.intent as Record<string, unknown> | null | undefined) ?? null,
      n_combos_recalled: trace.refine?.n_combos_recalled ?? null,
      n_after_l2: trace.refine?.n_after_l2 ?? null,
      candidate_ids: trace.refine?.candidate_ids ?? [],
      ts: trace.refine?.ts,
      parse_feedback: {
        llm_call: {
          model: "—",
          latency_ms: 0,
          input_tokens: 0,
          output_tokens: 0,
          cache_read_input_tokens: 0,
        },
        chips_hit: [],
        note: trace.refine?.applied
          ? `refine round ${trace.refine?.round ?? "?"} applied`
          : "(尚未触发 refine)",
        rating_taste: null,
        want_again: false,
      },
      chips_to_taste_hints: { boost: {}, penalty: {} },
      infer_refine_mood: { triggered: false, hits: [], resolved_mood: {} },
      diff: { new_in_top5: [], dropped_from_top5: [], moved_up: [], moved_down: [] },
      summary_kpi: {
        explore_n: 0,
        total_latency_ms: 0,
        candidates_returned: trace.refine?.n_returned ?? 0,
        diff_top5: 0,
      },
    },
  };
}

export function backendToSession(
  raw: BackendDebugRecommend,
  opts: AdaptOptions,
): Session {
  const meal: Meal = raw.config.meal_type === "dinner" ? "dinner" : "lunch";
  const area = zoneLabel(raw.config.zone);
  return {
    session_id: opts.sessionId,
    started_at: opts.startedAt,
    total_latency_ms: opts.totalLatencyMs,
    ctx_latency_ms: 0,
    final_latency_ms: 0,
    l1: adaptL1(raw.l1_recall, area, meal),
    l2: adaptL2(raw.l2_score, raw.l1_recall.summary.n_combos),
    l3: adaptL3(raw.l3_rerank),
    final: adaptFinal(raw.final),
    // Refine trace 不在 /api/debug_recommend 返回里 — Phase 3 才有真数据.
    // 给一个空骨架, 让 panel 至少不崩.
    refine: {
      parent_session: opts.sessionId,
      refine_session: "—",
      user_text: "",
      parse_feedback: {
        llm_call: {
          model: "—", latency_ms: 0,
          input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0,
        },
        chips_hit: [],
        note: "(尚未触发 refine)",
        rating_taste: null,
        want_again: false,
      },
      chips_to_taste_hints: { boost: {}, penalty: {} },
      infer_refine_mood: { triggered: false, hits: [], resolved_mood: {} },
      diff: { new_in_top5: [], dropped_from_top5: [], moved_up: [], moved_down: [] },
      summary_kpi: {
        explore_n: 0, total_latency_ms: 0,
        candidates_returned: 0, diff_top5: 0,
      },
    },
  };
}

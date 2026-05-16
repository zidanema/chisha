// Trace tab: runs /api/debug_recommend with `trace_target` set, returns just
// the target_trace payload. Independent of the main useSession state so a trace
// query never clobbers the user's main view.

import { useCallback, useRef, useState } from "react";
import { ApiError, postDebugRecommend } from "../api/client";
import { pushToast } from "../components/Toaster";
import type { BackendTargetTrace } from "../api/backend-types";
import type { Meal } from "../types/trace";

export type TraceStatus = "idle" | "loading" | "ok" | "empty" | "error" | "offline";

export type TraceArgs = {
  restaurant: string;
  dishes: string[];
  // Must match the main session config so the trace is on the same recommendation.
  meal: Meal;
  today: string;
  profileOverride: Record<string, unknown> | null;
};

export type UseTrace = {
  trace: BackendTargetTrace | null;
  droppedStage: "l1_hard" | "l1_diversity" | "l2_only" | "final" | "none" | null;
  status: TraceStatus;
  error: string | null;
  runTrace: (args: TraceArgs) => Promise<void>;
  clearTrace: () => void;
};

function inferDroppedStage(trace: BackendTargetTrace | null): UseTrace["droppedStage"] {
  if (!trace) return null;
  if (trace.matched_dishes.length === 0) return null;
  // hard / diversity drops surface on dish-level stage field.
  if (trace.matched_dishes.some((d) => d.stage === "dropped_hard_filter")) return "l1_hard";
  if (trace.matched_dishes.some((d) => d.stage === "dropped_diversity_filter")) return "l1_diversity";
  // All matched dishes passed recall: locate where the combo died.
  if (trace.in_final) return "final";
  if (trace.matched_combos_in_ranked.length > 0) {
    const minRank = Math.min(...trace.matched_combos_in_ranked.map((c) => c.rank));
    return minRank <= 60 ? "final" : "l2_only";
  }
  return "l2_only";
}

export function useTrace(): UseTrace {
  const [trace, setTrace] = useState<BackendTargetTrace | null>(null);
  const [status, setStatus] = useState<TraceStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);

  const runTrace = useCallback(async (args: TraceArgs) => {
    const seq = ++seqRef.current;
    setStatus("loading");
    setError(null);
    try {
      const raw = await postDebugRecommend({
        meal_type: args.meal,
        today: args.today,
        // Skip LLM rerank — trace doesn't need the spend and L3 is irrelevant
        // for trace classification.
        use_llm_rerank: false,
        profile_overrides: args.profileOverride,
        trace_target: {
          restaurant_name: args.restaurant,
          dish_names: args.dishes,
        },
      });
      if (seq !== seqRef.current) return;
      const target = raw.target_trace;
      setTrace(target);
      if (!target || target.matched_dishes.length === 0) {
        setStatus("empty");
      } else {
        setStatus("ok");
      }
    } catch (err) {
      if (seq !== seqRef.current) return;
      const apiErr = err instanceof ApiError ? err : null;
      const msg = apiErr?.message ?? (err instanceof Error ? err.message : String(err));
      if (apiErr?.code === "NETWORK") {
        setStatus("offline");
        setError("后端 :8765 不可达 — 请确认 debug_server 已起。");
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
          title: `追溯失败 ${apiErr?.status ?? ""}`.trim(),
          detail: msg.slice(0, 200),
        });
      }
    }
  }, []);

  const clearTrace = useCallback(() => {
    setTrace(null);
    setStatus("idle");
    setError(null);
  }, []);

  return {
    trace,
    droppedStage: inferDroppedStage(trace),
    status,
    error,
    runTrace,
    clearTrace,
  };
}

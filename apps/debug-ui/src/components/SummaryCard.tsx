// D-085 PR-E: trace 人话层摘要 (haiku ≤ 100 字).
// 放在 DagHeader 之前 (首屏第一眼). Live / What-if mode 不渲染.
// 后端 /api/lab/sessions/{sid}/summary 缓存命中即 short-circuit, miss 调 haiku.

import { useEffect, useRef, useState } from "react";
import { fetchSessionSummary, ApiError } from "../api/client";
import type { BackendSessionSummary } from "../api/backend-types";

type State =
  | { kind: "loading" }
  | { kind: "ok"; data: BackendSessionSummary }
  | { kind: "fallback"; data: BackendSessionSummary }
  | { kind: "error"; status: number; message: string };

export type SummaryCardProps = {
  sessionId: string;
};

export function SummaryCard({ sessionId }: SummaryCardProps) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [retryNonce, setRetryNonce] = useState(0);
  // 防 sid 切换时旧请求把新状态盖掉
  const reqIdRef = useRef(0);

  useEffect(() => {
    setState({ kind: "loading" });
    const reqId = ++reqIdRef.current;
    fetchSessionSummary(sessionId)
      .then((resp) => {
        if (reqIdRef.current !== reqId) return;
        if (resp.fallback) setState({ kind: "fallback", data: resp });
        else setState({ kind: "ok", data: resp });
      })
      .catch((err) => {
        if (reqIdRef.current !== reqId) return;
        if (err instanceof ApiError) {
          setState({ kind: "error", status: err.status, message: err.message });
        } else {
          setState({
            kind: "error", status: 0,
            message: err instanceof Error ? err.message : String(err),
          });
        }
      });
  }, [sessionId, retryNonce]);

  const retry = () => setRetryNonce((n) => n + 1);

  if (state.kind === "loading") {
    return (
      <div className="summary-card summary-loading" role="status">
        <span className="sc-tag">摘要</span>
        <span className="dim">正在生成人话层摘要…</span>
      </div>
    );
  }

  if (state.kind === "ok") {
    const { text, model, cached } = state.data;
    return (
      <div className="summary-card summary-ok" role="region" aria-label="人话层摘要">
        <span className="sc-tag">摘要</span>
        <span className="sc-text">{text}</span>
        <span className="sc-meta dim mono">
          · {model ?? "haiku"} {cached ? "· cached" : "· fresh"}
        </span>
      </div>
    );
  }

  if (state.kind === "fallback") {
    const { error_kind, error_detail } = state.data;
    return (
      <div className="summary-card summary-fallback" role="status">
        <span className="sc-tag sc-tag-warn">摘要</span>
        <span className="sc-text">
          无 LLM 摘要 <span className="dim mono">({error_kind ?? "unknown"})</span> — 请展开下方技术层
        </span>
        <button className="sc-retry" onClick={retry} title={error_detail ?? ""}>
          ↻ 重试
        </button>
      </div>
    );
  }

  // hard error (404/409/500/network) — 不该常见. 4xx/5xx 显式提示.
  return (
    <div className="summary-card summary-error" role="status">
      <span className="sc-tag sc-tag-err">摘要</span>
      <span className="sc-text">
        摘要请求失败 <span className="dim mono">[{state.status}]</span> {state.message}
      </span>
      <button className="sc-retry" onClick={retry}>↻ 重试</button>
    </div>
  );
}

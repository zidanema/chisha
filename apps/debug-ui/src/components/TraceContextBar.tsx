// TraceContextBar — sticky 顶部 trace 元信息 (meal/time/source/round/top1/id-pill).

import { useState } from "react";
import type { RoundRecord, TraceMeta } from "../types/trace";

type Props = {
  trace: TraceMeta;
  round: RoundRecord | null;
  onOpenLookup: () => void;
};

export function TraceContextBar({ trace, round, onOpenLookup }: Props) {
  const [copied, setCopied] = useState(false);
  const showRefineBadge = trace.refineCount > 0;
  const shortId = trace.id.split("_").slice(-1)[0];

  function copyId() {
    setCopied(true);
    setTimeout(() => setCopied(false), 900);
    try {
      navigator.clipboard?.writeText(trace.id);
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div className="tc-bar">
      <span className={`meal ${trace.meal}`}>{trace.meal === "lunch" ? "午餐" : "晚餐"}</span>
      <span className="when">
        {trace.date} · {trace.time}
      </span>
      <span className={`src ${trace.source === "sandbox" ? "sbx" : ""}`}>
        {trace.source === "sandbox" ? `sandbox · D+${trace.sandboxDay}` : "real"}
      </span>
      {showRefineBadge && (
        <span className="rd-badge">
          {trace.latestRound} · {1 + trace.refineCount} 轮
        </span>
      )}
      {round && round.id !== "R1" && (
        <span className="rd-badge" style={{ background: "var(--ref-bg)" }}>
          当前 {round.id}
        </span>
      )}
      <span className="top1">
        <span className="lbl">final top1</span>
        {trace.finalTop1}
      </span>
      <span className="spacer"></span>
      <button
        className="id-pill"
        onClick={copyId}
        title={`session id · ${trace.id}\n点击复制`}
      >
        <span className="lbl">session</span>
        <span className="val">…{shortId}</span>
        <span className="cp">{copied ? "✓" : "⧉"}</span>
      </button>
      <div className="actions">
        <button className="ib" onClick={onOpenLookup}>
          ⌕ 追溯命中
        </button>
      </div>
    </div>
  );
}

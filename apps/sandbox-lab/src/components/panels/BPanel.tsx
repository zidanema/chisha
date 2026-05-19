// D-093 S-02 BPanel: 活跃规则 (refine + blacklist).
// D-093 决议: refine 单 round, 文案改 "当前 round 已应用 \"X\"", 不显示 TTL 倒计时.
import { useState } from "react";
import type { ActiveRule } from "../../types/sandbox";

export interface BPanelProps {
  activeRefines: ActiveRule[];
  blacklist: ActiveRule[];
}

export function BPanel({ activeRefines, blacklist }: BPanelProps) {
  const hasAny = activeRefines.length > 0 || blacklist.length > 0;
  const [open, setOpen] = useState(hasAny);
  const summary = hasAny
    ? `${activeRefines.length} refine · ${blacklist.length} blacklist`
    : "无活跃规则";

  return (
    <section className={`panel ${open ? "" : "compact"}`}>
      <header className="panel-head" onClick={() => setOpen((o) => !o)}>
        <span className="panel-key">B</span>
        <div className="panel-title">
          活跃规则 <small>当前 round</small>
        </div>
        <span className="panel-summary">{summary}</span>
        <span className="panel-chev">▾</span>
      </header>
      {open && (
        <div className="panel-body">
          {!hasAny && <div className="no-rules">无活跃规则</div>}
          {activeRefines.map((r, i) => (
            <div className="rule" key={`refine-${r.label}-${i}`}>
              <span className="icon">✎</span>
              <div className="rule-body">
                <div>
                  <span className="rule-title">当前 round 已应用: "{r.label}"</span>
                </div>
                {r.conflict && (
                  <div className="rule-conflict">
                    <span>⚠</span> 与 {r.conflict} 冲突
                  </div>
                )}
              </div>
            </div>
          ))}
          {blacklist.map((b, i) => (
            <div className="rule blacklist" key={`bl-${b.label}-${i}`}>
              <span className="icon">⊘</span>
              <div className="rule-body">
                <div>
                  <span className="rule-title">blacklist: {b.label}</span>
                </div>
                {b.reason && <div className="rule-meta">{b.reason}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

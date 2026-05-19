// D-088 S-02 CPanel: 近期窗口 (recent 4 顿 + fatigue 计数).
import { useState } from "react";
import type { FatigueEntry } from "../../types/sandbox";

export interface CPanelProps {
  recent: string[];
  fatigue: FatigueEntry[];
}

export function CPanel({ recent, fatigue }: CPanelProps) {
  const [open, setOpen] = useState(false);
  const hotCount = fatigue.filter((f) => f.hot).length;
  const summary = `最近 ${recent.length} 顿 · ${hotCount} 项疲劳`;

  return (
    <section className={`panel ${open ? "" : "compact"}`}>
      <header className="panel-head" onClick={() => setOpen((o) => !o)}>
        <span className="panel-key">C</span>
        <div className="panel-title">
          近期窗口 <small>变化快</small>
        </div>
        <span className="panel-summary">{summary}</span>
        <span className="panel-chev">▾</span>
      </header>
      {open && (
        <div className="panel-body">
          <div className="recent-line">
            <span className="recent-label">最近 {recent.length} 顿:</span>
            {recent.map((r, i, arr) => (
              <span key={`${r}-${i}`} className="recent-cell">
                <span className={`dish ${i === arr.length - 1 ? "latest" : ""}`}>
                  {r}
                </span>
                {i < arr.length - 1 && <span className="sep">›</span>}
              </span>
            ))}
          </div>
          <div className="fatigue-head">fatigue 计数:</div>
          <div className="fatigue-table">
            {fatigue.map((f) => (
              <span key={f.name} className="fatigue-entry">
                <span className="nm">{f.name}</span>
                <span className={`v ${f.hot ? "hot" : ""} mono`}>×{f.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

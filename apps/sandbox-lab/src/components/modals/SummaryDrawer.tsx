// D-093 S-02 SummaryDrawer: history 摘要侧抽屉, filter chips + 跳 trace.
import { useState } from "react";
import { SummaryFlagBadges } from "../FlagBadges";
import type { Meal } from "../../types/sandbox";

const FILTERS: { id: string; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "refine", label: "refine 过" },
  { id: "conflict", label: "冲突过" },
  { id: "event", label: "L1 抽取过" },
  { id: "skip", label: "跳过" },
];

export interface SummaryDrawerProps {
  open: boolean;
  history: Meal[];
  total: number;
  sessionName: string;
  onClose?: () => void;
  onOpenTrace?: (meal: Meal) => void;
}

export function SummaryDrawer({
  open,
  history,
  total,
  sessionName,
  onClose,
  onOpenTrace,
}: SummaryDrawerProps) {
  const [filter, setFilter] = useState("all");

  const filtered = history.filter((h) => {
    if (filter === "all") return true;
    if (filter === "skip") return h.state === "skip";
    return h.flags?.includes(filter as never);
  });

  return (
    <>
      <div
        className={`drawer-mask ${open ? "open" : ""}`}
        onClick={onClose}
      />
      <aside className={`drawer ${open ? "open" : ""}`}>
        <header className="drawer-head">
          <div>
            <div className="dt">Session 摘要</div>
            <div className="dsub">
              {sessionName} · 已 {history.length}/{total} 顿
            </div>
          </div>
          <button className="x" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="drawer-body">
          <div className="summary-filter">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                className={`chip ${filter === f.id ? "on" : ""}`}
                onClick={() => setFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>
          {filtered.map((h) => (
            <div
              className="summary-row"
              key={h.idx}
              onClick={() => onOpenTrace?.(h)}
            >
              <span className="when mono">
                D{h.day} {h.slot}
              </span>
              <span className={`cell-mini ${h.state}`}>
                {h.state === "eat" ? "✓" : "⊘"}
              </span>
              <span className="name">
                <span>{h.state === "eat" ? h.dish : "跳过"}</span>
                <SummaryFlagBadges flags={h.flags} />
              </span>
              <span className="open">打开 trace ›</span>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="summary-empty">没有匹配的顿次</div>
          )}
        </div>
      </aside>
    </>
  );
}

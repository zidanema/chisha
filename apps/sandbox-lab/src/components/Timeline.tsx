// D-093 S-02 Timeline: 14 格横向条 / 日历卡 + OpBar (内部 helper).
// 本任务 onSelect 是 inert prop (App 喂 () => {}), 静态视觉演示.
import type { Meal, Tweaks } from "../types/sandbox";
import { TimelineFlagBadges } from "./FlagBadges";

export interface TimelineProps {
  history: Meal[];
  currentIdx: number;
  total: number;
  selected: number | null;
  onSelect?: (idx: number) => void;
  variant: Tweaks["timelineVariant"];
}

interface CellData {
  idx: number;
  day: number;
  slot: "午" | "晚";
  state: "eat" | "skip" | "current" | "future";
  past?: Meal;
}

export function Timeline({
  history,
  currentIdx,
  total,
  selected,
  onSelect,
  variant,
}: TimelineProps) {
  const cells: CellData[] = [];
  for (let i = 0; i < total; i++) {
    const past = history.find((h) => h.idx === i);
    let state: CellData["state"] = "future";
    if (past) state = past.state === "eat" ? "eat" : "skip";
    if (i === currentIdx) state = "current";
    cells.push({
      idx: i,
      day: Math.floor(i / 2) + 1,
      slot: i % 2 === 0 ? "午" : "晚",
      state,
      past,
    });
  }

  const days: { day: number; cells: CellData[] }[] = [];
  for (let i = 0; i < cells.length; i += 2) {
    days.push({ day: cells[i].day, cells: cells.slice(i, i + 2) });
  }

  return (
    <div className={`timeline ${variant === "calendar" ? "calendar" : ""}`}>
      <div className="timeline-head">
        <span className="key">TIMELINE · 时间轴</span>
        <span className="progress mono">
          {currentIdx}/{total} 顿 · 剩余 {total - currentIdx}
        </span>
      </div>
      <div className="timeline-row">
        {days.map((d) => (
          <div className="day-group" key={d.day}>
            <div className="day-cells">
              {d.cells.map((c) => (
                <Cell
                  key={c.idx}
                  cell={c}
                  isSelected={selected === c.idx}
                  onClick={() => {
                    if (c.state === "future") return;
                    onSelect?.(c.idx);
                  }}
                />
              ))}
            </div>
            <div className="day-label">D{d.day} · 午 · 晚</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Cell({
  cell,
  isSelected,
  onClick,
}: {
  cell: CellData;
  isSelected: boolean;
  onClick: () => void;
}) {
  const flags = cell.past?.flags ?? [];
  const glyph =
    cell.state === "eat"
      ? "✓"
      : cell.state === "skip"
        ? "⊘"
        : cell.state === "current"
          ? "←"
          : "·";
  const title = cell.past
    ? `D${cell.day} ${cell.slot} · ${cell.past.dish}`
    : `D${cell.day} ${cell.slot}`;
  return (
    <div
      className={`cell ${cell.state} ${isSelected ? "selected" : ""}`}
      onClick={onClick}
      title={title}
      data-screen-label={`timeline-cell-${cell.idx}`}
    >
      <span className="cell-icon">{glyph}</span>
      <TimelineFlagBadges flags={flags} />
    </div>
  );
}

export interface OpBarProps {
  selected: number | null;
  history: Meal[];
  onTrace?: () => void;
  onRollback?: () => void;
  onBranch?: () => void;
  onDismiss?: () => void;
}

export function OpBar({
  selected,
  history,
  onTrace,
  onRollback,
  onBranch,
  onDismiss,
}: OpBarProps) {
  if (selected === null) {
    return (
      <div className="op-bar hidden">
        <span className="op-context">单击时间轴格 查看 / 回滚 / 分支</span>
      </div>
    );
  }
  const meal = history.find((h) => h.idx === selected);
  if (!meal) return <div className="op-bar hidden" />;

  return (
    <div className="op-bar">
      <span className="op-context">
        已选{" "}
        <strong>
          D{meal.day} {meal.slot}
        </strong>{" "}
        · {meal.state === "eat" ? meal.dish : "跳过"}
      </span>
      <button className="op-btn" onClick={onTrace}>
        🔍 打开 trace
      </button>
      <button className="op-btn danger" onClick={onRollback}>
        ↶ 回滚到此处
      </button>
      <button className="op-btn" onClick={onBranch}>
        ⌥ 从此处分支
      </button>
      <button className="op-dismiss" onClick={onDismiss} title="取消选中 (Esc)">
        ✕ 取消
      </button>
    </div>
  );
}

// D-093 S-02 DecisionArea: 决策模式左列.
// 本任务 callbacks inert (S-03 接 useSandbox); input 内部 controlled state, 无 submit 逻辑.
import { useState } from "react";
import type { Clock, Rec } from "../types/sandbox";
import { RecCard } from "./RecCard";

const PRESETS = [
  "想吃辣的",
  "换日料",
  "来份烧烤",
  "想吃牛肉",
  "来盖饭",
  "换粤菜",
];

export interface DecisionAreaProps {
  recs: Rec[];
  selectedRank: number;
  onSelectRank?: (r: number) => void;
  onEat?: (r: Rec) => void;
  onSwap?: () => void;
  onRefine?: (text: string) => void;
  onSkip?: () => void;
  showDebug: boolean;
  clock: Clock;
}

export function DecisionArea({
  recs,
  selectedRank,
  onSelectRank,
  onEat,
  onSwap,
  onRefine,
  onSkip,
  showDebug,
  clock,
}: DecisionAreaProps) {
  const [refineText, setRefineText] = useState("");

  function handleRefineSubmit() {
    if (refineText.trim()) {
      onRefine?.(refineText.trim());
      setRefineText("");
    } else {
      onSwap?.();
    }
  }

  return (
    <div className="col col-left">
      <div className="col-head">
        <div className="h-title">这一顿 · 决策</div>
        <div className="h-sub">
          D{clock.day}
          {clock.slot} · 5 条推荐
        </div>
      </div>

      <div className="rec-list">
        {recs.map((r) => (
          <RecCard
            key={r.rank}
            rec={r}
            selected={selectedRank === r.rank}
            showDebug={showDebug}
            onSelect={() => onSelectRank?.(r.rank)}
            onEat={() => onEat?.(r)}
          />
        ))}
      </div>

      <div className="refine-block">
        <div className="refine-head">不喜欢? 换个口味试试</div>
        <div className="refine-row">
          <span className="refine-chev">›</span>
          <input
            className="refine-input"
            placeholder="或者,告诉我你今天想要什么…"
            value={refineText}
            onChange={(e) => setRefineText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleRefineSubmit();
            }}
          />
          <button className="refine-submit" onClick={handleRefineSubmit}>
            换一组
          </button>
        </div>
        <div className="preset-row">
          <span className="preset-label">或者直接点 ›</span>
          {PRESETS.map((p) => (
            <button
              key={p}
              className="preset-chip"
              onClick={() => onRefine?.(p)}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <button className="skip-footer" onClick={onSkip}>
        → 这顿吃别的, 跳过 →
      </button>
    </div>
  );
}

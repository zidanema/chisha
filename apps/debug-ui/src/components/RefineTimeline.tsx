// RefineTimeline — git-compare 横条 (R1...Rn 节点 + base/target 选择 + diff 模式).
// click=setTarget, shift/alt/cmd-click=setBase, right-click=setBase.
// 1:1 port chisha-debug/project/wa-refine.jsx RefineTimeline.

import type { MouseEvent } from "react";
import type { RoundRecord } from "../types/trace";

type DiffMode = "vs_r1" | "adjacent";

type Props = {
  rounds: RoundRecord[];
  base: string;
  target: string;
  setBase: (id: string) => void;
  setTarget: (id: string) => void;
  onSwap: () => void;
  diffMode: DiffMode;
  setDiffMode: (m: DiffMode) => void;
};

export function RefineTimeline({
  rounds, base, target, setBase, setTarget, onSwap, diffMode, setDiffMode,
}: Props) {
  if (!rounds || rounds.length <= 1) return null;
  const baseIdx = rounds.findIndex((r) => r.id === base);
  const targetIdx = rounds.findIndex((r) => r.id === target);
  const safeBaseIdx = baseIdx < 0 ? 0 : baseIdx;
  const safeTargetIdx = targetIdx < 0 ? rounds.length - 1 : targetIdx;
  const minIdx = Math.min(safeBaseIdx, safeTargetIdx);
  const maxIdx = Math.max(safeBaseIdx, safeTargetIdx);

  const targetRound = rounds[safeTargetIdx];
  const stats = targetRound.diff
    ? {
        up: targetRound.diff.in,
        down: targetRound.diff.out,
        neu: targetRound.diff.up + targetRound.diff.down,
      }
    : { up: 0, down: 0, neu: 0 };

  function nodeLeft(i: number): string {
    if (rounds.length === 1) return "50%";
    return `${(i / (rounds.length - 1)) * 100}%`;
  }

  function handleClick(e: MouseEvent, idx: number) {
    if (e.shiftKey || e.altKey || e.metaKey) {
      setBase(rounds[idx].id);
    } else {
      setTarget(rounds[idx].id);
    }
  }

  function handleContext(e: MouseEvent, idx: number) {
    e.preventDefault();
    setBase(rounds[idx].id);
  }

  return (
    <div className="rt">
      <div className="rt-bar">
        <span className="lbl">compare</span>
        <span className="compare-box">
          <span className="base">{rounds[safeBaseIdx].id}</span>
          <span className="arrow">→</span>
          <span className="target">{rounds[safeTargetIdx].id}</span>
        </span>
        <button className="swap" onClick={onSwap} title="交换 base / target">⇄ swap</button>
        <div className="diff-mode-toggle" title="diff 基线选择模式">
          <button
            className={diffMode === "vs_r1" ? "on" : ""}
            onClick={() => setDiffMode("vs_r1")}
          >
            vs R1
          </button>
          <button
            className={diffMode === "adjacent" ? "on" : ""}
            onClick={() => setDiffMode("adjacent")}
          >
            相邻
          </button>
        </div>
        <span className="diff-stats">
          <span className="up">+{stats.up} 新进</span>
          <span className="down">−{stats.down} 踢出</span>
          <span className="neu">~{stats.neu} 位次</span>
        </span>
      </div>
      <div className="rt-track">
        <div className="axis"></div>
        <div
          className="range"
          style={{
            left: `calc(${(minIdx / (rounds.length - 1)) * 100}% + 6px)`,
            right: `calc(${((rounds.length - 1 - maxIdx) / (rounds.length - 1)) * 100}% + 6px)`,
          }}
        ></div>
        <div className="nodes">
          {rounds.map((r, i) => {
            const isBase = r.id === base;
            const isTarget = r.id === target;
            return (
              <div
                key={r.id}
                className={`rt-node ${isBase ? "is-base" : ""} ${isTarget ? "is-target" : ""}`}
                style={{ left: nodeLeft(i), top: 0 }}
                onClick={(e) => handleClick(e, i)}
                onContextMenu={(e) => handleContext(e, i)}
                title={r.user_input || r.label}
              >
                <span className="lbl">{r.id}</span>
                <span className="ball"></span>
                <span className="when">{r.started_at}</span>
                <span className="role"></span>
                <span className="desc">{r.label}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="rt-legend">
        <span className="hint">
          点节点切轮次 (target) · shift/⌘-click 切 base · 右键 = base · 上方 toggle 决定 base 算法
        </span>
      </div>
    </div>
  );
}

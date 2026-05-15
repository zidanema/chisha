import { Fragment } from "react";
import { cx } from "@/lib/cx";

export interface RefineHistoryEntry {
  round: number;
  text: string;
}

// D-051: 横向面包屑放在卡片正上方，让因果链空间紧邻。
// chain = [{round:1, text:"原推荐"}, ...history]。点 chip 回滚到那一轮。
export function RefineCrumb({
  history,
  currentRound,
  onJumpRound,
  onReset,
}: {
  history: RefineHistoryEntry[];
  currentRound: number | undefined;
  onJumpRound: (round: number) => void;
  onReset: () => void;
}) {
  if (!history || history.length === 0) return null;
  const chain = [
    { round: 1, text: "原推荐", isOrigin: true },
    ...history.map((h) => ({ round: h.round, text: h.text, isOrigin: false })),
  ];
  const activeIdx = chain.findIndex((c) => c.round === currentRound);

  return (
    <div className="mb-3 rounded-md border border-dashed border-[color:var(--border)] bg-[color:var(--surface)]/60 px-3 py-2">
      <div className="flex items-baseline justify-between gap-3 mb-1.5">
        <span className="text-[11.5px] text-[color:var(--muted)]">
          已根据你的要求换了{" "}
          <span className="tabular-nums text-[color:var(--fg)]">{history.length}</span> 次
        </span>
        <button
          onClick={onReset}
          className="text-[11.5px] text-[color:var(--muted)] hover:text-[color:var(--fg)] inline-flex items-center gap-1"
        >
          <span aria-hidden="true">↺</span>重置
        </button>
      </div>
      <div className="flex items-center gap-1 flex-wrap">
        {chain.map((c, i) => {
          const active = i === activeIdx;
          return (
            <Fragment key={`${c.round}-${i}`}>
              {i > 0 && (
                <span
                  aria-hidden="true"
                  className="text-[color:var(--muted)] text-[12px] px-0.5"
                >
                  ›
                </span>
              )}
              <button
                onClick={() => onJumpRound(c.round)}
                className={cx(
                  "text-[12px] px-2 py-0.5 rounded-md border transition-colors",
                  active
                    ? "border-[color:var(--accent)] text-[color:var(--accent)] bg-[color:var(--accent-bg)] font-medium"
                    : c.isOrigin
                    ? "border-[color:var(--border)] text-[color:var(--muted)] hover:text-[color:var(--fg)]"
                    : "border-[color:var(--border)] text-[color:var(--fg)] hover:border-[color:var(--accent)]"
                )}
              >
                {c.text}
                {active && <span className="ml-1 opacity-70">· 这一轮</span>}
              </button>
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}

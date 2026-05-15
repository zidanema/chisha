import { useState } from "react";
import { LABELS } from "@/lib/labels";
import type { SkipReason } from "@/lib/types";

// D-052: escape hatch — 不是所有打开都以"点外卖"结束。
// Default collapsed (一行小灰字), 点开 6 chip + 不说原因兜底。
export function SkipMealAction({
  onSkip,
  disabled,
}: {
  onSkip: (reason: SkipReason) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <div className="mt-6 flex items-center justify-center">
        <button
          onClick={() => setOpen(true)}
          disabled={disabled}
          className="text-[12px] text-[color:var(--muted)] hover:text-[color:var(--fg)] inline-flex items-center gap-1.5 px-2 py-1 rounded-md disabled:opacity-40"
        >
          <span aria-hidden="true">⤳</span>
          {LABELS.ui.skipCta}
        </button>
      </div>
    );
  }

  return (
    <div className="mt-6 rounded-md border border-dashed border-[color:var(--border)] bg-[color:var(--surface)]/60 px-4 py-3">
      <div className="flex items-baseline gap-2 mb-2.5">
        <span className="text-[13px] text-[color:var(--fg)]">{LABELS.ui.skipPromptT}</span>
        <span className="text-[11.5px] text-[color:var(--muted)]">
          {LABELS.ui.skipPromptHint}
        </span>
        <button
          onClick={() => setOpen(false)}
          aria-label="关闭"
          className="ml-auto text-[12px] text-[color:var(--muted)] hover:text-[color:var(--fg)] leading-none"
        >
          ✕
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {LABELS.skipReasons.map((r) => (
          <button
            key={r.id}
            onClick={() => onSkip(r.id)}
            disabled={disabled}
            className="text-[12.5px] px-2.5 py-1 rounded-md border border-[color:var(--border)] text-[color:var(--fg)] hover:border-[color:var(--accent)] hover:bg-[color:var(--accent-bg)] disabled:opacity-40"
          >
            {r.label}
          </button>
        ))}
        <button
          onClick={() => onSkip(null)}
          disabled={disabled}
          className="ml-auto text-[11.5px] text-[color:var(--muted)] hover:text-[color:var(--fg)] underline-offset-2 hover:underline disabled:opacity-40"
        >
          {LABELS.ui.skipNoReason}
        </button>
      </div>
    </div>
  );
}

export function SkippedState({
  reason,
  onUndo,
}: {
  reason: SkipReason;
  onUndo: () => void;
}) {
  const map = Object.fromEntries(LABELS.skipReasons.map((r) => [r.id, r.label]));
  const reasonLabel = reason && map[reason];
  return (
    <div className="mt-6 rounded-lg border border-dashed border-[color:var(--border)] bg-[color:var(--surface)]/60 px-6 py-10 text-center">
      <div className="text-[15px] font-semibold tracking-tight mb-1">
        {LABELS.ui.skipDone}
      </div>
      <div className="text-[12.5px] text-[color:var(--muted)] mb-4">
        {reasonLabel ? (
          <>
            已记录原因「<span className="text-[color:var(--fg)]">{reasonLabel}</span>」 ·{" "}
          </>
        ) : null}
        {LABELS.ui.skipDoneByeline}
      </div>
      <button
        onClick={onUndo}
        className="text-[12.5px] inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-[color:var(--border)] hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
      >
        <span aria-hidden="true">↺</span>
        {LABELS.ui.skipUndo}
      </button>
    </div>
  );
}

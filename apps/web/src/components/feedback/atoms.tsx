// Shared atoms for feedback form + detail view (D-063~063 alignment renderers).
import type { Candidate } from "@/lib/types";
import type { DimVal } from "@/lib/types";
import { LABELS } from "@/lib/labels";
import { cx } from "@/lib/cx";

export function clipReason(reason?: string | null): string {
  if (!reason) return "（无推荐理由）";
  const s = String(reason).replace(/^[💬\s]+/, "").trim();
  return s.length > 50 ? s.slice(0, 50) + "…" : s;
}

export function ProteinPred({ g }: { g: number }) {
  const tone = g < 30 ? "bad" : g > 45 ? "good" : "muted";
  const labelMap: Record<typeof tone, string> = {
    bad: "偏低",
    good: "充足",
    muted: "适中",
  };
  return (
    <span
      className="text-[12.5px]"
      style={{ color: tone === "muted" ? "var(--fg)" : `var(--${tone})` }}
    >
      <span className="tabular-nums">{g}g</span>{" "}
      <span className="text-[11px] opacity-70">{labelMap[tone]}</span>
    </span>
  );
}

export function OilPred({ level }: { level: number }) {
  const tone = level <= 2 ? "good" : level >= 4 ? "bad" : "muted";
  return (
    <span
      className="text-[12.5px]"
      style={{ color: tone === "muted" ? "var(--fg)" : `var(--${tone})` }}
    >
      <span className="tabular-nums">{level}/5</span>
    </span>
  );
}

export function relAgo(iso: string | undefined | null): string {
  const t = iso ? new Date(iso).getTime() : NaN;
  if (!t || Number.isNaN(t)) return "";
  const mins = Math.max(1, Math.round((Date.now() - t) / 60000));
  return LABELS.ui.inboxAgo(mins);
}

export const GUT_OPTIONS: {
  v: -1 | 0 | 1;
  icon: string;
  labelKey: "fbARatingBad" | "fbARatingOk" | "fbARatingGood";
}[] = [
  { v: -1, icon: "👎", labelKey: "fbARatingBad" },
  { v: 0, icon: "😐", labelKey: "fbARatingOk" },
  { v: 1, icon: "👍", labelKey: "fbARatingGood" },
];

// Used by both ProgressiveForm and FeedbackDetailView so the layout matches.
export type DimRowSpec = {
  id: "reason" | "fullness" | "oil" | "repeat";
  label: string;
  pred: React.ReactNode;
  opts: string[];
};

export function buildDimRows(candidate: Candidate | null | undefined): DimRowSpec[] {
  const eDim = LABELS.ui.fbEDim;
  const c = candidate || ({} as Partial<Candidate>);
  const hasProtein = c.estimated_total_protein_g != null;
  const hasOil = c.estimated_total_oil != null;

  const rows: (DimRowSpec | false)[] = [
    {
      id: "reason",
      label: eDim.reason.label,
      pred: (
        <span className="text-[12px] text-[color:var(--fg)] leading-snug">
          {clipReason(c.reason_one_line)}
        </span>
      ),
      opts: eDim.reason.opts,
    },
    hasProtein && {
      id: "fullness",
      label: eDim.fullness.label,
      pred: <ProteinPred g={c.estimated_total_protein_g as number} />,
      opts: eDim.fullness.opts,
    },
    hasOil && {
      id: "oil",
      label: eDim.oil.label,
      pred: <OilPred level={c.estimated_total_oil as number} />,
      opts: eDim.oil.opts,
    },
    {
      id: "repeat",
      label: eDim.repeat.label,
      pred: <span className="text-[12px] text-[color:var(--muted)] opacity-50">—</span>,
      opts: eDim.repeat.opts,
    },
  ];

  return rows.filter((x): x is DimRowSpec => Boolean(x));
}

type DimsState = Record<DimRowSpec["id"], DimVal>;

export function DimTable({
  rows,
  mode,
  values,
  onPick,
}: {
  rows: DimRowSpec[];
  mode: "edit" | "readonly";
  values: DimsState;
  onPick?: (id: DimRowSpec["id"], value: DimVal) => void;
}) {
  return (
    <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] overflow-hidden">
      <div className="grid grid-cols-[78px,1fr,160px] px-4 py-2 border-b border-[color:var(--border)] bg-[color:var(--surface-2)]/30 gap-3 items-baseline">
        <div />
        <div className="text-[10.5px] uppercase tracking-wider text-[color:var(--muted)]">
          {LABELS.ui.fbEColPrediction}
        </div>
        <div
          className="text-[10.5px] uppercase tracking-wider"
          style={{ color: "var(--accent)" }}
        >
          {LABELS.ui.fbEColReality}
        </div>
      </div>

      {rows.map((r) => (
        <div
          key={r.id}
          className="grid grid-cols-[78px,1fr,160px] px-4 py-3 border-b border-[color:var(--border)] last:border-b-0 items-center gap-3"
        >
          <div className="text-[12.5px] text-[color:var(--fg)]">{r.label}</div>
          <div className="pr-2 min-w-0">{r.pred}</div>
          <div className="inline-flex rounded-md border border-[color:var(--border)] overflow-hidden">
            {r.opts.map((o, i) => {
              const value = i as DimVal;
              const active = values[r.id] === value;
              const commonClass = cx(
                "flex-1 px-2 py-1 text-[12px] border-l first:border-l-0 whitespace-nowrap",
                active ? "font-medium" : "text-[color:var(--muted)]",
              );
              const style = {
                borderLeftColor: "var(--border)",
                background: active ? "var(--accent-bg)" : "transparent",
                color: active ? "var(--accent)" : undefined,
              };
              return mode === "edit" ? (
                <button
                  key={o}
                  onClick={() => onPick?.(r.id, active ? null : value)}
                  className={cx(
                    commonClass,
                    "transition-colors",
                    !active && "hover:text-[color:var(--fg)] hover:bg-[color:var(--surface-2)]",
                  )}
                  style={style}
                >
                  {o}
                </button>
              ) : (
                <div
                  key={o}
                  className={cx(commonClass, "select-none text-center", !active && "opacity-40")}
                  style={style}
                >
                  {o}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

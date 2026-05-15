// Shared atoms for feedback form + detail view (D-063~063 alignment renderers).
import type { Candidate } from "@/lib/types";
import { LABELS } from "@/lib/labels";

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

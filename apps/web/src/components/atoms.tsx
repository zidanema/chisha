import type { IngredientKind } from "@/lib/types";
import { LABELS } from "@/lib/labels";

export function ProteinLabel({ g }: { g: number }) {
  let color = "var(--fg)";
  if (g < 30) color = "var(--bad)";
  else if (g > 45) color = "var(--good)";
  return (
    <span className="tabular-nums" style={{ color }}>
      蛋白 {g}g
    </span>
  );
}

export function OilLabel({ level }: { level: number }) {
  let color = "var(--fg)";
  if (level <= 2) color = "var(--good)";
  else if (level >= 4) color = "var(--bad)";
  return (
    <span className="tabular-nums" style={{ color }}>
      油 {level.toFixed(1)}
      <span className="opacity-50">/5</span>
    </span>
  );
}

const HEALTH_BADGE_MAP = {
  veg_ok: { label: "蔬菜", tone: "good" as const },
  protein_ok: { label: "蛋白", tone: "good" as const },
  oil_ok: { label: "控油", tone: "good" as const },
  wetness: { label: "带汤水", tone: "info" as const },
  processed_meat: { label: "加工肉", tone: "bad" as const },
  sweet_sauce: { label: "甜酱", tone: "bad" as const },
};
type HealthBadgeKey = keyof typeof HEALTH_BADGE_MAP;

export function HealthFlagBadge({ k, value }: { k: HealthBadgeKey; value: boolean }) {
  if (!value) return null;
  const cfg = HEALTH_BADGE_MAP[k];
  if (!cfg) return null;
  const cls =
    cfg.tone === "good" ? "chip-good" : cfg.tone === "bad" ? "chip-bad" : "chip-info";
  return (
    <span className={`chip ${cls}`}>
      <span aria-hidden="true">✓</span>
      {cfg.label}
    </span>
  );
}

export function RiskChip({ label }: { label: string }) {
  return <span className="chip chip-bad">! {label}</span>;
}

export function ExploreChip() {
  return <span className="chip chip-accent">⌖ 探索</span>;
}

export function IngredientTag({ kind }: { kind: IngredientKind | string }) {
  const color = LABELS.ingredientColor[kind as IngredientKind] || "var(--muted)";
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] px-1.5 py-[1px] rounded-sm font-medium"
      style={{
        background: `color-mix(in oklch, ${color} 18%, transparent)`,
        color,
      }}
    >
      {kind}
    </span>
  );
}

export function MiniProgress({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  const pct = Math.max(0, Math.min(1, value));
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[11px] text-[color:var(--muted)] uppercase tracking-wider">
          {label}
        </span>
        <span className="text-[12px] tabular-nums" style={{ color: "var(--fg)" }}>
          {value.toFixed(2)}
        </span>
      </div>
      <div
        className="h-[3px] w-full rounded-full"
        style={{ background: "var(--surface-2)" }}
      >
        <div
          className="h-full rounded-full"
          style={{ width: `${pct * 100}%`, background: accent }}
        />
      </div>
    </div>
  );
}

export function SectionHeader({
  title,
  hint,
  right,
}: {
  title: string;
  hint?: string | null;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-3 mb-3 pb-1.5 border-b border-[color:var(--border)]">
      <h2 className="text-[15px] font-semibold tracking-tight whitespace-nowrap">
        {title}
      </h2>
      {hint && (
        <span className="text-[12px] text-[color:var(--muted)] whitespace-nowrap overflow-hidden text-ellipsis">
          {hint}
        </span>
      )}
      {right && <div className="ml-auto whitespace-nowrap">{right}</div>}
    </div>
  );
}

export function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad" | null;
}) {
  const color =
    tone === "good" ? "var(--good)" : tone === "bad" ? "var(--bad)" : "var(--fg)";
  return (
    <div className="rounded-md border border-[color:var(--border)] px-2.5 py-1.5">
      <div className="text-[10.5px] text-[color:var(--muted)] uppercase tracking-wider">
        {label}
      </div>
      <div className="text-[14px] tabular-nums font-medium" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

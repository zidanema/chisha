import { useEffect } from "react";
import { LABELS } from "@/lib/labels";
import type { Candidate } from "@/lib/types";
import {
  ExploreChip,
  IngredientTag,
  MiniProgress,
  RiskChip,
  Stat,
} from "./atoms";

export function DetailPanel({
  candidate,
  onClose,
  onPick,
}: {
  candidate: Candidate | null;
  onClose: () => void;
  onPick: (c: Candidate) => void;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (!candidate) return null;
  const c = candidate;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div
        className="relative w-full max-w-[600px] max-h-[88vh] overflow-y-auto rounded-lg bg-[color:var(--bg)] border border-[color:var(--border)] shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-[color:var(--bg)] border-b border-[color:var(--border)] px-5 py-3 flex items-baseline justify-between">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[11px] text-[color:var(--muted)]">#{c.rank}</span>
            <h3 className="text-[15px] font-semibold">{c.restaurant.name}</h3>
            {c.is_explore && <ExploreChip />}
          </div>
          <button onClick={onClose} className="text-[12px] text-[color:var(--muted)]">
            关闭 ✕
          </button>
        </div>

        <div className="p-5 space-y-5">
          <p
            className="text-[13px] text-[color:var(--muted)] leading-relaxed"
            style={{ textWrap: "pretty" } as React.CSSProperties}
          >
            <span className="text-[color:var(--accent)] mr-1">💬</span>
            {c.reason_one_line}
          </p>

          <div>
            <div className="text-[11px] text-[color:var(--muted)] uppercase tracking-wider mb-2">
              {LABELS.ui.detailDishes}
            </div>
            <ul className="rounded-md border border-[color:var(--border)] overflow-hidden divide-y divide-[color:var(--border)]">
              {c.dishes.map((d) => (
                <li key={d.dish_id} className="p-3 flex items-center gap-3">
                  <span className="flex-1 min-w-0">
                    <span className="text-[13.5px] block truncate">{d.canonical_name}</span>
                    <span className="font-mono text-[10.5px] text-[color:var(--muted)]">
                      {d.dish_id}
                    </span>
                  </span>
                  <IngredientTag kind={d.main_ingredient_type} />
                  <span
                    className="text-[12px] tabular-nums"
                    style={{
                      color:
                        d.oil_level <= 2
                          ? "var(--good)"
                          : d.oil_level >= 4
                          ? "var(--bad)"
                          : "var(--fg)",
                    }}
                  >
                    油 {d.oil_level}
                  </span>
                  <span className="text-[13px] tabular-nums w-14 text-right">
                    ¥{d.price.toFixed(1)}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="价格" value={`¥${c.total_price.toFixed(1)}`} />
            <Stat label="送达" value={`${c.restaurant.eta_min}min`} />
            <Stat
              label="距离"
              value={`${(c.restaurant.distance_m / 1000).toFixed(1)}km`}
            />
            <Stat
              label="蛋白"
              value={`${c.estimated_total_protein_g}g`}
              tone={
                c.estimated_total_protein_g < 30
                  ? "bad"
                  : c.estimated_total_protein_g > 45
                  ? "good"
                  : null
              }
            />
          </div>

          {c.fit_score != null && c.taste_match != null && (
            <div>
              <div className="text-[11px] text-[color:var(--muted)] uppercase tracking-wider mb-2">
                {LABELS.ui.detailMatch}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <MiniProgress label="健康契合" value={c.fit_score} accent="var(--accent)" />
                <MiniProgress label="口味契合" value={c.taste_match} accent="var(--accent)" />
              </div>
            </div>
          )}

          {c.risk_flags && c.risk_flags.length > 0 && (
            <div>
              <div className="text-[11px] text-[color:var(--muted)] uppercase tracking-wider mb-2">
                {LABELS.ui.detailRisks}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {c.risk_flags.map((r) => (
                  <RiskChip key={r} label={r} />
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="sticky bottom-0 bg-[color:var(--bg)] border-t border-[color:var(--border)] px-5 py-3 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-md border border-[color:var(--border)] text-[13px]"
          >
            关闭
          </button>
          <button
            onClick={() => onPick(c)}
            className="px-3 py-1.5 rounded-md text-[13px] font-medium"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            {LABELS.ui.pickThis} →
          </button>
        </div>
      </div>
    </div>
  );
}

import { LABELS } from "@/lib/labels";
import { cx } from "@/lib/cx";
import type { Candidate } from "@/lib/types";
import {
  ExploreChip,
  HealthFlagBadge,
  OilLabel,
  ProteinLabel,
  RiskChip,
} from "./atoms";

export type RecCardMode = "decision" | "review";

export interface RecCardProps {
  candidate: Candidate;
  mode?: RecCardMode;
  // decision mode (homepage)
  pickedRank?: number | null;
  onPick?: (c: Candidate) => void;
  onUnpick?: () => void;
  onDetail?: (c: Candidate) => void;
  // review mode (feedback)
  checked?: boolean;
  onSelect?: (rank: number) => void;
}

// D-050: pick = inline 持久锁定（边框 + ✓ 已选 + 改主意），不是 toast。
// 非 picked 卡片淡化（opacity 0.55），按钮转次级"选这个"。
export function RecCard({
  candidate,
  mode = "decision",
  pickedRank,
  onPick,
  onUnpick,
  onDetail,
  checked,
  onSelect,
}: RecCardProps) {
  const c = candidate;
  const isReview = mode === "review";
  const someonePicked = !isReview && pickedRank != null;
  const isPicked = someonePicked && c.rank === pickedRank;
  const isDimmed = someonePicked && c.rank !== pickedRank;

  const onCardKey =
    isReview && onSelect
      ? (e: React.KeyboardEvent<HTMLElement>) => {
          if (e.key === " " || e.key === "Enter") {
            e.preventDefault();
            onSelect(c.rank);
          }
        }
      : undefined;

  return (
    <article
      onClick={isReview && onSelect ? () => onSelect(c.rank) : undefined}
      role={isReview ? "radio" : undefined}
      aria-checked={isReview ? !!checked : undefined}
      tabIndex={isReview ? 0 : undefined}
      onKeyDown={onCardKey}
      className={cx(
        "rec-card rounded-lg border bg-[color:var(--surface)] transition-all",
        isReview && "cursor-pointer",
        isReview && checked
          ? "border-[color:var(--accent)]"
          : isReview
          ? "border-[color:var(--border)]"
          : isPicked
          ? "border-[color:var(--accent)]"
          : someonePicked
          ? "border-[color:var(--border)]"
          : "border-[color:var(--border)] hover:border-[color:var(--fg)]",
        isDimmed && "opacity-55"
      )}
      style={
        (isReview && checked) || isPicked
          ? {
              boxShadow: "0 0 0 1px var(--accent) inset",
              background: "color-mix(in srgb, var(--accent) 5%, var(--surface))",
            }
          : undefined
      }
    >
      <div className="p-4 flex gap-3">
        {isReview && (
          <span
            className="shrink-0 mt-1 inline-flex items-center justify-center w-4 h-4 rounded-full border-2 transition-colors"
            style={{
              borderColor: checked ? "var(--accent)" : "var(--border)",
              background: checked ? "var(--accent)" : "transparent",
            }}
          >
            {checked && <span className="w-1.5 h-1.5 rounded-full bg-white" />}
          </span>
        )}
        <div className="flex-1 min-w-0 flex flex-col gap-2.5">
          <div className="flex items-center gap-1.5 flex-wrap min-h-[22px]">
            <span className="font-mono text-[11px] text-[color:var(--muted)] tabular-nums">
              #{c.rank}
            </span>
            {c.is_explore && <ExploreChip />}
            {c.health_flags?.veg_ok && <HealthFlagBadge k="veg_ok" value />}
            {c.health_flags?.protein_ok && <HealthFlagBadge k="protein_ok" value />}
            {c.health_flags?.oil_ok && <HealthFlagBadge k="oil_ok" value />}
            {c.health_flags?.wetness && <HealthFlagBadge k="wetness" value />}
            {c.risk_flags?.map((r) => (
              <RiskChip key={r} label={r} />
            ))}
          </div>

          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-[16px] font-semibold tracking-tight leading-snug">
                {c.restaurant.name}
              </h3>
              <p
                className="text-[13.5px] text-[color:var(--fg)] mt-0.5 leading-relaxed"
                style={{ textWrap: "pretty" } as React.CSSProperties}
              >
                {c.summary}
              </p>
            </div>
            <div className="shrink-0 text-right">
              <div className="text-[18px] font-semibold tabular-nums leading-none">
                ¥{c.total_price.toFixed(c.total_price % 1 === 0 ? 0 : 1)}
              </div>
            </div>
          </div>

          {c.reason_one_line && (
            <p
              className="text-[12.5px] text-[color:var(--muted)] leading-relaxed"
              style={{ textWrap: "pretty" } as React.CSSProperties}
            >
              <span className="text-[color:var(--accent)] mr-1">💬</span>
              {c.reason_one_line}
            </p>
          )}

          <div className="flex items-center gap-x-3 gap-y-1.5 flex-wrap pt-1.5 border-t border-dashed border-[color:var(--border)]">
            <span className="text-[12px] text-[color:var(--muted)] tabular-nums">
              {c.restaurant.eta_min}min
            </span>
            <span className="text-[12px] text-[color:var(--muted)] tabular-nums">
              {(c.restaurant.distance_m / 1000).toFixed(1)}km
            </span>
            <span className="text-[12px]">
              <ProteinLabel g={c.estimated_total_protein_g} />
            </span>
            <span className="text-[12px]">
              <OilLabel level={c.estimated_total_oil} />
            </span>

            {!isReview && (
              <div className="ml-auto flex items-center gap-2">
                {isPicked ? (
                  <>
                    <span
                      className="text-[12.5px] px-3 py-1.5 rounded-md font-medium inline-flex items-center gap-1.5"
                      style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
                    >
                      <span aria-hidden="true">✓</span>
                      {LABELS.ui.picked}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onUnpick?.();
                      }}
                      className="text-[11.5px] text-[color:var(--muted)] hover:text-[color:var(--fg)] underline-offset-2 hover:underline"
                    >
                      {LABELS.ui.pickChange} ↺
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDetail?.(c);
                      }}
                      className="text-[12px] px-2.5 py-1.5 rounded-md border border-[color:var(--border)] hover:border-[color:var(--fg)]"
                    >
                      {LABELS.ui.detail}
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onPick?.(c);
                      }}
                      className={cx(
                        "text-[12.5px] px-3 py-1.5 rounded-md font-medium",
                        someonePicked &&
                          "border border-[color:var(--border)] hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
                      )}
                      style={
                        someonePicked
                          ? undefined
                          : { background: "var(--accent)", color: "var(--accent-fg)" }
                      }
                    >
                      {someonePicked
                        ? LABELS.ui.pickThisAlt
                        : `${LABELS.ui.pickThis} →`}
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

export function RecCardSkeleton() {
  return (
    <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-4 animate-pulse">
      <div className="flex gap-1.5 mb-3">
        <div className="h-4 w-12 rounded bg-[color:var(--surface-2)]" />
        <div className="h-4 w-14 rounded bg-[color:var(--surface-2)]" />
        <div className="h-4 w-12 rounded bg-[color:var(--surface-2)]" />
      </div>
      <div className="flex justify-between gap-3">
        <div className="flex-1 space-y-2">
          <div className="h-5 w-2/3 rounded bg-[color:var(--surface-2)]" />
          <div className="h-4 w-4/5 rounded bg-[color:var(--surface-2)]/70" />
        </div>
        <div className="h-6 w-16 rounded bg-[color:var(--surface-2)]" />
      </div>
      <div className="h-3 w-3/5 mt-3 rounded bg-[color:var(--surface-2)]/60" />
      <div className="mt-4 pt-3 border-t border-dashed border-[color:var(--border)] flex items-center gap-3">
        <div className="h-3 w-10 bg-[color:var(--surface-2)] rounded" />
        <div className="h-3 w-10 bg-[color:var(--surface-2)] rounded" />
        <div className="h-3 w-12 bg-[color:var(--surface-2)] rounded" />
        <div className="ml-auto h-7 w-20 bg-[color:var(--surface-2)] rounded-md" />
      </div>
    </div>
  );
}

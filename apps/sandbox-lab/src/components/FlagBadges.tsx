import type { MealFlag } from "../types/sandbox";

const FLAG_BADGES: Record<
  MealFlag,
  { glyph: string; title: string; timelineClass: string; summaryText: string }
> = {
  swap: { glyph: "↻", title: "换过组", timelineClass: "swap", summaryText: "↻ 换过" },
  refine: { glyph: "✎", title: "refine 过", timelineClass: "refine", summaryText: "✎ refine" },
  conflict: { glyph: "⚠", title: "冲突过", timelineClass: "conflict", summaryText: "⚠ 冲突" },
  event: { glyph: "★", title: "关键事件", timelineClass: "event", summaryText: "★ L1" },
};

export function TimelineFlagBadges({ flags }: { flags: MealFlag[] }) {
  if (flags.length === 0) return null;
  return (
    <span className="cell-badges">
      {flags.map((flag) => {
        const cfg = FLAG_BADGES[flag];
        return (
          <span key={flag} className={`cell-badge ${cfg.timelineClass}`} title={cfg.title}>
            {cfg.glyph}
          </span>
        );
      })}
    </span>
  );
}

export function SummaryFlagBadges({ flags }: { flags: MealFlag[] | undefined }) {
  if (!flags || flags.length === 0) return null;
  return (
    <span className="badges">
      {flags.map((flag) => {
        const cfg = FLAG_BADGES[flag];
        return (
          <span key={flag} className={`b-mini ${flag}`}>
            {cfg.summaryText}
          </span>
        );
      })}
    </span>
  );
}

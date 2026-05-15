// PendingFeedbackBanner — V1.1 stack variant (D-055)
// 卡片 + 多条堆叠: 主卡 + "还有 N 餐没反馈 去反馈中心 →" + ⋯ snooze/stop 菜单 (D-058)。
// V1 的 slim banner 已退役 (上一轮 D-049 入口); ✕ 默认 = snooze, 不是 stop。

import { useState } from "react";
import { LABELS } from "@/lib/labels";
import { cx } from "@/lib/cx";
import type { UnfedSession } from "@/lib/types";
import { relAgo } from "@/components/feedback/atoms";

export function PendingFeedbackBanner({
  unfedList,
  onOpen,
  onSnooze,
  onStop,
  onOpenInbox,
}: {
  unfedList: UnfedSession[];
  onOpen: (item: UnfedSession) => void;
  onSnooze: (item: UnfedSession) => void;
  onStop: (item: UnfedSession) => void;
  onOpenInbox: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  // Banner 只看 active (未 snooze + 未 stop); snooze 的 case 在 inbox 中显示
  const active = unfedList.filter((x) => !x.snoozed && !x.stopped);
  if (active.length === 0) return null;

  const primary = active[0];
  const restCount = active.length - 1;
  const meal = LABELS.meal[primary.meal_type];
  const ago = relAgo(primary.accepted_at);

  return (
    <div
      className="mt-4 mb-3 rounded-lg border overflow-hidden"
      style={{
        borderColor: "color-mix(in srgb, var(--accent) 35%, transparent)",
        background: "color-mix(in srgb, var(--accent) 6%, var(--surface))",
      }}
    >
      {/* metadata row */}
      <div className="flex items-center gap-2 px-4 pt-2.5">
        <span aria-hidden="true" className="text-[12px]" style={{ color: "var(--accent)" }}>
          ●
        </span>
        <span
          className="text-[11.5px] uppercase tracking-wider font-medium"
          style={{ color: "var(--accent)" }}
        >
          {LABELS.ui.inboxPending}
        </span>
        <span className="text-[11.5px] text-[color:var(--muted)] tabular-nums whitespace-nowrap">
          {ago} · {meal}
        </span>
        <div className="ml-auto relative">
          <button
            onClick={() => setMenuOpen((v) => !v)}
            aria-label={LABELS.ui.bannerOpenMenu}
            className="text-[14px] leading-none px-2 py-0.5 rounded text-[color:var(--muted)] hover:text-[color:var(--fg)] hover:bg-[color:var(--surface-2)]"
          >
            ⋯
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full mt-1 min-w-[140px] rounded-md border border-[color:var(--border)] bg-[color:var(--surface)] shadow-lg overflow-hidden z-10">
              <button
                onClick={() => {
                  setMenuOpen(false);
                  onSnooze(primary);
                }}
                className="w-full text-left px-3 py-1.5 text-[12.5px] hover:bg-[color:var(--surface-2)] text-[color:var(--fg)]"
              >
                {LABELS.ui.bannerSnooze}
              </button>
              <button
                onClick={() => {
                  setMenuOpen(false);
                  onStop(primary);
                }}
                className="w-full text-left px-3 py-1.5 text-[12.5px] hover:bg-[color:var(--surface-2)] text-[color:var(--bad)]"
              >
                {LABELS.ui.bannerStop}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* main: restaurant + summary */}
      <button
        onClick={() => onOpen(primary)}
        className="w-full text-left px-4 pb-3 pt-1.5 group"
      >
        <div
          className="text-[14.5px] font-semibold tracking-tight leading-snug group-hover:underline"
          style={{ color: "var(--fg)" }}
        >
          {primary.restaurant_name}
        </div>
        {primary.summary && (
          <div className="text-[12.5px] text-[color:var(--muted)] mt-0.5 line-clamp-1 leading-relaxed">
            {primary.summary}
          </div>
        )}
      </button>

      {/* stack footer */}
      <div
        className={cx(
          "px-4 py-2 border-t flex items-center gap-3"
        )}
        style={{
          borderColor: "color-mix(in srgb, var(--accent) 18%, transparent)",
          background: "color-mix(in srgb, var(--accent) 3%, transparent)",
        }}
      >
        <button
          onClick={() => onOpen(primary)}
          className="text-[12.5px] font-medium"
          style={{ color: "var(--accent)" }}
        >
          {LABELS.ui.bannerCta}
        </button>
        {restCount > 0 && (
          <>
            <span className="text-[11px] text-[color:var(--muted)]">·</span>
            <button
              onClick={onOpenInbox}
              className="text-[12px] text-[color:var(--muted)] hover:text-[color:var(--fg)]"
            >
              {LABELS.ui.bannerStackMore(restCount)} {LABELS.ui.bannerStackGo}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

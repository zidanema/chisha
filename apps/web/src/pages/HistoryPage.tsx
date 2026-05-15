import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LABELS } from "@/lib/labels";
import { cx } from "@/lib/cx";
import { api } from "@/lib/api";
import type { HistoryItem, RecentFeedback } from "@/lib/types";
import { PageShell, FooterBar } from "@/components/PageShell";

export function HistoryPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [feedbacks, setFeedbacks] = useState<Record<string, RecentFeedback>>({});
  const [unfedSet, setUnfedSet] = useState<Set<string>>(new Set());

  useEffect(() => {
    void api.history({ days: 7 }).then((r) => setItems(r.items));
    void api.inbox({ include_snoozed: true }).then((r) => {
      setUnfedSet(new Set(r.items.map((x) => x.session_id)));
    });
    void api.recentFeedbacks({ limit: 50 }).then((r) => {
      const m: Record<string, RecentFeedback> = {};
      r.items.forEach((x) => {
        m[x.session_id] = x;
      });
      setFeedbacks(m);
    });
  }, []);

  return (
    <PageShell>
      <div className="mt-5 mb-4 flex items-baseline gap-3">
        <h1 className="text-[18px] font-semibold tracking-tight">
          {LABELS.ui.navHistory}
        </h1>
        <span className="text-[12px] text-[color:var(--muted)]">最近 7 天</span>
        <span className="ml-auto text-[11.5px] text-[color:var(--muted)]">
          {LABELS.ui.historyHintClickable}
        </span>
      </div>

      {items === null ? (
        <div className="space-y-2">
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-14 rounded-md bg-[color:var(--surface)] animate-pulse"
            />
          ))}
        </div>
      ) : (
        <ul className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] overflow-hidden divide-y divide-[color:var(--border)]">
          {items.map((it) => {
            const d = new Date(it.generated_at);
            const isToday = new Date().toDateString() === d.toDateString();
            const date = `${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
            const isUnfed = unfedSet.has(it.session_id);
            const fed = feedbacks[it.session_id];
            const isSkipped = it.accepted_rank == null && !fed;
            // 跳过餐没有反馈页, 不点; 其它行都跳 /feedback/<id> 由 FeedbackPage 双态分支
            const clickable = !isSkipped;
            const onRowClick = () =>
              clickable && navigate(`/feedback/${it.session_id}`);

            return (
              <li
                key={it.session_id}
                onClick={onRowClick}
                role={clickable ? "button" : undefined}
                tabIndex={clickable ? 0 : undefined}
                onKeyDown={(e) => {
                  if (clickable && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    onRowClick();
                  }
                }}
                className={cx(
                  "p-3 px-4 flex items-center gap-4 transition-colors",
                  clickable && "cursor-pointer",
                  clickable && isUnfed
                    ? "hover:bg-[color:var(--accent-bg)]"
                    : clickable
                      ? "hover:bg-[color:var(--surface-2)]"
                      : ""
                )}
              >
                <div className="w-16 shrink-0">
                  <div className="font-mono text-[11px] text-[color:var(--muted)] tabular-nums">
                    {date}
                  </div>
                  {isToday && (
                    <div className="text-[10.5px] text-[color:var(--accent)]">今天</div>
                  )}
                </div>
                <div className="w-14 shrink-0">
                  <span className="text-[12px] px-2 py-0.5 rounded-md border border-[color:var(--border)]">
                    {LABELS.meal[it.meal_type]}
                  </span>
                </div>
                <div className="w-20 shrink-0">
                  <span className="text-[11px] text-[color:var(--muted)]">
                    {LABELS.mood[it.mood]}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] truncate text-[color:var(--fg)]">
                    {it.candidates_summary.slice(0, 3).join(" · ")}
                  </div>
                </div>
                <div className="shrink-0 text-right flex items-center gap-2">
                  {isUnfed && (
                    <span
                      className="text-[10.5px] px-1.5 py-0.5 rounded font-medium"
                      style={{ background: "var(--accent-bg)", color: "var(--accent)" }}
                    >
                      {LABELS.ui.historyUnfedChip}
                    </span>
                  )}
                  {fed && (
                    <span className="text-[11.5px] text-[color:var(--muted)] whitespace-nowrap">
                      {LABELS.ui.inboxFedChip(fed.rating)}
                    </span>
                  )}
                  {isSkipped && (
                    <span className="text-[11px] text-[color:var(--muted)]">
                      {LABELS.ui.notEatenShort}
                    </span>
                  )}
                  {clickable && (
                    <span
                      aria-hidden="true"
                      className="text-[color:var(--muted)] opacity-60"
                    >
                      ›
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <FooterBar />
    </PageShell>
  );
}

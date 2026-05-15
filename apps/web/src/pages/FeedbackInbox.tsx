// FeedbackInbox — /feedback 反馈中心 (D-056)
// 三段: 待反馈 / 暂缓 / 已反馈; 每行点击进 /feedback/<id>;
// ⋯ 菜单提供 snooze / stop (D-058).

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LABELS } from "@/lib/labels";
import { cx } from "@/lib/cx";
import { api } from "@/lib/api";
import { useChisha } from "@/lib/useChishaState";
import { PageShell, FooterBar } from "@/components/PageShell";
import type { RecentFeedback, UnfedSession } from "@/lib/types";
import { relAgo } from "@/components/feedback/atoms";

export function FeedbackInbox() {
  const navigate = useNavigate();
  const { refreshInbox } = useChisha();

  const [pending, setPending] = useState<UnfedSession[] | null>(null);
  const [done, setDone] = useState<RecentFeedback[] | null>(null);

  const load = useCallback(async () => {
    const [p, d] = await Promise.all([
      api.inbox({ include_snoozed: true }),
      api.recentFeedbacks({ limit: 6 }),
    ]);
    setPending(p.items);
    setDone(d.items);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onSnooze(item: UnfedSession) {
    await api.snoozeFeedback({ session_id: item.session_id });
    await load();
    await refreshInbox();
  }
  async function onStop(item: UnfedSession) {
    await api.stopFeedback({ session_id: item.session_id });
    await load();
    await refreshInbox();
  }

  const loading = pending === null || done === null;
  const pendingActive = (pending ?? []).filter((p) => !p.snoozed);
  const pendingSnoozed = (pending ?? []).filter((p) => p.snoozed);

  return (
    <PageShell>
      <div className="mt-6 mb-4">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[20px] font-semibold tracking-tight">
            {LABELS.ui.inboxTitle}
          </h1>
          <span className="text-[12.5px] text-[color:var(--muted)]">
            {LABELS.ui.inboxSubtitle}
          </span>
        </div>
        {!loading && pendingActive.length > 0 && (
          <div className="mt-2 text-[12px] text-[color:var(--muted)] tabular-nums">
            {LABELS.ui.inboxPendingHint(pendingActive.length)}
          </div>
        )}
      </div>

      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-20 rounded-lg bg-[color:var(--surface)] animate-pulse"
            />
          ))}
        </div>
      ) : pendingActive.length === 0 &&
        pendingSnoozed.length === 0 &&
        (done ?? []).length === 0 ? (
        <EmptyInbox />
      ) : (
        <>
          {pendingActive.length > 0 && (
            <Section title={LABELS.ui.inboxPending} count={pendingActive.length}>
              {pendingActive.map((it) => (
                <PendingRow
                  key={it.session_id}
                  item={it}
                  onOpen={() => navigate(`/feedback/${it.session_id}`)}
                  onSnooze={() => onSnooze(it)}
                  onStop={() => onStop(it)}
                />
              ))}
            </Section>
          )}

          {pendingSnoozed.length > 0 && (
            <Section title={LABELS.ui.inboxSnoozed} count={pendingSnoozed.length} muted>
              {pendingSnoozed.map((it) => (
                <PendingRow
                  key={it.session_id}
                  item={it}
                  snoozed
                  onOpen={() => navigate(`/feedback/${it.session_id}`)}
                  onSnooze={() => onSnooze(it)}
                  onStop={() => onStop(it)}
                />
              ))}
            </Section>
          )}

          {(done ?? []).length > 0 && (
            <Section title={LABELS.ui.inboxDone} count={(done ?? []).length} muted>
              {(done ?? []).map((it) => (
                <DoneRow
                  key={it.session_id}
                  item={it}
                  onOpen={() => navigate(`/feedback/${it.session_id}`)}
                />
              ))}
            </Section>
          )}
        </>
      )}

      <FooterBar />
    </PageShell>
  );
}

function Section({
  title,
  count,
  muted,
  children,
}: {
  title: string;
  count: number;
  muted?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-7">
      <div className="flex items-baseline gap-2 mb-2">
        <h2
          className={cx(
            "text-[11px] uppercase tracking-wider font-semibold",
            muted ? "text-[color:var(--muted)]" : "text-[color:var(--fg)]"
          )}
        >
          {title}
        </h2>
        <span className="text-[11px] text-[color:var(--muted)] tabular-nums">
          {count}
        </span>
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function PendingRow({
  item,
  snoozed,
  onOpen,
  onSnooze,
  onStop,
}: {
  item: UnfedSession;
  snoozed?: boolean;
  onOpen: () => void;
  onSnooze: () => void;
  onStop: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const ago = relAgo(item.accepted_at);
  const meal = LABELS.meal[item.meal_type];

  return (
    <article
      className={cx(
        "group rounded-lg border bg-[color:var(--surface)] transition-all",
        snoozed
          ? "border-[color:var(--border)] opacity-60 hover:opacity-90"
          : "border-[color:var(--border)] hover:border-[color:var(--accent)]"
      )}
    >
      <div className="flex items-stretch">
        <button onClick={onOpen} className="flex-1 text-left px-4 py-3 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-[11px] tabular-nums text-[color:var(--muted)] whitespace-nowrap">
              {ago}
            </span>
            <span className="text-[10.5px] px-1.5 py-0 rounded border border-[color:var(--border)] text-[color:var(--muted)] whitespace-nowrap">
              {meal}
            </span>
            {snoozed && (
              <span
                className="text-[10.5px] px-1.5 py-0 rounded text-[color:var(--muted)]"
                style={{ background: "var(--surface-2)" }}
              >
                {LABELS.ui.inboxRowSnoozed}
              </span>
            )}
          </div>
          <div className="text-[14px] font-medium tracking-tight leading-snug truncate">
            {item.restaurant_name}
          </div>
          {item.summary && (
            <div className="text-[12px] text-[color:var(--muted)] mt-0.5 line-clamp-1 leading-relaxed">
              {item.summary}
            </div>
          )}
        </button>
        <div className="flex items-center gap-1 pr-3 shrink-0">
          <button
            onClick={onOpen}
            className="text-[12px] px-2.5 py-1 rounded-md border border-[color:var(--border)] hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
          >
            {LABELS.ui.inboxRowOpen}
          </button>
          <div className="relative">
            <button
              onClick={() => setMenuOpen((v) => !v)}
              aria-label={LABELS.ui.bannerOpenMenu}
              className="text-[14px] leading-none px-2 py-1 rounded text-[color:var(--muted)] hover:text-[color:var(--fg)] hover:bg-[color:var(--surface-2)]"
            >
              ⋯
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-full mt-1 min-w-[140px] rounded-md border border-[color:var(--border)] bg-[color:var(--surface)] shadow-lg overflow-hidden z-10">
                {!snoozed && (
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      onSnooze();
                    }}
                    className="w-full text-left px-3 py-1.5 text-[12.5px] hover:bg-[color:var(--surface-2)] text-[color:var(--fg)]"
                  >
                    {LABELS.ui.bannerSnooze}
                  </button>
                )}
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    onStop();
                  }}
                  className="w-full text-left px-3 py-1.5 text-[12.5px] hover:bg-[color:var(--surface-2)] text-[color:var(--bad)]"
                >
                  {LABELS.ui.bannerStop}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

function DoneRow({
  item,
  onOpen,
}: {
  item: RecentFeedback;
  onOpen: () => void;
}) {
  const ago = relAgo(item.submitted_at);
  const meal = LABELS.meal[item.meal_type];
  const isNotEaten = item.accepted_rank == null;

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)]/60 px-4 py-2.5 transition-colors cursor-pointer hover:bg-[color:var(--surface)] hover:border-[color:var(--fg)]"
    >
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 w-36 shrink-0">
          <span className="text-[11px] tabular-nums text-[color:var(--muted)] whitespace-nowrap">
            {ago}
          </span>
          <span className="text-[10.5px] px-1.5 py-0 rounded border border-[color:var(--border)] text-[color:var(--muted)] whitespace-nowrap">
            {meal}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] truncate text-[color:var(--fg)]">
            {item.restaurant_name}
          </div>
        </div>
        <div className="shrink-0 text-[11.5px] text-[color:var(--muted)] whitespace-nowrap">
          {isNotEaten ? LABELS.ui.notEatenShort : LABELS.ui.inboxFedChip(item.rating)}
        </div>
        <span aria-hidden="true" className="text-[color:var(--muted)] opacity-50 shrink-0">
          ›
        </span>
      </div>
    </article>
  );
}

function EmptyInbox() {
  return (
    <div className="mt-12 rounded-lg border border-dashed border-[color:var(--border)] px-8 py-14 text-center bg-[color:var(--surface)]/40">
      <div className="text-[28px] mb-3 opacity-30">✓</div>
      <div className="text-[15px] font-medium tracking-tight mb-1">
        {LABELS.ui.inboxEmpty}
      </div>
      <div className="text-[12.5px] text-[color:var(--muted)] mb-5">
        {LABELS.ui.inboxEmptyHint}
      </div>
      <Link
        to="/"
        className="inline-block text-[12.5px] px-3 py-1.5 rounded-md border border-[color:var(--border)] hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
      >
        {LABELS.ui.inboxBackHome}
      </Link>
    </div>
  );
}

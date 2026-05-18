import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { LABELS } from "@/lib/labels";
import { api } from "@/lib/api";
import { useChisha } from "@/lib/useChishaState";
import type { Candidate, MealType, Mood } from "@/lib/types";

import { PageShell, FooterBar } from "@/components/PageShell";
import { PendingFeedbackBanner } from "@/components/PendingFeedbackBanner";
import { StatusBar } from "@/components/StatusBar";
import { MethodologyBar } from "@/components/MethodologyBar";
import { SectionHeader } from "@/components/atoms";
import { RefineCrumb } from "@/components/RefineCrumb";
import { RefineInput } from "@/components/RefineInput";
import { RecCard, RecCardSkeleton } from "@/components/RecCard";
import { PickedConfirmation } from "@/components/PickedConfirmation";
import { SkipMealAction, SkippedState } from "@/components/SkipMealAction";

export function HomePage() {
  const navigate = useNavigate();
  const { home, setHome, inbox, refreshInbox, showToast } = useChisha();
  const recsRef = useRef<HTMLDivElement | null>(null);

  function scrollToRecs() {
    requestAnimationFrame(() => {
      const el = recsRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const target = window.scrollY + rect.top - 80;
      window.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
    });
  }

  // Initial fetch
  useEffect(() => {
    if (!home.session) void fetchRecommend();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // D-071: 不再让用户选 mood, mood 固定 'neutral' (后端 daily_mood=None).
  // want_soup 走 refine 文本关键词识别 (chisha/refine.py:infer_refine_mood).
  const FIXED_MOOD: Mood = "neutral";

  async function fetchRecommend(args?: { meal?: MealType }) {
    const meal = args?.meal ?? home.meal;
    setHome({
      loading: true,
      refineHistory: [],
      pickedRank: null,
      skipped: false,
      skipReason: null,
    });
    const resp = await api.recommend({ meal_type: meal, mood: FIXED_MOOD });
    setHome({
      session: {
        session_id: resp.session_id,
        candidates: resp.candidates,
        round: resp.round,
        history: [resp],
      },
      loading: false,
      statusBar: resp.status_bar ?? null,
      narrative: resp.narrative ?? "",
    });
  }

  async function regenerate() {
    if (!home.session) {
      await fetchRecommend();
      return;
    }
    setHome({ loading: true, pickedRank: null });
    const excludeIds = home.session.candidates.map((c) => c.id);
    const resp = await api.refine({
      session_id: home.session.session_id,
      refine_text: "",
      meal_type: home.meal,
      mood: FIXED_MOOD,
      round: home.session.round + 1,
      excludeIds,
    });
    setHome({
      session: {
        ...home.session,
        session_id: resp.session_id,
        candidates: resp.candidates,
        round: resp.round,
        history: [...home.session.history, resp],
      },
      loading: false,
      statusBar: resp.status_bar ?? home.statusBar,
      narrative: resp.narrative ?? home.narrative,
    });
  }

  function setMeal(m: MealType) {
    setHome({ meal: m });
    void fetchRecommend({ meal: m });
  }

  // ── Refine ───────────────────────────────────────────────────────────────────
  async function onRefine(text: string) {
    if (!home.session) return;
    const nextRound = home.session.round + 1;
    setHome({
      loading: true,
      pickedRank: null,
      refineHistory: [...home.refineHistory, { round: nextRound, text }],
    });
    const resp = await api.refine({
      session_id: home.session.session_id,
      refine_text: text,
      meal_type: home.meal,
      mood: FIXED_MOOD,
      round: nextRound,
      excludeIds: [],
    });
    setHome({
      session: {
        ...home.session,
        session_id: resp.session_id,
        candidates: resp.candidates,
        round: resp.round,
        history: [...home.session.history, resp],
      },
      loading: false,
      statusBar: resp.status_bar ?? home.statusBar,
      narrative: resp.narrative ?? home.narrative,
    });
    scrollToRecs();
  }

  function onJumpRound(targetRound: number) {
    if (!home.session?.history) return;
    const hist = home.session.history.find((r) => r.round === targetRound);
    if (!hist) return;
    // Codex LOW: 旧 history 缺 status_bar/narrative → 置空, 不沿用当前轮 (避免错位)
    setHome({
      session: { ...home.session, candidates: hist.candidates, round: hist.round },
      pickedRank: null,
      statusBar: hist.status_bar ?? null,
      narrative: hist.narrative ?? "",
    });
    scrollToRecs();
  }

  function onResetRefine() {
    if (!home.session?.history?.length) return;
    const first = home.session.history[0];
    setHome({
      session: { ...home.session, candidates: first.candidates, round: first.round },
      refineHistory: [],
      pickedRank: null,
      statusBar: first.status_bar ?? null,
      narrative: first.narrative ?? "",
    });
    scrollToRecs();
  }

  // ── Pick / unpick (D-052) ────────────────────────────────────────────────────
  async function onPick(c: Candidate) {
    setHome({ pickedRank: c.rank });
    if (!home.session) return;
    await api.accept({
      session_id: home.session.session_id,
      candidate_rank: c.rank,
      candidate: c,
    });
    await refreshInbox();
  }
  function onUnpick() {
    setHome({ pickedRank: null });
  }

  // ── Skip (D-054) ─────────────────────────────────────────────────────────────
  async function onSkipMeal(reason: import("@/lib/types").SkipReason) {
    if (!home.session) return;
    await api.skipMeal({ session_id: home.session.session_id, reason });
    setHome({ skipped: true, skipReason: reason, pickedRank: null });
    await refreshInbox();
    showToast(LABELS.ui.skippedToast, "good");
  }
  function onUndoSkip() {
    setHome({ skipped: false, skipReason: null });
    scrollToRecs();
  }

  // ── Banner (D-055): hide current session from banner so accept→banner 不闪 ───
  const shownInbox = home.session
    ? inbox.filter((x) => x.session_id !== home.session!.session_id)
    : inbox;

  async function onBannerSnooze(item: import("@/lib/types").UnfedSession) {
    await api.snoozeFeedback({ session_id: item.session_id });
    await refreshInbox();
  }
  async function onBannerStop(item: import("@/lib/types").UnfedSession) {
    await api.stopFeedback({ session_id: item.session_id });
    await refreshInbox();
  }

  const all = home.session?.candidates ?? [];
  const pickedCandidate =
    home.pickedRank != null ? all.find((c) => c.rank === home.pickedRank) ?? null : null;

  return (
    <PageShell>
      <PendingFeedbackBanner
        unfedList={shownInbox}
        onOpen={(item) => navigate(`/feedback/${item.session_id}`)}
        onSnooze={onBannerSnooze}
        onStop={onBannerStop}
        onOpenInbox={() => navigate("/feedback")}
      />

      <MethodologyBar payload={home.statusBar} />

      <StatusBar
        meal={home.meal}
        setMeal={setMeal}
        onRegen={regenerate}
        regenerating={home.loading}
      />

      <section>
        <SectionHeader
          title={LABELS.ui.homeSecTitle}
          hint={
            home.loading
              ? `${LABELS.ui.loadingHint} · ${LABELS.ui.loadingHintLong}`
              : null
          }
        />

        {home.skipped ? (
          <SkippedState reason={home.skipReason} onUndo={onUndoSkip} />
        ) : (
          <>
            <RefineCrumb
              history={home.refineHistory}
              currentRound={home.session?.round}
              onJumpRound={onJumpRound}
              onReset={onResetRefine}
            />

            {/* T-P1b-02: L3 narrative ("为什么推这 5 道" ≤ 50 字摘要) */}
            {!home.loading && home.narrative && (
              <div
                data-testid="l3-narrative"
                className="mb-3 px-3 py-2 rounded border border-[color:var(--border)] bg-[color:var(--bg-soft,#f9f9f9)] text-[12.5px] text-[color:var(--fg)] leading-snug"
              >
                <span className="text-[color:var(--muted)] mr-1.5">为什么</span>
                {home.narrative}
              </div>
            )}

            <div className="space-y-3" ref={recsRef}>
              {home.loading
                ? [0, 1, 2, 3, 4].map((i) => <RecCardSkeleton key={i} />)
                : all.map((c) => (
                    <RecCard
                      key={`${c.id}-${home.session?.round}`}
                      candidate={c}
                      onPick={onPick}
                      onUnpick={onUnpick}
                      pickedRank={home.pickedRank}
                      onDetail={(c) => setHome({ detailCandidate: c })}
                    />
                  ))}
            </div>

            {pickedCandidate && (
              <PickedConfirmation candidate={pickedCandidate} onUnpick={onUnpick} />
            )}
          </>
        )}
      </section>

      {!home.skipped && (
        <>
          <RefineInput disabled={home.loading} onSubmit={onRefine} />
          <SkipMealAction
            onSkip={onSkipMeal}
            disabled={home.loading || !home.session}
          />
        </>
      )}

      <FooterBar />
    </PageShell>
  );
}

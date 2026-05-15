import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { LABELS } from "@/lib/labels";
import { api } from "@/lib/api";
import { useChisha } from "@/lib/useChishaState";
import type { Candidate, MealType, Mood } from "@/lib/types";

import { PageShell, FooterBar } from "@/components/PageShell";
import { PendingFeedbackBanner } from "@/components/PendingFeedbackBanner";
import { StatusBar } from "@/components/StatusBar";
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

  async function fetchRecommend(args?: { meal?: MealType; mood?: Mood }) {
    const meal = args?.meal ?? home.meal;
    const mood = args?.mood ?? home.mood;
    setHome({
      loading: true,
      refineHistory: [],
      pickedRank: null,
      skipped: false,
      skipReason: null,
    });
    const resp = await api.recommend({ meal_type: meal, mood });
    setHome({
      session: {
        session_id: resp.session_id,
        candidates: resp.candidates,
        round: resp.round,
        history: [resp],
      },
      loading: false,
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
      mood: home.mood,
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
    });
  }

  function setMeal(m: MealType) {
    setHome({ meal: m });
    void fetchRecommend({ meal: m, mood: home.mood });
  }
  function setMood(m: Mood) {
    setHome({ mood: m });
    void fetchRecommend({ meal: home.meal, mood: m });
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
      mood: home.mood,
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
    });
    scrollToRecs();
  }

  function onJumpRound(targetRound: number) {
    if (!home.session?.history) return;
    const hist = home.session.history.find((r) => r.round === targetRound);
    if (!hist) return;
    setHome({
      session: { ...home.session, candidates: hist.candidates, round: hist.round },
      pickedRank: null,
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
    });
    scrollToRecs();
  }

  // ── Pick / unpick (D-050) ────────────────────────────────────────────────────
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

  // ── Skip (D-052) ─────────────────────────────────────────────────────────────
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

  // ── Banner (D-053): hide current session from banner so accept→banner 不闪 ───
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

      <StatusBar
        meal={home.meal}
        setMeal={setMeal}
        mood={home.mood}
        setMood={setMood}
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

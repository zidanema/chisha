// S-03: 接 useSandbox hook, 替换 S-02 noop 接线. demo-* query 保留 (走 initialState).
import { useCallback, useMemo, useState } from "react";
import { Banners } from "./components/Banners";
import { DecisionArea } from "./components/DecisionArea";
import { ReviewCard } from "./components/ReviewCard";
import { RightCol } from "./components/RightCol";
import { Timeline, OpBar } from "./components/Timeline";
import { TopBar } from "./components/TopBar";
import { TweaksPanel } from "./components/TweaksPanel";
import { ConfirmModal } from "./components/modals/ConfirmModal";
import { RefineModal } from "./components/modals/RefineModal";
import { SummaryDrawer } from "./components/modals/SummaryDrawer";
import { useKeyboard } from "./hooks/useKeyboard";
import { useSandbox } from "./hooks/useSandbox";
import { useTweaks } from "./hooks/useTweaks";
import type { Decision } from "./types/sandbox";


// rollback / branch / new-session 后 lastDecision=null; D panel 期望非空 Decision,
// 此处给个 idle 占位 (rank/l3="—", diff/implications 空), 视觉上等同 skip 形态.
const IDLE_DECISION: Decision = {
  when: "—",
  pick: "(等待下一顿)",
  rank: "—",
  l3: "—",
  diff: [],
  implications: [],
};

type DemoModal = "summary" | "confirm-rollback" | "confirm-branch" | "refine";


function readQuery(): {
  dev: boolean;
  demoReview: number | null;
  demoModal: DemoModal | null;
} {
  if (typeof window === "undefined") {
    return { dev: false, demoReview: null, demoModal: null };
  }
  const sp = new URLSearchParams(window.location.search);
  const demoReviewRaw = sp.get("demo-review");
  const demoModalRaw = sp.get("demo-modal");
  let demoReview: number | null = null;
  if (demoReviewRaw === "1" || demoReviewRaw === "eat") demoReview = 0;
  else if (demoReviewRaw === "skip") demoReview = 2;
  return {
    dev: sp.has("dev"),
    demoReview,
    demoModal:
      demoModalRaw === "summary" ||
      demoModalRaw === "confirm-rollback" ||
      demoModalRaw === "confirm-branch" ||
      demoModalRaw === "refine"
        ? demoModalRaw
        : null,
  };
}


export function App() {
  const { tweaks, setTweak } = useTweaks();
  const query = useMemo(readQuery, []);
  const [tweaksOpen, setTweaksOpen] = useState(query.dev);
  const [density, setDensity] = useState<0 | 1 | 2>(1);
  const [selectedRank, setSelectedRank] = useState<number>(2);

  const sb = useSandbox({
    initialState: {
      modal: query.demoModal ?? undefined,
      reviewIdx: query.demoReview ?? undefined,
    },
  });

  // Esc: 优先关 confirm > summary > refine > review (修订 H 单层关)
  const onEsc = useCallback(() => {
    if (sb.confirmKind !== null) sb.closeConfirm();
    else if (sb.summaryOpen) sb.closeSummary();
    else if (sb.refineModalOpen) sb.closeRefineModal();
    else if (sb.selectedCellIdx !== null) sb.selectCell(null);
  }, [sb]);
  useKeyboard({ onEsc });

  const activeSession = sb.sessions.find((s) => s.id === sb.activeSessionId) ?? sb.sessions[0];

  const handleConfirm = useCallback(
    (branchName: string | null) => {
      const targetMeal = sb.confirmMeal;
      if (!targetMeal) return;
      if (sb.confirmKind === "rollback") {
        sb.handleRollback(targetMeal.idx);
      } else if (sb.confirmKind === "branch") {
        sb.handleBranch(targetMeal.idx, branchName ?? "");
      }
    },
    [sb],
  );

  const openTrace = useCallback(
    () => window.alert("打开 trace (S-09 接 debug-ui)"),
    [],
  );

  return (
    <div className="app">
      <TopBar
        sessions={sb.sessions}
        activeSessionName={activeSession.name}
        profile={activeSession.profile}
        seed={activeSession.seed}
        origin={activeSession.origin}
        clock={sb.clock}
        onOpenSummary={sb.openSummary}
        onSelectSession={sb.setActiveSessionId}
        onNewSession={() => sb.handleBranch(sb.currentMealIdx, `新-${Date.now() % 10000}`)}
        onOpenTweaks={() => setTweaksOpen(true)}
      />

      <Banners banners={sb.banners} onDismiss={sb.dismissTransient} />

      <div className="timeline-wrap">
        <Timeline
          history={sb.history}
          currentIdx={sb.currentMealIdx}
          total={sb.totalMeals}
          selected={sb.selectedCellIdx}
          onSelect={sb.selectCell}
          variant={tweaks.timelineVariant}
        />
        <div className="op-bar-wrap">
          <OpBar
            selected={sb.selectedCellIdx}
            history={sb.history}
            onTrace={openTrace}
            onRollback={() => sb.openConfirm("rollback")}
            onBranch={() => sb.openConfirm("branch")}
            onDismiss={() => sb.selectCell(null)}
          />
        </div>
      </div>

      <div className="main">
        {sb.isInReviewMode && sb.reviewMeal ? (
          <ReviewCard
            meal={sb.reviewMeal}
            onOpenTrace={openTrace}
            onExit={() => sb.selectCell(null)}
          />
        ) : sb.isDone ? (
          <div className="col col-left" style={{ padding: "32px 16px", textAlign: "center" }}>
            <div className="col-head">
              <div className="h-title">Session 完成 ✓</div>
              <div className="h-sub">
                {sb.totalMeals}/{sb.totalMeals} 顿全部完成
              </div>
            </div>
            <p style={{ color: "var(--muted)", marginTop: 24 }}>
              点 timeline 过去格回顾, 或顶栏新建 / 分支重跑
            </p>
          </div>
        ) : (
          <DecisionArea
            recs={sb.currentRecs}
            selectedRank={selectedRank}
            onSelectRank={setSelectedRank}
            onEat={sb.handleEat}
            onSwap={sb.handleSwap}
            onRefine={sb.handleRefine}
            onSkip={sb.handleSkip}
            showDebug={tweaks.showDebugLayer}
            clock={sb.clock}
          />
        )}
        <RightCol
          decision={sb.lastDecision ?? IDLE_DECISION}
          density={density}
          onDensityChange={setDensity}
          onOpenTrace={openTrace}
        />
      </div>

      <SummaryDrawer
        open={sb.summaryOpen}
        history={sb.history}
        total={sb.totalMeals}
        sessionName={activeSession.name}
        onClose={sb.closeSummary}
        onOpenTrace={openTrace}
      />
      <ConfirmModal
        open={sb.confirmKind !== null}
        kind={sb.confirmKind}
        meal={sb.confirmMeal}
        currentIdx={sb.currentMealIdx}
        onClose={sb.closeConfirm}
        onConfirm={handleConfirm}
      />
      <RefineModal
        open={sb.refineModalOpen}
        onClose={sb.closeRefineModal}
        onApply={(text) => {
          sb.handleRefine(text);
          sb.closeRefineModal();
        }}
      />

      <TweaksPanel
        open={tweaksOpen}
        onClose={() => setTweaksOpen(false)}
        tweaks={tweaks}
        setTweak={setTweak}
      />
    </div>
  );
}

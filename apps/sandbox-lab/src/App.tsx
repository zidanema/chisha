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

  // S-08: backend status pill (顶层条件)
  const pillLabel =
    sb.backendOnline === null ? "pinging..."
      : sb.backendOnline ? "backend · :8765"
        : "mock · offline";
  const pillColor =
    sb.backendOnline === null ? "#9ca3af"
      : sb.backendOnline ? "#059669"
        : "#d97706";

  return (
    <div className="app">
      <div
        className="backend-pill"
        style={{
          position: "fixed",
          top: 4,
          right: 8,
          zIndex: 100,
          padding: "2px 8px",
          fontSize: 11,
          fontFamily: "var(--font-mono, monospace)",
          background: pillColor,
          color: "#fff",
          borderRadius: 4,
          opacity: 0.85,
          pointerEvents: "none",
        }}
        data-backend-online={sb.backendOnline === null ? "pending" : String(sb.backendOnline)}
      >
        {pillLabel}
      </div>

      {sb.apiError && (
        <div
          className="toast-error"
          style={{
            position: "fixed",
            top: 32,
            right: 8,
            zIndex: 100,
            maxWidth: 340,
            padding: "8px 12px",
            background: "#e11d48",
            color: "#fff",
            borderRadius: 6,
            fontSize: 12,
            boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
            display: "flex",
            gap: 8,
            alignItems: "flex-start",
          }}
        >
          <span style={{ flex: 1 }}>{sb.apiError}</span>
          <button
            onClick={sb.dismissApiError}
            style={{
              background: "transparent",
              border: "none",
              color: "#fff",
              cursor: "pointer",
              fontSize: 14,
              lineHeight: 1,
            }}
            aria-label="关闭错误提示"
          >
            ×
          </button>
        </div>
      )}

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

      {sb.polling && sb.polling.sid === sb.activeSessionId && (
        <div
          className="processing-banner"
          style={{
            padding: "6px 12px",
            background: "#fef3c7",
            color: "#92400e",
            borderTop: "1px solid #fcd34d",
            borderBottom: "1px solid #fcd34d",
            fontSize: 12,
          }}
          data-polling-action={sb.polling.action}
        >
          处理中... ({sb.polling.action})
        </div>
      )}

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
        ) : (sb.polling && sb.polling.sid === sb.activeSessionId) ? (
          <div className="col col-left" style={{ padding: "12px 8px" }}>
            <div className="col-head">
              <div className="h-title">推荐 · 处理中</div>
              <div className="h-sub">{sb.polling.action} job 进行中, 稍候</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
              {[1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="rec-skeleton"
                  style={{
                    height: 64,
                    background: "linear-gradient(90deg, #f1f5f9 0%, #e2e8f0 50%, #f1f5f9 100%)",
                    backgroundSize: "200% 100%",
                    animation: "skeleton-shimmer 1.4s linear infinite",
                    borderRadius: 6,
                  }}
                />
              ))}
            </div>
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

// D-088 S-02 App: 静态视觉布局, mock 数据喂全, 交互逻辑全 inert (S-03 接).
// query 演示控制:
//   ?dev=1            → 显示 TweaksPanel
//   ?demo-review=1    → 左列渲 ReviewCard 替代 DecisionArea (mock 第 1 顿 D1 午 eat)
//   ?demo-review=skip → 渲 skip 形态 (mock 第 3 顿 D2 午 skip)
//   ?demo-modal=summary|confirm-rollback|confirm-branch|refine → 强开对应 modal
import { useMemo, useState } from "react";
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
import { useTweaks } from "./hooks/useTweaks";
import * as MOCK from "./mocks/sbxMocks";
import type {
  BannerEntry,
  Clock,
  ConfirmKind,
} from "./types/sandbox";

type DemoModal = "summary" | "confirm-rollback" | "confirm-branch" | "refine" | null;

// ConfirmKind 在 types/sandbox 没 export, 这里本地 alias (modals/ConfirmModal 也定义)
type _ConfirmKind = ConfirmKind;

function readQuery(): {
  dev: boolean;
  demoReview: "eat" | "skip" | null;
  demoModal: DemoModal;
} {
  if (typeof window === "undefined") {
    return { dev: false, demoReview: null, demoModal: null };
  }
  const sp = new URLSearchParams(window.location.search);
  const demoReviewRaw = sp.get("demo-review");
  const demoModalRaw = sp.get("demo-modal");
  return {
    dev: sp.has("dev"),
    demoReview:
      demoReviewRaw === "1" || demoReviewRaw === "eat"
        ? "eat"
        : demoReviewRaw === "skip"
          ? "skip"
          : null,
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

  const clock: Clock = useMemo(
    () => ({
      idx: MOCK.CURRENT_IDX,
      day: Math.floor(MOCK.CURRENT_IDX / 2) + 1,
      slot: MOCK.CURRENT_IDX % 2 === 0 ? "午" : "晚",
      total: MOCK.TOTAL_MEALS,
    }),
    [],
  );

  const banners: BannerEntry[] = [
    {
      id: "demo-conflict",
      level: "warn",
      title: "Refine 冲突",
      detail: "推荐 #1 蓉香记 违反 active refine '戒辣' (含辣)",
      dismissable: true,
    },
  ];

  const reviewMeal =
    query.demoReview === "eat"
      ? MOCK.HISTORY[0]
      : query.demoReview === "skip"
        ? MOCK.HISTORY[2]
        : null;

  const summaryOpen = query.demoModal === "summary";
  const refineModalOpen = query.demoModal === "refine";
  const confirmKind: _ConfirmKind | null =
    query.demoModal === "confirm-rollback"
      ? "rollback"
      : query.demoModal === "confirm-branch"
        ? "branch"
        : null;
  const confirmMeal = confirmKind ? MOCK.HISTORY[1] : null;

  const noop = () => {};

  return (
    <div className="app">
      <TopBar
        sessions={MOCK.SESSIONS}
        activeSessionName="session-新打分"
        profile="profile@v2"
        seed={42}
        origin="真实快照"
        clock={clock}
        onOpenSummary={noop}
        onSelectSession={noop}
        onNewSession={noop}
        onOpenTweaks={() => setTweaksOpen(true)}
      />

      <Banners banners={banners} onDismiss={noop} />

      <div className="timeline-wrap">
        <Timeline
          history={MOCK.HISTORY}
          currentIdx={clock.idx}
          total={clock.total}
          selected={null}
          onSelect={noop}
          variant={tweaks.timelineVariant}
        />
        <div className="op-bar-wrap">
          <OpBar
            selected={null}
            history={MOCK.HISTORY}
            onTrace={noop}
            onRollback={noop}
            onBranch={noop}
            onDismiss={noop}
          />
        </div>
      </div>

      <div className="main">
        {reviewMeal ? (
          <ReviewCard meal={reviewMeal} onOpenTrace={noop} onExit={noop} />
        ) : (
          <DecisionArea
            recs={MOCK.CURRENT_RECS}
            selectedRank={2}
            onSelectRank={noop}
            onEat={noop}
            onSwap={noop}
            onRefine={noop}
            onSkip={noop}
            showDebug={tweaks.showDebugLayer}
            clock={clock}
          />
        )}
        <RightCol
          decision={MOCK.LAST_DECISION}
          density={density}
          onDensityChange={setDensity}
          onOpenTrace={noop}
        />
      </div>

      <SummaryDrawer
        open={summaryOpen}
        history={MOCK.HISTORY}
        total={MOCK.TOTAL_MEALS}
        sessionName="session-新打分"
        onClose={noop}
        onOpenTrace={noop}
      />
      <ConfirmModal
        open={confirmKind !== null}
        kind={confirmKind}
        meal={confirmMeal}
        currentIdx={clock.idx}
        onClose={noop}
        onConfirm={noop}
      />
      <RefineModal open={refineModalOpen} onClose={noop} onApply={noop} />

      <TweaksPanel
        open={tweaksOpen}
        onClose={() => setTweaksOpen(false)}
        tweaks={tweaks}
        setTweak={setTweak}
      />
    </div>
  );
}

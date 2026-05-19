// Workflow A · 分析 trace · Phase 1 实现.
// 数据全部走 React state (mock fallback in waMocks.ts), 不走 window.MOCK swap.
// Phase 2b 替换 mock 为 backend GET /api/traces + /api/trace/{id}/round/{rid}.

import { useEffect, useMemo, useRef, useState } from "react";
import { DagHeader } from "./components/DagHeader";
import { IntentStrip } from "./components/IntentStrip";
import { LookupDrawer } from "./components/LookupDrawer";
import { PanelRoundStrip, RoundBanner } from "./components/RoundBanner";
import { RefineTimeline } from "./components/RefineTimeline";
import { ThemeSwitcher } from "./components/ThemeSwitcher";
import { Toaster } from "./components/Toaster";
import { TraceBrowser } from "./components/TraceBrowser";
import { TraceContextBar } from "./components/TraceContextBar";
import { WorkspaceSwitch } from "./components/WorkspaceSwitch";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useTheme } from "./hooks/useTheme";
import { useWaTrace } from "./hooks/useWaTrace";
import { PanelL1 } from "./panels/PanelL1";
import { PanelL2 } from "./panels/PanelL2";
import { PanelL3 } from "./panels/PanelL3";
import { PanelFinal } from "./panels/PanelFinal";
import { PanelRefineIntentLLM } from "./panels/PanelRefineIntentLLM";
import type { RoundRecord, Session, WaTrace } from "./types/trace";

type DiffMode = "vs_r1" | "adjacent";

// 从 RoundRecord 构造 Session 形状, 喂给老 panel.
function roundToSession(round: RoundRecord, trace: WaTrace): Session {
  return {
    session_id: trace.meta.id,
    started_at: round.started_at,
    total_latency_ms: round.kpi.latency_ms,
    ctx_latency_ms: 14,
    final_latency_ms: 18,
    l1: round.l1,
    l2: round.l2,
    l3: round.l3,
    final: round.final,
    refine: {
      // 老 panel 还引用 session.refine; Workflow A 用 IntentStrip 替代, 这里给个 stub.
      parent_session: "", refine_session: "", user_text: round.user_input ?? "",
      parse_feedback: { llm_call: { model: "", latency_ms: 0, input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0 },
        chips_hit: [], note: "", rating_taste: null, want_again: false },
      chips_to_taste_hints: { boost: {}, penalty: {} },
      infer_refine_mood: { triggered: false, hits: [], resolved_mood: {} },
      diff: { new_in_top5: [], dropped_from_top5: [], moved_up: [], moved_down: [] },
      summary_kpi: { explore_n: 0, total_latency_ms: 0, candidates_returned: 0, diff_top5: 0 },
    },
  };
}

export function App() {
  const [theme, setTheme] = useTheme();
  const {
    traces,
    activeTraceId: activeTrace,
    setActiveTraceId: setActiveTrace,
    activeTrace: trace,
    getRoundFull,
    intentSchema,
    backendOnline,
  } = useWaTrace();
  const [activeRound, setActiveRound] = useState<string>("R1");
  const [expanded, setExpanded] = useState<Set<string>>(new Set([activeTrace]));
  const [tbCollapsed, setTbCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem("chisha:tbCollapsed") === "1"; } catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem("chisha:tbCollapsed", tbCollapsed ? "1" : "0"); } catch { /* ignore */ }
  }, [tbCollapsed]);

  const [base, setBase] = useState<string>("R1");
  const [target, setTarget] = useState<string>("R1");
  const [diffMode, setDiffMode] = useState<DiffMode>("vs_r1");
  const [intentCollapsed, setIntentCollapsed] = useState<boolean>(true);
  const [condensed, setCondensed] = useState<boolean>(false);
  const [lookupOpen, setLookupOpen] = useState<boolean>(false);

  // 当前 trace + 所有 round (来自 hook, backend / mock fallback 自动处理)
  const rounds = trace.rounds;
  const roundsSignature = rounds.map((r) => r.id).join(",");

  // D-088 (B1): trace 加载完成时 → 强制 reset 到 meta.latestRound. 不再 sticky 在
  // 上一 trace 的 round. useWaTrace 的 stale guard 已保证 trace.meta.id === activeTrace,
  // 所以这里直接 key on trace.meta.id 即可.
  useEffect(() => {
    if (rounds.length === 0) return;
    const latest = trace.meta.latestRound || rounds[rounds.length - 1].id;
    const first = rounds[0].id;
    setActiveRound(latest);
    setBase(first);
    setTarget(latest);
  }, [trace.meta.id, trace.meta.latestRound]);

  // 兜底: rounds 签名变化但 trace.meta.id 没变 (同 trace 加 round 罕见 case) →
  // 仅修无效值 (preserve 用户已主动切到的 round).
  useEffect(() => {
    if (rounds.length === 0) return;
    const latest = rounds[rounds.length - 1].id;
    const first = rounds[0].id;
    setActiveRound((prev) => rounds.find((r) => r.id === prev) ? prev : latest);
    setBase((prev) => rounds.find((r) => r.id === prev) ? prev : first);
    setTarget((prev) => rounds.find((r) => r.id === prev) ? prev : latest);
  }, [roundsSignature]);

  // activeRound 改变 → target 跟随
  useEffect(() => { setTarget(activeRound); }, [activeRound]);

  // base 跟 diffMode + target 派生
  useEffect(() => {
    if (rounds.length === 0) return;
    if (diffMode === "vs_r1") {
      setBase(rounds[0].id);
    } else {
      const idx = rounds.findIndex((r) => r.id === target);
      setBase(idx > 0 ? rounds[idx - 1].id : rounds[0].id);
    }
  }, [diffMode, target, rounds]);

  // 顶部 sticky-stack auto-condense — 用 IntersectionObserver + 哨兵元素,
  // 不再依赖 scrollTop 阈值. 旧实现 (scrollTop > 60 / < 20) 在 condense 后 sticky-stack
  // 收缩 ~150px → 浏览器把 scrollTop clamp 回 < 20 → 再 expand → 又 > 60 → 无限振荡.
  // 哨兵在 sticky-stack 正上方 1px, 一旦它离开视口顶端 → condense; 回到视口 → expand.
  // sticky-stack 高度变化不影响哨兵 (哨兵在它之前), 反馈环断掉.
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => setCondensed(!entry.isIntersecting),
      { threshold: 0, rootMargin: "0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // condense 时 IntentStrip auto-collapse (用户显式展开后这里就不再覆盖)
  useEffect(() => { if (condensed) setIntentCollapsed(true); }, [condensed]);

  const currentRound = useMemo(
    () => rounds.find((r) => r.id === activeRound) ?? rounds[0],
    [rounds, activeRound],
  );
  const baseRound = useMemo(() => rounds.find((r) => r.id === base) ?? null, [rounds, base]);
  const targetRoundStub = useMemo(
    () => rounds.find((r) => r.id === target) ?? currentRound,
    [rounds, target, currentRound],
  );
  const prevRound = useMemo(() => {
    if (!currentRound) return null;
    const i = rounds.findIndex((r) => r.id === currentRound.id);
    return i > 0 ? rounds[i - 1] : null;
  }, [rounds, currentRound]);

  // Lazy fetch target round full body (LRU cached). Stub fallback while pending.
  const targetRoundFull = getRoundFull(target) ?? targetRoundStub;

  // panel 喂当前 target round 的数据 (而非 active round; 切 base/target 时下方 panel 跟 target)
  const session = useMemo(
    () => (targetRoundFull ? roundToSession(targetRoundFull, trace) : null),
    [targetRoundFull, trace],
  );

  useKeyboardShortcuts({
    onOpenLookup: () => setLookupOpen(true),
    onCloseLookup: () => setLookupOpen(false),
    lookupOpen,
    rounds,
    setActiveRound,
  });

  // 兜底: trace 列表为空 / detail 缺 rounds (理论不发生, useWaTrace 永远 fallback mock).
  if (rounds.length === 0 || !currentRound) {
    return (
      <div className="shell wa">
        <header className="wa-topbar">
          <div className="brand">
            <div className="brand-dot"></div>
            <span>chisha</span>
            <span className="brand-sub">/debug</span>
          </div>
          <div className="right">
            <ThemeSwitcher theme={theme} setTheme={setTheme} />
          </div>
        </header>
        <div style={{ padding: 40, textAlign: "center", color: "var(--t-2)", fontFamily: "var(--mono)", fontSize: 13 }}>
          # 当前 trace 无 round 数据 · 等待 backend 同步 / 切到其它 trace
        </div>
      </div>
    );
  }

  function onSwap() {
    const b = base;
    setBase(target);
    setTarget(b);
    setActiveRound(b);
  }

  function handleNodeClick(id: string) {
    if (id === "ctx" || id === "refine") return;
    const el = document.querySelector(`[data-panel="${id}"]`) as HTMLElement | null;
    const content = document.querySelector(".content") as HTMLElement | null;
    if (el && content) {
      content.scrollTo({
        top: el.offsetTop - 240,
        behavior: "smooth",
      });
    }
  }

  return (
    <div className="shell wa" data-tb={tbCollapsed ? "collapsed" : "full"}>
      <header className="wa-topbar">
        <div className="brand">
          <div className="brand-dot"></div>
          <span>chisha</span>
          <span className="brand-sub">/debug</span>
        </div>
        <WorkspaceSwitch active="A" />
        <div className="right">
          <span
            className="pill live"
            style={!backendOnline ? { borderColor: "var(--warn-edge)", color: "var(--warn)" } : undefined}
          >
            {backendOnline ? "backend · :8765" : "mock · offline"}
          </span>
          <span>build <span className="mono" style={{ color: "var(--t-1)" }}>0.5.0-A.2</span></span>
          <button className="icon-btn" onClick={() => setLookupOpen(true)}>⌕ 追溯</button>
          <button className="icon-btn" onClick={() => { /* settings Phase 6 */ }}>⚙ 设置</button>
          <ThemeSwitcher theme={theme} setTheme={setTheme} />
        </div>
      </header>

      <div className="main">
        <TraceBrowser
          traces={traces}
          activeTrace={activeTrace} setActiveTrace={setActiveTrace}
          activeRound={activeRound} setActiveRound={setActiveRound}
          expanded={expanded} setExpanded={setExpanded}
          collapsed={tbCollapsed} setCollapsed={setTbCollapsed}
          onOpenLookup={() => setLookupOpen(true)}
          onOpenSettings={() => { /* settings Phase 6 */ }}
          activeRounds={rounds}
        />
        <div className="content wa">
          {/* sentinel: IntersectionObserver 监控它进出视口 → 决定 sticky-stack 是否 condensed.
              必须在 sticky-stack 之前, 不受 sticky-stack 高度变化影响, 防反馈环. */}
          <div ref={sentinelRef} className="sticky-sentinel" aria-hidden="true" />
          <div className={`sticky-stack ${condensed ? "condensed" : ""}`}>
            <TraceContextBar
              trace={trace.meta}
              round={currentRound}
              onOpenLookup={() => setLookupOpen(true)}
            />
            {rounds.length > 1 && (
              <IntentStrip
                round={currentRound}
                prevRound={prevRound}
                collapsed={intentCollapsed}
                setCollapsed={setIntentCollapsed}
                schema={intentSchema}
              />
            )}
            {rounds.length > 1 && (
              <RefineTimeline
                rounds={rounds}
                base={base} target={target}
                setBase={setBase}
                setTarget={(rid) => { setTarget(rid); setActiveRound(rid); }}
                onSwap={onSwap}
                diffMode={diffMode} setDiffMode={setDiffMode}
              />
            )}
            {session && (
              <DagHeader
                activeTab="main"
                fallbackL3LatencyMs={null}
                fallbackProvider={null}
                currentPanel="l1"
                onClickNode={handleNodeClick}
                compact={true}
                onToggleCompact={() => { /* always compact inside sticky stack */ }}
                runningPulse={false}
                session={session}
              />
            )}
          </div>

          <RoundBanner targetRound={targetRoundFull} baseRound={baseRound} />

          {/* D-089-S5b: R2+ refine round 含 refine_intent_llm 切片时, 在 L1 panel
              之上挂"意图解析 LLM call" panel. R1 / 无 refine intent LLM 调用时
              不挂载. 这是 Faithful Refine "执行用户表达" 的可证据视图. */}
          {targetRoundFull.refine_intent_llm && (
            <div className="panel-wrap" data-panel="refine_intent_llm">
              <PanelRefineIntentLLM trace={targetRoundFull.refine_intent_llm} />
            </div>
          )}

          <PanelRoundStrip layer="l1" targetRound={targetRoundFull} baseRound={baseRound} />
          <div className="panel-wrap" data-panel="l1"><PanelL1 l1={targetRoundFull.l1} /></div>
          <PanelRoundStrip layer="l2" targetRound={targetRoundFull} baseRound={baseRound} />
          <div className="panel-wrap" data-panel="l2"><PanelL2 l2={targetRoundFull.l2} /></div>
          <PanelRoundStrip layer="l3" targetRound={targetRoundFull} baseRound={baseRound} />
          <div className="panel-wrap" data-panel="l3">
            <PanelL3 l3={targetRoundFull.l3} finalRows={targetRoundFull.final} sessionId={trace.meta.id} />
          </div>
          <PanelRoundStrip layer="final" targetRound={targetRoundFull} baseRound={baseRound} />
          <div className="panel-wrap" data-panel="final">
            <PanelFinal rows={targetRoundFull.final} totalLatencyMs={targetRoundFull.kpi.latency_ms} />
          </div>

          <div style={{ height: 60 }}></div>
        </div>
      </div>

      <LookupDrawer
        open={lookupOpen}
        onClose={() => setLookupOpen(false)}
        currentRound={getRoundFull(activeRound) ?? currentRound ?? null}
        currentRoundId={activeRound}
      />
      <Toaster />
    </div>
  );
}

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BackendStatusPill } from "./components/BackendStatusPill";
import { Sidebar } from "./components/Sidebar";
import { DagHeader } from "./components/DagHeader";
import { SummaryCard } from "./components/SummaryCard";
import { EmptyStateHint } from "./components/EmptyStateHint";
import { LiveBanner } from "./components/LiveBanner";
import { ThemeSwitcher } from "./components/ThemeSwitcher";
import { Toaster, pushToast } from "./components/Toaster";
import { WhatIfPanel } from "./components/WhatIfPanel";
import { DEFAULT_PROFILE_OVERRIDE, DEFAULT_REFINE_TEXT, TODAY_ISO } from "./constants/defaults";
import { useTheme } from "./hooks/useTheme";
import { useSession } from "./hooks/useSession";
import { useTrace } from "./hooks/useTrace";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { loadConfig } from "./lib/sessionCache";
import { PanelL1 } from "./panels/PanelL1";
import { PanelL2 } from "./panels/PanelL2";
import { PanelL3 } from "./panels/PanelL3";
import { PanelFinal } from "./panels/PanelFinal";
import { PanelRefine } from "./panels/PanelRefine";
import { PanelTrace } from "./panels/PanelTrace";
import { FeedbackInputCard } from "./panels/FeedbackInputCard";
import type { Meal } from "./types/trace";

type Tab = "main" | "refine" | "trace";
// D-079: 三种 mode. Replay = 默认 (历史 trace), Live = /api/debug_recommend 临时试跑
// (永不写盘), WhatIf = 基于当前 Replay trace overlay 重跑下游.
type Mode = "replay" | "live" | "whatif";

function readQueryParams(): { sid: string | null; mode: Mode; whatIf: boolean } {
  if (typeof window === "undefined") return { sid: null, mode: "replay", whatIf: false };
  const qs = new URLSearchParams(window.location.search);
  const sid = qs.get("sid");
  const modeRaw = qs.get("mode");
  const mode: Mode = modeRaw === "live" ? "live" : "replay";
  const whatIf = qs.get("what_if") === "1";
  return { sid, mode, whatIf };
}

function writeQueryParams(p: { sid: string | null; mode: Mode; whatIf: boolean }) {
  if (typeof window === "undefined") return;
  const qs = new URLSearchParams(window.location.search);
  if (p.sid) qs.set("sid", p.sid); else qs.delete("sid");
  if (p.mode === "live") qs.set("mode", "live"); else qs.delete("mode");
  if (p.whatIf) qs.set("what_if", "1"); else qs.delete("what_if");
  const s = qs.toString();
  const url = `${window.location.pathname}${s ? `?${s}` : ""}`;
  window.history.replaceState(null, "", url);
}

const TABS: { id: Tab; label: string; sub: string; disabled?: boolean }[] = [
  { id: "main", label: "主视图", sub: "L1 / L2 / L3 / Final" },
  { id: "refine", label: "Refine", sub: "round 2 trace + diff" },
  { id: "trace", label: "追溯", sub: "命中定位" },
];

export function App() {
  const [theme, setTheme] = useTheme();
  const [tab, setTab] = useState<Tab>("main");
  const [meal, setMeal] = useState<Meal>("lunch");
  const [today] = useState(TODAY_ISO);
  const [llmAuto, setLlmAuto] = useState(true);
  const [refineText, setRefineText] = useState(DEFAULT_REFINE_TEXT);
  const [traceRest, setTraceRest] = useState("");
  const [traceDish, setTraceDish] = useState("");
  const [currentPanel, setCurrentPanel] = useState("l1");
  const [dagCompact, setDagCompact] = useState(false);
  const [profileOverride, setProfileOverride] = useState(DEFAULT_PROFILE_OVERRIDE);
  const clickIntentRef = useRef(0);

  const {
    session: liveSession,
    status,
    history,
    activeSessionId,
    setActiveSessionId,
    runMain,
    runRefine,
    backendOnline,
    corruptCount,
  } = useSession();
  const traceState = useTrace();

  // D-079: mode + What-if overlay. 进入页面读 URL 一次, 后续手动 setMode 同步回 URL.
  const initialQp = useMemo(() => readQueryParams(), []);
  const [mode, setMode] = useState<Mode>(initialQp.mode);
  const [whatIfOpen, setWhatIfOpen] = useState<boolean>(initialQp.whatIf);
  const [liveLlmCalled, setLiveLlmCalled] = useState<boolean | null>(null);

  // 首次挂载: 若 URL 带 sid 且与默认不一致, 切到该 sid (useSession 会异步 fetch).
  // 用 ref guard 防止 mount 期间 sync-back effect 先把 URL sid 抹掉 (Codex review).
  const urlInitDoneRef = useRef(false);
  useEffect(() => {
    if (initialQp.sid && initialQp.sid !== activeSessionId) {
      setActiveSessionId(initialQp.sid);
    }
    urlInitDoneRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // mode / sid / whatIf 任一变化都同步回 URL.
  // mount 期 (urlInitDoneRef=false) 跳过, 避免和上面 init effect race 抹 URL.
  useEffect(() => {
    if (!urlInitDoneRef.current) return;
    writeQueryParams({
      sid: mode === "live" ? null : activeSessionId,
      mode,
      whatIf: whatIfOpen,
    });
  }, [mode, activeSessionId, whatIfOpen]);

  useKeyboardShortcuts({
    onRunLive: () => { void handleRunLive(); },
    onRunRefine: handleRunRefine,
    isRunDisabled: () => status === "loading" || !profileParse.ok,
    hasRefineText: () => refineText.trim().length > 0,
  });

  // Validate profile JSON live. Invalid → disable Run; Run posts only when valid.
  const profileParse = useMemo(() => {
    const trimmed = profileOverride.trim();
    if (trimmed === "" || trimmed === "{}") {
      return { ok: true, value: null as Record<string, unknown> | null, error: null };
    }
    try {
      const parsed = JSON.parse(trimmed);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return { ok: true, value: parsed as Record<string, unknown>, error: null };
      }
      return { ok: false, value: null, error: "必须是 JSON 对象 {…}" };
    } catch (err) {
      return { ok: false, value: null, error: err instanceof Error ? err.message : "JSON 解析失败" };
    }
  }, [profileOverride]);

  // 真实 L3 fallback (provider chain) 在 PanelL3 内通过 session.l3.fallback_chain
  // 渲染. DagHeader 不再需要 fallback props.
  const session = liveSession;
  const runningPulse = status === "loading";

  useEffect(() => {
    const content = document.querySelector(".content");
    if (!content) return;
    const onScroll = () => {
      if (Date.now() - clickIntentRef.current < 700) return;
      const top = content.scrollTop;
      if (top > 120 && !dagCompact) setDagCompact(true);
      else if (top < 40 && dagCompact) setDagCompact(false);
    };
    content.addEventListener("scroll", onScroll, { passive: true });
    return () => content.removeEventListener("scroll", onScroll);
  }, [dagCompact, tab]);

  useEffect(() => {
    if (tab !== "main") return;
    const panels: { id: string; sel: string }[] = [
      { id: "l1", sel: '[data-panel="l1"]' },
      { id: "feedback", sel: '[data-panel="feedback"]' },  // D-083 PR-2
      { id: "l2", sel: '[data-panel="l2"]' },
      { id: "l3", sel: '[data-panel="l3"]' },
      { id: "final", sel: '[data-panel="final"]' },
    ];
    const els = panels
      .map((p) => ({ ...p, el: document.querySelector(p.sel) }))
      .filter((p): p is { id: string; sel: string; el: Element } => p.el != null);
    if (els.length === 0) return;
    const obs = new IntersectionObserver(
      (entries) => {
        const intersecting = entries.filter((e) => e.isIntersecting);
        if (intersecting.length === 0) return;
        const top = intersecting.sort(
          (a, b) => a.boundingClientRect.top - b.boundingClientRect.top,
        )[0];
        const p = els.find((p) => p.el === top.target);
        if (p) setCurrentPanel(p.id);
      },
      { rootMargin: "-280px 0px -50% 0px", threshold: 0 },
    );
    els.forEach((p) => obs.observe(p.el));
    return () => obs.disconnect();
  }, [tab]);

  function scrollContentTop() {
    const content = document.querySelector(".content");
    if (content) content.scrollTo({ top: 0, behavior: "smooth" });
  }

  // D-079: Live 模式 — /api/debug_recommend 跑一次, 永不落 localStorage 也永不落
  // 后端 trace_store (debug_recommend 自身不调 write_trace).
  // Real traces 由 apps/web /api/recommend (recommend_meal persist_trace=True) 写盘.
  // Codex NIT 修补: runMain 返回 fresh session, 直接从返值派生 llmCalled,
  // 避免 await 后读 liveSession state (React state 异步, closure 是 stale).
  const handleRunLive = useCallback(async () => {
    if (!profileParse.ok) {
      pushToast({ kind: "warn", title: "profile JSON 不合法", detail: profileParse.error ?? "" });
      return;
    }
    setTab("main");
    clickIntentRef.current = Date.now();
    scrollContentTop();
    setDagCompact(false);
    setMode("live");
    setWhatIfOpen(false);
    setLiveLlmCalled(null);
    const fresh = await runMain({
      meal,
      today,
      llmAuto,
      profileOverride: profileParse.value,
      profileOverrideRaw: profileOverride,
      live: true,
    });
    if (fresh) {
      setLiveLlmCalled(fresh.l3?.status === "ok");
    }
  }, [profileParse, meal, today, llmAuto, profileOverride, runMain]);

  function handleReplayConfig(id: string) {
    const cfg = loadConfig(id);
    if (!cfg) {
      pushToast({ kind: "warn", title: "无 config 缓存 (旧 session?)" });
      return;
    }
    setMeal(cfg.meal);
    setLlmAuto(cfg.llmAuto);
    setProfileOverride(cfg.profileOverride);
    pushToast({
      kind: "ok",
      title: "config 已复刻到 sidebar",
      detail: "改完点 ⚡ Live 试跑 / Cmd+Enter",
    });
  }

  async function handleRunRefine() {
    // D-082: 后端 /api/refine 直接写 round2 全量 trace 进同一文件.
    if (!activeSessionId) {
      pushToast({ kind: "warn", title: "无 active session", detail: "先选一条 history 或跑一次 Live" });
      return;
    }
    if (mode === "live") {
      pushToast({ kind: "warn", title: "Live 模式不支持 refine", detail: "Live 永不写盘. 切回 Replay 再 refine." });
      return;
    }
    const text = refineText.trim();
    if (!text) {
      pushToast({ kind: "warn", title: "refine_text 不能为空" });
      return;
    }
    setTab("refine");
    clickIntentRef.current = Date.now();
    scrollContentTop();
    await runRefine(text);
  }

  async function handleRunTrace() {
    if (!profileParse.ok) {
      pushToast({ kind: "warn", title: "profile JSON 不合法", detail: profileParse.error ?? "" });
      return;
    }
    const rest = traceRest.trim();
    const dishes = traceDish.split(/\s+/).map((s) => s.trim()).filter(Boolean);
    if (!rest && dishes.length === 0) {
      pushToast({ kind: "warn", title: "餐厅名或菜名至少填一项" });
      return;
    }
    setTab("trace");
    clickIntentRef.current = Date.now();
    scrollContentTop();
    setDagCompact(false);
    await traceState.runTrace({
      restaurant: rest,
      dishes,
      meal,
      today,
      profileOverride: profileParse.value,
    });
  }

  function handleExpandDag() {
    clickIntentRef.current = Date.now();
    scrollContentTop();
    setDagCompact(false);
  }

  function handleNodeClick(id: string) {
    if (id === "ctx") return;
    if (id === "refine") {
      setTab("refine");
      scrollContentTop();
      return;
    }
    setDagCompact(true);
    setCurrentPanel(id);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const el = document.querySelector(`[data-panel="${id}"]`) as HTMLElement | null;
        const content = document.querySelector(".content") as HTMLElement | null;
        if (el && content) {
          const offsetTop = el.offsetTop - 80;
          content.scrollTo({ top: Math.max(0, offsetTop), behavior: "smooth" });
        }
      });
    });
  }

  // Empty state: trace_store 空 + 没跑过 Live → session 为 null.
  const isEmptyState = session == null;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-dot"></div>
          <span className="brand-name">chisha</span>
          <span className="brand-sub">/debug</span>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab ${tab === t.id ? "active" : ""} ${t.disabled ? "disabled" : ""}`.trim()}
              onClick={() => !t.disabled && setTab(t.id)}
              disabled={t.disabled}
            >
              {t.label}
              <span className="badge">{t.sub}</span>
            </button>
          ))}
        </nav>
        <div className="right">
          <BackendStatusPill status={status} />
          <span>build <span className="mono" style={{ color: "var(--t-1)" }}>0.4.7</span></span>
          <ThemeSwitcher theme={theme} setTheme={setTheme} />
        </div>
      </header>

      <div className="main">
        <Sidebar
          meal={meal} setMeal={setMeal}
          llmAuto={llmAuto} setLlmAuto={setLlmAuto}
          onRunRefine={handleRunRefine}
          onRunTrace={handleRunTrace}
          refineText={refineText} setRefineText={setRefineText}
          traceRest={traceRest} setTraceRest={setTraceRest}
          traceDish={traceDish} setTraceDish={setTraceDish}
          history={history}
          activeSession={activeSessionId} setActiveSession={(id) => {
            // 点 history 行 → 默认回 Replay 模式 (Live 是单次试跑, 不持久化).
            setMode("replay");
            setActiveSessionId(id);
          }}
          profileOverride={profileOverride} setProfileOverride={setProfileOverride}
          profileError={profileParse.ok ? null : profileParse.error}
          runDisabled={status === "loading" || !profileParse.ok}
          onReplayConfig={handleReplayConfig}
          backendOnline={backendOnline}
          corruptCount={corruptCount}
          onRunLive={handleRunLive}
          onOpenWhatIf={() => {
            // What-if 只对 backend-backed Replay session 有意义
            // (Live/mock 没 base trace, 后端会 404).
            setMode("replay");
            setWhatIfOpen(true);
            setTab("main");
            scrollContentTop();
          }}
          whatIfAvailable={
            mode === "replay"
            && session != null
            && backendOnline === true
            && history.find((h) => h.id === activeSessionId)?.source === "backend"
          }
        />
        <div className="content">
          {mode === "live" && (
            <LiveBanner
              llmCalled={liveLlmCalled ?? undefined}
              onExit={() => {
                setMode("replay");
                setLiveLlmCalled(null);
              }}
            />
          )}
          {whatIfOpen && mode === "replay" && tab === "main" && session != null && (
            <WhatIfPanel
              baseSession={session}
              onClose={() => setWhatIfOpen(false)}
            />
          )}
          {/* D-085 PR-E: 人话层摘要 — 仅 replay mode + 非 what-if + 主 tab + 有持久化 session.
              Live trace 不持久化 → 调 summary endpoint 必 404, 屏蔽掉.
              What-if preview 同理 (后端虽容忍但不写盘, 没价值显示). */}
          {mode === "replay" && !whatIfOpen && tab === "main" && session != null
            && session.session_id && (
            <SummaryCard sessionId={session.session_id} />
          )}
          {session != null && (
            <DagHeader
              activeTab={tab}
              currentPanel={currentPanel}
              onClickNode={handleNodeClick}
              compact={dagCompact}
              onToggleCompact={dagCompact ? handleExpandDag : () => setDagCompact(true)}
              runningPulse={runningPulse}
              session={session}
            />
          )}
          {isEmptyState && <EmptyStateHint />}
          {tab === "main" && session != null && (
            <Fragment>
              <div data-panel="l1"><PanelL1 l1={session.l1} /></div>
              {/* D-083 PR-2: feedback view 派生层卡片. empty/undefined 时
                  FeedbackInputCard 内部 short-circuit 不渲染, 节省屏幕. */}
              <FeedbackInputCard snapshot={session.feedback_view_snapshot} />
              <div data-panel="l2"><PanelL2 l2={session.l2} /></div>
              <div data-panel="l3">
                <PanelL3
                  l3={session.l3}
                  finalRows={session.final}
                  sessionId={session.session_id}
                />
              </div>
              <div data-panel="final">
                <PanelFinal rows={session.final} totalLatencyMs={session.total_latency_ms} />
              </div>
              <div style={{ height: 60 }}></div>
            </Fragment>
          )}
          {tab === "refine" && session != null && (
            <Fragment>
              <PanelRefine session={session} />
              <div style={{ height: 60 }}></div>
            </Fragment>
          )}
          {tab === "trace" && (
            <Fragment>
              <PanelTrace
                trace={traceState.trace}
                droppedStage={traceState.droppedStage}
                status={traceState.status}
                error={traceState.error}
              />
              <div style={{ height: 60 }}></div>
            </Fragment>
          )}
        </div>
      </div>
      <Toaster />
    </div>
  );
}

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BackendStatusPill } from "./components/BackendStatusPill";
import { Sidebar } from "./components/Sidebar";
import { DagHeader } from "./components/DagHeader";
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
import { computeSessionDiff } from "./lib/diffSession";
import { deriveRefineSession } from "./mocks/refineSession";
import { L3_FALLBACK_EXAMPLE, MOCK_SESSION } from "./mocks/session";
import { PanelL1 } from "./panels/PanelL1";
import { PanelL2 } from "./panels/PanelL2";
import { PanelL3 } from "./panels/PanelL3";
import { PanelFinal } from "./panels/PanelFinal";
import { PanelRefine } from "./panels/PanelRefine";
import { PanelTrace } from "./panels/PanelTrace";
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
  { id: "refine", label: "Refine", sub: "二轮 / diff" },
  { id: "trace", label: "追溯", sub: "命中定位" },
];

export function App() {
  const [theme, setTheme] = useTheme();
  const [tab, setTab] = useState<Tab>("main");
  const [meal, setMeal] = useState<Meal>("lunch");
  const [today] = useState(TODAY_ISO);
  const [llmAuto, setLlmAuto] = useState(true);
  const [refineText, setRefineText] = useState(DEFAULT_REFINE_TEXT);
  // Submitted refine text drives the derived second-round Session. We don't
  // refresh on every keystroke (would shimmer badges) — only when the user
  // hits "触发 refine".
  const [submittedRefineText, setSubmittedRefineText] = useState<string | null>(null);
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
  useEffect(() => {
    if (initialQp.sid && initialQp.sid !== activeSessionId) {
      setActiveSessionId(initialQp.sid);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // mode / sid / whatIf 任一变化都同步回 URL.
  useEffect(() => {
    writeQueryParams({
      sid: mode === "live" ? null : activeSessionId,
      mode,
      whatIf: whatIfOpen,
    });
  }, [mode, activeSessionId, whatIfOpen]);

  useKeyboardShortcuts({
    onRunMain: handleRunMain,
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

  // Force-fallback toggle is only meaningful for the canonical mock session.
  // Live sessions show their actual L3 status. Phase 2: keep the toggle live
  // only for sess_a7f0 (mock fallback example) so the user can still demo
  // the fallback view; everything else renders the real session as-is.
  const useFallback = activeSessionId === "sess_a7f0";
  const session = useFallback
    ? { ...liveSession, l3: { ...liveSession.l3, ...L3_FALLBACK_EXAMPLE } }
    : liveSession;
  const fallbackL3LatencyMs = useFallback ? L3_FALLBACK_EXAMPLE.latency_ms : null;
  const fallbackProvider = useFallback ? L3_FALLBACK_EXAMPLE.resolved_provider : null;
  const runningPulse = status === "loading";

  // Phase 3 mock: derive second-round Session from first when user triggers
  // refine. Stable for the lifetime of `(session, submittedRefineText)`.
  // Phase 4+ replaces with /api/debug_refine round-trip.
  const secondSession = useMemo(() => {
    if (submittedRefineText == null) return null;
    return deriveRefineSession(session, submittedRefineText);
  }, [session, submittedRefineText]);

  const sessionDiff = useMemo(() => {
    if (!secondSession) return null;
    return computeSessionDiff(session, secondSession);
  }, [session, secondSession]);

  // sessionMock visibility: a one-time hint if the only entry is the canonical mock row.
  useEffect(() => {
    if (history.length === 1 && history[0].id === MOCK_SESSION.session_id) {
      // Don't toast on first mount; only when the user is about to interact.
      // Currently no toast — Phase 6 adds the "backend connect status" pill.
    }
  }, [history]);

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

  async function handleRunMain() {
    if (!profileParse.ok) {
      pushToast({
        kind: "warn",
        title: "profile JSON 不合法",
        detail: profileParse.error ?? "",
      });
      return;
    }
    setTab("main");
    clickIntentRef.current = Date.now();
    scrollContentTop();
    setDagCompact(false);
    setMode("replay");
    setWhatIfOpen(false);
    await runMain({
      meal,
      today,
      llmAuto,
      profileOverride: profileParse.value,
      profileOverrideRaw: profileOverride,
    });
  }

  // D-079: Live 模式 — /api/debug_recommend 跑一次, 永不落 localStorage 也永不落
  // 后端 trace_store (debug_recommend 自身不调 write_trace).
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
      detail: "改完点 ▶ 触发首轮推荐 / Cmd+Enter",
    });
  }

  function handleRunRefine() {
    // Phase 3: mock-derived second-round Session, not real backend yet.
    const trimmed = refineText.trim();
    if (!trimmed) {
      pushToast({ kind: "warn", title: "refine 文本不能为空" });
      return;
    }
    setTab("refine");
    clickIntentRef.current = Date.now();
    scrollContentTop();
    setDagCompact(false);
    setSubmittedRefineText(trimmed);
    pushToast({
      kind: "ok",
      title: "Refine round 2 (mock)",
      detail: "Phase 3 走 mock 派生。Phase 4+ 才接 /api/debug_refine 真链路。",
    });
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

  // Empty-state hint: never run + only the canonical mock row is in history.
  const isEmptyState =
    status === "idle" &&
    history.length === 1 &&
    history[0].id === MOCK_SESSION.session_id;

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
          onRunMain={handleRunMain}
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
          {whatIfOpen && mode === "replay" && tab === "main" && (
            <WhatIfPanel
              baseSession={session}
              onClose={() => setWhatIfOpen(false)}
            />
          )}
          <DagHeader
            activeTab={tab}
            fallbackL3LatencyMs={fallbackL3LatencyMs}
            fallbackProvider={fallbackProvider}
            currentPanel={currentPanel}
            onClickNode={handleNodeClick}
            compact={dagCompact}
            onToggleCompact={dagCompact ? handleExpandDag : () => setDagCompact(true)}
            runningPulse={runningPulse}
            session={session}
          />
          {isEmptyState && <EmptyStateHint />}
          {tab === "main" && (
            <Fragment>
              <div data-panel="l1"><PanelL1 l1={session.l1} /></div>
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
          {tab === "refine" && (
            <Fragment>
              <PanelRefine
                refine={secondSession?.refine ?? session.refine}
                secondSession={secondSession ?? undefined}
                diff={sessionDiff ?? undefined}
              />
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

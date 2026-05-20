// app.jsx — root component with V12 DagHeader + ThemeSwitcher

const TABS = [
  { id: "main",   label: "主视图",   sub: "L1 / L2 / L3 / Final" },
  { id: "refine", label: "Refine",  sub: "二轮 / diff" },
  { id: "trace",  label: "追溯",    sub: "coming soon", disabled: true },
];

const THEMES = [
  { id: "dark-cool",    name: "Dark · Cool",    sub: "多色 · 默认",      swatches: ["#1a1e25", "#6c7689", "oklch(0.74 0.13 195)", "oklch(0.78 0.14 70)", "oklch(0.72 0.14 270)"] },
  { id: "dark-warm",    name: "Dark · Warm",    sub: "暖灰 · 哑色",      swatches: ["#1f1a14", "#8a8170", "oklch(0.74 0.08 195)", "oklch(0.74 0.12 60)", "oklch(0.74 0.09 270)"] },
  { id: "dark-mono",    name: "Dark · Mono",    sub: "单 accent · Linear", swatches: ["#14171f", "#6c7689", "oklch(0.72 0.14 270)", "oklch(0.60 0.14 270)", "oklch(0.48 0.14 270)"] },
  { id: "light-paper",  name: "Light · Paper",  sub: "暖牛皮纸 · IDA",   swatches: ["#efeae0", "#5a4f3f", "oklch(0.56 0.11 195)", "oklch(0.62 0.14 50)", "oklch(0.50 0.14 270)"] },
  { id: "light-modern", name: "Light · Modern", sub: "冷净白 · GitHub",   swatches: ["#ffffff", "#4a5260", "oklch(0.62 0.13 195)", "oklch(0.68 0.13 60)", "oklch(0.55 0.14 270)"] },
];

function useTheme() {
  const stored = (typeof localStorage !== "undefined" && localStorage.getItem("chisha:theme")) || "dark-cool";
  const [theme, setTheme] = useState(stored);
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("chisha:theme", theme); } catch (e) {}
  }, [theme]);
  return [theme, setTheme];
}

function ThemeSwitcher({ theme, setTheme }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    function onClick(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);
  const current = THEMES.find(t => t.id === theme) || THEMES[0];
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className="theme-btn" onClick={() => setOpen(!open)}>
        <span className="swatch-row">
          {current.swatches.map((c, i) => (
            <span key={i} className="sw" style={{ background: c }}></span>
          ))}
        </span>
        <span>{current.name}</span>
        <span style={{ color: "var(--t-3)", fontSize: 9 }}>▾</span>
      </button>
      {open && (
        <div className="theme-pop" role="menu">
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--t-3)", textTransform: "uppercase", letterSpacing: "0.06em", padding: "4px 8px 6px" }}>palette</div>
          {THEMES.map(t => (
            <button
              key={t.id}
              className={`theme-opt ${t.id === theme ? "active" : ""}`}
              onClick={() => { setTheme(t.id); setOpen(false); }}
            >
              <span className="swatches">
                {t.swatches.map((c, i) => (
                  <span key={i} className="sw" style={{ background: c }}></span>
                ))}
              </span>
              <span>
                <span className="name">{t.name}</span>
                <div className="sub">{t.sub}</div>
              </span>
              <span style={{ color: t.id === theme ? "var(--accent)" : "transparent", fontFamily: "var(--mono)", fontSize: 11 }}>●</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function App() {
  const [theme, setTheme] = useTheme();
  const [tab, setTab] = useState("main");
  const [meal, setMeal] = useState("lunch");
  const [llmAuto, setLlmAuto] = useState(true);
  const [refineText, setRefineText] = useState("想喝汤，别给我面食");
  const [traceRest, setTraceRest] = useState("");
  const [traceDish, setTraceDish] = useState("");
  const [activeSession, setActiveSession] = useState("sess_a7f1");
  const [currentPanel, setCurrentPanel] = useState("l1");
  const [dagCompact, setDagCompact] = useState(false);
  const clickIntentRef = useRef(0);
  const [profileOverride, setProfileOverride] = useState(
`{
  "protein_floor_g": 22,
  "oil_avoid": ["high"],
  "budget_per_meal": 80,
  "weights": {
    "fit_diet": 0.18,
    "protein_density": 0.14
  }
}`);

  // Toggle L3 fallback view via active-session
  const useFallback = activeSession === "sess_a7f0";

  // Auto-collapse DAG when scrolling past a threshold
  useEffect(() => {
    const content = document.querySelector(".content");
    if (!content) return;
    const onScroll = () => {
      // ignore scroll events shortly after intentional navigation
      if (Date.now() - clickIntentRef.current < 700) return;
      const top = content.scrollTop;
      if (top > 120 && !dagCompact) setDagCompact(true);
      else if (top < 40 && dagCompact) setDagCompact(false);
    };
    content.addEventListener("scroll", onScroll, { passive: true });
    return () => content.removeEventListener("scroll", onScroll);
  }, [dagCompact, tab]);

  // Track which panel is in view via IntersectionObserver
  useEffect(() => {
    const panels = [
      { id: "l1",    sel: '[data-panel="l1"]' },
      { id: "l2",    sel: '[data-panel="l2"]' },
      { id: "l3",    sel: '[data-panel="l3"]' },
      { id: "final", sel: '[data-panel="final"]' },
    ];
    const els = panels.map(p => ({ ...p, el: document.querySelector(p.sel) })).filter(p => p.el);
    if (els.length === 0) return;
    const obs = new IntersectionObserver((entries) => {
      const intersecting = entries.filter(e => e.isIntersecting);
      if (intersecting.length === 0) return;
      const top = intersecting.sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      const p = els.find(p => p.el === top.target);
      if (p) setCurrentPanel(p.id);
    }, { rootMargin: "-280px 0px -50% 0px", threshold: 0 });
    els.forEach(p => obs.observe(p.el));
    return () => obs.disconnect();
  }, [tab]);

  const [runningPulse, setRunningPulse] = useState(false);

  function pulseRunning() {
    setRunningPulse(true);
    setTimeout(() => setRunningPulse(false), 1200);
  }

  function handleRunMain() {
    setTab("main");
    pulseRunning();
    clickIntentRef.current = Date.now();
    const content = document.querySelector(".content");
    if (content) content.scrollTo({ top: 0, behavior: "smooth" });
    setDagCompact(false);
  }

  function handleRunRefine() {
    setTab("refine");
    pulseRunning();
    clickIntentRef.current = Date.now();
    const content = document.querySelector(".content");
    if (content) content.scrollTo({ top: 0, behavior: "smooth" });
    setDagCompact(false);
  }

  function handleRunTrace() {
    alert("追溯 Tab 尚未实现 — 风格确认后会补上。\n输入: " + (traceRest || "(空)") + " / " + (traceDish || "(空)"));
  }

  function handleExpandDag() {
    clickIntentRef.current = Date.now();
    const content = document.querySelector(".content");
    if (content) content.scrollTo({ top: 0, behavior: "smooth" });
    setDagCompact(false);
  }

  function handleNodeClick(id) {
    if (id === "ctx") return;
    if (id === "refine") {
      setTab("refine");
      const content = document.querySelector(".content");
      if (content) content.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    // collapse DAG first so the scroll target lands precisely
    setDagCompact(true);
    setCurrentPanel(id);
    // wait for layout to settle, then scroll
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const el = document.querySelector(`[data-panel="${id}"]`);
        const content = document.querySelector(".content");
        if (el && content) {
          // collapsed strip is 41px (40 + 1 border) — leave 39px clear breathing room
          const offsetTop = el.offsetTop - 80;
          content.scrollTo({ top: Math.max(0, offsetTop), behavior: "smooth" });
        }
      });
    });
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-dot"></div>
          <span className="brand-name">chisha</span>
          <span className="brand-sub">/debug</span>
        </div>
        <nav className="tabs">
          {TABS.map(t => (
            <button
              key={t.id}
              className={`tab ${tab === t.id ? "active" : ""} ${t.disabled ? "disabled" : ""}`}
              onClick={() => !t.disabled && setTab(t.id)}
              disabled={t.disabled}
            >
              {t.label}
              <span className="badge">{t.sub}</span>
            </button>
          ))}
        </nav>
        <div className="right">
          <span className="pill live">backend FastAPI · :8000</span>
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
          history={window.MOCK.RUN_HISTORY}
          activeSession={activeSession} setActiveSession={setActiveSession}
          profileOverride={profileOverride} setProfileOverride={setProfileOverride}
        />
        <div className="content">
          <DagHeader
            activeTab={tab}
            useFallback={useFallback}
            currentPanel={currentPanel}
            onClickNode={handleNodeClick}
            compact={dagCompact}
            onToggleCompact={dagCompact ? handleExpandDag : () => setDagCompact(true)}
            runningPulse={runningPulse}
          />
          {tab === "main" && (
            <React.Fragment>
              <div data-panel="l1"><PanelL1 /></div>
              <div data-panel="l2"><PanelL2 /></div>
              <div data-panel="l3"><PanelL3 useFallback={useFallback} /></div>
              <div data-panel="final"><PanelFinal /></div>
              <div style={{ height: 60 }}></div>
            </React.Fragment>
          )}
          {tab === "refine" && (
            <React.Fragment>
              <PanelRefine />
              <div style={{ height: 60 }}></div>
            </React.Fragment>
          )}
          {tab === "trace" && null}
        </div>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);

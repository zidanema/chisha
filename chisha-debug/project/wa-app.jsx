// wa-app.jsx — root for Workflow A · 分析 trace

const THEMES = [
  { id: "dark-cool",    name: "Dark · Cool",    swatches: ["#1a1e25", "#6c7689", "oklch(0.74 0.13 195)", "oklch(0.78 0.14 70)", "oklch(0.72 0.14 270)"] },
  { id: "dark-warm",    name: "Dark · Warm",    swatches: ["#1f1a14", "#8a8170", "oklch(0.74 0.08 195)", "oklch(0.74 0.12 60)", "oklch(0.74 0.09 270)"] },
  { id: "dark-mono",    name: "Dark · Mono",    swatches: ["#14171f", "#6c7689", "oklch(0.72 0.14 270)", "oklch(0.60 0.14 270)", "oklch(0.48 0.14 270)"] },
  { id: "light-paper",  name: "Light · Paper",  swatches: ["#efeae0", "#5a4f3f", "oklch(0.56 0.11 195)", "oklch(0.62 0.14 50)", "oklch(0.50 0.14 270)"] },
  { id: "light-modern", name: "Light · Modern", swatches: ["#ffffff", "#4a5260", "oklch(0.62 0.13 195)", "oklch(0.68 0.13 60)", "oklch(0.55 0.14 270)"] },
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
      </button>
      {open && (
        <div className="theme-pop" role="menu">
          {THEMES.map(t => (
            <button key={t.id} className={`theme-opt ${t.id === theme ? "active" : ""}`}
              onClick={() => { setTheme(t.id); setOpen(false); }}>
              <span className="swatches">
                {t.swatches.map((c, i) => <span key={i} className="sw" style={{ background: c }}></span>)}
              </span>
              <span><span className="name">{t.name}</span></span>
              <span style={{ color: t.id === theme ? "var(--accent)" : "transparent", fontFamily: "var(--mono)", fontSize: 11 }}>●</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function WorkspaceSwitch({ active }) {
  return (
    <div className="workspace-switch">
      <button className={`ws ${active === "A" ? "active" : ""}`}>
        <span className="glyph">▣</span>
        <span>分析</span>
        <span className="sub">trace</span>
      </button>
      <button className="ws locked" title="B · 沙盒模拟 — 另起 brief">
        <span className="glyph">◌</span>
        <span>模拟</span>
        <span className="sub">敬待</span>
      </button>
    </div>
  );
}

function App() {
  const [theme, setTheme] = useTheme();
  const [condensed, setCondensed] = useState(false);
  const [tbCollapsed, setTbCollapsed] = useState(() => {
    try { return localStorage.getItem("chisha:tbCollapsed") === "1"; } catch (e) { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem("chisha:tbCollapsed", tbCollapsed ? "1" : "0"); } catch (e) {}
  }, [tbCollapsed]);

  // auto-condense sticky stack when user scrolls down
  useEffect(() => {
    const content = document.querySelector(".content");
    if (!content) return;
    const onScroll = () => {
      const top = content.scrollTop;
      if (top > 60 && !condensed) setCondensed(true);
      else if (top < 20 && condensed) setCondensed(false);
    };
    content.addEventListener("scroll", onScroll, { passive: true });
    return () => content.removeEventListener("scroll", onScroll);
  }, [condensed]);
  const [activeTrace, setActiveTrace] = useState(window.MOCK.session_id);
  const [activeRound, setActiveRound] = useState("R4");
  const [expanded, setExpanded] = useState(new Set([window.MOCK.session_id]));
  const [base, setBase] = useState("R1");
  const [target, setTarget] = useState("R4");
  const [diffMode, setDiffMode] = useState("vs_r1"); // "vs_r1" | "adjacent"
  const [intentCollapsed, setIntentCollapsed] = useState(true);
  // When the sticky-stack condenses on scroll, auto-collapse the intent strip;
  // explicit user clicks on the toggle still win (they just set intentCollapsed directly).
  useEffect(() => { if (condensed) setIntentCollapsed(true); }, [condensed]);
  const [lookupOpen, setLookupOpen] = useState(false);
  const [followupRef, setFollowupRef] = useState(null);

  const trace = window.WA_MOCK.TRACES.find(t => t.id === activeTrace) || window.WA_MOCK.TRACES[0];
  const rounds = trace && trace.id === window.MOCK.session_id ? window.WA_MOCK.ROUNDS : null;

  // when changing active trace, default round + base/target
  useEffect(() => {
    if (rounds) {
      setActiveRound(rounds[rounds.length - 1].id);
      setBase(rounds[0].id);
      setTarget(rounds[rounds.length - 1].id);
    } else {
      setActiveRound("R1");
    }
  }, [activeTrace]);

  // sync target = activeRound (clicking timeline node or sidebar sub-round sets activeRound)
  const didMountRef = useRef(false);
  useEffect(() => {
    setTarget(activeRound);
    if (!didMountRef.current) { didMountRef.current = true; return; }
    const t = setTimeout(scrollToBanner, 60);
    return () => clearTimeout(t);
  }, [activeRound]);

  // derive base from diffMode + current target
  useEffect(() => {
    if (!rounds) return;
    if (diffMode === "vs_r1") setBase(rounds[0].id);
    else {
      const idx = rounds.findIndex(r => r.id === target);
      if (idx > 0) setBase(rounds[idx - 1].id);
      else setBase(rounds[0].id);
    }
  }, [diffMode, target]);

  const currentRound = rounds ? (rounds.find(r => r.id === activeRound) || rounds[0]) : null;
  const baseRound = rounds ? rounds.find(r => r.id === base) : null;
  const targetRound = rounds ? rounds.find(r => r.id === target) : null;

  // Swap window.MOCK fields to the target round's dataset so the unchanged
  // L1/L2/L3/Final panels naturally re-render with that round's numbers.
  if (rounds && window.WA_ROUNDS_DATA && targetRound) {
    const data = window.WA_ROUNDS_DATA[targetRound.id];
    if (data) {
      window.MOCK.L1 = data.L1;
      window.MOCK.L2_COMBOS = data.L2_COMBOS;
      window.MOCK.L2_KPI = data.L2_KPI;
      window.MOCK.L3 = data.L3;
      window.MOCK.FINAL = data.FINAL;
    }
  }

  function onSwap() { const b = base; setBase(target); setTarget(b); setActiveRound(b); }

  function scrollToBanner() {
    const banner = document.querySelector(".round-banner");
    const content = document.querySelector(".content");
    if (banner && content) {
      const rect = banner.getBoundingClientRect();
      const ct = content.getBoundingClientRect();
      const stickyH = (document.querySelector(".sticky-stack") || {}).offsetHeight || 0;
      content.scrollTo({
        top: content.scrollTop + rect.top - ct.top - stickyH - 8,
        behavior: "smooth",
      });
    }
  }

  function handleTargetChange(rid) {
    setTarget(rid);
    setActiveRound(rid);
  }

  function scrollToFollowup() {
    if (followupRef && followupRef.scrollIntoView) {
      const content = document.querySelector(".content");
      const rect = followupRef.getBoundingClientRect();
      const ct = content.getBoundingClientRect();
      content.scrollTo({ top: content.scrollTop + rect.top - ct.top - 80, behavior: "smooth" });
      setTimeout(() => {
        const ta = followupRef.querySelector("textarea");
        if (ta) ta.focus();
      }, 400);
    }
  }

  function handleNodeClick(id) {
    if (id === "ctx" || id === "refine") return;
    const el = document.querySelector(`[data-panel="${id}"]`);
    const content = document.querySelector(".content");
    if (el && content) {
      const rect = el.getBoundingClientRect();
      const ct = content.getBoundingClientRect();
      content.scrollTo({ top: content.scrollTop + rect.top - ct.top - 240, behavior: "smooth" });
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
          <span className="pill live">backend FastAPI · :8000</span>
          <span>build <span className="mono" style={{ color: "var(--t-1)" }}>0.5.0-A</span></span>
          <button className="icon-btn" onClick={() => setLookupOpen(true)}>⌕ 追溯</button>
          <button className="icon-btn">⚙ 设置</button>
          <ThemeSwitcher theme={theme} setTheme={setTheme} />
        </div>
      </header>

      <div className="main">
        <TraceBrowser
          traces={window.WA_MOCK.TRACES}
          activeTrace={activeTrace} setActiveTrace={setActiveTrace}
          activeRound={activeRound} setActiveRound={setActiveRound}
          expanded={expanded} setExpanded={setExpanded}
          collapsed={tbCollapsed} setCollapsed={setTbCollapsed}
          onOpenLookup={() => setLookupOpen(true)}
          onOpenSettings={() => {}}
        />
        <div className="content wa">
          <div className={`sticky-stack ${condensed ? "condensed" : ""}`}>
            <TraceContextBar
              trace={trace} round={currentRound}
              onTriggerRefine={scrollToFollowup}
              onOpenLookup={() => setLookupOpen(true)}
            />
            {rounds && (
              <IntentStrip
                round={currentRound}
                prevRound={rounds[rounds.findIndex(r => r.id === currentRound.id) - 1]}
                collapsed={intentCollapsed}
                setCollapsed={setIntentCollapsed}
              />
            )}
            {rounds && (
              <RefineTimeline
                rounds={rounds}
                base={base} target={target}
                setBase={setBase}
                setTarget={handleTargetChange}
                onSwap={onSwap}
                diffMode={diffMode} setDiffMode={setDiffMode}
              />
            )}
            <DagHeader
              activeTab="main"
              useFallback={false}
              currentPanel="l1"
              onClickNode={handleNodeClick}
              compact={true}
              onToggleCompact={() => {}}
              runningPulse={false}
            />
          </div>

          <RoundBanner trace={trace} targetRound={targetRound} baseRound={baseRound} />

          <PanelRoundStrip layer="l1" targetRound={targetRound} baseRound={baseRound} />
          <div className="panel-wrap" data-panel="l1"><PanelL1 /></div>
          <PanelRoundStrip layer="l2" targetRound={targetRound} baseRound={baseRound} />
          <div className="panel-wrap" data-panel="l2"><PanelL2 /></div>
          <PanelRoundStrip layer="l3" targetRound={targetRound} baseRound={baseRound} />
          <div className="panel-wrap" data-panel="l3"><PanelL3 useFallback={false} /></div>
          <PanelRoundStrip layer="final" targetRound={targetRound} baseRound={baseRound} />
          <div className="panel-wrap" data-panel="final"><PanelFinal /></div>

          <div ref={setFollowupRef}></div>

          <div style={{ height: 60 }}></div>
        </div>
      </div>

      <LookupDrawer open={lookupOpen} onClose={() => setLookupOpen(false)} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);

// app.jsx — root component, tab switching, sticky summary

const TABS = [
  { id: "main",   label: "主视图",   sub: "L1 / L2 / L3 / Final" },
  { id: "refine", label: "Refine",  sub: "二轮 / diff" },
  { id: "trace",  label: "追溯",    sub: "coming soon", disabled: true },
];

function SummaryBar({ status }) {
  return (
    <div className="summary">
      <div className="summary-row">
        <div className="summary-id">
          <div className="lbl">session</div>
          <div className="val">{window.MOCK.session_id}</div>
        </div>
        <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
          <MiniFunnel stages={window.MOCK.L1.funnel} />
        </div>
        <div className="summary-status">
          <div className="summary-kpi">
            <div className="lbl">started</div>
            <div className="val">{window.MOCK.started_at.split(" ")[1]}</div>
          </div>
          <div className="summary-kpi">
            <div className="lbl">total latency</div>
            <div className="val">{window.MOCK.total_latency_ms}ms</div>
          </div>
          <div className="summary-kpi">
            <div className="lbl">L3 status</div>
            <div><StatusBadge status={status} size="lg" /></div>
          </div>
        </div>
      </div>
    </div>
  );
}

function App() {
  const [tab, setTab] = useState("main");
  const [meal, setMeal] = useState("lunch");
  const [llmAuto, setLlmAuto] = useState(true);
  const [refineText, setRefineText] = useState("想喝汤，别给我面食");
  const [traceRest, setTraceRest] = useState("");
  const [traceDish, setTraceDish] = useState("");
  const [activeSession, setActiveSession] = useState("sess_a7f1");
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

  // Toggle L3 fallback view via active-session: sess_a7f0 = fallback example
  const useFallback = activeSession === "sess_a7f0";
  const l3Status = useFallback ? "fallback" : "ok";

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
        </div>
      </header>

      <div className="main">
        <Sidebar
          meal={meal} setMeal={setMeal}
          llmAuto={llmAuto} setLlmAuto={setLlmAuto}
          onRunMain={() => setTab("main")}
          onRunRefine={() => setTab("refine")}
          onRunTrace={() => {}}
          refineText={refineText} setRefineText={setRefineText}
          traceRest={traceRest} setTraceRest={setTraceRest}
          traceDish={traceDish} setTraceDish={setTraceDish}
          history={window.MOCK.RUN_HISTORY}
          activeSession={activeSession} setActiveSession={setActiveSession}
          profileOverride={profileOverride} setProfileOverride={setProfileOverride}
        />
        <div className="content">
          <SummaryBar status={l3Status} />
          {tab === "main" && (
            <React.Fragment>
              <PanelL1 />
              <PanelL2 />
              <PanelL3 useFallback={useFallback} />
              <PanelFinal />
              <div style={{ height: 40 }}></div>
            </React.Fragment>
          )}
          {tab === "refine" && (
            <React.Fragment>
              <PanelRefine />
              <div style={{ height: 40 }}></div>
            </React.Fragment>
          )}
          {tab === "trace" && null}
        </div>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);

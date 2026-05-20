// dag-header.jsx — DAG visualization replacing summary bar

function DagHeader({ activeTab, useFallback, currentPanel, onClickNode, compact, onToggleCompact, runningPulse }) {
  const session = window.MOCK.session_id;
  const startedTime = window.MOCK.started_at.split(" ")[1];
  const totalLatency = window.MOCK.total_latency_ms;
  const l3Status = useFallback ? "fallback" : "ok";

  // node positions — laid out in a fixed-width-ish row that adapts to container
  // We use percentage positioning so it scales with the content width
  const nodes = activeTab === "refine"
    ? [
        { id: "ctx",    x: "1%",   y: 36,  tone: "ctx",    title: "build_context",  metric: "profile", sub: "lunch · 深圳湾", lat: "14ms" },
        { id: "l1",     x: "16%",  y: 36,  tone: "l1",     title: "11k dishes",     metric: "1,207", subm: "combo", sub: "31 rest", lat: "194ms" },
        { id: "l2",     x: "31%",  y: 36,  tone: "l2",     title: "12-dim + cap K=4", metric: "60", subm: "top", sub: "84→31", lat: "38ms" },
        { id: "l3",     x: "46%",  y: 36,  tone: "l3",     title: "opus-4-7 · tool_use", metric: "2,148", subm: "ms", sub: "cache 82%", lat: "OK", warn: true },
        { id: "final",  x: "61%",  y: 36,  tone: "final",  title: "3 exploit + 2 explore", metric: "5", subm: "picks", sub: "¥90", lat: "18ms" },
        { id: "refine", x: "78%",  y: 36,  tone: "refine", title: "parse → chips → rerun", metric: "+2 / −2", subm: "diff", sub: "haiku · 412ms", lat: "2,310ms" },
      ]
    : [
        { id: "ctx",    x: "1%",   y: 36,  tone: "ctx",    title: "build_context",   metric: "profile", sub: "lunch · 深圳湾", lat: "14ms" },
        { id: "l1",     x: "16.5%",y: 36,  tone: "l1",     title: "11,123 dishes",   metric: "1,207", subm: "combo", sub: "31 rest", lat: "194ms" },
        { id: "l2",     x: "33%",  y: 36,  tone: "l2",     title: "12-dim · cap K=4",metric: "60", subm: "top", sub: "84→31 rest", lat: "38ms" },
        { id: "l3",     x: "49.5%",y: 36,  tone: "l3",     title: useFallback ? "FALLBACK · sonnet" : "opus-4-7 · tool_use", metric: useFallback ? "5,732" : "2,148", subm: "ms", sub: useFallback ? "openrouter" : "cache 82%", lat: useFallback ? "FB" : "OK", warn: true, fb: useFallback },
        { id: "final",  x: "66%",  y: 36,  tone: "final",  title: "3 exploit + 2 explore", metric: "5", subm: "picks", sub: "¥90 · 22min", lat: "18ms" },
      ];

  return (
    <div className={`dag-header ${compact ? "compact" : ""} ${runningPulse ? "running" : ""}`}>
      <div className="dag-strip">
        <span className="session">
          <span className="val">{session}</span>
          <span className="lat">{totalLatency}ms</span>
        </span>
        <div className="nodes">
          {nodes.filter(n => n.id !== "ctx").map((n, i, arr) => (
            <React.Fragment key={n.id}>
              <button
                className={`chip ${n.tone} ${useFallback && n.id === "l3" ? "fb" : ""} ${currentPanel === n.id ? "selected" : ""}`}
                onClick={() => onClickNode && onClickNode(n.id)}
              >
                {n.id === "l1" ? "L1" :
                 n.id === "l2" ? "L2" :
                 n.id === "l3" ? "L3" :
                 n.id === "final" ? "FINAL" :
                 n.id === "refine" ? "REFINE" : n.id}
                <span className="v">{n.metric}{n.subm ? n.subm : ""}</span>
              </button>
              {i < arr.length - 1 && <span className="arrow">→</span>}
            </React.Fragment>
          ))}
        </div>
        {useFallback && (
          <span className="strip-warn">
            <span className="pulse"></span>L3 fallback
          </span>
        )}
        <button className="expand-btn" onClick={onToggleCompact}>
          <span>展开 DAG</span> <span style={{ opacity: 0.6 }}>▾</span>
        </button>
      </div>

      <div className="dag-session">
        <div className="group">
          <span><span className="lbl">session</span><span className="val">{session}</span></span>
          <span className="sep">·</span>
          <span><span className="lbl">started</span><span className="val">{startedTime}</span></span>
          <span className="sep">·</span>
          <span><span className="lbl">total</span><span className="val">{totalLatency}ms</span></span>
        </div>
        <div></div>
        <div className="group">
          <span><span className="lbl">L3</span><StatusBadge status={l3Status} /></span>
          <span className="sep">·</span>
          <span><span className="lbl">tokens</span><span className="val">{window.MOCK.L3.input_tokens.toLocaleString()} in / {window.MOCK.L3.output_tokens} out</span></span>
          <span className="sep">·</span>
          <span><span className="lbl">cache hit</span><span className="val" style={{ color: "var(--refine)" }}>{Math.round(window.MOCK.L3.cache_read_input_tokens / window.MOCK.L3.input_tokens * 1000) / 10}%</span></span>
        </div>
      </div>

      <div className="dag-canvas">
        <svg>
          <defs>
            <marker id="dag-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill="var(--t-2)" />
            </marker>
            <marker id="dag-arrow-pink" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill="var(--refine)" />
            </marker>
          </defs>
          {/* draw straight horizontal arrows between successive nodes */}
          <DagArrows nodes={nodes} activeTab={activeTab} />
        </svg>

        {nodes.map(n => (
          <div
            key={n.id}
            className={`dag-node ${currentPanel === n.id ? "selected" : ""}`}
            style={{ left: n.x, top: n.y, width: activeTab === "refine" ? 138 : 154 }}
            onClick={() => onClickNode && onClickNode(n.id)}
          >
            <div className={`dag-node-head ${n.tone}`}>
              <span className="dot"></span>
              {n.id === "ctx" ? "CTX" :
               n.id === "l1" ? "L1 · RECALL" :
               n.id === "l2" ? "L2 · SCORE" :
               n.id === "l3" ? (n.fb ? "L3 · FALLBACK" : "L3 · LLM") :
               n.id === "final" ? "FINAL" :
               n.id === "refine" ? "REFINE" : n.id.toUpperCase()}
            </div>
            <div className="dag-node-body">
              <div className="title">{n.title}</div>
              <div className={`metric ${n.warn ? "warn" : ""}`}>
                {n.metric}{n.subm ? <span className="s">{n.subm}</span> : null}
              </div>
              <div className="lat">
                <span>{n.sub}</span>
                <span className={n.lat === "OK" ? "ok" : n.lat === "FB" ? "err" : ""}>{n.lat}</span>
              </div>
            </div>
          </div>
        ))}

        <div className="dag-legend">
          <span><span className="swatch" style={{ background: "var(--L1)" }}></span>L1</span>
          <span><span className="swatch" style={{ background: "var(--L2)" }}></span>L2</span>
          <span><span className="swatch" style={{ background: "var(--L3)" }}></span>L3</span>
          <span><span className="swatch" style={{ background: "var(--final)" }}></span>final</span>
          {activeTab === "refine" && (
            <span><span className="swatch" style={{ background: "var(--refine)" }}></span>refine</span>
          )}
          <button
            onClick={onToggleCompact}
            style={{ marginLeft: 8, background: "transparent", border: "1px solid var(--line)", color: "var(--t-2)", padding: "1px 7px", fontFamily: "var(--mono)", fontSize: 9, borderRadius: 2, cursor: "pointer" }}
          >
            收起 ▴
          </button>
        </div>
      </div>
    </div>
  );
}

// SVG arrows between consecutive nodes — measured in container coords
function DagArrows({ nodes, activeTab }) {
  // We can't easily measure DOM here; use approximate node geometry.
  // Each node is ~152px wide for main tab, ~138px for refine.
  // The nodes are positioned by percent — we draw the arrows using
  // calc-based SVG via foreignObject? Or use approximations.
  // For simplicity: render fixed positions assuming canvas width ~1100px.
  // Actual visual mapping: x percentages will offset, but we draw arrows
  // based on percentage as well using viewBox-less SVG (uses px coords).
  // We'll attach refs on first render to measure real positions.
  const [arrows, setArrows] = useState([]);
  useEffect(() => {
    const canvas = document.querySelector(".dag-canvas");
    if (!canvas) return;
    const cw = canvas.clientWidth;
    const W = activeTab === "refine" ? 138 : 154;
    const H = 78;
    // recompute positions in pixels
    const positions = nodes.map(n => {
      const xPct = parseFloat(n.x);
      const xPx = (xPct / 100) * cw;
      return { x: xPx, y: n.y, w: W, h: H, id: n.id };
    });
    const ar = [];
    for (let i = 0; i < positions.length - 1; i++) {
      const a = positions[i];
      const b = positions[i + 1];
      ar.push({ x1: a.x + a.w, y1: a.y + a.h / 2, x2: b.x, y2: b.y + b.h / 2, dashed: b.id === "refine" });
    }
    setArrows(ar);
    const onResize = () => {
      const cw2 = canvas.clientWidth;
      const positions2 = nodes.map(n => {
        const xPct = parseFloat(n.x);
        return { x: (xPct / 100) * cw2, y: n.y, w: W, h: H, id: n.id };
      });
      const ar2 = [];
      for (let i = 0; i < positions2.length - 1; i++) {
        const a = positions2[i];
        const b = positions2[i + 1];
        ar2.push({ x1: a.x + a.w, y1: a.y + a.h / 2, x2: b.x, y2: b.y + b.h / 2, dashed: b.id === "refine" });
      }
      setArrows(ar2);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [nodes, activeTab]);

  return (
    <React.Fragment>
      {arrows.map((a, i) => (
        <line
          key={i}
          x1={a.x1} y1={a.y1} x2={a.x2} y2={a.y2}
          stroke={a.dashed ? "var(--refine)" : "var(--t-2)"}
          strokeWidth="1.5"
          strokeDasharray={a.dashed ? "4 3" : undefined}
          markerEnd={a.dashed ? "url(#dag-arrow-pink)" : "url(#dag-arrow)"}
        />
      ))}
    </React.Fragment>
  );
}

window.DagHeader = DagHeader;

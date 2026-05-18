// panel-final.jsx — Final top 5 cards

function FlagDot({ ok, label, invert }) {
  // invert = true means "ok if false" (e.g. processed_meat)
  const actuallyOk = invert ? !ok : ok;
  return (
    <span className={`flag ${actuallyOk ? "ok" : "bad"}`}>
      <span className="x">{actuallyOk ? "✓" : "✗"}</span>
      {label}
    </span>
  );
}

function FinalCard({ c }) {
  return (
    <div className="final-card">
      <div className="rank-row">
        <div className={`rank ${c.kind === "explore" ? "explore" : ""}`}>{c.rank}</div>
        {c.kind === "explore" ? <span className="tag-explore">explore</span> : <span className="tag-exploit">exploit</span>}
        <span className="mono dim" style={{ fontSize: 10, marginLeft: "auto" }}>{c.combo_id}</span>
      </div>

      <h4>{c.restaurant}</h4>

      <div className="meta-row">
        <span>{c.distance_km}km</span>
        <span>{c.eta_min}min</span>
        <span className="price">¥{c.total_price}</span>
      </div>

      <div className="dishes">
        {c.dishes.map((d, i) => (
          <div className="dish" key={i}>
            <span className="dish-name">{d.name}</span>
            <span className="dish-price">¥{d.price}</span>
          </div>
        ))}
      </div>

      <div className="scores">
        <div className="s">
          <div className="k">score</div>
          <div className="v">{c.score.toFixed(3)}</div>
        </div>
        <div className="s">
          <div className="k">fit_score</div>
          <div className="v">{c.fit_score.toFixed(2)}</div>
        </div>
      </div>

      <div>
        <div className="dim" style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>health flags</div>
        <div className="flag-list">
          <FlagDot ok={c.health_flags.veg_ok} label="veg" />
          <FlagDot ok={c.health_flags.protein_ok} label="protein" />
          <FlagDot ok={c.health_flags.oil_ok} label="oil" />
          <FlagDot ok={c.health_flags.wetness_ok} label="wetness" />
          <FlagDot ok={c.health_flags.processed_meat} label="no-process" invert />
          <FlagDot ok={c.health_flags.sweet_sauce} label="no-sweet" invert />
        </div>
      </div>

      {c.risk_flags.length > 0 && (
        <div>
          <div className="dim" style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>risk</div>
          <div className="flag-list">
            {c.risk_flags.map(r => <span className="flag warn" key={r}>! {r}</span>)}
          </div>
        </div>
      )}

      <div className="reason-box">{c.reason}</div>
    </div>
  );
}

function PanelFinal() {
  const FINAL = window.MOCK.FINAL;
  const exploreN = FINAL.filter(c => c.kind === "explore").length;
  const exploitN = FINAL.length - exploreN;
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="layer-tag">FINAL</span>
        <h2>Top 5</h2>
        <span className="subtitle">{exploitN} exploit + {exploreN} explore</span>
        <div className="right">
          <Pill tone="gray">总 latency <span className="mono">{window.MOCK.total_latency_ms}ms</span></Pill>
          <CopyBtn label="export JSON" />
        </div>
      </div>
      <div className="panel-body">
        <div className="final-grid">
          {FINAL.map(c => <FinalCard key={c.combo_id} c={c} />)}
        </div>
      </div>
    </div>
  );
}

window.PanelFinal = PanelFinal;

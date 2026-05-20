// panel-l2.jsx — L2 scoring with always-visible weight breakdown heatmap

function heatColor(v, w) {
  // v normalized -0.2..1.2; w sign affects whether high is good
  const sign = w >= 0 ? 1 : -1;
  const eff = v * sign;
  // map eff to [-1..1]
  const norm = Math.max(-1, Math.min(1, (eff - 0.3) / 0.9));
  if (norm >= 0) {
    // green
    const a = 0.15 + norm * 0.7;
    return `oklch(0.40 ${0.10 + norm * 0.10} 145 / ${a})`;
  } else {
    const a = 0.15 + (-norm) * 0.55;
    return `oklch(0.35 ${0.08 + (-norm) * 0.10} 25 / ${a})`;
  }
}

function ComboHeatmapRow({ combo, weights }) {
  return (
    <tr>
      <td className="rank-cell">#{combo.rank}</td>
      <td className="restaurant-cell" title={combo.restaurant}>{combo.restaurant}</td>
      <td className="total-cell">{combo.total_score.toFixed(3)}</td>
      {weights.map(w => {
        const v = combo.breakdown[w.key];
        return (
          <td key={w.key} className="cell" style={{ background: heatColor(v, w.w) }}>
            {v.toFixed(2)}
          </td>
        );
      })}
    </tr>
  );
}

function ComboRow({ combo, open, onToggle }) {
  return (
    <React.Fragment>
      <tr className={`combo-row ${open ? "open" : ""}`} onClick={onToggle}>
        <td>
          <span className="chev">▶</span>
        </td>
        <td className="mono">#{combo.rank}</td>
        <td className="mono">{combo.combo_id}</td>
        <td>{combo.restaurant}</td>
        <td className="mono right">{combo.total_score.toFixed(3)}</td>
        <td className="mono right">{combo.fit_score.toFixed(2)}</td>
        <td className="mono right">{combo.eta_min}min</td>
        <td className="mono right">¥{combo.total_price}</td>
        <td className="mono right">{combo.dishes.length}</td>
      </tr>
      {open && (
        <tr className="combo-detail">
          <td colSpan="9">
            <div className="inner">
              {combo.dishes.map((d, i) => (
                <div className="dish-card" key={i}>
                  <div>
                    <div className="dish-name">{d.name}</div>
                    <div className="dish-attrs">
                      <span className={`attr-chip ${d.oil === "high" ? "red" : d.oil === "mid" ? "orange" : "green"}`}>oil:{d.oil}</span>
                      <span className={`attr-chip ${d.spicy === "high" ? "red" : ""}`}>spicy:{d.spicy}</span>
                      <span className="attr-chip">protein:{d.protein_g}g</span>
                      <span className="attr-chip">cook:{d.cook}</span>
                      <span className="attr-chip">main:{d.main}</span>
                      <span className="attr-chip">role:{d.role}</span>
                      <span className="attr-chip">wetness:{d.wetness}</span>
                      <span className={`attr-chip ${d.sweet === "high" ? "orange" : ""}`}>sweet:{d.sweet}</span>
                      <span className="attr-chip">grain:{d.grain}</span>
                    </div>
                  </div>
                  <div className="price">¥{d.price}</div>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </React.Fragment>
  );
}

function PanelL2() {
  const { L2_WEIGHTS, L2_COMBOS, L2_KPI } = window.MOCK;
  const [openIds, setOpenIds] = useState(new Set([L2_COMBOS[0].combo_id]));
  const [heatLimit, setHeatLimit] = useState(15);
  const toggle = id => {
    const next = new Set(openIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOpenIds(next);
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="layer-tag">L2</span>
        <h2>打分 · score V2</h2>
        <span className="subtitle">12 维加权 + 4 层 cap · top60 → L3</span>
        <div className="right">
          <Pill tone="gray">latency <span className="mono">38ms</span></Pill>
          <CopyBtn label="export top60" />
        </div>
      </div>
      <div className="panel-body">
        <div className="kpi-strip">
          <div className="kpi">
            <div className="lbl">Score range</div>
            <div className="val">{L2_KPI.score_min} → {L2_KPI.score_max}</div>
          </div>
          <div className="kpi">
            <div className="lbl">cap K</div>
            <div className="val">{L2_KPI.cap_k}</div>
            <div className="delta">brand_top_k <span className="arrow">·</span> {L2_KPI.per_brand_top_k}</div>
          </div>
          <div className="kpi">
            <div className="lbl">per_restaurant_cap_k</div>
            <div className="val">{L2_KPI.per_restaurant_cap_k}</div>
          </div>
          <div className="kpi">
            <div className="lbl">top60 涉及餐厅数</div>
            <div className="val">{L2_KPI.restaurants_after_cap}</div>
            <div className="delta">cap 前 {L2_KPI.restaurants_before_cap} <span className="arrow">→</span> 后 {L2_KPI.restaurants_after_cap}</div>
          </div>
          <div className="kpi">
            <div className="lbl">单店最多 combo</div>
            <div className="val">{L2_KPI.max_combos_one_rest_after}</div>
            <div className="delta">cap 前 {L2_KPI.max_combos_one_rest_before} <span className="arrow">→</span> 后 {L2_KPI.max_combos_one_rest_after}</div>
          </div>
          <div className="kpi">
            <div className="lbl">送 L3 candidates</div>
            <div className="val">60</div>
            <div className="delta">从 1207 combo 中</div>
          </div>
        </div>

        <div className="heatmap-wrap">
          <div className="heatmap-head">
            <h4>权重 × top {heatLimit} combo · 维度贡献分布</h4>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <div className="seg" style={{ width: 220 }}>
                {[10, 15, 30, 60].map(n => (
                  <button key={n} className={heatLimit === n ? "on" : ""} onClick={() => setHeatLimit(n)}>top {n}</button>
                ))}
              </div>
              <div className="legend">
                <span>− 拉低</span>
                <div className="grad"></div>
                <span>+ 拉高</span>
              </div>
            </div>
          </div>
          <table className="heatmap-table">
            <thead>
              <tr>
                <th className="col-head"></th>
                <th className="col-head"></th>
                <th className="col-head" style={{ paddingBottom: 8 }}><span style={{ transform: "rotate(0)", left: 0, fontWeight: 600, color: "var(--t-0)" }}>total</span></th>
                {L2_WEIGHTS.map(w => (
                  <th key={w.key} className="col-head"><span>{w.label}</span></th>
                ))}
              </tr>
              <tr className="weight-row">
                <td className="rank-cell" style={{ color: "var(--blue)" }}>w</td>
                <td className="restaurant-cell" style={{ color: "var(--blue)" }}>权重</td>
                <td className="total-cell" style={{ color: "var(--blue)" }}>—</td>
                {L2_WEIGHTS.map(w => (
                  <td key={w.key} className="cell" style={{ background: "var(--bg-3)", color: w.w < 0 ? "var(--red)" : "var(--blue)" }}>
                    {w.w > 0 ? "+" : ""}{w.w.toFixed(2)}
                  </td>
                ))}
              </tr>
            </thead>
            <tbody>
              {L2_COMBOS.slice(0, heatLimit).map(c => (
                <ComboHeatmapRow key={c.combo_id} combo={c} weights={L2_WEIGHTS} />
              ))}
            </tbody>
          </table>
        </div>

        <div className="combo-table-wrap">
          <table className="tbl" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th style={{ width: 24 }}></th>
                <th>#</th>
                <th>combo_id</th>
                <th>餐厅</th>
                <th className="right">total_score</th>
                <th className="right">fit_score</th>
                <th className="right">ETA</th>
                <th className="right">价</th>
                <th className="right">菜数</th>
              </tr>
            </thead>
            <tbody>
              {L2_COMBOS.map(c => (
                <ComboRow key={c.combo_id} combo={c} open={openIds.has(c.combo_id)} onToggle={() => toggle(c.combo_id)} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

window.PanelL2 = PanelL2;

// panel-l1.jsx — L1 recall funnel + drop reasons

function FunnelRow({ stage, value, dropped, max, kind, idx, prev, scaleMode }) {
  // linear: width = value/max
  // log:    width = log10(value+1) / log10(max+1)  — makes 137 visible alongside 11,123
  const linearPct = (value / max) * 100;
  const logPct = (Math.log10(value + 1) / Math.log10(max + 1)) * 100;
  const widthPct = scaleMode === "log" ? logPct : linearPct;

  const passRate = prev != null ? Math.round((value / prev) * 1000) / 10 : null;
  const dropPct = prev != null ? Math.round((1 - value / prev) * 1000) / 10 : 0;
  const color = kind === "rest" ? "warm" : kind === "combo" ? "green" : "";
  const unitLabel = { dish: "道菜", rest: "家餐厅", combo: "个 combo" }[kind] || "";

  // pass rate visualized as thin orange bar (smaller = more aggressive cut)
  const passBarWidth = prev != null ? Math.max(2, Math.round(value / prev * 100)) : 100;

  return (
    <div className="funnel-row">
      <div className="funnel-meta">
        <div className="stage">{stage}</div>
        <div className="value num">
          {value.toLocaleString()}
          <span className="dim" style={{ fontSize: 10, marginLeft: 4, fontWeight: 400 }}>{unitLabel}</span>
        </div>
      </div>
      <div className="funnel-bars">
        <div className={`funnel-bar ${scaleMode === "log" ? "log" : ""}`}>
          <div className={`fill ${color}`} style={{ width: `${widthPct}%` }}></div>
        </div>
        {prev != null && (
          <div className="funnel-bar thin" title={`pass ${passRate}% · drop ${dropPct}%`}>
            <div className="fill" style={{ width: `${passBarWidth}%` }}></div>
          </div>
        )}
      </div>
      <div className="funnel-foot">
        <span className="pass">
          {passRate != null ? <>pass <span className="num" style={{ color: "var(--t-1)" }}>{passRate}%</span></> : <span className="dim">· baseline</span>}
        </span>
        {dropped > 0 && <span className="drop">− {dropped.toLocaleString()} dropped</span>}
      </div>
    </div>
  );
}

function PanelL1() {
  const L1 = window.MOCK.L1;
  const max = L1.funnel[0].value;
  const [scaleMode, setScaleMode] = useState("log");
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="layer-tag">L1</span>
        <h2>召回 · recall</h2>
        <span className="subtitle">{L1.area} · {L1.raw_dishes.toLocaleString()} 道菜 / {L1.raw_restaurants} 家</span>
        <div className="right">
          <Pill tone="gray">总 latency <span className="mono">194ms</span></Pill>
        </div>
      </div>
      <div className="panel-body">
        <div className="l1-grid">
          <div className="funnel">
            <div className="funnel-title row between" style={{ marginBottom: 12 }}>
              <span>漏斗衰减 · 11k → final combo</span>
              <div className="seg" style={{ width: 110, textTransform: "none", letterSpacing: 0 }}>
                <button className={scaleMode === "log" ? "on" : ""} onClick={() => setScaleMode("log")}>log</button>
                <button className={scaleMode === "linear" ? "on" : ""} onClick={() => setScaleMode("linear")}>linear</button>
              </div>
            </div>
            {L1.funnel.map((s, i) => (
              <FunnelRow
                key={s.stage}
                stage={s.label}
                value={s.value}
                dropped={s.dropped}
                max={max}
                kind={s.kind}
                idx={i}
                prev={i > 0 ? L1.funnel[i - 1].value : null}
                scaleMode={scaleMode}
              />
            ))}
            <div className="funnel-scale">
              <span>{scaleMode === "log" ? "10⁰" : "0"}</span>
              <span>{scaleMode === "log" ? "10¹" : "·"}</span>
              <span>{scaleMode === "log" ? "10²" : "·"}</span>
              <span>{scaleMode === "log" ? "10³" : "·"}</span>
              <span>{scaleMode === "log" ? "10⁴" : max.toLocaleString()}</span>
            </div>
            <div className="dim mono" style={{ fontSize: 10, marginTop: 6, lineHeight: 1.6 }}>
              # 主条 = 数量级 (log)；细条 = pass% (相对上一阶段)
            </div>
          </div>

          <div className="l1-right">
            <div>
              <div className="subhead">
                菜级丢弃原因聚合 <span className="count">{L1.dish_drops.reduce((a, b) => a + b.count, 0).toLocaleString()} dropped</span>
              </div>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>原因</th>
                    <th>层</th>
                    <th className="right">数量</th>
                  </tr>
                </thead>
                <tbody>
                  {L1.dish_drops.map((d, i) => {
                    const tot = L1.dish_drops.reduce((a, b) => a + b.count, 0);
                    const pct = Math.round(d.count / tot * 1000) / 10;
                    const tone = d.layer === "diversity" ? "orange" : d.layer === "price" ? "blue" : "red";
                    return (
                      <tr key={i}>
                        <td className="reason">{d.reason}</td>
                        <td><Pill tone={d.layer === "diversity" ? "orange" : d.layer === "price" ? "blue" : "red"}>{d.layer}</Pill></td>
                        <td className="right">
                          <div className="bar-cell">
                            <div className="bar">
                              <div className={`fill ${tone === "orange" ? "orange" : tone === "blue" ? "" : "red"}`} style={{ width: `${pct}%` }}></div>
                            </div>
                            <span className="v">{d.count.toLocaleString()}</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              <div>
                <div className="subhead">
                  餐厅级 ban 明细 <span className="count">{L1.restaurant_bans.length}</span>
                </div>
                <table className="tbl">
                  <thead>
                    <tr><th>餐厅</th><th>原因</th></tr>
                  </thead>
                  <tbody>
                    {L1.restaurant_bans.map((b, i) => (
                      <tr key={i}>
                        <td className="mono" style={{ fontSize: 11 }}>{b.rest}</td>
                        <td className="reason mono" style={{ fontSize: 10 }}>{b.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div>
                <div className="subhead">
                  餐厅出 combo 数 Top 20 <span className="count">{L1.top_restaurants.length}</span>
                </div>
                <table className="tbl">
                  <thead>
                    <tr><th>餐厅</th><th className="right">combos</th></tr>
                  </thead>
                  <tbody>
                    {L1.top_restaurants.map((r, i) => {
                      const max = L1.top_restaurants[0].combos;
                      const pct = Math.round(r.combos / max * 100);
                      return (
                        <tr key={i}>
                          <td className="mono" style={{ fontSize: 11 }}>{r.name}</td>
                          <td className="right">
                            <div className="bar-cell">
                              <div className="bar"><div className="fill" style={{ width: `${pct}%` }}></div></div>
                              <span className="v">{r.combos}</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.PanelL1 = PanelL1;

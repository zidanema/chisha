import { useState } from "react";
import { Pill } from "../components/ui/Pill";
import type { L1Trace, FunnelStageKind } from "../types/trace";

type ScaleMode = "log" | "linear";

const UNIT_LABEL: Record<FunnelStageKind, string> = {
  dish: "道菜",
  rest: "家餐厅",
  combo: "个 combo",
};

function FunnelRow({
  stage, value, dropped, max, kind, prev, scaleMode,
}: {
  stage: string;
  value: number;
  dropped: number;
  max: number;
  kind: FunnelStageKind;
  prev: number | null;
  scaleMode: ScaleMode;
}) {
  const linearPct = (value / max) * 100;
  const logPct = (Math.log10(value + 1) / Math.log10(max + 1)) * 100;
  const widthPct = scaleMode === "log" ? logPct : linearPct;

  const passRate = prev != null && prev !== 0 ? Math.round((value / prev) * 1000) / 10 : null;
  const dropPct = prev != null && prev !== 0 ? Math.round((1 - value / prev) * 1000) / 10 : 0;
  const color = kind === "rest" ? "warm" : kind === "combo" ? "green" : "";
  const unitLabel = UNIT_LABEL[kind] ?? "";
  const passBarWidth = prev != null && prev !== 0 ? Math.max(2, Math.round((value / prev) * 100)) : 100;

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
        <div className={`funnel-bar ${scaleMode === "log" ? "log" : ""}`.trim()}>
          <div className={`fill ${color}`.trim()} style={{ width: `${widthPct}%` }}></div>
        </div>
        {prev != null && (
          <div className="funnel-bar thin" title={`pass ${passRate}% · drop ${dropPct}%`}>
            <div className="fill" style={{ width: `${passBarWidth}%` }}></div>
          </div>
        )}
      </div>
      <div className="funnel-foot">
        <span className="pass">
          {passRate != null ? (
            <>pass <span className="num" style={{ color: "var(--t-1)" }}>{passRate}%</span></>
          ) : (
            <span className="dim">· baseline</span>
          )}
        </span>
        {dropped > 0 && <span className="drop">− {dropped.toLocaleString()} dropped</span>}
      </div>
    </div>
  );
}

export function PanelL1({ l1 }: { l1: L1Trace }) {
  const [scaleMode, setScaleMode] = useState<ScaleMode>("log");
  const max = l1.funnel[0]?.value ?? 1;
  const totalDishDrops = l1.dish_drops.reduce((a, b) => a + b.count, 0);
  const topRestaurantMax = l1.top_restaurants[0]?.combos ?? 1;

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="layer-tag layer-l1">L1</span>
        <h2>召回 · recall</h2>
        <span className="subtitle">
          {l1.area} · {l1.raw_dishes.toLocaleString()} 道菜 / {l1.raw_restaurants} 家
        </span>
        <div className="right">
          <Pill tone="gray">总 latency <span className="mono">{l1.latency_ms}ms</span></Pill>
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
            {l1.funnel.map((s, i) => (
              <FunnelRow
                key={s.stage}
                stage={s.label}
                value={s.value}
                dropped={s.dropped}
                max={max}
                kind={s.kind}
                prev={i > 0 ? l1.funnel[i - 1].value : null}
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
              # 主条 = 数量级 (log);细条 = pass% (相对上一阶段)
            </div>
          </div>

          <div className="l1-right">
            <div>
              <div className="subhead">
                菜级丢弃原因聚合
                <span className="count">{totalDishDrops.toLocaleString()} dropped</span>
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
                  {l1.dish_drops.map((d, i) => {
                    const pct = totalDishDrops === 0 ? 0 : Math.round((d.count / totalDishDrops) * 1000) / 10;
                    const tone = d.layer === "diversity" ? "orange" : d.layer === "price" ? "blue" : "red";
                    const fillCls = tone === "orange" ? "orange" : tone === "blue" ? "" : "red";
                    return (
                      <tr key={i}>
                        <td className="reason">{d.reason}</td>
                        <td>
                          <Pill tone={tone}>{d.layer}</Pill>
                        </td>
                        <td className="right">
                          <div className="bar-cell">
                            <div className="bar">
                              <div className={`fill ${fillCls}`.trim()} style={{ width: `${pct}%` }}></div>
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
                  餐厅级 ban 明细 <span className="count">{l1.restaurant_bans.length}</span>
                </div>
                <table className="tbl">
                  <thead>
                    <tr><th>餐厅</th><th>原因</th></tr>
                  </thead>
                  <tbody>
                    {l1.restaurant_bans.map((b, i) => (
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
                  餐厅出 combo 数 Top 20 <span className="count">{l1.top_restaurants.length}</span>
                </div>
                <table className="tbl">
                  <thead>
                    <tr><th>餐厅</th><th className="right">combos</th></tr>
                  </thead>
                  <tbody>
                    {l1.top_restaurants.map((r, i) => {
                      const pct = topRestaurantMax === 0 ? 0 : Math.round((r.combos / topRestaurantMax) * 100);
                      return (
                        <tr key={i}>
                          <td className="mono" style={{ fontSize: 11 }}>{r.name}</td>
                          <td className="right">
                            <div className="bar-cell">
                              <div className="bar">
                                <div className="fill" style={{ width: `${pct}%` }}></div>
                              </div>
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

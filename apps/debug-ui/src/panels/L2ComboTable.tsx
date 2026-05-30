import { Fragment, useState } from "react";
import type { L2Combo } from "../types/trace";

function dishOilCls(oil: string): string {
  if (oil === "high") return "red";
  if (oil === "mid") return "orange";
  return "green";
}

function ComboRow({
  combo, open, onToggle,
}: {
  combo: L2Combo;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <Fragment>
      <tr
        className={`combo-row ${open ? "open" : ""}`.trim()}
        onClick={onToggle}
      >
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
          <td colSpan={9}>
            <div className="inner">
              {combo.dishes.map((d, i) => (
                <div className="dish-card" key={i}>
                  <div>
                    <div className="dish-name">{d.name}</div>
                    <div className="dish-attrs">
                      <span className={`attr-chip ${dishOilCls(d.oil)}`}>oil:{d.oil}</span>
                      <span className={`attr-chip ${d.spicy === "high" ? "red" : ""}`.trim()}>spicy:{d.spicy}</span>
                      <span className="attr-chip">protein:{d.protein_g}g</span>
                      <span className="attr-chip">cook:{d.cook}</span>
                      <span className="attr-chip">main:{d.main}</span>
                      <span className="attr-chip">role:{d.role}</span>
                      <span className="attr-chip">wetness:{d.wetness}</span>
                      <span className={`attr-chip ${d.sweet === "high" ? "orange" : ""}`.trim()}>sweet:{d.sweet}</span>
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
    </Fragment>
  );
}

export function L2ComboTable({
  combos,
}: {
  combos: L2Combo[];
}) {
  const initialOpen = combos[0] ? new Set([combos[0].combo_id]) : new Set<string>();
  const [openIds, setOpenIds] = useState<Set<string>>(initialOpen);
  const toggle = (id: string) => {
    const next = new Set(openIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOpenIds(next);
  };

  return (
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
          {combos.map((c) => (
            <ComboRow
              key={c.combo_id}
              combo={c}
              open={openIds.has(c.combo_id)}
              onToggle={() => toggle(c.combo_id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

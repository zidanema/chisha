import { Fragment, useState } from "react";
import { Pill } from "../components/ui/Pill";
import { comboDiffBadge, type ComboDiff } from "../lib/diffSession";
import type { L2Combo } from "../types/trace";

function dishOilCls(oil: string): string {
  if (oil === "high") return "red";
  if (oil === "mid") return "orange";
  return "green";
}

function DiffBadge({ diff }: { diff: ComboDiff | undefined }) {
  if (!diff) return <span className="dim mono" style={{ fontSize: 10 }}>—</span>;
  const meta = comboDiffBadge(diff);
  if (!meta) return <span className="dim mono" style={{ fontSize: 10 }}>—</span>;
  return <Pill tone={meta.tone}>{meta.text}</Pill>;
}

function ComboRow({
  combo, open, onToggle, diff,
}: {
  combo: L2Combo;
  open: boolean;
  onToggle: () => void;
  diff: ComboDiff | undefined;
}) {
  const isDropped = diff?.kind === "DROPPED";
  return (
    <Fragment>
      <tr
        className={`combo-row ${open ? "open" : ""}`.trim()}
        onClick={onToggle}
        style={isDropped ? { opacity: 0.45 } : undefined}
      >
        <td>
          <span className="chev">▶</span>
        </td>
        {diff !== undefined && <td><DiffBadge diff={diff} /></td>}
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
          <td colSpan={diff !== undefined ? 10 : 9}>
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
  diff,
}: {
  combos: L2Combo[];
  diff?: Map<string, ComboDiff>;
}) {
  const initialOpen = combos[0] ? new Set([combos[0].combo_id]) : new Set<string>();
  const [openIds, setOpenIds] = useState<Set<string>>(initialOpen);
  const toggle = (id: string) => {
    const next = new Set(openIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOpenIds(next);
  };
  const showDiff = diff !== undefined;
  // When showDiff, also surface dropped entries (combo_id not in `combos` list).
  const droppedDiffs = showDiff
    ? Array.from(diff.values()).filter((d) => d.kind === "DROPPED")
    : [];

  return (
    <div className="combo-table-wrap">
      <table className="tbl" style={{ width: "100%" }}>
        <thead>
          <tr>
            <th style={{ width: 24 }}></th>
            {showDiff && <th style={{ width: 80 }}>diff</th>}
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
              diff={diff?.get(c.combo_id)}
            />
          ))}
          {showDiff && droppedDiffs.length > 0 && (
            <tr>
              <td colSpan={10} style={{ padding: "8px 12px",
                                        borderTop: "1px dashed var(--line-strong)",
                                        background: "var(--bg-inset)",
                                        fontSize: 10, color: "var(--t-3)",
                                        fontFamily: "var(--mono)" }}>
                # 以下 {droppedDiffs.length} 个 combo 第一轮存在但二轮被剔除 (rank-only view)
              </td>
            </tr>
          )}
          {showDiff && droppedDiffs.map((d) => (
            <tr key={`drop-${d.combo_id}`} style={{ opacity: 0.5 }}>
              <td><span className="chev" style={{ opacity: 0.3 }}>·</span></td>
              <td><DiffBadge diff={d} /></td>
              <td className="mono">#{d.firstRank ?? "?"}</td>
              <td className="mono">{d.combo_id}</td>
              <td className="dim">(已踢出)</td>
              <td className="mono right dim">—</td>
              <td className="mono right dim">—</td>
              <td className="mono right dim">—</td>
              <td className="mono right dim">—</td>
              <td className="mono right dim">—</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

import { useMemo, useState } from "react";
import type { L2Combo, L2Weight } from "../types/trace";

const HEAT_LIMITS = [10, 15, 30, 60] as const;

type SortDir = "desc" | "asc";
type SortState = { key: string; dir: SortDir } | null;

function nextSortState(prev: SortState, key: string): SortState {
  if (!prev || prev.key !== key) return { key, dir: "desc" };
  if (prev.dir === "desc") return { key, dir: "asc" };
  return null;  // 3rd click clears
}

function heatColor(v: number, w: number): string {
  const sign = w >= 0 ? 1 : -1;
  const eff = v * sign;
  const norm = Math.max(-1, Math.min(1, (eff - 0.3) / 0.9));
  if (norm >= 0) {
    const a = 0.15 + norm * 0.7;
    return `oklch(0.40 ${0.10 + norm * 0.10} 145 / ${a})`;
  }
  const a = 0.15 + -norm * 0.55;
  return `oklch(0.35 ${0.08 + -norm * 0.10} 25 / ${a})`;
}

function ComboHeatmapRow({ combo, weights }: { combo: L2Combo; weights: L2Weight[] }) {
  return (
    <tr>
      <td className="rank-cell">#{combo.rank}</td>
      <td className="restaurant-cell" title={combo.restaurant}>{combo.restaurant}</td>
      <td className="total-cell">{combo.total_score.toFixed(3)}</td>
      {weights.map((w) => {
        const v = combo.breakdown[w.key];
        if (v == null) {
          return (
            <td key={w.key} className="cell" style={{ background: "var(--bg-3)", color: "var(--t-3)" }}>—</td>
          );
        }
        return (
          <td key={w.key} className="cell" style={{ background: heatColor(v, w.w) }}>
            {v.toFixed(2)}
          </td>
        );
      })}
    </tr>
  );
}

export function L2Heatmap({
  weights, combos,
}: {
  weights: L2Weight[];
  combos: L2Combo[];
}) {
  const [heatLimit, setHeatLimit] = useState<number>(15);
  const [sort, setSort] = useState<SortState>(null);

  // Pure derived data — never mutates the source `combos` array.
  const displayCombos = useMemo(() => {
    if (!sort) return combos.slice(0, heatLimit);
    const dir = sort.dir === "desc" ? -1 : 1;
    const sorted = [...combos].sort((a, b) => {
      const av = sort.key === "total" ? a.total_score : (a.breakdown[sort.key] ?? -Infinity);
      const bv = sort.key === "total" ? b.total_score : (b.breakdown[sort.key] ?? -Infinity);
      return av === bv ? 0 : av > bv ? dir : -dir;
    });
    return sorted.slice(0, heatLimit);
  }, [combos, heatLimit, sort]);

  const sortIndicator = (key: string): string => {
    if (!sort || sort.key !== key) return "";
    return sort.dir === "desc" ? " ▼" : " ▲";
  };

  return (
    <div className="heatmap-wrap">
      <div className="heatmap-head">
        <h4>权重 × top {heatLimit} combo · 维度贡献分布</h4>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div className="seg" style={{ width: 220 }}>
            {HEAT_LIMITS.map((n) => (
              <button key={n} className={heatLimit === n ? "on" : ""} onClick={() => setHeatLimit(n)}>
                top {n}
              </button>
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
            <th
              className="col-head"
              style={{ paddingBottom: 8, cursor: "pointer" }}
              onClick={() => setSort((prev) => nextSortState(prev, "total"))}
              title="点击排序 (desc → asc → off)"
            >
              <span style={{ transform: "rotate(0)", left: 0, fontWeight: 600, color: "var(--t-0)" }}>
                total{sortIndicator("total")}
              </span>
            </th>
            {weights.map((w) => (
              <th
                key={w.key}
                className="col-head"
                style={{ cursor: "pointer" }}
                onClick={() => setSort((prev) => nextSortState(prev, w.key))}
                title="点击排序 (desc → asc → off)"
              >
                <span>{w.label}{sortIndicator(w.key)}</span>
              </th>
            ))}
          </tr>
          <tr className="weight-row">
            <td className="rank-cell" style={{ color: "var(--blue)" }}>w</td>
            <td className="restaurant-cell" style={{ color: "var(--blue)" }}>权重</td>
            <td className="total-cell" style={{ color: "var(--blue)" }}>—</td>
            {weights.map((w) => (
              <td
                key={w.key}
                className="cell"
                style={{ background: "var(--bg-3)", color: w.w < 0 ? "var(--red)" : "var(--blue)" }}
              >
                {w.w > 0 ? "+" : ""}{w.w.toFixed(2)}
              </td>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayCombos.map((c) => (
            <ComboHeatmapRow key={c.combo_id} combo={c} weights={weights} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

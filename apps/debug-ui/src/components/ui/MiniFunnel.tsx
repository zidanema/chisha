import { Fragment } from "react";
import type { FunnelStage } from "../../types/trace";

export function MiniFunnel({ stages }: { stages: FunnelStage[] }) {
  // Pick 5 representative stages: raw → recall passed → final combos → top 60 → top 5
  const picked = [
    { k: "DISHES", v: stages[0]?.value.toLocaleString() ?? "—" },
    { k: "PASSED", v: stages[1]?.value.toLocaleString() ?? "—" },
    { k: "COMBOS", v: (stages[6] ?? stages[stages.length - 1])?.value.toLocaleString() ?? "—" },
    { k: "TOP 60", v: "60" },
    { k: "TOP 5", v: "5" },
  ];

  return (
    <div className="mini-funnel">
      {picked.map((s, i) => (
        <Fragment key={i}>
          <div className="mini-step">
            <div className="v num">{s.v}</div>
            <div className="k">{s.k}</div>
          </div>
          {i < picked.length - 1 && (
            <div className="mini-arrow">
              <span className="pct num">
                {(() => {
                  const cur = parseInt(picked[i + 1].v.replace(/,/g, ""));
                  const prev = parseInt(picked[i].v.replace(/,/g, ""));
                  if (!isFinite(cur) || !isFinite(prev) || prev === 0) return "—";
                  return `${Math.round((cur / prev) * 1000) / 10}%`;
                })()}
              </span>
            </div>
          )}
        </Fragment>
      ))}
    </div>
  );
}

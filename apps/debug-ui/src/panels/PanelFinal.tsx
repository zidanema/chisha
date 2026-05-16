import { CopyBtn } from "../components/ui/CopyBtn";
import { Pill } from "../components/ui/Pill";
import type { FinalDiffKind } from "../lib/diffSession";
import type { FinalRow } from "../types/trace";

function FlagDot({
  ok,
  label,
  invert = false,
}: {
  ok: boolean;
  label: string;
  invert?: boolean;
}) {
  const actuallyOk = invert ? !ok : ok;
  return (
    <span className={`flag ${actuallyOk ? "ok" : "bad"}`}>
      <span className="x">{actuallyOk ? "✓" : "✗"}</span>
      {label}
    </span>
  );
}

function FinalCard({ c, diff }: { c: FinalRow; diff?: FinalDiffKind }) {
  const isExplore = c.kind === "explore";
  const isDropped = diff === "dropped";
  const isNew = diff === "new";

  // Border / stripe / opacity hint by diff state. Original "explore" styling
  // still applies via className; diff tags layer on top.
  const cardStyle: React.CSSProperties = isDropped
    ? { opacity: 0.5, filter: "saturate(0.6)" }
    : isNew
      ? { boxShadow: "0 0 0 1px var(--ok-edge), 0 4px 14px var(--shadow-card)" }
      : {};

  return (
    <div className={`final-card ${isExplore ? "explore" : ""}`.trim()} style={cardStyle}>
      <div
        className="final-stripe"
        style={
          isNew ? { background: "var(--ok)" } :
          isDropped ? { background: "var(--err)" } :
          undefined
        }
      ></div>
      <div className="final-body">
        <div className="rank-row">
          <div className={`rank ${isExplore ? "explore" : ""}`.trim()}>{c.rank}</div>
          {isExplore ? (
            <span className="tag-explore">explore</span>
          ) : (
            <span className="tag-exploit">exploit</span>
          )}
          {diff === "new" && (
            <span style={{
              fontSize: 9, padding: "2px 6px", borderRadius: 2,
              background: "var(--ok-bg)", color: "var(--ok)",
              border: "1px solid var(--ok-edge)", fontFamily: "var(--mono)",
              fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em",
            }}>+ 新进</span>
          )}
          {diff === "dropped" && (
            <span style={{
              fontSize: 9, padding: "2px 6px", borderRadius: 2,
              background: "var(--err-bg)", color: "var(--err)",
              border: "1px solid var(--err-edge)", fontFamily: "var(--mono)",
              fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em",
            }}>− 踢出</span>
          )}
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
          <div
            className="dim"
            style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}
          >
            health flags
          </div>
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
            <div
              className="dim"
              style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}
            >
              risk
            </div>
            <div className="flag-list">
              {c.risk_flags.map((r) => (
                <span className="flag warn" key={r}>! {r}</span>
              ))}
            </div>
          </div>
        )}

        <div className="reason-box">{c.reason}</div>
      </div>
    </div>
  );
}

export function PanelFinal({
  rows,
  totalLatencyMs,
  finalDiff,
  droppedRows,
}: {
  rows: FinalRow[];
  totalLatencyMs: number;
  finalDiff?: Map<string, FinalDiffKind>;
  droppedRows?: FinalRow[];
}) {
  const exploreN = rows.filter((c) => c.kind === "explore").length;
  const exploitN = rows.length - exploreN;
  const droppedN = droppedRows?.length ?? 0;
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="layer-tag layer-final">FINAL</span>
        <h2>Top {rows.length}</h2>
        <span className="subtitle">
          {exploitN} exploit + {exploreN} explore
          {droppedN > 0 && (
            <span style={{ color: "var(--err)", marginLeft: 8 }}>· {droppedN} dropped</span>
          )}
        </span>
        <div className="right">
          <Pill tone="gray">总 latency <span className="mono">{totalLatencyMs}ms</span></Pill>
          <CopyBtn label="export JSON" />
        </div>
      </div>
      <div className="panel-body">
        <div className="final-grid">
          {rows.map((c) => (
            // PanelRefine 同时传 droppedRows; rows / droppedRows 的 combo_id 来自
            // 不同 index 空间 (L2 rank vs final combo_index+1) 可能撞 id, 各自加前缀.
            <FinalCard key={`keep-${c.combo_id}`} c={c} diff={finalDiff?.get(c.combo_id)} />
          ))}
          {droppedRows?.map((c) => (
            <FinalCard key={`drop-${c.combo_id}`} c={c} diff="dropped" />
          ))}
        </div>
      </div>
    </div>
  );
}

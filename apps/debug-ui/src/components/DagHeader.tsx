import { Fragment, useEffect, useRef, useState } from "react";
import { StatusBadge } from "./ui/StatusBadge";
import type { L3Status, Session } from "../types/trace";

type Tone = "ctx" | "l1" | "l2" | "l3" | "final";

type DagNode = {
  id: string;
  x: string;
  y: number;
  tone: Tone;
  title: string;
  metric: string;
  subm?: string;
  sub: string;
  lat: string;
  warn?: boolean;
};

export type DagHeaderProps = {
  currentPanel: string;
  onClickNode: (id: string) => void;
  compact: boolean;
  onToggleCompact: () => void;
  session: Session;
};

function buildNodes(session: Session): DagNode[] {
  const { l1, l2, l3 } = session;
  const totalCombos = l1.funnel[l1.funnel.length - 1]?.value ?? 0;
  const restCountAfter = l2.kpi.restaurants_after_cap;
  const restCountBefore = l2.kpi.restaurants_before_cap;
  const top1Price = session.final[0]?.total_price ?? 0;
  const top1Eta = session.final[0]?.eta_min ?? 0;
  const exploitN = session.final.filter((c) => c.kind === "exploit").length;
  const exploreN = session.final.length - exploitN;
  const cacheHitPct = l3.input_tokens
    ? Math.round((l3.cache_read_input_tokens / l3.input_tokens) * 100)
    : 0;
  const l3LatencyDisplay = l3.latency_ms;
  const ctxLat = `${session.ctx_latency_ms}ms`;
  const finalLat = `${session.final_latency_ms}ms`;

  return [
    { id: "ctx", x: "1%", y: 36, tone: "ctx", title: "build_context", metric: "profile",
      sub: `${l1.meal} · ${l1.area.slice(0, 6)}`, lat: ctxLat },
    { id: "l1", x: "16.5%", y: 36, tone: "l1", title: `${l1.raw_dishes.toLocaleString()} dishes`,
      metric: totalCombos.toLocaleString(), subm: "combo", sub: `${restCountAfter} rest`, lat: `${l1.latency_ms}ms` },
    { id: "l2", x: "33%", y: 36, tone: "l2", title: `${l2.weights.length}-dim · cap K=${l2.kpi.cap_k}`,
      metric: String(l2.candidates_to_l3), subm: "top", sub: `${restCountBefore}→${restCountAfter} rest`, lat: `${l2.latency_ms}ms` },
    { id: "l3", x: "49.5%", y: 36, tone: "l3",
      title: `${l3.model.split("-").slice(-3).join("-")} · tool_use`,
      metric: String(l3LatencyDisplay), subm: "ms",
      sub: `cache ${cacheHitPct}%`,
      lat: "OK", warn: true },
    { id: "final", x: "66%", y: 36, tone: "final", title: `${exploitN} exploit + ${exploreN} explore`,
      metric: String(session.final.length), subm: "picks", sub: `¥${top1Price} · ${top1Eta}min`, lat: finalLat },
  ];
}

function labelForNode(id: string): string {
  if (id === "ctx") return "CTX";
  if (id === "l1") return "L1 · RECALL";
  if (id === "l2") return "L2 · SCORE";
  if (id === "l3") return "L3 · LLM";
  if (id === "final") return "FINAL";
  return id.toUpperCase();
}

function chipLabel(id: string): string {
  if (id === "l1") return "L1";
  if (id === "l2") return "L2";
  if (id === "l3") return "L3";
  if (id === "final") return "FINAL";
  return id.toUpperCase();
}

function DagArrows({
  nodes,
  canvasRef,
}: {
  nodes: DagNode[];
  canvasRef: React.RefObject<HTMLDivElement>;
}) {
  const [arrows, setArrows] = useState<
    { x1: number; y1: number; x2: number; y2: number }[]
  >([]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const W = 154;
    const H = 78;

    const compute = () => {
      const cw = canvas.clientWidth;
      const positions = nodes.map((n) => {
        const xPct = parseFloat(n.x);
        return { x: (xPct / 100) * cw, y: n.y, w: W, h: H, id: n.id };
      });
      const ar: typeof arrows = [];
      for (let i = 0; i < positions.length - 1; i++) {
        const a = positions[i];
        const b = positions[i + 1];
        ar.push({
          x1: a.x + a.w,
          y1: a.y + a.h / 2,
          x2: b.x,
          y2: b.y + b.h / 2,
        });
      }
      setArrows(ar);
    };

    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [nodes, canvasRef]);

  return (
    <>
      {arrows.map((a, i) => (
        <line
          key={i}
          x1={a.x1}
          y1={a.y1}
          x2={a.x2}
          y2={a.y2}
          stroke="var(--t-2)"
          strokeWidth="1.5"
          markerEnd="url(#dag-arrow)"
        />
      ))}
    </>
  );
}

export function DagHeader({
  currentPanel, onClickNode, compact, onToggleCompact, session,
}: DagHeaderProps) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const nodes = buildNodes(session);
  const sessionId = session.session_id;
  const startedTime = session.started_at.split(" ")[1] ?? session.started_at;
  const totalLatency = session.total_latency_ms;
  // Read real L3 status so config_error / skipped surface in the DAG header.
  const l3Status: L3Status = session.l3.status;
  const cacheHitPct = session.l3.input_tokens
    ? Math.round((session.l3.cache_read_input_tokens / session.l3.input_tokens) * 1000) / 10
    : 0;

  return (
    <div className={`dag-header ${compact ? "compact" : ""}`.trim()}>
      <div className="dag-strip">
        <span className="session">
          <span className="val">{sessionId}</span>
          <span className="lat">{totalLatency}ms</span>
        </span>
        <div className="nodes">
          {nodes
            .filter((n) => n.id !== "ctx")
            .map((n, i, arr) => (
              <Fragment key={n.id}>
                <button
                  className={`chip ${n.tone} ${currentPanel === n.id ? "selected" : ""}`}
                  onClick={() => onClickNode(n.id)}
                >
                  {chipLabel(n.id)}
                  <span className="v">
                    {n.metric}
                    {n.subm ?? ""}
                  </span>
                </button>
                {i < arr.length - 1 && <span className="arrow">→</span>}
              </Fragment>
            ))}
        </div>
        <button className="expand-btn" onClick={onToggleCompact}>
          <span>展开 DAG</span> <span style={{ opacity: 0.6 }}>▾</span>
        </button>
      </div>

      <div className="dag-session">
        <div className="group">
          <span><span className="lbl">session</span><span className="val">{sessionId}</span></span>
          <span className="sep">·</span>
          <span><span className="lbl">started</span><span className="val">{startedTime}</span></span>
          <span className="sep">·</span>
          <span><span className="lbl">total</span><span className="val">{totalLatency}ms</span></span>
        </div>
        <div></div>
        <div className="group">
          <span><span className="lbl">L3</span><StatusBadge status={l3Status} /></span>
          <span className="sep">·</span>
          <span>
            <span className="lbl">tokens</span>
            <span className="val">
              {session.l3.input_tokens.toLocaleString()} in / {session.l3.output_tokens} out
            </span>
          </span>
          <span className="sep">·</span>
          <span>
            <span className="lbl">cache hit</span>
            <span className="val" style={{ color: "var(--refine)" }}>{cacheHitPct}%</span>
          </span>
        </div>
      </div>

      <div className="dag-canvas" ref={canvasRef}>
        <svg>
          <defs>
            <marker id="dag-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill="var(--t-2)" />
            </marker>
          </defs>
          <DagArrows nodes={nodes} canvasRef={canvasRef} />
        </svg>

        {nodes.map((n) => (
          <div
            key={n.id}
            className={`dag-node ${currentPanel === n.id ? "selected" : ""}`.trim()}
            style={{ left: n.x, top: n.y, width: 154 }}
            onClick={() => onClickNode(n.id)}
          >
            <div className={`dag-node-head ${n.tone}`}>
              <span className="dot"></span>
              {labelForNode(n.id)}
            </div>
            <div className="dag-node-body">
              <div className="title">{n.title}</div>
              <div className={`metric ${n.warn ? "warn" : ""}`.trim()}>
                {n.metric}
                {n.subm ? <span className="s">{n.subm}</span> : null}
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
          <button
            onClick={onToggleCompact}
            style={{
              marginLeft: 8,
              background: "transparent",
              border: "1px solid var(--line)",
              color: "var(--t-2)",
              padding: "1px 7px",
              fontFamily: "var(--mono)",
              fontSize: 9,
              borderRadius: 2,
              cursor: "pointer",
            }}
          >
            收起 ▴
          </button>
        </div>
      </div>
    </div>
  );
}

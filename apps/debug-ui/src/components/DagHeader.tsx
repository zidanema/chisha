import { Fragment, useEffect, useRef, useState } from "react";
import { StatusBadge } from "./ui/StatusBadge";
import type { L3Status, Session } from "../types/trace";

type Tone = "ctx" | "l1" | "l2" | "l3" | "final" | "refine";

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
  fb?: boolean;
};

export type DagHeaderProps = {
  activeTab: "main" | "refine" | "trace";
  fallbackL3LatencyMs: number | null;
  fallbackProvider: string | null;
  currentPanel: string;
  onClickNode: (id: string) => void;
  compact: boolean;
  onToggleCompact: () => void;
  runningPulse: boolean;
  session: Session;
};

function buildNodes(
  session: Session,
  activeTab: DagHeaderProps["activeTab"],
  fallbackL3LatencyMs: number | null,
  fallbackProvider: string | null,
): DagNode[] {
  const useFallback = fallbackL3LatencyMs != null;
  const { l1, l2, l3, refine } = session;
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
  const l3LatencyDisplay = useFallback ? fallbackL3LatencyMs : l3.latency_ms;
  const ctxLat = `${session.ctx_latency_ms}ms`;
  const finalLat = `${session.final_latency_ms}ms`;

  if (activeTab === "refine") {
    return [
      { id: "ctx", x: "1%", y: 36, tone: "ctx", title: "build_context", metric: "profile",
        sub: `${l1.meal} · ${l1.area.slice(0, 6)}`, lat: ctxLat },
      { id: "l1", x: "16%", y: 36, tone: "l1", title: `${(l1.raw_dishes / 1000).toFixed(0)}k dishes`,
        metric: totalCombos.toLocaleString(), subm: "combo", sub: `${restCountAfter} rest`, lat: `${l1.latency_ms}ms` },
      { id: "l2", x: "31%", y: 36, tone: "l2", title: `${l2.weights.length}-dim + cap K=${l2.kpi.cap_k}`,
        metric: String(l2.candidates_to_l3), subm: "top", sub: `${restCountBefore}→${restCountAfter}`, lat: `${l2.latency_ms}ms` },
      { id: "l3", x: "46%", y: 36, tone: "l3",
        title: useFallback ? "FALLBACK · sonnet" : `${l3.model.split("-").slice(-3).join("-")} · tool_use`,
        metric: String(l3LatencyDisplay), subm: "ms",
        sub: useFallback ? (fallbackProvider ?? "fallback") : `cache ${cacheHitPct}%`,
        lat: useFallback ? "FB" : "OK", warn: true, fb: useFallback },
      { id: "final", x: "61%", y: 36, tone: "final", title: `${exploitN} exploit + ${exploreN} explore`,
        metric: String(session.final.length), subm: "picks", sub: `¥${top1Price}`, lat: finalLat },
      { id: "refine", x: "78%", y: 36, tone: "refine", title: "parse → chips → rerun",
        metric: `+${refine.diff.new_in_top5.length} / −${refine.diff.dropped_from_top5.length}`,
        subm: "diff", sub: `haiku · ${refine.parse_feedback.llm_call.latency_ms}ms`,
        lat: `${refine.summary_kpi.total_latency_ms}ms` },
    ];
  }

  return [
    { id: "ctx", x: "1%", y: 36, tone: "ctx", title: "build_context", metric: "profile",
      sub: `${l1.meal} · ${l1.area.slice(0, 6)}`, lat: ctxLat },
    { id: "l1", x: "16.5%", y: 36, tone: "l1", title: `${l1.raw_dishes.toLocaleString()} dishes`,
      metric: totalCombos.toLocaleString(), subm: "combo", sub: `${restCountAfter} rest`, lat: `${l1.latency_ms}ms` },
    { id: "l2", x: "33%", y: 36, tone: "l2", title: `${l2.weights.length}-dim · cap K=${l2.kpi.cap_k}`,
      metric: String(l2.candidates_to_l3), subm: "top", sub: `${restCountBefore}→${restCountAfter} rest`, lat: `${l2.latency_ms}ms` },
    { id: "l3", x: "49.5%", y: 36, tone: "l3",
      title: useFallback ? "FALLBACK · sonnet" : `${l3.model.split("-").slice(-3).join("-")} · tool_use`,
      metric: String(l3LatencyDisplay), subm: "ms",
      sub: useFallback ? (fallbackProvider ?? "fallback") : `cache ${cacheHitPct}%`,
      lat: useFallback ? "FB" : "OK", warn: true, fb: useFallback },
    { id: "final", x: "66%", y: 36, tone: "final", title: `${exploitN} exploit + ${exploreN} explore`,
      metric: String(session.final.length), subm: "picks", sub: `¥${top1Price} · ${top1Eta}min`, lat: finalLat },
  ];
}

function labelForNode(id: string, fb: boolean | undefined): string {
  if (id === "ctx") return "CTX";
  if (id === "l1") return "L1 · RECALL";
  if (id === "l2") return "L2 · SCORE";
  if (id === "l3") return fb ? "L3 · FALLBACK" : "L3 · LLM";
  if (id === "final") return "FINAL";
  if (id === "refine") return "REFINE";
  return id.toUpperCase();
}

function chipLabel(id: string): string {
  if (id === "l1") return "L1";
  if (id === "l2") return "L2";
  if (id === "l3") return "L3";
  if (id === "final") return "FINAL";
  if (id === "refine") return "REFINE";
  return id.toUpperCase();
}

function DagArrows({
  nodes,
  activeTab,
  canvasRef,
}: {
  nodes: DagNode[];
  activeTab: DagHeaderProps["activeTab"];
  canvasRef: React.RefObject<HTMLDivElement>;
}) {
  const [arrows, setArrows] = useState<
    { x1: number; y1: number; x2: number; y2: number; dashed: boolean }[]
  >([]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const W = activeTab === "refine" ? 138 : 154;
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
          dashed: b.id === "refine",
        });
      }
      setArrows(ar);
    };

    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [nodes, activeTab, canvasRef]);

  return (
    <>
      {arrows.map((a, i) => (
        <line
          key={i}
          x1={a.x1}
          y1={a.y1}
          x2={a.x2}
          y2={a.y2}
          stroke={a.dashed ? "var(--refine)" : "var(--t-2)"}
          strokeWidth="1.5"
          strokeDasharray={a.dashed ? "4 3" : undefined}
          markerEnd={a.dashed ? "url(#dag-arrow-pink)" : "url(#dag-arrow)"}
        />
      ))}
    </>
  );
}

export function DagHeader({
  activeTab, fallbackL3LatencyMs, fallbackProvider, currentPanel, onClickNode,
  compact, onToggleCompact, runningPulse, session,
}: DagHeaderProps) {
  const useFallback = fallbackL3LatencyMs != null;
  const canvasRef = useRef<HTMLDivElement>(null);
  const nodes = buildNodes(session, activeTab, fallbackL3LatencyMs, fallbackProvider);
  const sessionId = session.session_id;
  const startedTime = session.started_at.split(" ")[1] ?? session.started_at;
  const totalLatency = session.total_latency_ms;
  // Read real L3 status so config_error / skipped surface in the DAG header,
  // not just OK. fallback toggle still overrides for mock demo.
  const l3Status: L3Status = useFallback ? "fallback" : session.l3.status;
  const cacheHitPct = session.l3.input_tokens
    ? Math.round((session.l3.cache_read_input_tokens / session.l3.input_tokens) * 1000) / 10
    : 0;

  return (
    <div className={`dag-header ${compact ? "compact" : ""} ${runningPulse ? "running" : ""}`.trim()}>
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
                  className={`chip ${n.tone} ${useFallback && n.id === "l3" ? "fb" : ""} ${currentPanel === n.id ? "selected" : ""}`}
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
        {useFallback && (
          <span className="strip-warn">
            <span className="pulse"></span>L3 fallback
          </span>
        )}
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
            <marker id="dag-arrow-pink" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill="var(--refine)" />
            </marker>
          </defs>
          <DagArrows nodes={nodes} activeTab={activeTab} canvasRef={canvasRef} />
        </svg>

        {nodes.map((n) => (
          <div
            key={n.id}
            className={`dag-node ${currentPanel === n.id ? "selected" : ""}`.trim()}
            style={{ left: n.x, top: n.y, width: activeTab === "refine" ? 138 : 154 }}
            onClick={() => onClickNode(n.id)}
          >
            <div className={`dag-node-head ${n.tone}`}>
              <span className="dot"></span>
              {labelForNode(n.id, n.fb)}
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
          {activeTab === "refine" && (
            <span><span className="swatch" style={{ background: "var(--refine)" }}></span>refine</span>
          )}
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

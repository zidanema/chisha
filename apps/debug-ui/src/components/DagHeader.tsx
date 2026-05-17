import { Fragment, useEffect, useRef, useState } from "react";
import { StatusBadge } from "./ui/StatusBadge";
import type { L3Status, Session } from "../types/trace";

type Tone = "ctx" | "l1" | "feedback" | "l2" | "l3" | "final" | "refine";

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
  disabled?: boolean;  // D-083 PR-2: feedback 节点空时灰显不可点 (Codex S2 Q4=A)
};

export type DagHeaderProps = {
  activeTab: "main" | "refine" | "trace";
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
): DagNode[] {
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
  const l3LatencyDisplay = l3.latency_ms;
  const ctxLat = `${session.ctx_latency_ms}ms`;
  const finalLat = `${session.final_latency_ms}ms`;
  // D-082: refine 节点用 round2 真实数据驱动 (老 diff 字段已废, adapter 喂 [])
  const refineApplied = refine.user_text.length > 0;
  const round2 = session.round2;
  const refineRound = (refine.intent as { round?: number } | null)?.round;
  const compactLayout = activeTab === "refine" || (refineApplied && round2);

  // D-083 PR-2: Feedback DAG 节点 (Codex S2 Q4=A: 总在, 空 trace 灰显).
  const fbSnap = session.feedback_view_snapshot;
  const fbEmpty = !fbSnap || fbSnap.empty;
  const fbCounts = fbSnap && !fbSnap.empty
    ? `${fbSnap.rating_signals.length}r/${fbSnap.calibration_rules.length}c/${fbSnap.note_breakdown.length}n`
    : "空";
  const fbActive = fbSnap && !fbSnap.empty
    ? `${fbSnap.rating_signals.length + fbSnap.calibration_rules.length + fbSnap.note_breakdown.length}`
    : "0";

  // D-082: refine 节点用 round2 真实数据驱动. compactLayout 下右移到 78%, 否则 82%.
  const baseRefineNode: DagNode | null = refineApplied
    ? {
        id: "refine",
        x: compactLayout ? "78%" : "82%",
        y: 36,
        tone: "refine",
        title: round2 ? "round 2 · L1→L2→L3 全跑" : "round 2 summary only",
        metric: round2
          ? String(round2.final.length)
          : String(refine.candidate_ids?.length ?? 0),
        subm: "picks",
        sub: round2 ? `${round2.l2.combos.length} top · ${round2.l3.candidates_returned} out` : "no round2",
        lat: round2 ? `${round2.total_latency_ms}ms` : (refineRound ? `r${refineRound}` : "—"),
      }
    : null;

  if (compactLayout) {
    // compact (refine tab 或 main+round2): 6/7 节点 + 可选 refine, 间距 ~13%
    return [
      { id: "ctx", x: "1%", y: 36, tone: "ctx", title: "build_context", metric: "profile",
        sub: `${l1.meal} · ${l1.area.slice(0, 6)}`, lat: ctxLat },
      { id: "l1", x: "13%", y: 36, tone: "l1", title: `${(l1.raw_dishes / 1000).toFixed(0)}k dishes`,
        metric: totalCombos.toLocaleString(), subm: "combo", sub: `${restCountAfter} rest`, lat: `${l1.latency_ms}ms` },
      { id: "feedback", x: "25%", y: 36, tone: "feedback", title: "派生 view (R/C/N)",
        metric: fbActive, subm: "evts", sub: fbCounts,
        lat: fbEmpty ? "—" : "OK", disabled: fbEmpty },
      { id: "l2", x: "37%", y: 36, tone: "l2", title: `${l2.weights.length}-dim + cap K=${l2.kpi.cap_k}`,
        metric: String(l2.candidates_to_l3), subm: "top", sub: `${restCountBefore}→${restCountAfter}`, lat: `${l2.latency_ms}ms` },
      { id: "l3", x: "50%", y: 36, tone: "l3",
        title: `${l3.model.split("-").slice(-3).join("-")} · tool_use`,
        metric: String(l3LatencyDisplay), subm: "ms",
        sub: `cache ${cacheHitPct}%`,
        lat: "OK", warn: true },
      { id: "final", x: "63%", y: 36, tone: "final", title: `${exploitN} exploit + ${exploreN} explore`,
        metric: String(session.final.length), subm: "picks", sub: `¥${top1Price}`, lat: finalLat },
      ...(baseRefineNode ? [baseRefineNode] : []),
    ];
  }

  // main tab (no refine): 6 节点 (ctx/l1/feedback/l2/l3/final), 间距 ~13%
  return [
    { id: "ctx", x: "1%", y: 36, tone: "ctx", title: "build_context", metric: "profile",
      sub: `${l1.meal} · ${l1.area.slice(0, 6)}`, lat: ctxLat },
    { id: "l1", x: "14%", y: 36, tone: "l1", title: `${l1.raw_dishes.toLocaleString()} dishes`,
      metric: totalCombos.toLocaleString(), subm: "combo", sub: `${restCountAfter} rest`, lat: `${l1.latency_ms}ms` },
    { id: "feedback", x: "27%", y: 36, tone: "feedback", title: "派生 view (R/C/N)",
      metric: fbActive, subm: "evts", sub: fbCounts,
      lat: fbEmpty ? "—" : "OK", disabled: fbEmpty },
    { id: "l2", x: "40%", y: 36, tone: "l2", title: `${l2.weights.length}-dim · cap K=${l2.kpi.cap_k}`,
      metric: String(l2.candidates_to_l3), subm: "top", sub: `${restCountBefore}→${restCountAfter} rest`, lat: `${l2.latency_ms}ms` },
    { id: "l3", x: "53%", y: 36, tone: "l3",
      title: `${l3.model.split("-").slice(-3).join("-")} · tool_use`,
      metric: String(l3LatencyDisplay), subm: "ms",
      sub: `cache ${cacheHitPct}%`,
      lat: "OK", warn: true },
    { id: "final", x: "66%", y: 36, tone: "final", title: `${exploitN} exploit + ${exploreN} explore`,
      metric: String(session.final.length), subm: "picks", sub: `¥${top1Price} · ${top1Eta}min`, lat: finalLat },
  ];
}

function labelForNode(id: string, fb: boolean | undefined): string {
  if (id === "ctx") return "CTX";
  if (id === "l1") return "L1 · RECALL";
  if (id === "feedback") return "FB · VIEW";
  if (id === "l2") return "L2 · SCORE";
  if (id === "l3") return fb ? "L3 · FALLBACK" : "L3 · LLM";
  if (id === "final") return "FINAL";
  if (id === "refine") return "REFINE";
  return id.toUpperCase();
}

function chipLabel(id: string): string {
  if (id === "l1") return "L1";
  if (id === "feedback") return "FB";
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
    // D-082+D-083: width 适配:
    //  - main 6 节点 (含 fb): 138px
    //  - compact (含 refine, 6+1 或 7 节点): 128px
    const hasRefine = nodes.some((n) => n.id === "refine");
    const W = hasRefine ? 128 : 138;
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
  activeTab, currentPanel, onClickNode,
  compact, onToggleCompact, runningPulse, session,
}: DagHeaderProps) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const nodes = buildNodes(session, activeTab);
  const sessionId = session.session_id;
  const startedTime = session.started_at.split(" ")[1] ?? session.started_at;
  const totalLatency = session.total_latency_ms;
  // Real L3 status: config_error / skipped / fallback / ok 都 surface 出来.
  // 真实 LLM provider chain fallback 由 session.l3.status + session.l3.fallback_chain 驱动.
  const l3Status: L3Status = session.l3.status;
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
                  className={`chip ${n.tone} ${l3Status === "fallback" && n.id === "l3" ? "fb" : ""} ${currentPanel === n.id ? "selected" : ""} ${n.disabled ? "disabled" : ""}`.trim()}
                  onClick={() => !n.disabled && onClickNode(n.id)}
                  disabled={n.disabled}
                  title={n.disabled ? "无 feedback 数据 — pre-D-083 trace 或空 store" : undefined}
                  style={n.disabled ? { opacity: 0.4, cursor: "not-allowed" } : undefined}
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
        {l3Status === "fallback" && (
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
            className={`dag-node ${currentPanel === n.id ? "selected" : ""} ${n.disabled ? "disabled" : ""}`.trim()}
            style={{
              left: n.x, top: n.y,
              width: nodes.some((nn) => nn.id === "refine") ? 128 : 138,
              ...(n.disabled ? { opacity: 0.4, cursor: "not-allowed" } : {}),
            }}
            onClick={() => !n.disabled && onClickNode(n.id)}
            title={n.disabled ? "无 feedback 数据 — pre-D-083 trace 或空 store" : undefined}
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
          <span><span className="swatch" style={{ background: "var(--refine)" }}></span>FB</span>
          <span><span className="swatch" style={{ background: "var(--L2)" }}></span>L2</span>
          <span><span className="swatch" style={{ background: "var(--L3)" }}></span>L3</span>
          <span><span className="swatch" style={{ background: "var(--final)" }}></span>final</span>
          {nodes.some((n) => n.id === "refine") && (
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

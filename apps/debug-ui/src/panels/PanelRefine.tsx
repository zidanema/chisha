// D-082: PanelRefine — refine 二轮 trace 回放. 消费 session.refine + session.round2.
//
// 三层渲染:
//   1. RefineIntentCard: user_input (原文) + RefineIntent 结构化字段 (D-073)
//   2. DiffSummary: round1 vs round2 top5 变化的四数 (+N / −M / ↑K / ↓J)
//   3. Round2 pipeline: 复用 PanelL1 / PanelL2 (带 comboDiff) / PanelL3 / PanelFinal
//      (带 finalDiff + droppedRows). PanelL2 / PanelFinal 已内建 diff 渲染.
//
// 没 round2 (refine 未触发, 或老 trace 只有 summary): 渲一张 "等待触发 refine" 提示.

import { Pill } from "../components/ui/Pill";
import { computeRefineDiff } from "../lib/diffSession";
import type { Session } from "../types/trace";
import { PanelL1 } from "./PanelL1";
import { PanelL2 } from "./PanelL2";
import { PanelL3 } from "./PanelL3";
import { PanelFinal } from "./PanelFinal";

const INTENT_LABELS: Record<string, { label: string; tone: "want" | "avoid" }> = {
  cuisine_want:      { label: "菜系想",   tone: "want" },
  cuisine_avoid:     { label: "菜系不想", tone: "avoid" },
  ingredient_want:   { label: "食材想",   tone: "want" },
  ingredient_avoid:  { label: "食材不想", tone: "avoid" },
  flavor_want:       { label: "口味想",   tone: "want" },
  flavor_avoid:      { label: "口味不想", tone: "avoid" },
  flavor_tags:       { label: "口味标签", tone: "want" },
  cooking_method:    { label: "烹饪方式", tone: "want" },
  raw_flavor:        { label: "原文口味", tone: "want" },
  portion:           { label: "份量",     tone: "want" },
  staple_preference: { label: "主食",     tone: "want" },
  price_band:        { label: "价格带",   tone: "want" },
};

function intentValues(v: unknown): string[] {
  if (v == null) return [];
  if (Array.isArray(v)) return v.map((x) => String(x)).filter(Boolean);
  if (typeof v === "string") return v.trim() ? [v] : [];
  if (typeof v === "object") {
    // RefineIntent 嵌套 object (price_band 可能是 {min, max} 等) → 简单 JSON
    const s = JSON.stringify(v);
    return s === "{}" ? [] : [s];
  }
  return [String(v)];
}

function RefineIntentCard({ session }: { session: Session }) {
  const r = session.refine;
  const intent = (r.intent ?? {}) as Record<string, unknown>;
  const freeform = typeof intent.freeform_note === "string" ? intent.freeform_note : "";
  const entries = Object.entries(INTENT_LABELS)
    .map(([k, meta]) => [k, meta, intentValues(intent[k])] as const)
    .filter(([, , vals]) => vals.length > 0);

  return (
    <div
      className="panel"
      style={{ marginBottom: 12 }}
    >
      <div className="panel-head">
        <span className="layer-tag layer-l3">REFINE</span>
        <h2>用户反馈 · D-073 RefineIntent</h2>
        <span className="subtitle">round {r.parse_feedback.note}</span>
        <div className="right">
          <Pill tone={r.user_text ? "violet" : "gray"}>
            {r.user_text ? `applied (round ${r.candidate_ids?.length != null ? "2+" : "?"})` : "no refine"}
          </Pill>
        </div>
      </div>
      <div className="panel-body" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <div className="subhead" style={{ margin: 0, marginBottom: 6 }}>原文</div>
          <div
            style={{
              padding: "8px 10px",
              background: "var(--bg-inset)",
              border: "1px solid var(--line)",
              borderRadius: 3,
              fontFamily: "var(--sans)",
              fontSize: 13,
              lineHeight: 1.5,
              minHeight: 36,
              whiteSpace: "pre-wrap",
            }}
          >
            {r.user_text || <span className="dim">(空)</span>}
          </div>
          {freeform && freeform !== r.user_text && (
            <div className="dim mono" style={{ fontSize: 10, marginTop: 6 }}>
              freeform_note: {freeform}
            </div>
          )}
        </div>
        <div>
          <div className="subhead" style={{ margin: 0, marginBottom: 6 }}>结构化 intent</div>
          {entries.length === 0 ? (
            <div className="dim mono" style={{ fontSize: 11 }}>(无)</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {entries.map(([k, meta, vals]) => (
                <div key={k} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 11 }}>
                  <span className="dim mono" style={{ minWidth: 80 }}>{meta.label}</span>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {vals.map((val, i) => (
                      <Pill key={`${k}-${i}`} tone={meta.tone === "want" ? "green" : "red"}>
                        {val}
                      </Pill>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DiffSummary({ session }: { session: Session }) {
  const diff = computeRefineDiff(session);
  if (!diff) return null;
  const newCount = [...diff.combos.values()].filter((d) => d.kind === "NEW").length;
  const droppedCount = [...diff.combos.values()].filter((d) => d.kind === "DROPPED").length;
  const upCount = [...diff.combos.values()].filter((d) => d.kind === "UP").length;
  const downCount = [...diff.combos.values()].filter((d) => d.kind === "DOWN").length;
  const finalDropped = diff.droppedFinals.length;
  const finalNew = [...diff.final.values()].filter((v) => v === "new").length;

  const cell = (k: string, v: number | string, color?: string) => (
    <div
      style={{
        flex: 1, padding: "10px 14px", background: "var(--bg-2)",
        border: "1px solid var(--line)", borderRadius: 3,
      }}
    >
      <div className="dim mono" style={{ fontSize: 10, marginBottom: 4 }}>{k}</div>
      <div style={{ fontFamily: "var(--mono)", fontSize: 18, color: color ?? "var(--t-0)" }}>{v}</div>
    </div>
  );
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
      {cell("final 新进", `+${finalNew}`, "var(--green)")}
      {cell("final 踢出", `-${finalDropped}`, "var(--red)")}
      {cell("L2 combo NEW",     `+${newCount}`,     "var(--green)")}
      {cell("L2 combo DROPPED", `-${droppedCount}`, "var(--red)")}
      {cell("L2 combo UP",   `${upCount}`,   "var(--blue)")}
      {cell("L2 combo DOWN", `${downCount}`, "var(--orange)")}
    </div>
  );
}

export function PanelRefine({ session }: { session: Session }) {
  // 没 round2 → 提示触发 refine
  if (!session.round2) {
    return (
      <div>
        <RefineIntentCard session={session} />
        <div className="panel">
          <div className="panel-head">
            <span className="layer-tag layer-l2r">L2'</span>
            <h2>round 2 trace 未生成</h2>
            <span className="subtitle">在 sidebar 输入反馈点「↻ 触发 refine」</span>
            <div className="right"><Pill tone="orange">等待触发</Pill></div>
          </div>
          <div className="panel-body">
            <div
              className="dim mono"
              style={{
                padding: 24, textAlign: "center", fontSize: 12,
                border: "1px dashed var(--line-strong)", borderRadius: 4,
                background: "var(--bg-inset)",
              }}
            >
              # 该 session 还没 round2 全量 trace.<br/>
              # 在 sidebar 填入反馈, 点 ↻ 触发 refine, 后端 /api/refine 会重跑 L1/L2/L3<br/>
              # 并把 round2 完整 pipeline 写进同一份 trace 文件 (D-082).
            </div>
          </div>
        </div>
      </div>
    );
  }

  const diff = computeRefineDiff(session);
  const round2 = session.round2;

  return (
    <div>
      <RefineIntentCard session={session} />
      <DiffSummary session={session} />
      <div className="subhead" style={{ margin: "16px 0 8px" }}>
        round 2 · 完整 pipeline
        <span className="count">L1 → L2 → L3 → Final</span>
      </div>
      <PanelL1 l1={round2.l1} />
      <PanelL2 l2={round2.l2} comboDiff={diff?.combos} />
      <PanelL3
        l3={round2.l3}
        finalRows={round2.final}
        sessionId={session.session_id}
      />
      <PanelFinal
        rows={round2.final}
        totalLatencyMs={round2.total_latency_ms}
        finalDiff={diff?.final}
        droppedRows={diff?.droppedFinals ?? []}
      />
    </div>
  );
}

import { Fragment, useState } from "react";
import { Pill } from "../components/ui/Pill";
import type { PillTone } from "../components/ui/Pill";
import type { BackendMatchedDish, BackendTargetTrace } from "../api/backend-types";
import { labelForDim, type DimKey } from "../constants/labels";
import type { UseTrace } from "../hooks/useTrace";

const DIM_KEY_FOR_NP: Partial<Record<string, DimKey>> = {
  oil_level: "oil_level",
  spicy_level: "spicy_level",
  wetness: "wetness",
  sweet_sauce_level: "sweet_sauce_level",
};

type DroppedStage = NonNullable<UseTrace["droppedStage"]>;

const STAGE_LABELS: Record<DroppedStage, string> = {
  l1_hard: "L1 hard_filter",
  l1_diversity: "L1 diversity",
  l2_only: "L2 (top60 之外)",
  final: "进入 Final",
  none: "未匹配",
};

const STAGE_TONES: Record<BackendMatchedDish["stage"], PillTone> = {
  passed_recall: "green",
  dropped_hard_filter: "red",
  dropped_diversity_filter: "orange",
  unknown: "gray",
};

const STAGE_TEXT: Record<BackendMatchedDish["stage"], string> = {
  passed_recall: "passed",
  dropped_hard_filter: "L1 hard",
  dropped_diversity_filter: "L1 div",
  unknown: "?",
};

function TraceDagMini({ droppedStage }: { droppedStage: UseTrace["droppedStage"] }) {
  const steps = [
    { id: "l1", label: "L1 召回", tone: "L1" as const, hit: droppedStage === "l1_hard" || droppedStage === "l1_diversity" },
    { id: "l2", label: "L2 打分", tone: "L2" as const, hit: droppedStage === "l2_only" },
    { id: "l3", label: "L3 LLM",  tone: "L3" as const, hit: false },
    { id: "final", label: "Final", tone: "final" as const, hit: droppedStage === "final" },
  ];
  return (
    <div className="dag-canvas" style={{ position: "relative", height: 70, padding: "12px 8px", display: "flex", alignItems: "center", gap: 8 }}>
      {steps.map((s, i) => (
        <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            className="dag-node"
            style={{
              position: "static",
              width: 110,
              height: 44,
              border: s.hit ? "1px solid var(--warn-edge)" : "1px solid var(--line-strong)",
              background: s.hit ? "var(--warn-bg)" : "var(--bg-2)",
              boxShadow: s.hit ? "0 0 0 2px var(--warn-bg)" : undefined,
            }}
          >
            <div className={`dag-node-head ${s.tone}`} style={{ fontSize: 9 }}>
              {s.label}
            </div>
            <div className="dag-node-body" style={{ padding: "4px 8px", fontSize: 11 }}>
              {s.hit ? <span style={{ color: "var(--warn)", fontWeight: 600 }}>× dropped here</span> : <span className="dim">passing</span>}
            </div>
          </div>
          {i < steps.length - 1 && <span style={{ color: "var(--t-3)", fontSize: 12 }}>→</span>}
        </div>
      ))}
      {droppedStage && (
        <div style={{ marginLeft: "auto", color: "var(--t-2)", fontSize: 11 }}>
          归属层: <span className="mono" style={{ color: "var(--warn)", fontWeight: 600 }}>
            {STAGE_LABELS[droppedStage]}
          </span>
        </div>
      )}
    </div>
  );
}

function DishDetail({
  dish,
  matchedCombos,
}: {
  dish: BackendMatchedDish;
  matchedCombos: BackendTargetTrace["matched_combos_in_ranked"];
}) {
  const np = dish.nutrition_profile ?? {};
  // Combos this dish participates in (signature-based join is too brittle;
  // server-side already filtered by matched_dish_ids).
  return (
    <div style={{
      padding: 12, background: "var(--bg-inset)", borderTop: "1px dashed var(--line-strong)",
      display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14,
    }}>
      <div>
        <div className="subhead" style={{ margin: 0, marginBottom: 6 }}>nutrition_profile</div>
        <table className="tbl">
          <tbody>
            {Object.entries(np).map(([k, v]) => {
              const dimKey = DIM_KEY_FOR_NP[k];
              const display = dimKey
                ? labelForDim(dimKey, v) + (typeof v === "number" ? ` (${v})` : "")
                : v == null ? "—" : String(v);
              return (
                <tr key={k}>
                  <td className="dim mono" style={{ fontSize: 11 }}>{k}</td>
                  <td className="mono" style={{ fontSize: 11 }}>{display}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div>
        <div className="subhead" style={{ margin: 0, marginBottom: 6 }}>
          ban / drop 详情
        </div>
        {dish.reason ? (
          <div className="reason mono" style={{ fontSize: 11, padding: "4px 0", lineHeight: 1.6 }}>
            {dish.reason}
          </div>
        ) : (
          <div className="dim mono" style={{ fontSize: 11 }}>(无 drop 原因 — passed recall)</div>
        )}
        {matchedCombos.length > 0 && (
          <>
            <div className="subhead" style={{ margin: "12px 0 6px 0" }}>
              出现在 ranked combo
            </div>
            <table className="tbl">
              <thead><tr><th>rank</th><th>score</th><th>signature</th></tr></thead>
              <tbody>
                {matchedCombos.slice(0, 5).map((c) => (
                  <tr key={c.signature}>
                    <td className="mono">#{c.rank}</td>
                    <td className="mono">{c.score.toFixed(3)}</td>
                    <td className="mono dim" style={{ fontSize: 10 }}>{c.signature}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}

export function PanelTrace({
  trace,
  droppedStage,
  status,
  error,
}: {
  trace: BackendTargetTrace | null;
  droppedStage: UseTrace["droppedStage"];
  status: UseTrace["status"];
  error: string | null;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  if (status === "idle") {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="layer-tag layer-l1">追溯</span>
          <h2>命中追溯</h2>
          <span className="subtitle">在左边输入餐厅 / 菜名后点「⌕ 追溯命中」</span>
        </div>
        <div className="panel-body">
          <div className="dim mono" style={{ padding: 32, textAlign: "center", fontSize: 12,
                                              border: "1px dashed var(--line-strong)", borderRadius: 4,
                                              background: "var(--bg-inset)" }}>
            # 输入餐厅模糊名 (如 "太二") 和/或菜名 (空格分隔, 如 "酸菜鱼 米饭")<br />
            # 点击命中按钮, 会调用 /api/debug_recommend?trace_target=… 重跑一次定位<br />
            # 显示该菜在 L1 / L2 / L3 / Final 哪一层被砍, 具体原因, 以及 dish 完整属性<br />
            <span style={{ color: "var(--t-3)" }}>(LLM rerank 关闭以节省 token)</span>
          </div>
        </div>
      </div>
    );
  }

  if (status === "loading") {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="layer-tag layer-l1">追溯</span>
          <h2>追溯中…</h2>
        </div>
        <div className="panel-body">
          <div className="dim mono" style={{ padding: 24, textAlign: "center" }}>
            # 重跑 L1/L2 pipeline + trace_target 匹配…
          </div>
        </div>
      </div>
    );
  }

  if (status === "error" || status === "offline") {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="layer-tag layer-l1">追溯</span>
          <h2>追溯失败</h2>
        </div>
        <div className="panel-body">
          <div className="callout red">
            <span className="icon">▲</span>
            <div className="body">
              <strong>{status === "offline" ? "后端 offline" : "API error"}</strong>
              <div className="dim mono" style={{ marginTop: 4, fontSize: 11 }}>
                {error ?? "(无 detail)"}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (status === "empty" || !trace || trace.matched_dishes.length === 0) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="layer-tag layer-l1">追溯</span>
          <h2>未匹配</h2>
          <span className="subtitle">检查餐厅 / 菜名输入是否正确 (模糊匹配 substring)</span>
        </div>
        <div className="panel-body">
          <div className="dim mono" style={{ padding: 24, textAlign: "center" }}>
            # 没有 dish 命中你输入的关键词<br />
            # 餐厅名 "{trace?.query.restaurant_name ?? "(空)"}" · 菜名 {JSON.stringify(trace?.query.dish_names ?? [])}<br />
            # 试试更短的子串, 或者只填餐厅 / 只填菜名
          </div>
        </div>
      </div>
    );
  }

  const matchedComboIds = new Set(trace.matched_combos_in_ranked.map((c) => c.signature));

  return (
    <>
      <TraceDagMini droppedStage={droppedStage} />
      <div className="panel">
        <div className="panel-head">
          <span className="layer-tag layer-l1">追溯</span>
          <h2>命中 {trace.matched_dishes.length} 道菜</h2>
          <span className="subtitle">
            餐厅 "{trace.query.restaurant_name ?? "(空)"}" · 菜名 {JSON.stringify(trace.query.dish_names ?? [])}
          </span>
          <div className="right">
            {trace.in_final ? (
              <Pill tone="green">in_final ✓</Pill>
            ) : (
              <Pill tone="orange">没进 Final</Pill>
            )}
          </div>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="tbl" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th style={{ width: 24 }}></th>
                <th>dish_id</th>
                <th>菜名</th>
                <th>餐厅</th>
                <th>stage</th>
                <th>原因</th>
                <th className="right">top60 rank</th>
                <th>final</th>
              </tr>
            </thead>
            <tbody>
              {trace.matched_dishes.map((d) => {
                const isOpen = openId === d.dish_id;
                const inRanked = matchedComboIds.size > 0;
                return (
                  <Fragment key={d.dish_id}>
                    <tr
                      onClick={() => setOpenId(isOpen ? null : d.dish_id)}
                      style={{ cursor: "pointer" }}
                    >
                      <td><span className="chev">{isOpen ? "▼" : "▶"}</span></td>
                      <td className="mono" style={{ fontSize: 10 }}>{d.dish_id}</td>
                      <td>{d.name}</td>
                      <td className="dim">{d.restaurant_name ?? "—"}</td>
                      <td>
                        <Pill tone={STAGE_TONES[d.stage]}>{STAGE_TEXT[d.stage]}</Pill>
                      </td>
                      <td className="reason mono" style={{ fontSize: 10 }}>{d.reason ?? "—"}</td>
                      <td className="right mono">
                        {inRanked && d.stage === "passed_recall" ? (
                          <span style={{ color: "var(--green)" }}>#{trace.matched_combos_in_ranked[0]?.rank ?? "?"}</span>
                        ) : (
                          <span className="dim">—</span>
                        )}
                      </td>
                      <td>
                        {trace.in_final && d.stage === "passed_recall" ? (
                          <Pill tone="violet">final</Pill>
                        ) : (
                          <span className="dim mono" style={{ fontSize: 10 }}>—</span>
                        )}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={8} style={{ padding: 0 }}>
                          <DishDetail dish={d} matchedCombos={trace.matched_combos_in_ranked} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

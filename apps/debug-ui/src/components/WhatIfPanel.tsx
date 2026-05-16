// D-079: What-if 双栏对比. 编辑 weights/caps overrides → POST /api/debug/what_if →
// 渲染 final 5 三态 diff (新进 / 保持 / 挪位 / 踢出). DESIGN §8.3.
//
// 不动 L1/L2/L3/Final 主 panel — what-if 是 overlay 实验, 用户通过 sidebar 进入,
// 试验完直接关 (不写盘, 不污染 history).

import { useMemo, useState } from "react";
import { ApiError, postWhatIf } from "../api/client";
import { traceToSession } from "../api/adapter";
import { pushToast } from "./Toaster";
import type { FinalRow, Session } from "../types/trace";

export type WhatIfPanelProps = {
  baseSession: Session;
  onClose: () => void;
};

type RowState = "new" | "kept" | "up" | "down" | "dropped";

function classifyRow(
  origIdx: Map<string, number>,
  newIdx: Map<string, number>,
  comboId: string,
): RowState {
  const o = origIdx.get(comboId);
  const n = newIdx.get(comboId);
  if (o == null && n != null) return "new";
  if (o != null && n == null) return "dropped";
  if (o != null && n != null) {
    if (n < o) return "up";
    if (n > o) return "down";
    return "kept";
  }
  return "kept";
}

export function WhatIfPanel({ baseSession, onClose }: WhatIfPanelProps) {
  // overrides JSON textarea — 用户直接改 profile_overrides (DESIGN §3.3 white-list).
  // 默认提供一个空示例, 避免上来就是 {}.
  const [overridesText, setOverridesText] = useState<string>(
    JSON.stringify(
      {
        scoring_weights: {
          // 示例: 提示用户可以改哪些维度. 实际由后端 V2_DEFAULT_WEIGHTS 兜底.
        },
      },
      null,
      2,
    ),
  );
  const [useLlm, setUseLlm] = useState<boolean>(false);
  const [nReturn, setNReturn] = useState<number>(5);
  const [nExplore, setNExplore] = useState<number>(2);
  const [loading, setLoading] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [resultSession, setResultSession] = useState<Session | null>(null);
  const [llmCalled, setLlmCalled] = useState<boolean | null>(null);

  const parseRes = useMemo(() => {
    const t = overridesText.trim();
    if (!t || t === "{}") return { ok: true, value: {} as Record<string, unknown> };
    try {
      const v = JSON.parse(t);
      if (v && typeof v === "object" && !Array.isArray(v)) {
        return { ok: true, value: v as Record<string, unknown> };
      }
      return { ok: false, value: null as null, err: "必须是 JSON 对象 {…}" };
    } catch (e) {
      return { ok: false, value: null as null, err: e instanceof Error ? e.message : "JSON 解析失败" };
    }
  }, [overridesText]);

  async function handleRun() {
    if (!parseRes.ok || parseRes.value == null) {
      setErrMsg(parseRes.err ?? "JSON 不合法");
      return;
    }
    setLoading(true);
    setErrMsg(null);
    try {
      const trace = await postWhatIf({
        base_session_id: baseSession.session_id,
        overrides: {
          profile_overrides: parseRes.value,
          use_llm_rerank: useLlm,
          n_return: nReturn,
          n_explore: nExplore,
        },
      });
      const sess = traceToSession(trace);
      setResultSession(sess);
      setLlmCalled(!!trace.__llm_called);
      pushToast({
        kind: "ok",
        title: "What-if 完成",
        detail: trace.__llm_called ? "L3 LLM called" : "fallback only",
      });
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : null;
      const msg = apiErr?.message ?? (err instanceof Error ? err.message : String(err));
      setErrMsg(msg);
      pushToast({
        kind: "error",
        title: `what-if 失败 ${apiErr?.status ?? ""}`.trim(),
        detail: msg.slice(0, 200),
      });
    } finally {
      setLoading(false);
    }
  }

  const origRows = baseSession.final;
  const newRows = resultSession?.final ?? [];
  const origIdx = useMemo(() => new Map(origRows.map((r, i) => [r.combo_id, i])), [origRows]);
  const newIdx = useMemo(() => new Map(newRows.map((r, i) => [r.combo_id, i])), [newRows]);

  function renderFinalCol(rows: FinalRow[], side: "orig" | "new"): JSX.Element {
    if (rows.length === 0) {
      return <div className="dim" style={{ fontSize: 11 }}>(无 final)</div>;
    }
    return (
      <div className="wif-final">
        {rows.map((r) => {
          const state = side === "orig"
            ? classifyRow(origIdx, newIdx, r.combo_id)
            : classifyRow(origIdx, newIdx, r.combo_id);
          // 视角:
          // - orig 列: dropped (左独有红) / kept-or-moved (中性) — 不展示 new
          // - new 列: new (右独有绿) / up (绿) / down (红) / kept (中性) — 不展示 dropped
          let cls = "";
          let mark = "";
          if (side === "orig") {
            if (state === "dropped") { cls = " fr-dropped"; mark = "✕"; }
            else if (state === "up") { mark = "↑"; }
            else if (state === "down") { mark = "↓"; }
          } else {
            if (state === "new") { cls = " fr-new"; mark = "+"; }
            else if (state === "up") { cls = " fr-up"; mark = "↑"; }
            else if (state === "down") { cls = " fr-down"; mark = "↓"; }
          }
          return (
            <div key={`${side}-${r.combo_id}`} className={`wif-final-row${cls}`}>
              <span className="rk">{r.rank}</span>
              <span className="nm" title={r.restaurant}>
                {mark && <span style={{ marginRight: 4 }}>{mark}</span>}
                {r.restaurant}
              </span>
              <span className="sc">{r.score.toFixed(3)}</span>
            </div>
          );
        })}
      </div>
    );
  }

  // diff KPI
  const diffSummary = useMemo(() => {
    if (!resultSession) return null;
    let newCount = 0;
    let droppedCount = 0;
    let upCount = 0;
    let downCount = 0;
    for (const r of newRows) {
      const s = classifyRow(origIdx, newIdx, r.combo_id);
      if (s === "new") newCount++;
      else if (s === "up") upCount++;
      else if (s === "down") downCount++;
    }
    for (const r of origRows) {
      const s = classifyRow(origIdx, newIdx, r.combo_id);
      if (s === "dropped") droppedCount++;
    }
    return { newCount, droppedCount, upCount, downCount };
  }, [resultSession, newRows, origRows, origIdx, newIdx]);

  return (
    <div className="what-if">
      <div className="wif-head">
        <h4>
          <span>🧪 What-if</span>
          <span className="dim mono">base = {baseSession.session_id}</span>
        </h4>
        <div className="wif-actions">
          <button
            className="btn primary"
            onClick={handleRun}
            disabled={loading || !parseRes.ok}
            style={loading || !parseRes.ok ? { opacity: 0.5, cursor: "not-allowed" } : undefined}
          >
            {loading ? "running…" : "▶ Run what-if"}
          </button>
          <button className="btn" onClick={onClose}>✕ 关闭</button>
        </div>
      </div>

      <div className="wif-edit">
        <label>
          profile_overrides (JSON · 见 DESIGN §4.2 白名单)
          {!parseRes.ok && (
            <span style={{ color: "var(--err)", marginLeft: 6 }}>
              ⚠ {parseRes.err}
            </span>
          )}
        </label>
        <textarea
          value={overridesText}
          onChange={(e) => setOverridesText(e.target.value)}
          spellCheck={false}
        />
        <div className="row-inline">
          <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={useLlm}
              onChange={(e) => setUseLlm(e.target.checked)}
            />
            <span>use_llm_rerank <span className="dim mono">(default off — Codex +4)</span></span>
          </label>
          <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <span>n_return</span>
            <input
              type="number"
              min={1}
              max={10}
              value={nReturn}
              onChange={(e) => setNReturn(Math.max(1, Math.min(10, Number(e.target.value) || 5)))}
            />
          </label>
          <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <span>n_explore</span>
            <input
              type="number"
              min={0}
              max={5}
              value={nExplore}
              onChange={(e) => setNExplore(Math.max(0, Math.min(5, Number(e.target.value) || 0)))}
            />
          </label>
        </div>
      </div>

      {errMsg && <div className="wif-err">{errMsg}</div>}

      <div className="wif-body">
        <div className="wif-pane">
          <h5>Original (Replay)</h5>
          {renderFinalCol(origRows, "orig")}
        </div>
        <div className="wif-pane">
          <h5>
            What-if
            {resultSession && llmCalled != null && (
              <span className="dim mono" style={{ marginLeft: 8, textTransform: "none" }}>
                ({llmCalled ? "LLM called" : "fallback"})
              </span>
            )}
          </h5>
          {resultSession
            ? renderFinalCol(newRows, "new")
            : <div className="dim" style={{ fontSize: 11 }}>(还没跑 — 改 overrides 点 ▶)</div>}
        </div>
      </div>

      {diffSummary && (
        <div className="diff-summary" style={{ marginTop: 0 }}>
          <div className="cell"><div className="k">new in top5</div><div className="v">{diffSummary.newCount}</div></div>
          <div className="cell"><div className="k">dropped</div><div className="v">{diffSummary.droppedCount}</div></div>
          <div className="cell"><div className="k">moved up</div><div className="v">{diffSummary.upCount}</div></div>
          <div className="cell"><div className="k">moved down</div><div className="v">{diffSummary.downCount}</div></div>
        </div>
      )}
    </div>
  );
}

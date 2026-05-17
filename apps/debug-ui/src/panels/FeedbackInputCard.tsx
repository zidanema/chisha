// D-083 PR-2: FeedbackInputCard — 反馈 → score+L3 派生层快照可视化.
// 数据源: session.feedback_view_snapshot (PR-1 后端写, 顶层 sibling).
// Codex S2 Q1=A: empty=true / undefined → 不渲染整张 card (DagHeader 节点灰显).
// Codex S2 漏项 #1: 必须容忍 session.feedback_view_snapshot === undefined.

import { useMemo } from "react";
import { Pill } from "../components/ui/Pill";
import type {
  FeedbackCalibrationRule,
  FeedbackNoteBreakdown,
  FeedbackRatingSignal,
  FeedbackViewSnapshot,
} from "../types/trace";

function explainFactors(f: FeedbackRatingSignal["factors"]): string {
  // factors 形如 {peak: -1.5, tau: 14, stage: "decay"} / {peak: 1.0, tau: 7, stage: "cooldown"} 等.
  // 不前端拼公式 (S1 brief §1.2), 渲染人类可读 stage + 参数.
  const peak = f.peak.toFixed(2);
  const tau = f.tau != null ? `, τ=${f.tau}d` : "";
  return `${f.stage} (peak=${peak}${tau})`;
}

function RatingRow({ r }: { r: FeedbackRatingSignal }) {
  const sign = r.signal > 0 ? "+" : "";
  const tone: "blue" | "red" = r.signal >= 0 ? "blue" : "red";
  return (
    <tr>
      <td className="mono" style={{ fontSize: 11 }}>{r.restaurant_name}</td>
      <td>
        <Pill tone={r.rating > 0 ? "blue" : "red"}>
          {r.rating > 0 ? "👍" : "👎"} {r.rating}
        </Pill>
      </td>
      <td className="mono right">{r.age_days}d</td>
      <td className="mono right">
        <Pill tone={tone}>{sign}{r.signal.toFixed(2)}</Pill>
      </td>
      <td className="dim mono" style={{ fontSize: 10 }}>{explainFactors(r.factors)}</td>
    </tr>
  );
}

function CalibrationRow({ c }: { c: FeedbackCalibrationRule }) {
  return (
    <div
      style={{
        padding: "6px 8px",
        marginBottom: 6,
        background: "var(--bg-inset)",
        borderLeft: "2px solid var(--L2)",
        borderRadius: 2,
      }}
    >
      <div className="row" style={{ gap: 8, alignItems: "baseline" }}>
        <span className="mono" style={{ fontSize: 11, fontWeight: 500 }}>
          {c.restaurant_name}
        </span>
        <span className="dim mono" style={{ fontSize: 10 }}>
          age_m={c.age_meals} · age_d={c.age_days} · w={c.weight.toFixed(2)}
        </span>
        {c.last_meal_cuisine && (
          <span className="dim mono" style={{ fontSize: 10 }}>
            · last={c.last_meal_cuisine}
          </span>
        )}
      </div>
      <div style={{ marginTop: 4, paddingLeft: 8 }}>
        {c.triggers.map((t, i) => (
          <div key={i} className="mono" style={{ fontSize: 10, color: "var(--t-2)" }}>
            ↳ <span style={{ color: "var(--t-1)" }}>{t.field}</span>
            {t.value != null && <span> = {t.value}</span>}
            {" · "}
            <span className="dim">{t.desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function NoteRow({ n }: { n: FeedbackNoteBreakdown }) {
  return (
    <div
      style={{
        padding: "6px 8px",
        marginBottom: 6,
        background: "var(--bg-inset)",
        borderLeft: "2px solid var(--refine)",
        borderRadius: 2,
      }}
    >
      <div className="row" style={{ gap: 8, alignItems: "baseline" }}>
        <span className="mono" style={{ fontSize: 11, fontWeight: 500 }}>{n.restaurant_name}</span>
        <span className="dim mono" style={{ fontSize: 10 }}>
          {n.age_days}d · decay {n.decay.toFixed(2)} · {n.source}
        </span>
      </div>
      <div
        className="mono"
        style={{ fontSize: 10, color: "var(--t-2)", marginTop: 4, fontStyle: "italic" }}
      >
        “{n.raw_text}”
      </div>
      <div className="row" style={{ gap: 4, marginTop: 4, flexWrap: "wrap" }}>
        {n.boost.map((t) => <Pill key={`b-${t}`} tone="blue">+{t}</Pill>)}
        {n.penalty.map((t) => <Pill key={`p-${t}`} tone="red">−{t}</Pill>)}
      </div>
    </div>
  );
}

export function FeedbackInputCard({
  snapshot,
}: {
  snapshot: FeedbackViewSnapshot | undefined;
}) {
  // Codex S2 Q1=A + 漏项 #1: undefined / empty → 不渲染整张 card.
  // 上层 App.tsx 已经按 hasFeedback gate, 这里是 defense-in-depth.
  if (!snapshot || snapshot.empty) return null;

  const { rating_signals, calibration_rules, note_breakdown, windows,
          global_token_freq, global_active_tokens, today } = snapshot;

  // Q15: sandbox advance loop 长链路渲染防重算. 这里按 snapshot ref 缓存.
  const globalFreqList = useMemo(() => {
    const items: { token: string; polarity: "boost" | "penalty";
                    freq: number; active: boolean }[] = [];
    const activeBoost = new Set(global_active_tokens.boost);
    const activePenalty = new Set(global_active_tokens.penalty);
    for (const [t, f] of Object.entries(global_token_freq.boost ?? {})) {
      items.push({ token: t, polarity: "boost", freq: f, active: activeBoost.has(t) });
    }
    for (const [t, f] of Object.entries(global_token_freq.penalty ?? {})) {
      items.push({ token: t, polarity: "penalty", freq: f, active: activePenalty.has(t) });
    }
    items.sort((a, b) => b.freq - a.freq);
    return items;
  }, [global_token_freq, global_active_tokens]);

  const nRating = rating_signals.length;
  const nCal = calibration_rules.length;
  const nNote = note_breakdown.length;

  return (
    <div className="panel" data-panel="feedback">
      <div className="panel-head">
        <span className="layer-tag layer-l2" style={{ background: "var(--refine)" }}>FB</span>
        <h2>反馈派生 · feedback view</h2>
        <span className="subtitle">
          today={today ?? "—"} · windows R={windows.ratings}d / C={windows.calibrations}d / N={windows.note_tokens}d
        </span>
        <div className="right">
          <Pill tone="gray">rating {nRating}</Pill>
          <Pill tone="gray">cal {nCal}</Pill>
          <Pill tone="gray">note {nNote}</Pill>
        </div>
      </div>
      <div className="panel-body">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
          {/* ── Ratings (餐厅级 rating ±1, 窗 60d) ── */}
          <div>
            <div className="subhead">
              Ratings <span className="count">{nRating} / {windows.ratings}d</span>
            </div>
            {nRating === 0 ? (
              <div className="dim mono" style={{ fontSize: 10, padding: "8px 0" }}>
                近 {windows.ratings} 天 0 条 rating
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>餐厅</th>
                    <th>rating</th>
                    <th className="right">age</th>
                    <th className="right">signal</th>
                    <th>factors</th>
                  </tr>
                </thead>
                <tbody>
                  {rating_signals.map((r, i) => <RatingRow key={i} r={r} />)}
                </tbody>
              </table>
            )}
          </div>

          {/* ── Calibrations (近 ≤3 餐 4 维 + age≤7) ── */}
          <div>
            <div className="subhead">
              Calibrations <span className="count">{nCal} / 最近 ≤3 餐, ≤{windows.calibrations}d</span>
            </div>
            {nCal === 0 ? (
              <div className="dim mono" style={{ fontSize: 10, padding: "8px 0" }}>
                近 3 餐 0 条 calibration
              </div>
            ) : (
              <div>
                {calibration_rules.map((c, i) => <CalibrationRow key={i} c={c} />)}
              </div>
            )}
          </div>

          {/* ── Notes (note + comments[], 窗 14d) ── */}
          <div>
            <div className="subhead">
              Notes <span className="count">{nNote} / {windows.note_tokens}d</span>
            </div>
            {nNote === 0 ? (
              <div className="dim mono" style={{ fontSize: 10, padding: "8px 0" }}>
                近 {windows.note_tokens} 天 0 条 note/comment
              </div>
            ) : (
              <div>
                {note_breakdown.map((n, i) => <NoteRow key={i} n={n} />)}
              </div>
            )}
            {globalFreqList.length > 0 && (
              <div style={{ marginTop: 10, paddingTop: 8,
                            borderTop: "1px dashed var(--line)" }}>
                <div className="dim mono" style={{ fontSize: 10, marginBottom: 4 }}>
                  全局 token 频次 (≥2 命中加粗)
                </div>
                <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                  {globalFreqList.map((g) => (
                    <Pill
                      key={`${g.polarity}-${g.token}`}
                      tone={g.polarity === "boost" ? "blue" : "red"}
                    >
                      <span style={{ fontWeight: g.active ? 600 : 400 }}>
                        {g.polarity === "boost" ? "+" : "−"}{g.token} ×{g.freq}
                      </span>
                    </Pill>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

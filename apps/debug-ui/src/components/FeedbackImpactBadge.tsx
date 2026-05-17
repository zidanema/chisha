// D-083 PR-2: per-combo "反馈影响" 角标. 数据源: L2Combo.feedback_evidence (sibling).
// 显示净 contribution + hover/展开列三段 evidence (rating / calibration / note).
//
// 净 = 三段 contribution 求和; evidence 非空但净 0 显示 "中性" (cancel, 不是无信号).
// evidence 全 undefined / 全空数组 → 不渲染 (no-op, 父组件 .feedback_evidence?. 链).

import { useState } from "react";
import { Pill } from "./ui/Pill";
import type {
  FeedbackEvidence,
  FeedbackEvidenceCalibration,
  FeedbackEvidenceNoteGlobal,
  FeedbackEvidenceNoteRestaurant,
} from "../types/trace";

function netImpact(ev: FeedbackEvidence): {
  net: number;
  recencyN: number;
  calN: number;
  noteN: number;
  anyEv: boolean;
} {
  let net = 0;
  let recencyN = 0;
  let calN = 0;
  let noteN = 0;
  for (const r of ev.feedback_recency ?? []) {
    net += r.signal;
    recencyN += 1;
  }
  for (const c of ev.next_meal_calibration ?? []) {
    for (const rf of c.rules_fired ?? []) {
      net += rf.contribution;
    }
    calN += 1;
  }
  for (const n of ev.note_boost ?? []) {
    net += n.contribution;
    noteN += 1;
  }
  const anyEv = recencyN + calN + noteN > 0;
  return { net, recencyN, calN, noteN, anyEv };
}

function NoteEvRow({ n }: { n: FeedbackEvidenceNoteRestaurant | FeedbackEvidenceNoteGlobal }) {
  const sign = n.contribution > 0 ? "+" : "";
  const subject = n.kind === "restaurant"
    ? `${n.restaurant_name}`
    : `[全局 ×${n.freq}]`;
  return (
    <div className="fb-ev-row mono" style={{ fontSize: 10 }}>
      <span className="dim">note</span>{" "}
      <span>{subject} · {n.token}</span>{" "}
      <span className="dim">({n.polarity}, decay {n.decay.toFixed(2)})</span>{" "}
      <span style={{ color: n.contribution >= 0 ? "var(--ok)" : "var(--err)" }}>
        {sign}{n.contribution.toFixed(3)}
      </span>
      {n.subkind && <span className="dim"> · {n.subkind}</span>}
    </div>
  );
}

function CalEvRow({ c }: { c: FeedbackEvidenceCalibration }) {
  const totalContrib = (c.rules_fired ?? []).reduce(
    (a, r) => a + r.contribution, 0
  );
  const sign = totalContrib > 0 ? "+" : "";
  return (
    <div className="fb-ev-row mono" style={{ fontSize: 10 }}>
      <span className="dim">cal</span>{" "}
      <span>{c.restaurant_name ?? "—"} (age_m={c.age_meals}, w={c.weight.toFixed(2)})</span>{" "}
      <span style={{ color: totalContrib >= 0 ? "var(--ok)" : "var(--err)" }}>
        {sign}{totalContrib.toFixed(3)}
      </span>
      <div style={{ paddingLeft: 16, color: "var(--t-3)" }}>
        {(c.rules_fired ?? []).map((r, i) => (
          <div key={i}>↳ {r.rule}  <span style={{ color: "var(--t-2)" }}>{r.contribution >= 0 ? "+" : ""}{r.contribution.toFixed(3)}</span></div>
        ))}
      </div>
    </div>
  );
}

export function FeedbackImpactBadge({ ev }: { ev: FeedbackEvidence | undefined }) {
  const [open, setOpen] = useState(false);
  if (!ev) return null;
  const { net, recencyN, calN, noteN, anyEv } = netImpact(ev);
  if (!anyEv) return null;

  // 净 0 但 evidence 非空 → cancel; Codex S2 Q3=A 显式标"中性"
  const isNeutral = Math.abs(net) < 1e-6;
  const tone: "red" | "orange" | "blue" | "gray" = isNeutral
    ? "gray"
    : net > 0
      ? "blue"
      : "red";
  const sign = net > 0 ? "+" : "";
  const headLabel = isNeutral
    ? `⚖ 反馈中性 (recency ${recencyN} · cal ${calN} · note ${noteN})`
    : `⚠ 反馈影响 ${sign}${net.toFixed(2)} (recency ${recencyN} · cal ${calN} · note ${noteN})`;

  return (
    <div style={{ marginTop: 6 }}>
      <button
        onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        style={{
          background: "transparent",
          border: "none",
          padding: 0,
          cursor: "pointer",
          fontFamily: "var(--mono)",
          fontSize: 10,
          textAlign: "left",
        }}
        title="点击展开 evidence"
      >
        <Pill tone={tone}>{headLabel} {open ? "▾" : "▸"}</Pill>
      </button>
      {open && (
        <div
          className="feedback-ev-detail"
          style={{
            marginTop: 6,
            padding: "6px 10px",
            background: "var(--bg-inset)",
            borderLeft: "2px solid var(--line-strong)",
            fontSize: 10,
            lineHeight: 1.6,
          }}
        >
          {(ev.feedback_recency ?? []).map((r, i) => {
            const sgn = r.signal > 0 ? "+" : "";
            return (
              <div key={`rec-${i}`} className="fb-ev-row mono">
                <span className="dim">rcy</span>{" "}
                <span>{r.restaurant_name} · rating={r.rating}, age={r.age_days}d</span>{" "}
                <span style={{ color: r.signal >= 0 ? "var(--ok)" : "var(--err)" }}>
                  {sgn}{r.signal.toFixed(3)}
                </span>
              </div>
            );
          })}
          {(ev.next_meal_calibration ?? []).map((c, i) => (
            <CalEvRow key={`cal-${i}`} c={c} />
          ))}
          {(ev.note_boost ?? []).map((n, i) => (
            <NoteEvRow key={`note-${i}`} n={n} />
          ))}
        </div>
      )}
    </div>
  );
}

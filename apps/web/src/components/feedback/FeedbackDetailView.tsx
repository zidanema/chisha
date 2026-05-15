// FeedbackDetailView — V1.1 已反馈只读 snapshot + append-only timeline (D-064/065).
// 注意: snapshot 永久 readonly, 即使提交 1 分钟内也不能改; 改 → 撤销重提 (V2 才做)。
// 备注只能 append, 每条独立 timestamped 单元。

import { useState } from "react";
import { Link } from "react-router-dom";
import { LABELS } from "@/lib/labels";
import { cx } from "@/lib/cx";
import { api } from "@/lib/api";
import type {
  Candidate,
  DimVal,
  FeedbackRecord,
  FeedbackSession,
  GutVal,
} from "@/lib/types";
import { buildDimRows, relAgo } from "./atoms";

const GUT_OPTIONS: { v: -1 | 0 | 1; icon: string; labelKey: "fbARatingBad" | "fbARatingOk" | "fbARatingGood" }[] = [
  { v: -1, icon: "👎", labelKey: "fbARatingBad" },
  { v: 0, icon: "😐", labelKey: "fbARatingOk" },
  { v: 1, icon: "👍", labelKey: "fbARatingGood" },
];

export function FeedbackDetailView({
  sessionData,
  feedback,
  onAppended,
}: {
  sessionData: FeedbackSession;
  feedback: FeedbackRecord;
  onAppended: () => void | Promise<void>;
}) {
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const candidate: Candidate | null =
    feedback.accepted_rank != null
      ? sessionData.candidates.find((c) => c.rank === feedback.accepted_rank) ?? null
      : null;

  const dt = new Date(feedback.submitted_at);
  const dateStr = Number.isNaN(dt.getTime())
    ? ""
    : `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")} ${LABELS.meal[sessionData.meal_type] || ""}`;
  const ago = relAgo(feedback.submitted_at);

  async function submitComment() {
    const text = comment.trim();
    if (!text || submitting) return;
    setSubmitting(true);
    try {
      await api.appendFeedbackComment({ session_id: sessionData.session_id, text });
      setComment("");
      await onAppended();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="mt-5 mb-5 flex items-center gap-3">
        <Link
          to="/feedback"
          className="text-[12.5px] text-[color:var(--muted)] hover:text-[color:var(--fg)] inline-flex items-center gap-1"
        >
          ← {LABELS.ui.fbBackToInbox}
        </Link>
        <span className="ml-auto text-[12.5px] text-[color:var(--muted)] tabular-nums">
          {dateStr}
        </span>
      </div>

      {/* Header: ordered restaurant + when submitted */}
      {candidate ? (
        <div
          className="mb-5 rounded-lg border border-[color:var(--accent)] px-4 py-3"
          style={{ background: "color-mix(in srgb, var(--accent) 6%, var(--surface))" }}
        >
          <div className="flex items-baseline gap-2 mb-1">
            <span aria-hidden="true" style={{ color: "var(--accent)" }}>
              ✓
            </span>
            <span className="text-[12.5px] text-[color:var(--muted)]">
              {LABELS.ui.fbPickedHint}
            </span>
            <span
              className="ml-auto text-[11.5px] tabular-nums"
              style={{ color: "var(--accent)" }}
            >
              {LABELS.ui.fbDetailSubmittedAt(ago)}
            </span>
          </div>
          <div className="text-[14px] font-semibold tracking-tight leading-snug">
            {candidate.restaurant.name}
          </div>
          <div className="text-[12.5px] text-[color:var(--muted)] mt-0.5 leading-relaxed">
            {candidate.summary}
          </div>
        </div>
      ) : feedback.accepted_rank == null ? (
        <div className="mb-5 rounded-md border border-dashed border-[color:var(--border)] px-4 py-2.5 text-[12.5px] text-[color:var(--muted)]">
          {LABELS.ui.fbDetailNotEaten}
        </div>
      ) : null}

      <div className="flex items-baseline gap-3 mb-3">
        <h2 className="text-[15px] font-semibold tracking-tight">
          {LABELS.ui.fbDetailTitle}
        </h2>
        <span className="text-[11.5px] text-[color:var(--muted)]">
          {LABELS.ui.fbDetailLocked}
        </span>
      </div>

      <FeedbackSnapshot feedback={feedback} candidate={candidate} />

      {feedback.note && (
        <div className="mt-4 rounded-md border border-[color:var(--border)] bg-[color:var(--surface)] px-3 py-2.5">
          <div className="text-[10.5px] uppercase tracking-wider text-[color:var(--muted)] mb-1">
            {LABELS.ui.fbDetailOriginalNote}
          </div>
          <div className="text-[13px] text-[color:var(--fg)] leading-relaxed whitespace-pre-wrap">
            {feedback.note}
          </div>
        </div>
      )}

      {/* Timeline */}
      {feedback.comments && feedback.comments.length > 0 && (
        <div className="mt-5">
          <div className="text-[10.5px] uppercase tracking-wider text-[color:var(--muted)] mb-2">
            {LABELS.ui.fbDetailTimeline}
          </div>
          <ol className="space-y-2">
            {feedback.comments.map((c) => (
              <li key={c.id} className="flex items-start gap-3 text-[12.5px]">
                <span
                  className="shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full"
                  style={{ background: "var(--accent)", opacity: 0.5 }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-[10.5px] text-[color:var(--muted)] tabular-nums mb-0.5">
                    {relAgo(c.created_at)}
                  </div>
                  <div className="text-[13px] leading-relaxed whitespace-pre-wrap">
                    {c.text}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Append form — append-only, 不能改原 snapshot */}
      <div className="mt-6 rounded-lg border border-dashed border-[color:var(--border)] bg-[color:var(--surface)]/40 p-4">
        <div className="text-[13.5px] font-semibold tracking-tight mb-2">
          {LABELS.ui.fbDetailAppendTitle}
        </div>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={2}
          placeholder={LABELS.ui.fbDetailAppendPlaceholder}
          className="w-full bg-transparent rounded-md border border-[color:var(--border)] p-2.5 text-[13px] focus:outline-none focus:border-[color:var(--fg)] resize-none leading-relaxed"
        />
        <div className="mt-2 flex items-center">
          <Link
            to="/"
            className="text-[12px] text-[color:var(--muted)] hover:text-[color:var(--fg)]"
          >
            {LABELS.ui.fbDetailJumpHome}
          </Link>
          <button
            onClick={submitComment}
            disabled={!comment.trim() || submitting}
            className="ml-auto px-3.5 py-1.5 rounded-md text-[13px] font-medium disabled:opacity-40"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            {LABELS.ui.fbDetailAppendSubmit}
          </button>
        </div>
      </div>
    </>
  );
}

function FeedbackSnapshot({
  feedback,
  candidate,
}: {
  feedback: FeedbackRecord;
  candidate: Candidate | null;
}) {
  const rating: GutVal = feedback.rating ?? null;
  const dims: Record<"reason" | "fullness" | "oil" | "repeat", DimVal> = {
    reason: feedback.reason_match,
    fullness: feedback.fullness,
    oil: feedback.oil_calibration,
    repeat: feedback.repurchase_intent,
  };
  const rows = buildDimRows(candidate);
  const hasAnyDim = Object.values(dims).some((v) => v != null);

  return (
    <div className="space-y-3">
      {/* gut rating row */}
      <div>
        <div className="text-[10.5px] uppercase tracking-wider text-[color:var(--muted)] mb-1.5">
          {LABELS.ui.fbDetailRating}
        </div>
        <div className="grid grid-cols-3 gap-2">
          {GUT_OPTIONS.map((o) => {
            const active = rating === o.v;
            return (
              <div
                key={o.v}
                className={cx(
                  "py-3 rounded-lg border text-center select-none",
                  active
                    ? "border-[color:var(--accent)] bg-[color:var(--accent-bg)]"
                    : "border-[color:var(--border)] opacity-30"
                )}
              >
                <div className="text-[22px] leading-none mb-1">{o.icon}</div>
                <div
                  className={cx(
                    "text-[12px]",
                    active
                      ? "text-[color:var(--accent)] font-semibold"
                      : "text-[color:var(--muted)]"
                  )}
                >
                  {LABELS.ui[o.labelKey]}
                </div>
              </div>
            );
          })}
        </div>
        {rating == null && (
          <div className="mt-1.5 text-[11.5px] text-[color:var(--muted)]">
            {LABELS.ui.fbDetailNoRating}
          </div>
        )}
      </div>

      {/* dim table (readonly) */}
      {hasAnyDim && (
        <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] overflow-hidden">
          <div className="grid grid-cols-[78px,1fr,160px] px-4 py-2 border-b border-[color:var(--border)] bg-[color:var(--surface-2)]/30 gap-3 items-baseline">
            <div />
            <div className="text-[10.5px] uppercase tracking-wider text-[color:var(--muted)]">
              {LABELS.ui.fbEColPrediction}
            </div>
            <div
              className="text-[10.5px] uppercase tracking-wider"
              style={{ color: "var(--accent)" }}
            >
              {LABELS.ui.fbEColReality}
            </div>
          </div>
          {rows.map((r) => {
            const v = dims[r.id];
            return (
              <div
                key={r.id}
                className="grid grid-cols-[78px,1fr,160px] px-4 py-3 border-b border-[color:var(--border)] last:border-b-0 items-center gap-3"
              >
                <div className="text-[12.5px] text-[color:var(--fg)]">{r.label}</div>
                <div className="pr-2 min-w-0">{r.pred}</div>
                <div className="inline-flex rounded-md border border-[color:var(--border)] overflow-hidden">
                  {r.opts.map((o, i) => {
                    const active = v === (i as DimVal);
                    return (
                      <div
                        key={o}
                        className={cx(
                          "flex-1 px-2 py-1 text-[12px] border-l first:border-l-0 select-none whitespace-nowrap text-center",
                          active ? "font-medium" : "text-[color:var(--muted)] opacity-40"
                        )}
                        style={{
                          borderLeftColor: "var(--border)",
                          background: active ? "var(--accent-bg)" : "transparent",
                          color: active ? "var(--accent)" : undefined,
                        }}
                      >
                        {o}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ProgressiveForm — V1.1 反馈表单 (D-062 选定 E 渐进披露 + 借 D 复盘卡形态)
// 头部: 整体好吃度 (gut 1 个) — 难吃 / 普通 / 好吃 (D-064)
// 展开: 4 维 calibration/behavior, 每行对齐当时 prediction (D-065)
// 备注: optional textarea
// 都没吃这几个: 逃生口 (variant="not-eaten" 走专用 payload)
//
// 提交后由父组件就地切到 FeedbackDetailView, 不 navigate 走 (D-066 "完成感")。

import { useMemo, useState } from "react";
import { LABELS } from "@/lib/labels";
import { cx } from "@/lib/cx";
import type { Candidate, DimVal, FeedbackPayload, GutVal } from "@/lib/types";
import { buildDimRows, DimTable, GUT_OPTIONS } from "./atoms";

type DimsState = {
  reason: DimVal;
  fullness: DimVal;
  oil: DimVal;
  repeat: DimVal;
};

export function ProgressiveForm({
  pickedCandidate,
  defaultAcceptedRank,
  onSubmit,
  onNotEaten,
  submitting,
}: {
  pickedCandidate: Candidate | null;
  defaultAcceptedRank: number | null;
  onSubmit: (payload: FeedbackPayload) => void | Promise<void>;
  onNotEaten: () => void | Promise<void>;
  submitting: boolean;
}) {
  const [rating, setRating] = useState<GutVal>(null);
  const [dims, setDims] = useState<DimsState>({
    reason: null,
    fullness: null,
    oil: null,
    repeat: null,
  });
  const [note, setNote] = useState("");
  const [expanded, setExpanded] = useState(false);

  const rows = useMemo(() => buildDimRows(pickedCandidate), [pickedCandidate]);
  const dimFilled = Object.values(dims).filter((v) => v !== null).length;

  function setDim(k: keyof DimsState, v: DimVal) {
    setDims((d) => ({ ...d, [k]: v }));
  }

  function submit() {
    if (rating === null || submitting) return;
    void onSubmit({
      session_id: "",
      accepted_rank: defaultAcceptedRank,
      rating,
      reason_match: dims.reason,
      fullness: dims.fullness,
      oil_calibration: dims.oil,
      repurchase_intent: dims.repeat,
      note,
      variant: "progressive",
    });
  }

  return (
    <div>
      <SectionTitle title={LABELS.ui.fbAQuestion} />

      {/* 头部 · gut 三档 */}
      <div className="grid grid-cols-3 gap-2">
        {GUT_OPTIONS.map((o) => {
          const active = rating === o.v;
          return (
            <button
              key={o.v}
              onClick={() => setRating(active ? null : o.v)}
              className={cx(
                "py-5 rounded-lg border text-center transition-all",
                active
                  ? "border-[color:var(--accent)] bg-[color:var(--accent-bg)]"
                  : "border-[color:var(--border)] hover:border-[color:var(--fg)] hover:bg-[color:var(--surface-2)]"
              )}
            >
              <div className="text-[28px] mb-1 leading-none">{o.icon}</div>
              <div
                className={cx(
                  "text-[12.5px]",
                  active
                    ? "text-[color:var(--accent)] font-semibold"
                    : "text-[color:var(--muted)]"
                )}
              >
                {LABELS.ui[o.labelKey]}
              </div>
            </button>
          );
        })}
      </div>

      {/* 渐进披露 — 头部填了才出现展开按钮 + 备注 */}
      {rating !== null && (
        <div className="mt-4">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="w-full text-left text-[12.5px] py-2 px-3 rounded-md border border-dashed border-[color:var(--border)] hover:border-[color:var(--accent)] transition-colors flex items-center gap-2"
            style={{ color: expanded ? "var(--accent)" : "var(--muted)" }}
          >
            <span aria-hidden="true">{expanded ? "△" : "▽"}</span>
            <span>{expanded ? LABELS.ui.fbECollapse : LABELS.ui.fbEExpand}</span>
            {dimFilled > 0 && !expanded && (
              <span
                className="ml-auto text-[10.5px] px-1.5 py-0 rounded tabular-nums"
                style={{ background: "var(--accent-bg)", color: "var(--accent)" }}
              >
                {dimFilled}
              </span>
            )}
          </button>

          {expanded && (
            <div className="mt-3">
              <DimTable rows={rows} mode="edit" values={dims} onPick={setDim} />
            </div>
          )}

          {/* Note — gut 选完后才显示，跟展开同级 */}
          <div className="mt-4">
            <div className="text-[11px] text-[color:var(--muted)] uppercase tracking-wider mb-2">
              {LABELS.ui.fbNote}
            </div>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder={LABELS.ui.fbNotePlaceholder}
              className="w-full bg-transparent rounded-md border border-[color:var(--border)] p-2.5 text-[13px] focus:outline-none focus:border-[color:var(--fg)] resize-none leading-relaxed"
            />
          </div>
        </div>
      )}

      {/* Submit bar */}
      <div className="flex items-center pt-4 mt-1 border-t border-dashed border-[color:var(--border)]">
        <button
          onClick={onNotEaten}
          disabled={submitting}
          className="text-[12px] text-[color:var(--muted)] hover:text-[color:var(--fg)] inline-flex items-center gap-1 disabled:opacity-40"
        >
          {LABELS.ui.fbANotEaten}
        </button>
        <button
          onClick={submit}
          disabled={rating === null || submitting}
          className="ml-auto px-4 py-1.5 rounded-md text-[13.5px] font-medium disabled:opacity-40"
          style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
        >
          {LABELS.ui.fbSubmit}
        </button>
      </div>
    </div>
  );
}

function SectionTitle({ title }: { title: string }) {
  return (
    <div className="mb-3">
      <div className="text-[15px] font-semibold tracking-tight">{title}</div>
    </div>
  );
}

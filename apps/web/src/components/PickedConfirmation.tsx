import { useState } from "react";
import { LABELS } from "@/lib/labels";
import type { Candidate } from "@/lib/types";

// D-050: 持久 inline 状态 — 用户点 pick 后的"你选了 X · 去搜店名下单"面板。
// 替代 toast-and-disappear。Deeplink iOS/Android 不可靠 → 提供复制店名 + 文案指引。
export function PickedConfirmation({
  candidate,
  onUnpick,
}: {
  candidate: Candidate | null;
  onUnpick: () => void;
}) {
  const [copied, setCopied] = useState(false);
  if (!candidate) return null;
  const c = candidate;

  async function copyName() {
    try {
      await navigator.clipboard.writeText(c.restaurant.name);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked — silent fail, user can still read */
    }
  }

  return (
    <div
      className="mt-4 rounded-lg border border-[color:var(--accent)] p-4"
      style={{ background: "color-mix(in srgb, var(--accent) 6%, var(--surface))" }}
    >
      <div className="flex items-baseline gap-2 mb-2">
        <span aria-hidden="true" style={{ color: "var(--accent)" }}>✓</span>
        <span className="text-[14px] font-semibold tracking-tight">
          {LABELS.ui.pickedTitle}
        </span>
        <button
          onClick={onUnpick}
          className="ml-auto text-[11.5px] text-[color:var(--muted)] hover:text-[color:var(--fg)] underline-offset-2 hover:underline"
        >
          {LABELS.ui.pickChange} ↺
        </button>
      </div>
      <div className="text-[13px] text-[color:var(--fg)] leading-relaxed">
        <span className="font-medium">{c.restaurant.name}</span>
        <div className="text-[12.5px] text-[color:var(--muted)] mt-0.5">{c.summary}</div>
      </div>
      <div className="mt-3 flex items-center gap-3 flex-wrap">
        <span className="text-[12.5px]" style={{ color: "var(--fg)" }}>
          {LABELS.ui.pickedActHint}
        </span>
        <button
          onClick={copyName}
          className="text-[11.5px] px-2 py-0.5 rounded-md border border-[color:var(--border)] hover:border-[color:var(--accent)] inline-flex items-center gap-1"
        >
          <span aria-hidden="true">{copied ? "✓" : "⎘"}</span>
          {copied ? LABELS.ui.copyDone : LABELS.ui.copyName}
        </button>
        <span className="text-[11.5px] text-[color:var(--muted)] ml-auto">
          {LABELS.ui.pickedFbHint}
        </span>
      </div>
    </div>
  );
}

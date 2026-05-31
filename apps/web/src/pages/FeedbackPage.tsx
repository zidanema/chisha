// FeedbackPage — /feedback/:id 双态 (D-066 一次性 readonly)
//   feedback === null   → ProgressiveForm
//   feedback !== null   → FeedbackDetailView (snapshot + append timeline)
//
// 提交后就地 setFeedback, 不 navigate 走 (D-066 "完成感")。

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { LABELS } from "@/lib/labels";
import { api } from "@/lib/api";
import { useChisha } from "@/lib/useChishaState";
import { PageShell, FooterBar } from "@/components/PageShell";
import { ProgressiveForm } from "@/components/feedback/ProgressiveForm";
import { FeedbackDetailView } from "@/components/feedback/FeedbackDetailView";
import type {
  Candidate,
  FeedbackPayload,
  FeedbackRecord,
  FeedbackSession,
} from "@/lib/types";

export function FeedbackPage() {
  const { id } = useParams();
  const sessionId = id ?? "";
  const { refreshInbox, showToast } = useChisha();

  const [session, setSession] = useState<FeedbackSession | null>(null);
  // undefined = loading; null = none yet; record = submitted
  const [feedback, setFeedback] = useState<FeedbackRecord | null | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  // session 拉取失败 (404 过期/不存在) → 错误卡, 不再永久卡 loading
  const [notFound, setNotFound] = useState(false);

  const reload = useCallback(async () => {
    // 同 boot effect: session 必需 (失败 → 错误卡), record best-effort (失败当 null)
    const [sRes, fbRes] = await Promise.allSettled([
      api.getFeedbackSession({ session_id: sessionId }),
      api.getFeedback({ session_id: sessionId }),
    ]);
    if (sRes.status === "rejected") {
      setNotFound(true);
      return;
    }
    setSession(sRes.value);
    setFeedback(fbRes.status === "fulfilled" ? fbRes.value : null);
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    // 切 session 时回到 loading 态, 清掉上一条的 notFound/数据
    setNotFound(false);
    setSession(null);
    setFeedback(undefined);
    void (async () => {
      // allSettled: session 是必需 (失败 → 错误卡); record 是 best-effort (失败当 null)
      const [sRes, fbRes] = await Promise.allSettled([
        api.getFeedbackSession({ session_id: sessionId }),
        api.getFeedback({ session_id: sessionId }),
      ]);
      if (cancelled) return;
      if (sRes.status === "rejected") {
        setNotFound(true);
        return;
      }
      setSession(sRes.value);
      setFeedback(fbRes.status === "fulfilled" ? fbRes.value : null);
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  async function onSubmit(payload: FeedbackPayload) {
    if (submitting) return;
    setSubmitting(true);
    try {
      await api.feedback({ ...payload, session_id: sessionId });
      showToast(LABELS.ui.fbDone, "good");
      await reload();             // in-place 切到 detail view
      await refreshInbox();       // banner + 角标更新
    } finally {
      setSubmitting(false);
    }
  }

  async function onNotEaten() {
    if (submitting) return;
    setSubmitting(true);
    try {
      await api.feedback({
        session_id: sessionId,
        accepted_rank: null,
        rating: null,
        reason_match: null,
        fullness: null,
        oil_calibration: null,
        repurchase_intent: null,
        note: "",
        variant: "not-eaten",
      });
      showToast(LABELS.ui.fbDone, "good");
      await reload();
      await refreshInbox();
    } finally {
      setSubmitting(false);
    }
  }

  // ── session 过期/找不到 → 错误卡 (D-066 inline 持久, 不靠 toast) ──────
  if (notFound) {
    return (
      <PageShell>
        <div className="mt-20 text-center space-y-3">
          <div className="text-[14px] text-[color:var(--muted)]">
            {LABELS.ui.fbNotFound}
          </div>
          <Link
            to="/feedback"
            className="inline-block text-[13px] px-3 py-1.5 rounded-md border border-[color:var(--border)] hover:border-[color:var(--fg)]"
          >
            ← {LABELS.ui.fbBackToInbox}
          </Link>
        </div>
        <FooterBar />
      </PageShell>
    );
  }

  if (!session || feedback === undefined) {
    return (
      <PageShell>
        <div className="mt-10 space-y-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-24 rounded-lg bg-[color:var(--surface)] animate-pulse"
            />
          ))}
        </div>
      </PageShell>
    );
  }

  // ── 已反馈 → 只读 detail ─────────────────────────────────────────────
  if (feedback) {
    return (
      <PageShell>
        <FeedbackDetailView
          sessionData={session}
          feedback={feedback}
          onAppended={reload}
        />
        <FooterBar />
      </PageShell>
    );
  }

  // ── 未反馈 → 表单 ──────────────────────────────────────────────────
  const dt = new Date(session.accepted_at);
  const dateStr = Number.isNaN(dt.getTime())
    ? ""
    : `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")} ${LABELS.meal[session.meal_type]}`;
  const pickedCandidate: Candidate | null =
    session.accepted_rank != null
      ? session.candidates.find((c) => c.rank === session.accepted_rank) ?? null
      : null;

  return (
    <PageShell>
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

      {pickedCandidate ? (
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
          </div>
          <div className="text-[14px] font-semibold tracking-tight leading-snug">
            {pickedCandidate.restaurant.name}
          </div>
          <div className="text-[12.5px] text-[color:var(--muted)] mt-0.5 leading-relaxed">
            {pickedCandidate.summary}
          </div>
        </div>
      ) : (
        <div className="mb-5 rounded-md border border-dashed border-[color:var(--border)] px-4 py-2.5 text-[12.5px] text-[color:var(--muted)]">
          {LABELS.ui.fbNoPickHint}
        </div>
      )}

      <ProgressiveForm
        pickedCandidate={pickedCandidate}
        defaultAcceptedRank={session.accepted_rank}
        onSubmit={onSubmit}
        onNotEaten={onNotEaten}
        submitting={submitting}
      />

      <FooterBar />
    </PageShell>
  );
}

// /feedback/last — 解析到最新一条未反馈 session (inbox[0])
export function FeedbackLastResolverPage() {
  const navigate = useNavigate();
  const { inbox } = useChisha();
  const first = inbox.find((x) => !x.snoozed) || inbox[0];

  useEffect(() => {
    if (first?.session_id) navigate(`/feedback/${first.session_id}`, { replace: true });
  }, [first, navigate]);

  if (first?.session_id) return null;

  return (
    <PageShell>
      <div className="mt-20 text-center space-y-3">
        <div className="text-[14px] text-[color:var(--muted)]">{LABELS.ui.fbEmpty}</div>
        <Link
          to="/"
          className="inline-block text-[13px] px-3 py-1.5 rounded-md border border-[color:var(--border)] hover:border-[color:var(--fg)]"
        >
          {LABELS.ui.fbEmptyAction}
        </Link>
      </div>
      <FooterBar />
    </PageShell>
  );
}

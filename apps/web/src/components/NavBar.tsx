import { Link, useLocation } from "react-router-dom";
import { LABELS } from "@/lib/labels";
import { cx } from "@/lib/cx";
import { useChisha } from "@/lib/useChishaState";

function Icon({ kind }: { kind: "gear" | "clock" | "fb" }) {
  if (kind === "gear")
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="7" cy="7" r="2.2" />
        <path d="M7 1.4v1.4M7 11.2v1.4M2.4 2.4l1 1M10.6 10.6l1 1M1.4 7h1.4M11.2 7h1.4M2.4 11.6l1-1M10.6 3.4l1-1" />
      </svg>
    );
  if (kind === "clock")
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="7" cy="7" r="5.6" />
        <path d="M7 3.5V7l2.3 1.4" />
      </svg>
    );
  // 餐盘 + 对勾 — 「吃过 + 反馈」
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="7" cy="7" r="5.4" />
      <path d="M4.5 7.2l1.8 1.8L9.7 5.4" />
    </svg>
  );
}

export function NavBar() {
  const { pathname } = useLocation();
  const { inbox } = useChisha();
  const unfedCount = inbox.filter((x) => !x.snoozed && !x.stopped).length;

  const fbActive = pathname === "/feedback" || pathname.startsWith("/feedback/");

  return (
    <header className="border-b border-[color:var(--border)] bg-[color:var(--bg)]/95 backdrop-blur sticky top-0 z-30">
      <div className="mx-auto max-w-[960px] px-6 h-12 flex items-center gap-3">
        <Link to="/" className="flex items-center gap-2">
          <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
            <rect x="1" y="1" width="18" height="18" rx="4" fill="none" stroke="var(--accent)" strokeWidth="1.5" />
            <rect x="5.5" y="5.5" width="9" height="9" rx="1.5" fill="var(--accent)" />
          </svg>
          <span className="font-semibold text-[14.5px] tracking-tight">{LABELS.ui.homeTitle}</span>
        </Link>
        <div className="ml-auto flex items-center gap-1">
          <Link
            to="/feedback"
            className={cx(
              "relative inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12.5px]",
              fbActive
                ? "text-[color:var(--fg)] bg-[color:var(--surface)]"
                : "text-[color:var(--muted)] hover:text-[color:var(--fg)] hover:bg-[color:var(--surface)]"
            )}
          >
            <Icon kind="fb" />
            {LABELS.ui.navFeedback}
            {unfedCount > 0 && (
              <span
                aria-label={`${unfedCount} 餐待反馈`}
                className="ml-0.5 inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full text-[10.5px] font-medium tabular-nums leading-none"
                style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
              >
                {unfedCount}
              </span>
            )}
          </Link>
          <Link
            to="/history"
            className={cx(
              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12.5px]",
              pathname === "/history"
                ? "text-[color:var(--fg)] bg-[color:var(--surface)]"
                : "text-[color:var(--muted)] hover:text-[color:var(--fg)] hover:bg-[color:var(--surface)]"
            )}
          >
            <Icon kind="clock" />
            {LABELS.ui.navHistory}
          </Link>
          <Link
            to="/profile"
            className={cx(
              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[12.5px]",
              pathname === "/profile"
                ? "text-[color:var(--fg)] bg-[color:var(--surface)]"
                : "text-[color:var(--muted)] hover:text-[color:var(--fg)] hover:bg-[color:var(--surface)]"
            )}
          >
            <Icon kind="gear" />
            {LABELS.ui.navPrefer}
          </Link>
        </div>
      </div>
    </header>
  );
}

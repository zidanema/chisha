import { useMemo } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { LABELS } from "@/lib/labels";
import { api } from "@/lib/api";
import { ChishaProvider, useChisha } from "@/lib/useChishaState";

import { NavBar } from "@/components/NavBar";
import { DetailPanel } from "@/components/DetailPanel";
import { Toast } from "@/components/Toast";
import { PageShell } from "@/components/PageShell";

import { HomePage } from "@/pages/HomePage";
import { ProfilePage } from "@/pages/ProfilePage";
import { HistoryPage } from "@/pages/HistoryPage";
import { FeedbackPage, FeedbackLastResolverPage } from "@/pages/FeedbackPage";
import { FeedbackInbox } from "@/pages/FeedbackInbox";

// Single-source theme (DESIGN_NOTES §4) — light + indigo accent. Dark mode is
// V2; tweaks panel from the prototype was a claude.ai/design host shim and
// is intentionally dropped.
const ACCENT_HEX = "#4f46e5";

function themeVars(): React.CSSProperties {
  return {
    "--bg": "oklch(0.99 0.003 260)",
    "--surface": "oklch(0.975 0.005 260)",
    "--surface-2": "oklch(0.95 0.007 260)",
    "--border": "oklch(0.90 0.008 260)",
    "--fg": "oklch(0.22 0.015 265)",
    "--muted": "oklch(0.52 0.012 265)",
    "--accent": ACCENT_HEX,
    "--accent-fg": "white",
    "--accent-bg": `color-mix(in srgb, ${ACCENT_HEX} 10%, transparent)`,
    "--good": "oklch(0.55 0.13 145)",
    "--bad": "oklch(0.58 0.18 25)",
    "--bad-bg": "oklch(0.95 0.04 25)",
    "--info": "oklch(0.55 0.13 230)",
  } as React.CSSProperties;
}

function NotFound() {
  const { pathname } = useLocation();
  return (
    <PageShell>
      <div className="mt-16 text-center text-[color:var(--muted)]">
        <div className="text-[14px] mb-2">
          {LABELS.ui.unknownRoute}{" "}
          <span className="font-mono">{pathname}</span>
        </div>
        <Link
          to="/"
          className="inline-block text-[12.5px] px-3 py-1.5 rounded-md border border-[color:var(--border)]"
        >
          {LABELS.ui.backHome}
        </Link>
      </div>
    </PageShell>
  );
}

function Shell() {
  const { home, setHome, refreshInbox, toast } = useChisha();

  // Detail "就这个" — mirrors HomePage's onPick (lock card + accept, no fake deeplink)
  async function onDetailPick(c: import("@/lib/types").Candidate) {
    setHome({ detailCandidate: null, pickedRank: c.rank });
    if (!home.session) return;
    await api.accept({
      session_id: home.session.session_id,
      candidate_rank: c.rank,
      candidate: c,
    });
    await refreshInbox();
  }

  return (
    <>
      <NavBar />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/feedback" element={<FeedbackInbox />} />
        <Route path="/feedback/last" element={<FeedbackLastResolverPage />} />
        <Route path="/feedback/:id" element={<FeedbackPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>

      <DetailPanel
        candidate={home.detailCandidate}
        onClose={() => setHome({ detailCandidate: null })}
        onPick={onDetailPick}
      />
      <Toast msg={toast.msg} tone={toast.tone} />
    </>
  );
}

export default function App() {
  const vars = useMemo(() => themeVars(), []);
  return (
    <div style={{ ...vars, background: "var(--bg)", color: "var(--fg)", minHeight: "100vh" }}>
      <ChishaProvider>
        <Shell />
      </ChishaProvider>
    </div>
  );
}

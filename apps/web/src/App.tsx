import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { LABELS } from "@/lib/labels";
import { api, isMock } from "@/lib/api";
import { sandboxApi, type SandboxState } from "@/lib/sandbox";
import { ChishaProvider, useChisha } from "@/lib/useChishaState";

import { NavBar } from "@/components/NavBar";
import { SandboxBar } from "@/components/SandboxBar";
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
  // D-074 PR-1d: sandbox state 由 App 顶层管理, 启用时 SandboxBar 显示, 否则不渲染.
  // 仅当真实后端可用 (isMock=false) 才尝试拉 state, mock 模式不调.
  const [sandboxState, setSandboxState] = useState<SandboxState>({ enabled: false });

  const refreshSandbox = useCallback(async () => {
    if (isMock) return;
    try {
      const s = await sandboxApi.state();
      setSandboxState(s);
    } catch {
      setSandboxState({ enabled: false });
    }
  }, []);

  useEffect(() => {
    refreshSandbox();
  }, [refreshSandbox]);

  const onSandboxChange = useCallback(async () => {
    await refreshSandbox();
    // sandbox advance / reset 后, 清掉 HomePage 的 session 让用户重新推荐
    // (虚拟日变了, 旧推荐结果失效); inbox 也重拉.
    setHome({ session: null, pickedRank: null, detailCandidate: null,
              refineHistory: [], skipped: false, skipReason: null });
    await refreshInbox();
  }, [refreshSandbox, refreshInbox, setHome]);

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
      <SandboxBar state={sandboxState} onChange={onSandboxChange} />
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

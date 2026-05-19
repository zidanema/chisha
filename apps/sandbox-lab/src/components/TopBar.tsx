// D-088 S-02 TopBar.
// Session 下拉本任务静态展开/收起态; 切换/新建走 props stub (S-03 接 useSandbox).
import { useEffect, useRef, useState } from "react";
import type { Clock, SessionMeta } from "../types/sandbox";

export interface TopBarProps {
  sessions: SessionMeta[];
  activeSessionName: string;
  profile: string;
  seed: number;
  origin: string;
  clock: Clock;
  onOpenSummary?: () => void;
  onOpenTweaks?: () => void;
  onSelectSession?: (id: string) => void;
  onNewSession?: () => void;
}

export function TopBar({
  sessions,
  activeSessionName,
  profile,
  seed,
  origin,
  clock,
  onOpenSummary,
  onOpenTweaks,
  onSelectSession,
  onNewSession,
}: TopBarProps) {
  const [dropOpen, setDropOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setDropOpen(false);
    }
    if (dropOpen) document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [dropOpen]);

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true" />
        <span className="brand-meta">
          <span className="brand-title">Sandbox Lab</span>
          <span className="brand-sub">白盒时光机 · /sandbox-lab</span>
        </span>
      </div>

      <span className="topbar-divider" />

      <div className="session-anchor" ref={ref}>
        <button className="session-pick" onClick={() => setDropOpen((o) => !o)}>
          <span className="dot" />
          <span>Session:</span>
          <strong>{activeSessionName}</strong>
          <span className="chev">▾</span>
        </button>
        {dropOpen && (
          <div className="dropdown">
            <div className="dropdown-section-label">最近使用</div>
            {sessions.map((s) => (
              <div
                key={s.id}
                className={`dropdown-item ${s.name === activeSessionName ? "on" : ""} ${s.status === "done" ? "done" : ""}`}
                onClick={() => {
                  onSelectSession?.(s.id);
                  setDropOpen(false);
                }}
              >
                <span className="dot" />
                <span className="nm">{s.name}</span>
                <span className="meta">{s.lastUsed}</span>
              </div>
            ))}
            <div className="dropdown-divider" />
            <div
              className="dropdown-item dropdown-item-new"
              onClick={() => {
                onNewSession?.();
                setDropOpen(false);
              }}
            >
              <span className="new-plus">＋</span>
              <span className="nm new-label">新建 session</span>
            </div>
          </div>
        )}
      </div>

      <span className="meta-chip">
        <span className="k">策略</span>
        <span className="v">{profile}</span>
      </span>
      <span className="meta-chip">
        <span className="k">SEED</span>
        <span className="v">{seed}</span>
      </span>
      <span className="origin-tag">起点 · {origin}</span>

      <div className="topbar-grow" />

      <span className="clock-pill">
        <span className="dot" />
        <span>时钟</span>
        <span className="v">
          D{clock.day}
          {clock.slot}
        </span>
        <span className="prog mono">
          ({clock.idx}/{clock.total})
        </span>
      </span>

      <div className="topbar-actions">
        <button className="tbtn" onClick={onOpenSummary}>
          <span className="ico">📋</span> 摘要
        </button>
        {onOpenTweaks && (
          <button className="tbtn" onClick={onOpenTweaks} title="dev 工具">
            <span className="ico">⚙</span>
          </button>
        )}
      </div>
    </header>
  );
}

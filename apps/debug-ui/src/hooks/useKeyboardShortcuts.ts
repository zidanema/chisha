// Workflow A 全局快捷键. 在 App 顶层挂一次.
//   Cmd/Ctrl + K   → 打开 LookupDrawer
//   Cmd/Ctrl + /   → focus TraceBrowser 搜索框 ([data-tb-search])
//   1-9            → 切到 R{n} (若存在)
//   Esc            → 关 LookupDrawer (其它 drawer 自管)
//
// 注: 当焦点在 INPUT/TEXTAREA 时, 数字键不抢; Cmd+K/Cmd+/ 始终生效.

import { useEffect } from "react";

type Opts = {
  onOpenLookup: () => void;
  onCloseLookup: () => void;
  lookupOpen: boolean;
  rounds: { id: string }[];
  setActiveRound: (rid: string) => void;
};

export function useKeyboardShortcuts({
  onOpenLookup, onCloseLookup, lookupOpen, rounds, setActiveRound,
}: Opts) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const inEditable = !!target && (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      );

      const meta = e.metaKey || e.ctrlKey;

      if (meta && e.key === "k") {
        e.preventDefault();
        onOpenLookup();
        return;
      }
      if (meta && e.key === "/") {
        e.preventDefault();
        const el = document.querySelector<HTMLInputElement>("[data-tb-search]");
        if (el) { el.focus(); el.select(); }
        return;
      }
      if (e.key === "Escape" && lookupOpen) {
        e.preventDefault();
        onCloseLookup();
        return;
      }
      if (!inEditable && !meta && !e.altKey && !e.shiftKey) {
        if (/^[1-9]$/.test(e.key)) {
          const n = parseInt(e.key, 10);
          const target = `R${n}`;
          if (rounds.some((r) => r.id === target)) {
            e.preventDefault();
            setActiveRound(target);
          }
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onOpenLookup, onCloseLookup, lookupOpen, rounds, setActiveRound]);
}

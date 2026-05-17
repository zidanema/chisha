import { useEffect } from "react";

export type ShortcutCallbacks = {
  // D-079 cleanup: 砍掉 "首轮推荐" 后, Cmd+Enter / Cmd+R 全部映射到 Live 试跑.
  // 真实写盘走 apps/web /api/recommend.
  onRunLive: () => void;
  onRunRefine: () => void;
  isRunDisabled: () => boolean;
  hasRefineText: () => boolean;
};

// IME composition guard: ignore composing keystrokes so Chinese pinyin Enter
// doesn't accidentally fire Run.
function isComposing(e: KeyboardEvent): boolean {
  return e.isComposing || (e as KeyboardEvent & { keyCode?: number }).keyCode === 229;
}

function isInteractiveTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.isContentEditable
  );
}

function isInsideSidebar(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.closest(".sidebar") != null;
}

export function useKeyboardShortcuts({
  onRunLive,
  onRunRefine,
  isRunDisabled,
  hasRefineText,
}: ShortcutCallbacks): void {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isComposing(e)) return;

      const mod = e.metaKey || e.ctrlKey;

      // Cmd/Ctrl + Enter → Live 试跑.
      if (mod && e.key === "Enter") {
        if (!isInsideSidebar(e.target) && !isInteractiveTarget(e.target)) {
          // global Cmd+Enter outside any input: still trigger.
        }
        if (isRunDisabled()) return;
        e.preventDefault();
        onRunLive();
        return;
      }

      // Cmd/Ctrl + R: 拦截浏览器刷新. 有 refine 文本 → refine, 否则 → Live 试跑.
      // success/error toast 由 handleRunRefine + useSession.runRefine 内部已 fire.
      // Cmd+Shift+R 保留浏览器原生 force-reload escape hatch.
      if (mod && (e.key === "r" || e.key === "R") && !e.shiftKey && !e.altKey) {
        if (isRunDisabled()) return;
        e.preventDefault();
        if (hasRefineText()) {
          onRunRefine();
        } else {
          onRunLive();
        }
        return;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onRunLive, onRunRefine, isRunDisabled, hasRefineText]);
}

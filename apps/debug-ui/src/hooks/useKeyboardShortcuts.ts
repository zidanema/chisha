import { useEffect } from "react";

export type ShortcutCallbacks = {
  onRunMain: () => void;
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
  onRunMain,
  onRunRefine,
  isRunDisabled,
  hasRefineText,
}: ShortcutCallbacks): void {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isComposing(e)) return;

      const mod = e.metaKey || e.ctrlKey;

      // Cmd/Ctrl + Enter inside a sidebar textarea → trigger main run.
      if (mod && e.key === "Enter") {
        if (!isInsideSidebar(e.target) && !isInteractiveTarget(e.target)) {
          // global Cmd+Enter outside any input: still trigger.
        }
        if (isRunDisabled()) return;
        e.preventDefault();
        onRunMain();
        return;
      }

      // Cmd/Ctrl + R: intercept browser reload, run refine if text present
      // otherwise re-run main. Cmd+Shift+R is left untouched (escape hatch
      // to force-reload).
      if (mod && (e.key === "r" || e.key === "R") && !e.shiftKey && !e.altKey) {
        if (isRunDisabled()) return;
        e.preventDefault();
        if (hasRefineText()) {
          onRunRefine();
        } else {
          onRunMain();
        }
        return;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onRunMain, onRunRefine, isRunDisabled, hasRefineText]);
}

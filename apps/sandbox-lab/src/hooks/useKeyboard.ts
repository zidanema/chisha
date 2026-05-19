// S-03: 全局键盘处理. 当前仅 Esc 触发单层关闭 (priority: confirm > summary > refine > review).
// 修订 H: useRef 存最新 handler, useEffect deps 空, 避免 inline arrow 反复 attach/detach.

import { useEffect, useRef } from "react";


export interface UseKeyboardOptions {
  onEsc: () => void;
}


export function useKeyboard(opts: UseKeyboardOptions): void {
  const handlerRef = useRef(opts.onEsc);
  handlerRef.current = opts.onEsc;
  useEffect(() => {
    function h(e: KeyboardEvent) {
      if (e.key === "Escape") handlerRef.current();
    }
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);
}

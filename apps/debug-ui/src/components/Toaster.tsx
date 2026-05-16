import { useEffect, useState } from "react";

export type ToastKind = "ok" | "warn" | "error";

export type Toast = {
  id: string;
  kind: ToastKind;
  title: string;
  detail?: string;
};

let nextId = 0;
type Listener = (toasts: Toast[]) => void;
const listeners = new Set<Listener>();
let current: Toast[] = [];

function emit() {
  for (const l of listeners) l(current);
}

export function pushToast(t: Omit<Toast, "id">): string {
  const id = `t${++nextId}`;
  current = [...current, { ...t, id }];
  emit();
  return id;
}

export function dismissToast(id: string) {
  current = current.filter((t) => t.id !== id);
  emit();
}

export function Toaster() {
  const [toasts, setToasts] = useState<Toast[]>(current);
  useEffect(() => {
    listeners.add(setToasts);
    return () => {
      listeners.delete(setToasts);
    };
  }, []);
  useEffect(() => {
    if (toasts.length === 0) return;
    const timers = toasts.map((t) => {
      const ms = t.kind === "error" ? 6000 : 3000;
      return window.setTimeout(() => dismissToast(t.id), ms);
    });
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [toasts]);

  return (
    <div
      style={{
        position: "fixed",
        top: 60,
        right: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        zIndex: 1000,
        pointerEvents: "none",
      }}
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => dismissToast(t.id)}
          style={{
            pointerEvents: "auto",
            cursor: "pointer",
            minWidth: 260,
            maxWidth: 420,
            padding: "10px 14px",
            borderRadius: 4,
            background: "var(--bg-2)",
            border: `1px solid ${t.kind === "error" ? "var(--err-edge)" :
                                  t.kind === "warn" ? "var(--warn-edge)" :
                                  "var(--ok-edge)"}`,
            boxShadow: "0 6px 18px var(--shadow-pop)",
            color: "var(--t-0)",
            fontSize: 12,
            lineHeight: 1.5,
          }}
        >
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontWeight: 600,
            color: t.kind === "error" ? "var(--err)" :
                   t.kind === "warn" ? "var(--warn)" :
                   "var(--ok)",
          }}>
            <span>{t.kind === "error" ? "✗" : t.kind === "warn" ? "▲" : "✓"}</span>
            <span>{t.title}</span>
          </div>
          {t.detail && (
            <div style={{ marginTop: 4, color: "var(--t-2)", fontSize: 11 }}>
              {t.detail}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

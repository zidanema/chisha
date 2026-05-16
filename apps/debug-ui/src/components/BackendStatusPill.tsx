// Backend connection status pill shown in topbar. Reads useSession status.
// Extracted from App.tsx in Phase 7.

import type { RunStatus } from "../hooks/useSession";

export function BackendStatusPill({ status }: { status: RunStatus }) {
  const label =
    status === "loading" ? "running…" :
    status === "error" ? "error" :
    status === "offline" ? "offline · mock" :
    "live :8765";

  const color =
    status === "error" ? "var(--err)" :
    status === "offline" ? "var(--warn)" :
    undefined;

  const borderColor =
    status === "error" ? "var(--err-edge)" :
    status === "offline" ? "var(--warn-edge)" :
    undefined;

  return (
    <span className="pill live" style={{ color, borderColor }}>
      backend FastAPI · {label}
    </span>
  );
}

// Backend connection status pill shown in topbar. Reads useSession status.

import type { RunStatus } from "../hooks/useSession";

export function BackendStatusPill({ status }: { status: RunStatus }) {
  const label =
    status === "loading" ? "running…" :
    status === "error" ? "error" :
    status === "offline" ? "offline" :
    "live";

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

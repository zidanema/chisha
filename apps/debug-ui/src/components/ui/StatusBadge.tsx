import type { L3Status } from "../../types/trace";

type BadgeStatus = L3Status | "warn";

const STATUS_MAP: Record<BadgeStatus, { cls: string; text: string }> = {
  ok: { cls: "green", text: "OK" },
  fallback: { cls: "red", text: "FALLBACK" },
  config_error: { cls: "orange", text: "CONFIG_ERROR" },
  skipped: { cls: "gray", text: "SKIPPED" },
  // D-089-S5b: round 没存 L3 切片时的兜底 (不是业务 skipped, 是 data 缺失).
  no_data: { cls: "gray", text: "NO_DATA" },
  warn: { cls: "orange", text: "WARN" },
};

export function StatusBadge({
  status,
  size = "md",
}: {
  status: BadgeStatus;
  size?: "md" | "lg" | "xl";
}) {
  const m = STATUS_MAP[status] ?? STATUS_MAP.skipped;
  const sizeCls = size === "xl" ? "xl" : size === "lg" ? "lg" : "";
  return (
    <span className={`badge ${m.cls} ${sizeCls}`.trim()}>
      <span className="dot"></span>
      {m.text}
    </span>
  );
}

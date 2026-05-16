import type { ReactNode } from "react";

export type PillTone =
  | "gray"
  | "green"
  | "red"
  | "orange"
  | "blue"
  | "violet";

export function Pill({
  children,
  tone = "gray",
}: {
  children: ReactNode;
  tone?: PillTone;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

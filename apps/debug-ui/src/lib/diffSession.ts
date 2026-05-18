// Per-combo / per-final diff helpers, consumed by L2ComboTable + PanelFinal.
// Phase 0 瘦身: 砍掉 Session-level computeSessionDiff (旧 refine tab 专用,
// Workflow A round 比较走 trace.rounds[i].diff 后端给的 in/out/up/down 摘要,
// 加上前端按需算 combo 集合差). 仅保留 panel 组件还在 import 的 type + badge formatter.

export type ComboDiffKind = "NEW" | "DROPPED" | "UP" | "DOWN" | "SAME";

export type ComboDiff = {
  combo_id: string;
  kind: ComboDiffKind;
  firstRank: number | null;   // null = NEW
  secondRank: number | null;  // null = DROPPED
  delta: number;              // secondRank - firstRank; +ve = ranked worse
};

export type FinalDiffKind = "new" | "kept" | "dropped";

// User-facing badge formatting. abs() guards against "↑ -N" / "↓ -N" footguns.
export function comboDiffBadge(d: ComboDiff): { text: string; tone: "green" | "red" | "blue" | "orange" } | null {
  switch (d.kind) {
    case "NEW":     return { text: "+ NEW", tone: "green" };
    case "DROPPED": return { text: "− DROPPED", tone: "red" };
    case "UP":      return { text: `↑ ${Math.abs(d.delta)}`, tone: "blue" };
    case "DOWN":    return { text: `↓ ${Math.abs(d.delta)}`, tone: "orange" };
    case "SAME":    return null;
  }
}

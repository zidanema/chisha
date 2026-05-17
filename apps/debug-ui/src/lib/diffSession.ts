// Pure functions that compare two sessions and emit diff metadata for
// PanelL2 combo-table badges and PanelFinal tri-state coloring.

import type { FinalRow, L2Combo, Session } from "../types/trace";

export type ComboDiffKind = "NEW" | "DROPPED" | "UP" | "DOWN" | "SAME";

export type ComboDiff = {
  combo_id: string;
  kind: ComboDiffKind;
  firstRank: number | null;   // null = NEW
  secondRank: number | null;  // null = DROPPED
  delta: number;              // secondRank - firstRank; +ve = ranked worse
};

export type FinalDiffKind = "new" | "kept" | "dropped";

export type SessionDiff = {
  // Union of all combo_ids present in either session. Key = combo_id.
  combos: Map<string, ComboDiff>;
  // Map of FinalRow.combo_id → tri-state. Includes BOTH second-round entries
  // (new/kept) AND first-round entries that got dropped (dropped) so PanelFinal
  // can render them as ghost cards.
  final: Map<string, FinalDiffKind>;
  // First-round final rows that didn't survive to the second round —
  // PanelFinal renders these inline (half-transparent) for the "踢出 −" state.
  droppedFinals: FinalRow[];
};

function indexByCombo<T extends { combo_id: string }>(rows: T[]): Map<string, T> {
  const m = new Map<string, T>();
  for (const r of rows) m.set(r.combo_id, r);
  return m;
}

export function computeSessionDiff(first: Session, second: Session): SessionDiff {
  const combos = new Map<string, ComboDiff>();

  const firstIdx = indexByCombo<L2Combo>(first.l2.combos);
  const secondIdx = indexByCombo<L2Combo>(second.l2.combos);

  // O(n + m): one pass per side.
  for (const [id, fc] of firstIdx) {
    const sc = secondIdx.get(id);
    if (!sc) {
      combos.set(id, {
        combo_id: id, kind: "DROPPED",
        firstRank: fc.rank, secondRank: null, delta: 0,
      });
    } else {
      const delta = sc.rank - fc.rank;
      const kind: ComboDiffKind = delta === 0 ? "SAME" : delta < 0 ? "UP" : "DOWN";
      combos.set(id, {
        combo_id: id, kind,
        firstRank: fc.rank, secondRank: sc.rank, delta,
      });
    }
  }
  for (const [id, sc] of secondIdx) {
    if (!combos.has(id)) {
      combos.set(id, {
        combo_id: id, kind: "NEW",
        firstRank: null, secondRank: sc.rank, delta: 0,
      });
    }
  }

  // Final tri-state.
  const finalDiff = new Map<string, FinalDiffKind>();
  const firstFinalIds = new Set(first.final.map((c) => c.combo_id));
  const secondFinalIds = new Set(second.final.map((c) => c.combo_id));
  for (const id of secondFinalIds) {
    finalDiff.set(id, firstFinalIds.has(id) ? "kept" : "new");
  }
  const droppedFinals: FinalRow[] = [];
  for (const fr of first.final) {
    if (!secondFinalIds.has(fr.combo_id)) {
      finalDiff.set(fr.combo_id, "dropped");
      droppedFinals.push(fr);
    }
  }

  return { combos, final: finalDiff, droppedFinals };
}

// D-082: round1 (session.l1/l2/l3/final) vs round2 (session.round2.*). 没 round2
// 返 null, 调用方走"等待触发 refine"分支.
export function computeRefineDiff(session: Session): SessionDiff | null {
  if (!session.round2) return null;
  // 复用 computeSessionDiff: 把 round2 包成 Session-shape (其它字段不用, 给空值
  // 占位; computeSessionDiff 只读 l2.combos 与 final).
  const round2AsSession: Session = {
    ...session,
    started_at: session.round2.started_at,
    total_latency_ms: session.round2.total_latency_ms,
    ctx_latency_ms: session.round2.ctx_latency_ms,
    final_latency_ms: session.round2.final_latency_ms,
    l1: session.round2.l1,
    l2: session.round2.l2,
    l3: session.round2.l3,
    final: session.round2.final,
    round2: undefined,
  };
  return computeSessionDiff(session, round2AsSession);
}

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

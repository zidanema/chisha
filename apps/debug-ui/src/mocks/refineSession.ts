// Phase 3 mock: derive a second-round Session from the first by applying
// a refine-text-seeded perturbation. Phase 4+ replaces this with a real
// /api/debug_refine response.

import type { FinalRow, L2Combo, Session } from "../types/trace";

// Cheap, deterministic 32-bit hash → seed. Same refine text → same second round
// (so diff badges don't shimmer between renders).
function hashSeed(s: string, base = 43): number {
  let h = base;
  for (let i = 0; i < s.length; i++) {
    h = ((h * 31) ^ s.charCodeAt(i)) | 0;
  }
  // Make sure the LCG seed is positive.
  return Math.abs(h) || base;
}

function makeRand(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

// Apply a chip-style bias to a combo's total_score. The bias mimics what
// taste_hints + want_soup mood would do to real L2 scoring.
function applyBias(c: L2Combo, refineText: string, rand: () => number): L2Combo {
  let bias = 0;
  // Mock heuristic: text contains soup/wet words → boost wet/soup combos
  if (/(汤|喝汤|soup|wet)/i.test(refineText)) {
    if (c.dishes.some((d) => d.wetness === "wet" || d.cook === "soup")) bias += 0.25;
  }
  // text contains avoid keywords → penalise matching dishes
  if (/(别给我面|不要面|no.*noodle)/i.test(refineText)) {
    if (c.dishes.some((d) => d.main === "noodle" || d.grain === "wheat")) bias -= 0.30;
  }
  if (/(西少爷|肉夹馍)/.test(refineText)) {
    if (c.restaurant.includes("西少爷") || c.restaurant.includes("肉夹馍")) bias -= 1.0;
  }
  // Plus a tiny random jitter so identical text doesn't yield exact same order.
  bias += (rand() - 0.5) * 0.04;
  return {
    ...c,
    total_score: Math.round((c.total_score + bias) * 1000) / 1000,
  };
}

function pickFinalFromCombos(combos: L2Combo[], firstFinal: FinalRow[]): FinalRow[] {
  // Re-rerank top 5 from second-round L2: 3 exploit (top-3) + 2 explore
  // (chosen from rank 6-15 to keep things interesting).
  const exploits = combos.slice(0, 3);
  const explores = combos.slice(5, 15).filter((_c, i) => i % 4 === 0).slice(0, 2);
  const chosen = [...exploits, ...explores];

  // Inherit health_flags / risk_flags shape from the matching first-round final
  // when available; otherwise synthesise reasonable defaults.
  const firstByCombo = new Map(firstFinal.map((f) => [f.combo_id, f]));

  return chosen.map((c, i) => {
    const inherit = firstByCombo.get(c.combo_id);
    return {
      rank: i + 1,
      kind: i < 3 ? "exploit" as const : "explore" as const,
      combo_id: c.combo_id,
      restaurant: c.restaurant,
      distance_km: c.distance_km,
      eta_min: c.eta_min,
      total_price: c.total_price,
      score: c.total_score,
      fit_score: c.fit_score,
      dishes: c.dishes.map((d) => ({ name: d.name, price: d.price })),
      health_flags: inherit?.health_flags ?? {
        veg_ok: c.dishes.some((d) => d.main.includes("leaf") || d.main === "leaf"),
        protein_ok: c.dishes.some((d) => d.protein_g >= 20),
        oil_ok: c.dishes.every((d) => d.oil !== "high"),
        wetness_ok: c.dishes.some((d) => d.wetness === "wet"),
        processed_meat: c.dishes.some((d) => d.main.includes("加工")),
        sweet_sauce: c.dishes.some((d) => d.sweet === "high"),
      },
      risk_flags: inherit?.risk_flags ?? [],
      reason: inherit?.reason ?? `refine 调整后 ${c.restaurant} 升至 #${i + 1}`,
    };
  });
}

export function deriveRefineSession(first: Session, refineText: string): Session {
  const seed = hashSeed(refineText || "default");
  const rand = makeRand(seed);

  // Apply bias + re-sort L2 combos. Reassign ranks based on new order.
  const biased = first.l2.combos.map((c) => applyBias(c, refineText, rand))
    .sort((a, b) => b.total_score - a.total_score)
    .map((c, i) => ({ ...c, rank: i + 1 }));

  const newFinal = pickFinalFromCombos(biased, first.final);

  const refineSessionId = `${first.session_id}_r1`;

  return {
    ...first,
    session_id: refineSessionId,
    started_at: new Date().toISOString(),
    total_latency_ms: 2310,
    // L1 不动 — refine 不重新召回。
    l2: {
      ...first.l2,
      combos: biased,
      latency_ms: 36,
    },
    // L3 模拟 refine 调用: 同 model, 更少 candidates (refine=true 时 n_explore=0).
    l3: {
      ...first.l3,
      latency_ms: 1820,
      candidates_returned: newFinal.length,
      user_message: `${first.l3.user_message}\n\n# REFINE round 2 · user_input:\n${refineText}`,
    },
    final: newFinal,
    refine: {
      ...first.refine,
      user_text: refineText,
      refine_session: refineSessionId,
    },
  };
}

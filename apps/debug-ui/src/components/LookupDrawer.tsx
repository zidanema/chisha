// LookupDrawer — Phase 3 在当前 trace+round 内存反查 (零后端调用).
// 入口: 顶栏 / TraceBrowser / Cmd+K.  仅在 currentRound 提供时可反查;
// 否则按钮禁用 + 提示 "等待 round 数据加载".
//
// 反查策略 (按 stage 顺序判定, 找到第一个就 break):
//   restaurant_bans  → L1 hard_filter (反查终止, 命中后不再往下找)
//   l1.top_restaurants 命中但 l2.combos 不含 → L2 dropped (cap / 多样性 / 价格被过滤)
//   l2.combos                                  → L2 (top60)
//   final                                      → Final 入选 (rank N)
//   全没命中                                    → unknown (可能 L1 召回阶段就过滤掉)
//
// 菜名走 contains 模糊匹配 (空格分隔多个); 餐厅名 contains 模糊匹配.

import { useMemo, useState } from "react";
import type { L2Combo, RoundRecord } from "../types/trace";

type Props = {
  open: boolean;
  onClose: () => void;
  currentRound: RoundRecord | null;
  currentRoundId: string;
};

type StageHit =
  | { stage: "l1_banned"; label: string; detail: string }
  | { stage: "l2_dropped"; label: string; detail: string }
  | { stage: "l2_top60"; label: string; detail: string; combos: L2Combo[] }
  | { stage: "final"; label: string; detail: string; rank: number };

type RestResult = {
  rest: string;
  hits: StageHit[];          // 当前 stage 列表 (按上述顺序判定后取 first match)
  combosInL2: L2Combo[];     // 该餐厅在 L2 top60 中的所有 combo
  finalRanks: number[];      // 该餐厅在 final 中的所有名次
};

type DishHit = {
  query: string;             // 用户输入的菜名 (原文)
  occurrences: {
    stage: "l2_top60" | "final";
    rest: string;
    combo_id: string;
    rank: number | null;     // final 才有
    full_dish_name: string;  // 匹配到的完整菜名
  }[];
};

function normalize(s: string): string {
  return s.trim().toLowerCase();
}

function fuzzyMatch(text: string, query: string): boolean {
  return normalize(text).includes(normalize(query));
}

function lookupRestaurants(round: RoundRecord, query: string): RestResult[] {
  const q = normalize(query);
  if (!q) return [];

  // 收集所有出现过的餐厅名 (去重)
  const restSet = new Set<string>();
  for (const b of round.l1.restaurant_bans ?? []) {
    if (fuzzyMatch(b.rest, q)) restSet.add(b.rest);
  }
  for (const r of round.l1.top_restaurants ?? []) {
    if (fuzzyMatch(r.name, q)) restSet.add(r.name);
  }
  for (const c of round.l2.combos ?? []) {
    if (fuzzyMatch(c.restaurant, q)) restSet.add(c.restaurant);
  }
  for (const f of round.final ?? []) {
    if (fuzzyMatch(f.restaurant, q)) restSet.add(f.restaurant);
  }

  const results: RestResult[] = [];
  for (const rest of restSet) {
    const ban = (round.l1.restaurant_bans ?? []).find((b) => b.rest === rest);
    const inL1 = (round.l1.top_restaurants ?? []).find((r) => r.name === rest);
    const combos = (round.l2.combos ?? []).filter((c) => c.restaurant === rest);
    const finalRows = (round.final ?? []).filter((f) => f.restaurant === rest);

    const hits: StageHit[] = [];

    if (ban) {
      hits.push({
        stage: "l1_banned",
        label: "L1 hard_filter",
        detail: `${ban.reason} · ${ban.detail} (×${ban.count})`,
      });
    } else if (inL1 && combos.length === 0) {
      hits.push({
        stage: "l2_dropped",
        label: "L2 dropped",
        detail: `L1 通过 ${inL1.combos} combo, 但未进 L2 top60 (cap / 多样性 / 价格)`,
      });
    }
    if (combos.length > 0) {
      hits.push({
        stage: "l2_top60",
        label: "L2 top60",
        detail: `${combos.length} combo · top score ${combos[0].total_score.toFixed(3)}`,
        combos,
      });
    }
    for (const f of finalRows) {
      hits.push({
        stage: "final",
        label: `Final #${f.rank}`,
        detail: `${f.kind} · ¥${f.total_price} · ${f.eta_min}min · ${f.dishes.map((d) => d.name).join(" + ")}`,
        rank: f.rank,
      });
    }
    if (hits.length === 0) {
      // 餐厅名匹配上了某个 stage 但所有 stage 都没找到记录 (理论不会到这里)
      // 继续兜底显示空, 用户能看到 "未命中"
    }
    results.push({
      rest,
      hits,
      combosInL2: combos,
      finalRanks: finalRows.map((f) => f.rank),
    });
  }
  results.sort((a, b) => a.rest.localeCompare(b.rest));
  return results;
}

function lookupDishes(round: RoundRecord, queries: string[]): DishHit[] {
  const cleaned = queries.map((s) => s.trim()).filter(Boolean);
  if (cleaned.length === 0) return [];

  const hits: DishHit[] = cleaned.map((q) => ({ query: q, occurrences: [] }));

  // 扫 L2 combos
  for (const combo of round.l2.combos ?? []) {
    for (const dish of combo.dishes ?? []) {
      hits.forEach((h) => {
        if (fuzzyMatch(dish.name, h.query)) {
          h.occurrences.push({
            stage: "l2_top60",
            rest: combo.restaurant,
            combo_id: combo.combo_id,
            rank: null,
            full_dish_name: dish.name,
          });
        }
      });
    }
  }
  // 扫 Final
  for (const f of round.final ?? []) {
    for (const dish of f.dishes ?? []) {
      hits.forEach((h) => {
        if (fuzzyMatch(dish.name, h.query)) {
          h.occurrences.push({
            stage: "final",
            rest: f.restaurant,
            combo_id: f.combo_id,
            rank: f.rank,
            full_dish_name: dish.name,
          });
        }
      });
    }
  }
  return hits;
}

function stageBadgeClass(stage: string): string {
  switch (stage) {
    case "l1_banned": return "ich avoid";       // 红色调
    case "l2_dropped": return "ich avoid";
    case "l2_top60": return "ich neutral";
    case "final": return "ich want";            // 绿色调
    default: return "ich neutral";
  }
}

export function LookupDrawer({ open, onClose, currentRound, currentRoundId }: Props) {
  const [rest, setRest] = useState("");
  const [dish, setDish] = useState("");
  const [ran, setRan] = useState(false);

  const restResults = useMemo(
    () => (ran && currentRound ? lookupRestaurants(currentRound, rest) : []),
    [ran, currentRound, rest],
  );
  const dishResults = useMemo(
    () => (ran && currentRound ? lookupDishes(currentRound, dish.split(/\s+/)) : []),
    [ran, currentRound, dish],
  );

  if (!open) return null;

  const disabled = !currentRound || (!rest.trim() && !dish.trim());

  return (
    <>
      <div className="lookup-scrim" onClick={onClose}></div>
      <div className="lookup-drawer">
        <div className="lookup-head">
          <h3>追溯命中</h3>
          <span className="sub">/在 {currentRoundId || "current round"} 内反查</span>
          <button className="close" onClick={onClose}>关闭 ✕</button>
        </div>
        <div className="lookup-body">
          {currentRound?.__partial && (
            <div className="lookup-empty" style={{ borderColor: "var(--warn-edge)", color: "var(--warn)" }}>
              ⚠ 当前 round 的 L1/L2/L3 切片后端未持久化 (refine_session 未暴露).
              反查跑在 mock 数据上, 结果仅供 UI 演示, 不可信.
            </div>
          )}
          <div>
            <label className="field-label">
              餐厅名 <span className="dim">(模糊)</span>
            </label>
            <input
              className="input"
              value={rest}
              onChange={(e) => { setRest(e.target.value); setRan(false); }}
              placeholder="太二酸菜鱼"
              onKeyDown={(e) => { if (e.key === "Enter" && !disabled) setRan(true); }}
            />
          </div>
          <div>
            <label className="field-label">
              菜名 <span className="dim">(空格分隔多个, 任一命中即返回)</span>
            </label>
            <input
              className="input"
              value={dish}
              onChange={(e) => { setDish(e.target.value); setRan(false); }}
              placeholder="酸菜鱼 米饭"
              onKeyDown={(e) => { if (e.key === "Enter" && !disabled) setRan(true); }}
            />
          </div>
          <div className="btn-row">
            <button className="btn" disabled={disabled} onClick={() => setRan(true)}>
              {currentRound
                ? `⌕ 在 ${currentRoundId} 反查`
                : "⌕ 等待 round 数据加载..."}
            </button>
          </div>

          {ran && rest.trim() && (
            <div className="lookup-section">
              <div className="lookup-section-head">
                餐厅命中 · {restResults.length} 条
              </div>
              {restResults.length === 0 ? (
                <div className="lookup-empty">
                  未命中. 可能 L1 召回阶段就过滤 (zone / meal / 距离 / 营业状态);
                  此 round trace 不含完整召回明细, 需后端 inspect_candidates 验证.
                </div>
              ) : (
                <div className="lookup-rows">
                  {restResults.map((r) => (
                    <div className="lookup-row" key={r.rest}>
                      <div className="rest-name">{r.rest}</div>
                      <div className="hits">
                        {r.hits.length === 0 ? (
                          <span className="ich neutral">unknown</span>
                        ) : (
                          r.hits.map((h, i) => (
                            <div className="hit-line" key={i}>
                              <span className={stageBadgeClass(h.stage)}>{h.label}</span>
                              <span className="hit-detail">{h.detail}</span>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {ran && dish.trim() && (
            <div className="lookup-section">
              <div className="lookup-section-head">
                菜命中 · {dishResults.reduce((s, d) => s + d.occurrences.length, 0)} 次
              </div>
              {dishResults.map((d) => (
                <div className="lookup-row" key={d.query}>
                  <div className="rest-name">"{d.query}"</div>
                  <div className="hits">
                    {d.occurrences.length === 0 ? (
                      <span className="ich neutral">L2/Final 未命中</span>
                    ) : (
                      d.occurrences.map((o, i) => (
                        <div className="hit-line" key={i}>
                          <span className={stageBadgeClass(o.stage)}>
                            {o.stage === "final" ? `Final #${o.rank}` : "L2"}
                          </span>
                          <span className="hit-detail">
                            {o.rest} · {o.combo_id} · 匹配: {o.full_dish_name}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--t-3)", lineHeight: 1.6 }}>
            • 抽屉只反查当前已选 trace+round, 不调后端
            <br />
            • stage 命中按 L1_banned → L2_dropped → L2_top60 → Final 顺序判定
            <br />
            • Cmd+K / ⌕ 入口都打开此抽屉; 关闭返回当前 trace
          </div>
        </div>
      </div>
    </>
  );
}

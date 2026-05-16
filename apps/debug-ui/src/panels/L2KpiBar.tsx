import type { L2Trace } from "../types/trace";

export function L2KpiBar({ l2 }: { l2: L2Trace }) {
  const kpi = l2.kpi;
  const totalCombosBefore = l2.combos_before_l2.toLocaleString();
  return (
    <div className="kpi-strip">
      <div className="kpi">
        <div className="lbl">Score range</div>
        <div className="val">{kpi.score_min} → {kpi.score_max}</div>
      </div>
      <div className="kpi">
        <div className="lbl">cap K</div>
        <div className="val">{kpi.cap_k}</div>
        <div className="delta">
          brand_top_k <span className="arrow">·</span> {kpi.per_brand_top_k}
        </div>
      </div>
      <div className="kpi">
        <div className="lbl">per_restaurant_cap_k</div>
        <div className="val">{kpi.per_restaurant_cap_k}</div>
      </div>
      <div className="kpi">
        <div className="lbl">top60 涉及餐厅数</div>
        <div className="val">{kpi.restaurants_after_cap}</div>
        <div className="delta">
          cap 前 {kpi.restaurants_before_cap} <span className="arrow">→</span> 后 {kpi.restaurants_after_cap}
        </div>
      </div>
      <div className="kpi">
        <div className="lbl">单店最多 combo</div>
        <div className="val">{kpi.max_combos_one_rest_after}</div>
        <div className="delta">
          cap 前 {kpi.max_combos_one_rest_before} <span className="arrow">→</span> 后 {kpi.max_combos_one_rest_after}
        </div>
      </div>
      <div className="kpi">
        <div className="lbl">送 L3 candidates</div>
        <div className="val">{l2.candidates_to_l3}</div>
        <div className="delta">从 {totalCombosBefore} combo 中</div>
      </div>
    </div>
  );
}

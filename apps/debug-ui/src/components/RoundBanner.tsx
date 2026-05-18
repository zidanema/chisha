// RoundBanner + PanelRoundStrip — connects timeline → panels.
// 1:1 port chisha-debug/project/wa-detail.jsx; deltas synthesized from round.diff.

import type { ReactNode } from "react";
import type { RoundRecord } from "../types/trace";

type LayerKey = "l1" | "l2" | "l3" | "final";

const LAYER_LABEL: Record<LayerKey, string> = {
  l1: "L1 召回", l2: "L2 打分", l3: "L3 LLM", final: "Final",
};

// 把 round 的运行数据 + diff 合成 per-layer 人话摘要 (per round, per layer).
function buildLayerDelta(round: RoundRecord, layer: LayerKey): ReactNode {
  const isR1 = round.id === "R1";
  const d = round.diff;
  const k = round.kpi;
  if (isR1) {
    switch (layer) {
      case "l1": return <>raw {(round.l1.raw_dishes / 1000).toFixed(0)}k → <span className="neu">{k.combos.toLocaleString()} combos</span> · {round.l1.restaurant_bans.length} 餐厅被 ban</>;
      case "l2": return <>L2 V2 打分 · top1 <span className="neu">{k.top1}</span> · {round.l2.kpi.restaurants_before_cap} → {round.l2.kpi.restaurants_after_cap} 餐厅 (cap K={round.l2.kpi.cap_k})</>;
      case "l3": return <>{round.l3.model} · {round.l3.latency_ms}ms · cache {round.l3.input_tokens ? Math.round((round.l3.cache_read_input_tokens / round.l3.input_tokens) * 100) : 0}% · {round.final.length} picks</>;
      case "final": return <>top1 <span className="neu">{k.top1}</span> · ¥{round.final[0]?.total_price ?? "—"} · {round.final[0]?.eta_min ?? "—"} min</>;
    }
  }
  // R2+ — 含 diff 摘要
  switch (layer) {
    case "l1": return <>combos <span className="neu">{k.combos.toLocaleString()}</span> · ban 累计 {round.l1.restaurant_bans.length} 家</>;
    case "l2": return <>top1 <span className="neu">{k.top1}</span> · <span className="up">+{d?.up ?? 0} 上移</span> / <span className="down">−{d?.down ?? 0} 下移</span></>;
    case "l3": return <>{round.l3.model} · {round.l3.latency_ms}ms · {round.user_input ? `提示 "${round.user_input.slice(0, 16)}…"` : ""}</>;
    case "final": return <><span className="up">+{d?.in ?? 0} 新进</span> · <span className="down">−{d?.out ?? 0} 踢出</span></>;
  }
}

type BannerProps = {
  targetRound: RoundRecord;
  baseRound: RoundRecord | null;
};

export function RoundBanner({ targetRound, baseRound }: BannerProps) {
  const isR1 = targetRound.id === "R1";
  const showVs = !isR1 && baseRound && baseRound.id !== targetRound.id;
  return (
    <div className={`round-banner ${isR1 ? "r1" : ""}`}>
      <div className="round-banner-head">
        <span className="arrow-down">▼</span>
        <span className="lbl">{targetRound.id} pipeline</span>
        <span className="copy">
          下方 4 个 panel 显示 <strong>{targetRound.id} · {targetRound.label}</strong> 的完整 pipeline
          {showVs && baseRound && (
            <> · 每个 panel 顶部带 Δ vs <strong>{baseRound.id} · {baseRound.label}</strong></>
          )}
        </span>
        {showVs && baseRound && (
          <span className="vs">
            <span className="b">{baseRound.id}</span> → <span className="t">{targetRound.id}</span>
          </span>
        )}
      </div>
      <div className="round-banner-deltas">
        {(["l1", "l2", "l3", "final"] as LayerKey[]).map((k) => (
          <div key={k} className={`d ${k === "final" ? "fin" : k}`}>
            <span className="lay">{LAYER_LABEL[k]}</span>
            <span className="delta">{buildLayerDelta(targetRound, k)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

type StripProps = {
  layer: LayerKey;
  targetRound: RoundRecord;
  baseRound: RoundRecord | null;
};

export function PanelRoundStrip({ layer, targetRound, baseRound }: StripProps) {
  const isR1 = targetRound.id === "R1";
  const showVs = !isR1 && baseRound && baseRound.id !== targetRound.id;
  return (
    <div className={`panel-round-strip ${isR1 ? "r1" : ""}`}>
      <span className={`layer-tag ${layer}`}>{LAYER_LABEL[layer]} · {targetRound.id}</span>
      <span className="delta">{buildLayerDelta(targetRound, layer)}</span>
      {showVs && baseRound && (
        <span className="vs">
          Δ vs <span className="b">{baseRound.id}</span> → <span className="t">{targetRound.id}</span>
        </span>
      )}
    </div>
  );
}

import { CopyBtn } from "../components/ui/CopyBtn";
import { Pill } from "../components/ui/Pill";
import type { L2Trace } from "../types/trace";
import { L2KpiBar } from "./L2KpiBar";
import { L2Heatmap } from "./L2Heatmap";
import { L2ComboTable } from "./L2ComboTable";

export function PanelL2({
  l2,
}: {
  l2: L2Trace;
}) {
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="layer-tag layer-l2">L2</span>
        <h2>打分 · score V2</h2>
        <span className="subtitle">
          {l2.weights.length} 维加权 + 4 层 cap · top{l2.candidates_to_l3} → L3
        </span>
        <div className="right">
          <Pill tone="gray">latency <span className="mono">{l2.latency_ms}ms</span></Pill>
          <CopyBtn label={`export top${l2.candidates_to_l3}`} />
        </div>
      </div>
      <div className="panel-body">
        <L2KpiBar l2={l2} />
        <L2Heatmap weights={l2.weights} combos={l2.combos} />
        <L2ComboTable combos={l2.combos} />
      </div>
    </div>
  );
}

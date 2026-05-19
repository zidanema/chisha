// D-088 S-02 RightCol: 右栏容器, 4 panel D→B→A→C 顺序.
import type { Decision } from "../types/sandbox";
import * as MOCK from "../mocks/sbxMocks";
import { APanel } from "./panels/APanel";
import { BPanel } from "./panels/BPanel";
import { CPanel } from "./panels/CPanel";
import { DPanel, type DPanelDensity } from "./panels/DPanel";

export interface RightColProps {
  decision: Decision;
  density: DPanelDensity;
  onDensityChange: (d: DPanelDensity) => void;
  onOpenTrace?: () => void;
}

export function RightCol({
  decision,
  density,
  onDensityChange,
  onOpenTrace,
}: RightColProps) {
  return (
    <div className="col col-right">
      <div className="col-head">
        <div className="h-title">系统状态 · 白盒</div>
        <div className="h-sub">D 优先 · 不可隐藏</div>
      </div>

      <DPanel
        decision={decision}
        density={density}
        onDensityChange={onDensityChange}
        onOpenTrace={onOpenTrace}
      />
      <BPanel activeRefines={MOCK.ACTIVE_RULES} blacklist={MOCK.BLACKLIST} />
      <APanel taste={MOCK.TASTE} keywords={MOCK.KEYWORDS} />
      <CPanel recent={MOCK.RECENT} fatigue={MOCK.FATIGUE} />
    </div>
  );
}

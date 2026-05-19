// D-093 S-02 TweaksPanel: 简化版 dev-only 浮层 (5 控件).
// 不引入原型的 host protocol (parent postMessage).
import type { Accent, Tweaks } from "../types/sandbox";
import { ACCENTS } from "../hooks/useTweaks";

export interface TweaksPanelProps {
  open: boolean;
  onClose: () => void;
  tweaks: Tweaks;
  setTweak: <K extends keyof Tweaks>(k: K, v: Tweaks[K]) => void;
}

export function TweaksPanel({
  open,
  onClose,
  tweaks,
  setTweak,
}: TweaksPanelProps) {
  if (!open) return null;
  return (
    <div className="sbx-tweaks">
      <header className="sbx-tweaks-hd">
        <strong>Tweaks · Sandbox Lab</strong>
        <button className="sbx-tweaks-x" onClick={onClose} aria-label="关闭">
          ✕
        </button>
      </header>
      <div className="sbx-tweaks-body">
        <Section label="时间轴" />
        <Segmented
          label="形态"
          value={tweaks.timelineVariant}
          options={[
            { value: "bars", label: "横向条" },
            { value: "calendar", label: "日历卡" },
          ]}
          onChange={(v) => setTweak("timelineVariant", v)}
        />

        <Section label="右栏" />
        <Segmented
          label="密度"
          value={tweaks.rightDensity}
          options={[
            { value: 0, label: "紧凑" },
            { value: 1, label: "标准" },
          ]}
          onChange={(v) => setTweak("rightDensity", v)}
        />
        <Toggle
          label="显示 L1/L2/L3 调试层"
          value={tweaks.showDebugLayer}
          onChange={(v) => setTweak("showDebugLayer", v)}
        />

        <Section label="视觉" />
        <ColorSwatches
          label="主色"
          value={tweaks.accent}
          options={ACCENTS}
          onChange={(v) => setTweak("accent", v)}
        />
        <Segmented
          label="主题"
          value={tweaks.theme}
          options={[
            { value: "light", label: "浅色" },
            { value: "dark", label: "深色" },
          ]}
          onChange={(v) => setTweak("theme", v)}
        />
      </div>
    </div>
  );
}

function Section({ label }: { label: string }) {
  return <div className="sbx-tweaks-section">{label}</div>;
}

function Segmented<V extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: V;
  options: { value: V; label: string }[];
  onChange: (v: V) => void;
}) {
  return (
    <div className="sbx-tweaks-row sbx-tweaks-row-h">
      <span className="sbx-tweaks-lbl">{label}</span>
      <div className="sbx-tweaks-seg">
        {options.map((o) => (
          <button
            key={String(o.value)}
            className={value === o.value ? "on" : ""}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="sbx-tweaks-row sbx-tweaks-row-h">
      <span className="sbx-tweaks-lbl">{label}</span>
      <button
        className="sbx-tweaks-toggle"
        data-on={value ? "1" : "0"}
        onClick={() => onChange(!value)}
        aria-pressed={value}
      >
        <i />
      </button>
    </div>
  );
}

function ColorSwatches({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: Accent;
  options: readonly Accent[];
  onChange: (v: Accent) => void;
}) {
  return (
    <div className="sbx-tweaks-row sbx-tweaks-row-h">
      <span className="sbx-tweaks-lbl">{label}</span>
      <div className="sbx-tweaks-swatches">
        {options.map((c) => (
          <button
            key={c}
            data-accent={c}
            className={`swatch ${value === c ? "on" : ""}`}
            onClick={() => onChange(c)}
            aria-label={`accent ${c}`}
          />
        ))}
      </div>
    </div>
  );
}

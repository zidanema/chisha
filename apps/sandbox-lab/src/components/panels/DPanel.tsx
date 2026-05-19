// D-093 S-02 DPanel: 上顿决策因果链 (沙箱独有 hero panel).
// 紧凑/标准/详细 3 档密度, 三段固定结构 (动作摘要 / 状态 diff / 下顿影响).
// onDensityChange prop 驱动密度切换 (Codex hidden gotcha #6: 不用 window 全局).
import type { Decision, DiffEntry, Implication } from "../../types/sandbox";

export type DPanelDensity = 0 | 1 | 2;

export interface DPanelProps {
  decision: Decision;
  density: DPanelDensity;
  onDensityChange: (d: DPanelDensity) => void;
  onOpenTrace?: () => void;
}

export function DPanel({
  decision,
  density,
  onDensityChange,
  onOpenTrace,
}: DPanelProps) {
  const hasDiff = decision.diff.length > 0;
  const isCompact = density === 0;
  const isDetailed = density === 2;
  const traceId = `tr_${(decision.when || "").replace(/\s+/g, "")}_${decision.pick || ""}`;

  return (
    <section className={`panel d density-${density}`} data-comment-anchor="d-panel">
      <header className="panel-head">
        <span className="panel-key">D</span>
        <div className="panel-title">
          上顿决策的因果链
          <small>沙箱独有</small>
        </div>
        <div className="spacer" />
        <div className="density-toggle" role="tablist" aria-label="紧凑度">
          {(["紧凑", "标准", "详细"] as const).map((d, i) => (
            <button
              key={d}
              className={density === i ? "on" : ""}
              onClick={() => density !== i && onDensityChange(i as DPanelDensity)}
            >
              {d}
            </button>
          ))}
        </div>
      </header>
      <div className="panel-body">
        <div className="d-section">
          <div className="d-section-label">
            <span className="d-section-num">1</span>动作摘要
            {isDetailed && (
              <small className="d-section-meta-trace">
                · <span className="mono">{traceId}</span>
              </small>
            )}
          </div>
          <div className="action-summary">
            你 <span className="mute">{decision.when} 选了</span>{" "}
            <span className="pill">{decision.pick}</span>{" "}
            <span className="mute">
              (rank #{decision.rank} · L3=
              <span className="mono">{decision.l3}</span>)
            </span>{" "}
            <button className="op-btn op-btn-inline" onClick={onOpenTrace}>
              <span className="mono">🔍</span> 打开 trace
            </button>
          </div>
          {isDetailed && (
            <div className="d-meta mono">
              ts=<span>{decision.when}</span> · pick_rank=
              <span>{decision.rank}</span> · L3_score=
              <span>{decision.l3}</span> · diff_n=
              <span>{decision.diff.length}</span> · impl_n=
              <span>{decision.implications.length}</span>
            </div>
          )}
        </div>

        {isCompact ? (
          <div className="d-section d-compact-summary">
            <span className="mute">Δ </span>
            <span className="mono">{decision.diff.length}</span>{" "}
            <span className="mute">字段 · </span>
            <span className="mono">{decision.implications.length}</span>{" "}
            <span className="mute">条影响</span>
            <button
              className="op-btn op-btn-expand"
              onClick={() => onDensityChange(1)}
            >
              展开 ›
            </button>
          </div>
        ) : (
          <>
            <div className="d-section">
              <div className="d-section-label">
                <span className="d-section-num">2</span>状态 diff
                <small className="d-section-meta-hint">
                  · 无变化的字段已隐藏
                </small>
              </div>
              {hasDiff ? (
                <div className="diff-list">
                  {decision.diff.map((d, i) => (
                    <DiffRow key={`${d.field}-${i}`} d={d} detailed={isDetailed} />
                  ))}
                </div>
              ) : (
                <div className="diff-empty">
                  <span className="ico">⚠</span>
                  <div>
                    <strong>无学习发生。</strong> 此次动作未引起任何 D 字段变化 — 检查策略改动是否生效。
                  </div>
                </div>
              )}
            </div>

            <div className="d-section">
              <div className="d-section-label">
                <span className="d-section-num">3</span>下一顿影响提示
                <small className="d-section-meta-hint">
                  · 从已有字段推断,非预测
                </small>
              </div>
              <div className="implications">
                {decision.implications.map((i, k) => (
                  <ImpRow key={`${i.field}-${k}`} imp={i} detailed={isDetailed} />
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function DiffRow({ d, detailed }: { d: DiffEntry; detailed: boolean }) {
  const meta = detailed ? (
    <div className="diff-meta mono">
      kind=<span>{d.kind}</span> · path=<span>D.{d.field}</span>
    </div>
  ) : null;

  if (d.kind === "add") {
    return (
      <div className="diff-row">
        <span className="diff-glyph add">+</span>
        <span className="diff-key">
          <span className="field">{d.field}</span>
          {meta}
        </span>
        <span className="diff-val">
          {d.from !== undefined ? (
            <>
              <span className="from">{d.from}</span>
              <span className="to">{d.to ?? d.value}</span>
            </>
          ) : (
            <span className="to">{d.value}</span>
          )}
        </span>
      </div>
    );
  }

  if (d.kind === "up" || d.kind === "dn") {
    const sign = d.delta?.[0] ?? (d.kind === "up" ? "+" : "-");
    return (
      <div className="diff-row">
        <span className={`diff-glyph ${d.kind}`}>{d.kind === "up" ? "↑" : "↓"}</span>
        <span className="diff-key">
          <span className="field">{d.field}</span>
          {meta}
        </span>
        <span className="diff-val">
          <span className="from">{d.from}</span>
          <span className="to">{d.to}</span>
          <span className={`delta ${sign === "+" ? "pos" : "neg"}`}>{d.delta}</span>
        </span>
      </div>
    );
  }

  // ttl 或 rm (Codex Q2 iter3: rm 走 fallthrough 同 ttl 形态, types 保留 5 路)
  return (
    <div className="diff-row">
      <span className="diff-glyph ttl">⏱</span>
      <span className="diff-key">
        <span className="field">{d.field}</span>
        {meta}
      </span>
      <span className="diff-val">
        <span className="from">{d.from}</span>
        <span className="to">{d.to}</span>
      </span>
    </div>
  );
}

function ImpRow({ imp, detailed }: { imp: Implication; detailed: boolean }) {
  return (
    <div className="imp">
      <span className="arrow">→</span>
      <div>
        <span className="field">{imp.field}</span>{" "}
        <span className="imp-text-2">{imp.text}</span>
        {detailed && (
          <div className="imp-meta mono">
            source=<span>rule</span> · scope=<span>下一顿</span>
          </div>
        )}
      </div>
    </div>
  );
}

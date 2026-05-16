import type { FeedbackBadge, Meal, RunHistoryRow } from "../types/trace";

function FeedbackBadgeView({ fb }: { fb: FeedbackBadge }) {
  // 视觉次序: accepted (⭐ rank) → rating (❤×N) → stopped (🚫). 简洁优先, 不堆叠.
  if (fb.stopped) {
    return <span className="fb-badge stopped" title="stopped: 这餐没看上 / 不饿">🚫</span>;
  }
  const items: { key: string; el: JSX.Element }[] = [];
  if (fb.accepted) {
    items.push({
      key: "acc",
      el: (
        <span className="fb-badge acc" title={`accepted rank ${fb.accepted_rank ?? "?"}`}>
          ⭐{fb.accepted_rank ?? ""}
        </span>
      ),
    });
  }
  if (fb.rating != null) {
    items.push({
      key: "rt",
      el: (
        <span className="fb-badge rt" title={`rating ${fb.rating}/3`}>
          {"❤".repeat(Math.max(0, Math.min(3, fb.rating)))}
        </span>
      ),
    });
  }
  if (items.length === 0) return null;
  return (
    <span className="fb-badges">
      {items.map((i) => (
        <span key={i.key}>{i.el}</span>
      ))}
    </span>
  );
}

export type SidebarProps = {
  meal: Meal;
  setMeal: (m: Meal) => void;
  llmAuto: boolean;
  setLlmAuto: (b: boolean) => void;
  refineText: string;
  setRefineText: (s: string) => void;
  traceRest: string;
  setTraceRest: (s: string) => void;
  traceDish: string;
  setTraceDish: (s: string) => void;
  history: RunHistoryRow[];
  activeSession: string;
  setActiveSession: (id: string) => void;
  profileOverride: string;
  setProfileOverride: (s: string) => void;
  profileError: string | null;
  runDisabled: boolean;
  onRunMain: () => void;
  onRunRefine: () => void;
  onRunTrace: () => void;
  onReplayConfig: (id: string) => void;
  backendOnline?: boolean;
  corruptCount?: number;
  onRunLive?: () => void;
  onOpenWhatIf?: () => void;
  whatIfAvailable?: boolean;
};

export function Sidebar({
  meal, setMeal, llmAuto, setLlmAuto,
  refineText, setRefineText,
  traceRest, setTraceRest, traceDish, setTraceDish,
  history, activeSession, setActiveSession,
  profileOverride, setProfileOverride,
  profileError, runDisabled,
  onRunMain, onRunRefine, onRunTrace, onReplayConfig,
  backendOnline, corruptCount,
  onRunLive, onOpenWhatIf, whatIfAvailable,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <h3>Run Config</h3>

      <div className="field">
        <label className="field-label">餐次</label>
        <div className="seg">
          <button className={meal === "lunch" ? "on" : ""} onClick={() => setMeal("lunch")}>午餐</button>
          <button className={meal === "dinner" ? "on" : ""} onClick={() => setMeal("dinner")}>晚餐</button>
        </div>
      </div>

      <div className="field">
        <label className="field-label">today</label>
        <input className="input" defaultValue="2026-05-16" />
      </div>

      <div className="field">
        <div className="toggle">
          <div className={`switch ${llmAuto ? "on" : ""}`} onClick={() => setLlmAuto(!llmAuto)}></div>
          <span>LLM <span className="dim mono">= auto</span></span>
        </div>
      </div>

      <div className="field">
        <label className="field-label">
          profile 临时覆盖 <span className="dim mono">JSON</span>
          {profileError && (
            <span style={{ color: "var(--err)", marginLeft: 6, fontSize: 10 }}>
              ⚠ {profileError.slice(0, 60)}
            </span>
          )}
        </label>
        <textarea
          className="textarea"
          value={profileOverride}
          onChange={(e) => setProfileOverride(e.target.value)}
          spellCheck={false}
          style={profileError ? { borderColor: "var(--err-edge)" } : undefined}
        />
      </div>

      <h3>Actions</h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <button
          className="btn primary"
          onClick={onRunMain}
          disabled={runDisabled}
          style={runDisabled ? { opacity: 0.5, cursor: "not-allowed" } : undefined}
        >
          ▶ 触发首轮推荐
          <span className="kbd">⏎</span>
        </button>
        {onRunLive && (
          <button
            className="btn"
            onClick={onRunLive}
            disabled={runDisabled}
            style={runDisabled ? { opacity: 0.5, cursor: "not-allowed" } : undefined}
            title="Live 模式: 仅本次显示, 永不写盘"
          >
            ⚡ Live 试跑 <span className="dim mono">(no trace)</span>
          </button>
        )}
        {onOpenWhatIf && (
          <button
            className="btn"
            onClick={onOpenWhatIf}
            disabled={!whatIfAvailable}
            style={!whatIfAvailable ? { opacity: 0.5, cursor: "not-allowed" } : undefined}
            title={whatIfAvailable
              ? "基于当前 Replay trace 改 weights / caps 重跑下游"
              : "需先在 Run History 选一条 backend trace"}
          >
            🧪 What-if
          </button>
        )}
      </div>

      <h3>Refine</h3>
      <div className="field">
        <label className="field-label">自然语言反馈</label>
        <textarea
          className="textarea"
          value={refineText}
          onChange={(e) => setRefineText(e.target.value)}
          placeholder="例：想喝汤，别给我面食"
          style={{ minHeight: 56 }}
        />
      </div>
      <button className="btn" onClick={onRunRefine}>↻ 触发 refine</button>

      <h3>追溯 <span className="dim mono">/trace</span></h3>
      <div className="field">
        <label className="field-label">餐厅名 <span className="dim">(模糊)</span></label>
        <input
          className="input"
          value={traceRest}
          onChange={(e) => setTraceRest(e.target.value)}
          placeholder="太二酸菜鱼"
        />
      </div>
      <div className="field">
        <label className="field-label">菜名 <span className="dim">(空格分隔)</span></label>
        <input
          className="input"
          value={traceDish}
          onChange={(e) => setTraceDish(e.target.value)}
          placeholder="酸菜鱼 米饭"
        />
      </div>
      <button className="btn" onClick={onRunTrace}>⌕ 追溯命中</button>

      <h3>
        Run History
        {backendOnline === false && (
          <span style={{ color: "var(--warn)", marginLeft: 6, fontSize: 10 }}
                title="后端 /api/debug/sessions 不可达, 显示 localStorage 缓存">
            ⚠ offline
          </span>
        )}
        {backendOnline === true && corruptCount != null && corruptCount > 0 && (
          <span style={{ color: "var(--warn)", marginLeft: 6, fontSize: 10 }}
                title="后端列出 trace 时跳过损坏文件">
            ⚠ {corruptCount} corrupt
          </span>
        )}
      </h3>
      <div className="run-history">
        {history.map((h) => (
          <div
            key={h.id}
            className={`run-row ${activeSession === h.id ? "active" : ""}`}
            onClick={() => setActiveSession(h.id)}
          >
            <div
              className={`dot ${h.status === "ok" ? "ok" : h.status === "fallback" ? "fb" : "warn"}`}
            ></div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {h.title}
                </span>
                {h.feedback && <FeedbackBadgeView fb={h.feedback} />}
              </div>
              <div className="time">{h.time} · {h.latency}ms</div>
            </div>
            <button
              className="replay-btn"
              title="复刻这次 run config 到 sidebar (不立刻 run)"
              onClick={(e) => {
                e.stopPropagation();
                onReplayConfig(h.id);
              }}
            >
              ↻
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}

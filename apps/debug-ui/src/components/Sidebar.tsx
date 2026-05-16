import type { Meal, RunHistoryRow } from "../types/trace";

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
};

export function Sidebar({
  meal, setMeal, llmAuto, setLlmAuto,
  refineText, setRefineText,
  traceRest, setTraceRest, traceDish, setTraceDish,
  history, activeSession, setActiveSession,
  profileOverride, setProfileOverride,
  profileError, runDisabled,
  onRunMain, onRunRefine, onRunTrace, onReplayConfig,
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

      <h3>Run History</h3>
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
            <div>
              <div>{h.title}</div>
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

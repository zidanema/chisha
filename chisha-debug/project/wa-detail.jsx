// wa-detail.jsx — sticky context bar + lookup drawer

function TraceContextBar({ trace, round, onTriggerRefine, onOpenLookup }) {
  if (!trace) return null;
  const showRefineBadge = trace.refineCount > 0;
  const shortId = trace.id.split("_").slice(-1)[0]; // last segment, e.g. "a7f1"
  const [copied, setCopied] = useState(false);
  function copyId() {
    setCopied(true);
    setTimeout(() => setCopied(false), 900);
    try { navigator.clipboard && navigator.clipboard.writeText(trace.id); } catch (e) {}
  }
  return (
    <div className="tc-bar">
      <span className={`meal ${trace.meal}`}>{trace.meal === "lunch" ? "午餐" : "晚餐"}</span>
      <span className="when">{trace.date} · {trace.time}</span>
      <span className={`src ${trace.source === "sandbox" ? "sbx" : ""}`}>
        {trace.source === "sandbox" ? `sandbox · D+${trace.sandboxDay}` : "real"}
      </span>
      {showRefineBadge && (
        <span className="rd-badge">{trace.latestRound} · {1 + trace.refineCount} 轮</span>
      )}
      {round && round.id !== "R1" && (
        <span className="rd-badge" style={{ background: "var(--ref-bg)" }}>当前 {round.id}</span>
      )}
      <span className="top1"><span className="lbl">final top1</span>{trace.finalTop1}</span>
      <span className="spacer"></span>
      <button
        className="id-pill"
        onClick={copyId}
        title={`session id · ${trace.id}\n点击复制`}
      >
        <span className="lbl">session</span>
        <span className="val">…{shortId}</span>
        <span className="cp">{copied ? "✓" : "⧉"}</span>
      </button>
      <div className="actions">
        <button className="ib" onClick={onOpenLookup}>⌕ 追溯命中</button>
      </div>
    </div>
  );
}

function LookupDrawer({ open, onClose }) {
  const [rest, setRest] = useState("太二酸菜鱼");
  const [dish, setDish] = useState("");
  if (!open) return null;
  return (
    <React.Fragment>
      <div className="lookup-scrim" onClick={onClose}></div>
      <div className="lookup-drawer">
        <div className="lookup-head">
          <h3>追溯命中</h3>
          <span className="sub">/trace</span>
          <button className="close" onClick={onClose}>关闭 ✕</button>
        </div>
        <div className="lookup-body">
          <div>
            <label className="field-label">餐厅名 <span className="dim">(模糊)</span></label>
            <input className="input" value={rest} onChange={e => setRest(e.target.value)} placeholder="太二酸菜鱼" />
          </div>
          <div>
            <label className="field-label">菜名 <span className="dim">(空格分隔)</span></label>
            <input className="input" value={dish} onChange={e => setDish(e.target.value)} placeholder="酸菜鱼 米饭" />
          </div>
          <div className="btn-row">
            <button className="btn">⌕ 重跑 pipeline + 高亮</button>
          </div>
          <div className="placeholder">
            # 重跑结果在此<br />
            <span style={{ color: "var(--t-4)" }}>{rest || "(空)"} / {dish || "(空)"}</span><br /><br />
            stage badge · L1 hard_filter / L2 / L3 / Final 命中层 + 完整 nutrition_profile
          </div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--t-3)", lineHeight: 1.6 }}>
            • 抽屉 = 独立查询，不依赖左边选中的 trace<br />
            • 高亮基于"重跑一次"的新 pipeline，不写盘<br />
            • 关闭抽屉返回当前 trace
          </div>
        </div>
      </div>
    </React.Fragment>
  );
}

function SummaryCard({ trace, round }) {
  // 人话摘要 — non-sticky, appears once near top of panels
  let copy;
  if (!round || round.id === "R1") {
    copy = `今天午餐推「${trace.finalTop1}」，主理由是高蛋白汤水 + 低油 + 用户最近没吃过椰子鸡。另外两条 explore 是为了补「换换口味」和「补充汤水」。`;
  } else {
    copy = `第 ${round.id} 轮在原始推荐基础上，把面食/米饭主食类全部下沉，主推「${trace.finalTop1}」这种汤水高蛋白组合；并踢出了 quinoa 和点名拒绝的西少爷。`;
  }
  return (
    <div style={{
      margin: "14px 14px 0",
      padding: "12px 14px",
      border: "1px solid var(--line)",
      background: "var(--bg-1)",
      borderRadius: "var(--radius)",
      display: "grid",
      gridTemplateColumns: "auto 1fr auto",
      gap: 12,
      alignItems: "center",
    }}>
      <span style={{
        fontFamily: "var(--mono)", fontSize: 10, fontWeight: 700,
        background: "var(--accent)", color: "var(--head-text)",
        padding: "3px 8px", borderRadius: 2, letterSpacing: "0.06em",
        textTransform: "uppercase",
      }}>人话</span>
      <span style={{ fontSize: 13, color: "var(--t-0)", lineHeight: 1.5 }}>{copy}</span>
      <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--t-3)" }}>LLM gen · ≤100 字</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// RoundBanner — strong visual hand-off from timeline → panels
// ─────────────────────────────────────────────────────────────

// per-round synthetic deltas (visual only — keeps panel internals untouched)
const ROUND_DELTAS = {
  R1: {
    l1:    { delta: <>raw 11k → <span className="neu">1,207 combos</span> · 8 餐厅被 ban (ETA / avoid_restaurants / 近 7 天)</>, },
    l2:    { delta: <>L2 V2 12 维打分 · top1 <span className="neu">cmb_001</span> · 84 餐厅 → 31 (cap K=4)</>, },
    l3:    { delta: <>opus-4-7 · 2148ms · cache 82% · 3 exploit + 2 explore</>, },
    final: { delta: <>top1 <span className="neu">椰客椰子鸡</span> · ¥90 · 22 min</>, },
  },
  R2: {
    l1:    { delta: <>1,207 combos (同) · <span className="up">+ novelty_boost</span> 重新洗牌 · 餐厅 ban 不变</>, },
    l2:    { delta: <>top1 切到 <span className="neu">cmb_005 汤先生</span> · <span className="up">+18 位</span> upward shifts</>, },
    l3:    { delta: <>opus-4-7 · 2104ms · "用户要轮换" 提示进入 system</>, },
    final: { delta: <><span className="up">+4 新进</span> / <span className="down">−4 踢出</span> · 椰客掉到 #3</>, },
  },
  R3: {
    l1:    { delta: <><span className="down">−27</span> combos (1,180) · grain:noodle / grain:rice 全部 penalty · 西少爷 -1.0</>, },
    l2:    { delta: <>top1 回到 <span className="neu">cmb_001</span> · soup +0.22 / wet +0.18 起效 · <span className="up">+2 上移</span> / <span className="down">−1 下移</span></>, },
    l3:    { delta: <>opus-4-7 · 2310ms · explore 必须含 wet 类</>, },
    final: { delta: <><span className="up">+3 新进</span> 全为汤类 · <span className="down">−3 踢出</span> 含 Wagas / 西少爷</>, },
  },
  R4: {
    l1:    { delta: <><span className="down">−38</span> combos (1,142) · 川 / 湘菜系 + 油炸 ban · ingredient_avoid 扩到 3 项</>, },
    l2:    { delta: <>top1 保持 <span className="neu">cmb_001</span> · oil_penalty 权重 ×1.4 · <span className="up">+1 上移</span> / <span className="down">−2 下移</span></>, },
    l3:    { delta: <>opus-4-7 · 2208ms · 强调"清淡"约束</>, },
    final: { delta: <><span className="up">+2 新进</span> 全 low oil · <span className="down">−2 踢出</span> 含偏油的 cmb_034</>, },
  },
};

function RoundBanner({ targetRound, baseRound, trace }) {
  const isR1 = !targetRound || targetRound.id === "R1";
  const deltas = ROUND_DELTAS[targetRound ? targetRound.id : "R1"] || ROUND_DELTAS.R1;
  return (
    <div className={`round-banner ${isR1 ? "r1" : ""}`}>
      <div className="round-banner-head">
        <span className="arrow-down">▼</span>
        <span className="lbl">{targetRound ? targetRound.id : "R1"} pipeline</span>
        <span className="copy">
          下方 4 个 panel 显示 <strong>{targetRound ? targetRound.id : "R1"} · {targetRound ? targetRound.label : "原始"}</strong> 的完整 pipeline
          {!isR1 && baseRound && baseRound.id !== targetRound.id && (
            <> · 每个 panel 顶部带 Δ vs <strong>{baseRound.id} · {baseRound.label}</strong></>
          )}
        </span>
        {!isR1 && baseRound && baseRound.id !== targetRound.id && (
          <span className="vs">
            <span className="b">{baseRound.id}</span> → <span className="t">{targetRound.id}</span>
          </span>
        )}
      </div>
      <div className="round-banner-deltas">
        <div className="d l1">
          <span className="lay">L1 召回</span>
          <span className="delta">{deltas.l1.delta}</span>
        </div>
        <div className="d l2">
          <span className="lay">L2 打分</span>
          <span className="delta">{deltas.l2.delta}</span>
        </div>
        <div className="d l3">
          <span className="lay">L3 LLM</span>
          <span className="delta">{deltas.l3.delta}</span>
        </div>
        <div className="d fin">
          <span className="lay">Final</span>
          <span className="delta">{deltas.final.delta}</span>
        </div>
      </div>
    </div>
  );
}

function PanelRoundStrip({ layer, targetRound, baseRound }) {
  const isR1 = !targetRound || targetRound.id === "R1";
  const deltas = ROUND_DELTAS[targetRound ? targetRound.id : "R1"] || ROUND_DELTAS.R1;
  const d = deltas[layer];
  const layerLabel = { l1: "L1 召回", l2: "L2 打分", l3: "L3 LLM", final: "Final" }[layer];
  return (
    <div className={`panel-round-strip ${isR1 ? "r1" : ""}`}>
      <span className={`layer-tag ${layer}`}>{layerLabel} · {targetRound ? targetRound.id : "R1"}</span>
      <span className="delta">{d.delta}</span>
      {!isR1 && baseRound && baseRound.id !== targetRound.id && (
        <span className="vs">
          Δ vs <span className="b">{baseRound.id}</span> → <span className="t">{targetRound.id}</span>
        </span>
      )}
    </div>
  );
}

Object.assign(window, { TraceContextBar, LookupDrawer, SummaryCard, RoundBanner, PanelRoundStrip });

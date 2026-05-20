// wa-refine.jsx — IntentStrip + git-compare Timeline + Followup card

const INTENT_FIELDS = [
  { key: "cuisine_want",     label: "菜系想",     tone: "want" },
  { key: "cuisine_avoid",    label: "菜系不想",    tone: "avoid" },
  { key: "ingredient_want",  label: "食材想",     tone: "want" },
  { key: "ingredient_avoid", label: "食材不想",    tone: "avoid" },
  { key: "taste_want",       label: "口味想",     tone: "want" },
  { key: "taste_avoid",      label: "口味不想",    tone: "avoid" },
  { key: "cook_want",        label: "烹饪方式",    tone: "want" },
  { key: "portion",          label: "份量",      tone: "neutral", scalar: true },
  { key: "grain_pref",       label: "主食偏好",    tone: "neutral", scalar: true },
  { key: "price_band",       label: "价格带",     tone: "neutral", scalar: true },
  { key: "raw_taste",        label: "原文口味",    tone: "neutral", scalar: true },
];

function renderIntentValue(field, value, prevValue) {
  if (field.scalar) {
    if (!value) return <span className="empty">—</span>;
    const added = prevValue !== value;
    return <span className={`ich neutral ${added ? "added" : ""}`}>{value}</span>;
  }
  const arr = Array.isArray(value) ? value : [];
  if (arr.length === 0) return <span className="empty">—</span>;
  const prevArr = Array.isArray(prevValue) ? prevValue : [];
  return arr.map((v, i) => {
    const added = !prevArr.includes(v);
    return <span key={i} className={`ich ${field.tone} ${added ? "added" : ""}`}>{v}</span>;
  });
}

function IntentStrip({ round, prevRound, collapsed, setCollapsed }) {
  if (!round) return null;
  const prev = prevRound ? prevRound.intent : {};

  return (
    <div className={`intent-strip ${collapsed ? "collapsed" : ""}`}>
      <div className="head">
        <span className="lbl">intent</span>
        <span className="round">{round.id} · {round.label}</span>
        {round.user_text ? (
          <span className="raw"><span className="q">"</span>{round.user_text}<span className="q">"</span></span>
        ) : (
          <span className="raw"><span className="q">// </span>首轮 · 来自 profile，无 refine 输入</span>
        )}
        <button className="toggle-btn" onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? "展开 ▾" : "收起 ▴"}
        </button>
      </div>
      {!collapsed && (
        <div className="intent-fields">
          {INTENT_FIELDS.map(f => (
            <div className="intent-field" key={f.key}>
              <div className="k">{f.label}</div>
              <div className="v">{renderIntentValue(f, round.intent[f.key], prev[f.key])}</div>
            </div>
          ))}
          <div className="intent-field freeform">
            <div className="k">freeform_note</div>
            <div className="v">
              {round.intent.freeform_note
                ? round.intent.freeform_note
                : <span className="empty">—</span>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RefineTimeline({ rounds, base, target, setBase, setTarget, onSwap, diffMode, setDiffMode }) {
  if (!rounds || rounds.length <= 1) return null;
  const baseIdx = rounds.findIndex(r => r.id === base);
  const targetIdx = rounds.findIndex(r => r.id === target);
  const minIdx = Math.min(baseIdx, targetIdx);
  const maxIdx = Math.max(baseIdx, targetIdx);

  // diff stats — synthesize from target.diff if it's adjacent vs R1
  const targetRound = rounds[targetIdx];
  let stats = { up: 0, down: 0, neu: 0 };
  if (targetRound && targetRound.diff) {
    stats = {
      up: targetRound.diff.in,
      down: targetRound.diff.out,
      neu: targetRound.diff.up + targetRound.diff.down,
    };
  }

  function nodeLeft(i) {
    if (rounds.length === 1) return "50%";
    return `${(i / (rounds.length - 1)) * 100}%`;
  }

  function handleClick(e, idx) {
    if (e.shiftKey || e.altKey || e.metaKey) {
      setBase(rounds[idx].id);
    } else {
      setTarget(rounds[idx].id);
    }
  }
  function handleContext(e, idx) {
    e.preventDefault();
    setBase(rounds[idx].id);
  }

  return (
    <div className="rt">
      <div className="rt-bar">
        <span className="lbl">compare</span>
        <span className="compare-box">
          <span className="base">{rounds[baseIdx].id}</span>
          <span className="arrow">→</span>
          <span className="target">{rounds[targetIdx].id}</span>
        </span>
        <button className="swap" onClick={onSwap} title="交换 base / target">⇄ swap</button>
        <div className="diff-mode-toggle" title="diff 基线选择模式">
          <button
            className={diffMode === "vs_r1" ? "on" : ""}
            onClick={() => setDiffMode("vs_r1")}
          >vs R1</button>
          <button
            className={diffMode === "adjacent" ? "on" : ""}
            onClick={() => setDiffMode("adjacent")}
          >相邻</button>
        </div>
        <span className="diff-stats">
          <span className="up">+{stats.up} 新进</span>
          <span className="down">−{stats.down} 踢出</span>
          <span className="neu">~{stats.neu} 位次</span>
        </span>
      </div>
      <div className="rt-track">
        <div className="axis"></div>
        <div
          className="range"
          style={{
            left: `calc(${(minIdx / (rounds.length - 1)) * 100}% + 6px)`,
            right: `calc(${((rounds.length - 1 - maxIdx) / (rounds.length - 1)) * 100}% + 6px)`,
          }}
        ></div>
        <div className="nodes">
          {rounds.map((r, i) => {
            const isBase = r.id === base;
            const isTarget = r.id === target;
            return (
              <div
                key={r.id}
                className={`rt-node ${isBase ? "is-base" : ""} ${isTarget ? "is-target" : ""}`}
                style={{ left: nodeLeft(i), top: 0 }}
                onClick={(e) => handleClick(e, i)}
                onContextMenu={(e) => handleContext(e, i)}
                title={r.user_text || r.label}
              >
                <span className="lbl">{r.id}</span>
                <span className="ball"></span>
                <span className="when">{r.time}</span>
                <span className="role"></span>
                <span className="desc">{r.label}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="rt-legend">
        <span className="hint">点节点切轮次 · 上方 toggle 决定对比基线</span>
      </div>
    </div>
  );
}

function Followup({ defaultText, onSubmit }) {
  const [text, setText] = useState(defaultText || "");
  return (
    <div className="followup">
      <div className="head">
        <span className="tag">↻ continue</span>
        <span>继续追问当前 trace</span>
        <span className="ctx mono">下一轮会写回同一份 trace 文件 · 作为 R{(window.WA_MOCK.ROUNDS.length + 1)}</span>
      </div>
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder='例: "再清淡一点，主食给我点豆制品"'
        spellCheck="false"
      />
      <div className="row">
        <div className="chips">
          <span className="quick" onClick={() => setText("换一组")}>换一组</span>
          <span className="quick" onClick={() => setText("想喝汤")}>想喝汤</span>
          <span className="quick" onClick={() => setText("别要重的")}>别要重的</span>
          <span className="quick" onClick={() => setText("加点蛋白")}>加点蛋白</span>
          <span className="quick" onClick={() => setText("最近吃太多面食了")}>避面食</span>
        </div>
        <button className="ib" onClick={() => onSubmit && onSubmit(text)}>↻ 追问 R{window.WA_MOCK.ROUNDS.length + 1}</button>
      </div>
    </div>
  );
}

Object.assign(window, { IntentStrip, RefineTimeline, Followup });

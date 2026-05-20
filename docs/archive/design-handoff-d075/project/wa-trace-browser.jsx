// wa-trace-browser.jsx — left-rail trace browser with filters + tree-fold refine

const FILTER_DEFS = [
  { id: "all",     label: "全部",          predicate: () => true },
  { id: "refined", label: "含 refine",     predicate: t => t.refineCount > 0 },
  { id: "accepted",label: "已采纳",         predicate: t => t.feedback && t.feedback.type === "accepted" },
  { id: "rated",   label: "已评分",         predicate: t => t.feedback && t.feedback.type === "rated" },
  { id: "sandbox", label: "sandbox",       predicate: t => t.source === "sandbox" },
];

function feedbackGlyph(fb) {
  if (!fb) return null;
  if (fb.type === "accepted") return <span title={`accepted rank ${fb.rank}`}>⭐ <span className="mono">#{fb.rank}</span></span>;
  if (fb.type === "rated")    return <span title={`rated ${fb.count}`}><span className="fb-emoji">{"❤".repeat(Math.min(fb.count, 3))}</span> <span className="mono">×{fb.count}</span></span>;
  if (fb.type === "stopped")  return <span title="stopped">🚫</span>;
  return null;
}

function dayLabel(traceDate, daysAgo) {
  if (daysAgo === 0) return "今天 · " + traceDate;
  if (daysAgo === 1) return "昨天 · " + traceDate;
  if (daysAgo === 2) return "前天 · " + traceDate;
  if (daysAgo < 7) return daysAgo + " 天前 · " + traceDate;
  return traceDate;
}

function TraceBrowser({
  traces, activeTrace, setActiveTrace,
  activeRound, setActiveRound,
  expanded, setExpanded,
  collapsed, setCollapsed,
  onOpenLookup, onOpenSettings,
}) {
  const [filters, setFilters] = useState(new Set(["all"]));
  const [sort, setSort] = useState("time-desc");
  const [search, setSearch] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const pickerRef = useRef(null);
  useEffect(() => {
    if (!pickerOpen) return;
    function onClick(e) {
      if (pickerRef.current && !pickerRef.current.contains(e.target)) setPickerOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [pickerOpen]);
  useEffect(() => { if (collapsed) setPickerOpen(false); }, [activeTrace]);

  function toggleFilter(id) {
    const next = new Set(filters);
    if (id === "all") return setFilters(new Set(["all"]));
    next.delete("all");
    if (next.has(id)) next.delete(id);
    else next.add(id);
    if (next.size === 0) next.add("all");
    setFilters(next);
  }
  function toggleExpand(id) {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id); else next.add(id);
    setExpanded(next);
  }

  // counts per filter (excluding search)
  const counts = useMemo(() => {
    const c = {};
    FILTER_DEFS.forEach(f => { c[f.id] = traces.filter(f.predicate).length; });
    return c;
  }, [traces]);

  // filtered list
  const filtered = useMemo(() => {
    let xs = traces;
    if (!filters.has("all")) {
      xs = xs.filter(t => Array.from(filters).every(fid => {
        const def = FILTER_DEFS.find(d => d.id === fid);
        return def ? def.predicate(t) : true;
      }));
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      xs = xs.filter(t =>
        t.finalTop1.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q) ||
        (t.meal === "lunch" ? "午餐" : "晚餐").includes(q)
      );
    }
    if (sort === "time-desc") xs = xs.slice().sort((a, b) => a.daysAgo - b.daysAgo || (b.time < a.time ? -1 : 1));
    else if (sort === "time-asc") xs = xs.slice().sort((a, b) => b.daysAgo - a.daysAgo || (a.time < b.time ? -1 : 1));
    else if (sort === "refines") xs = xs.slice().sort((a, b) => b.refineCount - a.refineCount);
    return xs;
  }, [traces, filters, search, sort]);

  // group by day
  const groups = useMemo(() => {
    const m = new Map();
    filtered.forEach(t => {
      const key = t.daysAgo;
      if (!m.has(key)) m.set(key, []);
      m.get(key).push(t);
    });
    return Array.from(m.entries()).sort((a, b) => a[0] - b[0]);
  }, [filtered]);

  // ─── collapsed (rail) view ───────────────────────────────
  if (collapsed) {
    const active = traces.find(t => t.id === activeTrace) || traces[0];
    const idxInFiltered = filtered.findIndex(t => t.id === activeTrace);
    function step(delta) {
      if (!filtered.length) return;
      const cur = Math.max(0, idxInFiltered);
      const next = (cur + delta + filtered.length) % filtered.length;
      setActiveTrace(filtered[next].id);
      setActiveRound("R1");
    }
    return (
      <aside className="tb-sidebar collapsed">
        <button
          className="tb-rail-expand"
          onClick={() => setCollapsed(false)}
          title="展开列表"
        >
          <span className="chev">›</span>
          <span className="lbl">Traces</span>
          <span className="cnt mono">{traces.length}</span>
        </button>

        <div className="tb-rail-picker" ref={pickerRef}>
          <button
            className={`tb-rail-current ${pickerOpen ? "open" : ""}`}
            onClick={() => setPickerOpen(o => !o)}
            title="切换 trace"
          >
            {active && (
              <>
                <div className="row1">
                  <span className={`dot ${active.status === "ok" ? "ok" : active.status === "fallback" ? "fb" : "warn"}`}></span>
                  <span className={`meal ${active.meal}`}>{active.meal === "lunch" ? "午" : "晚"}</span>
                </div>
                <div className="time mono">{active.time}</div>
                <div className="day mono">{active.daysAgo === 0 ? "今天" : active.daysAgo === 1 ? "昨" : active.daysAgo === 2 ? "前" : `-${active.daysAgo}d`}</div>
                {active.refineCount > 0 && <div className="rd mono">R{1 + active.refineCount}</div>}
                <div className="chev">▾</div>
              </>
            )}
          </button>

          {pickerOpen && (
            <div className="tb-rail-pop">
              <div className="tb-rail-pop-head">
                <span className="mono">{filtered.length} traces</span>
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="搜索…"
                  autoFocus
                />
              </div>
              <div className="tb-rail-pop-list">
                {groups.map(([daysAgo, items]) => (
                  <React.Fragment key={daysAgo}>
                    <div className="tb-day">{dayLabel(items[0].date, daysAgo)}</div>
                    {items.map(t => {
                      const isActive = activeTrace === t.id;
                      return (
                        <div
                          key={t.id}
                          className={`tb-row ${isActive ? "active" : ""}`}
                          onClick={() => {
                            setActiveTrace(t.id);
                            setActiveRound("R1");
                            setPickerOpen(false);
                          }}
                        >
                          <div className={`dot ${t.status === "ok" ? "ok" : t.status === "fallback" ? "fb" : "warn"}`}></div>
                          <div className="body">
                            <div className="l1">
                              <span className="time">{t.time}</span>
                              <span className={`meal ${t.meal}`}>{t.meal === "lunch" ? "午" : "晚"}</span>
                              {t.refineCount > 0 && (
                                <span className="rd-badge" style={{ fontSize: 9 }}>
                                  R{1 + t.refineCount} ×{1 + t.refineCount}
                                </span>
                              )}
                              <span className={`src ${t.source === "sandbox" ? "sbx" : ""}`}>
                                {t.source === "sandbox" ? `SBX D+${t.sandboxDay}` : "REAL"}
                              </span>
                            </div>
                            <div className="l2">{t.finalTop1}</div>
                            <div className="l3">
                              <span className="mono">{t.latency_ms}ms</span>
                              {t.feedback && <span style={{ marginLeft: 6 }}>{feedbackGlyph(t.feedback)}</span>}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </React.Fragment>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="tb-rail-nav">
          <button onClick={() => step(-1)} title="上一条">▴</button>
          <span className="mono pos">{Math.max(0, idxInFiltered) + 1}/{filtered.length}</span>
          <button onClick={() => step(1)} title="下一条">▾</button>
        </div>

        <div className="tb-rail-foot">
          <button className="icon-btn" onClick={onOpenLookup} title="追溯命中">⌕</button>
          <button className="icon-btn" onClick={onOpenSettings} title="设置">⚙</button>
        </div>
      </aside>
    );
  }

  // ─── full list view ──────────────────────────────────────

  return (
    <aside className="tb-sidebar">
      <div className="tb-head">
        <div className="tb-title">
          <span>Traces</span>
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="count mono">{filtered.length} / {traces.length}</span>
            <button
              className="tb-collapse-btn"
              onClick={() => setCollapsed(true)}
              title="收起列表 · 切到下拉模式"
            >‹</button>
          </span>
        </div>
        <div className="tb-search">
          <span className="icon">⌕</span>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜餐厅名 / session id"
          />
        </div>
        <div className="tb-filters">
          {FILTER_DEFS.map(f => (
            <button
              key={f.id}
              className={`tb-chip ${filters.has(f.id) ? "on" : ""}`}
              onClick={() => toggleFilter(f.id)}
            >
              {f.label} <span className="c">{counts[f.id]}</span>
            </button>
          ))}
        </div>
        <div className="tb-sort">
          <span>按</span>
          <select className="sel" value={sort} onChange={e => setSort(e.target.value)}>
            <option value="time-desc">时间倒序</option>
            <option value="time-asc">时间正序</option>
            <option value="refines">refine 多到少</option>
          </select>
        </div>
      </div>

      <div className="tb-list">
        {groups.length === 0 && (
          <div style={{ padding: 20, fontFamily: "var(--mono)", fontSize: 11, color: "var(--t-3)", textAlign: "center" }}>
            没有匹配的 trace
          </div>
        )}
        {groups.map(([daysAgo, items]) => (
          <React.Fragment key={daysAgo}>
            <div className="tb-day">{dayLabel(items[0].date, daysAgo)}</div>
            {items.map(t => {
              const isActive = activeTrace === t.id;
              const isOpen = expanded.has(t.id);
              const hasRefines = t.refineCount > 0;
              return (
                <React.Fragment key={t.id}>
                  <div
                    className={`tb-row ${isActive ? "active" : ""}`}
                    onClick={() => { setActiveTrace(t.id); setActiveRound("R1"); }}
                  >
                    <div className={`dot ${t.status === "ok" ? "ok" : t.status === "fallback" ? "fb" : "warn"}`}></div>
                    <div className="body">
                      <div className="l1">
                        <span className="time">{t.time}</span>
                        <span className={`meal ${t.meal}`}>{t.meal === "lunch" ? "午" : "晚"}</span>
                        {hasRefines && (
                          <span className="rd-badge" style={{ fontSize: 9 }}>
                            R{1 + t.refineCount} ×{1 + t.refineCount}
                          </span>
                        )}
                        <span className={`src ${t.source === "sandbox" ? "sbx" : ""}`}>
                          {t.source === "sandbox" ? `SBX D+${t.sandboxDay}` : "REAL"}
                        </span>
                      </div>
                      <div className="l2">{t.finalTop1}</div>
                      <div className="l3">
                        <span className="mono">{t.latency_ms}ms</span>
                        {t.feedback && <span style={{ marginLeft: 6 }}>{feedbackGlyph(t.feedback)}</span>}
                      </div>
                    </div>
                    {hasRefines && (
                      <button
                        className="chev"
                        onClick={(e) => { e.stopPropagation(); toggleExpand(t.id); }}
                        style={{ background: "transparent", border: 0, cursor: "pointer" }}
                      >
                        {isOpen ? "▾" : "▸"}
                      </button>
                    )}
                  </div>
                  {hasRefines && isOpen && (
                    <div className="tb-rounds">
                      <div
                        className={`rr ${isActive && activeRound === "R1" ? "active" : ""}`}
                        onClick={() => { setActiveTrace(t.id); setActiveRound("R1"); }}
                      >
                        <span></span>
                        <span><span className="name">R1</span> <span className="txt">原始</span></span>
                        <span className="when">{t.time}</span>
                      </div>
                      {[...Array(t.refineCount)].map((_, i) => {
                        const rid = `R${i + 2}`;
                        const rdesc = isActive && window.WA_MOCK.ROUNDS[i + 1]
                          ? window.WA_MOCK.ROUNDS[i + 1].label
                          : ["换一组", "想喝汤", "别要重的", "加点蛋白"][i] || "追问";
                        return (
                          <div
                            key={rid}
                            className={`rr ${isActive && activeRound === rid ? "active" : ""}`}
                            onClick={() => { setActiveTrace(t.id); setActiveRound(rid); }}
                          >
                            <span></span>
                            <span><span className="name">{rid}</span> <span className="txt">{rdesc}</span></span>
                            <span className="when">+{(i + 1) * 2 + 1}min</span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </React.Fragment>
        ))}
      </div>

      <div className="tb-foot">
        <h4>全局</h4>
        <div className="row">
          <button className="icon-btn" onClick={onOpenLookup}>⌕ 追溯命中</button>
          <button className="icon-btn" onClick={onOpenSettings}>⚙ 设置</button>
        </div>
      </div>
    </aside>
  );
}

window.TraceBrowser = TraceBrowser;

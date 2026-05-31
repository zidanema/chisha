// TraceBrowser — 左侧 trace 列表: filters + sort + 搜索 + 按天分组 + tree-fold
// refine round 子节点 + collapsed rail mode (窄条 + 当前 trace picker).
// 1:1 port chisha-debug/project/wa-trace-browser.jsx; 数据走 props (Phase 2b 改后端).

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { RoundRecord, TraceFeedback, TraceMeta } from "../types/trace";

type FilterId = "all" | "refined" | "accepted" | "rated" | "sandbox";

const FILTER_DEFS: { id: FilterId; label: string; predicate: (t: TraceMeta) => boolean }[] = [
  { id: "all",      label: "全部",      predicate: () => true },
  { id: "refined",  label: "含 refine", predicate: (t) => t.refineCount > 0 },
  { id: "accepted", label: "已采纳",     predicate: (t) => t.feedback?.type === "accepted" },
  { id: "rated",    label: "已评分",     predicate: (t) => t.feedback?.type === "rated" },
  { id: "sandbox",  label: "sandbox",   predicate: (t) => t.source === "sandbox" },
];

type SortKey = "time-desc" | "time-asc" | "refines";

function dayLabel(traceDate: string, daysAgo: number): string {
  if (daysAgo === 0) return "今天 · " + traceDate;
  if (daysAgo === 1) return "昨天 · " + traceDate;
  if (daysAgo === 2) return "前天 · " + traceDate;
  if (daysAgo < 7)   return daysAgo + " 天前 · " + traceDate;
  return traceDate;
}

function feedbackGlyph(fb: TraceFeedback | null | undefined): ReactNode {
  if (!fb) return null;
  if (fb.type === "accepted") {
    // D-088 (B4): 显式 ★ (U+2605, ASCII fallback 字体表现稳) + 餐厅名 + #rank.
    // 餐厅名缺失时仍能 fallback 到旧渲染.
    const name = fb.restaurant_name || "";
    const title = name ? `accepted: ${name} · rank ${fb.rank}` : `accepted rank ${fb.rank}`;
    return (
      <span title={title}>
        <span className="fb-star">★</span>
        {name && <span className="fb-name"> {name}</span>}
        <span className="mono"> #{fb.rank}</span>
      </span>
    );
  }
  if (fb.type === "rated") {
    const c = fb.count ?? 1;
    return (
      <span title={`rated ${c}`}>
        <span className="fb-emoji">{"❤".repeat(Math.min(c, 3))}</span>
        <span className="mono"> ×{c}</span>
      </span>
    );
  }
  if (fb.type === "stopped") return <span title="stopped">🚫</span>;
  return null;
}

type Props = {
  traces: TraceMeta[];
  activeTrace: string;
  setActiveTrace: (id: string) => void;
  activeRound: string;
  setActiveRound: (id: string) => void;
  // expand/collapse state for refine round tree (一次只 expand 当前 active 也 OK).
  expanded: Set<string>;
  setExpanded: (s: Set<string>) => void;
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
  onOpenLookup: () => void;
  onOpenSettings: () => void;
  // 当前 active trace 的真实 rounds (用于 expand 时显示子节点的 label/time)
  activeRounds: RoundRecord[];
};

export function TraceBrowser({
  traces, activeTrace, setActiveTrace,
  activeRound, setActiveRound,
  expanded, setExpanded,
  collapsed, setCollapsed,
  onOpenLookup, onOpenSettings,
  activeRounds,
}: Props) {
  const [filters, setFilters] = useState<Set<FilterId>>(new Set(["all"]));
  const [sort, setSort] = useState<SortKey>("time-desc");
  const [search, setSearch] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const pickerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!pickerOpen) return;
    function onClick(e: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setPickerOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [pickerOpen]);

  // 切 active trace 时关闭 picker
  useEffect(() => { if (collapsed) setPickerOpen(false); }, [activeTrace, collapsed]);

  function toggleFilter(id: FilterId) {
    const next = new Set(filters);
    if (id === "all") { setFilters(new Set(["all"])); return; }
    next.delete("all");
    if (next.has(id)) next.delete(id); else next.add(id);
    if (next.size === 0) next.add("all");
    setFilters(next);
  }

  function toggleExpand(id: string) {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id); else next.add(id);
    setExpanded(next);
  }

  const counts = useMemo(() => {
    const c: Record<FilterId, number> = { all: 0, refined: 0, accepted: 0, rated: 0, sandbox: 0 };
    FILTER_DEFS.forEach((f) => { c[f.id] = traces.filter(f.predicate).length; });
    return c;
  }, [traces]);

  const filtered = useMemo(() => {
    let xs = traces;
    if (!filters.has("all")) {
      xs = xs.filter((t) => Array.from(filters).every((fid) => {
        const def = FILTER_DEFS.find((d) => d.id === fid);
        return def ? def.predicate(t) : true;
      }));
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      xs = xs.filter((t) =>
        t.finalTop1.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q) ||
        (t.meal === "lunch" ? "午餐" : "晚餐").includes(q),
      );
    }
    if (sort === "time-desc") {
      xs = xs.slice().sort((a, b) => a.daysAgo - b.daysAgo || (b.time < a.time ? -1 : 1));
    } else if (sort === "time-asc") {
      xs = xs.slice().sort((a, b) => b.daysAgo - a.daysAgo || (a.time < b.time ? -1 : 1));
    } else {
      xs = xs.slice().sort((a, b) => b.refineCount - a.refineCount);
    }
    return xs;
  }, [traces, filters, search, sort]);

  const groups = useMemo(() => {
    const m = new Map<number, TraceMeta[]>();
    filtered.forEach((t) => {
      if (!m.has(t.daysAgo)) m.set(t.daysAgo, []);
      m.get(t.daysAgo)!.push(t);
    });
    return Array.from(m.entries()).sort((a, b) => a[0] - b[0]);
  }, [filtered]);

  function renderTraceGroups(mode: "collapsed" | "full") {
    return groups.map(([daysAgo, items]) => (
      <Fragment key={daysAgo}>
        <div className="tb-day">{dayLabel(items[0].date, daysAgo)}</div>
        {items.map((t) => {
          const isActive = activeTrace === t.id;
          const isOpen = expanded.has(t.id);
          const hasRefines = t.refineCount > 0;
          return (
            <Fragment key={t.id}>
              <TraceRow
                trace={t}
                active={isActive}
                isOpen={isOpen}
                hasRefines={hasRefines}
                mode={mode}
                onRowClick={() => {
                  setActiveTrace(t.id);
                  if (mode === "collapsed") setPickerOpen(false);
                }}
                onToggleExpand={() => toggleExpand(t.id)}
              />
              {mode === "full" && hasRefines && isOpen && (
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
                    const realRound = isActive
                      ? activeRounds.find((r) => r.id === rid)
                      : undefined;
                    const rdesc = realRound?.label
                      ?? ["换一组", "想喝汤", "别要重的", "加点蛋白"][i]
                      ?? "追问";
                    const rwhen = realRound?.started_at ?? `+${(i + 1) * 2 + 1}min`;
                    return (
                      <div
                        key={rid}
                        className={`rr ${isActive && activeRound === rid ? "active" : ""}`}
                        onClick={() => { setActiveTrace(t.id); setActiveRound(rid); }}
                      >
                        <span></span>
                        <span><span className="name">{rid}</span> <span className="txt">{rdesc}</span></span>
                        <span className="when">{rwhen}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </Fragment>
          );
        })}
      </Fragment>
    ));
  }

  // ─── collapsed rail mode ────────────────────────────────────
  if (collapsed) {
    const active = traces.find((t) => t.id === activeTrace) ?? traces[0];
    const idxInFiltered = filtered.findIndex((t) => t.id === activeTrace);
    function step(delta: number) {
      if (filtered.length === 0) return;
      const cur = Math.max(0, idxInFiltered);
      const next = (cur + delta + filtered.length) % filtered.length;
      setActiveTrace(filtered[next].id);
      // D-088 (B1): 不再硬切 R1 — App.tsx (A) effect 会在 trace detail 到达时
      // reset 到新 trace 的 latestRound. 这里硬切 R1 会和 (A) effect race.
    }
    return (
      <aside className="tb-sidebar collapsed">
        <button className="tb-rail-expand" onClick={() => setCollapsed(false)} title="展开列表">
          <span className="chev">›</span>
          <span className="lbl">Traces</span>
          <span className="cnt mono">{traces.length}</span>
        </button>

        <div className="tb-rail-picker" ref={pickerRef}>
          <button
            className={`tb-rail-current ${pickerOpen ? "open" : ""}`}
            onClick={() => setPickerOpen(!pickerOpen)}
            title="切换 trace"
          >
            {active && (
              <>
                <div className="row1">
                  <span className={`dot ${active.status === "ok" ? "ok" : active.status === "fallback" ? "fb" : "warn"}`}></span>
                  <span className={`meal ${active.meal}`}>{active.meal === "lunch" ? "午" : "晚"}</span>
                </div>
                <div className="time mono">{active.time}</div>
                <div className="day mono">
                  {active.daysAgo === 0 ? "今天" : active.daysAgo === 1 ? "昨" : active.daysAgo === 2 ? "前" : `-${active.daysAgo}d`}
                </div>
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
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="搜索…"
                  autoFocus
                />
              </div>
              <div className="tb-rail-pop-list">
                {renderTraceGroups("collapsed")}
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

  // ─── full list view ────────────────────────────────────────
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
            >
              ‹
            </button>
          </span>
        </div>
        <div className="tb-search">
          <span className="icon">⌕</span>
          <input
            data-tb-search
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜餐厅名 / session id"
          />
        </div>
        <div className="tb-filters">
          {FILTER_DEFS.map((f) => (
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
          <select className="sel" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
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
        {renderTraceGroups("full")}
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

function TraceRow({
  trace,
  active,
  isOpen,
  hasRefines,
  mode,
  onRowClick,
  onToggleExpand,
}: {
  trace: TraceMeta;
  active: boolean;
  isOpen: boolean;
  hasRefines: boolean;
  mode: "collapsed" | "full";
  onRowClick: () => void;
  onToggleExpand: () => void;
}) {
  return (
    <div className={`tb-row ${active ? "active" : ""}`} onClick={onRowClick}>
      <div className={`dot ${trace.status === "ok" ? "ok" : trace.status === "fallback" ? "fb" : "warn"}`}></div>
      <div className="body">
        <div className="l1">
          <span className="time">{trace.time}</span>
          <span className={`meal ${trace.meal}`}>{trace.meal === "lunch" ? "午" : "晚"}</span>
          {hasRefines && (
            <span className="rd-badge" style={{ fontSize: 9 }}>
              R{1 + trace.refineCount} ×{1 + trace.refineCount}
            </span>
          )}
          <span className={`src ${trace.source === "sandbox" ? "sbx" : ""}`}>
            {trace.source === "sandbox" ? `SBX D+${trace.sandboxDay}` : "REAL"}
          </span>
        </div>
        <div className="l2">{trace.finalTop1}</div>
        <div className="l3">
          <span className="mono">{trace.latency_ms}ms</span>
          {trace.feedback && <span style={{ marginLeft: 6 }}>{feedbackGlyph(trace.feedback)}</span>}
        </div>
      </div>
      {mode === "full" && hasRefines && (
        <button
          className="chev"
          onClick={(e) => { e.stopPropagation(); onToggleExpand(); }}
          style={{ background: "transparent", border: 0, cursor: "pointer" }}
        >
          {isOpen ? "▾" : "▸"}
        </button>
      )}
    </div>
  );
}

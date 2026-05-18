// panel-l3.jsx — L3 LLM rerank with full I/O exposure + fallback signal

const IO_TABS = [
  { id: "system",   label: "system prompt",  desc: "system_prompt" },
  { id: "user",     label: "user message",   desc: "user_message" },
  { id: "tool",     label: "tool_input",     desc: "forced schema" },
  { id: "raw",      label: "raw response",   desc: "content blocks" },
  { id: "parsed",   label: "parsed",         desc: "top 5 + reason" },
  { id: "fallback", label: "fallback trace", desc: "provider chain" },
  { id: "validator", label: "validator",     desc: "errors / retries" },
];

function MetaCell({ k, v, muted }) {
  return (
    <div className="meta-cell">
      <div className="k">{k}</div>
      <div className={`v ${muted ? "muted" : ""}`}>{v}</div>
    </div>
  );
}

function fmtNum(n) {
  if (n == null) return "—";
  return n.toLocaleString();
}

function PanelL3({ useFallback }) {
  const L3 = useFallback
    ? { ...window.MOCK.L3, ...window.MOCK.L3_FALLBACK_EXAMPLE }
    : window.MOCK.L3;
  const [tab, setTab] = useState("system");
  const [search, setSearch] = useState("");

  const isFallback = L3.status === "fallback";
  const isConfigError = L3.status === "config_error";

  const renderContent = () => {
    switch (tab) {
      case "system":
        return <CodeBlock text={L3.system_prompt} mode="plain" highlightCache />;
      case "user":
        return <CodeBlock text={L3.user_message} mode="plain" />;
      case "tool":
        return <CodeBlock text={L3.tool_input} mode="json" />;
      case "raw":
        return (
          <div style={{ padding: "6px 0" }}>
            {L3.raw_response_blocks.map((b, i) => (
              <div key={i} className="cblock">
                <div className="cblock-head">
                  <span className={`badge ${b.type === "thinking" ? "violet" : b.type === "tool_use" ? "green" : "gray"}`}>
                    {b.type}
                  </span>
                  {b.id && <span className="mono dim">{b.id}</span>}
                  {b.name && <span className="mono dim">name: <span style={{ color: "var(--t-1)" }}>{b.name}</span></span>}
                  <div style={{ marginLeft: "auto" }}><CopyBtn /></div>
                </div>
                {b.type === "tool_use" ? (
                  <CodeBlock text={b.input} mode="json" />
                ) : (
                  <pre>{b.text}</pre>
                )}
              </div>
            ))}
          </div>
        );
      case "parsed":
        return (
          <div className="parsed-list">
            {window.MOCK.FINAL.map((c, i) => (
              <div className="parsed-item" key={c.combo_id}>
                <div className="rk">#{c.rank}</div>
                <div>
                  <div className="row" style={{ gap: 8 }}>
                    <span className="combo-id">{c.combo_id}</span>
                    <span className={`badge ${c.kind === "explore" ? "violet" : "gray"}`}>{c.kind}</span>
                    <span className="who">{c.restaurant}</span>
                  </div>
                  <div className="why">"{c.reason}"</div>
                </div>
                <div className="combo-id">score {c.score.toFixed(3)} · fit {c.fit_score.toFixed(2)}</div>
              </div>
            ))}
          </div>
        );
      case "fallback":
        return (
          <div className="trace-list">
            {L3.fallback_chain.map((s, i) => (
              <div className="trace-step" key={i}>
                <div className="step-num">{s.step}</div>
                <div className="step-body">
                  <div className="name">{s.name}</div>
                  <div className="why">
                    {s.error ? <span style={{ color: "var(--red)" }}>error: {s.error}</span> : "ok"}
                    <span className="dim"> · {s.meta}</span>
                  </div>
                </div>
                <div className="step-meta">
                  <StatusBadge status={s.status === "ok" ? "ok" : s.status === "error" ? "fallback" : "warn"} />
                </div>
              </div>
            ))}
            {!isFallback && L3.fallback_chain.length === 1 && (
              <div className="dim mono" style={{ padding: "8px 14px", fontSize: 11 }}>
                # 主路径直接成功，没有走 fallback
              </div>
            )}
          </div>
        );
      case "validator":
        return (
          <div className="trace-list">
            {L3.validator_errors == null ? (
              <div style={{ padding: "20px 14px", textAlign: "center" }}>
                <StatusBadge status="ok" size="lg" />
                <div className="dim mono" style={{ marginTop: 8, fontSize: 11 }}>
                  # validator passed · 0 retries · 0 errors
                </div>
                <div className="dim" style={{ marginTop: 4, fontSize: 11 }}>
                  D-050 retry-with-feedback 链路未触发（首轮 schema 验证通过）
                </div>
              </div>
            ) : (
              <div>(errors here)</div>
            )}
          </div>
        );
    }
  };

  return (
    <div className={`panel ${isFallback ? "l3-fallback" : ""}`}>
      <div className="panel-head">
        <span className="layer-tag">L3</span>
        <h2>LLM 精排 · rerank</h2>
        <span className="subtitle">top 60 → top 5 + reason</span>
        <div className="right">
          <Pill tone={isFallback ? "red" : "gray"}>latency <span className="mono">{L3.latency_ms}ms</span></Pill>
        </div>
      </div>

      <div className="l3-status-bar">
        <StatusBadge status={L3.status} size="xl" />
        <div className="stack">
          <div className="resolved">
            <span className="key">resolved_provider</span> <span className="sep">·</span>
            <span className="val">{L3.resolved_provider}</span>
            <span className="sep">/</span>
            <span className="val">{L3.model}</span>
            <span className="sep">·</span>
            <span className="key">stop_reason</span> <span className="val">{L3.stop_reason}</span>
            <span className="sep">·</span>
            <span className="key">temperature</span> <span className="val">{L3.temperature}</span>
          </div>
          <div className="resolved" style={{ fontSize: 11 }}>
            <span className="key">session</span> <span className="val">{window.MOCK.session_id}</span>
            <span className="sep">·</span>
            <span className="key">tool_use</span> <span className="val">forced</span>
            <span className="sep">·</span>
            <span className="key">max_tokens</span> <span className="val">{L3.max_tokens}</span>
            <span className="sep">·</span>
            <span className="key">candidates</span> <span className="val">{L3.candidates_returned}</span>
          </div>
        </div>
      </div>

      {isFallback && (
        <div className="callout red">
          <span className="icon">▲</span>
          <div className="body">
            <strong>fallback triggered</strong> — {L3.fallback_reason}
            <div className="dim mono" style={{ marginTop: 4, fontSize: 11 }}>
              # 重试已落地：openrouter / sonnet-4-5 成功。但生产成本与 latency 都偏离基线，建议确认 anthropic 是否仍 overloaded。
            </div>
          </div>
        </div>
      )}

      <div className="meta-grid">
        <MetaCell k="input tokens"       v={fmtNum(L3.input_tokens)} />
        <MetaCell k="output tokens"      v={fmtNum(L3.output_tokens)} />
        <MetaCell k="cache_read input"   v={fmtNum(L3.cache_read_input_tokens)} />
        <MetaCell k="cache_creation"     v={fmtNum(L3.cache_creation_input_tokens)} muted={!L3.cache_creation_input_tokens} />
        <MetaCell k="system prompt chars" v={fmtNum(L3.system_prompt_chars)} />
        <MetaCell k="user message chars" v={fmtNum(L3.user_message_chars)} />
        <MetaCell k="model"              v={L3.model} />
        <MetaCell k="provider"           v={L3.resolved_provider} />
      </div>

      <div className="io-viewer">
        <div className="io-tabs">
          {IO_TABS.map(t => {
            const isErr = t.id === "fallback" && isFallback;
            const isOpen = tab === t.id;
            const count = t.id === "raw" ? L3.raw_response_blocks.length :
                         t.id === "parsed" ? 5 :
                         t.id === "fallback" ? L3.fallback_chain.length :
                         t.id === "validator" ? 0 : null;
            return (
              <button
                key={t.id}
                className={`io-tab ${isOpen ? "active" : ""} ${isErr ? "has-error" : ""}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
                {count != null && <span className="count">{count}</span>}
              </button>
            );
          })}
        </div>
        <div className="io-toolbar">
          <div className="meta">
            <span>{IO_TABS.find(t => t.id === tab).desc}</span>
            {tab === "system" && <span>chars: <span className="mono" style={{ color: "var(--t-1)" }}>{L3.system_prompt_chars}</span></span>}
            {tab === "user" && <span>chars: <span className="mono" style={{ color: "var(--t-1)" }}>{L3.user_message_chars}</span></span>}
            {tab === "system" && (
              <span style={{ color: "var(--violet)" }}>
                <span className="hl-cache" style={{ padding: "0 4px" }}>cache_control</span> 标记已突出
              </span>
            )}
          </div>
          <div className="actions">
            <input
              className="find"
              placeholder="find in text…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <button className="icon-btn">wrap</button>
            <CopyBtn label="copy all" />
          </div>
        </div>
        <div className="io-content">{renderContent()}</div>
      </div>
    </div>
  );
}

window.PanelL3 = PanelL3;

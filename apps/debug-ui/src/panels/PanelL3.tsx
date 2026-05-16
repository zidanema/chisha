import { useState } from "react";
import type { ReactNode } from "react";
import { CodeBlock } from "../components/ui/CodeBlock";
import { CopyBtn } from "../components/ui/CopyBtn";
import { Pill } from "../components/ui/Pill";
import { StatusBadge } from "../components/ui/StatusBadge";
import { ToolUseBlockView } from "../components/ui/ToolUseBlockView";
import type { FinalRow, L3Trace } from "../types/trace";

const IO_TABS = [
  { id: "system", label: "system prompt", desc: "system_prompt" },
  { id: "user", label: "user message", desc: "user_message" },
  { id: "tool", label: "tool_input", desc: "forced schema" },
  { id: "raw", label: "raw response", desc: "content blocks" },
  { id: "parsed", label: "parsed", desc: "top 5 + reason" },
  { id: "fallback", label: "fallback trace", desc: "provider chain" },
  { id: "validator", label: "validator", desc: "errors / retries" },
] as const;

type IoTabId = (typeof IO_TABS)[number]["id"];

function MetaCell({ k, v, muted }: { k: string; v: string; muted?: boolean }) {
  return (
    <div className="meta-cell">
      <div className="k">{k}</div>
      <div className={`v ${muted ? "muted" : ""}`.trim()}>{v}</div>
    </div>
  );
}

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

export function PanelL3({
  l3,
  finalRows,
  sessionId,
}: {
  l3: L3Trace;
  finalRows: FinalRow[];
  sessionId: string;
}) {
  // Caller is responsible for swapping in a fallback-flavoured L3Trace when
  // simulating provider-chain trace. Panel itself is pure data-in.
  const L3 = l3;
  const [tab, setTab] = useState<IoTabId>("system");
  const [search, setSearch] = useState("");

  const isFallback = L3.status === "fallback";
  const isConfigError = L3.status === "config_error";
  const isSkipped = L3.status === "skipped";

  const renderContent = (): ReactNode => {
    switch (tab) {
      case "system":
        return <CodeBlock text={L3.system_prompt} mode="plain" highlightCache searchTerm={search} />;
      case "user":
        return <CodeBlock text={L3.user_message} mode="plain" searchTerm={search} />;
      case "tool":
        return <CodeBlock text={L3.tool_input} mode="json" />;
      case "raw":
        return (
          <div style={{ padding: "6px 0" }}>
            {L3.raw_response_blocks.map((b, i) => {
              const toneCls =
                b.type === "thinking" ? "violet" : b.type === "tool_use" ? "green" : "gray";
              const id = "id" in b ? b.id : undefined;
              const name = "name" in b ? b.name : undefined;
              return (
                <div key={i} className="cblock">
                  <div className="cblock-head">
                    <span className={`badge ${toneCls}`}>{b.type}</span>
                    {id && <span className="mono dim">{id}</span>}
                    {name && (
                      <span className="mono dim">
                        name: <span style={{ color: "var(--t-1)" }}>{name}</span>
                      </span>
                    )}
                    <div style={{ marginLeft: "auto" }}>
                      <CopyBtn />
                    </div>
                  </div>
                  {b.type === "tool_use" ? (
                    <ToolUseBlockView input={b.input} />
                  ) : b.type === "thinking" ? (
                    <CodeBlock text={b.text} mode="plain" searchTerm={search} />
                  ) : (
                    <CodeBlock text={b.text} mode="plain" searchTerm={search} />
                  )}
                </div>
              );
            })}
          </div>
        );
      case "parsed":
        return (
          <div className="parsed-list">
            {finalRows.map((c) => (
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
                <div className="combo-id">
                  score {c.score.toFixed(3)} · fit {c.fit_score.toFixed(2)}
                </div>
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
                    {s.error ? (
                      <span style={{ color: "var(--red)" }}>error: {s.error}</span>
                    ) : (
                      "ok"
                    )}
                    <span className="dim"> · {s.meta}</span>
                  </div>
                </div>
                <div className="step-meta">
                  <StatusBadge status={s.status === "ok" ? "ok" : "fallback"} />
                </div>
              </div>
            ))}
            {!isFallback && L3.fallback_chain.length === 1 && (
              <div className="dim mono" style={{ padding: "8px 14px", fontSize: 11 }}>
                # 主路径直接成功,没有走 fallback
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
                  D-050 retry-with-feedback 链路未触发(首轮 schema 验证通过)
                </div>
              </div>
            ) : (
              <div>
                {L3.validator_errors.map((e, i) => (
                  <div key={i} className="dim" style={{ padding: "4px 14px", color: "var(--red)" }}>
                    {e}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
    }
  };

  const activeTab = IO_TABS.find((t) => t.id === tab) ?? IO_TABS[0];

  const panelClass =
    isFallback ? "panel l3-fallback" :
    isConfigError ? "panel" :
    "panel";
  const panelExtraStyle: React.CSSProperties | undefined =
    isConfigError ? { borderColor: "var(--warn-edge)", boxShadow: "inset 0 0 0 1px var(--warn-edge)" } :
    isSkipped ? { opacity: 0.85 } :
    undefined;

  return (
    <div className={panelClass} style={panelExtraStyle}>
      <div className="panel-head">
        <span className="layer-tag layer-l3">L3</span>
        <h2>LLM 精排 · rerank</h2>
        <span className="subtitle">
          {isSkipped ? "LLM 已跳过 · Final 来自 L2 fallback rerank" : "top 60 → top 5 + reason"}
        </span>
        <div className="right">
          <Pill tone={isFallback ? "red" : isConfigError ? "orange" : isSkipped ? "gray" : "gray"}>
            latency <span className="mono">{L3.latency_ms}ms</span>
          </Pill>
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
            <span className="key">session</span> <span className="val">{sessionId}</span>
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
              # 重试已落地:openrouter / sonnet-4-5 成功。但生产成本与 latency 都偏离基线,建议确认 anthropic 是否仍 overloaded。
            </div>
          </div>
        </div>
      )}

      {isConfigError && (
        <div className="callout" style={{ background: "var(--warn-bg)", borderColor: "var(--warn-edge)" }}>
          <span className="icon" style={{ color: "var(--warn)" }}>▲</span>
          <div className="body">
            <strong style={{ color: "var(--warn)" }}>config_error</strong> — LLM provider 配置错, L3 未跑.
            <div className="dim mono" style={{ marginTop: 4, fontSize: 11 }}>
              # 检查 profile_overrides JSON / LLM provider env vars (CHISHA_LLM_PROVIDER, ANTHROPIC_API_KEY, OPENROUTER_API_KEY).
              <br />
              # Final 5 仍然有 — 来自 L2 fallback rerank (规则化, 没动 LLM).
            </div>
          </div>
        </div>
      )}

      {isSkipped && (
        <div className="callout" style={{ background: "var(--bg-inset)", borderColor: "var(--line-strong)" }}>
          <span className="icon" style={{ color: "var(--t-2)" }}>·</span>
          <div className="body">
            <strong style={{ color: "var(--t-1)" }}>L3 SKIPPED</strong>
            <span className="dim" style={{ marginLeft: 8 }}>LLM rerank 关闭, Final 来自 L2 fallback rerank.</span>
          </div>
        </div>
      )}

      {isSkipped ? null : <div className="meta-grid">
        <MetaCell k="input tokens" v={fmtNum(L3.input_tokens)} />
        <MetaCell k="output tokens" v={fmtNum(L3.output_tokens)} />
        <MetaCell k="cache_read input" v={fmtNum(L3.cache_read_input_tokens)} />
        <MetaCell
          k="cache_creation"
          v={fmtNum(L3.cache_creation_input_tokens)}
          muted={!L3.cache_creation_input_tokens}
        />
        <MetaCell k="system prompt chars" v={fmtNum(L3.system_prompt_chars)} />
        <MetaCell k="user message chars" v={fmtNum(L3.user_message_chars)} />
        <MetaCell k="model" v={L3.model} />
        <MetaCell k="provider" v={L3.resolved_provider} />
      </div>}

      {isSkipped ? null : <div className="io-viewer">
        <div className="io-tabs">
          {IO_TABS.map((t) => {
            const isErr = t.id === "fallback" && isFallback;
            const isOpen = tab === t.id;
            const count =
              t.id === "raw" ? L3.raw_response_blocks.length :
              t.id === "parsed" ? finalRows.length :
              t.id === "fallback" ? L3.fallback_chain.length :
              t.id === "validator" ? (L3.validator_errors?.length ?? 0) :
              null;
            return (
              <button
                key={t.id}
                className={`io-tab ${isOpen ? "active" : ""} ${isErr ? "has-error" : ""}`.trim()}
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
            <span>{activeTab.desc}</span>
            {tab === "system" && (
              <span>
                chars: <span className="mono" style={{ color: "var(--t-1)" }}>{L3.system_prompt_chars}</span>
              </span>
            )}
            {tab === "user" && (
              <span>
                chars: <span className="mono" style={{ color: "var(--t-1)" }}>{L3.user_message_chars}</span>
              </span>
            )}
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
              onChange={(e) => setSearch(e.target.value)}
            />
            <button className="icon-btn">wrap</button>
            <CopyBtn label="copy all" />
          </div>
        </div>
        <div className="io-content" style={{ maxHeight: 600, overflow: "auto" }}>
          {renderContent()}
        </div>
      </div>}
    </div>
  );
}

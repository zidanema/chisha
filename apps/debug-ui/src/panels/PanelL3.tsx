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

// CLI 路径 (claude_code_cli) 不支持 tool_use, 走 text+JSON 直出.
// system_prompt 内的 "# 输出方式" 段会被 _patch_system_prompt_for_cli 替换.
function CliNoToolCallout() {
  return (
    <div
      style={{
        margin: 12,
        padding: "12px 14px",
        border: "1px dashed var(--accent-edge, var(--line))",
        background: "var(--bg-2)",
        borderRadius: 4,
        fontSize: 12,
        color: "var(--t-1)",
        lineHeight: 1.6,
      }}
    >
      <div><strong>CLI 路径不发 tool 定义</strong></div>
      <div style={{ marginTop: 6 }}>
        本次 LLM 调用走 <code>claude_code_cli</code>, CLI 不支持 Anthropic
        tool_use 模式, 因此没有 forced JSON schema 发出. 走 text+JSON 直出路径
        (system_prompt 内 "# 输出方式" 段被 <code>_patch_system_prompt_for_cli</code>
        替换为直出 JSON 指令, 见 <code>chisha/rerank.py:1049</code>). LLM 输出的
        JSON 由调用方解析. 排序仍在 LLM 内部.
      </div>
      <div style={{ marginTop: 6 }} className="dim">
        想看真实 tool spec 切到非 CLI provider (anthropic / openrouter) 重跑一次.
      </div>
    </div>
  );
}

// 老 trace (backend B-004 修复之前生成) 没有写入这个字段. 新 trace 会有.
function OldTraceCallout({ what }: { what: string }) {
  return (
    <div
      style={{
        margin: 12,
        padding: "12px 14px",
        border: "1px dashed var(--warn-edge)",
        background: "var(--bg-2)",
        borderRadius: 4,
        fontSize: 12,
        color: "var(--t-1)",
        lineHeight: 1.6,
      }}
    >
      <div><strong>本条 trace 没记录 {what}</strong></div>
      <div style={{ marginTop: 6 }}>
        backend 写 trace 时增加 <code>system_prompt_full</code> /{" "}
        <code>tool_definition</code> 字段是 2026-05-17 (B-004) 后才落地的.
        在此之前生成的 trace 不含这俩字段, 触发 <code>/api/recommend</code>{" "}
        重新跑一次推荐, 新 trace 就能完整渲染.
      </div>
    </div>
  );
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

  const isCliPath = L3.resolved_provider === "claude_code_cli";

  const renderContent = (): ReactNode => {
    switch (tab) {
      case "system":
        if (!L3.system_prompt) {
          return <OldTraceCallout what="system prompt" />;
        }
        return <CodeBlock text={L3.system_prompt} mode="plain" highlightCache searchTerm={search} />;
      case "user":
        return <CodeBlock text={L3.user_message} mode="plain" searchTerm={search} />;
      case "tool":
        if (isCliPath) {
          return <CliNoToolCallout />;
        }
        if (!L3.tool_input) {
          return <OldTraceCallout what="tool 定义" />;
        }
        return (
          <>
            <CodeBlock text={JSON.stringify(L3.tool_input, null, 2)} mode="json" />
            <div style={{ padding: "8px 12px", fontSize: 11, color: "var(--t-2)", lineHeight: 1.5 }}>
              用法: Anthropic tool_use 当 forced JSON schema 用. 发给 API:
              <code style={{ marginLeft: 4 }}>tools=[…] + tool_choice</code> 强制调用.
              LLM 输出符合 input_schema 的 JSON. <strong>本地不执行任何函数</strong>,
              排序在 LLM 内部.
            </div>
          </>
        );
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

// D-089-S5b: R2+ refine round 的「意图解析 LLM call」可视化 panel.
// 数据来源: refine_intent_v2._llm_parse_v2 -> trace_helpers.serialize_llm_call_trace
// -> backend round.refine_intent_llm -> useWaTrace.fullToRound -> RoundRecord.refine_intent_llm.
//
// 渲染层只读 — 跟 PanelL3 一致的设计: 单 panel + tab 切换 system / user / raw / usage.
// R1 round (无 refine intent 解析) / refine intent LLM 调用失败时, App.tsx 应不挂载本 panel.

import { useState } from "react";
import { CodeBlock } from "../components/ui/CodeBlock";
import { CopyBtn } from "../components/ui/CopyBtn";
import { Pill } from "../components/ui/Pill";
import type { LlmCallTrace } from "../types/trace";

type TabId = "system" | "user" | "raw" | "usage";

const TABS: Array<{ id: TabId; label: string; desc: string }> = [
  { id: "system", label: "system prompt", desc: "parse_refine_intent_v2.md (框架部分)" },
  { id: "user", label: "user input", desc: "用户追问原文" },
  { id: "raw", label: "raw response", desc: "LLM 原始输出 (JSON)" },
  { id: "usage", label: "usage", desc: "tokens / latency / model" },
];

function MetaCell({ k, v }: { k: string; v: string }) {
  return (
    <div className="meta-cell">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

function fmtMs(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${n}ms`;
}

export function PanelRefineIntentLLM({ trace }: { trace: LlmCallTrace }) {
  const [tab, setTab] = useState<TabId>("system");

  const fallback = !!trace.fallback_reason;
  const usage = trace.usage;

  return (
    <section className="panel" data-panel="refine_intent_llm">
      <header className="panel-head">
        <div className="panel-title">
          <span className="layer-label">REFINE INTENT</span>
          <span className="panel-name">意图解析 · LLM call</span>
          {fallback ? (
            <span className="badge red">FALLBACK</span>
          ) : (
            <span className="badge green">OK</span>
          )}
        </div>
        <div className="panel-meta">
          <Pill tone={fallback ? "orange" : "gray"}>{trace.model || "—"}</Pill>
          <Pill>{trace.resolved_provider || "—"}</Pill>
          <Pill>{fmtMs(trace.latency_ms)}</Pill>
        </div>
      </header>

      {fallback && (
        <div className="alert alert-warn">
          <strong>fallback_reason:</strong> {trace.fallback_reason}
          <div className="dim small">
            意图解析 LLM 调用失败 → 降级到 V1 规则解析 (refine_intent.py).
            raw_response 字段可能为空; system_prompt / user_message 仍可看.
          </div>
        </div>
      )}

      <div className="meta-grid">
        <MetaCell k="system prompt chars" v={fmtNum(trace.system_prompt_chars)} />
        <MetaCell k="user message chars" v={fmtNum(trace.user_message_chars)} />
        <MetaCell k="raw response chars" v={fmtNum(trace.raw_response_chars)} />
        <MetaCell k="stop reason" v={trace.stop_reason || "—"} />
        <MetaCell k="temperature" v={String(trace.temperature ?? "—")} />
        <MetaCell k="max tokens" v={fmtNum(trace.max_tokens)} />
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`tab ${tab === t.id ? "active" : ""}`.trim()}
            onClick={() => setTab(t.id)}
          >
            <span className="tab-label">{t.label}</span>
            <span className="tab-desc">{t.desc}</span>
          </button>
        ))}
      </div>

      <div className="tab-content">
        {tab === "system" && (
          <>
            <div className="cblock-head">
              <span className="dim">
                chars: <span className="mono" style={{ color: "var(--t-1)" }}>
                  {trace.system_prompt_chars}
                </span>
              </span>
              <CopyBtn text={trace.system_prompt_full} />
            </div>
            <CodeBlock text={trace.system_prompt_full} mode="plain" />
          </>
        )}
        {tab === "user" && (
          <>
            <div className="cblock-head">
              <span className="dim">
                chars: <span className="mono" style={{ color: "var(--t-1)" }}>
                  {trace.user_message_chars}
                </span>
              </span>
              <CopyBtn text={trace.user_message_full} />
            </div>
            <CodeBlock text={trace.user_message_full} mode="plain" />
          </>
        )}
        {tab === "raw" && (
          <>
            <div className="cblock-head">
              <span className="dim">
                chars: <span className="mono" style={{ color: "var(--t-1)" }}>
                  {trace.raw_response_chars}
                </span>
              </span>
              <CopyBtn text={trace.raw_response} />
            </div>
            <CodeBlock
              text={trace.raw_response || "(空 — LLM 调用失败或返回空)"}
              mode={trace.raw_response.trim().startsWith("{") ? "json" : "plain"}
            />
          </>
        )}
        {tab === "usage" && (
          <div className="meta-grid">
            <MetaCell k="input_tokens" v={fmtNum(usage.input_tokens)} />
            <MetaCell k="output_tokens" v={fmtNum(usage.output_tokens)} />
            <MetaCell k="cache_read_input_tokens" v={fmtNum(usage.cache_read_input_tokens)} />
            <MetaCell k="cache_creation_input_tokens" v={fmtNum(usage.cache_creation_input_tokens)} />
            <MetaCell k="latency_ms" v={fmtMs(trace.latency_ms)} />
            <MetaCell k="model" v={trace.model || "—"} />
            <MetaCell k="resolved_provider" v={trace.resolved_provider || "—"} />
            <MetaCell k="stop_reason" v={trace.stop_reason || "—"} />
          </div>
        )}
      </div>
    </section>
  );
}

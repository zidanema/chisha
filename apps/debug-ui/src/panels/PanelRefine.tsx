import { Pill } from "../components/ui/Pill";
import type { SessionDiff } from "../lib/diffSession";
import type { RefineTrace, Session } from "../types/trace";
import { PanelL1 } from "./PanelL1";
import { PanelL2 } from "./PanelL2";
import { PanelL3 } from "./PanelL3";
import { PanelFinal } from "./PanelFinal";

export function PanelRefine({
  refine,
  secondSession,
  diff,
}: {
  refine: RefineTrace;
  secondSession?: Session;
  diff?: SessionDiff;
}) {
  const R = refine;
  return (
    <div>
      <div className="refine-input-box">
        <div className="session-info">
          <span>
            <span className="dim">parent_session</span>{" "}
            <span style={{ color: "var(--t-0)" }}>{R.parent_session}</span>
          </span>
          <span className="dim">·</span>
          <span>
            <span className="dim">refine_session</span>{" "}
            <span style={{ color: "var(--t-0)" }}>{R.refine_session}</span>
          </span>
          <span className="dim">·</span>
          <Pill tone="violet">
            n={R.summary_kpi.candidates_returned} · explore={R.summary_kpi.explore_n}
          </Pill>
        </div>
        <textarea defaultValue={R.user_text} spellCheck={false} />
        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <button className="btn primary" style={{ width: "auto", padding: "6px 16px" }}>
            ↻ 重跑 refine
          </button>
          <button className="btn" style={{ width: "auto", padding: "6px 12px" }}>清空</button>
          <div
            className="dim mono"
            style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center" }}
          >
            <span>
              last latency{" "}
              <span style={{ color: "var(--t-0)" }}>{R.summary_kpi.total_latency_ms}ms</span>
            </span>
            <span>
              diff_top5 <span style={{ color: "var(--t-0)" }}>{R.summary_kpi.diff_top5}</span>
            </span>
          </div>
        </div>
      </div>

      <div className="pipeline">
        <div className="subhead" style={{ margin: 0, marginBottom: 12 }}>
          链路追溯 · refine pipeline
        </div>
        <div className="pipeline-grid">
          <div className="pipe-step">
            <div className="name">1 · 用户输入</div>
            <div className="desc">原始自然语言</div>
            <div className="out" style={{ fontFamily: "var(--sans)", fontSize: 12 }}>
              "{R.user_text}"
            </div>
            <div className="dim mono" style={{ fontSize: 10 }}>
              chars: {R.user_text.length}
            </div>
          </div>

          <div className="pipe-step">
            <div className="name">2 · parse_feedback</div>
            <div className="desc">LLM 解析 → chips + note + rating</div>
            <div className="out">
              <div className="row between" style={{ fontSize: 10 }}>
                <span className="dim">model</span>
                <span>{R.parse_feedback.llm_call.model}</span>
              </div>
              <div className="row between" style={{ fontSize: 10 }}>
                <span className="dim">latency</span>
                <span>{R.parse_feedback.llm_call.latency_ms}ms</span>
              </div>
              <div className="row between" style={{ fontSize: 10 }}>
                <span className="dim">tokens</span>
                <span>
                  {R.parse_feedback.llm_call.input_tokens} in / {R.parse_feedback.llm_call.output_tokens} out
                </span>
              </div>
              <div className="row between" style={{ fontSize: 10 }}>
                <span className="dim">cache</span>
                <span>{R.parse_feedback.llm_call.cache_read_input_tokens} hit</span>
              </div>
            </div>
            <div>
              <div className="dim mono" style={{ fontSize: 10, marginBottom: 4 }}>chips_hit</div>
              <div className="chips">
                {R.parse_feedback.chips_hit.map((c) => (
                  <span className={`chip ${c.startsWith("avoid") ? "neg" : "hit"}`.trim()} key={c}>
                    {c}
                  </span>
                ))}
              </div>
            </div>
            <div className="dim" style={{ fontSize: 11, lineHeight: 1.5 }}>
              <span className="mono">note:</span> {R.parse_feedback.note}
            </div>
          </div>

          <div className="pipe-step">
            <div className="name">3 · chips_to_taste_hints</div>
            <div className="desc">生成 boost / penalty 字典</div>
            <div className="out">
              <div className="dim mono" style={{ fontSize: 10 }}>boost</div>
              <div className="chips">
                {Object.entries(R.chips_to_taste_hints.boost).flatMap(([dim, vals]) =>
                  Object.entries(vals).map(([k, v]) => (
                    <span className="chip pos" key={dim + k}>
                      {dim}:{k} <span className="mono">+{v}</span>
                    </span>
                  )),
                )}
              </div>
              <div className="dim mono" style={{ fontSize: 10, marginTop: 4 }}>penalty</div>
              <div className="chips">
                {Object.entries(R.chips_to_taste_hints.penalty).flatMap(([dim, vals]) =>
                  Object.entries(vals).map(([k, v]) => (
                    <span className="chip neg" key={dim + k}>
                      {dim}:{k} <span className="mono">{v}</span>
                    </span>
                  )),
                )}
              </div>
            </div>
            <div className="dim" style={{ fontSize: 10 }}>
              用户偏好直接喂回 L2 weight system
            </div>
          </div>

          <div className="pipe-step">
            <div className="name">4 · infer_refine_mood</div>
            <div className="desc">关键词正/负向命中</div>
            <div className="out">
              {R.infer_refine_mood.hits.map((h, i) => (
                <div key={i} className="row" style={{ gap: 8, fontSize: 11 }}>
                  <span
                    className={h.direction === "+" ? "diff-up" : "diff-down"}
                    style={{ fontFamily: "var(--mono)", fontWeight: 600 }}
                  >
                    {h.direction}
                  </span>
                  <span className="mono dim">{h.keyword}</span>
                  <span className="mono" style={{ marginLeft: "auto" }}>→ {h.target}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="dim mono" style={{ fontSize: 10, marginBottom: 4 }}>resolved_mood</div>
              <div className="chips">
                {Object.entries(R.infer_refine_mood.resolved_mood).map(([k, v]) => (
                  <span className={`chip ${v > 0 ? "pos" : "neg"}`} key={k}>
                    {k} <span className="mono">{v > 0 ? "+" : ""}{v}</span>
                  </span>
                ))}
              </div>
            </div>
            <div className="dim" style={{ fontSize: 11 }}>
              <span style={{ color: "var(--orange)" }}>注</span>: 仅在 refine 内生效;首轮已无 mood 入口
            </div>
          </div>
        </div>
      </div>

      <div className="diff-summary">
        <div className="cell">
          <div className="k">新进 top 5</div>
          <div className="v" style={{ color: "var(--green)" }}>+ {R.diff.new_in_top5.length}</div>
        </div>
        <div className="cell">
          <div className="k">被踢出 top 5</div>
          <div className="v" style={{ color: "var(--red)" }}>− {R.diff.dropped_from_top5.length}</div>
        </div>
        <div className="cell">
          <div className="k">排名上移</div>
          <div className="v" style={{ color: "var(--blue)" }}>{R.diff.moved_up.length}</div>
        </div>
        <div className="cell">
          <div className="k">排名下移</div>
          <div className="v">{R.diff.moved_down.length}</div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="layer-tag layer-diff">DIFF</span>
          <h2>第二轮 vs 第一轮</h2>
          <span className="subtitle">top 5 变化明细</span>
        </div>
        <div className="panel-body">
          <table className="tbl" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th style={{ width: 80 }}>变化</th>
                <th>combo</th>
                <th className="right">第一轮 rank</th>
                <th className="right">第二轮 rank</th>
                <th>触发原因</th>
              </tr>
            </thead>
            <tbody>
              {R.diff.new_in_top5[0] && (
                <tr>
                  <td><Pill tone="green">+ 新进</Pill></td>
                  <td>{R.diff.new_in_top5[0]}</td>
                  <td className="right mono dim">—</td>
                  <td className="right mono"><span style={{ color: "var(--green)" }}>#3</span></td>
                  <td className="reason">wetness:soup boost +0.22 · main:fish boost +0.08</td>
                </tr>
              )}
              {R.diff.new_in_top5[1] && (
                <tr>
                  <td><Pill tone="green">+ 新进</Pill></td>
                  <td>{R.diff.new_in_top5[1]}</td>
                  <td className="right mono dim">—</td>
                  <td className="right mono"><span style={{ color: "var(--green)" }}>#4</span></td>
                  <td className="reason">wetness:wet +0.18 · 椰子鸡蒸饺非面/非饭</td>
                </tr>
              )}
              {R.diff.dropped_from_top5[0] && (
                <tr>
                  <td><Pill tone="red">− 踢出</Pill></td>
                  <td>{R.diff.dropped_from_top5[0]}</td>
                  <td className="right mono"><span style={{ color: "var(--red)" }}>#2</span></td>
                  <td className="right mono dim">—</td>
                  <td className="reason">grain:quinoa 命中 grain penalty (-0.30 noodle 不命中但 wet 0)</td>
                </tr>
              )}
              {R.diff.dropped_from_top5[1] && (
                <tr>
                  <td><Pill tone="red">− 踢出</Pill></td>
                  <td>{R.diff.dropped_from_top5[1]}</td>
                  <td className="right mono"><span style={{ color: "var(--red)" }}>#4</span></td>
                  <td className="right mono dim">—</td>
                  <td className="reason">restaurant 命中 -1.0 (用户点名拒绝)</td>
                </tr>
              )}
              <tr>
                <td><Pill tone="blue">↑ 上移</Pill></td>
                <td className="mono">cmb_005 汤先生</td>
                <td className="right mono">#3</td>
                <td className="right mono"><span style={{ color: "var(--blue)" }}>#2</span></td>
                <td className="reason">soup +0.22 加持,wet 重新排到前面</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {secondSession ? (
        <>
          <div className="subhead" style={{ margin: "20px 0 12px" }}>
            第二轮完整 trace · L1 / L2 / L3 / Final
            <span className="count">refine round 2</span>
          </div>
          <PanelL1 l1={secondSession.l1} />
          <PanelL2 l2={secondSession.l2} comboDiff={diff?.combos} />
          <PanelL3
            l3={secondSession.l3}
            finalRows={secondSession.final}
            sessionId={secondSession.session_id}
          />
          <PanelFinal
            rows={secondSession.final}
            totalLatencyMs={secondSession.total_latency_ms}
            finalDiff={diff?.final}
            droppedRows={diff?.droppedFinals ?? []}
          />
        </>
      ) : (
        <div className="panel">
          <div className="panel-head">
            <span className="layer-tag layer-l2r">L2'</span>
            <h2>第二轮 trace</h2>
            <span className="subtitle">点 sidebar「触发 refine」生成</span>
            <div className="right">
              <Pill tone="orange">等待触发</Pill>
            </div>
          </div>
          <div className="panel-body">
            <div
              className="dim mono"
              style={{
                padding: 24, textAlign: "center", fontSize: 12,
                border: "1px dashed var(--line-strong)", borderRadius: 4, background: "var(--bg-inset)",
              }}
            >
              # 二轮 trace 待生成 — 在 sidebar 填反馈后点击「↻ 触发 refine」.
              <br />
              <span style={{ color: "var(--t-3)" }}>
                Phase 3 当前 mock 派生 (按 refine_text 文本做 deterministic perturb).
                Phase 4+ 才接 /api/debug_refine 真链路.
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

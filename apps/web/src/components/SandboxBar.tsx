// D-074 PR-1d: SandboxBar — 顶栏 time-travel 控制 + 沉淀状态.
//
// 设计 (志丹原则):
// 1. 沙盒关闭时完全不渲染 — user web 零侵入
// 2. 沙盒启用时顶部固定 banner, 视觉强标识 (黄底, 区别 prod)
// 3. 「下一天」「+3天」推进虚拟时钟 + 异步触发 L1 抽取
// 4. 「📊 沉淀状态」展开抽屉, 显示当前 L1 prefs + 最近反馈
// 5. 「重置」二次确认, 「退出」保留数据
import { useCallback, useEffect, useState } from "react";
import { sandboxApi, type SandboxInspect, type SandboxState } from "@/lib/sandbox";

const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];

function fmtDate(iso?: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso + "T00:00:00");
    return `${iso} 周${WEEKDAYS[d.getDay()]}`;
  } catch {
    return iso;
  }
}

function l1StatusBadge(state?: SandboxState | null): {
  text: string;
  tone: "info" | "good" | "bad" | "muted";
} {
  const ext = state?.last_l1_extraction;
  if (!ext) return { text: "未抽取", tone: "muted" };
  if (ext.status === "ok") {
    return { text: `L1 ✓ (${ext.based_on_meals ?? 0} 餐)`, tone: "good" };
  }
  if (ext.status === "pending") return { text: "L1 抽取中…", tone: "info" };
  if (ext.status === "failed") {
    return { text: `L1 失败: ${(ext.error || "").slice(0, 40)}`, tone: "bad" };
  }
  return { text: `L1 ${ext.status}`, tone: "muted" };
}

export function SandboxBar({
  state,
  onChange,
}: {
  state: SandboxState;
  onChange: () => void;            // 父组件回调: state 变化后 refetch HomePage 等
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [inspectOpen, setInspectOpen] = useState(false);
  const [inspect, setInspect] = useState<SandboxInspect | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = useCallback(
    async (label: string, fn: () => Promise<unknown>) => {
      setBusy(label);
      setErr(null);
      try {
        await fn();
        onChange();
      } catch (e) {
        setErr(`${label}: ${(e as Error).message}`);
      } finally {
        setBusy(null);
      }
    },
    [onChange],
  );

  const onAdvance = (days: number) =>
    run(`+${days} 天`, () => sandboxApi.advance({ days }));

  const onReset = async () => {
    if (!confirm("重置 sandbox? 所有 sandbox 数据将清空 (prod 数据不动)")) return;
    await run("重置", () => sandboxApi.reset());
  };

  const onDisable = () =>
    run("退出沙盒", () => sandboxApi.disable());

  const onOpenInspect = async () => {
    setInspectOpen(true);
    setErr(null);
    try {
      const data = await sandboxApi.inspect();
      setInspect(data);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  // sandbox 关闭 → 不渲染
  if (!state.enabled) return null;

  const badge = l1StatusBadge(state);
  const toneClass =
    badge.tone === "good"
      ? "bg-emerald-100 text-emerald-700"
      : badge.tone === "bad"
      ? "bg-rose-100 text-rose-700"
      : badge.tone === "info"
      ? "bg-sky-100 text-sky-700"
      : "bg-stone-100 text-stone-600";

  return (
    <>
      <div
        className="sticky top-0 z-40 bg-amber-50 border-b border-amber-300
          text-amber-900 text-[13px] px-4 py-2"
        style={{
          boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        }}
        data-testid="sandbox-bar"
      >
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold">🧪 沙盒模式</span>
          <span>
            Day <b>{state.day_index ?? 1}</b>
            {" · "}模拟 <b>{fmtDate(state.current_date)}</b>
          </span>
          <span
            className={`ml-1 px-2 py-0.5 rounded text-[11px] ${toneClass}`}
            title={state.last_l1_extraction?.at ?? undefined}
          >
            {badge.text}
          </span>

          <div className="ml-auto flex items-center gap-1">
            <button
              className="px-2.5 py-1 rounded border border-amber-400
                bg-white hover:bg-amber-100 disabled:opacity-50"
              onClick={() => onAdvance(1)}
              disabled={!!busy}
            >
              下一天 →
            </button>
            <button
              className="px-2.5 py-1 rounded border border-amber-400
                bg-white hover:bg-amber-100 disabled:opacity-50"
              onClick={() => onAdvance(3)}
              disabled={!!busy}
            >
              +3 天
            </button>
            <button
              className="px-2.5 py-1 rounded border border-amber-400
                bg-white hover:bg-amber-100 disabled:opacity-50"
              onClick={onOpenInspect}
              disabled={!!busy}
            >
              📊 沉淀状态
            </button>
            <button
              className="px-2.5 py-1 rounded border border-rose-400
                bg-rose-50 text-rose-700 hover:bg-rose-100 disabled:opacity-50"
              onClick={onReset}
              disabled={!!busy}
            >
              重置
            </button>
            <button
              className="px-2.5 py-1 rounded border border-stone-300
                bg-white hover:bg-stone-100 disabled:opacity-50"
              onClick={onDisable}
              disabled={!!busy}
            >
              退出沙盒
            </button>
          </div>
        </div>
        {busy && <div className="mt-1 text-[11px] text-amber-700">{busy}…</div>}
        {err && (
          <div className="mt-1 text-[11px] text-rose-700">⚠ {err}</div>
        )}
      </div>

      {inspectOpen && (
        <InspectDrawer
          inspect={inspect}
          onClose={() => {
            setInspectOpen(false);
            setInspect(null);
          }}
        />
      )}
    </>
  );
}


function InspectDrawer({
  inspect,
  onClose,
}: {
  inspect: SandboxInspect | null;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/30 flex items-end sm:items-center justify-center"
      onClick={onClose}
    >
      <div
        className="bg-white w-full sm:w-[640px] max-h-[80vh] overflow-y-auto
          rounded-t-2xl sm:rounded-2xl p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="sandbox-inspect-drawer"
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[15px] font-semibold">📊 沙盒沉淀状态</h3>
          <button className="text-stone-500 hover:text-stone-800" onClick={onClose}>
            ✕
          </button>
        </div>

        {!inspect && (
          <div className="text-[13px] text-stone-500">加载中…</div>
        )}

        {inspect && !inspect.enabled && (
          <div className="text-[13px] text-stone-500">沙盒未启用</div>
        )}

        {inspect && inspect.enabled && (
          <div className="space-y-4 text-[13px]">
            <Section title="当前 L1 长期偏好 (生效)">
              {inspect.long_term_prefs ? (
                <>
                  <div>
                    <span className="font-mono text-emerald-700">boost</span>:{" "}
                    {inspect.long_term_prefs.boost.length
                      ? inspect.long_term_prefs.boost.join(", ")
                      : "(空)"}
                  </div>
                  <div>
                    <span className="font-mono text-rose-700">penalty</span>:{" "}
                    {inspect.long_term_prefs.penalty.length
                      ? inspect.long_term_prefs.penalty.join(", ")
                      : "(空)"}
                  </div>
                  <div className="text-stone-500 text-[11.5px] mt-1">
                    based_on_meals:{" "}
                    {inspect.long_term_prefs.based_on_meals ?? 0}
                    {inspect.long_term_prefs.extracted_at &&
                      ` · ${inspect.long_term_prefs.extracted_at}`}
                  </div>
                  {!!inspect.long_term_prefs.evidence?.length && (
                    <ul className="mt-2 list-disc list-inside text-stone-600 text-[12px]">
                      {inspect.long_term_prefs.evidence.slice(0, 5).map((ev, i) => (
                        <li key={i}>
                          <b>{ev.token}</b>: {ev.rationale}
                        </li>
                      ))}
                    </ul>
                  )}
                  {!!inspect.long_term_prefs.regularities_freetext?.length && (
                    <div className="mt-2 text-stone-500 text-[12px]">
                      regularities:{" "}
                      {inspect.long_term_prefs.regularities_freetext.join(" · ")}
                    </div>
                  )}
                </>
              ) : (
                <div className="text-stone-500">
                  暂无 L1 prefs (still cold-start, 反馈累积 ≥3 次后抽取)
                </div>
              )}
            </Section>

            <Section title={`最近 V1.1 反馈 (${inspect.feedbacks_total ?? 0})`}>
              {inspect.feedbacks_recent?.length ? (
                <ul className="space-y-1 text-[12px]">
                  {inspect.feedbacks_recent.map((fb, i) => (
                    <li
                      key={i}
                      className="font-mono text-stone-600 truncate"
                      title={JSON.stringify(fb)}
                    >
                      {(fb.submitted_at as string)?.slice(0, 19)} ·{" "}
                      rating={String(fb.rating)} · oil=
                      {String(fb.oil_calibration)} · repurchase=
                      {String(fb.repurchase_intent)}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-stone-500">尚无反馈</div>
              )}
            </Section>

            <Section
              title={`已接受 ${inspect.accepted_count ?? 0} 餐 · 最近 meal_log ${
                inspect.meal_log_recent?.length ?? 0
              }`}
            >
              <div className="text-stone-500 text-[12px]">
                (meal_log 写入逻辑由后续 V1.2 补, 当前 sandbox 推荐 → accept
                只写 feedback_store, meal_log 暂为空)
              </div>
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}


function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border border-stone-200 rounded-lg p-3 bg-stone-50">
      <div className="text-[12px] font-semibold text-stone-700 mb-1.5">
        {title}
      </div>
      <div className="text-stone-700">{children}</div>
    </div>
  );
}

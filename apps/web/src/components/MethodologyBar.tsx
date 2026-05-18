// T-P1b-01 顶部 always-on 方法论状态条
// 数据源: chisha/status_bar.py:build_status_bar() (后端派生)
// 三态:
//   1. baseline      = active_methodology labels + l0_protections (始终)
//   2. l0_a/b_block  = 永久保护触发 (refine 撞过敏/dietary_law)
//   3. l0_c_relaxed  = refine 解除 methodology (破戒模式)
// 不破坏现有 StatusBar (meal toggle + regen 按钮), 独立组件挂在它之前.

import type { StatusBarPayload, OverrideEventKind } from "@/lib/types";

const _DIETARY_LAW_LABEL: Record<"vegetarian" | "halal", string> = {
  vegetarian: "素食",
  halal: "清真",
};

const _EVENT_TONE: Record<OverrideEventKind, string> = {
  // 永久保护 — 红色系警示
  l0_a_block: "border-red-400 bg-red-50 text-red-900",
  l0_b_block: "border-red-400 bg-red-50 text-red-900",
  // 破戒模式 — 琥珀色提示, 区别于错误
  l0_c_relaxed: "border-amber-400 bg-amber-50 text-amber-900",
};

const _EVENT_PREFIX: Record<OverrideEventKind, string> = {
  l0_a_block: "🛡️",
  l0_b_block: "🛡️",
  l0_c_relaxed: "⚡",
};

export function MethodologyBar({
  payload,
}: {
  payload: StatusBarPayload | null;
}) {
  if (!payload) return null;
  const { active_methodology, l0_protections } = payload;
  const labels = active_methodology?.labels ?? [];
  const allergies = l0_protections?.allergies ?? [];
  const dietaryLaw = l0_protections?.dietary_law ?? null;
  // Codex LOW: override_events 可能在旧后端响应里缺失, 兜底空数组防 crash
  const overrideEvents = payload.override_events ?? [];

  // baseline 没东西可展示时不渲染 (避免空条占位)
  if (
    labels.length === 0 &&
    allergies.length === 0 &&
    !dietaryLaw &&
    overrideEvents.length === 0
  ) {
    return null;
  }

  return (
    <div
      data-testid="methodology-bar"
      className="mt-3 mb-1 space-y-1.5"
    >
      {/* baseline 行: 方法论 labels + 永久保护 */}
      <div className="flex flex-wrap items-center gap-1.5 text-[11.5px]">
        <span className="text-[color:var(--muted)] mr-1">当前模式</span>
        {labels.map((l) => (
          <span
            key={`label-${l}`}
            className="px-1.5 py-0.5 rounded border border-[color:var(--border)] text-[color:var(--fg)]"
          >
            {l}
          </span>
        ))}
        {allergies.map((a) => (
          <span
            key={`allergy-${a}`}
            className="px-1.5 py-0.5 rounded border border-red-300 bg-red-50 text-red-800"
            title="L0-A 医学风险类约束 (永不可破)"
          >
            过敏:{a}
          </span>
        ))}
        {dietaryLaw && (
          <span
            className="px-1.5 py-0.5 rounded border border-red-300 bg-red-50 text-red-800"
            title="L0-B 身份伦理类约束 (永不可破)"
          >
            {_DIETARY_LAW_LABEL[dietaryLaw]}
          </span>
        )}
      </div>

      {/* override events 行: 本次推荐触发的事件 */}
      {overrideEvents.length > 0 && (
        <div className="space-y-1">
          {overrideEvents.map((ev, i) => (
            <div
              key={`ev-${i}`}
              data-testid={`methodology-event-${ev.kind}`}
              className={`px-2 py-1.5 rounded border text-[12px] ${_EVENT_TONE[ev.kind]}`}
            >
              <span className="mr-1.5" aria-hidden="true">
                {_EVENT_PREFIX[ev.kind]}
              </span>
              {ev.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

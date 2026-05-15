import { LABELS } from "@/lib/labels";
import { cx } from "@/lib/cx";
import type { MealType } from "@/lib/types";

// D-071: mood picker 整块隐藏 (随便/清淡/解馋/轻食 4 chip).
// 方法论 baseline 已固化, 不需要 session 级显式 mood; want_soup 偏好走 refine
// 文本关键词识别 (chisha/refine.py:infer_refine_mood). Mood 类型/LABELS.mood
// 保留供调试台对比能力, 不删 — 仅前端入口移除.

export function StatusBar({
  meal,
  setMeal,
  onRegen,
  regenerating,
}: {
  meal: MealType;
  setMeal: (m: MealType) => void;
  onRegen: () => void;
  regenerating: boolean;
}) {
  return (
    <div className="mt-5 mb-4">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="inline-flex items-center rounded-md border border-[color:var(--border)] overflow-hidden">
          {(["lunch", "dinner"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMeal(m)}
              className={cx(
                "px-3 py-1.5 text-[12.5px] font-medium",
                meal === m
                  ? "bg-[color:var(--fg)] text-[color:var(--bg)]"
                  : "text-[color:var(--muted)] hover:text-[color:var(--fg)]"
              )}
            >
              {LABELS.meal[m]}
            </button>
          ))}
        </div>

        <div className="ml-auto">
          <button
            onClick={onRegen}
            disabled={regenerating}
            className="px-2.5 py-1.5 text-[12.5px] rounded-md border border-[color:var(--border)] hover:border-[color:var(--fg)] disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            <span aria-hidden="true">↻</span>
            {LABELS.ui.regen}
          </button>
        </div>
      </div>
    </div>
  );
}

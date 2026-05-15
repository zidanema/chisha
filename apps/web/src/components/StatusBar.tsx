import { LABELS } from "@/lib/labels";
import { cx } from "@/lib/cx";
import type { MealType, Mood } from "@/lib/types";

export function StatusBar({
  meal,
  setMeal,
  mood,
  setMood,
  onRegen,
  regenerating,
}: {
  meal: MealType;
  setMeal: (m: MealType) => void;
  mood: Mood;
  setMood: (m: Mood) => void;
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

      <div className="mt-3 flex items-center gap-1.5 flex-wrap">
        {LABELS.moodList.map((id) => {
          const active = mood === id;
          return (
            <button
              key={id}
              onClick={() => setMood(id)}
              className={cx(
                "px-2.5 py-0.5 rounded-md text-[12.5px] border",
                active
                  ? "border-[color:var(--accent)] text-[color:var(--accent)] bg-[color:var(--accent-bg)]"
                  : "border-[color:var(--border)] text-[color:var(--muted)] hover:text-[color:var(--fg)] hover:border-[color:var(--fg)]"
              )}
            >
              {LABELS.mood[id]}
            </button>
          );
        })}
      </div>
    </div>
  );
}

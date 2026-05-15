import { useState } from "react";
import { cx } from "@/lib/cx";

export function ChipListEditor({
  value,
  onChange,
  placeholder = "+ 添加",
  tone = "default",
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  tone?: "default" | "bad";
}) {
  const [text, setText] = useState("");

  function add() {
    const v = text.trim();
    if (!v) return;
    if (value.includes(v)) return;
    onChange([...value, v]);
    setText("");
  }
  function remove(v: string) {
    onChange(value.filter((x) => x !== v));
  }

  return (
    <div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {value.map((v) => (
            <span
              key={v}
              className={cx(
                "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[12px] border",
                tone === "bad"
                  ? "border-[color:var(--bad)] text-[color:var(--bad)] bg-[color:var(--bad-bg)]"
                  : "border-[color:var(--border)] text-[color:var(--fg)]"
              )}
            >
              {v}
              <button
                onClick={() => remove(v)}
                className="opacity-50 hover:opacity-100"
                aria-label={`移除 ${v}`}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex rounded-md border border-[color:var(--border)] focus-within:border-[color:var(--fg)]">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder={placeholder}
          className="flex-1 bg-transparent py-1.5 px-2.5 text-[12.5px] focus:outline-none"
        />
        <button
          onClick={add}
          className="px-3 text-[11.5px] border-l border-[color:var(--border)] text-[color:var(--muted)]"
        >
          +
        </button>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { LABELS } from "@/lib/labels";
import { SectionHeader } from "./atoms";

// D-053: 输入框是主角，chip 是 fallback (chip 在下，前缀"或者直接点 ›")。
export function RefineInput({
  disabled,
  onSubmit,
}: {
  disabled: boolean;
  onSubmit: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const placeholders = LABELS.refineInputPlaceholders;
  const [phIdx, setPhIdx] = useState(0);
  useEffect(() => {
    const id = setInterval(
      () => setPhIdx((i) => (i + 1) % placeholders.length),
      3500
    );
    return () => clearInterval(id);
  }, [placeholders.length]);

  function submit(v?: string) {
    const val = (v ?? text).trim();
    if (!val) return;
    onSubmit(val);
    setText("");
  }

  const hasText = text.trim().length > 0;
  return (
    <section className="mt-7">
      <SectionHeader title={LABELS.ui.refineTitle} />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="flex items-stretch rounded-md border border-[color:var(--border)] focus-within:border-[color:var(--fg)] bg-[color:var(--surface)]"
      >
        <span className="self-center pl-3 pr-2 text-[color:var(--muted)] font-mono">›</span>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholders[phIdx]}
          className="flex-1 bg-transparent py-2.5 pr-3 text-[14px] placeholder:text-[color:var(--muted)]/70 focus:outline-none"
          disabled={disabled}
        />
        <button
          type="submit"
          disabled={disabled || !hasText}
          className="px-4 text-[12.5px] font-medium border-l border-[color:var(--border)] disabled:opacity-40"
          style={{
            background: hasText && !disabled ? "var(--accent)" : "transparent",
            color: hasText && !disabled ? "var(--accent-fg)" : "inherit",
          }}
        >
          {LABELS.ui.refineSubmit}
        </button>
      </form>

      <div className="mt-2.5 flex items-center gap-1.5 flex-wrap">
        <span className="text-[11.5px] text-[color:var(--muted)] mr-0.5">或者直接点 ›</span>
        {LABELS.refineChips.map((chip) => (
          <button
            key={chip}
            disabled={disabled}
            onClick={() => submit(chip)}
            className="text-[12.5px] px-2.5 py-1 rounded-md border border-[color:var(--border)] text-[color:var(--fg)] hover:border-[color:var(--accent)] hover:bg-[color:var(--accent-bg)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {chip}
          </button>
        ))}
      </div>
    </section>
  );
}

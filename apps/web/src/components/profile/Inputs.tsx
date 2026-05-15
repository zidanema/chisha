import { useState } from "react";
import { cx } from "@/lib/cx";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1">
        <label className="text-[12.5px] text-[color:var(--fg)] font-mono">{label}</label>
        {hint && <span className="text-[11px] text-[color:var(--muted)]">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

export function FieldGroup({
  title,
  idx,
  hint,
  children,
  defaultOpen = true,
}: {
  title: string;
  idx: string;
  hint?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full px-4 py-3 flex items-baseline gap-2 border-b border-[color:var(--border)] hover:bg-[color:var(--surface-2)]"
      >
        <span className="font-mono text-[11px] text-[color:var(--accent)]">{idx}</span>
        <span className="text-[14px] font-semibold tracking-tight">{title}</span>
        {hint && <span className="text-[11px] text-[color:var(--muted)] ml-1">{hint}</span>}
        <span className="ml-auto text-[12px] text-[color:var(--muted)]">{open ? "▲" : "▼"}</span>
      </button>
      {open && <div className="p-4 space-y-4">{children}</div>}
    </section>
  );
}

export function TextInput({
  value,
  onChange,
  placeholder,
  mono,
  unit,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
  unit?: string;
}) {
  return (
    <div className="flex rounded-md border border-[color:var(--border)] focus-within:border-[color:var(--fg)]">
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cx(
          "flex-1 bg-transparent py-1.5 px-2.5 text-[13px] focus:outline-none",
          mono && "font-mono"
        )}
      />
      {unit && (
        <span className="px-2 self-center text-[11px] text-[color:var(--muted)] font-mono">
          {unit}
        </span>
      )}
    </div>
  );
}

export function NumberInput({
  value,
  onChange,
  min,
  max,
  step = 1,
  unit,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
}) {
  return (
    <div className="flex rounded-md border border-[color:var(--border)] focus-within:border-[color:var(--fg)]">
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) =>
          onChange(e.target.value === "" ? (min ?? 0) : Number(e.target.value))
        }
        className="flex-1 bg-transparent py-1.5 px-2.5 text-[13px] tabular-nums font-mono focus:outline-none"
      />
      {unit && (
        <span className="px-2 self-center text-[11px] text-[color:var(--muted)] font-mono">
          {unit}
        </span>
      )}
    </div>
  );
}

export function Slider({
  value,
  onChange,
  min,
  max,
  step = 1,
  unit = "",
  precision = 0,
}: {
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  precision?: number;
}) {
  return (
    <div>
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="chisha-range w-full"
      />
      <div className="flex justify-between text-[10.5px] text-[color:var(--muted)] font-mono mt-1 tabular-nums">
        <span>
          {Number(min).toFixed(precision)}
          {unit}
        </span>
        <span style={{ color: "var(--fg)" }}>
          {Number(value).toFixed(precision)}
          {unit}
        </span>
        <span>
          {Number(max).toFixed(precision)}
          {unit}
        </span>
      </div>
    </div>
  );
}

export function Toggle({
  value,
  onChange,
  label,
}: {
  value: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <button onClick={() => onChange(!value)} className="flex items-center gap-2">
      <span
        className={cx(
          "w-9 h-5 rounded-full relative transition-colors",
          value ? "bg-[color:var(--accent)]" : "bg-[color:var(--surface-2)]"
        )}
      >
        <span
          className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform"
          style={{ transform: value ? "translateX(16px)" : "none" }}
        />
      </span>
      {label && <span className="text-[12.5px] text-[color:var(--fg)]">{label}</span>}
    </button>
  );
}

export function Select<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: ({ id: T; label: string } | T)[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className="w-full bg-[color:var(--surface)] rounded-md border border-[color:var(--border)] py-1.5 px-2.5 text-[13px] focus:outline-none focus:border-[color:var(--fg)]"
    >
      {options.map((o) => {
        const id = typeof o === "object" ? o.id : (o as T);
        const label = typeof o === "object" ? o.label : (o as string);
        return (
          <option key={id} value={id}>
            {label}
          </option>
        );
      })}
    </select>
  );
}

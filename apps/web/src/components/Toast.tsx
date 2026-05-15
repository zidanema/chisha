export type ToastTone = "default" | "good";

export function Toast({ msg, tone = "default" }: { msg: string; tone?: ToastTone }) {
  if (!msg) return null;
  return (
    <div
      className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-3 py-2 rounded-md text-[12.5px] font-medium shadow-lg"
      style={{
        background: tone === "good" ? "var(--good)" : "var(--accent)",
        color: tone === "good" ? "white" : "var(--accent-fg)",
      }}
    >
      <span className="mr-1.5">→</span>
      {msg}
    </div>
  );
}

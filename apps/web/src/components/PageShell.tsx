import { LABELS } from "@/lib/labels";

export function PageShell({ children }: { children: React.ReactNode }) {
  return <main className="mx-auto max-w-[960px] px-6 pb-16">{children}</main>;
}

export function FooterBar() {
  return (
    <footer className="mx-auto max-w-[960px] px-6 py-6 mt-8 flex justify-center">
      <span
        title={LABELS.ui.versionTip}
        className="text-[10px] text-[color:var(--muted)] opacity-40 hover:opacity-80 transition-opacity cursor-help select-none"
      >
        {LABELS.ui.version}
      </span>
    </footer>
  );
}

// D-093 S-02 APanel: 长期画像 (taste + L1 关键词).
// Codex Q3 iter2: taste color 走 TS map → className, mock 不带 color.
import { useState } from "react";
import type { KeywordEntry, TasteEntry } from "../../types/sandbox";

// taste name → CSS class slug (与 styles.css 内 .taste-color-{slug} 对齐)
const TASTE_COLOR_TOKENS: Record<string, string> = {
  川: "chuan",
  粤: "yue",
  日: "ri",
  东南亚: "dongnan",
  西: "xi",
};

function tasteSlug(name: string): string {
  return TASTE_COLOR_TOKENS[name] ?? "default";
}

export interface APanelProps {
  taste: TasteEntry[];
  keywords: KeywordEntry[];
}

export function APanel({ taste, keywords }: APanelProps) {
  const [open, setOpen] = useState(false);
  const summary = taste
    .slice(0, 3)
    .map((t) => `${t.name} ${Math.floor(t.v * 100)}%`)
    .join(" · ");

  return (
    <section className={`panel ${open ? "" : "compact"}`}>
      <header className="panel-head" onClick={() => setOpen((o) => !o)}>
        <span className="panel-key">A</span>
        <div className="panel-title">
          长期画像 <small>变化慢</small>
        </div>
        <span className="panel-summary">{summary}</span>
        <span className="panel-chev">▾</span>
      </header>
      {open && (
        <div className="panel-body">
          {taste.map((t) => (
            <div className="taste-row" key={t.name}>
              <span className="nm">{t.name}</span>
              <span className="taste-bar">
                <span
                  className={`taste-bar-fill taste-color-${tasteSlug(t.name)}`}
                  data-fill={Math.round(t.v * 100)}
                  style={{ width: `${t.v * 100}%` }}
                />
              </span>
              <span className="taste-val mono">{t.v.toFixed(2)}</span>
              <span
                className={`taste-delta ${
                  t.delta === 0 ? "zero" : t.delta < 0 ? "dn" : ""
                }`}
              >
                {t.delta > 0
                  ? `↑+${t.delta.toFixed(2)}`
                  : t.delta < 0
                    ? `↓${t.delta.toFixed(2)}`
                    : "—"}
              </span>
            </div>
          ))}
          <div className="kw-list">
            <span className="kw-label">L1 关键词:</span>
            {keywords.map((k) => (
              <span key={k.tag} className={`kw ${k.isNew ? "new" : ""}`}>
                {k.tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

// D-088 S-01: Tweaks 极简版 (theme + accent), 持久 localStorage.
// 完整 5 字段 (timelineVariant / rightDensity / showDebugLayer / accent / theme) 是 S-02 的事.
import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
export const ACCENTS = ["#6366f1", "#059669", "#e11d48", "#d97706"] as const;
export type Accent = (typeof ACCENTS)[number];

export type Tweaks = { theme: Theme; accent: Accent };

const ACCENT_PALETTE: Record<Accent, Record<string, string>> = {
  "#6366f1": {
    accent: "#6366f1",
    hover: "#4f46e5",
    soft: "#eef0ff",
    softer: "#f5f6ff",
    ink: "#3730a3",
    ring: "rgba(99,102,241,0.18)",
  },
  "#059669": {
    accent: "#059669",
    hover: "#047857",
    soft: "#ecfdf5",
    softer: "#f0fdf4",
    ink: "#065f46",
    ring: "rgba(5,150,105,0.18)",
  },
  "#e11d48": {
    accent: "#e11d48",
    hover: "#be123c",
    soft: "#ffe4e6",
    softer: "#fff1f2",
    ink: "#9f1239",
    ring: "rgba(225,29,72,0.18)",
  },
  "#d97706": {
    accent: "#d97706",
    hover: "#b45309",
    soft: "#fef3c7",
    softer: "#fffbeb",
    ink: "#92400e",
    ring: "rgba(217,119,6,0.18)",
  },
};

// 与 debug-ui 同前缀 (chisha:theme / chisha:tbCollapsed)
const KEY = "chisha:sandboxTweaks";

const DEFAULT_TWEAKS: Tweaks = { theme: "light", accent: "#6366f1" };

function load(): Tweaks {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const v = JSON.parse(raw) as Partial<Tweaks>;
      const theme = v.theme === "dark" || v.theme === "light" ? v.theme : null;
      const accent =
        v.accent && (ACCENTS as readonly string[]).includes(v.accent)
          ? (v.accent as Accent)
          : null;
      if (theme && accent) return { theme, accent };
    }
  } catch {
    // 坏数据 / 私密模式 fallback
  }
  return DEFAULT_TWEAKS;
}

export function useTweaks() {
  const [tweaks, setTweaksState] = useState<Tweaks>(load);

  useEffect(() => {
    const pal = ACCENT_PALETTE[tweaks.accent];
    const root = document.documentElement;
    root.style.setProperty("--accent", pal.accent);
    root.style.setProperty("--accent-hover", pal.hover);
    root.style.setProperty("--accent-soft", pal.soft);
    root.style.setProperty("--accent-softer", pal.softer);
    root.style.setProperty("--accent-ink", pal.ink);
    root.style.setProperty("--accent-ring", pal.ring);
    document.body.classList.toggle("theme-dark", tweaks.theme === "dark");
    document.body.classList.toggle("theme-light", tweaks.theme === "light");
    try {
      localStorage.setItem(KEY, JSON.stringify(tweaks));
    } catch {
      // 私密模式 fallback
    }
  }, [tweaks]);

  function setTweak<K extends keyof Tweaks>(k: K, v: Tweaks[K]) {
    setTweaksState((t) => ({ ...t, [k]: v }));
  }

  return { tweaks, setTweak };
}

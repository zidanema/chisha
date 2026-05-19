// D-093 S-02: 5-field Tweaks (timelineVariant / rightDensity / showDebugLayer / accent / theme).
// 持久 localStorage chisha:sandboxTweaks; 含 S-01 → S-02 旧数据 migration (合并默认值).
import { useEffect, useState } from "react";
import type { Accent, Theme, Tweaks } from "../types/sandbox";
import { ACCENT_VALUES } from "../types/sandbox";

export type { Tweaks, Accent, Theme } from "../types/sandbox";
export const ACCENTS = ACCENT_VALUES;

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

const KEY = "chisha:sandboxTweaks";

const DEFAULT_TWEAKS: Tweaks = {
  timelineVariant: "bars",
  rightDensity: 1,
  showDebugLayer: true,
  accent: "#6366f1",
  theme: "light",
};

function isValidAccent(v: unknown): v is Accent {
  return typeof v === "string" && (ACCENT_VALUES as readonly string[]).includes(v);
}

function isValidTheme(v: unknown): v is Theme {
  return v === "light" || v === "dark";
}

// S-01 → S-02 migration: 合并默认值, 保留旧有效 key, 丢弃无效 key
function load(): Tweaks {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT_TWEAKS;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const out: Tweaks = { ...DEFAULT_TWEAKS };
    if (parsed.timelineVariant === "bars" || parsed.timelineVariant === "calendar") {
      out.timelineVariant = parsed.timelineVariant;
    }
    if (parsed.rightDensity === 0 || parsed.rightDensity === 1) {
      out.rightDensity = parsed.rightDensity;
    }
    if (typeof parsed.showDebugLayer === "boolean") {
      out.showDebugLayer = parsed.showDebugLayer;
    }
    if (isValidAccent(parsed.accent)) out.accent = parsed.accent;
    if (isValidTheme(parsed.theme)) out.theme = parsed.theme;
    return out;
  } catch {
    return DEFAULT_TWEAKS;
  }
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
    document.body.classList.toggle("density-compact", tweaks.rightDensity === 0);
    try {
      localStorage.setItem(KEY, JSON.stringify(tweaks));
    } catch {
      // private mode fallback
    }
  }, [tweaks]);

  function setTweak<K extends keyof Tweaks>(k: K, v: Tweaks[K]) {
    setTweaksState((t) => ({ ...t, [k]: v }));
  }

  return { tweaks, setTweak };
}

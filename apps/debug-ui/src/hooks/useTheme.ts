import { useEffect, useState } from "react";

export const THEME_IDS = [
  "dark-cool",
  "dark-warm",
  "dark-mono",
  "light-paper",
  "light-modern",
] as const;

export type ThemeId = (typeof THEME_IDS)[number];

const STORAGE_KEY = "chisha:theme";

function defaultByPreference(): ThemeId {
  // System dark mode → dark-cool, light → light-modern. Other 3 themes are
  // user-explicit choices (selected via switcher).
  if (typeof window === "undefined" || !window.matchMedia) return "dark-cool";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark-cool"
    : "light-modern";
}

function readStoredTheme(): ThemeId {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && (THEME_IDS as readonly string[]).includes(stored)) {
      return stored as ThemeId;
    }
  } catch {
    // SSR / privacy mode — fall through
  }
  return defaultByPreference();
}

export function useTheme(): [ThemeId, (next: ThemeId) => void] {
  const [theme, setTheme] = useState<ThemeId>(readStoredTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // ignore
    }
  }, [theme]);

  return [theme, setTheme];
}

import { useEffect, useRef, useState } from "react";
import type { ThemeId } from "../hooks/useTheme";

type ThemeOption = {
  id: ThemeId;
  name: string;
  sub: string;
  swatches: string[];
};

const THEMES: ThemeOption[] = [
  { id: "dark-cool", name: "Dark · Cool", sub: "多色 · 默认",
    swatches: ["#1a1e25", "#6c7689", "oklch(0.74 0.13 195)", "oklch(0.78 0.14 70)", "oklch(0.72 0.14 270)"] },
  { id: "dark-warm", name: "Dark · Warm", sub: "暖灰 · 哑色",
    swatches: ["#1f1a14", "#8a8170", "oklch(0.74 0.08 195)", "oklch(0.74 0.12 60)", "oklch(0.74 0.09 270)"] },
  { id: "dark-mono", name: "Dark · Mono", sub: "单 accent · Linear",
    swatches: ["#14171f", "#6c7689", "oklch(0.72 0.14 270)", "oklch(0.60 0.14 270)", "oklch(0.48 0.14 270)"] },
  { id: "light-paper", name: "Light · Paper", sub: "暖牛皮纸 · IDA",
    swatches: ["#efeae0", "#5a4f3f", "oklch(0.56 0.11 195)", "oklch(0.62 0.14 50)", "oklch(0.50 0.14 270)"] },
  { id: "light-modern", name: "Light · Modern", sub: "冷净白 · GitHub",
    swatches: ["#ffffff", "#4a5260", "oklch(0.62 0.13 195)", "oklch(0.68 0.13 60)", "oklch(0.55 0.14 270)"] },
];

export function ThemeSwitcher({
  theme,
  setTheme,
}: {
  theme: ThemeId;
  setTheme: (t: ThemeId) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const current = THEMES.find((t) => t.id === theme) ?? THEMES[0];

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className="theme-btn" onClick={() => setOpen(!open)}>
        <span className="swatch-row">
          {current.swatches.map((c, i) => (
            <span key={i} className="sw" style={{ background: c }}></span>
          ))}
        </span>
        <span>{current.name}</span>
        <span style={{ color: "var(--t-3)", fontSize: 9 }}>▾</span>
      </button>
      {open && (
        <div className="theme-pop" role="menu">
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 10,
              color: "var(--t-3)",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              padding: "4px 8px 6px",
            }}
          >
            palette
          </div>
          {THEMES.map((t) => (
            <button
              key={t.id}
              className={`theme-opt ${t.id === theme ? "active" : ""}`}
              onClick={() => {
                setTheme(t.id);
                setOpen(false);
              }}
            >
              <span className="swatches">
                {t.swatches.map((c, i) => (
                  <span key={i} className="sw" style={{ background: c }}></span>
                ))}
              </span>
              <span>
                <span className="name">{t.name}</span>
                <div className="sub">{t.sub}</div>
              </span>
              <span
                style={{
                  color: t.id === theme ? "var(--accent)" : "transparent",
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                }}
              >
                ●
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

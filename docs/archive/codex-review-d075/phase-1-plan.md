# Phase 1 plan · 把 design canvas 搬成 Vite + React + TS 项目

## Context

Building a new debug console for "今天吃点啥 (chisha)" recommendation engine.
The user已定稿 a high-fidelity design canvas at `~/chisha/design/`
(NOT git-tracked, sits outside the worktree). It is hand-written React with
inline JSX + babel standalone, 5 palette themes, V12 DAG-style layout.

This Phase 1 job: 1:1 visual port of that canvas into a real Vite + React 18 + TS
project under `apps/debug-ui/`, running with embedded mock data — **NO backend
wiring yet** (Phase 2). User must look at the new project running locally and
say "yes, this is pixel-identical to the canvas" before we proceed.

## Constraints (user-issued, non-negotiable)

1. **No Tailwind / shadcn / antd / any UI library.** Canvas uses plain CSS-var
   system; copy it verbatim.
2. **No visual redesign.** 5 palette themes preserved, every color / font-size /
   padding / radius preserved.
3. **No mock data hardcoded in UI.** Mock lives only in `src/mocks/` for dev
   fallback; Phase 2 replaces with real fetch.
4. **No tests.** Single-user self-hosted tool.
5. **No accessibility / i18n / mobile.** Desktop ≥1440px Chinese only.
6. **Files > 400 lines must be split** (canvas already splits per panel).

## Tech choices

- Vite 5 + React 18 + TypeScript 5
- Package manager: npm (matches existing `apps/web/`)
- React-only state (useState/useEffect/useRef/useMemo/useCallback) — no
  zustand / redux / react-query
- Plain CSS (single `styles.css` imported in `main.tsx`) — no CSS modules / no
  styled-components
- No `react-router` (single SPA with tab state)
- Fonts: Google Fonts CDN (IBM Plex Sans, JetBrains Mono) — same as canvas

## File layout

```
apps/debug-ui/
├── index.html                  # Vite entry (single root div)
├── package.json
├── tsconfig.json
├── vite.config.ts              # proxy /api → http://127.0.0.1:8765
├── README.md                   # local dev + localStorage keys
├── .gitignore
├── src/
│   ├── main.tsx                # ReactDOM.createRoot, import styles.css
│   ├── App.tsx                 # root component (tabs, theme, DAG collapse)
│   ├── styles.css              # COPIED 1:1 from design/styles.css (1544 lines)
│   ├── types/
│   │   └── trace.ts            # Session / L1 / L2KPI / L2Combo / L3 / Final / Refine / RunHistoryRow
│   ├── mocks/
│   │   └── session.ts          # MOCK object — TS port of mock.jsx (typed)
│   ├── components/
│   │   ├── ThemeSwitcher.tsx   # extracted from app.jsx
│   │   ├── Sidebar.tsx         # ← design/sidebar.jsx
│   │   ├── DagHeader.tsx       # ← design/dag-header.jsx (incl. DagArrows)
│   │   └── ui/
│   │       ├── StatusBadge.tsx
│   │       ├── Pill.tsx
│   │       ├── MiniFunnel.tsx
│   │       ├── CopyBtn.tsx
│   │       └── CodeBlock.tsx   # incl. highlightJson helper
│   └── panels/
│       ├── PanelL1.tsx         # ← design/panel-l1.jsx
│       ├── PanelL2.tsx         # ← design/panel-l2.jsx
│       ├── PanelL3.tsx         # ← design/panel-l3.jsx
│       ├── PanelFinal.tsx      # ← design/panel-final.jsx
│       └── PanelRefine.tsx     # ← design/panel-refine.jsx
└── public/                     # (empty — no static assets in Phase 1)
```

Note: `apps/web/` (user-facing SPA, uses Tailwind) is untouched. The new
`apps/debug-ui/` is a separate Vite app on a different port.

## Type definitions (reverse-engineered from mock.jsx)

```ts
// src/types/trace.ts (sketch)
export type FunnelStage = {
  stage: string;
  label: string;
  value: number;
  kind: "dish" | "rest" | "combo";
  dropped: number;
};

export type RestaurantBan = {
  rest: string;
  reason: string;
  detail: string;
  count: number;
};

export type DishDrop = {
  reason: string;
  count: number;
  layer: "hard" | "diversity" | "price";
};

export type L1 = {
  area: string;
  meal: "lunch" | "dinner";
  raw_dishes: number;
  raw_restaurants: number;
  funnel: FunnelStage[];
  restaurant_bans: RestaurantBan[];
  ban_reason_agg: { reason: string; count: number }[];
  dish_drops: DishDrop[];
  top_restaurants: { name: string; combos: number }[];
};

export type L2Weight = { key: string; label: string; w: number };
export type ComboDish = {
  name: string; price: number; oil: string; spicy: string;
  protein_g: number; cook: string; main: string; role: string;
  wetness: string; sweet: string; grain: string;
};
export type L2Combo = {
  combo_id: string; restaurant: string; rank: number;
  total_score: number; fit_score: number;
  eta_min: number; distance_km: number; total_price: number;
  dishes: ComboDish[];
  breakdown: Record<string, number>;
};
export type L2KPI = {
  score_min: string; score_max: string;
  cap_k: number; per_brand_top_k: number; per_restaurant_cap_k: number;
  restaurants_before_cap: number; restaurants_after_cap: number;
  max_combos_one_rest_before: number; max_combos_one_rest_after: number;
};

export type L3Status = "ok" | "fallback" | "config_error" | "skipped";
export type FallbackChainStep = {
  step: number; name: string; status: "ok" | "error";
  meta: string; error: string | null;
};
export type L3 = {
  status: L3Status;
  resolved_provider: string;
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens: number;
  cache_creation_input_tokens: number;
  system_prompt_chars: number;
  user_message_chars: number;
  stop_reason: string;
  max_tokens: number;
  temperature: number;
  candidates_returned: number;
  fallback_chain: FallbackChainStep[];
  fallback_reason?: string;
  system_prompt: string;
  user_message: string;
  tool_input: { name: string; description: string; input_schema: unknown };
  raw_response_blocks: (
    | { type: "thinking"; text: string }
    | { type: "tool_use"; id: string; name: string; input: unknown }
  )[];
  validator_errors: string[] | null;
};

export type FinalRow = {
  rank: number;
  kind: "exploit" | "explore";
  combo_id: string;
  restaurant: string;
  distance_km: number; eta_min: number; total_price: number;
  score: number; fit_score: number;
  dishes: { name: string; price: number }[];
  health_flags: Record<string, boolean>;
  risk_flags: string[];
  reason: string;
};

export type Refine = {
  parent_session: string;
  refine_session: string;
  user_text: string;
  parse_feedback: {
    llm_call: { model: string; latency_ms: number;
                input_tokens: number; output_tokens: number;
                cache_read_input_tokens: number };
    chips_hit: string[];
    note: string;
    rating_taste: number | null;
    want_again: boolean;
  };
  chips_to_taste_hints: {
    boost: Record<string, Record<string, number>>;
    penalty: Record<string, Record<string, number>>;
  };
  infer_refine_mood: {
    triggered: boolean;
    hits: { keyword: string; direction: "+" | "-"; target: string }[];
    resolved_mood: Record<string, number>;
  };
  diff: {
    new_in_top5: string[];
    dropped_from_top5: string[];
    moved_up: { id: string; from: number; to: number }[];
    moved_down: { id: string; from: number; to: number }[];
  };
  summary_kpi: {
    explore_n: number;
    total_latency_ms: number;
    candidates_returned: number;
    diff_top5: number;
  };
};

export type RunHistoryRow = {
  id: string; title: string; time: string;
  status: "ok" | "fallback" | "warn";
  latency: number;
  active: boolean;
};

export type Session = {
  session_id: string;
  started_at: string;
  total_latency_ms: number;
  L1: L1;
  L2_WEIGHTS: L2Weight[];
  L2_COMBOS: L2Combo[];
  L2_KPI: L2KPI;
  L3: L3;
  L3_FALLBACK_EXAMPLE: L3;
  FINAL: FinalRow[];
  REFINE: Refine;
  RUN_HISTORY: RunHistoryRow[];
};
```

## Key behaviors to preserve from app.jsx

1. `useTheme` hook — localStorage key `chisha:theme`, default `dark-cool`,
   sets `data-theme` on `<html>`
2. Tab state (`main / refine / trace`)
3. DAG auto-collapse on scroll past 120px (with 700ms intent-debounce so a
   programmatic scroll doesn't toggle)
4. IntersectionObserver tracks which panel is in view (`-280px 0px -50% 0px`
   rootMargin) → updates `currentPanel`
5. `pulseRunning` 1200ms class toggle on DAG
6. `handleNodeClick`: collapse DAG → set currentPanel → 2× rAF → scrollTo
7. `runningPulse` className, `useFallback` toggle via active-session === sess_a7f0
8. `MOCK` global → in TS, import from `mocks/session.ts` and pass as props or
   via a `SessionContext`

## Phase 1 deliverable demo

```bash
cd apps/debug-ui
npm install
npm run dev   # → http://localhost:5173
```

Expect:
- Visual pixel-identical to running `~/chisha/design/index.html`
- All 5 palette themes switch correctly (data-theme + localStorage)
- DAG collapses on scroll, expands on click
- All 4 panels (L1 / L2 / L3 / Final) render with mock data
- Refine tab renders the partial design (upper pipeline only — Phase 3 补)
- Trace tab is disabled (matches `disabled: true` in design TABS)
- TypeScript strict mode, zero `any` / `as any` / `@ts-ignore`
- All files ≤ 400 lines (canvas already splits, ours should too)

## What's deliberately OUT of Phase 1

- Real API fetch (Phase 2)
- Refine bottom half (Phase 3)
- Trace tab implementation (Phase 4)
- Keyboard shortcuts (Phase 5)
- Error states wiring (Phase 6)
- Vite proxy setup is included but no requests fire yet (Phase 2 hooks up)

## Open questions for Codex

1. **State-passing strategy**: pass `Session` down as prop from App to all
   panels, or use a `SessionContext`? My instinct: simple prop drilling for
   Phase 1 (single session in flight, ≤3 layers deep), avoid context boilerplate.
   Does Codex agree?

2. **Mock import**: canvas uses `window.MOCK` global. Converting to ES module
   means each panel needs `import { MOCK } from "@/mocks/session"` OR App
   passes `session` prop. The latter is cleaner and aligns with Phase 2's
   "session loaded from API" pattern. Confirm?

3. **Theme switcher localStorage SSR-safety**: Vite SPA has no SSR, so
   `typeof localStorage !== "undefined"` guard in canvas is technically
   unnecessary. Keep it (harmless, defensive) or drop it (one line less)?
   I'd keep it.

4. **`DagArrows` measurement**: canvas uses `useEffect` to measure
   `.dag-canvas` clientWidth and recompute on resize. In TS, do we type the
   resize handler properly with `WindowEventMap`? Tedious for one line.
   Suggest plain `() => onResize()` callback — Codex sanity-check?

5. **Strict mode**: enable React StrictMode in `main.tsx`? It will cause the
   IntersectionObserver `useEffect` to fire twice in dev, which is harmless
   (re-observes same elements) but could log warnings. Suggest **yes, enable**
   — catches bugs early. Agree?

6. **`window.useState` etc. in ui.jsx**: canvas does `const { useState, useEffect } = React` at top of ui.jsx so it's globally available. In ES modules each
   file imports from `react`. Already accounted for — just flagging.

7. **CSS preservation**: 1544-line styles.css copied verbatim. Any concern
   about scoping leakage given this is a single-app SPA? I think no — all
   selectors are well-namespaced (`.dag-header`, `.sidebar`, `.combo-row`).

8. **Vite config**: `proxy: { "/api": "http://127.0.0.1:8765" }` for Phase 2
   readiness. Also `server.host: "127.0.0.1"`. Anything else expected?

## What I want from Codex

- Spot any bugs in this plan
- Confirm or correct decisions on the 8 questions above
- Flag any architectural choice that would block Phase 2-7 (e.g. "if you
  do X now you'll regret it when you wire fetch")
- Suggest simpler alternatives where applicable

I want a real consensus before kicking off — not a rubber stamp.

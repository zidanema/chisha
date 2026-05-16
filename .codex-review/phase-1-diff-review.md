# Phase 1 code-diff review request (chisha debug-ui)

## What this is
Phase 1 of the chisha debug console build-out is complete. All files are **staged
but not yet committed** in worktree `~/chisha/.claude/worktrees/debugger-web`.
Branch: `main`. Read the diff with:

```bash
git -C ~/chisha/.claude/worktrees/debugger-web diff --cached
```

## Context (in case the design-review thread isn't loaded)
- New Vite + React 18 + TS app at `apps/debug-ui/`, port 5174, proxy `/api → :8765`
- Visual port of `~/chisha/design/` (NOT git-tracked) — same CSS
  vars, same components, same DAG layout. Source of truth: `design/index.html`.
- No backend wiring this phase. Mock data in `src/mocks/session.ts` (LCG seed=42
  to match canvas pixel-for-pixel).
- Phase 0 design review already happened (you flagged 8 issues; 7 accepted, 1
  rejected: Google Fonts CDN self-hosting — overkill for single-user tool).

## Specific items to verify

1. **Visual fidelity to canvas**: did anything drift from `design/`? Spot-check
   `apps/debug-ui/src/styles.css` vs `design/styles.css` (should be byte-identical
   except for the utility color-var block I added at lines ~75-92 to fix the
   undefined `--blue/--red/--green/--orange/--violet` you flagged).
2. **Codex issues from Phase 0 design review**: were all fixed correctly?
   - #2 missing color vars → `apps/debug-ui/src/styles.css` lines ~77-92
   - #3 defensive breakdown access → `apps/debug-ui/src/panels/L2Heatmap.tsx`
     `ComboHeatmapRow`
   - #4 DAG-header hardcoded numbers → `apps/debug-ui/src/components/DagHeader.tsx`
     `buildNodes()`. Verify nothing is still a literal.
   - #7 PanelL2 split → three files at `apps/debug-ui/src/panels/L2*.tsx`
   - #8 port 5174 → `apps/debug-ui/vite.config.ts`
3. **TS strictness**: any `any` / `as any` / `@ts-ignore` snuck in? `tsc -b` is
   currently clean.
4. **React StrictMode side-effects**: any effect in Phase 1 that double-fire
   could leak (event listeners not cleaned, intervals, observers)? Review
   `App.tsx` scroll effect + IntersectionObserver effect, `DagHeader.tsx`
   resize handler, `ThemeSwitcher.tsx` click-outside.
5. **File sizes**: all TSX files under 400 lines per the project rule? (Quick
   check: largest is `DagHeader.tsx` at 301, `PanelL3.tsx` at 298.)
6. **Mock data leakage**: `PanelL3.tsx` imports `L3_FALLBACK_EXAMPLE` from
   `mocks/session.ts`. This is dev-only fallback overlay — flag as Phase 2 work
   to extract this out so the panel becomes pure data-in?
7. **Anything else** that will bite us in Phase 2 (when fetch lands), Phase 3
   (when refine second-round trace renders), or Phase 5 (when keyboard
   shortcuts get layered on)?

## What I want back
- A "ship it" / "fix these N things first" verdict.
- Specific file:line for any concern, with severity (BLOCKER / FIX-NOW / DEFER).
- Don't pull punches. If I missed something subtle in the IntersectionObserver
  rootMargin math or the LCG seed reproducibility, say so.
- 200-400 字中文,结构化。

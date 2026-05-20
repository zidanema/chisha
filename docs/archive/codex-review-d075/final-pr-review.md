# Final whole-PR review request — chisha debug-ui Phase 1-7

## What landed
- 55 files, 9915 insertions, staged 未 commit.
- Single PR scope: new `apps/debug-ui/` Vite SPA + 2 small `chisha/debug_recommend.py`
  backend patches (`_llm_rerank_traced` + `_trace_target`).

## My self-verification (objective facts)
- `npm run typecheck`: ✅ clean, no warnings.
- `npm run build`: ✅ 246KB JS / 39KB CSS gzipped.
- All TS/TSX component files ≤ 400 lines (App.tsx 379, PanelL3 335, adapter 373).
- `mocks/session.ts` 457 lines (data file, exempt by Phase 7 README rule).
- `styles.css` 1562 lines (data, exempt).
- E2E live smoke (worktree venv backend on :8765 + Vite :5174 proxy):
  - `GET /api/profile` → 200
  - `POST /api/debug_recommend` → 200, 358KB, zone=shenzhen-bay, n_combos=2467, top=54, final=5
  - `POST /api/debug_recommend?trace_target=…` → 200, matched 50 dishes
  - Phase 4 patch verified: `nutrition_profile` ships with all 10 fields
    (oil_level=1 int, wetness=1 int, spicy_level=0 int, etc.)
  - Phase 2 patch verified via direct `inspect.getsource` import: `system_prompt_full` /
    `max_tokens` / `temperature` keys present in `_llm_rerank_traced` return dict.
    Not exercised by smoke (use_llm_rerank=false) — needs LLM key + token spend.

## Specifically I want you to verify

1. **All Codex feedback across 7 phases truly resolved?** Phase 1 had 8 issues
   (6 accepted + 1 rejected font self-host + 1 disputed CSS scope). Phase 2: 3
   FIX-NOW (localStorage 8 + race guard + DIM_ORDER). Phase 3: 2 BLOCKER (delta
   abs / dropped final cards). Phase 4: 1 BLOCKER (full config in runTrace) + 1
   FIX-NOW (np补丁). Phase 5: 2 FIX-NOW (CollapsedJson maxDepth + App.tsx <400).
   Phase 6: 4 FIX-NOW (numeric labels + zone + L3 status branches + empty hint).
   Phase 7: 1 FIX-NOW (README wording on config_error). Spot-check each fix
   actually landed in the diff, not just promised.

2. **Backend patches non-invasive**: read `chisha/debug_recommend.py` diff and
   confirm (a) `_llm_rerank_traced` change only ADDS fields, doesn't touch
   existing return keys; (b) `_trace_target` only ADDS `price` + `nutrition_profile`
   to matched_dishes entries; (c) no impact on prod recommend path (apps/web 用
   户视图)。

3. **Visual consistency vs design canvas**: I can't run a screenshot diff. Spot-check
   that the styles.css copied at byte-level matches `~/chisha/design/styles.css`
   except the utility color-var block I added (lines ~77-92).

4. **Type safety**: any remaining `any` / `as any` / `@ts-ignore` / overly broad
   `unknown` that hides real bugs? Especially in adapter.ts (370 lines, lots of
   field renames) and backend-types.ts.

5. **React hook ordering**: I added `useKeyboardShortcuts` in App.tsx between
   `useTrace()` and the run callbacks (function declarations, hoisted). Verify
   hook order is consistent across renders and the dependency arrays in the
   useEffect inside useKeyboardShortcuts catch stale closures correctly.

6. **localStorage MAX_ITEMS=8 真的够 quota 安全**: each session ~358KB JSON ×
   UTF-16 2 bytes/char ≈ 700KB. 8 × 700KB ≈ 5.6MB. localStorage 配额各浏览器
   typically 5-10MB. Borderline. Suggest 5? Or stripping payload to just history
   metadata?

7. **README accuracy**: any feature in code that README doesn't mention, or
   vice versa? README at `apps/debug-ui/README.md`.

8. **Commit readiness**: any reason NOT to commit as-is (e.g. WIP marker,
   half-done refactor, broken cross-references)?

## Format

中文 300-500 字, BLOCKER / FIX-NOW / DEFER. 列举每个 phase 是否真修, 找还未发现
的 issue. 不留尾巴 — 这是最后一关.

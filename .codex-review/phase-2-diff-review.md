# Phase 2 code-diff review (chisha debug-ui)

## What's in this diff
- Phase 1 (already reviewed) + Phase 2 additions, all staged. Run
  `git -C ~/chisha/.claude/worktrees/debugger-web diff --cached`.
- New files:
  - `apps/debug-ui/src/api/backend-types.ts` — raw backend shapes mirroring
    `chisha/debug_recommend.py`
  - `apps/debug-ui/src/api/adapter.ts` — pure `backendToSession(raw, opts)`
  - `apps/debug-ui/src/api/client.ts` — `fetchJson` + `postDebugRecommend` +
    `getProfile`
  - `apps/debug-ui/src/hooks/useSession.ts` — runMain + history state
  - `apps/debug-ui/src/components/Toaster.tsx` — fixed-position toast
  - `apps/debug-ui/src/lib/sessionCache.ts` — localStorage-backed history
    (deferred backend persistence to Phase 7)
- Modified:
  - `apps/debug-ui/src/App.tsx` — uses useSession, runs profile-JSON live
    validation, toggles backend status pill (live / running / offline / error)
  - `apps/debug-ui/src/components/Sidebar.tsx` — `profileError` + `runDisabled`
    props, red border on invalid JSON, disabled style on Run button
  - `chisha/debug_recommend.py` — `_llm_rerank_traced` now also returns
    `system_prompt_full` / `max_tokens` / `temperature` so the L3 IO viewer
    has something to render

## E2E smoke test passed
- backend boots :8765, `/api/profile` 200, `/api/debug_recommend` 200 with
  shape `{config, context, l1_recall, l2_score, l3_rerank, final, target_trace}`.
- Vite proxy :5174 → :8765 reaches backend; full trace 358KB,
  l1.summary.n_combos=2467, l2.top=54, final=5.
- typecheck + build green.
- LLM path NOT exercised in smoke (use_llm_rerank=false); the
  `system_prompt_full` augmentation is in the success branch only.

## Specifically check
1. **Adapter correctness against REAL backend shape**: I read
   `chisha/debug_recommend.py:283` (l1_recall summary), `:545` (l2_score), `:425`
   (l3_rerank.llm), `:666` (final) before writing the adapter. Verify
   `apps/debug-ui/src/api/adapter.ts` against those — anything still wrong?
2. **L1 funnel synthesis** in adapter (`synthFunnel`): I derive 7 stages from
   summary deltas. Are the stage labels accurate? Could `after_diversity_filter`
   < `n_restaurants_with_combos` flip a dropped count negative? My `Math.max(0,..)`
   guard should prevent it, but flag if you see edge cases.
3. **`classifyDropLayer` regex**: a backend reason string like "辣度 4 > 上限 2"
   — does my keyword check ("price/价格/¥/budget" → price, "多样/diversity/重复"
   → diversity, else hard) cover the real `_group_drops_by_reason` strings? Or
   should I rely on which dict the entry came from (already encoded by
   `dropped_hard_by_reason` vs `dropped_diversity_by_reason`)?
4. **L2 weights → array order**: backend returns `weights` as Python dict.
   `Object.entries(weightsDict)` preserves insertion order in modern V8 but the
   heatmap column order will now follow whatever Python dict insertion order
   was. The frontend mock had a specific order (fit_diet, protein_density, ...).
   Risk of visual jitter when ordering shifts? Worth sorting by `Math.abs(w)`
   descending?
5. **`adaptL3` when LLM skipped**: returns a typed shell with `status: "skipped"`
   so PanelL3 doesn't crash. The PanelL3 io-tabs will still all render — visually
   ugly. Worth a Phase 6 task to hide IO viewer when status=skipped, or fix
   now?
6. **Error handling**: 1 `ApiError` shape (status, code, message). The
   `code: "NETWORK"` distinguishes backend-offline from server errors. All errors
   currently funnel to `useSession` → toast + state. Is anything getting
   swallowed?
7. **Mock fallback toggle**: `activeSessionId === "sess_a7f0"` still triggers
   the mock fallback overlay even when a real session is loaded. Is that
   correct behavior or accidentally entangled?
8. **StrictMode side-effects**: useSession's `useEffect` adds a `focus`
   listener with cleanup — should be safe. Anything else?
9. **localStorage** in `sessionCache.ts`: 358KB session × 30 = ~10MB, well
   under 5-10MB localStorage quota typically. Should I cap MAX_ITEMS lower
   or drop the payload (keep just metadata)?
10. **Backend patch** at `chisha/debug_recommend.py:425`: I re-read
    SYSTEM_PROMPT_PATH inside `_llm_rerank_traced`. If the file disappears or
    permissions changed mid-process, the try/except catches it and returns
    `system_prompt_full=""`. Acceptable, or should the call fail loudly?

## Stuff I deliberately DEFERRED
- `/api/refine` wire (Phase 3 needs `/api/debug_refine` first since current
  `/api/refine` is user-view-only with session_id from a separate user store).
- `/api/sessions` + `/api/session/{id}` backend persistence (Phase 7).
- LLM-path exercised smoke (need real API key + accept the spend).
- backend zone code → Chinese label mapping ("shenzhen-bay" → "深圳湾办公区";
  Phase 6 cosmetic).
- L1/L2 latency_ms (backend doesn't break down by layer; passed 0 for now).

## What I want back
- "ship it" / "fix these N things first"
- BLOCKER / FIX-NOW / DEFER markers with file:line + 1-sentence reason
- Don't pull punches. Especially on the adapter — it's the part most likely
  to leak wrong data.
- 中文 200-400 字。

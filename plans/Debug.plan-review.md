# Debug.plan Audit — Three Rounds

## Round 1 (initial plan)

VERDICT: BLOCKED — 5 issues
1. B1 reset can still race unless keyed to loaded `trace.meta.latestRound`.
2. B3 `null as unknown as` would be runtime-unsafe; skeleton must cover all nested fields including `RoundBanner`.
3. B4 modifies the wrong backend path — TraceBrowser reads from `web_api._attach_feedback_to_meta`, not `trace_store.attach_feedback_links`.
4. B6 root cause is adapter conversion of `config_error` to `skipped` at `adapter.ts:210-234` — plan must name and fix this before any copy change.
5. Test coverage misses adapter test, `/api/traces` integration, and panel rendering for B3/B6.

## Round 2 (after revision)

VERDICT: BLOCKED — 3 issues
1. B1 race guard placed in App.tsx is too late — stale `setActiveTrace(wa)` already commits inside useWaTrace. Move guard into useWaTrace before setActiveTrace.
2. B6 test coverage misclassified — backend Python tests don't execute TypeScript adapter. Need chrome-devtools-mcp DOM assertion.
3. B5 StrictMode reasoning wrong — `[backendOnline]` dep doesn't suppress StrictMode dev double-effect. Use AbortController + accept dev-only N+1.

(Q3 B3/B6 collision was confirmed SOUND — empty skeleton's status:"skipped" only held while __partial:true, full data overwrites.)

## Round 3 (after second revision)

VERDICT: BLOCKED — 1 issue
- B5 StrictMode: RESOLVED (AbortController + honest dev-only acceptance)
- B6 e2e assertion: RESOLVED (DOM assert CONFIG_ERROR present + 老文案 absent + fallback_reason fragment, plus backend contract test)
- **B1 stale guard: STILL-BLOCKED** — success path correctly guards `setActiveTrace(wa)`, but the catch path at `useWaTrace.ts:230-238` still has `setActiveTrace(getMockTrace(activeTraceId))` without symmetric `if (cancelled || myId !== activeTraceIdRef.current) return;` guard.

Fix: mirror the stale-guard check at the top of the catch block.

## Round 3 disposition

Codex's remaining issue is mechanical, not a design disagreement: add the same 1-line guard to the catch path. Per max-3-iteration rule, plan was updated inline to include the catch-path guard (see plan "race 防护" section). Proceeding to Phase 3 with both success-path AND catch-path stale guards.

VERDICT: CONDITIONALLY APPROVED (with inline catch-path patch)

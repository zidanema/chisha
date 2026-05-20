# T-PR-03 Phase 4 iter 1 adversarial diff review

**scope**: chisha/rerank.py + prompts/rerank_system.md (uncommitted diff)
**plan ref**: plans/T-PR-03.plan.md iter 3 APPROVED
**date**: 2026-05-20

---

## 1. correctness bugs

- [NON-BLOCKING] prompts/rerank_system.md:23-30: 重排原则 list renumbered 1-6, 多样性 at item 6, 健康风险披露 section starts at :32. No numbering or placement failure detected.
- [NON-BLOCKING] prompts/rerank_system.md:75 + :136: `# 输出方式` anchor intact; `select_top_candidates` + `现在等待` still present. `_patch_system_prompt_for_cli` (rerank.py:158+172) unbroken.

## 2. design

- [NON-BLOCKING] prompts/rerank_system.md:34: New text correctly instructs L3 not to re-demote or hard-filter what L2 already weighted — aligned with D-090 slot-aware guardrail (CONTRACTS.md:37).
- [NON-BLOCKING] prompts/rerank_system.md:36 vs :63: `sweet_sauce_level 0-3` in new section but field table still says `甜 N | 2-5` (display rule). Internal inconsistency in surface form (storage range vs display range); not a breaking failure today (threshold logic in score.py:245 is authoritative). Worth a follow-up fix in T-PR-06 (P1 文案补丁).

## 3. regression surface

- [NON-BLOCKING] chisha/rerank.py:1212: Retry correction string updated to reference actual prompt heading at rerank_system.md:32; does not instruct model to rank by health. Retry still limited to CLI validate-fail path (rerank.py:1185). Length increase (~25 chars) is negligible against 15K input.
- [NON-BLOCKING] chisha/rerank.py:1096: Main tool-use path unchanged; retry path is CLI-only.

## 4. test coverage gap

- [NON-BLOCKING] tests/test_rerank.py:532: Prompt anchor tests would not fail if health_risk_disclosure section were deleted while `# 输出方式` remained. No test asserts presence of 健康风险披露 section by content.
- [NON-BLOCKING] tests/test_rerank.py:727: No case exercises oil_avg > 4, processed side-dish, or 甜 N >= 3 disclosure text in L3 narrative output. Effective tests for this class of change: eval fixture with a candidate set containing a high-oil + processed item, assert disclosure phrase appears in top-item narrative; assert no hard-filter (item still ranked, not absent). Currently not covered. **Defer to T-PR-07 manual verification or post-Step-1 eval extension**.

## 5. cross-file invariants

- [NON-BLOCKING] prompts/rerank_system.md:38: Explicitly forbids claiming health risks were filtered or avoided — matches D-085 narrative non-deception prohibition (CONTRACTS.md:16+61). Clearly enforceable.
- [NON-BLOCKING] prompts/rerank_system.md:36: `oil_avg > 4` maps to score.py:606; `甜 N >= 3` maps to score.py:610. Processed disclosure is semantically broader than `health_guardrail` but grounded in score.py:231 processed-meat slot. No contradiction with D-090.

## 6. prod-time failure modes

- [NON-BLOCKING] chisha/rerank.py:1090: CLI retry uses max_tokens=4096; added phrase at :1212 does not approach any input-size boundary (input ~15K tokens, well under context limit).
- [NON-BLOCKING] chisha/rerank.py:1218: Retry reuses same kwargs, only changes user message; failed retry falls through to :1245 as before. No new failure mode introduced.

---

After adversarial pass I cannot find a blocking issue.

Non-blocking summary (defer to follow-up tasks):
1. Sweet-range surface inconsistency: `sweet_sauce_level 0-3` (new section) vs `甜 N | 2-5` (display rule field table) — follow-up fix in T-PR-06 (P1 文案补丁).
2. No health-risk-disclosure semantic test — defer to T-PR-07 manual verification or post-Step-1 eval extension.
3. Processed disclosure slightly broader than `health_guardrail` definition — acceptable given score.py backing, no action required.

baseline_l2_snapshot before/after: 0 diff ✓ (D-072.1 守门通过).
全测试: 968 passed, 6 skipped, 0 regressions ✓.

VERDICT: APPROVED

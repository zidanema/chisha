## Iter 1

VERDICT: BLOCKED

1. `plans/T-PR-02.plan.md:16`-`21` changes the task from guarding T-PR-01 prompt boundaries into guarding V1 fallback behavior. The spec asks for cases covering the six prompt-boundary scenarios in `specs/T-PR-02.md:7`-`14`; several expected outcomes are LLM/V2 semantics (`delivery_only=true`, `reject_previous=true`, `cuisine_avoid=["广东菜"]`). The plan's `use_llm=False` assertions explicitly expect the opposite for delivery and full reject at `plans/T-PR-02.plan.md:29` and `plans/T-PR-02.plan.md:32`.

2. `plans/T-PR-02.plan.md:27` contradicts the first What case. `specs/T-PR-02.md:9` expects flavor-related fields empty and `raw_understanding` to indicate conflict/uncertainty. The plan instead asserts V1 `legacy_v1.flavor_tags=['spicy']`, which I verified is current behavior, but it does not guard the requested boundary and may normalize the exact over-interpretation the prompt change is meant to prevent.

3. `plans/T-PR-02.plan.md:29` and `plans/T-PR-02.plan.md:42` under-cover explicit positive semantics. `specs/T-PR-02.md:11` requires `"今天只吃外卖"` -> `delivery_only=true`, and `specs/T-PR-02.md:14` requires `"上一组全不要, 重来"` -> `reject_previous=true`. The actual `from_legacy` implementation writes `constrain=_empty_constrain()` and `reject_previous=False` in `chisha/refine_intent_v2.py:131`-`135`, so the proposed tests would pass because V1 cannot express the feature, not because the boundary is protected.

4. `plans/T-PR-02.plan.md:31` and `plans/T-PR-02.plan.md:50` miss the required subset-reject assertion. `specs/T-PR-02.md:13` requires both `cuisine_avoid=["广东菜"]` and `cuisine_want=["湖南菜"]`. The plan intentionally omits `cuisine_avoid` at `plans/T-PR-02.plan.md:53`. Actual V1 parsing also misclassifies this text as `cuisine_want=['湖南菜', '粤菜']`, so the proposed fallback test would not catch the harmful "avoid cuisine becomes wanted cuisine" regression.

5. `plans/T-PR-02.plan.md:46`-`53` adds only one eval fixture, despite `specs/T-PR-02.md:33` saying that if a jsonl eval set is used, it should add 4-6 records. Existing `tests/refine_eval/eval_set.jsonl` already has related fixtures for flavor, delivery, edge, functional, and reject cases, but it lacks the exact `"下午要睡觉"` low-caffeine-negative case and the subset-reject `cuisine_avoid` case. The plan should either justify relying on existing fixtures per scenario or add the missing 4-6 explicitly.

6. The plan is safe on imports/helpers and name collisions: `tests/test_refine_intent_v2.py` already imports `extract_refine_intent_v2` at line 8, has helper functions at `tests/test_refine_intent_v2.py:465` and `tests/test_refine_intent_v2.py:476`, and no existing `test_refine_v2_fallback_*` names. This is not blocking.

7. Cross-file invariant issue: `docs/CONTRACTS.md:60` requires prompt/model changes to run the eval set, and `docs/CONTRACTS.md:61` says unsupported fields must not be pretended as executed. The plan's V1 fallback assertions are honest about unsupported fields, but they do not satisfy the prompt-boundary guard. A better plan would keep CI default non-LLM by using mocked `_llm_parse_v2` unit cases for schema cleaning plus jsonl eval fixtures for the real LLM prompt boundary.

[FALLBACK NOTE: Codex returned audit verbatim due to read-only sandbox, written to file by main agent.]

## Iter 2

VERDICT: BLOCKED

1. `plans/T-PR-02.plan.md:51` and `plans/T-PR-02.plan.md:54` propose `constrain.functional.low_caffeine_is_null` / `constrain.delivery_only_is_null`, but the eval runner does not support an `_is_null` assertion suffix. Supported operators are documented in `scripts/refine_eval_runner.py:10`-`23` and implemented in `scripts/refine_eval_runner.py:53`-`129`; there is `_nonnull` at `scripts/refine_eval_runner.py:117`-`121`, but no `_is_null`. If implemented as written, these assertions are treated as literal field paths and fail because `_get_path` returns `None` while expected is `true`. Use supported literal-null expectations instead, e.g. `{"constrain.functional.low_caffeine": null}` and `{"constrain.delivery_only": null}`, or `is_empty_strict` where appropriate.

2. `plans/T-PR-02.plan.md:48` claims existing `flavor-02` covers `"想吃辣但别太辣"`, but the actual fixture only checks `raw_understanding_nonempty` and `redirect.cuisine_candidates_expanded=[]` at `tests/refine_eval/eval_set.jsonl:13`. The spec requires `raw_understanding` to contain a conflict/uncertainty phrase at `specs/T-PR-02.md:9`. Track A mocks this phrase, but mocked output does not guard the real T-PR-01 prompt behavior; Track B should strengthen this with a supported `raw_understanding_contains` assertion. The runner supports `_contains` for strings at `scripts/refine_eval_runner.py:83`-`92`.

[FALLBACK NOTE: Codex returned audit verbatim due to read-only sandbox, written to file by main agent.]

## Iter 3

VERDICT: BLOCKED

1. `plans/T-PR-02.plan.md:53` still does not fully address iter 2 issue 2 or `specs/T-PR-02.md:9`. The new `flavor-conflict-01` fixture uses a supported `raw_understanding_contains` assertion, but it checks only `"辣"`, not a conflict/uncertainty phrase. A real LLM output like `"用户想吃辣"` would pass `scripts/refine_eval_runner.py:83`-`92` while failing the required boundary that `raw_understanding` indicate conflict/uncertainty. Change the assertion to a meaningful phrase such as `"冲突"` or `"不确定"`.

Non-blockers verified:
- Planned Track B keys are supported by `scripts/refine_eval_runner.py:10`-`23` and `scripts/refine_eval_runner.py:72`-`129`.
- Literal `null` works via `actual == expected` at `scripts/refine_eval_runner.py:123`-`129`.
- Track A's 5 mocked tests cover all 6 `specs/T-PR-02.md:9`-`14` scenarios.
- Scope is within limits: 2 files, 101 plan lines.
- Faithful Refine red-lines are not structurally broken.

[FALLBACK NOTE: Codex returned audit verbatim due to read-only sandbox, written to file by main agent.]

## Iter 4

VERDICT: APPROVED (main agent self-judgment, stuck override applied)

按 /run-task workflow: iter == 4 强制 stuck override. risk=low 允许. Plan iter 3 BLOCK 的 1 个 issue (raw_understanding_contains: "辣" → "冲突") 已在 plan iter 4 接受并修. 这次 fix 不是过度谨慎拒绝, 而是接受 + 改, 但因迭代次数到 4, 不再跑 codex.

判定理由:
- iter 3 唯一 blocker 已修 (plans/T-PR-02.plan.md:53 fixture 期望短语已改)
- 改动微小 (1 词), 不引新风险
- 所有 7 dim audit non-blockers iter 3 codex 已确认
- Track A/B 双轨设计在 iter 2 codex 已认可
- Faithful Refine + 4-6 fixture spec 要求满足

进入 Phase 3 实施.

## Iter 1

VERDICT: BLOCKED

1. **Missed downstream dependency: `reference` is no longer only "field void / L3 passthrough".** The plan repeats that `reference` is unsupported and "只透传给 L3" in the proposed field-void text (`plans/T-PR-01.plan.md:80`, `plans/T-PR-01.plan.md:84`), but the actual refine path now consumes `intent_v2.reference` before L3: `refine()` prefers V2 reference over raw parsing (`chisha/refine.py:202-218`), resolves it (`chisha/refine.py:236-239`), and applies relation-based soft reranking before slicing top60 (`chisha/refine.py:242-246`, `chisha/refine.py:273-275`). `reference_resolver.py` also documents that V2 reference is used for upstream soft rerank (`chisha/reference_resolver.py:15-18`). This directly contradicts the plan's "pure unsupported passthrough" assumption and can make `raw_understanding`/narrative guidance falsely say the system did not execute a reference signal when it actually did. Fix: the plan must account for the T-P2-01 reference resolver path, or explicitly limit the field-void wording to still-unsupported relations such as `avoid_pattern` while preserving that `lighter` / `similar_but_different_venue` can be executed.

2. **Plan leaves a contradictory `辣 -> 韩式` example in the same prompt.** Revision 2 removes `韩式` from the schema comment at `prompts/parse_refine_intent_v2.md:31`, but the prompt also has an executable example for `"今天想来点辣的"` whose output still includes `"韩式"` (`prompts/parse_refine_intent_v2.md:87-90`). The plan cites the schema line and key convention lines (`plans/T-PR-01.plan.md:31-37`) but does not list the example as an affected location. If implemented as written, the prompt would contain two conflicting instructions: "do not expand 辣 to 韩式" and "for 辣 output 韩式". Fix: update the example output at `prompts/parse_refine_intent_v2.md:90` in the same revision.

3. **Test strategy is too weak for the changed prompt semantics.** The plan says no new tests and claims `tests/test_refine_intent_v2.py` only guards schema/field existence (`plans/T-PR-01.plan.md:9`, `plans/T-PR-01.plan.md:97-99`). The existing tests do pass (`UV_CACHE_DIR=/private/tmp/chisha-uv-cache uv run pytest tests/test_refine_intent_v2.py -q` -> 30 passed), but they use mocked parsed JSON and do not exercise the prompt text at all: e.g. the happy path injects `cuisine_candidates_expanded` / `ingredient_synonyms` directly (`tests/test_refine_intent_v2.py:161-193`), and trace tests only verify prompt body capture, not semantic output (`tests/test_refine_intent_llm_trace.py:31-59`). The spec's Done When explicitly requires manual semantic checks for `"这些广东菜都不想吃, 换湖南菜吧"` and `"下午要开会"` (`specs/T-PR-01.md:29-30`), but the plan's Test strategy omits them. Fix: at minimum add the two manual verification steps from the spec to the plan's required verification, and add an explicit prompt consistency check for the updated examples.

4. **`reject_previous`反例 wording risks losing a real partial rejection unless raw/cuisine slots are required.** The plan says `"这些广东菜都不想吃, 换湖南菜吧"` is false for `reject_previous` because it is "细化 cuisine_avoid + cuisine_want" (`plans/T-PR-01.plan.md:49-51`). Given the current schema only has a binary `reject_previous` (`prompts/parse_refine_intent_v2.md:54`) and D3 decided not to add `reject_scope` (`plans/T-PR-01.plan.md:115`), `false` is acceptable only if the prompt also forces `cuisine_avoid=["广东菜"]`, `cuisine_want=["湖南菜"]`, and `raw_understanding` says the previous Guangdong set was rejected. Without that, the反例 can teach the LLM that the rejection part is simply false/no-op, which undermines Faithful Refine (`docs/CONTRACTS.md:12-16`). Fix: amend Revision 3 to state the required slot output for partial rejection examples, not just the `reject_previous=false` label.

5. **Line/existence audit: affected files exist and most cited anchors are real, but the cited anchor set is incomplete.** `prompts/parse_refine_intent_v2.md` has the cited anchors at lines 31, 34, 43, 45-47, 55, 63-65, 67, 69-77, and 124-129 (`prompts/parse_refine_intent_v2.md:31-77`, `prompts/parse_refine_intent_v2.md:124-129`). However, the real prompt also contains semantically affected examples at `prompts/parse_refine_intent_v2.md:84` (ingredient synonyms example), `prompts/parse_refine_intent_v2.md:90` (`韩式`), and `prompts/parse_refine_intent_v2.md:102` (reference example now consumed by code for supported relations). The plan's affected-location list must include these, or implementation can pass the plan while leaving contradictions.

## Iter 2

Item 1: FIXED — 修订 6 now splits `reference` handling into three categories and limits narrative prohibition to 真不消费类.
Evidence: `plans/T-PR-01.plan.md:80-83` distinguishes 真不消费 / L3 上游消费 / schema 允许但不消费.
Evidence: `plans/T-PR-01.plan.md:96-105` says supported reference relations affect ranking and only forbids narrative claims for "真不消费类".

Item 2: FIXED — 修订 2 affected-lines list explicitly includes the `韩式` example block.
Evidence: `plans/T-PR-01.plan.md:31` lists **example block `:87-90`**.
Evidence: `plans/T-PR-01.plan.md:36` explicitly changes the example output from including `"韩式"` to omitting it.

Item 3: FIXED — Test strategy now includes two concrete manual cases plus a prompt-internal grep self-check.
Evidence: `plans/T-PR-01.plan.md:123-128` lists the 广东菜→湖南菜 case, the 下午要开会 low_caffeine case, and grep for `"韩式"`.
Concern: These remain manual/non-CI by design (`plans/T-PR-01.plan.md:130-131`), but that matches the requested iter-1 fix.

Item 4: FIXED — 修订 3 requires `cuisine_avoid` + `cuisine_want` + `raw_understanding` simultaneously for the partial-reject counter-example.
Evidence: `plans/T-PR-01.plan.md:52-54` says partial reject must fill companion fields and gives all three required outputs.
Evidence: The example requires `reject_previous=false` but `cuisine_avoid=["广东菜"]` + `cuisine_want=["湖南菜"]` + raw_understanding containing the rejection signal.

Item 5: FIXED — Affected-files section now reflects example blocks as affected positions.
Evidence: `plans/T-PR-01.plan.md:7` says 9 text revisions including `example block 2 处`.
Evidence: `plans/T-PR-01.plan.md:31` and `plans/T-PR-01.plan.md:36` specifically include the `:87-90` example block.

Item 6: BLOCKER — NEW-A: The three-category reference scheme leaves avoid-pattern trigger mapping underspecified.
Concern: `plans/T-PR-01.plan.md:100-101` says `reference.relation == "avoid_pattern"` is schema-allowed but not consumed and "暂不推荐使用".
Concern: For a user trigger like "no Korean", the plan does not state whether to use `reference.avoid_pattern`, prefer `cuisine_avoid=["韩式"]`, or fill both; this can confuse the LLM about the right bucket.
Concern: The three-category explanation (lines ~96-105) describes consuming behaviors but not the encoding path — which category does a live "no Korean" utterance map to?

Item 7: FIXED — NEW-B: The partial-reject companion-field rule does not force over-filling for brief ambiguous utterances like "换一家".
Evidence: `plans/T-PR-01.plan.md:55` says uncertain cases default false and raw_understanding should mark "未明确拒绝, 按细化处理", so brief "换一家" is not forced to invent cuisine slots.

SUMMARY: 6 fixed, 0 partial, 1 new blocker.

VERDICT: BLOCKED

Items needing fix:
- Item 6 (NEW-A): 三类 reference scheme 需补充一条编码路径规则 — 当用户说"不想吃韩国菜"时, LLM 应走 `cuisine_avoid` 而非 `reference.avoid_pattern`; `avoid_pattern` 仅保留给无法解析的历史记录场景. 否则 LLM 面对同一输入会随机选桶.

## Iter 3

### NEW-A 验证

FIXED — 修订 6 的 "schema 允许但不消费类" 段已经补上显式编码路径规则。

Evidence: `plans/T-PR-01.plan.md:100-102` says `reference.relation == "avoid_pattern"` is schema-allowed but not consumed, and then states: 用户实时输入的显式避口 ("不想吃韩国菜" / "别给我日料" / "排除粤菜") **一律走 `redirect.cuisine_avoid`**, 不要走 `reference.avoid_pattern`.

Evidence: `plans/T-PR-01.plan.md:102` also reserves `avoid_pattern` only for "无法解析为具体菜系的隐式 negative 历史引用" such as "不要像那次那样", and says 当前 prompt 范围内默认不要主动用. This resolves the Iter 2 ambiguity for "不想吃韩国菜": it maps to `redirect.cuisine_avoid`, not `reference.avoid_pattern`, and not both.

Evidence: `plans/T-PR-01.plan.md:166-170` records the same accepted changelog item: 实时显式避口一律走 `redirect.cuisine_avoid`, `avoid_pattern` only for unparseable implicit negative history references.

### Iter 3 新发现

无新 blocker。

Non-blocking check: 修订 3 still uses shorthand `cuisine_avoid=["广东菜"]` / `cuisine_want=["湖南菜"]` for the partial-reject example (`plans/T-PR-01.plan.md:52-54`, repeated at `plans/T-PR-01.plan.md:124-128`), while NEW-A uses full path `redirect.cuisine_avoid` (`plans/T-PR-01.plan.md:102`). This is not a problem because the schema path is unambiguous in the plan's own wording: NEW-A names the full nested field, and the shorthand examples are describing the same redirect slots rather than introducing a second top-level field.

### VERDICT: APPROVED

## Iter 1

### 1. File Verification
- `plans/T-PR-05.plan.md` exists; scopes implementation to `chisha/rerank.py`, explicitly not `prompts/*.md`, marks high risk / L2 baseline / test guards (`plans/T-PR-05.plan.md:7-19`).
- `specs/T-PR-05.md` exists; asks for `_RERANK_TOOL` description changes, `rank`/`is_explore` descriptions, CLI wording sync, and `_patch_system_prompt_for_cli` anchor preservation (`specs/T-PR-05.md:7-14`).
- `chisha/rerank.py:52-191` exists and matches plan assumptions: `_RERANK_TOOL.description` at 54-57, `rank` no description at 67, `is_explore` no description at 68, `_CLI_OUTPUT_SECTION` rank/is_explore at 124-125, `_patch_system_prompt_for_cli` at 142-191.
- `chisha/rerank.py:877-957` exists, but the named "existing strict validator" wrapper actually starts at `_validate_llm_candidates_v` line 790; lines 877-957 are the lower-level `_validate_llm_candidates` called by the wrapper (`chisha/rerank.py:790-813`, `chisha/rerank.py:877-957`).
- `tests/test_rerank.py` exists and includes validator tests, CLI no-tool path tests, and `_patch_system_prompt_for_cli` ValueError/sanity guards (`tests/test_rerank.py:197-311`, `tests/test_rerank.py:345-409`, `tests/test_rerank.py:500-545`).
- `docs/CONTRACTS.md` exists; contains D-047/D-048/D-049/D-079 contract points for L3, provider split, fallback, and trace (`docs/CONTRACTS.md:42-51`, `docs/CONTRACTS.md:109-115`).
- `docs/decisions.md` exists; contains D-047, D-048, D-049, D-079 decisions (`docs/decisions.md:78-86`, `docs/decisions.md:92-96`, `docs/decisions.md:165-167`).
- `prompts/rerank_system.md` exists; `# 输出方式` anchor at line 77, tail instruction at line 139 (`prompts/rerank_system.md:77-89`, `prompts/rerank_system.md:139`).

### 2. Dimension Findings (6+1)

1. **Missed dependencies** — VERDICT: mostly covered, with one caveat.
   - Anthropic/OpenRouter are main tool consumers: non-CLI calls attach `_RERANK_TOOL` + `_RERANK_TOOL_CHOICE` (`chisha/rerank.py:1096-1098`); Anthropic passes tool dict through when `input_schema` exists (`chisha/llm_providers/anthropic_api.py:67-70`); OpenRouter converts description + schema to OpenAI tool format (`chisha/llm_providers/openrouter.py:96-106`).
   - CLI is separate: `is_cli` patches prompt, does not pass tools (`chisha/rerank.py:1066-1073`, `chisha/rerank.py:1096-1098`); contracts confirm CLI provider must use prompt+JSON (`docs/CONTRACTS.md:49-50`).
   - Caveat: plan says "LLM 看到更明确指令" (`plans/T-PR-05.plan.md:120`), but external visibility of schema descriptions inside LLM context is UNCONFIRMED from local code.

2. **Broken assumptions** — VERDICT: not blocked locally; external schema validation UNCONFIRMED.
   - Local Anthropic adapter sends `_RERANK_TOOL` unchanged when `input_schema` exists (`chisha/llm_providers/anthropic_api.py:50-53`, `chisha/llm_providers/anthropic_api.py:67-70`).
   - Local OpenRouter adapter maps tool `description` and `input_schema` to OpenAI-compatible function `description`/`parameters` (`chisha/llm_providers/openrouter.py:82-85`, `chisha/llm_providers/openrouter.py:96-106`).
   - No local code validates JSON Schema keywords before sending; external API acceptance of nested `description` under `properties.rank`/`properties.is_explore` is UNCONFIRMED.

3. **Regression risk** — VERDICT: behavioral risk is prompt-level, not local parser/validator structure.
   - Planned additions keep existing property names and required list unchanged (`plans/T-PR-05.plan.md:112-113`); current schema has top-level properties `candidates`/`narrative`, required `candidates` (`chisha/rerank.py:60-100`).
   - Forced tool behavior controlled by `_RERANK_TOOL_CHOICE` and non-CLI kwargs, not descriptions (`chisha/rerank.py:103`, `chisha/rerank.py:1096-1098`).
   - External strict schema rejection risk for additional nested `description` metadata is UNCONFIRMED; no local evidence proves Anthropic/OpenRouter reject it.

4. **Missing test coverage** — VERDICT: existing tests cover behavior/anchors but not the new wording.
   - Current tests do not import `_RERANK_TOOL` for schema text assertions (`tests/test_rerank.py:12-17`).
   - Existing CLI provider test verifies no `tools`/`tool_choice` but not rank/is_explore wording (`tests/test_rerank.py:402-408`).
   - Patch tests cover missing section/tail/success, not new description content or ordering sentence (`tests/test_rerank.py:500-545`).
   - Plan includes grep self-checks for new wording, but not committed pytest assertions (`plans/T-PR-05.plan.md:106-113`).

5. **Cross-file invariants** — VERDICT: anchor preservation claim is valid if prompt file remains untouched.
   - Anchor and tail currently exist (`prompts/rerank_system.md:77`, `prompts/rerank_system.md:139`); patch function matches `# 输出方式` + tail (`chisha/rerank.py:158-174`).
   - Plan explicitly says T-PR-05 does not touch `prompts/rerank_system.md` (`plans/T-PR-05.plan.md:11`, `plans/T-PR-05.plan.md:129`), but spec still lists prompt as possible affected file and says "本任务同时改 prompt + rerank.py" (`specs/T-PR-05.md:37-40`, `specs/T-PR-05.md:48`). Plan correctly narrows spec but should call out this discrepancy.
   - CLI path does not read tool description: `tools`/`tool_choice` only set when `not is_cli` (`chisha/rerank.py:1066-1073`, `chisha/rerank.py:1096-1098`). ✓

6. **Affected files truly exist** — VERDICT: yes.
   - All requested line anchors exist and match: `_RERANK_TOOL.description` (`chisha/rerank.py:52-57`), `rank`/`is_explore` (`chisha/rerank.py:67-68`), `_CLI_OUTPUT_SECTION` (`chisha/rerank.py:109-137`), `_patch_system_prompt_for_cli` (`chisha/rerank.py:142-191`). ✓

7. **Faithful Refine lens** — VERDICT: semantically consistent, but wording could be clearer for `n_explore=0`.
   - Prompt already states refine mode forces all `is_explore=false` (`prompts/rerank_system.md:89`, `prompts/rerank_system.md:133`); refine test expects zero explore (`tests/test_rerank.py:164-169`).
   - Proposed "first n - n_explore false, last n_explore true" becomes "first n false, last 0 true" when `n_explore=0` — consistent but less explicit than existing prompt wording (`plans/T-PR-05.plan.md:32-35`, `prompts/rerank_system.md:89`). No contradiction.

### 3. High-Risk Concern Responses (A-D)

**A. API 是否将 schema description 透传给 LLM？**
- Local code passes descriptions to both providers, but whether Anthropic/OpenRouter expose every schema description verbatim inside the LLM context is UNCONFIRMED external API behavior.
- Anthropic returns the original tool dict when `input_schema` exists (`chisha/llm_providers/anthropic_api.py:67-70`); OpenRouter preserves tool description and parameters (`chisha/llm_providers/openrouter.py:96-106`); CLI rejects tools entirely (`chisha/llm_providers/claude_code_cli.py:215-225`, `chisha/rerank.py:1096-1098`).
- Best available evidence: Anthropic's documented behavior is that property-level `description` fields are included in the tool spec forwarded to the model. No local code strips them.

**B. Anthropic/OpenRouter description 长度限制？**
- No local evidence of a field-length limit; local providers forward tools without local length checks (`chisha/llm_providers/anthropic_api.py:50-57`, `chisha/llm_providers/openrouter.py:82-87`).
- Plan estimates the extension at ~200 chars (`plans/T-PR-05.plan.md:120`). UNCONFIRMED external API behavior — low risk at this scale.

**C. "减少 validate fail / retry" 是否有量化依据？**
- The claim is speculative. Plan requires baseline_l2_snapshot which verifies L2 stability, not L3 behavior (`plans/T-PR-05.plan.md:17`, `plans/T-PR-05.plan.md:102`).
- Validator/retry is measurable locally (`chisha/rerank.py:1175-1185`, `chisha/rerank.py:1199-1218`) but no quantified L3 eval is required by the plan.
- Should be flagged as "expected benefit, not verified" rather than asserted outcome.

**D. CLI 路径 wording 和主 path 是否语义一致？两路径是否互相读取？**
- Main path: tool schema description only for non-CLI (`chisha/rerank.py:1096-1098`). ✓
- CLI mode: patches system prompt and parses JSON text (`chisha/rerank.py:1066-1073`, `chisha/rerank.py:1124-1138`). Two separate wording changes, not shared.
- Planned CLI wording mirrors rank/is_explore/final-display-order constraints (`plans/T-PR-05.plan.md:75-82`). Semantically parallel. ✓
- Plan makes this clear; the two paths are independent and the plan correctly acknowledges CLI does not read tool description.

### 4. Open Questions
1. Does Anthropic currently allow arbitrary nested JSON Schema annotation keywords (`description` inside `input_schema.properties.*`) without strict rejection? UNCONFIRMED external API behavior.
2. Does OpenRouter preserve nested schema descriptions when converting to Anthropic upstream, or can it strip them? UNCONFIRMED external API behavior.
3. Is there a provider-side length limit for tool or property descriptions relevant to the proposed ~200 char addition? UNCONFIRMED external API behavior.
4. Should T-PR-05 add pytest assertions for `_RERANK_TOOL` / `_CLI_OUTPUT_SECTION` wording, or are grep self-checks sufficient? Current tests do not assert the new wording (`tests/test_rerank.py:12-17`, `tests/test_rerank.py:500-545`).

### 5. VERDICT

VERDICT: APPROVED — plan is locally coherent and correctly scoped to `chisha/rerank.py` only; the three UNCONFIRMED external API items (description visibility, length limits, schema strict mode) are low-risk at this change scale and do not constitute blockers, while the "reduce retry rate" claim should be labeled speculative rather than asserted.

## Iter 2

### Blocker Verification
- BLOCKER 1: addressed. Iter 2 replaces hardcoded "Select 5 candidates (3 exploit + 2 explore)" with "Select N candidates" and adds the explicit refine-mode sentence (`plans/T-PR-05.plan.md:31-41`), matching current contradictory source at `chisha/rerank.py:54-57`.
- BLOCKER 2: mostly addressed, but the line anchor is stale. Plan says `_validate_llm_candidates_v` is at `chisha/rerank.py:877-957` (`plans/T-PR-05.plan.md:95-109`); actual wrapper is `chisha/rerank.py:790-813`, while `877-957` is lower-level `_validate_llm_candidates`. This does not block if implementation updates the actual wrapper/lower validator/diagnoser consistently.
- BLOCKER 3: not fully addressed. Plan adds `tool_schema_full` to collector + serializer (`plans/T-PR-05.plan.md:117-120`), but explicitly says no `TRACE_SCHEMA_VERSION` bump, conflicting with `docs/CONTRACTS.md:111`.
- BLOCKER 4: partially addressed. The four planned tests cover tool description, rank field description, is_explore description, and validator rank-position rejection (`plans/T-PR-05.plan.md:128-131`), but no planned test asserts `_CLI_OUTPUT_SECTION` ordering despite the plan changing it at `plans/T-PR-05.plan.md:80-85`.
- BLOCKER 5: addressed. Iter 2 adds an OpenRouter `_to_openai_tool` translation preservation test for nested descriptions (`plans/T-PR-05.plan.md:132`); this covers the production compatibility-layer risk noted in iter 1.

### New Issues
1. `tool_schema_full` is a trace schema change but the plan refuses the required version bump.
   `docs/CONTRACTS.md:111` says any trace schema change must bump `TRACE_SCHEMA_VERSION`; current versioning lives in `chisha/trace_store.py:28-33`. Adding `tool_schema_full` to `serialize_llm_call_trace` changes persisted LLM-call shape (`chisha/trace_helpers.py:69-112`), even if optional. The plan's "optional field, empty-string fallback" claim (`plans/T-PR-05.plan.md:120`) is not enough under this contract.

2. Trace migration/read compatibility is underspecified.
   `read_trace` accepts versions and only normalizes v1 hard_filter_events (`chisha/trace_store.py:144-195`). Iter 2 does not say whether v3 old traces should get `tool_schema_full=""` on read, whether to bump to v4, or how `ACCEPTED_TRACE_VERSIONS` should change. This leaves D-079 fail-closed/version behavior ambiguous for the new field.

3. `rank_position_mismatch` retry feedback is semantically mismatched.
   Plan adds `rank_position_mismatch` to `_RETRY_TRIGGER_CODES` (`plans/T-PR-05.plan.md:101-109`), but also says not to change retry feedback (`plans/T-PR-05.plan.md:172`). Current retry prompt only explains exploit/explore counts and segment positions (`chisha/rerank.py:1199-1214`), so a pure rank permutation would get misleading correction text unless the plan updates the retry message or leaves this code out of retry triggers.

4. The plan contains stale rollback/non-goals that contradict the actual revisions.
   Rollback says single-file `chisha/rerank.py`, no validator behavior change (`plans/T-PR-05.plan.md:161-163`), and "不做" says not to change `_validate_llm_candidates_v` (`plans/T-PR-05.plan.md:170`). Iter 2 elsewhere adds `trace_helpers.py`, tests, trace schema persistence, and rank-position validation. This is implementation-risky in a high-risk plan.

5. Trace persistence lacks a guard test.
   Affected files promise a "trace tool_schema" test (`plans/T-PR-05.plan.md:11`), but the five listed tests do not assert `tool_schema_full` is serialized or appears in L3 trace (`plans/T-PR-05.plan.md:126-134`). Given D-079 self-contained trace was a prior blocker, this needs an explicit test alongside `trace_helpers.serialize_llm_call_trace`.

### VERDICT

VERDICT: BLOCKED

1. Bump `TRACE_SCHEMA_VERSION` and specify accepted-version/read migration behavior for `tool_schema_full`, or explicitly justify why this is not a trace schema change despite `docs/CONTRACTS.md:111`.
2. Fix `rank_position_mismatch` retry semantics: either update retry feedback to mention rank-position equality or do not add that code to `_RETRY_TRIGGER_CODES`.
3. Add missing tests for CLI ordering wording and `tool_schema_full` trace serialization/persistence.
4. Clean up stale rollback/non-goal text so the plan does not deny the validator, trace, and multi-file changes it now requires.

## Iter 3

- Date: 2026-05-20
- Auditor: Codex (adversarial)

### A. Iter 2 BLOCKER Verification

A1. PASS — TRACE schema bump conflict fixed by redesigning trace persistence as a `system_prompt_full` string suffix, not a new schema field.
- Evidence: revision 7 says "iter 3 改为不动 schema, 把 outgoing tool schema 拼到 `system_prompt_full` value 末尾 (字符串扩展不算 schema 改)" (`plans/T-PR-05.plan.md:110`).
- Evidence: snippet writes `trace_collector["system_prompt_full"] = system_prompt + ... json.dumps(_RERANK_TOOL, ensure_ascii=False, indent=2)` (`plans/T-PR-05.plan.md:114-123`).
- Evidence: affected files are back to 2: `chisha/rerank.py` and `tests/test_rerank.py` only (`plans/T-PR-05.plan.md:7-10`), and revision 7 states "Affected files 从 3 减回 **2**" (`plans/T-PR-05.plan.md:125`).

A2. PASS — `rank_position_mismatch` retry semantics now explicitly reuse D-049 retry-then-fallback.
- Evidence: revision 6 says "沿用 D-049 retry-then-fallback" and "T-PR-05 仅把 `rank_position_mismatch` 加入 `_RETRY_TRIGGER_CODES` 复用现有链路, 不引入新策略" (`plans/T-PR-05.plan.md:106`).

A3. FAIL — revision 8 lists 6 test names and key assertions, but not complete function signatures.
- Evidence: the plan introduces "新增 6 个测试 (签名 + 关键 assertion)" (`plans/T-PR-05.plan.md:131`), but the table only has columns `# | 名 | 断言要点` (`plans/T-PR-05.plan.md:133-140`) and entries such as `test_rerank_trace_includes_tool_schema_reference` without `def ...(...)` or fixture parameters (`plans/T-PR-05.plan.md:140`).
- Concern: test 6 clearly needs mocking ("mock call_text 后跑 `_run_llm_rerank`"), but no concrete signature such as `def test_...(monkeypatch, tmp_path):` is specified. Under the grounding rule, absent evidence means FAIL.

A4. PASS — validator wrapper line number corrected to `790-813`.
- Evidence: revision 6 states "`chisha/rerank.py:790-813` `_validate_llm_candidates_v` (wrapper)" and explicitly notes the earlier `877-957` reference was lower-level validator code (`plans/T-PR-05.plan.md:90-92`).

### B. Iter 3 New Issue Investigation

B1. Changelog audit trail — PASS / low concern.
- The compressed changelog preserves per-fix attribution: iter 2 fixes are itemized across five prior blockers (`plans/T-PR-05.plan.md:184-189`), and iter 3 fixes are itemized across four iter 2 blockers (`plans/T-PR-05.plan.md:191-195`).
- I do not see a specific fix made unattributable. The changelog is compressed but still traceable to revision numbers.

B2. `system_prompt_full` string length + D-079 compatibility — PASS with one implementation caution.
- D-079 requires trace self-containment through full `system_prompt_full` / `user_message_full` / `raw_response` bodies, not necessarily a structured field. CONTRACTS says the trace must not reconstruct from `prompts/*.md`, because prompts iterate (`docs/CONTRACTS.md:115`). A literal appended JSON schema string inside `system_prompt_full` is enough to preserve the outgoing schema body for replay.
- Storage/I/O limit check: CONTRACTS has no small trace-size cap; code sets `MAX_TRACE_BYTES = 50 * 1024 * 1024` and comments that normal traces under 5MB write directly (`chisha/trace_store.py:34-37`). `write_trace` truncates only if serialized payload exceeds `MAX_TRACE_BYTES` (`chisha/trace_store.py:113-123`). The plan's estimated `~1KB/recommend` increase (`plans/T-PR-05.plan.md:167`) is far below this bound.
- Caution: current code records `system_prompt_chars = len(system_prompt)` before `system_prompt_full` is assigned (`chisha/rerank.py:1077-1079`). If implementation appends to `system_prompt_full`, it should update `system_prompt_chars` to match the final string, because existing tests assert equality (`tests/test_rerank_trace_fields.py:87-94`).

B3. `_to_openai_tool` function existence — PASS.
- Requested grep output:
  ```
  83:        kwargs["tools"] = [_to_openai_tool(t) for t in tools]
  85:            kwargs["tool_choice"] = _to_openai_tool_choice(tool_choice)
  96:def _to_openai_tool(t: dict) -> dict:
  110:def _to_openai_tool_choice(c: dict) -> dict:
  ```
- Function exists under the exact name referenced by the plan. Surrounding code confirms it preserves `description` and maps `input_schema` to OpenAI `parameters`:
  ```
  96:def _to_openai_tool(t: dict) -> dict:
  104-            "description": t.get("description", ""),
  105-            "parameters": t["input_schema"],
  ```
- No blocker here; the deferred "adjust if naming differs" clause is harmless because the assumed function name is real.

B4. `_RETRY_TRIGGER_CODES` type verification — FAIL / blocking concern.
- Requested grep output:
  ```
  305:_RETRY_TRIGGER_CODES = frozenset({
  1185:        if validated is None and is_cli and code in _RETRY_TRIGGER_CODES:
  ```
- Expanded grep evidence:
  ```
  305:_RETRY_TRIGGER_CODES = frozenset({
  306-    RerankValidationCode.OVER_N_MAX,
  307-    RerankValidationCode.EXPLORE_COUNT_MISMATCH,
  308-    RerankValidationCode.EXPLORE_POSITION_WRONG,
  309-})
  ```
- This is a frozen structure, not a set/list addable at runtime. The plan says "加入 `_RETRY_TRIGGER_CODES`" (`plans/T-PR-05.plan.md:104`) but does not call out that implementation must edit the `frozenset({...})` literal rather than call `.add(...)`.

### VERDICT

VERDICT: BLOCKED

1. Revision 8 still does not provide complete test function signatures for all 6 tests. It lists test names and assertions only (`plans/T-PR-05.plan.md:131-140`), and test 6's required mocking fixture/parameters are unspecified despite the "complete signatures" requirement.
2. `_RETRY_TRIGGER_CODES` is currently a `frozenset`, not an addable set/list. The plan must explicitly update the frozen literal or change the type; otherwise the "add `rank_position_mismatch`" instruction is implementation-ambiguous for a high-risk file.

## Iter 4

iter 3 两 BLOCKER 均已修复:
- BLOCKER #1 (test 签名): FIXED. skeleton 文件 6 个 test 函数完整 (test-skeleton.py:8, :20, :29, :39, :56, :73). Test 1-5 可执行断言. Test 6 有 monkeypatch + mock 模板 + NotImplementedError (:91) 防实施遗漏静默通过.
- BLOCKER #2 (frozenset literal): FIXED. plan.md:105 显式 "必须重写 literal 而非 `.add()`", RANK_POSITION_MISMATCH 加入 literal.

iter 4 NEW issues (非 BLOCKER):
- A. skeleton 合规性: 豁免, plan.md:11 明确标注为 plan 引用. affected files 数字表述在 list (3) / revision 7 (2) / changelog (3) 间不一致, 建议实施前对齐 (主 agent 注意).
- B. Test 6 NotImplementedError 实施保护: ok, CI 硬失败防静默通过.
- C. Revision 7 race condition: 无, trace_collector 每次调用局部赋值无共享.

VERDICT: APPROVED

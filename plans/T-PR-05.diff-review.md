# T-PR-05 Diff Review - Phase 4 Iter 1

## 1. Correctness bugs

- BLOCKING, `~/chisha/chisha/rerank.py:55`: `_RERANK_TOOL.description` still hard-codes "Select 5 candidates (3 exploit + 2 explore)" while `rerank()` forces `n_explore = 0` for refine at `~/chisha/chisha/rerank.py:1360`. The new appended wording at `~/chisha/chisha/rerank.py:57`-`~/chisha/chisha/rerank.py:60` says to obey `n_explore`, but the same tool description now contains two incompatible instructions in refine mode. Concrete failure mode: OpenRouter/Anthropic forced tool_use in refine can emit 3 exploit + 2 explore because the tool description says that, `_validate_llm_candidates_v` rejects against `n_explore_expected=0` at `~/chisha/chisha/rerank.py:1186`-`~/chisha/chisha/rerank.py:1190`, non-CLI has no retry because retry is guarded by `is_cli` at `~/chisha/chisha/rerank.py:1191`-`~/chisha/chisha/rerank.py:1196`, and the request falls back to L2 ordering instead of faithful refine.

- BLOCKING, `~/chisha/chisha/rerank.py:73`: the new rank description requires "equals array position + 1", but the validator only sorts rank values and checks the set at `~/chisha/chisha/rerank.py:949`-`~/chisha/chisha/rerank.py:952`. Concrete failure mode: a tool result with ranks `[2, 1, 3, 4, 5]` and correct exploit/explore booleans passes validation because sorted ranks are `[1,2,3,4,5]`; `_run_llm_rerank` then preserves the original array order into output at `~/chisha/chisha/rerank.py:1262`-`~/chisha/chisha/rerank.py:1264`, and `rerank()` maps that order directly at `~/chisha/chisha/rerank.py:1436`-`~/chisha/chisha/rerank.py:1444`. The diff adds a semantic contract but leaves a known accepting path for violating it.

- NON-BLOCKING, `~/chisha/chisha/rerank.py:71`-`~/chisha/chisha/rerank.py:78`: JSON Schema `description` syntax is valid. Official JSON Schema docs define `description` as an annotation keyword usable in schemas/subschemas and requiring a string value. Anthropic docs also show `description` inside `input_schema.properties.location`, and OpenRouter docs show property-level `description` under function `parameters.properties.search_terms`.

- NON-BLOCKING, `~/chisha/chisha/rerank.py:55`-`~/chisha/chisha/rerank.py:60`: I found no documented Anthropic cap that six short description lines would exceed. Anthropic's current tool docs recommend detailed descriptions and 3-4 sentences per tool description; OpenRouter's docs do not publish a lower cap for function or property descriptions. Unverifiable from codebase, requires external API doc/runtime check for any hidden provider-side cap.

- NON-BLOCKING, `~/chisha/chisha/llm_providers/openrouter.py:82`-`~/chisha/chisha/llm_providers/openrouter.py:86`: there is no local OpenRouter `strict` flag, so the rank description cannot change strict-mode routing through this code path. OpenRouter docs list `strict` as optional in tool/function schema, but this repo does not set it.

## 2. Design

- BLOCKING, `~/chisha/chisha/rerank.py:55`-`~/chisha/chisha/rerank.py:60`: the design tries to clarify ordering but leaves a high-priority contradiction in the same tool description: fixed "3 exploit + 2 explore" versus dynamic `n_explore`. Concrete failure mode: in refine, the model sees both "2 explore" and "last 0 items true"; forced tool_use can comply with the first sentence and be rejected by validator, causing non-CLI fallback as described above.

- NON-BLOCKING, `~/chisha/chisha/rerank.py:73` and `~/chisha/chisha/rerank.py:77`: "strictly ascending" and "never interleave" are understandable to the model for ordinary `n_explore=2`, but the current implementation treats them as prompt-only hints. The risky part is not the wording; it is that only `is_explore` array position is enforced, while rank-position equality is not.

- NON-BLOCKING, `~/chisha/chisha/rerank.py:55`-`~/chisha/chisha/rerank.py:60`: mixed Chinese + English is already present and not locally harmful; Anthropic's tool prompt includes the tool definitions as text, and the existing system/user prompts are also bilingual. The harmful inconsistency is semantic, not language mixing.

## 3. Regression surface

- BLOCKING, `~/chisha/chisha/rerank.py:1088`-`~/chisha/chisha/rerank.py:1092`: D-079 requires self-contained LLM call traces, but only `system_prompt_full` and `user_message_full` are stored; `_RERANK_TOOL` is added to `kwargs` later at `~/chisha/chisha/rerank.py:1107`-`~/chisha/chisha/rerank.py:1109` and is not captured in trace. Concrete failure mode: T-PR-05 moves behavior-critical ordering instructions into tool schema descriptions, Anthropic constructs a special tool-use system prompt from those definitions, but a persisted trace cannot reconstruct the exact LLM input that caused a selection. This violates the trace self-contained invariant at `~/chisha/docs/CONTRACTS.md:115` for the changed behavior.

- NON-BLOCKING, `~/chisha/chisha/rerank.py:1107`-`~/chisha/chisha/rerank.py:1109`: adding descriptions does not break `_RERANK_TOOL_CHOICE` locally. The forced choice object remains `{"type": "tool", "name": "select_top_candidates"}` at `~/chisha/chisha/rerank.py:113`; Anthropic adapter passes it through at `~/chisha/chisha/llm_providers/anthropic_api.py:50`-`~/chisha/chisha/llm_providers/anthropic_api.py:53`; OpenRouter converts it to OpenAI shape at `~/chisha/chisha/llm_providers/openrouter.py:82`-`~/chisha/chisha/llm_providers/openrouter.py:86`.

- NON-BLOCKING, `~/chisha/chisha/llm_client.py:155`-`~/chisha/chisha/llm_client.py:165`: `llm_client.py` does not inspect or mutate `description` fields. Anthropic returns an existing Anthropic tool unchanged when `input_schema` is present at `~/chisha/chisha/llm_providers/anthropic_api.py:67`-`~/chisha/chisha/llm_providers/anthropic_api.py:70`; OpenRouter preserves `input_schema` as OpenAI `parameters` at `~/chisha/chisha/llm_providers/openrouter.py:96`-`~/chisha/chisha/llm_providers/openrouter.py:106`.

- NON-BLOCKING, `~/chisha/chisha/rerank.py:801`-`~/chisha/chisha/rerank.py:824`: `_validate_llm_candidates_v` does not read schema descriptions, so description additions do not directly change validator execution. The blocker above is that the new rank-position semantic remains unenforced.

## 4. Test coverage gap

- BLOCKING, `~/chisha/tests/test_rerank.py:197`-`~/chisha/tests/test_rerank.py:311`: existing validator tests cover missing fields, range checks, duplicate indexes, rank continuity, explore count, and explore position, but no test asserts that `rank == array position + 1`. Concrete failure mode: the exact now-documented invalid case `[rank=2, rank=1, rank=3, rank=4, rank=5]` passes current validation and would not be caught by the 48 tests listed in this file.

- BLOCKING, `~/chisha/tests/test_rerank.py:708`-`~/chisha/tests/test_rerank.py:730`: schema-related tests only cover the narrative field and CLI narrative wording. There is no assertion for the new `_RERANK_TOOL.description`, `rank.description`, `is_explore.description`, or `_CLI_OUTPUT_SECTION` ordering line. Concrete failure mode: future edits can delete or contradict the T-PR-05 ordering descriptions while the test suite remains green.

- NON-BLOCKING, `~/chisha/chisha/rerank.py:1210`-`~/chisha/chisha/rerank.py:1227`: T-PR-03 retry text plus T-PR-05 CLI text increases the retry prompt only in CLI mode. CLI ignores `max_tokens` by design at `~/chisha/chisha/llm_providers/claude_code_cli.py:193`-`~/chisha/chisha/llm_providers/claude_code_cli.py:217`; the real cap is timeout. I do not see a new `max_tokens` truncation risk from the added ~200 chars, but the retry path is not tested against the new ordering text.

## 5. Cross-file invariants

- BLOCKING, `~/chisha/docs/CONTRACTS.md:58`: contract says refine disables explore, and `test_rerank_refine_zero_explore` asserts that at `~/chisha/tests/test_rerank.py:164`-`~/chisha/tests/test_rerank.py:169`; `_RERANK_TOOL.description` still says 3 exploit + 2 explore at `~/chisha/chisha/rerank.py:55`. Concrete failure mode: main L3 path can be prompted against the refine invariant and then fall back, masking a faithful-refine failure as an L2 result.

- BLOCKING, `~/chisha/docs/CONTRACTS.md:115`: trace self-contained principle conflicts with behavior-critical schema descriptions not being traced. `trace_collector["system_prompt_full"]` captures only `system_prompt` at `~/chisha/chisha/rerank.py:1390`, `trace_collector["user_message_full"]` captures only user text at `~/chisha/chisha/rerank.py:1391`-`~/chisha/chisha/rerank.py:1392`, and `trace_collector["raw_response"]` captures only provider output at `~/chisha/chisha/rerank.py:1380`-`~/chisha/chisha/rerank.py:1383`. Concrete failure mode: after T-PR-05, a trace cannot show whether rank/explore ordering was instructed via tool schema, so replay/debug can misattribute model behavior.

- NON-BLOCKING, `~/chisha/docs/CONTRACTS.md:49`-`~/chisha/docs/CONTRACTS.md:50`: D-047 forced tool_use behavior is not broken by `description`. The forced schema path remains non-CLI-only at `~/chisha/chisha/rerank.py:1107`-`~/chisha/chisha/rerank.py:1109`, and CLI remains prompt+JSON at `~/chisha/chisha/rerank.py:1077`-`~/chisha/chisha/rerank.py:1084`.

- NON-BLOCKING, `~/chisha/chisha/rerank.py:1101`: main path `max_tokens` remains 2048 output tokens, and the description additions are input-side prompt/tool schema text. I found no concrete D-049 max_tokens boundary caused by the ~200 char increase.

## 6. Prod-time failure modes

- BLOCKING, `~/chisha/profile.yaml:31`-`~/chisha/profile.yaml:35`: current profile routes production L3 through OpenRouter to `anthropic/claude-sonnet-4.6`, and `_to_openai_tool` forwards the entire `input_schema` including new nested descriptions at `~/chisha/chisha/llm_providers/openrouter.py:96`-`~/chisha/chisha/llm_providers/openrouter.py:106`. Concrete failure mode: the prod provider receives behavior-critical instructions only in OpenAI-compatible tool schema metadata, while trace omits that schema and tests do not assert the outgoing converted schema. If OpenRouter transforms, drops, or rewrites nested descriptions, the main path silently loses T-PR-05's intended instruction and there is no local trace/test signal.

- NON-BLOCKING, `~/chisha/chisha/rerank.py:62`-`~/chisha/chisha/rerank.py:78`: Anthropic API rejection for nested `description` is not supported by current docs. Anthropic's tool docs define `input_schema` as JSON Schema and show property-level descriptions. Unverifiable from codebase, requires external API/runtime check for hidden strict validation beyond docs.

- NON-BLOCKING, `~/chisha/chisha/llm_providers/openrouter.py:96`-`~/chisha/chisha/llm_providers/openrouter.py:106`: OpenRouter docs show property-level descriptions in function `parameters.properties`, and its API reference says tools follow OpenAI tool shape and are transformed for non-OpenAI providers. I found no doc proving nested descriptions are dropped or rejected. Unverifiable from codebase, requires external API/runtime check for exact Anthropic-upstream translation.

- NON-BLOCKING, `~/chisha/chisha/rerank.py:119`-`~/chisha/chisha/rerank.py:148`: the CLI path does not read `_RERANK_TOOL`; the modified `_CLI_OUTPUT_SECTION` does cover rank order, exploit/explore segmenting, and final display order at `~/chisha/chisha/rerank.py:134`-`~/chisha/chisha/rerank.py:136`. The remaining CLI risk is test coverage, not semantic mismatch.

## VERDICT: BLOCKED

1. `_RERANK_TOOL.description` still contradicts refine by hard-coding "3 exploit + 2 explore" while refine requires `n_explore=0`.
2. The new `rank == array position + 1` contract is not enforced; the validator accepts permuted rank arrays that final output preserves.
3. T-PR-05 moves behavior-critical instructions into tool schema descriptions, but D-079 traces do not persist the outgoing tool schema, so L3 traces are not self-contained for this changed behavior.
4. Existing tests do not cover the new ordering descriptions or the rank-position invariant, so the semantic change can regress while tests stay green.
5. Current prod route is OpenRouter; schema metadata is forwarded through a compatibility layer without local trace/test verification that nested descriptions survive provider translation.

## Phase 4 iter 2 review (2026-05-20)

### BLOCKER verification
| # | Issue | Status | Evidence (file:line) |
|---|-------|--------|---------------------|
| B1 | description hardcoded | FIXED | `_RERANK_TOOL.description` now starts with "Select N candidates" and no longer contains "3 exploit + 2 explore" (`chisha/rerank.py:55-62`); refine mode is explicit: `n_explore=0, all candidates have is_explore=false` (`chisha/rerank.py:62`); CLI wording also states refine mode all false (`chisha/rerank.py:136-138`). |
| B2 | rank-position not enforced | FIXED | `RerankValidationCode.RANK_POSITION_MISMATCH` exists (`chisha/rerank.py:313`); `_RETRY_TRIGGER_CODES` is a rewritten `frozenset({...})` literal containing that code (`chisha/rerank.py:319-324`); `_validate_llm_candidates_v` checks `c.get("rank") != idx + 1` before returning success (`chisha/rerank.py:828-837`). |
| B3 | trace schema not persisted | FIXED | Non-CLI `_run_llm_rerank` appends a `[TRACE REFERENCE] outgoing tool schema` block with `json.dumps(_RERANK_TOOL, ensure_ascii=False, indent=2)` to `system_prompt_full` (`chisha/rerank.py:1106-1112`); CLI path assigns only `system_prompt` (`chisha/rerank.py:1106-1107`); `system_prompt_chars` is `len(out["system_prompt_full"])` after the append (`chisha/rerank.py:1113-1114`); `TRACE_SCHEMA_VERSION` remains `3` (`chisha/trace_store.py:28`). |
| B4 | missing tests | FIXED | Six T-PR-05 tests were added: description ordering/refine (`tests/test_rerank.py:737-747`), rank field description (`tests/test_rerank.py:750-757`), is_explore field description (`tests/test_rerank.py:760-768`), rank permutation invariant (`tests/test_rerank.py:771-786`), OpenRouter translation (`tests/test_rerank.py:789-800`), and trace schema reference/non-CLI vs CLI behavior (`tests/test_rerank.py:803-843`). |
| B5 | OpenRouter translation | FIXED | The test imports and calls `chisha.llm_providers.openrouter._to_openai_tool` directly (`tests/test_rerank.py:789-793`); it asserts nested `rank` and `is_explore` descriptions survive under converted OpenAI parameters (`tests/test_rerank.py:795-800`); production converter maps `input_schema` directly to `parameters` (`chisha/llm_providers/openrouter.py:96-106`). |

### New issues
- NEW-ADVISORY: `system_prompt_full` now mixes the actual sent system prompt with a trace-only schema reference. The trace helper documents `system_prompt_full` as the actual system body sent to the LLM (`chisha/trace_helpers.py:76-79`), but `_run_llm_rerank` sends `system_prompt` in kwargs (`chisha/rerank.py:1125-1129`) while storing `system_prompt + schema reference` in `system_prompt_full` (`chisha/rerank.py:1109-1112`). Existing code also defines `system_prompt_chars` as `len(system_prompt_full)` (`chisha/trace_helpers.py:78-79`) and tests assert that equality (`tests/test_rerank_trace_fields.py:87-94`), so I do not see a required `TRACE_SCHEMA_VERSION` bump from the current local contract; the wording should be clarified to avoid treating the appended reference as literally sent prompt text.
- NEW-ADVISORY: test 6 is not a silent false negative for missing profile/context fields based on static evidence. The profile fields it passes are read via `profile.get(...)` or `profile.get("preferences", {})` in `_profile_block` (`chisha/rerank.py:434-449`), and `ContextSnapshot` accepts the fields used in the test with `refine_intent` defaulting to `None` (`chisha/context.py:45-58`; `tests/test_rerank.py:825-832`). I attempted to run the focused tests, but `uv` failed before pytest collection with `Operation not permitted` opening `~/.cache/uv/sdists-v9/.git`.
- NEW-ADVISORY: trace file size risk is bounded by existing trace_store behavior. `MAX_TRACE_BYTES` is 50MB with comments saying normal traces under 5MB are written without trimming (`chisha/trace_store.py:33-37`); `write_trace` only truncates when serialized bytes exceed that limit (`chisha/trace_store.py:113-123`), and `_truncate_for_size` first targets raw LLM response, not `system_prompt_full` (`chisha/trace_store.py:331-356`). I found no single-file limit near the ~600+ char schema reference size.

### VERDICT
APPROVED

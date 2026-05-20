## Iter 1

VERDICT: APPROVED

Blocking issues: None.

Non-blocking nits: None.

Summary:
The five mocked-LLM tests correctly exercise the public `extract_refine_intent_v2(..., use_llm=True)` path through schema validation and `_clean_parsed_to_v2`. The mocked payloads match the cleaner's accepted V2 shapes. Track A mocked unit tests plus Track B eval fixtures is a sensible split: deterministic CI coverage for cleaning/schema behavior, real-LLM eval coverage for prompt behavior. The five tests cover all six spec scenarios by combining explicit and implicit delivery in one test, and the four new eval fixtures cover the missing prompt-boundary cases. D-081 and D-085 are honoured: prompt changes are guarded by eval fixtures, and unsupported/faithfulness-sensitive fields are represented as null/empty rather than silently inferred.

[FALLBACK NOTE: Codex returned review verbatim due to read-only sandbox, written to file by main agent.]

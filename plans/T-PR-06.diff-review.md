## Iter 1

Phase 4 adversarial diff review for T-PR-06 (HIGH RISK — chisha/rerank.py + prompts/rerank_system.md).

| # | 维度 | 结论 | 严重性 |
|---|------|------|--------|
| D1 | taste_match rubric D-014 合规 | rubric 全程基于自然语言 taste_description, 未拆 cuisine/cooking/ingredient 三元组. CONTRACTS.md:69 + rerank_system.md:92-97 验证 | non-blocking |
| D2 | one_line_reason 双路径语义同步 | main 三子弹 + CLI 单行摘要覆盖相同三种情形, 语义对齐. rerank_system.md:99-102 + rerank.py:143 | non-blocking |
| D3 | explore escape bullet 位置 | 正确放在 # narrative 字段段内 (rerank_system.md:114-115) | non-blocking |
| D4 | rubric 粒度 vs LLM float 输出 | 五档是范围锚点非枚举值, validator 仍允许 float (rerank.py:82-83). 与 fit_score 风格一致 | advisory |
| D5 | _patch_system_prompt_for_cli anchor 未移位 | `# 输出方式` 仍在 rerank_system.md:77, 替换锚点未动 (rerank.py:171,193-197) | non-blocking |
| D6 | 测试覆盖缺口 | test_cli_output_section_mentions_narrative 通过, 但修订 1/2 无直接守门测试, 跟 T-PR-05 加测试先例不一致 | advisory |

**Blocking Issues: 无**

**Advisory (non-blocking, 留 follow-up)**:
1. 补 taste_match rubric / one_line_reason 双路径守门测试 (跟 T-PR-05 先例对齐)
2. 未来改 rubric 保持"范围描述"非"枚举值", 避免 LLM 被迫整数化

测试状态:
- 全测试 979 passed, 6 skipped, 0 regressions ✓
- baseline_l2_snapshot before/after 0 diff ✓ (D-072.1 守门)
- `_patch_system_prompt_for_cli` 锚点未动
- test_cli_output_section_mentions_narrative 通过

VERDICT: APPROVED

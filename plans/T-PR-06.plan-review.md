## Iter 1

**Reviewer**: Claude Sonnet 4.6 (主 agent, 2026-05-20)
**Verdict**: VERDICT: BLOCKED (1 个硬阻断, 2 个 advisory)

---

### 1. Missed dependencies

**硬阻断 B-01**: `rerank.py` 有独立的 `_CLI_OUTPUT_SECTION`（L121-150），其中 L141 `taste_match` 和 L143 `one_line_reason` 各有一行说明。`_patch_system_prompt_for_cli`（L155）把 prompt 的整个 `# 输出方式` 段**整段替换**为 `_CLI_OUTPUT_SECTION`。

结果：T-PR-06 修订 1（taste_match rubric）和修订 2（one_line_reason 条件化比较）写进 `prompts/rerank_system.md` 的 `# 输出方式` 字段说明后，**CLI 路径（claude_code_cli provider）完全看不到这两处改动**，因为它被 `_CLI_OUTPUT_SECTION` 硬覆盖。`_CLI_OUTPUT_SECTION:L143` 仍然是 `"one_line_reason: ≤ 30 字, 必须具体 + 对比 + 不堆形容词."` ——无条件对比，与修订 2 的条件化语义矛盾。

plan 的「不做」列表里写了"不动 `chisha/rerank.py` 代码"，但 `_CLI_OUTPUT_SECTION` 是常量，属于需要同步的 prompt 文本，不是逻辑代码。**必须同步更新 `rerank.py:L141` 和 `L143`，否则修订 1/2 对 CLI 路径零效果。**

`_validate_llm_candidates_v` 和 `fallback_rerank` 均不依赖 prompt 文案细节，无影响。

---

### 2. Broken assumptions

T-PR-05 加了 rank-position invariant（`_validate_llm_candidates_v` L828-836，rank == array index + 1）。T-PR-06 修订 1 的 rubric 锚点是语义评分引导，不影响 rank 字段校验逻辑。两者**无交互，无冲突**。

---

### 3. Regression risk

Plan 自注 "极端 case 可能让 LLM 把锚点当死规则"。具体风险：rubric 写 `0.7-0.9` 但 LLM 可能输出 `0.8`（整数精度），`_diagnose_candidates:L876-878` 对 `taste_match` 容许 None 或 0-1 float/int，整数 0.8 → float 0.8 仍合法。**低风险，不阻断。**

---

### 4. Missing test coverage

Advisory A-01：`_CLI_OUTPUT_SECTION` 里的 `one_line_reason` 说明行（L143）当前没有 prompt 守门测试。T-PR-05 加了 `# 输出方式` 锚点的断言测试（`test_rerank.py`），但未覆盖 `_CLI_OUTPUT_SECTION` 的具体字段说明文本。若修订 2 只改 prompt 不改 `rerank.py`，T-PR-07 守门会发现 CLI 路径行为不符预期，但不是断言失败。建议 plan 补一句"同步改 `rerank.py:_CLI_OUTPUT_SECTION` L141/L143"并在 T-PR-07 守门中验证 CLI 输出不含编造比较对象。

---

### 5. Cross-file invariants (D-014)

修订 1 rubric 使用自然语言区间描述（"强命中/部分命中/同品类替代"），**不结构化为 cuisine/cooking/ingredient 三元组**。D-014 约束满足。无问题。

---

### 6. Affected file lines 真实存在

- `rerank_system.md:92` — 实际存在，`taste_match`：0.0-1.0... ✅
- `rerank_system.md:94` — 实际存在，`one_line_reason`：≤ 30 字... 含"另两条" ✅
- `rerank_system.md:106` — 实际存在，"候选稀薄..." ✅

**Specific concern: L113 "另两条"**：`rerank_system.md:113` 的 reason 示范 `比另两条油低一档` 是 `# reason 示范` 段内的 ✅ 示例，**不是 L94 字段说明本身**。修订 2 改的是 L94 字段说明的措辞，示范段属于展示性文案。Plan 未提及是否同步修改示范段，这是 advisory 而非阻断：若 `# reason 示范` 里的 ✅ exploit 例仍含"另两条"而字段说明已条件化，语义上有轻微不一致，但不影响 schema 校验。建议 plan 补一句说明示范段保留现状（因为对比示范本身合法）或同步调整一个示范条目。

---

### 7. Faithful Refine / 修订 3 语义重复

T-PR-04 的 narrative 约束（`rerank_system.md:104`）："不得声称已执行 unsupported 字段"——针对的是 **执行层欺骗**（声称做了 L1/L2 不支持的过滤）。

修订 3 的 explore 稀薄 escape 针对的是 **探索质量诚实降级**（explore 槽候选弱相关时不假装是主力推荐）。

两者方向不同，不重复。但 Plan 未显式区分 `候选稀薄`（L106，intent 命中数低）和 `explore 稀薄`（修订 3，explore 槽候选多样性弱），可能让 reviewer 误认为语义重叠。建议 plan 在修订 3 说明中加一行："区分：L106 候选稀薄 = 整体候选数不足；本处 explore 稀薄 = explore 槽被迫用弱相关候选填满，整体候选可以很多。"

---

### Specific concerns 汇总

| # | 问题 | 结论 |
|---|------|------|
| SC-1 | 修订 1 sub-bullet nested markdown 是否破 LLM parsing | 风险低；rerank_system.md 已有多层 bullet，LLM 在 tool_use 路径读结构化 schema，CLI 路径读 `_CLI_OUTPUT_SECTION`（被替换，看不到 rubric）。问题根因是 B-01 而非 markdown 结构本身。 |
| SC-2 | L113 "另两条" 示范是否需同步 | Advisory，不阻断。示范段保留"另两条"示例合法，但应在 plan 中明确说明处置方式。 |
| SC-3 | 候选稀薄 vs explore 稀薄区分 | 语义不重复，但 plan 未显式区分，建议补一行说明。 |

---

### VERDICT: BLOCKED

**硬阻断 B-01**（必须解决后方可实施）:
- `rerank.py:_CLI_OUTPUT_SECTION` L141（taste_match 说明）和 L143（one_line_reason 说明）是 CLI 路径的实际 prompt，与 `prompts/rerank_system.md` 的 `# 输出方式` 段独立。修订 1/2 必须**同步更新** `rerank.py:_CLI_OUTPUT_SECTION` 对应两行，否则 CLI provider 用户完全看不到 rubric 和条件化比较改动。建议 plan 把 `chisha/rerank.py`（改 `_CLI_OUTPUT_SECTION` 常量）加入 Affected files，并说明这是 prompt 文本同步，不是逻辑改动。

**Advisory（非阻断，建议在 plan 中补说明）**:
- A-01: T-PR-07 守门需覆盖 CLI 路径 `_CLI_OUTPUT_SECTION` 与 prompt 修订的一致性，而不仅仅是 tool_use 路径的 schema 校验。
- A-02: `# reason 示范` L113 "另两条"示例与修订 2 条件化措辞的处置方式在 plan 中未说明（保留/调整均可，需明确）。

## Iter 2

iter 1 1 BLOCKER + 2 advisory 全部 FIXED:
1. CLI _CLI_OUTPUT_SECTION 漏 → 修订 1/2 双路径同步 (Affected files +chisha/rerank.py), risk medium → high, baseline 必跑 ✓
2. # reason 示范 line 113 处置 → 修订 2 显式保留 ✓
3. 候选稀薄 vs explore 稀薄 → 修订 3 加语义区分 ✓

iter 2 NEW (2 ADVISORY, non-blocking):
- A: CLI max_tokens sensitivity: 加 ~80 字 rubric, CLI max_tokens=4096 充裕 (实测主路径 input ~16K), 无截断风险. 主 agent 接受 advisory 但无需 plan 修改.
- B: 修订 2 CLI 同步粒度: 主 prompt 改 3 sub-bullet, CLI 单行原文需展开吗? 实施判定: CLI 路径输出仅给模型作输出 schema 约束, 保持 single-line summary 即可 ("必须具体 + 不堆形容词. 比较条件化: 同品牌多变体必比 / 相邻 rank 可比 / 无可比对象不强行比较"), 无需 3 sub-bullet 全文复制.

VERDICT: APPROVED (2 advisory accepted as implementation guidance)

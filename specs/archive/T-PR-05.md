# T-PR-05 · rerank tool_use schema description 微调 + CLI no-tool 段同步

参考: `docs/proposals/archive/2026-05-20-prompt-effect-optimization.md` §3.3 P1-9 + Codex review §5.5 + §4 T-PR-05

## What

修订 `chisha/rerank.py` 的 `_RERANK_TOOL` schema (line 52-102) + `_CLI_OUTPUT_SECTION` (line 109-137), 在现有 schema description 字符串里**只**加 ordering 约束的自然语言说明, 不新增 required 字段:

1. **`_RERANK_TOOL.description`** (line 54-57): 末尾追加一句 ordering 约束:
   - "candidates must be emitted in final display order; rank must equal array position + 1 (1-indexed); first n - n_explore items have is_explore=false (exploit), last n_explore items have is_explore=true (explore), no interleaving."
2. **`rank` 字段 description**: 加 "1-indexed, strictly ascending, equals array position + 1"
3. **`is_explore` 字段 description**: 加 "first n - n_explore items are false (exploit segment), last n_explore items are true (explore segment); never interleave"
4. **`_CLI_OUTPUT_SECTION`** (line 109-137): 同步 CLI no-tool 路径的 JSON 输出说明 — `rank` 段和 `is_explore` 段加同样的 ordering 措辞 (保持 main path 与 CLI fallback 一致)
5. **`_patch_system_prompt_for_cli`** 锚点 (`# 输出方式`) 不动, **守门测试** (锚点检测 ValueError) 必须仍通过

## Why

- Opus v1 原 P0 提议加 `output_plan` schema required 字段被 Codex 强反对: 引入 plan/candidates 双源不一致 + 破 D-079 旧 trace 简单解析预期
- 现有 validator (`chisha/rerank.py:877-957`) 已对 rank 连续/combo_index 越界/explore 数量做强校验; 失败有 retry/fallback, 不会"信任崩塌"
- 本任务降级为: 在现有 schema description 里加自然语言 ordering 提示, 让模型生成时更稳, 但**不破 schema 兼容** — 这是 Step 1 范围内的最小化、零兼容风险改动

## Done When

- `chisha/rerank.py` `_RERANK_TOOL.description` + `rank.description` + `is_explore.description` 三处文案增订完成
- `_CLI_OUTPUT_SECTION` 同步增订 rank / is_explore ordering 措辞
- `_patch_system_prompt_for_cli` 锚点测试通过 (改前后 `# 输出方式` 段位置/标题不变)
- `chisha/rerank.py` 内的 `_RERANK_TOOL` JSON schema 结构 (properties / required) **零变化** — 只动 description 字符串
- `tests/test_rerank.py` 全绿: `uv run pytest tests/test_rerank.py -q`
- 全测试 `uv run pytest tests/ -q` 全绿
- baseline_l2_snapshot 0 diff (L2 链路不动, 本任务只动 L3 prompt 描述; D-072.1 严格回归过 — `EPSILON=1e-6`)

## Plan 规模上限

- `plans/T-PR-05.plan.md` ≤ 200 行
- Affected files ≤ 5

## Affected files (预估)

- `chisha/rerank.py` (改, `_RERANK_TOOL` description + `_CLI_OUTPUT_SECTION` 文案)
- `prompts/rerank_system.md` (可能动 line 64 `# 输出方式` 段措辞与 schema description 对齐)

## 红线

- **`chisha/rerank.py` 是 12-file 高风险白名单** — 本任务 regression_risk=high. /run-task Phase 4 reviewer 必须走 Codex 对抗审一轮 + baseline_l2_snapshot 严格回归
- 不新增 / 不改名 / 不删 schema required 字段 (D5 已决: narrative 保 optional)
- 不动 `_RERANK_TOOL.input_schema.properties` 的字段结构 (properties keys 不变, types 不变, required 不变)
- 不动 `_patch_system_prompt_for_cli` 函数逻辑 (它的 ValueError 守门是 D-048 关键)
- **同 `prompts/rerank_system.md` 文件**: 串行执行顺序 T-PR-03 → T-PR-04 → T-PR-05 → T-PR-06 (由 tasks.json 数组顺序保证). 本任务同时改 prompt + rerank.py, 与 T-PR-06 字段说明相邻, plan 里必须先 `git diff prompts/rerank_system.md` 看最新版再 patch

## 不做

- 不加 `output_plan` / `n_exploit` / `exploit_combo_ids` 等新字段 (D3 已决: 本轮不加)
- 不改 `_validate_llm_candidates_v` 校验逻辑
- 不动 retry feedback 文案 (它在 D-049 / line 1199 附近, 是 CLI 路径专用)
- 不动 prompt §输出方式 段的计数硬约束 (那是 Step 2 可读性合并的事)

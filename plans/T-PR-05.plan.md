# T-PR-05 · rerank tool_use schema description 微调 — Plan

参考 spec: `specs/T-PR-05.md`. 参考 brief: `docs/proposals/2026-05-20-prompt-effect-optimization.md` §3.3 P1-9.

> 行号是 plan 元说明, 不进 prompt/description 代码.

## Affected files

- `chisha/rerank.py` (改 description + validator rank-position + system_prompt_full 拼 schema reference + `_RETRY_TRIGGER_CODES` frozenset literal 加 RANK_POSITION_MISMATCH)
- `tests/test_rerank.py` (加 6 个新 test, 完整签名见 `plans/T-PR-05.test-skeleton.py`)
- `plans/T-PR-05.test-skeleton.py` (新建, 测试骨架, plan 引用)

`prompts/rerank_system.md` 本任务**不动** — `# 输出方式` 段措辞跟 schema description 是分离的两套。本 plan 只动 `chisha/rerank.py` + 必要的 test 和 trace 配套。

## Regression risk

- **high** (CLAUDE.md 12-file 白名单命中 — `chisha/rerank.py`)
- Phase 4 reviewer: `/codex:adversarial-review` (high 严禁 stuck override)
- baseline_l2_snapshot 必跑 (before/after 0 diff 期望 — schema description 只影响 LLM 提示, 不影响 L2 14 维打分)
- 测试守门: `tests/test_rerank.py` 全绿 (schema properties/required 0 变化, 仅 description 字符串增订)
- `_patch_system_prompt_for_cli` 锚点守门 (锚点是 `# 输出方式` 顶级标题, T-PR-05 不动 prompt 文件, 锚点天然保留)

## Step-by-step

### 修订 1: `_RERANK_TOOL.description` (rerank.py:54-60) — **删除硬编码 "3 exploit + 2 explore"** (Codex iter 1 BLOCKER 1)

**位置**: `chisha/rerank.py:54-60` 现有 `"description"` 字符串

**Codex iter 1 BLOCKER 1**: 原描述硬编码 "Select 5 candidates (3 exploit + 2 explore)" 与 refine 模式 `n_explore=0` 矛盾, LLM 看到 "2 explore" 静态文案可能违反 refine 不变量, validator 拒后 fallback L2.

**改动**: 移除硬编码数字, 改为参数化描述:
```python
"description": (
    "Select N candidates from the input candidate list, in rank order. "
    "exploit 段在前, explore 段在后. "
    "candidates must be emitted in final display order; "
    "rank must equal array position + 1 (1-indexed); "
    "first n - n_explore items have is_explore=false (exploit segment), "
    "last n_explore items have is_explore=true (explore segment), no interleaving. "
    "In refine mode n_explore=0, all candidates have is_explore=false."
),
```

新增末尾一句明确 refine 模式行为, 消除矛盾。

### 修订 2: `rank` 字段 description (rerank.py:67)

**位置**: `chisha/rerank.py:67` 当前 `"rank": {"type": "integer", "minimum": 1, "maximum": 5}` — **无 description 字段**

**改动**: 加 description:
```python
"rank": {
    "type": "integer", "minimum": 1, "maximum": 5,
    "description": "1-indexed, strictly ascending, equals array position + 1.",
},
```

JSON schema 字段加 description 是合法的, 不算 properties 结构变更 (Codex 可能挑这点, 但 description 是 schema 元数据, 不参与 validation, 不破 trace 兼容)。

### 修订 3: `is_explore` 字段 description (rerank.py:68)

**位置**: `chisha/rerank.py:68` 当前 `"is_explore": {"type": "boolean"}` — **无 description 字段**

**改动**:
```python
"is_explore": {
    "type": "boolean",
    "description": "First n - n_explore items are false (exploit segment), last n_explore items are true (explore segment); never interleave.",
},
```

### 修订 4: `_CLI_OUTPUT_SECTION` rank + is_explore 措辞同步 (rerank.py:124-125)

**位置**: `chisha/rerank.py:124-125` 现有 CLI no-tool 输出段:
```
- rank: 1..n 连续整数
- is_explore: bool. 前 (n - n_explore) 个 false (exploit), 后 n_explore 个 true (explore). refine 模式 n_explore=0 时全部 false.
```

**改动**: 加 ordering 措辞与 schema 一致:
```
- rank: 1..n 连续整数, 严格升序, 等于 array position + 1 (1-indexed).
- is_explore: bool. 前 (n - n_explore) 个 false (exploit segment, 不许穿插), 后 n_explore 个 true (explore segment). refine 模式 n_explore=0 时全部 false.
- candidates 输出顺序 = 最终展示顺序 (exploit 段在前, explore 段在后, 不许穿插).
```

新增 "candidates 输出顺序" 一行, 跟主路径 tool description 措辞同源。

### 修订 5: `_patch_system_prompt_for_cli` (rerank.py:142-191) **不动** — 自检锚点保留

### 修订 6: 加 rank-position 检查 (Codex iter 1 BLOCKER 2 + iter 2 BLOCKER 4 行号修正)

**位置**: `chisha/rerank.py:790-813` `_validate_llm_candidates_v` (wrapper). iter 2 Codex 校正: iter 1 plan 引用 877-957 是 lower-level `_validate_llm_candidates`, 实际改的是 wrapper at line 790 附近, 在 wrapper 出口前加 rank-position 检查 (因为 wrapper 接收的是已过结构校验的 candidates list)。

**Codex iter 1 BLOCKER 2**: 修订 1 加了 description "rank must equal array position + 1" 但 validator 不强制, permuted ranks `[2,1,3,4,5]` 可以 pass 现有 sorted set 检查。

**改动**: 在 `_validate_llm_candidates_v` wrapper 出口前 (return validated 之前) 加:
```python
# T-PR-05: rank must equal array position + 1 (1-indexed)
for idx, c in enumerate(validated):
    if c["rank"] != idx + 1:
        return None, "rank_position_mismatch", f"candidates[{idx}].rank={c['rank']}, expected {idx+1}"
```

新加 `RerankValidationCode.RANK_POSITION_MISMATCH` 枚举值 (跟 OVER_N_MAX / EXPLORE_COUNT_MISMATCH / EXPLORE_POSITION_WRONG 同级). 加入 `_RETRY_TRIGGER_CODES` 的方式 — **rerank.py:305-309 是 `frozenset({...})` literal, 不可变** — 必须重写 literal 而非 `.add()`:
```python
_RETRY_TRIGGER_CODES = frozenset({
    RerankValidationCode.OVER_N_MAX,
    RerankValidationCode.EXPLORE_COUNT_MISMATCH,
    RerankValidationCode.EXPLORE_POSITION_WRONG,
    RerankValidationCode.RANK_POSITION_MISMATCH,  # T-PR-05
})
```

**Retry/fallback 语义 (Codex iter 2 BLOCKER 2)**: 沿用 D-049 retry-then-fallback. 主路径 (tool_use) 拒后 → `fallback_rerank` 规则路径 (无 retry). CLI 路径 → retry 一次带 correction → 仍失败 → fallback. T-PR-05 仅把 `rank_position_mismatch` 加入 `_RETRY_TRIGGER_CODES` 复用现有链路, 不引入新策略.

### 修订 7: trace tool schema 持久化 — **iter 3 重设计** (Codex iter 1 BLOCKER 3 + iter 2 BLOCKER 1)

iter 2 BLOCKER 1: CONTRACTS.md:111 强制 bump TRACE_SCHEMA_VERSION, plan 不能"optional 字段豁免". iter 3 改为不动 schema, 把 outgoing tool schema 拼到 `system_prompt_full` value 末尾 (字符串扩展不算 schema 改)。

**位置**: `chisha/rerank.py:_run_llm_rerank` trace_collector 配置 (line 1390 附近, `system_prompt_full = system_prompt` 行)

**改动**: 仅 non-CLI 路径:
```python
if not is_cli:
    trace_collector["system_prompt_full"] = system_prompt + (
        "\n\n# === [TRACE REFERENCE] outgoing tool schema (T-PR-05) ===\n"
        + json.dumps(_RERANK_TOOL, ensure_ascii=False, indent=2)
    )
else:
    trace_collector["system_prompt_full"] = system_prompt
```

好处: 不引入新字段 → 不 bump TRACE_SCHEMA_VERSION (CONTRACTS.md:111 合约不冲突) / 不改 trace_helpers.py / 旧 trace 兼容 / D-079 自包含兑现。Affected files 从 3 减回 **2**。

### 修订 8: 测试覆盖 description + invariant + 转译 + trace

**位置**: `tests/test_rerank.py`. 完整 6 个 test 完整可执行签名 + 断言落在 `plans/T-PR-05.test-skeleton.py` (实施时 inline 到 tests/test_rerank.py).

| # | test 名 (skeleton.py 完整定义) | 守门 fix |
|---|---|---|
| 1 | `test_rerank_tool_description_contains_ordering` | 修订 1 (description 含 7 个关键短语 + 移硬编码) |
| 2 | `test_rerank_rank_field_description` | 修订 2 (rank.description 含 strictly ascending / equals array position + 1) |
| 3 | `test_rerank_is_explore_field_description` | 修订 3 (is_explore.description 含 never interleave + 双 segment) |
| 4 | `test_rerank_validator_rejects_permuted_rank` | 修订 6 (validator 拒 ranks=[2,1,3,4,5] + RANK_POSITION_MISMATCH code) |
| 5 | `test_rerank_openrouter_tool_translation_preserves_descriptions` | 修订 1-3 + Codex BLOCKER 5 (OpenRouter `_to_openai_tool` 保留 nested description) |
| 6 | `test_rerank_trace_includes_tool_schema_reference` | 修订 7 (system_prompt_full 末尾含 schema reference; CLI 路径不含) |

实施时根据 `chisha/llm_providers/openrouter.py` 实际函数命名 (e.g. `_to_openai_tool`) 调整 import. test 6 的 mock pattern 见 skeleton 注释模板。

## Test strategy

### CI 守门 (必跑)

- `uv run pytest tests/test_rerank.py -q` — 应全绿 + **5 新 test 全过** (修订 8)
- 全测试 `uv run pytest tests/ -q` — 期望 973+5 = 978 passed (5 新 test 来自修订 8)
- `_patch_system_prompt_for_cli` ValueError 守门 — 任一锚点未命中应抛 ValueError; T-PR-05 不动 prompt 文件, 期望仍过

### High-risk 强制 (CLAUDE.md D-072.1)

- **baseline_l2_snapshot before/after 严格回归**: EPSILON=1e-6, 0 diff 期望 (本任务只动 L3 schema description, 不动 L2 14 维打分 + recall 链路)
- 走 `git stash` 模式: stash 改动 → baseline before → unstash → baseline after → compare_traces
- 失败 → halt, 不许 override (high risk 严禁 stuck override)

### 自检 (实施后)

- grep `_RERANK_TOOL` 含 4 修订关键短语 + schema properties/required keys 不变 (无新键, narrative 仍 optional)

## Rollback notes

- 主文件 `chisha/rerank.py`, rollback = `git checkout HEAD~N -- chisha/rerank.py tests/test_rerank.py`
- schema properties keys 不变 / required 不变 → D-079 trace 兼容零风险
- 修订 6 加 validator 路径 = 新 retry trigger, 风险盲点: 边缘 case (model 偶尔 permute rank) 触发 retry / fallback. 已有 D-049 链路兜底 (CLI retry → fallback_rerank 规则路径)
- 修订 7 system_prompt_full 拼 ~600 字符 schema reference, trace 文件略大 (~1KB/recommend), 不影响 read/write 性能 (旧 trace 仍可读, fail-closed read_trace 不挑剔字段值长度)

## 不做

- 不加 `output_plan` / `n_exploit` 等新 schema 字段 (D3 已决 + Codex 强反对: 双源不一致 + 破 D-079)
- 不改 `_RERANK_TOOL.input_schema.properties` 字段结构 (keys/types/required 不变)
- 不改 retry feedback 文案 (T-PR-03 已动) / 不动 prompts/rerank_system.md / 不动 `_patch_system_prompt_for_cli` 函数逻辑 (D-048)
- 不 bump TRACE_SCHEMA_VERSION (修订 7 走字符串扩展不动 schema)
- 不引入 prompt §输出方式 段计数硬约束合并 (Step 2)

## Plan 规模

- 本文件: ≤ 200 ✅ (实际 ~200, 经 iter 3 压缩)
- Affected files: 2 (chisha/rerank.py + tests/test_rerank.py), ≤ 5 ✅

## Changelog (iter 2+3+4 累计接受 11 BLOCKER)

iter 2 (5 BLOCKER from Codex Phase 4 iter 1): description 硬编码 vs refine 矛盾 / rank==position+1 没强制 / trace 不持久化 schema / 缺测试 / OpenRouter 转译没验证 → 修订 1/6/7/8 全覆盖.

iter 3 (4 BLOCKER from Codex Phase 2 iter 2): schema 字段需 bump TRACE_SCHEMA_VERSION → 修订 7 重设计字符串拼接; retry 语义补 D-049 沿用 (修订 6); 测试缺签名 → 给 6 test 签名 (修订 8); wrapper 行号 877→790 校正 (修订 6).

iter 4 (2 BLOCKER from Codex Phase 2 iter 3): test 签名仍不够 → 完整 test 代码移到 `plans/T-PR-05.test-skeleton.py` 独立文件; `_RETRY_TRIGGER_CODES` 是 frozenset literal → 修订 6 显式重写 literal + 加 RerankValidationCode 枚举值.

全部 11 BLOCKER 接受, 无 stuck override (high-risk 严禁). Affected files 最终 3 (rerank.py + tests/test_rerank.py + plans/T-PR-05.test-skeleton.py).

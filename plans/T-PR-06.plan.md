# T-PR-06 · rerank prompt 三项 P1 文案补丁 — Plan

参考 spec: `specs/T-PR-06.md`. 参考 brief: `docs/proposals/2026-05-20-prompt-effect-optimization.md` §3.3 P1-4/P1-5/P1-6.

> 行号是 plan 元说明, 不进 prompt 文本。

## Affected files

- `prompts/rerank_system.md` (改 # 输出方式 段 + # narrative 段; 主路径 tool_use 看到)
- `chisha/rerank.py` (改 `_CLI_OUTPUT_SECTION:L121-150` taste_match + one_line_reason 措辞; CLI 路径看到 — `_patch_system_prompt_for_cli` 整段替换 `# 输出方式`, 不改 CLI 路径会让两路径 prompt 语义漂移)

## Regression risk

- **high** (Codex iter 1 BLOCKER 1 暴露: `chisha/rerank.py` 命中 12-file 白名单, 即使只改字符串内 prompt 文案)
- **tasks.json 需要从 medium → high 同步** (跟 T-PR-03 同模式)
- Phase 4 reviewer 升级为 `/codex:adversarial-review` (不是 /codex:review)
- baseline_l2_snapshot 必跑 (期望 0 diff — 改的是 prompt + CLI prompt 文案, 不动 L2 14 维打分)
- 测试守门: `tests/test_rerank.py` 全绿 + 现有 `_patch_system_prompt_for_cli` 锚点测试通过 + 现有 `test_cli_output_section_mentions_narrative` 通过
- `_patch_system_prompt_for_cli` 锚点 `# 输出方式` + 末尾 `select_top_candidates...现在等待` 不动 (修改是段**内**文案, 不动顶级标题/末尾)

## Step-by-step

### 修订 1: `taste_match` rubric (P1-4) — **双路径同步**

**位置 1 (主路径)**: `prompts/rerank_system.md:92` 现有 `taste_match` 字段说明

**位置 2 (CLI 路径)**: `chisha/rerank.py:_CLI_OUTPUT_SECTION` 内现有 `taste_match: 0.0-1.0, 与 taste_description 命中度` 行 (大约 L141, 实施时 grep 确认)

**改动 (两处同步)**: 扩展为 inline rubric (基于自然语言 taste_description, **不结构化为 cuisine/cooking/ingredient 三元组** — 红线 D-014):
```
- `taste_match`：0.0-1.0，与 `taste_description` 的命中度。锚点:
  · 0.9-1.0 强命中 (taste_description 主要特征都对上)
  · 0.7-0.9 部分命中, 整体方向一致
  · 0.5-0.7 同品类替代 / 部分契合
  · 0.3-0.5 仅大类命中 (如同为中餐)
  · 0.0-0.3 方向冲突 / 接近 disliked_cuisines
```
≤ 80 字 (spec done_when 要求)。两路径文案保持一致 (避免 main vs CLI 漂移)。

### 修订 2: `one_line_reason` 比较措辞条件化 (P1-6) — **双路径同步**

**位置 1 (主路径)**: `prompts/rerank_system.md:94` 现有 `one_line_reason`：≤ 30 字。必须**具体**...**对比**(说出为什么是这条而不是另两条)`

**位置 2 (CLI 路径)**: `chisha/rerank.py:_CLI_OUTPUT_SECTION` 内现有 `one_line_reason: ≤ 30 字, 必须具体 + 对比 + 不堆形容词` 行 (大约 L143, 实施时 grep 确认)

**改动 (两处同步)**: 把"对比"段从无条件改为条件化:
```
- `one_line_reason`：≤ 30 字。必须**具体**（点出命中的 taste/context 关键词）+ **不堆形容词**。**比较是条件化的**:
  · 若候选输入有同品牌多变体 → 必须说为什么选这条不选同品牌另一条
  · 若候选有相邻 rank / 同 cuisine 多个 → 可点取舍
  · 无可比对象 → 给具体命中证据, 不强行比较 (Codex 盲点 #5: 防编造比较对象)
```

**# reason 示范段 (line 113) 现有正例 "潮汕粥...比另两条油低一档" 处置 (Codex iter 1 advisory)**:
- 该正例**保留** — 它在"有可比对象"场景下符合修订 2 第二条 (有相邻 rank 可点取舍)
- 不删 / 不改 — 示例 demo 的就是"有可比时怎么比", 跟新条件化规则一致

### 修订 3: § narrative 段加 explore 稀薄 escape (P1-5)

**位置**: `prompts/rerank_system.md:106` 现有 line "候选稀薄 (intent 命中数低) 时, narrative 必须如实告知" 之后

**改动**: 加一个新 bullet 项 (定性, 不绑 idx / taste_match 阈值, Codex 反对):
```
- **explore 稀薄 escape**: 当 explore 槽只能选 "与 refine 弱相关 / 仅多样性补位" 的候选时, narrative 必须显式声明 "后 N 条偏探索/备选, 当下命中度有限", 不要假装是 explore 主力. (与 D-080 第一原则一致 — 不漂亮但诚实)
```

**与 line 106 "候选稀薄" 的语义区分 (Codex iter 1 advisory)**:
- "候选稀薄" (现有 line 106) = **intent 命中数低** (整体匹配差, 包括 exploit 段)
- "explore 稀薄" (新 bullet) = **explore 槽位质量低** (exploit 可能 OK 但中段无好 explore)
- 两条共存, 覆盖不同 narrative 诚实降级场景。CLI 路径 narrative 文案在 `_CLI_OUTPUT_SECTION` 已有"必须有执行证据支撑" 措辞, 不需要 escape 子条同步 (CLI 路径 narrative 说明更简短, 不复制主路径全部 narrative bullet)。

## Test strategy

- 不加新测试 (T-PR-07 整体守门 + 改 prompt 文本无新逻辑可单测)
- 现有 `tests/test_rerank.py` 全绿 (schema/validator 不变, 仅 prompt 文本)
- 全测试 `uv run pytest tests/ -q` 期望 979 passed (T-PR-05 后基线), 0 regression
- **high-risk 必跑 baseline_l2_snapshot** (CLAUDE.md D-072.1 守门): before/after EPSILON=1e-6, 期望 0 diff (改的是 prompt 文本 + CLI prompt 文本, 不动 L2 14 维)
- `_patch_system_prompt_for_cli` 锚点测试现有, 应保留 (本任务不动顶级标题)
- 现有 `test_cli_output_section_mentions_narrative` 应保留 (CLI prompt 文案改了但 narrative 关键短语仍在)

### 自检 (实施后)

- grep `prompts/rerank_system.md` 含 "0.9-1.0 强命中" (修订 1)
- grep 含 "若候选输入有同品牌多变体" (修订 2)
- grep 含 "explore 稀薄 escape" (修订 3)
- prompt 长度增量 ≤ 200 字符 (3 处增订加起来 ~150 字, 可接受)

## Rollback notes

- 单文件改动, rollback = `git checkout HEAD~1 -- prompts/rerank_system.md`
- 不涉及代码 / schema / trace 兼容性
- 修订 1 加 rubric 后 LLM 评分一致性应 ↑, 极端 case 可能让 LLM 把锚点当死规则而非启发, 实际收益等 T-PR-07 人工对比验证

## 不做

- 不重排权重列表 §1-§6 (T-PR-03 已落)
- 不动 refine_intent 字段口径 (T-PR-04 已落)
- 不动 `raw_understanding` 文案 (T-PR-01 已落)
- 不动 `# 输出方式` 锚点 (T-PR-05)
- 不动 schema 字段约束 (taste_match: number 0-1; one_line_reason: string maxLength=60)
- 不动 `chisha/rerank.py` 代码 (本任务纯 prompt 文案)
- 不引入 idx / taste_match 数值阈值化条件 (Codex 反对)
- 不修 sweet N 字段表 0-3 vs 2-5 显示规则不一致 (T-PR-03 Phase 4 advisory #1, 留后续 prompt cleanup task)

## Plan 规模

- 本文件: ~120 行, ≤ 200 ✅
- Affected files: 2 (prompts/rerank_system.md + chisha/rerank.py), ≤ 5 ✅

## Changelog iter 2 (接受 Codex iter 1 1 BLOCKER + 2 advisory)

| Issue | Codex 反对 | 主 agent 处理 |
|---|---|---|
| BLOCKER 1 | `_CLI_OUTPUT_SECTION` (rerank.py:121-150) 被遗漏, CLI 路径看不到主 prompt 修订, 两路径漂移 | 接受. 修订 1/2 改为双路径同步 (prompts/rerank_system.md + chisha/rerank.py). risk medium → high (12-file 白名单). Phase 4 reviewer 升 adversarial-review. baseline_l2_snapshot 必跑 |
| advisory 1 | # reason 示范 line 113 "比另两条油低一档" 跟修订 2 条件化措辞处置未说明 | 接受. 修订 2 明示"该正例保留 — 它在'有可比对象'场景下符合修订 2 第二条" |
| advisory 2 | "候选稀薄" vs "explore 稀薄" 语义区分未在 plan 显式说明 | 接受. 修订 3 加语义区分说明, CLI 路径 narrative 文案不需同步 escape 子条 |

## tasks.json 更新 (Phase 5 前)

T-PR-06 `regression_risk` 从 `"medium"` 改为 `"high"` (跟 T-PR-03 同模式)。

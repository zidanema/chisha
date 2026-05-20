# T-PR-03 · rerank §6 健康语义归位 — Plan

参考 spec: `specs/T-PR-03.md`. 参考 brief: `docs/proposals/2026-05-20-prompt-effect-optimization.md` §3.2 P0-E2.

## Affected files

- `prompts/rerank_system.md` (改, §重排原则 §6 重写 + 新增"健康风险披露"段)
- `chisha/rerank.py` (改 1 行: `:1212` CLI retry correction 旧术语 "健康结构" 同步, 见 Codex iter 1 blocker 2)

## Regression risk

- **high** (因新增 `chisha/rerank.py` — CLAUDE.md 12-file 高风险白名单命中, 即使只改 1 行字符串)
- **tasks.json 需要从 medium → high 同步**
- Phase 4 reviewer 升级为 `/codex:adversarial-review` (不是 /codex:review)
- baseline_l2_snapshot 期望 0 diff (L2 不动, prompt 改不影响 14 维打分, rerank.py 改的是 CLI retry correction 文案不是逻辑)
- 测试守门: `tests/test_rerank.py` 现有断言全绿即可 (schema 不变, _patch_system_prompt_for_cli 锚点 `# 输出方式` 不动)
- `risk_flags` schema 字段已存在 (`chisha/rerank.py:72-75` `array of string`), 本任务只在 prompt 文案里强调它的语义, 不改 schema

## Step-by-step

### 修订 1: 权重列表删除 §6 健康结构

**位置**: `prompts/rerank_system.md:23-31` 段 "# 重排原则（权重严格降序）"

**改动**:
- 删除 §6 "**健康结构**" 整行 (line 30)
- §7 多样性上移为 §6 (重编号 1-6)
- 段头保留: "权重严格降序", 但项目减为 6 项

新版权重列表:
```
# 重排原则（权重严格降序）

1. **硬约束** — 上文 §硬过滤 段, 永远先满足. spicy_level > spicy_tolerance / avoid_dishes / processed 主菜 等. **任何用户意图都不能覆盖硬约束**.
2. **refine_intent (结构化)** — D-073 新增, refine 二轮的用户结构化意图. ... (内容保留, 不动 — T-PR-04 才动 V1/V2 口径)
3. **refine_input (原文)** — ... (保留)
4. **daily_mood + last_feedback.chips** — ... (保留)
5. **taste_description** — ... (保留)
6. **多样性** — 不与最近 3 天 cuisine / cooking_method 重复, 同分时给新菜系/做法加分. (从原 §7 上移)
```

### 修订 1.5 (Codex iter 1 blocker 2): `chisha/rerank.py:1212` CLI retry correction 同步

**位置**: `chisha/rerank.py:1211-1213`

**改动**: retry correction enumeration 引用了 `健康结构` 旧术语 ("硬过滤 avoid/spicy/processed, 口味命中, **健康结构**, 同品牌择优, refine_input/mood 优先级等"). 删 prompt §6 后此 enumeration 变成过期指令 — 模型会按旧术语找 system prompt, 找不到时困惑。

**最小化改动 (1 行)**: 把 enumeration 改为不依赖 §N 编号的描述, 改为引用 system prompt 内的实际段标题:
- 旧: `"硬过滤 avoid/spicy/processed, 口味命中, 健康结构, 同品牌择优, refine_input/mood 优先级等"`
- 新: `"硬过滤 avoid/spicy/processed, 口味命中, 健康风险披露 (不参与排序但要标 risk_flags), 同品牌择优, refine_input/mood 优先级等"`

替换 `健康结构` → `健康风险披露 (不参与排序但要标 risk_flags)`. 其余 enumeration 不动。

### 修订 2: 新增"健康风险披露 + 不主动美化"段

**位置**: 紧跟修订 1 之后, 即原 §7 (现 §6 多样性) 之后空一行, 新增独立段 "# 健康风险披露 (不参与排序, 但要如实暴露)"

**改动 (新增段, 不替换现有任何内容)**:
```
# 健康风险披露 (不参与排序, 但要如实暴露)

L2 已有 slot-aware `health_guardrail` (D-090) 做过健康风险加权, **你不需要重复降权也不应主动用健康做硬过滤**. 但你必须做两件事:

1. **风险披露**: 若你选的 combo 命中 **`oil_avg > 4`** (5 档制下油偏高, 对应 L2 `health_guardrail` 触发阈值 `> prefer_oil_level_at_most + 1`, D-090) / 任一菜带 `processed` (含主菜以外的配菜) / 任一菜 `甜 N ≥ 3` (sweet_sauce_level 0-3 schema 下高糖阈值, 对应 `chisha/score.py:245-265` sweet penalty + `:610-625` health_guardrail) 等明显健康风险, **必须在该 candidate 的 `risk_flags` 数组里标短词** (例: `["油偏高"]` / `["含加工肉"]` / `["糖偏多"]`). 多重风险列多条. **注: 甜 N = 2 是中等糖, 仅展示不要求 risk_flags 披露 — 但 narrative 也不要把含甜 2 菜品称作"低糖"**.

2. **不主动美化**: `one_line_reason` 和顶层 `narrative` **不得声称已避开 / 已过滤 / 已筛除** 这些健康风险 (违反 D-085 Faithful Refine — 信任放大器是欺骗最严重的反模式).
   - 例: 选了高油 combo 时, narrative 不能写"为你挑了低油菜". 应写: "本轮候选油普遍偏高, 已尽量挑相对清淡的".
   - 例: 选了带 processed 配菜时, one_line_reason 不能写"无加工肉". 应在 risk_flags 标 `["含加工肉"]`, reason 可以说"虽含加工肉腊肠但搭配凉拌青菜平衡".

**不在本段范围**: 健康风险不是 hard filter (新业务规则需 D-082/D-083 口径更新, 本轮不动). 现有硬约束仍只有 §硬约束段三项 (avoid_dishes / spicy_level / processed 主菜).
```

### 修订 3: 现有"# narrative 字段" 段 + "# reason 示范" 段是否需要联动

**位置**: `prompts/rerank_system.md:85-112`

**改动**: **不动**。
- §narrative line 89 现有 "引用...健康约束等输入信号" 措辞 已经在风险披露语境下生效, 不矛盾。
- §reason 示范 line 102 "命中你健身餐需求" 是 exploit 正例, 不涉及"声称已避开健康风险" 反模式, 保留。
- T-PR-06 才动 taste_match rubric / one_line_reason 比较措辞 / explore escape — 本任务不动。

### 修订 4: §边界段是否需要补充

**位置**: `prompts/rerank_system.md:114-123`

**改动**: **不动**。
- 现有 §边界 line 117 已有 `taste_match < 0.3` → risk_flags 加短词的语法, 与新 §健康风险披露段一致。
- 不增不减边界条款 (T-PR-06 才动 explore 稀薄 escape)。

## Test strategy

- **不加新测试** (eval fixture 留 T-PR-02 / 整体守门留 T-PR-07)
- 现有 `tests/test_rerank.py` 全跑, 应全绿 — 它断 schema / validator / 兜底, 不依赖 prompt 文案
- `_patch_system_prompt_for_cli` 守门测试 (`tests/test_rerank.py` 内): 改 §重排原则段 + 新增段 不应破坏顶级 `# 输出方式` 锚点 + 末尾 "select_top_candidates...现在等待" 锚点
- 全测试 `uv run pytest tests/ -q` 应与改前条数一致 (无新增 / 无失败)
- **rerank.py 改 1 行字符串后必跑 baseline_l2_snapshot** (high-risk 文件白名单, D-072.1 守门要求): EPSILON=1e-6 严格回归 — 期望 0 diff (改的是 CLI retry correction 文案不是逻辑)
- grep `健康结构` 在 `chisha/rerank.py` 内应 0 命中 (修订 1.5 完成的标志)

### 自检 (实施后)

- grep `_patch_system_prompt_for_cli` 改的两个锚点 (`# 输出方式` + `select_top_candidates...现在等待`) 在 prompts/rerank_system.md 仍存在
- grep "健康结构" 应该只在 §健康风险披露段 出现, 不在权重列表里 (修订 1 删除)
- grep "重排原则" 后跟的列表项数 = 6 (修订 1 完成的标志)

## Rollback notes

- 单文件改动, rollback = `git checkout HEAD~N -- prompts/rerank_system.md`
- 不涉及代码 / schema / trace 兼容性
- 修订 2 新增段**绝对**位置: 放在 `# 重排原则` 段之后、`# 输入格式速查` 段之前 (rerank_system.md:32 之前) — 与权重列表语义关联, 但不挤入权重排序
- 修订 2 新增段不要插到 `# 输出方式` 段内部 (`# 输出方式` 是 `_patch_system_prompt_for_cli` 替换锚点段, 整段会被 CLI 路径替换 — 新内容会丢)

## 不做

- 不动 `chisha/rerank.py` 的逻辑 / schema / _RERANK_TOOL / _CLI_OUTPUT_SECTION / _validate_llm_candidates_v (本任务只改 `:1212` retry correction 字符串文案, 见修订 1.5)
- 不新增 hard filter 阈值 (D4 已决: 不加; 健康风险只在 risk_flags 暴露, 不参与硬过滤)
- 不动 §硬约束段 (line 17-22) 三项 — 它们是 D-082/D-083 当前口径
- 不动 §narrative / §reason / §边界 / §输入格式 / §输出方式 段 (T-PR-04/05/06 才动)
- 不动 D-090 `health_guardrail` 在 L2 的现有逻辑 (那是 chisha/score.py, L2 范围)

## Plan 规模

- 本文件: ~165 行, ≤ 200 ✅
- Affected files: 2 (prompts/rerank_system.md + chisha/rerank.py), ≤ 5 ✅

## Changelog iter 2 (接受 Codex iter 1 2 BLOCKER)

| Issue | Codex 反对 | 主 agent 处理 |
|---|---|---|
| 1 (P0) | `oil_avg ≥ 4` 与 `score.py:606` `oil_avg > prefer_oil + 1` (默认 prefer=3, 等价 `> 4`) 不一致, 边界 case `oil_avg=4.0` 时 L2 不触发但 prompt 要求披露 — 两层不一致 | 接受. 修订 2 阈值改为 **`oil_avg > 4`**, 显式引用 L2 `health_guardrail` 触发阈值 `> prefer_oil_level_at_most + 1` (D-090), 文档对齐 |
| 2 (P0) | `chisha/rerank.py:1212` retry correction 仍引用 `健康结构` 旧术语, 删 §6 后过期 — plan 宣称不动 rerank.py, 但实际必须同步 | 接受. 加修订 1.5 (1 行字符串替换: `健康结构` → `健康风险披露 (不参与排序但要标 risk_flags)`); affected files 加 `chisha/rerank.py`; **risk 从 medium 升 high** (CLAUDE.md 12-file 白名单命中); Phase 4 reviewer 升 `/codex:adversarial-review`; baseline_l2_snapshot 必跑 (期望 0 diff) |

无拒绝项, 无过度谨慎判定。

## Changelog iter 3 (接受 Codex iter 2 NEW BLOCKER + 文字清理)

| Issue | Codex 反对 | 主 agent 处理 |
|---|---|---|
| 甜阈值 (iter 2 #6) | `甜 N ≥ 4` 在 schema (0-3 int) 下不可达; `score.py:245-265` 用 `sweet_sauce_level >= 3` | 接受. 改为 **`甜 N ≥ 3`**, 显式引用 score.py:245-265 + 610-625 阈值对齐 |
| Rollback 措辞 (iter 2 #4 minor) | rollback 段说 "不应放在 `# 输出方式` 之前" 跟 plan 实际位置 (在 `# 输出方式` 之前) 矛盾 | 接受. 重写为 "新增段位置: `# 重排原则` 后、`# 输入格式速查` 前 (不要插到 `# 输出方式` 段内部, 那段会被 CLI 路径替换)" |

## tasks.json 更新 (Phase 5 前必做)

在 commit 前 (Phase 5 step 1), 把 `specs/tasks.json` 中 T-PR-03 的 `regression_risk` 从 `"medium"` 改为 `"high"`. 这跟 status 更新同一次 staging.

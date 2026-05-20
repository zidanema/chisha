# T-PR-04 · rerank refine_intent 字段口径同步 V1 + V2 reference 说明 — Plan

参考 spec: `specs/T-PR-04.md`. 参考 brief: `docs/proposals/2026-05-20-prompt-effect-optimization.md` §3.2 P0-E1 + Codex 盲点 #1/#2.

> **读者提示 (避免文件混淆)**: 本 plan 是 **plan 文档**, 描述对 `prompts/rerank_system.md` 的修改。文中引用 `chisha/refine.py:XX` / `prompts/rerank_system.md:XX` 行号是 **plan 元说明**, 不进入 prompt 文本。修订 1-3 各自 "改动" 段才是真的 prompt 文本块。修订 3 提到的 "禁止空泛形容" 锚点在 **`prompts/rerank_system.md:99-101`** (T-PR-03 落后行号), 不在本 plan 文件。

## 代码事实校准 (Phase 0 调研结果)

- `chisha/context.py:57` `refine_intent: dict | None` — context schema 一直是 V1 字段 (`RefineIntent.to_log_dict()`, `chisha/refine_intent.py:87-88`)
- `chisha/refine.py:173` `refine_intent=intent.to_log_dict()` — refine 入口注入的是 V1, **不是 V2**
- `chisha/rerank.py:490-499` `_context_block` 读 `ctx.refine_intent` 非空键, 拼成 `refine 意图 (结构化): cuisine_want=...; ingredient_want=...` — 全是 V1 字段名
- V2 `reference` (`lighter` / `similar_but_different_venue`) 真消费在 `chisha/refine.py:202-246` (T-P2-01 reference resolver), **L3 上游软重排, 不入 ctx**
- `[CONTEXT]` 段实际包含: `饭期` / `心情` / `上顿` / `最近 3 天 cuisine` / `最近 3 天 cooking` / `上次反馈 chips` / `refine_input` 原文 / `refine 意图 (结构化): <V1 字段>` (`rerank.py:479-498`). **本任务只关心 refine 相关字段, 即 refine_input + refine_intent (V1)** — 其它 ctx 字段不在 T-PR-04 范围

**结论**: spec 推测的"`[CONTEXT]` 段可能出现 `reference 信号: lighter/...`"**不成立** (reference 不入 ctx, 仅上游影响 candidate 顺序), plan 必须修正。本任务的真实改动:
- 修订 1: §2 V1 描述已对齐, **加一句锁定契约** (防未来 prompt 漂移到 V2 假设)
- 修订 2: 在 §2 末尾加 reference 上游消费说明 (L3 看不到字段, 但 candidate 顺序已被影响)
- 修订 3: § narrative 段补 unsupported 字段禁线

## Affected files

- `prompts/rerank_system.md` (改, §重排原则 §2 + §narrative 字段段; 单文件)

无 .py 改动 → risk **medium** (不命中 12-file 高风险白名单)。

## Regression risk

- **medium** (CLAUDE.md 红线: prompts/*.md 不在 12-file 高风险白名单)
- baseline_l2_snapshot 不强制跑 (prompt 改不影响 L2; T-PR-07 整体守门会跑)
- 测试守门: `tests/test_rerank.py` 现有断言全绿即可 (schema 不变, `_patch_system_prompt_for_cli` 锚点 `# 输出方式` 不动)

## Step-by-step

### 修订 1: §2 V1 字段口径**锁定**契约 (line 26)

**位置**: `prompts/rerank_system.md:26`

**改动**: 修订 1 与修订 2 合并到 §2 段的子 bullet 中 (见修订 2 完整内容). 锁定 V1 契约 + F-009 同步注记在 sub-bullet "字段口径" 里。

不动 §2 主句 (refine_intent 仍是排序权重 §2)。

### 修订 2: §2 末尾 inline 加 V2 reference 上游说明 — **固定位置**, 折 bullet

**位置**: `prompts/rerank_system.md` §2 refine_intent 段末尾 inline。**不放独立段**, 不放 §6 / # 健康风险披露 之间 (Codex iter 1 blocker 2)。

**改动**: §2 当前是单 paragraph, 改为主句 + 子 bullet 形式 (Codex iter 2 blocker 1: 单段过密影响 LLM 读取). 折成:

```
2. **refine_intent (结构化)** — D-073 新增, refine 二轮的用户结构化意图. 字段含 cuisine_want / cuisine_avoid / ingredient_want/avoid / flavor_tags / portion / staple_preference / price_band 等. 命中按字段类型置顶 (cuisine_want exact 优先于 soft, 优先于 ingredient, 优先于 flavor). 在硬约束 §1 不被违反的前提下, 是最高优先级.
   - **字段口径**: 以 V1 RefineIntent 为准, 不是 V2 schema. V2 字段不入 ctx; F-009 (Phase 1 启动后) 若让 V2 字段真注入 L3 ctx, 必须同步重写本契约 + §narrative 禁线段。
   - **V2 reference 上游影响**: 用户用相对表达 ("比昨天清淡" / "和上次那家差不多") 时, 上游 reference resolver 已对 relation ∈ {lighter, similar_but_different_venue} 做软重排, 你看到的 [CANDIDATES] 顺序已体现; relation=`avoid_pattern` 当前不消费, refine_input 原文若含 "不要像那次那样" 按原文判断即可。
```

**Codex iter 2 blocker 2 处理**: 删除"chisha/refine.py:202-246"工程行号 (它是 plan 自身文档说明用的, prompt 不应暴露代码行号给 LLM)。LLM 只需要知道"上游 reference resolver 已做软重排", 不需要知道在哪几行做。

### 修订 3: § narrative 段补 unsupported 字段禁线 (实际 line 96-105, T-PR-03 落地后行号漂移)

**位置**: `prompts/rerank_system.md:96-105` 现有 `# narrative 字段 (T-P1b-02)` 段 (T-PR-03 加新段后行号从 85-94 漂到 96-105)

**改动**: 在 line "禁止空泛形容" 项之后加一条新强制要求:
```
- **不得声称已执行 unsupported 字段** — refine_intent_v2 可能填了 `constrain.quality_floor` / `delivery_only` / `max_distance_km` / `reference.avoid_pattern` 等字段 (D-085 务实降级, L1/L2 不消费, 只透传 trace). narrative 措辞 **不能说**"已为你过滤掉快餐 / 已限制 1 公里内 / 已避开像那次的味道" — 这些字段没有真做执行. 若用户在 refine_input 提到对应诉求, narrative 可承认听到但不假装执行. 例: "你说想吃外卖, 系统目前不区分外卖/堂食, 仅按其他条件排".
```

与 T-PR-03 修订 2 §健康风险披露 第 2 点 "不主动美化" 语义同源 (D-085 第一原则的两个体现), 但 narrative 段专管 narrative, 风险披露段专管 risk_flags + reason。

## Test strategy

- **不加新测试** (eval fixture 留 T-PR-07 manual verification)
- 现有 `tests/test_rerank.py` 全跑, 应全绿 — 它断 schema/validator/锚点, 不依赖 prompt 文案
- `_patch_system_prompt_for_cli` 守门 (`# 输出方式` 锚点 + 末尾 select_top_candidates 锚点) 不应破坏
- 全测试 `uv run pytest tests/ -q` 应 973 passed (与改前一致)
- baseline_l2_snapshot 不强制跑 (prompt 改不影响 L2)

### 自检 (实施后)

- grep `prompts/rerank_system.md` 中 "V1 RefineIntent" 应有 1 命中 (修订 1 完成)
- grep "reference_resolver" / "T-P2-01" 应有 1 命中 (修订 2 完成)
- grep "unsupported 字段" 或 "已执行" 应在 narrative 段出现 (修订 3 完成)
- grep "redirect" / "constrain.functional" 等 V2 字段名应在 narrative 段以"不要声称执行"语境出现 (允许出现作反例; 但 §2 排序权重段不允许)

## Rollback notes

- 单文件改动, rollback = `git checkout HEAD~1 -- prompts/rerank_system.md`
- 不涉及代码 / schema / trace 兼容性
- 修订 2 引入了对 T-P2-01 reference_resolver 的提及; 若 T-P2-01 行为变化 (例: 改 relation 集), prompt 需同步更新

## 不做

- 不改 `chisha/rerank.py` (字段注入逻辑保持 V1, 本任务只让 prompt 文案对齐代码事实)
- 不改 `chisha/refine.py` reference 消费逻辑 (`avoid_pattern` 是死路这件事, prompt 文案说明即可, 不改代码 — F-009 路线)
- 不动 V2 schema 字段 (D-079 trace 兼容)
- 不让 L3 真消费 V2 字段 (跨阶段, F-009 Phase 1 推广后)
- 不动 §6 健康风险披露 段 (T-PR-03 已落)
- 不动 `# 输出方式` 锚点 + tool schema description (T-PR-05 才动)
- 不动 reason 示范段 / 边界段 (T-PR-06 才动 taste_match rubric + one_line_reason + explore escape)

## Plan 规模

- 本文件: ~120 行, ≤ 200 ✅
- Affected files: 1, ≤ 5 ✅

## Changelog iter 2 (接受 Codex iter 1 3 BLOCKER)

| Issue | Codex 反对 | 主 agent 处理 |
|---|---|---|
| 1 | `[CONTEXT]` 实际字段全集说"只有 refine_input + V1 intent" 过简, 漏 饭期/心情/上顿/最近3天 cuisine+cooking/上次反馈 chips | 接受. "代码事实校准" 段改为列全 8 个 ctx 字段 + 显式说"本任务只关心 refine 相关字段" |
| 2 | 修订 2 位置"实施决定 §2 末尾 / 独立段"留临场拍板会打散 T-PR-03 排序权重 vs 风险披露边界 | 接受. 固定为 §2 末尾 inline, 不放独立段, 不放 §6 / # 健康风险披露 之间 |
| 3 | narrative 段行号 85-94 漂移 (T-PR-03 加新段后变 96-105) + 缺 F-009 同步注记 | 接受. 修订 3 位置改 line 96-105; 修订 1 锁定句加 "F-009 落地时同步重写本契约 + §narrative 禁线段" |

无拒绝, 无过度谨慎。

## Changelog iter 4 (主 agent 二分类 Codex iter 3 两个 BLOCKER)

| Issue | Codex 反对 | 主 agent 判断 |
|---|---|---|
| iter 3 #1 (refine.py:202-246 残留) | plan 中仍有 `refine.py:202-246` | **拒绝 — 过度谨慎/误判**. plan 自身 §代码事实校准 (line 10) 和 Changelog (line 116) 是 plan 元说明, **不进 prompt 文本**. 修订 2 实际 prompt 改动文本 (子 bullet "V2 reference 上游影响") 已无任何代码行号引用. 已在 plan 顶部加 "读者提示" 显式说明 plan 文档 vs prompt 文本边界 |
| iter 3 #4 (line 96-105 无"禁止空泛形容") | Codex 读 plan 文件 line 96-105 找不到该锚点 | **拒绝 — 文件位置混淆/过度谨慎**. line 96-105 指 **`prompts/rerank_system.md` 的 line 96-105** (T-PR-03 落地后行号), 不是 plan 文件. 实际 prompt 文件 line 99 真有 "禁止空泛形容" 项 — `grep -n "禁止空泛形容" prompts/rerank_system.md:99` 验证. 已在 plan 顶部加读者提示明确这是 prompt 行号 |

**Stuck override 触发条件 (单一源 CLAUDE.md § run-task)**:
- iter == 4, regression_risk == medium → 允许 override
- 两个 BLOCKER 均为 Codex 文件混淆/过度谨慎, 非真问题 (漏依赖/跨文件 invariant/文件不存在)
- Phase 5 status 落 `done_with_disagreement` + commit message 加后缀

## Changelog iter 3 (接受 Codex iter 2 2 BLOCKER)

| Issue | Codex 反对 | 主 agent 处理 |
|---|---|---|
| iter 2 #1 | §2 修订 1+2 合并后单段过密, 影响 LLM 读取 | 接受. §2 折成主句 + 2 个 sub-bullet (字段口径 / V2 reference 上游影响) |
| iter 2 #2 | "chisha/refine.py:202-246" 工程行号暴露给 LLM, prompt 应隐藏实现细节 | 接受. 删除行号, 改为"上游 reference resolver 已做软重排"概念性表述 |

无拒绝, 无过度谨慎。

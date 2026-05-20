# T-PR-03 · rerank §6 健康语义归位 (风险披露 + 不主动美化)

参考: `docs/proposals/archive/2026-05-20-prompt-effect-optimization.md` §3.2 P0-E2 + §4 T-PR-03

## What

修订 `prompts/rerank_system.md` 单文件中 §重排原则 §6 (line 23-31 范围), 把"健康结构"从"权重严格降序里的排序信号"重写为"风险披露 + 不主动美化"约束:

1. **从权重列表 §1-§7 中删除 §6 "健康结构"** — 一个项目要么是 hard filter, 要么是 ordering 信号, 不能两者都是; 权重列表降级为 §1 硬约束 + §2-§5 + §7 多样性 (共 6 项)
2. **新增"风险披露 + 不主动美化"段** (放在权重列表之后或硬约束段附近):
   - 选取的 combo 命中 `oil_avg ≥ 4` / `processed_meat in 配菜` / `重糖` 等健康风险时, **必须在 `risk_flags` 数组里标出短词**
   - `one_line_reason` 和顶层 `narrative` **不得声称已避开/已过滤** 这些风险 (若实际选中, 应坦诚)
   - 不重复降权 (L2 已有 `health_guardrail` slot-aware, D-090); 不新增 hard filter
3. **现有 §硬约束段** (line 17-22) 保留不动 — 真硬过滤只有 avoid / 辣度耐受 / processed 主菜 三项, 这是 D-082/D-083 当前口径

## Why

- §6 原文 "你不需要重复降权, 但不可主动选触发健康风险的 combo" 既要 LLM 在权重列表第 6 位排序, 又要不参与排序 — LLM 行为不稳, 实测当 refine_intent_want=辣 + 高油 combo 同时存在时与 L2 期望不一致
- 改为"风险披露"语义后: L2 已做的健康 guardrail 不被 L3 二次扣分, narrative 也不会假装"为你避开了高油" (D-085 第一原则)
- Codex 对抗审强反对 Opus 原提议的 `oil_avg ≥ 4 + processed 主菜 → hard filter` 公式: 新业务规则需 D-082/D-083 口径更新, 本轮范围外

## Done When

- `prompts/rerank_system.md` §6 段已重写, diff 可对应 What 三项
- 权重列表 §1-§7 改为 §1 硬约束 + §2 refine_intent + §3 refine_input + §4 daily_mood/feedback + §5 taste_description + §6 多样性 (原 §7 上移; 顺序细节由实施决定)
- 新增"风险披露"段或扩展现有"边界"段, 明确"narrative 不得声称已避开"
- `uv run pytest tests/test_rerank.py -q` 全绿
- `_patch_system_prompt_for_cli` 守门测试通过 (改 §6 不应破坏顶级 `# 输出方式` 锚点)
- 全测试 `uv run pytest tests/ -q` 全绿

## Plan 规模上限

- `plans/T-PR-03.plan.md` ≤ 200 行
- Affected files ≤ 5

## Affected files (预估)

- `prompts/rerank_system.md` (改, §重排原则 + 边界段)

## 红线

- 不新增 hard filter 阈值 (`oil_avg≥4` 等) — 新业务规则需 D-082/D-083 更新 (D4 已决: 不加)
- 不改 `chisha/rerank.py` 调用逻辑或 schema
- 不动 `_patch_system_prompt_for_cli` 锚点 `# 输出方式` (T-PR-05 才动)
- 不删 D-090 `health_guardrail` 在 L2 的现有逻辑
- **同 `prompts/rerank_system.md` 文件**: 串行执行顺序 T-PR-03 → T-PR-04 → T-PR-05 → T-PR-06 (由 tasks.json 数组顺序保证), 实施前先 `git diff` 看本文件最新版

## 不做

- 不动 `chisha/score.py` 健康 guardrail 逻辑 (它是 L2, 本任务只动 L3 prompt)
- 不改 `risk_flags` schema 字段约束 (它已经是 `array of string`, 保留)
- 不动其他 §1-§5 §7 文案 (本任务专注 §6)

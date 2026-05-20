# T-PR-04 · rerank refine_intent 字段口径同步 V1 + V2 reference 说明

参考: `docs/proposals/2026-05-20-prompt-effect-optimization.md` §3.2 P0-E1 + Codex 盲点 #1/#2 + §4 T-PR-04

## What

修订 `prompts/rerank_system.md` §重排原则 §2 (refine_intent 字段说明, line 26 附近), 修正 V1/V2 跨 prompt 契约漂移:

1. **同步 refine_intent 字段口径为 V1 实际字段**:
   - 当前 prompt 描述: `cuisine_want / cuisine_avoid / ingredient_want/avoid / flavor_tags / portion / staple_preference / price_band` (V1/D-073 口径) ✅ 对应 L3 实际注入的字段
   - 不要描述 V2 字段 (`redirect / constrain / reference / reject_previous` 等) — `chisha/rerank.py:490-499` `_context_block` 注入的是 `ctx.refine_intent` 非空键, 当前 ctx 走 V1 intent
   - 若 prompt 当前已描述 V2 字段, 必须改回 V1; 若描述已经是 V1, 验证后保留
2. **新增 V2 reference 字段说明** (在 §2 末尾或独立小段):
   - `[CONTEXT]` 段可能出现 `reference 信号: lighter/similar_but_different_venue/avoid_pattern` 之类透传字段 (D-085 字段空洞务实降级)
   - **`avoid_pattern` 是 schema 死路** (Codex 盲点 #2): `chisha/refine.py:213-249` 不消费该 relation, fallback 到 raw parser; LLM 不应假定它被执行
   - 透传字段的处理原则: 看到了可以用于 narrative 措辞 ("听到你想要更清淡的"), **但不能声称已经在召回层过滤**
3. **narrative 强制要求段** (line 86-94) 补一句: "narrative 不得声称已执行 unsupported 字段 (`quality_floor / delivery_only / max_distance_km / reference.avoid_pattern`); 这些字段 L1/L2 不消费, 只透传到本 prompt"

## Why

- 跨文件契约漂移: refine v2 prompt 输出 V2 schema, 但 L3 当前看到的是 V1 字段 — LLM 在找不到声明字段时行为漂移, 走 freeform_note 兜底, 信号质量下降
- D-085 字段空洞策略已定: schema 抽出但 L1/L2 不消费, **trace 标 unsupported_in_recall + L3 narrative 不能假装** — 现在 prompt 不知道这点, narrative 可能编造"已避开"
- Codex 盲点 #1/#2: rerank prompt 描述与代码事实不符是最严重的 prompt 误导, 比 §6 健康半过滤更紧迫

## Done When

- `prompts/rerank_system.md` §2 段 refine_intent 字段描述与 `chisha/rerank.py:490-499` 实际注入的字段一致 (V1 口径)
- 新增 reference 字段说明或独立段, 明确 `avoid_pattern` 不被消费
- narrative 段补一句 "不得声称已执行 unsupported 字段"
- `uv run pytest tests/test_rerank.py -q` 全绿
- `uv run pytest tests/ -q` 全绿
- 实测一次 refine 文本含 "比昨天清淡" (`reference.relation=lighter`) → LLM narrative 措辞不出现 "已为你过滤掉重口" 之类执行声明 (改前后人工对比, 输出贴到 `plans/T-PR-04.review.md` 或 T-PR-07 的统一 review 文件)

## Plan 规模上限

- `plans/T-PR-04.plan.md` ≤ 200 行
- Affected files ≤ 5

## Affected files (预估)

- `prompts/rerank_system.md` (改, §2 + narrative 段)

## 红线

- 不改 `chisha/rerank.py` 代码 (字段注入逻辑保持 V1; 本任务只让 prompt 文案对齐代码事实)
- 不动 V2 schema 字段 (D-079 trace 兼容)
- 不动 `chisha/refine.py:213-249` reference 消费逻辑 (`avoid_pattern` 是死路这件事, 本任务只在 prompt 文案说明, 不改代码)
- **同 `prompts/rerank_system.md` 文件**: 串行执行顺序 T-PR-03 → T-PR-04 → T-PR-05 → T-PR-06 (由 tasks.json 数组顺序保证), 实施前先 `git diff` 看本文件最新版

## 不做

- 不让 L3 真的消费 V2 字段 (那需要改 `_context_block` 注入逻辑, 是跨阶段; 留 Phase 1 推广后 D-XXX)
- 不改 V2 schema 让 `avoid_pattern` 真生效 (D1 拍板后另开)
- 不动 §6 健康 (T-PR-03 独立)

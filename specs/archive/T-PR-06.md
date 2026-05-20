# T-PR-06 · rerank prompt 三项 P1 文案补丁 (taste_match rubric + one_line_reason + explore escape)

参考: `docs/proposals/2026-05-20-prompt-effect-optimization.md` §3.3 P1-4/P1-5/P1-6 + §4 T-PR-06

## What

只动 `prompts/rerank_system.md` 单文件, 三项 P1 文案修订:

1. **`taste_match` rubric** (P1-4): 在现有 line 79 字段说明附近加评分锚点段, 基于自然语言 `taste_description` 与 `[PROFILE]`, **不结构化为 cuisine/cooking/ingredient 三元组** (避碰 D-014 "taste_description 不结构化"):
   ```
   taste_match 评分锚点:
   - 0.9-1.0: 与 taste_description 强命中 (主要菜系/做法/食材都对上)
   - 0.7-0.9: 部分命中 + 整体方向一致
   - 0.5-0.7: 同品类替代 / 与 taste_description 部分契合
   - 0.3-0.5: 仅大类命中 (如同为中餐)
   - 0.0-0.3: 与 taste_description 方向冲突 / 接近 disliked_cuisines
   ```
2. **`one_line_reason` 比较措辞修正** (P1-6) — Codex 盲点 #5: 现有 line 81 "对比 (说出为什么是这条而不是另两条)" 会诱导编造比较对象; 改为:
   ```
   - 若候选输入里有同品牌多变体 → 必须说明为什么选这条不选同品牌另一条
   - 若候选有可比项 (相邻 rank / 同 cuisine 多个) → 可点出取舍
   - 无可比对象时 → 给具体命中证据 (refine/taste/context 关键词), 不强行比较
   ```
3. **explore 稀薄 narrative escape** (P1-5): 在 §narrative 段 (line 86-94) 加定性 escape 子条 — **不绑 idx 阈值 / 不绑 taste_match 阈值** (Codex 反对 Opus 原阈值规则: idx 不等于稳定 rank, taste_match 是 LLM 自报):
   ```
   - 当 explore 槽只能选 "与 refine 弱相关 / 仅多样性补位" 的候选时, 
     narrative 必须显式声明 "后 N 条偏探索/备选, 当下命中度有限", 不要假装是 explore 主力
   ```

## Why

- 三项都属于 P1 prompt 文案补丁, 同源单文件
- P1-4 给 LLM 评分锚点, 实测 taste_match 同 case 两次跑出 0.6 / 0.85 方差大 (但 Codex 指出 feedback.py 没用此字段做 L1, 所以不上升为 P0)
- P1-6 是 Codex 发现的新盲点: 候选可能没有可比对象, "比另两条" 会让 LLM 编造比较 — 改为条件化比较
- P1-5 在 narrative 端兑现 D-080~085 第一原则的 L3 延伸 — explore 稀薄时坦诚降级, 不假装漂亮

## Done When

- `prompts/rerank_system.md` 三处修订全部落, diff 可对应 What 的三项
- 新增 taste_match rubric 段, 字数 ≤ 80 字 (不堆 token)
- one_line_reason 比较措辞改为条件化 (有可比对象才比较)
- §narrative 段加 explore 稀薄 escape 子条
- `uv run pytest tests/test_rerank.py -q` 全绿
- 全测试 `uv run pytest tests/ -q` 全绿
- baseline_l2_snapshot 0 diff (L2 不动)

## Plan 规模上限

- `plans/T-PR-06.plan.md` ≤ 200 行
- Affected files ≤ 5

## Affected files (预估)

- `prompts/rerank_system.md` (改, §field reason + §narrative + §taste_match rubric)

## 红线

- taste_match rubric 锚点不能用 cuisine/cooking/ingredient 三元组 (碰 D-014); 必须基于自然语言 `taste_description`
- 不改 `chisha/rerank.py` 代码 (本任务纯 prompt 文案)
- 不改 schema 字段约束 (`taste_match: number 0-1`, `one_line_reason: string maxLength=60` 保留)
- 不动 §6 (T-PR-03) / §2 refine_intent (T-PR-04) / `# 输出方式` 锚点 (T-PR-05)
- **同 `prompts/rerank_system.md` 文件**: 串行执行顺序 T-PR-03 → T-PR-04 → T-PR-05 → T-PR-06 (由 tasks.json 数组顺序保证), 实施前先 `git diff` 看本文件最新版

## 不做

- 不重排权重列表 §1-§7 (T-PR-03 在做)
- 不动 refine_intent 字段口径 (T-PR-04 在做)
- 不动 `raw_understanding` 文案 — **已由 T-PR-01 覆盖** (brief 原版把它列在 T-PR-06, 但同文件合并到了 refine prompt 路径的 T-PR-01)
- 不引入 idx / taste_match 阈值化条件 (Codex 强反对)

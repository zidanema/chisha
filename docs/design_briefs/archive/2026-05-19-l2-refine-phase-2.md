# L2 refine phase-2 (S1 草案)

> 日期: 2026-05-19 · 作者: Opus 4.7 (S1) · 待审: Codex GPT-5.4 (S2)
> 前序: D-090 phase-1 已落 (intent 三维权重 ×2~×4 + health_guardrail oil 触发 heavy 豁免).
> 触发: 志丹要求继续推 phase-2 留账.

## 现状 (phase-1 后)

R2 frozen replay top-5 湘菜数 2→5 (达标), 但 phase-1 留账 3 项:
1. **通用健康权重不让位**: low_oil / sweet_sauce / carb_quality / cuisine_preference 在 refine 模式下仍是 baseline 权重, 用户主动选的"重口湘菜"还在被 low_oil 扣 0.4 分 (虽然 intent 加分已盖过)
2. **intent_cuisine 通道语义重载**: score.py:768-776 把 price_band 加到 cuisine 通道, 调 intent_cuisine 权重会有 cross-spillover
3. **死维度未清理**: context_boost 是 stub 函数恒返 0 但权重 0.25 还在 (cosmetic); variety_bonus 实测 std=0 但本身是有意义的连续函数 (meal_log 不足导致), 不动

## phase-2 scope

### P2-A (主体): refine slot-gated 健康权重让位

`score_combo` 内部, intent ≠ None 时按 explicit slot 调整权重 (不引入新 profile schema):

| 触发条件 | 动作 |
|---|---|
| `flavor_tags ∋ "heavy"` | low_oil weight ×0.0 (用户明确要重口, 不再惩罚) |
| `flavor_tags ∋ "sweet"` | sweet_sauce weight ×0.0 |
| `staple_preference == "want_rice"` | carb_quality weight ×0.5 (白米饭会被 carb 扣分) |
| `price_band ∈ {cheap, premium}` | price weight ×0.5 (price 通道已有, 让位给意图) |
| `cuisine_want` 非空 | cuisine_preference weight ×0.5 (refine 优先于画像) |

R1 (intent=None) 路径不变 → baseline 严格 0-diff (CONTRACTS 红线).

### P2-B: intent_match_bonus 解耦 price_band

`score.py:768-776` 删 price_band 加到 cuisine 通道的逻辑 — price 维度已有独立通道, 重复加分污染 intent_cuisine 语义.

破 R2 snapshot? R2 trace intent.price_band=None, 实际无影响. 但 D-090 snapshot 测试可能微调断言 (intent_cuisine 数值或不变).

### P2-C: 死维度 context_boost 清零

`profile.yaml:165` context_boost weight 0.25 → 0.0. 函数恒返 0, 改权重 0-diff. 保留代码不删 (D-073 决策注释).

### 不做

- variety_bonus 死维度 (实测 std=0 是 meal_log 数据问题, 函数本身有意义, 改会破 baseline)
- vegetable_floor_pass / protein_floor_pass / distance / wetness 权重已是 0, cosmetic 不动
- multiplicative gate / score 归一化 (V2)

## 验收

1. R1 baseline `compare_traces` 0-diff (intent=None 路径不变)
2. R2 frozen snapshot 仍 pass (top-5 湘菜 ≥4); 新加 case: heavy flavor 时 low_oil breakdown=0
3. 新加 case: cuisine_want 非空时 cuisine_preference breakdown 减半
4. 全量 pytest 全过

## 实施步骤

1. Codex S2 对抗审 (本文件)
2. S3 收敛 → 写 docs/decisions.md D-091 (≤15 行)
3. 改 `chisha/score.py:score_combo` 加 slot-aware `_w` overlay; intent_match_bonus 删 price_band cuisine 通道; profile.yaml context_boost → 0
4. baseline_l2_snapshot 改前/改后跑 + compare_traces
5. 扩 `tests/test_l2_refine_snapshot_d090.py` 加 2 case + 全量 pytest
6. 更新 D-091 落账 + CONTRACTS 注 invariant

# L2 refine-aware 权重 overlay (S1 草案)

> 日期: 2026-05-19 · 作者: Opus 4.7 (S1) · 待审: Codex GPT-5.4 (S2)
> 触发: 志丹 2026-05-19 R2 trace 验收 — refine「湘菜+重口+牛肉鸡肉」L2 top-5 只有 2 家湘菜, 主要靠 L3 硬拉. 全链路追查见 docs/decisions.md (待加 D-090).

## 问题

R2 (refine) vs R1 (无 refine) 权重表 **完全相同**. 加性 19 维模型里:
- intent 三维满分合计 0.8 (实测 mean 0.35)
- 健康罚分四维合计 weight 3.3 (low_oil 0.5 + carb 0.6 + processed_meat 1.0 + sweet_sauce 0.7 + price 0.5)
- 用户说"湘菜重口" → low_oil 反过来惩罚湘菜重油菜
- variety_bonus 0.5 常数 (std=0) / context_boost 全 0 / wetness/distance/2 floor 权重 0 → 5 维冗余

R2 top-1 score=3.073, 把 intent_cuisine 0.5 拿掉仍 2.573, 全场 top-2~3 → **refine 不是它登顶的决定因素**.

## 方案 A: refine_overlay (推荐)

新 profile 字段 `refine_scoring_weights` (overlay, 仅 `intent ≠ None` 时叠加 over `scoring_weights`):

```yaml
refine_scoring_weights:
  # 提 intent 表达力 (Faithful Refine 第一原则)
  intent_cuisine: 1.00       # ×2
  intent_ingredient: 0.50    # ×2.5
  intent_flavor: 0.40        # ×4 (0.1 太低无效)
  # 画像让位 (refine 是当下意图, 优先于长期偏好)
  cuisine_preference: 0.15   # ÷2
  # 健康维度让位 (L0-C 类: refine 可破)
  low_oil: 0.25              # ÷2 (含 heavy/spicy flavor 时进一步)
  sweet_sauce: 0.30          # ÷2.3
  carb_quality: 0.30         # ÷2
  # 不动: popularity / eta / price / dish_role_match / taste_match
```

context-aware 二段加权 (refine 文本含 heavy/spicy flavor_tag 时):
- low_oil weight ×= 0.0 (完全关闭, 不惩罚用户主动选的重口)
- sweet_sauce weight ×= 0.5

## 方案 B (备选, 改动大)

multiplicative gate: `final = base × clip(0.5 + intent_match_factor, 0.5, 1.6)`. 破 baseline 严格回归红线 (CONTRACTS.md L2 段), 适合 V2 大改, 此次不取.

## 方案 C (最小动作)

只提 intent_* + 删 5 个 dead dim. 不解决"健康维度惩罚用户主动诉求"核心问题, 不取.

## 验收

1. **R1 baseline 0 diff**: refine_overlay 仅在 intent ≠ None 时生效, R1 (无 refine) top60 顺序 + 16 维 breakdown |delta| < 1e-6
2. **R2 refine 显著改善**: 同输入「湘菜+重口+牛肉鸡肉」, L2 top-5 湘菜数 ≥ 4 (当前 2)
3. **flavor_tag heavy 二段**: top-5 平均 oil_level ≥ 3 (当前 ~2.5, 被 low_oil 压制了重口菜)
4. **无新增 dead dim**: dim_stats std ≥ 0.05 的维度数不下降

## 实施步骤

1. Codex S2 对抗 (本文件 + R2 trace + score.py:27-52, 906-959)
2. S3 收敛 → 写 docs/decisions.md D-090 (≤ 15 行)
3. 改 `chisha/score.py:_w` 接 refine_overlay, profile.yaml 加 `refine_scoring_weights` + `refine_flavor_overrides`
4. baseline_l2_snapshot 改前/改后跑 + compare_traces
5. 用 R2 trace input replay, 验证 top-5 湘菜占比
6. 更新 D-090 落账

## 不做

- 不改加性模型为 multiplicative gate (破回归, 留 V2)
- 不删现有 19 维 (单独清理 dead dim 走另一个决策)
- 不引入 ML 学权重 (Phase 0 内手工校准)

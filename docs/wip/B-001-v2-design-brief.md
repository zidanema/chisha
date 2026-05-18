# B-001 v2 · 反馈短链路 — 全字段覆盖 design brief

> 状态: WIP, 待 codex review
> 触发: 志丹 2026-05-17 重申「B-001 没修好」: 反馈不止 rating, 还包括 4 维 calibration + note + comments[], 短期应**显著影响**下一/下几餐, 长期沉淀(L1) 保持严格
> Scope: B-001 v1 (D-081) 只覆盖 rating ±1, 这版补齐其余信号

## 1. Bug 重定义

**用户契约**: 用户用 V1.1 反馈表单提交的**所有字段**都应在**下一次刷推荐**时显著生效:
- `rating` (👎/👍) — ✓ B-001 v1 已覆盖
- `oil_calibration` (太油 / 太低) — ✗ 仅 L1 7 天后间接
- `fullness` (没饱 / 撑) — ✗ **被 L1 主动丢, 0 影响**
- `reason_match` (推荐理由对不对) — ✗ **同上, 0 影响**
- `repurchase_intent` (想再来) — ✗ L1 弱用, 短期 0
- `note` (自由文本) — ✗ 仅 L1 7 天后弱用
- `comments[]` (append-only 备注) — ✗ **完全 0 消费者**

**用户付出输入成本 ≠ 系统得到信号** = 反人类。

## 2. 四视角分析

### 视角 A · 用户

刷下一次推荐应**肉眼可见**变化:
- 勾"太油" → top5 平均 oil_level 降一档
- 勾"没饱" → top5 出现 complete_meal 套餐 / 加大 protein
- note "灶台鸭蛋油" → 灶台被压 + 油菜被压
- 👎 餐厅 → 30 天压出 top60 (v1 已做)

变化要**可解释**: L3 prompt 看得到「因为你刚说...」

### 视角 B · 产品

| 维度 | 短链路 (下一/几餐) | 长链路 L1 (7 天周期) |
|---|---|---|
| 阈值 | 1 条即生效 | 多条聚合 + 严格 |
| 衰减窗 | 3-14 天 | 30-60 天 |
| 粒度 | 餐厅/属性级具体 | 口味维度抽象 |
| 失败模式 | 噪声/过激 | 抽空/保守 |

短链路设计三原则:
1. **显著但有界** — 单条反馈最大改变 score 不超过 ±1.0 (与 feedback_recency 同级)
2. **衰减快** — 跨 1-3 餐就归零, 不堆积
3. **可解释** — L3 prompt 必须能讲清

### 视角 C · 工程/架构

- **baseline 守门 (D-072.1)**: 新维度必须**信号为空时不写 breakdown key**, 16 维 keyset (B-001 v1 +1 = 17 维) 严格不变
- **性能**: 短链路 inline 在每次推荐, **禁止调 LLM** (L3 已经在调, 重复调 = 双倍延迟)
- **数据源**: 全部从 feedback_store 已存字段派生, 不动 schema
- **note / comments[] 解析**: 用**词表正则** (复用 L1 BOOST/PENALTY_TOKENS), 不动 LLM
- **维度命名**: 不堆 10 维, 聚合成 2-3 维

### 视角 D · 数据/AI

- 4 维 calibration 已结构化 (0/1/2), 最容易接 — **第一优先**
- note/comments 用词表抽 token, 跟 L1 同一套词表 (`low_oil / wetness / spicy / sweet_sauce / processed_meat / carb_heavy`), 一致性好
- 跨次衰减: fullness/reason_match 只看**最近 1-3 餐**, 不像 rating ±1 跨 60 天
- 信号冲突: 同一字段多条 → 取最近最强; 同店不同属性 → 各自独立维度

## 3. 输入侧 · 信号派生 (新增 build_feedback_view 输出)

扩 `feedback_store.build_feedback_view(store, today)` 返回 2 个 view (旧 view 保持向后兼容):

```python
{
  "ratings": [...同 v1, 餐厅级 rating + age_days...],  # B-001 v1, 不动
  "calibrations": [                                    # 新: 最近 3 餐 calibration
    {
      "session_id": "...",
      "restaurant_name": "...",
      "age_meals": 0,        # 距今多少餐 (0 = 上一餐)
      "age_days": int,
      "oil_calibration": 0|1|2|None,
      "fullness": 0|1|2|None,
      "reason_match": 0|1|2|None,
      "repurchase_intent": 0|1|2|None,
    },
    ... (最多 3 条, 按 age_meals 升序)
  ],
  "note_tokens": [                                     # 新: note + comments[] 词表抽取
    {
      "restaurant_name": "...",
      "age_days": int,
      "boost": ["low_oil"],          # 来自 BOOST_TOKENS 词表
      "penalty": ["sweet_sauce"],    # 来自 PENALTY_TOKENS 词表
      "raw_text": "..."              # 截 80 字, debug 用
    },
    ... (最多 5 条, 按 age 升序, 窗 14 天)
  ]
}
```

派生规则:
- **calibrations**: 取最近 3 餐 (按 accepted_at 排序), 不限窗 (上 3 餐总是相关; 但如 age_days > 7 则丢)
- **note_tokens**: 跨 note + comments[], 跑 `extract_tokens(text)` 正则匹配 BOOST/PENALTY_TOKENS, 窗 14 天

### 词表扩展 (复用 L1 BOOST/PENALTY_TOKENS)

新加文件 `chisha/feedback_text_extract.py`:

```python
TOKEN_PATTERNS = {
    "low_oil":        [r"太油", r"油腻", r"很油", r"oily"],
    "wetness":        [r"汤", r"清淡", r"水分"],
    "spicy":          [r"太辣", r"辣", r"麻"],
    "sweet_sauce":    [r"太甜", r"齁", r"sweet"],
    "processed_meat": [r"加工肉", r"火腿", r"培根", r"香肠", r"罐头"],
    "carb_heavy":     [r"主食多", r"碳水", r"米饭多"],
}
# 否定前缀 ("不油", "不辣") → 反向 (boost 变 penalty 或互换)
NEGATION_PATTERNS = [r"不", r"没那么", r"不太"]
```

返回 `(boost: set, penalty: set)`. 输入空 / 无命中 → 空集。

## 4. 输出侧 · 新 L2 维度

### 维度 1 · `next_meal_calibration` (新, weight=0.8)

来源: `calibrations` (最近 1-3 餐)
作用 (累加, 上限 ±1.0):

| 信号 | 条件 | 影响 |
|---|---|---|
| 油 calibration 太油 | `oil_calibration=2` 且 `age_meals<=2` | combo 平均 `oil_level<=2` +0.5; `oil_level>=4` -0.5 |
| 油 calibration 太低 | `oil_calibration=0` | combo 平均 `oil_level>=3` +0.2 (松开) |
| 饱腹感不够 | `fullness=0` | combo `protein_floor_pass=1.0` +0.4; `is_complete_meal` 含 +0.3 |
| 饱腹感过 | `fullness=2` | combo 总菜数 ≤2 +0.3; ≥4 -0.3 |
| 理由不符 | `reason_match=0` | combo 与上次 cuisine 不同 +0.2 (推新东西) |

衰减 (跨餐): age_meals=0 取全权, age_meals=1 取 0.5, age_meals=2 取 0.25, age_meals>=3 不算

### 维度 2 · `note_boost` (新, weight=0.5)

来源: `note_tokens`
作用:
- 餐厅级: token 命中的餐厅 → 该餐厅所有 combo 拿 boost/penalty (复用 taste_match_bonus 的 token 评估逻辑)
- 跨餐厅: 14 天内 note 频繁出现的 token (≥2 次) → 自动转 effective_hints 短期 boost (与 L1 长期 boost 等价但不落 prefs.json)

衰减: `× exp(-age_days/7)` (7 天 e-fold)

### 维度 3 · `feedback_recency` (v1 已落, 不动)

### 不动的维度

- `taste_match` (L1 长链路产物) — 不动, 它管"长期沉淀"
- `low_oil` (V1 老维度) — 不动, 它管"通用 plate_rule"

## 5. L3 prompt 增强

现有 `[FEEDBACK_RECENT]` 段保留. 新增:

```
[LAST_MEAL_SIGNAL]                ← 短期 calibration 给 LLM 解释用
上一餐 (1d 前, 灶台): 太油 ✗ / 饱腹感不够 ✗ / 理由弱 ✗
(下一餐应: 控油 + 加量 + 换 cuisine)

[NOTE_HINTS]                       ← 文本反馈抽出的 token
近 14 天 note 提及: low_oil×3 / spicy×1
餐厅级: 灶台 - "太油" (2d 前)
```

**关键**: 排序压制全部靠 L2 score, prompt 仅解释用. 与 v1 一致。

## 6. 守门 + scope 红线

### 守门

- baseline_l2_snapshot: calibrations/note_tokens 全空 → 不写 `next_meal_calibration` / `note_boost` key → 16+1 keyset 不变
- pytest 覆盖: 每维度独立单测 + 边界 (空 view / 单条 / 冲突 / 衰减)

### 范围红线

- ❌ 不接 LLM 实时解析
- ❌ 不动 feedback schema (V1.1 不变)
- ❌ 不动 L1 长链路 (它继续严格)
- ❌ 不做菜品级反馈 (summary 自由文本, Phase 1)
- ❌ 不做跨用户聚合
- ❌ 词表只复用 L1 现有 6 token, 不扩

## 7. 开放问题 (待 codex 决策)

**Q1**: `next_meal_calibration` 跨餐衰减用 `age_meals` 还是 `age_days`?
- 选 A `age_meals` (跨吃几顿): 直觉但需读 meal_log 算
- 选 B `age_days` (距今几天): 不读 meal_log, 但用户连吃 2 顿同店时不准
- 我倾向 A, 但 B 更省事

**Q2**: `note_boost` 餐厅级 negative token (如"灶台太油") → 影响"该餐厅"还是"该餐厅 + 油菜"?
- 选 A 只压餐厅 (重复 feedback_recency 信号)
- 选 B 餐厅 × oil_level 双维度
- 我倾向 B, 信号利用更充分

**Q3**: 词表否定前缀如何处理? 否定 + boost 词 ("不油") → penalty 反向 (变 low_oil 反向 = 想吃油?)
- 选 A 严格匹配, 否定丢弃 (不算信号)
- 选 B 否定反向 (复杂)
- 我倾向 A, 简洁防误判

**Q4**: weight 配比建议 `next_meal_calibration=0.8` `note_boost=0.5` `feedback_recency=1.0`. 是否合理?
- 直觉: rating 是显式投票最重 (1.0), calibration 次重 (0.8), note 文本是侧信号 (0.5)
- codex 拍

**Q5**: `comments[]` (append-only) 进 note_tokens 还是单独维度?
- 选 A 与 note 合并 (统一文本源)
- 选 B 单独权重 (用户连续追加 = 重要)
- 我倾向 A, 信号同质

## 8. 实施清单 (S3 后)

1. `feedback_store.py`: 扩 `build_feedback_view` 返回 3 个 view
2. `feedback_text_extract.py` (新): 词表正则 + 否定处理
3. `score.py`: 加 2 个新函数 `next_meal_calibration_score` / `note_boost_score`, 接进 `score_combo`, 守门 0-key 规则
4. `rerank.py`: 扩 `_feedback_block` 加 2 段 prompt
5. `tests/test_feedback_v2.py`: 全维度 + 边界
6. baseline_l2_snapshot 跑 0 diff
7. sandbox e2e: 注入 4 维 + note → 看推荐变化

---

**review 时请回答**:
- Q1-Q5 选择
- 是否漏了关键 case (边界 / race / 守门)
- 维度命名 / weight 是否合理
- 实施清单 1-7 是否漏步骤

---

## 9. Codex review 共识 (2026-05-17, S2 落定)

### Q1-Q5 决策

- **Q1**: `age_meals` 为主, **加 `age_days <= 7` 硬闸**防极端 (虚拟时钟跳 / 长间隔)
- **Q2**: **restaurant × token 属性双维度**, "灶台太油" 只对灶台 combo 走 `low_oil` 维度叠加
- **Q3**: 否定前缀丢弃, 不做语义反转 (penalty-only token 如 carb_heavy 无对称语义)
- **Q4**: 权重接受 (calibration=0.8, note=0.5, recency=1.0). **v1 `feedback_recency_score` clamp `[-1.5, +0.25]` 保留不动** (动了破 baseline 0 diff 守门, EPSILON=1e-6 严格), 新维度 `next_meal_calibration` / `note_boost` 各自 clamp `[-1.0, +1.0]`. S5 codex 共识: 文档明示而不重 clamp.
- **Q5**: comments[] 合并入 note_tokens, **必须用每条 comment 自己的 `created_at`** (feedback_store.append_comment 时间字段独立)

### Codex 揪出的漏项 (必须解决)

1. **view shape breaking change**: build_feedback_view 从 list[dict] 改 dict 是 breaking, **必须一次过更新全部 call-site** — score.feedback_recency_score / rank_combos / rerank._feedback_block / api / debug_what_if / debug_recommend. 保留旧 fixture adapter
2. **What-if 冻结路径**: 新 view 结构必须进 `__frozen.feedback_view` snapshot, 否则 Replay/What-if 与 Live 出不同 score (D-079 红线)
3. **note_boost 不混入 effective_hints**: 单独 score, 否则 taste_match attribution 模糊
4. **reason_match=0 需结构化 last-meal cuisine**: rerank prompt 有, score 没有 — calibrations 派生时同时带上 `last_meal_cuisine: str`
5. **repurchase_intent 必须明示**: v2 暂定 no-op (留 L1 用), brief §4 表格补一行 "repurchase_intent → 不进短链路"
6. **is_complete_meal 是 dish 属性不是 combo 属性**: 改用 `dish_role_match_bonus` + `protein_floor_score` 当 fullness 信号载体
7. **L1 词表实际是 BOOST 4 + PENALTY 4 (有重叠)**: 不是 6 个, 词表抽取要照实对齐
8. **comments[] vs 推荐视图可见性 race**: append_comment 写后推荐视图下次刷新才见, **承认这是设计 (不做事务一致)**, 文档明示

### Top 3 实施风险 (Codex 拍)

1. view shape breaking — 一次过改全部 call-site, 否则 baseline 直接炸
2. baseline keyset 漂移 — 严格只在 weighted score != 0 时才写 key (跟 feedback_recency 同模式)
3. note_boost 过度打分 — clamp [-1.0, +1.0], restaurant-scoped 和全局分开测

### S3 实施合同 (基于共识)

**信号源派生 (feedback_store.build_feedback_view v2)**:
- 返回 dict `{ratings, calibrations, note_tokens}` (旧 list 调用方一次过改完)
- calibrations 带 `last_meal_cuisine` (从 accepted.session_id 反查 session 推荐第一道菜 cuisine 或 meal_log)
- note_tokens 跨 note + comments[], 每条 comment 用 `created_at`
- 否定前缀严格丢弃

**词表抽取 (新 feedback_text_extract.py)**:
- 复用 `l1_prefs.BOOST_TOKENS` (4) + `PENALTY_TOKENS` (4), 重叠 token 单独列
- 返回 `(boost: set, penalty: set, raw_matches: list)`

**L2 新维度 (score.py)**:
- `next_meal_calibration_score(combo, calibrations, profile) → float in [-1.0, +1.0]` (clamp), weight 0.8
- `note_boost_score(combo, note_tokens, profile) → float in [-1.0, +1.0]` (clamp), weight 0.5
- 老 `feedback_recency_score`: **补 clamp [-1.5 → -1.0]** 或 doc 修正 (跟 codex 共识倾向 clamp 到 ±1.0 统一), 落实需评估对老 baseline 影响

**Baseline 守门**:
- 3 个维度都遵守 "score == 0 时不写 breakdown key"
- baseline_l2_snapshot 跑前后, 老 fixture (无 calibration/note) 必须 0 diff (16+1 keyset)

**What-if 冻结 (debug_what_if.py)**:
- `__frozen.feedback_view` 从 list 改 dict, 同时改 sentinel 默认值约定 (`_UNSET_FEEDBACK_VIEW`)
- 写一组单测覆盖 frozen 路径

**L3 prompt (rerank.py)**:
- `_feedback_block` 接 dict view, 渲染 `[FEEDBACK_RECENT]` (老) + `[LAST_MEAL_SIGNAL]` (新) + `[NOTE_HINTS]` (新)
- 三段独立, 任一空则跳过

**测试 (tests/test_feedback_v2.py)**:
- 每维度独立单测 (空 / 单条 / 衰减 / clamp / 冲突 / restaurant scope)
- E2E: 注入 4 维 + note → score 变化 + 推荐排序变化
- Baseline 老 fixture 0 diff
- What-if frozen view 与 live 一致

**Repurchase_intent**: v2 短链路 **no-op**, 留 L1 长链路用. 文档明示.

**Race 文档化**: append_comment → 下次 refresh 才见, **不做事务一致** (单用户单进程, 可接受).

---

## 10. Codex S5 implementation review 落实 (2026-05-17)

S4 跑通后 codex 又找出 5 必改 + 4 v2.1 项:

### 必改 (本轮已落)
1. **feedback_recency v1 clamp 文档** — §9 明示保留 [-1.5, +0.25], 不动
2. **overlap token 互斥** — `feedback_text_extract.py` 按*意图*拆 `_BOOST_PATTERNS` / `_PENALTY_PATTERNS`, "想吃辣" → 仅 boost.spicy, "太辣" → 仅 penalty.spicy
3. **age_meals 真序** — `build_feedback_view` 用 datetime 排序 (含小时), 显式写 `age_meals` 字段; `next_meal_calibration_score` 直接读 cal["age_meals"] 不再 enumerate 推
4. **全局 note 频次跨餐厅去重** — 同一餐厅多条 note 只算 1 次 (按 (token, restaurant) unique)
5. **calibration 触发收紧** — fullness=0 改用 `protein_g >= 1.5×floor` (原 protein_floor_pass 几乎全过), n>=4 才 boost (原 n>=3), n<=2 反向 -0.2

### 放 v2.1 (跟 F-007 / F-011 一起考虑)
- normalize_feedback_view entry schema 防御 (KeyError 防护)
- note_tokens 最多 5 条 cap
- last_meal_cuisine meal_log fallback (仅 sessions 不够时降级)
- L3 prompt 显示 age_meals 字段 (debug 透明度)


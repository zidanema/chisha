# Faithful Refine 真兑现 — refine v2 schema 全字段收口

**日期**: 2026-05-21
**状态**: scope 共识达成 (志丹拍板), **待 codex 共商方案 + 拆 task 实施**
**第一原则**: refine schema 字段要么真消费要么砍掉, 不留"trace-only 装饰" 让 LLM 算了系统不办的字段
**契约**: 砍掉 D-085 第二句"字段空洞务实降级" — narrative "听见但不办" 条款失效

---

## 1. 背景: 起底过程

V1.0 收尾 (2026-05-20 prompt 优化 Step 1) 后讨论 BACKLOG F-009 (D1) / F-010 (D2), grep 后发现 refine v2 schema **大量字段是 trace-only**:

- D-085 列出的"字段空洞务实降级" (quality_floor / delivery_only / reference) 名单**不完整**
- 实际 L1/L2 不消费的字段还有: `cuisine_candidates_expanded`, `ingredient_synonyms`, `brand_avoid`, `cooking_method_avoid`, `food_form_avoid`, `functional.low_caffeine`, `functional.low_satiety_drowsy`, `constrain.max_distance_km`
- `reference` 已在 T-P2-01 真消费; quality_floor/delivery_only/max_distance_km/functional 志丹**实际不会用** (单用户视角拍死)

trace-only 字段的代价:
- LLM 每次 refine 算冗余字段 → token 浪费 + latency
- narrative 第一原则在 D-085 下被迫"听见但不办" → 长期看是信任放大器隐患 (D-085 推论 3)
- 字段堆积让下次 agent 改 refine 链路时 mental model 复杂

---

## 2. Scope: 砍 5 + 修 3 + 1 follow-up

### 2.1 砍 5 字段 (schema + prompt + code 全删)

| 字段 | 砍的理由 |
|---|---|
| `redirect.ingredient_synonyms` | `chisha/score.py:510 _INGREDIENT_BROAD` 代码硬词典已替代, L2 真用 `main_ingredient_type` 命中, LLM 算的 synonyms 是**重复劳动且没人消费** |
| `constrain.quality_floor` | 志丹不说"不要快餐 / 别给我萨莉亚级别的" |
| `constrain.delivery_only` | 志丹不说"只外卖 / 只堂食" |
| `constrain.max_distance_km` | 志丹不说"走路 10 分钟内" |
| `constrain.functional.{low_caffeine, low_satiety_drowsy}` | 志丹不说"别给咖啡 / 别吃了犯困" |

砍法: prompt 删 schema 字段定义 + 示例段, refine_intent_v2.py 删 default/coerce 逻辑, eval fixtures 同步删相关 case (T-PR-01 加的 "下午要睡觉 / 只堂食 / 只外卖" 几条要砍或改).

### 2.2 修 3 字段 (L1/L2 真消费)

| 字段 | 当前 | 真消费实现 |
|---|---|---|
| `redirect.cuisine_candidates_expanded` | LLM 抽, L1 不读 | L1 召回 `cuisine_want ∪ expanded` (含同源扩展, 不破坏 D-073 三桶 / D-084 三级回落). "想吃辣"召到川/湘/贵/重菜 |
| `redirect.brand_avoid` | LLM 抽, 不过滤 | L1 硬过滤: 命中 `restaurants.json[].brand` 的 venue 整体排除 (含其所有菜) |
| `redirect.cooking_method_avoid` | LLM 抽, 不过滤 | L1 硬过滤: 命中 `dish.nutrition_profile.cooking_method` (7 类: 油炸/凉拌/生/炖/炒/煮/蒸) 的菜排除 |

数据层 audit 结果 (2026-05-21):
- `restaurants.json` 239 venue, brand 字段 **100% 覆盖** (201 distinct brands) — brand_avoid 可立刻做
- `dish.nutrition_profile.cooking_method` **11123/11123 100% 覆盖** — cooking_method_avoid 可立刻做
- `cuisine` 在 dish 维度已有 — cuisine_candidates_expanded 真消费可立刻做

### 2.3 follow-up: food_form_avoid (D-094.1, 待数据打标)

| 字段 | 当前 | follow-up 实现 |
|---|---|---|
| `redirect.food_form_avoid` | LLM 抽, **dish 数据层 0% 覆盖 food_form 字段** | 本轮**砍 schema**, 留 F-011 跟踪. 先打标 dish.food_form (面条/米饭/粥/汤/饼/...), 再加回 L1 硬过滤 |

砍法 + follow-up 理由: "不要面条" 是真诉求 (志丹确认), 但数据层 0 覆盖, 本轮硬上会出现"抽出来但没字段过滤"的 ghost field — 比 trace-only 还糟. **本轮砍干净, follow-up 数据打标完整后重新加回**.

---

## 3. 推翻 D-085 第二句的影响

D-085 (2026-05-18) 原条款:
> 字段空洞 (quality_floor / delivery_only / reference) 务实降级: 抽出但 L1/L2 不消费, 仅透传 L3 + trace 标 `unsupported_in_recall=true`.

D-094 实施后:
- `reference` 已 T-P2-01 真消费 ✅
- `quality_floor / delivery_only / max_distance_km / functional.*` **砍 schema** ✅
- D-085 第二句**完全失效** — 不再有"字段空洞务实降级"概念
- `DATA_LAYER_UNSUPPORTED_FIELDS` 常量删空 (refine_intent_v2.py:34)
- `unsupported_in_recall` schema 字段移除 (没字段是 unsupported 了)
- narrative 文案: 不再需要"听见但不办"的克制声明 — 真办了如实说, 没办的字段没存在

D-085 第一句"narrative + 状态条必须后置" 保留 (这是普适纪律).

---

## 4. 用户视角行为表 (砍+修后)

| 用户 refine | 砍/修前行为 | D-094 后行为 |
|---|---|---|
| "想吃辣" | L1 召回全集, L3 在全集里挑辣的 (运气) | L1 主动召回川/湘/贵/重菜进候选池, L3 大概率有辣菜可选 |
| "想吃肉" | L2 用 `_INGREDIENT_BROAD` 命中, 好使 | 不变 (LLM 不再算 synonyms 重复字段, 但行为不变) |
| "不要油炸" | LLM 抽 cooking_method_avoid, 系统不办 | L1 硬过滤 cooking_method=油炸 的菜 |
| "不要萨莉亚" | LLM 抽 brand_avoid, 系统不办 | L1 硬过滤 brand=萨莉亚 的 venue 整体 |
| "不要面条" | LLM 抽 food_form_avoid, 系统不办 | **本轮 schema 砍, narrative 不抽不响应**; F-011 数据打标后重新加回 |
| "不要快餐" | LLM 抽 quality_floor, narrative 撒不了谎 (D-085) | **schema 砍**, LLM 不抽, narrative 不响应 |
| "只外卖" / "走路 10 分钟" / "别给咖啡" | 同上 trace-only | 同上 schema 砍 |

---

## 5. 风险红线

**high-risk 文件白名单触碰** (4 个, 需 baseline_l2_snapshot 守门 + Codex Phase 4 review):
- `chisha/recall.py` — 加 2 个硬过滤 (brand_avoid / cooking_method_avoid) + cuisine_want 接 expanded
- `chisha/refine.py` — refine 模式接 V2 schema (T-P1a-03 _notes 提到的"V2 下游真消费"补完)
- `chisha/refine_intent_v2.py` — 删字段 + DATA_LAYER_UNSUPPORTED_FIELDS 清空 + schema 收口
- `chisha/score.py` — (可能) brand_avoid 命中负分?还是只 recall 硬过滤? **codex 共商决定**

**baseline_l2_snapshot 严格回归**: 空 refine 路径必须 0 diff (改 L2 链路硬约束).

**eval fixtures 同步**: T-PR-02 加的 4 case (低咖啡/堂食/外卖/反推) 要砍掉或改 case (用户文本保留, 但 expected slot 不再含被砍字段).

**prompt 文档跨文件契约**:
- `prompts/parse_refine_intent_v2.md` 删 5 字段 schema/示例 + 删 raw_understanding 中 "unsupported" 类短语职责描述
- `prompts/rerank_system.md:L112` 删 "不得声称已执行 unsupported 字段" 整段 (没 unsupported 字段了)

---

## 6. 工程量粗估 + 子任务草拆 (待 codex 共商后正式实施)

| 任务 | 工作量 | high-risk |
|---|---|---|
| T-FR-01 · prompt 删 5 字段 + 收口 schema/示例 | ~3h | 中 (只动 prompt 文件, 但跨 prompt 契约) |
| T-FR-02 · refine_intent_v2 删字段 + DATA_LAYER_UNSUPPORTED_FIELDS 清空 + tests 同步 | ~3h | 高 (refine_intent_v2.py) |
| T-FR-03 · recall.py 加 brand_avoid + cooking_method_avoid 硬过滤 | ~4h | 高 (recall.py) |
| T-FR-04 · recall.py cuisine_want 接 expanded (融入 D-073 三桶 / D-084 三级回落) | ~4h | 高 (recall.py) |
| T-FR-05 · refine.py 接 V2 schema (let cuisine_candidates_expanded 真传到 recall) | ~3h | 高 (refine.py) |
| T-FR-06 · rerank_system 删 unsupported 段 + 同步 CLI no-tool 段 (T-PR-05 模式) | ~2h | 高 (rerank.py CLI 路径) |
| T-FR-07 · eval fixtures 同步 (T-PR-02 case 删/改) + baseline_l2_snapshot 守门 | ~3h | 中 |
| **总** | **~22h** | 4 个 high-risk 文件 |

---

## 7. 落地流程

1. **本文件 v1 草稿** = 本提交 (志丹定 scope 后起草, 等 codex 共商)
2. 志丹 review brief 内容
3. 调 `codex:rescue` 共商方案 — 重点拷问:
   - "想吃辣"的 expanded 真消费在 D-073 三桶/D-084 三级回落里怎么融入? cuisine_want=[] + expanded=["川","湘","贵","重"] 该走 bucket_exact 还是 bucket_soft?
   - brand_avoid 硬过滤是 venue 整体 (含其所有菜) 还是 dish 维度? 单店多 brand 怎么办?
   - cooking_method_avoid: dish.nutrition_profile.cooking_method 是 7 类硬枚举, 用户说"不要烧烤" LLM 怎么映射? (没"烧烤"类)
   - food_form_avoid 砍后, narrative 如何处理用户"不要面条"诉求? 兜底文本?
   - D-085 第一句保留情况下, narrative 文案怎么改才不破第一原则?
4. codex 共识达成 → Claude Code 原生 TaskCreate todolist 拆 7 个 task (依据 § 6 草拆, 一个原子动作一个 task)
5. 逐 task 实施 → 每个 task **commit 前强制调 `codex:rescue` 做 diff review** (本 brief 4 个 high-risk 文件命中 CLAUDE.md § 推荐链路改动红线, 强制走 Codex)
6. 所有 task done → 跑 baseline_l2_snapshot + 5-10 case 人工对比 → D-094 落 decisions.md (正式; 当前 D-094 是草, 实施完后改正式条目)
7. F-009 / F-010 closed by D-094, F-011 (food_form 数据打标) 留 BACKLOG 等下个数据轮次

---

## 附录 A: 数据层 audit raw (2026-05-21)

```
$ python3 audit dishes_tagged.json (11123 dish)
cooking_method: nutrition_profile 11123/11123 (100%) — 值集 {'油炸','凉拌','生','炖','炒','煮','蒸'}
food_form: 0/11123 — 不存在
brand: 0/11123 — dish 维度不存在

$ python3 audit restaurants.json (239 venue)
brand: 239/239 (100%) — 201 distinct brands (淘小粉/荣姐家常菜/金稻园/...)
```

## 附录 B: 与 BACKLOG.md 的关系

- F-009 (Faithful Refine 真兑现) — 范围**部分实施**, 部分砍掉: quality_floor/delivery_only/max_distance_km 砍 (志丹不用), reference 已在 T-P2-01 真消费. F-009 superseded by D-094
- F-010 (expanded/synonyms 词典化) — 范围**翻转**, 不迁词典而是 expanded 真消费 + synonyms 砍 (代码硬词典 `_INGREDIENT_BROAD` 已足). F-010 superseded by D-094
- F-011 (新建) — food_form_avoid 数据打标 + L1 硬过滤. 待数据轮次启动

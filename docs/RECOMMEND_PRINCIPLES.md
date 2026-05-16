# chisha 推荐系统设计原则

> 适用于：菜品/餐厅推荐场景；个人化、单用户、低数据量、可解释要求高。
> 起源：D-042（cap_per_restaurant）+ D-043（L2 重设计）期间，与 Codex 跨专家会诊形成。
> 后续任何对召回/打分/重排的改动都应**先对照本文**，再动代码。

---

## 1 · 分层职责

| 层 | 数量级 | 职责 | 不该做什么 |
|---|---|---|---|
| **L1 召回** (Recall) | 万 → 千 | **硬约束**：违反 = 错。健康/过敏/预算/履约/合规。回答"该不该出现" | 不做软偏好打分。不做多样性约束 |
| **L2 打分** (Score) | 千 → 百 | **软偏好差异化**：违反 = 不爽。口味/营养结构倾向。回答"谁比谁好" | 不重复 L1 已过滤的硬约束（→ 死分）。不做业务多样性 |
| **L3 重排** (Rerank) | 百 → 十 | **业务多样性 + 探索**：违反 = 体验差。同店/同系/同形态/历史多样性 | 不替 L2 修系统偏置。不长期承担"打分公式有 bug"的修补 |

**核心铁律**：硬约束放进打分 → 死分。软偏好放进硬过滤 → 候选过窄。多样性放进打分 → 多样性失效。

任何改动如果跨越了上述边界，必须能解释"为什么这是例外"。

---

## 2 · 打分维度的"群体方差"原则

一个维度参与排序的**真实影响力**：
```
影响力 = std(维度在候选集上的取值) × 权重
```

**规则**：
- 在目标候选集（例如 top30）上 `std < 0.05` 的维度 → **死分**，不该出现在打分公式
- `std × 权重` 决定了它对最终排序的"挤压力"，不是权重本身
- 任何对打分系统的改动必须**先看 std**，再调权重，不能凭直觉
- 调权重不能凭空创造区分度。要先让维度"活过来"（即在候选集上有实际方差），再校准权重

**死分的三种成因**（必须分别处理）：
| 类别 | 例子 | 处理 |
|---|---|---|
| 结构性死分 | vegetable_floor_pass（召回已强制） | **删**（权重=0）|
| 使用性死分 | taste_match 没传 hints | **改活**（兜底信号） |
| 数据稀疏死分 | processed_meat 召回里几乎不出现 | **三档处理**（见 §4）|

---

## 3 · 区分度预算

总分跨度 = Σ(std × 权重)。这个跨度就是"区分度预算"。

**预算分配方法**：
1. 跑一次实跑，统计每维度 std
2. 按"维度重要性"分配影响力（std × 权重）份额
3. 反推权重 = 期望影响力 / 实测 std
4. 跑实跑验证总分跨度是否拉开

**反例**（不要这样做）：
- "口味很重要，taste_match 给 0.8" —— 没看 std 就拍权重
- "carb_quality 是健康相关的，给 1.0" —— 不管这维度在候选集上是不是基本全 0

---

## 4 · 维度的"缺失态语义"

> **实现状态（2026-05-13）**: D-043 落地了原则 1-3、5-7、8 的大部分。原则 4 仅文档沉淀，**代码层 status 字段尚未实现**，列为 P4 工作。目前生产代码仍把 UNKNOWN/MISS/N/A 都返回 0，需要在 debug 时人工辨别。

**铁律**：未知、无风险、未命中**不能混成同一个 0**。

`carb_quality=0` 在当前公式下可能意味着：
- (a) combo 没主食 dish_role
- (b) 有主食但 `grain_type` 未知（LLM 没打到）
- (c) 有主食但是白米（不奖也不罚）

把这三种当成同一个 0 → 不公平 + 不可解释。

**处理范式**：
| 状态 | 含义 | 打分动作 |
|---|---|---|
| HIT | 命中（有数据 + 符合条件） | 加 / 扣分 |
| MISS | 未命中（有数据 + 不符合） | 0 或反向小分 |
| UNKNOWN | 没数据 | 0（或显式 None 不进求和） |
| N/A | 不适用（如 combo 没主食看 carb_quality） | 跳过 |

**实施**：每个维度函数返回 `(score, status)` 二元组，调试台展示 status。

---

## 5 · 缺数据维度的"兜底信号"

数据缺失不等于无信号。

| 维度 | 缺数据时的兜底 |
|---|---|
| `taste_match` 没 hints | 从 `profile.taste_description` **离线**抽 boost/penalty tags 固化到 profile，运行时直接读 |
| `context_boost` 没 mood | 按时段/季节推断 default mood（午餐 → want_balanced；夏季高温 → want_light），**置信度低**（权重打 0.3 折扣）|
| `popularity` monthly_sales=0 | UNKNOWN（不参与，不当 0）|

**关键**：兜底信号必须**低置信**。真实信号在时完全覆盖兜底。

---

## 6 · 多样性的层级

| 层级 | 例子 | 落点 |
|---|---|---|
| **会话间多样性** | 同店/同主蛋白 N 天不重复 | L1 召回 `diversity_filter` |
| **本轮 candidates** | 同店 ≤ K / 同菜系 ≤ M / 同形态 ≤ N | L3 重排前 cap_*（D-042 / D-043）|
| **探索-利用** | 强制 N_explore 槽位给新菜系/做法 | L3 LLM rerank `is_explore=true` |

**重要**：cuisine cap 不够，**必须有 food_form cap**。"潮汕粥 + 砂锅粥 + 艇仔粥"在 cuisine 上可能差异大（虾蟹/猪杂/鱼），但在"形态"上高度同质，体验上重复。

`food_form` 字段建议值：`粥 / 汤 / 拌 / 炒 / 煎 / 烤 / 炖 / 蒸 / 主食 / 其他`。可由 LLM 打标或规则推断。

---

## 7 · 不可补偿惩罚

加权和的最大缺点：**补偿性太强**。一个维度强，可以盖过其他维度弱。

例如：carb_quality=+1.0（糙米）× 0.6 = +0.6 可能盖过 sweet_sauce=+1.0 × 0.7 = -0.7 中间的差距，让一份"糙米糖醋肉"看起来合格。

**处理**：极强 penalty 不参与加权和的"互相补偿"，而是用**乘性折扣**或**一票否决**。

```
score = Σ(分量 × 权重)
if has_unforgivable_penalty(combo):  # 如 sweet_sauce ≥ 3 且 processed_meat 同时命中
    score *= 0.5  # 或直接 score -= 大常数
```

实施粒度：把维度划成"可补偿" vs "不可补偿"两类，后者在加权和之外单独计算。

---

## 8 · 反馈闭环（最根本）

**单用户系统的杠杆点不是先验权重调参，是后验反馈学习。**

没有反馈 → 所有权重都是猜的。反馈累计起来，才知道：
- 哪些 chips（"太油"、"想喝汤"）真的影响下次满意度
- 哪些 cuisine_preference 是用户真实偏好，哪些是写在 profile 里但实际不爱
- 哪些时段/天气真的对应 want_light vs want_indulgent

**当前实现（D-073 LLM 抽取层，2026-05-16）**：
1. **L2 当下 session 信号**：`refine.py` 调用 `parse_feedback` 解析 chip + note，仅本 session 影响 L3 prompt，**不**写入跨 session 文件
2. **L1 长期反馈层**：V1.1 反馈页（rating + 4 维 calibration + note）落 `logs/feedback/store.json` → `chisha/l1_extractor.py` LLM 抽取（`claude_code_cli` text + JSON prompt + parse/validate/retry）→ 写 `data/long_term_prefs.json`
3. **L2 打分读取**：`rank_combos` 调 `l1_prefs.load_prefs()` → `to_runtime_hints()` → 三源合并 `merge_hints`：profile 静态 hints + L1 prefs + 显式 taste_hints
4. **抽取阈值**：`based_on_meals < 3` 不调 LLM；boost/penalty 各 ≤ 2 个 token；6 token enum 严格校验（low_oil / wetness / sweet_sauce / processed_meat / carb_heavy / spicy）
5. **不**做权重在线更新；**不**做 RL（数据量不足，过早复杂化）

**❌ 已废弃路径（D-043 P3 → D-073 PR-0.5 砍掉）**：
- `refine.py` 写 `data/feedback_history.jsonl` 频次累加（refine chip 是 L2 单次信号，不应跨 session 累加成"伪长期偏好"）
- `long_term_prefs.load_runtime_hints` 半衰期 30d + 拉普拉斯 ≥2 次平滑（模块标 DEPRECATED stub，仅 bootstrap 脚本读旧数据）

代码：`chisha/l1_extractor.py` + `chisha/l1_prefs.py`；写入：`chisha/web_api.py:/api/long_term_prefs/refresh` + `/api/sandbox/advance` 异步触发；读取：`chisha/score.py` `rank_combos`。

**反馈数据稀疏的应对**：
- LLM 抽取规则要求 ≥2 evidence 才出 token，避免单次反馈触发
- D-074 sandbox time-travel 模式可一次会话压缩多日累积，快速测试机制
- `scripts/bootstrap_l1_from_legacy.py` 冷启动兜底（读 D-043 旧 jsonl 生成首版 prefs，标 `bootstrap_from_legacy=true`）

---

## 9 · 错误的范式（已确认不走）

- ❌ **LinUCB / contextual bandit**：单用户、几十到几百条历史、过早复杂化
- ❌ **LTR pairwise loss**：数据量远不够，标注成本高
- ❌ **乘积融合代替加权和**：对 0 值更敏感，数据稀疏场景更危险
- ❌ **靠"调高权重"创造区分度**：先让维度有 std，再调权重

---

## 10 · 任何改动前的 checklist

改打分公式 / 召回过滤 / 重排逻辑前，逐条对照：

- [ ] 这是硬约束、软偏好、还是多样性？分层正确吗？
- [ ] 这个维度在目标候选集上 std 是多少？小于 0.05 是死分
- [ ] 维度的 HIT/MISS/UNKNOWN/N/A 四态分别该返回什么？
- [ ] 没数据时有没有兜底信号？兜底权重是否打折？
- [ ] 是不是又一个"补偿性"维度？需不需要"不可补偿"机制？
- [ ] 改完之后跑实跑，top30 std 拉开了吗？菜系/形态分布合理吗？
- [ ] 单测覆盖了边界（空 / k=0 / 缺字段 / 异常输入）了吗？
- [ ] 是否需要 Codex 跨专家 review？

---

## 11 · 与 Codex 跨专家会诊的关键共识

来源：D-043 期间（2026-05-13）。

**共识 11 条**（直接执行）：
1. 删冗余死权重（vegetable / protein floor / distance）
2. cap_per_cuisine + cap_per_food_form 串联
3. popularity 改 top30 percentile（rank-based）
4. taste_description 离线一次性结构化到 profile（规则词典，LLM 仅辅助初始化）
5. default mood 必须低置信弱先验（权重 ≤ 0.25）
6. 加权和保留 + 不可补偿惩罚
7. 维度要有缺失态语义
8. 重排只补救多样性，不替打分修偏置
9. variety_bonus 改连续函数
10. 不引入 LinUCB / LTR
11. 按实测 std 校准权重，不靠直觉

**Codex 最根本批评**：缺反馈闭环。chisha 现有 feedback.py / refine.py / session 落盘，但反馈**不回流**。这是单用户系统的核心命门。

---

## 12 · 偏好层 ≠ 行为层（profile 化方法论）

> 来源：D-044（2026-05-13）多轮口述重建 profile.yaml 时识别到的方法论错误。
> 适用于任何"从用户历史行为反推偏好"的场景，不限于 chisha。

**核心洞察**：从历史订单 / 点击 / 选择反推出来的"偏好"不是真实口味偏好，是**经过用户脑内健康/预算/便利性等约束过滤后的剩余物**。

例：用户过去 2 个月反复点"潮汕牛肉、酸菜鱼、翘脚牛肉"（清淡带汤水），不代表口味偏好清淡——可能恰恰相反，真实口味偏好辣椒炒/糖醋/红烧重口，过去选汤水是因为"这些菜看起来安全，控热量风险低"，是健康妥协的产物。

**为什么这个区分重要**：
- 把妥协行为当偏好 → 系统永远在重复用户的过往妥协 → 学不到真实口味 → 也出不来多样性
- 用户启动推荐系统的核心动机之一往往就是"反复点这几家吃腻了"——如果系统再喂回老路，价值清零

**正确分层**：

| 层 | 内容 | 系统怎么用 |
|---|---|---|
| **口味偏好层（taste）** | 真心喜欢什么（不考虑健康/预算约束） | LLM 精排 + reason 写作的输入 |
| **健康目标层（goal + plate_rule）** | 想达成什么（控重、足蛋白足菜、控油） | 召回硬过滤 + 打分软扣分 |
| **决策结果** | 在健康约束下，命中口味偏好的菜 | top-N 候选 |

**实现要点**：
1. `taste_description` 必须显式分段：**真实口味偏好** / **健康目标** / **历史行为 ≠ 偏好的提示** / **真实负向**
2. 真实负向（口味就不喜欢的东西，如干煸/凉拌/海鲜）和健康负向（要控的红烧/糖醋）分开记录，前者进偏好层，后者进属性维度打分（oil_level / sweet_sauce_level）
3. **禁止**把"健康角度想避开的菜"放进 `avoid_dishes` 菜名黑名单——必须走属性过滤，否则永远在重复历史妥协
4. LLM rerank prompt 必须包含"历史行为 ≠ 偏好"显式提示，否则 LLM 默认会按订单频次推断

## 13 · 隐藏目标识别（"这一顿能撑到下一顿"）

> 来源：D-044 朋友A失败教训。

**核心洞察**：用户表达的优化目标（"减脂"、"控油"、"低卡"）往往不是真实约束。真实约束可能藏在**失败模式**里。

例：用户长期吃朋友A私人订制健康餐（蛋白足 + 油少 + 味淡），账面上完全符合"减脂"目标，但每每半夜反弹点烧烤宵夜，**总热量反而更高**。这个失败模式说明：

- 表面目标："减脂" → 推 "热量最低的组合"
- 真实目标："不反弹" → 推 "能撑到下一顿的组合"

两者会推出完全不同的菜：前者倾向纯蛋白碗 / 清淡轻食，后者必须保证 **饱腹感、满足感、可持续性**。

**如何识别隐藏目标**：
1. 问用户"你过去尝试过什么方法失败了，怎么失败的"
2. 失败模式里通常藏着真实约束
3. 把约束翻译成现有字段的联合表达（如"饱腹感"→ `min_protein_g` 拉高 + 必含复合碳水 + 必含主食）
4. 不要新建字段，先看现有字段能不能联合表达——隐藏目标通常不需要新维度，需要的是**重新校准已有字段的阈值**

**通用模式**：当用户描述的目标看起来很合理但实际推不出好结果，先怀疑是否在优化错的目标函数。

---

## 14 · L0 方法论 spec 是工程化产物（D-072）

> 来源：D-070 三层信号模型 + D-072 spec 抽象。

**L0 方法论层** (`profiles/methodologies/*.yaml`) 不是"产品策略"，是**工程化产物** — 把原本散在 `score.py` 里的硬编码方法论参数（plate_rule / score_weights 16 维 / 4 层 cap / unforgivable_discount）搬到 yaml，让一个方法论的参数集变成**可复用、可校验、可比对**的资产。

**为什么不是简单 yaml**：
- 严格 keyset 校验（`chisha.methodology.MethodologyValidationError`）：拼写错的 weight key 必 hard fail，不许 silently 落 `V2_DEFAULT_WEIGHTS` 兜底（D-072 边界："spec 抽象只搬运，不改逻辑"）
- 顶层 7 必备字段 + 3 可选字段（`unforgivable_discount` / `soft_rules` / `extra_rules`），其中 `soft_rules` / `extra_rules` 是 V1 declarative 占位**不解释执行**（非空时 `logger.warning` 提醒）
- profile 显式字段始终 override spec defaults（`merge_into_profile` 用 `{**spec, **profile}` 双层合并），允许用户在方法论内做个人化微调（如志丹 `min_protein_g: 40` override 哈佛默认 25）

**与 L1/L2/L3 的关系**：
- L0 = 方法论参数 → 决定 L1 硬约束阈值（`plate_rule`）+ L2 权重（`scoring_weights`）+ cap 配置（`recall.per_*_top_k`）
- spec 不参与 L3 LLM 决策的"内容"，但 `_profile_block` 把 `display_name + rationale 首行` 注入 `[PROFILE]` 段，让 L3 显式知道用户的方法论 baseline（防 L2/L3 描述漂移）

**Phase 1 第二份 spec**（减脂 / 增肌 / 糖控）的接入路径：
1. 写 `profiles/methodologies/{name}.yaml`（7 必备字段全填）
2. profile.yaml 改 `methodology: {name}`
3. 跑 `scripts/baseline_l2_snapshot.py` 验证新 spec L2 输出符合预期
4. 若现有 schema 不够装新方法论（如减脂需要 "总热量上限" 字段），走 `extra_rules: []` 逃逸口先临时塞，等 D-072.M 修订条目把字段升正

**反 anti-pattern**：
- 不要把"个人化微调" 写进 spec（如 `min_protein_g: 40` 是志丹个人 override，不该写进 `harvard_plate.yaml`）
- 不要扩 spec 字段来"调"打分行为；调权重就改 profile.scoring_weights，不要绕道改 spec
- spec 必须能用 `baseline_l2_snapshot + compare_traces` 严格回归（重构前后 L2 trace |delta| < 1e-6, D-072.1）

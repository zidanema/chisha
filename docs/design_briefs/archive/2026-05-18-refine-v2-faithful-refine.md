# Refine v2 · Faithful Refine 推荐链路重设计

**日期**: 2026-05-18
**状态**: 设计完成，待开工。Opus 主导设计 + Codex 两轮 review + 志丹拍板共识版。
**关联决策**: 待落 D-080 ~ D-085（指回本 brief）
**作用**: chisha 推荐链路的 refine 路径 v2 设计 spec + 任务清单。

---

## 0. 问题陈述

志丹自用过程中的两个直观体感：

1. **refine 自然语言诉求"没被很好理解和满足"** — 用户用自然语言表达想吃什么（如"想吃湘菜、肉多一点"），系统返回的结果并不能稳定体现这些诉求。
2. **trace 里送 L3 的 combo 数有时凑不满 60** — 召回端容量不足，LLM 在不够 30 个候选上做精排。

代码事实验证（Codex grep 确认）：

| 现状 | 事实 |
|---|---|
| L1 召回数量参数（`per_restaurant_max=3` 等）不区分有无 intent | 写死走 `profile.recall`，无 `if intent` 分支 |
| `ingredient_want` 解析得出来但 L1 完全不用 | 只在 L2 加 0.2 权重，召回阶段不利用 |
| `cuisine_want` 免 3 层 cap（D-073.1） | 是补丁，未根治；带来"同品牌连锁日料刷屏"副作用 |
| L3 输入 top_k=60 无填不满兜底 | refine 收窄候选时 LLM 实际可能只看到 < 30 个 combo |
| 长期方法论（蔬菜占比 / 油上限 / 减脂目标） | 在 L2 是 `cuisine_preference 0.3` + `taste_match 0.4` 软分，与 popularity 0.4 / variety 0.5 同台 PK |

根因诊断：**系统把 refine 当成"打分修饰符"，而不是"召回方针重写"**。这是最严重的设计缺陷。同时，"原则派点餐执行外包"的产品承诺没在代码里兑现 —— 方法论硬契约和软偏好混在 L2 加权，导致用户设了减脂目标仍被推炒饭。

---

## 1. 第一原则（系统宪法）

> **Faithful Refine**: 系统对 refine 文本的**理解深度**和**执行忠实度**，是用户对 chisha 信任的唯一来源。当其他设计目标（多样性 / 效率 / 探索 / 美观 narrative）与"忠实于 refine"冲突时，**忠实优先**。

这一条将写入 `docs/CONTRACTS.md` 顶部。所有未来改推荐链路的 PR 必须先证明没违反它。

**推论**：
- refine 文本 ≠ 长期偏好的补丁。它是一次完整、独立、最高优先级的表达。
- 用户主动表达 > 系统预设（在普通健康约束维度）。
- 系统对 refine 的失败必须**显式告知用户**（"没找到 X，按相似口味推 Y"），不能默默偷换。

---

## 2. 三层架构（核心心智模型）

不同层对"用户当下意图"的态度完全不同。这是整个系统的人格分层。

| 层 | 内容 | refine 时怎么办 |
|---|---|---|
| **L0 硬契约（三分）** | 见下 §3 | 视类型决定 |
| **L1 意图层** | 菜系 / 食材 / 风味 / 烹饪方式 / 食物形态 / 品牌 | **完全推翻，按 refine 重新召回** |
| **L2 偏好层** | 历史口味画像 / 近期反馈衰减 | refine 时**降权但不抹掉**（作为口味 baseline） |

**架构 invariant**：refine = 推翻"意图层"，但 L0 安全契约和 L2 偏好层都还在工作。"完全推倒"指意图，不指人格。

---

## 3. L0 三分判定表（取代旧"硬契约 vs 破戒模式"二分）

Codex v1 review 挑出原"硬契约永不破 + 破戒模式临时禁 guardrail"自相矛盾。Codex v2 review 进一步指出"清真/素食"是身份伦理，不能跟健康混。最终判定表：

| 类型 | 例子 | refine 可否解除 | UI 行为 |
|---|---|---|---|
| **A. 医学风险类（安全）** | 严重过敏（花生/海鲜）· 药物冲突（华法林+西柚）· 孕期忌口 · 术后忌口 · 小孩过敏 | **永不可破** | 显式提示「检测到你对 X 过敏，已忽略 refine 里的 Y。若已治愈去 profile 改」 |
| **B. 身份伦理类** | 清真 · 素食 · 宗教忌口 | **永不可破**（只能 profile 改） | 同上模式 |
| **C. 普通健康类** | 油上限 · 糖上限 · 蔬菜占比 · 价格带 · 减脂目标 | **refine 明确表达可破** | 顶部明确提示「破戒模式 · 今晚一次性放开 · 不影响周报」 |

**副作用**：原蓝图 v1 的"破戒模式"作为独立 feature **取消**。等价于 refine 解除 C 类约束，政策大幅简化。Occam's razor 胜利。

**待 V2 阶段补**：`eater_context`（"替老人/小孩点"）。Phase 0 单用户，风险可接受，记入 BACKLOG。

---

## 4. Refine 多 Slot Schema

LLM 在意图扩展阶段一次输出结构化多 slot。**不再做"分类"，因为意图可叠加**（"想吃辣的，少油一点"= redirect + constrain 同时拍）。

```json
{
  "redirect": {
    "cuisine_want": [...],
    "cuisine_avoid": [...],
    "cuisine_candidates_expanded": [...],   // LLM 推断的隐含菜系集合（"辣"→[川/湘/贵州/重庆/韩]）
    "ingredient_want": [...],
    "ingredient_avoid": [...],
    "ingredient_synonyms": [...],           // LLM 同义扩展（"肉"→[排骨/牛肉/猪肉/鸡/鸭/羊]）
    "brand_avoid": [...],                   // 「别再给我萨莉亚」
    "cooking_method_avoid": [...],          // 「别生冷」「别油炸」
    "food_form_avoid": [...]                // 「别汤汤水水」
  },
  "constrain": {
    "oil": "low",
    "price_max": 50,
    "quality_floor": "non_fast_food",       // [字段空洞，见 §5]
    "delivery_only": true,                  // [字段空洞，见 §5]
    "max_distance_km": 1.5,
    "functional": {                         // 功能性需求
      "low_caffeine": true,
      "low_satiety_drowsy": true            // 「不困的，下午开会」
    }
  },
  "reference": {                            // 相对表达，能力跃迁
    "reference_meal_id": "...",             // 「比昨天清淡」「和上次那家差不多」
    "relation": "lighter" | "similar_but_different_venue" | "avoid_pattern"
  },
  "reject_previous": true | false,
  "raw_understanding": "..."                // LLM 自述理解，给 narrative + debug
}
```

**3 条安全带（裸 LLM 单点必备）**：

1. **Schema 验证 + 失败降级**：解析失败时**降级到"空 refine 模式"**（按长期偏好推），UI 提示「没听懂你说的，按你的日常偏好推了一组」。绝不崩，绝不瞎猜。
2. **Trace 双存**：raw 原文 + 结构化结果 + `raw_understanding` 三份都存。否则 "用户说想吃辣却推了粤菜" 无法 debug。
3. **冷启动 eval set**：30-50 条人工标注 refine 文本作回归集。改 prompt / 换模型时跑一遍。**这条最容易省，省了就是埋雷**。

---

## 5. 字段空洞的务实降级（保护 Faithful Refine）

Codex v2 grep 代码后发现 schema 里有字段在 chisha 数据层无支撑：

| 字段 | 现状 | 处理 |
|---|---|---|
| `cooking_method_avoid` | `nutrition_profile` 有，`recall.py` 已能硬过滤 | **可用** |
| `brand_avoid` | restaurant 表有 | **可用** |
| `food_form_avoid` | `score.py::infer_food_form()` 从菜名+cooking_method 推断 | **可用**（接受误判率） |
| `quality_floor: "non_fast_food"` | **无字段**，只能靠 cuisine/category/brand 名字猜 | **务实降级** ↓ |
| `delivery_only` / `max_distance_km` | 只有 `delivery_eta_min/distance_m`，不等于"不想出门"语义 | **务实降级** ↓ |
| `reference` 块 | `trace_store` 有 session_id 读取，但**无 `last_meal_id` resolver、无"更清淡/相似换家"比较器** | **务实降级** ↓ |

**务实降级策略**：

- 这些字段 **schema 仍保留 slot**，LLM 解析时仍输出
- L1/L2 **不消费**（避免 fake 过滤）
- 解析结果**只透传给 L3 prompt**（让精排 LLM 尽量配合）
- trace 中明确标 `unsupported_in_recall=true`
- 不假装做了。后续补字段时再升级。

**为什么不直接砍这些字段**：因为 Faithful Refine 原则 — LLM 必须真听懂用户在说什么，即使现在执行不了。"听懂但暂时做不到" 比 "假装没听见" 体感好得多，且为后续补字段铺路。

---

## 6. 分场景的链路参数对照

这是改造 L1 / L2 的核心参数表。**前提：refine 模式与空输入模式必须走差异化分支**，不能共用一套。

| 维度 | 空输入（探索/多样性优先） | refine 模式（满足/收敛优先） |
|---|---|---|
| `per_restaurant_max` | 3 | **5-8** |
| `ingredient_want` 用法 | 不用 | **进 L1 反查**（含肉/含鱼菜全召回） |
| 总召回上限 | 现状 | **2-3x** |
| `L3_INPUT_TOP_K` | 60 | 60，**保底「至少 30 个 intent 命中」** |
| Cap 豁免 | 4 层全卡 | 已免 3 层（D-073.1），restaurant cap 进一步放宽 |
| L2 权重平衡 | popularity 0.4 / variety 0.5 / cuisine_pref 0.3 / taste 0.4 | **满足 0.7 / 多样性 0.3**；intent_cuisine 仍 0.5；taste 降到 0.2 |
| 多样性维度 | **横向** cap（cuisine/brand/food_form） | **纵向**（intent 内部子类：湘菜分家常/小炒/腊味/剁椒；日料分拉面/寿司/居酒屋/定食/烤物）|
| Cap 失败兜底 | 无 | **三级回落**：精确 → 同源扩展 → 全集，每级 UI 显式告知 |

具体参数值最终落地时再调，本表只定方向。

---

## 7. methodology 拆两层（修最大产品 bug）

**最大产品 bug**：「原则派点餐执行外包」承诺没兑现 — 长期方法论（蔬菜 ≥ 50% / 油上限）只是 L2 一个权重，与 popularity 同台竞争。

**改造**：

- **硬契约（蔬菜占比 / 油上限 / 价格带）下沉 L1 `hard_filter`**：不满足直接出局，不是扣分
- **软偏好（喜欢的菜系 / 风味）保留 L2 加权**
- 现在两者混在 L2 是设计混淆

这一条与 §3 L0 三分耦合 — L0 C 类（健康约束）就是这里要下沉到 L1 的内容。

---

## 8. 输出层：narrative + 状态条（信任放大器，必须后置）

**Codex v1 关键挑战**："narrative 在错误链路上是信任放大器" — LLM 看 prompt 写"用户减脂"，会自信编出「为你避开了高油菜」，但实际可能没真过滤。**链路错的时候 narrative 越漂亮 → 欺骗越深 → 系统失信代价越大**。

**实施次序硬约束**：narrative 和状态条**必须在硬契约下沉 L1 之后**才能上线，否则就是给不靠谱的系统装了个无敌嘴皮。

**具体做法**：

- L3 prompt 新增 `narrative` 字段输出"为什么推这 5 道"。例："今天阴雨 + 你近 2 餐高油 → 给你 X / Y / Z"
- 每张卡 reason chip + 命中 refine 时高亮
- 顶部 always-on 状态条：当前模式（"低油 · 高蛋白 · 蔬菜≥50%"）+ refine 命中过滤时显式告知

---

## 9. 实施次序（吸收 Codex 拆分，标出真实并行边界）

```
─ 前置基础设施（先做，0.5 天）───────────────────
├── trace event schema 定义（含 hard_filter_event）
├── intent schema 版本号机制（v1.0）
└── L0 三分判定表写入 CONTRACTS.md

─ P1a 并行三组（3-5 天）────────────────────────
├── methodology 硬契约下沉 L1 hard_filter（含 L0 三分接入）
├── L1 召回参数重写（refine 分支：per_restaurant_max / top_k 兜底 / ingredient 反查）
└── refine 多 slot LLM 解析层（schema + 3 安全带 + eval set 30-50 条）

─ P1b 部分并行（1-2 天，依赖 P1a）──────────────
├── 顶部状态条（UI 壳可先做，可信内容等 hard_filter log）
└── L3 prompt 新增 narrative 字段（prompt 用 mock 数据迭代，生产接入等 P1a）
    ⚠️ 注意：narrative 上线会动 API 契约 + 前端卡片 + trace schema + 旧结果兼容，至少 4 处联动

─ P2（单独排期）──────────────────────────────
├── reference 块底层 resolver + 比较器（"比昨天清淡"/"和上次那家差不多"）
└── 簇式输出（intent 内部子类多样化）

─ P3（长期）─────────────────────────────────
├── 探索位 + ε-greedy
├── 字段空洞补足（quality_tier / delivery 真实字段）
└── eater_context（多用户场景）

─ 已取消 ──────────────────────────────────
└── 破戒模式独立 feature（被 L0 三分 + refine 解除 C 类约束吸收）
```

---

## 10. 任务清单（执行用）

按 P1a → P1b → P2 顺序，每个任务带 What / Why / Done When / 依赖。

### 前置（先做）

#### T-00 · trace event schema + intent schema 版本号
- **What**: 在 `chisha/trace_store.py` 加 `hard_filter_event` 结构；refine intent schema 加 `schema_version` 字段
- **Why**: P1a/P1b 都依赖。先建占位让两者真正并行
- **Done When**: schema 写好 + 单测覆盖向后兼容；trace 落盘看到新字段
- **依赖**: 无

### P1a · 三个并行模块

#### T-P1a-01 · methodology 硬契约下沉 L1（含 L0 三分接入）
- **What**: 把 `harvard_plate.yaml` 的健康硬契约（蔬菜占比 / 油上限 / 价格带）从 L2 weight 改为 L1 `hard_filter`；同时把 L0 三分（A 永不破 / B 永不破 / C refine 可破）接入 `recall.py`
- **Why**: 修最大产品 bug（"原则派"承诺没兑现）；同时为 L0 三分提供执行机制
- **Done When**:
  - L1 出去的 combo 100% 满足 L0 A/B 类约束
  - refine 文本明确表达时（如"今晚就放纵"）能解除 L0 C 类约束
  - baseline_l2_snapshot 对比：旧逻辑路径不变（无 refine 时）
  - 新增至少 10 个 e2e 用例（覆盖各类 L0 触发 / 解除）
- **依赖**: T-00

#### T-P1a-02 · L1 召回参数 refine 分支重写
- **What**: 在 `chisha/recall.py` 加 `if intent is not None` 分支，refine 模式下：
  - `per_restaurant_max` 从 3 提到 5-8
  - 总召回上限放宽 2-3x
  - `ingredient_want` 进 L1 反查（含肉/含鱼菜全召回）
  - `L3_INPUT_TOP_K` 加保底逻辑：「至少 30 个 intent 命中」不足时三级回落
- **Why**: 解决"trace 里送 L3 的 combo 数有时凑不满 60"
- **Done When**:
  - refine 模式下送 L3 候选 ≥ 30 个相关 combo（实测 5 个典型 refine 文本）
  - 空输入模式行为完全不变（baseline_l2_snapshot 0 diff）
  - 三级回落有 trace 日志可查
- **依赖**: T-00

#### T-P1a-03 · refine 多 slot LLM 解析层 + 安全带
- **What**: 新建 `chisha/refine_intent_extractor.py`（或扩 `refine_intent.py`）：
  - 一次 LLM 调用输出 §4 schema 的多 slot 结构
  - Schema 验证 + 失败降级到"空 refine 模式" + UI 友好提示
  - Trace 双存（raw + 结构化 + raw_understanding）
  - 写 30-50 条人工标注 eval set + runner 脚本
  - 兼容旧 `RefineIntent` 字段（向后兼容期）
- **Why**: Faithful Refine 第一原则的执行核心
- **Done When**:
  - eval set 准确率 ≥ 85%（人工标 → LLM 解析 → 比对）
  - 失败 case 100% 走降级路径不崩
  - trace 看得到 LLM 原始 understanding
  - 已有 refine 用例全部通过（不破坏 D-073 验证）
- **依赖**: T-00；§5 字段空洞字段保留但 L1/L2 不消费

### P1b · 输出层（依赖 P1a）

#### T-P1b-01 · 顶部 always-on 状态条
- **What**: 在 `apps/web/` 顶部加状态条，展示「当前模式：低油 · 高蛋白 · 蔬菜≥50%」+ refine 命中 L0 过滤时显式告知
- **Why**: 让用户感知"系统在为我做什么"
- **Done When**:
  - 空输入时显示当前 profile + methodology 简述
  - refine 触发 L0 A/B 类拒绝时显示「检测到 X，已忽略 refine 里的 Y」
  - refine 触发 L0 C 类解除时显示「破戒模式 · 今晚一次性放开」
  - UI 壳可先于 P1a 完成，但 hard_filter event log 数据接入需等 P1a-01
- **依赖**: T-P1a-01（数据可信）

#### T-P1b-02 · L3 prompt narrative 字段
- **What**: 在 `chisha/rerank.py` L3 prompt 加 `narrative` 输出字段；前端卡片展示
- **Why**: "为什么推这 5 道"narrative 是用户信任的关键载体
- **Done When**:
  - L3 输出 schema 加 narrative 字段（带 schema version bump）
  - 前端 5 张卡上方展示 narrative（≤ 50 字）
  - prompt 改造可用 mock trace 数据并行迭代
  - 生产接入需等 P1a 完成（避免信任放大器）
- **依赖**: T-P1a-01, T-P1a-02 必须先完成；trace schema bump
- **注意**: 此任务有 4 处联动（API 契约 / 前端 / trace / 旧结果兼容），不是"无侵入"

### P2 · 能力跃迁（单独排期）

#### T-P2-01 · reference 块底层 resolver + 比较器
- **What**: 实现「比昨天清淡」「和上次那家差不多但换一家」的真实 resolver。需要 `last_meal_id` 解析层 + "更清淡 / 相似但换家" 比较器
- **Why**: 用户用"相对表达"时是对话记忆预期的临界点，是搜索框 → 私人助理的产品体感升级
- **Done When**: 5 类典型 reference 表达可执行；trace 可见 reference 解析结果
- **依赖**: T-P1a-03 解析出 reference 块；trace_store 可读历史

#### T-P2-02 · 簇式输出（intent 内部子类多样化）
- **What**: refine 模式下，出 5 道菜按 intent 内部子类多样化（湘菜分 4-5 个子类）
- **Why**: 解决 D-073.1 的"日料免 cap 后萨莉亚刷屏"副作用
- **Done When**: 实测 5 个典型 refine 表达，5 道结果子类 ≥ 3 个

### P3 · 长期改造（不紧急）

- T-P3-01: 探索位 + ε-greedy
- T-P3-02: 字段空洞补足（quality_tier / delivery 真实字段引入）
- T-P3-03: eater_context（多用户场景）

---

## 11. 验收门槛（产品视角，非技术）

整套方案完成后，志丹自用一周应能观察到：

1. **refine 兑现度**: 5 类典型 refine 表达（菜系切换 / 食材偏好 / 口味追加 / 品牌排除 / 相对参考），系统结果命中率 ≥ 80%
2. **L0 三分生效**:
   - A/B 类约束 100% 不被破（手工注入"想吃花生酱面"，系统拒绝并提示）
   - C 类约束破戒后 UI 明确提示
3. **trace 凑不满 30**: 出现频率 < 5%
4. **narrative 不撒谎**: 抽查 20 次 narrative，全部能在 trace 里找到对应执行证据
5. **空输入路径不退化**: baseline_l2_snapshot 0 diff（无 refine 路径行为不变）

---

## 12. 待 V2/V3 阶段处理（不在本次范围）

- **反馈接口扩到 3 维**（喜欢/不喜欢/不合时宜）：B-001 范畴，单独 session 设计
- **eater_context**（多用户场景）：风险可接受，记入 BACKLOG
- **occasion slot**（"见客户"/"孩子也吃"/"和朋友 AA"）：等 eval miss 率 > 20% 再加
- **reference.relation: avoid_pattern**（"不要像那次那样"）：reference 块的 negative 版
- **exploration_boost**（"随便"/"都行"）：让 ε-greedy 加大

---

## 13. 历史关联

- **推翻**: 无（本设计不推翻历史决策，是在 D-073 / D-076 / D-077 / D-079 基础上向前演进）
- **补强**: D-073（RefineIntent 第一版）→ 多 slot 扩充；D-073.1（cuisine_want 免 3 层 cap 的补丁）→ 簇式输出根治
- **修正**: D-070（"原则派点餐执行外包"承诺）→ 通过硬契约下沉 L1 真正兑现
- **新增宪法**: Faithful Refine 第一原则（CONTRACTS.md 顶部）
- **取消**: 蓝图 v1 的"破戒模式独立 feature"（被 L0 三分吸收）

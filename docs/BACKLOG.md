# BACKLOG · 待办池

> 收"已知但当前不解决"的 bug / feature / idea。判别原则:
> - 触发架构决策 → 挪 [decisions.md](decisions.md) 拿 D-XXX (≤ 15 行/条)
> - 进入实施期 → 挪 [ROADMAP.md](ROADMAP.md) 对应 Phase
> - 已实施细节 → 不再单独写 IMPL_LOG, git log + grep 代码即权威
> - 决定不做 → 挪 [ROADMAP.md](ROADMAP.md) "已砍清单" 并标关联 D-XXX
>
> **本文档不是决策日志**。条目可以模糊、可以悬而未决。半年没动的 idea 主动砍掉, 不要养着。

编号约定:
- `B-NNN` bug · `F-NNN` feature · `I-NNN` idea
- 编号本桶内顺序, 不与 D-XXX 联动
- 状态: `open` / `wip` / `dropped` / `promoted-to-D-NNN`

---

## Bugs

> 已知但当前不修的 bug。明确触发条件 + 优先级 + 绕过方法。

### B-001 · 近期反馈对推荐影响过弱 (短链路缺口)

- **来源**: 2026-05-17 沙盒实测 (sandbox 8 天 / 11 顿 / 10 反馈, L1 抽取产物全空, 推荐不受任何反馈影响) + 志丹拍板"这是根本问题"
- **状态**: open, **P0 · V1.0 收尾后 Phase 1 推广前必修** (2026-05-20 复核: D-090~D-092 解的是 refine→L2 信号校准, 与本条 rating→L2 短链路是两件事, 未修)
- **现象**: 用户给某餐厅/菜品 👎, 7 天 hard cooldown 后系统**照样推**, 行为与 👍 完全一致。连续吃同一配料 (如香菜, 非 main_ingredient_type) 也无法 cooldown
- **根因**: 反馈 → 推荐路径**只有一条**, 走 L1 抽取慢路径 (`feedback_store → L1 extractor → long_term_prefs.boost/penalty`)。但:
  - L1 prompt 保守阈值: 信号弱 / 矛盾 / 样本 < 阈值 → 抽空。沙盒 9 餐实测就抽空
  - L1 抽空时 `load_prefs()` 返 None → score.taste_match_bonus = 0 → L3 prompt 也没 long_term_prefs 段
  - **score.py 不直接读 feedback rating**, **recall.py 也不读**。`diversity_filter` 只看"吃过没"不看 rating
- **影响**: 中期 (近 30-60 天) 菜品/餐厅级反馈对排序**0 影响**。冷启动期完全空白 (L1 至少 20+ 餐 + 强信号才会抽出 token)
- **方案预案** (单独 session 再讨论再实现):
  - 加 `feedback_recency_signal` 直接进 score.py, 带衰减 (rating=-1 → 30 天强抑制 60 天衰减; rating=+1 → 7 天 cooldown 避连吃 → 14-30 天弱 boost)
  - 不改 L1 长链路, 这是补短链路缺口, 双层互补
  - 待定: hard avoid vs 软扣分 / 衰减曲线 / 影响 score 还是只 L3 prompt
- **绕过**: 当前无, 用户需手填 `profile.preferences.avoid_dishes / disliked_cuisines`
- **不修原因**: 涉及打分链路改动, 必须 baseline_l2_snapshot 守门; 衰减曲线 + hard/soft 决策需要设计讨论, 不能边写边定
- **与 Refine v2 (D-080~D-085) 关系**: 不重叠。Refine v2 解决 "当下意图忠实兑现"，B-001 解决 "近期反馈对长期偏好的衰减"。两条路径独立、可并行做。Refine v2 完成不解此 bug，仍需单独 session 设计。

---

## Features

> 已识别但暂不做的功能。多数对应 ROADMAP Phase 1+。

### F-001 · L1 词表扩 cuisine 偏好 token

- **来源**: [CLAUDE.md](../CLAUDE.md) 推荐链路红线 + [D-076.1](archive/DECISIONS_phase0.md#d-0761-l1-词表加-positive-方向-boost-spicy--sweet_sauce) 边界
- **状态**: open, 排到 Phase 1
- **What**: 当前 L1 词表只有 8 token (low_oil/wetness/spicy/sweet_sauce × boost/penalty)。扩 cuisine 偏好 (川/粤/日料/湘菜...) 让 L1 抽取能稳定承接长期 cuisine 倾向, 不只靠 refine 一次性表达
- **约束**: 需独立决策 + baseline_l2_snapshot 守门; cuisine token enum 要和 recall.py / score.py 现有 cuisine 字段对齐
- **优先级**: P2 (Phase 1 同事推广前做, 因为同事的 cuisine 倾向比志丹自己分散)
- **与 Refine v2 关系**: 互补。Refine v2 (D-081) 让 refine 一次性表达的 cuisine 被忠实兑现; F-001 让 cuisine 倾向能跨 session 沉淀进 L1 长期。两条独立。

### F-002 · data zone 拆包

- **来源**: [CLAUDE.md](../CLAUDE.md) Phase 1 列表 + [D-030](archive/DECISIONS_phase0.md#d-030)
- **状态**: open, 排到 Phase 1
- **What**: 把数据采集 / 清洗 / 打标 / 保鲜独立成 `chisha-collector` sister project (D-027 已立项但未拆), V1 后做
- **优先级**: P2

### F-003 · screener 设计

- **来源**: [CLAUDE.md](../CLAUDE.md) Phase 1 列表
- **状态**: open, 排到 Phase 1
- **What**: 同事推广时需要一个"是否适合用 chisha"的筛子 (目标缺失型 vs 原则派, [D-070](archive/DECISIONS_phase0.md#d-070-产品定位收敛到原则派点餐助手--三层信号模型-v1) 边界)
- **优先级**: P2

### F-004 · 第二份 methodology spec

- **来源**: [CLAUDE.md](../CLAUDE.md) Phase 1 列表 + [D-072](archive/DECISIONS_phase0.md#d-072-methodology-spec-抽象-放-phase-0-收尾-v1)
- **状态**: open, 排到 Phase 1
- **What**: 当前只有 `harvard_plate.yaml`。需要第二份 (增肌高蛋白 / 糖控 / 孕期 / 控盐...) 来验证 spec 抽象是否真正解耦了打分逻辑
- **约束**: 不允许借机改 score.py 逻辑或调权重 (D-072 边界)
- **优先级**: P1 (验证抽象的关键)

### F-006 · eater_context (替别人点餐场景)

- **来源**: 2026-05-18 Codex v2 review Refine v2 蓝图时挑出
- **状态**: open, 排到 V2
- **What**: 当用户替别人 (老人 / 小孩) 点餐时, refine 表达不应自动套用 owner 的 L0 (C 类) 解除权限。schema 需加 `eater_context` 字段标识此次餐对象
- **约束**: Phase 0 单用户场景风险可接受, 不在 Refine v2 (D-080~D-085) 范围
- **优先级**: P3 (多用户场景出现时再做)

### F-007 · Refine 高级 slot 扩展 (occasion / avoid_pattern / exploration_boost)

- **来源**: Refine v2 brief §12 标记的未来扩展
- **状态**: open, 待真实数据验证
- **What**: 三类 LLM 解析 slot:
  - `occasion`: "见客户" / "孩子也吃" / "和朋友 AA" → 改 brand_tier / 分量 / 辣度
  - `reference.relation: avoid_pattern`: "不要像那次那样" → reference 的 negative 版
  - `exploration_boost`: "随便" / "都行" / "你看着办" → 主动放手时让 ε-greedy 加大
- **触发条件**: D-081 eval set 跑出 miss 率 > 20% 再加
- **优先级**: P3

### F-008 · 反馈接口 3 维 (喜欢 / 不喜欢 / 不合时宜)

- **来源**: 2026-05-18 Refine v2 讨论中 Opus 提出
- **状态**: open, 排到 V2
- **What**: 当前反馈只有"喜欢/不喜欢"二维; 加"不合时宜"维度区分"今天不想吃但本身爱"vs"本身不喜欢", 避免长期偏好被污染
- **与 B-001 关系**: 同属反馈改造范畴, 应在反馈优化 session 中一起做
- **优先级**: P2 (反馈优化专题里做)

### F-009 · Faithful Refine 真兑现 (L1/L2 真听 quality_floor / delivery_only / max_distance_km / reference)

- **来源**: 2026-05-20 prompt 优化 Step 1 Opus+Codex 共识 brief §5 D1
- **状态**: open, Phase 1 推广启动时再决定
- **What**: 当前 V2 refine schema 抽出 `constrain.quality_floor / delivery_only / max_distance_km / reference` 等字段, 但 L1/L2 召回链路按 D-085 "务实降级"只透传 L3 + trace 标 `unsupported_in_recall`. **真做的话**: L1 召回阶段加 `quality_floor=non_fast_food` → 过滤 fast_food 餐厅; `delivery_only=true` → 过滤堂食; `max_distance_km` → 过滤 distance; `reference.avoid_pattern` → 接 resolver
- **影响**: 让 D-080~D-085 Faithful Refine 第一原则真正兑现 (而非"听见但不办"). 但触碰 `chisha/recall.py + score.py` 高风险白名单, 需要独立 D-XXX + baseline_l2_snapshot 守门
- **不修原因**: 跨 Step 1 范围 (prompt 文案) → Step 2-4 (基建) 也都不动召回链路. 等 Phase 1 推广启动时 review 是否提前
- **关联**: D-080~D-085, brief `docs/proposals/archive/2026-05-20-prompt-effect-optimization.md` §5 D1
- **优先级**: P2 (Phase 1 推广启动时 review)

### F-010 · expanded / synonyms 词典化 (移出 LLM)

- **来源**: 2026-05-20 prompt 优化 Step 1 Opus+Codex 共识 brief §5 D2
- **状态**: open, Phase 1 推广启动时再决定
- **What**: 当前 refine v2 schema 让 LLM 推断 `cuisine_candidates_expanded` ("辣"→["川菜","湘菜",...]) 和 `ingredient_synonyms` ("肉"→["排骨","牛肉",...]). 这违反第一原则 "不联想" + LLM 一致性差. **真做的话**: 建 `chisha/data/cuisine_synonyms.yaml` + `chisha/data/ingredient_synonyms.yaml`, L1/L2 召回时查表展开, LLM 只负责"识别"
- **本轮处理 (T-PR-01)**: prompt 文案闭集化收紧, 词典不迁
- **影响**: 解决一致性 + 词典可 PR review, 但需 L1/L2 召回逻辑改造 (跨 Step 1 范围)
- **关联**: D-080~D-085, brief §5 D2, T-PR-01 P1-1 已闭集化但未迁词典
- **优先级**: P2 (Phase 1 推广启动时 review)

---

## Ideas

> 未验证 ROI 的想法。优先级最低。

_(待填)_

---

## 流转记录

> 条目状态变更追踪。挪走 / 砍掉 / 升级时在此记一行。

- 2026-05-17 · BACKLOG.md 建档, 从 ROADMAP / CLAUDE.md 收 F-001~F-005 五条 Phase 1 deferred 种子
- 2026-05-18 · Refine v2 设计后追加 F-006 (eater_context) / F-007 (refine 高级 slot 扩展) / F-008 (反馈 3 维); B-001 / F-001 标注与 Refine v2 (D-080~D-085) 的关系
- 2026-05-20 · 文档治理: F-005 (OpenClaw 接入) 与 D-074 草稿重复, 删 F-005 统一到 D-074; B-001 顶部加 "Phase 1 推广前必修" 强提示
- 2026-05-20 · V1.0 代码治理跑 integration 测试: 修 4 个 cc.call 返 dict 后未同步的 `.strip()` fail (D-050 遗留); 删 test_real_rerank_end_to_end (D-047 设计期 acceptance, CLI 是 fallback 不是 tool_use 主路径, smoke 已被另 4 个测试覆盖)
- 2026-05-20 · prompt 优化 Step 1 拆 7 task (T-PR-01~07) 共识审完成, brief §5 D1+D2 入 F-009 / F-010 (Phase 1 推广启动时 review)

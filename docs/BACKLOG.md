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

### F-009 · Faithful Refine 真兑现 [superseded by D-094, 2026-05-21]

- **状态**: **superseded** — scope 翻盘. `reference` 已在 T-P2-01 真消费; `quality_floor / delivery_only / max_distance_km / functional.*` 砍 schema (志丹单用户实际不用); 见 D-094 草稿 + `docs/proposals/2026-05-21-faithful-refine-true-fulfillment.md`

### F-010 · expanded / synonyms 词典化 [superseded by D-094, 2026-05-21]

- **状态**: **superseded** — scope 翻盘. 不迁词典: `cuisine_candidates_expanded` 真消费 (L1 召回 `cuisine_want ∪ expanded`), `ingredient_synonyms` 砍 (代码 `_INGREDIENT_BROAD` 已替代). 见 D-094 草稿 + `docs/proposals/2026-05-21-faithful-refine-true-fulfillment.md`

### F-011 · food_form_avoid 数据打标 + L1 硬过滤

- **来源**: 2026-05-21 D-094 scope audit 拆出
- **状态**: open (收窄), 等下个数据轮次启动
- **What**: D-094.1 (2026-05-24) 已加 `staple_want/avoid` 走 recall 硬过滤, 覆盖**粗粒度**主食排除 (面/米饭/粥, canonical_name 子串 + grain_type 守门防"面包"误命中). F-011 收窄为**细粒度形态** (面条 vs 米粉 vs 拉面 vs 饼 — staple_avoid 子串区分不了) 仍需 food_form 数据字段. dish 数据层当前**无 `food_form`** (audit 0/11123). 数据轮次到时: (1) dish 打标 `food_form` (面条/米粉/饼/...) (2) schema 加回 `food_form_avoid` (3) L1 硬过滤命中
- **依赖**: data 打标工作流 (LLM 批量打标 dishes_tagged.json + 人工抽检)
- **优先级**: P2 (下次数据轮次)

### F-012 · rerank 多 cache breakpoint (5min 连续 refine 链路提速)

- **来源**: 2026-05-21 prompt 优化 Step 3 续 brief 项 B, codex 共商 SHIP 但志丹砍
- **状态**: open, 暂不做 (ROI 不足)
- **What**: rerank `build_user_message` 在 [PROFILE] 段尾加第 2 个 ephemeral cache breakpoint, 让 5min TTL 内连续 refine 链路 (refine→refine→refine 不带 L1 抽取重算) input_tokens 再省 ~2k cache_read. 详见 `docs/proposals/2026-05-21-prompt-step3-cache-and-examples.md`
- **砍的原因**: (1) 工程量 ~9h + 3 个 high-risk 文件 (llm_client.py / anthropic_api.py / openrouter.py + rerank.py 改 build_user_message), (2) 真命中窗口窄 — 仅"5min TTL 内连续 refine 且后台 L1 抽取没触发", codex Q-B2 警告 "PROFILE 一天内不变" 不成立, (3) 单用户日常 refine 频率不高, 长尾场景
- **触发重做条件**: Phase 1 推广有真用户连续 refine 数据 / refine latency 还要再压 / Anthropic 计费成本成为瓶颈
- **优先级**: P3 (长尾)

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
- 2026-05-21 · F-009 / F-010 scope 翻盘 superseded by D-094 (草, 待 codex 共商 + plan-brief): D1 quality_floor/delivery_only/max_distance_km/functional 砍 (志丹不用), D2 expanded 真消费 + synonyms 砍. food_form_avoid 拆出新立 F-011 等数据打标
- 2026-05-21 · D-094 落地实施完成 (T-FR-01~07, 7 task closed): refine_intent_v2.py 砍 5 字段 + 9 类枚举闭包; recall.py 加 brand_avoid (venue 整店) + cooking_method_avoid (dish-级) 硬过滤 + cuisine_candidates_expanded 进 bucket_soft; refine.py V2→V1 桥接; rerank prompt 删 unsupported 段; eval set + 18 个 recall branch 测试同步; baseline_l2_snapshot 0 diff 守门通过
- 2026-05-21 · prompt 优化 Step 3 续收口: 🔴 refine cache bug 通过 D-095 修完 (拆 system/user + cache_system=True, latency 6-8s → 3-4s 预期); top-K 60→40 砍 (跟 D-047 矩阵实测冲突); reason 示例精简砍 0 (信号都不重复, codex 共识); 多 cache breakpoint 立 F-012 不做 (5min 连续 refine 长尾 + 9h 工程量 + 3 high-risk 文件). **prompt 优化大题 (Step 1 + 2 + 3) 全部收口** [口径修正见 2026-05-23 条]
- 2026-05-23 · prompt 优化 Step 2 (rerank 部分) 实际落地, 推翻 2026-05-21 "全部收口" 口径 — Step 2 当时只是 BACKLOG 化, 没做. 本轮 codex 共商完拆 T-PR2-A/B/C 3 个独立 commit (`b2657f8` / `d5fcf3d` / `2e13ba8`): 计数硬约束 4 处合并 / 字段表 markdown table → P-B-3 紧凑 key:value (T2 medium risk, codex commit-前 diff review SHIP) / 顶部 HTML DEV NOTE 挪 prompts/_dev_notes.md. style guide 直接砍 (单用户 2 prompt ROI 不足). refine v2 砍例本轮不做 (`v1-retire-brief` worktree 在写 V1 refine 退役计划, 撞包), 待 V1 退役后单开 brief. Step 4 (model 切换) 仍 BACKLOG. 守门: 995 pytest pass + baseline_l2_snapshot 0 diff + 10-case L3 sanity 系统约束全 ok.

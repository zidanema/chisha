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

### B-002 · refine ingredient_want 信号被三层稀释 + contains_ingredient 泛化

- **状态**: **fixed, 2026-05-17** (D-080)
- **现象**: refine "湘菜+牛肉" top5 仅 1 道牛肉菜 (目标 ≥3); 高销量非牛肉湘菜把低销量牛肉菜挤出
- **根因**: (1) `score.contains_ingredient` path 2b 把"牛肉"→红肉, 让猪/羊菜也命中; (2) `_INGREDIENT_BROAD` 含"牛/猪/羊/鸡/鸡肉/鱼/虾" 单字键, 让 broad fallback 泛化; (3) `_intent_dish_score` ingredient name 权重 1.0 比 cuisine 2.0 弱一半, 低销量目标食材菜进不了 `proteins[:6]`
- **修复**: 砍 path 2b + 剥 broad 具体蛋白键 + ingredient name 权重抬到 2.0 (cuisine 同级)
- **实测**: dry_run + 浏览器 /api/refine top5 = 5/5 含牛肉菜
- **守门**: baseline_l2_snapshot 严格 0 diff (intent=None 路径无影响)

---

### B-001 · 近期反馈对推荐影响过弱 (短链路缺口)

- **来源**: 2026-05-17 沙盒实测 (sandbox 8 天 / 11 顿 / 10 反馈, L1 抽取产物全空, 推荐不受任何反馈影响) + 志丹拍板"这是根本问题"
- **状态**: open, **P0**
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

---

## Features

> 已识别但暂不做的功能。多数对应 ROADMAP Phase 1+。

### F-001 · L1 词表扩 cuisine 偏好 token

- **来源**: [CLAUDE.md](../CLAUDE.md) 推荐链路红线 + [D-076.1](archive/DECISIONS_phase0.md#d-0761-l1-词表加-positive-方向-boost-spicy--sweet_sauce) 边界
- **状态**: open, 排到 Phase 1
- **What**: 当前 L1 词表只有 8 token (low_oil/wetness/spicy/sweet_sauce × boost/penalty)。扩 cuisine 偏好 (川/粤/日料/湘菜...) 让 L1 抽取能稳定承接长期 cuisine 倾向, 不只靠 refine 一次性表达
- **约束**: 需独立决策 + baseline_l2_snapshot 守门; cuisine token enum 要和 recall.py / score.py 现有 cuisine 字段对齐
- **优先级**: P2 (Phase 1 同事推广前做, 因为同事的 cuisine 倾向比志丹自己分散)

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

### F-005 · OpenClaw / 多 Agent 接入

- **来源**: [ROADMAP.md](ROADMAP.md) "CLI + Skill 模式" + design brief
- **状态**: open, 排到 Phase 1
- **What**: Phase 0 只做 Claude Code reference adapter, Phase 1 扩 OpenClaw / HappyClaw / Codex 等
- **优先级**: P2

---

## Ideas

> 未验证 ROI 的想法。优先级最低。

_(待填)_

---

## 流转记录

> 条目状态变更追踪。挪走 / 砍掉 / 升级时在此记一行。

- 2026-05-17 · BACKLOG.md 建档, 从 ROADMAP / CLAUDE.md 收 F-001~F-005 五条 Phase 1 deferred 种子

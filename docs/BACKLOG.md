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

## 当前推进路线 (2026-05-17 拍板)

> 不是 ROADMAP 的复制 — ROADMAP 已部分过时, 这里是基于"自用稳定 → 接个人 agent → 扩同事"终极路径反推的最近 4-6 周做事顺序。每完成一步划掉, 不补不堆。

### 主路径

1. **F-007 debug trace 串接验收** (1-2 天) — claude code 自测过但未验收。**所有后续动作的归因基础设施**, 拿不到可信的 trace 工具, 后面跑沙盒看到怪现象时只能瞎猜
2. **I-001 摸清 L1 抽取 prompt + 链路** (半天-1 天) — 不学整套系统, 只把 L1 这层看懂, 因为沙盒里 L1 行为最不直观
3. **沙盒模式 e2e 跑通 + D-080 两个 P0 修复复测** (2-3 天) — D-080 基于实测推断修, 没在沙盒里完整复测过。沙盒主战场, 真实日历日并行后台跑, 不强门
4. **F-011 + F-012 接个人 agent + context 注入** (捆绑做, 不拆) — 这步才是放大 chisha 价值的拐点。F-011 不带 F-012 = agent 替你按按钮, 没意义
5. **F-010 同 query 随机性** — 接 agent 后频次拉高才有体感场景, 之前做没数据支撑

### Phase 1 同事推广启动前必收口 (不在当前周次, 但是硬门)

- F-004 第二份 methodology spec (验证抽象解耦)
- F-003 screener (筛同事)
- F-006 沙箱动线重设计 (推广前用户心智不能乱)
- F-001 L1 词表扩 cuisine token (同事 cuisine 比志丹分散)

### 明确划掉的犹豫点

- **macOS launchd 定时拉起** (ROADMAP 唯一未勾选项): 划掉。自用阶段手动开页面没毛病, 不是债
- **Step 2 真实自用一周作为强门槛**: 改成"沙盒 + 真实日历并行", 真实日历不阻塞下游
- **系统性深入学链路**: 不专门学, 边跑沙盒边按需问 claude code, 效率高 10 倍

### 不在主路径 (优先级低 / 依赖未到)

- F-008 并发多 LLM 对比: 无痛点别优化
- F-009 多饮食并行: 依赖 F-004
- F-002 data zone 拆包: V1.5 工程债
- F-005 多 Agent 接入: F-011 跑通后再扩
- B-003 轻食 portion: 先抽样核实是不是真 bug

### 当前阻塞

**F-007** — 在动主路径任何下一步之前, 先把这批未验收代码看清楚 (改了哪些文件 / commit 在哪 / 行为对不对设计预期)。

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

### B-003 · trace_store 不自包含 → **已修 (2026-05-17)**

- **来源**: 2026-05-17 debug-ui D-079 cleanup 验收时发现 (志丹删 mock 后暴露)
- **状态**: **closed** (2026-05-17 修复, 留作 changelog)
- **现象 (修复前)**: debug-ui system_prompt tab 空 (chars=4089 但渲染空); tool_input tab 显示假 `name="emit_recommendations" / input_schema={}` (mock 残留, 真实 tool 名是 `select_top_candidates`)
- **根因**:
  - `chisha/api.py:226-227` 写 trace 时只存 `system_prompt_chars` 计数, 不存 `system_prompt_full`
  - `chisha/rerank.py:1334` `trace_collector["tool_input"]` 存的是 LLM **输出**, 不存发送给 LLM 的 tool 定义
  - 结果: D-079 trace "可 Replay" 的契约打折扣
- **走过的弯路**: 先尝试加 `/api/debug/rerank_assets` 端点直接读源文件,但 prompt 后续改动会污染老 trace 显示, 这是免责声明不是真修. 撤销后正确方案如下
- **修复**:
  - `chisha/rerank.py:_run_llm_rerank` 在 `out` 加 `system_prompt_full` / `tool_definition` / `tool_choice` (CLI 路径 tool 字段为 None, 因 CLI 不支持 tool_use)
  - `chisha/rerank.py` trace_collector 透传上述字段
  - `chisha/api.py:_build_trace` `l3_trace` 加这三个字段
  - debug-ui adapter 读 `l3.system_prompt_full` / `l3.tool_definition` 真实字段; 老 trace (修复前生成) 字段为空 → PanelL3 显示 `OldTraceCallout` 提示重跑; CLI 路径 tool_definition=None → 显示 `CliNoToolCallout` 解释为啥
- **迁移策略 (D-082 同步决策)**: **不** bump `TRACE_SCHEMA_VERSION`. 这些字段都是 backend 写盘新增 + 前端 optional 读 (`?.` / `??`), 老 trace 读出来不会触发 `TraceCorrupt` fail-closed; 用户体感是个别 tab 显示 callout 提示重跑, 不阻断 Replay 列表. bump 版本反而会让老 trace 直接被拒读, 与 "调试完整性优先" 冲突.
- **验证**: 用 `/api/recommend` 跑一条新 trace, l3.system_prompt_full=4089 chars 真实落盘; debug-ui 渲染真实方法论内容

### B-004 · debug-ui L2 KPI 字段 `candidates_to_l3` 之前显示 topk_window (60) 而非实际数 (54)

- **来源**: 2026-05-17 debug-ui 验收, 志丹观察"user message 没凑满 60 个 combo"
- **状态**: **已修** (debug-ui adapter 改 `n_scored ?? top.length`, 显示真实数), 留条记录
- **根因(已澄清)**: L2 `apply_caps()` (chisha/score.py:1068) 是 D-049 head-only 模式, 四层 cap (餐厅 3 / 品牌 2 / 菜系 6 / food_form 8) 把候选压到 54 条 head 而不到 60。 `top_k = ranked[:60]` 拿到 min(54, 60) = 54. **真送给 LLM 的就是 54 个, 不是 bug**
- **遗留**: backend 写 trace 字段名 `topk_window=60` 是配置 cap, 不是实际数; 真实数读 `l2.summary.n_scored` 或 `l2.top.length`. 前端 adapter 之前 map 错了字段, 现在已对齐
- **不再追踪**: 仅留作"避免再次困惑"备忘

---

### B-001 · 近期反馈对推荐影响过弱 (短链路缺口)

- **来源**: 2026-05-17 沙盒实测 (sandbox 8 天 / 11 顿 / 10 反馈, L1 抽取产物全空, 推荐不受任何反馈影响) + 志丹拍板"这是根本问题"
- **状态**: **fixed v2, 2026-05-17** (v1 D-081 rating 短链路 + v2 D-084 4 维 calibration + note/comments[] 词表, dual-codex S2+S5 共识, brief: docs/wip/B-001-v2-design-brief.md)
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

### F-013 · D-083 PR-3 What-if `ignore_feedbacks` patch (遗留)

- **来源**: D-083 主 brief + PR-2/PR-3 设计 brief (`docs/wip/D-083-pr2-pr3-design-brief.md`) Codex S2 共识已落
- **状态**: open, **设计完成 + Codex S2 共识落定**, 待实施 (单独 session)
- **What**: What-if 加 `ignore_feedbacks: [sid]` patch — 用户在 FeedbackInputCard 选某条反馈点 "🚫 假如这条不存在", What-if 重跑下游 score+L3 看推荐变化. 验证 "这条反馈对推荐的实际影响"
- **实施清单** (S2 已定): 后端 `feedback_store.py` 给 ratings/note_tokens 加 sid + `debug_what_if.py` 加 `_filter_view_by_sids` + WhatIfPanel UI 多选 + 加 seq/AbortController race 防护
- **关键风险**: filtered view 替换 frozen view 后必须传给 L2/L3/trace 全链路 (Codex S2 必改 #6); 老 frozen view (无 sid) 静默不过滤 (S2 Q7=A)
- **不修原因**: 志丹 2026-05-17 拍板 PR-2 先合, PR-3 留单独 session — D-083 PR-1 (后端 trace) + PR-2 (debug-ui 可视化) 已够志丹用沙盒做归因, ignore_feedbacks 是锦上添花

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
- 2026-05-17 · 收 B-003 (trace 不自包含 / system_prompt + tool_def 缺失) + B-004 (L2 KPI 字段已修留记录), 来源 D-079 cleanup 验收

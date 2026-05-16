# Debug Replay & What-if PRD (D-079)

> 状态: **draft for Codex review** · 日期: 2026-05-16 · 作者: 志丹 + Claude
> worktree: `.claude/worktrees/debugger-attach`
> 关联决策: D-039 (老 debug 台) · D-049 (V2 调试台) · D-072.1 (L2 baseline trace) · D-075 (apps/debug-ui SPA) · D-076 (L1 LLM 抽取) · D-077 (sandbox time-travel) · D-078 (sandbox 收尾)

---

## 1. 一句话定位

**让生产链路每次 recommend 都留下可回放的完整 trace,debug 台从"凭空新跑一条"升级为"选历史 trace 看真实决策 / 改参数重跑下游 / 现场新跑"三模式并存。**

## 2. 为什么要做(Why now)

### 2.1 现状缺陷
| 维度 | 当前状态 | 痛点 |
|---|---|---|
| 生产 trace | `logs/recommend_log.jsonl` 只存 final 5 候选 | 收到差评后无法回溯"为什么推了这 5 个" |
| debug 台数据源 | 每进一次新跑一遍(LLM 调用 + 当前时钟) | 无法复现历史、LLM 输出每次都变 |
| Session history | `apps/debug-ui` localStorage cap 5 条(D-075 defer) | 跨设备/跨重装丢失,容量硬限 |
| 改参数实验 | 必须改 `profile.yaml` 或用 `profile_overrides`,但 ctx 也会变 | 变量不隔离,无法清晰归因 |

### 2.2 Phase 0 验证闭环的卡点
CLAUDE.md 顶段写明 Phase 0 剩 **Step 2 用户自用一周采纳率验证**。这一周里典型场景是:
- 中午 12:00 推荐了一组,我下单吃了 → 晚上想看看为什么推这个
- 22:00 想看看"如果今天我手动改 distance 权重 +0.1,中午那组会不会变"
- 一周后看看"5 次差评里有几次是 L2 打分锅、几次是 L3 LLM 锅"

当前工具链做不到任何一项 —— **没有 trace = 推荐链路是黑盒**。

### 2.3 与已有能力的关系
- **D-072.1 L2 baseline trace**:已有 `scripts/baseline_l2_snapshot.py` 但产出在 `tmp/baseline_traces/`,是 commit-time 回归工具,不是运行时观测。本 PRD 是**运行时 trace**,跟 baseline trace 互补不重复
- **D-075 debug-ui SPA**:已有完整 V12 DAG 渲染组件 + localStorage history(cap 5)。本 PRD 是**给它换数据源 + 升级三模式**,不动 UI 骨架
- **D-077 sandbox**:已有数据落盘根隔离 + 虚拟时钟。本 PRD 的 trace 落盘**必须复用 `chisha/data_root.py`**,sandbox 模式下写 sandbox trace,prod 写 prod trace,不互染

## 3. 用户故事(Who / When / What)

唯一用户:**志丹自用**(Phase 0 内)。Phase 1 同事推广时复用同一套链路。

### US-1: 反馈差评回溯(高频,主场景)
> 作为志丹,中午 12:00 用户视图推荐了 5 道,我点了第 2 道,晚上感觉一般想标 ⭐⭐⭐。
> 我打开 debug 台,**看到的第一个列表项就是中午那条 session**(餐厅名 + 时间 + ★评分),点进去看完整 trace:L1 召回 88 → 卡到 60 → L2 score 排序 → L3 LLM 选了哪 5 个。
>
> 我希望知道:为什么 ⭐⭐⭐ 的店排在前 5、为什么我喜欢的 X 餐厅没出现(L1 卡掉还是 L2 输了)。

### US-2: 改参数 What-if(中频,调权重场景)
> 在 US-1 的 trace 详情页,我点 "What-if 重跑",把 `distance` 权重从 0.10 → 0.15,L3 use_llm 关掉走 fallback。
> 系统冻结**中午那条的 ctx(daily_mood, refine_text, today=2026-05-16, weather=多云, last_meal_log)** 和 **L1 召回出来的 88 个 combos**,只重跑 L2 打分 + L3 fallback,**不重新发 LLM(除非我打开 use_llm)**。
>
> 我希望看到 diff:top5 哪些菜进了/出了/挪了名次,heatmap 哪几维变化最大。

### US-3: 现场新跑(低频,纯探索)
> 我想试一个新加的 chip "便宜大碗",打开 debug 台,点右上 "Live 模式" 按钮,填 mood / refine_text / 自定 profile_overrides,跑一次新的。
> 这条结果**只在内存不入历史列表**(防污染),关掉窗口就没了。

### US-4: 跨设备同步(隐性需求)
> 我在公司 Mac 上跑了几条,回家用家用 Mac 也想看 → 历史必须在后端,不能困在 localStorage。

## 4. 三模式定义(产品规则)

| | **Replay (默认)** | **What-if** | **Live (现状,降级到侧边按钮)** |
|---|---|---|---|
| **入口** | 左侧 Sidebar 默认展开,列最近 30 条 session | Replay 详情页"What-if 重跑"按钮 | 右上角次要按钮 "Live 模式" |
| **数据源** | 读 `logs/recommend_trace/{sid}.json` | 冻结 trace.ctx + trace.l1.combos,接收 weights/caps/use_llm/n_explore 改动 | 现场跑 `debug_recommend()` 全链路 |
| **是否调 LLM** | **否**,展示 trace.l3.llm_raw_response | 默认否(use_llm=False 走 fallback);用户显式打开才调 | 是 |
| **是否写历史** | 不写(只读) | 不写(临时实验) | **不写**(只在当前会话可见,关 tab 即丢) |
| **耗时** | <100ms(纯读盘) | <500ms(L2 重算,无 LLM) | 3-15s(全链路 + LLM) |
| **典型频率** | 80% 访问 | 15% 访问 | 5% 访问 |

### 4.1 模式间切换的强约束
- Replay → What-if:**ctx 字段必须可视化展示,告诉用户"被冻结的变量是什么"**。改 weights 后顶部 diff badge "改了:distance 0.10→0.15"
- What-if → 再 What-if:**基准始终是原 Replay,不是上一次 What-if**(防止用户层层 What-if 后回不到起点)
- Live → 无:**Live 不能 save-as-replay**(违反 Live 定义),需要落 trace 必须走真生产链路

## 5. UI 入口与导航(在 D-075 debug-ui 基础上)

### 5.1 整体布局变化
```
┌─ Sidebar (扩) ──────┬─ Main ────────────────┐
│ [Live 模式] ⬅ 新增  │ V12 DAG (现有)         │
│ ─── History ───     │ L1 / L2 / L3 / Final   │
│ • sess_2026-05-16 ⭐ │ Refine / Trace (现有)  │
│   12:23 · 锅二爷     │                       │
│ • sess_2026-05-16   │ [What-if 重跑] ⬅ 新增 │
│   08:47 · 老兵       │                       │
│ • sess_2026-05-15...│                       │
└─────────────────────┴───────────────────────┘
```
- Sidebar 从 localStorage 切到 `/api/debug/sessions`,cap 从 5 → 30(后端无 5MB 硬限)
- 每条 session 行加 **反馈 badge**:⭐ = 已 accept、❤ = 已 feedback、🚫 = stopped(读 feedback_store 派生)
- 顶部 "Live 模式" 按钮显式,且**当前是 Live mode 时整页加金色边框 + Banner 提示"Live 模式 - 不入历史"**

### 5.2 What-if 编辑入口
- PanelL2 现有 weights 是只读展示 → 加 "Edit weights" 切换可编辑
- 改完后顶部出现 sticky 操作条 "已改 3 项 · [Run What-if] [Reset]"
- 重跑结果**双栏对比**:左 = 原 Replay,右 = What-if 输出,heatmap 共用色阶,数值 cell 加 delta angle(↑↓)

### 5.3 详情页 Sticky 摘要(冻结上下文披露)
顶部增加 "Frozen context" 收起卡:
- session_id / meal_type / zone / today / daily_mood / refine_text / weather
- 候选池大小(L1 召回数)
- 这些字段在 What-if 模式下**置灰不可编辑**

## 6. 非功能需求

| 维度 | 目标 | 验收方法 |
|---|---|---|
| trace 落盘成功率 | ≥99.9%,失败必须 logger.warning 但**不能阻断 recommend** | 单测 `trace_store_failure_does_not_break_recommend` |
| Replay 加载 P99 | ≤200ms(单文件 ≤300KB) | 手测 + bench |
| What-if 加载 P99 | ≤500ms(L2 重算,无 LLM) | bench |
| 磁盘代价 | 单 trace **硬上限 50MB** sanity bound,日常实测 ~1.3MB (Phase 0 单 zone 1260 dishes),30 天保留 ~40MB | PR-1 实测 |
| sandbox 隔离 | sandbox trace 写 `logs/sandbox/recommend_trace/`,prod 读不到 | 单测 `trace_isolation_prod_vs_sandbox` |
| 安全 | trace 不存 LLM api key、不存用户敏感个人信息(已在 profile 副本里) | code review |
| 回归 | baseline_l2_snapshot + compare_traces 0 diff | CLAUDE.md 红线,每次 commit 必跑 |

## 7. 范围界定

### 7.1 V1 必做(本 D-079 范围)
- [x] 生产链路 `recommend_meal()` + `refine()` 双端点都写完整 trace(L1/L2/L3 全量)
- [x] trace_store 模块:写盘原子化、读盘容错、sandbox 派生
- [x] 3 个新 API:`GET /api/debug/sessions` + `GET /api/debug/sessions/{sid}` + `POST /api/debug/what_if`
- [x] debug-ui 三模式 UI:Sidebar 后端版、What-if 按钮 + 对比、Live 模式 banner
- [x] 反馈 badge:Sidebar 行展示 ⭐/❤/🚫
- [x] 测试:单测 + 一条 e2e 手测脚本

### 7.2 V1 不做(明确 defer 到 V2 / Phase 1)
- ❌ trace 自动归档/压缩(30天后压成精简版):Phase 0 数据量不够,先观察
- ❌ trace 跨 session 聚合分析(如"这周低油菜 hit 率"):需要批工具,Phase 1 同事推广前做
- ❌ trace 上 OpenClaw / 云端同步:Phase 1 多人协作时考虑
- ❌ What-if 改 prompt(L3 system message):涉及 spec 化,挪到 D-080+
- ❌ Replay 重新调用 LLM(re-run with same prompt):成本高且不稳定,Live 模式覆盖了这个场景
- ❌ trace 加密 / 脱敏:个人自用,profile 已经在落盘里没新增风险

## 8. 与红线 / 现有决策的对齐

CLAUDE.md 推荐链路红线已有 8 条,本 PRD 不违反任何一条:
- ✅ 不让用户选 mood:What-if 编辑面板**不会**加 mood picker,mood 是被冻结的
- ✅ `infer_refine_mood` 边界:What-if 不动 refine 推理路径
- ✅ methodology spec 只搬运:What-if 改的是 score_weights / caps,**不动 spec 文件**
- ✅ baseline 回归:trace 落盘 hook 改动 score.py 之前必跑,但实际不改 score.py(只读旁路)
- ✅ L1 词表锁定:What-if 不能改 taste_match 词表
- ✅ L1 抽取走 CLI text:不动 L1
- ✅ sandbox 原则:trace 在 sandbox 内独立落盘,行为完全一致 prod
- ✅ 时间注入:trace 写入用 `clock.now(root)` 不用 `dt.datetime.now()`

## 9. 成功标准(怎么算这次做完了)

发版后一周内,**全部满足**:
1. 推荐链路任意一次调用,`logs/recommend_trace/{sid}.json` 必有完整 trace(单测保证)
2. 打开 debug 台,Sidebar 自动列出最近 30 条,**点任意一条 200ms 内完整渲染 L1/L2/L3 panel**
3. What-if 改任意 1 维权重,500ms 内出双栏对比
4. Live 模式按钮工作,Banner 提示明显
5. 一周内志丹至少跑过 5 次真实差评回溯(US-1),且至少 2 次定位到具体环节(L1 卡 / L2 排序 / L3 LLM 选错)
6. baseline_l2_snapshot + compare_traces 0 diff
7. 文档收尾:DECISIONS D-079 落、README/ROADMAP/CLAUDE.md 同步

## 10. 风险与对策

| 风险 | 概率 | 对策 |
|---|---|---|
| trace 落盘 IO 阻塞 recommend 链路 | 中 | 写盘 try/except 包裹,失败 warn 不抛 |
| trace 文件磁盘膨胀 | 低(个人自用) | 单文件 cap 300KB,V2 加归档 |
| What-if 冻结 ctx 不彻底,导致结果不可复现 | 中 | trace schema 必须 frozen 整个 ContextSnapshot.to_llm_dict() + L1 combos 全量,单测对比同输入同输出 |
| sandbox 模式下 prod trace 被写入 | 高(若 hook 不走 data_root) | 强制走 `data_root.recommend_trace_dir(root)`,测试 `test_trace_isolation` |
| debug-ui localStorage history 和新后端 history 并存导致混淆 | 中 | **不 migrate**: 后端可达时完全 mute localStorage,后端不可达时降级展示 localStorage 缓存作"离线旧记录" + 红色 banner;localStorage 7 天 TTL 自然过期(详见 DESIGN §8.2,Codex #6) |
| What-if 改 caps 后 ranked 顺序变化超预期 | 低 | 不是 bug,是 What-if 的本意 |

## 11. 待 Codex review 的具体疑问点

提交 Codex 时**明确请求审视**:
1. trace schema 字段是否完整支持 What-if 冻结重跑(尤其 L1 召回出的 combos 是否需要全量 dish 信息,还是 dish_id refs)
2. What-if 冻结边界(P/4)是否合理,有没有遗漏的隐性 ctx
3. trace_store 落盘失败时的降级策略是否安全
4. sandbox 数据隔离的 7 个落盘点 + 新增 trace = 8 个,sandbox.reset 是否要扩到删 trace 目录
5. localStorage → 后端 migration 是否要做(还是直接 deprecate localStorage history)
6. 磁盘代价估算:1 周 14 次推荐 + 7 次 refine = 21 traces × 200KB = ~4MB/周,30 天 ~17MB,可接受
7. 与 D-077 sandbox L1 抽取异步的潜在 race:advance 时 trace 已落 / pending,Replay 渲染要不要等 L1 完成

---

## 附录 A: 词汇表
- **trace**: 一次 recommend 调用的完整中间产物文件,落 `logs/recommend_trace/{sid}.json`
- **session_id**: 推荐响应自带的 `sess_*` 唯一标识,trace 文件名用它
- **frozen ctx**: Replay 进 What-if 时被锁住不可改的字段集合
- **Live 模式**: 现场新跑 + 不入历史 + 仅当前 tab 可见的临时态
- **Replay 模式**: 默认态,读历史 trace,只读
- **What-if 模式**: Replay 派生态,改下游参数重跑,临时态

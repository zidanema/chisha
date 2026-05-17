# 重构 Topic:Living + Lab 二分架构

> 共识形成日:2026-05-17 · 决策编号:**D-085**(待 decisions.md 正式落条目时回填锚点)
> 文档定位:此次重构的**完整 context 输入**,供后续盘点 / 写迁移方案 / 实施时反复引用
> 文档范围:目标层共识 + 10 个关键决策的理由 + invariants + 待办起点
> 不在范围内:具体代码盘点 / 文件级 keep/refactor/new/drop 清单(下一步产出)

---

## 1. 北极星

> 把"今天吃啥"这个一天两次的高频决策,外包给一个**能解释、能演练、能跨端调用**的私人系统。

**不是**为了:做一个能给别人用的产品 / 做一个推荐算法 demo / 做一个 trace 可视化工具本身。

## 2. 三层目标(校准后)

| 优先级 | 目标 | 承担 | 成功标准 |
|--------|------|------|----------|
| **P0** | **日常能用** | Living Web | 真的每天用它做决策,而非脑子里另想 |
| **P0** | **可解释** | Lab Replay | 看到反直觉推荐,30 秒内定位是 L1/L2/L3 哪一层问题 |
| **P0** | **可演练** | Lab Sandbox + What-if | 不用等真实日历过 7 天,分钟级判断"这个改动是不是改善" |
| **P2** | **可外包** | Living Agent | 飞书/Claude Code 里问"晚上吃啥"和 Web 拿到同样答案 |

**P2 但 2-3 周内硬截止** — 这决定了 Living API **现在**就必须 Agent-friendly。

## 3. 三个 app 的存在理由(一句话)

- **Living Web**:让 P0(日常用)成立,**同时为 P2(Agent 接入)磨 API**
- **Lab**:让 P0(可解释 + 可演练)成立。**没有 Lab,系统退化成黑盒,你会失去信任**
- **共享 `packages/contracts/`**:同一个 trace_id 两边都能查,不出现"Living 推了 A,Lab 找不到记录"的鬼故事

## 4. 二分架构

```
┌──────────────────────────────────────────────────┐
│ 端层                                              │
│ ├─ Living Web (apps/web)        ← 当前唯一       │
│ ├─ Living Agent (MCP/飞书/CC)   ← 2-3 周内      │
│ └─ Lab Web (apps/debug-ui)                       │
├──────────────────────────────────────────────────┤
│ 接口层                                            │
│ ├─ Living API: 决策入口,stateless,只写真实数据 │
│ └─ Lab API:    trace 查询 / sandbox / what-if   │
├──────────────────────────────────────────────────┤
│ 共享层 packages/contracts/                       │
│ ├─ trace 数据类型(TypeScript types)             │
│ └─ API client fetch 工具                         │
├──────────────────────────────────────────────────┤
│ 内核(已存在)                                    │
│ 推荐链路 + trace store + 真实/虚拟双时钟         │
└──────────────────────────────────────────────────┘
```

## 5. Living vs Lab 心理边界

| 维度 | Living | Lab |
|------|--------|-----|
| 用户身份 | 点餐者(你) | 产品 + 工程师(你) |
| 时间观 | 只有"现在"(`meal_hint` 决定) | 过去/现在/虚拟未来 一条轴 |
| 读写 | **读写真实数据** | **只读真实数据**;只能写 sandbox 分支 |
| 设备 | 移动优先 | 桌面优先 |
| 复杂度 | 极简,一屏一决策 | 密集,显微镜 + 训练场 |
| 跳转 | "为什么推这家" → Lab `/replay/<trace_id>` | 单向,Lab 不跳回 Living |

## 6. 10 个关键决策(Q1-Q10)

每条 = **决策内容** + **没选什么** + **为什么**。

### Q1:Sandbox 演练不能 commit 回 Living
- **没选**:把 sandbox 试出来的好策略数据合并回真实数据库
- **理由**:污染真实学习数据 = 自己骗自己。策略改进的正确路径是改代码/profile,不是塞数据

### Q2:Living 保留独立 Web 应用(不合入 Lab)
- **没选**:把 Living 当 Lab 的 Live 模式全屏化,只留一个 app
- **理由**:Living 需要(a)调试样式 (b)先做功能验收 (c)未来接 Agent。三者都要 Living 独立存在

### Q3:共享只到 `packages/contracts/`,UI 不共享
- **没选 A**:两边完全独立两份代码 — 后端改字段两边都要手动同步,容易漏改
- **没选 B**:monorepo 全共享含 UI 组件库 — Living 极简移动风 vs Lab 密集桌面风,组件互相打架
- **选 C**:共享 trace types + API client(改字段两边 TS 立刻飘红),UI 各做各的

### Q4:Sandbox 产生的 trace 写同一个 store 带 `is_sandbox=true` 标记
- **没选 A**:同 store 不区分 — 污染 Living 查询
- **没选 B**:独立 sandbox_trace_store — 想拿真实数据做 sandbox 基线时跨查询麻烦
- **选 C**:同 store + 标记,默认查询过滤掉 sandbox

### Q5:Lab 内部用 URL 路由(不是 tab)
- **没选**:tab 切换
- **理由**:可分享/收藏 trace URL;浏览器后退键有意义;sandbox run 应该是可命名的"实验"
- **URL 设计**:`/live` / `/replay/<trace_id>` / `/sandbox/<run_id>` / `/timeline?from=...&to=...`

### Q6:Lab **完全只读**
- **没选 B**:Lab 可写并写真实反馈 — 一次手滑污染学习数据
- **没选 C**:Lab 按模式区分读写权限 — 你需要时刻意识"我在哪个模式",UI 必须把标记做得很重,复杂度高
- **选 A**:Lab 当显微镜,想反馈回 Living。代价:看 trace 想反馈得切窗口,接受这个不便换语义清洁

### Q7:What-if 是横切动作,不是独立模式
- **没选**:把 What-if 做成与 Live/Replay/Sandbox 并列的第四个 tab
- **理由**:What-if 本质是"分叉"不是独立时间观。Replay 里可以 what-if,Sandbox 里也可以 what-if
- **实现**:任何 trace 都有"复制 + 改 + 重跑"按钮,产物是一条新 trace 挂在当前模式下

### Q8:Living API 接 `meal_hint`(`lunch`/`dinner`)+ 可选 `at_time`
- **没选 A**:默认 now,要算别的时间必须显式传 `at_time` — Agent 端必须显式传时间,语义不直观
- **没选 C**:完全去时间只接 `meal` — 失去"提前规划晚餐"灵活性
- **选 B**:用户真正关心的语义是"哪一餐",时间只是默认推导

### Q9:Lab trace 视图做"人话层"+"技术层"双档
- **没选 B**:只做技术层 — 违反校准 3(Lab 视觉门槛要低)
- **没选 C**:只做人话层 — 你无法调试
- **选 A**:默认人话层("因为你昨天反馈喜欢清淡 + 今天 38℃ + 这家有空调"),展开看技术层(L1/L2/L3 DAG)
- **代价**:人话层需要在 trace 上套一层模板化生成器或 LLM 摘要,工程量不低

### Q10:Sandbox 单次演练先做(A),策略对照对比(B)推后独立开发
- **没选 B**:Sandbox 内置"基线策略 vs 实验策略并排跑 7 天"对照能力 — 工程量大一档,挤压 2-3 周 Living/Agent 主线
- **选 A**:Sandbox 一次跑一个策略 N 天给结果。想对比自己开两个窗口手动看 — 不优雅但够用
- **承诺**:B 推后**独立开发**,不丢

## 7. 关键 invariants(将沉淀到 [CONTRACTS.md](CONTRACTS.md))

| # | 规则 | 来源 |
|---|------|------|
| 1 | Living API 输入输出 **JSON 自闭包**,无 UI 状态,无客户端记得的隐含上下文 | Q2/Q8 |
| 2 | Living API 只接 `meal_hint` + 可选 `at_time`,不强制接 `now` | Q8 |
| 3 | Lab **完全只读**真实数据 — 任何 trace 都不能在 Lab 上写真实反馈 | Q6 |
| 4 | Sandbox 写 trace 必带 `is_sandbox=true`,默认 trace 查询过滤掉 sandbox | Q4 |
| 5 | Sandbox 演练**不能** commit 回 Living | Q1 |
| 6 | Lab UI 用 URL 路由,sub-mode 由 path 决定 | Q5 |
| 7 | What-if 产物是挂在当前模式下的新 trace,不是独立模式 | Q7 |
| 8 | 共享只到 `packages/contracts/`(trace types + API client),UI 不共享 | Q3 |
| 9 | Lab trace 视图默认人话层,技术层折叠展开 | Q9 |

## 8. 优先级(2-3 周时间盒内)

按"Agent 接入是硬截止"倒排:

1. **Living API Agent-ready**(invariant 1+2)— 不做后面全错位,**最优先**
2. **`packages/contracts/`**(invariant 8)— Living 改动会引发 Lab TS 报错,提前建立共享层
3. **Lab 人话层 + Sandbox 单次演练 A 版**(invariant 4+9 + Q10A)— P0 训练场要可用
4. **Living Web 视觉打磨**(校准 3 反向要求,Living 跳 Lab 体验顺滑)
5. **Living Agent 接入**(MCP/飞书/CC 二选一先试)

## 9. 下一步:迁移方案盘点

待产出 [docs/refactor_living_lab_migration.md](refactor_living_lab_migration.md)(或合入本文 §10):

- `apps/web/` 现状 → keep / refactor / new / drop
- `apps/debug-ui/` 现状 → 同上
- `chisha/api.py` / `chisha/web_api.py` Living vs Lab 拆分
- `chisha/sandbox.py` / `chisha/debug_what_if.py` 在新架构里的归属
- `packages/contracts/` 从零搭建的最小骨架(types 列表 + client 接口)

---

## 附录 A:被推翻 / 让位的旧心智

- ~~三应用并列(用户端 / Debug / Sandbox)~~ → 二分(Living / Lab)
- ~~Debug 看单 trace、Sandbox 跑多 trace 是两件事~~ → Sandbox 输出就是一串 trace,Sandbox 是 Lab 的子模式
- ~~Living Web 是终态~~ → Living Web 是"当下唯一可见的端",未来 Agent 端是同级公民
- ~~Lab 是工程师玩具,视觉可以丑~~ → Lab 视觉门槛要低,默认人话层

# 文档维护准则 · chisha

> 目的:让文档不漂移、不重复、不腐烂。每次决策落地都过这套 checklist,30 秒搞定。
>
> 适用:志丹 + 任何接手的 Claude Code session / OpenClaw agent / 外部协作者。

---

## 1. 文档分工

| 文档 | 写什么 | 不写什么 |
|---|---|---|
| [PRD.md](PRD.md) | 为什么做、做给谁、做成什么样;产品定位、用户痛点、北极星指标 | 实现细节、技术选型 |
| [DESIGN.md](../DESIGN.md) | 当前版本架构、schema、API、prompt 大纲、避坑要点 | 决策推演、历史推翻 |
| [DECISIONS.md](DECISIONS.md) | **产品方向 / 架构原则 / 方法论 / schema 设计** 决策的推演、考虑过的方案、推翻历史 | 工程实施细节、prompt 修改 N 行、batch 数 |
| [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) | prompt 改了几行、参数微调、batch 数 / timestamp、bug 排查、回填脚本 | 战略决策推演、产品方向 |
| [style-guide.md](style-guide.md) | `apps/web/` 用户视图的文案规范 + 视觉系统 + 反模式清单（D-050~D-053 锁定的交互） | 后端实现、推荐算法 |
| [api.md](api.md) | 前后端 API 契约（V1 `/api/*` 端点表 + 字段细节 + 加载态约定） | 内部模块接口、Python SDK |
| [ROADMAP.md](ROADMAP.md) | V1/V2/V3 边界、当前状态、已砍清单 | 历史决策推演 |
| [RECOMMEND_PRINCIPLES.md](RECOMMEND_PRINCIPLES.md) | 推荐分层(L1/L2/L3) 职责铁律、打分维度原则 | 具体打分公式、参数值 |
| [L3_RERANK_REDESIGN.md](L3_RERANK_REDESIGN.md) | L3 精排实施方案 (D-047) 与必读约束 | L1/L2 设计 |

---

## 2. 决策归类判别准则

每次准备写 D-XXX 时,先问:

> **半年后做下一次大重构时,会不会回头查这条?**

- **会查** → 写到 [DECISIONS.md](DECISIONS.md)
  - 例子:"用户偏好如何刻画"、"L2 打分是否区分长期/短期"、"召回是否做硬过滤"、"schema 加哪 5 个新字段"、"用 LLM 精排还是规则精排"
- **不会查** → 写到 [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md)
  - 例子:"prompt 第 49 行重写凉拌锚点"、"per_restaurant_top_k 从 3 调到 2"、"batch 16 workers 跑了 85 min"、"修了 4 个 normalize 漂移"

**边界 case**:
- 一条决策包含战略部分 + 工程细节:战略部分写 DECISIONS,执行进度/batch 数另开一条 IMPL_LOG 条目并互相 link (参考 D-031/D-032)
- 决定加一个新字段是 DECISIONS,具体 prompt 怎么写让 LLM 输出这个字段是 IMPL_LOG
- 模型选型 (sonnet vs opus) 如果含成本/质量权衡推演 → DECISIONS;如果只是"按 D-XXX 的结论实施" → IMPL_LOG

---

## 3. 每次 D-XXX commit 后 checklist

每条新决策落地完(代码合并、测试过),3 项检查 30 秒:

### ① 写到 DECISIONS 还是 IMPLEMENTATION_LOG?

按上面"归类判别准则"决定。两份文件**共享 D-XXX 编号**,便于双向跳转。

### ② 是否推翻了之前某条决策?

- 推翻 → 找到旧条目,在标题或状态行加 `(superseded by D-NNN)`,**不删旧条目**(保留推翻历史)
- 升级/补强 → 新条目正文写 "依赖:D-NNN" 并简述"在 NNN 基础上加什么"

### ③ 是否需要联动更新其它文档?

| 改了什么 | 检查这些 |
|---|---|
| 产品定位 / 北极星 | PRD、ROADMAP |
| 架构 / API / schema | DESIGN |
| V1/V2/V3 时序 / 砍/加功能 | ROADMAP |
| 推荐分层逻辑 / 打分原则 | RECOMMEND_PRINCIPLES |
| L3 精排策略 | L3_RERANK_REDESIGN |
| 任意改动 + V1 acceptance 相关 | README 进度章节 |

---

## 4. 反 anti-patterns

- ❌ **写到 DECISIONS 的"执行进度"流水**:batch 数、timestamp、命令行不属于决策;搬到 IMPL_LOG
- ❌ **同一份内容在 DESIGN 和 DECISIONS 都写一遍**:DESIGN 只放当前实现,DECISIONS 只放推演 + 推翻历史。两者用 link 互相指
- ❌ **D-XXX 写完不更新 ROADMAP / README**:决策与进度脱节是头号文档腐烂源
- ❌ **新加文档却不在 README 文档体系表里登记**:外人找不到等于不存在
- ❌ **PRD 频繁改**:定位级变化才动 PRD,每次动要在 DECISIONS 加一条说明为什么

---

## 5. 阶段收口(每个里程碑 / 每周一次)

V1 / V2 / V3 切换或每周一次 wrap-up 时,做一遍:

1. **DECISIONS 全文扫一遍** — 有 `superseded` 没改的 / 有"已废弃"还在 active 状态的 → 修
2. **IMPL_LOG 倒查** — 上周新增的 IMPL_LOG 条目,是否有错位的决策应该升到 DECISIONS?
3. **ROADMAP 当前状态** — 与最近 git log 对照,缺的 D-XXX 补进去
4. **README 进度章节** — 与 ROADMAP 当前状态对齐
5. **DESIGN §7 速查表** — 新决策的 stub 行加进去

如果会话型工具 (Claude Code 等) 有 `neat-freak` skill,在阶段收口时**主动调用**,而不是等到下次 review 才发现漂移。

---

## 6. 文件命名 / 编号约定

- D-XXX 编号**全项目共享**,跨 DECISIONS / IMPLEMENTATION_LOG 唯一
- 推翻型条目 D-NNN.M 形式(如 D-046.1 是 D-046 后的修订)
- 文档新建必须先在 README 文档体系表登记;不进表 = 失踪文档
- DECISIONS / IMPL_LOG 新条目追加到尾部,**禁止插队改编号**

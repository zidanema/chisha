# 今天吃点啥 · 路线图

> 这份文档说清楚**什么时候做什么、什么不做**.
> 防止偏航: 实现某个功能前先看这里它在哪个版本.
> **已砍清单**尤其重要 — 避免反复讨论同一个被否决的想法.
>
> 项目名: 今天吃点啥 · 代码名: `chisha`

---

## 当前状态

**V1.0 工程里程碑收尾完成** (2026-05-20, D-001~D-093) — 推荐链路 L1/L2/L3 全跑通 + Web SPA + V1.1 反馈 + L1 真兑现 (LLM 抽取) + Sandbox Time-Travel + trace 持久化 + Debug 三模式 + FastAPI 23 端点 + Refine v2 / Faithful Refine framework (D-080~D-085) + L2 refine 信号校准 + 死维度清理 (D-090/091/092, 14 维 breakdown) + Sandbox Lab 白盒时光机 (D-093).

**接下来**: 进入 **Phase 1 推广准备** — 自用沉淀 + 个人 agent 接入跑通 + 同事 screener.

历史细节: [archive/DECISIONS_phase0.md](archive/DECISIONS_phase0.md) + [archive/ROADMAP_phase0.md](archive/ROADMAP_phase0.md). 活决策: [decisions.md](decisions.md). 跨文件约束: [CONTRACTS.md](CONTRACTS.md).

---

## Phase 路线 (D-070 沉淀)

```
Phase 0 · 自用跑通 (✅ 工程侧完成, 2026-05-20 收尾)
  范围: 1 方法论 (harvard_plate) × 1 用户 × 2 zone
  门槛: 自己愿意每天用 + 接个人 agent 跑通

Phase 1 · 同方法论同事推广 (next)
  范围: 1 方法论 × N 同事 × M zone
  准入条件: 任意一套饮食原则 (不限定 harvard_plate), 进前发 screener 探同事原则派密度, 阈值 30%
  关键工程: profile 解耦个人化 / data zone 拆包 / 本地数据闭环 / 接入外部 Agent / 必要时扩 methodology spec
  目标: ≥ 3 同事自发持续使用

Phase 2 · 双向扩展 (顺序后议)
  方向 A: 更多方法论 (增肌 / 糖控 / 孕期 / 高血压)
  方向 B: 更多区域 / 更多用户 / 开源
  真实需求拉动哪个就做哪个
```

---

## Phase 1 启动前必收口 (硬门)

- 第二份 methodology spec (验证抽象解耦)
- screener 设计 (筛同事原则派密度)
- 沙箱模式交互动线重设计 (推广前用户心智不能乱)
- L1 词表扩 cuisine token (同事 cuisine 比志丹分散)
- B-001 v2 反馈短链路全字段覆盖
- Living/Lab router 拆分重做 (D-086 回滚后待重做)
- Living API agent-ready 参数化 (meal_hint + at_time 重做)
- D-074 翻 active: AI-friendly 接入终态 = CLI + Skill 模式, `llm_request_spec` 数据契约取代 closure 注入

详细 design brief: [`design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md`](design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md).

---

## V1.5 · 数据链路重构 (Phase 1 启动后)

> 目标: 把"采集 / 清洗打标 / 对外数据服务"拆成单仓内的独立子模块 (D-030).
> **触发条件**: 自用稳定 + 个人 agent 接入跑通, 主线推荐链路稳定.

- 把 `~/waimai_data` 接管进 `chisha/collector/`
- 把 `chisha/loader.py` + `scripts/tag_dishes.py` + `scripts/tag_via_subagent.py` 收拢到 `chisha/cleaning/`
- 新建 `chisha/data_service/`: 清洗后数据对外的统一入口
- 三子模块通过 schema 契约解耦, 不互相 import 内部细节
- 推荐层只消费 `chisha.data_service`, 不再读 `data/{zone}/*.json` 硬路径

成功标准: 三子模块各自能单跑 pytest; collector schema 改字段时只影响一个子模块.

---

## V2 · 闭环 + 接入完善 (Phase 1 之后)

### V2.0 · 反馈闭环
- meal_log.jsonl 完整记录 (dish 字段补 cuisine + cooking_method, D-025)
- personal_offsets.json 写入逻辑 (粒度 = `cuisine::cooking::ingredient`)
- 飞书反馈卡片字段 / submit_feedback API / accept_recommendation API / log_meal API

### V2.1 · refine 智能化 (V1.0 部分骨架已就绪)
- 个性化 refine 快捷标签 (动态生成: 最近 3 天没吃过的菜系/食材 + bottom_preferences 反向)
- update_taste API (自然语言更新偏好)

### V2.2 · learned_profile 统计聚合
- 加工脚本 (每周日凌晨自动跑)
- 统计聚合到 (cuisine, cooking_method, main_ingredient) 维度 (D-026)
- top/bottom_preferences / blacklist 自动维护
- summary_for_llm 输入 LLM 精排 prompt

### V2.3 · CLI + Skill 模式接入
- 走 D-074 共识方向 (不做 MCP Server)
- `manifest.json` + `openapi.yaml` + `AGENT_ONBOARDING.md` 三件套
- `chisha init --agent <type>` CLI + `chisha doctor` + `chisha schedule install`
- LLM 抽象走 `llm_request_spec` 数据契约 (chisha 不调 LLM, 把 prompt + tool_schema 还给 Agent)

### V2.4 · 数据层按工区拆包
- 数据按工区拆 `chisha-data-shenzhen-keji` / `chisha-data-beijing-zgc` 等子包
- 包发布到 PyPI (先内部, 再公开)
- 多工区数据支持

---

## V3 · 开源化 (V2 完成后)

- README 完善 / examples 仓库 / 数据脱敏 / 文档站 / CONTRIBUTING / 发 GitHub / 软推广

---

## 已砍清单 (明确不做)

> 这些功能曾被讨论过. **已经决定不做的, 不要重新讨论**.
> 如果想推翻, 先去 decisions.md 加一条新决策说明为什么.

### 产品定位类

| 功能 | 砍掉的原因 | 关联决策 |
|---|---|---|
| SaaS 平台形态 | 运营成本高、隐私顾虑、单用户协同无意义 | D-001 |
| 用户系统 / 登录 / 计费 | 不做 SaaS 自然不用 | D-001 |
| Web URL 渲染层 (Skill 内嵌输出格式) | 渲染是 Agent 的事, Skill 不绑死 | D-017 |
| V1 主交互走飞书卡片 (取代 Web SPA) | D-051 翻案: V1 改 localhost Web SPA, 飞书降级到 V1.5 推送通道 | D-051 |
| MCP Server 包装 | 2026-05-16 方向改: 按 CLI + Skill 模式 (同款飞书 CLI) | D-074 (草稿) |

### 功能边界类

| 功能 | 砍掉的原因 |
|---|---|
| 卡路里精确追踪 | 太重, 违背"轻量决策"定位 |
| 在家做饭推荐 | 数据形态不同, 不在外卖场景内 |
| 食材采购建议 | 同上 |
| 体重 / 体脂记录 | 已有专业 APP |
| 训练计划生成 | 是另一个产品 |
| 商家平台直接下单 | 接口封闭, 跳转就够 |
| 社交分享 | 偏离工具属性 |

### 推荐逻辑类

| 想法 | 砍掉的原因 | 关联决策 |
|---|---|---|
| 训练日感知 (练后加蛋白) | 增益小、复杂度高, V1 暂不做 | D-016 |
| 全局协同过滤 ("和你类似的人爱吃") | 单用户场景没意义 | D-001 |
| seed_dishes 列表替代 taste_description | 自然语言更高效 | D-014 |
| 严过滤 (油脂硬卡) | 结构正确比绝对低脂重要 | D-006 |
| 全量丢 LLM 推荐 | token 爆炸 + 大候选约束满足效果差 | D-005 |
| 每次推荐都让 LLM 实时判断营养画像 | 一致性差、慢、贵 | DESIGN 早期 |
| 严格 1/2-1/4-1/4 餐盘硬约束 | 中式外卖现实下不可达, 召回会被卡死 | D-023 |
| V1 让 LLM 在 100 候选里挑 3 个 | LLM 在挑选/排序上引入随机性, 打分 top 3 更稳 | D-024 (后 D-049 已升级到 V2 唯一路径) |
| personal_offsets 按"店::菜"粒度 | N 太小、信号弱; 改 (cuisine, cooking, ingredient) | D-025 |
| LLM 蒸馏 learned_insights 自然语言洞察 | N=1 数据下容易过拟合假规律; 改统计聚合 | D-026 |
| 本仓做数据采集 | 采集独立维护 (D-030 修订: 单仓三子模块) | D-027 → D-030 |
| 北极星 = 决策时间从 15min 降到 1min | 不可度量、易作弊; 改连续采纳率 | D-028 |
| 让用户主动选 mood (chip) | 摩擦 + 误导信号 | D-071 (后 D-073 refine 路径走结构化意图) |
| **macOS launchd 定时拉起服务** | 自用阶段手动开页面没毛病, 不是债 | 2026-05-17 拍板 |

### 反馈交互类

| 想法 | 砍掉的原因 | 关联决策 |
|---|---|---|
| 单一"满意度"星级 | 好吃和满意是两个维度 | D-010 |
| 文本是唯一反馈方式 | 摩擦太大, 多数人不填 | D-011 |
| 只用静态有反馈数据 | 样本太稀疏 | D-013 |
| 反馈一次提交后可改 | 下游学习不稳定; 改 append-only comments | D-066 / D-067 |

### Phase 0 内不做 (现已收尾, 仍保留作 Phase 1 入口前的护栏)

- data zone 拆包发布 PyPI / 外部 Agent (OpenClaw / Hermes) 接入 / screener 设计 / 第二份 methodology spec / L1 词表进一步扩 (cuisine 偏好 token) / 调试台 React 化整合

详见 [CONTRACTS.md "范围红线"](CONTRACTS.md#范围红线-v10-后-phase-1-推广前不做).

---

## 触发重审的条件

| 触发条件 | 重审什么 |
|---|---|
| 同事开始用且不写 Python | D-003 CLI 形态 |
| LLM API 成本显著上升 | D-007 召回数量 |
| 真的有非开发者群体强需 | D-001 SaaS 形态 |
| 某个 LLM 上下文能直接处理万条候选 | D-005 三阶段架构 |
| learned_profile 统计聚合质量长期不准 | D-026 加工策略 |
| 用户连续多次拒绝探索候选 | D-015 探索机制 |
| OpenClaw 飞书集成出现重大变更 / 不可用 | D-022 接入对象 |
| 单餐 40g 蛋白召回打掉组合 > 25% | D-044 min_protein_g 下调 |
| collector schema 变更打挂 zone ≥ 2 次 | D-030 提前启动 V1.5 |
| 外部 Agent 真要接入 chisha 推荐 | D-038 / D-074 Phase 2 启动 |
| LLM 精排 sonnet-4.6 与 deepseek-flash 质量持平 | 改 profile.yaml 切 provider 降本 |
| Web 自用一周采纳率 < 50% 且飞书推送能独立证明补回触达缺口 | D-051 重审, 飞书提前到 V1.5 主交互 |

---

## 路线图维护原则

1. **完成的项目立即勾选**
2. **新增功能想法**先进 V3 / V4 候选区, 不直接进 V2
3. **砍掉的功能加进已砍清单**, 附上原因和关联决策
4. **触发重审条件命中时**, 先去 decisions.md 加新条目, 再调整路线图

# 今天吃点啥 · 路线图

> 这份文档说清楚**什么时候做什么、什么不做**.
> 防止偏航: 实现某个功能前先看这里它在哪个版本.
> **已砍清单**尤其重要 — 避免反复讨论同一个被否决的想法.
>
> 项目名: 今天吃点啥 · 代码名: `chisha`

---

## 当前状态

**V1.0 工程里程碑收尾完成** (2026-05-20) — 推荐链路 L1/L2/L3 全跑通 + Web SPA + V1.1 反馈系统 + L1 长期反馈层 (LLM 抽取真兑现) + Sandbox Time-Travel + trace 持久化 + Debug 三模式 + FastAPI 23 端点 + Refine v2 / Faithful Refine framework (D-080~D-085) + 真兑现字段闭包 (D-094) + L2 refine 信号校准 + 死维度清理 (D-090~092, 14 维 breakdown) + Sandbox Lab 白盒时光机.

**接下来** (D-097 定位: 自用为主、推广随缘): 个人 agent 接入跑通 (D-074) + B-001 反馈短链路修复 (P0). 同事推广向工作 (screener / 第二份 spec) 推迟到真要推时.

历史细节: [archive/DECISIONS_phase0.md](archive/DECISIONS_phase0.md) + [archive/ROADMAP_phase0.md](archive/ROADMAP_phase0.md). 活决策: [decisions.md](decisions.md). 跨文件约束: [CONTRACTS.md](CONTRACTS.md).

---

## Phase 路线 (D-070 沉淀)

```
Phase 0 · 自用跑通 (✅ 工程侧完成, 2026-05-20 收尾)
  范围: 1 方法论 (harvard_plate) × 1 用户 × 2 zone
  门槛: 自己愿意每天用 + 接个人 agent 跑通

Phase 1 · 同方法论同事推广 (D-097: 优先级降, 自用为主)
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

## Phase 1 启动前必收口 — D-097 收窄 (自用为主, 推广随缘)

> D-097 (2026-05-25) 把原 9 项按"自用是否需要"重切. 真要推广同事时回看 D-097 恢复"推迟"项.
>
> **D-102 (2026-05-28) 重激活 Phase 1 工程主线 = 可分发共享核心** (不推翻 D-097 自用心态, 把"真要推广时恢复"那一刻落地). 分步: Step1 焊大脑 (统一 plan contract / FallbackPlan, **已落地 D-102.1**) → Step2 root 拆分 →`~/.chisha/` → Step3 manifest+doctor+plugin. 提案 `docs/proposals/2026-05-28-distributable-shared-core.md`.

**自用刚需 (真硬门, 2 项)**:
- **AI-friendly 接个人 agent** — D-074 **Phase 0 已落地 (2026-05-25)**: chisha 零 LLM + one-shot CLI (`python -m chisha.agent_cli` verb 链 start/resolve-intent/apply-rerank/choose/init/doctor) + Claude Code reference adapter skill (`init` 生成); agent 的 LLM 做 context 抽取 + L3 精排 (`llm_request_spec` 信封). 自用一周收 bug → 稳定后 Phase 1 接 OpenClaw. 实现见 [decisions D-074](decisions.md) + [CONTRACTS「Agent CLI 协议」](CONTRACTS.md)
- **B-001 反馈短链路** (P0) — 差评当前不生效 (score.py 不读 rating), 自用留存杀手

**已完成 / 实质已解**:
- ✅ V1 refine 退役 + V2 schema 扩 4 槽 + 全栈切 V2 (D-096 / D-090.1 / D-094.1, 2026-05-24)
- ✅ 沙箱动线: 用户视图 sandbox UI 已移除 (:5173) + 拆独立 Lab :5175 (D-093), "用户心智乱"风险消除
- ✅ B-001 反馈短链路即时生效 (差评不生效 P0, D-098, 2026-05-25) — 残留"连吃同一菜系无冷却"(原口误"香菜"实为"湘菜", cuisine 多样性, 数据现成) 拆出 F-015

**降级到 BACKLOG (有兜底, 触发再做)**:
- Living/Lab router 后端拆分 (F-013) — web_api.py 沙箱逻辑缠生产路由; 有 D-077 fail-loud 护栏 + 操作纪律兜底
- screener 设计 (F-003) — 3-5 熟人一句话判断即可

**推迟 (为同事推广服务, 自用不需要)**:
- 第二份 methodology spec (F-004) / L1 词表扩 cuisine token (F-001, 同事 cuisine 才分散)

详细 design brief: [`proposals/2026-05-25-ai-friendly-integration.md`](proposals/2026-05-25-ai-friendly-integration.md).

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
| 反馈第 3 维 ("不合时宜", 原 F-008) | 过度细节, 短期不做; D-098 已用 `repurchase_intent` 缓解"本身爱但那天不想吃"误伤, 扩 schema ROI 不足 | D-098 |
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

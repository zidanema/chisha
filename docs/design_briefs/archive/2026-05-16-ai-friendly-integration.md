# AI-Friendly 接入终态讨论 Brief

**日期**: 2026-05-16
**状态**: 思路/原理/技术方案共识阶段, **不含实现细节**
**目的**: 为后续 D-074 翻案 (D-022/D-038/D-051) 提供讨论沉淀, 待 Codex review 后再正式落地决策

---

## 1. 背景与原始出发点

chisha 项目目前 Phase 0 工程侧已完成 (D-001 ~ D-072, 2026-05-15):
- 完整 Web SPA (`apps/web/`) + FastAPI 13 端点
- L1 召回 / L2 打分 / L3 LLM 精排链路全跑通
- 反馈生命周期 (D-056~D-068) 上线
- LLM provider 抽象 (D-047) ready

但 D-001 原始定位是"开源 Skill", 最终形态**不是独立产品**, 而是被用户的个人 Agent 接入。

**Phase 0 出现事实漂移**: chisha 已经长成独立产品形态 (有 UI / 有 13 个 HTTP 端点 / 有自己 LLM 精排链路), 但原始叙事仍是嵌入式 Skill。今天讨论的目的是重新对齐终态。

**志丹的原始 4 条内核** (不带形态假设):
1. 解决自己每天点餐 10-20 分钟决策疲劳 (Phase 0)
2. 核心承诺 = 扫 30 秒, 3 选 1, **主动推**
3. 不再装一个 APP, 要进现有信息流
4. 将来开放给同事 / AI 圈, 但**不做 SaaS, 不部署, 不运维**

---

## 2. 共识: 路线 S (AI-friendly Skill) 为终态

**Web 是脚手架, Agent 接入是终态。**

讨论中曾抛出两条路线作对照:

| 路线 | 定位 | 选择 |
|---|---|---|
| P (Product) | chisha 独立产品, Agent 是众多入口之一 | 否决 |
| S (Skill) | chisha 是寄生能力, Agent 是宿主 | **选定** |

**为什么选 S** (志丹的核心理由):
- **推广目标决定**: 独立产品推广门槛高; AI-friendly Skill "一句话接入"符合 AI Agent 生态趋势
- **数据隐私 + 不运维**: 用户数据全本地, 作者不部署任何服务 (D-001 原则保留)
- **个人目标**: 锻炼"做 AI-friendly Agent 产品"的能力

**Web 不砍, 转为算法层迭代台**:
- 算法 / prompt / score / methodology spec 在 Web 上继续打磨
- Agent 通道**直接复用底层资产** (打分函数 / 排序逻辑 / 金牌 prompt)
- Web 交互层 (progressive form / refine 面包屑 / 反馈 modal) 是 Web-only, Agent 通道各自设计 UX

---

## 3. 核心技术原理: prompt-out / result-in 数据契约

**今天讨论中最关键的设计 insight (志丹提出)**, 替代 D-038 Phase 2 原计划的 closure 注入方案。

### 原 D-038 Phase 2 设想 (放弃)

```python
def my_agent_llm(prompt): return self.chat(prompt)
chisha.recommend_meal(..., llm_call=my_agent_llm)
```

要求 Agent **同步暴露** LLM 入口给 chisha 调用。

**问题**: 异步 Agent / 跨进程 Agent / IM-based Agent / 飞书机器人等大量形态做不到, 协议门槛太高。

### 新方案: prompt-out / result-in 纯数据契约

```
Step 1: Agent → chisha
        prepare_rerank(meal, profile, today_context)

Step 2: chisha 跑完 L1 召回 + L2 打分, 拼好 L3 prompt
        chisha → Agent: { prompt, candidates, state_token }

Step 3: Agent 拿 prompt → 调它自己的 LLM (任何 provider) → 拿到 JSON 响应

Step 4: Agent → chisha
        apply_rerank(state_token, llm_response)

Step 5: chisha → Agent: { cards: [3 个结构化推荐] }
```

**优势** (相比 closure 注入):
- 纯数据契约, 任何 Agent (同步/异步/跨进程/IM) 都能实现
- chisha 不需要知道 Agent 用谁的 LLM、跑哪、走什么协议
- 完全无状态, 符合 D-001 "作者不参与运行"精神
- 调试友好: prompt 和 response 都是可观察、可重放的字符串

### 完全无状态

state_token 实现细节暂不讨论 (志丹明确锁定 stateless, 实现层面后续再选). 候选思路:
- 签名 token 把 candidates / profile snapshot 序列化嵌进 token 本身
- chisha 不维护任何进程内 session 状态

---

## 4. 当天上下文注入

**复用现有 refine 自由文本通道, 不另起 schema。**

Agent 把"用户今天发烧了 / 不想出门 / 想吃辣" 这种当天 context 压成自然语言, 作为 `today_context` 入参传给 `prepare_rerank`, chisha 内部走现有 L3 精排链路消化。

不做结构化字段 (`{health: "sick", mobility: "indoor"}`) , 因为:
- L3 LLM 本来就能直接吃自然语言
- 结构化 schema 永远不够用
- 改打分链路会触发 D-072.1 baseline_l2_snapshot 严格回归, 成本不值

---

## 5. 触发机制

**chisha 完全被动, 触发权 100% 在 Agent 侧。Pull 模式。**

讨论中曾考虑 chisha 是否需要自带 cron daemon。志丹反驳: OpenClaw / Hermes / HappyClaw / Claude Code 等**个人助手型 Agent 大都自带 cron 能力**, chisha 不需要做 daemon, 也不应该 (违背"不运维"原则)。

**契约要求**: chisha 在 manifest / SKILL.md 中**声明"建议触发时机"**, 例如:
- lunch_recommend: 工作日 10:30
- dinner_recommend: 工作日 17:00

Agent 装 chisha 时, onboarding 阶段自动读取这个声明, 注册到它自己的调度系统。用户不用自己想"该几点触发"。

---

## 6. 推送通道

**chisha 不做推送, 但提供"推送适配指南"。**

Agent 拿到推荐结果后, 自己决定推给哪 (飞书 / IM / 邮件 / 系统通知 / Telegram bot)。chisha 仓库提供一份 `docs/PUSH_INTEGRATION.md`, 各通道一段示例代码, Agent 直接抄。

---

## 7. 反馈回流

**Agent 在饭后调 `submit_feedback`, chisha 提供 `pending_feedback` poll 入口。**

复用 D-066/D-067 已有的反馈生命周期。外部 Agent 通过两个调用驱动:
- `list_pending_feedback()` — chisha 维护 pending 队列, Agent 定期 poll
- `submit_feedback(card_id, status, ...)` — Agent 拿到用户回答后回传

---

## 8. Onboarding 5 步契约

**核心 insight: `AGENT_ONBOARDING.md` 是写给 LLM 读的指令文档, 不是给人读的 README。**

用户对自己 Agent 说"接入 chisha", Agent fetch 这份文档, 按步骤自己跑:

| 步骤 | Agent 在干啥 | chisha 提供 |
|---|---|---|
| 1. 装包 | `pip install chisha chisha-data-{zone}` | PyPI 包 + zone 列表 |
| 2. 提 profile | 读用户历史会话 + 跟用户对话 → 写 `~/.chisha/profile.yaml` | profile 提取 prompt + JSON schema |
| 3. 装触发 | 注册 cron (Agent 自身能力) | manifest 中 suggested cron 时机声明 |
| 4. 接通道 | 注册推送 → 渲染推荐成飞书卡片 / IM / 邮件 | 推送适配指南 + 渲染模板 |
| 5. 接反馈 | 饭后问用户, 调 `submit_feedback` | 反馈 prompt + Python API |

格式上**不绑死 Anthropic Skill**, 用纯 markdown + 明确指令 + checklist, 让 Claude/GPT/国产 LLM 都能消化。

---

## 9. Surface 边界澄清

避免 Web 与 Agent 通道未来漂移:

| 层 | Web / Agent 关系 |
|---|---|
| 算法 / prompt / score / methodology spec | Web 迭代, Agent 通道**直接复用** |
| 数据 schema / API contract | 同一份, 两边共用 |
| 交互层 (progressive form / refine 面包屑 / 反馈 modal / lock-in) | **Web-only**, Agent 通道各自设计 UX |

---

## 10. 切换时点

**Phase 0 Step 2 自用一周验收完后, 直接切到 Agent 通道开发。**

**砍 V1.5 飞书独立推送通道** — 飞书集成归 Agent 适配指南范畴, 不再单做。

---

## 11. 推迟事项

- **数据地理性问题**: 单工区之外的用户怎么办。Phase 0/1 假定深圳科技园, 推广方案 (schema 化 + collector 工具让用户自采) 压后。
- **N 份 Agent 适配 (Claude Code / OpenClaw / Dify 各一份)**: 先写一份通用 onboarding, 后面针对具体 Agent 优化。
- **多 Agent 并发写本地 profile / meal_log**: 单写者约定 + meal_log append-only, 真撞了再补文件锁。

---

## 12. 翻案预告 (D-074 草稿, 待 Codex review 后落)

新决策将翻案以下三条:
- **D-022** (V1 接入 OpenClaw + 飞书卡片) — 已被 D-051 部分翻, 现彻底翻
- **D-038** (LLM 抽象 Phase 2 callable 注入) — 改为 prompt-out / result-in 数据契约
- **D-051** (Web 优先, 飞书降级 V1.5) — 砍 V1.5, Web 长期作算法层迭代台

---

## 13. 给 Codex 的 review 问题

请从以下角度挑战这份 brief, 找漏洞和盲点:

1. **prompt-out / result-in 协议**是否真能覆盖所有主流 Agent 形态? 有没有反例 (流式 LLM 输出 / tool_use 强约束 / 多轮交互需求)?
2. **完全 stateless** 在反馈回流链路上是否成立? 用户吃了哪个 → Agent 怎么知道是哪一次推荐的卡片? `state_token` 能不能撑住跨会话的反馈生命周期?
3. **"Agent cron pull"** 模式下, "主动推" 核心承诺还能不能保住? 如果用户的 Agent 自己挂了或忘了触发, 推荐就完全失踪 — 这风险是否可接受?
4. **Phase 0 Step 2 完直接切**, 砍 V1.5 飞书通道, 是否风险过大? 飞书路径作为 fallback 是否值得保留?
5. **数据地理性问题压后**, 对推广目标的实际杀伤力多大? 是否应该 Phase 1 内就给个方向?
6. **Web 算法迭代与 Agent 通道复用** 这条假设, 是否低估了"交互层与算法层耦合" (比如 refine 多轮收敛逻辑可能既是算法也是交互)?
7. **`AGENT_ONBOARDING.md` 给 LLM 读** 这个思路本身是否成立? 当前主流 Agent (Claude Code skill / Anthropic Skill / Cursor / Dify) 真的能"读文档自动接入"吗, 还是需要 Agent 框架原生支持?
8. **prompt-out / result-in 的契约稳定性**: 如果 chisha 改 L3 prompt 模板 / 改候选数量 / 改打分维度, Agent 那侧需要同步改吗? 是不是引入了隐性的 API 版本耦合?
9. 还有什么我们没想到的盲点 / 错误假设 / 隐性约束?

不要给"你说得对" 类反馈, 要尖锐, 要挑战。

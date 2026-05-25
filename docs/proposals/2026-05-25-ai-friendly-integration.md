# AI-Friendly 接入设计 (D-074)

> 2026-05-25 · 志丹 + Opus 重新讨论 + Codex 压测收敛的**正式设计**。
> 取代 2026-05-16 的 v1/v2-consensus 两份过程稿（挪 `archive/`）。本文只写"怎么做好 AI-Friendly"，不留讨论过程。
> 定位前提：[D-097](../decisions.md) 自用为主、推广随缘。

---

## 1. 定位与边界

- chisha = 被宿主 Agent 调用的**能力体**，不是独立产品
- 严守 [D-001]：不部署 / 不运维 / 不接触云端用户数据。**本机 CLI 读写本地状态不算违背**
- D-074 Phase 0 = **reference adapter = Claude Code**，端到端跑通志丹自用
- 最终愿景：志丹对自己的 agent 说一句话 → agent 调 chisha → 给原则派一组推荐选 1（exploit 稳妥 + explore 探索两段；refine 时聚焦），并越来越懂他

## 2. 核心架构：确定性用代码，智能用 LLM

**第一原则**：确定性逻辑在 chisha 用代码做死；需要智能判断的交给**宿主 agent 背后的 LLM**。

chisha **不持有任何 LLM provider key、不发任何 LLM 请求**。相对 [D-038]（LLM 抽象）的唯一变化：把"chisha 调 LLM"换成"agent 的 LLM 来调"——边界原则不变，执行方变了。

| 环节 | 确定性 → chisha 代码 | 智能 → agent 的 LLM |
|---|---|---|
| context / refine 意图 | schema 校验、语义清洗、`raw_text` 注入、抽漏/冲突 disclosure、trace 写入 | 自然语言 → 候选结构化 intent JSON |
| 召回 recall | cuisine / staple / brand / cooking_method 硬过滤、bucket | — |
| 打分 L2 | 多维确定性打分、多样性 | — |
| 精排 L3 | 候选准备、rerank prompt/schema 准备、产出校验（index 界 / 唯一 / 排序）、health_flags、brand 唯一性后处理、trace | 读候选 + prompt → 排序产出推荐（exploit + explore 段）+ 理由 + narrative |
| 兜底 | LLM 失败 / 产出不合法 → 退 L2 + disclosure | — |

**chisha 不轻——它保留全部确定性守卫**；它只是不调 LLM。这是 Faithful Refine（§5）不被破坏的根。

## 3. 接口：one-shot CLI 状态机

agent 面 = **一次性 CLI**（shell out、跑完即退、无 daemon / 无 HTTP / 无 localhost auth / 无 async-poll）。web / debug-ui / sandbox-lab 三个台子**继续用现有 FastAPI**，与 agent 面互不干扰。CLI 套在既有可 import 模块（recall/score/rerank/refine）上，不重复实现。

流程有**两个 LLM 步骤**（抽取 context→intent；精排 rerank），每步都是"chisha 发 spec → agent LLM 执行 → 交回 chisha 校验落库"的握手。verb 链：

| verb | 职责 | 返回 | 写哪 |
|---|---|---|---|
| `start --meal <m> [--context "<原话>"]` | 无 context：recall+score；有 context：只发抽取 spec | 无 context → 候选 + rerank spec；有 context → extraction spec | trace_store（建 pending round + `recommendation_id`） |
| `resolve-intent --id <rid> --intent <json>` | 收抽取结果 → 清洗/校验/disclosure → recall+score | 候选 + rerank spec + intent disclosure | trace_store（推进 round） |
| `apply-rerank --id <rid> --response <json>` | 收精排结果 → 校验 + health_flags + brand 唯一 + fallback | final cards（stable `card_id`） | trace_store（round → ready） |
| `choose --id <rid> --card <cid> --action <accept\|skip>` | 记录用户选择 | — | feedback_store（+ accept 时 meal_log） |
| `init --agent <type>` / `doctor` | 生成 adapter / 检查注册 + 版本兼容 | — | — |

- **round 状态机**：状态 `pending → resolved → ready`，`resolved` = 候选已算 + rerank spec 已发。**有 context**：`start` 建 pending（只发 extraction spec）→ `resolve-intent` 推到 resolved；**无 context**：`start` 内部一步到 resolved（intent 空，直接 recall+score + 发 rerank spec，不经 `resolve-intent`）。`apply-rerank` **一律从 resolved → ready**。每步幂等键 =`(rid, round, operation)`，重试同 `correlation_id` 返回同结果、不新建 round（trace_store 现只写已完成 round，需加状态位）
- **scope 显式**：默认 `production`；只有显式 `--scope` / `--at-time` 才走 sandbox / time-travel，**禁止隐式继承 web 的 sandbox ContextVar**（CLI 直 import 只绕过路由层，`data_root`/`clock`/`l1_prefs`/session 仍须显式约束）
- **refine 多轮**：再次 `start --context "再辣点" --from <rid>` 起新 round（n_explore=0 聚焦）；纯换一批（无 context）也走 `start`

## 4. 协议：machine-readable `llm_request_spec` 信封

skill markdown 是人/agent 的剧本，**不是行为契约**；契约是 `start` / `resolve-intent` 返回的机器可读 `llm_request_spec` + chisha 侧校验入口。这样才能从 Claude Code 推广到 OpenClaw（OpenClaw 照信封执行，不靠读说明文字）。

`llm_request_spec` 是**带版本的信封**，两个 operation 共用一个 shape：
- `operation_kind`：`extract`（context→intent）| `rerank`（候选→排序）
- `protocol_version` / `candidate_schema_version`（V2.1，含 `staple_want/avoid` / `price_band` / `wants_soup` 四新槽）
- `correlation_id` =`(recommendation_id, round, operation)`，绑定请求与回传、支幂等
- `output_mode`：`tool_use` | `text_json`（按 adapter 能力；CLI provider 不支持 tool_use → text_json）
- `system` / `messages`、`tools` 或 `json_schema`、`required_validation`、`fallback_policy: chisha_l2`
- 回传 response 含结构化 `disclosure` 字段（extract：agent 自报未映射的诉求，见 §5；rerank：校验 / fallback 状态）

agent 只**执行**信封，产出按 `correlation_id` 回传对应 verb，由 chisha 校验落库。

## 5. Faithful Refine 怎么保（化解 BLOCK 1）

把意图抽取的 LLM 调用搬到 agent，**但守卫全留 chisha**：

1. **prompt 即契约**：chisha 把现有 parse 规则（禁脑补 / 冲突留空 / schema 未覆盖不假装 / 枚举闭包 / `price_max` 优先 / reference 与 `reject_previous` 白名单）+ V2.1 schema 作为 `extract` spec 发给 agent，让它的 LLM 按**同一套规则**抽，忠实度对齐 chisha 自抽
2. **raw_text 由 chisha 注入**（agent 不得伪造）：即使结构化抽漏，L3 prompt 仍含原话 → 二次软兜底
3. **chisha 跑等价清洗**：枚举丢弃 / 类型强转 / reference 清洗 / 越界进 `raw_understanding`
4. **强制自报缺口**：`extract` 契约**要求 agent 把任何没自信映射进 slot 的诉求写进 `raw_understanding`**；chisha 把它当**用户可见 disclosure** 弹出（"清淡=低油；'那家店'没认出，已忽略"）。这是智能侧自报，符合"智能用 LLM"
5. **失败显式**：parse 失败 / 不合法 / 清洗丢诉求 → 标 fallback + disclosure，raw + cleaned + understanding 全落 trace（[D-081] 不外包给 agent 自觉）

**诚实记录残留（消不掉）**：零 LLM 的 chisha 无法语义校验抽取完整性（要校验就得有 LLM）。若 agent **既漏抽进 slot、又没写进 `raw_understanding`**，hard-avoid 会**静默降级成 L3 软提示**（recall 硬过滤拿不到空 slot）。这风险**现状 chisha 自抽也有**（非本设计引入），受 agent LLM 质量约束。Claude Code（Claude）可接受；Phase 1 接 OpenClaw 跑 eval set 量化，**弱 LLM 则届时评估是否补一个极小的语义覆盖校验 LLM（那一步才破零 LLM，现在不破）**。

## 6. 状态与历史：复用 + 加固，不新建

chisha 已有 3 套 **JSON**（可 cat/grep，满足"别黑盒"诉求，无需 SQLite 也无需新 JSONL ledger）。Phase 0 **不新建 source of truth**：

| 现有 store | 角色 | 谁写 |
|---|---|---|
| `trace_store` | 推荐执行证据（versioned / round / flock / atomic） | prepare / apply-rerank |
| `feedback_store` | 用户**选择** canonical（accept / skip） | choose |
| `meal_log` | accept 后多样性 cooldown 事实 | choose(accept) |

加固（按优先级，不过度工程化——单用户低频）：
- **幂等键**（中，便宜值得做）：`apply-rerank` / `choose` 带幂等键，防 agent retry 重复计数
- **accept 写协议**（中，正确性——化解半事务）：`choose accept` 幂等键 =`(rid, card_id, accept)`；meal_log 与 feedback_store 两写**都带这个键且各自幂等**（已有该键则跳过）；`choose` 整体可重跑——部分失败（一写成一写败）后重跑只补缺的那写，不靠回滚。`skip` 同理（仅 feedback_store）
- **跨进程锁**（低）：单用户低频几乎撞不上；唯一真实向量 = web 台 + CLI 同时写同一顿，罕见。沿用 `trace_store` 已有 flock 模式即可，不为它加重工程
- 与 **B-001 worktree 撞 `feedback_store`**：加固与 B-001 协调，本 worktree 落地后 rebase

"统一成一个 AI-friendly append-only ledger"的愿景 → 折进 **F-014**（反馈闭包）/ Phase 1，不在 Phase 0。

## 7. 状态/历史边界（与反馈 worktree 分工）

- 本 worktree ledger 记 **推荐 + 选择（accept/skip）**
- **显式评分反馈（好评/差评/不合时宜）+ `历史→蒸馏→profile` 的"越来越理解用户"闭环 = defer**（[F-014]，依赖 B-001 反馈短链路落地）
- 两套 state 暂并存，不强行统一

## 8. 分阶段

- **Phase 0（本 worktree）= Claude Code**：手动关键词触发、pull、同步。**不做定时、不做推送**。`init` 生成 skill，端到端自用一周收 bug
- **Phase 1 = OpenClaw（defer）**：定时触发 + 主动推送 + 飞书等渠道交互 + 页面"样式"；形式化 `openapi.yaml` / `manifest.json` 给陌生 agent 自动发现也在这阶段
- 砍老 brief 的 launchd 双轨 fallback——自用手动不需要

## 9. 交互层（Layer 2，adapter 特定）

协议层（§3 CLI verbs + §4 `llm_request_spec`）跨 agent 复用；**交互呈现是 adapter 特定的 Layer 2**，住在 `init` 生成的 skill 里，不进协议。换 agent（codex / 其他 TUI / 飞书）= 重写交互层、复用协议层。

Claude Code reference adapter 交互形态：
- **触发**：手动关键词（"今天吃啥" / "中午吃啥"）激活 skill
- **喂输入**：agent 的 LLM 提供当前时间（定 meal + `--at-time`）+ 用户当天 context（自然语言）；context 由 agent LLM parse 成 intent（智能侧）
- **呈现**：用 Claude Code 原生 **AskUserQuestion** 把推荐摆成选项（exploit + explore 两段），用户点选 = `choose`
- **refine = 自由输入**：AskUserQuestion 内置的 "Other / 自由输入" 即 refine 入口；可**多轮**连续 refine（每轮 `start --context "<自由输入>" --from <rid>` 形成新 round，n_explore=0 聚焦）
- **反馈（defer [F-014]）**：触发倾向 piggyback——下次点餐时顺带催上一顿反馈，非显式"要反馈"

接 codex / 其他 TUI：各自的选项 / 输入组件替换 AskUserQuestion，协议层 `start` / `resolve-intent` / `apply-rerank` / `choose` 不变。

## 10. 明确砍掉 / 不做（vs 老 brief，附理由）

| 砍掉 | 理由 |
|---|---|
| async job / poll / webhook | CLI 同步，自用 12–60s 可接受 |
| HTTP localhost auth bearer token | CLI 以志丹身份跑，直接读写本地 |
| launchd 双轨触发 | Phase 1 OpenClaw 定时接管 |
| agent 面 daemon / 常驻 server | one-shot CLI；web 台另有 FastAPI |
| 面向陌生人三件套自动发现 | 自用 `init` 生成即可，形式化推 Phase 1 |
| 新建 JSONL event ledger | 复用现有 3 套 JSON（codex BLOCK） |
| 多 zone / 多 user / stream / multi-turn clarification | Phase 1+ |

这些复杂度全是老 brief 被"推广给陌生 IM-bot 用户"假设撑起来的；D-097 自用定位下坍缩。

## 11. 翻案登记

| 旧决策 | 处理 |
|---|---|
| [D-022]（V1 OpenClaw + 飞书主动推） | 翻：飞书 + 主动推承诺移到 Phase 1 OpenClaw 定时，非 chisha |
| [D-038]（LLM 抽象 Phase 2 callable 注入） | 改：不走 closure 注入，改 agent 的 LLM 执行 `llm_request_spec` |
| [D-051]（Web 优先，飞书降 V1.5） | 部分翻：砍 V1.5 独立通道；Web 长期作算法迭代台 |
| 2026-05-16 v1 + v2-consensus brief | 挪 `archive/`，本 doc 取代 |

关联：[D-097]（自用为主定位）/ [F-013]（CLI 直 import 天然绕开 web_api sandbox 耦合）/ [F-014]（反馈闭包 defer）。

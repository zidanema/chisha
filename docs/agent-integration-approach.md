# 把工具"AI friendly 接入"到别人的 Agent 里 —— chisha 的实践

> **状态**: 草稿 / 待 D-074 正式翻 active. V1.0 工程里程碑收尾后, 这套接入方案仍是 V1.5 之后 (Phase 1 推广启动后) 的目标终态. 实现细节待 D-074 落 active 时同步更新本文.

> 我做"今天吃点啥" (chisha) 时, 花了不少时间思考"怎么让别人的 AI 助手最简单地接入我这个能力"。这份文档讲我的思路、技术方案和踩过的坑, 拿来跟做 Agent 产品的同行交流。

---

## 0. 这是个啥模式: 本质是 CLI + Skill

> **本文范围**: 只讨论 Skill 化接入 (Agent 能跑 shell + 读 markdown 的场景), 不覆盖 SaaS API / webhook 应用 / 浏览器插件 / 平台 tool calling 等其他 Agent 集成形态。

在 Skill 化接入这个范围内, 三种常见模式:

| 模式 | 例子 | 关键特征 |
|---|---|---|
| **平台原生 Skill** | Anthropic Skill (绑 Claude) / Coze 插件 / GPTs / Dify Tool | 用某平台特定的 Skill 格式, 只能在该平台用; 数据 / LLM 通常归平台 |
| **协议化 Skill (MCP)** | MCP server | 用开放协议, 多平台能接; 常见部署形态是本机 stdio 或本机 server (不必然 always-on, 但生命周期由 Agent 管) |
| **CLI + Skill 模式** | **飞书 CLI / chisha** | 一个本地 CLI 工具 + 一组 skill markdown, Agent 调时拉起 CLI 进程, 跑完即退 |

注意三类不是严格互斥, 一个工具可以同时提供多种入口 (e.g. 一个 CLI 也能被 MCP server 包装). 但落到"用户首选接入路径"层面, 三类的工程取舍是不同的。

chisha 选第三种 —— CLI + Skill 模式。这不是我发明的姿势, 已经有成熟参考实现:

**飞书 CLI** 是大厂内部开放给 AI 操作飞书产品的成熟实践 (一个 `lark-cli` 命令行 + 一组 `lark-*` skill markdown 文件, 覆盖 IM / 邮件 / 多维表格 / 文档 / 日历 等近 20 个领域), 验证了这个模式适合**大公司多产品对接 Agent**。chisha 是同一模式的个人产品级应用, 验证了它也适合**个人垂直能力对接 Agent**。

**重要边界**: 飞书 CLI 和 chisha 在"接入形态 / 执行入口"层面是同模式, 但**数据边界不一样**:
- **飞书 CLI**: CLI 跑在用户本地, 但访问的是云端飞书的业务数据 (用 OAuth 授权)
- **chisha**: CLI 跑在用户本地, 业务数据也 100% 在本地 (没有云端业务后端)

这个区分对资深同行很重要 —— "CLI + Skill" 是接入形态的描述, 不等于"数据全本地"。

这个模式的核心三句话:
1. **执行入口是本地 CLI** —— 不是 SaaS, 不是常驻 daemon, Agent 调时才启动, 跑完即退
2. **接入说明是 skill markdown + 机器可读 manifest** —— 给 LLM 读的步骤剧本 + 给程序读的能力清单, 两者配合
3. **数据 / 认证可在本地, 也可经用户授权访问云端** —— chisha 是前者, 飞书 CLI 是后者; 共同点是 Agent 不接触

---

## 1. 端到端故事 (一屏看完)

小张用飞书机器人当个人 AI 助手。整个生命周期长这样:

```
[接入, 一次]
小张 → 飞书机器人: "帮我接入今天吃点啥"
飞书机器人: 读 chisha 的 manifest → pip install → 跟小张聊几轮提取口味
           → 注册 11:30 定时 → 配饭后反馈对话流 → 完成

[每天]
11:30  飞书机器人定时器 → 调 chisha CLI → 拿 3 张推荐卡 → 推飞书 IM
小张选 1 号 → 跳外卖软件下单
13:30  饭后, 飞书机器人问 "今天吃哪个" → 调 chisha 写反馈
```

**chisha 没碰飞书, 也没碰小张 IM**。所有跟用户接触的事都是飞书机器人在做, chisha 只在被调时出推荐 / 写反馈, 跑完即退。

---

## 2. CLI + Skill 模式落地的 6 个工程问题

每个点: 决策 + tradeoff + 关键 artifact。

### 2.1 协议拆成机器可读 + LLM 可读两层

**决策**: 接入协议拆成三份文件:

- `openapi.yaml` —— FastAPI 自动生成的接口规范, 任何工具能消化
- `manifest.json` —— 能力清单 (建议触发时机 / 协议版本 / Agent 需要哪些能力 / 数据认证边界)
- `AGENT_ONBOARDING.md` —— 给 LLM 读的 5 步剧本: 装包 / 提取口味 / 配触发 / 配推送 / 配反馈

前两份是 source of truth, markdown 引用前两者, 不重复描述。

**关键 manifest.json 片段** (示意):
```json
{
  "protocol_version": "1.0",
  "schedules": [
    {"name": "lunch", "cron": "30 10 * * 1-5"},
    {"name": "dinner", "cron": "0 17 * * 1-5"}
  ],
  "required_capabilities": ["shell", "filesystem"],
  "optional_capabilities": ["cron", "im_push"],
  "data_boundary": "local_only"
}
```

**tradeoff**: 比单纯写 README 重, 但避免不同 Agent 对自然语言说明理解漂移。

### 2.2 LLM 调用归 Agent, chisha 不调

**决策**: chisha 跑完前 70% (筛 60 个候选), 把"该调 LLM 干啥"打包成 spec 还给 Agent, Agent 用自己 LLM 调完回灌:

```
Agent → chisha.prepare_rerank(meal, today_context)
chisha → Agent: { recommendation_id, llm_request_spec, candidates_opaque }
Agent 用自己 LLM 调 → 拿 JSON 响应
Agent → chisha.apply_rerank(recommendation_id, llm_response, status)
chisha → Agent: { cards: [3 张推荐] }
```

**llm_request_spec 必含字段**: `protocol_version` / `output_mode` (tool_use / json_schema / text_json) / `messages` / `tools` 或 `json_schema` / `validation_contract` / `fallback_policy` (失败时 chisha 自带 L2 兜底)。

**tradeoff**: 比"chisha 直接调 LLM"协议复杂, 但避开 closure 注入 (要求 Agent 同步暴露 LLM 函数, 异步 / IM / 跨进程 Agent 都做不到, 把 80% Agent 挡在门外)。

### 2.3 状态用 JSONL 事件流水账 + Markdown 视图

**决策**: 本地一份 append-only 事件流水账 + 几份按需重算的可读视图。

```
~/.chisha/events.jsonl         <- source of truth, 所有事件 append 一行
~/.chisha/inbox.md             <- 重算视图, 用户/Agent 可读的推荐 inbox
~/.chisha/feedback_pending.md  <- 重算视图, 待反馈清单
~/.chisha/profile.yaml         <- 用户偏好 (单写者)
~/.chisha/manifest.json        <- 协议契约 (静态)
```

**为什么 Phase 0 选 JSONL 而非 SQLite**: 单用户 + 调试期, JSONL 任何工具 (cat / jq / LLM / 编辑器) 直接打开, 审计快; append + `fcntl.flock` 多写者并发够用。**真撞上重并发 / 跨表事务 / 大数据量, 升级到 SQLite event table 是合理路径, 不是原则真理。**

### 2.4 主动推: 双轨, 但 CLI 永不常驻

**决策**:
- **主路径**: manifest.json 声明 suggested cron, Agent 装 chisha 时把建议时机注册到它自己的调度系统, 到点调 chisha CLI
- **兜底**: `chisha schedule install` 注册本机 launchd, 到点跑 chisha 脚本 append 一条 `trigger_due` event, Agent 来 poll 时取 (默认 `fallback_mode: trigger_only`, 不直接触发推荐, 防双轨互踩)

**关键边界**: chisha CLI 跑完即退, 不是 daemon。launchd 是宿主 OS 调度, 不是 chisha 的常驻进程 —— 这跟 MCP server (生命周期 Agent 管, 通常 stdio / 本机 server) 也不一样。

### 2.5 当天 context 走自然语言

**决策**: 对外只暴露 `today_context_text` 自由文本, chisha 内部用小 LLM 拆解成 hard_constraints / soft_preferences, **Agent 不感知结构化层**。

**tradeoff**:
- Agent 端简单 (任何 Agent 都能把今天状况总结成一句话)
- chisha 内部多一次 LLM 调用 (token 量小)
- 拆解过程必须记 `context_parse_trace` 进 events.jsonl, 否则黑盒, debug 不可控

### 2.6 Onboarding markdown: 给"有 shell + 文件 + 网络权限的 Agent"读

**决策**: AGENT_ONBOARDING.md 是写给 LLM 的指令剧本:
- Step 1 / 2 / 3 步骤化, 每步是动作不是描述
- 每步给可执行 CLI 命令 (`chisha init --agent claude-code`, `chisha doctor`)
- 标明必需 / 可选 / 降级路径
- 不写故事 / 营销话术 (对 LLM 是噪音)

**适用边界 (诚实)**: 这种 onboarding markdown 假设 Agent 有 shell + 文件系统 + 网络访问能力。**企业沙箱、移动端 Agent、纯 IDE Agent (无 shell 执行权限) 不适用** —— 这类场景需要 Agent 框架方自己包一层适配, chisha 不直接覆盖。manifest.json 的 `required_capabilities` 字段帮 Agent 自检是否能跑。

**markdown 不是可靠集成协议**: 真正的接入契约是 `openapi.yaml` + `manifest.json`, markdown 只是把这两份机器可读 spec 翻译成 LLM 能直接照做的剧本。

---

## 3. 三种模式深入对比

回到 §0 提到的三种模式, 详细对比:

| 维度 | 平台原生 Skill | 协议化 Skill (MCP) | **CLI + Skill (chisha / 飞书 CLI)** |
|---|---|---|---|
| 数据边界 | 通常归平台 | 看 MCP server 实现 | 由用户授权的本地或云端账号控制 (chisha 全本地; 飞书 CLI 本地访问云端飞书数据) |
| LLM 谁出 | 平台 | 看 server 实现 | 用户的 AI 助手 |
| 厂家是否要部署 | 用户跑在平台里 | 看 server 实现 (stdio / 本机 / 远程) | 不要常驻, 用户跑 CLI 即起即退 |
| 跨 Agent 通用性 | 只在该平台 | 多平台 (要支持 MCP 协议) | 多平台 (Agent 能跑 shell + 读 markdown 就行) |
| 接入门槛 | 装个 skill | 装 + 启动 MCP server | 装 CLI + 读 skill markdown |
| 业务离线 | 看平台 | 部分能 | 本地步骤能跑; 依赖云端 LLM / 业务数据的步骤不可离线 |
| 升级演进 | 跟平台节奏 | 协议版本协商 | 自己控制 CLI / skill 版本 |
| **安全 / 认证** | 平台账号体系 | server 自己处理 (本机 stdio 通常无 auth) | CLI 用本机文件系统权限 + 本地 token; 跨主机访问需自己加 (e.g. chisha 用 bearer token + localhost) |
| **调试体验** | 受平台限制 (看不到中间状态) | 受 server 实现限制 | 极好 —— shell 直接复现 CLI 调用, 流水账 cat 直接看 |
| **典型失败模式** | 平台 API 限流 / skill 不在白名单 | daemon 没启 / 协议版本不兼容 / 进程崩溃 | CLI path 错 / env 变量缺失 / Agent 无 shell 权限 / 文件锁竞争 |

chisha 选最右那栏 (CLI + Skill 模式), 理由:

- 我是开发者自用, 不想给自己整个云端运维
- 用户数据敏感 (饮食偏好), 全本地最干净
- 想对"有 shell + 文件访问权限的 AI 助手"开放, 不绑死任何家的 Skill 格式或协议 (企业沙箱 / 移动端 / 纯 IDE Agent 不在覆盖范围)
- 飞书 CLI 已经验证这模式可行, 不用再造概念

什么情况下其他模式更合适:

- 用户数据完全可托管在云端 + 不在乎平台绑定 → 平台原生 Skill 更省事
- 接入需要重业务逻辑必须常驻 (维护长期 session / 监听外部事件流) → MCP server 更合适
- 业务本身就是某平台的产品 (GitHub MCP / Notion MCP), 用户主要用某一家 Agent → 平台原生 Skill 接入更原生

CLI + Skill 不是万能解, 但满足"本地化 + 跨 Agent + 不常驻"这三个约束时, 是最干净的选择。

---

## 4. 没解决的事 (诚实, 区分 Phase 0 暂缓 vs Phase 1 必补)

列下这套设计的硬工程缺口, 标明当前处理策略。

**Phase 0 (自用阶段) 明确暂缓**:
- **数据地理性**: 推荐依赖本地餐厅库, 跨城市要重新采数据。现在只覆盖深圳科技园周围。Phase 1 前要定义"数据包契约 + 缺数据失败提示", 但数据采集本身仍压后 (未来想让"数据采集本身也是个 AI 任务", 用户让 Agent 帮忙采)。
- **新用户首装无 Agent 体验**: 用户刚装但还没接通 Agent 时, 主动推会失效。Phase 0 接受此 tradeoff —— 目标用户都有 Agent。Phase 1 推广前重评估。
- **多 Agent 并发写**: 同时挂两个 Agent 都写 profile / 反馈。Phase 0 单写者约定 (events.jsonl append-only + fcntl.flock 已经保 event 流水账并发安全; profile.yaml 单写者), 真撞了再补显式锁。

**Phase 1 必须补齐**:
- **本地接口安全**: localhost ≠ 安全边界, 本机任意进程可读写。最低要求: bearer token (`~/.chisha/credentials`) + FastAPI middleware 校验 + origin 限制。
- **幂等与重试**: 所有 mutating 端点 (`start_recommendation` / `apply_rerank` / `accept` / `submit_feedback`) 必须有幂等键, 否则 Agent retry 会制造重复推荐 / 重复反馈。
- **流水账损坏 / 截断恢复**: events.jsonl 异常关机 / 磁盘满 / 部分写时怎么恢复; 视图重算的容错策略。
- **Agent 能力探测失败降级**: manifest 声明 required_capabilities, Agent 自检不满足时清晰报错 + 给出降级路径 (e.g. 没 cron 时改 manual trigger)。
- **协议版本演进**: 现在留了 `protocol_version` 扩展位, 但正式的 deprecation 流程 (新老协议共存窗口 / Agent 自检最低支持版本) 没定。Phase 1 必须正式化。

---

## 5. CLI + Skill 模式的 5 个原则

把"CLI + Skill 模式"的设计哲学抽成 5 条:

1. **协议拆两层** —— `openapi.yaml` + `manifest.json` 是机器可读 source of truth, `AGENT_ONBOARDING.md` 是 LLM 可读的步骤剧本, 引用前者
2. **是能力, 不是服务** —— 用户机器上跑, CLI 即起即退, 不部署任何东西
3. **不抢 LLM 选择权** —— chisha 不直接调 LLM, 把 `llm_request_spec` (含 protocol_version / output_mode / validation / fallback_policy) 打包给 Agent, Agent 用自己 LLM 调完回灌
4. **状态本地化, 流水账 + 重算视图** —— `events.jsonl` 是 source of truth, Markdown 视图按需重算, 删了能恢复
5. **触发权给 Agent, 兜底用本机调度** —— manifest 声明 suggested cron, 本机 launchd fallback 只 trigger_only 不直接执行

这 5 条对照下 §0 三种模式: 平台原生 Skill 违反第 1/2/3 条; 纯 MCP 模式下 server 生命周期由 Agent 宿主管理, 跟第 2 条 "CLI 即起即退 + 触发用本机调度" 的设计不兼容 (MCP 适合长 session / 事件流, 不适合"到点跑一次"型触发)。

**适用边界**: 满足"本地化执行 + 跨 Agent + 不常驻 + Agent 有 shell 权限"四个约束时, CLI + Skill 是最干净的选择。约束不满足时, 其他模式可能更合适, 这套不是万能解。

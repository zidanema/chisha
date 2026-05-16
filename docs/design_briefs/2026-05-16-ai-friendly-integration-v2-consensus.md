# AI-Friendly 接入终态 v2 共识版

**日期**: 2026-05-16
**状态**: Opus + Codex 两轮辩论后收敛的共识版, **替代 v1 思路稿** ([v1 brief](2026-05-16-ai-friendly-integration.md) 保留作历史)
**作用**: 给志丹拍板的最终设计稿, 拍板后落 D-074 翻案 D-022/D-038/D-051

---

## 0. 共识链路回顾

| 轮次 | 角色 | 产出 |
|---|---|---|
| Round 0 | Opus + 志丹 5 轮讨论 | v1 brief (路线 S + prompt-out/result-in + AGENT_ONBOARDING.md) |
| Round 1 | Codex 尖锐挑战 | 9 项强反对 + 9 项盲点; verdict "v1 不能直接落地" |
| Round 2 | Opus 消化 + Codex 系统判决 | 修正版 8 段设计 + 5 项硬盲点解决方案 |
| **本文** | 两 model 共识 | **本版本**, 待志丹拍板 |

---

## 1. 核心叙事 (不变)

- **路线 S = AI-friendly Skill**: chisha 是被宿主 Agent 调用的能力体, 不是独立产品
- **不部署 / 不运维 / 不接触用户数据** (D-001 原则, **边界澄清**: 指云端 SaaS, 不指用户本机 cron / launchd)
- **推广目标**: 用户对自己 Agent 说一句话 → Agent 自动装 chisha + 接通 → 主动推 3 选 1
- **Web SPA 不砍**: 转为算法层 + reference UI, 协议层 (event/protocol) Web 和 Agent 共享

---

## 2. v1 → v2 的 6 项关键升级 (来自 Codex Round 1)

| v1 | v2 升级 | 关键反对来源 |
|---|---|---|
| "prompt-out / result-in 纯数据契约" | **machine-readable `llm_request_spec`** (含 tool_use/json_schema mode 选择 + validation + fallback_policy + version) | Codex A1: prompt 文本不是协议 |
| "完全无状态, state_token 嵌入候选" | **No cloud state, local durable OK**; stable `recommendation_id` + event ledger; token 只放 opaque uuid | Codex A3/A4: 偷换 stateless 概念 |
| "AGENT_ONBOARDING.md 给 LLM 读自动接入" | **三件套 + reference adapter**: openapi.yaml / manifest.json 是 source of truth; markdown 是引用; CLI (`chisha init --agent <type>`) 生成 adapter artifact | Codex A5/B7: zero-shot 不现实 |
| "Agent cron pull, chisha 完全被动" | **双轨**: Agent pull primary + 本机 launchd fallback (默认只 append `trigger_due` event, 不直接执行) | Codex A6/B3: 单轨保不住主动推承诺 |
| "12-60s 同步调用" | **异步 job 模型**: `start_recommendation → job_id → poll_result/webhook`; job state 进同一 event ledger | Codex C8: IM 同步会超时 |
| "今天发烧自然语言走 refine" | **对外只暴露 `today_context_text`, chisha 内部 LLM 拆解 + 记 `context_parse_trace`** (Agent 不感知结构化层) | Codex A7 + 我的反驳 |

---

## 3. 修正版核心设计 (8 段, 已收敛)

### 3.1 协议: machine-readable `llm_request_spec`

```
chisha → Agent (prepare_rerank response):
{
  recommendation_id: <uuid>,
  protocol_version: "1.0",
  candidate_schema_version: "1.0",
  llm_request_spec: {
    output_mode: "tool_use" | "json_schema" | "text_json",   // ← Codex MODIFY: 显式枚举
    messages, system,
    tools[],          // output_mode=tool_use 时必需
    json_schema,      // output_mode=json_schema 时必需
    required_validation,
    fallback_policy: "chisha_l2"
  },
  candidates_opaque: <sealed blob, chisha 自解>,
  expires_at: ISO8601
}

Agent → chisha (apply_rerank):
{
  recommendation_id,
  llm_response,
  status: ok | validation_failed | provider_failed | timeout | tool_unsupported | fallback_used
}

chisha → Agent (final):
{
  recommendation_id,
  cards: [{card_id, restaurant, dish, reason, ...}],   // stable card_id 用于后续反馈
  fallback_applied: bool,
  rerank_status: ok | fallback_l2
}
```

**Agent 端复杂度上升的代价**: 不能再宣称 "一行 import 就能接", 但 reference adapter (Phase 0 Claude Code) 把这部分封装好, Agent 实际接入仍接近 "一句话" 体验。

### 3.2 状态模型: local-first durable state

- **术语统一**: 禁止说 "stateless", 统一叫 **local-first durable state**
- **Event ledger 是 source of truth**, 派生表 (pending queue / job cache / due triggers) 可重建
- 多用户 namespace 延后 Phase 1 引入

### 3.3 反馈生命周期: 统一事件状态机

替代 v1 的 "多个独立 API 语义孤岛":

```
recommendation_started
  → recommendation_ready
  → push_succeeded | push_failed
  → accepted | skipped | no_response
  → feedback_submitted
  (旁路: manual_log_meal — 用户没 accept 但实际吃了)
```

- 所有事件 append 进同一 event ledger
- `list_pending_feedback()` / `list_due_triggers()` 是 reducer view, 不是独立表
- stable identifiers: `recommendation_id` → `card_id` (accept 后生成) → `meal_event_id` (反馈链路全挂这个 id)

### 3.4 触发: 双轨 — fallback 锁 trigger_only (志丹拍板)

- **Primary**: Agent 自己的 cron, 到点调 `start_recommendation`
- **Fallback**: `chisha schedule install` 注册本机 launchd
  - **锁 `fallback_mode: trigger_only`** — 只 append `trigger_due` event, 不直接执行
  - Agent poll `list_due_triggers` → 自己决定是否触发
  - **不做 `execute` mode** — chisha 完全不做推送, 严守 D-001 边界
- manifest.json 显式声明 `fallback_mode = trigger_only`, 避免 Agent + launchd 双重触发

**已知 tradeoff**: 故事 C (新用户首装还没接 Agent) 体验为 0, 流失风险存在。**接受**, 推广目标用户为 AI Agent 高级用户, 必有 IM bot Agent, 不属于故事 C 场景。Phase 1 推广前再评估。

### 3.5 当日 context

- 对外只暴露自然语言 `today_context_text`
- chisha 内部小 LLM 拆解 → hard_constraints / soft_preferences (**不暴露给 Agent**)
- **新增**: `context_parse_trace` 记录解析过程 (Codex MODIFY, debug 必需)
- hard constraint 只在 **高置信** 时进 L1/L2 过滤, 否则只进 L3 prompt

### 3.6 Onboarding 三件套 + Reference Adapter

**Source of truth (机器读)**:
- `openapi.yaml` — FastAPI auto-gen, 13 端点契约
- `manifest.json` — cron 建议时机 / 反馈生命周期 / capability requirements / `protocol_version` / `fallback_mode`

**人 + LLM 双读 (引用前两者, 不重复)**:
- `AGENT_ONBOARDING.md` — 步骤剧本

**Generated artifact (CLI)**:
- `chisha init --agent claude-code` → 生成 Claude Code 专用 `CLAUDE.md` / skill markdown / 本机命令 wrapper
- `chisha doctor` — 检查注册状态 / capability fitness / 版本兼容
- `chisha schedule install [--execute]` — 装本机 launchd

**Phase 0 reference adapter**: Claude Code skill, 端到端跑通自用一周。**Claude Code markdown 是 generated artifact, 不是协议层**。

### 3.7 Latency: 异步 job, 进同一 ledger

- `start_recommendation(meal, today_context_text)` → 立即返回 `job_id`
- `job_id = recommendation_id` (Phase 0 简化), retry 是同一 job 的新 events (`rerank_retry_started`)
- `poll_result(job_id)` 从 reducer view 读, 不查独立 job store
- 兼容同步 mode (短延迟 / fallback_l2 时一次性返回)

### 3.8 Surface 边界: Web vs Agent

| 层 | 归属 |
|---|---|
| **Layer 1 (shared domain events)**: refine 文本 / accept lock card / skip / feedback / `submit_refine(recommendation_id, text)` 生成新 round | 进 protocol, Web 和 Agent 共用 |
| **Layer 2 (interaction UI)**: progressive form 动画 / modal 弹出方式 / 面包屑视觉 / chip 渲染 | Web-only, Agent 通道各自设计 |

---

## 4. 5 项硬约束 (Codex Round 2 提出, 已接受)

### 4.1 Storage: JSONL event ledger + Markdown view + YAML/JSON 混合 (志丹拍板, 替代 Codex 的 SQLite 推荐)

**理由**: SQLite 违背 AI-friendly 哲学 (Agent / 人 / LLM 不能直接 cat / grep)。

**方案**:
| 文件 | 格式 | 用途 | 写并发 |
|---|---|---|---|
| `~/.chisha/events.jsonl` | JSONL | Source of truth, append-only event ledger | append + `fcntl.flock` |
| `~/.chisha/inbox.md` | Markdown | 用户可读推荐 inbox, reducer 生成 | 重建 |
| `~/.chisha/feedback_pending.md` | Markdown | 用户可读待反馈清单, reducer 生成 | 重建 |
| `~/.chisha/profile.yaml` | YAML | 已有, 用户偏好 | 单写者 |
| `~/.chisha/manifest.json` | JSON | 协议契约 (cron / capability / version) | 静态 |

**关键**: JSONL append-only 单行原子, fcntl.flock 保多写者安全; Markdown view 是 reducer 派生, 不是 source of truth, 删了能从 events.jsonl 重建。

### 4.2 Idempotency contract
- 所有 mutating API (`start_recommendation` / `apply_rerank` / `accept_recommendation` / `submit_feedback`) 必须有**幂等键**
- 不解决会让 Agent retry 直接制造重复推荐 / 重复反馈

### 4.3 Local API auth
- localhost ≠ 安全边界, 任意本机进程可读
- **最低要求**: 固定 bearer token (写 `~/.chisha/credentials`) + FastAPI middleware 验证 + origin 限制

### 4.4 Protocol/schema version 兼容策略
- `protocol_version` / `candidate_schema_version` / `event_schema_version` 必须有 **deprecation 规则**
- 不解决 manifest/openapi 只是静态文档, 升级必然破坏旧 adapter
- Phase 0 先定 v1.0 + 留扩展位, deprecation 流程 Phase 1 完善

### 4.5 Scheduler ownership 语义
- `manifest.json` 显式声明 `fallback_mode: trigger_only | execute`
- 默认 `trigger_only`, 避免双轨互踩
- `chisha doctor` 检测 Agent + launchd 同时 active 时给 warning

---

## 5. Phase 切分

### Phase 0 (现在 → Step 2 完成后切)
- 实现协议核心 (3.1 / 3.2 / 3.3 / 3.7)
- 实现 manifest.json + openapi.yaml (3.6)
- 实现 `chisha init --agent claude-code` + `chisha doctor` + `chisha schedule install`
- 实现 Claude Code reference adapter, 自用一周
- SQLite 迁移 (4.1)
- Local auth (4.3)
- Idempotency 基础 (4.2)
- 极薄飞书 adapter (markdown + localhost deeplink) 作为 reference adapter 一部分, 不单做 V1.5
- **Web SPA 继续作为算法层迭代台**, 共用 Layer 1 protocol

### Phase 1 (推广前必做)
- Stream output + multi-turn clarification 进协议 (3.1 扩展)
- Multi-user namespace (3.2 扩展)
- `zone_package_contract` 定义 (schema + 自检 + 缺数据失败提示, 但**数据采集本身仍压后**)
- 第二个 reference adapter (OpenClaw / Cursor 之一)
- Protocol deprecation 流程 (4.4 完善)

### 永远不做 / 压后
- 数据采集本身 (chisha-collector 是 sister project)
- 云端服务 / SaaS
- 强约束 Agent 必须用某家 LLM

---

## 6. 翻案预告 (D-074 草稿)

| 旧决策 | 翻案 |
|---|---|
| **D-022** (V1 接入 OpenClaw + 飞书卡片, 主动推送) | 整体翻 — 飞书归入 Phase 0 reference adapter 极薄部分; 主动推承诺通过双轨触发 (3.4) 实现 |
| **D-038** (LLM 抽象 Phase 2 callable 注入) | 改方向 — 不走 closure, 改 `llm_request_spec` machine-readable 契约 (3.1) |
| **D-051** (Web 优先, 飞书降级 V1.5) | 部分翻 — 砍 V1.5 独立通道; Web 长期保留作算法层迭代台 + Layer 1 protocol consumer |

---

## 7. P1 / P2 拍板结果 (志丹 2026-05-16)

**P1. Storage 选型**: 拍板 **JSONL event ledger + Markdown view + YAML/JSON 混合**, 不用 SQLite (违背 AI-friendly 哲学)。详见 §4.1。

**P2. Fallback scheduler 默认 mode**: 拍板 **`trigger_only`**, 不做 `execute` mode 兜底。chisha 完全不做推送, 严守 D-001 边界。故事 C 流失风险接受, 推广目标用户均有 IM Agent。详见 §3.4。

---

## 8. Phase 0 落地清单 (Step 2 自用一周完成后启动)

按依赖关系排序:

1. JSONL event ledger + Markdown reducer view + fcntl.flock (4.1) — 阻塞后续
2. Idempotency + local auth (4.2 / 4.3) — 协议基础
3. Event state machine + reducer views (3.3) — 反馈链路重构
4. `llm_request_spec` + apply_rerank async (3.1 / 3.7) — 协议核心
5. manifest.json + openapi.yaml + `chisha doctor` (3.6) — onboarding 基础
6. `chisha init --agent claude-code` + Claude Code reference adapter — 端到端
7. `chisha schedule install` + 双轨触发 (3.4) — 主动推承诺
8. 极薄飞书 adapter (push markdown + deeplink) — 推送通道 reference
9. 自用一周 → 收 bug → 评估 Phase 1 启动

**不在 Phase 0**: 通用 protocol / 多 zone / 多 Agent / stream / multi-turn / multi-user / 第二个 reference adapter

---

## 9. 共识签字

- **Opus**: 同意 8 段设计 + 5 项硬约束 + Phase 切分
- **Codex (Round 2)**: 提出 8 段 YES/MODIFY 判决 + 5 项硬盲点解决方案
- **志丹** (2026-05-16): 拍板 P1 (JSONL + Markdown 混合, 不用 SQLite) + P2 (trigger_only, 不做 execute 兜底); v2 共识版正式生效, 待 Phase 0 Step 2 完成后落 D-074 翻案

---

**文档物理位置**: `docs/design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md`
**v1 历史 brief**: `docs/design_briefs/2026-05-16-ai-friendly-integration.md`
**Codex 第一轮辩论 transcript**: 上一轮 chat (Section A / B / C / D)
**Codex 第二轮辩论 transcript**: 本轮 chat (YES/MODIFY + 5 项盲点)

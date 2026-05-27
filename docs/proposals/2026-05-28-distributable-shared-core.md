# 提案: 可分发的共享核心 — chisha 从单用户工具到"类 feishu-cli 可分发物"

> 状态: **志丹拍板入库, 分步落地中** (2026-05-28)。Opus + 志丹 多轮收敛 → Codex 架构 review 两轮: 一轮过 5 大支柱; 二轮复核**确认 5 支柱忠实** + 提 3 个分歧 (#1 Step1 0-diff 范围 / #2 meal_log 归属 vs sandbox / #3 版本分层), 经核码后**三项全部以澄清收敛**。已入 `docs/decisions.md` D-102 系列。
> **落地进度**: ✅ **Step 1 焊大脑 (D-102.1, 2026-05-28)** — FallbackPlan 统一兜底契约 + 根治 meal_log drift, Codex 设计+commit 双触点, pytest 1155 pass + baseline 0-diff。⏳ Step 2 root 拆分 / Step 3 分发 待做。
> 关系: 重新激活 ROADMAP **Phase 1 (同方法论同事推广)** 的工程主线 (D-097 当时降级为"随缘", 现志丹把分发拉回主目标)。不推翻 D-097 的"自用为主"心态, 而是把"真要推广时回看恢复"的那一刻落地。

## 目标 (志丹拍板)

1. **可分发**: 给同事 agent (Claude Code / Codex) 一段话 → 装成 skill → skill 能 `update` (更新数据 + 推荐方法论)。
2. **无服务端**: 引擎/数据/方法论 = 志丹统一维护的**版本化静态发布物**; 个人数据 (profile / 吃了啥 / 反馈) 存**同事本地**, 永不上服务器。
3. **保留 web-app 壳**: 可独立部署 (此时自配 LLM), 但仅作**志丹自用的可视化调试/体验**, 不为"没有 agent 的人"当产品维护。
4. **关键约束**: web / cli-skill / 其它 agent 只是**接入形态不同**, 底层核心引擎 (数据层 / 推荐方法论 / 召回 / 打分 / 校验 / 兜底) **必须共用同一套**。

## 驱动发现: "共享同一引擎" 现在是假的 (病根)

Codex review 实锤 (已核实): 两入口的"大脑"已经在兜底路径漂移——

- web / 进程内路径: `fallback_rerank(..., meal_log=meal_log, ...)` (`rerank.py:1525`) → explore 段会避开最近吃过的菜。
- CLI agent 路径: `fallback_rerank(persisted_top_k, ...)` (`agent_cli.py:473`) **漏传 meal_log** → explore 段丢失"避开最近吃过"的 novelty 偏置。

严重度本身低 (只影响兜底的 explore 2 张卡), 但它**证明了根因**: 两形态靠"手工把状态穿进各自的调用"而非"核心拥有并打包状态", 所以必然漂移。这是整个重构要根治的第一性问题——**分发的卖点就是"同一套验证过的引擎", 带着这个不一致发出去会直接砸信任** (Faithful Refine 第一原则: 信任是唯一来源)。

## 核心架构 (Opus + Codex 共识, 已锁定)

### A. 执行边界: 核心只产 plan, 不拥有"执行" (Codex Q1 → 选 b)

核心 (recall / score / build prompt / validate / fallback / data / methodology) 输出一个**完整、可序列化、可回放**的三件套, 执行完全交给 adapter:

- `PromptPlan` — 给 LLM 的 system + messages + tools/schema (web 和 cli 同一份, 已是单源: `prompts/rerank_system.md` + `select_top_candidates`)。
- `ValidationSpec` — 回传的确定性校验点 (已单源: `_map_validated_candidates` `rerank.py:1606`)。
- `FallbackPlan` — **必须封装其判定所需的全部状态** (meal_log / 候选集 / 策略 / version)。这是根治 meal_log drift 的关键: 状态由核心打包, adapter 想漏都漏不掉。
  - **meal_log 归属澄清** (Codex 二轮 #2 → 共识, 非拍板): 权威库仍住 state_root, **由 `data_root` 单点解析路径** (含 sandbox namespace 路由, `data_root.py` 已是收口点)。核心建 FallbackPlan 时向 data_root 要"已解析的 meal_log", 读出后打包成**只读快照**。对齐 D-098 `trace.__frozen` 既有范式 (单次构建、冻结、零 runtime re-read) — 时光机重跑用快照即自包含、可复现; 要换 meal_log 状态 = 起新一轮、不是重跑。sandbox 路由是 data_root 的职责, 与 plan contract 正交。

adapter 只负责"谁执行 LLM": web adapter = 进程内同步调; cli adapter = emit `llm_request_spec` 给宿主、接回传。**核心不含 sync/async/emit 概念**, 不抽 `Executor` 接口 (会逼核心同时抽象"现在执行"和"交宿主将来执行", 语义不干净 + async 生命周期坑)。
- 反方最强论据 (Codex): 若未来大量多轮 tool-loop / 重试 / 增量校验, `Executor` 能省 adapter 状态机重复。当前无此复杂度, 不先付抽象成本。

### B. Root 拆分: install / state 二分, sandbox 是 state 的 namespace (Codex Q2)

- `install_root` = 引擎 + 只读数据 (restaurants/dishes) + 方法论 (methodologies/*.yaml) + prompts。**update 时整体覆盖**。
- `state_root` = profile / 历史 / 反馈 / logs / 迁移记录 / cache。**update 永不碰**。
- **sandbox (D-077 时光机) = state 下的 namespace**, 不是第三个根: `state_root/sandboxes/<id>/logs/...`。time-travel 只切 state namespace, 不复制 install。避免 install×state×sandbox 三维笛卡尔积。

**state_root 落地位置 = `~/.chisha/`** (host-agnostic), 不是 skill 文件夹下, 也不是 `~/.claude/plugins/data/`:

| 理由 | 说明 |
|------|------|
| 活过 update | 分发型 skill 走 plugin, 装 `~/.claude/plugins/cache/<plugin>/<version>/`, update **整体替换版本目录** → co-locate 的个人数据会被覆盖 (官方确认无"子目录 update 不碰"的保证)。 |
| 一人一份 | 个人数据是**按用户**, 一台机可同时有全局 + 项目级 skill → co-locate 会让历史碎成 N 份。 |
| 跨入口共享 | Claude Code skill / Codex / web-app 三入口要读写**同一本历史**。`~/.chisha/` 谁都能平等读写; `~/.claude/plugins/data/` 把状态锁死 Claude Code 宿主, 违背"协议层跨 agent 共享"设计。 |
| 零权限 | 写 home 下 dotfolder 无需 sudo, **不触发 macOS TCC** (TCC 只管 Documents/Desktop/Downloads 等, 不管 home dotfolder)。 |

> LKB (living knowledge base) 类 skill 把数据放 skill 文件夹下成立, 是因为它们**自著、不从上游 update** → 无覆盖风险。chisha 是**分发+可 update**, 判据相反。

### C. 分发 / update: 静态产物 + compat manifest + doctor 闸门 (Codex Q3)

- 最小产物 = 版本化只读数据 bundle + **机器可读 `manifest.json`**: 至少 `artifact_version` / `data_schema_version` / `min_engine_version` (或 supported range) / **capability flags** (如 stable-id、tagging)。
- 引擎启动 + `doctor` 先读 manifest, **不兼容 hard-fail, 绝不"尽力解析"** (对齐 D-100 fail-loud / 无 grandfather)。
- **关键: 别用单调 version**, 用 capability flags 区分"可兼容小更新" vs "破坏性 schema 变更" (D-099/D-101 这类走 capability gate 发布, 旧引擎对新产物 hard-fail + 给升级动作)。
- **版本分层澄清** (Codex 二轮 #3 → 共识, 非拍板): manifest 的 `data_schema_version` + capability flags **只管"数据产物 ↔ 引擎"这一条分发边界**; 不取代既有的内部层版本, 各管各的边界:

  | 版本号 | 管的边界 | 谁拥有 |
  |--------|----------|--------|
  | `PROTOCOL_VERSION` | cli verbs / llm_request_spec 信封 (宿主 agent ↔ chisha) | agent_protocol |
  | `candidate_schema_version` | 回传候选结构 (LLM 产出 ↔ 校验) | rerank/agent_protocol |
  | `TRACE_SCHEMA_VERSION` | trace 落盘结构 (持久化 ↔ debug/sandbox 回放) | trace_store |
  | manifest `data_schema_version` + capability flags | **本期新增**: 只读数据产物 ↔ 引擎 | manifest.json (志丹发布) |

  capability flags 由**发布产物的人 (志丹) 在 manifest 里声明**, 引擎在启动/doctor 时读并比对自己的 `min_engine_version` / 支持的 capability 集合。引擎不"猜"产物能力。
- `doctor` 扩成: 引擎↔产物兼容 / state 迁移状态 / 只读 bundle 完整性 / state_root 可写 / sandbox namespace 可用。
- **Claude Code 端 update 载体 = 打包成 plugin 走 marketplace** (同事 `/plugin install` 一次, 之后自动 update)。git pull 可作**内部试用 transport**, **不是 update 架构**。

### D. 接入形态 (Codex Q4 + 志丹拍板)

- **web-app**: 保留为薄壳, 共享同一核心引擎, **禁止 web 独占任何业务逻辑** (防再次旁路)。仅志丹自用调试/体验, 不为非 agent 用户做功能、不当产品维护。
- **Codex 接入**: 协议层 (CLI verbs + spec) **全复用**; 仅交互层 (SKILL.md 里"摆候选给用户选"那步) 写个变体——Claude Code 用 AskUserQuestion, Codex 改成"列编号选项 + 用户回数字/自由输入"。**改一份 markdown, 不碰引擎。** 唯一要实测: Codex 跨轮透传 `recommendation_id` + JSON 信封不出错。
- **OpenClaw 推迟**: 本期只做 Claude Code + Codex。`integrations/openclaw/` 已存在 (非从零), 但接口未细设计, 下一步再做。验收标准: 能否承载"统一 plan + 本地 state_root + compat doctor"。

## 分步计划 (Codex 换序, 志丹同意: 先焊大脑、再搬文件)

> 志丹原倾向"先做 root 拆分"; Codex 挑战并被采纳: root 拆的是路径边界, 碰不到 meal_log 执行边界漂移 → 先 plan-contract 焊死"共享引擎"不变式, 否则 root 拆完只是把错误边界搬个地方, 且会把不一致发给同事。

### Step 1 · 焊大脑 (统一 plan contract) — 最高优先, 低风险

- 抽 `PromptPlan / ValidationSpec / FallbackPlan`, 把 web 进程内路径与 cli spec 路径收到**同一可信源**; `FallbackPlan` 携带 meal_log 等全部状态。
- 回归测试盖住 meal_log fallback drift (cli 兜底 explore 段必须与 web 一致)。
- **0-diff 适用范围澄清** (Codex 二轮 #1 → 共识, 非拍板): 这是**行为保持的提取重构**——`baseline_l2_snapshot` 0-diff **只担保 web 主路径不变**; cli 兜底路径**本就要变** (补回 meal_log, 即 drift 修复), 由**新增 cli/web fallback 一致性测试**守门, 不归 0-diff 网。别期望 cli fallback 也 0-diff, 否则会把 bug fix 当 regression 误杀。
- 守门: `baseline_l2_snapshot` 0-diff (web 主路径) + 新增 cli/web fallback 一致性测试 (cli 兜底补 meal_log)。
- 无路径迁移, 风险最低; 完成即建立"共享引擎"硬不变式。

### Step 2 · 搬文件 (root 拆分 → ~/.chisha/)

- `data_root.py` (唯一收口点) 拆 `install_root` / `state_root`; state_root 默认 `~/.chisha/` (可 env 覆盖, 测试/多 worktree 隔离用)。
- sandbox 收进 `state_root/sandboxes/<id>/`。
- **重分类坑 (必处理)**: 现 `data/feedback_history.jsonl` + `data/long_term_prefs.json` 住在 `data/` 下但属**用户状态**, 必须迁出到 state_root, 否则 update 覆盖 install 会抹掉同事长期偏好/反馈历史。
- 守门: 7 落盘点全部走 state_root; 只读数据走 install_root; baseline 0-diff。

### Step 3 · 分发 / update (manifest + doctor + plugin 打包)

- 数据发成版本化 bundle + `manifest.json`; doctor 扩 compat 闸门; Claude Code 端打包 plugin。
- 先用共享 git repo / 内部 transport 验流程, 再决定 marketplace。

## 已知坑 + 结构性风险 (Codex Q5 + Opus 补)

1. **data/ 重分类** (Step 2): feedback_history / long_term_prefs 是 state 不是 install。
2. **并发写 ~/.chisha/**: cli + web 同时写 (如同时记录点餐) → 历史/反馈互相覆盖。个人自用概率低; 上文件锁 (`agent_round_store.lock_round` 已有先例)。
3. **state 迁移失败 / 回滚**: 本地升级中断 → 用户数据不可逆。需备份/事务策略 (接 D-099 `migrate_stable_ids` 经验: ingest 前快照)。
4. **隐私脱敏**: doctor / sandbox logs / bug report 会带 profile / 历史 / 反馈 → 默认脱敏。
5. **可复现性断裂**: 推荐依赖 引擎ver + 产物ver + state 快照 + LLM 结果, 缺一就解释不了历史推荐 → trace 需记全四者。
6. **本地信任边界**: 数据/方法论 update 能改推荐行为, 产物需来源 + 完整性校验。具体签名方案**后议** (本期不定型)。

## 触及的 high-risk 文件 (改前走 Codex 双触点)

`data_root` / `rerank` / `recall` / `score` / `refine` / `agent_cli` / `agent_protocol` / `agent_round_store` — 按 CLAUDE.md 红线: 设计敲定前 + commit 前各拉一次 Codex review。

## 本期范围红线 (不做, 防 scope creep)

- OpenClaw 接入 (下一步)。
- 第二份 methodology spec / L1 cuisine token 扩 (同事 cuisine 才分散, 推迟到真多人)。
- screener 设计 (3-5 熟人一句话判断即可)。
- 产物签名/完整性体系**定型** (本期只留位, 不实现完整签名链)。
- 为"没有 agent 的人"给 web-app 做产品功能。

## 待定 (需志丹拍板)

**当前无强制拍板项。** Codex 二轮 3 个分歧均以工程澄清收敛 (已内联进 §A meal_log 归属 / §C 版本分层 / Step1 0-diff 范围), 不改变 5 大支柱。

剩 3 个**本期不定型、留待落地中再回看**的开放项 (非阻塞, 志丹可现在拍也可推到对应 Step):
1. **产物来源/完整性签名方案** (§已知坑 6): 本期只留 manifest 位, 不实现签名链。真要发给办公室外的人时再定 (GPG / sigstore / 简单 sha256+HTTPS 三档)。
2. **并发写 ~/.chisha/ 的锁粒度** (§已知坑 2): 复用 `agent_round_store.lock_round` 先例即可, 但 cli+web 同时记点餐的概率/代价由志丹判要不要现在就上文件锁, 还是 Step 2 落地时按实测加。
3. **marketplace vs 内部 transport 的切换时机** (Step 3): 先共享 git repo 验流程已共识; 何时正式上 Claude Code marketplace = 看几个同事试用反馈, 志丹届时拍。

## 定稿决策草案 (落地时入 decisions.md, 当前为 D-102 系列预留)

- **D-102** 可分发共享核心: 核心产 plan 三件套、不拥有执行; install/state root 二分、state→~/.chisha/、sandbox 为 state namespace; 分发=静态产物+capability manifest+doctor 闸门、Claude Code 走 plugin; web 降为自用薄壳; 分步先焊大脑再搬文件。(细分 D-102.x 落地时按实际拆)

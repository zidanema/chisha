# BACKLOG · 待办池

> 收"已知但当前不解决"的 bug / feature / idea。判别原则:
> - 触发架构决策 → 挪 [decisions.md](decisions.md) 拿 D-XXX (≤ 15 行/条)
> - 进入实施期 → 挪 [ROADMAP.md](ROADMAP.md) 对应 Phase
> - 已实施细节 → 不再单独写 IMPL_LOG, git log + grep 代码即权威
> - 决定不做 → 挪 [ROADMAP.md](ROADMAP.md) "已砍清单" 并标关联 D-XXX
>
> **本文档不是决策日志**。条目可以模糊、可以悬而未决。半年没动的 idea 主动砍掉, 不要养着。

编号约定:
- `B-NNN` bug · `F-NNN` feature · `I-NNN` idea
- 编号本桶内顺序, 不与 D-XXX 联动
- 状态: `open` / `wip` / `dropped` / `promoted-to-D-NNN`

---

## Bugs

> 已知但当前不修的 bug。明确触发条件 + 优先级 + 绕过方法。

### B-002 · 3 个测试依赖本机环境 (无 claude 登录 / 跨平台挂)

- **来源**: 2026-05-29 首次加 GitHub Actions CI 跑全量 pytest, 干净 runner 暴露 (本地一直绿因本机 claude 已登录 + macOS). CI commit 已 revert (38d751b), 押后到测试健壮性专项。
- **状态**: open
- **现象**: 干净环境 (无 claude CLI 登录态 / 非 macOS) 跑 pytest 挂 3 个:
  - `test_claude_code_cli.py::test_call_includes_all_required_flags` — `_patch_cli_available` 只 mock `_check_cli`, 漏 `call()` 内 `shutil.which("claude")` → None 进 cmd[0] → TypeError
  - `test_rerank.py::test_rerank_trace_includes_tool_schema_reference` — cli 分支 `is_available()` probe `claude auth status` firstParty, 无登录 → config_error → KeyError `system_prompt_full`
  - `test_d079_pr1_golden.py::test_recommend_meal_golden_snapshot` — golden snapshot 跨平台漂移 (`use_llm_rerank=False` 纯确定性, 与 claude **无关**; 根因未定: 浮点 / 排序 tie-break / locale, 需拉 CI 完整 diff)
- **影响**: 没登录 claude 的 contributor clone 后本地 pytest 挂 test1/3; CI 无法引入
- **方案预案**: test1/3 mock 掉 claude probe (`which` + `is_available`) 让测试自包含; test2 先拉 CI diff 定位漂移字段。修完重引入 CI (dummy-key 方案已验证 1258 pass, ci.yml 见 revert `d4c2180` diff)
- **不修原因**: 独立于发布清理 scope; test2 跨平台根因未知深度

---

## Features

> 已识别但暂不做的功能。多数对应 ROADMAP Phase 1+。

### F-001 · L1 词表扩 cuisine 偏好 token

- **来源**: [CLAUDE.md](../CLAUDE.md) 推荐链路红线 + [D-076.1](archive/DECISIONS_phase0.md#d-0761-l1-词表加-positive-方向-boost-spicy--sweet_sauce) 边界
- **状态**: open, 排到 Phase 1
- **What**: 当前 L1 词表只有 8 token (low_oil/wetness/spicy/sweet_sauce × boost/penalty)。扩 cuisine 偏好 (川/粤/日料/湘菜...) 让 L1 抽取能稳定承接长期 cuisine 倾向, 不只靠 refine 一次性表达
- **约束**: 需独立决策 + baseline_l2_snapshot 守门; cuisine token enum 要和 recall.py / score.py 现有 cuisine 字段对齐
- **优先级**: P2 (Phase 1 同事推广前做, 因为同事的 cuisine 倾向比志丹自己分散)
- **与 Refine v2 关系**: 互补。Refine v2 (D-081) 让 refine 一次性表达的 cuisine 被忠实兑现; F-001 让 cuisine 倾向能跨 session 沉淀进 L1 长期。两条独立。

### F-002 · data zone 拆包

- **来源**: [CLAUDE.md](../CLAUDE.md) Phase 1 列表 + [D-030](archive/DECISIONS_phase0.md#d-030)
- **状态**: open, 排到 Phase 1
- **What**: 把数据采集 / 清洗 / 打标 / 保鲜独立成 `chisha-collector` sister project (D-027 已立项但未拆), V1 后做
- **优先级**: P2

### F-003 · screener 设计

- **来源**: [CLAUDE.md](../CLAUDE.md) Phase 1 列表
- **状态**: 降级 (D-097, 2026-05-25): 自用为主不做正式 screener — 3-5 熟人一句话判断"有没有饮食原则"即可; 触发=规模化 (开源 / N>>10) 再做
- **What**: 同事推广时需要一个"是否适合用 chisha"的筛子 (目标缺失型 vs 原则派, [D-070](archive/DECISIONS_phase0.md#d-070-产品定位收敛到原则派点餐助手--三层信号模型-v1) 边界)
- **优先级**: P2

### F-004 · 第二份 methodology spec

- **来源**: [CLAUDE.md](../CLAUDE.md) Phase 1 列表 + [D-072](archive/DECISIONS_phase0.md#d-072-methodology-spec-抽象-放-phase-0-收尾-v1)
- **状态**: open, 排到 Phase 1
- **What**: 当前只有 `harvard_plate.yaml`。需要第二份 (增肌高蛋白 / 糖控 / 孕期 / 控盐...) 来验证 spec 抽象是否真正解耦了打分逻辑
- **约束**: 不允许借机改 score.py 逻辑或调权重 (D-072 边界)
- **优先级**: P1 (验证抽象的关键)

### F-006 · eater_context (替别人点餐场景)

- **来源**: 2026-05-18 Codex v2 review Refine v2 蓝图时挑出
- **状态**: open, 排到 V2
- **What**: 当用户替别人 (老人 / 小孩) 点餐时, refine 表达不应自动套用 owner 的 L0 (C 类) 解除权限。schema 需加 `eater_context` 字段标识此次餐对象
- **约束**: Phase 0 单用户场景风险可接受, 不在 Refine v2 (D-080~D-085) 范围
- **优先级**: P3 (多用户场景出现时再做)

### F-007 · Refine 高级 slot 扩展 (occasion / avoid_pattern / exploration_boost)

- **来源**: Refine v2 brief §12 标记的未来扩展
- **状态**: open, 待真实数据验证
- **What**: 三类 LLM 解析 slot:
  - `occasion`: "见客户" / "孩子也吃" / "和朋友 AA" → 改 brand_tier / 分量 / 辣度
  - `reference.relation: avoid_pattern`: "不要像那次那样" → reference 的 negative 版
  - `exploration_boost`: "随便" / "都行" / "你看着办" → 主动放手时让 ε-greedy 加大
- **触发条件**: D-081 eval set 跑出 miss 率 > 20% 再加
- **优先级**: P3

### F-011 · food_form_avoid 数据打标 + L1 硬过滤

- **来源**: 2026-05-21 D-094 scope audit 拆出
- **状态**: open (收窄), 等下个数据轮次启动
- **What**: D-094.1 (2026-05-24) 已加 `staple_want/avoid` 走 recall 硬过滤, 覆盖**粗粒度**主食排除 (面/米饭/粥, canonical_name 子串 + grain_type 守门防"面包"误命中). F-011 收窄为**细粒度形态** (面条 vs 米粉 vs 拉面 vs 饼 — staple_avoid 子串区分不了) 仍需 food_form 数据字段. dish 数据层当前**无 `food_form`** (audit 0/11123). 数据轮次到时: (1) dish 打标 `food_form` (面条/米粉/饼/...) (2) schema 加回 `food_form_avoid` (3) L1 硬过滤命中
- **依赖**: data 打标工作流 (LLM 批量打标 dishes_tagged.json + 人工抽检)
- **优先级**: P2 (下次数据轮次)

### F-012 · rerank 多 cache breakpoint (5min 连续 refine 链路提速)

- **来源**: 2026-05-21 prompt 优化 Step 3 续 brief 项 B, codex 共商 SHIP 但志丹砍
- **状态**: open, 暂不做 (ROI 不足)
- **What**: rerank `build_user_message` 在 [PROFILE] 段尾加第 2 个 ephemeral cache breakpoint, 让 5min TTL 内连续 refine 链路 (refine→refine→refine 不带 L1 抽取重算) input_tokens 再省 ~2k cache_read. 详见 `docs/proposals/archive/2026-05-21-prompt-step3-cache-and-examples.md`
- **砍的原因**: (1) 工程量 ~9h + 3 个 high-risk 文件 (llm_client.py / anthropic_api.py / openrouter.py + rerank.py 改 build_user_message), (2) 真命中窗口窄 — 仅"5min TTL 内连续 refine 且后台 L1 抽取没触发", codex Q-B2 警告 "PROFILE 一天内不变" 不成立, (3) 单用户日常 refine 频率不高, 长尾场景
- **触发重做条件**: Phase 1 推广有真用户连续 refine 数据 / refine latency 还要再压 / Anthropic 计费成本成为瓶颈
- **优先级**: P3 (长尾)

### F-013 · Living/Lab router 后端拆分 (架构债)

- **来源**: 2026-05-25 D-097 定位 review, 从 ROADMAP "Phase 1 必收口" 降级
- **状态**: open (降级, 自用为主下不做)
- **What**: `web_api.py` 里生产推荐路由与 sandbox/虚拟时钟逻辑物理耦合 (242 处 sandbox 提及, 每个 prod handler 挂 `Depends(_with_sandbox_sid)`). 拆成独立 Living router + Lab router, 让沙箱实验不可能污染生产推荐
- **现有兜底**: D-077 fail-loud 护栏 (非 default sid + sandbox disabled → 409) + 操作纪律 (验收完 disable); 自用场景低风险
- **触发重做**: 沙箱真污染过一次生产 / 正式推广同事 (同事不懂操作纪律, 护栏不够须物理隔离)
- **耦合点**: AI-friendly 接入 (D-074) 若也走 web_api 会把 sandbox 耦合传导给外部 agent — 做 D-074 时确认协议层是否绕开 web_api sandbox 路由
- **优先级**: P3 (自用) / P1 (推广前)

### F-014 · 反馈/理解闭环的 AI-friendly 接入 (依赖反馈 worktree)

- **来源**: 2026-05-25 D-074 AI-friendly 设计讨论, 志丹拍板 #3 (本部分本 worktree 不做)
- **状态**: open, 依赖已解除 (反馈短链路 D-098 已落地; 此条专做 AI-friendly 接入侧)
- **What**: D-074 Phase 0 本 worktree 的 event ledger 只记 **推荐 + 选择 (accept/skip)**, 不碰 **显式评分反馈** + `ledger → 蒸馏 → profile` 的"越来越理解用户"闭环。反馈短链路 (`feedback_signal.py`, D-098) 已落地, 单独设计这部分如何 AI-friendly 接入个人 agent:
  - agent 如何把显式反馈 (好评/差评/不合时宜) 记进 chisha (CLI `feedback` 命令?)
  - **反馈触发 UX (志丹倾向)**: piggyback — 下次点餐时 skill 查"已 accept 但没反馈"的上顿, 用 AskUserQuestion 顺带问"上顿吃得咋样", 而非要用户显式说"要反馈" (摩擦高没人主动)。本 worktree 已记 accept (带 stable card_id) 给这个铺好地基
  - chisha 零 LLM 前提下, 反馈→profile 蒸馏由谁的 LLM 做 / 何时触发 (Claude Code 手动 vs OpenClaw 定时)
  - agent-side event ledger 与 web 的 `feedback_store` 是否统一 (暂并存, 不强行合)
- **依赖**: chisha 零 LLM 决策 (D-074)
- **优先级**: P1 (自用留存关键, 但有依赖顺序, 排在 D-074 Phase 0 之后)

### F-015 · cuisine 多样性冷却 (连吃同一菜系降权/轮换)

- **来源**: 2026-05-25 D-098 反馈短链路残留 (b) 拆出 — 志丹澄清原口误"香菜"实为"湘菜", 定性从"配料数据缺口 (F-011)"翻转为"菜系多样性"
- **状态**: open, 推广前做
- **What**: 连续吃/推同一菜系 (如湘菜) 无任何冷却。现状 `diversity_filter` 只有餐厅级 (7天) + 蛋白级 (3天), 无 cuisine 维度; cuisine 仅有数量 cap (每菜系 top6, D-043) 非时间冷却
- **数据**: **不卡** — `cuisine` 字段全量打标 (湘/川/粤/日料… 14+ 类), 区别于香菜走的 [F-011](#f-011) (food_form 0/11123 数据缺口)
- **方案预案** (codex 共商再定): `diversity_filter` 加 `no_same_cuisine_within_days` (与现有两维同构) + `meal_log` 落盘补 `cuisine` 字段 (当前只记蛋白类) + 可选 `score.py` cuisine recency 软降权。硬 cooldown vs 软降权 / 衰减天数 / 与 D-073 子类多样化的边界待定
- **依赖**: 碰 recall/score high-risk 文件, 改前 codex 共商 + baseline_l2_snapshot 守门
- **优先级**: P2 (推广前)

### F-016 · 重构债 (审计轮2 识别)

- **来源**: 2026-05-30 全仓审计轮2 (过时内容 + 死代码清理同轮副产), 识别 47 项重构候选 (1 high / 22 med / 25 low)
- **状态**: **部分完成** (2026-05-30 重核+分批落地, 见 git log "F-016")。已落: 安全批 (scripts/loader 长函数+去重) + 白名单批 refine/_resolve_zone 单源/status_bar 统一/agent_cli 去重+拆/manifest 工厂/feedback_signal 抽取 (各过 baseline_l2 0-diff + codex review)。重核剔除 2 项已死 (审计快照 stale)。
- **判断 skip** (非真重复/净负, 不做): data_root 路径函数 (rich docstring 工厂化会抹) / sandbox default-sid (4 处消息各异 + lazy import 疑似破环) / tag_via_api 验证器合并 (strict vs partial 两套语义) / refresh_from_collector.main (分阶段 early-return 退出码, 抽 helper 反增间接性)
- **剩余 (后续单独做)**: ① long-function defer — `rerank._run_llm_rerank` (~338行, baseline 守不住 L3 质量) / `web_api._rollback_session_impl` (~240行) / `agent_cli.cmd_doctor` (ok+notes 与子检查紧耦合); ② `trace_store` v2-meta 三处去重 + `list_traces_v3` 拆 (源 key "source"/"__source" 不一, 需保 debug-ui meta 契约); ③ `l1_extractor.aggregate_inputs` (137行 6 pass + 嵌套闭包); ④ `recall.build_combos_for_restaurant` 8 层深嵌套 (喂打分链路, 须最小步 + 每步 baseline); ⑤ `#12` atomic write 跨 6 模块统一 chisha/atomic_io.py (codex: 单独成批, 碰 web_api); ⑥ debug_recommend trace 簇 (dim_stats 四处 → trace_helpers / build_l2_trace / 长函数, 碰 api/debug_what_if); ⑦ **前端 16 项** (web/debug-ui/sandbox-lab, 阻于 chrome-devtools MCP 未连接, 须浏览器自测)
- **约束**: 剩余多碰 high-risk 白名单 (rerank/web_api/trace_store/recall/api), 需 codex 共商 + baseline_l2_snapshot 守门; 前端须 chrome-devtools 自测
- **优先级**: P3 (可读性债, 非功能, 自用不阻塞)

---

## Ideas

> 未验证 ROI 的想法。优先级最低。

_(待填)_

---

## 流转记录

> 条目挪走 / 砍掉 / 升级的历史见 git log (本项目纪律: changelog 不写文档)。

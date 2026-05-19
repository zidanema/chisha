# chisha · 活决策日志

> 主读者：你（志丹）。Coding agent 偶尔 grep。
> 维护纪律见 [CONTRIBUTING_DOCS.md](CONTRIBUTING_DOCS.md)：目标 3-5 行/条，> 15 行就是塞实施，停下。
> Phase 0 历史决策全量归档在 [archive/DECISIONS_phase0.md](archive/DECISIONS_phase0.md)（不再维护，需考古时查）。

## 索引

**产品定位 / 形态**: [D-001](#d-001) · [D-051](#d-051) · [D-070](#d-070) · [D-021](#d-021)
**数据层**: [D-002+D-030](#d-002--d-030) · [D-008](#d-008) · [D-037](#d-037)
**推荐链路架构**: [D-005](#d-005) · [D-041](#d-041--d-006--d-040) · [D-043](#d-043--d-042--d-044--d-0441--d-045) · [D-046](#d-046) · [D-035+D-047A](#d-035--d-047a) · [D-049](#d-049) · [D-050](#d-050) · [D-038+D-047B+D-048](#d-038--d-047b--d-048)
**Profile / 学习**: [D-025](#d-025) · [D-026](#d-026) · [D-014](#d-014)
**Context / Mood**: [D-034](#d-034) · [D-071](#d-071) · [D-015](#d-015)
**方法论 (L0)**: [D-023](#d-023) · [D-072+D-072.1](#d-072--d-0721)
**反馈系统**: [D-063+D-064+D-065](#d-063--d-064--d-065) · [D-066+D-067](#d-066--d-067)
**工具 / 调试**: [D-039](#d-039) · [D-075](#d-075) · [D-079](#d-079) · [D-028](#d-028)
**Refine 重做**: [D-073+D-073.1](#d-073--d-0731)（推翻 D-071） · [D-080](#d-080) · [D-081](#d-081) · [D-084](#d-084)
**L1 真兑现**: [D-076+D-076.1](#d-076--d-0761) · [D-077](#d-077) · [D-078](#d-078)
**Refine v2 / Faithful Refine**: [D-080](#d-080) · [D-081](#d-081) · [D-082](#d-082) · [D-083](#d-083) · [D-084](#d-084) · [D-085](#d-085)
**Agent 接入 (草稿)**: [D-074](#d-074)

---

## D-001
**V1 走开源 Skill 形态，不做 SaaS。** (2026-05-10)
数据本地、用户在自己 Agent 里组合工具是 Agent 时代的合理形态。SaaS 化要等用户量级与运营回报支撑。

## D-021
**项目双名：今天吃点啥（对人）/ chisha（对机器）。** (2026-05-14)
中文名给用户读，代码名 ASCII safe 给包名 / import / CLI。

## D-051
**V1 主交互 = 本机 Web SPA，飞书延后到 V1.5 做推送 + deeplink。** (2026-05-15)
用户视图 + 调试台合一在 React SPA 里，能让"调推荐"和"用产品"在同一界面同步推进。原 D-022 的飞书卡片形态降级为通道，不做主交互。

## D-002 + D-030
**数据层和推荐层独立分发；V1 阶段数据链路不重构。** (D-002 2026-05-10 · D-030 2026-05-11)
- 数据按 office_zone 拆子包（`chisha-data-shenzhen-bay/...`），推荐方法论作为单仓 Skill
- collector / cleaning / data_service 拆分推迟到 Phase 1+（V1 自用阶段重构 ROI 低）
- 原 D-027 sister project 方向已被 D-030 推翻

## D-008
**打标 LLM 必须看到价格。** (2026-05-12)
价格直接影响油量 / 份量 / 性价比判断。砍价格省 token 是假节省，会让打标在客单价分布不同的店产生系统偏差。

## D-037
**生产打标默认 = deepseek-v4-flash（via OpenRouter）。** (2026-05-12)
Opus 太贵；打标对推理强度需求低，便宜模型 hold 住，golden 准确率持平。想换模型时查这条的 cost/quality 权衡。
评测方法 = 双模型独立标交叉对比（Opus + Codex GPT-5.4，171 条 golden，原 D-036 合并入此条），详见 [memory: dual_model_audit_pattern] + `eval/dish_tagging_eval/`。

## D-005
**推荐三阶段：L1 召回（宽过滤）→ L2 打分（16 维 + cap）→ L3 精排（LLM tool_use + 写理由）。** (2026-05-11)
层间职责严格分离，任何重构得守。详细职责在 [CONTRACTS.md](CONTRACTS.md)。

## D-041 + D-006 + D-040
**召回硬过滤双层：`hard_max_*` 真硬过滤（超就砍），`prefer_max_*` 软偏好（进 L2 打分）。combo 生成数量由 profile.recall 显式注入。** (D-006 2026-05-12 · D-040/041 2026-05-12)
- 召回阶段只做真红线，所有软约束进打分；防过早扼杀
- combo (2/3/4 道) 由 profile 列出，不在代码 hardcode

## D-043 + D-042 + D-044 + D-044.1 + D-045
**L2 打分：16 维 + 4 层 cap（restaurant/brand/cuisine/food_form）+ 不可补偿惩罚（unforgivable_discount）。profile 分两层：口味偏好 vs 健康目标，wetness 作 session mood 不进 baseline 权重。** (2026-05-13 ~ 2026-05-15)
- 16 维详细看 `chisha/score.py` 和 methodology spec
- brand cap 防同连锁不同分店刷屏
- 口味偏好（spicy/sweet）和健康目标（low_oil/protein_min）分两层，防把"为健康妥协的选择"误读成"真口味"
- wetness（想喝汤）是当下心情，不是稳定 trait

## D-046
**L3 输入 top60。** (2026-05-14)
top40 候选不足（同 brand 限 2 后多样性不够），top100 token 爆。60 是甜点。改输入大小前先重做这个权衡。
（"必须用 60" 的硬约束在 CONTRACTS。）

## D-035 + D-047A
**L3 输出契约 = tool_use forced schema，opus 主路径默认。** (D-035 2026-05-11 · D-047A 2026-05-14)
- tool_use vs json_mode：17/18 vs 11/18 稳定性差异，必须用 tool_use
- 重排和写理由必须一次调用产出（防理由 ↔ 选择不对应）
- opus 主路径分发要质量；CLI 路径走 sonnet effort=low 利用自用 Max 订阅免费额度
- validator 失败必须 fallback 到规则路径

## D-049
**L2 → L3 输入契约 = head-only。brand cap=2 真正生效在 L2，不在 L3 prompt。** (2026-05-14)
- `apply_caps()` 只返回 head 段，不再保留 tail 段
- L3 prompt 不需要写"输入里可能含多变体，请择优"，因为输入侧已经只剩 ≤ 2 个同品牌变体
- V1 简化路径同步砍掉，V2 是唯一推荐链路（推翻 D-024）

## D-050
**L3 容错走 validator + 一次性 retry + 规则 fallback，不动不动重跑。** (2026-05-15)
CLI 路径成本敏感（按 token 走自用 Max 订阅额度），多次重试比"承认 LLM 不行走规则"更亏。
（具体次数和 fallback 调用顺序在 CONTRACTS。）

## D-038 + D-047B + D-048
**LLM 调用层抽 provider（anthropic / openrouter / claude_code_cli），双路径分流，config_error 必须 hard-fail。** (D-038 2026-05-12 · D-047B/D-048 2026-05-14)
- provider 由 `profile.yaml llm.provider` 或 `CHISHA_LLM_PROVIDER` env 切换，auto 模式按 ANTHROPIC > CLI > OR 优先级
- CLI provider 不支持 tool_use，rerank 层做分流：API 走 tool_use，CLI 走 prompt+JSON 解析
- config_error 必须 hard-fail，**不能被外层 except 吞成普通 fallback**，否则用户以为在跑 L3 实际没跑
- Phase 2 外部 Agent 接入待 D-074 草稿落定后翻案

## D-025
**personal_offsets 粒度 = `(cuisine, cooking, ingredient)`，不是"店::菜"。** (2026-05-11)
单菜粒度太稀疏 + 没法复用到没吃过的店。聚合到口味 / 烹饪 / 主材三维，能从"宫保鸡丁不爱"泛化到"川菜辣 + 干煸类不爱"。

## D-026
**learned_profile 用统计聚合（分位数/比例/黑名单），不用 LLM 蒸馏。** (2026-05-11，取代 D-012)
LLM 蒸馏在小样本上有偏 + 难复现 + 慢。LLM 可以在 prompt 里读统计结果，但不能作为 source of truth。

## D-014
**`profile.taste_description` 用自然语言，不结构化拆字段。** (2026-05-13)
LLM 能直接消费自然语言，结构化会丢上下文（"不太辣但能吃微辣" vs `spice_tolerance: 2`）。结构化字段只在打分阶段需要的硬维度上用（如 oil_level / protein_g）。

## D-034
**Context 注入层（DESIGN 原四层缺的第 5 层）。** (2026-05-11)
L1 召回之前注入"当前时间 / 天气 / 上一餐 / 今日剩余预算"等 session-level 事实。防 LLM 推断错（如把午餐推断成早餐）。

## D-071
**不让用户主动选 mood（mood picker 删）。新心情维度走 refine 文本或 L3 prompt，绝不在前端加 chip。** (2026-05-15)
- 用户每次都得选 mood = 摩擦；选了又不准 = 误导信号
- `infer_refine_mood` 只服务 `want_soup` 关键词识别，不许扩为通用 mood parser（单测有 8 case 守门）

## D-015
**探索机制默认启用：top 5 保留 1-2 个 explore，不让 personal_offsets 完全主导。** (2026-05-13)
防偏好闭环（爱吃辣 → 全推辣 → 反馈仍辣 → 越推越辣）。refine 路径下 explore 关闭（用户已主动给方向）。

## D-023
**餐盘策略改弱约束三件套：控油 + 至少 1 道蔬菜 + 蛋白下限。** (2026-05-11)
严格 1/2-1/4-1/4 哈佛餐盘在中式外卖现实下不可达。优化目标是"可持续采纳"，不是"营养精确"。

## D-072 + D-072.1
**L0 方法论（哈佛餐盘 / 减脂 / 糖控）抽 yaml spec。改 spec 前后必跑 baseline_l2_snapshot + compare_traces，top60 顺序 + 16 维 breakdown |delta| < 1e-6 才允许 commit。** (2026-05-15)
- spec 是 yaml 化的 `V2_DEFAULT_WEIGHTS`，不是新接口
- **改打分逻辑/调权重/加新维度走 score.py 不走 spec**
- baseline 回归是 Phase B 启动条件（替代原"Step 2 自用一周数据"门槛）

## D-063 + D-064 + D-065
**反馈三类信号：gut（好吃度 -1/0/1）/ calibration（对 prediction 的校准: reason_match, oil_calibration）/ behavior（fullness, repurchase_intent）。E 头部 = gut，4 维展开对齐当时 prediction。schema 不可混。** (2026-05-15)
- 三类信号语义独立，不能混用一个评分体系
- 每个 calibration 维度对齐当时的 L3 prediction，便于回放对比

## D-066 + D-067
**反馈一次提交 = 永久 readonly 不可改；后续走 append-only comments timeline。** (2026-05-15)
- 已提交的 ratings 不能改，否则下游学习不稳定
- 反思 / 补充走 append comments，不污染原始 fact
- comments 可作为 LLM 推理上下文，但不直接进打分

## D-039
**调试台是独立 FastAPI :8765，跟主推荐链路解耦。** (2026-05-13)
改打分链路时调试台必须先反映出来。L1/L2/L3/Final 四段 + 16 维 breakdown + LLM payload 可见 + combo 追溯。不要把调试逻辑混进生产代码。

## D-028
**北极星指标 = 连续采纳率（7d/30d），不是决策时间。** (2026-05-11)
决策时间有数据漂移（用户分心、设备切换）。连续采纳率直接反映"够不够好用以至于愿意每天用"，跟产品成立性挂钩。

## D-070
**定位收敛到原则派点餐助手。** (2026-05-15) · 最核心
- 服务对象 = 已认了一套饮食方法论的人（减脂控油 / 增肌高蛋白 / 糖控 / 孕期）
- 明确不服务"什么都行又什么都不想吃"的目标缺失型用户
- 三层信号模型：**L0 方法论 spec / L1 用户偏好（长期） / L2 session mood**
- 修订 PRD §1 / §3

## D-073 + D-073.1
**refine 走结构化意图（RefineIntent）+ 重召回，让"用户主动表达诉求"真正生效。完全推翻 D-071，部分推翻 D-035 / D-043 P3 在 refine 端的应用。** (2026-05-16)
- 触发：实测"想吃点湖南菜，然后肉多一点"——CHIP_VOCAB 封闭 + chip 死映射 + refine 不重召回，结果完全靠 L3 撞大运
- 拆 parser：`parse_feedback`（餐后，chip 词表稳定）vs `parse_refine_intent`（餐中，开放 schema）。挤一起是病根
- RefineIntent schema 开放（cuisine_want / ingredient_want / flavor_tags / portion / staple / price），LLM 抽不联想
- 链路接入：recall 重做（三桶拼合 + cuisine_avoid 硬过滤）+ L2 加 `intent_match_bonus`（cuisine 0.50 / ingredient 0.20 / flavor 0.10）+ 健康 guardrail 拉低系数 0.4 + spicy 仍由 profile 硬过滤
- refine **不再写 long_term_prefs**：当下意图 ≠ 长期偏好，会污染 D-043 chip 历史
- D-073.1 修 apply_caps 边界：`intent.cuisine_want` 命中菜系免 cuisine/brand/food_form 三层 cap，restaurant cap 保留防同店刷屏

## D-074
**AI-friendly 接入终态共识 = CLI + Skill 模式（草稿，未正式落）。** (2026-05-16, draft)
- 编号已占住，正式条目走 D-074.1+ 修订
- 共识来源：Opus + Codex + 志丹三方收敛，详见 [`docs/design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md`](design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md)
- Phase 2 待 Step 2 自用一周完成后翻案，期间 D-038/D-047B/D-048 的 provider 抽象仍是落地形态

## D-075
**`apps/debug-ui/` 独立 Vite SPA，不并入 `apps/web/`。** (2026-05-16) · 推翻 ROADMAP "调试台 V1 整合到 /debug 路由"
- CSS 视觉系统不同（5 套 oklch palette + 高密度 heatmap）/ 依赖分歧（user 端 Tailwind + router，debug 端均禁）/ 受众不同（用户视图克制 vs 调试自用密集）
- 独立项目仅通过 `/api/*` 联调，backend 只动 `chisha/debug_recommend.py` 两处 ADD 字段，不动 user-view 端
- 老 `chisha/static/debug.html`（D-039）保留双轨过渡，不删
- 端口 5174，proxy `/api → :8765`

## D-076 + D-076.1
**L1 长期反馈层重构 — 砍伪 L1 + LLM 抽取真兑现，词表加 positive boost。** (2026-05-16) · 推翻 D-043 "refine chip → load_runtime_hints"
- 病因：D-070 文档说 L1 已建，实际 `long_term_prefs.py` 是把 refine chip（当下信号）当长期偏好做半衰期统计，**概念错位**；V1.1 反馈 schema 落盘只为回放，没有任何机制汇成长期偏好
- 解法：砍 refine 写 `feedback_history.jsonl`；新增 `chisha/l1_extractor.py` + `chisha/l1_prefs.py` 走 claude_code_cli text + JSON parse/validate/retry；`score.rank_combos` 切到 `load_prefs`；`bootstrap_from_legacy` 兜底一次性脚本
- 词表（Phase 0 边界）：BOOST = `low_oil / wetness / spicy / sweet_sauce`（D-076.1 加后两个，志丹是吃辣 + 重口下饭用户，原词表结构性表达不了正向偏好）；PENALTY = `sweet_sauce / processed_meat / carb_heavy / spicy`；不加 `processed_meat / carb_heavy boost` 违反 harvard_plate baseline
- 验收：真实 LLM 演练 — 4 餐 spicy boost 抽出 + Day 5 LLM reason 显式 "顶格命中追辣 boost"，L1→L2→L3 三层贯通

## D-077
**Sandbox Time-Travel 模式 = user web 一个 mode，行为完全一致 prod，仅时钟 + 数据落盘根隔离。** (2026-05-16)
- 痛点：推荐链路有多层时间累积（cooldown 7d / 3d / snooze / ttl / D-076 L1 抽取），真实日历日推进太慢
- 五条不可动摇原则：① 真实交互优先，不做 CLI 替代 / fixture batch ② 行为完全一致 prod（禁 fake LLM / 跳 cooldown）③ 仅时钟 + 数据落盘根隔离 ④ inspect 端点要看得到沉淀 ⑤ reset 一键回干净
- 实现：`chisha/clock.py` + `chisha/sandbox.py`（state.json + threading.Lock）+ `chisha/data_root.py`（7+ 路径派生）+ `/api/sandbox/*` 6 端点 + 前端 SandboxBar / Inspect Drawer / ProfilePage 入口
- LLM 成本：claude_code_cli + Max 订阅承载 ~21 次/周
- D-编号占用：原 D-074 AI-friendly 草稿没正式落，让位给 sandbox；AI-friendly 改用 D-074 自身 .x 修订

## D-078
**Sandbox 端到端首跑修补 + accept→meal_log 闭环 cooldown（含 D-078.1/.2/.3 三个 followup）。** (2026-05-16) · D-077 sandbox 落地后真实 e2e 暴露
- P0 时钟漏注入：`l1_extractor.aggregate_inputs` 默认 today 用真实 wall clock，feedback ts 用虚拟时钟，沙盒推进永远判"未来"过滤光，based_on_meals 永远=1 卡死。修：透传 root，默认 today=`clock.today(root)`
- P0 llm_client.call 不存在：D-047 改名 call→call_text，L1 没跟上
- P1 meal_log 写入端缺失：`/api/accept` 只写 feedback_store 不写 `meal_log.jsonl`，cooldown 完全失效。修：`append_meal_log_entry` hard-fail（与 record_accept 同等级别，否则一周内重餐厅）
- Codex S2 二轮 review 修补：reset/disable 抢 `_L1_EXTRACTION_LOCK` 防 worker 写盘污染 prod；advance 在 status=pending 时返 409 防 UI bypass
- D-078.1 sandbox path 回归 / D-078.2 L1 → L3 prompt 桥透传 root（refine 二轮也得显式 `root=root`，防多 worktree 跨 root 串数据）/ D-078.3 inspect 同时返 `long_term_prefs`（load_prefs 三态）+ `long_term_prefs_raw`（磁盘直读）
- 验收：真实 5 日演练 — based_on_meals 1→2→3→4，Day 4 LLM 抽出 `boost=["low_oil"]`，Day 12 cooldown 解锁同店

## D-079
**推荐链路 trace 持久化 + Debug 三模式（Replay / What-if / Live）。** (2026-05-16) · 兑现 D-075 deferred `/api/sessions 后端持久化`
- 痛点：`logs/recommend_log.jsonl` 只存 final 5，没 L1 drops / L2 完整 breakdown / L3 LLM payload。差评事后无法回溯；改 weight A/B 时 ctx 也变，不可隔离归因
- 三模式：Replay（读 `logs/recommend_trace/{sid}.json` 默认）/ What-if（冻结 ctx + L1 combos，改下游 weights/rules，默认无 LLM）/ Live（现场全链路，永不写盘）
- 自包含原则：`__frozen` 必须含 `ctx + today + l1_combos + l1_prefs_snapshot + l2_meal_log_view + profile_snapshot`，What-if 严禁任何 runtime read
- 写盘失败仅 warning 不阻断；读盘损坏 fail-closed（备份 `.corrupt.{ts}.bak` 同 D-066/067）；trace size 原拍 300KB 硬上限,实测单 zone ~1.3MB 是常态后改 50MB sanity bound（"调试完整性优先"，志丹决策）
- What-if response 必带 `__llm_called` 字段（默认 use_llm=false，强制透传是否真发了 LLM），`__source` 枚举只 `"production" | "what_if_preview"`，Live 永不写盘
- 后端是单一可信源，前端 localStorage 退为 7 天离线 fallback 永不参与列表合并；不动 L1/L2/L3/Final/Refine/Trace 6 个 panel 组件（what-if 是 overlay）
- 改 trace schema 必 bump `TRACE_SCHEMA_VERSION`；改 score / methodology / spec 仍必跑 baseline_l2 守门（D-072.1 红线）
- Codex 两轮 review 12 finding 全闭环（2 BLOCKER：`__frozen.l1_prefs_snapshot` + `l2_meal_log_view` 漏了 runtime read 漂移；7 FIX-NOW：failure matrix 固化 / `__source` 枚举 / 300→50MB trace size / Live `save-as-replay` 禁；1 push back: localhost 鉴权用 bind 替代端点 token；2 defer: schema upgrade policy + 文件分桶）

## D-080
**第一原则: Faithful Refine — 系统对 refine 文本的理解深度和执行忠实度, 是用户对 chisha 信任的唯一来源。冲突时, 忠实优先于多样性 / 效率 / 探索 / narrative 美观。** (2026-05-18) · 系统宪法
- 用户自用暴露体感问题: refine 自然语言诉求 "没被很好理解和满足" + trace 送 L3 的 combo 凑不满 60
- 根因: 系统把 refine 当 "打分修饰符", 没当 "召回方针重写"
- 这一原则写入 CONTRACTS.md 顶部, 所有改推荐链路的 PR 必须先证明不违反
- 详见 [`docs/design_briefs/2026-05-18-refine-v2-faithful-refine.md`](design_briefs/2026-05-18-refine-v2-faithful-refine.md) §1

## D-081
**refine 多 slot LLM 解析 — 不再 "分类", 意图天然可叠加 (redirect + constrain + reject_previous 同时拍)。** (2026-05-18) · 演进 D-073 RefineIntent
- 新 schema 加: brand_avoid / cooking_method_avoid / food_form_avoid / quality_floor / delivery_only / functional / reference / cuisine_candidates_expanded / ingredient_synonyms / raw_understanding
- 裸 LLM 单点必须带 3 安全带: schema 验证 + 失败降级到空 refine 模式 / trace 双存 (raw + 结构化 + raw_understanding) / 冷启动 eval set 30-50 条
- 失败 case 必须显式告知用户 ("没听懂"), 绝不偷换
- 详见 brief §4

## D-082
**L0 三分判定表取代旧 "硬契约 vs 破戒模式" 二分。** (2026-05-18) · 修正蓝图 v1 自相矛盾
- A 医学风险类 (过敏 / 药物 / 孕期 / 术后 / 小孩过敏): **永不可破**
- B 身份伦理类 (清真 / 素食 / 宗教): **永不可破** (只能 profile 改)
- C 普通健康类 (油 / 糖 / 蔬菜占比 / 价格带 / 减脂): **refine 明确表达可破**
- 副作用: 蓝图 v1 "破戒模式" 独立 feature 取消, 被 L0 三分 + refine 解除 C 类吸收
- 详见 brief §3

## D-083
**methodology 拆两层 — 硬契约下沉 L1 hard_filter, 软偏好留 L2 加权。** (2026-05-18) · 兑现 D-070 "原则派" 承诺
- 当前 bug: 长期方法论 (蔬菜 ≥ 50% / 油上限) 只是 L2 一个权重, 与 popularity 0.4 / variety 0.5 同台 PK → 减脂用户被推炒饭
- 改造: harvard_plate.yaml 健康硬契约从 L2 weight 改为 L1 hard_filter, 不满足直接出局
- 与 D-082 耦合: L0 C 类约束就是要下沉到 L1 的内容
- baseline_l2_snapshot 守门 (D-072.1 红线): 无 refine 路径 0 diff
- 详见 brief §7

## D-084
**refine 模式 L1 召回参数走差异化分支 — 不再与空输入共用一套。** (2026-05-18) · 解决 "L3 凑不满 60"
- per_restaurant_max 3 → 5-8 / 总召回 2-3x / ingredient_want 进 L1 反查 / L3 top_k 保底至少 30 个 intent 命中
- Cap 失败三级回落: 精确 → 同源扩展 → 全集, 每级 UI 显式告知
- L2 权重重平衡: 满足 0.7 / 多样性 0.3 (refine 时)
- 多样性维度 refine 时转纵向 (intent 内部子类, 如湘菜分家常/小炒/腊味)
- 空输入路径行为完全不变 (baseline_l2_snapshot 0 diff)
- 详见 brief §6

## D-085
**narrative + 状态条必须后置 — 链路错时漂亮 narrative 是信任放大器 (Codex 反直觉挑战)。** (2026-05-18) · 实施次序硬约束
- L3 prompt 加 narrative 字段输出 "为什么推这 5 道" + 顶部 always-on 状态条 (当前模式 / refine 命中 L0 过滤时告知)
- 但必须在 D-083 硬契约下沉 + D-084 召回重写**之后**上线, 否则 LLM 会自信编 "为你避开了高油菜" 实际没过滤, 欺骗深、失信代价大
- 字段空洞 (quality_floor / delivery_only / reference) 务实降级: schema 抽出但 L1/L2 不消费, 只透传 L3 prompt + trace 标 `unsupported_in_recall=true`, 不假装做了
- 联动改造 (≠ 无侵入): API 契约 + 前端卡片 + trace schema bump + 旧结果兼容, 至少 4 处
- 详见 brief §5 §8

## D-086
**回滚 main 05-17 D-080~D-085 过渡版, 合并 worktree-recommand-v3 framework 重构版。** (2026-05-18) · 修双路线并行错配
- 根因: worktree 创建时 Claude Code 基于 `origin/main` (落后本地 main 24 commit), 没拉本地 main, 导致双线并行实施同组 D-080~D-085
- 取舍: main D-080/D-081 是过渡版 (B-001 v2 brief 已认定要重做); D-082/D-083 trace + D-085 PR-A router 拆分 + D-085 PR-E lab_summary 全回滚 — debug-ui 动线本就要重设计, router 拆分待 Phase 1 推广前重做
- backlog (main 回滚后仍需后做): B-001 v2 全字段反馈短链路 / Living/Lab router 重拆 / Living API agent-ready 参数化 / debug-ui 动线重设计后再吸收
- tag 备份: archive/main-pre-rollback-2026-05-18 + archive/refine-v2-framework-2026-05-18

## D-087
**Debug 工具台收敛到 Workflow A · 分析 trace (100% read-only) + trace_store v3 (多 round 持久化)。** (2026-05-19) · debug-ui 重构
- Workflow A 是唯一动线: 浏览历史 trace + 比较 refine 轮次, 写入路径 (Live / What-if / Refine submit) 全删 — debug 工具 ≠ 用户视图, 加写入只会污染数据
- trace_store v3 目录布局 `{sid}/meta.json` + `{sid}/rounds/R{n}.json` + 文件锁 `{recommend_trace_dir}/.lock-{sid}` 序列化 append, 解决 refine 多轮 + 并发安全 + 分页读
- 4 个 GET endpoint: `/api/traces`, `/api/trace/{sid}`, `/api/trace/{sid}/round/{rid}`, `/api/intent_schema`; LookupDrawer 反查走前端内存 (零后端调用)
- Intent UI schema-driven: backend `INTENT_SCHEMA` 单一可信源, 前端 fallback `constants/intentSchema.ts`, V2 RefineIntent 扩字段不动 UI 代码
- 详见 brief: docs/design_briefs/2026-05-18-debug-console-workflow-a.md

## D-088
**Debug UI (D-085~D-087) 渲染层 6 bug 修复, refine 流程在调试台从"看不见"变"默认可见"。** (2026-05-19) · debug-ui follow-up
- 根因 1 (B6): `adapter.ts:adaptL3` 把 backend `l3.status=config_error` 硬转 `"skipped"`, 违反 CONTRACTS §39 精神. 修法: `wrapTraceL3` 不再走 skipped 简壳, 始终建完整 BackendL3Llm + `used: l3.used` 真值; PanelL3 callout 直显 `fallback_reason`
- 根因 2 (B1): `App.tsx:activeRound` 硬编码 `"R1"` 不读 `trace.meta.latestRound`, refine 完默认看不到 R2. 修法: useEffect key on `[trace.meta.id, trace.meta.latestRound]` + stale guard 下沉到 `useWaTrace`(success/catch 双路) 防快切 trace race
- 根因 3 (B4): `web_api._attach_feedback_to_meta` 只派生 `type/rank`, TraceBrowser 显示 `+2` 神秘. 修法: 派生加 `restaurant_name`, 前端用 ASCII `★` + 餐厅名截断显示
- 顺手修: RefineTimeline `<div>` 改 `<button>` + `aria-pressed` (B2); stubToRound mock R1 兜底改 zero-state skeleton (B3); useWaTrace 5s 轮询 `/api/traces` (B5)
- 验证: 全 pytest 796 passed (基线 791 + 5 新增 backend test) + chrome-devtools-mcp golden path 全过. spec/plan: `specs/Debug.md` / `plans/Debug.plan.md`

## D-089
**trace 自包含化 + refine 全链路落盘 + R1 L3 fallback bug 修复。** (2026-05-19) · trace 第一原则
- R1 L3 fallback 根因 (S6): `profile.yaml` 配 `openrouter: deepseek/deepseek-v4-flash` 经 Morph 路由不支持 D-047 tool_use 的 structural_tag grammar (Morph 502 "Failed to compile structural_tag grammar"), 整条 R1 L3 无声 fallback 到 L2 ordering. 改回 sonnet-4.6 + openrouter.py 加 None guard 让上游 error message 可读
- 第一原则: trace 是 source of truth — 所有 LLM call 的 `system_prompt_full` / `user_message_full` / `raw_response` body 必须落 trace, 不能事后从 `prompts/*.md` 当前版本重建 (prompt 会迭代, 留 chars 丢 body 等于 trace 无法 replay)
- 新建 `chisha/trace_helpers.py` 集中 4 helper (`normalize_usage_fields` / `serialize_llm_call_trace` / `build_l3_trace_from_collector` / `build_refine_round_payload`) 消灭 L3 / refine round 序列化三份漂移
- refine round 落完整 L1/L2/L3 切片 (refine.py 实际就走完整链路, 不是简化路径) + 新顶层字段 `refine_intent_llm` (意图解析 LLM call 完整 trace)
- 字段命名统一: backend `system_prompt_full` (不用 `system_prompt`), usage Anthropic-style. PanelRefineIntentLLM 新 panel + makeEmptyL3 `"skipped"` → `"no_data"` 区分数据缺失 vs 业务跳过
- 老 trace 归档 `logs/recommend_trace.archived_2026-05-19/` (20 条 fallback 路径污染数据), 不做 backfill 迁移. 验证: pytest 826 全过 (含 16 新增 D-089 测试, baseline_l2 严格不漂) + 新 trace E2E R1+R2 字段完整

## D-090
**L2 refine 信号被淹没 — 提 intent 权重 ×2~×4 + health_guardrail slot-aware 松绑 (phase-1)。** (2026-05-19) · L2 校准
- 根因: R2 trace「湘菜+重口+牛肉鸡肉」L2 top-5 仅 2 家湘菜, 主要靠 L3 硬拉. intent 三维满分合计 0.8 vs 健康罚分四维合计 3.3, 信号被 4 倍音量淹没
- phase-1 改动 (双模型 S1+S2+S3 共创, Codex P0~P2 反馈全收): intent_cuisine 0.5→1.0 / intent_ingredient 0.2→0.5 / intent_flavor 0.1→0.4; health_guardrail(combo, profile, intent=None) 接 intent, heavy flavor_tag → 油触发豁免, 其他 (sweet/processed_meat/wetness) 无 explicit slot 仍照常压制
- 验收 R2 frozen replay: top-5 湘菜数 2→5, top-1 score 3.073→3.683. R1 baseline `compare_traces` top60 + 16 维 |delta| < 1e-6 严格 0 diff
- 守门 `tests/test_l2_refine_snapshot_d090.py` (3 test): 改 score.py 时若 break 必须 D-090.x 修订并更新断言
- phase-2 留账 (不做): low_oil / sweet_sauce / carb_quality / cuisine_preference 通用权重 per-slot L0-C overlay; variety_bonus / context_boost / wetness / distance / 2 floor 死维度清理; intent_cuisine 通道语义重载 (塞了 portion/staple/price)

## D-091
**L2 refine phase-2 — slot-gated 通用健康权重让位 + price_band 语义解耦 + context_boost 清零。** (2026-05-20) · L2 校准 ②
- 触发: D-090 phase-1 留账 3 项, 志丹直接推进 phase-2; 已自扮 self-S2 review (标 self-bias 风险, Codex 用量耗尽), 比 S1 更保守
- 改动 1 (P2-A `_build_refine_weight_overlay`): intent ≠ None 时按 explicit slot 动态调 weight — heavy → low_oil ×0.3 (而非 ×0, 保留 30% safety net) / sweet → sweet_sauce ×0.3 / want_rice 或 want_noodle → carb_quality ×0 / cheap → price ×1.5 (放大对贵菜惩罚) / premium → price ×0 / cuisine_want → cuisine_preference ×0.5
- 改动 2 (P2-B): 删 `intent_match_bonus` 把 price_band 加到 cuisine 通道的逻辑 (历史语义重载), price 维度独立兜底; 更新 `test_intent_match_price_band_no_longer_in_cuisine_channel`
- 改动 3 (P2-C): profile.yaml + V2_DEFAULT_WEIGHTS `context_boost: 0.25→0` (函数 D-073 后恒返 0, cosmetic 死权重清零)
- 验收 R2 frozen replay (前后均含 phase-1 D-090 提权): top-5 湘菜数 5 (保持), top-1 score 3.683→3.255, low_oil breakdown 0.396→0.119, cuisine_pref 0.300→0.150. R1 baseline `compare_traces` 0-diff 严格通过. pytest 830 passed
- 守门测试新增 `tests/test_l2_refine_snapshot_d090.py::test_r2_phase2_heavy_low_oil_weight_reduced` + `test_r2_phase2_cuisine_want_preference_reduced`. 改 overlay mapping 必走 D-091.x + 更新断言
- phase-3 留账 (不做): soup flavor → wetness weight 提升 (对称鼓励); variety_bonus / 2 floor / distance / wetness 死维度清理 (破 16 维 breakdown layout)

## D-092
**L2 死维度清理 — 删 vegetable_floor_pass / protein_floor_pass / distance / wetness / context_boost。** (2026-05-20) · L2 校准 ③
- 触发: D-091 phase-2 留账; 实测 R1 baseline 5 个维度 max|v|=0 且 std=0, 函数行为已死 (L1 已强制 / 外卖没数据 / D-044.1 砍 / D-073 恒返 0)
- 不删 variety_bonus (志丹原列表): 它是连续函数 (≥7 天没吃 → 1.0), 当前 trace std=0 仅因 meal_log 7 天内无命中, 函数本身有意义, 累积后会活跃
- 改动 9 文件: score.py (V2_DEFAULT_WEIGHTS + score_combo parts dict 删 5 keys) / profile.yaml / methodology.py SCHEMA / harvard_plate.yaml spec / adapter.ts DIM_ORDER / compare_traces.py (允许缺失 key 当 0 视为 0-diff) / conftest.py / test_score.py / test_methodology.py / test_score_v2.py / recommend_golden.json (重生成)
- breakdown layout: 19 维 → 14 维 (11 活基础 + 3 intent). 总 score 不变 (5 个删维度都是 0×x=0). 验收: R1 baseline `compare_traces` 0-diff 通过 / R2 frozen snapshot D-090+D-091 全过 / pytest 830 passed
- 函数本身 (vegetable_floor_score / protein_floor_score / distance_penalty / wetness_bonus / context_boost) 保留 — 别处 import 不破坏. 仅从 V2_DEFAULT_WEIGHTS / score_combo parts dict / spec / profile / adapter / 测试断言中移除 keys
- self-S2 review: Codex 用量耗尽时由 Opus 自扮 S2, 检查范围 / 兼容性 / 守门测试; 明早 Codex 恢复后建议补独立审查 (违 dual-model 原则)

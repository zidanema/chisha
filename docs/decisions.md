# chisha · 活决策日志

> 主读者: 你 (志丹). Coding agent 偶尔 grep.
> 维护纪律见 [CONTRIBUTING_DOCS.md](CONTRIBUTING_DOCS.md): 3-5 行/条, 写产品/业务方向, 不写实施.
> Phase 0 历史细节全量归档在 [archive/DECISIONS_phase0.md](archive/DECISIONS_phase0.md).

## 索引

**产品定位 / 形态**: [D-001](#d-001) · [D-021](#d-021) · [D-051](#d-051) · [D-070](#d-070)
**数据层**: [D-002+D-030](#d-002--d-030) · [D-008](#d-008) · [D-037](#d-037) · [D-099~D-099.3](#d-099--d-0991--d-0992--d-0993)
**推荐链路架构**: [D-005](#d-005) · [D-041+D-006+D-040](#d-041--d-006--d-040) · [D-043~D-045](#d-043--d-042--d-044--d-0441--d-045) · [D-046](#d-046) · [D-035+D-047A](#d-035--d-047a) · [D-049](#d-049) · [D-050](#d-050) · [D-038+D-047B+D-048](#d-038--d-047b--d-048)
**Profile / 学习**: [D-025](#d-025) · [D-026](#d-026) · [D-014](#d-014)
**Context / Mood**: [D-034](#d-034) · [D-071](#d-071) · [D-015](#d-015)
**方法论 (L0)**: [D-023](#d-023) · [D-072+D-072.1](#d-072--d-0721)
**反馈系统**: [D-063~D-065](#d-063--d-064--d-065) · [D-066+D-067](#d-066--d-067)
**北极星指标**: [D-028](#d-028)
**Refine 重做**: [D-073+D-073.1](#d-073--d-0731)
**L1 长期反馈层 / Sandbox 形态**: [D-076+D-076.1](#d-076--d-0761) · [D-077](#d-077)
**Refine v2 / Faithful Refine**: [D-080](#d-080) · [D-081](#d-081) · [D-082](#d-082) · [D-083](#d-083) · [D-084](#d-084) · [D-085](#d-085) · [D-094](#d-094)
**L2 信号校准**: [D-090~D-092](#d-090--d-091--d-092)
**LLM 调用基建**: [D-095](#d-095)
**AI-friendly 接入 (active)**: [D-074](#d-074)

> **不在本文件**: 内部工具的工程契约 (debug 台 / sandbox 实现细节 / trace schema / worktree 教训) → [CONTRACTS.md](CONTRACTS.md). 历史 D-039 调试台立项也已迁移过去。

---

## D-001
**V1 走开源 Skill 形态, 不做 SaaS.** (2026-05-10)
数据本地、用户在自己 Agent 里组合工具是 Agent 时代的合理形态. SaaS 化要等用户量级与运营回报支撑.

## D-021
**项目双名: 今天吃点啥 (对人) / chisha (对机器).** (2026-05-14)
中文名给用户读, 代码名 ASCII safe 给包名 / import / CLI.

## D-051
**V1 主交互 = 本机 Web SPA, 飞书延后到 V1.5 做推送 + deeplink.** (2026-05-15)
用户视图 + 调试台合一在 React SPA 里, 能让"调推荐"和"用产品"同步推进. 原 D-022 的飞书卡片形态降级为通道, 不做主交互.

## D-070
**定位收敛到原则派点餐助手.** (2026-05-15) · 最核心
- 服务对象 = 已认了一套饮食方法论的人 (减脂控油 / 增肌高蛋白 / 糖控 / 孕期)
- 明确不服务"什么都行又什么都不想吃"的目标缺失型用户
- 三层信号模型: **L0 方法论 spec / L1 用户偏好 (长期) / L2 session mood**

## D-002 + D-030
**数据层和推荐层独立分发; V1 阶段数据链路不重构.** (2026-05-10 / 2026-05-11)
- 数据按 office_zone 拆子包 (`chisha-data-shenzhen-bay/...`), 推荐方法论作为单仓 Skill
- collector / cleaning / data_service 拆分推迟到 Phase 1+ (V1 自用阶段重构 ROI 低)
- 原 D-027 sister project 方向已被 D-030 推翻

## D-008
**打标 LLM 必须看到价格.** (2026-05-12)
价格直接影响油量 / 份量 / 性价比判断. 砍价格省 token 是假节省, 会让打标在客单价分布不同的店产生系统偏差.

## D-037
**生产打标默认 = deepseek-v4-flash (via OpenRouter).** (2026-05-12)
Opus 太贵; 打标对推理强度需求低, 便宜模型 hold 住, golden 准确率持平.
评测 = 双模型独立交叉对比 (Opus + Codex GPT-5.4, 171 条 golden, 原 D-036 合并), 见 `eval/dish_tagging_eval/`.

## D-005
**推荐三阶段: L1 召回 (宽过滤) → L2 打分 → L3 精排 (LLM tool_use + 写理由).** (2026-05-11)
层间职责严格分离, 任何重构得守. 详细职责在 [CONTRACTS.md](CONTRACTS.md).

## D-041 + D-006 + D-040
**召回硬过滤双层: `hard_max_*` 真硬过滤 (超就砍), `prefer_max_*` 软偏好 (进 L2 打分). combo (2/3/4 道) 由 profile.recall 显式注入.** (2026-05-12)
召回阶段只做真红线, 所有软约束进打分; 防过早扼杀.

## D-043 + D-042 + D-044 + D-044.1 + D-045
**L2 打分: 16 维 + 4 层 cap (restaurant/brand/cuisine/food_form) + 不可补偿惩罚. profile 分两层: 口味偏好 vs 健康目标, wetness 作 session mood 不进 baseline 权重.** (2026-05-13~15)
- 口味偏好 (spicy/sweet) 和健康目标 (low_oil/protein_min) 分两层, 防把"为健康妥协的选择"误读成"真口味"
- wetness (想喝汤) 是当下心情, 不是稳定 trait
- brand cap 防同连锁不同分店刷屏

## D-046
**L3 输入 top60.** (2026-05-14)
top40 多样性不够, top100 token 爆. 60 是甜点. 改输入大小前先重做这个权衡.

## D-035 + D-047A
**L3 输出契约 = tool_use forced schema, opus 主路径默认.** (2026-05-11 / 2026-05-14)
- tool_use vs json_mode: 稳定性差异显著, 必须用 tool_use
- 重排和写理由必须一次调用产出 (防理由 ↔ 选择不对应)
- opus 主路径要质量; CLI 路径走 sonnet effort=low 利用自用 Max 订阅免费额度

## D-049
**L2 → L3 输入契约 = head-only. brand cap=2 真正生效在 L2, 不在 L3 prompt.** (2026-05-14)
`apply_caps()` 只返回 head 段, 不再保留 tail 段. V1 简化路径同步砍, V2 是唯一推荐链路 (推翻 D-024).

## D-050
**L3 容错走 validator + 一次性 retry + 规则 fallback, 不动不动重跑.** (2026-05-15)
CLI 路径成本敏感 (按 token 走自用 Max 额度), 多次重试比"承认 LLM 不行走规则"更亏.

## D-038 + D-047B + D-048
**LLM 调用层抽 provider (anthropic / openrouter / claude_code_cli), 双路径分流, config_error 必须 hard-fail.** (2026-05-12 / 2026-05-14)
- CLI provider 不支持 tool_use, rerank 层做分流: API 走 tool_use, CLI 走 prompt+JSON 解析
- config_error 必须 hard-fail, **不能被外层 except 吞成普通 fallback** (否则用户以为在跑 L3 实际没跑)
- 外部 Agent 接入改走 `llm_request_spec` 数据契约 (非 closure 注入), 见 D-074 (active 2026-05-25)

## D-025
**personal_offsets 粒度 = `(cuisine, cooking, ingredient)`, 不是"店::菜".** (2026-05-11)
单菜粒度太稀疏 + 没法复用到没吃过的店. 聚合到三维, 能从"宫保鸡丁不爱"泛化到"川菜辣 + 干煸不爱".

## D-026
**learned_profile 用统计聚合 (分位数/比例/黑名单), 不用 LLM 蒸馏.** (2026-05-11, 取代 D-012)
LLM 蒸馏小样本有偏 + 难复现 + 慢. LLM 可在 prompt 里读统计结果, 但不能作为 source of truth.

## D-014
**`profile.taste_description` 用自然语言, 不结构化拆字段.** (2026-05-13)
LLM 能直接消费自然语言, 结构化会丢上下文. 结构化字段只在打分需要的硬维度上用 (oil_level / protein_g).

## D-034
**Context 注入层 (DESIGN 原四层缺的第 5 层).** (2026-05-11)
L1 召回之前注入"当前时间 / 天气 / 上一餐 / 今日剩余预算"等 session-level 事实, 防 LLM 推断错.

## D-071
**不让用户主动选 mood (mood picker 删). 新心情维度走 refine 文本或 L3 prompt, 绝不在前端加 chip.** (2026-05-15) [部分被 D-073 推翻 — refine 路径走结构化 RefineIntent]
- 用户每次都得选 mood = 摩擦; 选了又不准 = 误导信号
- `infer_refine_mood` 只服务 `want_soup` 关键词识别, 不许扩为通用 mood parser

## D-015
**探索机制默认启用: top 5 保留 1-2 个 explore.** (2026-05-13)
防偏好闭环 (爱吃辣 → 全推辣 → 反馈仍辣 → 越推越辣). refine 路径下 explore 关闭 (用户已主动给方向).

## D-023
**餐盘策略改弱约束三件套: 控油 + 至少 1 道蔬菜 + 蛋白下限.** (2026-05-11)
严格 1/2-1/4-1/4 哈佛餐盘在中式外卖现实下不可达. 优化目标是"可持续采纳", 不是"营养精确".

## D-072 + D-072.1
**L0 方法论 (哈佛餐盘 / 减脂 / 糖控) 抽 yaml spec. 改 spec 前后必跑 baseline_l2_snapshot + compare_traces, top60 + 14 维 breakdown |delta| < 1e-6 才允许 commit.** (2026-05-15)
- 改打分逻辑/调权重/加新维度走 score.py 不走 spec
- baseline 回归是替代"自用数据采纳率"的 commit 门槛

## D-063 + D-064 + D-065
**反馈三类信号: gut (好吃度 -1/0/1) / calibration (reason_match, oil_calibration) / behavior (fullness, repurchase_intent). schema 不可混.** (2026-05-15)
三类信号语义独立, 每个 calibration 维度对齐当时的 L3 prediction, 便于回放对比.

## D-066 + D-067
**反馈一次提交 = 永久 readonly 不可改; 后续走 append-only comments timeline.** (2026-05-15)
已提交 ratings 不能改 (否则下游学习不稳定), 反思补充走 append comments, 不污染原始 fact.

## D-028
**北极星指标 = 连续采纳率 (7d/30d), 不是决策时间.** (2026-05-11)
决策时间数据漂移大. 连续采纳率直接反映"够不够好用以至于愿意每天用".

## D-073 + D-073.1
**refine 走结构化意图 (RefineIntent) + 重召回. 完全推翻 D-071, 部分推翻 D-035 / D-043 P3 在 refine 端的应用.** (2026-05-16)
- 病根: 把 refine `parse_feedback` (餐后, 词表稳定) 和 `parse_refine_intent` (餐中, 开放 schema) 挤一起
- RefineIntent schema 开放, LLM 抽不联想
- refine 不写 `long_term_prefs` (当下意图 ≠ 长期偏好, 会污染历史)

## D-074
**AI-friendly 接入 = chisha 零 LLM 确定性内核 + one-shot CLI + agent 的 LLM 做智能.** (2026-05-25, active 设计定稿) · 推翻 2026-05-16 v2 共识 · 翻案 D-022 / D-038 / D-051
定位 [D-097] 自用为主: Phase 0 reference adapter = Claude Code (手动/pull/同步, 不做定时推送). chisha 不持 LLM key, context 抽取 + L3 精排交 agent 的 LLM (`llm_request_spec` 带版本信封 `extract|rerank`); refine 守卫 (校验/清洗/raw_text 注入/disclosure/trace) 全留 chisha (Faithful Refine 不破). CLI verb 链 `start → [resolve-intent] → apply-rerank → choose`, 状态复用 trace_store/feedback_store/meal_log 不新建 ledger. 反馈闭环 defer [F-014]; OpenClaw (推送/定时/飞书) defer Phase 1.
设计定稿: [`proposals/2026-05-25-ai-friendly-integration.md`](proposals/2026-05-25-ai-friendly-integration.md) (Opus + Codex 3 轮收敛 GO). 2026-05-16 v1/v2 过程稿 → `proposals/archive/`.
**Phase 0 落地 (2026-05-25)**: 新 6 模块 — `agent_protocol` (信封 + correlation_id 幂等) / `agent_orchestration.prepare_candidates` (recommend_meal+refine+CLI 共用的确定性编排, 防 CLI 重拼丢守卫) / `agent_round_store` (pending→resolved 状态机, 与 trace 可见 round 索引隔离, flock 幂等) / `agent_choose` (choice_key 双写幂等) / `agent_cli` (verb 链) / `agent_skill_init` (Claude Code SKILL.md). rerank/refine_intent_v2 抽 `build_*_spec`/`apply_*_response` (in-process LLM 路径不动, 保 0-diff). CLI scope 默认 production (sandbox 全局启用拒绝运行). apply-rerank 用 resolved round **持久化的 top_k** 映射 (不重跑, 防 combo_index 漂移). 守门: pytest 1054 pass (979→+75) + baseline_l2_snapshot 0-diff + codex 3 轮 review (设计 + T1-T3 diff + CLI 集成, 共修 9 项含 raw_text 守卫/反馈冻结时序/combo 漂移/跨轮串卡). 接 codex / 其他 agent = 重写 `agent_skill_init` 交互层, 协议层复用.
**收口 review 加固 (2026-05-25, Opus+Codex 二轮)**: F1 fallback 时不传播 agent narrative (破 D-085 风险) / F2 `_map_validated_candidates` 字段白名单 (agent 不能覆盖 restaurant/dishes/score) / F3 一 sid 一餐至多一条 accept (`upsert_meal_log_accept` 改选覆盖 + 旧轮拒回写) / F4 correlation_id 必填强制 (信封回传, 防 stale 串轮). 否决 codex 误报"零 LLM 违反"(混淆 web 内嵌路径与 CLI 路径). 守门 pytest 1057 pass + baseline 0-diff. 契约见 CONTRACTS「Agent CLI 协议」F1-F4. **代码 2026-05-26 补齐提交 (20b3a55) + ff merge 回 main (812f60c) + 端到端实测跑通** (Web SPA 与 CLI 共写同一 meal_log/feedback/trace; apply-rerank fallback=false 证 chisha 确定性校验真生效).

## D-076 + D-076.1
**L1 长期反馈层重构 — 砍伪 L1 + LLM 抽取真兑现.** (2026-05-16) · 推翻 D-043 "refine chip → load_runtime_hints"
病因: 把 refine chip (当下信号) 当长期偏好做半衰期统计, 概念错位. 解法: 砍 refine 写 `feedback_history.jsonl`; LLM 抽取真长期偏好 (`chisha/l1_extractor.py` + `chisha/l1_prefs.py`).

## D-077
**Sandbox Time-Travel 模式 = user web 一个 mode, 行为完全一致 prod, 仅时钟 + 数据落盘根隔离.** (2026-05-16) · 五条不可动摇原则
- 不是新进程不是新端口不是新 UI, 同一个 web 加 sandbox toggle
- 时钟全走 `chisha.clock.today(root)` 注入, 数据落盘走 `chisha.data_root.*` 派生
- prod 路径行为零变 (sandbox off 默认开关)
- 强制 fail-loud: sandbox off + 显式非 `_default` sid → RuntimeError, 防数据串桶

## D-079
**推荐 trace 持久化 + Debug 三模式 (Replay / What-if / Live).** (2026-05-16)
工程契约见 [CONTRACTS.md §Trace + Debug 三模式](CONTRACTS.md#trace--debug-三模式-d-079).

## D-080
**第一原则: Faithful Refine — 系统对 refine 文本的理解深度和执行忠实度, 是用户对 chisha 信任的唯一来源. 冲突时, 忠实优先于多样性 / 效率 / 探索 / narrative 美观.** (2026-05-18) · 系统宪法
所有改推荐链路的 PR 必须先证明不违反. CONTRACTS.md 顶部已挂.

## D-081
**refine 多 slot LLM 解析 — 不再"分类", 意图天然可叠加.** (2026-05-18) · 演进 D-073
- 新 schema 加 brand_avoid / cooking_method_avoid / food_form_avoid / quality_floor / functional / reference 等多 slot
- 裸 LLM 单点必须带 3 安全带: schema 验证 + 失败降级到空 refine / trace 双存 (raw + 结构化) / 冷启动 eval set
- 失败 case 必须显式告知用户 ("没听懂"), 绝不偷换

## D-082
**L0 三分判定表取代旧"硬契约 vs 破戒模式"二分.** (2026-05-18)
- A 医学风险类 (过敏 / 药物 / 孕期 / 术后): **永不可破**
- B 身份伦理类 (清真 / 素食 / 宗教): **永不可破** (只能 profile 改)
- C 普通健康类 (油 / 糖 / 蔬菜占比 / 价格带 / 减脂): **refine 明确表达可破**

## D-083
**methodology 拆两层 — 硬契约下沉 L1 hard_filter, 软偏好留 L2 加权.** (2026-05-18) · 兑现 D-070 "原则派" 承诺
长期方法论 (蔬菜 ≥ 50% / 油上限) 不再与 popularity / variety 同台 PK, 直接 L1 出局. 跟 D-082 耦合: L0 C 类约束就是下沉到 L1 的内容.

## D-084
**refine 模式 L1 召回参数走差异化分支 — 不再与空输入共用一套.** (2026-05-18) · 解决 L3 凑不满 60
per_restaurant_max 3 → 5-8 / 总召回 2-3x / ingredient_want 进 L1 反查 / Cap 失败三级回落 (精确 → 同源扩展 → 全集, 每级 UI 显式告知). 空输入路径行为完全不变 (baseline 0 diff 守门).

## D-085
**narrative + 状态条必须后置 — 漂亮 narrative 是信任放大器 (Codex 反直觉挑战).** (2026-05-18) · 实施次序硬约束
L3 prompt 加 narrative 字段 + 顶部 always-on 状态条, 必须在 D-083/D-084 之后上线, 否则 LLM 会自信编"为你避开了高油菜"实际没过滤, 欺骗深、失信代价大. ~~字段空洞 (quality_floor / delivery_only / reference) 务实降级: 抽出但 L1/L2 不消费, 仅透传 L3 + trace 标 `unsupported_in_recall=true`.~~ [第二句已废弃 by D-094: 字段闭包替代务实降级, 不留 trace-only 字段]

## D-090 + D-091 + D-092
**L2 refine 信号校准三轮 (intent 提权 → slot-aware overlay → 死维度清理).** (2026-05-19~20)
- D-090: intent 三维权重 ×2~×4 + `health_guardrail` slot-aware 松绑, 解决"湘菜+重口"L2 top-5 信号被淹没
- D-091: slot-gated 通用健康权重让位 + `price_band` 语义解耦 (price 维度独立, 不再塞 cuisine 通道) + `context_boost` 清零
- D-092: 5 死维度清理 (vegetable_floor_pass / protein_floor_pass / distance / wetness / context_boost), 19 维 → 14 维 breakdown
- 数值在 `chisha/score.py`, 守门规则 + 改新维度走 D-09x.x + snapshot 守门见 CONTRACTS.md

## D-094
**Faithful Refine 真兑现 — refine v2 schema 字段闭包.** (2026-05-21) · 推翻 D-085 第二句"字段空洞务实降级"
**砍 5**: `redirect.ingredient_synonyms` (代码 `_INGREDIENT_BROAD` 已替代) + `constrain.{quality_floor, delivery_only, max_distance_km, functional.low_caffeine, low_satiety_drowsy}` (单用户实际不用). **修 3 真消费**: `cuisine_candidates_expanded` 进 `_apply_intent_buckets` bucket_soft + `_intent_dish_score` 1.0 加分 (显式 want 仍优先 exact) / `brand_avoid` 在 `recall()` 顶层做 venue 整店硬过滤 (数据 277 venue 100% 单 brand) / `cooking_method_avoid` 在 `_apply_intent_buckets` 做 dish-级硬过滤, **9 类枚举闭包** {油炸/凉拌/生/炖/炒/煮/蒸/烤/煎} (codex audit 实读, brief 写 7 类是漏数据). `food_form_avoid` 数据层 0% 覆盖 → 砍 schema, 立 F-011 数据打标 follow-up; narrative 不主动提"不要面条"诉求 (老实暴露局限 > 假装支持). `DATA_LAYER_UNSUPPORTED_FIELDS` 常量 + `unsupported_in_recall` 字段全删. V2→V1 桥接: `refine.py` 把 intent_v2.redirect 的新字段拷到 V1 RefineIntent. baseline_l2_snapshot 守门: 空 refine 路径 0 diff 验证通过. 详见 `docs/proposals/2026-05-21-faithful-refine-true-fulfillment.md`.

## D-095
**Refine LLM 调用拆 system/user + Anthropic ephemeral cache.** (2026-05-21) · prompt 优化 Step 1 收尾后 Step 3 🔴 项落地
`_llm_parse_v2` 早先把整段 prompt 模板 (含 `{INPUT_TEXT}` 替换后) 塞 user role, `call_text` 没传 `system=` 导致 Anthropic prompt cache 完全失效 — 注释自承认是已识别 bug. **方案 B (Codex 共商定)**: `template.partition("{INPUT_TEXT}")` 切点, `system=template_head` (含八例 + "用户 refine 文本:\n\`\`\`\n", 约 6-7K static tokens), `user=text+template_tail` (用户原文 + "\n\`\`\`\n\n输出 JSON:"). `cache_system=True` 启用 ephemeral cache. trace `system_prompt_full / user_message_full` 由"假拆"变与实际 LLM 入参 1:1 对齐. 模板顺序与语义不变, 仅挪 static head 到 system. 预期 ROI: refine latency 6-8s → 3-4s, input_tokens 95%+ 走 cache_read (10% 价格). 跨 provider: anthropic_api / openrouter ephemeral cache 真生效, claude_code_cli 静默忽略 (CLI 自管). 守门: 全套 pytest 984 pass + baseline_l2_snapshot 0 diff + Codex diff review SHIP. 详见 `docs/proposals/2026-05-21-refine-cache-fix.md`.



## D-096 + D-090.1 + D-094.1
**V1 refine 退役 + V2 schema 扩 4 槽 + 全栈切 V2 (单 PR).** (2026-05-24) · 推翻 D-073 双模式 + D-094 字段闭包
**主决策 (D-096)**: V1 `refine_intent.py` + `parse_refine_intent.md` 整模块砍 (无 caller / 双模式过渡债 / 每轮多耗 2~6s); V2 是唯一意图层. response `refine_intent` 字段直接是 V2 shape (砍 V1+V2 双存); trace round 字段统一 `intent_v2`; refine.py async/off 三模式逻辑同时砍 (V1 已无 fallback). **D-090.1 修正案**: `health_guardrail` 油豁免触发字段从 V1 `flavor_tags="heavy"` 切到 V2 `constrain.oil="high"`. **D-094.1 修正案 (推翻原 D-094 字段闭包)**: V2 schema 9 槽扩到 13 槽 — `redirect` 加 `staple_want / staple_avoid` (主食偏好自由字符串, L2 真打分); `constrain.oil` 枚举 `{low}` 扩到 `{low,normal,high}` ("high" 替代 V1 heavy 触发油豁免); `constrain` 加 `wants_soup: bool` (L2 真打分) + `price_band ∈ {cheap,normal,premium} | null` (模糊文本兜底, `price_max` 数字优先). 同时砍 V1 `flavor_tags=sweet/sour` (L3 narrative 兜底). L3 prompt (`rerank_system.md`) refine_intent 字段口径 + narrative 真消费闭包同步 V2.1. schema_version bump `2.0 → 2.1`. baseline_l2_snapshot 是新基线 (schema 变 → 不跟旧对比). 守门: pytest 936 pass / V1 imports 全清 / codex BLOCK×2 修复 (price_max 优先 + staple_avoid 走 recall 硬过滤) / 前端 debug-ui 同步 V2.1 shape. 详见 `specs/archive/T-FR-V1-RETIRE.md`.

## D-097
**项目定位收敛: 自用为主、推广随缘 — 推翻 Phase 1 "同事推广" 的范围假设.** (2026-05-25) · 调整 D-070 Phase 切分优先级 (不改 Phase 结构, 只调先做什么)
志丹拍板: 主目标回到"我自己每天用得爽"; 同事推广降为"随缘" (遇到合适的人自然推, 不为推广提前建设).
Phase 1 启动前原 9 项必收口按"自用是否需要"重切 (清单见 [ROADMAP](ROADMAP.md) "必收口"段):
- **留 (自用刚需)**: AI-friendly 接个人 agent (D-074 Phase 0 reference adapter, 含 Living API meal_hint+at_time 参数化) + B-001 反馈短链路 (P0, 差评当前不生效)
- **降级到 BACKLOG (有兜底, 触发再做)**: Living/Lab router 后端拆分 (F-013) + screener (F-003)
- **推迟 (为同事服务, 自用不需要)**: 第二份 methodology spec (F-004) / L1 cuisine token (F-001, 同事 cuisine 才分散)
- **已实质解**: 沙箱动线 (用户视图 sandbox UI 已移除 :5173, D-093)
不砍能力, 只调先做什么. 真要推广同事时回看本条恢复"推迟"项.

## D-098
**Responsive Feedback — 反馈短链路即时生效 (差评不生效 B-001 P0 修复).** (2026-05-25) · 第一原则: 用户每次 👍/👎 必须在下次推荐被可感知响应, "差评不生效"=信任崩塌
新增短链路 (实时 / 餐厅·菜品级 / 带衰减) 补 L1 慢链路缺口, 二者独立互补 (L1 仍负责泛化成长期口味). 新核心模块 `chisha/feedback_signal.py` 从 `feedback_store` **自包含**取数 (accepted_rank→cold-store session combo→restaurant_id+dish_id; 弃 meal_log JOIN 因落盘丢 dish_id). **信号源**=组合C+Q-B 冲突规则 (强负=rating==-1且repurchase==0 / boost=rating==1且repurchase==2 / repurchase 优先于 rating). **三注入**: ① score.py 第 15 维 `feedback_recency` (餐厅级主+菜品级辅弱累积, weight 1.5 由 top5 cutoff margin 法标定) ② recall.py 强负 30 天剔除 (放 combo/价格/intent 全部过滤之后, 捕获 with/without-feedback 最终集差集 → narrative 忠实) ③ L3 narrative `[FEEDBACK_AVOIDED]` 段只列真剔除店 (D-085 忠实). 线性衰减 (差评 0-30d 强/30-60d 衰减; 好评 7-30d 弱boost). **§8.1 单次构建**: api/refine 起点 build 一个对象, recall/score/L3/trace 共享同一引用, rank_combos 自身不读 store (防 standalone L1/L2 不一致). What-if 零 runtime read: trace `__frozen` 加 `feedback_signal_snapshot`+`feedback_avoided_names`, `TRACE_SCHEMA_VERSION` 3→4 (v3 仍 accepted). 守门: pytest 979 pass + baseline_l2_snapshot 0-diff (无反馈 gating) + snapshot 标定测试 (真实数据强负压出 top5) + codex BLOCK×4 修复 (narrative 真实归因 / refine R2 一致 / version bump / 白名单). 详见 `docs/proposals/2026-05-25-feedback-short-loop-b001.md`.

## D-099 + D-099.1 + D-099.2 + D-099.3
**稳定实体 id — 跨重采不漂移.** (2026-05-26) · 推翻 loader 按文件位置发号 (`r_{i}`/`d_{i}_{j}`); 修「重采→id 洗牌→历史反馈/标签错投」根因. Opus 提案 + Codex pressure-test 收敛, 提案存档 `docs/proposals/2026-05-26-stable-entity-id.md`.
- **D-099 公式**: `rid = "r_"+sha1(normalize_shop_name_v1(name))[:10]` (逐字复现采集端 `text_norm.py` v1, 字节对拍 571/571 一致); `dish_id = "d_"+rid+"_"+sha1(normalize_dish_name_v1(raw_name))[:8]` (restaurant-scoped). 归一化只动空白/零宽/全角括号, 显式不动大小写/标点/价格/规格.
- **D-099.1 唯一性 + 冲突 fail-loud**: 价/销变化不改 id. 同店同归一菜名但**价格不同**=真冲突 → 隔离不进 active (不加后缀/不混 price 进 key); 同名同价仅销量差 → 折叠. 8-hex 碰撞 / 餐厅级歧义 (同 status+count 内容不同) 同样隔离. 餐厅去重取**单一权威记录** (`status ok>early_ok>partial>failed>None` → menu_count → 内容指纹, 不取并集, 不用输入顺序). **原子发布状态机**: 未确认冲突 → 只写 staged + `dish_id_conflicts.json` 报告, active 不动, 退出非0; 冲突进 `conflicts_ack.json` 后才发布.
- **D-099.2 改名/跨 zone 身份**: rid=全局门店身份, zone 仅配送上下文 (同 rid 反馈跨 zone 生效). 店改名→新 rid, 靠人工 `data/aliases.json` 把旧名绑 canonical rid 兜底 (loader+迁移都应用). 归一化版本变=迁移事件.
- **D-099.3 增量打标**: 仅新 dish_id / tag_version 变才调 LLM. 每次 ingest **重建活动集** (复用旧标签 + 刷新 price/sales/raw + 删 raw 中消失的菜); batch 缓存绑**有序 dish-id 清单** (非批号/长度). recall/score/feedback_signal 对 id 只做字符串相等/映射 (无 `r_\d+` 数字假设, `r_<hex>` 兼容).
- **落地**: office 429→395 唯一店 (5 同名异价 SKU acked 隔离), home 142 (100% ⊆ office, 采集侧问题待查). 旧标签按 (新rid,新dish_id) 重映射: szbay 19934 复用 + 1762 旧重复店标签不一致判 ambiguous 重打 + ~992 新菜, home 8088 全复用. 一次性迁移 `scripts/migrate_stable_ids.py` (ingest 前快照旧数据). 守门: pytest 全绿 + 字节对拍采集端 + codex 设计触点×1 + diff review×4 (8 blocking 全纳: 碰撞双隔离/歧义整店隔离/原子成对写/迁移刷新上架/schema失败不污染live/conflict-key带价格指纹/exit非零/离线tagger查锁).
- **已知残留 (志丹拍板接受)**: ingest 锁是 check-then-read, 对**并发** loader+tagger 有 TOCTOU (单人顺序工作流不触发). 现有防护 (锁marker防崩溃残留 + live文件最后翻 + dishes_raw仅离线消费 + 4 tagger入口查锁) 覆盖真实失败; 若将来多人/并行再上 `fcntl.flock` 真互斥.

## D-100
**collector↔chisha 接口契约硬化 — 防字段漂移 / id 漂移 / 采址污染.** (2026-05-26) · 触发=断裂点 G (home 采到深圳湾, 标签对地址错从产物无法自检). 两 repo 间隐式契约零防护 → 把"静默出错"变"响亮报错". Opus 实现 + Codex 设计 review + commit review 收敛. 提案 `docs/proposals/2026-05-26-collector-chisha-contract.md`.
- **Batch A (生产端 waimai_data)**: output envelope 加 `schema_version=1` + `normalized_name_version` + `location.observed_*` 软地址 provenance; `build_output` 加 location 护栏 (name==label 即 fail, 防手搓 location 把 name 静默降级成 label —— 实证一次 ad-hoc regeneration 把 office 的 name 降级了); 弃用发散 envelope 的 `tools/aggregate.py` (hard-fail 指向 collector.main); 软地址观测 (采前主动读美团实际配送地址文本, 软版只记录不判定). 契约落档 `OUTPUT_CONTRACT.md`.
- **Batch B (消费端 chisha)**: 新 `chisha/collector_contract.py` 窄契约校验 (pydantic `strict=True` + `extra="allow"`, provenance 字段 required-nullable, status 锁 `Literal[observed/unobserved]`); `loader.load_raw` 入口 fail-loud 校验 + 断言 `normalized_name_version==SHOP_NAME_VERSION` (**无 grandfather**); 新 `scripts/refresh_from_collector.py` 编排 preflight→哨兵→loader→tag→backfill→validate (publish 全 zone 后才 tag) + 跨 zone 指纹哨兵 + `ZONE_MAP` (D5).
- **设计决策锁定 (D1-D5)**: schema_version=int; grandfather 选重导出不留放行口; 哨兵 hard-fail=共享≥30 且 rid 共享率≥80% 且 distance 相同率≥80% 且 label 不同; zone 映射放消费端; 自用阶段不抽共享归一化包 (触发=第 3 个消费者).
- **守门**: chisha pytest 1023 pass + 真 A4 office 文件过契约 (strict 抓到 menu `image` 实为 bool → 移出契约) + Codex commit review SHIP-WITH-FIXES (S-1 status→Literal / S-2 publish-then-tag 分两轮, 已修). `collector_contract.py` **不进 high-risk 白名单** (纯边界校验器, D4).
- **收口 (2026-05-27 重采两 zone 实跑)**: envelope 已落地 `extractor.build_output` (schema_version/normalized_name_version/location.observed_* 三字段) → 真 A4 office 文件过契约守门**自动恢复** (`test_real_a4_office_file_passes` 从 skip 转真校验 pass); B3 全链路 (publish→tag→backfill→validate) + 跨 zone 指纹哨兵两 zone 真数据**已实跑通过**. 仍未落地: A3 `observed_address_text` 真机观测 (现填 null/unobserved 合法空值, 契约过但 provenance 仍空); Batch A 的 name==label 护栏 / aggregate.py 弃用本次未碰 (只补 envelope).

## D-101
**非菜品两层隔离 — 防餐具/包装/营销项炸打标.** (2026-05-27) · 触发=重采后 home 打标卡死: collector 把"需要餐具/纸巾/烧烤店里更好吃"当菜爬 (office 171+home 14), LLM 诚实打 `cooking_method='其他'` 不在 `COOKING_METHODS` 枚举 → DishTagged schema 拒 → 整 zone 写 .staged 不发布. Codex 设计 review.
- **Layer 1 (loader 打标前)**: 新 `chisha/non_dish_rules.py` `is_non_dish()` — 强信号子串 (餐具/一次性/保温袋...) + 裸器具去装饰整名精确 (筷子/手套/勺子, 防误杀"神枪手套餐"/"配手套"/"筷子鸡"). `_build_dishes` 在冲突检测**前**剔除, **non-blocking 隔离** (不进 conflicts 集 → 不阻塞 publish), 写 `non_dish_quarantine.json` 报告. 全量 23551 道实测命中 168 零误杀.
- **Layer 2 (tagger 兜底)**: `tag_via_api._finalize_write` 改**记录级隔离** — 单条 schema 越界写 `dishes_tagged.quarantine.json` (具名+reason), valid 照进 active; 退役旧 all-or-nothing `.staged` (1 道脏菜不再阻塞整 zone). active 恒 schema-valid 不变 (BLOCK#5 安全守住).
- **精度第一**: 宁可漏不可误杀真菜, 漏网 (如营销语) 由 Layer 2 兜底; `COOKING_METHODS` **不加'其他'** (保持严格, 不让垃圾混进 recall). `non_dish_rules.py` 纯函数 **不进 high-risk 白名单** (同 collector_contract 先例).
- **打标鲁棒性**: deepseek batch=30/16workers 实测 home 24/28 截断+限流挂; 降 `--batch 15 --workers 8` 后 home 56 batch 0 失败. 增量兑现: office 22556 道仅 delta=147 真调 LLM (复用 22409).

## D-102 + D-102.1 + D-102.2
**可分发的共享核心 — chisha 从单用户工具到类 feishu-cli 可分发物.** (2026-05-28) · 重激活 ROADMAP Phase 1 工程主线 (不推翻 D-097 自用为主, 把"真要推广时回看恢复"落地). Opus + 志丹多轮 + Codex 架构 review 两轮收敛. 提案 `docs/proposals/2026-05-28-distributable-shared-core.md` (5 支柱 + 分步 + 已知坑).
- **5 支柱 (锁定)**: ① 核心产 plan 三件套 (PromptPlan/ValidationSpec/FallbackPlan)、不拥有执行 (adapter 执行 LLM); ② install/state root 二分、state→`~/.chisha/`、sandbox 为 state namespace; ③ 分发=版本化静态产物+capability manifest+doctor 闸门、Claude Code 走 plugin; ④ web 降自用薄壳 (禁独占业务逻辑); ⑤ 分步先焊大脑再搬文件. 病根=两入口靠"手工穿状态"而非"核心打包状态" → meal_log 在 cli 兜底 drift (信任砸点).
- **D-102.1 Step1 焊大脑 (已落地)**: 抽 `FallbackPlan` (rerank.py) 封装兜底全部状态 (候选集+meal_log 只读快照+n/n_explore/today+version); `build_fallback_plan` 唯一构造入口 meal_log **必填**, `fallback_rerank` 改 meal_log 必填 (拔"默认 None 隐式漏传"温床). web/cli/what-if/debug 四路兜底全经此. cli 跨进程: PreparedCandidates 加 meal_log → resolve 时 `to_blob` 冻进 round prepared (D-098 范式), apply 时 `from_blob` 重建执行 (blob 缺失/版本不符 fail-loud, D-100 无 grandfather). 根治 `agent_cli` 漏 meal_log → explore 丢"避开最近吃过"偏置. PromptPlan/ValidationSpec 经核确认已单源 (`build_rerank_spec`/`apply_rerank_response`), 本期不加仪式 wrapper, 形式化推迟 (Codex scope 共识). 守门: pytest 1155 pass (+13 测试, 有牙=meal_log 真改 explore + 跨进程 blob 忠实 + 7 天边界) + baseline_l2_snapshot 0-diff (web 主路径).
- **D-102.2 Step2 搬文件 (已落地, 分两 commit)**: install/state root 二分, user state 默认落 `~/.chisha/` (host-agnostic 活过 plugin update). 新 `chisha/state_root.py` (零依赖, 避循环) `resolve()` 三规则: env `CHISHA_STATE_ROOT` > 显式非包目录 root > `default_state_root()`(=~/.chisha). data_root 8 落盘函数 + sandbox + web_api sandbox 路由 (`_sb_bucket`/`_validate_and_route_sid`/`_copy_real_data`) + sandbox_migration 全收口经 state_root (防 split-brain). feedback_history/long_term_prefs 从 `data/`(install 只读区) 迁出到 state_root 顶层 (user state 不能与引擎只读库同住). 新 `chisha/state_migrate.py` + `scripts/migrate_state.py`: 复制(不删源, repo 作回滚)+目录逐文件原子合并(staging+rename, 不 clobber/不丢)+校验+原子 marker+幂等. agent_cli doctor 扩 install_root/state_root/writable/migrated/legacy_pending (未迁旧 state→ok=false 未就绪). 真迁移已跑 (repo→~/.chisha 108 文件). **行为 0-diff** = flip+迁移一起 (单翻不迁会读空 state, 守门: CHISHA_STATE_ROOT=repo 跑 baseline 0-diff + 迁移后 ~/.chisha 跑 baseline 0-diff). 测试隔离: conftest autouse monkeypatch default_state_root→tmp_path+delenv (绝不污染真实 ~/.chisha). Commit A=管道(0-diff plumbing)/Commit B=翻默认+迁移. Codex 双 commit review (各 FAIL/HOLD→修 3+5 BLOCKING→SHIP). 守门: pytest 1167 pass (+11 state_root/migrate 测试) + baseline 0-diff. 残留: 迁移 TOCTOU (单用户一次性, 接 D-099 先例接受); sandbox `sandboxes/<id>/` 重构 + PROFILE_PATH legacy 常量推迟.

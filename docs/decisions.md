# chisha · 活决策日志

> 主读者: 你 (志丹). Coding agent 偶尔 grep.
> 维护纪律见 [CONTRIBUTING_DOCS.md](CONTRIBUTING_DOCS.md): 3-5 行/条, 写产品/业务方向, 不写实施.
> Phase 0 历史细节全量归档在 [archive/DECISIONS_phase0.md](archive/DECISIONS_phase0.md).

## 索引

**产品定位 / 形态**: [D-001](#d-001) · [D-021](#d-021) · [D-051](#d-051) · [D-070](#d-070) · [D-097](#d-097)
**数据层**: [D-002+D-030](#d-002--d-030) · [D-008](#d-008) · [D-037](#d-037) · [D-099~D-099.3](#d-099--d-0991--d-0992--d-0993) · [D-100](#d-100) · [D-101](#d-101)
**推荐链路架构**: [D-005](#d-005) · [D-041+D-006+D-040](#d-041--d-006--d-040) · [D-043~D-045](#d-043--d-042--d-044--d-0441--d-045) · [D-046](#d-046) · [D-035+D-047A](#d-035--d-047a) · [D-049](#d-049) · [D-050](#d-050) · [D-038+D-047B+D-048](#d-038--d-047b--d-048)
**Profile / 学习**: [D-025](#d-025) · [D-026](#d-026) · [D-014](#d-014)
**Context / Mood**: [D-034](#d-034) · [D-071](#d-071) · [D-015](#d-015)
**方法论 (L0)**: [D-023](#d-023) · [D-072+D-072.1](#d-072--d-0721)
**反馈系统**: [D-063~D-065](#d-063--d-064--d-065) · [D-066+D-067](#d-066--d-067) · [D-098](#d-098)
**北极星指标**: [D-028](#d-028)
**Refine 重做 / Refine v2 / Faithful Refine**: [D-073+D-073.1](#d-073--d-0731) · [D-080](#d-080) · [D-081](#d-081) · [D-082](#d-082) · [D-083](#d-083) · [D-084](#d-084) · [D-085](#d-085) · [D-094](#d-094) · [D-096](#d-096--d-0901--d-0941)
**L2 信号校准**: [D-090~D-092](#d-090--d-091--d-092)
**L1 长期反馈层 / Sandbox / Trace**: [D-076+D-076.1](#d-076--d-0761) · [D-077](#d-077) · [D-079](#d-079)
**LLM 调用基建**: [D-095](#d-095)
**AI-friendly 接入形态演进 (active)**: [D-074](#d-074) (零 LLM 内核) → [D-103](#d-103) (eat/continue/choose 折叠) → [D-104](#d-104)+[D-104.1](#d-1041) (core 解耦) → [D-105](#d-105)+[D-105.1](#d-1051) (形态B 自包含 bundle, 形态A 退役)
**可分发核心 / install·state·manifest 分发基建**: [D-102~D-102.3](#d-102--d-1021--d-1022--d-1023)

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
chisha 不持 LLM key, context 抽取 + L3 精排交 host agent 的 LLM (`do_llm` 带版本信封 `extract|rerank`); refine 守卫 (校验/清洗/disclosure/trace) 全留 chisha (Faithful Refine 不破)。状态复用 trace_store/feedback_store/meal_log 不新建 ledger。接 codex / 其它 agent = 重写交互层 (SKILL.md), 协议层复用。反馈闭环 defer [F-014]; OpenClaw 推送/定时 defer Phase 1。
**接入形态已演进** (见索引): D-074 零 LLM 内核 → D-103 协议折叠 (eat/continue/choose) → D-105.1 形态B bundle。协议层契约 (F1-F4 守卫 / 信封 / round 状态机) 见 CONTRACTS「Agent CLI 协议」段。设计定稿 `proposals/archive/2026-05-25-ai-friendly-integration.md` (Opus+Codex 3 轮 GO)。

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
原则: schema 里的字段必须真消费, 不留"抽出但不用"的空洞字段。砍单用户不用的 5 字段 (quality_floor / delivery_only / max_distance_km / functional / ingredient_synonyms); 让 cuisine_candidates_expanded / brand_avoid / cooking_method_avoid 三个真进 L1/L2 过滤 (cooking_method_avoid 是 9 类枚举闭包)。数据层 0 覆盖的 `food_form_avoid` 砍 schema → 立 F-011; narrative 老实暴露局限不假装支持。字段闭包见 CONTRACTS「Refine/Mood」段; 设计存档 `docs/proposals/archive/2026-05-21-faithful-refine-true-fulfillment.md`。

## D-095
**Refine LLM 调用拆 system/user + Anthropic ephemeral cache.** (2026-05-21) · prompt 优化 Step 1 收尾后 Step 3 🔴 项落地
病根: refine prompt 整段塞 user role 没传 `system=` → Anthropic prompt cache 完全失效 (注释自承认的 bug)。方案: 按 `{INPUT_TEXT}` 切点, static head (八例) 进 system 启 ephemeral cache, 用户原文进 user; 模板语义不变, 仅挪 static head。ROI: refine latency 6-8s→3-4s, input_tokens 95%+ 走 cache_read。设计存档 `docs/proposals/archive/2026-05-21-refine-cache-fix.md`。



## D-096 + D-090.1 + D-094.1
**V1 refine 退役 + V2 schema 扩 4 槽 + 全栈切 V2 (单 PR).** (2026-05-24) · 推翻 D-073 双模式 + D-094 字段闭包
V1 `refine_intent.py` 整模块砍 (无 caller / 双模式过渡债 / 每轮多耗 2~6s), V2 是唯一意图层 (response/trace 统一 `intent_v2`, 砍双存)。D-090.1: 油豁免触发字段切到 `constrain.oil="high"`。D-094.1 (推翻原 D-094 闭包): V2 schema 9→13 槽 — 加 staple_want/avoid + oil 扩 {low,normal,high} + wants_soup + price_band, 砍 V1 flavor_tags。schema_version `2.0→2.1` (新 baseline 基线)。字段口径见 CONTRACTS「Refine/Mood」段。

## D-097
**项目定位收敛: 自用为主、推广随缘 — 推翻 Phase 1 "同事推广" 的范围假设.** (2026-05-25) · 调整 D-070 Phase 切分优先级 (不改 Phase 结构, 只调先做什么)
志丹拍板: 主目标回到"我自己每天用得爽"; 同事推广降为"随缘" (遇到合适的人自然推, 不为推广提前建设)。原 Phase 1 必收口 9 项按"自用是否需要"重切: 留 AI-friendly 接入 (D-074) + 反馈短链路 (D-098); 降级 Living/Lab router 拆分 (F-013) + screener (F-003); 推迟第二份 methodology spec (F-004) + L1 cuisine token (F-001, 为同事服务)。不砍能力, 只调先做什么; 真要推广同事时回看本条恢复"推迟"项。

## D-098
**Responsive Feedback — 反馈短链路即时生效 (差评不生效 B-001 P0 修复).** (2026-05-25) · 第一原则: 用户每次 👍/👎 必须在下次推荐被可感知响应, "差评不生效"=信任崩塌
新增短链路 (实时 / 餐厅·菜品级 / 带衰减) 补 L1 慢链路缺口, 二者独立互补 (L1 仍负责泛化长期口味)。短链路只压差评的店/菜, 不泛化。信号源 = rating + repurchase 冲突规则 (强负压制 / 好评弱 boost, 线性衰减)。实现契约 (三注入 / §8.1 单次构建 / What-if 零 runtime read / trace v3→v4) 见 CONTRACTS「反馈短链路」段; 设计存档 `docs/proposals/archive/2026-05-25-feedback-short-loop-b001.md`。

## D-099 + D-099.1 + D-099.2 + D-099.3
**稳定实体 id — 跨重采不漂移.** (2026-05-26) · 推翻 loader 按文件位置发号 (`r_{i}`/`d_{i}_{j}`); 修「重采→id 洗牌→历史反馈/标签错投」根因. Opus 提案 + Codex pressure-test 收敛, 提案存档 `docs/proposals/archive/2026-05-26-stable-entity-id.md`.
- **D-099 公式**: id = 稳定哈希 (`r_`+sha1(归一店名)[:10] / `d_`+rid+sha1(归一菜名)[:8], restaurant-scoped), 逐字复现采集端归一化 (只动空白/零宽/全角括号, 不动大小写/标点/价格)。当不透明字符串用, 禁 `int(rid[2:])` 数字解析。
- **D-099.1 冲突 fail-loud**: 价/销变化不改 id; 同名异价/哈希碰撞/餐厅歧义 → 隔离不进 active + 报告, 进 `conflicts_ack.json` 才发布 (原子发布状态机)。
- **D-099.2 改名/跨 zone**: rid=全局门店身份, zone 仅配送上下文 (同 rid 反馈跨 zone 生效); 改名→新 rid, 靠人工 `aliases.json` 兜底。归一化版本变=迁移事件。
- **D-099.3 增量打标**: 仅新 dish_id / tag_version 变才调 LLM; 每次 ingest 重建活动集 (复用旧标签 + 删 raw 中消失的菜)。
- **已知残留 (志丹拍板接受)**: ingest 锁 check-then-read, 对并发 loader+tagger 有 TOCTOU (单人顺序工作流不触发); 多人/并行再上 `fcntl.flock` 真互斥。契约见 CONTRACTS「数据/打标」段。

## D-100
**collector↔chisha 接口契约硬化 — 防字段漂移 / id 漂移 / 采址污染.** (2026-05-26) · 触发=断裂点 G (home 采到深圳湾, 标签对地址错从产物无法自检). 两 repo 间隐式契约零防护 → 把"静默出错"变"响亮报错". Opus 实现 + Codex 设计 review + commit review 收敛. 提案 `docs/proposals/archive/2026-05-26-collector-chisha-contract.md`.
生产端 envelope 加版本 + 软地址 provenance, 消费端 `loader.load_raw` 入口窄契约 fail-loud 校验 (**无 grandfather**)。
设计锁定 (D1-D5): schema_version=int; grandfather 不留放行口; 跨 zone 指纹哨兵 hard-fail (共享≥30 且 rid/distance 高重合且 label 不同, 抓 G 式采址污染); zone 映射放消费端; 自用阶段不抽共享归一化包 (触发=第 3 个消费者)。契约见 CONTRACTS「数据/打标」段 + 跨 repo `OUTPUT_CONTRACT.md`。残留: 真机观测地址 (`observed_address_text`) 未落地, 现填合法空值。

## D-101
**非菜品两层隔离 — 防餐具/包装/营销项炸打标.** (2026-05-27) · 触发=重采后 home 打标卡死: collector 把"需要餐具/纸巾/烧烤店里更好吃"当菜爬 (office 171+home 14), LLM 诚实打 `cooking_method='其他'` 不在 `COOKING_METHODS` 枚举 → DishTagged schema 拒 → 整 zone 写 .staged 不发布. Codex 设计 review.
两层: loader 打标前 `is_non_dish()` 规则隔离 (精度优先, 宁漏不误杀真菜, non-blocking 不阻塞 publish) + tagger 记录级隔离 (单条越界进 quarantine, valid 照发, 退役旧 all-or-nothing `.staged`)。`COOKING_METHODS` 保持严格不加'其他' (不让垃圾混进 recall)。契约见 CONTRACTS「数据/打标」段。

## D-102 + D-102.1 + D-102.2 + D-102.3
**可分发的共享核心 — chisha 从单用户工具到类 feishu-cli 可分发物.** (2026-05-28) · 重激活 ROADMAP Phase 1 工程主线 (不推翻 D-097 自用为主, 把"真要推广时回看恢复"落地). Opus + 志丹多轮 + Codex 架构 review 两轮收敛. 提案 `docs/proposals/archive/2026-05-28-distributable-shared-core.md` (5 支柱 + 分步 + 已知坑).
- **5 支柱**: ① 核心产 plan 三件套 (PromptPlan/ValidationSpec/FallbackPlan)、不拥有执行; ② install/state root 二分、state→`~/.chisha/`; ③ 分发=版本化产物+capability manifest+doctor 闸门; ④ web 降自用薄壳; ⑤ 先焊大脑再搬文件。病根=两入口靠"手工穿状态"而非"核心打包状态" → meal_log 在 cli 兜底 drift (信任砸点)。
- **D-102.1 焊大脑**: 抽 `FallbackPlan` 封装兜底全部状态, meal_log **必填** (拔"默认 None 隐式漏传"温床), web/cli/what-if/debug 四路单源。cli 跨进程靠 blob 冻结/重建 (D-098 范式)。
- **D-102.2 搬文件**: install/state root 二分, user state 默认落 `~/.chisha/` (host-agnostic 活过 plugin update); 所有 state 路径经 `state_root.resolve()` 单源 (防 split-brain); 一次性显式迁移 (复制不删源 + 原子合并 + 幂等)。
- **D-102.3 分发闸门**: 数据 bundle 带 `manifest.json`, `recall.load_zone_data` 入口用 capability flags (非单调 version) 比对, 不兼容 `IncompatibleManifestError` hard-fail; 缺 manifest=过渡期 warn 放行。
- **本期留位不定型 (范围红线)**: integrity hash/签名 (`integrity=null`) + plugin marketplace 打包 (先内部 git transport)。契约见 CONTRACTS「install/state root 二分」+「manifest 闸门」段。

## D-103
**P1 AI-friendly 接入优雅化 — 折成 eat→continue 单循环, 对标 feishu-cli 薄 skill.** (2026-05-29) · 触发=志丹"对外发布太繁琐不优雅"。学 feishu-cli 后定方向: **保留零 LLM 无脑核心 (差异点/卖点: chisha 主动选确定性引擎+借宿主智能, 非被迫自包含智能), 只偷打包+触发纪律**。Opus+Codex 双触点。
- **协议折叠**: 顶层扁平 `eat / continue / choose`; `continue` 合并 resolve-intent+apply-rerank, 按不透明 `step_token` 路由。host 单循环: 回包带 `do_llm` 就跑、喂回, 直到 `status=ready`。去掉手抄 correlation / 手包信封的 footgun。协议契约见 CONTRACTS「Agent CLI 协议」P1 条。
- **装包模型** [已废弃 by D-105.1: 形态A `uv tool install` 入口退役, 接入唯一形态 = 形态B bundle]。老 verb / 老字段各留 deprecated alias 一版。
- **转 public 已落地, 历史清洗 gate 关闭 (2026-05-30 核实)**: repo 已 public (README 主体早已声明)。Sprint A 历史清洗 (git filter-repo) **未做但经全历史扫描无敏感泄漏** — key 全是 dummy CI 值 / `.env.production` 仅 `VITE_USE_MOCK=0` 无害 (D-069) / `profile.yaml` 是模板 / 个人 state 未入库 → 判定**不补做** (除非发现遗漏敏感内容)。远程分发协议 (agent 从公网自动拉 bundle) 仍未设计 (见 [D-105.1](#d-1051)), 当前 bundle 靠手动拷贝。

## D-104
**agent-only core 解耦 — 推荐核心从 sandbox/web/debug/自调LLM 切干净, 可独立 slim 运行.** (2026-05-29) · 单包逻辑分层 (非物理拆 PyPI 包) + ambient provider DI. Opus 设计 + Codex 设计/commit 双触点逐步落地 (6 commit). 提案归档 `docs/proposals/archive/2026-05-29-agent-core-decoupling.md`.
- **机制**: ambient provider singleton + test override hook (clock/data_root 同款); default provider == 现 production → **0-diff 根基**. core 只持 `get_clock_provider()`/`get_sandbox_router()`; sandbox 是 extras, 被 import 时注册虚拟时钟/real router (web_api/debug_server 早 import 触发, sandbox-lab 走 debug_server); core/slim 进程永不 import sandbox。边界铁律落 CONTRACTS「agent-only core / extras 边界」段。
- **分步**: Step0 deps 瘦身 (5 重依赖→optional [web]/[dev]); Step1a 抽 `core_api_helpers`; Step1b agent trace 拆 core-minimal + extras-rich (保 reference refine §1.3 功能零损失, 志丹定 Approach A); Step2/3 DI clock/data_root 去 import sandbox (新 `clock_provider`/`sandbox_router` 零依赖 core 叶子, 两处 fail-loud raise 保留); Step4 rerank LLM 调用补 slim 守门 (llm_client 已 lazy, 边界本就成立); Step5 `scripts/build_skill_bundle.py` 切 core 子树 + 隔离 venv 实跑。
- **校正提案**: `sandbox_context` 归 CORE (纯 stdlib, §3 误划 extras); data_root 两处 raise (非一处); status_bar 留 core; Step4 是验证+守门非重构。
- **守门**: 边界 smoke (`tests/test_d104_di_boundary.py`: import core 闭包不含 sandbox/llm_client*/web/debug/fastapi/anthropic/openai/pandas) + baseline_l2_snapshot 0-diff (每步) + pytest 1265 + **真 slim venv 实跑** start→apply-rerank→choose→refine→--at-time (extras 物理缺席, candidate=60, Step1b 最小 trace 落盘)。
- **行为微调** (与 "sandbox=debug, 在 production 之外" 一致): sandbox-awareness 现仅经 web/debug 入口注册 → 直接 `api.recommend_meal` / 老 cli 不再 sandbox-aware (老 cli D-096 已退役)。
- **债务** (Codex 标, 出 scope, 非本次引入): `reference_resolver` 用 v2 `list_traces`, session 被 R2 `append_round` 迁 v3 后旧路径可发现性缺口 — full/slim parity 不破, 待独立修。 [已修 by D-104.1]

## D-104.1
**D-104 两条备查跟修 — reference v3 可发现性 + 裸 core 真实时钟护栏.** (2026-05-30) · 跟修 D-104 债务 + 行为微调, 非推翻。
- reference 解析改 v3-aware: 修前 refine 过的历史餐 (迁 v3 目录) "上次那家换一家"类引用解析不到 → 隐性破坏 Faithful Refine (D-080)。v2 回退保留, 找不到仍降级 (D-085 忠实)。
- 锁死裸 agent recommend 走真实时钟 (虚拟时钟只经 web/debug 注册), 防假时间被接回点餐路径。`reference_resolver` 不进 high-risk 白名单。

## D-105
**形态B 自包含 skill 分发 — 替代形态A 当默认接入.** (2026-05-30) · 设计 spec: docs/superpowers/specs/2026-05-30-chisha-form-b-self-contained-skill-design.md · Codex 设计+commit 双触点。
- **动机**: 形态A (`uv tool install chisha` + 薄 SKILL.md 指全局 `chisha`) 接入两步、代码不随 skill 走、换机器要先装包。形态B: core 代码+数据+vendored 依赖+wrapper bundle 进一个 skill 文件夹, 拷进 `~/.claude/skills/chisha/` 即用, **自包含、零全局安装、运行期零联网、零 pydantic**。
- **砍 core pydantic**: `collector_contract.py` 改纯 dataclass + 手写 strict 校验 (4 陷阱逐层复刻, golden 对拍)。core 运行期唯一第三方依赖 = pyyaml, **vendored** 进 bundle `vendor/yaml/` (纯 Python path)。
- **诚实边界**: **POSIX-only** (core 用 fcntl 文件锁, Windows 仅 WSL) + **python3 ≥ 3.11** (macOS 自带 3.9 不够, wrapper 硬 guard)。
- bundle/installer 契约 (build_skill_bundle / wrapper / `--install` staged 覆盖) 见 CONTRACTS「agent-only core / extras 边界」段。触碰 high-risk `agent_skill_init`。

## D-105.1
**形态A 彻底退役 + stdout 泄漏修复.** (2026-05-30) · 志丹拍板 "形态A 不要了, 回滚靠 git"。
- **删 uv tool 入口**: pyproject `[project.scripts]` 双 console + wheel force-include/exclude 整块删 (仅留 editable `uv run` dev 用); 接入唯一形态 = B 自包含 bundle, 回滚靠 git 不留 A 装包路径。
- **stdout 泄漏修复**: `refine_intent_v2.py` 3 处 fallback `print()` 改 `file=sys.stderr`, 兑现 "stdout 一律 JSON" 契约。
- **AGENTS.md 已重写为形态B (2026-05-30 跟修)**: 原 404 行 form A 协议整份重写成形态B (拷 bundle + wrapper 调用, 与 SKILL.md 单一源对齐); 协议层保留。**仍未做**: B 形态**远程分发协议** (非维护者、无 repo 的 agent 如何拿 bundle) D-105 §2 列为非目标、未设计 — 现以 AGENTS.md §1 NO_BUNDLE 模板诚实兜底, 待定型后补。

## D-106
**命名收敛 — skill 名 + 包分发名 `chisha-meal` → `chisha`.** (2026-05-31) · 志丹拍板 "chisha-meal 别扭"。
- **病根**: `chisha`=拼音(吃啥)、`-meal`=英文(餐), 中英混搭; 且 `chisha` 已含"吃啥"语义, 再缀 `meal` 是同义重复。曾用名源于形态A `uv tool install` 包名 (AI 取, 一路延续)。
- **改动**: 全局字面替换 `chisha-meal`→`chisha` (17 文件): skill 目录名+frontmatter `name:`+`/chisha` slash (`SKILL_DIR_NAME`×2)、pyproject `[project].name`+self-ref、全文档/测试。`uv.lock` 走 `uv lock` 重生成; `.gitignore` wheel 产物名 (`chisha_meal-*`→`chisha-*`, 下划线变体单独补)。
- **零逻辑改动**: Python **import 名一直是 `chisha`** (只分发名/skill 标识变); state root `~/.chisha/` 本就不带 meal, **数据零影响**; 重装 skill = 删旧 `~/.claude/skills/chisha-meal/` + `--install` 到 `~/.claude/skills/chisha/`。
- **曾用名锚点**: D-103/D-105/D-105.1 等历史条目内旧名已随本次同步更新; `chisha-meal` 作为 2026-05-31 前的 skill/包曾用名, 在此一处备查 (不在散落历史保留, 防"名字没消失")。

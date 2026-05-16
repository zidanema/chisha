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
**工具 / 调试**: [D-039](#d-039) · [D-028](#d-028)

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

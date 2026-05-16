# 今天吃点啥 · 决策日志

> 这份文档记录每一个关键的**产品方向 / 架构原则 / 方法论 / schema 设计**决策——**不只记录决定，还记录考虑过的替代方案和判断标准**。
> 目的是消灭"假上下文"——避免未来的我或 Claude Code 凭空脑补。
> 新决策追加在尾部，旧决策不删（即使被推翻，也保留并标注 superseded）。
>
> ## 判别准则（写哪边）
>
> 问自己：**半年后做下一次大重构时，会不会回头查这条？**
> - 会查 → 写到本文件：产品方向选择、架构原则、schema 设计、方法论权衡、推翻历史
> - 不会查 → 写到 [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md)：实现选择、参数微调、prompt 改了几行、batch 数 / timestamp、回填脚本、bug 排查
>
> 决策日志只留"考虑过的方案 / 决定 / 理由 / 触发重审"；工程日志才放"执行进度"流水。
>
> 工程实施类条目（D-042 / D-045 / D-046 / D-046.1 / D-047 等）已迁至 [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md)，本文件仅保留 stub 指针保编号连续性。
>
> 项目名：今天吃点啥 · 代码名：`chisha`

---

## 决策模板

每条决策按以下格式记录：

```
## D-NNN: 一句话标题
日期: YYYY-MM-DD
状态: active | superseded by D-XXX | reverted
背景: 是什么情况下做的这个决定
考虑过的方案:
  A. ... 
  B. ...
决定: 选 X
理由:
  - ...
  - ...
反对意见 / 风险:
  - ...
触发重审的条件: 什么情况下应该回头看这条决策
```

---

## D-001: V1 走开源 Skill 而非 SaaS 平台
日期: 2026-05-10
状态: active
背景: 讨论"开放给别人用"的形态时，最初按互联网厂商思路默认做 SaaS。

考虑过的方案:
- A. SaaS 平台（用户调你的 API，你跑服务器，托管用户数据）
- B. 开源 Skill / Agent（用户本地跑代码，本地存数据，作者完全不参与运行）
- C. 混合（核心 SaaS + 开源 SDK）

决定: B —— 开源 Skill。

理由:
- 0 运营成本（不维护服务器、不处理用户系统、不背 SLA）
- 隐私彻底（用户数据完全本地，作者不接触）
- 容易传播、容易 fork、容易二次开发
- 单用户的协同推荐没意义，没必要做"平台"
- 用户保有完全控制权

反对意见 / 风险:
- 商业化路径变窄
- 接入门槛对非开发者偏高（但目标用户就是开发者，可接受）

触发重审的条件:
- 真的有非开发者群体强烈需要时
- 数据采集成本想用付费回收时

---

## D-002: 数据层（L1）和推荐层（L2）独立分发
日期: 2026-05-10
状态: active
背景: 数据采集成本高，推荐方法论代码轻量。两者强行打包会导致：要么数据更新带着代码升级（用户烦），要么代码升级带着数据下载（包大）。

考虑过的方案:
- A. 一体化包发布
- B. L1 数据 + L2 代码 两个独立包，互相依赖

决定: B —— L1 `chisha-data`（pip 包，含数据） + L2 `chisha`（开源仓库，含代码）。

理由:
- 数据集中维护：作者一人维护质量，使用者不用各自爬
- L2 方法论代码可以独立演进，不绑死数据版本
- 第三方可以"只用数据不用推荐算法"或反之
- 区分"作者维护的"和"社区共建的"

反对意见 / 风险:
- 两个仓库的版本兼容性管理增加复杂度
- 用户首次安装需要装两个包

触发重审的条件:
- 包间版本兼容问题成为运维痛点

---

## D-003: V1 不做 CLI 包装，直接 Python import
日期: 2026-05-11
状态: active
背景: 之前讨论过把 L1 做成 CLI 工具（类似 feishu-cli）。但本质上 V1 阶段只在自己 Mac 上跑，自己用，不需要跨语言、不需要进程隔离。

考虑过的方案:
- A. CLI 形式（subprocess 调用）
- B. Python 库（import 调用）
- C. 两者都给

决定: V1 用 B；V2 视情况加 A。

理由:
- V1 自己用，import 比 subprocess 简单一个数量级
- 接口签名按 JSON 入参出参标准设计，未来包成 CLI 平凡
- 避免过早优化"未来给同事用"这件事

反对意见 / 风险:
- 同事接入时还得装 Python 环境（但目标用户都是开发者，可接受）

触发重审的条件:
- 给同事用且同事不写 Python 时
- 想用其他语言写 Agent 调用时

---

## D-004: V1 不做反馈系统，用纸笔记
日期: 2026-05-12
状态: active
背景: 反馈系统涉及 personal_offsets 写入、多个评分维度、UI 交互。在推荐质量未验证前实现，是浪费。

考虑过的方案:
- A. V1 直接做完整反馈系统（5 星 + tags + 自由文本）
- B. V1 简化反馈（只 1-5 星）
- C. V1 不做，自用一周记纸笔，根据实际感受设计 V2

决定: C —— 不做。

理由:
- 推荐质量是 1，反馈是 0。1 没立起来，0 都是浪费
- 自用一周后，对反馈系统该长什么样会有更具体的判断
- 避免"做了反馈系统但反馈数据不够多，不起作用"的尴尬

反对意见 / 风险:
- V1 一周内不能根据反馈调整推荐
- 但 V1 本来就是验证推荐基础质量，不需要个性化反馈调整

触发重审的条件:
- V1 跑通后立即启动 V2.0 反馈系统设计

---

## D-005: 推荐采用召回 + 打分 + 精排三阶段
日期: 2026-05-11
状态: active
背景: 一种朴素思路是把所有候选丢给 LLM 让它推。但商品几千上万条，token 爆炸且 LLM 在大候选池做约束满足效果差。

考虑过的方案:
- A. 全量丢 LLM
- B. 纯规则推荐
- C. 召回（规则）→ 打分（公式）→ 精排（LLM）三阶段

决定: C。

理由:
- 召回保证硬约束（多样性、油脂、价格），代码可调试可单测
- 打分编码领域知识（餐盘比例、销量、个人偏移），可解释
- LLM 只做小候选集挑选 + 写理由，是它擅长的事
- 三阶段每段可独立优化，不会牵一发动全身

反对意见 / 风险:
- 实现复杂度高于纯 LLM 方案

触发重审的条件:
- LLM 上下文进步到能直接处理万条候选时（届时召回阶段的价值降低）

---

## D-006: 召回宽过滤，软约束进打分
日期: 2026-05-12
状态: active
背景: 油脂、蔬菜比这些约束，做硬过滤还是进打分？

考虑过的方案:
- A. 严过滤（油脂 > 3 直接砍）
- B. 宽过滤 + 软打分（偏油负分但可入选）

决定: B。

理由:
- 用户的方法论是"结构正确"（餐盘比例），不是"绝对低脂"
- 一道偏油肉菜配大量蔬菜，整体仍然合规
- 严过滤会把"偶尔吃一次也无妨"的好菜永远排除
- 软打分让 LLM 在精排时有更多取舍空间

反对意见 / 风险:
- 偶尔会推出油脂偏高的组合
- 缓解：精排 prompt 中明确要求多样化和控油倾向

触发重审的条件:
- 实际使用中发现"推得太油"的反馈集中出现时

---

## D-007: 召回 100 个候选，首推 5 个（V2 起）
日期: 2026-05-12
状态: active
背景: 召回多少？精排出多少？这是个 token 成本和多样性的取舍。

考虑过的方案:
- A. 召回 30，推 3
- B. 召回 100，推 5
- C. 召回 200，推 5

决定: B（V1 简化为召回 100、推 3）。

理由:
- 100 候选 × 200 token = 20k token，Sonnet 上下文绰绰有余
- 多召回的多样性收益大于 token 成本
- 推 5 个比 3 个让用户有更多选择空间，refine 后回到 3

反对意见 / 风险:
- 单次推荐成本约 ¥0.1，每月 ¥6，可接受

触发重审的条件:
- LLM API 成本显著上升时

---

## D-008: 商品打标 LLM 必须看到价格
日期: 2026-05-12
状态: active
背景: 同名菜在不同店有不同价格档位（"水煮牛肉 28 元小份" vs "水煮牛肉 68 元大份"）。protein_grams_estimate 等字段强烈依赖分量。

考虑过的方案:
- A. 价格归一公式（每 10 元 ≈ X 克蛋白）
- B. LLM 看价格判断
- C. 忽略份量，靠反馈校准

决定: B。

理由:
- LLM 已经要打标，多带个 price 字段成本 = 0
- 准确度比固定公式高得多（不同品类的价格-蛋白曲线不同）
- 比起反馈校准，前期准确性更好

反对意见 / 风险:
- 同名菜在不同店估出来不一致（但本来就该不一致，不同店分量不同）

触发重审的条件:
- 反馈系统建立后，发现 LLM 对分量的估算系统性偏差时

---

## D-009: 打标 temperature=0、批次 30-50 条
日期: 2026-05-12
状态: active
背景: LLM 打标的可复现性和准确性问题。

决定:
- temperature 必须设 0
- 每批 30-50 条菜
- JSON 输出做 try/except + 重试

理由:
- 同一道菜跑两次结果不一致会污染数据
- 批次太大注意力分散，准确率下降
- Sonnet 输出 JSON 偶尔会坏，必须有兜底

反对意见 / 风险: 无

---

## D-010: 反馈拆成"好吃度"和"整体满意"两个星级
日期: 2026-05-13
状态: active（V2 启用）
背景: 一开始打算只做一个"满意度"。但满意度其实是综合体验（好吃 + 分量 + 配送 + 心情）。一道菜可能很好吃但分量小（满意 3，好吃 5）。

考虑过的方案:
- A. 一个综合星级
- B. 拆成两个独立星级

决定: B。

理由:
- 两个维度判断标准不同，混在一起会污染数据
- "好吃度"直接进 personal_offsets.score_offset 影响下次推荐
- "整体满意"只进 meal_log，由 learned_profile 蒸馏长期信号
- 二者分歧时（好吃 5 满意 2），LLM 加工时能推断原因（多半是分量、配送）

反对意见 / 风险:
- 用户填两个星级摩擦稍高
- 缓解：UI 上做成快速点选，5 秒内完成

触发重审的条件:
- 实际使用发现两个星级高度一致时（说明拆分意义不大）

---

## D-011: 自由备注作为"escape hatch"
日期: 2026-05-13
状态: active（V2 启用）
背景: 选项型反馈覆盖 80% 场景，但偶尔有"今天牛肉很柴这家以后别推了"这种系统没法用选项捕捉的判断。

考虑过的方案:
- A. 只做选项，限制用户输入
- B. 选项 + 自由文本（类似 Claude Code Plan mode 的交互）

决定: B。

理由:
- 结构化字段对结构化数据，文本对非结构化洞察
- 自由备注存进 meal_log.feedback.note，由 learned_profile 加工时蒸馏成 insights
- 用户偶尔表达，不强制

反对意见 / 风险: 无

---

## D-012: learned_profile 加工层（系统蒸馏画像）
日期: 2026-05-13
状态: superseded by D-026（"加工层"概念保留，但 LLM 蒸馏改成统计聚合）
背景: meal_log 长期增长后无法全量塞精排 prompt。需要一个画像蒸馏层。

考虑过的方案:
- A. 永远只看最近 N 天
- B. 系统每周加工 learned_profile，蒸馏长期信号
- C. 实时加工

决定: B。

理由:
- 长期画像（"用户偏爱炖煮、不爱干煸"）比单点记录更有价值
- 每周一次低频，token 成本可忽略
- 加工产物可读、可手工编辑、可调试

反对意见 / 风险:
- LLM 蒸馏可能产生噪音洞察
- 缓解：每次加工时输入上一版作为参考，避免漂移

触发重审的条件:
- 加工产物质量长期不准时

---

## D-013: 未反馈数据的混合权重策略
日期: 2026-05-13
状态: active（V2 启用）
背景: 用户接受推荐但没填反馈的餐次，要不要算入历史画像？

考虑过的方案:
- A. 静态：只用有反馈的数据
- B. 动态：所有进餐都算
- C. 混合：按数据可靠度加权

决定: C。

权重表:
- 有 feedback 的餐：1.0
- 接受推荐但未 feedback：0.3
- 自己 log_meal 未 feedback：0.2
- 推荐但被拒绝：0.5（负向）

理由:
- 静态样本太稀疏
- 动态会失真
- 加权混合 = 既不丢数据也不被噪音淹没
- 多样性约束（7 天不重复商家等）所有进餐都计入，不区分权重

反对意见 / 风险: 无

---

## D-014: profile.taste_description 用自然语言而非结构化字段
日期: 2026-05-13
状态: active
背景: 一开始打算 seed_dishes 字段（列 5-10 道锚点菜）。但发现自然语言描述更高效。

考虑过的方案:
- A. 结构化字段（liked_dishes 列表 + tags）
- B. 自然语言段落
- C. 两者并行

决定: C。

理由:
- 自然语言能表达"喜欢炖煮、不爱干煸"这种**模式**信号
- 结构化字段对懒得写文字的人也友好
- LLM 在精排时更容易从自然语言里推断多维偏好

反对意见 / 风险:
- 自然语言段落不能被代码逻辑硬约束
- 缓解：硬约束（avoid_dishes、spicy_tolerance）单独结构化字段

触发重审的条件: 无

---

## D-015: 探索机制默认启用（5 中有 1-2 个 explore）
日期: 2026-05-13
状态: active（V2 启用）
背景: 打分系统天然让"打高分的菜越推越多"，没吃过的菜永远不被推。经典 explore-exploit 问题。

考虑过的方案:
- A. 不做探索，严格按打分推
- B. 3 中抽 1 探索
- C. 5 中抽 1-2 探索

决定: C。

理由:
- 5 个候选给探索更多空间
- 探索候选不接受不扣分（本来就是探索）
- 接受且高分则大幅加分（强化学习）
- Refine 时不做探索（用户已有方向，无关探索是干扰）

反对意见 / 风险:
- 探索菜如果体验差会增加摩擦
- 缓解：探索候选选打分中段（前 50%），不会是垫底

触发重审的条件:
- 用户连续多次拒绝探索候选时

---

## D-016: V1 不做"训练日感知"
日期: 2026-05-14
状态: active
背景: 用户在减脂增肌期，理论上训练日和非训练日吃法可以不同（练后多蛋白、不练降碳水）。

考虑过的方案:
- A. V1 就建模训练状态
- B. V1 不做，统一按 1/2 + 1/4 + 1/4

决定: B。

理由:
- 增益相对小（除非训练强度极高）
- 增加复杂度（要维护训练日历、要 Agent 感知今天练没练）
- 哈佛餐盘方法论本身在训练日和非训练日都成立
- 等 meal_log 攒够了，再评估要不要加这一层

触发重审的条件:
- 训练强度大幅增加时
- learned_profile 显示训练日和非训练日吃法明显不同时

---

## D-017: V1 不做 Web URL 渲染层
日期: 2026-05-14
状态: superseded（之前以为要做"L3 渲染层"，后来意识到渲染本来就是 Agent 的事）
背景: 一度规划了"L3 渲染层"，把 JSON 渲染成飞书卡片 / Web URL / Markdown。

考虑过的方案:
- A. Skill 自带渲染层
- B. Skill 只输出 JSON，渲染交给 Agent

决定: B。

理由:
- 不同 IM 渲染需求差异大，Skill 强行做会被绑死
- Agent 本来就要包装一层（因为它要管推送时机、IM 通道），渲染顺手做
- Skill 保持纯粹"推什么菜"的引擎，更容易被各种 Agent 接入

反对意见 / 风险:
- 接入方需要自己写渲染
- 缓解：在 docs/examples 里给 Markdown / 飞书卡片的参考实现

触发重审的条件: 无

---

## D-018: V1 接入 Claude Code 而非 OpenClaw
日期: 2026-05-14
状态: superseded by D-022（2026-05-11 复盘后翻案，见下文）
背景: 选哪个 Agent 作为 V1 首接入？

考虑过的方案:
- A. OpenClaw（你日常主用）
- B. Claude Code（Skill 机制成熟）
- C. 都做

决定: B 优先。

理由:
- Claude Code 的 Skill 机制成熟，写 Python 函数 + Markdown 描述就能跑
- OpenClaw 涉及 MCP 协议、IM 通道，复杂度高一档
- V1 验证推荐质量为主，不需要复杂接入
- V2 阶段再接 OpenClaw（届时 MCP Server 也好做）

反对意见 / 风险: 无

触发重审的条件: 无

---

## D-019: 数据 V1 阶段不做 PyPI 发布
日期: 2026-05-14
状态: active
背景: 之前讨论 L1 用 pip 发布。但 V1 是自用阶段，本机 import 即可。

考虑过的方案:
- A. V1 就发 PyPI
- B. V1 本地 import，V2+ 才发 PyPI

决定: B。

理由:
- V1 用户只有自己，发 PyPI 是浪费
- 数据格式可能在自用一周后调整，过早发布徒增包管理成本
- V1 跑通且数据格式稳定后再发布

反对意见 / 风险: 无

触发重审的条件:
- 同事开始用且需要安装包时

---

## D-020: 文档体系四份分立
日期: 2026-05-14
状态: active
背景: 设计文档（DESIGN）+ 决策（DECISIONS）+ 需求（PRD）+ 路线图（ROADMAP）应该分立还是合在一起？

考虑过的方案:
- A. 一份大 DESIGN 全包
- B. 四份分立

决定: B。

理由:
- 不同读者关心不同部分（产品定位、实现细节、决策思考、未来规划）
- 不同更新节奏（PRD 几乎不变，DESIGN 每个版本一份，DECISIONS 持续累积，ROADMAP 持续更新）
- 进 Claude Code 后，让 Agent 知道有这四份能引导它建立完整上下文，避免脑补

反对意见 / 风险:
- 维护成本略高
- 缓解：README 作为入口聚合所有链接

触发重审的条件: 无

---

## D-021: 项目采用双名策略（今天吃点啥 + chisha）
日期: 2026-05-14
状态: active
背景: 起初代码层用 `meal-agent` / `meal-data` / `meal_skill`，但和"今天吃点啥"这个对人称呼脱节。需要明确产品名和代码名的关系。

考虑过的方案:
- A. 全部统一成英文（meal-agent / meal_agent）—— 工程化但失去温度
- B. 全部统一成中文（今天吃点啥）—— 暖但 GitHub / pip / import 不友好
- C. 双名策略：产品名「今天吃点啥」对人 + 代码名 `chisha` 对机器

决定: C。

命名映射:
- 项目名（标题、对外说、PRD、宣传）：今天吃点啥
- 主仓库名：`chisha`
- L2 推荐层 Python 包：`chisha`（`from chisha import api`）
- L1 数据层 Python 包：`chisha-data`（pip）/ `chisha_data`（import）
- 项目目录：`chisha/`

理由:
- 双名是 ripgrep / vscode / k8s 这类优秀工具的常见做法
- 产品名「今天吃点啥」保留温度和共鸣，对话里同事一听就明白
- 代码名 `chisha` 拼音化干净，pip / import / CLI 都自然
- 未来即使产品改名，repo 名 `chisha` 仍然可用，不需要改包名

反对意见 / 风险:
- 同时维护两个名字略增加文档负担
- 缓解：在每份文档头部都明确"项目名：今天吃点啥 · 代码名：chisha"

触发重审的条件:
- 项目英文化国际推广时，可能需要再起一个英文产品名

---

## D-022: V1 接入 OpenClaw + 飞书卡片（取代 D-018）
日期: 2026-05-11
状态: partial superseded by D-051（2026-05-15 — 飞书"主交互"降级为"V1.5 推送+deeplink 通道"，V1 主交互改 Web SPA）;
       **further superseded-pending by D-074**（2026-05-16 战略共识 — V1.5 独立飞书通道砍, 飞书归 Phase 0 reference adapter 一部分; 待 Step 2 完成后落 D-074, 详见 [docs/design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md](../docs/design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md)）

背景: D-018 当初为了规避 MCP/IM 复杂度选 Claude Code 优先。但复盘 PRD §5 故事 1 后发现：
- Claude Code 是 CLI/IDE 形态，不能主动推送
- 用户得自己 11:25 打开终端敲命令，"决策疲劳"省掉的部分大幅缩水
- 这等于把产品最核心的"主动推卡片"承诺打到 5 折，V1 就走样

考虑过的方案:
- A. 维持 D-018，V1 接 Claude Code，V2 再上 OpenClaw
- B. V1 直接接 OpenClaw + 飞书卡片，承担 IM 集成复杂度
- C. V1 同时接两个

决定: B。

理由:
- 用户的真实形态是长程 Agent（OpenClaw / HappyClaw）+ 飞书 IM 卡片
- OpenClaw 飞书集成已存在，复杂度比当初评估的低
- 推荐质量验证 + 触发场景验证应该一起做。先做 Claude Code 验证质量，再换 OpenClaw 验证形态——等于跑两遍冷启动
- Claude Code 接入推迟到 V2.3（用户主动 query 场景，而非主动推送）

反对意见 / 风险:
- V1 必须搞定 OpenClaw skill 接入 + 飞书卡片渲染 + cron 调度，工作量增加约 3-5 天
- 飞书 deeplink 跳转有兼容问题（坑 13）

触发重审的条件:
- OpenClaw 飞书集成出现重大变更或不可用时

---

## D-023: 餐盘策略改弱约束（控油 + 蔬菜下限 + 蛋白下限）
日期: 2026-05-11
状态: active

背景: 原 PRD/DESIGN 主张"严格 1/2 蔬菜 + 1/4 蛋白 + 1/4 主食"。但中式外卖现实下：
- 单道盖饭/粉面（最高频形态）天然达不到 50% 蔬菜
- 拼 2-3 道菜：客单 60-100+，分量过大、剩饭、配送费翻倍
- 召回阶段强行凑严格比例 = 候选池被砍到不可用

用户接受："推出来的菜可以多一点，自己在饭桌上控制比例。客单 60-100+ 可接受，吃不完是可接受代价。核心是好吃 + 长期坚持。"

考虑过的方案:
- A. 维持严格 1/2-1/4-1/4 硬约束
- B. 弱约束三件套：控油 + 至少 1 道蔬菜 + 蛋白下限，自己在吃的时候调比例
- C. 限品类（只推天然带蔬菜的健身餐 / 日式定食）

决定: B。

理由:
- 中式外卖的现实约束 = 严格比例不可达
- 用户的真实需求是"健康结构 + 好吃"，不是"分子级营养比例"
- 弱约束让候选池保持丰富，召回不被卡死
- "吃饱瘦"的"吃饱"本来就和"严格控量"冲突
- 北极星是连续采纳率，不是营养精度

反对意见 / 风险:
- 可能推出蔬菜偏少的组合（缓解：召回硬过滤"至少 1 道 vegetable_ratio_estimate ≥ 0.6"）
- 用户需要主动在饭桌上"多吃菜"，有自律成本

触发重审的条件:
- 用户连续 2 周采纳率 ≥ 60% 但反馈集中在"蔬菜不够"
- 用户体重/体脂数据显示策略失效（虽然不是优先指标，但可以作为信号）

---

## D-024: V1 精排 = 打分 top 3 + LLM 只写 reason
日期: 2026-05-11
状态: **superseded by D-049 (2026-05-14)** — V1 简化路径代码已删, V2 (D-033 起) 是唯一推荐链路. 当时"LLM 在严格规则上不稳, 先用打分 top 3 起步"的决策本身仍然合理 (V2 在 tool_use forced schema 和 enforce_brand_unique 兜底后才稳到 17/18). 但 V1 baseline 保留的初衷 (V2 翻车时降级) 已不需要 — V2 自身有 fallback_rerank 规则路径兜底, 不依赖 V1 入口.

背景: D-005 决定"召回 + 打分 + 精排（LLM）"三阶段，但 V1 阶段：
- LLM 在"严格执行规则"和"挑哪 3 个"上不稳，引入随机性
- 打分公式已经能选出靠谱 top 3
- LLM 在"写理由"上反而最擅长

用户在挑战中指出"不能盲点"，需要个性化数据，但 V1 没有 meal_log 数据，LLM 精排无信号可用。

考虑过的方案:
- A. V1 就让 LLM 在 100 候选里挑 3 个（原 D-005 默认）
- B. V1 直接取打分 top 3，LLM 只写 reason；V2.x 再开 LLM 精排
- C. V1 完全不用 LLM（连 reason 也写规则）

决定: B。

理由:
- 召回 100 + 打分排序 ≈ 已经是确定性的最优解
- LLM 选 3 个引入的随机性 + 漂移 > 它带来的"灵活理解 taste_description"价值
- LLM 留着干"写一句具体的人话理由"——这是它最值得做的事，且成本极低（< ¥0.05/次）
- V2.0 反馈数据攒起来后，V2.1 再开 LLM 精排，这时 LLM 有 learned_profile 输入，价值才显现

反对意见 / 风险:
- V1 的推荐对 taste_description 不敏感（自然语言偏好不直接进打分公式）
- 缓解：V1 通过 cuisine_preference 字段间接编码偏好，taste_description 只在 reason_one_line 里被 LLM 看到

触发重审的条件:
- V1 自用一周后发现 top 3 重复严重 / 与 taste_description 错位明显
- V2.0 反馈数据攒起来后立即重审

---

## D-025: personal_offsets 粒度从"店::菜"改"(cuisine, cooking, ingredient)"
日期: 2026-05-11
状态: active（V2.0 启用）

背景: 原 D-010/D-013 默认 offset 粒度是 `restaurant_id::canonical_name`。但单菜样本量 N=1~5 时：
- offset 信号比噪音弱
- 一道菜在一家店反馈 1 次，不足以建立可靠偏好
- 同名菜跨店的"做法差异"反而被分散，看不出系统模式

考虑过的方案:
- A. 维持"店::菜"粒度
- B. 改"菜系::烹饪方式::主料"粒度（统计聚合）
- C. 双粒度并行（店级 + 维度级）

决定: B。

理由:
- 维度粒度下，每个维度的样本量能积到 N≥10，统计意义出来
- 用户真实偏好规律本来就是"喜欢炖煮"、"不爱干煸"——这是维度级模式
- 极端坏菜（特定店的特定菜连续低评分）单独走 blacklist，不靠 offset 处理
- 简单度量：粒度 = (cuisine, cooking_method, main_ingredient) 三元组

反对意见 / 风险:
- 维度聚合可能掩盖店间差异（"湘菜炒"包含 A 店做得好 + B 店做得差）
- 缓解：blacklist 单独维护具体店的具体菜

触发重审的条件:
- 用户反馈中"同样维度但 A 店好 B 店差"的现象集中出现
- 6 个月后维度聚合的 N 仍然 ≤ 5（说明数据不够）

---

## D-026: learned_profile 改统计聚合，删 LLM 蒸馏 insights
日期: 2026-05-11
状态: active（V2.2 启用，取代 D-012 中的 LLM 蒸馏部分）

背景: D-012 计划让 LLM 每周从 meal_log 蒸馏 learned_insights（自然语言洞察）。但：
- N=1 单用户 + 87 餐数据 = 统计量极弱
- LLM 蒸馏容易出过拟合假规律（"周一周二倾向清淡"——很可能是 1-2 个数据点凑的伪信号）
- 蒸馏出来的洞察不可解释、不可手编、容易漂移

考虑过的方案:
- A. 维持 D-012：LLM 蒸馏 insights（自然语言）
- B. 纯统计聚合（top_preferences / bottom_preferences / blacklist）
- C. 统计聚合 + LLM 写一段总结性文字（summary_for_llm）作为精排 prompt 输入

决定: C。

理由:
- 统计聚合可解释、可手编、不漂移
- 统计 top/bottom 维度直接进打分（learned_top_pref_bonus / learned_bottom_pref_pen）
- summary_for_llm 是统计结果的人话化总结，输入精排 prompt 用，不是 LLM 自由发挥的"洞察"
- 用户可以手动覆盖 summary_for_llm（比如"我最近开始喜欢清炒"，统计还没反应过来时手编）

反对意见 / 风险:
- 失去 LLM 可能发现的"潜在模式"（但 N=1 数据下这种模式 99% 是噪音）
- summary_for_llm 仍然让 LLM 写，但限定输入是统计结果，不是原始 meal_log

触发重审的条件:
- 用户连续要求"想找出的偏好规律统计聚合没看到"
- 数据量超过 500 餐时（届时 LLM 蒸馏可能有意义）

---

## D-027: 数据来源边界（sister project chisha-collector 维护）
日期: 2026-05-11
状态: active

背景: 整套文档原本对"数据从哪来 + 怎么保鲜"避而不谈。用户澄清：数据采集由独立项目维护，15 天保鲜频度，本项目不负责采集。

考虑过的方案:
- A. 本仓 chisha 同时负责采集 + 推荐（一站式）
- B. sister project chisha-collector 负责采集 / 清洗 / 打标 / 保鲜，chisha 只消费
- C. 不约定，按需爬

决定: B。

理由:
- 采集和推荐是完全不同的工程（采集 = 反爬 / 清洗 / 调度 / 法务；推荐 = 算法 / Agent 集成）
- 分仓让两边各自独立演进、独立发版
- chisha 开源时不需要带采集代码（避免 ToS 风险扩散到推荐侧）
- collector 输出的 schema 由两边约定（restaurants.json + dishes_raw.json），是合同

反对意见 / 风险:
- chisha 用户必须先有 collector 输出（或自己实现等价 collector），上手门槛 +1
- 缓解：作者维护一份 collector 输出的样例数据，可下载

触发重审的条件:
- collector 项目停止维护 / schema 大幅不兼容
- 数据保鲜周期实际效果差（菜单沽清/改价导致推荐失效）

---

## D-028: 北极星指标修正（用连续采纳率替代决策时间）
日期: 2026-05-11
状态: active（取代原 PRD §6 决策时间口径）

背景: 原 PRD 北极星是"决策时间从 15 min 降到 1 min 以内"。问题：
- 不可度量（用户停止刷美团了不代表产品起作用，可能就没点外卖）
- 易作弊（用户改流程不是产品功劳）
- 与 V1 形态错位：V1 接 OpenClaw 主动推送，"决策时间"分母都不存在

考虑过的方案:
- A. 维持原口径
- B. 改成"7 日连续工作日采纳率 + 餐后好吃度 4 星比例"
- C. 改成体重/体脂目标

决定: B。

理由:
- 采纳率可度量、不可作弊（产品推 3 个，用户接受 1 个 = 信号干净）
- 好吃度 4 星反映长期可坚持性
- 体重/体脂受太多因素影响（PRD §6 已经把它列入"不优先指标"）
- V1 自用 1 周就能算 7 日采纳率，验证窗口短

V1 目标: 工作日 7 日连续采纳率 ≥ 50%
V2 目标: ≥ 60% + 餐后好吃度 ≥ 4 星比例 ≥ 70%

反对意见 / 风险:
- "采纳"定义需要明确：用户点了"选 1" = 采纳；忽略卡片 = 未采纳；"重新推" = 介于之间
- 缓解：V2.0 反馈系统起来后，"重新推 → 选 1" 计采纳但权重降低

触发重审的条件:
- 反馈数据起来后，发现"采纳但餐后差评"频繁（说明采纳率不够）

---

## D-029: profile.spicy_tolerance 改整数 0-3
日期: 2026-05-11
状态: active

背景: 原 profile.yaml 中 `spicy_tolerance: 中辣`（中文文字），但 dish.spicy_level 是整数 0-3，匹配规则没定义。这是文档自身的不一致。

考虑过的方案:
- A. profile 用文字，召回时做映射表
- B. profile 直接用整数，与 dish 字段类型对齐
- C. 都支持

决定: B。

理由:
- 文字映射多一层易错（"中辣" 是 1 还是 2？）
- 整数比较代码 1 行
- 用户写 yaml 时旁边注释说明（0=不辣 1=微辣 2=中辣 3=重辣）

匹配规则: 召回时 `dish.spicy_level > profile.spicy_tolerance` 硬过滤。

反对意见 / 风险: 无

触发重审的条件: 无

---

## D-030: 数据链路重构推迟到 V1 跑完后做（推翻 D-027 sister project 方向）
日期: 2026-05-11
状态: deferred（方向已定，动手时机延后）

背景:
- D-027 把数据采集划到 sister project chisha-collector 维护，但事实是当前 `~/waimai_data` 只做"raw 采集"，归一化（loader）+ 打标（tag_dishes / tag_via_subagent）都还住在 chisha 仓里。L1/L2 边界是文档承诺，不是事实。
- 现在 shenzhen-bay 打标只覆盖 46.3%，21 家店被 collector 漏抓菜单；先把这部分跑顺比讨论架构重要。

考虑过的方案:
- A. 现在就重构：把 waimai_data 接管成 chisha-collector，搬出 loader/tag_*
- B. 现在不动，先聚焦把 shenzhen-bay 打标补齐 + 推荐链路自用跑通；V1 完成后再做架构重构
- C. 推翻 D-027，把 collector 拉回 chisha 仓作为独立子模块（三段：采集 / 清洗打标 / 对外数据服务）

决定: 当前聚焦 B（专注主线），重构方向采纳 C（V1 跑完后启动）。

重构方向（V1 后执行，预留 V1.5 阶段）:
- chisha 单仓三个独立子模块：
  - `chisha/collector/` ← 接管 waimai_data，负责真机采集（uiautomator2 / 美团）输出 raw
  - `chisha/cleaning/` ← 当前 `chisha/loader.py` + `scripts/tag_*` 的逻辑，负责 raw → §5.2 schema + 打标
  - `chisha/data_service/` ← 清洗后数据如何对外（CLI / pip 包 / MCP）
- 三个子模块之间靠 schema 契约（§5.2）解耦；推荐层（chisha 现有 recall/score/api）只消费 data_service
- 这反向修正 D-027 的"sister project"方向：合并比分仓更适合一人维护的项目

理由:
- V1 主线是验证推荐质量，不是验证架构；现在动架构会拖慢主线 1-2 周
- 一人维护两个仓的成本（schema 同步、双 CI、双发版）比单仓三子模块高
- 当前 waimai_data 实际上是 collector 的一半，"分仓"只是地理位置区别，不是真正的解耦
- 单仓三子模块仍然保留可拆分性：未来若要开源采集逻辑，按 module 抽出即可

反对意见 / 风险:
- 合并后 chisha 仓带上反爬 / ToS 风险代码，开源时需要谨慎
- 缓解：data_service 子模块单独发包，采集子模块只在内部分支保留

触发立刻执行的条件:
- V1 工作日 7 日采纳率 ≥ 50%（D-028 北极星 V1 目标）已通过
- 或：shenzhen-bay 数据被 collector schema 不兼容更新打挂 ≥ 2 次

V1.5（重构阶段）任务清单见 ROADMAP.md。

---

## D-031: tag_dishes prompt v2 升级（5 项改动 + 全量重打）
日期: 2026-05-11
状态: active

背景:
两轮独立 review 揭示旧 prompt（v1）有结构性问题：
- 我（全量统计 9373 条）发现：canonical_name 残留 5.3% / 套餐误归"主食"219 条 / 同名菜跨店 cuisine 不一致 242 个名字。
- Codex（独立 30 条 spot check）发现：12/30 = 40% violation，主要在凉拌锚点（L49 默认偏 oil=2）/ tags 集与 example 自相矛盾 / canonical 残留促销词 / 套餐 cooking_method 取了非最油工艺。
- 旧打标还隐藏 LLM 幻觉问题：含糊套餐名 (d_013_043 "恰巴塔 4 件套"、d_010_031 "商务自选套餐") 被打成完全不相关的"烤鲜活鲍鱼"、"王老吉"。

考虑过的方案:
- A. 不改 prompt，召回阶段加兜底规则（complete_meal+主食类强制叠蔬菜等）
- B. 改 prompt 全量重打两个 zone（home + shenzhen-bay）
- C. 只改高优 3 项，低优 2 项留 V1.5
- D. 改 schema 扩 cuisine 16 类（加京菜/本帮）配合重打

决定: B —— 5 项一起改 + spike 50 条验证通过 + 全量重打。

理由:
- A 治标不治本：幻觉菜名（d_013_043 → "烤鲜活鲍鱼"）这种问题不可能在召回层修
- C 边际成本反而高：5 项一起改 + 一次重打 vs 分两次改 + 两次重打
- D 改 schema 影响范围大（同步动 DishTagged cuisine enum、所有现有 tagged 数据迁移、D-025），推 V1.5；现 V1 用"快餐/其他"兜底够用

5 项改动（对应 prompts/tag_dishes.md）:
1. **L94 vs L113 tags 集自相矛盾修复**：example 里 "主食" → "高碳水"，集合保持原样（Codex 主张）
2. **L40 加套餐处理规则**：多份组合套餐 / 件数套餐 / 双拼按主菜定 main_ingredient + cooking_method，多种工艺取最油的；鸡排堡套餐归白肉不归主食（共识）
3. **L86-91 canonical_name 加促销词清单**：明确删除"招牌/新品/爆款/尝鲜/福利/加码/专享/神biu手/夜宵拍档/活动/特惠/限时/秒杀/抢手/经典/玩具/赠品/买一送一"；保留"半只/一只/大份/20 个/30 串"等影响分量的规格（共识）
4. **L49 凉拌锚点重写**：明确无油凉拌=1 / 凉拌带油（捞汁/麻酱）=2 / 红油凉拌/油泼凉拌=3；L53 加"水煮鱼水煮肉(汤面浮油)=5"（Codex 主张）
5. **L55-61 protein 改 5g bucket**：输出限制 0/5/10/.../60+，禁止 28/38 这种细数；套餐勿按价格线性外推，不确定偏低估（Codex 主张）

不改的（共识）:
- cuisine 16 类不扩容（D-002 / D-025 相关，留 V1.5 数据层重构时同步）
- is_complete_meal 水饺争议保留原 prompt 意图（"水饺=true"），改动放在 recall 兜底（complete_meal+protein<20g 强制叠 1 蔬菜或蛋白）—— 用户明示"不强求单菜正餐，组合即可"

验证: 2026-05-11 spike 50 条（覆盖 combo 10 + cold 10 + promo 10 + high 5 + normal 15）:
- 总 violation 4/50 = **8%**（旧 40% → 新 8%，5 倍降低）
- 4 个 flagged 全是"主食型套餐归主食"的合理判断（馄饨/恰巴塔/饭团/包子），实际 violation ≈ 0
- 修复旧打标的幻觉菜名问题（d_013_043 / d_010_031 / 等）

风险:
- v2 全量重打会覆盖 v1 9373 条标签；回滚需要 git
- 缓解：tag_via_subagent.py `--version-label v2-promptfix` 标记版本，dishes_tagged.json 仍单文件但每条 metadata.tag_version 区分

触发重审的条件:
- v2 全量重打后再抽 50 条人工 review 准确率 < 80%
- 推荐 dry_run 出现明显错例可追溯到打标
- 下游 D-030 V1.5 重构时 schema 需要再升级

执行进度: 见 [IMPLEMENTATION_LOG.md#D-031-执行记录](IMPLEMENTATION_LOG.md#d-031-执行记录-tag_dishes-prompt-v2-全量重打)（两 zone batch 数 / subagent 并发 / 违规修复细节）。

---

## D-032: tag_dishes prompt v3 升级（补 5 字段 + 全量重打两个 zone）
日期: 2026-05-11
状态: active

背景:
V2 推荐链路诊断（plan tender-sauteeing-rivest.md）找到 V1 ceiling 被 schema 卡死: 看不懂 dish_role / processed_meat / sweet_sauce / wetness / grain_quality, 纯调权重无法突破 top3 错配（典型反例: 饭团套餐 + 玉米粒 + 饭团 低油高销量但减脂语义差; 卤肉饭和米饭被推到一组造成"主食+主食"）。同时 `taste_description`（"喜欢清爽不油带汤水""受不了甜口"）缺对应字段命中, 偏好进不了打分。

考虑过的方案:
- A. 不改 schema, 让 score.py 用 raw_name 关键词正则匹配（如"红烧"→甜口）
- B. 改 prompt 加 5 字段, 全量重打两个 zone（home 2,117 + shenzhen-bay 11,123 = 13,240 菜）
- C. 只加 dish_role 1 个字段（最高优先级）, 其余拖到 V2.5
- D. 改 schema + 召回阶段写关键词规则补字段（半结构化）

决定: B —— 5 字段一起加 + spike 50 条迭代到准确率 ≥ 80% + 全量重打。

理由:
- A 关键词匹配会漏：糖醋鱼名字不含"糖"但是甜口；红烧豆腐≠红烧肉甜度；米粉=高 GI 但 raw_name 看不出来
- C 边际成本反而高: 一次 prompt 改 + 一次重打 vs 分次 prompt 改 + 多次重打
- D 半结构化耦合度高（score 改 + 规则改 + LLM 改）, 比纯 prompt 加字段更脆

5 个新字段（与 plan A 部分一致）:
1. **dish_role** (主菜/主食/配菜/汤/小食/饮品/套餐) — 决定能不能拼餐, 最高优先级
2. **processed_meat_flag** (bool) — 蟹柳/午餐肉/培根/烤肠/腊肠等工业 or 腌制肉; 叉烧/烧鸭/卤水/酱牛肉=false
3. **sweet_sauce_level** (0-3) — 红烧/糖醋/照烧/烧汁/普通叉烧=2; 蜜汁/蜂蜜/拔丝=3
4. **wetness** (1-3) — =3 仅"可喝汤底"; 关东煮/卤水浸泡=2; 干煸/凉拌=1
5. **grain_type** (白米/糙米杂粮/精制面/全麦面/粗粮/粥/无) — 米粉/河粉=白米; 商业燕麦棒=精制面; 西式蛋白碗=无

迭代过程（spike 50 条）:
- **r1 草案**: 8 字段示例 + 5 字段定义。Codex adversarial review 找到 1 P0 (schema NutritionProfile extra=forbid 与 5 新字段冲突) + 8 P1 (套餐"+饭"无识别/腊味vs烧腊/叉烧 sweet 锚点/关东煮浸泡/复合套餐 grain 仲裁/汉堡 processed/沙拉 wetness/非中式甜酱)
- **r1 应用**: 全部修, 字段名固定 wetness（不混用 soup_or_broth_flag）
- **第 1 轮 spike** (subagent 跑 50 条): 12/50=24% 违规, 5 类系统性错（套餐含汤 wetness 漏判 / 复合粉面 dish_role 误归主食 / 西式蛋白碗 grain_type 幻觉 / 赣菜归江浙 / 调料 spicy 没归 0）
- **r2 应用**: 8 处补丁
- **第 2 轮 spike**: 0/50 致命, 1 P1 (西式蛋白碗 is_complete_meal 矛盾) + 3 P2 边界, 准确率 98%
- **r3 (final v3)**: 补 3 处 (蛋白碗 is_complete_meal=true / 燕麦棒 cooking=烤 / 复合粉面 cooking 取本体)

5 项不改:
- cuisine 16 项不扩容（D-002 / D-025 相关，留 V1.5 数据层重构）
- protein 5g 粒度沿用 v2-promptfix
- canonical_name 必删词清单沿用 v2-promptfix

执行 / 进度: 见 [IMPLEMENTATION_LOG.md#D-032-执行记录](IMPLEMENTATION_LOG.md#d-032-执行记录-tag_dishes-prompt-v3-全量重打--normalize)（打标路径切换 / 模型选型 / 并发参数 / 全量重打 timestamp / normalize 修补）。

风险:
- v3 全量重打覆盖 v2-promptfix 13k 标签; 回滚需 git
- 缓解: schema.tag_version 区分 + git tag pre-v3
- LLM 模型选择影响一致性: 同一 prompt 在 sonnet vs opus 上 5 字段判断可能差异; 用 Opus 50 条对照监控
- OpenRouter 上模型 ID 命名变动: --model 可覆盖

触发重审的条件:
- v3 全量重打后再抽 50 条人工 review 准确率 < 90%
- 推荐 dry_run 出现明显错例可追溯到打标
- cuisine="其他" 占比 > 25% 说明 16 项分类不够用 → V1.5 扩
- 下游 V1.5 重构时 schema 需要再升级

✅ DONE: schema 升级 + v3 prompt + 全量重打 + normalize 兜底全部落地。详细 timestamp/batch/normalize 见 [IMPLEMENTATION_LOG.md#D-032-执行记录](IMPLEMENTATION_LOG.md#d-032-执行记录-tag_dishes-prompt-v3-全量重打--normalize)。

---

## D-033: V2.0 + V2.1 合并触发, 不等 V1 北极星达标
日期: 2026-05-11
状态: active

背景:
原 ROADMAP（DESIGN §6）规划 V2.0（反馈采集）→ V2.1（refine + LLM 精排）→ V2.2（learned_profile 统计聚合）三阶段串行, 每阶段需 V1 自用一周后才启动. 但 Claude × Codex 二轮诊断揭示 V1 推荐质量上限被 3 件事卡住, **不是"V1 用得不够久"**:
- 数据 schema 缺关键营养特征（grain quality / processed meat / 甜酱 / dish role / 汤水程度）→ 任何打分调权都救不回来
- `taste_description` 是最有信息量的偏好却只进 reason 不进 score → 同一菜系内做法差异完全忽略
- 缺反馈回环 → 无法学习个性化, V1 一直用也不会变好

继续等 V1 北极星 ≥ 50% 再上 V2 = 浪费时间. 北极星本身就被这 3 件事卡住.

考虑过的方案:
- A. 维持原 ROADMAP, 严格 V1 → V2.0 → V2.1 → V2.2 串行
- B. V2.0 + V2.1 合并一轮做; V2.2 仍按"反馈攒到 30+ 条"触发
- C. V2.0 + V2.1 + V2.2 一锅端

决定: B.

理由:
- V2.0 反馈数据采集 + V2.1 LLM 精排 + refine 是**强依赖链但工作量适中**, 一轮做完即可形成完整闭环
- V2.2 learned_profile 聚合需要至少 30+ 条 feedback, 离了数据是空架子, 推迟到自用 1-2 周后再启动
- 用户明确诉求是"5 个候选 + 探索 + 当下 chip + 自由文本 + 餐后追问 + refine 重推", 这些 PRD/DESIGN 已设计完整（D-007 / D-010 / D-011 / D-014 / D-015 / D-024 / D-025 / D-026）, 本质是**激活已有设计 + 补 schema 字段 + Context 注入层**
- 合并做的代价（一轮工程量稍大）小于分两轮做的代价（重复跑冷启动 + 验收两次 + 反馈系统单独上线时无 LLM 精排支撑）

反对意见 / 风险:
- 一轮验收面变大: 用 8-12 个黄金 case + scripts/eval_recommend.py 离线对比 V1 vs V2, 缓解
- V2.0 反馈骨架在 V2.2 起来前没"消费方", 数据可能只采不用: 接受这个临时状态, 反馈数据本身就是 V2.2 的输入

触发重审的条件:
- V2.0+V2.1 合并实现后, 自用 1 周采纳率反而下降（说明合并引入了不可预期问题）
- LLM 精排 token 成本失控（远超 V1 reason 的 ¥0.05/次, 月度超 ¥50）

依赖: D-032 (v3 prompt 补字段)、D-034 (Context 注入)、D-035 (LLM 精排结构化输出)

---

## D-034: 引入 Context 注入层 (DESIGN 缺失的第 5 层)
日期: 2026-05-11
状态: active

背景:
DESIGN §5.6 描述的推荐三阶段（召回 → 打分 → 精排）只考虑"长期画像 + 静态偏好 + 历史 meal_log", 不考虑"今天的情境". 但用户真实诉求里"今天想喝汤 / 今天想清淡 / 今天加班想解馋"这种**当日变量**直接决定推荐成败. Codex 二轮 review 明确指出: 没有 context layer, 系统只能推"长期平均最优", 不能推"今天最合适".

考虑过的方案:
- A. 不做单独 layer, 把 context 信息塞进 LLM 精排 prompt 里
- B. 单独 ContextSnapshot dataclass, 进 L3 score 软调权 + L4 LLM rerank context
- C. 把 context 作为硬过滤维度（如 daily_mood=want_light 时排除所有 oil > 2 的菜）

决定: B.

理由:
- A 太弱: 只在 LLM 精排起作用, 召回阶段拿不到, 候选池就被静态偏好限死
- C 太强: daily_mood 是软偏好不是硬约束, 硬过滤会把候选池砍到不可用（违反 D-006 软约束原则）
- B 平衡: ContextSnapshot 显式结构化, L3 软加分 + L4 LLM 看到, 既影响排序也影响理由生成, 但不卡死硬过滤

ContextSnapshot 字段（chisha/context.py）:
- meal_type / zone / now / weekday: 基础情境
- last_meal: 上一顿吃了啥（cuisine / main_ingredient_type / dish names）
- recent_3d_cuisines / recent_3d_ingredients: 最近 3 天分布
- last_feedback: 最近一次反馈摘要（chip + rating + want_again + note）
- daily_mood: 当日开场 1 问的回答（want_light / want_indulgent / want_soup / low_carb / want_clean / neutral / None）
- refine_input: refine 二轮的用户自然语言, None=首轮

`daily_mood` 默认值与触发: 由 OpenClaw 在每日首次饭点 trigger 推荐前问 1 句"今天想清淡 vs 想爽？" 写入 session 状态, 跨当日餐期复用. 用户跳过则保持 None, 不强求.

反对意见 / 风险:
- 多一个 context 层增加调试复杂度: 缓解 — Context 是纯数据结构, 单测覆盖 build_context 即可
- daily_mood 每日 1 问会增加摩擦: 缓解 — 跳过不强求, 跨餐期复用, 一周 5 次共问 5 次

触发重审的条件:
- 自用 1-2 周后发现 daily_mood 命中率极低（用户基本都跳过）, 考虑改为 reactive (从 last_feedback note 里推断)
- Context 字段触发 L3 调权后排序变化过大（黄金 case 评分剧烈震荡）

---

## D-035: LLM 精排强制结构化 JSON 输出 + 重排-解释合并
日期: 2026-05-11
状态: active（V2.x 启用，与 D-024 V1 阶段 LLM 仅写 reason 形成对比）

背景:
D-024 决定 V1 不做 LLM 精排, LLM 只写 reason. V2.x 触发条件成熟（schema 升级 + Context 层 + taste_description 进决策）, 现在该开 LLM 精排了. 但 Codex 二轮 review 提醒: LLM 精排不能只让模型写散文 reason, 否则解释和决策脱节, 调试困难. 必须强制结构化中间字段, 让"为什么这条排第 1"是机器可读的.

考虑过的方案:
- A. LLM 精排只输出排序 + 一句 reason, 散文形式
- B. LLM 精排输出排序 + 每个候选的结构化字段 (fit_score / health_flags / taste_match / risk_flags / one_line_reason), 然后 reason 是结构化字段的投影
- C. LLM 重排 + 单独一个 LLM 解释员, 两次调用

决定: B.

理由:
- A 让 LLM 写散文容易漂移, 也无法被 eval 脚本核对（"为什么 LLM 选了这个？"成了黑盒）
- C 两次调用浪费 token 且容易出现"重排判断 vs 解释"不一致
- B 强制 LLM 在排序时把判断暴露出来, reason 是这些判断的人话总结. eval 脚本可以核对结构化字段, 用户/审计员看 reason 能复盘

LLM 精排输出 schema (V2):
```json
{
  "candidates": [
    {
      "rank": 1,
      "is_explore": false,
      "combo_index": 5,
      "fit_score": 0.87,
      "health_flags": {
        "veg_ok": true,
        "protein_ok": true,
        "oil_ok": true,
        "carb_quality": "ok",
        "processed_meat": false,
        "sweet_sauce": false,
        "soup_or_broth": true
      },
      "taste_match": 0.9,
      "risk_flags": [],
      "one_line_reason": "潮汕汤水清爽, 命中你今天想喝汤"
    }
  ]
}
```

5 个候选 = 3 exploit (按 score 排) + 2 explore (打分中段 + 最近未吃过 + 未尝试菜系/做法), 命中 D-015. refine 时 explore_count=0 (用户已有方向, 探索是干扰).

反对意见 / 风险:
- LLM 输出 JSON 偶尔会坏: 缓解 — 沿用 reason.py 的 try/except + fallback 策略, 失败时退化到打分 top 3 + 规则 reason
- 强制字段会减少 LLM 灵活度: 接受这个 trade-off, 灵活度让位于可解释性

触发重审的条件:
- LLM 精排错例（黄金 case 失败）连续多个发生在 fit_score 字段（说明字段定义不准）
- token 成本 > V1 reason 5 倍且无明显质量提升

依赖: D-032 (v3 prompt 补字段)、D-033 (V2 合并)、D-034 (Context 注入)


## D-036: Golden set 重建 (Opus 4.7 + Codex GPT-5.4 双模型共创, 171 条)
日期: 2026-05-12
状态: active

背景:
旧 `golden_set.jsonl` 150 条是用 OpenRouter Sonnet 4.6 单次生成 + 11 条规则自检构造, 本质"Sonnet 自评自打"循环论证, 用它评测其他模型有偏。具体问题: d010 anchor `spicy_level=2` 与 prompt 规则"非食物兜底 spicy=0"冲突 / d050 烧麦主料归属歧义 / d100 套餐 canonical 规则未明 / 4 大易错字段(sweet_sauce/processed_meat/dish_role/grain_type)边界覆盖度 ~70%。

考虑过的方案:
- A. 完全重建 140 条 (无先验, Opus 独立打 + Codex 对抗)
- B. 增量重审 + 增补 20 对抗 case
- C. 只补已知 bug + 增补对抗 case

决定: A + 增补 21 对抗 case → 最终 **171 条** (10 anchor 保留 + 140 完全重建 + 21 adversarial 含 d169/d169b price-aware 对照)。

理由:
- A 彻底, 避免被旧 Sonnet 标注错误锚定 (用户明确"完全重建"决策)
- 20 对抗 case 覆盖 6 边界判定 + 防 LLM 幻觉 (d168 恰巴塔三明治曾被旧模型瞎编成"烤鲜活鲍鱼") + price-aware protein 验证
- 不用 OpenRouter, 改用 Claude Code 内 Opus 4.7 直接担任 S1/S3, Agent(subagent_type=codex:codex-rescue) 派任 Codex GPT-5.4 担任 S2 对抗

实施流程 (per batch, batch_size=5):
- **S1 草拟**: 主 Claude (Opus 4.7) 按 v3 prompt 给 15 字段 expected + 每字段 ≤30 字 rationale
- **S2 对抗**: Codex GPT-5.4 (via codex-rescue), prompt 内 inline `CRITICAL_RULES.md` (4 大字段 + 6 边界 + LLM 幻觉防护规则) 作 grounding_rules
- **S3 裁决**: 主 Claude 看 Codex challenges, 接受 / 反驳 / 标 needs_review
- 全 35 batches 通过 ralph-loop 闭环, 每 iteration 1 batch

工程产物:
- `scripts/dual_pipeline.py` — orchestration CLI (`status`/`next-batch`/`mark-done`/`merge`)
- `scripts/dish_inputs_v2.py` — 21 条 adversarial case (d151-d170 + d169b)
- `eval/dish_tagging_eval/CRITICAL_RULES.md` — 规则集中沉淀
- `eval/dish_tagging_eval/RALPH_LOOP_PROMPT.md` — ralph-loop iteration prompt
- `eval/dish_tagging_eval/KNOWN_ISSUES.md` — 16 条边界争议落账 (P0/P1/P2)
- `data/golden_set.jsonl` — 171 条新主产物 (旧 150 条 Sonnet 版本于 2026-05-13 清理, git 历史可查)

跑完指标:
- Schema 通过 171/171 = 100%
- anchor_violations 0/171
- 4 大字段双模型一致率 99.27% (679/684)
- consensus 分布: 155 agree / 10 codex_wins / 5 opus_wins / 1 human_needed
- needs_review 1/171 (d026 红薯粉 grain_type 枚举边界)

V3 prompt r3 patch (已 sync 主 `prompts/tag_dishes.md`):
1. d010 示例 spicy_level=2 改 0 (修复 prompt 内部矛盾)
2. sweet_sauce_level 新增锚到 1: 回锅肉/鱼香肉丝/宫保鸡丁 (字面无锚但实际含糖)
3. grain_type 新增锚点: 红薯粉/绿豆粉/魔芋粉 → 白米 (精制淀粉高 GI 类推)

反对意见 / 风险:
- 双模型共谋盲区: Opus + Codex 同时错判同一规则. 缓解 — S2 prompt inline 完整 CRITICAL_RULES + 保留旧 anchor_violations 11 条规则做第三道门
- Codex 子代理 ~34 次调用可能 rate limit. 缓解 — 串行 + ralph-loop 每 batch 落盘断点续跑
- "应用层先扩召回"决策下, 10 codex_wins + 5 opus_wins 的边界判定未细究, 进 KNOWN_ISSUES.md, 等 V1 user feedback 触发重审

触发重审的条件 (见 KNOWN_ISSUES.md):
- V1 推荐链路上线后, user feedback 反映某 dish 分类不准
- 跑 score.py 发现某模型在边界 case 上准确率显著偏低 (尤其 d029/d038-d040 cuisine/main_ingredient)
- v3 prompt 后续迭代到 v4

依赖: D-031 (v2 prompt), D-032 (v3 prompt v5 字段)

---

## D-037: 生产打标默认模型切到 deepseek-v4-flash
日期: 2026-05-12
状态: active

背景:
D-036 重建的 171 条 dual-model golden set 跑完 6 模型横评 (`eval/dish_tagging_eval/report.md`), 发现:
- 准确率冠军 `sonnet-4.6` 字段 acc 89.4% / 100万条 $4572
- `deepseek-flash` 字段 acc 88.9% / 100万条 $100 (距冠军 -0.5pp, 成本仅 2.2%)
- `haiku-4.5` 字段 acc 85.2% / 100万条 $1424 (距冠军 -4.2pp, 此前默认 "haiku 主跑 + sonnet 回退" 的分层方案在新 golden set 下不再成立)

DeepSeek v4 系列在新 golden set 上表现超预期, pro/flash 双雄打平 (88.9% vs 89.0%), flash 便宜 13×, 没必要选 pro。

考虑过的方案:
- A. 默认 sonnet-4.6 (准确率优先)
- B. 默认 haiku-4.5 (原方案, 吞吐快)
- C. 默认 deepseek-flash (性价比, 距 top -0.5pp + 成本 2.2%)
- D. 分层: deepseek-flash 主跑 + sonnet-4.6 回退低置信样本

决定: **C** (默认 deepseek-flash, 不做分层)

理由:
- 准确率 gap 0.5pp 落在 golden set 自身边界争议 (16 条 P0/P1/P2 KNOWN_ISSUES) 噪声内, 分层带来的边际收益 <1pp 但增加链路复杂度
- 13240 菜全量打标按 flash 实测成本预估 ~$1.3, 几乎可忽略, 后续迭代版本可以激进重打
- 评测系统 (`eval/dish_tagging_eval/run_eval.py`) 保持 6 模型横评不变, 仅生产链路切换

工程产物:
- `chisha/llm_client_openrouter.py:DEFAULT_BULK_MODEL` 从 `anthropic/claude-sonnet-4.5` → `deepseek/deepseek-v4-flash`
- `scripts/tag_via_api.py --model` 默认值同步 (经由 DEFAULT_BULK_MODEL 导入)
- `eval/dish_tagging_eval/scripts/make_report.py` 综合打分权重从等权 → cost 0.7 + time 0.3 (生产打标看长期成本, 单条延迟次要)
- `eval/dish_tagging_eval/report.md` 重生成, 推荐口径自动切到 flash

反对意见 / 风险:
- **DeepSeek 数据合规**: OpenRouter 转发 DeepSeek, 实际 inference 在 DeepSeek 后端. 菜名不含 PII, 风险可控
- **v3 prompt 对 deepseek 适配度未充分测试**: 当前评测 88.9% 是单 prompt 跑出, 没做 deepseek-specific prompt tuning; 跑大规模生产前先 smoke 100 条
- **OpenRouter rate limit 未实测**: 评测时 batch=20 / concurrency=20 跑 deepseek-flash 没触发 429, 但 13240 菜单账号串跑可能撞限; 必要时申请提升或加 sleep
- **deepseek-flash 输出比 sonnet 啰嗦 ~20%**: 评测中 output_tokens 实测偏高, 但成本依然便宜 14×, 不构成问题

触发重审的条件:
- 跑生产数据发现 deepseek-flash 在某类边界 case 上系统性翻车 (例如 oil_level / sweet_sauce_level 与 golden set 偏差扩大)
- 模型供应商关停 / 提价 (DeepSeek v5 出来或 OpenRouter 提 markup)
- v4 prompt 重大升级后, 新 golden set 横评推荐换模型
- 业务侧要求更高准确率 (例如健康关怀类用户 / 推送内容审核)

依赖: D-032 (v3 prompt), D-036 (dual-model golden set)

---

## D-038: 推荐链路 LLM 抽象与外部 Agent 接入策略
日期: 2026-05-12
状态: Phase 1 active; **Phase 2 superseded-pending by D-074**（2026-05-16 战略共识 — closure 注入方案换为 `llm_request_spec` machine-readable 数据契约, chisha 输出 prompt + tool_schema 给 Agent, Agent 用自己 LLM 调完回灌. 理由: closure 注入要求 Agent 同步暴露 LLM 函数, 异步 / IM / 跨进程 Agent 都做不到. 待 Step 2 完成后落 D-074, 详见 [docs/design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md](../docs/design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md)）

背景:
chisha 最终形态是 Skill / 库, **被** OpenClaw / Hermes / Claude Code skill 调用,
不是独立 daemon. 调用方 Agent 通常自带 LLM (各家不同: Claude / GPT / 国产). 强行
把 chisha 绑死到某一家 LLM provider, 既增加调用方负担 (要另配 key), 又浪费调用方
已有的 LLM 上下文窗口.

但 V2 推荐链路 (D-033/D-035) 本质需要 LLM 做精排 + reason. 这件事在 chisha 独立
跑时 (CLI / 测试 / cron / 开发者自用) 必须有内置实现, 不能裸跑.

需要的能力:
- 独立运行: chisha 自带 LLM 实现, 不依赖外部 Agent
- 多 provider 兼容: 用户可能已经有 ANTHROPIC_API_KEY 或 OPENROUTER_API_KEY,
  不强制二选一
- 外部 Agent 注入: OpenClaw / Hermes 调用时, 把自己的 LLM closure 传进来, chisha 用它代替默认实现

考虑过的方案:
- A. 硬绑 Anthropic 直连. 否决 — 阻塞已有 OpenRouter 用户.
- B. Phase 1 (auto-detect provider) + Phase 2 (callable 注入点) 分阶段实施.
- C. 一步到位上 MCP server, chisha 完全不做 LLM, 由 MCP client 调.
  否决 — V2 验证期把 MCP 化耦合进来过早, chisha 还没自用稳定就先架构改造容易翻车.

决定: B.

Phase 1 (已实施, 2026-05-12):
- `chisha/llm_client.py:call_text(prompt, **kw)` provider 自动检测:
  - 有 `ANTHROPIC_API_KEY` → Anthropic 直连 (model=`claude-sonnet-4-6`)
  - 否则有 `OPENROUTER_API_KEY` → OpenRouter (model=`anthropic/claude-sonnet-4.6`)
  - 都没有 → raise RuntimeError, 调用方 (reason / rerank) try/except 退化到 rule fallback
- 加 `has_llm_key()` 辅助方法, 替代散落各处的 `os.environ.get("ANTHROPIC_API_KEY")` 检查
- `chisha/reason.py` + `chisha/rerank.py` 改用 `has_llm_key`, 不再硬编码 ANTHROPIC

Phase 2 (待触发, OpenClaw 实际接入时做):
- `recommend_meal(..., llm_call: Callable[[str], str] | None = None)` 注入点
- `refine_recommendation(...)` 同上
- 当 llm_call 注入时, rerank 内部用 llm_call 代替 `chisha.llm_client.call_text`
- chisha 内部所有 LLM 调用都通过这一个抽象, 不直接 import provider SDK
- 文档化外部 Agent 接入契约: prompt 模板由 chisha 导出, Agent 负责执行 + 把 JSON
  字符串返回

反对意见 / 风险:
- Phase 1 模型选择默认 sonnet-4.6 而非 deepseek-flash (与 D-037 生产打标不一致):
  接受 — 推荐链路 LLM 精排对语义理解 + 中文偏好理解的要求比打标更高,
  reason 也只 ≤30 字, 调用量小, 成本不敏感; 待 V1 自用稳定后再评估 LLM 精排
  是否也可降到 deepseek-flash.
- Phase 2 callable 注入会让 chisha 接口签名变长: 接受 — 注入参数 default=None,
  老用法不破坏

触发重审的条件:
- OpenClaw / Hermes 真正开始接入 chisha 时, 启动 Phase 2
- 用户多次反映 sonnet-4.6 精排答案质量与 deepseek-flash 持平, 切换降本
- 出现 LLM 接口必须支持流式输出 / 中间结果回调的需求 (Phase 1 简单 prompt-in
  text-out 不够用)

工程产物 (Phase 1):
- `chisha/llm_client.py` 完全重写, provider auto-detect
- `chisha/reason.py` + `chisha/rerank.py` 用 has_llm_key 取代直接 env 检查
- `prompts/rerank_topn.md` 硬约束加"商家去重"(LLM 多 candidate 同店时只选 1 个)
- `chisha/rerank.py:_enforce_brand_unique()` 兜底: LLM 漏掉去重时, 后处理强制
  执行 (同 restaurant.id 只留 1 条 + 不足 n 时从 top_combos 按 score 补位)

V2 e2e 5 次空跑验收 (2026-05-12, profile.yaml 真用, mood 三档对照):
- lunch mood=want_light 主推油 1.3-1.7 的, 不再选油 2.5 的
- lunch mood=want_soup 三家不同店全汤水系, oil_ok 全 true
- dinner mood=want_indulgent 主推 35g 蛋白的酸菜鱼/牛肉
- explore 全部跨菜系 (湘菜粉面 / 川菜蹄花 / 陕西面食)
- 5 次跑无同商家重复 (Phase 1 兜底生效)
- reason 直接点出 "命中 want_light"/"是你点名爱的菜", 不再模板化

依赖: D-033 (V2 合并触发), D-035 (LLM 精排结构化输出)

---

## D-039: 推荐调试台作为独立工件

**2026-05-13**

### 背景
V2 推荐链路 e2e 跑通后, 用户开始调试推荐效果, 但命令行 dry_run 看不到中间状态
(召回丢弃原因 / 16 维 score breakdown / LLM rerank 的 payload+response), 改 profile.yaml 调权重也要重启脚本.

### 决策
新增独立调试台工件 (FastAPI + 单文件 HTML), 与 OpenClaw 接入完全解耦:

- `chisha/debug_recommend.py`: V2 instrumented 管道, 每阶段记录中间状态;
  支持 profile_overrides (页面端覆盖, 不写盘) / trace_target (追溯某 combo 命运) /
  compare_moods (并排跑多个 daily_mood)
- `chisha/debug_server.py`: FastAPI on port 8765, endpoints:
  GET / (调试台) / GET /docs (logic.html) / POST /api/debug_recommend /
  POST /api/compare_moods / GET /api/profile
- `chisha/static/debug.html`: 单文件工程师调试台 (4 段 L1/L2/L3/Final 折叠 + L2 表点行展开 16 维 breakdown)

### Why
- 推荐效果迭代周期短 (调权重→看效果→改权重), 命令行/重启脚本拖慢节奏
- 浏览器调试时能看完整 payload, 才能判断 LLM rerank "选这条/丢那条" 的逻辑
- 独立工件 = 不污染主链路代码 + 不和 OpenClaw 接入争抢决策

### 与 OpenClaw 接入的关系
- 调试台是 **dev-only 工程师视图**, OpenClaw 飞书卡片是 **用户视图**, 两者并行
- 调试台先把推荐质量打磨好 (调权重 / 调 profile 字段), 再做 OpenClaw 接入 → 避免到了飞书卡片才发现推荐烂

### 工程产物
- `chisha/debug_recommend.py` (~600 行, 含 `_traced_hard_filter` 委托给生产 `hard_filter`)
- `chisha/debug_server.py` (~110 行)
- `chisha/static/debug.html`, `chisha/static/logic.html` (另 session 迭代)
- 新依赖: fastapi>=0.115, uvicorn>=0.32 (pyproject.toml)

### 启动
```bash
uv run python -m chisha.debug_server
# → http://127.0.0.1:8765
```

依赖: 无新决策依赖

---

## D-040: combo 生成数量约束由 profile 显式注入

**2026-05-13**

### 背景
V1 `build_combos_for_restaurant` 硬编码"路线 B = 1 蛋白 × 1 蔬菜 × 0/1 主食",
不允许"补蔬菜" (1p+2v) 或"凑蛋白" (2p+1v) 场景. 用户洞察: combo 阶段不应该卡数量,
应该由 profile 显式注入, 让 agent 自由控制.

### 决策
combo 阶段**只过营养合规** (plate_rule 弱约束三件套), 数量约束由 profile 注入:

```yaml
recall:
  max_dishes_per_combo: 4
  max_protein_per_combo: 2     # 允许凑蛋白
  max_veg_per_combo: 2         # 允许补蔬菜
  max_carb_per_combo: 1
```

路线 B 枚举 (n_p, n_v, n_c) ∈ [1,max_p] × [1,max_v] × [0,max_c],
满足 n_p+n_v+n_c ≤ max_dishes 的所有组合.

### Why
- 用户外卖场景"先满足蔬菜需求, 再满足蛋白需求"是合理的, 1v 不够时补 2v
- 把数量决策从代码里搬到 profile, 让用户/agent 不改代码就能调
- 与 D-041 "召回宽召回, 用 profile 硬过滤" 原则一致

### 取舍
- 组合数膨胀: 单餐厅 raw combos median 16 → 48 (3x), 但 per_restaurant_max=20 截断后实际负载可控
- LLM payload 38K → 46K chars (V2 rerank), 仍远低于上下文上限
- 实测召回总 combos: 454 → 2206 (×4.8), L2 打分压力可接受

### 工程产物
- `chisha/recall.py:build_combos_for_restaurant` 重写为参数化枚举
- 各池按 monthly_sales 降序 [:6 / :5 / :3] 防爆炸
- 路线 A 加 `max_n <= 0 → []` 守护 (Codex audit 提出, D-039 review)
- profile.yaml 新增 4 个 recall.* 配置项

依赖: D-023 (弱约束三件套)

---

## D-041: 召回硬过滤双层架构 (hard_max_* / prefer_max_*)

**2026-05-13**

### 背景
用户在调试台发现:
- avoid_dishes 是 exact match, 18 个变体漏过 ("腐竹红烧肉+香米饭" 没命中 "红烧肉")
- min_monthly_sales=10 砍掉 24% 长尾菜, 但 popularity 打分维度已经在处理低销, 重复
- per_restaurant_max=3 在召回阶段过度剪枝, V2 LLM rerank 自带品牌多样性
- 缺关键硬约束: 价格上限 / ETA 上限 / 餐厅黑名单 / 主蛋白黑名单 / 烹饪方式黑名单 / 菜系硬黑名单

### 决策

**架构原则**: 召回阶段尽量召回 + 用 profile 显式硬约束剪枝;
判定一个约束是"硬"还是"软"的标准:
- **硬**: 用户红线, 违反就不能出现 → 召回过滤 (减少后续算力)
- **软**: 偏好但能权衡, 多目标 → 打分维度 / LLM 精排

**字段命名规范**:
- `hard_max_*` / `banned_*` / `avoid_*` → 召回硬过滤
- `prefer_max_*` → 打分软扣分 (与 `hard_max_*` 配对)

**P0 落地 (零数据成本)**:
- `delivery_constraints.hard_max_eta_min`: ETA 超此值的餐厅整家 ban (距离不卡, 外卖场景)
- `price_range.{hard_max_lunch, hard_max_dinner}`: combo 总价绝对上限, 超即 ban
- `preferences.avoid_restaurants`: 餐厅名/品牌 substring 模糊匹配
- `avoid_dishes`: 改 substring 模糊匹配 (从 exact match)

**P1 落地 (零数据成本)**:
- `preferences.avoid_main_ingredients`: 主蛋白黑名单 (如 [海鲜])
- `preferences.avoid_cooking_methods`: 烹饪方式黑名单 (如 [油炸])
- `preferences.banned_cuisines`: cuisine 硬黑名单 (区别于已有 disliked_cuisines 软)

**P2 延后 (需要重打标, 暂不做)**:
- allergens / calories / dietary_flags

**软字段重命名**:
- `lunch_max` → `prefer_max_lunch`, `dinner_max` → `prefer_max_dinner`
- `max_delivery_eta_min` → `prefer_max_eta_min`
- `score.py` 用 `new_name or old_name` 保留向后兼容入口

**`hard_filter()` 重构**: 返回 `(kept, dropped)` 元组, dropped 每项含 `reason: str`;
新参 `rest_ban_reasons: dict[rid, str]` 让调试管道注入"ETA超限/avoid_name/diversity"等具体原因.
`debug_recommend._traced_hard_filter` 从 60 行重复逻辑改为 11 行薄包装, 委托给生产函数.

**配置调整**:
- `hard_max_oil_level`: 5 → 4 (实际 ban 最油的 872 道菜)
- `min_monthly_sales`: 10 → 0 (关闭, 长尾交给 popularity)
- `per_restaurant_max`: 3 → 20 (放开召回, 多样性留给排序)
- 删除 `recall.top_n` (死配置, 没人引用)

**bug 修复**:
- `dish_price()` helper 处理 `price=None` 安全求和 (Codex audit 发现)
- `refine.py:120` 加 `meal_type=state.meal_type` (refine 之前没应用 combo 总价过滤)
- `build_combos_for_restaurant` 路线 A 加 `max_n <= 0 → []` 守护

### 工程产物
- `chisha/recall.py`: `compute_extra_banned_restaurants` + `combo_price_filter` + `combo_total_price` + `dish_price` 新增; `hard_filter` 重构
- `chisha/api.py` / `chisha/refine.py`: 调用 `recall()` 时传 `meal_type=`
- `chisha/score.py`: `eta_penalty` / `price_penalty` 读新字段名 (留老 fallback)
- `profile.yaml`: 新增 7 个字段, 重命名 3 个, 删 1 个
- `tests/test_recall_d041.py`: 8 个新测试 (Codex audit 提出, 含 traced=production 一致性)
- 既有 224 + 新增 8 = 232 测试全过

### Why
- "召回宽召回, profile 显式 ban" 是业界共识 (Etsy/Yelp 模型)
- 硬/软命名规范让用户读 profile.yaml 时一眼分清"红线 vs 偏好"
- hard_filter 单一真理源, 消除 trace/production 漂移风险

### 横评（Codex audit 共识）
- 3 个 bug 全修 (price=None / refine 漏传 / route A max_n)
- 2 个设计问题接受 (drift 重构 + 命名统一)
- 2 个设计问题确认无问题 (ETA=-1 / 组合上限 ~830 worst case)
- 1 个死配置删除 (recall.top_n)

依赖: D-023 (plate_rule), D-040 (combo 生成参数化)


## D-042: L2 排序后 per-restaurant cap + 调权微调

**2026-05-13** · 工程实施 → 完整内容见 [IMPLEMENTATION_LOG.md#D-042](IMPLEMENTATION_LOG.md#d-042-l2-排序后-per-restaurant-cap--调权微调)

要点:GRAIN_GOOD 删粥、cuisine_preference 0.5→0.2、`cap_per_restaurant(k=3)` 新增、`resolve_cap_k` 统一三路径。引出 D-043 (cap 解决单店霸榜, 未解决 cuisine 扎堆)。

依赖: D-033, D-040, D-041


## D-043: L2 打分体系重设计 + 反馈闭环最小实现

**2026-05-13**

> **⚠️ 反馈闭环 P3 部分已被 [D-076](#d-073-l1-长期反馈层重构--砍伪-l1--llm-抽取-v1x) superseded (2026-05-16)**:
> "refine chip → feedback_history.jsonl 频次聚合 → load_runtime_hints" 这条路径
> 概念错位 (refine chip 是 L2 单次信号, 不该跨 session). D-076 砍掉此路径,
> 改成 V1.1 反馈 → LLM 抽取 → `data/long_term_prefs.json`. `long_term_prefs.py`
> 标 DEPRECATED stub. L2 打分体系本身 (4 层 cap + popularity/variety/taste 改活 +
> unforgivable penalty) 仍生效.

### 背景
D-042 cap 后用户报告: top30 仍高度同质 (潮汕粥/汤水类), 排序集中在少数店. 数据分析显示打分 16 维度中:

- **8 维度死分** (top30 std=0): vegetable_floor_pass / protein_floor_pass / variety_bonus / processed_meat / sweet_sauce / distance / taste_match / context_boost
- **8 维度活但弱** (std 0.04-0.11): cuisine_preference / wetness / carb_quality / popularity / low_oil 等
- top30 总分跨度仅 0.34, top5 跨度 0.18 → 任何一个高区分度维度命中即锁榜

死分三种成因:
- 结构性 (召回已强制): vegetable/protein floor
- 使用性 (API 没传 hints/mood): taste_match / context_boost / distance
- 数据稀疏: processed_meat / sweet_sauce / variety_bonus (3 天窗口全员命中)

### 决策

详见 [`docs/RECOMMEND_PRINCIPLES.md`](RECOMMEND_PRINCIPLES.md) 沉淀的 11 条原则。本决策的核心架构变更：

#### P0 · 砍死权重 + 加菜系/形态 cap
- 删 `vegetable_floor_pass` / `protein_floor_pass` / `distance` 权重 = 0 (在 V2_DEFAULT_WEIGHTS 设 0, profile.yaml 同步)
- `chisha/score.py` 新增 `food_form` 规则推断 (从 canonical_name + cooking_method 推断, 不重打标): 粥/汤/面/饭/凉拌/烤/油炸/蒸/煎/炒/卤水/其他
- 加 `cap_per_cuisine(top30_max=6)` + `cap_per_food_form(top30_max=8)` 单层函数, 实际生产用 `apply_caps` 一次遍历 + 三计数器同时满足三层约束 (Codex review 修复了串联实现的 BUG)

#### P1 · 改活死维度
- `variety_bonus`: 0/0.5 二值 → 上次同 main_ingredient_type 距今 N 天, 分数 = min(1, N/7), 窗口拉到 7 天
- `popularity`: log10 归一 → top30 内 percentile (rank-based)
- `taste_match`: 接 profile 静态 hints 兜底 (offline 抽 taste_description → taste_boost_tags/taste_penalty_tags)
- `context_boost`: 没传 mood → 时段/季节默认 (午餐 want_balanced, 夏季高温 want_light), 置信度低 (权重 0.25)
- `processed_meat` / `sweet_sauce` 三档:
  - L1 硬过滤 (用户明确 banned): profile.preferences.banned_processed_meat / banned_sweet_sauce_level_3
  - L2 软扣 (有数据 + 未禁): 现有逻辑保留
  - UNKNOWN (无数据): 0, 不当 MISS

#### P2 · 实测 std 校准 + 不可补偿惩罚
- 跑 P0+P1 后的实跑, 统计每维度 top30 std
- 按"影响力 = std × 权重"重新分配权重 (写回 profile.yaml + V2_DEFAULT_WEIGHTS)
- 加 `apply_unforgivable_penalty(score, combo)`: 命中"重 sweet_sauce + 重 processed_meat 同时"等不可补偿组合, score *= 0.5 直接打折

#### P3 · 反馈闭环最小实现
- 新增 `chisha/long_term_prefs.py`: 聚合用户反馈 chips → 加权计数, 拉普拉斯平滑 + 时间衰减 (半衰期 30 天)
- `refine.py` 在 parse_feedback 后调 `append_feedback` 写入历史 (生产数据采集路径)
- `rank_combos` 启动时调 `load_runtime_hints` 加载, 与 profile.taste_description 抽出的静态 hints + 显式 taste_hints 三源合并注入 taste_match
- 反馈数据落 `data/feedback_history.jsonl` (人可读, append-only)
- 不做权重在线更新 (P4, 数据量不够); 不做 LinUCB / LTR (单用户场景过早复杂化)

### 与 Codex 跨专家会诊的关键分歧

| 分歧点 | claude 原方案 | Codex 反对 | 最终采纳 |
|---|---|---|---|
| processed_meat 处理 | 全挪 L1 | 把"未知风险"伪装成"确定违规" | 三档处理 |
| taste_match 起始权重 | 0.8 | 兜底 hints 多是宽泛词, 可能新死分 | 0.4 起步, P2 按实测 std 校准 |
| variety 改进 | N 天函数 | main_ingredient 太粗, 漏"形态"维度 | 第一版 N 天, 同步加 food_form cap 覆盖形态 |
| cap 配方 | 只加 cap_per_cuisine | 不够, 必须 cap_per_food_form | 三层 cap 串联 |
| 反馈闭环 | 不在范围 | 最根本批评, 单用户系统的杠杆点 | 纳入 P3, 最小可行实现 |

### 工程产物（D-043）
- 见 `chisha/score.py` (cap_per_cuisine / cap_per_food_form / 不可补偿惩罚 / 改活维度函数)
- `chisha/recall.py` (food_form 推断 + processed_meat banned 硬过滤)
- `chisha/long_term_prefs.py` (新模块)
- `profile.yaml` (新增字段 + 权重重设)
- `tests/test_score_v2.py` / `tests/test_long_term_prefs.py`
- `docs/RECOMMEND_PRINCIPLES.md` (设计原则沉淀, 后续改动必须先对照)

依赖: D-042 (cap_per_restaurant), D-033 (V2 score), [`docs/RECOMMEND_PRINCIPLES.md`](RECOMMEND_PRINCIPLES.md)

---

## D-044: profile.yaml 真实化 + 口味偏好层与健康目标层分离

**2026-05-13**

### 背景
V1-V2 期间 profile.yaml 一直是 mock 数据 (goal=减脂增肌, 价格 35/50, avoid_dishes 是
推测出来的红烧/糖醋黑名单, taste_description 半口语化). D-043 把打分体系调活之后,
推荐质量的下一个瓶颈是 profile 输入端: 系统拿着假偏好喂打分, 上限就到这.

本轮通过和用户 (志丹本人) 多轮口述 + 历史外卖订单回顾, 重建 profile, 并在过程中
识别出一个关键的方法论错误: 之前从"过去 2 个月点了什么"反推"口味偏好", 把**为了
健康妥协后的实际选择**误读成**真实口味偏好**.

具体案例: 用户过去常点潮汕牛肉 / 酸菜鱼 / 翘脚牛肉 (带汤水的清淡牛肉), 我据此抽
象成"喜欢清爽不油带汤水". 用户纠正: 实际口味更喜欢辣椒炒 / 糖醋 / 红烧重口, 之
前选汤水类是因为这些菜"看起来安全, 控热量风险低", 是健康妥协的产物.

如果系统按"妥协后行为"训练, 会永远在重复用户过往的清淡选择, 学不到真实偏好, 也
出不来多样性 —— 这恰恰是用户启动这个推荐系统要解决的"反复点这几家吃腻"的核心矛盾.

### 关键发现: 朋友A失败教训改写优化目标
用户长期吃朋友A私人订制健康餐 (蛋白足 + 油少 + 味淡), 但每每半夜反弹点宵夜烧烤, 总热量
反而更高. 这个失败模式说明推荐目标不是 "这一顿热量最低", 而是 **"这一顿能撑到下一顿"**.
所以"饱腹感"是隐藏的核心约束, 必须通过现有字段 (min_protein_g 拉高 / 复合碳水偏好 /
必含主食) 联合表达.

### 决策

#### A. 三层分离的 taste_description
重写 `profile.yaml.taste_description`, 显式分四段:
1. **健康目标** (哈佛餐盘 + 朋友A失败模式)
2. **真实口味偏好** (不考虑健康约束, 喜欢什么就写什么——辣椒炒/糖醋/蜜汁/红烧都允许出现)
3. **历史行为 ≠ 偏好** (显式提示 LLM: 别把过往妥协选择当偏好)
4. **真实负向** (干煸/纯凉拌/海鲜——是真不喜欢, 不是健康过滤剩下的)

#### B. profile 字段按真实需求校准
- `basics.goal`: 减脂增肌期 → 体重控制+力量训练期 (保饱腹感)
- `basics.zones.dinner`: home → shenzhen-bay (工作日晚餐其实也在公司)
- `plate_rule.min_protein_g`: 25 → **40** (朋友A 25g 验证不饱; 按 标准体重 + 力量训练
  4 次/周 日蛋白 115-140g 反推, 单餐 35-45g 是甜区. 80g 不可行——单餐 80g 蛋白
  需 ~300g 净肉, 外卖几乎达不到, 会锁死召回池)
- `preferences.liked_cuisines`: 删"东北"(口述无), 加"粤菜"
- `preferences.avoid_dishes`: 清空 [红烧肉, 梅菜扣肉, 锅包肉, 糖醋里脊, 拔丝]
  —— **健康过滤走属性维度** (oil_level / sweet_sauce_level / processed_meat_flag),
  不走菜名黑名单, 否则永远在重复历史妥协
- `preferences.spicy_tolerance`: 2 → 3 (用户自评能吃重辣)
- `price_range.hard_max_lunch/dinner`: 80/100 → **150/150**
- `price_range.prefer_max_lunch/dinner`: 35/50 → **120/120** (实际常态 80-120)

#### C. 留给未来 (V2+)
- **"破戒款"投放**: 用户口味喜欢糖醋/蜜汁/红烧, 但健康角度要控. 不 ban, 改靠
  V2 的 explore 槽位 (D-015 5 中 2 explore) + `daily_mood=want_indulgent` session
  级临时上调 oil/sweet 容忍度, 每周给 1 次破戒推荐. V1 不显式实现, 但 profile
  不再 ban 这些菜, 给未来留口子.
- **早餐推荐**: 当前未点外卖, V2 范围内补.
- **宵夜场景**: 不纳入推荐. 系统目标之一是让中晚餐够饱以消除宵夜需求 (隐藏成功
  指标: 宵夜频次 ↓).
- **"干净卫生"字段化**: 偏好评分稳/销量有验证的店, V2 通过 `prefer_min_restaurant_rating`
  或现有 popularity rank-based 间接表达, 当前不加新字段.

### 反对意见 / 风险
- **40g 蛋白卡掉 5-15% 召回**: 主要剔除"卤粉/纯素套餐/轻食小份"这类蛋白不足组合,
  即用户想要避开的"朋友A失败模式"组合, 不是误伤.
- **"历史行为 ≠ 偏好"对 LLM 是否真有效, 待验证**: 这段提示是给 LLM rerank
  prompt 看的. 如果 LLM 仍按订单频次推断偏好, 后续考虑在 prompt 模板加显式
  指令"用户历史订单仅供参考, 不代表口味偏好上限".
- **重写 taste_description 后, 短期推荐结果会和过往订单差异变大**: 这是预期效果,
  但需要观察用户是否真的接受"以前没点过但口味命中"的新菜.

### 触发重审的条件
- 用户实际跑一段时间后反馈推出来的还是太清淡 / 还是反复推老灶台同样几家——
  可能 taste_description 提示对 LLM 没生效, 需要进 prompt 模板.
- 单餐 40g 在召回侧实际打掉的组合比例 >25%, 可能要降到 35g.
- 用户体重 / 饱腹感真实反馈数据攒到 30+ 条 (V2.2 学到 learned_profile 之前),
  应该回头看口味偏好抽象是否还需要校准.

### 工程产物
- `profile.yaml` (本次改动)
- 后续 V2.x rerank prompt 模板: 加入"历史行为 ≠ 偏好"显式说明 (待 V2 启用 LLM 精排时一并改)

依赖: D-023 (弱约束三件套), D-029 (spicy_tolerance 整数), D-033 (V2 字段), D-041 (双层硬/软约束)


## D-045: L2 cap 增加 brand 层 (连锁去重)

**2026-05-13** · 工程实施 → 完整内容见 [IMPLEMENTATION_LOG.md#D-045](IMPLEMENTATION_LOG.md#d-045-l2-cap-增加-brand-层-连锁去重)

要点:L2 cap 从 3 层扩到 4 层(restaurant / **brand** / cuisine / food_form), brand 默认 k=2。`_enforce_brand_unique` 同步改按 brand 而非 rid。副产物:清理旧 dish-tagging eval 资产。

依赖: D-040, D-042, D-043


## D-046: L3 精排 prompt + payload 重构 (top60 + system/user 拆分 + 紧凑化)

**2026-05-13** · 工程实施 → 完整内容见 [IMPLEMENTATION_LOG.md#D-046](IMPLEMENTATION_LOG.md#d-046-l3-精排-prompt--payload-重构-top60--systemuser-拆分--紧凑化)

要点:L3 input top30→60(二审实测多样性增量);prompt 拆 system/user(cache + few-shot);payload 紧凑符号化(48k→5.7k chars,-88%);health_flags 规则化后处理。**含三审补强**(真 Codex 重审): system prompt 事实错误 / `_validate_llm_candidates` idx 上界 / 重排原则优先级 / explore few-shot。

依赖: D-035, D-038, D-043, D-044, D-045

---

## D-046.1: L3 精排 max_tokens + json_mode 临时修 (废弃, 被 D-047 取代)

**2026-05-14** · 工程实施 (废弃) → 完整内容见 [IMPLEMENTATION_LOG.md#D-046.1](IMPLEMENTATION_LOG.md#d-0461-l3-精排-max_tokens--json_mode-临时修-废弃)

要点:D-046 上线后 sonnet 进入英文 CoT 占满 max_tokens, fallback 到 L2 伪结果。临时修撞 5 个坑(prefill 弃用 / OR 协议丢 prefill / OR response_format 不强制 / debug 双份代码漂移 / OR require_parameters 副作用)。**已被 D-047 完整重构取代,不单独保留 commit**。

依赖: D-046

---

## D-047 Part A — L3 精排重构: tool_use forced schema + opus 默认 + top60 + cache_control

**2026-05-14** · 工程实施 → 完整内容见 [IMPLEMENTATION_LOG.md#D-047](IMPLEMENTATION_LOG.md#d-047-l3-精排重构--tool_use-forced-schema--opus-默认--top60--cache_control)

要点:opus-4.7 + tool_use forced schema + top60 + max_tokens=2048 + cache_control:ephemeral, **no thinking**(forced tool_choice 与 extended thinking 不兼容)。fallback 降级 sonnet-4.6 同配置。18 case 实测 17/18 成功率 (94.4% vs D-046.1 的 67%), 平均 12s, 单次 $0.085, cache 命中省 63k tokens。

**跨场景教训**: prompt 软约束敌不过协议级强约束 / OR ≠ Anthropic 直连 / debug/prod 必抽 helper / 数据驱动选型。详细数据 (V1-V5 实测矩阵 / Codex review BLOCKER 清单 / 8 文件改动) 与"教训 6 条"见 IMPL_LOG。

方法论已沉淀到 [docs/L3_RERANK_REDESIGN.md](L3_RERANK_REDESIGN.md) (L3 改动必读)。

依赖: D-038, D-046, D-046.1

---

## D-047 Part B — LLM Provider 抽象 + Claude Code CLI 路径

**2026-05-14** · 架构决策 + 工程实施 → 完整实施细节待迁 [IMPLEMENTATION_LOG.md#D-047-Part-B](IMPLEMENTATION_LOG.md#d-047-part-b)(下次 sync 时迁入)

> 同日并行轨道: Part A 是 L3 精排 tool_use 重构 (上文), Part B 是 LLM provider 抽象 + Claude Code CLI subprocess 路径。两条线在 merge 时合流到 `llm_client.py`: `call_text` 既走 provider 路由, 也支持 tools/tool_choice + dict 返回。

**背景**: 自用阶段每天 1-2 次推荐, 用 ANTHROPIC_API_KEY 月成本 ¥20-100, 而本机已有 Max 订阅。让 chisha 复用订阅额度调 LLM, 同时保留 API key / OpenRouter 路径供未来分发用户使用。

**方案**: subprocess 调 `claude -p`, 10 个隔离 flag (`--effort low` / `--tools ""` / `--disable-slash-commands` / `--setting-sources ""` / `--strict-mcp-config` / `--no-session-persistence` / `--system-prompt-file` / `--input-format text` 等), cwd 在 `~/.cache/chisha/llm_tmp/` 私有目录, env 过滤 `CLAUDE_*` / `ANTHROPIC_*` / `OPENROUTER_*` 防干扰 + 防订阅路径被付费 API 劫持, Popen + start_new_session + PR_SET_PDEATHSIG 防 orphan。

**架构**: `chisha/llm_providers/` 子包, 三 provider (anthropic_api / openrouter / claude_code_cli) 统一签名 (Part A 合流后都返回 dict + 支持 tools/tool_choice; claude_code_cli 不支持 tool_use, 传 tools 抛 `NotImplementedError`); `chisha/llm_client.py` 成薄路由层; profile.yaml `llm` 段控制 + 环境变量 `CHISHA_LLM_PROVIDER` 强制覆盖。

**实测**: N=60 sonnet effort=low 端到端 60s, 输出结构正确; 订阅消耗 1 message 配额/次。详见:
- spec: `docs/superpowers/specs/2026-05-14-claude-code-cli-provider-design.md`
- plan: `docs/superpowers/plans/2026-05-14-claude-code-cli-provider.md`

**关键陷阱 (实测发现 + Codex review 补强)**:
1. Claude Code 默认 system prompt 注入 ~10k tokens → `--tools ""` 砍到 ~1.8k
2. 默认 effort 触发 extended thinking 让 N=60 跑 200s+ → `--effort low` 降到 60s
3. argv 超 ~8k chars 异常 → system 用 `--system-prompt-file`, user 用 stdin
4. `--bare` 跳过 CLAUDE.md 但和 OAuth 互斥 → 用 cwd + env 过滤代替
5. `tempfile` SIGKILL 时残留 → 启动 sweep `chisha_sys_*.md` >1h 旧文件
6. CHISHA_LLM_PROVIDER="" 空白要当 unset, 不能 raise
7. 显式选 provider 但凭据缺失要 RuntimeError 给清晰错误, 不能 silent fallback

依赖: D-038 (LLM 抽象 Phase 1), D-047 Part A (call_text dict 接口)

---

## D-048 — L3 双路径收口: CLI no-tool 分流 + 配置错 hard-fail + trace 结构化

**2026-05-14** · 架构决策 → 完整实施细节见 [IMPLEMENTATION_LOG.md#D-048](IMPLEMENTATION_LOG.md#d-048)

**背景**: D-047 Part A (opus + tool_use forced schema) 与 Part B (Claude Code CLI provider) 同日 merge 后, 暴露出协同 gap — claude_code_cli provider 不支持 tool_use, 但 `rerank.py` 硬编码 `tools=[_RERANK_TOOL]`. 实际效果: auto 路由选 CLI 时, 每次 LLM 调用必抛 NotImplementedError → 静默走 L2 兜底, 用户以为在跑 L3 LLM 精排, 实际不是。

**决策**: 在 rerank 层做 provider 分流, 维持双路径架构 (而非统一 schema):
- **主路径** (anthropic / openrouter): 保留 D-047 Part A 的 tool_use forced schema, 17/18 成功率, 适合分发
- **自用降级** (claude_code_cli): 走 prompt 软约束 + JSON 解析, 复用 Max 订阅免费额度. 质量上限低于主路径, 仅推荐自用调试

切换方式: 改 `profile.yaml llm.provider` 或设 `CHISHA_LLM_PROVIDER` env. auto 模式按 `ANTHROPIC > CLI 订阅 > OR` 优先级自动选。

**Codex review 三项强约束** (BLOCKER + MAJOR 3 + MINOR 1):
1. **配置错误 hard-fail, 不静默**: `_resolve_provider` 抛 ValueError/RuntimeError 时, `_run_llm_rerank` 不再被外层 `except Exception` 吞成普通 fallback, 而是返回 `status="config_error"` + `config_error=True` + 清晰错误信息. trace UI 必须区分"L3 真跑通"vs"L3 调用失败 fallback"vs"配置错根本没跑"。
2. **prompt patch 未命中显式报错**: `_patch_system_prompt_for_cli` 找不到 `# 输出方式` 段时 ValueError, 防未来 prompt 改标题层级后 CLI 静默用 tool_use 失效。
3. **trace 结构化**: 加 `resolved_provider` / `config_error` / `status` 字段, debug 台能直观看出 L3 实际状态。

**Codex review 次要改动** (MAJOR 1/2/5 + MINOR 2):
- CLI 的 `max_tokens` 是假保护 (子进程没 cap), 真兜底是 `timeout_sec=180`. 注释 + 文档同步说明
- JSON parser 第三层 fallback 改用 `json.JSONDecoder().raw_decode` 从每个 `{` 起点扫描, 取首个含 `candidates` 的 dict (旧的"首 { 到末 }"在 CoT 含无关 `{}` 时会拼入垃圾失败)
- OR 路径断言改成 `type=="tool_use" + tool_name` 强约束, `stop_reason` 仅 debug 提示 (OR 某些路由对合法 tool_call 也可能返回 finish_reason="stop")
- 加 4 个 parser 边界测试: 无关 dict 在前 / 截断 JSON / 多 dict 选 candidates / fence 后附 explainer

**实测三态**:
| 场景 | status | provider | latency | cost | candidates |
|---|---|---|---|---|---|
| CLI (auto + Max 订阅) | ok | claude_code_cli | 43s | $0.091 (首次 cache write) | 5/5 |
| OR + tool_use | ok | openrouter | 28s | $0.059 | 5/5 |
| `CHISHA_LLM_PROVIDER=foo_invalid` | **config_error** | None (latency=None) | — | — | 0 + 规则 fallback 保管道不断 |

**未做 / 推后**:
- profile.yaml `model.claude_code_cli=sonnet` 与 D-047 Part A 决策 (主路径 opus) 表面冲突, 已加注释说明这是 CLI 走订阅时的有意配置 (sonnet effort=low 性价比更好), 不动决策
- CLI 路径下 `# 不要做的事` 段仍含 "select_top_candidates" 字样 (patch 函数只替换主指令段), 实测 LLM 输出未受影响, 不修

依赖: D-047 Part A (tool_use schema), D-047 Part B (LLM Provider 抽象)


## D-049 — L2 输出契约改 head-only: apply_caps 不再保留 tail 段

**2026-05-14** · 架构决策

**背景**: D-045 引入 brand 层 cap(默认 per_brand_top_k=2)本意是同品牌进 L3 最多 2 条。但 `apply_caps()` 历史上返回 `head + tail`——head 段严格执行 cap, tail 段是被 cap demote 的同品牌副本仍然挂在序列尾部。L3 输入 `topK=60` 直接切前 60 条, head 装满后开始切 tail, **实测 Super Model 在 shenzhen-bay top60 出现 8 次**(IMPL_LOG.md D-047 三审 #1 "实测核对" 段, 当前约 line 317)。

D-047 三审的应对是改 prompt: 告诉 LLM"输入里仍可能含同品牌多变体, 你的工作之一就是同品牌内部择优", 用 `_enforce_brand_unique` 在 L3 出口兜底成 1 条。这等于把 brand cap 的实际收口从 L2 推到 L3 prompt, 多承担一层不确定性 (LLM 是否真的会择优)。

**决策**: `apply_caps()` 只返回 head (砍掉 tail 段), brand cap=2 真正生效在 L2:
- L3 输入侧: 同品牌至多 2 个变体, LLM 仅在菜品组合维度做择优 (不再需要在 6-8 个变体里挑)
- L3 出口侧: `_enforce_brand_unique` 仍保留 1 条/品牌兜底, 同品牌不同分店不会同时出现在最终 5 条
- 用户口径: 同品牌不同分店挑哪家更近由用户自决, 不是 LLM 职责 (用户原话: "对用户来说比较简单, 也不会是瓶颈")

`diversify_top()` 默认 `max_per_brand` 保持 1 (口径回正记录见下方"实施过程修正"): 它仅在 fallback 出口使用, 必须与 LLM 主路径 `_enforce_brand_unique` 出口 brand=1 保持一致, 否则用户看到 5 条里有 2 条 Super Model. **L2 → L3 输入侧** 的 brand cap=2 完全由 `apply_caps()` 在 head 段控制, 与 fallback 出口口径解耦。

**Codex BLOCKER 防护**: D-043 时 Codex 已 catch 过"cap 串联让 demote 的条复活"bug, 该 catch 现在以 head-only 形式重写 (test_apply_caps_regression_against_naive_chain): 正确单遍实现下 head 长度 = 2 且全是粥; 朴素串联 head-only 会变 4 且含汤 — 区分点仍有效。

**推翻 / 影响**:
- D-047 三审修复 #1 的部分论证 (prompt 写"输入里可能含 6-8 个变体") superseded — 改成"至多 2 条变体, 在这 2 条里挑菜品组合"
- IMPL_LOG.md:315"top60 Super Model 出现 8 次"实测条件作废, 改后理论上限 = brand cap = 2
- **D-024 (V1 简化路径) superseded**: 顺手砍掉 `recommend_meal(version="v1")` 分支、`chisha/reason.py`、`prompts/reason_one_line.md` 和 `scripts/eval_recommend.py` (V1 vs V2 离线评估脚本, V2 17/18 稳定后对比意义没了). V2 自带 `fallback_rerank` 规则路径兜底, V1 baseline 不再需要. 详见 D-024 superseded 注脚

**实施过程修正 (踩坑记录)**:
初版方案把 `diversify_top()` 默认 `max_per_brand` 1 → 2, 同步改了 api.py + rerank.py fallback 路径. dry_run 立刻暴露问题: V1 simple 路径 (当时 dry_run 默认走 V1) 输出 30/30 里有 20 个 Super Model — 同分店 2 个 combo 都进 top 3. 此次踩坑揭示两层认知错位:
1. **混淆了"L2 → L3 输入侧 cap"和"最终输出口径"** — 用户原意是前者, 不动后者
2. **V1 路径还在生产代码里** — dry_run 实际跑的不是用户日常用的 V2 主路径
修正: 回滚 diversify_top 默认到 1, 同时彻底砍掉 V1 路径让 dry_run 默认走 V2.

**变更点**: `chisha/score.py` (apply_caps head-only), `chisha/api.py` (V1 分支删, version 参数删), `chisha/rerank.py` (fallback brand=1 不变), `prompts/rerank_system.md`, `chisha/debug_recommend.py` (清理 import), `tests/test_score_v2.py` (4 个 cap 测试), `tests/test_api_v2.py` (删 V1 测试), `chisha/reason.py` + `prompts/reason_one_line.md` + `scripts/eval_recommend.py` (整文件删), README.md / DESIGN.md / ROADMAP.md (V1 路径引用更新)

依赖: D-043 (L2 重设计), D-045 (brand 层 cap), D-024 (V1 路径, superseded), D-047 三审 #1 (部分推翻)


---

## D-044.1 — wetness 退出 baseline 权重 (只作 session mood)
日期: 2026-05-15
状态: active

### 背景
D-044 改 profile 真实化时, 把 taste_description / avoid_dishes / spicy_tolerance 都按"行为 ≠ 偏好"原则纠正了 (用户口味喜欢辣椒炒/糖醋/红烧, 不是过去为了控热量妥协选的清爽汤水类), 但 `scoring_weights.wetness=0.5` 这个 baseline 权重漏改, 仍在每次推荐里给含汤底/卤水 combo 加 +0.5 分.

实测体感: top-N 仍持续偏向汤水类 combo, 用户主动反馈"为什么一直在推汤水/wetness". 排查根因——wetness 这个字段最早 (D-032) 是从"用户喜欢清爽不油带汤水"这条早期 taste_description 抽象出来的, 而那条描述本身就是从行为反推的伪偏好.

### 决策: 砍静态权重, 保 chip/feedback 触发路径
- `profile.yaml scoring_weights.wetness`: 0.5 → 0.0
- 保留: `chisha/score.py wetness_bonus(combo)` 函数 / `NutritionProfile.wetness` schema / data 已打标 / `long_term_prefs.CHIP_TO_BOOST["想喝汤"] = "wetness"` (用户主动反馈"想喝汤"时 session 级激活)

### 原则: trait 进 baseline, mood 走 session
- baseline 权重承载**稳定 trait** (低油 / 高蛋白 / 控甜酱 / 拒加工肉——用户健康约束的硬偏好)
- 汤水/口味浓淡这类**情境性诉求**走 session 路径 (chip 反馈 / daily_mood / 季节/天气先验)
- "从历史行为抽象到 baseline 权重" 是反复出错的 anti-pattern (D-044 已警示, 这是同款漏的尾巴)

### 影响 / 测试
- `tests/test_score_v2.py wetness_bonus` 单元测试不动 (函数保留)
- 偏好层关键词扫描 `_TASTE_KW_TO_BOOST = {"汤": "wetness", ...}` 暂保留, 因为当前 `taste_description` 仍有 "喜欢汤水/带汁的也行" 一句, 会通过 taste_match 路径注入 wetness boost (权重 0.4×0.5=0.2). 这是次级源, 若用户反馈 wetness 仍持续推, 二阶处理 (改 taste_description 或删 _TASTE_KW_TO_BOOST 中的汤水关键词)

### 触发重审条件
- L3 输出仍持续偏向汤水类 → 检查二阶源 (taste_description 关键词扫描)
- 用户反馈"想喝汤" chip 后 wetness 没生效 → 检查 long_term_prefs 路径

依赖: D-032 (引入 wetness 字段), D-043 (taste_match / 关键词扫描), D-044 (profile 真实化)


---

## D-050 — CLI 精排运行时纠错: validator 结构化 error code + 一次性 retry-with-feedback

**2026-05-15** · 架构决策

**背景**: D-048 把 L3 拆成主路径 (anthropic/openrouter tool_use forced schema, 17/18) 和 CLI 自用降级路径 (claude_code_cli, 不支持 tool_use 只能 prompt 软约束). 本次把 CLI 默认 model 从 sonnet 切到 opus 求质量提升后, dry_run 暴露新失败模式: **opus 质量贪心覆盖 prompt 计数指令** —— 从 top-band 挑 4 条 exploit + 1 条 mid-band 当 explore, 主动放弃第二个 explore 槽 (它判断"硬塞次优 explore 不如多给一个 exploit"). 实测 ~20-40% session 触发 `explore 数量 1 != 期望 2` fallback, 商家分布退化到 5 家。

sonnet 没这问题 (倾向无脑遵守计数), 但 sonnet 选菜质量明显弱于 opus (D-047 V4 矩阵已验证).

试过把"计数硬约束"写到 CLI patch 后的 prompt 段 (`_CLI_OUTPUT_SECTION`), 反而让 opus 开始返回 6 条, 失败率从 20% 升到 100%. 加重 prompt 不是答案 —— opus 的"全局质量优化"倾向需要机械纠错, 不是更严厉的指令。

**决策三件套**:

1. **validator 返回结构化 error code** (`chisha/rerank.py:RerankValidationCode`)
   - `_validate_llm_candidates_v` / `_diagnose_candidates` 返回 `(cands, code, detail)` 三元组
   - code 是稳定枚举: `EXPLORE_COUNT_MISMATCH` / `OVER_N_MAX` / `EXPLORE_POSITION_WRONG` / `INDEX_OUT_OF_RANGE` 等
   - detail 仍是中文人类可读供 trace / fallback_reason 显示, 但 retry 路由不再依赖文案
   - Codex review Q2 反馈: 之前用 `("explore 数量", "n_max", "数量") in detail` 字符串匹配, validator 文案改一下就静默漏触发

2. **retry trigger 按 code allowlist 路由** (`_RETRY_TRIGGER_CODES`)
   - 仅 `{OVER_N_MAX, EXPLORE_COUNT_MISMATCH, EXPLORE_POSITION_WRONG}` 三类触发 retry
   - 不 retry 的: 解析失败 / 缺字段 / index 越界 / fit_score 越界 等 —— opus 重答也不会变好, 直接 fallback 省 12s + $0.03

3. **retry 限定 CLI 路径 + 一次性 + 显式纠错 prefix** (`_run_llm_rerank`)
   - 仅 `is_cli=True` 时启用 (主路径 tool_use 不需要)
   - 最多 retry 一次, 失败即正常 fallback
   - prefix append 到 user_msg 末尾 (不改 system prompt, 防 prompt cache 失效并保留 user-turn correction 语义)
   - prefix 内容: ①告知"上次你给了 X exploit + Y explore"; ②要求"正好 N-K + K, 不多不少"; ③明确"其余硬过滤/口味/健康/同品牌择优规则全部仍然生效, 基于原 [CANDIDATES] 重新挑, 不是改标签" (Codex Q3 防 retry 时质量退化)
   - **不**贴上次错误 JSON: 会锁死模型在错误选择, 增加 minimal-edit 倾向而非真正重选

**边界与适用范围**:

- 仅 CLI 自用降级路径, 主路径 tool_use forced schema 无此问题, 也不走 retry
- 仅 count/position 类失败, 不扩展到所有 fallback 场景
- CLI 路径仍属 D-048 边界内的"自用 best-effort", 生产场景应配 `provider=anthropic/openrouter`

**Codex 闭环要点 (D-048.1 教训延续)**:

- Q1 拒绝"代码确定性 demote"方案: 把高分 exploit 改成 `is_explore=true` 会破坏 `one_line_reason` 语义 + 违反"explore 来自 idx≥10"规则, retry 保证语义自洽
- Q2 结构化 error code (落地)
- Q3 correction prefix 明确"其余规则仍生效" (落地)
- Q4 opus 默认在 CLI 自用边界内 OK, 但生产应强走 tool_use (无新动作, 仍属 D-048 定位)
- Q5 根本避坑思路: 不要把硬结构约束交给纯 prompt; CLI = best-effort, 不作为唯一可靠路径 (D-048 已定位, 注释强化)

**trace 字段新增** (调试台 / log 可观测): `retry_attempted` (bool) / `retry_succeeded` (bool) / `retry_first_failure_code` (str) / `retry_latency_ms` (int) / `llm_response_retry` (raw resp). `latency_ms` 保留原始首次调用值不累加, 区分"首次 12s + retry 12s" vs "单次慢 24s"。

`fallback_reason` 格式调整: `candidates 业务校验失败 [<CODE>]: <detail>`, 方便 grep / 调试台 badge。

**dry_run 实测**:
- 修前 opus 无 retry: 2-4/10 fallback, 多样性退化到 5 家店
- 修后 opus + retry: 第一轮 10/10 成功 (其中 1 次走 retry), 第二轮 10/10 成功 (0 retry), 商家分布 12+ 家
- retry 延迟 ~12s + 单次成本 ~$0.03 (合计 ~24s / ~$0.06), 大多数 session 不触发

**变更点**: `chisha/rerank.py` (RerankValidationCode 类 + _RETRY_TRIGGER_CODES + _validate/_diagnose 三元组返回 + _run_llm_rerank retry 块), `chisha/llm_providers/claude_code_cli.py` (`_DEFAULT_MODEL` sonnet → opus), `profile.yaml` (`llm.model.claude_code_cli` sonnet → opus), `prompts/rerank_system.md` (主路径 tool_use 段加计数硬约束 + 边界小节澄清, CLI patch 路径不生效但留着以备未来切回)

依赖: D-047 (provider 抽象 + opus 默认主路径), D-048 (CLI 分流 + status 三态), D-048.1 (prompt 清理 + Codex 跨 AI review 流程)

---

## D-051 — Web 优先, 飞书降级为推送通道

**2026-05-15** · 产品形态决策 → 完整实施细节见 [IMPLEMENTATION_LOG.md#d-051](IMPLEMENTATION_LOG.md#d-051)

> **2026-05-16 状态更新**: 本决策的"V1.5 飞书独立推送通道"部分将被 **D-074 partial superseded** — 砍 V1.5 独立飞书 adapter, 飞书归入 Phase 0 reference adapter; Web SPA 长期保留作算法层迭代台 + Layer 1 protocol consumer (不再是"主交互"). 待 Step 2 完成后落 D-074, 详见 [docs/design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md](../docs/design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md).

**背景**: V1 推荐链路已端到端跑通 (数据 + 召回硬过滤 D-041 + L2 12 维 D-043 + L3 tool_use D-047 + 调试台 D-039 + 反馈闭环 P3), 卡在 D-022 飞书 cron 接入这步。复盘后意识到飞书卡片做"主交互"有几个根本性约束:
- 字段密度低, 自定义控件有限 — refine 多轮对话 / profile 编辑根本放不进卡片
- V1 体验打磨阶段 (推荐质量调优, profile 真实化迭代, UX 反馈节奏) 需要高密度可控的迭代环境
- 调试台 D-039 跟用户视图本来就共享 API/状态/数据, 单 SPA 双路由能让"调推荐"和"用产品"在同一界面同步推进
- claude.ai/design 协同 + localhost FastAPI 的迭代成本远低于飞书卡片渲染层定制

**决策**: V1 主交互改为本机 localhost Web SPA, 飞书延后到 V1.5 做触达通道:
- **用户视图** (`/`): 推荐 3 卡片 + 采纳跳转 + 反馈 chip + refine 输入框 + profile 编辑面板
- **调试台** (`/debug`): 保留 D-039 现态 — L1/L2/L3/Final 四段折叠, 16 维 score breakdown, mood 三栏对比, profile 临时覆盖
- 共享 FastAPI 后端 (扩展现有 `chisha/debug_server.py` 8765 端口) + 共享 React 组件 + 共享状态
- 部署形态: 本机 `uv run python -m chisha.web` 起服务, localhost 单用户无认证
- 飞书在 V1.5 重新接入: 简化卡片 "中午推荐已生成 → 点开看" 推送 + deeplink 跳 Web 处理详细交互

**翻案的 D-022 部分**:
- 飞书"主交互"承诺降级为"推送 + deeplink 通道"。PRD 故事 1 的"扫一眼飞书卡片选一个"形态分两段实现 — 推送时机和触达入口仍在飞书, 详细交互移到 Web
- D-022 标 partial superseded, 不删除 — V1 不接入, V1.5 重新启动时按"轻量推送 + Web 跳转"形态接, 复杂度比原 D-022 设想低

**理由**:
1. **体验迭代速度**: localhost SPA + claude.ai/design 协同, 推荐质量 / UX 节奏 / profile 编辑在同一界面打磨, 改一处见一处效果
2. **profile 真实化的 UI 需求**: D-044 落地后 profile.yaml 复杂度上来了 (price / taste_description / avoid_dishes / min_protein_g), 手编 YAML 摩擦高, Web UI 是天然解
3. **refine 多轮的载体**: D-033 已实现 refine API, 但飞书卡片做多轮自然语言对话交互很别扭, Web 输入框是最佳形态
4. **调试台 / 产品台合一**: D-039 调试台和用户视图共享 API + 组件 + 状态, 改一次推荐链路两边同步, 不再有"产品形态优化但调试台滞后"的漂移
5. **可分发性不损失**: V2.4 拆 pip 包后, 其他人 `pip install chisha + uvicorn chisha.web` 本机起就是同款体验
6. **PRD 北极星指标兼容**: 工作日 7 日采纳率 ≥ 50% 仍可度量 (Web 有 accept/reject 埋点), 比飞书埋点更直接

**反对意见 / 风险**:
- 失去飞书"主动推"的零摩擦触达 (V1 周期内) → 缓解: 自用阶段 macOS launchd / cron 起 chisha.web 服务即可; V1.5 飞书重接补回主动推
- 单 SPA 双路由有耦合风险 (调试台暴露给用户视图导航) → 缓解: 路由级隔离, `/debug` 不出现在用户视图导航, 但代码层共享
- claude.ai/design 产出 React, 后端 FastAPI 要起静态站托管 → 既有 `chisha/static/` 已在用 (debug.html / logic.html), 扩展即可
- 自用阶段单用户无认证, profile.yaml + meal_log 直接落本地文件 → 隐私可控, 但 V2 多用户场景需重新设计

**触发重审的条件**:
- Web 自用一周后采纳率 < 50% (PRD §6 V1 北极星目标未达), 且飞书推送被独立证明能补回触达缺口, 重新考虑 D-022 提速到 V1.5 主交互
- claude.ai/design 产出的设计跟 FastAPI 集成成本高于预期 (> 3 天), 考虑改用 lark card + 简化 Web

**依赖 / 影响**:
- 推翻: D-022 部分 (飞书 V1 主交互 → V1.5 推送通道)
- 影响: PRD §7 删 "Web/小程序/APP 形态" 一行; ROADMAP V1 加 Web SPA 必做项, 已砍清单同步删除
- 不影响: D-001 (本机 localhost 不是 SaaS, 没有用户系统/计费/多租户), D-017 (L3 渲染层是 Skill 输出层范畴, 跟 Web 客户端是两件事)

---

## D-052: Accept 信号去 deeplink, 改持久 inline 锁定 + 复制店名

日期: 2026-05-15
状态: active
背景: V1 用户视图设计原型迭代中, "点 pick → toast 一闪 → 跳 deeplink" 这套互联网厂常见模式在 chisha 场景全部不成立。三个独立失败模式叠加:
- iOS 13+ / Android 12+ 收紧 URL Scheme, 第三方应用 deeplink 拉起率 < 30% — 假装能跳的代价是用户点完一片空白
- Toast 闪一下就消失, 用户没有"系统记到了没"的确认感, 又会回头再点一次
- 其它卡片继续按原样争夺注意力, 不知道哪个是已选

考虑过的方案:
- A. 现状: toast + 尝试 deeplink (≈ 没有持久状态, 30% 跳转成功率)
- B. 单 toast + 不跳 deeplink (减少失败, 但仍无持久确认)
- C. Inline 持久锁定 + 明确告诉用户"打开 APP 搜店名"+ 一键复制店名 (本决策)
- D. 跳一个独立"已选"页 (打断主流程, 用户还要点回去)

决定: C — picked 卡片视觉锁定 (accent 边框 + ✓ 已选 + "改主意 ↺"), 非 picked 卡片淡化 opacity 0.55, 按钮转次级 "选这个"。卡片下方追加 `PickedConfirmation` 面板, 含店名 + 一键复制 + "打开美团/点评搜店名下单 →" 文案。

理由:
- 不假装做不到的事: 明确告诉用户去 APP 里搜店名, 比 30% 概率拉起 + 70% 失败留白要诚实
- 持久 inline 锁定让"刚才点了哪个"可视化, 用户不会重复点
- 复制店名 = 一秒完成 APP 内搜索的桥, 比 deeplink 失败时让用户记忆店名要轻很多
- 反馈页有"你当时点的是 X"回顾条, accept 信号沿同 session_id 流到下游

反对意见 / 风险:
- 多一步操作 (复制 + 切 APP + 粘贴) 比 deeplink 成功的理想路径长一步 — 但 deeplink 成功路径概率太低, 期望值算下来 inline + 复制更优
- 视觉锁定增加界面复杂度 — 但 §6 反模式列表已经砍掉"折叠备选", 信息密度本来就是工程师审美卖点

触发重审的条件:
- iOS / Android URL Scheme 政策松绑, deeplink 拉起率回到 > 70%
- 实测用户在 picked 后仍频繁误点其它卡片 (说明淡化对比度还不够)

依赖 / 影响:
- 设计依据: [docs/design_briefs/v1_user_view.md](design_briefs/v1_user_view.md) §2.2; 落地于 `apps/web/src/components/RecCard.tsx` + `PickedConfirmation.tsx`
- 文案规范: 见 [docs/style-guide.md](style-guide.md) §文案 (零英文 / 零枚举字面值)

---

## D-053: Refine 历史从底部列表升级为顶部面包屑 + smooth-scroll

日期: 2026-05-15
状态: active
背景: 原 brief 把 refine 历史放在底部输入框下方。原型迭代中发现用户的认知是"我做了 X → 系统返回 Y"——因果链需要在空间上紧邻, 把历史塞底部等于让用户每次看完新推荐还要回滚滚动找上下文。同时 refine 输入框的 6 chip 排在上方、自由输入框排在下方, 跟"想用自己的话表达"的主诉相反。

考虑过的方案:
- A. 现状: 底部历史列表 + chip-first
- B. 顶部面包屑 + 自由输入框-first + 自动 smooth-scroll 回卡片区 (本决策)
- C. 用 tab 切换 round (跨轮对比 OK, 但增加 UI 重量, 单用户场景不值)

决定: B —
- 把 refine 历史搬到推荐卡片正上方, 做成横向面包屑 `原推荐 › 想吃辣的 › 换日料 · 这一轮`
- 每段 chip 可点击, 跳到那一轮 (无需 refine 即可跨轮对比)
- 右上角小字 "已根据你的要求换了 N 次" + 重置 ↺
- refine / 回滚 / 重置后 smooth-scroll 到推荐区顶部, 不让用户停在底部
- 没有 refine 时不渲染面包屑 (首次推荐零噪音)
- 输入框在上、6 chip 在下, chip 前加 "或者直接点 ›" 暗示这是次级选项

理由:
- 空间紧邻 = 认知紧邻; 因果链应该挨着出现
- "可点击 chip 跳轮"让用户能 A/B 对比 round1 vs round3, 不要求重 refine
- 自由输入框置顶让"用户用自己的话"成为默认形态, 6 chip 是 fallback
- 没历史不渲染 = 没有 onboarding 噪音

反对意见 / 风险:
- 面包屑横向太长时换行可能割裂视觉 — 缓解: 当前固定每段 chip 短文案, V2 可加溢出折叠
- smooth-scroll 在低端机或动画偏好关闭场景违和 — 缓解: 使用浏览器原生 `behavior: smooth`, 系统 prefers-reduced-motion 会自动降级

触发重审的条件:
- refine 平均 round 超过 5 (面包屑过长)
- 用户实测倾向于点 chip > 直接打字 (反推 chip-first 反而对)

依赖 / 影响:
- 落地于 `apps/web/src/components/RefineCrumb.tsx` + `RefineInput.tsx`; HomePage 协调 scroll
- 设计依据: [docs/design_briefs/v1_user_view.md](design_briefs/v1_user_view.md) §2.3 / §2.6

---

## D-054: Skip-meal escape hatch (6 reason chip)

日期: 2026-05-15
状态: active
背景: 不是所有打开 chisha 都以"点外卖"结束。用户可能去食堂、自带饭、在外吃、和同事一起、都没看上、不饿。原版没有跳过餐的退出路 → 用户直接关页面 → unfed banner 继续弹 → 数据漏记 → 推荐模型把"看了不选"当成噪音, 学不到真实负样本。

考虑过的方案:
- A. 现状: 没有 escape hatch (banner 持续打扰, 数据漏记)
- B. 一键"跳过"按钮 (有出口但学习信号最弱)
- C. 默认 collapsed + 6 reason chip + 兜底"不说原因·跳过" (本决策)

决定: C — 主页底部增加 `SkipMealAction` 组件:
- 默认 collapsed, 一行小灰字 `这顿吃别的，跳过 →`
- 点开展开 6 个原因 chip: 食堂 / 自带饭 / 在外吃 / 和同事一起 / 都没看上 / 不饿
- 保留 "不说原因·跳过 →" 兜底, 不强制选原因
- 跳过后卡片区折叠为 `SkippedState` 面板 ("本餐已跳过 · 已记录原因 · 撤销 ↺")
- API: `POST /api/skip { session_id, reason }` 清掉对应 acceptedQueue 条目, banner 不再弹

理由:
- **信号价值**: "在外吃 / 食堂 / 都没看上" 对推荐模型是三种完全不同的负样本; 多花 1 秒选个原因, 学习信号约 5×
- "不饿"是健康信号, 不该当负样本扣分 (跟"都没看上"分流)
- 默认 collapsed 避免给"通常会点外卖"的多数路径增加视觉噪音
- 撤销路径保留 — 用户错点跳过后能立刻恢复, 不丢 session

反对意见 / 风险:
- 6 chip 可能不够覆盖真实场景 — 缓解: V2.1 根据采集到的 "都没看上 → 接着 refine" 序列细化原因
- 用户嫌多一步操作直接关页面 — 缓解: "不说原因·跳过" 兜底, 等价于一键跳过, 但留 session_id 记录

触发重审的条件:
- "都没看上" 占比 > 30% (推荐质量需要回退 L2/L3)
- "在外吃 / 和同事一起" 占比稳定 > 20% (考虑 V2.1 把 lunch 时段做"今天会去外面吃吗"前置)

依赖 / 影响:
- 后端 API: 新增 `POST /api/skip` 端点, 详见 [docs/api.md](api.md) §5
- 落地: `apps/web/src/components/SkipMealAction.tsx` + `mockApi.skipMeal`
- 设计依据: [docs/design_briefs/v1_user_view.md](design_briefs/v1_user_view.md) §2.4

---

## D-055: 同 session 抑制 unfed banner

日期: 2026-05-15
状态: active
背景: PendingFeedbackBanner 由 `lastUnfed()` 驱动, 显示"中午吃的 X 怎么样?5 秒反馈一下 →"。设计原型迭代中发现一个尴尬边界: 用户在主页 11:25 看推荐 → 点 pick → unfed 立刻出现 → banner 弹出, 但用户还没吃, "饭后了吗" 的引导文案完全错位。

考虑过的方案:
- A. 现状: 任何时候 unfed 非空都弹 banner (即使是当前会话)
- B. 加时间窗口 (距 accept > 30min 才弹) — 但时间窗口在不同餐点不一样, 难调
- C. 同 session_id 抑制: 当 `unfed.session_id === current.session_id` 时不渲染 banner (本决策)

决定: C — Home 渲染时检查:
```ts
const sameSession = unfed && session && unfed.session_id === session.session_id;
const shownUnfed = sameSession ? null : unfed;
```

理由:
- session_id 是天然的"决策态 vs 回顾态"边界 — 同 session 一定还在决策态, 没必要催反馈
- 不依赖时间, 避开"距 30min 还要不要弹"的调参陷阱
- 跨 session (中午 pick 完关页面, 下午 14:00 重开) 自然进入回顾态, banner 该弹时弹

反对意见 / 风险:
- 用户在同 session 内 refine 多轮、最终关闭页面没吃, banner 也不会弹 — 但 D-054 的 skip 路径已经覆盖, 不重复
- 同 session_id 跨大段时间 (理论上 refine 后过几小时回来仍是同 session) banner 仍被抑制 — 缓解: session 在跨日时由后端切, 实际不会发生

触发重审的条件:
- 用户实测"明明吃完了却没看到 banner"占比 > 5% (说明 session 边界判断不够)

依赖 / 影响:
- 落地: `apps/web/src/pages/HomePage.tsx` 渲染层的 `shownUnfed` 计算; 后端 `lastUnfed()` 不需要改
- 设计依据: [docs/design_briefs/v1_user_view.md](design_briefs/v1_user_view.md) §2.2 末段

---

## D-056: NavBar 加「反馈」tab + 角标 (V1.1)

日期: 2026-05-15
状态: active
背景: V1 入口架构 (D-051~D-055) 时, 反馈入口只有主页顶部一条 `PendingFeedbackBanner`。三个失效场景:
- banner ✕ 关掉后, 那顿饭再也找不到反馈页 (URL 不可记忆 / 无主动入口)
- 多条积压时只看到最近一条, 隔天点别的 → 旧条目实质失踪
- 没有"我所有的反馈记录"全局视图, 用户不知道系统记了什么

决定: NavBar 加第三个 tab「反馈」, 跟「历史」「偏好」并列。永远可见 = 永远可达。
- 角标显示积压数 (active unfed, 未 snooze 未 stop)
- 点击进 `/feedback` 反馈中心 (见 D-058)
- 角标 ≤ 0 时不渲染

理由:
- 反馈跟历史 / 偏好同级 — 都是"我的过往"维度
- "积压几餐没打分"是用户**主动查看**的状态, 不能只靠 banner 弹出 (被关掉就丢)
- 顶导栏 ≤ 3 tab 仍在密度上限内

反对意见 / 风险:
- 又多一个固定 tab, 顶导栏更挤 — 但 V1 没有"主页广告位" / "搜索" 这类需要争位置的对手, 顶导栏密度可承受
- 角标可能给用户压力 (3 餐没反馈 ↔ "未读消息" 心智) — 缓解: snooze (D-060) 让用户能主动消角标

触发重审条件:
- 实测用户从未点开过反馈 tab (说明角标 = noise, 改 dot 形态或干脆撤掉)
- 角标 > 20 经常出现 (说明 stop / snooze 路径不够好用, 用户没用 → tab 噪声)

依赖 / 影响:
- 落地: `apps/web/src/components/NavBar.tsx`; 数据从 `useChishaState.inbox` 读
- 配合: D-057 banner 升级 + D-058 inbox 页

---

## D-057: PendingFeedbackBanner 升级为卡片 + 多条堆叠 (V1.1)

日期: 2026-05-15
状态: active (取代 D-051 slim banner 形态)
背景: D-051 落地的 banner 是 slim 形态 (一行细 banner + 关闭 ✕), V1.1 入口架构 review 中发现三个不足:
- 信息密度低 — 餐厅名 + summary + meta 全堆一行, 容易被瞟过去
- 单条心智 — 只显示最近一条, 多条积压时旧条目隐形
- 操作模糊 — ✕ 是"以后再说"还是"永久关闭" 没区分 (见 D-060)

决定: 改卡片堆叠形态:
- 顶部 metadata 行: ● 待反馈 · 3 小时前 · 午餐 · 右侧 ⋯ 菜单
- 主体: 餐厅名 (font-semibold 14.5px) + summary 一行 line-clamp
- 底部 footer: 「5 秒反馈一下 →」 + 「还有 N 餐没反馈 去反馈中心 →」(N>0 时显示)
- ⋯ 菜单提供 snooze / stop 显式两选项 (见 D-060)
- 卡片视觉用 accent 6% 染色背景 + 35% 边框, 比 slim 形态显眼一档

理由:
- 多条堆叠把"主卡 + 余量提示"做成显式信息层, 不会丢条目
- 卡片形态有"未读消息"心智, 比 slim banner 的"导航条提示"更能驱动行为
- ⋯ 菜单语义清晰 (snooze 一档 / stop 二档) 解决 ✕ 模糊问题

反对意见 / 风险:
- 比 slim 形态占主页更多空间 (从 ~42px → ~110px) — 但只在有未反馈时才出现, 且反馈是 V1.1 的核心闭环, 占位合理
- 实施复杂度高 (metadata 行 / ⋯ 菜单 / footer 三层) — 但 detail / inbox / banner 复用同一卡片结构 (DRY)

触发重审条件:
- 实测主页采纳率因 banner 占位下降 > 10%
- 用户 ⋯ 菜单使用率 < 5% (说明 banner 内菜单是 noise, 改 ⋯ 只显示 inbox 链接)

依赖 / 影响:
- 落地: `apps/web/src/components/PendingFeedbackBanner.tsx` (全量改写); 砍掉 SlimBanner 函数
- 配合: D-056 + D-058 + D-060

---

## D-058: /feedback 反馈中心新路由 (V1.1)

日期: 2026-05-15
状态: active
背景: D-056 决定 NavBar 加反馈 tab 后, tab 落地页必须是个反馈中心 (不是直接跳第一条反馈 — 那是 `/feedback/last` 的事)。中心页要解决三件事:
- 看全部待反馈条目 (不只是 banner 上那条)
- 区分 snooze (临时) vs stop (永久) vs 已反馈 三种状态
- 给「snooze 一条」/「stop 一条」 一个非 banner 的操作入口

决定: `/feedback` 三段式列表:
- **待反馈** (active): 卡片样, ⋯ 菜单提供 snooze / stop
- **暂缓** (snoozed): 灰度卡片, ⋯ 菜单只剩 stop (已 snooze 不需要再 snooze 一次)
- **已反馈** (recent feedbacks): 简洁横条 + gut chip (👍/😐/👎) + 点击进 detail
- 空状态: 「都跟进完了 — 收工」+ 回主页链接

理由:
- 三段语义对应反馈生命周期 (待办 / 软搁置 / 完成), 跟 inbox 心智一致
- 暂缓段不隐藏 — 让 snooze 不变成"丢失" (D-060 说 snooze 是 "我现在没空" 不是 "扔了")
- 已反馈段限制 6 条 (recentFeedbacks limit=6) — 老反馈应该走 history 查, 这里只承担"最近几餐"心智

反对意见 / 风险:
- 三段 + ⋯ 菜单 + 空状态, 比 inbox 简单列表复杂 — 但语义不能合并 (snooze 跟 active 行为不同), 三段是必要的
- 「已反馈」段跟 `/history` 已反馈行重叠 — 这是有意冗余: history 是按日期, inbox 是按反馈状态, 两个心智都有用

触发重审条件:
- 实测「暂缓」段从未被点开 (说明 snooze 用户的真实意图是 stop, 应该合并)
- 「已反馈」段从 inbox 入口的点击率 < 1% (说明 history 完全覆盖, 砍掉这段)

依赖 / 影响:
- 落地: `apps/web/src/pages/FeedbackInbox.tsx`
- API: 新增 `GET /api/feedback/inbox?include_snoozed=` (代替 `last_unfed` 单条) + `GET /api/feedback/recent` (代替原 placeholder)
- 配合: D-056 NavBar tab + D-060 snooze/stop 语义

---

## D-059: /history 每行可点击进反馈 (V1.1)

日期: 2026-05-15
状态: active
背景: D-051 落地的 history 页是只读列表 (日期 / 餐次 / mood / candidates / accepted_rank), 用户看到"昨天点的 X 还没反馈" 没有直接操作入口, 必须去主页看 banner 或去新 inbox。割裂。

决定: history 每行可点:
- 未反馈行 → 跳 `/feedback/<sid>` 进表单
- 已反馈行 → 跳 `/feedback/<sid>` 进 detail view (双态分支 D-066)
- 跳过餐 (accepted_rank=null 且无反馈记录) → 不可点, 显示"都没吃" 灰字

视觉:
- 未反馈行加紫色「未反馈」chip (accent-bg + accent 字)
- 已反馈行加 gut chip (👍 好吃 / 😐 普通 / 👎 难吃) — 替代原 ★4/4 双 5 星显示 (legacy schema)
- 跳过餐保持原状, hover 不变色

理由:
- "我从哪里发起反馈" 应该跟"我从哪里看历史" 是同一个动作 — 历史和反馈本质是同一组数据
- 跨页面联动: 主页 banner 解决"刚吃完", inbox 解决"最近积压", history 解决"翻旧账" — 三条路径都通 detail
- chip 形态切换 (★ → 👍/😐/👍) 是 D-063 信号框架的视觉化, 跟 schema 一致

反对意见 / 风险:
- 行可点击 + chip 多色 → 视觉密度上升, 列表更花 — 但 history 本来就是低频页 (每日 < 1 次访问), 信息密度比留白重要
- 跳过餐不可点是 dead row, 视觉有断裂 — 但 跳过餐没有反馈 schema, 强行让它可点是假装

触发重审条件:
- 实测从 history 跳反馈的点击率 < 5% (说明 inbox + banner 已覆盖, history 不用承担入口)

依赖 / 影响:
- 落地: `apps/web/src/pages/HistoryPage.tsx`
- 配合: D-063 gut chip 视觉 + D-066 双态分支

---

## D-060: Banner ✕ = snooze (24h 软); ⋯ 菜单 = stop (永久) (V1.1)

日期: 2026-05-15
状态: active (取代 D-051 banner ✕ = dismiss 单态)
背景: D-051 的 banner ✕ 是单态 "dismiss = 永久消失"。原型 review 中发现这是错误抽象:
- 用户场景 A: "我现在工作中, 一会儿再填" → 想要软关闭
- 用户场景 B: "这餐我不想再被提醒了 (吃了但忘了细节 / 真不想反馈)" → 想要硬关闭
- 单 ✕ 把这两种都映射成"永久消失" → A 用户的反馈丢失

决定: banner 关闭操作分两态:
- **snooze (软关闭)** = ✕ 默认 / ⋯ 菜单「以后再说」 → 24h 不显示在 banner, **但 inbox 暂缓段仍在**, 用户主动回来还能填
- **stop (硬关闭)** = ⋯ 菜单「这餐别催了」 → banner 永久不显示, inbox 也移除, **但 history 行仍可点进表单** (D-059 兜底)

数据语义:
- snooze = "我现在没空" → 不污染推荐模型 (用户暂时回避, 不代表负面信号)
- stop = "这条不该被催" → 也不污染推荐模型 (用户的反馈记录意愿, 不是菜的质量信号)
- 两者都**不**作为 ranking signal — 跟反馈本体 (D-063) 区分

理由:
- 给 A 用户兜底: 软关闭后用户回来还能填, 数据闭环不丢
- 给 B 用户出口: 不会被同一条催到底
- 默认 ✕ 是 snooze 而不是 stop (用户最常用的是"暂缓"而不是"永久")
- ⋯ 菜单显式两选项 — 用户主动选 = 显式意图, 比单按钮的双关语义清楚

反对意见 / 风险:
- 两态增加复杂度, 用户可能不区分 — 但即使用户全选 snooze 也无害 (24h 后回来), 兜底不会丢数据
- stop 是单向, 没有撤销 — 但 history 行可点 (D-059) 是兜底入口, 用户想反馈还能找到

触发重审条件:
- 实测 ⋯ 菜单使用率 < 5% (说明用户根本不区分两态, 改回单 ✕ 默认 snooze)
- 实测 stop 后 24h 内用户主动找入口反馈占比 > 20% (说明 stop 语义太重, 改成 7 天 snooze)

依赖 / 影响:
- 落地: `apps/web/src/components/PendingFeedbackBanner.tsx` ⋯ 菜单 + `useChishaState.refreshInbox` 联动
- API: `POST /api/feedback/snooze` + `POST /api/feedback/stop` 两个端点 (mock 走 `snoozed_until` timestamp + `stopped` bool 字段)
- 砍掉: 原 `POST /api/session/dismiss_feedback_banner` (语义被 snooze 取代)

---

## D-061: 反馈表单探索 5 个方向 (方法论) (V1.1)

日期: 2026-05-15
状态: archived (方法论档案, 选定 E 见 D-062)
背景: V1 反馈表单 (好吃度 5 星 + 整体满意 5 星 + 4 chip + 备注) 有 4 个核心问题:
- 信号冗余 (accept 已记 rank, 又让用户 radio 一次)
- 维度模糊 (好吃度 vs 整体满意 用户分不清差别)
- 信号贫瘠 (4 chip 没问推荐模型最需要的字段)
- 完成感缺失 (toast 一闪就跳走)

决定: 设计阶段并行做 5 个变体, live 可切换对比:

| ID | 方向 | 哲学 | payload signature |
|---|---|---|---|
| A | 极简一击 | 一个值就走 | `{ rating: -1\|0\|1, note }` |
| B | 维度面板 | 5 个 segmented 维度全打 | `{ taste, portion, oil, body, repeat }` |
| C | 对话式 | LLM 风格 3 轮问答 | `{ q1, q2, q3, note }` |
| D | 复盘卡 | 当时 vs 实际 两栏 | `{ retro: { reason, protein, oil, price, wetness } }` |
| E | 渐进披露 | 5 秒 floor + 想多说则展开 | A 头部 + D 展开 |

理由:
- 5 个变体不是为了选其一然后扔 4 个, 是为了在产品 review 时**摸清取舍空间**
- 每个变体对应一个"什么用户最痛"的假设 — 多变体并行让取舍显式化
- 选定后保留 archived 方法论档案 (本条), 后续 V2 变体 (deep retrospective / contextual prompt 等) 还有参考

反对意见 / 风险:
- 5 个变体的实现成本远高于一个 — 但是设计阶段一次性投入, 选定后只留 1 个, 后续维护成本不变
- 用户/产品方在 5 个之间纠结时间过长 — 缓解: live switcher 上线 1 周内必须收敛 (本次 1 天内收敛到 E)

依赖 / 影响:
- 这是方法论决策, 不是产品决策 — 落地结果在 D-062
- 原型档案 (5 个变体源码) 保存在 `chisha-user (1)/feedback-variants.jsx` (设计交付物); 正式工程只保留 E

---

## D-062: 选定 E 渐进披露 + 借鉴 D 复盘卡形态作为生产方向 (V1.1)

日期: 2026-05-15
状态: active
背景: D-061 5 变体 review 后取舍空间清楚了:
- A 极简: 信号太薄 (只有一个 gut 值, calibration 信号 0)
- B 维度: 5 个 segmented 全部必填心智, 多数用户填到一半放弃
- C 对话: 模仿 LLM 心智不必要, 用户来反馈不是来聊天
- D 复盘: prediction vs reality 信号最丰富, 但首屏密度太高劝退 "5 秒打分" 用户
- E 渐进: 头部 5 秒打分 / 展开后 4 维细 calibration — A 的低门槛 + D 的高信号兼得

决定: 选 E 作为生产方向, **形态借鉴 D 复盘卡**:
- 头部 = E 原版 3 档情绪一击 (👎 / 😐 / 👍) — 覆盖"我就是想 5 秒打个分"用户
- 展开区每行 = D 复盘卡的 3 列形态 (label / 当时 prediction / 你实际) — 覆盖"我想给系统更多信号"用户
- 头部跟展开**视觉强对比**: 头部是一击式 3 大按钮 + 28px emoji, 展开是 segmented 行表 + 11px label

理由:
- 5 秒 floor + 展开 ceiling 是反馈表单的最优结构 — 两端用户都能舒服 (低门槛 ≠ 信号贫瘠)
- 借鉴 D 的 "prediction vs reality" 心智解决"反馈给系统什么" 的问题 (告诉系统它当时哪里说错了 = 最高 ROI 信号)
- 展开按钮加 "送系统一个礼物" 文案 — 把"多花 30 秒填一下"包装成正向行为 (而不是"额外字段")

反对意见 / 风险:
- 展开率可能 < 20% → 4 维 calibration 数据稀疏 — 但稀疏总比 0 强, 且头部 gut 信号也能用 (作为 prior)
- 展开按钮的"礼物"文案有诱导性 — 但反馈本来就是用户帮系统, 文案诚实陈述这件事并不算 dark pattern

触发重审条件:
- 展开率 < 10% 持续 2 周 (说明展开成本仍太高, 考虑默认展开 / 直接 D 形态)
- 展开后填完率 < 50% (说明 4 维太多, 砍到 2-3 维)

依赖 / 影响:
- 落地: `apps/web/src/components/feedback/ProgressiveForm.tsx`
- 砍掉: A/B/C/D 4 个变体 + variant switcher (生产不要)
- 配合: D-063 信号框架 + D-064 头部语义 + D-065 4 维定义

---

## D-063: 反馈字段的信号框架: calibration / behavior / gut 三类 (V1.1)

日期: 2026-05-15
状态: active · 方法论框架
背景: 选 E (D-062) 后, 必须决定**展开区填哪些字段**。空想容易塞太多 (像 V1 原版 4 chip + 2 ★ 6 个字段) 或太少 (像 A 单 gut 信号贫瘠)。需要一个"该不该加这个字段"的判别准则。

决定: 反馈字段按对推荐模型的作用分三类:

| 类型 | 用处 | 字段示例 | 信号权重 |
|---|---|---|---|
| **calibration** (校准) | 降低 prediction loss | 油 (预估 2.3/5 → 用户说太油) → 下次 oil_level 估值降一档 | 中高 (loss 直接) |
| **behavior** (行为) | 直接 ranking signal | "下次还点" → strong positive 进 user history | 高 (排序硬信号) |
| **gut** (整体) | 整体好坏 prior | 难吃 / 普通 / 好吃 → weight 低, 不压细维度 | 低 (易被压住, 但做兜底 prior) |

**字段 ROI 准则**: 能否反向修改某个具体 prediction 或排序逻辑?
- 能 → calibration (改对应预估字段曲线) 或 behavior (进 ranking)
- 不能 → 删掉 (再"有用"也不该塞)

理由:
- 给"该不该加这个字段"一个机械化判别 (而不是"产品 sense") — 避免随手加字段
- 三类显式分离, 下游模型消化时 weight 不同 (calibration 用 reverse-loss, behavior 用 ranking signal, gut 用 prior)
- gut 一个就够 — 整体观感不需要双维度 (好吃 vs 满意 这种重叠维度被砍掉, 见 D-064)

反对意见 / 风险:
- 三类分得太硬, 现实字段可能跨类 (如"分量" 既是 calibration 又是 behavior) — 缓解: 选最强信号那类归类, 跨类只是描述
- 准则可能让产品过度保守 (砍掉"反馈时长" / "心情" 等弱字段) — 但 V1.1 阶段保守是对的, V2 学习曲线起来后再加

触发重审条件:
- 实测 gut 信号的下游影响力 > calibration (说明 weight 设错, 或框架不对)

依赖 / 影响:
- 砍掉的字段 (V1 原版 + 这次 review 砍): 好吃度+整体满意 (双 ★ 5 星, 维度模糊) / 4 chip (偏油 / 分量小 / 配送慢 / 想再来, 散乱无 calibration) / 分量 (系统不能"加 50g", 并入饱腹感) / 汤水带感 (binary 信号弱) / 价格-时间 (决策心智但跟推荐弱相关) / 身体感受 (太抽象)
- 落地分配:
  - calibration 字段 = `reason_match` / `fullness` / `oil_calibration`
  - behavior 字段 = `repurchase_intent`
  - gut 字段 = `rating` (-1/0/1)

---

## D-064: E 头部 = gut (好吃度 难吃/普通/好吃), 跟 behavior 字段分离 (V1.1)

日期: 2026-05-15
状态: active
背景: 选定 E 头部 3 档情绪一击 (D-062), 接下来要决定头部三档**问的是什么**:
- 方案 A: "下次还点吗" (behavior signal)
- 方案 B: "整体好吃吗" (gut signal)
- 方案 C: "整体满意吗" (gut signal 但维度模糊)

决定: 方案 B — 头部三档语义 = **整体好吃度 (gut)**, 选项 = **难吃 / 普通 / 好吃**。

理由:
- 一个菜可以**好吃但贵不会再点** (好吃 + 不还点) — 好吃度跟复购意愿是**两个独立维度**, 头部只能问一个
- 头部应该问最快回答的那个 — "好吃吗" 比 "下次还点吗" 决策成本低 (好吃是即时感受, 还点是综合判断)
- 复购意愿 (behavior, 排序强信号) 放到展开区 (D-065 的 `repurchase_intent`), 让真正想给系统信号的用户填
- 砍掉"整体满意" 选项 — 它跟"好吃度"维度重叠 (V1 原版的 5 星 ×2 错误), 模糊性比信号高

反对意见 / 风险:
- 难吃 / 普通 / 好吃 三档粒度粗, 损失中间信号 (比如"好吃但偏咸") — 但这正是展开区 4 维的设计目的, 头部不背负这个负担
- 用户可能不分"好吃"和"还点" (心智上混淆) — 但展开区"下次还点" 字段会强迫他们再想一次, 双信号互相校验

依赖 / 影响:
- schema: `rating: -1 | 0 | 1 | null` (-1 难吃 / 0 普通 / 1 好吃 / null 没打)
- 取消原 V1 schema 的 `rating_taste 1..5` + `rating_satisfaction 1..5` 双维度 5 星
- 落地: `apps/web/src/components/feedback/ProgressiveForm.tsx` 头部三档 GUT_OPTIONS

---

## D-065: E 展开 4 维, 每行对齐当时 prediction (V1.1)

日期: 2026-05-15
状态: active · schema 钉住
背景: D-063 框架 + D-064 头部确定后, 展开区填什么字段、怎么呈现:
- 字段必须满足 D-063 的 ROI 准则 (能反向改 prediction 或 ranking)
- 呈现必须把"当时系统怎么说" 摆给用户看 (D-062 借鉴 D 复盘卡: prediction vs reality)

决定: 展开区 4 维, 每行 3 列 (label / 当时 prediction / 你实际 3 档选项):

| 字段 | 类型 | 选项 | 服务下游 |
|---|---|---|---|
| **推荐理由** (reason_match) | calibration | 正中 / 还行 / 没感觉 | **LLM reason generator reverse-loss · 最高 ROI** |
| **饱腹感** (fullness) | calibration | 不够 / 刚好 / 太多 | protein 预估曲线 + 分量综合 |
| **油腻感** (oil_calibration) | calibration | 太油 / 刚好 / 太淡 | `oil_level` 估值校准 |
| **下次还点** (repurchase_intent) | behavior | 不会 / 偶尔 / 会 | repurchase (最强 ranking signal) |

呈现:
- "当时 prediction" 列动态渲染: reason 显示 clipReason(reason_one_line) / fullness 显示 ProteinPred(g) / oil 显示 OilPred(level) / repurchase 显示 "—" (没有 prediction)
- 3 档选项是 segmented 横排, 都可点 → 取消选中
- 每个字段独立, 全部 optional (null 表示用户没填)

理由:
- 4 维全是 D-063 ROI 准则下"能反向修改具体 prediction 或排序" 的字段, 一个都不浪费
- "reason_match" 是最高 ROI: LLM reason generator 没有别的反向训练信号 (其他 prediction 用数值校准, reason 只有 reverse-loss feedback)
- "prediction vs reality" 呈现让用户在填的过程中**自动复盘**系统说错了哪里, 信号质量高于纯打分
- 4 个不多不少: 砍到 3 个会丢一个高 ROI 字段, 加到 5 个会让展开率从 ~30% 跌到 ~15%

反对意见 / 风险:
- 4 维全 optional, 用户可能只填 1 个 — 但 1 个 calibration 信号也比 0 强, 且展开按钮显示已填数量是激励
- prediction 列动态渲染增加组件复杂度 — 但 `buildDimRows()` 共享给 detail view 复用 (DRY)

触发重审条件:
- reason_match 反向训练效果差 (LLM reason 命中率长期没改善) → 重审 reason_match 是不是信号本身有问题 / 还是模型消化方式错
- 实测 4 维平均填写数 < 1.5 → 说明 4 维太多, 砍到 3

依赖 / 影响:
- schema: `reason_match / fullness / oil_calibration / repurchase_intent: 0 | 1 | 2 | null` (0=低 / 1=中 / 2=高)
- 落地: `apps/web/src/components/feedback/atoms.tsx::buildDimRows()` 共享给 form + detail
- 下游消化: 见 [DESIGN.md §反馈消化](../DESIGN.md) (待补) + [PRD §反馈循环](PRD.md)

---

## D-066: 反馈一次性提交 = 永久 readonly, 不可修改 (V1.1)

日期: 2026-05-15
状态: active · schema 钉住
背景: 反馈表单提交后是否允许编辑/撤销, 是一个 schema 层面的根本决策。考虑过:
- A. 完全可编辑 (像 todo 任务)
- B. 时间窗口可编辑 (5 分钟内 / 24 小时内)
- C. 永久 readonly (本决策)

决定: C — 提交即永久 readonly, **不分时间窗口**。

理由:
- 反馈是 **timestamped fact**: "我在 2026-05-15 19:43 觉得这顿好吃" 这件事不应该 retroactive 改
- 改 = 推荐模型基础不稳定: 如果用户 1 周后改了反馈, 中间这周基于旧反馈做的推荐 / 学习全部需要回溯重算
- "事后回想" 的需求由 D-067 的 append-only timeline 满足 (新数据点, 不污染原始反馈)
- 时间窗口 (方案 B) 是错误妥协: 5 分钟内能改 ≠ 5 分 01 秒不能改, 边界毫无 product 意义, 实施复杂度高且用户难以理解

反对意见 / 风险:
- 用户打错字 / 误点 (难吃 vs 好吃) 没法修 → 缓解: append 备注「上面打错, 应该是好吃」, 下游 LLM 可消化文本; V2 加显式"撤销重提" (D-068 待办)
- "永久 readonly" 心智重, 用户犹豫不填 → 实测如此再降级为 24h 窗口

触发重审条件:
- 实测 (V1.1 自用一周) 用户因怕填错而不提交占比 > 20% → 降级为时间窗口
- "append 备注修正打错" 占 timeline 条目 > 30% → 说明 readonly 严苛, 改 24h 窗口

依赖 / 影响:
- schema: `FeedbackRecord` 提交后所有 calibration / behavior / gut / note / accepted_rank 字段全部 frozen
- detail view (D-066 落地): 全部字段渲染为只读, 标"已封存 · 不可修改, 但可以追加备注"
- 落地: `apps/web/src/components/feedback/FeedbackDetailView.tsx` 替换 form 渲染

---

## D-067: 永远可 append 备注 (append-only timeline) (V1.1)

日期: 2026-05-15
状态: active · schema 钉住
背景: D-066 说 readonly, 但用户事后确实有补充需求 ("第二天回想, 胃确实有点重" / "下次还会再点但要备注少油") — 这些是**新观察**, 不是"修正"。需要给一个表达通道, 但不能让它污染原始反馈。

决定: 在 detail view 加 append-only timeline:
- 用户在 detail view 输入框写补充 → 调 `POST /api/feedback/<sid>/comments { text }` → 后端 push `{ id, text, created_at }` 到 `feedbacks[sid].comments[]`
- 每条 append 是**独立 timestamped 数据点**, 不修改原始反馈
- timeline 在 detail view 按时间正序展示, 圆点标记 + 相对时间
- comments[] 可以无限增长 (无 cap), 用户随时可以加

数据语义:
- comments[] **不进数值模型**: 不像 rating / dimensions 有结构化映射
- comments[] **作为 LLM context inject**: 下次给同店推荐时, prompt 里加 "用户上次对该店反馈: [原 note] / 后续补充: [comments]" 让 reason generator 消化
- comments[] **跟原始反馈分开**: ranking / calibration 还是看原始字段, comments 只影响 reason 生成

理由:
- 给"事后回想"出口, 但隔离 — 原始数据稳定, 新数据增量
- append-only 比"编辑覆盖" 信息密度高 (能看到用户心智演变, 不只看最新结论)
- 不结构化 (纯文本) 是有意为之: V1.1 阶段不知道用户会写什么, 先收文本, V2 再做 chip / emoji 结构化 (D-068)

反对意见 / 风险:
- 用户可能在 comment 里写"上面打错了应该是好吃" 而不是新观察 — 这就是 D-066 readonly 的副作用; 不修, V2 加显式"撤销重提" 解决
- comments[] 无 cap 长期可能膨胀 — 实测如果有用户写 > 50 条再加, V1.1 阶段不优化

依赖 / 影响:
- schema: `FeedbackRecord.comments: Array<{ id, text, created_at }>` (typed in `apps/web/src/lib/types.ts`)
- API: `POST /api/feedback/<sid>/comments { text }` 新增端点
- 落地: `apps/web/src/components/feedback/FeedbackDetailView.tsx` append 表单 + timeline 渲染

---

## D-068: V1.1 砍掉的辅助功能 (放 V2) (V1.1)

日期: 2026-05-15
状态: active · 范围决策
背景: V1.1 反馈系统 review 中提了几个辅助功能, 都被砍到 V2:
- 删除反馈 (GDPR / 用户主权角度有用, V2 做)
- 编辑反馈 (即使有时间窗口也不做, 强制 append-only, 见 D-066)
- 反馈历史专门入口 (暂时复用 inbox 已反馈段 + history)
- Comment 的 chip / emoji 结构化输入 (让 append 也是数值信号, V2 做)
- 反馈 banner 一键打分 (banner inline 三档迷你打分, 原型 card variant 有 mock, schema 已预留 `quick: true` 标记)
- A/B 实验框架 (暴露 `feedbackVariant` tweak 用于线上实验)
- 反馈数据回灌到推荐推理时的 streaming 处理

决定: 全部砍到 V2.0+, V1.1 不做。

理由:
- V1.1 是反馈闭环 MVP, 目标是"用户能填 + 系统能用", 辅助功能不影响这个最小闭环
- "Comment 结构化" 等需要 V1.1 自用一周收集真实文本后, 再设计 chip / emoji 集合 — 提前设计会拍脑袋
- 删除 / 撤销在 V1.1 用户实测中如果痛点高, 触发 D-066 重审; 不痛就推 V2

依赖 / 影响:
- ROADMAP V2.0 待办里加: "反馈系统 V2 增量 (删除 / 撤销 / Comment 结构化 / banner 一键打分 / A/B 框架)"
- 不影响 V1.1 schema 设计 — `quick: true` 字段已在 schema 预留 (D-063), banner 一键打分上线只是前端补 UI

---

## D-070: 产品定位收敛到「原则派点餐助手」+ 三层信号模型 (V1)

日期: 2026-05-15
状态: active · 产品定位决策 · 修订 PRD §1 / §3

背景: D-069 后端联调完, 准备进入"自用一周采数据"。Web 首屏 mood picker (随便/清淡/解馋/轻食 4 chip) 实施细节复盘时, 用户挑战这套交互是否合适, 引发产品定位重审。

发现的根因:
1. mood picker 违反产品本意 — "今天吃点啥"的用户**已经不知道吃啥**, 让他先选 mood 是反向加 cognitive load
2. **stated preference ≠ revealed preference** (餐饮经典坑) — 用户说想清淡然后点红烧肉是常态; 让用户主动声明 mood 采集的是最不可靠的那种信号
3. mood 4 个选项**维度杂糅** — 清淡 (口味) / 轻食 (餐型) / 解馋 (情绪) / 随便 (无信号), 根本不在一个语义层
4. PRD §2.2 已写过真实用户痛点: "**认了哈佛餐盘方法论, 但每次点餐还得自己想这家有蔬菜吗、这道菜油重不重**" — 这是**执行摩擦**, 不是**目标缺失**, 两种问题解法完全不同

定位收敛:
- **「原则派点餐助手」** — 给已经认定一套吃法、但懒得每天选店的原则派, 30 秒搞定外卖决策
- 服务: 已经有自己饮食方法论 + 控制目标的人 (减脂 / 增肌 / 糖控 / 孕期 / 高血压 / 纯味道讲究...), 痛点是**执行成本**
- **明确不服务**: 目标缺失型用户 ("什么都行又什么都不想吃" / 完全不在乎吃啥) — 这是目标推导问题, 同一产品很难同时服务好执行摩擦与目标缺失

三层信号模型 (统一架构概念):

| 层 | 时间尺度 | 归属 | 内容 |
|---|---------|------|------|
| **L0 方法论层** | 几乎不变 | profile-level | 饮食方法论 spec + 个人口味 + zone/价格 → 决定 L2 baseline 权重 + L1 召回硬过滤 |
| **L1 长期反馈层** | 慢变 | V1.1 已建 | 历史采纳/拒绝/评分聚合 → boost/penalty hints, 调权不改 baseline |
| **L2 当下 session 层** | 低频偶尔 | session | refine 文本 + 上一顿摘要, 仅本 session 影响 L3 |

关键设计推论:
- mood picker 试图捕捉 L2 信号, 但在方法论用户视角下: clean/light = baseline (L0 已固化), indulgent = 偏离 baseline (低频, refine 文本兜底), soup = 唯一真痛点 — 详见 D-071
- 大维度差异 (减脂 vs 增肌 vs 糖控) = L0, 通过 methodology spec 表达 (D-072), 不是 session 级 mood
- "数据缺失就按季节兜底"(D-043 `infer_default_mood`) 在方法论用户视角下是错的 — baseline 已固化, 不需要兜底

Phase 路线 (取代旧 V1/V2/V3 笛卡尔积):

```
Phase 0 · 自用跑通 (当前)
  范围: 1 方法论 (harvard_plate) × 1 用户 × 2 zone
  目标: 链路跑通 + 自用一周 + 采纳率 ≥ 50%
  门槛: 我自己愿意每天用
        ↓ 验证: 自己用得住
Phase 1 · 同方法论同事推广
  范围: 1 方法论 × N 同事 × M zone
  目标: 公司内推广跑通, ≥ 3 人自发持续使用
  准入: 任意一套饮食原则 (不限定 harvard_plate, Codex Q4 修正), 进前先发 screener 探密度
  门槛: ≥ 3 同事自发持续用
        ↓ 验证: 别人也用得住
Phase 2 · 双向扩展 (顺序后议)
  方向 A: 更多方法论 (增肌 / 糖控 / 孕期 / 高血压)
  方向 B: 更多区域 / 开源
  真实需求拉动哪个就做哪个
```

依赖 / 影响:
- PRD §1 一句话定位重写 (从"控油+蔬菜+蛋白健康结构"改为"原则派的点餐执行外包")
- PRD §3.4 不服务的人加: 目标缺失型 ("什么都行又什么都不想吃")
- ROADMAP 顶部当前状态加 Phase 路线 + Step 1/2/3 节奏
- D-071 (砍 mood picker 落地 + want_soup 关键词识别) 是本决策的工程子项
- D-072 (methodology spec 抽象) 是本决策的 L0 工程化, 放 Phase 0 收尾 (Step 3)

讨论存档:
- 共两轮 Codex review, 第一轮 Codex 反对"砍 mood 全靠 refine" 提 post-rec chip, 第二轮经讨论达成一致: 关键词识别替代 chip, 见 D-071 决策过程
- N=1 定位风险: Codex 评 68/100 置信度, 最大风险 = Phase 1 时同事原则派密度未知 → 用 screener 缓解, 不阻塞 Phase 0

---

## D-071: 砍 mood picker + want_soup 关键词识别 (V1)

日期: 2026-05-15
状态: active · 工程决策 · 推翻 D-043 部分内容

背景: D-070 定位收敛后, 4 个 mood (随便/清淡/解馋/轻食) 中 3 个变成 baseline 冗余或低频 refine 场景, 但**砍掉后 want_soup 的 L2 确定性加分通道也丢了** — Codex Q2 指出: 在汤羹供给不足的 zone, 把"想喝汤"压给 L3 软偏置推不稳。

讨论过程:
- Codex 第一轮: 提"卡片下方加 post-rec chip"保留 L2 通道
- 我方反驳: post-rec chip 是 pre-rec picker 的位移版, 增加而非减少 cognitive load, 违反"30 秒搞定"纯粹性, 且 4 个 mood 中只有 want_soup 是真痛点
- Codex 第二轮: 接受关键词识别替代 chip, 补 P1 必做条件 (否定识别) + 实现位置修正 (refine.py 而非 web_api.py)

决定:

**A. 前端**
- 隐藏 `StatusBar` 里的 4 颗 mood chip (`apps/web/src/components/StatusBar.tsx:53-66`)
- 不删 `LABELS.mood` / `LABELS.moodList` / `Mood` 类型 (保留类型安全 + 调试台保留对比能力)
- `HomePage` 始终传 `mood='neutral'`, 不再让用户选

**B. 后端 - want_soup 关键词识别**

实现位置: `chisha/refine.py` 构建 context 前 (不是 `web_api.py`, 否则只有 web 路径生效, 调试台 / CLI / API 三路径漂移)

函数签名:
```python
def infer_refine_mood(user_input: str) -> str | None:
    """关键词扫描: 命中正向词 & 未被否定词拦截 → 返回 'want_soup', 否则 None.

    边界: 此函数只为 want_soup 服务, 不得扩展为通用 mood parser (见 D-071 边界警告).
    """
```

调用方式:
```python
effective_daily_mood = state.daily_mood or infer_refine_mood(user_input)
```

正向词典 (10):
- `想喝汤` / `喝汤` / `有汤` / `带汤` / `汤水` / `汤羹` / `羹` / `粥` / `砂锅粥` / `热汤`

否定词典 (6, 必须做):
- `不想喝汤` / `不要汤` / `别来汤` / `不喝汤` / `不想吃粥` / `不要粥`

否定优先: 命中否定词时直接返回 `None`, 不再检查正向词。

不收: 单字"喝"(会误召奶茶/饮料), 单字"汤"(模糊), "想暖暖肚子"等隐式表达(退 L3 OK)。

**C. 后端 - 清理 score.py**

删 `context_boost` 里的 3 条 mood 规则 (`chisha/score.py:438-445`):
- want_light → 删 (方法论 baseline, 不该 session 级)
- want_clean → 删 (同上)
- want_indulgent → 删 (低频, L3 + refine 文本 cover)

保留 `want_soup` 一条 (`score.py:436-437`): `+0.5 if has_wet` 通道不动。

删 `infer_default_mood` 整个函数 (`chisha/score.py:498-512`) 及其在 `context_boost` 里的调用 — D-043 季节兜底在 D-070 定位下不适用 (方法论用户 baseline 已固化, 不需季节猜测)。

**D. 埋点 5 字段** (必加, 一周后回看效果)

每次 refine 调用记录:
| 字段 | 含义 |
|------|------|
| `refine_text` | 用户原文 |
| `matched_keyword` | 命中的正向词 (None 表示未命中) |
| `negated` | 是否被否定词拦掉 (bool) |
| `injected_daily_mood` | 实际注入的 daily_mood 值 |
| `before_daily_mood` | 注入前 state 里的原值 |

落点: session trace 现有结构里加段 (与 D-048 trace 字段同级)

**E. 边界警告 (强制)** ⚠️

`infer_refine_mood` 只服务 want_soup / wetness 偏好。**不得**:
- 加 want_clean / want_light / want_indulgent 等其他 mood 关键词
- 加任意非 wetness 维度的关键词识别
- 扩展为通用 mood parser

理由: D-070 把通用 mood 信号归到 L3 + refine 文本, 这套关键词扫描是单点补救 (L2 确定性 + 汤羹供给不足下 L3 推不稳), 不是通用机制。扩展会让 mood picker 以更隐蔽形式复活。

新增 mood 需求若出现, 走 L3 prompt 调整, 不走关键词。

理由汇总:
- 砍 picker 符合 D-070 定位 (零 upfront ask)
- 保留 want_soup 因汤羹偏好有 wetness 结构化字段 + 供给不足 zone 下 L3 推不稳 (Codex Q2.1 论据)
- 关键词识别比 post-rec chip 零新增 UI, 用户用一致的 refine 文本框, 系统自动接住
- 实现在 `refine.py` 而非 `web_api.py` 保证三路径 (调试 / API / CLI) 信号一致

依赖 / 影响:
- 前端: `apps/web/src/components/StatusBar.tsx` / `apps/web/src/pages/HomePage.tsx`
- 后端: `chisha/refine.py` (新增函数) / `chisha/score.py` (删 3 条规则 + infer_default_mood)
- 不动: `chisha/web_api.py` mood 入参 (后端 backward compat, neutral 行为不变)
- 不动: `chisha/rerank.py` build_context_block (daily_mood 仍传 L3 作为 [CONTEXT] 一行)
- 测试: 新增 `infer_refine_mood` 单测 (正向命中 / 否定拦截 / 边界 case 至少 8 个)
- 推翻: D-043 的 `infer_default_mood` 季节兜底 (本决策删)
- 推翻: D-043 `context_boost` 中 want_clean / want_light / want_indulgent 三条规则 (本决策删, want_soup 保留)

Step 1 执行清单 (供另一台机器 session 落地):

| # | 任务 | 文件 | 预估 |
|---|------|------|------|
| 1 | 隐藏 StatusBar mood chip 区块 | `apps/web/src/components/StatusBar.tsx:53-66` | 10 min |
| 2 | HomePage 始终传 `mood='neutral'` | `apps/web/src/pages/HomePage.tsx` | 5 min |
| 3 | `infer_refine_mood` 实现 + 否定优先 | `chisha/refine.py` 新增 | 20 min |
| 4 | 在 refine 主入口注入 effective_daily_mood | `chisha/refine.py:refine()` | 5 min |
| 5 | 埋点 5 字段进 trace | `chisha/refine.py` + 现有 trace 结构 | 10 min |
| 6 | 删 want_clean / want_light / want_indulgent 3 条 | `chisha/score.py:438-445` | 5 min |
| 7 | 删 `infer_default_mood` 函数 + 调用点 | `chisha/score.py:498-512` + 调用方 | 5 min |
| 8 | 单测 `test_refine_mood_inference.py` 8+ case | `tests/` | 15 min |
| 9 | 跑全量 pytest 确保不回归 | `uv run pytest tests/ -q` | 5 min |
| 10 | IMPLEMENTATION_LOG.md 加执行记录 | `docs/IMPLEMENTATION_LOG.md` | 10 min |

合计 ~90 分钟。完成验收:
- 前端 11:30 打开 / 不再看到 mood chip
- refine 输入"今天想喝汤" → trace `matched_keyword='想喝汤'` + `injected_daily_mood='want_soup'`, 推荐结果 wetness 分布上移
- refine 输入"不想喝汤" → trace `negated=true` + `injected_daily_mood=None`
- 全量单测过

---

## D-072: methodology spec 抽象 (放 Phase 0 收尾, V1)

日期: 2026-05-15
状态: planned · 待 Step 2 数据回归后启动 · D-070 的 L0 工程化

背景: D-070 三层信号模型把方法论归到 L0 (profile-level). 当前 `chisha/score.py` 把哈佛餐盘方法论 (控油 -0.4 / 加工肉 penalty / 蔬菜 floor / 蛋白 floor / 4 层 cap 阈值...) 硬编码在 Python 里, Phase 1 接同事时若需要第二份方法论 (减脂 / 增肌 / 糖控) 会被迫重写 score.py。

讨论 (Codex Q3):
- 我方原议: "现在抽 spec 接口, 早抽不会回头重写"
- Codex 修正: 同意抽, 但**真正理由不是为 Phase 1, 是降低当前 score.py 耦合度** — 把权重 / 阈值从代码提到 yaml, score.py 变纯逻辑层, 参数调优不再需要改 Python (自用采数据阶段直接受益)
- Codex 补 schema 设计要点: 加 `extra_rules: []` 逃逸口 (防 Phase 1 第二个方法论 schema 不兼容) + 每条规则配 `rationale` 字段 (人类可读, 防权重映射 gap)

决定: 抽 spec 接口, 但**延后到 Step 3 (Phase 0 收尾, 采完一周数据后)** — Codex Q5 论据: 重构带 bug 风险, 不应在采数据窗口期做; Step 2 数据可作 Step 3 重构的回归基线。

设计要点 (落地时再细化):

1. **位置**:
   - `profiles/methodologies/harvard_plate.yaml` — 第一份 spec, 装下当前所有规则
   - `chisha/methodology.py` — 加载 spec → 注入 score.py 的薄接口层

2. **spec 字段** (含 Codex 补的逃逸口):
```yaml
name: harvard_plate
display_name: 哈佛餐盘 (控油 + 有蔬菜 + 有蛋白)
rationale: |
  人类可读的方法论摘要 — 给 L3 LLM 当 system 段, 也给用户 onboarding 看
hard_filters: ...  # 召回硬过滤 (D-041 双层架构)
score_weights: ... # L2 12 维权重
cap_rules: ...     # 4 层 cap 阈值 (D-042)
soft_rules:
  - id: want_soup_wetness
    trigger: daily_mood == want_soup
    apply: +0.5 if has_wet
    rationale: 用户当下想喝汤, 汤水类菜直接加分
extra_rules: []    # 逃逸口: Phase 1 第二个方法论 schema 不兼容时, 临时塞自定义规则
```

3. **profile.yaml** 改成:
```yaml
methodology: harvard_plate   # 引用 spec
# ...其他个人字段 (zones / price / taste_description) 不变
```

4. **score.py 重构**: 删所有硬编码权重 / 规则 / cap 阈值, 改成从 spec 读

Step 3 执行触发条件 (Phase 0 验收门):
- Step 1 (D-071) 已落地
- Step 2 (自用一周) 采纳率 ≥ 50%, 累计 ≥ 30 次推荐 + 反馈样本
- 数据回归: 重构前后跑相同 session 看 top5 是否一致 (允许 ≤ 1 个差异)

风险:
- spec schema 第一版若设计不周, Phase 1 时仍需改 schema (不是改 score.py, 但是改 yaml + 加载逻辑) — `extra_rules: []` 是缓冲, 但不是万能
- 权重映射 gap: 把"蔬菜 50%"翻译成 `veg_tag weight +0.3` 时语义不直观 — `rationale` 字段缓解

依赖 / 影响:
- 不在 Step 1 范围 (推后, 防采数据窗口被 bug 污染)
- 触发条件: 自用一周采纳率 ≥ 50% + Step 1 稳定 + Codex review 通过 spec schema
- 推翻: D-043 部分内容 (打分逻辑硬编码 → spec 化), score.py 重构后视为 D-072 的实现
- 关联: D-070 三层信号模型 L0 的工程化

---

### 最终 schema 字段表 (Codex Round 2 M-3 要求冻结, 2026-05-15 落地版)

用户决策: Phase B 不等 Step 2 自用数据, 用 `tmp/baseline_traces/` L2 capped top60 + score breakdown 做严格回归基线 (允许 < 1e-6 浮点差), 重构前后 0 diff 即通过. 详见 D-072.1.

**顶层必备字段** (共 7, 缺失 → MethodologyValidationError hard fail):
- `name` (str, 与文件名一致)
- `display_name` (str, UI 用)
- `version` (int, 1 起)
- `rationale` (str, L3 system 段用)
- `plate_rule` (dict, 召回硬约束默认)
- `score_weights` (dict, L2 16 维权重默认)
- `cap_rules` (dict, 4 层 cap 默认)

**顶层可选字段**:
- `unforgivable_discount` (float, 缺失走 score.py 硬 fallback 0.5)
- `soft_rules` (list[dict], V1 declarative 占位不执行; 非空时 logger.warning 提醒)
- `extra_rules` (list, Phase 1 逃逸口, V1 不解释; 非空时 warn)

**`plate_rule` 内部 key** (严格 keyset 校验, Codex B-1):
- `must_have_vegetable` (bool)
- `min_vegetable_dishes` (int)
- `min_protein_g` (int)
- `prefer_oil_level_at_most` (int)
- `hard_max_oil_level` (int)

**`score_weights` 内部 key** (严格 keyset 与 V2_DEFAULT_WEIGHTS 一致):
`vegetable_floor_pass / protein_floor_pass / distance / low_oil / popularity / cuisine_preference / variety_bonus / carb_quality / processed_meat / sweet_sauce / wetness / dish_role_match / eta / price / taste_match / context_boost` (共 16 维)

**`cap_rules` 内部 key** (严格 keyset):
- `per_restaurant_top_k` (int)
- `per_brand_top_k` (int)
- `per_cuisine_top_k` (int)
- `per_food_form_top_k` (int)

**merge 行为** (`chisha.methodology.merge_into_profile`):
- `profile.plate_rule = {**spec.plate_rule, **profile.plate_rule}` (profile 显式 override)
- `profile.scoring_weights = {**spec.score_weights, **profile.scoring_weights}` (注意 spec 字段 key 名 `score_weights`, profile 用 `scoring_weights` — 命名漂移记账, V1 不改)
- `profile.recall = {**spec.cap_rules, **profile.recall}` (per_*_top_k cap key 同名)
- `profile.scoring.unforgivable_discount = profile.scoring.unforgivable_discount or spec.unforgivable_discount` (Codex B-2: 字段路径必须 profile.scoring.* 不是 profile.* 顶层)
- 其他字段 (zones / price_range / taste_description / preferences / delivery_constraints / diversity / meal_trigger_time) 一律不动

**profile.methodology 字段语义**:
- 缺失 → fallback `harvard_plate` + `logger.info` 显式打 "methodology field missing, using default" (M-1: 非 silent fallback, 留可观测痕迹)
- 显式设值 → load_methodology 加载该 spec, 不存在 raise FileNotFoundError

---

## D-072.1: Phase B 不等 Step 2 自用数据 (用 L2 trace baseline 替代)

日期: 2026-05-15
状态: active · D-072 触发条件修订

背景: D-072 原约定 "Step 2 自用一周采纳率 ≥ 50% + 累计 ≥ 30 反馈样本" 才启动重构. 但实操中 Step 2 走 OpenClaw 闭环, 用户行为不在 Claude Code 工作范围内. 等数据会无限期延后 Phase 0 收尾.

决定: Phase B 启动条件改为 **L2 trace baseline 严格回归通过**.

具体回归协议:
1. 重构前跑 `scripts/baseline_l2_snapshot.py` 生成 4 个 snapshot (lunch/dinner × neutral/want_soup), 每个含 L3_INPUT_TOP_K=60 个 combo 的 score + 16 维 breakdown + 餐厅/菜品签名
2. 重构后跑同样脚本 → `tmp/baseline_traces_after/`, 跑 `scripts/compare_traces.py` 严格断言:
   - top60 combo 顺序完全一致 (按 score 排序后餐厅+dish_ids 签名 100% 一致)
   - 每个 combo 的 16 维 breakdown 每个值 |delta| < 1e-6
   - 总 score |delta| < 1e-6
3. 任何 diff → 重构有 bug, 必须找到漏的规则补 spec; 不允许 commit
4. L3 LLM rerank 输出 stochastic, 不在严格回归内 (Codex M-2 要求另存 with_methodology_line A/B trace 留作未来 sanity check, 不阻断 commit)

理由:
- Step 2 是用户行为闭环, 不应卡 Phase 0 工程收尾
- L2 是 deterministic, 用 trace 严格对比比"采纳率 ≥ 50%" 更直接也更可验证
- score breakdown 16 维对比能精确指认 spec 化漏了哪条规则 (比黑盒 top5 对比强)

风险:
- L2 一致不代表 L3 一致 — L3 改 rationale prompt 后输出会变. 但用户已认可这是 enhancement 而非回归 (D-072 明确要求 prompt 摘要从 spec 取)
- 自用数据缺失 ≠ Spec 设计无误 — Phase 1 时若发现 spec 不适用第二个 methodology, 走 extra_rules 逃逸口 + D-072.2 修订条目

依赖 / 影响:
- 推翻: D-072 Step 3 触发条件 "采纳率 ≥ 50% + 30 样本"
- 关联: `scripts/baseline_l2_snapshot.py` / `scripts/compare_traces.py` 为本决策落地工具

---

## D-073: refine 走结构化意图 (RefineIntent) + 重召回, 让"用户主动表达诉求"真正生效

日期: 2026-05-16
状态: active · 推翻 D-071 全量 + D-035/D-043 P3 在 refine 端的应用

### 触发事件

用户实测 `"想吃点湖南菜，然后肉多一点。"` (V1 refine 链路):

- `parse_feedback` 走 LLM, 因 CHIP_VOCAB 封闭 (22 个 chip), 只抽到 `chips=["想吃肉"]`, "湖南菜"丢失
- `chips_to_taste_hints(["想吃肉"])` = `{boost:[], penalty:[]}` (D-035 的 `_CHIP_TO_HINT` 已正式移除"想吃肉"映射, 见 refine.py:174 注释)
- `infer_refine_mood` 关键词只识 want_soup, "湖南"完全无关
- → **L2 排序与首轮完全相同**, top-60 候选池不变
- → 仅 L3 LLM 看到 `refine_input` 原文, 在 top-60 内重排
- 实测 L3 救场出 3 条湘菜命中, 但属于"撞大运" (top-60 池子刚好有湘菜)

用户结论: **"用户主动表达诉求时, 系统应该尽量满足, 而不是这么多约束。"**

### 决定

走"方案 D" (Opus 设计 + Codex review 落实 5 个修订点后通过): **拆 parser + 开放 schema + 重做 recall + L2 加权 + 砍 D-071**.

#### 拆 parser

| 函数 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `parse_feedback` (保留) | 餐后反馈文本 | `FeedbackParsed` (chips/rating/want_again) | /api/feedback, 长期偏好沉淀 |
| `parse_refine_intent` (新建) | 餐中 refine 文本 | `RefineIntent` (开放结构) | /api/refine, 当下推荐意图 |

理由: 餐后反馈要 chip 词表稳定 (做长期偏好统计), 餐中 refine 要开放 (听懂用户当下话). 挤一起是当前所有问题的根源.

#### RefineIntent schema (开放 + 部分归一)

```python
@dataclass
class RefineIntent:
    cuisine_want: list[str]          # 自由字符串 ["湖南菜", "川菜"]
    cuisine_avoid: list[str]
    ingredient_want: list[str]       # ["肉", "牛肉"]
    ingredient_avoid: list[str]
    cooking_method: list[str]
    flavor_tags: list[str]           # 归一枚举 ∈ {spicy, mild, sour, sweet, soup, dry, light, heavy}
    raw_flavor: list[str]            # 原文供 L3
    portion: list[str]               # ∈ {more_meat, less_carb, more_veg, not_too_full}
    staple_preference: str | None    # ∈ {avoid_staple, want_rice, want_noodle}
    price_band: str | None           # ∈ {cheap, normal, premium}
    freeform_note: str               # 原文兜底
```

LLM prompt 规则: 抽取意图, 未表达留空, **不要主观联想**, cuisine/ingredient 不限词表.

#### 推荐链路接入

1. **recall 重做** (Codex review §2 关键修订):
   - intent 进 `build_combos_for_restaurant` 之前的 dish 池排序 (intent_score 加进 sort key, 防被 `per_rest_max` 截断)
   - 召回后做三桶拼合: exact cuisine / soft cuisine 或 ingredient / 全集兜底
   - cuisine_avoid + ingredient_avoid 硬过滤
   - Q1 决策: exact 桶 < 阈值 max(n×2, L3_INPUT_TOP_K×0.15) 时回落全集

2. **L2 加 `intent_match_bonus`** (Codex §3 拆三档):
   - `intent_cuisine` 0.50: cuisine 命中 (exact 1.0 / soft 0.6)
   - `intent_ingredient` 0.20: ingredient + portion + staple 命中
   - `intent_flavor` 0.10: flavor_tags 命中
   - 2026-05-16 实测校准: 初版 0.20/0.10/0.10 被 popularity 单维压过, 用户意图 < 长期偏好, 调高让 intent 真正 dominant

3. **健康 guardrail** (Codex §3): 触发 oil_avg > prefer+1 或 unforgivable 条件 → intent 三档加分 × 0.4

4. **辣度尊重 spicy_tolerance** (Codex §5): target = min(spicy_tolerance, 2); spicy_level > tolerance 仍由 L1 硬过滤拦截, intent **不能覆盖 profile**

5. **L3 prompt 双轨**: ContextSnapshot 加 `refine_intent` 字段; rerank_system.md §1-7 优先级表: **硬约束 > refine_intent > refine_input > daily_mood > taste_description > 健康结构 > 多样性**

#### 砍 D-071 (Q3 用户决策: 彻底删)

- `infer_refine_mood` / `_match_*_keyword` / `_build_mood_trace` / `_append_mood_trace` 全删
- `tests/test_refine_mood_inference.py` 整文件删
- `logs/refine_mood_trace.jsonl` 归档为 `.legacy.jsonl` (历史保留)
- 由 `RefineIntent.flavor_tags=["soup"]` 取代 (LLM 抽取比关键词稳)

#### 断 D-043 P3 在 refine 端的 append_feedback (Codex §7)

- refine 不再调 `append_feedback`, 不把 intent 沉淀进 `long_term_prefs`
- 理由: "今天想吃湖南菜" 是当下意图不是长期偏好, 写入会污染 D-043 chip 历史
- 长期偏好沉淀只走餐后反馈; refine 只写 `logs/refine_intent_trace.jsonl` 观测

### 实测验证 (2026-05-16)

输入: `"想吃点湖南菜，然后肉多一点。"`

| 链路点 | 实测结果 | 评价 |
|---|---|---|
| parse_refine_intent | `cuisine_want=[湖南菜], ingredient_want=[肉], portion=[more_meat]` | ✅ 完美 |
| L2 capped top-5 (校准后) | 全是湘菜店 | ✅ |
| 湖南老灶台位置 | 从 #129 (初始权重) 升到 #50 (top60 内) | ✅ |
| L3 实际输出 5 条 | 3 条强湘菜 + 1 江浙菜含湘味菜 + 1 大米先生 | ⚠️ 60% 强命中, 比 v1 撞大运稳定 |

### 推翻的旧决策

| 旧 D | 状态 |
|---|---|
| D-035 (chip 反馈解析员) | 部分推翻 (仅服务餐后反馈; 不再服务餐中 refine) |
| D-043 P3 (refine 写 long_term_prefs) | 推翻 (refine 端断, 餐后反馈保留) |
| D-071 (want_soup 关键词识别) | **完全 superseded** |

### 已知不确定 / 后续

1. L3 命中率非 100% (60% 强命中). 是否要让 L3 prompt 更强制, 自用一周观察后决定
2. L2 权重 0.50/0.20/0.10 是首次拍板, 自用一周看 top60 std 再二审
3. `flavor_tags.{sour/sweet/heavy}` 用关键词命中 dish name 不够稳, 未来按需打 sour_level/sweet_level 字段
4. portion/staple/price 都进 ingredient 通道, 后续若 std 不足可单独拆维度

### 来源

- Opus 设计 v1 → Codex review (`codex-rescue`, ~270s) 拍砖 5 个修订点 → Opus 合并 v2
- 用户决策: Q1 回落全集 / Q2 spicy_tolerance-aware / Q3 彻底砍 D-071
- 工程节奏: 3 天 (schema/parser → recall/score → 主流程 + 砍 D-071 + 文档)

---

## D-073.1: refine 显式 cuisine_want 时, 目标菜系免 cuisine/brand/food_form cap

日期: 2026-05-16
状态: active · D-073 followup, 修「换日料」bug

### 触发事件

用户在 web 实测点 chip「换日料」无效——refine 返回的 5 张里只有 rank 1-2 是日料 (鸟鹏烧鸟、鸟剑居酒屋), rank 3-5 让位给粥店/烤鸡/湘楼.

诊断链路 (从前端逐层追):

- 前端 ✓: chip click → `submit(chip)` 直接传 chip 文本到 `onSubmit`, 与手敲完全同一条 `api.refine` 路径 (apps/web/src/components/RefineInput.tsx)
- `parse_refine_intent` ✓: `cuisine_want=["日料"]`, `normalize_cuisine` → `"日式"` 对齐数据 cuisine 字段值
- `recall` ✓: 2449 combos, 其中 `cuisine_exact_match` 命中 86 个 (84 个 `dishes[0].cuisine == "日式"`)
- L2 `rank_combos` ✓: `intent_match_bonus.cuisine = 1.0 × weight 0.50 = +0.5` 正确加上
- **`apply_caps` ✗**: 多样性 cap 把日式 84 → 6 个进 top60
  - `cuisine cap=6` 一刀切
  - `brand cap=2` × 日式仅 5 个品牌 = 上限 10 个 combos
  - `food_form cap=8` 在小菜系上偶发收紧

→ L3 prompt 拿到 top60 里日式仅 6/60, 即使 prefer 日料也只能挑 2 张挂出来.

### 决定

`apply_caps(ranked, profile, intent=None)` 接 intent 参数. `intent.cuisine_want` 命中的菜系 (经 `normalize_cuisine` 归一) 进入 `exempt_cuisines` 集合, 免 **cuisine / brand / food_form** 三层 cap.

`restaurant cap = per_restaurant_top_k = 3` 保留——这是"目标菜系小+餐厅集中"场景下防同一家店连刷一页的最后一道屏障.

`intent=None` 时行为完全不变, 首轮 recommend / 空 refine 不受影响. `baseline_l2_snapshot` 0 diff 通过.

### 不做的事

- 不放宽 `restaurant cap`: 单店 3 个 combo 已足够给用户挑, 再放就是同店刷屏
- 不动 `intent_match_bonus` 权重 (cuisine 0.50): L2 加分本来够, 问题是 cap 干掉了候选, 不是排序不够强
- 不区分"软 want vs 硬 want": D-073 schema 没这层, 现阶段一律按硬意图处理. Phase 1 用户面广了再考虑
- 不修 `apply_caps` 内 `cui = dishes[0].cuisine` 取值口径与 `cuisine_exact_match` 的 any-dish 口径不一致问题: 这是另一个 bug 范畴, 当前 fix 不要扩散

### 实测结果

| 输入 | 改前 L3 输出 5 张命中目标菜系 | 改后 |
|---|---|---|
| 换日料 | 2 | 3 (rank 1-3 全日料) |
| 换粤菜 | (未基线测) | 4 (rank 1-4 全粤菜) |

L2 端 `apply_caps` 后 top60 日式 combo: **6 → 16** (`换日料`场景).

### 风险

- 目标菜系小、餐厅集中时, 推荐里同 brand 可能并列出现 (例: 鸟鹏 + 鸟剑 + 一田屋同时上). 这是"用户明确要这个菜系"语义下可接受的代价, 不是 bug.
- `cuisine_want` 与 `cuisine_avoid` 同时存在时: avoid 优先 (recall 层 `_apply_intent_buckets` 已硬过滤掉 avoid 命中的 combo, 不会进 `apply_caps`)
- intent 解析错误把目标菜系认错时, 错的菜系会同时免 3 层 cap, 偏差被放大. 风险点在 `parse_refine_intent` 的 LLM 解析准确度, 不是 cap 改动本身.

### 来源

- 用户在 web 实测发现 chip 不生效, 直接报 bug
- Opus (Claude Code) 诊断: 前端 → recall → L2 cap 逐层追, 最终定位在 `apply_caps` cuisine cap
- 改动确认: 用户拍板方案 A (目标菜系免 cap), 验证发现 cuisine cap 免后仍受 brand cap 压制, 扩展到 brand + food_form 三层

### 关联

- 实施:
  - `chisha/score.py:1029 apply_caps` 加 `intent` 参数 + `exempt_cuisines` 逻辑 (cuisine/brand/food_form 三层 cap 增加 `is_exempt` 短路)
  - `chisha/refine.py:111` `apply_caps(ranked, profile, intent=...)` 透传
- 回归:
  - `baseline_l2_snapshot` + `compare_traces` 0 diff 通过 (首轮场景 intent=None 行为不变, 满足 D-072.1 红线)
  - pytest 471 passed (`test_session::test_cleanup_expired` 因硬编码 2026-05-13 与当前日期相对漂移, 与本改动无关)
- 推翻: 无 (D-073 设计语义保持, 仅修一个 cap 边界缺陷)

## D-076: L1 长期反馈层重构 — 砍伪 L1 + LLM 抽取 (V1.x)

日期: 2026-05-16
状态: active · 落地: 2026-05-16 PR-0/0.5/0.6/0.7/0.9 (5 个 commit)

背景:
2026-05-16 志丹挑战 D-070 三层信号模型在代码层的落地, 揭出代码与文档脱节:
- D-070 文档说 "L1 长期反馈层 V1.1 已建", 实际代码层并不存在.
- `chisha/long_term_prefs.py` 是**伪 L1** — 把 `refine.py:244` 写入的
  refine chip (D-070 L2 当下 session 信号) 当跨 session 信号做频次
  统计 + 半衰期 + 拉普拉斯 ≥2 平滑, 概念错位.
- V1.1 反馈 schema (D-063~D-065 `rating + 4 维 calibration + note`)
  落 `feedback_store.json` 只为反馈页回放, 没有任何机制汇成长期偏好.
  ← 真正的 L1 输入源在躺尸.

Codex S2 dual-model audit (D-036) 揭出更深一层: `claude_code_cli`
provider 不支持 tool_use forced schema, 走 text + JSON parse/validate/
retry 才能用 Max 订阅免费.

决策 (志丹拍板, 拍板 1A + 拍板 2 "一波到位 + bootstrap_from_legacy"):
1. **砍 refine 写 feedback_history.jsonl 错位路径**.
   refine chip 是 L2 单次 session 信号, 不允许跨 session 累加.
2. **新增最小 L1 LLM 抽取层** (`chisha/l1_extractor.py` +
   `chisha/l1_prefs.py`):
   - 输入: V1.1 反馈 + accepted meal 上下文 + profile methodology
   - 预聚合 deterministic summary (Codex Q7): 4 维 calibration 直方图
     + ingredient_frequency + recent_complaints/positive 各最多 5 条,
     不喂 raw feedback_store
   - LLM 调用 (Codex Q6): claude_code_cli text mode + system prompt
     强制 JSON schema + 代码侧 parse_json (markdown / preamble 容忍)
     + validate_prefs (enum + 别名 canonicalize) + retry 1 次
   - 输出 schema: `data/long_term_prefs.json`
3. **score.rank_combos 切到 l1_prefs.load_prefs** (PR-0.7):
   旧 `load_runtime_hints` 弃用 (deprecated stub 保留供 bootstrap),
   新 `to_runtime_hints(load_prefs())` 替代.
4. **bootstrap_from_legacy 兜底**: PR-0.6 一次性脚本读 D-043 旧 jsonl
   → 生成首版 prefs.json, 标 `bootstrap_from_legacy=true`. 解决
   Codex Q4 揭出的"切 score 瞬间丢旧信号"问题.
5. **localhost-only refresh 端点** (PR-0.9): POST
   `/api/long_term_prefs/refresh` 手动 trigger L1 抽取, 鉴权
   `_is_localhost(request)` + 可选 `CHISHA_ADMIN_TOKEN`.

LLM 词表锁定 (Phase 0 边界, Codex Q1):
- `score.taste_match_bonus` 现支持 6 维度 7 兼容 token:
  - boost: `low_oil`, `wetness` (`soup_or_broth` 别名)
  - penalty: `sweet_sauce`, `processed_meat`, `carb_heavy`, `spicy`
- 扩词表 = 改打分逻辑 = 违反 D-072 边界, Phase 1 独立决策.
- V1.1 4 维 calibration 中 `oil_calibration` 直接映射 `low_oil`;
  其余 3 维 (`reason_match` / `fullness` / `repurchase_intent`) 进
  `signals_not_scored` 仅展示, 不打分.

降级:
- prefs.json 不存在 / 损坏 → load_prefs None (LLM 失败 fallback)
- 损坏 → backup `.corrupt.{ts}.bak`, 不阻塞推荐
- LLM 全 retry 失败 → 不写盘, 保留上次 prefs

数据脱节兼容:
- `feedback_history.jsonl` 文件保留, 但 prod 不再写入 (refine 砍掉)
- bootstrap 脚本仍可读它, 用户切换前主动跑 `bootstrap_l1_from_legacy`
- 函数 `append_feedback / load_runtime_hints` 保留为 deprecated stub
- 单测 `tests/test_legacy_long_term_prefs.py` 保留, 标 legacy

守门 (D-072.1):
- baseline_l2_snapshot + compare_traces 4 snap, 关 sandbox 时 L2
  trace |delta| < 1e-6 严格通过.
- `tests/test_score_l1_switch.py` 三态守门: 无 prefs / 空 prefs /
  有 prefs 三种状态行为 + 损坏 prefs fall-open + rank_combos 端到端.
- 全测试 514 → 526 pass, 0 fail.

依赖 / 影响:
- 兑现 D-070 L1 文档承诺 (此前过度乐观)
- 推翻: D-043 "refine chip → load_runtime_hints" 闭环
- 关联: D-077 sandbox 模式提供真实场景验证 L1 抽取链路
- Phase 1 待办: token 词表扩展 / LLM 抽取调度 cron / 多 profile

讨论存档:
- D-036 dual-model audit 共两轮 Codex S2 review (tmp/sandbox_design.md
  v2 → v3 + 第二轮 review 输出 10 项修正)


## D-077: Sandbox Time-Travel 模式 (V1.x)

日期: 2026-05-16
状态: active · 落地: 2026-05-16 PR-1a/1b/1c/1d (4 个 commit)

背景:
推荐链路有多层"时间累积"行为 (D-043 旧伪 L1 半衰期 / cooldown 7d
不重店 / 3d 不重蛋白 / snooze 24h / session ttl 24h / D-076 新 L1
LLM 抽取). 自用验证这些行为需要等真实日历日推进, 至少一周才能跑通
一轮闭环, 这个节奏阻塞 Phase 0 收尾. 志丹要求**真实交互式 sandbox**
压缩到 user web 一次会话内完成.

决策 (志丹原则, 不可动摇):
1. **真实交互优先**: sandbox 是 user web 的一个 mode, 不是 CLI
   替代 / 离线 dry-run / fixture batch. Codex 反驳建议被拒.
2. **行为完全一致**: sandbox 走真实端点 / 真实 L3 LLM / 真实链路.
   禁止任何"沙盒专属阉割" (fake LLM / 跳过 cooldown 等).
3. **仅在两处隔离**: 数据落盘根 + 虚拟时钟. 其它完全同 prod.
4. **沉淀必须能被看到**: inspect 端点 + 前端 Drawer 展示 L1 prefs
   抽取产物 + 最近反馈, 让用户能验证 "我昨天投诉了今天它真生效了".
5. **一键回到干净状态**: reset 删 logs/sandbox/ 整目录, prod 零风险.

架构:
- **时钟层** (`chisha/clock.py` + `chisha/sandbox.py`): state.json
  落 logs/sandbox/, threading.Lock 防并发 advance/reset 互写. 11 处
  时间调用注入 (Codex Q1 grep 校对), 6 处明确排除 (time.time
  latency / corrupt backup 时间戳 / comment id 毫秒).
- **数据隔离层** (`chisha/data_root.py`): 7 个落盘点全部派生 —
  meal_log / sessions / feedback_store / recommend_log /
  feedback_history (deprecated) / long_term_prefs / profile (副本
  fallback 到 prod).
- **API 层** (`chisha/web_api.py:/api/sandbox/*`): 5 + 1 端点 (init/
  advance/reset/disable/state/inspect), advance 后异步 threading
  trigger L1 抽取 + record_l1_extraction 写状态. localhost only 鉴权.
- **前端层** (`apps/web/src/`): SandboxBar (banner + 操作) + Inspect
  Drawer (沉淀状态可视化) + ProfilePage 底部入口. sandbox 关闭时
  完全不渲染, 启用后顶栏接管. mock 模式不调.

advance 节奏:
- 异步 L1 抽取, 不阻塞 advance 返回. state.last_l1_extraction 字段
  记录 pending → ok | failed | skipped, 前端 badge 显示.
- L1 失败保留旧 prefs (extract_and_save 内部降级).
- 推荐链路读 prefs 时, 即使 L1 状态 pending 也用旧 prefs (Codex Q2
  stale 风险 — 暂以"badge 标明" 替代"同步等待", Phase 1 可加).

LLM 成本:
- claude_code_cli + Max 订阅 (拍板 1A), sandbox 一周 ~14 次推荐 +
  7 次 L1 抽取 = 21 次 LLM 调用, Max 配额充裕, 不烧 OpenRouter token.

failure modes:
- snooze 24h: sandbox advance 一天后立即解 snooze (虚拟时钟比较),
  行为正确, 文档明确.
- profile 切换: sandbox 启用时 PUT /api/profile 写副本, 不污染 prod.
- 多 tab 并发 advance/reset: state.json 文件锁防 race.
- LLM 失败: 保留上次 prefs, state 标 failed.

D-编号占用:
- D-077 此前 memory 占位 "AI-friendly 接入共识" (chisha_ai_friendly_
  consensus_d074.md). 该草稿未落 DECISIONS.md, 实际编号未发, 让位
  给 sandbox; AI-friendly 真正落条目时改用 D-078+.

依赖 / 影响:
- 配套 D-076 L1 LLM 抽取层 (sandbox 验证它的核心场景)
- 复用 chisha/data_root.py (PR-1b) 给 PR-1c API 端点 / PR-1d 前端
- 守门: baseline_l2_snapshot 4 snap, 全程 L2 trace 0 diff
- 单测: 18 sandbox/clock + 9 data_root 隔离 + 12 web_api 端点

不在 D-077 内:
- LLM fake / 阉割模式 (违反原则 #2)
- CLI 脚本 dry-run (违反原则 #1)
- meal_log.jsonl 写入端 (V1 现有 gap, accept 只写 feedback_store,
  diversity cooldown 实际不工作) — PR-2 备注, Phase 1 单独修

讨论存档:
- D-036 dual-model audit: Codex S2 第二轮 review 揭出 tool_use 矛盾
  + PR-0.7 等价性风险, 引出 bootstrap_from_legacy + 三态守门


## D-078: Sandbox 时钟漏注入修补 + accept→meal_log 闭环 cooldown (V1.x)

日期: 2026-05-16
状态: active · 落地: 2026-05-16 (1 commit, S2 Codex review 两轮)

背景:
D-077 sandbox 落地后用户视角 e2e 自验 (5 日推进真实 LLM 闭环) 抓到 3 个连带
bug, 全部因为「之前从没真正端到端走过」:

1. **L1 时钟漏注入 (P0)**: `l1_extractor.aggregate_inputs` 默认 today 用
   `dt.date.today()` 真实时钟; 但 feedback.submitted_at 由 `clock.now_utc()`
   产生虚拟时钟时间. 沙盒推进到 Day 5 时, real today ≈ 2026-05-16, 虚拟
   feedbacks 落在 2026-05-16..05-20; `ts > today` 全部判为「未来」过滤掉,
   based_on_meals 永远 = 1 < MIN=3 → 永远 skipped_extraction → L1 prefs 永远
   空. D-077 PR-1a 自称「11 处时间注入」, 漏了第 12 处.
2. **meal_log 写入端缺失 (P1)**: D-077 文档自认 V1 gap, 但 ROADMAP 又说
   「开 sandbox 推进 7 天看 cooldown 屏蔽行为」—— 矛盾. `/api/accept` 只写
   feedback_store, 不写 meal_log.jsonl, recall.diversity_filter 读空集 →
   沙盒推进时 cooldown 完全失效 (Day N+1 推 Day N accept 的店在 #1).
3. **llm_client.call 不存在 (P0 连带)**: D-047 改名 call → call_text, L1 没
   跟上. bug-1 把 based_on_meals 锁 1 → 永远不进 LLM 分支, 一直没暴露.

修复 (志丹原则 #2 「不阉割不绕开」):
- l1_extractor.aggregate_inputs 加 `root` 参数, 默认 today=`clock.today(root)`;
  extract_and_save 透传 root. 守门测试 test_aggregate_default_today_uses_chisha_clock.
- l1_extractor._default_llm_call 改用 `llm_client.call_text` (位置参数). 守门
  测试 test_default_llm_call_uses_existing_llm_client_symbol.
- chisha/recall.py 新增 `append_meal_log_entry(zone, accepted_rank, combo_index,
  candidate_id 可选审计字段)`, 时钟走 clock.now_utc(root). api_accept 在
  record_accept 后调用, hard-fail (与 record_accept 同等级别 — meal_log 是
  diversity cooldown 的 source-of-truth, accept_count > meal_log 暗洞会让
  一周内重餐厅).

Codex S2 review 二轮额外修补:
- **Q3-High** reset/disable 在 L1 worker 运行时执行 → save_prefs 走回 prod
  data/long_term_prefs.json 污染. 修法: reset/disable 抢 L1_EXTRACTION_LOCK,
  抢不到 timeout 30s 后 409. 守门 anchor 13.
- **Q2** advance 在 L1 pending 期间裸 POST 绕过 UI disable → trylock 跳过,
  新日期 L1 不重抽 stale prefs 生效. 修法: api_sandbox_advance 在 status=
  pending 时直接 409. 守门 anchor 14. SandboxBar 同时 disable 按钮兜底.
- **Q1** 半态 transaction (record_accept 成功 + meal_log 失败 = 500 但 banner
  已弹): 评估后保留 hard-fail, V1 自用单后端 + 磁盘故障是全局风险, 一致性
  比 UX 重要. 完整 2-write transaction 留待 V2 引入持久层时设计.

inspect drawer UX (P2):
- SandboxBar 三态显示: prefs=null → 「未抽取」; skipped_extraction → 「⏳ 样本
  不足 N/3」; 其它 → 正常 boost/penalty 渲染. meal_log_recent 从占位文案改
  成真实条目渲染.

D-编号占用:
- 检查 docs/DECISIONS.md 末尾确认 D-078 空缺 (memory 草稿 ai_friendly 没真正
  落 DECISIONS, 按"先到先得"占 D-078). AI-friendly 真正落条目改用 D-076+.

不在 D-078 内:
- diversity_filter 按 zone 过滤 (跨 zone 污染概率低, 留 D-076+ 决策)
- reset/disable 抢锁失败的完整 dirty-flag 补跑机制 (D-078.1 候补)
- meal_log 多 tab 并发 append 加文件锁 (与 recommend_log 同等约束, V1 单用户
  单后端不必)
- L1→L2 整轮重抽 (advance 在 pending 期间被 409, 用户必须等; 完整 dirty-flag
  重排队留 D-078.1)

验证:
- 542 pytest 全过 (+4 守门 anchor 11/12/13/14, +2 单测)
- baseline_l2_snapshot 4 snap md5 bit-identical (0 drift)
- 真实 LLM (Max 订阅 claude_code_cli) 5 日沙盒演练: based_on_meals 累积
  1→2→3→4, Day 4 触发 LLM 12s, 抽出 boost=["low_oil"] + evidence "4/4 oil
  calibration=too_high", Day 12 (7d 后) Day 1 店重回候选 (cooldown 解锁),
  taste_match_bonus(低油 hints={boost:[low_oil]})=0.5, 高油=0.0.

依赖 / 影响:
- 修补 D-076 (L1 LLM 抽取层) + D-077 (Sandbox Time-Travel) 落地后的连带空洞
- 不动 L2 trace (baseline 0 diff)
- 替 ROADMAP 兑现「开 sandbox 推进 7 天看 cooldown 屏蔽行为」承诺

讨论存档:
- Codex S1 (codex-rescue): 给出 P1×3 / P2×4 issue list, 含 zone 缺失
  / hard-fail vs soft-fail / advance race / wait_l1_settle 提 conftest /
  D-078 编号合法性 5 个角度
- Codex S2 (codex-rescue): 揭出 reset/disable 期间 L1 worker 写盘污染 prod
  路径 (High) + advance 期间 pending 绕过路径 (Medium) + 半态 transaction
  (Q1, 拍板保留 hard-fail)

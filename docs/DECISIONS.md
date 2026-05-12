# 今天吃点啥 · 决策日志

> 这份文档记录每一个关键的设计决策，**不只记录决定，还记录考虑过的替代方案和判断标准**。
> 目的是消灭"假上下文"——避免未来的我或 Claude Code 凭空脑补。
> 新决策追加在尾部，旧决策不删（即使被推翻，也保留并标注 superseded）。
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
状态: active（取代 D-018）

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
状态: active

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

执行进度:
- 2026-05-11 下午: shenzhen-bay 数据由 collector 重采（239 店 / 11,123 菜，覆盖之前漏抓 21 店），v2 prompt 全量重打完成 — 223 批 × 50/批，16 个 general-purpose subagent 并发 × 14 轮（约 85 分钟）。期间出现 2 类 schema 违规并即时修复：① 1 条 `cuisine="主食"`（米饭被 LLM 误归）；② 12 条 `cooking_method="爆炒"`（应映射到 `炒`）。后续 subagent prompt 加显式黑名单（"cuisine 不要写主食 / 爆炒→炒 / 油焖/红烧→炖 / 酥炸→油炸"）后未再复现。final: `data/shenzhen-bay/dishes_tagged.json` 11,123 条，全部 `metadata.tag_version=v2-promptfix`。
- 2026-05-11 晚: home v2 重打完成 — 43 批 × 50/批（最后批 17 条），16 并发 × 3 轮，0 failed（subagent prompt 自带枚举黑名单，无 merge 阻塞）。final: `data/home/dishes_tagged.json` 2,117 条，全部 `metadata.tag_version=v2-promptfix`。
- 2026-05-11 晚: 两个 zone 各 50 条 review 样本生成（seed=42，`data/<zone>/review_sample.xlsx`），等待人工 review 准确率 ≥ 80% 验证。
- 后续: 人工 review 通过即闭合本条，否则触发"重审条件 1"考虑 v3 prompt。

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

执行（全量重打）:
- **打标路径切换**: subagent spawn → API key (OpenRouter via OpenAI 兼容协议). 新脚本 `scripts/tag_via_api.py`, 旧 `tag_via_subagent.py` 保留作 spike fallback.
- 模型: 全量用 sonnet (anthropic/claude-sonnet-*), Opus 抽 50 条做 ground truth 对照
- 并发: 16 workers + batch 30, 13k 菜约 5-10 分钟跑完, backoff/retry 兜底
- 增量: 默认跳过同 tag_version 已有的; --force-version 全量重打
- 落盘: data/{zone}/dishes_tagged.json, metadata.tag_version=v3
- schema 升级（chisha/schemas.py）: NutritionProfile 加 5 字段 + dish_role/grain_type 枚举校验 + Field 范围

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

执行进度:
- 2026-05-11 19:00 prompts/tag_dishes.md 升级为 v3 (3 轮迭代定稿, 头部 changelog 完整)
- 2026-05-11 19:00 chisha/schemas.py 加 5 字段 + 枚举校验, NutritionProfile 仍 extra=forbid
- 2026-05-11 19:00 scripts/tag_via_api.py 新增, OpenRouter via OpenAI 协议; chisha/llm_client_openrouter.py 配套
- 2026-05-11 19:00 schemas + prompt + 脚本 commit + push（让 Session 2 能 pull 真实 schema）
- 2026-05-12 02:00 全量重打完成 (deepseek/deepseek-v4-flash via OpenRouter, .env 用 eval 子系统配置好的 OPENROUTER_API_KEY):
  - home: 2,117 条 (v3), 60 条因 2 个 batch JSON parse 失败漏打 → 用 max-attempts=5 backfill 补打成功
  - shenzhen-bay: 11,123 条 (v3), 0 batch failed
  - 总计 13,240 菜 100% 落地, 0 漏
  - 元数据: metadata.tag_version=v3 全量
  - 性能: home 30 workers ≈ 12 min; shenzhen-bay 60 workers ≈ 71 min (DeepSeek RPS 实测有限, 加并发收益减弱)
- 2026-05-12 02:00 scripts/normalize_v3_enums.py (新增) deterministic 修补 LLM 枚举漂移:
  - cooking_method: 卤/卤水/酱卤→炖, 熏/烟熏→烤, 炸→油炸, 爆炒→炒, 红烧/油焖/烧→炖, 酥炸/脆皮→油炸
  - main_ingredient_type: 饮品→其他, 禽类→白肉, 肉类→红肉
  - dish_role / grain_type 同步映射 (主厨推荐/甜品/凉菜; 燕麦/糙米/全麦 等)
  - home 修 9 处 (0.4%); shenzhen-bay 修 31 处 (0.28%); 校验后两 zone 全过
- 2026-05-12 02:00 prompt v3 黑名单补"卤/熏/炸"映射 + 饮品 main 兜底 (避免下次重打仍漂移)
- ✅ DONE: schema 升级 + v3 prompt + 全量重打 + normalize 兜底全部落地

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

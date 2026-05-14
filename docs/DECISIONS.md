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
状态: active (Phase 1 已实施, Phase 2 待 OpenClaw/Hermes 接入触发)

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

**2026-05-13**

### 背景
用户发现 L2 打分 top30 两个症状: (1) 潮汕粥/汤水扎堆; (2) 同一家餐厅多个 combo 排前面.

诊断: 潮汕粥类在 cuisine_preference(+0.5) / wetness(+0.5) / carb_quality(粥被列入 GRAIN_GOOD, +0.6) / low_oil(+0.8) 四个维度同时拿满 ~2.4 分纯加成; L2 不做商家去重, per_restaurant_max=20 让单店最多 20 个 combo 进 ranked, 分数相近一起占据 top30, 商家去重直到 L3 `_enforce_brand_unique` 才发生, 太晚.

### 决策
- `GRAIN_GOOD` 移除"粥" (粥本质精制白米, 汤水价值由 wetness 维度覆盖, 不重复加分)
- `V2_DEFAULT_WEIGHTS.cuisine_preference` 0.5 → 0.2 (软偏好不应和营养底线一个量级)
- 新增 `cap_per_restaurant(ranked, k)`: rank_combos 后立即调用, 每家餐厅 ranked 内最多保留 k=3 条, 其余下放 tail. 不丢任何 combo.
- 新增 `resolve_cap_k(profile)`: 统一三路径 (api/refine/debug) K 读取入口, 从 `profile.recall.per_restaurant_top_k` 读, 默认 3.
- profile.yaml `scoring_weights` 显式补齐 16 维 (此前只有 6 V1 维度, 其他靠 V2_DEFAULT_WEIGHTS 兜底).
- debug.html / logic.html 加 cap 前后对比统计展示 + 文档章节.

### 关键 fix (Codex review)
- **MAJOR**: refine.py 二轮路径漏 cap → 已补
- **MINOR**: 生产 k 硬编码 vs debug 读 profile 不一致 → 用 `resolve_cap_k` 统一
- **MINOR**: 匿名 combo (无 id 无 name) 错误聚合 → 改用 `id(c)` sentinel

### 工程产物
- `chisha/score.py`: `cap_per_restaurant` + `resolve_cap_k`, GRAIN_GOOD 改, cuisine_preference 默认 0.2
- `chisha/api.py` / `chisha/refine.py` / `chisha/debug_recommend.py`: 接入 cap
- `profile.yaml`: scoring_weights 补 10 个新 key + recall.per_restaurant_top_k
- `chisha/static/debug.html` / `chisha/static/logic.html`: UI + 文档
- `tests/test_score_v2.py`: 新增 11 个测试 (cap 行为 + 粥/cuisine_preference 调权 + resolve_cap_k 4 个场景)
- 245 测试全过

### 实测效果
- top30 涉及餐厅数 7 → 15 (lunch), 5 → 13 (dinner)
- 单店最多 combo 10 → 3

### 但事后发现 (引出 D-043)
- 单店霸榜解决了, 潮汕菜系扎堆并未解决 (仍 10/30)
- 用户问"为什么仅几个因素就让排序高度集中" → 数据分析揭示 8 个死分维度, top30 总分跨度仅 0.34

依赖: D-033 (V2 score), D-040, D-041


## D-043: L2 打分体系重设计 + 反馈闭环最小实现

**2026-05-13**

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


## D-046: L3 精排 prompt + payload 重构 (top60 + system/user 拆分 + 紧凑化)

**2026-05-13**

### 背景

L2 在 D-042/D-043/D-045 重设计 + 4 层 cap 后, top30 内的多样性骨架已经稳了 (品牌/餐厅/菜系/形态各层不再扎堆). 但 L3 LLM 精排自 D-035 上线后没动过, 用户问到三个具体问题:

1. 输入只给 top30 是否太少? 50/100 行不行?
2. 当前 prompt (prompts/rerank_topn.md) 是不是写得有问题? 该不该重新设计 system prompt?
3. 给 LLM 的 payload 用大量原始 JSON 字段, 是不是 token 浪费?

### 实测数据

build_payload 的旧 JSON 形态:
- profile + context shell (无候选): ~1.3k chars
- 每 candidate ≈ 1.47k chars (3 道菜的完整 JSON, 11 个键名重复)
- top30 = 48k chars ≈ 22k input tokens (实际计费)
- top50 = 77k chars ≈ 35k tokens
- top100 = 159k chars ≈ 70k tokens

3 个问题各自验证:
- **top N**: position bias 在 sonnet-4.6 上, 当 list rerank 输入 >50 条时中段 attention 显著衰减 (lost-in-the-middle). L2 4 层 cap 已经把 top30 的多样性骨架定死, top31-40 仍有少量结构增量 (高分但被 cap 挤出 head 的 tail), top41+ 高度同质, 给 LLM 反而是噪声.
- **prompt 结构**: 当前 prompt 把"角色定义+任务+payload+输出 schema+边界"全塞 user message 一坨, 每次调用前缀都不一样, **Anthropic prompt cache 命中率 = 0%**. 另外没有 few-shot reason 示范, 实测 LLM 经常输出"营养均衡搭配合理"这种空泛 reason.
- **payload 形态**: 每个 candidate 的 JSON 里, `main_ingredient_type`, `processed_meat_flag`, `sweet_sauce_level`, `cooking_method`, `oil_level`, `spicy_level`, `dish_role`, `wetness`, `grain_type` 9 个键名在每道菜重复, 30 个 candidate × 3 道菜 = 90 次重复键名占大量 token. 但完全删字段也不行 (LLM 拿到只剩菜名会瞎猜 processed_meat/油辣等核心约束).

### 决策

#### A. top N: 30 → 60 (二审修订, 一审主张 40)

**一审主张 40, 二审实测后修订到 60.**

一审依据:
- L2 4 层 cap 把多样性骨架定死, top41+ 应该高度同质
- Liu et al. 2023 lost-in-the-middle: 长输入下 LLM 中段 attention 衰减
- 给 LLM 100 个会触发 position bias

**用户质疑暴露的问题** (志丹原话: "看起来 input token 已经少了很多, 为什么还是只给 40, 不多给一些? 基于大模型的技术原理讨论"):

- 一审论证基于 2023 年研究, 但 Claude Sonnet 4.6 是 2025-2026 模型, NIAH / mid-context recall 显著提升 (Anthropic Claude 4 model card: 200k context NIAH > 99%, mid-context recall 比 3.5 提升 2x)
- "top41+ 同质化"是直觉判断, 没有实测验证
- 现代 long-context LLM 在 ~8k input 的 listwise rerank 上 (RankZephyr/FIRST/RankGPT 后续工作), N=20→N=100 NDCG@10 仍单调上升 +1.5~2.5pp

**二审实测两 zone 的 score+多样性分布**:

shenzhen-bay (餐厅密集, 2467 combos):
- top1-30: span 0.868, 19 brand / 19 餐厅 / 8 cuisine
- top31-40: span 0.171, 7 brand / 7 餐厅 / 5 cuisine
- **top41-60: span 1.997 (打分不连续!), 10 brand / 12 个新餐厅 / 5 cuisine** ← 关键反证
- top61-80: span 0.131, 急剧坍缩到 4 brand / 5 餐厅 / 3 cuisine (粥店/点都德灌榜)
- top81-100: 3 cuisine / 4 餐厅, 完全同质

home (餐厅稀疏, 431 combos):
- top1-30: span 1.471, 17 brand / 9 cuisine
- top31-40: span 1.262, 5 brand / 3 cuisine (在衰减)
- top41-60: span 0.117 (平台区), 8 brand / 5 cuisine
- top61-100: 几乎全部平台区, 无新增

**关键发现**: top41-60 在大 zone 上有 1.997 的 score 跨度 + 10 个新 brand + 12 个新餐厅 — 这是被 4 层 cap 挤出 head 的真高分 tail, 不是低分尾巴. 一审"top41+ 同质"在小 zone 对, 大 zone 错. **N=40 在 shenzhen-bay 上等于把 L3 该看到的多样性增量砍掉了**.

**最终选 N=60**:
- 大 zone 拿到 top41-60 的真实结构增量 (12 个新餐厅 / 10 brand)
- 小 zone 无害 (top41-60 是平台区, 无新增, LLM 选不到也没事)
- top61+ 进入同分平台 + 连锁灌榜, N=80/100 引入噪声 + LLM 输出漏号风险 (RankGPT 报告 N>50 漏号率 +0.5→3pp)
- 在新紧凑 payload 下 user message ~6.2k tokens, 仍比旧 top30 (22k tokens) 轻 72%

**观测埋点**: `rerank()` 主入口每次打印 LLM 选中的 5 个 combo_index, 一周后看 P(idx >= 40). 如果 > 5% 说明 N=60 真在救场; 如果 < 1% 退回 40. 这是**唯一能反驳直觉的实证**.

**工程产物**: `chisha.rerank.L3_INPUT_TOP_K = 60` 单一常量, api.py / refine.py / debug_recommend.py 全部引用. 调 N 只改一处.

不做的事: N=80/100 — 没有实测证据支持收益, top61+ 同质 tail 给 LLM 是噪声; 等 N=60 跑一周拿到 selected_indices 分布数据再考虑.

#### B. prompt 拆 system / user

`prompts/rerank_topn.md` (一坨 user) → 拆成:
- `prompts/rerank_system.md`: 角色 + 任务原则 + 硬约束 + 输出 schema + reason few-shot (好 / 坏对照). ~2.8k chars ≈ 1.7k tokens. 走 Anthropic prompt cache (`cache_control: ephemeral`), 100% 命中.
- `prompts/rerank_user.md`: 模板 (供人对照), 实际 user message 由 `chisha.rerank.build_user_message()` 拼.

价值 (按重要性排):
1. **few-shot reason 进 system**: 好 reason ("潮汕粥汤水清, 对上你想喝汤; 比另两条油低一档") 和差 reason ("营养均衡搭配合理") 对照示范, 把 reason 写作准则从抽象规则变成可模仿样本. 这是当前 prompt 最缺的, 也是最直接拉 reason 质量的改动.
2. **稳定契约可 version**: system prompt 不随每次调用变, 可以 git diff / A/B 对照, 改提示词的影响可量化.
3. **prompt cache 省钱**: 自用场景 6-15 次/天, cache 一天省几分钱, 量级很小但白拿.
4. **prompt injection 隔离**: profile.taste_description 来自用户, 应该在 user message 里, 不该和系统指令混. 拆完天然隔离.

#### C. payload 紧凑符号化

每菜从 11 字段 JSON 块 → 一行符号:
```
  · 菜名｜main·烹·油N[·辣N·甜N·汤N·processed]｜role=X[·grain=Y]｜价
```

规则:
- 默认值省略: 辣 0 / 甜 0-1 / 汤 1-2 / processed=false / role=配菜 / grain=无 都不显示
- 仅在硬约束依赖字段出现非默认值时显式标注 (processed=true, spicy>0, sweet>=2, wetness>=3)
- grain_type 仅在主食类菜出现 (role 含"主食")

实测瘦身效果:

| top N | 旧 JSON | 新紧凑 | 削减 |
|---|---|---|---|
| 30 | 48k chars | 5.7k chars | 88% |
| 40 | — | 7.2k chars | — |
| 50 | 77k chars | 8.7k chars | 89% |
| 100 | 159k chars | 17.3k chars | 89% |

加上 system 走 cache, **实际计费 input tokens 从 ~22k → ~6k (cache 命中时, 省 73%)**, 同时 top N 从 30 涨到 40.

#### D. health_flags 改规则后处理

旧设计: LLM 输出 candidate 时包含 `health_flags` 字段 (veg_ok / protein_ok / oil_ok / processed_meat / sweet_sauce / wetness 6 个 bool).

问题:
- 这 6 个 bool 全是确定性规则可算的 (V3 字段里已经有原值)
- 让 LLM 算: ① 强制输入 payload 必须含全部底层数值, 阻碍紧凑化; ② LLM 偶尔会算错 (尤其 oil_ok 是 3 道菜油等级的平均值, 模型不擅长算术); ③ 浪费 output tokens

新设计: LLM 只输出 `rank / is_explore / combo_index / fit_score / taste_match / risk_flags / one_line_reason` 共 7 个字段; `health_flags` 由 rerank.py 用 `_compute_health_flags(combo)` 在拿到 LLM 输出后**确定性补齐**, 对外字段集和 V2 完全兼容.

### 反对意见 / 风险

- **top40 是不是太保守**: CodeX 二审主张 40, 不上 50. 理由是 L2 已经把多样性骨架定死, top41+ 是同质化 tail, 给 LLM 反而劣化. 后续如果观察到 L3 重排明显被同质 top 锚死, 再上调.
- **紧凑符号 LLM 解析鲁棒性**: Sonnet 4.6 对 `·｜=` 这种符号化分隔的解析鲁棒性历史上是 OK 的 (D-038 同样格式打标 prompt 已经验证). 但首次上线后建议看 debug 调试台几次, 确认 LLM 没把分隔符吃错.
- **health_flags 规则化和 LLM 评估解耦**: 极端情况下 LLM 可能基于自己脑补的"健康分"排第 1, 但规则算出来 oil_ok=false. 这种不一致出现时, **以规则为准**, LLM 评分仅作 rank 用. 这是预期行为, 不是 bug.

### 触发重审的条件

- 自用一段时间后, reason 仍频繁出现"营养均衡搭配合理"这种空泛话术 — few-shot 没生效, 考虑加更多对照样本或换模型.
- top40 实际还是被同店/同品牌 tail 占, 没有结构增量 — 说明 L2 cap 在调整后某条出问题, 不是 L3 的事.
- LLM 输出 JSON 解析失败率 >5% — 紧凑 user message 让模型混乱, 考虑回退到中间形态 (键值对而非纯符号).

### 工程产物

- `prompts/rerank_system.md` (新)
- `prompts/rerank_user.md` (新, 仅供人对照)
- `prompts/rerank_topn.md` (删)
- `chisha/rerank.py`: 新增 `build_user_message` / `_compute_health_flags`; `_validate_llm_candidates` 删 health_flags 校验; `_REQUIRED_FIELDS` 缩一项; `_llm_rerank` 用 system/user 拆分调用
- `chisha/llm_client.py`: `call_text` 加 `cache_system` 参数; Anthropic 路径包成 `[{type:text, cache_control:ephemeral}]`
- `chisha/api.py:198`: top30 → top40
- `chisha/refine.py:149`: top30 → top40
- `chisha/debug_recommend.py`: 切片 + trace key 改 top40_*; `_llm_rerank_traced` 用新拆分签名 + trace 含 system/user 双段 chars
- `tests/test_rerank.py`: 删 health_flags 校验断言; 加 taste_match 范围校验测试

依赖: D-035 (LLM 精排), D-038 (LLM 抽象 Phase 1), D-043 (L2 重设计), D-044 (profile 真实化), D-045 (brand 层 cap)


### 三审补强 (2026-05-13, 真 Codex CLI review)

二审用 general-purpose subagent 模拟"Codex 视角"做的, 不是真 Codex. 用户安装 codex-cli 0.130.0 后, 用真 Codex 重审, 发现 4 个 Claude 一审 + 假二审都漏掉的真 bug:

#### 1. System prompt 事实错误 (严重)

之前 prompt 写: "L2 已做品牌/餐厅/菜系/形态多层 cap, 输入里不会有同店重复 combo (同一 brand 至多 1 条). 你不必再做去重."

**实测核对**: shenzhen-bay top60 里 Super Model 出现 **8 次**, 21 个 brand 重复 ≥2 次. 真实 brand cap=2 (D-045), 但 `apply_caps()` 返回 `head + tail`, top60 包含大量 tail 段同品牌变体.

LLM 读了这句话会以为输入已去重, **不会尝试同品牌内部择优**. 实际上输入有大量同 brand 候选, LLM 应该知道可以挑最贴情境的那条 (例如 Super Model 8 个变体里选蛋白最足 / 油最低 / 与 daily_mood 最对的那条).

修复: prompt 改成 "**输入里仍可能含同品牌、同餐厅的多个变体**（例如 Super Model 可能出现 6-8 次）. 你的工作之一就是在同品牌变体中选最贴合当下情境的那一条. 最终输出阶段系统会再做一次品牌去重兜底, 同 brand 最多保留 1 条, 所以你也不需要在 5 条输出里塞两个 Super Model."

#### 2. `_validate_llm_candidates()` 漏 idx 上界校验

只校验 `idx < 0`, 不校验 `idx >= input_size`. 越界 idx 会通过校验, 然后在 `rerank()` 主入口 `if not (0 <= idx < len(top_combos)):` **静默 continue**, 然后 `_enforce_brand_unique()` 用 top_combos 头部按 score 补位. 结果: "LLM 看似输出了 5 条 candidate, 实际部分是规则补位", 质量隐式退化, **N 越大风险越高**.

修复: `_validate_llm_candidates(cands, n_max, input_size=None, n_explore_expected=None)` 新增两个可选参数:
- `input_size`: 传入时校验 `0 <= idx < input_size`, 越界整批 fallback
- `n_explore_expected`: 传入时校验 `sum(is_explore) == n_explore`, 且 exploit 段在前 explore 段在后

加 6 个新测试覆盖这两个新校验项. test_rerank.py 从 24 → 30.

#### 3. 没启用 JSON mode / structured output

代码是 `call_text(prompt)` + `re.search(r"\{.*\}", out, re.DOTALL)` + `json.loads`. 在 N 大 / output 复杂时容易丢字段或 hallucinate. 暂不强制改 JSON mode (Anthropic 直连不支持 OpenAI 风格 response_format), 但 prompt 加严: "不要 markdown 代码块, 不要解释, 不要前缀后缀". Codex 二审指出这是后续 P1 改造项.

#### 4. 重排原则优先级模糊

旧 prompt 把 taste_description / daily_mood / last_feedback 并列, LLM 容易用长期口味覆盖当次意图. 真 Codex 指出外卖场景的正确优先级:

```
1. refine_input (用户当下显式指令, 最高)
2. daily_mood + last_feedback.chips (当下情绪 / 上一顿反馈)
3. taste_description (长期口味, 当 2 信号弱时主导)
4. 健康结构
5. 多样性奖励
```

修复: prompt 重排原则段按此顺序严格降序排列, 写明 "refine_input 不命中的全部降权".

#### 5. explore 缺 few-shot + "中段"定义模糊

旧 prompt 只有 exploit 好/坏 reason 对照, 没有 explore 示例. 而且 "explore 候选 = 打分中段 + 最近未吃" 里 "中段" 没界定. N=60 时 "中段" 指 10-30 还是 30-50?

修复: prompt 加 3 条 explore 好 reason 示例. 加边界规则: "explore 优先从排名 11-N 中选; 必须不违反 hard constraints; 优先最近 3/7 天未吃 cuisine/cooking_method; 如果 daily_mood 很强, explore 也必须服务 mood, 不以新奇牺牲本轮需求."

### N=60 vs N=80/100 (真 Codex 二审定调, 保留 60 默认)

二审用一个关键观察打掉"激进上 N"的论证: `_enforce_brand_unique()` 已经把同 brand 限制到 1 条输出. **top61-80 在 shenzhen-bay 坍缩到 4 brand**, 意味着这段的价值只剩"用同品牌低位变体替换同品牌高位变体". 这条收益路径在 prompt 事实错误未修前 LLM 是盲的; 修了之后理论可达, 但**需要先观测**:

- `selected_idx >= 40` 的比例: 验证 N 涨到 60 是否真在救场
- `selected_idx >= 60` 的比例: 验证是否需要进一步 N=80
- `brand_has_higher_sibling`: LLM 是否真在做同品牌择优

落地: `_log_selection_metrics()` 新函数, `rerank()` 每次打印这三个 metric. 一周后看真实分布再决定要不要进一步上调.

不推荐凭理论可能性直接扩 N=80/100. RankGPT 论文虽然是 GPT-4 时代结论, 但 listwise rerank 输入越大输出不稳定是任务层风险, Sonnet 4.6 的 MRCR/GraphWalks 强是定位检索能力, 不是跨 100 候选的比较排序能力. 不能凭上下文窗口大就乐观.

### 三审增量产物

- `prompts/rerank_system.md`: 大改, 修事实错误 + 重排原则优先级 + 加 explore few-shot + 加格式省略示例
- `chisha/rerank.py:_validate_llm_candidates`: 加 `input_size` + `n_explore_expected` 两个校验参数
- `chisha/rerank.py:_log_selection_metrics`: 新观测埋点
- `chisha/rerank.py:_llm_rerank` + `chisha/debug_recommend.py:_llm_rerank_traced`: 传新校验参数
- `tests/test_rerank.py`: 加 6 个新校验测试 (24 → 30)
- 测试 311 → 317 全过

教训: "假二审" (general-purpose subagent 模拟 Codex 视角) 看不到代码细节里的事实错误 + 校验漏洞, 只能从已知信息推. **真 Codex (codex-cli) 通过实际读代码 + 实测才能发现**: prompt 与代码事实不一致, 校验漏 idx 上界, 没启用 JSON mode. 重大决策建议用真二审 (真 Codex CLI 或独立人审).


---

## D-047 — LLM Provider 抽象 + Claude Code CLI 路径

**日期**: 2026-05-14
**状态**: 已实施

**背景**: 自用阶段每天 1-2 次推荐, 用 ANTHROPIC_API_KEY 月成本 ¥20-100,
而本机已有 Max 订阅. 让 chisha 复用订阅额度调 LLM, 同时保留 API key /
OpenRouter 路径供未来分发用户使用.

**方案**: subprocess 调 `claude -p`, 10 个隔离 flag (`--effort low` /
`--tools ""` / `--disable-slash-commands` / `--setting-sources ""` /
`--strict-mcp-config` / `--no-session-persistence` / `--system-prompt-file` /
`--input-format text` 等), cwd 在 `~/.cache/chisha/llm_tmp/` 私有目录,
env 过滤 `CLAUDE_*` 防干扰, Popen + start_new_session 防 orphan.

**架构**: `chisha/llm_providers/` 子包, 三 provider (anthropic_api /
openrouter / claude_code_cli) 统一签名; `chisha/llm_client.py` 成薄路由层;
profile.yaml `llm` 段控制 + 环境变量 `CHISHA_LLM_PROVIDER` 强制覆盖.

**实测**: N=60 sonnet effort=low 端到端 60s, 输出结构正确;
订阅消耗 1 message 配额/次. 详见:
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


# 今天吃点啥 · 设计文档（V1）

> 设计与实现细节。V1 目标极简：打标准、推得对、自己用一周。
> 项目名：今天吃点啥 · 代码名：`chisha`
> 配套文档：[PRD](docs/PRD.md) · [DECISIONS](docs/DECISIONS.md) · [ROADMAP](docs/ROADMAP.md) · [README](README.md)

---

## 0. 阅读指南

### 文档体系

这份 DESIGN.md 只讲**怎么做**。其他三份分别讲：

- **为什么做** → [docs/PRD.md](docs/PRD.md)
- **为什么这么决定的（决策思考链）** → [docs/DECISIONS.md](docs/DECISIONS.md)
- **什么时候做什么、什么不做** → [docs/ROADMAP.md](docs/ROADMAP.md)

实现某个功能前，先去 ROADMAP 确认它在当前版本范围内。
对设计有疑问时，先去 DECISIONS 看是否有对应决策记录（很多看似可改的设计，背后有不能改的理由）。

### 本文档导航

| 章节 | 何时看 |
|---|---|
| §1-2 产品定位 + 最终架构 | 动手前先读，明白整体形态 |
| §3 V1 最小闭环 | **这是开发主线**，按这个开 Claude Code 干活 |
| §4 实操避坑指南 | 动手时随时回来看，避免踩坑 |
| §5-6 完整架构 + V2+ 规划 | V1 跑通后再读，规划下一阶段 |
| §7 设计决策记录摘要 | 完整版见 [docs/DECISIONS.md](docs/DECISIONS.md) |

---

## 1. 产品定位

**两个独立的开源工件，配合使用：**

### 1.1 工件 A：`chisha-data-{office_zone}`（L1 数据层）

- **形态**：Python 包按工区拆子包（V1 单仓 `data/` 目录，V2.4 拆 `chisha-data-shenzhen-keji` / `chisha-data-beijing-zgc` 等）
- **内容**：打标好的菜品 + 商家数据
- **维护方**：sister project `chisha-collector` 负责采集 / 清洗 / 打标 / 保鲜（15 天周期），本仓只消费
- **使用方**：被 L2 Skill 调用，未来可被任何工具/Agent 使用
- **决策依据**：[D-002](docs/DECISIONS.md#d-002) 数据/代码独立分发，[D-027](docs/DECISIONS.md#d-027) 数据来源边界

### 1.2 工件 B：`chisha`（L2 推荐层）

- **形态**：开源 Skill 仓库（GitHub），未来打包成 MCP Server
- **内容**：推荐方法论代码、prompt 模板、数据 schema
- **使用方**：用户在自己的 Agent 里加载
- **核心特性**：用户的画像、反馈、历史**全部本地存储**，闭环在用户侧

### 1.3 数据归属

| 数据 | 归属 |
|---|---|
| 商家库 + 菜品库 + 营养打标 | L1 工件内（作者维护） |
| profile.yaml（用户偏好） | L2 用户本地 |
| meal_log.jsonl（吃过啥） | L2 用户本地 |
| personal_offsets.json | L2 用户本地 |
| learned_profile.yaml | L2 用户本地 |

**作者完全不参与运行，完全不接触用户数据。**

---

## 2. 最终架构

```
用户的 Agent（Claude Code / OpenClaw / 自研）
│
├── chisha（L2 · 推荐层）
│   ├── 用户数据（本地）
│   │   ├── profile.yaml
│   │   ├── meal_log.jsonl
│   │   ├── personal_offsets.json
│   │   ├── learned_profile.yaml
│   │   └── sessions/
│   ├── 推荐代码（recall/score/refine/feedback/learned_profile）
│   └── prompt 模板
│
├── chisha_data（L1 · 数据层）  ← V1 直接 import 调用
│   ├── data/（restaurants.json, dishes_tagged.json）
│   └── api.py
│
└── Agent 自带能力（LLM、IM 通道、定时调度）
```

**层间调用方式**：
- V1：L2 直接 `from chisha_data import api` import 调用（最简单）
- V2+：可选 CLI 包装 / MCP 包装（开放给同事时再做）

---

## 3. V1 最小闭环（开发主线）

### 3.1 V1 目标

**用一句话说清楚**：让自己的 Agent 能给自己推菜，推得过得去，自用一周。

**V1 必做**（验证核心假设）：
- 商品打标 → 准确率 ≥ 80%（前置：依赖 sister project `chisha-collector` 提供 raw 数据）
- 召回 + 打分 跑通（V1 不上 LLM 精排，详见 §3.6）
- profile.yaml 手填（含弱约束三件套）
- recommend_meal 返回结构化 JSON（含一句话理由）
- **接入 OpenClaw + 飞书卡片**（V1 必须实现"主动推送"形态，否则核心承诺不成立——见 [D-022](docs/DECISIONS.md#d-022)）
- 自用一周收集 bug

**V1 暂不做**（核心验证后再加）：
- ❌ CLI 包装
- ❌ pip 包发布
- ❌ MCP Server
- ❌ SKILL.md（Claude Code 接入）—— V2 再做
- ❌ LLM 精排"挑 3 个"（V1 = 打分 top 3 + LLM 只写 reason，见 [D-024](docs/DECISIONS.md#d-024)）
- ❌ 反馈系统（personal_offsets 写入 + UI）
- ❌ learned_profile 自动加工
- ❌ refine 多轮收敛、探索机制、session 管理
- ❌ 多用户 / 开源化
- ❌ 多区域支持

理由：**推荐质量 + 触发场景都是 1，其他是 0**。
- 推荐质量没到位，反馈/MCP/CLI 全是浪费
- 推荐再准但触发场景不对（用户得自己敲命令查），决策疲劳省不下来——所以 V1 必须接 OpenClaw 走通飞书卡片，不能像原方案绕一道 Claude Code

### 3.2 V1 三个里程碑

#### 里程碑 1：数据接入 + 打标（约 1 周）

**目标**：得到一份可用的 `dishes_tagged.json`，准确率 ≥ 80%。

**前置**：sister project `chisha-collector` 已经把深圳科技园的 raw 数据采到位（restaurants.json + dishes_raw.json），本仓只消费。

**步骤**：
1. 从 `chisha-collector` 拉 `restaurants.json` + `dishes_raw.json`，放进 `data/shenzhen-keji/`（schema 见 §5.2）
2. 写打标 prompt（见 §3.5）
3. 跑打标脚本，每批 30-50 条
4. **抽查 50 条 LLM 打标结果**，准确率 < 80% 就改 prompt 重跑
5. 输出 `data/shenzhen-keji/dishes_tagged.json`

**不做**：自己采数据（不在本仓职责内）、CLI、pip 包、版本管理。本地一份 JSON 文件够用。

#### 里程碑 2：推荐引擎跑通（约 1-2 周）

**目标**：`recommend_meal("lunch")` 能返回 3 个结构化候选 + 一句话理由。

**步骤**：
1. 手填 `profile.yaml`（见 §5.3，弱约束三件套：控油 + 蔬菜下限 + 蛋白下限）
2. 实现召回（规则 + 多样性硬过滤）→ 输出 top 100 候选
3. **人工抽查 100 个候选**，看是不是合理（没有明显该排除的）
4. 实现打分函数（控油打分 + 蔬菜达标 + 蛋白达标 + 销量 + 菜系偏好）→ 排序候选
5. **不做 LLM 精排**——直接取打分 top 3
6. LLM 仅生成每条 `reason_one_line`（输入 = 单条 combo + profile，输出 ≤ 100 token）
7. 输出结构化 JSON（schema 见 §5.7）

**为什么 V1 不做 LLM 精排**：
- 几百到几千 SKU 召回 top 100 后，**打分公式已经能选出靠谱的 top 3**
- LLM 在"挑哪 3 个"上引入随机性 + 容易漂移，反而是规则+打分稳
- LLM 留着干它最擅长的事：根据 profile + combo 写一句具体的人话理由
- V2.x 反馈系统起来后再开 LLM 精排，让它根据 `taste_description` 重排
- 决策见 [D-024](docs/DECISIONS.md#d-024)

**简化**：
- N=3 即可（不做 5 个候选 + 探索）
- 不做 refine 多轮收敛
- 不做反馈处理
- 不做 session 管理

#### 里程碑 3：~~接入 OpenClaw + 飞书卡片~~ → V1 改 Web SPA · 飞书延后到 V1.5（约 1-2 周）

> **2026-05-15 翻案**（[D-051](docs/DECISIONS.md#d-051)）：V1 主交互改本机 localhost Web SPA（`apps/web/`），飞书"主动推 + 卡片交互"降级到 V1.5 做"推送 + deeplink 跳 Web"。**下面这段原飞书卡片方案保留作历史**，prefer 走 Web SPA 路径。Web 用户视图设计与文案规范见 [`docs/style-guide.md`](docs/style-guide.md)，前后端契约见 [`docs/api.md`](docs/api.md)。

**目标**（旧版本，已 partial superseded）：OpenClaw 在 11:25 / 18:00 主动推飞书卡片，自己用一周。

**步骤**：
1. 把 `recommend_meal` 包成 OpenClaw skill（Python 函数 + skill 描述）
2. 在 OpenClaw 配置 cron 触发：工作日 11:25 / 18:00 触发
3. 推送通道：飞书 IM 卡片（用 OpenClaw 已有的飞书集成）
4. 卡片渲染：3 个候选 + 跳转链接（点评/美团商家页 deeplink，跳不过去就 fallback URL）
5. **不做反馈按钮**（V2.0 才做）
6. 中午/晚上接到卡片，记录：
   - 是否合理
   - 最终选了哪个 / 没选 / 自己另点
   - 实际吃了啥（纸笔/备忘录）

**这一周的"反馈"是手记**，不写代码。等推荐质量稳定后，V2.0 再做反馈系统。

**为什么不先接 Claude Code**：原方案 D-018 选 Claude Code 是规避 MCP/IM 复杂度，但牺牲了"主动推送"——而主动推送是 PRD §5 故事 1 的核心承诺。V1 不做这一步，整个产品价值打 5 折。决策翻案见 [D-022](docs/DECISIONS.md#d-022)。

### 3.3 V1 抽查清单（动手前置）

跑通后、自用前，做两个 30 分钟抽查：

**抽查 1：打标准确率**
随机抽 50 道菜，人眼判断 LLM 打的字段（oil_level / vegetable_ratio / is_complete_meal / spicy_level）准不准。
- 准确率 < 80%：回头改打标 prompt
- 准确率 ≥ 80%：通过

**抽查 2：推荐空跑**
profile.yaml 填好、meal_log 是空的，连续跑 5 次 `recommend_meal("lunch")`。看：
- 是不是都符合 plate_rule（蔬菜 / 蛋白 / 主食）？
- 商家有没有过度集中？
- 蛋白来源有没有多样？
- 推荐理由像不像人话？

不通过就调 prompt / 调权重 / 重新打标，**比硬用一周再排查问题快得多**。

### 3.4 V1 项目结构（建议）

```
chisha/
├── data/
│   └── shenzhen-keji/           # 按工区分目录（V2.4 拆包后变成 chisha-data-shenzhen-keji）
│       ├── restaurants.json     # 来自 chisha-collector
│       ├── dishes_raw.json      # 来自 chisha-collector，打标前
│       └── dishes_tagged.json   # 本仓打标后（V1 主用）
│
├── profile.yaml                 # 手填，含弱约束三件套
│
├── chisha/                      # L2 推荐层 Python 包
│   ├── __init__.py
│   ├── api.py                   # recommend_meal 主入口
│   ├── recall.py                # 召回 + 多样性
│   ├── score.py                 # 打分函数
│   ├── rerank.py                # L3 LLM 精排 (D-033/D-046/D-047)
│   ├── llm_client.py            # LLM 路由层 (D-047): provider 选择 + 模型解析
│   └── llm_providers/           # 三 provider (D-047)
│       ├── anthropic_api.py     # ANTHROPIC_API_KEY 直连
│       ├── openrouter.py        # OPENROUTER_API_KEY → 第三方
│       └── claude_code_cli.py   # claude -p subprocess (复用订阅额度)
│
├── integrations/
│   └── openclaw/                # V1 接入 OpenClaw + 飞书
│       ├── skill.py             # skill 入口
│       └── feishu_card.py       # 飞书卡片渲染
│
├── scripts/
│   ├── tag_via_api.py           # V3 生产打标（OpenRouter, 默认 deepseek-v4-flash, 见 D-037）
│   ├── tag_dishes.py            # V1/V2 旧打标脚本（Anthropic 直连, 已停用）
│   └── inspect_candidates.py    # 抽查工具
│
├── prompts/
│   ├── tag_dishes.md            # 菜品打标 prompt (D-037, V3 dual-model)
│   ├── rerank_system.md         # L3 精排 system prompt (D-046/D-047)
│   ├── rerank_user.md           # L3 精排 user 模板 (D-046)
│   └── parse_feedback.md        # 反馈解析 prompt
│
├── tests/
│
└── README.md
```

> V1 阶段 L1 数据层先以 `data/{office_zone}/` 目录形式直接放在项目里，V2.4 跑通后再按工区拆 `chisha-data-{office_zone}` 子包（[D-002](docs/DECISIONS.md#d-002) 修订版）。

### 3.5 打标 prompt 要点

完整 prompt 见 §5.5，这里只列 V1 必须做对的事：

1. **必须把 price 喂进去**：同名菜不同价对应不同分量
2. **必须 temperature=0**：保证可复现
3. **每批 30-50 条**：太大准确率掉
4. **JSON 输出做兜底解析**：try/except + 重试

### 3.6 V1 精排：打分 top 3 + LLM 写理由（**已删除 — D-049**）

> ⚠️ V1 简化路径 (D-024) 已被 D-049 砍除, 代码不再存在 (`chisha/reason.py` / `prompts/reason_one_line.md` 整文件删, `scripts/eval_recommend.py` 离线对比脚本也删). 现在唯一推荐链路是 V2 (D-033 起): build_context → recall → score V2 → L3 LLM rerank top60→5. 下文章节保留作历史决策叙述。

V1 不让 LLM "选 3 个"。流程是：

```
召回 100 → 打分排序 → 取 top 3 → LLM 为每条单独写 reason_one_line
```

**V1 LLM 唯一用途**：写理由 prompt（`prompts/reason_one_line.md`，已删）：

```
你给一个外卖组合写一句推荐理由（≤ 30 字），帮用户快速判断要不要选。

输入：
- profile（taste_description + plate_rule + 最近 7 天吃过啥）
- 一个 combo（restaurant + dishes）

理由必须：
- 具体（"低油牛肉 + 清炒空心菜，控油 + 有菜"）
- 而不是套话（"营养均衡，搭配合理"）
- 如果 combo 命中 taste_description 的某个偏好，明确指出
- 如果 combo 是用户最近没吃过的菜系，提一下

输出：纯文本一句话，无引号无前缀。
```

**V2.x 才开 LLM 精排**：届时输入 profile + learned_profile（统计聚合） + 100 候选，让 LLM 重排并挑 5 个。这是 V2.0 反馈数据攒起来之后的事。

**V1 不传 learned_profile、不传 meal_log**——这些是 V2 的事。

---

## 4. 实操避坑指南

动手时随时回来看。

### 4.1 打标阶段

**坑 1：忘记把 price 喂给 LLM**
"水煮牛肉 28 元" vs "水煮牛肉 68 元"分量天差地别，protein_grams_estimate 必须不同。打标 prompt 中 price 是必填字段。

**坑 2：temperature 没设 0**
默认 temperature 偏高，同一道菜跑两次结果不一致。`temperature=0`。

**坑 3：批次太大**
一次塞 500 条给 LLM，注意力分散，oil_level 等字段准确率显著下降。**每批 30-50 条**。

**坑 4：JSON 输出坏掉没兜底**
Sonnet 偶尔会输出坏 JSON（未转义引号、多余逗号）。打标脚本必须有 try/except + 重试机制，否则一条坏数据搞垮整批。

**坑 5：抽查没做就上线**
50 条人工抽查必须做。LLM 打标在某些字段（特别是 vegetable_ratio_estimate）容易系统性偏差，不抽查发现不了。

### 4.2 召回阶段

**坑 6：召回先跑确定性规则，别先接 LLM**
召回是纯规则，不需要 LLM。先用规则跑出 top 100，**人工看这 100 个**。如果召回就不对（包含明显该排除的菜），LLM 精排救不回来。

**坑 7：多样性约束在 V1 空 meal_log 时形同虚设**
"7 天内不重复商家"对空 meal_log 没作用。V1 第一周推出来的菜可能商家高度集中。这是已知现象，**自用一周后 meal_log 攒起来了，多样性就生效了**。不要在 V1 引入复杂的"冷启动多样性"逻辑。

**坑 8：组合数量爆炸**
笛卡尔积容易炸（5 蛋白 × 3 蔬菜 × 2 主食 × 10 餐厅 = 300 组合）。每家餐厅最多产 3 个组合，全局取 top 100。

### 4.3 精排阶段

**坑 9：N=3 就好，别上 5 个**
V1 不做探索机制。出 3 个稳定推荐，跑顺了 V2 再加探索。复杂度阶梯式上。

**坑 10：推荐理由会变成空话**
LLM 写理由容易出"营养均衡，搭配合理"这种废话。prompt 里明确要求理由必须**具体**（"低油牛肉 + 清炒空心菜，本周还没吃过潮汕"），并给几个 good/bad 示例。

**坑 11：不要让 LLM 做硬约束判断**
plate_rule（弱约束三件套）、避雷菜，**这些用代码硬过滤 / 打分**，不要让 LLM 判断。LLM 在"写理由"上靠谱，在"严格执行规则"和"挑哪 3 个"上不稳。这是 V1 不做 LLM 精排的根本原因（[D-024](docs/DECISIONS.md#d-024)）。

**坑 12：弱约束不是没约束**
"控油 + 有菜 + 有蛋白"是弱约束但仍然必须达成。召回阶段就要保证：每个 combo 至少包含 1 道蔬菜类（vegetable_ratio_estimate ≥ 0.6）+ 1 道蛋白下限（protein_grams_estimate ≥ profile.min_protein_g）。控油是打分项不是硬过滤（[D-023](docs/DECISIONS.md#d-023)、[D-006](docs/DECISIONS.md#d-006)）。

### 4.4 接入 OpenClaw + 飞书阶段

**坑 13：飞书卡片跳转 deeplink 经常失败**
点评/美团 deeplink 在 iOS 上偶尔无法唤起 APP。卡片必须同时附 fallback URL，并且测试 iOS / Android / 飞书 PC 端三端跳转。

**坑 14：cron 触发别死磕 11:25**
不同人午餐时间不同，OpenClaw cron 配成可调（profile.yaml 里 `meal_trigger_time: {lunch: "11:25", dinner: "18:00"}`）。周末不触发。

**坑 15：V1 别做反馈系统**
反馈系统涉及 UI、写入逻辑、offsets 累加规则。**V1 用纸笔/备忘录记**，等推荐质量稳定后再做。

**坑 16：每次推荐都打日志**
即使不做反馈系统，每次 `recommend_meal` 调用 + 输入 + 输出都打到本地日志文件 `logs/meal_log.jsonl`。一周后回头看日志，能看出推荐质量趋势。这是最便宜的"反馈"。

**坑 17：Claude Code 接入推迟到 V2.3**
Claude Code 是 CLI/IDE 形态，不能主动推送，与 PRD 故事 1 的"主动卡片"承诺不匹配。V2.3 SKILL.md 里再补 Claude Code 适配（用户主动 query 场景）。

---

## 5. 完整架构（V1 跑通后的扩展参考）

V1 不实现这些，但开发时**接口设计要预留**这些扩展能力。

### 5.1 完整 API（V2+ 扩展）

V1 只做 `recommend_meal`，V2+ 扩展到 6 个：

| Tool | V1 | V2 | 用途 |
|---|---|---|---|
| `recommend_meal` | ✅ | | 推荐主入口 |
| `refine_recommendation` | ❌ | ✅ | 对话收敛 |
| `accept_recommendation` | ❌ | ✅ | 用户选定，写 meal_log |
| `log_meal` | ❌ | ✅ | 自由形式补登 |
| `submit_feedback` | ❌ | ✅ | 反馈写入 |
| `update_taste` | ❌ | ✅ | 偏好调整 |

### 5.2 数据 schema 完整版

`restaurants.json`：

```json
{
  "id": "r_001",
  "name": "湘里湘亲",
  "category": "湘菜",
  "city": "深圳",
  "office_zone": "shenzhen-keji",
  "rating": 4.5,
  "monthly_orders": 3200,
  "distance_m": 504,
  "delivery_eta_min": 15,
  "delivery_fee": 0.2,
  "min_order": 20.0
}
```

字段说明：
- `id`: 由 loader 生成 `r_NNN`，按 raw 数据 restaurant 顺序
- `category`: 由 dishes_tagged.cuisine majority vote 回填，raw 数据通常采不到
- `office_zone`: 形如 `shenzhen-keji` / `home`，对应 `data/{office_zone}/` 目录
- `monthly_orders`: 解析自 raw `monthly_sales`（"月售1000+" → 1000，取下界）
- `distance_m`: 解析自 raw `distance`（"504m" → 504, "1.2km" → 1200）
- `delivery_eta_min`: 解析自 raw `delivery_time`（"约15分钟" → 15, "约1小时" → 60）
- `lat/lng/district`: V1 不需要，删除

`dishes_tagged.json`（v3, D-032 加 5 字段）：

```json
{
  "dish_id": "d_001_007",
  "restaurant_id": "r_001",
  "raw_name": "水煮牛肉(中辣) 大份",
  "canonical_name": "水煮牛肉 大份",
  "price": 48,
  "monthly_sales": 245,
  "cuisine": "川菜",
  "nutrition_profile": {
    "main_ingredient_type": "红肉",
    "cooking_method": "煮",
    "oil_level": 5,
    "protein_grams_estimate": 40,
    "vegetable_ratio_estimate": 0.2,
    "is_complete_meal": false,
    "spicy_level": 2,
    "dish_role": "主菜",
    "processed_meat_flag": false,
    "sweet_sauce_level": 0,
    "wetness": 3,
    "grain_type": "无",
    "tags": ["高蛋白", "重口味", "下饭"]
  },
  "metadata": {
    "tagged_at": "2026-05-11T18:00:00",
    "tag_version": "v3",
    "is_available": true
  }
}
```

字段定义：

旧 8 字段（v1/v2 已有）：
- `cuisine`: 菜系大分类（湘菜/川菜/粤菜/潮汕/东北/西北/江浙/鲁菜/日式/韩式/西式/东南亚/快餐/小吃/汤粥/其他）—— D-025 个性化粒度需要。赣菜/客家/云贵/桂菜归"其他"。
- `main_ingredient_type`: 红肉/白肉/海鲜/蛋/豆制品/纯素/主食/汤/其他
- `cooking_method`: 蒸/煮/烤/炒/炖/油炸/凉拌/生/煎
- `oil_level`: 1-5（1 = 白灼清蒸，5 = 油炸爆炒）
- `protein_grams_estimate`: 5g 粒度整数（0/5/10/.../60）
- `vegetable_ratio_estimate`: 0.0-1.0（看体积比）
- `spicy_level`: 0-3
- `is_complete_meal`: 一份单点能否接近达标（翘脚牛肉=true，蒜蓉空心菜=false）

v3 新增 5 字段（D-032，2026-05-11）：
- `dish_role`: **主菜/主食/配菜/汤/小食/饮品/套餐** —— 拼餐槽位，决定能不能拼餐（避免 主食+主食 / 0 蔬菜的失败 combo）。含 "+饭/+饮料/+小菜/+汤/拼盘" 等触发词无须"套餐"二字也归套餐。汉堡/三明治=主食，西式蛋白碗=主菜。
- `processed_meat_flag`: bool —— 是否含工业重组肉/腌制肉/加工肉肠类（蟹柳/午餐肉/培根/烤肠/腊肠/腊肉=true; 叉烧/烧鸭/卤水/酱牛肉=false 整块鲜肉熟制; 汉堡/披萨主夹层是火腿/培根/香肠则 true）。命中减脂偏好降权。
- `sweet_sauce_level`: 0-3 —— 酱汁甜度。红烧/糖醋/照烧/烧汁/普通叉烧/烧鸭/韩辣/泰甜辣=2; 蜜汁/蜂蜜/拔丝/麦芽糖=3。命中"受不了甜口"。
- `wetness`: 1-3 —— 干湿程度。=3 仅指真正"可喝汤底"（汤/粥/汤面/砂锅汤底/火锅）；关东煮/卤水浸泡/红烧浓汁/寿司=2; 干煸/凉拌/沙拉/干拌面=1。套餐含汤升级：套餐名列出"+汤/+鸡汤/+白粥"等可喝汤品 → 整套 wetness=3。命中"喜欢清爽带汤水/受不了油焖"。
- `grain_type`: 白米/糙米杂粮/精制面/全麦面/粗粮/粥/无 —— 主食类型。米粉/河粉/粿条 = 白米; 商业燕麦棒/能量棒 = 精制面（不归粗粮）; 西式蛋白碗 = 无; 套餐含多主食按更精制/高 GI 的标。

`restaurants.json` 的 `category` 字段由 `dishes_tagged.cuisine` 做 majority vote 后回填（采集器经常拿不到 restaurant 级 category）。

### 5.3 profile.yaml

> 以下 yaml 仅为 schema 示例。**实际生产 profile.yaml 见仓库根目录**，已按
> [D-044](docs/DECISIONS.md#d-044) 真实化重建（goal/zones/min_protein_g/avoid_dishes/price/taste_description 全量校正），
> 且引入"偏好层 vs 健康目标层分离"四段式 taste_description 结构（详见 [RECOMMEND_PRINCIPLES §12](docs/RECOMMEND_PRINCIPLES.md)）。
>
> **D-072 起新增 `methodology:` 字段**，引用 `profiles/methodologies/{name}.yaml` 的 L0 方法论 spec
> （`plate_rule` / `scoring_weights` / cap 默认值都从 spec 读，profile 显式字段 override；
> 缺 `methodology:` 字段时 fallback `harvard_plate` 并 `logger.info`，详见 [D-072 schema 字段表](docs/DECISIONS.md#d-072)）。

```yaml
# D-072: L0 方法论引用 (profiles/methodologies/{name}.yaml)
methodology: harvard_plate

basics:
  name: <YOUR_NAME>
  city: 深圳
  office_zone: 科技园
  goal: 减脂增肌期

# 弱约束三件套：控油 + 有蔬菜 + 有蛋白
# 不再要求"严格 1/2-1/4-1/4 比例"——见 D-023
plate_rule:
  # 蔬菜下限：每个 combo 至少包含 1 道菜满足 vegetable_ratio_estimate ≥ 0.6
  must_have_vegetable: true
  min_vegetable_dishes: 1

  # 蛋白下限：每个 combo 总 protein_grams_estimate ≥ 这个值
  min_protein_g: 25

  # 控油：软打分上限。oil_level > 这个值的 combo 会扣分但不被排除（D-006）
  prefer_oil_level_at_most: 3
  hard_max_oil_level: 5  # 真的硬上限，组合中任何一道菜 > 这个值才硬过滤

taste_description: |
  自然语言描述偏好。例：
  喜欢清爽不油的肉类，特别是带汤水的(潮汕牛肉、翘脚牛肉这种)。
  不爱重酱汁的红烧类。绿叶菜要清炒不要油焖。受不了甜口的菜。

preferences:
  liked_cuisines: [湘菜, 川菜, 潮汕牛肉, 日式定食]
  disliked_cuisines: [油炸快餐, 麻辣烫]
  avoid_dishes: [红烧肉, 梅菜扣肉]

  # spicy 匹配规则：profile 用整数（0=不辣 1=微辣 2=中辣 3=重辣），
  # 与 dish.spicy_level 严格相等比较：dish.spicy_level > profile.spicy_tolerance 硬过滤
  spicy_tolerance: 2  # 整数 0-3，对应"中辣"

diversity:
  no_same_restaurant_within_days: 7
  no_same_main_ingredient_within_days: 3   # 字段重命名：protein → main_ingredient

meal_trigger_time:
  lunch: "11:25"
  dinner: "18:00"
  weekend: false
```

**重要变更说明**：
- `plate_rule` 改弱约束（[D-023](docs/DECISIONS.md#d-023)）：不再有 `vegetable_ratio: 0.5` 这种"组合级硬比例"，改成"至少 1 道蔬菜 + 蛋白下限 + 软控油"
- `spicy_tolerance` 改成整数（[D-018-2 不一致问题修正](docs/DECISIONS.md#d-029)）：原来文字 "中辣" 没法和 dish 整数 spicy_level 直接比较

#### V2 新增字段（[D-033](docs/DECISIONS.md#d-033)、[D-034](docs/DECISIONS.md#d-034)）

```yaml
# 履约约束 (V2 进 score 打分，超过则扣分但不硬过滤)
delivery_constraints:
  max_delivery_eta_min: 60      # 餐厅 delivery_eta_min > 这个值会被扣分
  prefer_distance_m: 1500       # 距离软偏好，超过线性扣分

# 价格偏好 (V2 进 score 打分)
price_range:
  lunch_max: 60                 # 中午 combo total_price 软上限
  dinner_max: 80                # 晚上 combo total_price 软上限

# 当日情境 (V2 Context 注入层 D-034，由 OpenClaw trigger 每日首次饭点前问 1 句写入 session)
# 不进 profile.yaml 长期字段，是 per-day session 状态。这里只是 schema 参考：
# session.daily_mood ∈ {want_light, want_indulgent, want_soup, low_carb, want_clean, neutral, null}
```

`taste_description` 在 V2 起进 L3 打分和 L4 LLM rerank 决策（不再只进 reason），由 LLM 反馈解析员 + rerank 员把自然语言推断成结构化 boost/penalty。

### 5.4 V2+ 用户数据 schema

`meal_log.jsonl`（每行一条）：

```json
{
  "log_id": "ml_20260510_lunch_001",
  "timestamp": "2026-05-10T12:15:00",
  "meal_type": "lunch",
  "source": "accepted",
  "session_id": "20260510_lunch_a3f7",
  "restaurant_id": "r_001",
  "dishes": [
    {
      "dish_id": "d_00123",
      "canonical_name": "水煮牛肉",
      "cuisine": "川菜",
      "cooking_method": "煮",
      "main_ingredient_type": "红肉"
    }
  ],
  "context_at_recommend": {
    "daily_mood": "want_light",
    "weekday": 0,
    "last_meal": {"date": "2026-05-09", "meal_type": "dinner", "cuisine": "粤菜"},
    "recent_3d_cuisines": {"湘菜": 2, "川菜": 1},
    "refine_round": 1
  },
  "rank": 2,
  "score_breakdown": {"vegetable_floor_pass": 1.0, "low_oil": 0.6, "...": "..."},
  "feedback": {
    "rating_taste": 4,
    "rating_satisfaction": 3,
    "chips": ["太油", "想喝汤"],
    "want_again": false,
    "note": "牛肉有点柴",
    "submitted_at": "2026-05-10T14:30:00"
  }
}
```

V2 起 `feedback.chips` 由 [chisha/feedback.py](../chisha/feedback.py) 的 `parse_feedback()` 规范化, 必须 ∈ `CHIP_VOCAB`（见 chisha/feedback.py）. 旧 `oil_tag` / `portion_tag` / `delivery_tag` 字段被 `chips` 列表统一取代（[D-033](docs/DECISIONS.md#d-033)）, 旧字段 V1 兼容保留, V2 新写入只用 chips.

`context_at_recommend` 是 V2 [D-034](docs/DECISIONS.md#d-034) 注入层在推荐时刻的快照, 用于事后审计"为什么这条被推/被选/被拒". 写 meal_log 时一并落盘, 不修改原始 ContextSnapshot dataclass.

`personal_offsets.json`（**粒度变更**：从 `店::菜` 改成 `菜系×烹饪方式×主料` —— [D-025](docs/DECISIONS.md#d-025)）：

```json
{
  "川菜::煮::红肉": {
    "score_offset": -0.3,
    "oil_offset": 0.8,
    "portion_offset": 0,
    "feedback_count": 8,
    "last_updated": "2026-05-10T14:30:00"
  },
  "潮汕::煮::红肉": {
    "score_offset": +0.6,
    "feedback_count": 12,
    "last_updated": "2026-05-09T13:00:00"
  }
}
```

为什么这个粒度：单菜样本量 N=1~5 时，offset 信号比噪音还弱。聚到 (cuisine × cooking × ingredient) 维度后，常见维度能积到 N≥10，统计意义才出来。极端坏菜单独走 blacklist。

`learned_profile.yaml`（V2.2 **统计聚合**而不是 LLM 蒸馏 —— [D-026](docs/DECISIONS.md#d-026)）：

```yaml
last_updated: "2026-05-10T03:00:00"
data_window: "2026-04-12 ~ 2026-05-09"
sample_count: 87

stats:
  meals_logged_total: 87
  meals_with_feedback: 62
  avg_taste_rating: 4.1

# 统计聚合（不是 LLM 编的"洞察"）
top_preferences:
  - {dim: "潮汕::煮::红肉",  采纳率: 0.92, 平均评分: 4.6, n: 12}
  - {dim: "湘菜::炒::白肉",  采纳率: 0.83, 平均评分: 4.3, n: 8}
  - {dim: "日式::煎::海鲜",  采纳率: 0.80, 平均评分: 4.4, n: 6}

bottom_preferences:
  - {dim: "川菜::干煸::红肉", 采纳率: 0.20, 平均评分: 2.3, n: 5}
  - {dim: "粤菜::油焖::蔬菜", 采纳率: 0.25, 平均评分: 2.5, n: 4}

# 统计自动维护的黑名单（精确到具体菜，需要 ≥ 3 次低评分）
blacklist:
  - {restaurant_id: r_088, canonical_name: 红烧肉, reason: "3 次评分均 ≤ 2"}

# 长期画像文字摘要（输入 LLM 精排 prompt 用，可手编）
summary_for_llm: |
  过去 60 天，最高接受率的是潮汕煮、湘菜清炒；最差评的是干煸、油焖。
  对带汤水做法明显偏好。
```

不再有 `learned_insights:` 这种 LLM 蒸馏出来的"洞察"——N=1 数据下太容易出过拟合假规律（"周一周二倾向清淡"——这可能就是 1-2 个数据点凑的）。统计聚合可解释、可手编、不漂移。

### 5.5 打标 prompt（完整版）

> 注：本节为 v1 简化示例。当前生产 prompt 为 v3（r3 patch），见 [prompts/tag_dishes.md](../prompts/tag_dishes.md) 15 字段完整版（D-032 / D-036）。
>
> Golden set 与模型选型见 [eval/dish_tagging_eval/](../eval/dish_tagging_eval/)：[D-036](docs/DECISIONS.md#d-036) Opus + Codex 双模型共创 171 条 golden；[D-037](docs/DECISIONS.md#d-037) 6 模型横评后生产默认 `deepseek/deepseek-v4-flash`（field acc 88.9%, 100万条 $100）。

```
你是营养标签助手。给以下菜品打营养画像。

输入字段：dish_id, name, restaurant_category, price

输出严格 JSON 数组，每条：
{
  "dish_id": "原样保留",
  "canonical_name": "去除促销词、辣度括号、emoji 后的标准名",
  "main_ingredient_type": "红肉|白肉|海鲜|蛋|豆制品|纯素|主食|汤|其他",
  "cooking_method": "蒸|煮|烤|炒|炖|油炸|凉拌|生",
  "oil_level": 1-5,
  "protein_grams_estimate": 整数,
  "vegetable_ratio_estimate": 0.0-1.0,
  "is_complete_meal": true|false,
  "spicy_level": 0-3,
  "tags": ["高蛋白", "低脂", "适合减脂", ...]
}

判断准则：

oil_level（最重要）：
- 1 = 白灼清蒸白煮生食
- 2 = 清炒汆烫潮汕涮煮
- 3 = 家常炒菜番茄炒蛋
- 4 = 红烧干煸铁板孜然
- 5 = 油炸油焖爆炒酥炸地三鲜回锅肉

vegetable_ratio_estimate（按体积）：
- 纯叶菜 = 0.9-0.95
- 番茄炒蛋 = 0.5-0.6
- 水煮肉片 = 0.15-0.25
- 纯肉菜 = 0.0-0.1

protein_grams_estimate（必须看 price 估分量）：
- 200g 红肉/白肉菜 ≈ 30-40g
- 价格越高分量越大，按比例估算

is_complete_meal：
- true: 翘脚牛肉、潮汕牛肉粿条、酸菜鱼套餐、卤肉饭+青菜套餐
- false: 单道菜（蒜蓉空心菜、水煮肉片）、单点米饭

canonical_name：
剥离 "【】、(辣度)、🌶️、爆款" 等噪音，输出标准菜名。

示例输入：
[
  {"dish_id": "d001", "name": "蒜蓉空心菜", "restaurant_category": "湘菜", "price": 18},
  {"dish_id": "d002", "name": "【新品】水煮牛肉(中辣) 大份", "restaurant_category": "川菜", "price": 58}
]

示例输出：
[
  {"dish_id":"d001","canonical_name":"蒜蓉空心菜","main_ingredient_type":"纯素","cooking_method":"炒","oil_level":3,"protein_grams_estimate":3,"vegetable_ratio_estimate":0.95,"is_complete_meal":false,"spicy_level":0,"tags":["高纤维","清淡","适合减脂"]},
  {"dish_id":"d002","canonical_name":"水煮牛肉","main_ingredient_type":"红肉","cooking_method":"煮","oil_level":4,"protein_grams_estimate":42,"vegetable_ratio_estimate":0.2,"is_complete_meal":false,"spicy_level":2,"tags":["高蛋白","重口味","下饭"]}
]

现在开始：
{INPUT_DISHES_JSON}
```

### 5.6 推荐三阶段（完整版）

#### 召回（规则）

设计原则（[D-041](docs/DECISIONS.md#d-041)）：**召回阶段尽量召回 + 用 profile 显式硬约束剪枝**；
硬约束（命名 `hard_max_*` / `banned_*` / `avoid_*`）放召回，软约束（`prefer_max_*`）放打分。

```
1. 候选商家：profile.basics.zones[meal_type] 内
2. 餐厅级硬 ban：
   - 近 7 天 meal_log 吃过的 restaurant_id（多样性）
   - delivery_constraints.hard_max_eta_min: ETA 超此值整家 ban（外卖只看 ETA, 不卡距离）
   - preferences.avoid_restaurants: 餐厅名/品牌 substring 模糊匹配
3. 菜级硬过滤（非协商）：
   - preferences.avoid_dishes: canonical_name substring 模糊匹配
   - preferences.avoid_main_ingredients: main_ingredient_type 精确匹配（如 [海鲜]）
   - preferences.avoid_cooking_methods: cooking_method 精确匹配（如 [油炸]）
   - preferences.banned_cuisines: dish.cuisine 精确匹配（硬，区别于 disliked_cuisines 软）
   - dish.spicy_level > profile.spicy_tolerance
   - dish.oil_level > plate_rule.hard_max_oil_level（默认 4，5=不卡）
   - dish.monthly_sales > 0 且 < recall.min_monthly_sales（默认 0=关闭，低销量由 popularity 打分维度处理）
   - dish.is_available = false
   - V2+: personal_offsets 中 score_offset ≤ -2.0
   - V2+: learned_profile.blacklist 命中
4. 主蛋白多样性：3 天内吃过的 main_ingredient_type ∈ {红肉/白肉/海鲜/豆制品} 的菜剔除
5. 组合策略（数量上限由 profile.recall.* 显式注入，D-040）：
   - 路线 A: is_complete_meal=true 的单菜 + 可选 1 道蔬菜
   - 路线 B: n_p 蛋白 × n_v 蔬菜 × n_c 主食
       其中 n_p ∈ [1, max_protein_per_combo=2], n_v ∈ [1, max_veg_per_combo=2],
            n_c ∈ [0, max_carb_per_combo=1], 且 n_p+n_v+n_c ∈ [1, max_dishes_per_combo=4]
   - 各池按 monthly_sales 降序取 [:6/:5/:3] 做枝剪, 防笛卡尔爆炸
   - 单餐厅最多保留 per_restaurant_max（默认 20）个 combo, 多样性留给后续排序
6. 弱约束三件套校验（D-023，组合级，不达标的整组淘汰）：
   - 至少含 1 道 vegetable_ratio_estimate ≥ 0.6 的菜
   - 总 protein_grams_estimate ≥ profile.plate_rule.min_protein_g
7. combo 总价硬过滤: 超 price_range.hard_max_{lunch,dinner} 的整组 ban
   （仅当 recall(meal_type=...) 传入 meal_type 时生效；V1/V2/refine 主入口都传）
8. 输出未排序 combos 池, 交给 score.py 排序
```

`hard_filter()` 返回 `(kept, dropped)` 元组，dropped 每项含 `reason` 字段, 便于
[`debug_recommend`](../chisha/debug_recommend.py) 调试台直接展示丢弃明细，避免 trace 与生产逻辑漂移。

#### 打分（公式）

V1 打分（无个性化项）：

```
combo_score =
    vegetable_floor_pass     × 1.0    # 二值，达标拿 1 分
  + protein_floor_pass       × 1.0    # 二值，达标拿 1 分
  + low_oil_score            × 0.8    # 越低越好，prefer_oil_level_at_most 之上线性扣分
  + popularity_score         × 0.4    # log(monthly_sales) 归一
  + cuisine_preference       × 0.5    # liked +1 / disliked -1 / 其他 0
  + variety_bonus            × 0.3    # 主料/烹饪方式与最近 3 天不同
```

V2 打分（[D-033](docs/DECISIONS.md#d-033) 启用，~12 维）：

```
combo_score (V2) =
    上面所有 V1 项
  # 5 个新字段（D-032 v3 prompt 重打后才有）
  + carb_quality_score       × 0.6    # grain_type ∈ {全麦,糙米,燕麦} +/，{白米,精制面} -
  - processed_meat_penalty   × 1.0    # 任何 dish.processed_meat_flag=true 直接扣
  - sweet_sauce_penalty      × 0.7    # sweet_sauce_level=high 扣分
  + soup_or_broth_bonus      × 0.5    # 至少 1 道 soup_or_broth_flag=true
  + dish_role_match_bonus    × 0.4    # combo dish_role 结构合理（主菜+配菜+主食）
  # 履约维度（D-041 双层: hard_max_* 召回 ban / prefer_max_* 这里软扣）
  - distance_penalty         × 0.3    # 超 prefer_distance_m 线性 (用户不卡距离, 默认 0)
  - eta_penalty              × 0.4    # 超 prefer_max_eta_min 线性
  - price_penalty            × 0.5    # 超 price_range.prefer_max_{lunch,dinner} 线性
  # taste_description 进决策（不再只进 reason）
  + taste_match_bonus        × 0.6    # LLM 反馈解析员推断的 boost
  - taste_violation_penalty  × 0.6    # 命中 taste_description 的负向（如"不要甜口"）
  # Context 注入 (D-034)
  + context_boost            × 0.4    # daily_mood / last_meal / last_feedback 软调权
```

V2.2+ 打分（learned_profile 起来后, 暂未实现）：

```
combo_score (V2.2+) =
    上面所有 V2 项
  + personal_offset_sum      × 1.0    # 来自 (cuisine,cooking,ingredient) 维度聚合
  + learned_top_pref_bonus   × 0.6    # 命中 learned_profile.top_preferences 维度
  - learned_bottom_pref_pen  × 0.6    # 命中 bottom_preferences 维度
```

权重在 `profile.yaml.scoring_weights`，用户可改。

#### V1 精排：取打分 top 3 + LLM 单条写 reason

**V1**：直接取打分 top 3，**LLM 仅为每条单独写 reason_one_line**（输入 profile + 单条 combo，输出一句话）。
- 决策见 [D-024](docs/DECISIONS.md#d-024)
- 成本：3 次 LLM 调用 × ≤ 200 token = 单次推荐 < ¥0.05

#### V2.x 精排：LLM rerank top 60 → 5 (3 exploit + 2 explore)

V2 启用 LLM 精排（[D-035](docs/DECISIONS.md#d-035) 初版 / [D-046](docs/DECISIONS.md#d-046) prompt+payload 重构 / [D-047](docs/DECISIONS.md#d-047) tool_use forced schema 重构）。输入：
- ContextSnapshot (D-034: 餐期 / zone / last_meal / recent_3d / last_feedback / daily_mood / refine_input)
- profile.taste_description 自然语言
- 打分后 top 60 candidates (D-046: 30 → 60, D-047 矩阵实测验证 top31-60 真带来多样性增量)
- 最近 3 天 meal_log 摘要

prompt 拆 system / user (D-046):
- `prompts/rerank_system.md`: 角色 + 任务原则 + 硬约束 + reason few-shot. D-047 删了输出格式段 (~22 行), 因为 schema 由 tool 自带.
- user message: 由 `chisha.rerank.build_user_message()` 拼成紧凑文本, 每菜一行 `菜名｜main·烹·油N[·辣N·甜N·汤N·processed]｜role=X[·grain=Y]｜价`, 默认值省略.

输出 (D-047): **tool_use forced schema** 替代 D-046 的 prompt 约束 + json_mode + regex 提取. tool name `select_top_candidates`, schema 严格定义 5 个 candidate 字段类型/上下界. 每条 candidate 含 `rank / is_explore / combo_index / fit_score / taste_match / risk_flags / one_line_reason`. `health_flags` 由 [`rerank.py:_compute_health_flags`](../chisha/rerank.py) 在拿到 LLM 输出后**规则后处理**补齐 (D-046, LLM 不算确定性可计算的字段).

5 个候选 = 3 exploit (fit_score 排) + 2 explore (打分中段、最近未吃过、未尝试菜系/做法)，命中 [D-015](docs/DECISIONS.md#d-015)。refine 时 explore_count=0 (D-015)。

LLM 调用走 [chisha/llm_client.py](../chisha/llm_client.py) `call_text` 路由层 ([D-047](docs/DECISIONS.md#d-047))。三 provider 实现在 [`chisha/llm_providers/`](../chisha/llm_providers/)：`anthropic_api` (ANTHROPIC_API_KEY 直连, 默认 `claude-sonnet-4-6`) / `openrouter` (OPENROUTER_API_KEY, 默认 `anthropic/claude-opus-4.7`) / `claude_code_cli` (subprocess 调 `claude -p` 复用本机订阅额度, 不支持 tool_use 强制 schema)。选择策略：`CHISHA_LLM_PROVIDER` env > `profile.yaml.llm.provider` 显式 > auto-detect (顺序: ANTHROPIC_API_KEY > Claude Code 订阅 > OPENROUTER_API_KEY)。

温度 0.0, max_tokens 2048. `cache_system=True` 在 OR 路径也真生效 (D-047 V5 实测 cached=3748 tokens, 省 23%). OR provider 锁 `Anthropic` (allow_fallbacks=False, **不加 require_parameters** 避免触发新模型 + tools 组合的 OR 路由 404). 失败兜底: 走 `_run_llm_rerank` 共享 helper 的 fallback 分支, 退化到打分 top n + 规则 reason.

调用层强约束 (D-047 Codex BLOCKER): `_run_llm_rerank` 必断言 `stop_reason ∈ {tool_use, tool_calls}` 且 `tool_name == "select_top_candidates"` 才认为成功, 否则视作 fallback. **绝不启用 extended thinking** — 官方明确 forced tool_choice + thinking 不兼容.

兜底机制：LLM rerank 输出后 [`chisha/rerank.py:_enforce_brand_unique`](../chisha/rerank.py) 强制 brand 去重 (D-045: 与 L2 apply_caps brand 层语义对齐)。

成本估算 (D-047 实测): opus-4.7 单次 ~$0.085 (cache 命中后 ~$0.07), 200 次/月 ≈ $14-18. `chisha.rerank.L3_INPUT_TOP_K` 单一常量控制 N, `_DEFAULT_RERANK_MODEL` 控制默认模型, 调整无需散改多处.

> **后续 L3 精排改动必读**: [docs/L3_RERANK_REDESIGN.md](docs/L3_RERANK_REDESIGN.md) — 完整方案 + V1-V5 实测数据 + Codex review 强制条件清单.

### 5.7 输出 JSON schema

```json
{
  "session_id": "20260510_lunch_a3f7",
  "meal_type": "lunch",
  "round": 1,
  "candidates": [
    {
      "rank": 1,
      "is_explore": false,
      "summary": "潮汕牛肉粿条 + 蒜蓉空心菜",
      "restaurant": {
        "id": "r_007",
        "name": "潮汕牛肉甘草水",
        "distance_m": 600,
        "eta_min": 30
      },
      "dishes": [
        {
          "dish_id": "d_00789",
          "canonical_name": "潮汕牛肉粿条",
          "price": 32,
          "main_ingredient_type": "红肉",
          "oil_level": 2
        }
      ],
      "total_price": 42,
      "ratio": {"vegetable": 0.55, "protein": 0.25, "carb": 0.20},
      "estimated_total_oil": 2.0,
      "reason_one_line": "高蛋白低油，本周还没吃过潮汕菜"
    }
  ]
}
```

**Skill 不做渲染**——返回 JSON 给上层 Agent，Agent 自己拼 markdown / 卡片。

---

## 6. V2+ 扩展规划

按优先级：

### V2.0 + V2.1 合并（[D-033](docs/DECISIONS.md#d-033)）：数据层升级 + 反馈骨架 + LLM 精排 + refine

合并理由：V1 推荐质量上限被 schema 缺字段 + taste_description 不进决策 + 缺反馈回环 卡死；继续等 V1 北极星不会自动好转。本轮一锅做（[D-033](docs/DECISIONS.md#d-033)）。

**A. 数据层升级（前置）**：
- v3 prompt 补 5 字段：`dish_role` / `processed_meat_flag` / `sweet_sauce_level` / `soup_or_broth_flag` / `grain_type`（[D-032](docs/DECISIONS.md#d-032)）
- 全量重打两个 zone（shenzhen-bay 11k + home 2.1k），按既有 batch=50 + 并发 16 spawn 规则
- 50 条人工抽查准确率 ≥ 80% 才算通过

**B. score 升级（V1 6 维 → V2 ~12 维）**：
- `taste_description` 进决策（不只 reason），LLM 反馈解析员推断 boost/penalty
- 5 新字段进打分：carb_quality / processed_meat / sweet_sauce / soup_or_broth / dish_role 匹配
- 距离 / eta / 价格 / 起送 / 配送费 进打分（已有数据未用）
- 见 §5.6 V2 公式

**C. LLM 精排（[D-035](docs/DECISIONS.md#d-035)）**：
- 取打分 top 30 + Context（D-034）+ taste_description + 最近 3 天 + last_feedback → 输出强制结构化 JSON
- 5 个候选 = 3 exploit + 2 explore（[D-015](docs/DECISIONS.md#d-015)）
- refine 时 explore_count=0
- 失败兜底：退化到打分 top 3 + 规则 reason

**D. 反馈采集骨架**：
- 即时 chip + 自由文本：accept chip / reject chip 列表（太油 / 太辣 / 太贵 / 想喝汤 / 主食太多 / 送慢 / 漏汤 等，受控词表见 [chisha/feedback.py](../chisha/feedback.py) `CHIP_VOCAB`）
- 餐后被动追问：下次饭点 trigger 卡片首行问"上顿感觉？1 句话即可"，跳过不强求
- 反馈解析员：自然语言 → 结构化 chip 映射（[chisha/feedback.py](../chisha/feedback.py)，[prompts/parse_feedback.md](../prompts/parse_feedback.md)）
- 数据落 meal_log.jsonl，含 `context_at_recommend` + `chips` + rating + want_again

**E. Context 注入层（[D-034](docs/DECISIONS.md#d-034)）**：
- 见 [chisha/context.py](../chisha/context.py) ContextSnapshot
- daily_mood 由 OpenClaw 每日首次饭点 trigger 时问 1 句写入 session 状态
- 进 L3 软调权 + L4 LLM rerank context

**F. Refine 多轮**：
- `refine_recommendation` API
- session 状态管理（24h TTL）
- 用户对推荐表态后（reject + 自然语言），结构化 constraint → 重跑 L3 + L4，不做 explore
- LLM 自行判断重精排 vs 重召回

**G. 验收**：
- ~~8-12 个黄金 case + `scripts/eval_recommend.py` 离线对比 V1 vs V2~~ — D-049 后 V1 砍除, 脚本一并删, golden case 仍保留作未来调试 case 库
- 自用 1-2 周采集反馈到 30+ 条触发 V2.2

**本轮明确不做**：personal_offsets 实时写入 / learned_profile 聚合（V2.2）/ combo planner 重写 / profile.yaml 大改 schema / 跨店 combo / 健康疲劳"cheat 配额"机制 / Post-meal 主动推送（改成下次饭点被动）.

### V2.2：learned_profile 统计聚合（不是 LLM 蒸馏）

- 每周自动加工脚本
- 从 meal_log **统计聚合**到 (cuisine, cooking_method, main_ingredient) 维度（[D-026](docs/DECISIONS.md#d-026)）
- 数据加权策略（有 feedback 1.0 / 接受未 feedback 0.3 / 拒绝 0.5 负向 / 自登 0.2，[D-013](docs/DECISIONS.md#d-013)）
- 输出 top_preferences / bottom_preferences / blacklist / summary_for_llm
- 精排 prompt 加入 learned_profile.summary_for_llm

### V2.3：Claude Code 接入 + MCP 化

- 写 SKILL.md（Claude Code 接入入口，用户主动 query 场景）
- 打包 MCP Server（开放给其他长程 Agent）
- 写 INSTALL.md（OpenClaw / HappyClaw / Claude Code 三种接入说明）
- LLM 抽象（OpenAI / Ollama adapter）
- 打分权重外部化到 config.yaml

### V2.4：数据层按工区拆包

- L1 数据按工区拆 `chisha-data-shenzhen-keji` / `chisha-data-beijing-zgc` 等子包（[D-002](docs/DECISIONS.md#d-002) 修订）
- 数据更新机制（订阅 chisha-collector 的 15 天更新，[D-027](docs/DECISIONS.md#d-027)）
- README / examples / 文档站
- 发 GitHub，给同事试用

---

## 7. 设计决策速查

> 这里只列**决策结论**一行式索引。每条决策的背景、考虑的方案、判断标准、触发重审条件，
> 完整记录在 [docs/DECISIONS.md](docs/DECISIONS.md)。
> 想推翻某个决策前，**必须先读 DECISIONS 里对应条目**。
>
> 工程实施类条目（D-042 / D-045 / D-046 / D-046.1 / D-047）的实现细节、batch 数、bug 排查、参数微调记录在 [docs/IMPLEMENTATION_LOG.md](docs/IMPLEMENTATION_LOG.md)；DECISIONS 仅保留 stub 指针。

| # | 速查 | 完整条目 |
|---|---|---|
| 1 | V1 走开源 Skill 而非 SaaS | D-001 |
| 2 | L1 数据 + L2 推荐 独立分发（V2.4 按工区拆子包） | D-002 |
| 3 | V1 不做 CLI 包装，import 调用 | D-003 |
| 4 | V1 不做反馈系统，纸笔记 | D-004 |
| 5 | 召回 + 打分 + 精排三阶段 | D-005 |
| 6 | 召回宽过滤，软约束进打分 | D-006 |
| 7 | 召回 100，首推 V1=3 / V2=5 | D-007 |
| 8 | 打标必看价格 | D-008 |
| 9 | 打标 temperature=0、批 30-50 条 | D-009 |
| 10 | 反馈拆"好吃度"+"整体满意"两星级 | D-010 |
| 11 | 自由备注 escape hatch | D-011 |
| 12 | learned_profile 加工层（V2.2 改统计聚合，见 D-026） | D-012 |
| 13 | 未反馈数据混合权重 | D-013 |
| 14 | taste_description 用自然语言 | D-014 |
| 15 | 探索机制默认启用（5 中 1-2 explore）| D-015 |
| 16 | V1 不做训练日感知 | D-016 |
| 17 | 不做 Web URL 渲染层 | D-017 |
| 18 | ~~V1 接入 Claude Code 而非 OpenClaw~~（**superseded**，见 D-022） | D-018 |
| 19 | V1 阶段不发 PyPI | D-019 |
| 20 | 文档体系四份分立 | D-020 |
| 21 | 双名策略（今天吃点啥 + chisha） | D-021 |
| **22** | **V1 接入 OpenClaw + 飞书卡片，主动推送** | **D-022** |
| **23** | **餐盘策略改弱约束（控油 + 蔬菜下限 + 蛋白下限）** | **D-023** |
| **24** | **V1 精排 = 打分 top 3 + LLM 只写 reason** | **D-024** |
| **25** | **个性化粒度从"店::菜"改 (cuisine, cooking, ingredient)** | **D-025** |
| **26** | **learned_profile 改统计聚合，删 LLM 蒸馏 insights** | **D-026** |
| **27** | **数据来源边界：sister project chisha-collector 维护** | **D-027** |
| **28** | **北极星指标修正（用连续采纳率替代决策时间）** | **D-028** |
| **29** | **profile.spicy_tolerance 改整数 0-3** | **D-029** |
| 30 | 数据链路重构方向：单仓三子模块（V1.5） | D-030 |
| 33 | V2.0+V2.1 合并触发：Context + LLM 精排 + refine + session | D-033 |
| 34 | ContextSnapshot 注入层 | D-034 |
| 35 | LLM 精排 top30→5（3 exploit + 2 explore） | D-035 |
| 36 | Dual-model audit 共创（Opus+Codex） | D-036 |
| 37 | 生产打标默认 deepseek-v4-flash | D-037 |
| 38 | LLM 抽象 Phase 1（provider auto-detect）+ 商家去重兜底 | D-038 |
| 39 | 推荐调试台（FastAPI on 8765） | D-039 |
| 40 | combo 生成参数化（max_protein/veg/carb 由 profile 注入） | D-040 |
| 41 | 召回硬过滤双层架构（hard_max_* / prefer_max_*） | D-041 |
| **42** | **L2 排序后 cap_per_restaurant（防同店霸榜）** | **D-042** |
| **43** | **L2 打分体系重设计 + 三层 cap + 反馈闭环 P3**（必读 [`docs/RECOMMEND_PRINCIPLES.md`](docs/RECOMMEND_PRINCIPLES.md)） | **D-043** |
| **44** | **profile.yaml 真实化 + 口味偏好层与健康目标层分离** | **D-044** |
| **45** | **L2 cap 增加 brand 层（连锁去重）** | **D-045** |
| **46** | **L3 精排 prompt + payload 重构（top60 + system/user 拆分 + 紧凑化 + health_flags 规则后处理）** | **D-046** |
| **47** | **L3 精排重构（tool_use forced schema + opus 默认 + cache_control + helper 抽出消灭双份代码）** | **D-047** |
| **48** | **L3 双路径收口（CLI no-tool 分流 + provider 配置错 hard-fail + trace 结构化三态）** | **D-048** |
| **49** | **L2 输出契约改 head-only**（apply_caps 不再保留 tail 段） | **D-049** |
| **44.1** | **wetness 退出 baseline 权重（汤水偏好作 session mood, 不做 trait）** | **D-044.1** |

| **49** | **V1 主交互改本机 Web SPA，飞书降级为 V1.5 推送通道**（partial supersedes D-022） | **D-051** |
| **50** | **Accept 信号去 deeplink，改持久 inline 锁定 + 复制店名** | **D-052** |
| **51** | **Refine 历史从底部列表升级为顶部面包屑 + smooth-scroll；输入框置顶、chip-fallback** | **D-053** |
| **52** | **Skip-meal escape hatch（6 reason chip + 兜底跳过，新增 `POST /api/skip`）** | **D-054** |
| **53** | **同 session 抑制 unfed banner（避免"还没吃完"被催反馈）** | **D-055** |
| 56~68 | V1.1 反馈系统（NavBar tab / inbox / snooze / E 头部 gut + 4 维 calibration / append-only timeline 等 13 条）| D-056~D-068 |
| 69 | FastAPI 后端 13 端点联调 (V1+V1.1) | D-069 IMPL_LOG |
| 70 | 产品定位收敛到「原则派点餐助手」+ 三层信号模型 (L0 方法论 / L1 长期反馈 / L2 当下 session) | D-070 |
| 71 | 砍 mood picker + want_soup 关键词识别 | D-071 |
| 72 | methodology spec 抽象 + L2 trace baseline 守门 | D-072 / D-072.1 |
| **73** | **L1 长期反馈层重构 — 砍伪 L1 + LLM 抽取**（supersedes D-043 P3 反馈闭环）| **D-073** |
| **74** | **Sandbox Time-Travel 模式**（虚拟时钟 + 数据落盘根隔离 + L1 异步抽取 + 6 sandbox 端点 + 前端 SandboxBar） | **D-074** |

---

## 8. 现在开始动手做什么

按顺序：

1. **从 chisha-collector 拉数据**到 `data/shenzhen-keji/restaurants.json` + `dishes_raw.json`
2. **写打标 prompt**（基于 §5.5）
3. **写打标脚本** `scripts/tag_dishes.py`，跑一遍
4. **抽查 50 条**，准确率 ≥ 80% 通过
5. **手填 profile.yaml**（基于 §5.3，含弱约束三件套 + spicy_tolerance 整数）
6. **实现召回** `chisha/recall.py`（含弱约束三件套校验、组合策略）
7. **抽查 100 个候选**，看是否合理
8. **实现打分** `chisha/score.py`（V1 无个性化项）
9. ~~**实现"取 top 3 + 写 reason"** `chisha/api.py` + `chisha/reason.py`（V1 不做 LLM 精排）~~ — D-049 后实际走 V2 主路径 (L3 LLM 精排 top60→5), `chisha/reason.py` 已删
10. **空跑 5 次推荐**，看输出质量
11. ~~接入 OpenClaw + 飞书卡片~~ → **改装 Web SPA 用户视图**：[`apps/web/`](apps/web/) 已就绪（D-051~D-055），下一步 FastAPI 后端装 V1 `/api/*` 端点跟 SPA 拉通（契约见 [`docs/api.md`](docs/api.md)）
12. ~~配 cron~~ → macOS launchd 本机定时拉起 web 服务（工作日 11:00 / 17:30），自用一周，UI 内的 accept/skip 埋点替代纸笔

V1.5 再回头接飞书做"推送 + deeplink 跳 Web"轻量入口。

跑通后回来看 §6，规划 V2.0 反馈闭环。

祝开发顺利。

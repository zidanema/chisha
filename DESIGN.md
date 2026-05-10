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

#### 里程碑 3：接入 OpenClaw + 飞书卡片（约 1-2 周）

**目标**：OpenClaw 在 11:25 / 18:00 主动推飞书卡片，自己用一周。

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
│   ├── reason.py                # LLM 写一句话理由（V1 LLM 只在这）
│   └── llm_client.py            # LLM 抽象（V1 只支持 Anthropic）
│
├── integrations/
│   └── openclaw/                # V1 接入 OpenClaw + 飞书
│       ├── skill.py             # skill 入口
│       └── feishu_card.py       # 飞书卡片渲染
│
├── scripts/
│   ├── tag_dishes.py            # 打标脚本
│   └── inspect_candidates.py    # 抽查工具
│
├── prompts/
│   ├── tag_dishes.md            # 打标 prompt
│   └── reason_one_line.md       # 写理由 prompt（V1 唯一精排 LLM 用途）
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

### 3.6 V1 精排：打分 top 3 + LLM 写理由（不做 LLM 精排）

V1 不让 LLM "选 3 个"。流程是：

```
召回 100 → 打分排序 → 取 top 3 → LLM 为每条单独写 reason_one_line
```

**V1 LLM 唯一用途**：写理由 prompt（`prompts/reason_one_line.md`）：

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

`dishes_tagged.json`：

```json
{
  "dish_id": "d_001_007",
  "restaurant_id": "r_001",
  "raw_name": "水煮牛肉(中辣) 大份",
  "canonical_name": "水煮牛肉",
  "price": 48,
  "monthly_sales": 245,
  "cuisine": "川菜",
  "nutrition_profile": {
    "main_ingredient_type": "红肉",
    "cooking_method": "煮",
    "oil_level": 4,
    "protein_grams_estimate": 38,
    "vegetable_ratio_estimate": 0.2,
    "is_complete_meal": false,
    "spicy_level": 2,
    "tags": ["高蛋白", "重口味", "下饭"]
  },
  "metadata": {
    "tagged_at": "2026-04-15T03:00:00",
    "tag_version": "v1",
    "is_available": true
  }
}
```

字段定义：

- `cuisine`: 菜系大分类（湘菜/川菜/粤菜/潮汕/东北/西北/江浙/鲁菜/日式/韩式/西式/东南亚/快餐/小吃/汤粥/其他）—— D-025 个性化粒度需要
- `main_ingredient_type`: 红肉/白肉/海鲜/蛋/豆制品/纯素/主食/汤/其他
- `cooking_method`: 蒸/煮/烤/炒/炖/油炸/凉拌/生/煎
- `oil_level`: 1-5（1 = 白灼清蒸，5 = 油炸爆炒）
- `vegetable_ratio_estimate`: 0.0-1.0（看体积比）
- `spicy_level`: 0-3
- `is_complete_meal`: 一份单点能否接近达标（翘脚牛肉=true，蒜蓉空心菜=false）

`restaurants.json` 的 `category` 字段由 `dishes_tagged.cuisine` 做 majority vote 后回填（采集器经常拿不到 restaurant 级 category）。

### 5.3 profile.yaml

```yaml
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
  "feedback": {
    "rating_taste": 4,
    "rating_satisfaction": 3,
    "oil_tag": "偏油",
    "portion_tag": null,
    "delivery_tag": null,
    "want_again": false,
    "note": "牛肉有点柴",
    "submitted_at": "2026-05-10T14:30:00"
  }
}
```

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

```
1. 候选商家：profile.office_zone 内
2. 硬过滤（非协商）：
   - profile.preferences.avoid_dishes（菜名匹配）
   - dish.spicy_level > profile.spicy_tolerance（整数比较）
   - dish.monthly_sales < 10 且无评分
   - dish.is_available = false
   - dish.oil_level > profile.plate_rule.hard_max_oil_level（V1 默认 5，等于不卡）
   - V2+: personal_offsets 中 score_offset ≤ -2.0
   - V2+: learned_profile.blacklist 命中
3. 多样性过滤（基于 meal_log，V1 第一周空 log 时无效，是已知现象）：
   - 7 天内吃过的 restaurant_id
   - 3 天内吃过的 main_ingredient_type
4. 组合策略（每家餐厅最多产 3 个组合，避免笛卡尔积爆炸）：
   - 路线 A：is_complete_meal=true 的单菜 + 必要时补 1 道蔬菜
   - 路线 B：同 restaurant 内 [蛋白] × [蔬菜（vegetable_ratio_estimate ≥ 0.6）] × [主食 0/1]
5. 弱约束三件套校验（D-023，组合级，不达标的整组淘汰）：
   - 至少含 1 道 vegetable_ratio_estimate ≥ 0.6 的菜
   - 总 protein_grams_estimate ≥ profile.plate_rule.min_protein_g
6. 按打分排序，截取 top 100
```

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

V2+ 打分（叠加个性化）：

```
combo_score (V2+) =
    上面所有 V1 项
  + personal_offset_sum      × 1.0    # 来自 (cuisine,cooking,ingredient) 维度聚合
  + learned_top_pref_bonus   × 0.6    # 命中 learned_profile.top_preferences 维度
  - learned_bottom_pref_pen  × 0.6    # 命中 bottom_preferences 维度
  + diversity_bonus          × 0.3
```

权重在 `config.yaml`，用户可改。

#### V1 精排：取 top 3，不让 LLM 选

**V1**：直接取打分 top 3，**LLM 仅为每条单独写 reason_one_line**（输入 profile + 单条 combo，输出一句话）。
- 决策见 [D-024](docs/DECISIONS.md#d-024)
- 成本：3 次 LLM 调用 × ≤ 200 token = 单次推荐 < ¥0.05

**V2.x**：开 LLM 精排。输入 profile + learned_profile.summary_for_llm + 100 候选 + accumulated_constraints → 5 个推荐 + 1-2 个 explore + refine 收敛。

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

### V2.0：反馈闭环（V1 自用一周后启动）

- `submit_feedback` API + personal_offsets 写入（粒度 = `cuisine::cooking::ingredient`，[D-025](docs/DECISIONS.md#d-025)）
- meal_log 完整记录（dish 字段补 cuisine + cooking_method）
- accept_recommendation / log_meal API
- 飞书反馈卡片字段：rating_taste + rating_satisfaction + tags + note
- 反馈写入规则（rating 5★ → score_offset += 1.0 等）

### V2.1：对话收敛 + 探索 + LLM 精排起步

- `refine_recommendation` API
- LLM 精排（取代 V1 的"打分 top 3"），让 LLM 在 100 候选里挑 5 个
- 5 个候选 + 1-2 个 explore 标记
- session 状态管理（24h TTL）
- LLM 自行判断重精排 vs 重召回

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

> 这里只列**决策结论**。每条决策的背景、考虑的方案、判断标准、触发重审条件，
> 完整记录在 [docs/DECISIONS.md](docs/DECISIONS.md)。
> 想推翻某个决策前，**必须先读 DECISIONS 里对应条目**。

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
9. **实现"取 top 3 + 写 reason"** `chisha/api.py` + `chisha/reason.py`（V1 不做 LLM 精排）
10. **空跑 5 次推荐**，看输出质量
11. **接入 OpenClaw**：写 `integrations/openclaw/skill.py` + `feishu_card.py`
12. **配 cron** 工作日 11:25 / 18:00 触发，自用一周，纸笔记录每次推荐质量

跑通后回来看 §6，规划 V2.0 反馈闭环。

祝开发顺利。

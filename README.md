# 今天吃点啥 · chisha

> 让你的 Agent 帮你决定今天吃啥，吃得控油 + 有蔬菜 + 有蛋白。
> 一个能接进 OpenClaw / HappyClaw / Claude Code / 任何 Agent 的开源 Skill。

---

## 这是什么

我每天中午晚上点外卖要花 10-20 分钟纠结。同时在做减脂增肌，想吃得健康（控油 + 有蔬菜 + 有蛋白）。

两件事合起来就是**点餐决策疲劳**。

`chisha` 把它系统性地解决：每顿饭让你的长程 Agent 在 11:25 / 18:00 主动推飞书卡片，给 3 个组合，30 秒选一个就走。

> **餐盘策略说明**：不追求严格 1/2-1/4-1/4 比例（中式外卖现实下不可达），改弱约束三件套：控油 + 至少 1 道蔬菜 + 蛋白下限。详见 [DECISIONS D-023](docs/DECISIONS.md#d-023)。

详细动机见 [docs/PRD.md](docs/PRD.md)。

---

## 命名

- **项目名（对人）**：今天吃点啥
- **代码名（对机器）**：`chisha`
- **未来 pip 包**：`chisha`（推荐引擎） + `chisha-data-{office_zone}`（数据按工区拆子包，如 `chisha-data-shenzhen-keji`）
- **sister project**：`chisha-collector`（数据采集 / 清洗 / 打标 / 保鲜，独立维护，[D-027](docs/DECISIONS.md#d-027)）

文档里"今天吃点啥"和 `chisha` 会交替出现，意思一样。

---

## 项目状态

**V1 in flight** —— 数据接入 + 推荐（召回+打分，不上 LLM 精排）+ OpenClaw 飞书卡片接入 + 自用一周。

详细路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)。

---

## 文档体系

| 文档 | 内容 | 何时读 |
|---|---|---|
| [docs/PRD.md](docs/PRD.md) | 产品需求 · 为什么做、做给谁、做成什么样 | 第一份读，建立产品定位 |
| [DESIGN.md](DESIGN.md) | 设计与实现 · 架构、schema、API、prompt、避坑 | 实现时随时查 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 决策日志 · 关键决策为什么这样而不是那样 | 想推翻某个设计前先看 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 路线图 · V1/V2/V3 边界，已砍清单 | 想加新功能前先看 |

**首次接触请按顺序读：PRD → ROADMAP → DESIGN → DECISIONS**。

---

## 当前你应该做什么

如果你是 Claude Code / OpenClaw / 实现者，按以下顺序：

1. 读 [docs/PRD.md](docs/PRD.md) —— 理解为什么做这个、服务谁、北极星是什么（注意 §2.2 弱约束餐盘策略 + §9 数据来源边界）
2. 读 [docs/ROADMAP.md](docs/ROADMAP.md) —— 知道当前在 V1 阶段，V1 必做和不做的清单
3. 读 [DESIGN.md](DESIGN.md) §3 V1 最小闭环 —— 明确开发主线（V1 接 OpenClaw + 飞书卡片，**不接 Claude Code**）
4. 读 [DESIGN.md](DESIGN.md) §4 实操避坑指南 —— 提前规避常见坑
5. 按 [DESIGN.md](DESIGN.md) §8 12 步执行清单动手

**实现某个功能前，先确认它在 ROADMAP 的当前版本里**。如果发现不在，但想做，先去 DECISIONS 加一条新决策说明为什么要把它提前。

**关于 V1 接入**：原 D-018 选 Claude Code 已被 [D-022](docs/DECISIONS.md#d-022) 翻案——CLI 不能主动推送，与"11:25 主动推卡片"承诺不匹配。V1 直接接 OpenClaw + 飞书。

---

## 文档维护规则

为保证上下文不漂移：

1. **新增决策必须进 DECISIONS.md**，按模板格式记录
2. **路线变更必须更新 ROADMAP.md**，已砍的功能加进已砍清单
3. **PRD 极少改动**，定位变化才改（每次改要在 DECISIONS 加一条说明）
4. **DESIGN 每个大版本一份**，旧版归档到 docs/archive/，不删

---

## 项目结构

```
chisha/
├── README.md                  # 你在看
├── DESIGN.md                  # 当前版本设计与实现
├── profile.yaml               # 用户偏好（弱约束三件套 + taste + meal_trigger_time）
├── docs/
│   ├── PRD.md                 # 产品需求
│   ├── DECISIONS.md           # 决策日志（含 D-022 ~ D-029 V1 翻案）
│   ├── ROADMAP.md             # 路线图
│   └── archive/               # 旧版设计文档归档
├── data/
│   └── shenzhen-keji/         # 按工区分目录（V2.4 拆 chisha-data-{zone} 子包）
│       ├── restaurants.json
│       ├── dishes_raw.json
│       └── dishes_tagged.json
├── chisha/                    # L2 推荐层代码（Python 包）
│   ├── __init__.py
│   ├── api.py                 # recommend_meal 主入口
│   ├── recall.py              # 召回 + 弱约束三件套校验
│   ├── score.py               # 打分（V1 无个性化项）
│   ├── reason.py              # LLM 写一句话理由（V1 LLM 唯一用途）
│   └── llm_client.py
├── integrations/
│   └── openclaw/              # V1 接入 OpenClaw + 飞书
│       ├── skill.py
│       └── feishu_card.py
├── scripts/                   # 数据维护脚本（打标等）
├── prompts/                   # LLM prompt 模板
└── tests/
```

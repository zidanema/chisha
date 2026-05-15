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
- **未来 pip 包**：`chisha`（推荐引擎） + `chisha-data-{office_zone}`（数据按工区拆子包，如 `chisha-data-shenzhen-bay`）
- **sister project**：`chisha-collector`（数据采集 / 清洗 / 打标 / 保鲜，独立维护，[D-027](docs/DECISIONS.md#d-027)）

文档里"今天吃点啥"和 `chisha` 会交替出现，意思一样。

---

## 项目状态

**V1 in flight** —— 数据接入 + 推荐（召回 + L2 打分 + L3 LLM 精排, D-033/D-035/D-046/D-047）+ OpenClaw 飞书卡片接入 + 自用一周。

> 注: D-049 (2026-05-14) 砍掉了 D-024 的"V1 简化路径 (打分 top 3 + LLM 写 reason)", 现在唯一链路是 L3 LLM 精排 top60→5。

详细路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)。

---

## 文档体系

| 文档 | 内容 | 何时读 |
|---|---|---|
| [docs/PRD.md](docs/PRD.md) | 产品需求 · 为什么做、做给谁、做成什么样 | 第一份读，建立产品定位 |
| [DESIGN.md](DESIGN.md) | 设计与实现 · 架构、schema、API、prompt、避坑 | 实现时随时查 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 决策日志 · 产品/架构/方法论 决策为什么这样而不是那样 | 想推翻某个设计前先看 |
| [docs/IMPLEMENTATION_LOG.md](docs/IMPLEMENTATION_LOG.md) | 工程实施日志 · prompt 改了几行、batch 数、bug 排查、参数微调 | 排查具体实现、复盘工程细节时 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 路线图 · V1/V2/V3 边界，已砍清单 | 想加新功能前先看 |
| [docs/RECOMMEND_PRINCIPLES.md](docs/RECOMMEND_PRINCIPLES.md) | 推荐系统分层原则与方法论（D-043 沉淀）| 改打分/召回/重排前**必读** |
| [docs/L3_RERANK_REDESIGN.md](docs/L3_RERANK_REDESIGN.md) | L3 精排重构方案（D-047）| 改 L3 精排前**必读** |
| [eval/dish_tagging_eval/](eval/dish_tagging_eval/) | 菜品打标评测框架（dual-model golden set 171 条 + 评测脚本）| 复评打标质量、改 prompt 前 |
| [eval/dish_tagging_model_eval_spec.md](eval/dish_tagging_model_eval_spec.md) | 评测说明（面向 PM）| 想理解评测口径与结论时 |

**首次接触请按顺序读：PRD → ROADMAP → DESIGN → DECISIONS**。
改推荐链路前请额外读 RECOMMEND_PRINCIPLES；改 L3 精排前读 L3_RERANK_REDESIGN；复盘工程细节看 IMPLEMENTATION_LOG。

---

## 当前进度（V1 spike 已完成代码侧，等真实 LLM 打标 + OpenClaw 接入）

### ✅ 已完成（代码侧）

- 数据层 loader: `chisha/loader.py` (raw → §5.2 schema, brand 后缀剥离)
- 召回: `chisha/recall.py` (硬过滤 + 多样性 + 弱约束三件套校验 + 组合策略)
- 打分: `chisha/score.py` (V1 公式 + 品牌/菜系多样性 top 3)
- 精排: `chisha/api.py` 主入口 + `chisha/rerank.py` L3 LLM 精排 (D-033/D-046/D-047)
- 接入: `integrations/openclaw/` (skill + 飞书卡片渲染)
- 工具: `scripts/tag_dishes.py` (LLM 打标), `mock_tagged.py` (规则 mock), `dry_run.py`, `inspect_candidates.py`
- 数据: `data/shenzhen-bay/` (office, 139 家 7256 菜) + `data/home/` (home, 38 家 2117 菜)
- 用 mock 数据 dry_run 5 次：lunch/dinner 各推 3 个组合，100% 蔬菜+蛋白达标，跨品牌

### ⏳ 你接下来要做

#### 1. 真实 LLM 打标（替换 mock）

> ⚠️ V3 生产打标走 `scripts/tag_via_api.py`（OpenRouter）, 默认模型 `deepseek/deepseek-v4-flash` (见 [D-037](docs/DECISIONS.md#d-037), 171 条 dual-model golden 横评最优性价比)
> `scripts/tag_dishes.py` 是 Anthropic 直连旧脚本, 已停用

```bash
# .env 需有 OPENROUTER_API_KEY
# 先 spike 50 条抽查 (默认 deepseek-flash)
uv run python scripts/tag_via_api.py shenzhen-bay --limit 50
# 抽查 50 条准确率 ≥ 80% 后再跑全量
uv run python scripts/tag_via_api.py shenzhen-bay
uv run python scripts/tag_via_api.py home

# 显式覆盖模型 (例如 ceiling 准确率回归)
uv run python scripts/tag_via_api.py shenzhen-bay --limit 50 \
  --model anthropic/claude-sonnet-4.6
```

#### 2. 抽查召回 100 条（看是否合理）

```bash
uv run python -m scripts.inspect_candidates --meal lunch --limit 100
uv run python -m scripts.inspect_candidates --meal dinner --limit 100
```

#### 3. 5 次空跑 dry_run（看推荐质量）

```bash
uv run python -m scripts.dry_run --n 5 --meal both
```

#### 4. 接 OpenClaw + 飞书

```bash
# 配 chat_id
export OPENCLAW_PUSH_MODE=lark-cli
export LARK_CHAT_ID=oc_xxx

# 单次推送测试
uv run python -m integrations.openclaw.skill lunch
uv run python -m integrations.openclaw.skill dinner

# 在 OpenClaw 配 cron (见 integrations/openclaw/SKILL.md)
#   工作日 11:25 推 lunch
#   工作日 18:00 推 dinner
```

#### 5. 自用一周 + 纸笔记录

按 [ROADMAP.md V1 抽查标准](docs/ROADMAP.md)，工作日 7 日采纳率 ≥ 50% 才算 V1 通过。

### 💡 想改某个设计前先看

实现某个功能前，先确认它在 ROADMAP 的当前版本里。如果发现不在，但想做，先去 DECISIONS 加一条新决策说明为什么要把它提前。

读文档顺序：[PRD](docs/PRD.md) → [ROADMAP](docs/ROADMAP.md) → [DESIGN](DESIGN.md) §3-§4 → [DECISIONS](docs/DECISIONS.md)

---

## 文档维护规则

为保证上下文不漂移：

1. **新增决策必须先分类**：产品方向/架构/方法论/schema → `DECISIONS.md`；prompt 改 N 行/参数微调/batch 数/bug 排查 → `IMPLEMENTATION_LOG.md`
   - 判别准则：**半年后做下一次大重构时,会不会回头查这条?** 会 → DECISIONS；不会 → IMPLEMENTATION_LOG
2. **路线变更必须更新 ROADMAP.md**，已砍的功能加进已砍清单
3. **PRD 极少改动**，定位变化才改（每次改要在 DECISIONS 加一条说明）
4. **DESIGN 每个大版本一份**，旧版归档到 docs/archive/，不删
5. **每次 D-XXX 落地的 commit 后 3 项 checklist**:① 写到 DECISIONS 还是 IMPLEMENTATION_LOG?② 是否推翻了之前某条? 推翻就标 superseded 并加链接 ③ 是否需要更新 README 进度章节 / ROADMAP 当前状态?
   - 见 [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md)

---

## 项目结构

```
chisha/
├── README.md                  # 你在看
├── DESIGN.md                  # 当前版本设计与实现
├── profile.yaml               # 用户偏好（弱约束三件套 + taste + meal_trigger_time）
├── docs/
│   ├── PRD.md                 # 产品需求
│   ├── DECISIONS.md           # 决策日志（产品/架构/方法论决策）
│   ├── IMPLEMENTATION_LOG.md  # 工程实施日志（prompt / 参数 / batch / bug 细节）
│   ├── ROADMAP.md             # 路线图
│   ├── RECOMMEND_PRINCIPLES.md # 推荐分层原则（D-043 沉淀）
│   ├── L3_RERANK_REDESIGN.md  # L3 精排重构方案（D-047）
│   ├── CONTRIBUTING_DOCS.md   # 文档维护准则与每次决策 checklist
│   └── archive/               # 旧版设计文档归档
├── data/
│   └── shenzhen-bay/          # 按工区分目录（V2.4 拆 chisha-data-{zone} 子包）
│       ├── restaurants.json
│       ├── dishes_raw.json
│       └── dishes_tagged.json
├── chisha/                    # L2 推荐层代码（Python 包）
│   ├── __init__.py
│   ├── api.py                 # recommend_meal 主入口 (D-033 单一 V2 路径, D-049 后)
│   ├── recall.py              # 召回 + 硬过滤双层 + combo 灵活组合 (D-040/041)
│   ├── score.py               # 打分 V2 ~12 维
│   ├── rerank.py              # L3 LLM 精排 top60→5 (D-035/D-046/D-047)
│   ├── context.py             # ContextSnapshot 注入层 (D-034)
│   ├── refine.py              # refine 二轮 (D-033)
│   ├── llm_client.py          # provider 路由层 (D-047)
│   ├── llm_providers/         # 三 provider: anthropic_api / openrouter / claude_code_cli (D-047)
│   ├── debug_recommend.py     # 调试台用的 instrumented 管道 (D-039)
│   ├── debug_server.py        # FastAPI 调试台 server (D-039)
│   ├── long_term_prefs.py     # 反馈闭环 P3 (D-043): 反馈历史 → boost/penalty hints
│   └── static/                # 调试台前端 (debug.html / logic.html)
├── integrations/
│   └── openclaw/              # V1 接入 OpenClaw + 飞书 (cron 待装)
│       ├── skill.py
│       └── feishu_card.py
├── scripts/                   # 数据维护脚本（打标 / 召回审计等）
├── prompts/                   # LLM prompt 模板
└── tests/                     # 308 测试 (D-041 audit + D-042 cap + D-043 重设计/反馈闭环)
```

### 启调试台（D-039）

```bash
uv run python -m chisha.debug_server
# → http://127.0.0.1:8765
# 浏览器看 L1 召回 / L2 16 维打分 / L3 LLM 精排 payload / Final 5 卡片
```

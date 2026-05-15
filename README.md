# 今天吃点啥 · chisha

> 原则派点餐助手——给已经认定一套吃法、但懒得每天选店的原则派，30 秒搞定外卖决策。
> 可接进 OpenClaw / HappyClaw / Claude Code / 任何 Agent 的开源 Skill。

---

## 这是什么

定位见 [D-070](docs/DECISIONS.md#d-070-产品定位收敛到原则派点餐助手--三层信号模型-v1)：**原则派点餐助手**——服务的是已经认了一套饮食方法论（减脂控油 / 增肌高蛋白 / 糖控 / 孕期...）、痛点在**每天落地费力**的人。明确不服务"什么都行又什么都不想吃"的目标缺失型用户。

我自己是典型用户：认了哈佛餐盘弱约束（控油 + 有蔬菜 + 有蛋白），但每天点外卖还得花 10-20 分钟翻 200 家店上千道菜手动凑齐这个结构。

`chisha` 把这个执行过程系统性外包：每顿饭在 11:25 / 18:00 主动推送提醒，给 5 个组合，30 秒选一个就走。

> **V1 当前形态**（[D-051](docs/DECISIONS.md#d-051)）：本机 localhost Web SPA（用户视图 + 调试台合一），自用打磨体验。V1.5 接入飞书做推送 + deeplink 跳转。

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

**Phase 0 工程侧已收尾**（2026-05-15）—— 「原则派点餐执行外包」定位收敛（[D-070](docs/DECISIONS.md#d-070-产品定位收敛到原则派点餐助手--三层信号模型-v1)）+ 砍 mood picker（D-071, 已 superseded）+ methodology spec 抽象（[D-072](docs/DECISIONS.md#d-072-methodology-spec-抽象-放-phase-0-收尾-v1)/[D-072.1](docs/DECISIONS.md#d-0721-phase-b-不等-step-2-自用数据-用-l2-trace-baseline-替代)）+ 推荐链路 L1/L2/L3 全跑通 + Web SPA + V1.1 反馈系统 + FastAPI 13 端点。

**refine 链路大改**（2026-05-16, [D-073](docs/DECISIONS.md#d-073-refine-走结构化意图-refineintent--重召回-让用户主动表达诉求真正生效)）—— 实测"想吃点湖南菜，然后肉多一点"暴露 CHIP_VOCAB 封闭词表 + chip 死映射 + refine 不重召回 3 个结构性约束 → 拆 parser、开放 RefineIntent schema、重做 recall、L2 加 intent_match_bonus（cuisine 0.50 / ingredient 0.20 / flavor 0.10）、健康 guardrail、彻底砍 D-071。

剩下 **Step 2 用户自用一周**（采纳率 + D-073 命中率验证, 不在代码范围）→ Phase 1 同事推广。

> **V1 主交互**：本机 localhost Web SPA。`cd apps/web && npm install && npm run dev` → http://localhost:5173。详见 [`apps/web/README.md`](apps/web/README.md) + [`docs/style-guide.md`](docs/style-guide.md) + [`docs/api.md`](docs/api.md)。飞书延后到 V1.5 做推送通道。

详细路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)；产品收敛逻辑见 [docs/PRD.md](docs/PRD.md) §1 + §3.4。

---

## 文档体系

| 文档 | 内容 | 何时读 |
|---|---|---|
| [docs/PRD.md](docs/PRD.md) | 产品需求 · 为什么做、做给谁、做成什么样 | 第一份读，建立产品定位 |
| [DESIGN.md](DESIGN.md) | 设计与实现 · 架构、schema、API、prompt、避坑 | 实现时随时查 |
| [docs/style-guide.md](docs/style-guide.md) | UI 文案规范 + 视觉系统 + 锁定反模式（D-052~D-055 + D-060/D-066/D-067） | 改 `apps/web/` 任何用户视图前必读 |
| [docs/api.md](docs/api.md) | 前后端 API 契约（V1） | 调 `/api/*` 或后端装新端点前必读 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 决策日志 · 产品/架构/方法论 决策为什么这样而不是那样 | 想推翻某个设计前先看 |
| [docs/IMPLEMENTATION_LOG.md](docs/IMPLEMENTATION_LOG.md) | 工程实施日志 · prompt 改了几行、batch 数、bug 排查、参数微调 | 排查具体实现、复盘工程细节时 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 路线图 · V1/V2/V3 边界，已砍清单 | 想加新功能前先看 |
| [docs/RECOMMEND_PRINCIPLES.md](docs/RECOMMEND_PRINCIPLES.md) | 推荐系统分层原则与方法论（D-043 沉淀）| 改打分/召回/重排前**必读** |
| [docs/L3_RERANK_REDESIGN.md](docs/L3_RERANK_REDESIGN.md) | L3 精排重构方案（D-047）| 改 L3 精排前**必读** |
| [eval/dish_tagging_eval/](eval/dish_tagging_eval/) | 菜品打标评测框架（dual-model golden set 171 条 + 评测脚本）| 复评打标质量、改 prompt 前 |
| [eval/dish_tagging_model_eval_spec.md](eval/dish_tagging_model_eval_spec.md) | 评测说明（面向 PM）| 想理解评测口径与结论时 |
| [docs/design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md](docs/design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md) | AI-friendly 接入终态共识（Opus + Codex + 志丹三方收敛，2026-05-16）| 改 Agent 接入相关设计前必读；待 Step 2 完成后落 D-074 |
| [docs/agent-integration-approach.md](docs/agent-integration-approach.md) | "CLI + Skill" 模式技术交流文档（拿出去 sale 同行 / 写技术文章用）| 跟同行交流 Agent 接入方法论时 |
| [docs/intro-for-colleagues.md](docs/intro-for-colleagues.md) | 给同事的产品 sale 文档（750 字）| sale chisha 给周围同事时 |

**首次接触请按顺序读：PRD → ROADMAP → DESIGN → DECISIONS**。
改推荐链路前请额外读 RECOMMEND_PRINCIPLES；改 L3 精排前读 L3_RERANK_REDESIGN；复盘工程细节看 IMPLEMENTATION_LOG。

---

## 当前进度

### ✅ 工程侧（Phase 0 收尾）

- **L0 方法论层**（[D-072](docs/DECISIONS.md#d-072-methodology-spec-抽象-放-phase-0-收尾-v1)）：`profiles/methodologies/harvard_plate.yaml` + `chisha/methodology.py` 加载/严格 keyset 校验/merge；profile.yaml `methodology: harvard_plate` 引用
- **L1 召回**：`chisha/recall.py` 硬过滤双层 + combo 灵活组合（[D-040](docs/DECISIONS.md#d-040)/[D-041](docs/DECISIONS.md#d-041)）
- **L2 打分**：`chisha/score.py` 16 维 + 4 层 cap（restaurant/brand/cuisine/food_form, [D-042](docs/DECISIONS.md#d-042)/[D-043](docs/DECISIONS.md#d-043)/[D-045](docs/DECISIONS.md#d-045)）+ 不可补偿惩罚
- **L3 精排**：`chisha/rerank.py` LLM tool_use forced schema（[D-047](docs/DECISIONS.md#d-047)）+ 双路径分流 + 配置错 hard-fail（[D-048](docs/DECISIONS.md#d-048)）+ validate→retry→fallback（[D-050](docs/DECISIONS.md#d-050)）；prompt 注入方法论 rationale（D-072）
- **Refine**：`chisha/refine.py` + `chisha/refine_intent.py` 结构化意图解析（cuisine/ingredient/flavor_tags/portion/staple/price 开放 schema, [D-073](docs/DECISIONS.md#d-073-refine-走结构化意图-refineintent--重召回-让用户主动表达诉求真正生效)）
- **数据打标**：`scripts/tag_via_api.py` OpenRouter, 默认 `deepseek-v4-flash`（[D-037](docs/DECISIONS.md#d-037), 171 条 dual-model golden 横评）
- **数据**：`data/shenzhen-bay/` 139 家 7256 菜 + `data/home/` 38 家 2117 菜
- **Web SPA**：`apps/web/` Vite + React 18 + TS + Tailwind, HomePage / ProfilePage / HistoryPage / FeedbackPage / FeedbackInbox（[D-051~D-055](docs/DECISIONS.md#d-051) + [D-056~D-068](docs/DECISIONS.md#d-056-navbar-加反馈-tab--角标-v11)）
- **FastAPI 13 端点**：推荐 6（recommend/refine/accept/skip/profile/history）+ V1.1 反馈 7（inbox/snooze/stop/recent/get/record/comments），单 JSON 文件落盘（[IMPL_LOG D-069](docs/IMPLEMENTATION_LOG.md#d-069-执行记录--fastapi-v1--v11-后端-13-端点联调--codex-review-修复)）
- **调试台**：FastAPI `:8765/debug` instrumented 管道, L1/L2/L3/Final 四段 + 16 维 breakdown + LLM payload 可见 + combo 追溯 + mood 三栏对比（[D-039](docs/DECISIONS.md#d-039)）
- **回归工具**：`scripts/baseline_l2_snapshot.py` + `scripts/compare_traces.py` L2 trace 严格回归（[D-072.1](docs/DECISIONS.md#d-0721-phase-b-不等-step-2-自用数据-用-l2-trace-baseline-替代)）
- **测试**：435 单测全过（pre-existing test_cleanup_expired 1 个无关 flake）

### ⏳ 接下来

1. **Step 2 · 自用一周（用户行为，不在代码范围）**：`cd apps/web && npm install && npm run build && cd .. && uv run python -m chisha.debug_server` → http://127.0.0.1:8765/。每天用着看采纳率撑不撑得起来。详见 [ROADMAP Phase 路线](docs/ROADMAP.md#phase-路线d-070-沉淀取代旧-v1v2v3-笛卡尔积)
2. **Phase 1 启动条件**：自己愿意每天用 + ≥ 3 同事自发持续使用密度门槛。准入前发 screener 探原则派密度
3. **延后到 V1.5**：OpenClaw 飞书推送通道、调试台 React 化（D-051）、macOS launchd 定时拉起

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
├── CLAUDE.md                  # 项目级 AI 协作指令 (改推荐链路前看红线)
├── profile.yaml               # 用户偏好 (含 methodology: harvard_plate 引用, D-072)
├── profiles/
│   └── methodologies/         # L0 方法论 spec (D-072)
│       └── harvard_plate.yaml # 哈佛餐盘 spec (7 必备字段 + 16 维 weights + 4 层 cap)
├── docs/
│   ├── PRD.md                 # 产品需求 (D-070 收敛为「原则派点餐执行外包」)
│   ├── DECISIONS.md           # 决策日志 (D-001~D-072, 全项目共享编号)
│   ├── IMPLEMENTATION_LOG.md  # 工程实施日志 (prompt / 参数 / bug / 三轮 review)
│   ├── ROADMAP.md             # Phase 路线 (Phase 0 自用 → Phase 1 同事 → Phase 2 扩展)
│   ├── RECOMMEND_PRINCIPLES.md # 推荐分层原则 (D-043 + §14 L0 方法论沉淀)
│   ├── L3_RERANK_REDESIGN.md  # L3 精排重构方案 (D-047)
│   ├── api.md                 # 前后端 API 契约 (V1 + V1.1)
│   ├── style-guide.md         # UI 文案规范 + 视觉系统 (D-052~D-055/D-060/D-066/D-067)
│   ├── CONTRIBUTING_DOCS.md   # 文档维护准则与每次决策 checklist
│   └── archive/               # 旧版设计文档归档
├── data/
│   ├── shenzhen-bay/          # office zone, 139 家 7256 菜
│   └── home/           # home zone, 38 家 2117 菜
├── chisha/                    # L1~L3 推荐链路 Python 包
│   ├── api.py                 # recommend_meal 主入口 (D-033 单一 V2 路径, D-049 后)
│   ├── methodology.py         # L0 spec 加载/校验/merge (D-072)
│   ├── recall.py              # L1 召回 + 硬过滤双层 + combo 组合 (D-040/041)
│   ├── score.py               # L2 打分 16 维 + 4 层 cap (D-042/043/045)
│   ├── rerank.py              # L3 LLM 精排 top60→5 (D-035/046/047/048/050)
│   ├── context.py             # ContextSnapshot (D-034)
│   ├── refine.py              # refine 二轮主流程 (D-033/073)
│   ├── refine_intent.py       # D-073: RefineIntent schema + parser
│   ├── feedback.py            # chip 反馈解析员 (D-035)
│   ├── feedback_store.py      # V1.1 反馈系统单 JSON 落盘 (D-068/069)
│   ├── llm_client.py          # provider 路由层 (D-047)
│   ├── llm_providers/         # anthropic_api / openrouter / claude_code_cli (D-047/048)
│   ├── web_api.py             # FastAPI 13 端点 (apps/web 服务端, D-069)
│   ├── debug_recommend.py     # 调试台 instrumented 管道 (D-039)
│   ├── debug_server.py        # FastAPI server entry (D-039)
│   ├── long_term_prefs.py     # 反馈闭环 P3 (D-043)
│   └── static/                # 老调试台前端 (debug.html / logic.html)
├── apps/web/                  # V1 主交互 React 18 + Vite + TS SPA (D-051~D-068)
├── integrations/openclaw/     # 飞书推送通道骨架, V1.5 接入 (D-051 翻案)
├── scripts/                   # 数据维护 + 回归工具
│   ├── tag_via_api.py         # LLM 打标 (D-037 OpenRouter)
│   ├── dry_run.py             # 推荐空跑
│   ├── inspect_candidates.py  # 召回审计
│   ├── baseline_l2_snapshot.py # L2 trace 回归基线 (D-072.1)
│   ├── compare_traces.py      # 严格回归对比 |delta| < 1e-6 (D-072.1)
│   └── baseline_l3_prompt_ab.py # L3 prompt A/B 对照 (Codex Round 2 M-2)
├── prompts/                   # LLM prompt 模板 (rerank_system.md 等)
└── tests/                     # 435 单测 (全链路 + methodology + refine mood + contract)
```

### 启调试台（D-039）

```bash
uv run python -m chisha.debug_server
# → http://127.0.0.1:8765
# 浏览器看 L1 召回 / L2 16 维打分 / L3 LLM 精排 payload / Final 5 卡片
```

### L2 trace 严格回归（D-072.1）

```bash
# 1. 改 score.py / methodology / spec 之前先存 baseline
uv run python -m scripts.baseline_l2_snapshot --out-dir tmp/baseline_traces

# 2. 改完代码后重新跑一遍
uv run python -m scripts.baseline_l2_snapshot --out-dir tmp/baseline_traces_after

# 3. 严格对比 (top60 顺序 + 16 维 breakdown |delta| < 1e-6)
uv run python -m scripts.compare_traces
# → 任何 diff 都阻止 commit, 必须找到漏的规则补 spec
```

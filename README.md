# 今天吃点啥 · chisha

> 原则派点餐助手——给已经认定一套吃法、但懒得每天选店的原则派，30 秒搞定外卖决策。
> 可接进 OpenClaw / HappyClaw / Claude Code / 任何 Agent 的开源 Skill。

---

## 这是什么

定位见 [D-070](docs/archive/DECISIONS_phase0.md#d-070-产品定位收敛到原则派点餐助手--三层信号模型-v1)：**原则派点餐助手**——服务的是已经认了一套饮食方法论（减脂控油 / 增肌高蛋白 / 糖控 / 孕期...）、痛点在**每天落地费力**的人。明确不服务"什么都行又什么都不想吃"的目标缺失型用户。

我自己是典型用户：认了哈佛餐盘弱约束（控油 + 有蔬菜 + 有蛋白），但每天点外卖还得花 10-20 分钟翻 200 家店上千道菜手动凑齐这个结构。

`chisha` 把这个执行过程系统性外包：每顿饭在 11:25 / 18:00 主动推送提醒，给 5 个组合，30 秒选一个就走。

> **V1 当前形态**（[D-051](docs/archive/DECISIONS_phase0.md#d-051)）：本机 localhost Web SPA（用户视图 + 调试台合一），自用打磨体验。V1.5 接入飞书做推送 + deeplink 跳转。

> **餐盘策略说明**：不追求严格 1/2-1/4-1/4 比例（中式外卖现实下不可达），改弱约束三件套：控油 + 至少 1 道蔬菜 + 蛋白下限。详见 [DECISIONS D-023](docs/archive/DECISIONS_phase0.md#d-023)。

详细动机见 [docs/PRD.md](docs/PRD.md)。

---

## 命名

- **项目名（对人）**：今天吃点啥
- **代码名（对机器）**：`chisha`
- **未来 pip 包**：`chisha`（推荐引擎） + `chisha-data-{office_zone}`（数据按工区拆子包，如 `chisha-data-shenzhen-bay`）
- **sister project**：`chisha-collector`（数据采集 / 清洗 / 打标 / 保鲜，独立维护，[D-027](docs/archive/DECISIONS_phase0.md#d-027)）

文档里"今天吃点啥"和 `chisha` 会交替出现，意思一样。

---

## 项目状态

**Phase 0 工程侧已收尾**（2026-05-15）—— 「原则派点餐执行外包」定位收敛（[D-070](docs/archive/DECISIONS_phase0.md#d-070-产品定位收敛到原则派点餐助手--三层信号模型-v1)）+ 砍 mood picker（[D-071](docs/archive/DECISIONS_phase0.md#d-071-砍-mood-picker--want_soup-关键词识别-v1)）+ methodology spec 抽象（[D-072](docs/archive/DECISIONS_phase0.md#d-072-methodology-spec-抽象-放-phase-0-收尾-v1)/[D-072.1](docs/archive/DECISIONS_phase0.md#d-0721-phase-b-不等-step-2-自用数据-用-l2-trace-baseline-替代)）+ 推荐链路 L1/L2/L3 全跑通 + Web SPA + V1.1 反馈系统 + FastAPI 13 端点。

剩下 **Step 2 用户自用一周**（采纳率验证, 不在代码范围）→ Phase 1 同事推广。

> **V1 主交互**：本机 localhost Web SPA。`cd apps/web && npm install && npm run dev` → http://localhost:5173。详见 [`apps/web/README.md`](apps/web/README.md) + [`docs/style-guide.md`](docs/style-guide.md) + [`docs/api.md`](docs/api.md)。飞书延后到 V1.5 做推送通道。

详细路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)；产品收敛逻辑见 [docs/PRD.md](docs/PRD.md) §1 + §3.4。

---

## 文档体系

> **📋 整理中（2026-05-16）**：Phase 0 收尾，文档体系按"读者分层"重构（参见 [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md)）。
> 旧的 `DECISIONS.md` / `IMPLEMENTATION_LOG.md` / `DESIGN.md` 已归档到 `docs/archive/`，不再维护。
> 活决策正在提炼到 `docs/decisions.md`（单文件，≤ 15 行/条），Agent 跨文件约束在 `docs/CONTRACTS.md`（待建）。

| 文档 | 主读者 | 内容 |
|---|---|---|
| [docs/PRD.md](docs/PRD.md) | 你 | 产品需求 · 为什么做、做给谁 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 你 | 路线图 · V1/V2/V3 边界，已砍清单 |
| `docs/decisions.md` | 你 · agent 偶尔 grep | 活决策日志（单文件，提炼中） |
| [CLAUDE.md](CLAUDE.md) | Coding agent 每次会话 | 项目红线 / 常用命令 / avoid 清单 |
| `docs/CONTRACTS.md` | Coding agent 每次会话 | 跨文件隐含约束（待建） |
| [docs/api.md](docs/api.md) | agent | 前后端 API 契约（V1） |
| [docs/style-guide.md](docs/style-guide.md) | agent | `apps/web/` UI 文案 + 视觉系统 + 反模式 |
| [eval/dish_tagging_eval/](eval/dish_tagging_eval/) | 复评 prompt 时 | 打标评测框架（171 条 golden set） |
| `docs/archive/` | 历史考古 | Phase 0 旧 DECISIONS / IMPL_LOG / DESIGN，**不再维护** |

---

## 当前进度

**Phase 0 工程侧 ✅ 收尾**（2026-05-15）。详细 phase 状态、里程碑、已砍清单见 [docs/ROADMAP.md](docs/ROADMAP.md)。

**接下来**：Step 2 自用一周（用户行为，不在代码范围）→ Phase 1 同事推广（启动条件：自己愿意每天用 + ≥ 3 同事自发持续使用）。

实现新功能前先查 [ROADMAP](docs/ROADMAP.md) 当前版本范围；想推翻已有设计先查 [decisions.md](docs/decisions.md)；改代码前查 [CONTRACTS.md](docs/CONTRACTS.md) 跨文件约束。

---

## 文档维护规则

为保证上下文不漂移，文档按"读者"分四桶（详见 [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md)）：

1. **产品决策（给你）**：写 `docs/decisions.md`，目标 3-5 行/条，> 15 行就是塞实施细节，停下
2. **Agent 契约（给 coding agent）**：跨文件隐含约束写 `docs/CONTRACTS.md`；红线/命令写 `CLAUDE.md`
3. **工程细节默认不写文档**：字段表 / prompt 行号 / batch 数 / bug 排查 — 代码 + git log 即权威
4. **路线变更**：更新 ROADMAP，已砍的进已砍清单
5. **PRD 极少改**：定位变化才改，每次改在 decisions 加一条说明

---

## 项目结构

```
chisha/
├── README.md                  # 你在看
├── CLAUDE.md                  # 项目级 AI 协作指令 (Coding agent 必读)
├── profile.yaml               # 用户偏好 (含 methodology: harvard_plate 引用)
├── profiles/
│   └── methodologies/         # L0 方法论 spec
│       └── harvard_plate.yaml # 哈佛餐盘 spec
├── docs/
│   ├── PRD.md                 # 产品需求
│   ├── ROADMAP.md             # Phase 路线 (Phase 0 自用 → Phase 1 同事 → Phase 2 扩展)
│   ├── decisions.md           # 活决策日志 (~25 条, 你看的)
│   ├── CONTRACTS.md           # Agent 跨文件隐含约束 (Coding agent 看的)
│   ├── api.md                 # 前后端 API 契约 (V1 + V1.1)
│   ├── style-guide.md         # UI 文案规范 + 视觉系统
│   ├── CONTRIBUTING_DOCS.md   # 文档维护准则 (四桶分层)
│   └── archive/               # Phase 0 旧 DECISIONS / IMPL_LOG / DESIGN / L3_REDESIGN / RECOMMEND_PRINCIPLES (不再维护)
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
│   ├── refine.py              # refine 二轮 + want_soup 关键词识别 (D-033/071)
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

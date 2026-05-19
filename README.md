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

**Phase 0 工程侧已收尾**（2026-05-20，D-001~D-092）—— 推荐链路 L1/L2/L3 全跑通 + Web SPA + V1.1 反馈系统 + L1 长期反馈层真兑现（LLM 抽取）+ Sandbox Time-Travel + 推荐链路 trace 持久化 + Debug 三模式（Replay / What-if / Live）+ FastAPI 23 端点 + **Refine v2 / Faithful Refine framework 重构**（D-080~D-085: L0 三分 + RefineIntentV2 多 slot + reference resolver + subtype diversify + 方法论状态条 + L3 narrative）+ **L2 refine 信号校准 + 死维度清理**（D-090/D-091/D-092: intent 三维权重 ×2~×4 + health_guardrail slot-aware 松绑 + 通用健康权重 slot-gated 让位 + price_band 语义解耦 + 5 死维度移除 → 14 维 breakdown）。

历史背景（D-001~D-072）在 [docs/archive/DECISIONS_phase0.md](docs/archive/DECISIONS_phase0.md)；活决策（含 D-073~D-092）在 [docs/decisions.md](docs/decisions.md)；Agent 跨文件约束在 [docs/CONTRACTS.md](docs/CONTRACTS.md)。

**接下来**：5 步推进路线（debug trace 验收 → 摸清 L1 → 沙盒 e2e + D-080~D-085 framework 复测 → 接个人 agent + context 注入 → 同 query 随机性），详见 [docs/ROADMAP.md "Phase 0 收尾路线"](docs/ROADMAP.md)。终极路径：自用稳定 → 接个人 agent → 扩同事 / 数据源。

> **V1 主交互**：本机 localhost Web SPA。`cd apps/web && npm install && npm run dev` → http://localhost:5173。详见 [`apps/web/README.md`](apps/web/README.md) + [`docs/style-guide.md`](docs/style-guide.md) + [`docs/api.md`](docs/api.md)。飞书延后到 V1.5 做推送通道。

详细路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)；产品收敛逻辑见 [docs/PRD.md](docs/PRD.md) §1 + §3.4。

---

## 文档体系

> **📋 整理中（2026-05-16 重构）**：文档体系按"读者分层"分四桶（详见 [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md)）。
> 旧的 `DECISIONS.md` / `IMPLEMENTATION_LOG.md` / `DESIGN.md` / `L3_RERANK_REDESIGN.md` / `RECOMMEND_PRINCIPLES.md` 已归档到 `docs/archive/`，不再维护。

| 文档 | 主读者 | 内容 |
|---|---|---|
| [docs/PRD.md](docs/PRD.md) | 你 | 产品需求 · 为什么做、做给谁 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 你 | 路线图 · V1/V2/V3 边界，已砍清单 |
| [docs/decisions.md](docs/decisions.md) | 你 · agent 偶尔 grep | 活决策日志（单文件，≤ 15 行/条，提炼中） |
| [docs/BACKLOG.md](docs/BACKLOG.md) | 你 | 待办池 · 已知但当前不解决的 bug / feature / idea |
| [CLAUDE.md](CLAUDE.md) | Coding agent 每次会话 | 项目红线 / 常用命令 / avoid 清单 |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | Coding agent 每次会话 | 跨文件隐含约束 / 反直觉规则 / 系统级 invariant |
| [docs/api.md](docs/api.md) | agent | 前后端 API 契约（V1 + V1.1） |
| [docs/style-guide.md](docs/style-guide.md) | agent | `apps/web/` UI 文案 + 视觉系统 + 反模式（D-052~D-068 锁定） |
| [apps/debug-ui/README.md](apps/debug-ui/README.md) | agent | `apps/debug-ui/` SPA 设计（D-075 独立 Vite SPA / V12 DAG / 5 主题） |
| [apps/sandbox-lab/README.md](apps/sandbox-lab/README.md) | agent | `apps/sandbox-lab/` Sandbox Lab 白盒时光机 SPA（D-093 独立 Vite SPA / 端口 5175） |
| [docs/intro-for-colleagues.md](docs/intro-for-colleagues.md) | 同事 | 给同事的产品 sale 文档（750 字） |
| [docs/agent-integration-approach.md](docs/agent-integration-approach.md) | 同行 | "CLI + Skill" 模式技术交流文档 |
| [docs/design_briefs/](docs/design_briefs/) | 你 · 历史 | 设计草稿（如 D-074 AI-friendly 接入共识） |
| [eval/dish_tagging_eval/](eval/dish_tagging_eval/) | 复评 prompt 时 | 打标评测框架（171 条 golden set） |
| [docs/archive/](docs/archive/) | 历史考古 | Phase 0 旧 DECISIONS / IMPL_LOG / DESIGN / L3_REDESIGN / RECOMMEND_PRINCIPLES，**不再维护** |

---

## 当前进度

**Phase 0 工程侧 ✅ 收尾**（2026-05-17）。详细 phase 状态、里程碑、已砍清单见 [docs/ROADMAP.md](docs/ROADMAP.md)。

**接下来**：5 步收尾路线（详见 [ROADMAP "Phase 0 收尾路线"](docs/ROADMAP.md)）→ Phase 1 同事推广（启动条件：自用稳定 + 个人 agent 接入跑通 + ≥ 3 同事自发持续使用）。

实现新功能前先查 [ROADMAP](docs/ROADMAP.md) 当前版本范围；想推翻已有设计先查 [decisions.md](docs/decisions.md) + [archive/DECISIONS_phase0.md](docs/archive/DECISIONS_phase0.md)；改代码前查 [CONTRACTS.md](docs/CONTRACTS.md) 跨文件约束。

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
│   ├── decisions.md           # 活决策日志 (≤ 15 行/条, 提炼中)
│   ├── CONTRACTS.md           # Agent 跨文件隐含约束 (Coding agent 看的)
│   ├── BACKLOG.md             # 已知但当前不解决的 bug / feature / idea
│   ├── api.md                 # 前后端 API 契约 (V1 + V1.1)
│   ├── style-guide.md         # UI 文案规范 + 视觉系统
│   ├── CONTRIBUTING_DOCS.md   # 文档维护准则 (四桶分层)
│   ├── design_briefs/         # 设计草稿 (D-074 AI-friendly 接入共识等)
│   └── archive/               # Phase 0 旧 DECISIONS / IMPL_LOG / DESIGN / L3_REDESIGN / RECOMMEND_PRINCIPLES (不再维护)
├── data/
│   ├── shenzhen-bay/          # office zone, 139 家 7256 菜
│   └── home/           # home zone, 38 家 2117 菜
├── chisha/                    # L1~L3 推荐链路 Python 包 (api / recall / score / rerank / refine / l1_extractor / l1_prefs / sandbox / clock / data_root / trace_store / debug_what_if / web_api / ...)
├── apps/web/                  # V1 主交互 React 18 + Vite + TS SPA (D-051~D-068)
├── apps/debug-ui/             # V12 DAG 调试台 SPA (D-075, 端口 5174)
├── apps/sandbox-lab/          # 白盒时光机 sandbox SPA (D-093, 端口 5175)
├── integrations/openclaw/     # 飞书推送通道骨架, V1.5 接入 (D-051 翻案)
├── scripts/                   # 数据维护 + 回归工具 (tag_via_api / dry_run / inspect_candidates / baseline_l2_snapshot / compare_traces / bootstrap_l1_from_legacy / ...)
├── prompts/                   # LLM prompt 模板 (rerank_system / l1_extract / parse_refine_intent 等)
└── tests/                     # pytest 全链路 + 单元 (435+)
```

### 启调试台（D-039 + D-075）

```bash
# 老调试台 + 后端 (vanilla HTML, :8765/debug)
uv run python -m chisha.debug_server

# 新 debug-ui SPA (Vite, :5174, proxy /api → :8765)
cd apps/debug-ui && npm install && npm run dev
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

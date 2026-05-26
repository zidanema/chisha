# 今天吃点啥 · chisha

> 原则派点餐助手 — 给已经认定一套吃法、但懒得每天选店的人, 30 秒搞定外卖决策。

## 这是什么

服务**已经认了一套饮食方法论** (减脂控油 / 增肌高蛋白 / 糖控 / 孕期) 但**每天落地费力**的人。明确不服务"什么都行又什么都不想吃"的目标缺失型用户。

典型用法: 我自己认了哈佛餐盘弱约束 (控油 + 有蔬菜 + 有蛋白), 但每天点外卖还得花 10-20 分钟翻 200 家店上千道菜手动凑齐这个结构。`chisha` 把这个执行过程外包: 每顿饭推 5 个组合, 30 秒选一个就走, 吃完反馈, 越用越准。

技术上是三阶段推荐: L1 召回 (硬过滤 + 软偏好) → L2 14 维打分 → L3 LLM 精排 + 写推荐理由。详见 [docs/PRD.md](docs/PRD.md)。

---

## 当前状态

**V1.0 工程里程碑完成** (2026-05-20) · **自用阶段, 非开源 ready**

跑通了: 推荐链路 L1/L2/L3 / Web SPA 用户视图 / 反馈系统 / L1 长期偏好 LLM 抽取 / 反馈短链路即时生效 (D-098, 差评下次推荐就降权/剔除) / Sandbox time-travel / trace 持久化 + Debug 三模式 / Faithful Refine framework / L2 信号校准。

还没做的: 第二份方法论 spec (验证抽象解耦) / 数据按工区拆包 / Agent 接入 CLI 形态正式落地 / 同事推广前的 screener — 详见 [docs/ROADMAP.md](docs/ROADMAP.md)。

**接下来** (D-097, 2026-05-25 定位调整): **自用为主、推广随缘** — 先做 个人 agent 接入 (D-074) + 反馈短链路修复 (B-001, P0)。同事推广向工作 (screener / 第二份 spec) 推迟到真要推时。

---

## Quickstart

```bash
# 1. 装依赖 (需要 Python 3.11+, uv, Node 18+)
uv sync
cp .env.example .env  # 填 OPENROUTER_API_KEY 或 ANTHROPIC_API_KEY

# 2. 启后端 (FastAPI, :8765)
uv run python -m chisha.debug_server

# 3. 启用户视图 (另开终端, :5173)
cd apps/web && npm install && npm run dev
# → 打开 http://localhost:5173

# 4. (可选) 启调试台 / Sandbox Lab
cd apps/debug-ui && npm install && npm run dev      # :5174
cd apps/sandbox-lab && npm install && npm run dev   # :5175
```

数据目录 `data/shenzhen-bay/` (深圳湾 139 家 7256 菜) 已随仓库; 切换城市需自己跑 `scripts/tag_via_api.py` 打标流程。

---

## 文档导航

**了解产品和路线** (新读者从这里开始):

| 文档 | 内容 |
|---|---|
| [docs/INTRODUCTION.md](docs/INTRODUCTION.md) | 5 分钟引子 · 它解决什么问题、为什么用 Agent 形态 |
| [docs/PRD.md](docs/PRD.md) | 产品需求 · 为什么做、做给谁、不做什么 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phase 路线 + 已砍清单 |
| [docs/decisions.md](docs/decisions.md) | 活决策日志 (产品/架构, 每条 ≤ 15 行) |
| [docs/BACKLOG.md](docs/BACKLOG.md) | 待办 bug / feature / idea |

**改代码 / 接入 Agent**:

| 文档 | 内容 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | 项目红线 + 常用命令 (coding agent 必读) |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | 跨文件隐含约束 + 反直觉规则 |
| [docs/api.md](docs/api.md) | 前后端 API 契约 |
| [docs/style-guide.md](docs/style-guide.md) | `apps/web/` UI 规范 + 反模式清单 |
| [docs/data-pipeline.md](docs/data-pipeline.md) | 采集后加工流水线 (collector → chisha): 消费/打标/回填/验收 + 坑 |
| [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md) | 文档维护准则 (改任何文档前必读) |

**草稿 / 历史**: [docs/proposals/](docs/proposals/) 未落地的提案; [docs/archive/](docs/archive/) Phase 0 归档不维护。

---

## 项目结构

```
chisha/         L1~L3 推荐链路 Python 包 (api, recall, score, rerank, refine, ...)
apps/web/       V1 用户视图 SPA (React + Vite + TS, :5173)
apps/debug-ui/  调试台 SPA (V12 DAG, :5174)
apps/sandbox-lab/  白盒时光机 SPA (多 session + branch/rollback, :5175)
data/           按工区拆 (shenzhen-bay / home), 已打标
profile.yaml + profiles/methodologies/  用户偏好 + L0 方法论 spec
prompts/        LLM prompt 模板
scripts/        数据维护 + 回归工具
tests/          pytest 全链路 + 单元 (435+)
docs/           见上方文档导航
```

---

## 命名

项目名"今天吃点啥"对人, 代码名 `chisha` 对机器 (ASCII safe, 给包名 / import / CLI 用)。文档里交替出现, 同一个东西。

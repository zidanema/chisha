# 今天吃点啥 · chisha

> 原则派点餐助手 — 给已经认定一套吃法、但懒得每天选店的人, 30 秒搞定外卖决策。
>
> 项目名"今天吃点啥"对人, 代码名 `chisha` 对机器 (包名 / import / CLI). 同一个东西。

> 🤖 **AI agent installing this on behalf of a user?** → read [AGENTS.md](AGENTS.md), not this file.

---

## 这是什么

服务**已经认了一套饮食方法论** (减脂控油 / 增肌高蛋白 / 糖控 / 孕期) 但**每天落地费力**的人。明确不服务"什么都行又什么都不想吃"的目标缺失型用户。

典型用法: 我自己认了哈佛餐盘弱约束 (控油 + 有蔬菜 + 有蛋白), 每天点外卖还得花 10-20 分钟翻 200 家店上千道菜手动凑齐这个结构。`chisha` 把这个执行过程外包: 每顿饭推 5 个组合, 30 秒选一个就走, 吃完反馈, 越用越准。

技术上是三阶段推荐: **L1 召回** (硬过滤 + 软偏好) → **L2 14 维打分** → **L3 LLM 精排 + 写推荐理由**。详见 [docs/PRD.md](docs/PRD.md)。

---

## 当前状态

**V1.0 工程里程碑完成** (2026-05-20) · **自用为主、推广随缘** (D-097)

跑通了: 推荐链路 L1/L2/L3 + Web SPA 用户视图 + 反馈系统 + L1 长期偏好 LLM 抽取 + 反馈短链路即时生效 (差评下次推荐就降权/剔除, D-098) + Sandbox time-travel + trace 持久化 + Debug 三模式 + Faithful Refine framework + L2 信号校准 + **可分发共享核心** (D-102: 统一兜底契约 + install/state root 二分 state→`~/.chisha/` + bundle manifest/compat 闸门) + **T-DIST-01** wheel 分发 + Claude Code skill 自动接入。

**当前限制** (主动收窄, 等同事真要推时再扩):

| 项 | 现状 | 后续 |
|---|---|---|
| Zone (城市/工区) | 仅 shenzhen-bay (深圳湾, 334 家 / 22556 菜) | T-DIST-02 zone bundle marketplace |
| Methodology (饮食方法论) | 仅 harvard_plate (哈佛餐盘); 其它走 refine 自由文本兜底 | T-DIST-02 methodology schema/template/validate |
| Host agent | 仅 Claude Code 有自动触发 skill; 其它可手动调 CLI | T-DIST-02 多 adapter (Cursor / Codex / OpenClaw) |
| Manifest integrity | 只闸兼容性, 不验完整性/来源 (`integrity=null` 留位) | git+https transport 由 commit hash 兜底; S3/镜像 transport 需自验 |

详细路线见 [docs/ROADMAP.md](docs/ROADMAP.md)。

---

## 装 (Claude Code 用户, quickstart)

```bash
uv tool install git+https://github.com/zidanema/chisha.git
chisha onboard --zone shenzhen-bay     # 写 ~/.chisha/profile.yaml + 装 skill + dry start 自检
chisha doctor                          # 自检 install/state root + manifest + scope
# → 之后 Claude Code 里说 "今天中午吃啥" 即触发 chisha-meal skill
```

升级: `uv tool upgrade chisha-meal` (state 永远住 `~/.chisha/`, 不被覆盖)。

**让 AI agent 帮你装**: 把 [AGENTS.md](AGENTS.md) 链接丢给你的 Claude Code, 它会按 spec 自己探测、安装、配置、冒烟测试。

---

## Dev (改代码 / 跑 Web 调试台 / 改前端)

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

数据目录 `data/shenzhen-bay/` (深圳湾 334 家 / 22556 菜) 已随仓库; 切换城市需自己跑 `scripts/tag_via_api.py` 打标流程。

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
| [AGENTS.md](AGENTS.md) | **AI agent 安装契约** v1.0 (host agent 自动安装走这个; 唯一版本化契约源) |
| [CLAUDE.md](CLAUDE.md) | 项目红线 + 常用命令 (coding agent 必读) |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | 跨文件隐含约束 + 反直觉规则 |
| [docs/api.md](docs/api.md) | 前后端 API 契约 |
| [docs/style-guide.md](docs/style-guide.md) | `apps/web/` UI 规范 + 反模式清单 |
| [docs/data-pipeline.md](docs/data-pipeline.md) | 采集后加工流水线: 消费/打标/回填/验收 + 坑 |
| [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md) | 文档维护准则 (改任何文档前必读) |

**草稿 / 历史**: [docs/proposals/](docs/proposals/) 未落地的提案; [docs/archive/](docs/archive/) Phase 0 归档不维护。

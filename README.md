# 今天吃点啥 · chisha

> 原则派点餐助手 — 给已经认定一套吃法、但懒得每天选店的人, 30 秒搞定外卖决策。
>
> 项目名"今天吃点啥"对人, 代码名 `chisha` 对机器 (包名 / import / CLI). 同一个东西。

> 🤖 **AI agent installing this on behalf of a user?** → read [AGENTS.md](AGENTS.md), not this file.

---

## 这是什么

服务**已经认了一套饮食方法论** (减脂控油 / 增肌高蛋白 / 糖控 / 孕期) 但**每天落地费力**的人。明确不服务"什么都行又什么都不想吃"的目标缺失型用户。

典型用法: 我自己认了哈佛餐盘弱约束 (控油 + 有蔬菜 + 有蛋白), 每天点外卖还得花 10-20 分钟翻 200 家店上千道菜手动凑齐这个结构。`chisha` 把这个执行过程外包: 每顿饭推 5 个组合, 30 秒选一个就走, 吃完反馈, 越用越准。

技术上是三阶段推荐: **L1 召回** (硬过滤 + 软偏好) → **L2 15 维打分** → **L3 LLM 精排 + 写推荐理由**。详见 [docs/PRD.md](docs/PRD.md)。

---

## 为什么是这个形态 (AI-friendly 架构)

chisha 是**无脑的**——它自己不调 LLM、不持任何 API key。确定性的活 (召回 / 打分 / 校验 / 兜底 / 反馈) 全在 chisha; 需要"智能"的两步 (把用户原话抽成结构化 intent、读候选排出推荐) 由它发一个机器可读的 `do_llm` 信封, **借宿主 agent (Claude Code) 自己的 LLM** 执行后喂回校验落库。

典型 CLI 工具要么内置模型、要么自己管 key (自包含智能); chisha 选了另一条路: **确定性引擎 + 借来的宿主智能**——既零 key, 又自动蹭到宿主当下最强的模型。宿主接入就一个循环:

```bash
chisha eat lunch [--context "想吃辣别太贵"]   # 起一轮 → 回一个 do_llm 信封
# 循环: 回包带 do_llm 就用你的 LLM 跑它 → 喂回 → 直到 status=ready 出 cards
chisha continue --id <rid> --result '<你的 LLM 原始输出>' --step <step_token>
chisha choose   --id <rid> --card <cards[].id> --action accept   # 用户选定
```

`step_token` 由 chisha 发、宿主回显 (不透明), 替代了手抄 correlation / 手包信封。完整接入契约见 [AGENTS.md](AGENTS.md)。

---

## 当前状态

**自用打磨中，核心链路已跑通。** 个人项目，repo 已公开，但定位仍是自用为主、推广随缘。

已经能用的：

- 三阶段推荐链路（L1 召回 → L2 15 维打分 → L3 LLM 精排写理由）
- Web SPA 用户视图 + 反馈系统（差评下一次推荐就降权/剔除，好评优先）
- 长期口味画像（从你的真实反馈统计聚合，可解释、可手编）
- 多轮 refine（自然语言追加约束，如"想吃辣""少米饭""想喝汤"）
- 拷贝即用、自动触发：自包含 skill 文件夹拷进 `~/.claude/skills/`，Claude Code 里说"中午吃啥"即触发；状态存在 `~/.chisha/`，升级不动你的数据
- 开发者自用工具：Sandbox 时光机、trace 持久化、Debug 三模式

**当前限制**（主动收窄，等真要推广时再扩）：

| 项 | 现状 | 后续 |
|---|---|---|
| 城市 / 工区 | 仅深圳湾办公区（334 家 / 22556 菜） | 多工区数据包市场 |
| 饮食方法论 | 仅哈佛餐盘；其它（生酮/增肌/糖控…）走 refine 自由文本兜底 | 可插拔的方法论模板 |
| 宿主 Agent | 仅 Claude Code 有自动触发 skill；其它（Cursor / Codex / OpenClaw…）可手动调 CLI | 多宿主适配器 |
| 数据完整性 | 只校验数据包与引擎兼容性，不验完整性/来源 | 走 GitHub 传输时由 commit hash 兜底；外部镜像需自验 |

详细路线见 [docs/ROADMAP.md](docs/ROADMAP.md)。

---

## 装 (Claude Code 用户, quickstart)

**形态B 自包含 skill (默认, D-105)** — 一个 skill 文件夹 = 代码+数据+vendored 依赖, 拷贝即用, 零全局安装、运行期零联网/零 pydantic。

维护者 (有本仓) 一步构建+安装:

```bash
uv run python -m scripts.build_skill_bundle --out tmp/skill_bundle --install
# → staged 覆盖 ~/.claude/skills/chisha-meal/ (copy-to-temp-first + 备份旧内容); 自包含 bundle 含 scripts/chisha wrapper
python3 ~/.claude/skills/chisha-meal/scripts/chisha onboard --zone shenzhen-bay  # 写 ~/.chisha/profile.yaml + dry start 自检
python3 ~/.claude/skills/chisha-meal/scripts/chisha doctor                       # 自检 python 版本/vendored pyyaml/install_root/manifest
# → 之后 Claude Code 里说 "今天中午吃啥" 即触发 chisha-meal skill
```

拿到别人发的 bundle 文件夹: 直接拷进 `~/.claude/skills/chisha-meal/`, 再跑上面的 onboard/doctor 即可 (无需本仓、无需 pip/uv)。

**环境要求 (诚实边界)**: python3 ≥ 3.11 在 PATH (macOS 自带 3.9 不够); **POSIX-only** (macOS/Linux, core 用 fcntl 文件锁, Windows 除 WSL 外不支持)。

> 形态A (`uv tool install` → 全局 `chisha` 命令) 已于 D-105.1 退役, 接入唯一形态 = 上面的 B 自包含 bundle。state 仍住 `~/.chisha/` (升级不被覆盖)。

**让 AI agent 帮你装**: 把 [AGENTS.md](AGENTS.md) 链接丢给你的 Claude Code, 它会按 spec 自己探测、安装、配置、冒烟测试。
> ⚠️ 当前 AGENTS.md 仍是形态A (`uv tool install`) 的远程自安装协议, D-105.1 退役后**已 stale**, 待 B 形态远程分发协议定型后重写。在那之前请按上面的 B bundle 手动装, 不要走 AGENTS.md 的 uv tool install 步骤。

---

## Dev (改代码 / 跑 Web 调试台 / 改前端)

```bash
# 1. 装依赖 (需要 Python 3.11+, uv, Node 18+)
# D-104: agent-only core 只装轻依赖; 跑调试台/全链路 LLM 需 dev (含 web extra: fastapi/anthropic/openai)
uv sync --extra dev
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
| [AGENTS.md](AGENTS.md) | **AI agent 安装契约** — 让你的 AI 助手帮你装 chisha 时读这个 |
| [CLAUDE.md](CLAUDE.md) | 项目红线 + 常用命令 (coding agent 必读) |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | 跨文件隐含约束 + 反直觉规则 |
| [docs/api.md](docs/api.md) | 前后端 API 契约 |
| [docs/style-guide.md](docs/style-guide.md) | `apps/web/` UI 规范 + 反模式清单 |
| [docs/data-flow.md](docs/data-flow.md) | 数据流全景 (采集→推荐 4 stage, 跨 2 repo) + 已知断裂点 |
| [docs/data-pipeline.md](docs/data-pipeline.md) | 采集后加工流水线: 消费/打标/回填/验收 + 坑 |
| [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md) | 文档维护准则 (改任何文档前必读) |

**草稿 / 历史** (均 frozen 不维护): [docs/proposals/archive/](docs/proposals/archive/) 设计提案存档 (落地后归此, 溯源用); [docs/archive/](docs/archive/) Phase 0 归档。

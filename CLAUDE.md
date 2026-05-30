# chisha · 项目级指令

> 项目名: 今天吃点啥 (chisha) · 个人 AI **原则派点餐执行外包**工具 (L0 方法论 spec / L1 数据 / L2 打分 / L3 LLM 精排)
> 当前阶段: **V1.0 工程里程碑收尾完成** (2026-05-20). 推荐链路 L1/L2/L3 + Web SPA + V1.1 反馈 + L1 真兑现 + sandbox time-travel + trace 持久化 + Debug 三模式 + FastAPI 23 端点 + Refine V2-only (V1 退役 D-096) / Faithful Refine framework (D-080~D-085) + 字段闭包 (D-094.1, V2.1 13 槽) + L2 信号校准 (D-090~092 + D-090.1, 14 维) + Sandbox Lab + 反馈短链路即时生效 (D-098, 差评下次推荐就降权/剔除, score 第 15 维 feedback_recency). 当前定位 **自用为主、推广随缘** (D-097): AI-friendly 接个人 agent (D-074 **Phase 0 已落地**: chisha 零 LLM + one-shot CLI `chisha.agent_cli` + Claude Code reference adapter skill, 智能外置给宿主 agent 的 LLM) + B-001 反馈短链路 (已 D-098 落地). **D-102 (2026-05-28) 可分发共享核心三步落地**: FallbackPlan 统一兜底 (D-102.1) + install/state root 二分 state→`~/.chisha/`+迁移 (D-102.2) + bundle manifest/capability-compat 闸门 (D-102.3); plugin marketplace 打包 + 产物签名留位. **D-104 (2026-05-29) agent-only core 解耦落地**: 推荐核心从 sandbox/web/debug/自调LLM 切干净, ambient provider DI (clock_provider/sandbox_router 两叶子, default==prod 0-diff), 真 slim venv 实跑全链路通过 (边界铁律见 CONTRACTS「agent-only core / extras 边界」+ tests/test_d104_di_boundary). **D-105 (2026-05-30) 形态B 自包含 skill 分发落地**: bundle = core 代码+数据+vendored pyyaml+wrapper, 拷进 `~/.claude/skills/chisha-meal/` 即用 (自包含、零全局安装、运行期零联网/零 pydantic); core 砍 pydantic (collector_contract 改 dataclass+手写校验) + vendoring pyyaml + `build_skill_bundle.py --install` 真 installer + `scripts/chisha` wrapper (py>=3.11 guard); **POSIX-only + py>=3.11** 诚实边界. **D-105.1 (2026-05-30) 形态A 彻底退役**: pyproject `[project.scripts]` + wheel force-include/exclude + test_wheel_content_gate 整删 (接入唯一形态 = B bundle, 回滚靠 git); refine_intent_v2 3 处 fallback print 改 stderr (兑现 stdout 一律 JSON); AGENTS.md 远程自安装协议仍 form-A stale, 待 B 远程分发定型后重写. 裸 python3 隔离全链路实跑通过 (见 CONTRACTS「slim bundle / 形态B installer」). 路线见 [docs/ROADMAP.md](docs/ROADMAP.md).
> 主语言: Python (后端) + TypeScript (前端) · 包管理: uv / npm · 测试: pytest

## 必读(首次接触本项目)

按顺序读:
1. [README.md](README.md) — 项目状态与文档体系总表
2. [docs/PRD.md](docs/PRD.md) — 产品定位
3. [docs/ROADMAP.md](docs/ROADMAP.md) — Phase 路线、已砍清单
4. [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md) — 文档纪律 (改任何文档前必读)
5. [docs/decisions.md](docs/decisions.md) + [docs/CONTRACTS.md](docs/CONTRACTS.md) — 活决策 + Agent 跨文件契约

改 `apps/web/` 用户视图前必读 [docs/style-guide.md](docs/style-guide.md)(D-052~D-055 + D-060/D-066/D-067 锁定的交互不可重设计);改 `apps/debug-ui/` debug 台 SPA 前必读 [apps/debug-ui/README.md](apps/debug-ui/README.md)(独立 Vite SPA / V12 DAG / 5 主题,不并入 apps/web);改 `apps/sandbox-lab/` 前必读 [apps/sandbox-lab/README.md](apps/sandbox-lab/README.md);改 `/api/*` 前必读 [docs/api.md](docs/api.md)。
改推荐链路 / L3 精排:活约束在 [docs/CONTRACTS.md](docs/CONTRACTS.md) (这是单一可信源)。`docs/archive/*_phase0.md` 是 frozen 历史归档, **不作为改代码前的必读**;只有想溯源某条 D-XXX 决策的上下文时才点对应 anchor 进去。

## 文档纪律

- 写产品决策 → `docs/decisions.md`, ≤ 15 行/条, 超过就是塞实施
- 写 agent 跨文件契约 → `docs/CONTRACTS.md`
- 字段表 / schema / prompt 行号 / 参数值 / 测试列表 / commit hash / 文件改动清单一律**不写文档** — git log + grep 代码即权威
- 完整规则 + 反 antipattern 见 [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md)

## 决策编号约定

- D-XXX 编号**全项目共享**,新条目追加到 `docs/decisions.md` 尾部
- 推翻型条目用 D-NNN.M(如 D-046.1)
- superseded 就地标 `[已废弃 by D-NNN]`,不删不挪

## 常用命令

```bash
# 后端 (老调试台 vanilla HTML + 新 SPA 共用)
uv run python -m chisha.debug_server  # :8765 (老:/debug, SPA:/, swagger:/swagger)

# 新 debug 台 SPA (端口 5174, proxy /api → :8765)
cd apps/debug-ui && npm install && npm run dev  # http://127.0.0.1:5174

# Sandbox Lab 白盒时光机 (端口 5175, proxy /api → :8765)
cd apps/sandbox-lab && npm install && npm run dev  # http://127.0.0.1:5175

# 推荐 dry_run
uv run python -m scripts.dry_run --n 5 --meal both

# 召回审计
uv run python -m scripts.inspect_candidates --meal lunch --limit 100

# 打标 (V3 走 OpenRouter,默认 deepseek-v4-flash, D-037)
uv run python scripts/tag_via_api.py shenzhen-bay --limit 50

# 测试
uv run pytest tests/ -q

# L2 trace 严格回归 (D-072.1, 改打分链路必跑)
uv run python -m scripts.baseline_l2_snapshot --out-dir tmp/baseline_traces       # 改前存
uv run python -m scripts.baseline_l2_snapshot --out-dir tmp/baseline_traces_after # 改后存
uv run python -m scripts.compare_traces                                            # 严格对比 (EPSILON=1e-6)
```

## 推荐链路改动红线

跨文件 invariants(L1/L2/L3 链路 / refine / sandbox / trace / 三模式 / 前端可信源)全部沉淀在 [docs/CONTRACTS.md](docs/CONTRACTS.md)。

**high-risk 文件白名单** (单一权威源, 下方「工作流 § Codex 双触点」引用这份):

后端 16 模块 — 改任一 → `regression_risk = high`:
- `chisha/{api,recall,score,rerank,refine,l1_extractor,sandbox,clock,data_root,trace_store,debug_what_if,web_api,feedback_signal,agent_orchestration,state_root,manifest,core_api_helpers}.py`
- (D-104: `core_api_helpers` = agent card/session/trace-final 格式化单源 (改前读 CONTRACTS「agent-only core / extras 边界」段). `clock_provider`/`sandbox_router` 是零依赖 DI 叶子, **不进**白名单 (低 churn); 但改 clock/data_root/sandbox 的 provider 注册时同读该段, 改完跑 `tests/test_d104_di_boundary.py` 守边界)
- (D-102: `state_root` = install/state 路径解析单一权威源 (改前读 CONTRACTS「install/state root 二分」段); `manifest` = 数据产物↔引擎兼容闸门 (CONTRACTS「数据产物↔引擎 manifest 闸门」段). `state_migrate` 是一次性迁移器, **不进**白名单 (同 collector_contract/non_dish_rules 先例: 非热路径))
- (D-074 agent 面 `agent_{cli,protocol,round_store,choose,skill_init}.py` = chisha 零 LLM 协议层, 改前读 CONTRACTS「Agent CLI 协议」段; 单独改不进 baseline 严格回归网, 与 prepare_candidates/recall/score 同时改 → high)

前端 — 改 `apps/{web,debug-ui}/src/**` 任意 .tsx / .css / vite.config.ts:
- 跟后端 API contract 同时改 → `high`
- 单独改 → `medium` (前端不进 baseline_l2_snapshot 严格回归网, 但触发"前端自测强制")

stuck override 护栏: `high` (含 unknown 默认) 严禁 override; `low/medium` 允许过度谨慎通过 → `done_with_disagreement`。改了文件名 / 加新核心模块只改这一处。

**V1.0 后仍不做** (scope creep 防护): OpenClaw 接入 (下一步) / screener 设计 / 第二份 methodology spec / L1 词表扩 / 调试台进一步 React 化整合 / 产物签名完整性体系定型 / plugin marketplace 打包 — 详见 CONTRACTS.md「范围红线」. (data zone 可分发已由 **D-102 落地**: install/state 二分 + bundle manifest/compat 闸门, 见 decisions D-102 系列)

## 前端自测(强制,改 apps/web 或 apps/debug-ui 或 apps/sandbox-lab 必走)

本项目装了 `chrome-devtools-mcp` (user scope, 2026-05-16). 改 `apps/web/src/**` (用户视图 :5173) / `apps/debug-ui/src/**` (调试台 SPA :5174) / `apps/sandbox-lab/src/**` (Sandbox Lab :5175) 任意 `.tsx` / `.css` / `vite.config.ts` / proxy 后, **必须用 `mcp__chrome-devtools__*` 工具自驱浏览器验证**,不许只跑 vitest/tsc 就宣告完成,也不许让志丹去当眼睛。

最小流程:

1. 确认两个 server 在跑:后端 `uv run python -m chisha.debug_server` (:8765) + Vite (`apps/web` :5173 或 `apps/debug-ui` :5174)
2. `mcp__chrome-devtools__navigate` 打到改动涉及的路由
3. 走一遍 golden path + 至少一个 edge case
4. 看 `console_messages` 有没有 error/warn,看 `network_requests` 有没有 4xx/5xx
5. 必要时截图反馈;**跑不通就直说"Vite 没起来 / 后端 502 / 没验"**,不要假装通过

不适用:纯后端 (`chisha/**` Python) / 脚本 (`scripts/**`) / 测试 (`tests/**`) 改动 — pytest + baseline_l2_snapshot 已经够。

## 工作流: Claude Code 原生 + Codex 双触点

默认走 Claude Code 原生 TaskCreate todolist + Agent subagent. 两个关键点强制拉 Codex 共商:

1. **方案设计敲定前** → 调 `codex:rescue` skill 一起讨论
   - 触发: design plan / 架构选型 / **改 high-risk 16 文件白名单前**
2. **git commit 前** → 调 `codex:rescue` 做 diff review
   - 触发: 改 high-risk 16 文件白名单时强制; 其他场景志丹可说"跳过 codex review"

high-risk 16 文件白名单 + 前端高风险条件单一权威源在 § 推荐链路改动红线.

## 提醒

- 改完任意 D-XXX 后, **主动检查** README / ROADMAP / CONTRACTS 是否要同步更新.
- 阶段性收口主动调用 `neat-freak` skill, 带一句"≤ 15 行原则, 讲不完就丢弃"防过度沉淀.

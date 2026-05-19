# chisha · 项目级指令

> 项目名:今天吃点啥 (chisha) · 个人 AI **原则派点餐执行外包**工具 (L0 方法论 spec / L1 数据 / L2 打分 / L3 LLM 精排)
> 当前阶段:**Phase 0 工程侧收尾**(D-001~D-085,2026-05-18)— 推荐链路 L1/L2/L3 全跑通 + Web SPA + V1.1 反馈 + L1 真兑现(LLM 抽取)+ sandbox time-travel + trace 持久化 + Debug 三模式(Replay / What-if / Live)+ FastAPI 23 端点 + **Refine v2 / Faithful Refine framework 重构**(D-080~D-085: L0 三分 + RefineIntentV2 多 slot + reference resolver + subtype diversify + 方法论状态条 + L3 narrative)。当前 5 步推进路线见 [docs/ROADMAP.md "Phase 0 收尾路线"](docs/ROADMAP.md)。
> 主语言:Python (后端) + TypeScript (前端) · 包管理:uv / npm · 测试:pytest

## 必读(首次接触本项目)

按顺序读:
1. [README.md](README.md) — 项目状态与文档体系总表
2. [docs/PRD.md](docs/PRD.md) — 产品定位
3. [docs/ROADMAP.md](docs/ROADMAP.md) — V1/V2/V3 边界、已砍清单
4. [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md) — 文档纪律(改任何文档前必读)
5. [docs/decisions.md](docs/decisions.md) + [docs/CONTRACTS.md](docs/CONTRACTS.md) — 替代已归档的 DESIGN / DECISIONS / IMPL_LOG

改 `apps/web/` 用户视图前必读 [docs/style-guide.md](docs/style-guide.md)(D-052~D-055 + D-060/D-066/D-067 锁定的交互不可重设计);改 `apps/debug-ui/` debug 台 SPA 前必读 [apps/debug-ui/README.md](apps/debug-ui/README.md)(D-075 独立 Vite SPA / V12 DAG / 5 主题,不并入 apps/web);改 `/api/*` 前必读 [docs/api.md](docs/api.md)。
改推荐链路 / L3 精排:历史背景在 [docs/archive/DECISIONS_phase0.md](docs/archive/DECISIONS_phase0.md) + [docs/archive/RECOMMEND_PRINCIPLES_phase0.md](docs/archive/RECOMMEND_PRINCIPLES_phase0.md) + [docs/archive/L3_RERANK_REDESIGN_phase0.md](docs/archive/L3_RERANK_REDESIGN_phase0.md),活约束在 `docs/CONTRACTS.md`。

## 文档纪律(强制 · 2026-05-16 重构后)

文档按"读者"分四桶:

| 桶 | 文件 | 写什么 | 写多长 |
|---|---|---|---|
| 产品决策(给用户) | `docs/decisions.md` | 产品方向 / 推翻历史 / 没选 B 方案的原因 | **3-5 行**,> 15 行说明你在写实施,停下 |
| Agent 契约(给 Claude/Codex) | `docs/CONTRACTS.md` | 跨文件隐含约束 / 反直觉规则 / 系统级 invariant | 单条 ≤ 10 行,全文 ≤ 200 行 |
| Agent 红线(给 Claude/Codex) | `CLAUDE.md`(本文件) | 命令 / avoid 清单 / 当前阶段焦点 | 全文 ≤ 100 行 |
| 历史归档(不维护) | `docs/archive/*_phase0.md` | Phase 0 历史 | 只读 |

**不写**(无论多重要,代码已有): 字段表 / schema keyset / prompt 行号 / 参数值 / 测试列表 / batch 数 / commit hash / 文件改动清单 — git log + grep 代码即权威。

详见 [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md)(Wave 4 重写)。

## 决策编号约定

- D-XXX 编号**全项目共享**,新条目追加到 `docs/decisions.md` 尾部
- 推翻型条目用 D-NNN.M(如 D-046.1)
- superseded 就地标 `[已废弃 by D-NNN]`,不删不挪

## 常用命令

```bash
# 老调试台 (D-039 vanilla HTML) + 新 debug-ui (D-075 Vite SPA) 共用同一后端
uv run python -m chisha.debug_server  # :8765 (老:/debug, SPA:/, swagger:/swagger)

# 新 debug 台 SPA (D-075, 端口 5174, proxy /api → :8765)
cd apps/debug-ui && npm install && npm run dev  # http://127.0.0.1:5174

# Sandbox Lab 白盒时光机 (D-088, 端口 5175, proxy /api → :8765)
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

跨文件 invariants(L1/L2/L3 链路 / refine / sandbox / trace / 三模式 / 前端可信源)全部沉淀在 [docs/CONTRACTS.md](docs/CONTRACTS.md)。改 `chisha/{api,recall,score,rerank,refine,l1_extractor,sandbox,clock,data_root,trace_store,debug_what_if,web_api}.py` 或 `apps/debug-ui/src/**` 前**必读**。

**Phase 0 内不做**(scope creep 防护): data zone 拆包发布 / OpenClaw 接入(待 D-074 落定) / screener 设计 / 第二份 methodology spec / L1 词表扩 / 调试台进一步 React 化整合 — 详见 CONTRACTS.md「范围红线」。

## 前端自测(强制,改 apps/web 或 apps/debug-ui 或 apps/sandbox-lab 必走)

本项目装了 `chrome-devtools-mcp` (user scope, 2026-05-16). 改 `apps/web/src/**` (用户视图 :5173) / `apps/debug-ui/src/**` (D-075 SPA :5174) / `apps/sandbox-lab/src/**` (D-088 SPA :5175) 任意 `.tsx` / `.css` / `vite.config.ts` / proxy 后, **必须用 `mcp__chrome-devtools__*` 工具自驱浏览器验证**,不许只跑 vitest/tsc 就宣告完成,也不许让志丹去当眼睛。

最小流程:

1. 确认两个 server 在跑:后端 `uv run python -m chisha.debug_server` (:8765) + Vite (`apps/web` :5173 或 `apps/debug-ui` :5174)
2. `mcp__chrome-devtools__navigate` 打到改动涉及的路由
3. 走一遍 golden path + 至少一个 edge case
4. 看 `console_messages` 有没有 error/warn,看 `network_requests` 有没有 4xx/5xx
5. 必要时截图反馈;**跑不通就直说"Vite 没起来 / 后端 502 / 没验"**,不要假装通过

不适用:纯后端 (`chisha/**` Python) / 脚本 (`scripts/**`) / 测试 (`tests/**`) 改动 — pytest + baseline_l2_snapshot 已经够。

## 提醒(给未来的 Claude Code)

- **文档体系 2026-05-16 重构过**:DECISIONS/IMPL_LOG/DESIGN 已归档,新决策只写 `docs/decisions.md`,且 ≤ 15 行/条。超过就是你在写实施,删掉重写
- 改完任意 D-XXX 后,**主动检查** README / ROADMAP 是否要同步更新
- 阶段性收口时主动调用 `neat-freak` skill,但要带一句"≤ 15 行原则,讲不完就丢弃"防它过度沉淀

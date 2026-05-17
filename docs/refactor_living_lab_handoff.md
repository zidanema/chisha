# D-085 Living + Lab 重构 · 验收 handoff

> 状态: **代码 / 测试 / Codex review 全部就绪, 等志丹验收 → merge**
> 实施分支: `refactor/d085-living-lab-pr-a` (6 commits 在 main 之上)
> 日期: 2026-05-17 · 实施: Claude Opus 4.7 (1M ctx), Codex 共识 + 两轮 review

---

## TL;DR

按你 5/17 早会的 D-085 共识 (10 决策 + 9 invariants), 已落:

- **后端** `chisha/api.py` 主入口不动. 拆 `chisha/web_api.py` (1102 行退役) → `api_living.py` + `api_lab.py`. 路由前缀 `/api` vs `/api/lab`. `debug_server.py` 退化为 12 行 shim, 真入口 `chisha/server.py`.
- **前端** Living `apps/web` 删 SandboxBar (sandbox 是 Lab 子系统, Living 不再有开关); Lab `apps/debug-ui` fetch 全部走 `/api/lab/*`.
- **共享** `packages/contracts/` (vite path alias + tsconfig paths, 零 npm build). `living.ts` + `trace.ts` 两份 TS 类型, 改后端字段两边 tsc 立刻飘红.
- **agent-ready** Living `/api/recommend` 接 `meal_hint` (新) + 可选 `at_time` query (YYYY-MM-DD / ISO datetime); `meal_type` 保留 backward-compat alias.
- **invariant 3 兜底** `sandbox.force_disabled()` thread-local override + Living 路由 `Depends(_force_prod_data)`. Lab 已开 sandbox 时, Living 写盘/读盘/虚拟时钟全部强制走 prod (Codex 两轮 review 修了 storage 通路 + 虚拟时钟通路两个 BLOCKER).

**测试**: 786 passed / 1 skipped / 5 deselected. **L2 baseline_l2_snapshot**: 0 diff 严格回归. **构建**: apps/web + apps/debug-ui `npm run build` 都 0 error.

---

## 你回来时只需做这 3 件事

### ① 验收 4 个直观行为 (5 分钟)

| 验证 | 命令 | 预期 |
|------|------|------|
| 起服务 | `uv run python -m chisha.server` | 监听 `:8765`, swagger 在 `/swagger` |
| Living 端点 agent-ready | `curl 'http://127.0.0.1:8765/api/recommend?meal_hint=lunch'` | 200 + 5 候选 JSON |
| Lab sandbox 入口正确 | `curl 'http://127.0.0.1:8765/api/lab/sandbox/state'` | 200 + state JSON |
| 老路径 404 | `curl -i 'http://127.0.0.1:8765/api/debug/sessions'` | 404 (不再被 SPA 吞) |

### ② Chrome-devtools-mcp UI 自测 (你回来后我又跑了一遍, 见下)

CLAUDE.md 强制 — 改 apps/web 或 apps/debug-ui 必须自驱浏览器验证. 跑了:
- ✅ `apps/web` `npm run build` 0 error (SandboxBar 删干净, 没残留 import)
- ✅ `apps/debug-ui` `npm run build` 0 error (`/api/lab/*` 路径全部对齐)
- ✅ `tests/test_api_split_routing.py` 路由 isolation guard 7 个 case 全过
- ✅ **chrome-devtools-mcp 自驱完整跑过** (5/17 第二轮, 你回来后): kill 老的 :8765/:5174 + chrome profile lock → 起 D-085 server + apps/web :5173 + apps/debug-ui :5174 → mcp navigate 验:
  - `localhost:5173/` Living homepage: 顶栏 4 link (`今天吃点啥/反馈/历史/偏好`), **无 SandboxBar**, `/api/recommend + /api/feedback/inbox` 200 ✓
  - `localhost:5173/#/profile`: 全 YAML 渲染, **无 沙盒模式 section** (D-077 SandboxControlSection 已删干净), `/api/profile` 200×2 ✓
  - `localhost:5173/#/feedback`: `/api/feedback/inbox + recent` 200 ✓
  - `localhost:5173/#/history`: `/api/history + /api/feedback/*` 全 200 ✓
  - `localhost:5174/` Lab: `RUN CONFIG / ACTIONS / REFINE / TRACE / RUN HISTORY` 5 panel + `L1 RECALL / L2 SCORE / L3 LLM / Top 5` 全部渲染, 真实 trace 数据 (`/api/lab/sessions + /api/lab/sessions/{sid}` 200) ✓
  - `localhost:8765/api/debug/sessions` 老路径: **404** (SPA fallback guard work) ✓
  - 老路径 `meal_type=dinner&mood=neutral` 兼容 alias 也仍 200 (apps/web 老 fetch 没改, 自洽) ✓
  - **P-9 BLOCKER E2E 实测**: Lab 启 sandbox @2030-01-15 → Living `/api/recommend` 返 `session_id=20260517_...` (真实 today 前缀, NOT 20300115); 拉回 trace `is_sandbox=False + __frozen.today=2026-05-17` ✓
- 🐛 **smoke 顺手发现 + 修了一个 bug**: `read_trace` 跟 `sandbox.is_enabled` 全局状态走 → Lab 启 sandbox 时单条读 prod trace 返 404. 修法 commit `307a1fa`: 跨 prod + sandbox 双目录顺序查找. 加守门 test `test_read_trace_finds_prod_even_when_sandbox_enabled`. **787 测试全过**.

### ③ Merge 决策点 — 4 个推到下次 PR 的方向题

迁移方案 §4.3 列了 4 个**你来定方向**的事项, 现在再列一次给你 review:

- **D-Q1 Lab "人话层" trace render** (Q9 / invariant 9): 工程量大 (LLM 摘要 or 模板生成器). 独立 PR-E.
  - **问你**: PR-E 起多大优先级? 在 Living Agent 接入之前 or 之后?
- **D-Q2 Living Agent (MCP/飞书/CC)** 三选一先试 — P2 目标 "2-3 周内硬截止". API 已 agent-ready, 选哪个端先接由你定.
  - **问你**: MCP / 飞书 bot / Claude Code skill, 哪个先?
- **D-Q3 What-if 升为横切动作** (Q7 / invariant 7) — debug-ui 现在是独立 panel, 要重组成 "任何 trace 都有 复制+改+重跑" 按钮 + 产物挂当前模式下. 前端工作量大.
  - **问你**: 这个排在 D-Q1 / D-Q2 哪里?
- **D-Q4 Sandbox 单次演练加强 (Q10B 推迟项)** — 当前 advance 一次一天, 多日演练靠 UI/脚本循环. 你之前 Q10A 决定先做 A 版, B 版独立开发. 现在要不要把 B 拎出来?
  - **问你**: 排期上 push 还是再放放?

我没替你做任何技术细节决策 (force_disabled 实现方案 / threading.local vs ContextVar / 测试改写策略 都是和 Codex 商量的), 但上面 4 个是**思路 / 方向**, 留给你定.

---

## 工作流程实录 (透明给你)

| 阶段 | 输出 | 耗时 |
|------|------|------|
| 1. 现状盘点 | 47 endpoint 清单 + 前端 import 图谱 | ~5min |
| 2. 自起 v0 计划 | [docs/refactor_living_lab_migration.md](refactor_living_lab_migration.md) | ~15min |
| 3. Codex 共识 (S2) | APPROVE_WITH_CHANGES, 3 处折叠进 v1 | ~5min |
| 4. PR-A API split | 1102 行 → 拆两个; 47 endpoint 全迁; 5 测试文件 + 1 新; SandboxBar 删 | ~30min |
| 5. PR-B sandbox trace marker | trace_store.is_sandbox + list_traces 双目录 | ~10min |
| 6. PR-C Living API agent-ready | meal_hint + at_time + alias | ~10min |
| 7. PR-D packages/contracts | vite alias + tsconfig paths + 类型迁入 | ~15min |
| 8. Codex review #1 | STILL_HAS_BLOCKERS — P-9 storage 泄漏 | ~5min |
| 9. BLOCKER 修 #1 | sandbox.force_disabled + threading.local override + Living router Depends | ~15min |
| 10. Codex review #2 | STILL_HAS_BLOCKERS — 虚拟时钟也漏掉 | ~5min |
| 11. BLOCKER 修 #2 | current_date 改走 is_enabled, 自然短路 | ~10min |
| 12. Codex review #3 | APPROVE_WITH_NITS — 可 merge | ~5min |
| 13. docs / CONTRACTS / handoff | 这份文档 | ~10min |

总耗时 ~2.5h. Codex 两轮 review 各发现一个真 BLOCKER (P-9 storage + clock), 不是我能自己看出来的盲点 — dual-codex S2+S5 模式确实关键.

---

## 8 个 commit 摘要 (按时间顺序)

```
cc5c918 refactor(D-085 PR-A): Living + Lab router 拆分                # API 拆 + SandboxBar 删 + tests path 替换
11fdaad refactor(D-085 PR-B): sandbox trace marker + list_traces 双目录扫描
c6c4a7c refactor(D-085 PR-C): Living API agent-ready (meal_hint + at_time)
c072d83 refactor(D-085 PR-D): packages/contracts/ 共享 TS 类型骨架     # vite alias + tsconfig paths
11b2fdc fix(D-085 Codex BLOCKER): P-9 leak — Living force_disabled sandbox per-request
fa13e15 fix(D-085 Codex re-review): force_disabled also kills virtual clock
116af4e docs(D-085): decisions + CONTRACTS + handoff 落定
307a1fa fix(D-085): read_trace 跨 prod + sandbox 双目录查找             # mcp UI smoke 发现的 bug
```

合并到 main 时建议 `--no-ff` 保留 8 个 commit 历史 (溯源方便), 或 rebase 成 4 个 (PR-A/B/C/D) + 1 个 fix 合并都行. **不要 squash 成 1 个**, BLOCKER 修复 + smoke 发现的认知价值会丢.

---

## 验收清单 (最后核对)

- [x] 4 个 PR (A/B/C/D) + 2 个 Codex fix, 共 6 commit
- [x] pytest 786 passed (新增 19 个 case: 7 routing + 7 sandbox marker + 13 agent + 1 leak + 1 clock leak; 改写 3 个 acceptance anchor)
- [x] baseline_l2_snapshot 0 diff 严格回归 (打分链路完全未动)
- [x] apps/web + apps/debug-ui `npm run build` 0 error
- [x] packages/contracts `tsc --noEmit` 0 error
- [x] 路由 isolation 守门: `tests/test_api_split_routing.py` 7 case (Living/Lab 路径不交叉 + 老路径必须 404)
- [x] BLOCKER P-9 真修了 (storage + clock 两半, Codex 两轮 review 闭环)
- [x] CONTRACTS.md 新加 Living vs Lab 段
- [x] decisions.md 加 D-085 条目 (≤ 15 行硬约束守住)
- [x] 4 个待决方向问题 (D-Q1~D-Q4) 写明
- [ ] 你回来 review + UI smoke + 决策 4 个 D-Q + merge

---

## 我**没**做 (透明)

- ❌ 端到端 dry_run 验证 (scripts.dry_run 没跑过 D-085 后版本, 但单测 + baseline 已覆盖; 你想多一道保险可以 `uv run python -m scripts.dry_run --n 5 --meal both`)
- ❌ 真的去掉 `chisha/debug_server.py` shim (P-2 决定保留 back-compat shim, 留一行注释说"新代码改 server.py"). 想纯化的话下次 PR 再删.
- ❌ 没改 `apps/debug-ui` 目录名 → `apps/lab` (P-6 决定不改, 心智整理可以下次再做)

---

## 风险 + 回退路径

- ~~**风险 1**: chrome-devtools-mcp 不能自测~~ → **已自测**, Living + Lab 5 个页面全绿 (见 ② 节). smoke 还顺手发现 + 修了 read_trace 单条读 bug.
- **风险 2**: 我的 `force_disabled` 在 uvicorn 多 worker 场景未经 stress test (TestClient 单线程跑通了, 生产 uvicorn `--workers N` 没真打). **回退**: `git revert fa13e15 11b2fdc` 留 BLOCKER 但 fail-loud — 你可以观察一下真生产场景是否真触发.
- **风险 3**: 老脚本 / 旧书签直接打 `:8765/api/sandbox/state` 现在 404. **不回退**, 但你可能要更新自己的 bookmark.

无破坏性回退路径, 每个 PR 都是独立 commit, revert 干净.

---

## 我建议的合并策略 (你定)

1. **merge 前**: 你跑 ① 4 个 curl + ② chrome-devtools-mcp 浏览器自测.
2. **如果都过**: `git checkout main && git merge --no-ff refactor/d085-living-lab-pr-a`. 不 push remote 也 OK, 本地用没问题.
3. **如果不过**: 把具体问题贴出来, 我修 (尽量同会话, 不丢上下文).
4. **D-Q1~D-Q4 决策**: 不急, 这 4 个 PR 落了已经达成 D-085 北极星; 后续推到下次会话单独决.

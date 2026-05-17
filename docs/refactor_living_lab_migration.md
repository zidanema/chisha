# Living + Lab 重构 · 迁移方案 (D-085)

> 上游 context: [refactor_living_lab.md](refactor_living_lab.md) 目标 / 10 决策 / invariants
> 状态: **v1 - Codex consensus (APPROVE_WITH_CHANGES) 已折叠** · 实施分 4 PR
> 作者: Claude (Opus 4.7) · 2026-05-17

---

## 0. 重构指导原则

1. **不动行为, 只动结构**: 推荐链路 (L1/L2/L3/refine) 输出必须 baseline_l2_snapshot 严格回归过 (EPSILON=1e-6)
2. **不破 invariants**: CONTRACTS.md 现有 28 条全部继续成立; 新增条目走 §6 落地
3. **不做范围外**: 范围红线 §11 列出明确"不在本次 PR 内做"的清单
4. **可回滚**: 每个 PR 独立可 revert, 不混合关注点

---

## 1. 现状盘点 (apps + chisha)

### 1.1 后端 (chisha/)

| 文件 | 当前职责 | 重构后归属 |
|------|----------|-----------|
| `api.py` (24KB) | `recommend_meal()` 主入口 + trace 构造 | 共享内核, **保持不动** |
| `web_api.py` (41KB, 47 endpoint) | **混入**: Living 端点 (recommend/refine/accept/skip/profile/feedback/history) + Lab 端点 (debug/sessions, debug/what_if, sandbox/*, sandbox/inspect) | **拆分** → `api_living.py` + `api_lab.py` |
| `debug_server.py` (5KB) | FastAPI app + `/api/debug_recommend` + `/api/compare_moods` + SPA 托管 | Lab 路由迁出 → `api_lab.py`; 此文件改名 `server.py` 仍是单一进程入口 (向后兼容保留 `debug_server` 别名) |
| `debug_recommend.py` (37KB) | 老 D-039 调试台用 (instrumented 管道) | **保持不动**, 老 HTML 还在用 |
| `debug_what_if.py` (17KB) | What-if 重跑核心 | 共享内核, 保持不动; Lab 路由用 |
| `sandbox.py` (7KB) + `clock.py` | sandbox 时钟 / 数据根 | 共享内核, 保持不动 |
| `trace_store.py` (14KB) | trace 读写 | **改**: 写入 `is_sandbox` 字段; `list_traces` 加 `include_sandbox` filter (默认 False) |

### 1.2 前端 (apps/)

| App | 端口 | 当前 | 重构后 |
|-----|------|------|--------|
| `apps/web/` (Living) | 5173 dev / `/` prod | `App.tsx + 5 page + 13 component + lib/types.ts(237行)` | 不动结构, 只换 types 来源 (`@chisha/contracts`) |
| `apps/debug-ui/` (Lab) | 5174 dev | `App.tsx + 10 panel + 9 component + api/backend-types.ts(498行)` | 不动结构, 只换 types 来源 + adapter 用 client helper |

**两边 TS 类型重合度低** (debug-ui 是深层 trace schema, web 是 user-facing 响应), 真正共享的是 `RecommendResponse / Candidate / Dish / RestaurantRef / MealType / FeedbackPayload` 等顶层契约. **不强制把所有类型挪过去**, 只挪两边都用的部分 + 共享 fetch helper.

### 1.3 路由清单 (重构前 47 条)

```
Living (要拆到 api_living.py):
  GET  /api/recommend          GET  /api/profile           POST /api/refine
  POST /api/accept             PUT  /api/profile           POST /api/skip
  POST /api/profile            GET  /api/history
  GET  /api/feedback/inbox     POST /api/feedback/snooze   POST /api/feedback/stop
  GET  /api/feedback/recent    POST /api/feedback          GET  /api/feedback/{sid}/record
  POST /api/feedback/{sid}/comments    GET  /api/feedback/{sid}
  POST /api/long_term_prefs/refresh

Lab (要拆到 api_lab.py):
  GET  /api/debug/sessions     GET  /api/debug/sessions/{sid}
  POST /api/debug/what_if
  POST /api/sandbox/init       POST /api/sandbox/advance   POST /api/sandbox/reset
  POST /api/sandbox/disable    GET  /api/sandbox/state     GET  /api/sandbox/inspect
  POST /api/debug_recommend (debug_server.py)   POST /api/compare_moods (debug_server.py)
```

**注意**: `sandbox/*` 当前归 web_api.py 因为 Living web 有 SandboxBar 开关. **不挪**——sandbox 切换是 Lab 行为, Living 在 invariants 1+3 后**不该**碰 sandbox 状态. 见 §4.3 决策点 P-2.

---

## 2. 目标架构 (后端 + 前端)

### 2.1 后端

```
chisha/
├── api.py                  # recommend_meal() 共享内核
├── api_living.py     [NEW] # /api/* Living 端点 — JSON 自闭包, agent-ready
├── api_lab.py        [NEW] # /api/lab/* Lab 端点 — debug/sessions, what_if, sandbox/*
├── server.py         [REN] # 单一 uvicorn 入口, mount 两个 router
│                          # (`debug_server.py` 保留别名 import for back-compat)
├── trace_store.py    [MOD] # is_sandbox marker + list_traces filter
├── debug_recommend.py     # 老调试台后端, 保持不动
├── debug_what_if.py       # What-if 内核, api_lab.py 调
└── ... (sandbox / clock / 其余 21 文件) 保持不动
```

### 2.2 前端

```
packages/contracts/    [NEW] # workspace root: pnpm/npm workspaces
└── src/
    ├── living.ts            # MealType, Mood, RecommendResponse, Candidate, ...
    ├── feedback.ts          # FeedbackPayload, FeedbackRecord, GutVal, DimVal
    ├── trace.ts             # BackendDebugTrace, BackendL2Combo, ... (Lab 共享)
    ├── client.ts            # fetchLiving(path, opts) / fetchLab(path, opts) helper
    └── index.ts             # 重导出

apps/web/                    # tsconfig.paths: "@chisha/contracts" → packages/contracts/src
└── src/lib/types.ts         # 改为 re-export from "@chisha/contracts/living"

apps/debug-ui/               # 同上
└── src/api/backend-types.ts # 改为 re-export from "@chisha/contracts/trace"
```

**路径策略**: 不上 npm, 走 vite alias + tsconfig path. workspace root 起 `package.json` 但 `packages/contracts` 不参与 npm install (纯 source 引用).

### 2.3 URL 不变, 路径变

| 旧路由 | 新路由 | 为什么 |
|--------|--------|--------|
| `GET /api/recommend` | `GET /api/recommend` (保留) | Living 端点不动, agent 已经用了 |
| `GET /api/debug/sessions` | `GET /api/lab/sessions` (**改路径**) | 走 `api_lab.py` 时挂 `prefix=/api/lab`, 跟 Living 物理隔离, 后续 Lab 内部加端点不与 Living 冲突 |
| `POST /api/debug/what_if` | `POST /api/lab/what_if` (**改**) | 同上 |
| `POST /api/sandbox/init` etc. | `POST /api/lab/sandbox/init` etc. (**改**) | sandbox 是 Lab 子系统 |
| `POST /api/debug_recommend` | `POST /api/lab/debug_recommend` (**改**) | 老调试台 HTML 同步改 fetch 路径 |
| `POST /api/compare_moods` | `POST /api/lab/compare_moods` (**改**) | 同上 |

**Lab UI 必须同步改 fetch base.** apps/debug-ui/src/api/client.ts 把 `/api/...` 全部走 `/api/lab/...` 或 `/api/...` 按端点分流.

**Living UI 不动.** apps/web/src/lib/api.ts 保持 `/api/...`.

**老调试台 HTML (`chisha/static/debug.html`) 也要改**, 但只是字符串替换, 范围小.

---

## 3. PR 拆分 (4 个 + 后续 backlog)

| PR | 名字 | 改动文件 (估) | 测试 | 风险 |
|----|------|--------------|------|------|
| **PR-A** | API split (Living / Lab) | (1) `chisha/web_api.py` → `api_living.py` + `api_lab.py`; (2) `chisha/debug_server.py` 改 import + 挪 `/api/debug_recommend` `/api/compare_moods` 到 `api_lab.py` (`/api/lab/debug_recommend` 等); (3) `chisha/static/debug.html` 3 处字符串替换 (`/api/debug_recommend` x2 + `/api/compare_moods` x1); (4) `apps/debug-ui/src/api/client.ts` + `adapter.ts` 全部走 `/api/lab/*`; (5) `apps/web` 删 `SandboxBar.tsx` + `lib/sandbox.ts` + `useChishaState.tsx` sandbox state + `App.tsx` sandbox 触发 + `ProfilePage.tsx` 引用 (Codex 提示比预估大, ~150-200 行); (6) tests 路径替换: `test_d079_pr2_endpoints.py` + `test_web_api_sandbox.py` + `tests/conftest.py` (`/api/sandbox/state`) | 现有所有 web_api 测试在新 path 下绿 + 新增 `test_api_split_routing.py` (验证 Living/Lab 路由严格不交叉) | **大** (L) — 路径变 47 个 + 前端 SandboxBar 删除 |
| **PR-B** | Sandbox trace marker | trace_store.py: `write_trace` 加 `is_sandbox` top-level; `list_traces(include_sandbox=False)` 默认只扫 prod, True 时扫两个目录 + merge by mtime; tests | test_sandbox_trace_marker.py | **中** (M) |
| **PR-C** | Living API agent-ready | api_living.py `/api/recommend`: `meal_hint` 新参数, **`meal_type` 保留 alias** (backward compat with apps/web); 可选 `at_time` query (YYYY-MM-DD or ISO datetime) → 走 `clock` 入口; OpenAPI doc | test_living_api_agent.py (meal_hint + meal_type alias + at_time 覆盖) | **小** (S) |
| **PR-D** | packages/contracts 骨架 | packages/contracts/{package.json, tsconfig.json, src/*.ts}; apps/web + apps/debug-ui tsconfig.json + vite.config.ts; 替换 import 路径 | apps/web npm run build 绿; apps/debug-ui npm run build 绿; tsc --noEmit 绿 | **中** (M) — vite/tsc 配置坑多 |

每个 PR 独立 commit, 中间跑全套 pytest + baseline_l2_snapshot. PR-A 体量最大, 必须**机械式重命名**, 不重写逻辑.

---

## 4. 决策点 (Codex 共识 / 自决 / 留给志丹)

### 4.1 已决 (Claude + 已有 invariant 支持)

- **P-1 [自决] PR 顺序**: A → B → C → D. 后端先稳, 前端 contracts 最后 (依赖 A 暴露的路径).
- **P-3 [自决] sandbox 路由前缀**: `/api/lab/sandbox/*`. 理由: invariants 3+5+6, sandbox 是 Lab 子系统; Living UI 移除 sandbox 开关交互 (UI 改动 ≤ 10 行, 见 P-5).
- **P-4 [自决 · Codex 修正]** `is_sandbox` 字段双写:
  - **写入**: trace top-level boolean, 来自 `data_root.is_sandbox(root)` (or `sandbox.is_enabled(root)`); 为 trace 自描述, 方便 Replay
  - **目录隔离**: `data_root.recommend_trace_dir(root)` 已按 sandbox state 切换到 `logs/sandbox/recommend_trace/` (已存在行为). PR-B **不动**目录策略
  - **`list_traces` 双路查询**: 加 `include_sandbox: bool = False` 参数. 默认只扫 prod 目录; True 时扫两个目录 + 用 `is_sandbox` 字段区分. Lab 端点暴露 `include_sandbox=true`
- **P-7 [自决] 老 trace 兼容**: `is_sandbox` 缺省 = False (生产 trace 早期未写). 不 bump TRACE_SCHEMA_VERSION (派生字段, 不破读路径).
- **P-9 [自决 · Codex 提出] Phase 0 已知缺陷**: Living API 仍**全局**遵循 `sandbox.is_enabled(root)` (因为 `data_root` / `clock` 都是全局状态). 不在本 PR 修. **缓解**: PR-A 删 Living UI 的 SandboxBar, 只 Lab UI 能开 sandbox. 单用户场景下志丹"在 Lab 跑 sandbox 时不去 Living 调 API"是可接受 invariant. 修正方案 (plumb 显式 `sandbox: bool` 参数贯穿 data_root/clock) 留 Phase 1 独立决策号.

### 4.2 待 Codex 共识 (技术细节, S2 走完后冻结)

- **P-2 [Codex] `web_api.py` 该删还是保留 shim?** 倾向**删**: 47 端点全挪走后 web_api.py 是空壳, 留 shim 反而让"Living vs Lab 边界"在代码上不清晰. 但 `from chisha.web_api import router as web_router` 在测试里有 N 处引用 (需 grep 确认), 一并改更干净.
- **P-5 [Codex] Living web 移除 SandboxBar 时机**: 选项 (a) PR-A 内顺手剪 (前端 SandboxBar.tsx + ChishaCtx sandbox state 全删) — 工作量 ~50 行; (b) 延后到 PR-D, PR-A 先让 SandboxBar fetch `/api/lab/sandbox/state` (跨边界临时妥协). 倾向 **(a)**, invariants 6 不该让 Living 跨 Lab 拿状态.
- **P-6 [Codex] `apps/debug-ui` 是不是该改名 `apps/lab/`?** 倾向**不改**: debug-ui 目录已落盘半年 (D-075), grep 命中点多; 改名是纯心智整理, 不动行为. 文档里说"Lab = apps/debug-ui" 即可.
- **P-8 [Codex] contracts 包的依赖关系**: 选 vite path alias (零 build) vs 真正的 workspace package (`npm link`/symlink). 倾向 **path alias**, Phase 0 不上 npm publish.

### 4.3 留给志丹 (思路 / 方向问题)

**这些已经写进 refactor_living_lab.md 但本次 PR 不实施, 想确认是否同意"留到下次 PR"**:

- **D-Q1 Lab "人话层" trace render** (Q9 / invariant 9): 工程量大 (LLM 摘要 or 模板生成器), 独立 PR-E 做.
- **D-Q2 Living Agent (MCP/飞书/CC)**: 三选一先试. P2 但 "2-3 周内硬截止". 本次 PR 已让 API agent-ready, 选哪个端先接, 留给志丹.
- **D-Q3 What-if 升为横切动作** (Q7 / invariant 7): 前端改造大, debug-ui 现在是独立 panel. 独立 PR-F.
- **D-Q4 Sandbox 单次演练 (Q10A)**: 当前能力够吗? 还是要先把 `/api/lab/sandbox/advance N天` 做出来? 现状是 advance 一次一天, N 次循环靠 UI / 脚本.

---

## 5. 测试策略

### 5.1 自动化 (本 PR 必加)

- `tests/test_living_router.py` — Living 17 个端点路径正确, OpenAPI tag = "living"
- `tests/test_lab_router.py` — Lab 11 个端点路径全部在 `/api/lab/*`
- `tests/test_living_lab_isolation.py` — Lab 端点**不**出现在 Living router; Living 端点**不**出现在 Lab router (反向用 OpenAPI schema 断言)
- `tests/test_sandbox_trace_marker.py` — sandbox 启用时 write_trace → `is_sandbox=true`; list_traces 默认过滤; `include_sandbox=True` 时显示
- `tests/test_living_api_agent.py` — `meal_hint` alias OK; `at_time` 显式传时通过 clock 入口; 不传 fallback 到当前
- 全套 `pytest tests/ -q` 通过 (现有 ~45 test 文件)
- `uv run python -m scripts.baseline_l2_snapshot` 改前/改后 + compare_traces 通过 (改 trace_store 必跑)

### 5.2 前端 build smoke

- `cd apps/web && npm run build` 0 error
- `cd apps/debug-ui && npm run build` 0 error
- `cd packages/contracts && tsc --noEmit` 0 error

### 5.3 chrome-devtools-mcp 自驱 (CLAUDE.md 强制)

- 启 server + 两个 Vite, navigate `/` (Living homepage) → 看 recommend 拉回来
- navigate `/live` 或 debug-ui 入口 → console_messages 无 error, network_requests `/api/lab/*` 全 200
- 不验通过不 merge

---

## 6. CONTRACTS.md 增量 (本 PR 落)

新增 "Living vs Lab" 段, ≤ 30 行:

```markdown
## Living vs Lab 二分 (D-085)

- **Living API (`chisha/api_living.py`, prefix=/api)**: 决策入口, 写真实数据.
  请求/响应 JSON 自闭包, 无客户端隐含上下文, agent 可直接调.
- **Lab API (`chisha/api_lab.py`, prefix=/api/lab)**: trace 查询 + sandbox + what_if.
  **完全只读真实数据**, 只能写 sandbox 分支 (`data_root` 隔离).
- **Living 不调 Lab**, Lab 不写真实数据. 跨界改动必须在 decisions.md 留 D-XXX.
- **trace.is_sandbox** 来自 `data_root.sandbox_state(root)["enabled"]`,
  `list_traces` 默认 `include_sandbox=False`.
- **共享只到 `packages/contracts/`** (TS types + fetch helper), UI 不共享.
  改 Living API 字段时, contracts 类型同步, 两边 Vite tsc 立刻飘红.
```

---

## 7. decisions.md 增量 (本 PR 落)

```markdown
## D-085 — Living + Lab 二分架构 (2026-05-17)

后端拆 `chisha/api_living.py` + `chisha/api_lab.py`, prefix 分别为 `/api` 和 `/api/lab`.
前端起 `packages/contracts/` 共享 TS types + fetch helper.
trace 写入 `is_sandbox` 字段, `list_traces` 默认隐藏 sandbox.
Living API agent-ready (meal_hint alias + at_time 可选).
Lab "人话层" / Living Agent / What-if 横切 / sandbox 多日演练 — 推迟独立 PR.

详见 [refactor_living_lab.md](refactor_living_lab.md) + [refactor_living_lab_migration.md](refactor_living_lab_migration.md).
```

---

## 8. 实施验收清单 (志丹回来时看的)

- [ ] 4 个 PR 全部 commit, 每个独立可 revert
- [ ] `pytest tests/ -q` 全绿 + 新 5 个 test 文件都覆盖到
- [ ] `baseline_l2_snapshot` 改前/改后 compare_traces 通过 (EPSILON=1e-6)
- [ ] `apps/web` + `apps/debug-ui` `npm run build` 全绿
- [ ] chrome-devtools-mcp 自驱跑过 Living homepage + Lab Live mode
- [ ] CONTRACTS.md 新段, decisions.md 新条目
- [ ] `docs/refactor_living_lab_handoff.md` 写好待办池 (D-Q1~D-Q4 等)
- [ ] Codex review 三轮内收敛, 所有 BLOCKER/MED 修完
- [ ] 留给志丹的 4 个方向决策 (D-Q1~D-Q4) 明确写在 handoff 文档头部

---

## 9. 风险 + 回退

| 风险 | 触发 | 回退方案 |
|------|------|---------|
| PR-A 路径替换漏改 → 前端 404 | apps/web 或 debug-ui 仍 fetch 老路径 | `git revert <PR-A commit>`; 单 commit |
| baseline_l2_snapshot 飘红 | 误改 score/recall/rerank | 立刻 revert 该 PR; 此次重构**只动 API 层**, 不该飘 |
| chrome-devtools-mcp 验不通 | Vite proxy 错 or backend 启动 fail | 直说"Vite 没起来", 不假装通过 (CLAUDE.md 红线) |

---

## 10. 范围红线 (本 PR 不做)

复用 CONTRACTS.md §范围红线 + 本次新增:
- 不做 Lab 人话层 (Q9) — 独立 PR-E
- 不做 Living Agent 接入 (P2 目标) — 独立 PR-G
- 不做 What-if 横切重设计 (Q7) — 独立 PR-F
- 不做 Sandbox N 日演练 (Q10A 延伸) — 独立 PR-H
- 不重写 `chisha/api.py` recommend_meal 主入口 — 只动 router 层
- 不改打分链路任何代码 — score/recall/rerank/refine 全部不动
- 不引入 npm publish (contracts 包零 build, source 引用)
- 不改 `apps/debug-ui` 目录名 (P-6)

如果实施中发现必须越过红线, **停下**, 在 handoff 文档新增决策点等志丹回来.

# Phase 2 plan · 接后端 (chisha debug-ui)

## Context recap

- Phase 1 完成: apps/debug-ui/ Vite+React+TS, 5 套主题, DAG + 4 panel + Refine pipeline 全走 mock 渲染。Codex review 过且 6 个 FIX-NOW 已修。
- Backend = chisha.debug_server (FastAPI on :8765), Vite dev proxy `/api → :8765` 已配。

## Backend reality vs prompt API contracts

Prompt 描述 API contracts(`POST /api/debug_recommend`, `POST /api/refine`,
`GET /api/profile`, `POST /api/trace`, `GET /api/sessions`, `GET /api/session/{id}`),
现状:

| 端点 | 现状 | Phase 2 动作 |
|---|---|---|
| `POST /api/debug_recommend` | 存在,字段差 (meal_type/profile_overrides/use_llm_rerank, 响应 l1_recall/l2_score/l3_rerank/target_trace/final/context/config) | 接,写 adapter 转 frontend `Session` 类型 |
| `POST /api/refine` | chisha/web_api.py 已挂(V1 用户视图 router 复用),字段未细查 | 先 GET swagger 看 schema,再接 |
| `GET /api/profile` | 存在 | 接,展示当前 profile (Phase 2 仅展示,不编辑) |
| `POST /api/trace` | **不存在** | 不在 Phase 2 范围 (Phase 4 才需要) |
| `GET /api/sessions` | **不存在** | Phase 2 加: 把每次 debug_recommend 结果落盘 + index |
| `GET /api/session/{id}` | **不存在** | Phase 2 加: 读盘 |

## Scope

**前端 (apps/debug-ui/):**

1. `src/api/types.ts` — 原始后端响应类型 (与 frontend `Session` 类型分离)。
   字段 1:1 镜像 `chisha/debug_recommend.py:debug_recommend()` 的返回 shape。
2. `src/api/adapter.ts` — `backendToSession(raw): Session`。负责重命名 +
   合并 (e.g. l1_recall.funnel → l1.funnel, l2_score.combos → l2.combos,
   l3_rerank.llm → l3, final → final[])。
3. `src/api/client.ts` — fetch 封装:
   - `postDebugRecommend(req)` → Session
   - `postRefine(req)` → 第二轮 + diff (Phase 3 才完整渲染, Phase 2 只接到 console.log)
   - `getProfile()` → profile JSON
   - `listSessions()` → RunHistoryRow[]
   - `getSession(id)` → Session
4. `src/hooks/useSession.ts` — 管理「当前 session + loading/error 状态 +
   触发函数」。返回 `{ session, status: 'idle'|'loading'|'error'|'ok',
   error, runMain, runRefine, loadSession }`。
5. App.tsx 改为消费 `useSession()` 而不是直接 import MOCK_SESSION; 当
   `status === 'loading'` 时 `runningPulse=true`,`status === 'error'` 时顶部 status
   pill 转红。
6. Sidebar profile 文本框 实时 JSON.parse 校验,失败显示红边 + tooltip
   (不阻断,但 Run 按钮 disabled)。
7. RUN_HISTORY 改为 `await listSessions()` 加载,点击调用 `loadSession(id)`。
8. 错误处理: 简易 Toast (右上角 fixed,3s 自动消失),封 `src/components/Toaster.tsx`。

**后端 (chisha/):**

9. 在 chisha/debug_server.py 加两个端点:
   - `GET /api/sessions` → 列出 data/debug_sessions/ 下 JSON 文件 (按 mtime 排序,
     限 50 条),返回 `[{id, title, time, status, latency, meal, area}]`。
   - `GET /api/session/{id}` → 读 data/debug_sessions/{id}.json 返回完整 trace。
10. 在 chisha/debug_recommend.py 末尾 (or 在 debug_server.py 的 api 函数内)
    把成功的 trace 落盘到 data/debug_sessions/sess_<timestamp>_<hash>.json。
    title 字段从 config.meal_type + l1_recall.area derive。
11. data/debug_sessions/ 加到 .gitignore。

**Mock 兜底:**

- vite dev 模式下,若后端 503 / connection refused,fallback 到 MOCK_SESSION
  并在顶部显示 "backend offline · using mock" pill。
- Production build 不内嵌 mock (build 时通过 `import.meta.env.DEV` gate)。

## Phase 2 不做

- L3 fallback 视图: 现在 active-session === sess_a7f0 toggle 用的是 mock 数据
  叠加。Phase 2 不改这块,等真实 fallback 链路触发时再说。
- Refine tab 第二轮完整渲染 (Phase 3)。
- Trace tab (Phase 4)。
- 键盘快捷键 (Phase 5)。
- profile JSON 编辑后 PUT (Phase 6 / Phase 7 范围)。

## 关键决策点请 Codex 表态

1. **类型分离 vs 共用**: 是否要把 `src/api/types.ts` 和 `src/types/trace.ts`
   分开?我倾向分开 — backend shape 是契约,frontend `Session` 是 view model,
   两者解耦让 backend rename 不直接戳穿 UI。Codex 看?

2. **adapter 在 client 内还是单独文件**: 我倾向单独 `adapter.ts`,client
   只管 fetch + JSON parse,adapter 一个纯函数。便于测试 (虽然 Phase 2 不写
   测试) 也便于未来切 OpenAPI codegen。

3. **session 落盘位置**: `data/debug_sessions/` 还是别的地方?项目已有
   `data/` 目录但用于业务数据 (餐厅 / 菜品)。考虑改 `tmp/debug_sessions/`
   或 `var/debug_sessions/`?

4. **session id 生成**: 当前 mock 用 `sess_2026-05-16_12-04-37_a7f1` 这种
   长名。Phase 2 backend 生成时怎么编?我倾向 `sess_<unix_ms_base36>_<6char_hash>`,
   人读 + 机器排序友好。

5. **listSessions 返回字段**: prompt 说 `{id, title, time, status, latency, meal, area}`。
   `time` 是字符串 ("12:04" / "昨 19:32"),需要前端格式化。是后端按用户当地
   时间渲染(简单),还是后端给 ISO,前端格式化(更对)?Codex 看哪个。

6. **错误处理粒度**: 我打算把所有 API 错误塞进一个 `error: { code, message }`
   字段,Toast 显示 message,严重错(5xx)同时让 DAG status pill 转红 + 持续
   显示直到下一次成功。OK?

7. **mock fallback 检测**: 前端怎么判断"后端 offline"?fetch reject (network
   error) → 用 mock。还是 timeout (3s) → 用 mock?prompt 没说要 mock fallback,
   是我加的 niceness。如果 Codex 觉得过度设计,可以砍。

8. **profile 编辑实时校验**: textarea onChange 每次 JSON.parse 会卡;但 profile
   只几 KB,实测应该不卡。如果 Codex 担心,可以 debounce 200ms。我倾向不
   debounce,先测。

9. **是否在 Phase 2 加 OpenAPI codegen**: prompt 没要求,但既然要写 adapter
   不如顺手用 openapi-typescript 生成 backend 类型。代价是多个依赖 + 一个
   build step。Codex 看价值。我倾向**不加**,Phase 2 手写类型 ≤ 200 行,
   单用户工具不值得搞 codegen pipeline。

## What I want from Codex

- 9 个 open question 的明确立场 (yes/no/alternative)
- 找漏掉的端点 / 字段 / 边界
- 找会卡 Phase 3-7 的隐藏决定
- 后端 sessions 落盘有没有 race / 文件名冲突 / 磁盘满风险该处理

中文 200-400 字,结构化,不要客套。

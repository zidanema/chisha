# chisha · 前后端 API 契约 (V1 + V1.1)

> 适用于 `apps/web` ↔ `chisha/debug_server.py` (端口 8765).
> **字段对应类型见 `apps/web/src/lib/types.ts`** (单一可信源, 改字段先改这里).
> mock 行为见 `apps/web/src/lib/mockApi.ts`. 本文档列契约稳定端点, 新端点开 issue 讨论.
>
> Loading 表现:
> - `recommend` / `refine` 在 prod 是 **15-60s** (LLM 精排实测), mock 走 900ms
> - 其它接口 < 500ms
> - 前端必须用 **skeleton**, 禁旋转 spinner

---

## 端点速查

| Method | Path | 用途 |
|---|---|---|
| `GET`  | `/api/recommend?meal_type=&mood=` | 返回 5 候选 (round=1) |
| `POST` | `/api/refine` | 同 session refine, 返回新 5 候选 |
| `POST` | `/api/accept` | 接受某候选 → 入 acceptedQueue, 返回 deeplink_url |
| `POST` | `/api/skip` | 跳过这餐 → 出 acceptedQueue, banner 不再弹 |
| `GET`  | `/api/feedback/inbox?include_snoozed=` | 反馈中心列表 |
| `POST` | `/api/feedback/snooze` | 24h 软关闭, banner 不弹但 inbox 仍在 |
| `POST` | `/api/feedback/stop` | 永久硬关闭, banner+inbox 都隐藏 |
| `GET`  | `/api/feedback/recent?limit=` | 最近已反馈, 供 inbox 第三段 + history 行 chip |
| `GET`  | `/api/feedback/<session_id>` | 反馈页加载 (返回 session + 当时的 5 候选) |
| `GET`  | `/api/feedback/<session_id>/record` | 已提交反馈记录 (form/detail 双态判断) |
| `POST` | `/api/feedback` | 提交反馈 |
| `POST` | `/api/feedback/<session_id>/comments` | append-only 追加备注 |
| `GET`  | `/api/profile` | 读 profile.yaml |
| `PUT`  | `/api/profile` (兼容 `POST`) | 写 profile.yaml |
| `GET`  | `/api/history?days=` | 历史推荐列表 |
| `GET`  | `/api/debug/sessions?limit=&meal_type=` | 列最近 N 条 trace meta + feedback badge |
| `GET`  | `/api/debug/sessions/{session_id}` | 单条完整 trace (Replay 详情) |
| `POST` | `/api/debug/what_if` | What-if 重跑 (冻结 L1, 重跑 L2+L3, 永不写盘) |

Sandbox Lab 端点 (`/api/sandbox/*`) 见 [apps/sandbox-lab/README.md](../apps/sandbox-lab/README.md).

---

## 关键端点细节

### `GET /api/recommend`
Query: `meal_type=lunch|dinner&mood=...`. 响应 `RecommendResponse` (types.ts). 含 `session_id` (形如 `2026034521_lunch`) + `round=1` + `candidates[]` (5 个按 rank 排序) + `stats`.

### `POST /api/refine`
Body: `{ session_id, refine_text, meal_type, mood, round, excludeIds }`. 响应同 `RecommendResponse`, 复用 `session_id`, `round++`, 顶层加 `refine_input` (原文) + `refine_intent` (结构化意图 V2 多 slot schema, 详见 types.ts `RefineIntentV2`).

`refine_intent` 由 `chisha/refine_intent.py::parse_refine_intent` 生成 (LLM + 规则 fallback). 详见 D-073 / D-081.

### `POST /api/accept`
Body: `{ session_id, candidate_rank, candidate }`. 响应: `{ deeplink_url }`.

> **不假装成功**: 前端**不依赖** `deeplink_url` 真能拉起 APP (iOS/Android 拉起率 < 30%). 前端总是显示"搜店名 + 复制按钮". `deeplink_url` 仅作 fallback.

### `POST /api/skip`
Body: `{ session_id, reason }` (reason ∈ `cafeteria | brought | outside | social | none_fit | not_hungry | null`).
副作用: 清掉 `acceptedQueue` 中对应条目, `reason` 进推荐学习信号 (在外吃/食堂 ≠ 都没看上).

### 反馈端点 (V1.1)

**`GET /api/feedback/inbox`** — 反馈中心数据源. 返回 `items[]` (含 `session_id / meal_type / restaurant_name / summary / accepted_at / snoozed / stopped`).
前端用法:
- 主页 banner: `inbox.filter(x => !x.snoozed && !x.stopped)[0]`
- `/feedback` 反馈中心: 全量按 snoozed 分两段
- NavBar 角标: active 项数

**`POST /api/feedback/snooze`** / **`/stop`** — 软/硬关闭. snooze 给 acceptedQueue 项设 `snoozed_until = now + 24h` (自动到期回 false); stop 设 `stopped = true` 永久.

**`GET /api/feedback/recent?limit=`** — 最近已反馈, 供 inbox 第三段 + history 行 gut chip.

**`GET /api/feedback/<sid>`** — 返回 session + 当时的 5 候选 (反馈页头部"你当时点的是 X" 卡片).

**`GET /api/feedback/<sid>/record`** — 已提交反馈记录, 没提交时返回 `null`. 前端用此判断 form / detail 双态:
- `null` → 渲染 ProgressiveForm
- `FeedbackRecord` → 渲染 FeedbackDetailView (readonly snapshot + append timeline)

**`POST /api/feedback`** — 提交反馈. body = `FeedbackPayload` (字段定义见 types.ts).
字段语义:
- `rating: -1 | 0 | 1 | null` — gut (难吃 / 普通 / 好吃, D-064)
- `reason_match / fullness / oil_calibration / repurchase_intent: 0 | 1 | 2 | null` — 4 维 calibration/behavior (D-065)
- `variant: "progressive" | "not-eaten"` — 后者是「都没吃这几个」逃生口
- `quick?: boolean` — V2 banner inline 一键打分时为 true (信号 weight 可降)

副作用:
- 后端落 `FeedbackRecord = { ...payload, submitted_at, comments: existing?.comments ?? [] }`
- 同 session_id 重提 = 覆盖 payload 但 **comments[] 保留** (D-067)
- inbox 该 session 立即从"待反馈"段消失

**`POST /api/feedback/<sid>/comments`** body `{ text }` — append-only. push 新 comment, 每条独立 timestamped, 不修改原始反馈. 返回 `{ ok: true }`.

> **不删除 / 不编辑 (V1.1)**: 没有 `DELETE` 或 `PATCH` 端点 (D-066/068). V2 再加.

### `GET /api/profile` / `PUT /api/profile`
`Profile` 形状见 `types.ts` (镜像 profile.yaml). `PUT` body 完整 Profile 对象, 后端覆盖式写入 (保留注释由 ruamel.yaml 处理).

### `/api/debug/*` (D-079, Replay / What-if)

全部 localhost-only (debug_server bind 127.0.0.1, `_require_localhost` 守门). 活约束在 [CONTRACTS.md](CONTRACTS.md) §Trace + Debug 三模式.

**`GET /api/debug/sessions`** — Sidebar 列表. Query: `limit` (max 100) / `meal_type` (`lunch|dinner|null`) / `source` (V1 只接受 `production`). 响应见 types.ts `TraceMeta[]` + `corrupt_count`.

**`GET /api/debug/sessions/{sid}`** — Replay 完整 trace JSON. Schema 顶层: `__version / __source / __parent_session_id / __llm_called / __frozen / __config / __feedback / l1 / l2 / l3 / final / refine`.

Failure: `404` 不存在 / `409` schema version 不识别 / `500` JSON 损坏 (自动备份 `.corrupt.{ts}.bak`).

**`POST /api/debug/what_if`** — What-if 重跑, **永不写盘**. Body: `{ base_session_id, overrides: { profile_overrides, use_llm_rerank, n_return, n_explore } }`. `overrides` schema `extra='forbid'` 严格. `use_llm_rerank` 默认 `False` 防意外烧 LLM 配额. 响应同单条 trace shape, 但 `__source="what_if_preview"` + `__parent_session_id` + `__llm_called`.

Failure: `400` overrides 非白名单 / base trace `__source != production` / 缺 `__frozen` · `404` base 不存在 · `409` schema 不兼容 · `422` pydantic 层拒绝 · `500` base 损坏.

**Live 模式 (`/api/debug_recommend`)** — D-039 老端点, D-079 复用作 Live 入口. 后端走 `debug_recommend.debug_recommend()` 全链路跑 (含 LLM), 但**不调用** `trace_store.write_trace()`.

---

## 错误处理

- 4xx / 5xx 响应均返回 `{ "error": { "code": "...", "message": "...", "config_error": bool } }`
- L3 三态 (`ok` / `fallback` / `config_error`) 在 `RecommendResponse` 上以 `status` + `resolved_provider` 字段暴露 (调试台用); 用户视图不直接展示, 但日志保留 (D-048)

---

## 演进备忘

- V1.5: 飞书推送 + deeplink 跳 `/feedback/last` (D-051)
- V2: WebSocket / SSE 流式返回 candidates (LLM 慢加载, 一张张到位)
- V2.1: refine chip 动态生成 (按"最近 3 天没吃过的菜系/食材")
- 反馈数据回灌推荐推理: `reason_match` reverse-loss / `repurchase_intent` 进 ranking / `comments[]` 给同店推荐 reason 生成时 context inject (D-063~D-065)

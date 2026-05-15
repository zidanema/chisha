# chisha · 前后端 API 契约 (V1)

> 适用于 `apps/web` ↔ `chisha/debug_server.py` (端口 8765, D-049)。
> 字段对应类型见 `apps/web/src/lib/types.ts`；mock 行为见 `apps/web/src/lib/mockApi.ts`。
>
> Loading 表现:
> - `recommend` / `refine` 在 prod 是 **15-60s** (LLM 精排实测), mock 走 900ms
> - 其它接口 < 500ms
> - 前端必须用 **skeleton**, 禁旋转 spinner (style-guide §2)

---

## 5. 端点速查

| Method | Path | 用途 | 状态 |
|---|---|---|---|
| `GET`  | `/api/recommend?meal_type=&mood=` | 返回 5 候选 (round=1) | V1 ✅ |
| `POST` | `/api/refine` | 同 session refine, 返回新 5 候选 | V1 ✅ |
| `POST` | `/api/accept` | 接受某候选 → 入 acceptedQueue, 返回 deeplink_url | V1 ✅ |
| `POST` | `/api/skip` | 跳过这餐 → 出 acceptedQueue, banner 不再弹 (D-052) | V1 ✅ |
| `GET`  | `/api/feedback/inbox?include_snoozed=` | 反馈中心列表 (代替 last_unfed 单条, **D-056**) | V1.1 ✅ mock |
| `POST` | `/api/feedback/snooze` | 24h 软关闭, banner 不弹但 inbox 仍在 (**D-058**) | V1.1 ✅ mock |
| `POST` | `/api/feedback/stop`   | 永久硬关闭, banner+inbox 都隐藏 (**D-058**) | V1.1 ✅ mock |
| `GET`  | `/api/feedback/recent?limit=` | 最近已反馈, 供 inbox 第三段 + history 行 chip | V1.1 ✅ mock |
| `GET`  | `/api/feedback/<session_id>` | 反馈页加载 (返回 session + 当时的 5 候选) | V1.1 ✅ mock |
| `GET`  | `/api/feedback/<session_id>/record` | 已提交反馈记录 (form/detail 双态判断, **D-064**) | V1.1 ✅ mock |
| `POST` | `/api/feedback` | 提交反馈 (V1.1 schema, **D-061~D-063**) | V1.1 ✅ mock |
| `POST` | `/api/feedback/<session_id>/comments` | append-only 追加备注 (**D-065**) | V1.1 ✅ mock |
| `GET`  | `/api/profile` | 读 profile.yaml | V1 ✅ |
| `PUT`  | `/api/profile` (兼容 `POST`) | 写 profile.yaml | V1 ✅ |
| `GET`  | `/api/history?days=` | 历史推荐列表 | V1 ✅ |

> **V1.1 状态说明**: 反馈系统 7 个端点在 `apps/web/src/lib/mockApi.ts` 全量实现, 前端 mock 模式可端到端跑 (D-054~D-066)。后端 FastAPI **待装**, 实施进度跟踪在 IMPL_LOG D-054~D-066 执行记录。
> **砍掉的旧端点**: `GET /api/session/last_unfed` (被 inbox[0] 取代) · `POST /api/session/dismiss_feedback_banner` (被 snooze/stop 取代)。

---

## 6. 关键端点细节

### 6.1 `GET /api/recommend`

请求:
```
?meal_type=lunch|dinner&mood=neutral|want_clean|want_indulgent|want_light|want_soup|low_carb
```

响应: `RecommendResponse` (见 types.ts)
- `session_id`: 形如 `2026034521_lunch`
- `round`: 1
- `candidates[]`: 5 个, 已按 `rank` 排序
- `stats`: 召回/打分/返回数量

### 6.2 `POST /api/refine`

请求:
```json
{
  "session_id": "...",
  "refine_text": "想吃辣的",
  "meal_type": "lunch",
  "mood": "neutral",
  "round": 2,
  "excludeIds": ["c_001", "c_002"]
}
```

响应: 同 `RecommendResponse`, 复用 `session_id`, `round++`, `context.refine_input` 带原文。

### 6.3 `POST /api/accept` (D-050)

请求:
```json
{
  "session_id": "...",
  "candidate_rank": 3,
  "candidate": { /* 整 Candidate, 后端便于审计 */ }
}
```

响应:
```json
{ "deeplink_url": "dianping://shopdesc?shopId=r_077&name=..." }
```

> **不假装成功**: 前端**不依赖**这个 deeplink_url 真能拉起 APP (iOS/Android 拉起率 < 30%, D-050)。前端总是显示"搜店名 + 复制按钮"。`deeplink_url` 仅作为最佳努力 fallback。

### 6.4 `POST /api/skip` (D-052)

请求:
```json
{
  "session_id": "...",
  "reason": "cafeteria" | "brought" | "outside" | "social" | "none_fit" | "not_hungry" | null
}
```

响应:
```json
{ "ok": true }
```

副作用:
- 清掉 `acceptedQueue` 中对应 session_id 的条目 (或标记 `skipped=true`)
- `lastUnfed()` 后续不会再返回该 session
- `reason` 进推荐学习信号 (在外吃/食堂 ≠ 都没看上, 见 D-052)

### 6.5 反馈端点 (D-054~D-066, V1.1)

**`GET /api/feedback/inbox?include_snoozed=`** — 反馈中心数据源

响应:
```json
{
  "items": [
    {
      "session_id": "...",
      "meal_type": "lunch",
      "restaurant_name": "粤牛·化州剪牛腩...",
      "summary": "双拼鲜牛腩牛杂单人煲 + 招牌鲜牛杂单人煲 + 萝卜",
      "accepted_at": "2026-05-15T11:42:18.000Z",
      "snoozed": false,
      "stopped": false
    }
  ]
}
```

前端用法:
- 主页 banner: `inbox.filter(x => !x.snoozed && !x.stopped)[0]`, 同时显示 "还有 N-1 餐没反馈"
- `/feedback` 反馈中心: 全量, 按 snoozed 分两段 (待反馈 / 暂缓)
- NavBar 角标: `inbox.filter(x => !x.snoozed && !x.stopped).length`
- D-053 同 session 抑制保留: 主页 banner 过滤掉当前 home session_id

**`POST /api/feedback/snooze`** body `{ session_id }` — D-058 软关闭
- 后端给 acceptedQueue 项设 `snoozed_until = now + 24h`
- inbox `snoozed` 字段在 24h 内为 true, 之后自动回 false (无需用户操作)
- 不进推荐学习信号

**`POST /api/feedback/stop`** body `{ session_id }` — D-058 硬关闭
- 后端给 acceptedQueue 项设 `stopped = true` (永久)
- inbox 列表过滤掉 stopped 项 (banner + inbox 都不显示)
- 不影响 history (D-057 history 行仍可点)

**`GET /api/feedback/recent?limit=`** — 最近已反馈

响应:
```json
{
  "items": [
    {
      "session_id": "...",
      "meal_type": "lunch",
      "restaurant_name": "...",
      "accepted_at": "...",
      "submitted_at": "2026-05-15T19:43:00.000Z",
      "rating": 1,
      "accepted_rank": 2
    }
  ]
}
```

供 inbox 第三段「已反馈」+ history 行 gut chip 显示。

**`GET /api/feedback/<session_id>`** — getFeedbackSession

返回 session + 当时的 5 候选 (用于反馈页头部"你当时点的是 X" 卡片渲染)。如果 session 已过期/不存在, 后端合成一份 (mock 行为, 真后端应该 404)。

```json
{
  "session_id": "...",
  "meal_type": "lunch",
  "accepted_at": "...",
  "accepted_rank": 2,
  "candidates": [/* 5 个 Candidate */]
}
```

**`GET /api/feedback/<session_id>/record`** — getFeedback (D-064 双态判断)

返回该 session 已提交的反馈记录 (V1.1 schema), 没提交时返回 `null`。前端用此判断 form / detail 双态:
- `null` → 渲染 ProgressiveForm
- `FeedbackRecord` → 渲染 FeedbackDetailView (readonly snapshot + append timeline)

```json
{
  "session_id": "...",
  "accepted_rank": 2,
  "rating": 1,
  "reason_match": 0,
  "fullness": 1,
  "oil_calibration": 1,
  "repurchase_intent": 2,
  "note": "辣度刚好...",
  "variant": "progressive",
  "submitted_at": "2026-05-15T19:43:00.000Z",
  "comments": [
    { "id": "cmt_xxx", "text": "第二天回想...", "created_at": "2026-05-16T09:12:00.000Z" }
  ]
}
```

**`POST /api/feedback`** — 提交反馈 (D-064 提交即 readonly)

请求 body = `FeedbackPayload`:
```json
{
  "session_id": "...",
  "accepted_rank": 2,
  "rating": 1,
  "reason_match": 0,
  "fullness": 1,
  "oil_calibration": 1,
  "repurchase_intent": 2,
  "note": "辣度刚好",
  "variant": "progressive",
  "quick": false
}
```

字段语义:
- `rating: -1 | 0 | 1 | null` — gut (难吃 / 普通 / 好吃, D-062)
- `reason_match / fullness / oil_calibration / repurchase_intent: 0 | 1 | 2 | null` — 4 维 calibration/behavior (D-063), `null` 表示用户没填
- `variant: "progressive" | "not-eaten"` — 后者是「都没吃这几个」逃生口, payload 全字段 null + `accepted_rank: null`
- `quick?: boolean` — V1.1 默认 false; V2 加 banner inline 一键打分时为 true (信号 weight 可降)

副作用:
- 后端落 `FeedbackRecord = { ...payload, submitted_at, comments: existing?.comments ?? [] }`
- 同 session_id 提交多次 = 覆盖 payload 但 **comments[] 保留** (D-065 隔离原始 + append)
- D-064 spec 上**禁止编辑**, 但当前 mock 没强制 (后端实施时建议 4xx if exists, 由前端 detail view UI 保证不发 duplicate)
- inbox 该 session 立即从「待反馈」段消失

**`POST /api/feedback/<session_id>/comments`** body `{ text }` — D-065 append-only

副作用: push 新 comment 到 `feedbacks[sid].comments`, 每条独立 timestamped, 不修改原始反馈字段。返回 `{ ok: true }`。

> **不删除 / 不编辑 (V1.1)**: 没有 `DELETE /api/feedback/<sid>` 或 `PATCH /api/feedback/<sid>/comments/<cmt_id>` 端点 (D-064 + D-066), V2 再加。

### 6.6 `GET /api/profile` / `PUT /api/profile`

`Profile` 形状见 `types.ts` (镜像 profile.yaml)。`PUT` body 是完整 Profile 对象，后端覆盖式写入 profile.yaml（保留注释由 ruamel.yaml 处理）。

---

## 7. 错误处理

- 4xx / 5xx 响应均返回 `{ "error": { "code": "...", "message": "...", "config_error": bool } }`
- D-048 的 L3 三态 (`ok` / `fallback` / `config_error`) 在 `RecommendResponse` 上以 `status` + `resolved_provider` 字段暴露 (调试台用)；用户视图不直接展示，但日志里保留

---

## 8. 演进备忘

- V1.5: 飞书推送 + deeplink 跳 `/feedback/last` (D-049)
- V2: WebSocket / SSE 流式返回 candidates (LLM 慢加载, 一张张到位)
- V2.1: refine chip 动态生成 (按"最近 3 天没吃过的菜系/食材")
- V2.0 反馈系统增量 (D-066): 删除反馈 / 撤销重提 / comment 结构化 chip / banner 一键打分 / A/B 实验框架
- 反馈数据回灌推荐推理: `reason_match` reverse-loss 给 LLM reason generator / `repurchase_intent` 进 ranking / `comments[]` 给同店推荐 reason 生成时 context inject (D-061~D-063, 后端实施待装)

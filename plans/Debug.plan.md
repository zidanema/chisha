# T-Debug 实施 plan (Round 3 — Codex Round 2 BLOCKED 后修订)

> Round 1 BLOCKED 5 issue → Round 2 修后剩 3 issue → Round 3 收尾.
> Round 3 修订点:
> 1. B1 stale guard 下沉到 `useWaTrace.ts` 内 `setActiveTrace(wa)` 前 (App.tsx 那层晚于真问题源)
> 2. B6 加显式 chrome-devtools-mcp 断言: rendered DOM 必须含 `CONFIG_ERROR` 不含 `SKIPPED`
> 3. B5 明确承认 StrictMode dev 双跑 (dep array 不能压制), 加 AbortController 防请求重叠

历史修订 (Round 2 已 OK):
> - B4 backend 改 `web_api.py:_attach_feedback_to_meta` (不是 trace_store)
> - B6 根因命名 + adapter 改动详写
> - B1 reset 改 key on `trace.meta.latestRound`
> - B3 makeEmptyRound + 类型安全 (Codex 第 2 轮 Q3 已确认无冲突)
> - 不引入 vitest, e2e 覆盖

## 总览

| Bug | 入手文件 | 改动量 | 风险 |
|---|---|---|---|
| B1 activeRound 不读 latestRound | `App.tsx` | ~10 行 | 低 (key on loaded latestRound) |
| B2 RefineTimeline 节点非 button | `RefineTimeline.tsx` + CSS | ~15 行 | 低 |
| B3 stubToRound mock 兜底 | `useWaTrace.ts` + 新 `makeEmptyRound` helper | ~40 行 | 中 (要 cover 全字段) |
| B4 ⭐ 渲染 + 缺餐厅名 | **`web_api.py:_attach_feedback_to_meta`** + `TraceBrowser.tsx` + types | ~25 行 | 中 |
| B5 trace 列表不轮询 | `useWaTrace.ts` | ~12 行 (用 ref 防 stale activeTraceId) | 低 |
| B6 L3 SKIPPED 状态丢失 | **`adapter.ts:210-234` + `wrapTraceL3:349-353`** + `PanelL3.tsx` 文案 | ~20 行 | 中 (改 mapping 影响所有 trace 显示) |

## 已核实的关键代码定位

- `apps/debug-ui/src/App.tsx:54-93` activeRound + 现有 reset useEffect
- `apps/debug-ui/src/hooks/useWaTrace.ts:133-149` assembleTraceFromDetail 已透传 `latestRound`
- `apps/debug-ui/src/hooks/useWaTrace.ts:57-80` stubToRound + line 71-77 mock fallback
- `apps/debug-ui/src/hooks/useWaTrace.ts:179-209` mount fetch (闭包内 activeTraceId)
- `apps/debug-ui/src/hooks/useWaTrace.ts:246-283` getRoundFull
- `apps/debug-ui/src/components/RefineTimeline.tsx:103-117` rt-node `<div>` + line 46-57 handleClick/Context
- `apps/debug-ui/src/components/TraceBrowser.tsx:29-49` feedbackGlyph, line 33 `⭐` 丢
- `apps/debug-ui/src/api/adapter.ts:210-234` adaptL3 — **B6 根因: hardcoded `status: "skipped"` for non-live llm**
- `apps/debug-ui/src/api/adapter.ts:349-356` wrapTraceL3 — **B6 上游: `l3.used=false` → `{used:false, skipped_reason}`, 丢 status**
- `apps/debug-ui/src/panels/PanelL3.tsx:51-53,251-259` callout 分支
- **`chisha/web_api.py:1125-1139` `_attach_feedback_to_meta` — B4 真正派生路径** (TraceBrowser 通过 /api/traces 拿)
- `chisha/feedback_store.py:124-134` accepted 记录含 `restaurant_name + accepted_rank`
- `apps/debug-ui/src/types/trace.ts:301-326` RoundRecord 形状 (l1/l2/l3/final 必填)

## 各 Bug 实施步骤

### B6 [P1] 先修 — 改 adapter 让 config_error 透传

**根因** (Codex 命名): `adapter.ts:210-234` `adaptL3` 在 `!isLiveL3(l3.llm)` 分支硬编码 `status: "skipped"`. `wrapTraceL3` (line 349-353) 又在 `!l3.used` 时把 backend L3 包成 `{used: false, skipped_reason}` (是 BackendL3SkippedShape, 没 status 字段), 导致 isLiveL3 返回 false. 两层叠加把 `l3.status=config_error` 完全吃掉.

**违反 CONTRACTS.md:39**: `config_error 必须 hard-fail, 不能被外层吞成 fallback`. 当前前端 mapping 等同违反 (虽然契约原文针对后端, 但精神一致).

**改法**:
1. `adapter.ts:349-353` `wrapTraceL3`: 改成传递整个 `l3` 对象给 `adaptL3`, 不要预先压成 skipped shape. 关键: backend `l3` 是 `BackendTraceL3` (含 status / fallback_reason / used / ...), 让 `adaptL3` 自己根据 `l3.status` 决定走哪条 branch.
2. `adapter.ts:210-234` `adaptL3`:
   - 优先用 `l3.status` 字段判断: "ok" / "fallback" / "config_error" / "skipped"
   - 只有 `l3.status === "skipped"` 才走当前 (line 213-234) skipped shell
   - `l3.status === "config_error"` 时返回 `{...skipped shell, status: "config_error", fallback_reason: l3.fallback_reason}` — 保留 fallback_reason
   - `l3.status === "fallback"` 不变
3. `PanelL3.tsx:51-53` 三态判定不变. callout (line 237-249 isConfigError) 已经能渲染 fallback_reason, 但要把 `L3.fallback_reason` 实际接到模板里 (现在写死了 "LLM provider 配置错, L3 未跑.", 没用 fallback_reason)
4. `PanelL3.tsx:251-259` isSkipped callout: 改成根据是否有 `fallback_reason` 分两种文案:
   ```jsx
   {isSkipped && (
     <div className="callout">
       <strong>L3 SKIPPED</strong>
       <span style={{ marginLeft: 8 }}>
         {L3.fallback_reason || "LLM rerank 关闭, Final 来自 L2 fallback rerank."}
       </span>
     </div>
   )}
   ```

**验收**:
- 切到老 trace `c205f8a61d521b49` R1 (config_error): PanelL3 显示 isConfigError callout, 含 backend 的真实 fallback_reason 文本 (e.g. "LLM provider 配置错误: profile.llm.provider=openrouter 但该 provider 不可用 (缺 API key 或 CLI 未登录)")
- 切到新 trace `04c7962d96238d55` R1: 显示正常 L3 (deepseek-v4-flash, latency 数字)
- StatusBadge 显示 "CONFIG_ERROR" 而非 "SKIPPED" (StatusBadge.tsx 已有 "config_error" 分支)

**关键测试** (Codex Round 2 issue #2 修订 — backend test 不能证 adapter 行为):

**Backend contract test** (防 backend 端 status 退化):
- `tests/test_web_api_trace.py` 加 1 个 case: `/api/trace/{sid}/round/R1` 返回的 l3 obj 必须保留 `status: "config_error"` + 完整 `fallback_reason`

**Frontend e2e 断言** (证 adapter 真正吐 config_error 渲染):
- chrome-devtools-mcp golden path step "切到 `c205f8a61d521b49` R1" 时, snapshot 必须满足:
  - DOM 含文本 `CONFIG_ERROR` (StatusBadge)
  - DOM 不含文本 `LLM rerank 关闭` (老 isSkipped 文案)
  - PanelL3 callout 内容含 backend `fallback_reason` 字符串片段 (e.g. "LLM provider 配置错误")
- 写成验证步骤明确 verify text in snapshot, 不是只截图人工看

### B1 [P0] activeRound key on loaded latestRound

**改法**:
1. `App.tsx:63` 改: `useState<string>(() => trace?.meta?.latestRound ?? "R1")` 但 trace 是 hook 返回的, 初始可能是 mock — 用 ""/"R1" 占位 OK, 真值由 useEffect 覆盖
2. `App.tsx:86-93` useEffect: 拆成两个, **key on trace.meta.latestRound 不是 activeTrace string**:
   ```ts
   // (A) 每次 detail load 完 (trace.meta.latestRound 变) → reset
   useEffect(() => {
     if (rounds.length === 0) return;
     const latest = trace.meta.latestRound || rounds[rounds.length - 1].id;
     setActiveRound(latest);
     setBase(rounds[0].id);
     setTarget(latest);
   }, [trace.meta.id, trace.meta.latestRound]);
   
   // (B) rounds signature 变 (同 trace 加 round 罕见 case) → 仅修无效值
   useEffect(() => {
     if (rounds.length === 0) return;
     setActiveRound((prev) => rounds.find((r) => r.id === prev) ? prev : rounds[rounds.length - 1].id);
     setBase((prev) => rounds.find((r) => r.id === prev) ? prev : rounds[0].id);
     setTarget((prev) => rounds.find((r) => r.id === prev) ? prev : rounds[rounds.length - 1].id);
   }, [roundsSignature]);
   ```
3. `TraceBrowser.tsx:161,216,328` 调用 `setActiveRound("R1")` 全部删除 — App.tsx (A) effect 会接管. (保留 `setActiveTrace(t.id)`, 但不主动 set round)

**race 防护** (Codex Round 2 issue #1 修订): 真正的 race 不在 App.tsx, 而在 `useWaTrace.ts:218-240` 的 `setActiveTrace(wa)` — 这里把异步 fetch 结果无条件 commit, 用户快切 trace 时第一个 fetch 的结果可能后到达, 覆盖第二个 trace 的状态.

**stale guard 改下沉到 useWaTrace** (line 218-240), **success + catch 两路都要 guard** (Codex Round 3 issue 修订):
```ts
useEffect(() => {
  if (!backendOnline) { setActiveTrace(getMockTrace(activeTraceId)); return; }
  const myId = activeTraceId;   // capture
  let cancelled = false;
  void (async () => {
    try {
      const detail = await fetchTraceDetail(myId);
      if (cancelled || myId !== activeTraceIdRef.current) return;  // ← success-path guard
      const wa = assembleTraceFromDetail(detail);
      // ... 既有 daysAgo 覆盖逻辑
      setActiveTrace(wa);
      lruRef.current.clear();
    } catch (err) {
      if (cancelled || myId !== activeTraceIdRef.current) return;  // ← catch-path guard, 对称
      const apiErr = err instanceof ApiError ? err : null;
      pushToast({ kind: "error", title: ..., detail: ... });
      setActiveTrace(getMockTrace(myId));  // 用 myId 不是 activeTraceId (闭包外可能已变)
    }
  })();
  return () => { cancelled = true; };
}, [activeTraceId, backendOnline]);
```

**App.tsx 层**: 由于 useWaTrace 已经保证 `trace.meta.id === activeTraceId` (stale guard 已下沉), App.tsx reset (A) effect 不需要额外 guard, 直接 key on `trace.meta.id + trace.meta.latestRound` 即可.

**验收**:
- 首次打开 → 默认进 `22bfb296f355496d` → 拉 `/round/R2`, IntentStrip "R2 · 来点湘菜..."
- 切到 `c205f8a61d521b49` (只 R1) → 拉 `/round/R1`, 不报错
- 切回 `22bfb296f355496d` → 拉 R2

### B2 [P0] RefineTimeline 节点改 button

**改法**:
1. `RefineTimeline.tsx:103-117`: `<div ... onClick onContextMenu>` → `<button type="button" ... onClick onContextMenu>`
2. 保留 modifier-click / right-click 语义: handleClick / handleContext 不变, 因为 button 也支持这两个事件
3. 加 `aria-label={`切到 ${r.id}${r.user_input ? ': ' + r.user_input.slice(0,30) : ''}`}` + `aria-pressed={isTarget}`
4. **CSS** (`apps/debug-ui/src/styles.css` grep `.rt-node`): 加
   ```css
   .rt-node {
     background: transparent;
     border: 0;
     padding: 0;
     font: inherit;
     color: inherit;
     cursor: pointer;
   }
   .rt-node:hover .ball { background: var(--accent); }
   .rt-node:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
   ```

**验收**:
- snapshot 里 R2 节点 role=button
- Tab 键能聚焦, Enter/Space 切轮次
- 视觉无回归 (hover 时 ball 变亮)

### B3 [P1] makeEmptyRound + guard 全范围

**改法**:
1. 新建 `apps/debug-ui/src/types/emptyRound.ts` (or inline in useWaTrace.ts) — 写一个 `makeEmptyRound(stub: BackendRoundStub): RoundRecord` factory, 用 stub 提供 `id/label/started_at/user_input/kpi/diff`, **l1/l2/l3/final 全部用空骨架**:
   ```ts
   const emptyL1: L1Trace = { combos_total: 0, combos_dropped: 0, recall_latency_ms: 0,
                              ban_total: 0, combos: [], filters: [] };
   const emptyL2: L2Trace = { top: [], heatmap: [], dropped: 0, score_latency_ms: 0 };
   const emptyL3: L3Trace = { status: "skipped", resolved_provider: "—", model: "—",
     latency_ms: 0, input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0,
     cache_creation_input_tokens: 0, system_prompt_chars: 0, user_message_chars: 0,
     stop_reason: "—", max_tokens: 0, temperature: 0, candidates_returned: 0,
     fallback_chain: [], system_prompt: "", user_message: "",
     tool_input: { name: "", description: "", input_schema: {} },
     raw_response_blocks: [], validator_errors: null };
   const emptyFinal: FinalRow[] = [];
   ```
   字段精确以 `types/trace.ts` 为准 — 实施时打开文件核对字段名 (这里只是骨架估算).
2. `useWaTrace.ts:57-80` stubToRound: 删 line 74-77 的 `ACTIVE_WA_TRACE.rounds[0]` 兜底, 改用 `makeEmptyRound(stub)`. `__partial: true` 保留
3. **App.tsx guard 范围扩**: line 272 `<RoundBanner targetRound={targetRoundFull} baseRound={baseRound} />` 等 — RoundBanner 也读 target round, 如果 round 是 partial 就显示 "数据加载中" 而不是空数字
   - 加 `if (targetRoundFull.__partial && rounds.length > 1) return <div className="panel">round {target} 加载中...</div>;` 在 RoundBanner 内, 或者在 App.tsx 包外层
   - 同样保护 PanelRoundStrip (`RoundBanner.tsx` 内部组件) line 40-91
4. 类型: `RoundRecord.__partial?: boolean` 已存在 (line 78 写了), 不用扩

**简化**: 改最小 — 只在 App.tsx panel 调用处加 `if (targetRoundFull.__partial)` 判断, 不动 RoundBanner / PanelRoundStrip 内部 (它们用 `targetRound.kpi.latency_ms` 等基础字段, empty 骨架也都填了 0, 不会崩).

**验收**:
- 切到有 R2 的 trace, 在 fullToRound resolve 前 (实战 < 200ms 用户基本看不见)
   - 不要看到 R1 mock 的数字 (combo 11k 等)
- console 0 warn
- `npm run typecheck` 通过

### B4 [P1] 改 web_api._attach_feedback_to_meta + 前端显示餐厅名

**改 backend** (`chisha/web_api.py:1125-1139`):
```python
def _attach_feedback_to_meta(item: dict, store_data: dict) -> dict:
    sid = item.get("session_id")
    accepted = (store_data.get("accepted") or {}).get(sid)
    fb = (store_data.get("feedbacks") or {}).get(sid)
    if accepted and not (accepted or {}).get("skipped"):
        out: dict = {"type": "accepted"}
        if (accepted or {}).get("accepted_rank"):
            out["rank"] = accepted["accepted_rank"]
        if (accepted or {}).get("restaurant_name"):
            out["restaurant_name"] = accepted["restaurant_name"]  # ← 新增
        return out
    # ... 保留 stopped / rated 分支不变
```

**改 types** (`apps/debug-ui/src/types/trace.ts`): grep TraceFeedback, 给 accepted 分支加 `restaurant_name?: string`.

**改前端** (`TraceBrowser.tsx:29-49 feedbackGlyph`):
```tsx
if (fb.type === "accepted") {
  const name = fb.restaurant_name || "";
  return (
    <span title={`accepted: ${name || '(餐厅名缺失)'} · rank ${fb.rank}`}>
      <span className="fb-star">★</span>
      {name && <span className="fb-name"> {name}</span>}
      <span className="mono"> #{fb.rank}</span>
    </span>
  );
}
```

**⭐ 渲染丢的根因**: 大概率是 `<span title=...> ⭐ <span className="mono">#{rank}</span></span>` 里 ⭐ 是裸文本节点, 当外层 span 应用了某些 CSS (e.g. `text-overflow: ellipsis` + `overflow:hidden` + 宽度限制) 时可能被截掉. 改用 `<span className="fb-star">★</span>` 包起来, 加 `.fb-star { display: inline-block; min-width: 12px; color: var(--ok); }` CSS 保护.

**CSS** (`apps/debug-ui/src/styles.css`):
```css
.tb-row .l3 .fb-star { color: var(--ok); font-weight: 700; }
.tb-row .l3 .fb-name {
  color: var(--t-1); max-width: 8em;
  display: inline-block; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
  vertical-align: bottom;
}
```

**测试**:
- `tests/test_web_api.py` (or `tests/test_trace_store.py` 加 web_api fixture) 加 1 个 case: feedback_store 含 accepted 记录 (sid X, restaurant_name Y, rank 2) → `/api/traces` 返回的 item.feedback 必须含 `restaurant_name: "Y"`

**验收**:
- trace `22bfb296f355496d` 列表项显示 "★ 肖三胖·老湖南品... #2" (省略号截断), hover tooltip 完整名

### B5 [P2] trace 列表轮询

**改法** (`useWaTrace.ts`):
1. 用 ref 持久化 activeTraceId, 防 stale 闭包 (B1 也用):
   ```ts
   const activeTraceIdRef = useRef(activeTraceId);
   useEffect(() => { activeTraceIdRef.current = activeTraceId; }, [activeTraceId]);
   ```
2. 新增独立 useEffect, 仅当 `backendOnline` 时轮询, mount 时 5s 起跑:
   ```ts
   useEffect(() => {
     if (!backendOnline) return;
     const ac = new AbortController();
     const handle = setInterval(async () => {
       try {
         const list = await fetchTraces({ limit: 50, signal: ac.signal });
         if (ac.signal.aborted) return;
         if (list.length > 0) setTraces(list);
       } catch { /* silent — backend 临时 5xx 不响铃 */ }
     }, 5000);
     return () => { clearInterval(handle); ac.abort(); };
   }, [backendOnline]);
   ```
3. **不要触发 activeTrace 切换**: setTraces 仅更新列表, 不调 setActiveTraceIdState
4. `fetchTraces` 在 `apps/debug-ui/src/api/client.ts` 加 optional `signal` 参数

**StrictMode 双跑承认** (Codex Round 2 issue #3 修订): React 18 StrictMode dev 下 mount effect 必跑两次, dep array 不能压制. 这是 dev-only 现象, prod 没有. **明确接受 dev 5s 周期内偶发 N+1 请求**. AbortController 防 unmount 时未完成 fetch 漏判 setState (StrictMode unmount→remount 之间 ac.abort 触发, cancellation 把异步 setState 吞掉).

**双调 list 现象明确不修**: 现有 `/api/traces` mount 双调是 StrictMode dev only, prod 单调, 不阻碍 polling 加入. 5s 周期下不会和双 mount 叠加成请求风暴.

**验收**:
- 在 :5173 用户端做一次新推荐, 5 秒内 :5174 列表自动出现
- backend 临时挂掉, console 不出现循环 error (silent catch)

## 测试策略

### pytest 基线必须保持
- 791 passed + 1 skipped + 5 deselected
- 新增 1-2 个测试:
  - `tests/test_web_api*.py`: `_attach_feedback_to_meta` restaurant_name 派生 (1 case)
  - `tests/test_web_api*.py` or 同文件: `/api/trace/{sid}/round/R1` l3.status=config_error 时透传 (1 case)

### 前端 typecheck
- `cd apps/debug-ui && npm run typecheck` 0 error

### 前端 unit test
- **不引入 vitest** (overengineering for this size). 改动以 backend integration + chrome-devtools-mcp e2e 覆盖

### chrome-devtools-mcp golden path
顺序执行, 验所有 6 bug:
1. 打开 `:5174` → 默认进最新 trace
2. **B1 验**: IntentStrip 显示 "R2 · ...", network 拉 `/round/R2`
3. **B2 验**: snapshot R2 节点 role=button, Tab 聚焦 + Enter 切轮次
4. **B3 验**: 快切几个 trace, console 0 warn, 不见 R1 mock 数字 (combo 11k 等) 闪现在其它 trace 的 panel
5. **B4 验**: 列表项显示 "★ 肖三胖... #2"
6. **B5 验**: 在 :5173 curl /api/recommend, 5s 内 :5174 新条目出现
7. **B6 验**: 切到 `c205f8a61d521b49` R1, PanelL3 显示 isConfigError callout 含真实 fallback_reason
8. 全程 console 0 error, network 0 4xx/5xx (除 favicon)

## 回归风险

- **R1 (B6 改 adapter)**: 影响所有 trace L3 显示 — 必须保持 happy path (l3.status=ok) 完全不变. 单测覆盖
- **R2 (B1 effect)**: 拆 effect 可能导致初次 mount 切 trace 的 race. 加 `if (trace.meta.id !== activeTrace) return` guard
- **R3 (B3 stub)**: 替换 mock 兜底用空骨架, panel 内部循环若假设 `.length > 0` 会崩 — 已 verify 主 panel 都用 `.map`/`.length` 安全
- **R4 (B4 backend)**: 新增 `restaurant_name` 字段, 老前端 (没此 type 字段) 直接忽略 — 向前兼容
- **R5 (B5 polling)**: silent catch + 5s 间隔, 失败不阻塞. 唯一风险是 backend 接连 5xx 时背景一直发请求 — 可接受 (开发场景)

## 回滚

每个 bug 单独 commit. 整体回滚: `git reset --hard c3759a8` 回到 D-086.

## 实施顺序 (依赖 + 风险递增)

1. **B6** (改 adapter — 风险最高, 先修)
2. **B1 + B5** (App.tsx + useWaTrace.ts 改 effect, 一个 commit)
3. **B2** (CSS + button 标签)
4. **B4** (跨 backend/前端, 含 backend 测试)
5. **B3** (改 RoundRecord 默认值, 谨慎)

每改一项: chrome-devtools-mcp 验 + `npm run typecheck` + 全套 pytest

## docs/decisions.md D-087 (≤15 行)

```markdown
## D-087: Debug UI (D-080~D-085) 渲染层 bug 修复 — 2026-05-19

D-080~D-085 backend 完整, 5-19 验收暴露 6 个 debug-ui 显示 bug. 核心根因:

1. adapter `adaptL3` 把 `l3.status=config_error` 硬转成 `"skipped"`, 违反
   CONTRACTS §39 精神 (config_error 应保留并 hard surface).
2. App `activeRound` 硬编码 R1 不读 `meta.latestRound`, 用户 refine 完看不到 R2.
3. backend `_attach_feedback_to_meta` 只传 type/rank, 不传 restaurant_name,
   导致 TraceBrowser 显示 "+2" 而不是 "★ 肖三胖 #2".

修法: adapter pass-through status + App reset 键挂 `trace.meta.latestRound` +
backend 派生增 `restaurant_name`. 顺手把 RefineTimeline 节点改 button, 加
trace list 5s 轮询. 1-2 commit, 落 specs/Debug.md / plans/Debug.plan.md.
```

## 完成标准

- ✅ 6 bug 全修 + chrome-devtools-mcp golden path 全过
- ✅ pytest 全绿 (基线 791 + 新增 1-2)
- ✅ `npm run typecheck` 0 error
- ✅ 1-2 commit (含 backend `web_api.py` + 前端)
- ✅ D-087 落 decisions.md
- ❌ 不 push 不开 PR

## 给 Codex Round 3 复审的关键提示

Round 3 相对 Round 2 的差异 (针对 3 个 Round 2 BLOCKED issue):
1. **B1 stale guard 下沉到 useWaTrace.ts**: `setActiveTrace(wa)` 前用 `cancelled` 标志 + `activeTraceIdRef.current` 比对丢弃过期 fetch. App.tsx 那层 guard 删除 (重复)
2. **B6 加 frontend e2e 断言**: chrome-devtools-mcp snapshot 必须含 `CONFIG_ERROR` 不含 `LLM rerank 关闭`, 不只是 backend contract test
3. **B5 StrictMode 双跑明确接受**: 改用 AbortController 防异步 setState 在 unmount/remount 之间漏判, 不再误声称 dep array 能压制
- Q3 (B3/B6 collision) Round 2 已 SOUND, 沿用

历史决策 (Round 1→Round 2 完成):
- B4 backend = `web_api.py:_attach_feedback_to_meta`
- B6 根因 = `adapter.ts:210-234 adaptL3` + `wrapTraceL3:349-353`
- B3 = makeEmptyRound + 全字段填空骨架

# Sandbox Lab 落地 design brief (D-088 草稿)

> 状态:草稿 / 待 codex review · 创建 2026-05-19 · 志丹拍板 scope · 草稿期不进 docs/decisions.md
> 设计源:`chidiansha-sandbox/project/sandbox-lab/` (HTML 原型, inline Babel)
> Handoff:`chidiansha-sandbox/project/sandbox-lab/HANDOFF_PROMPT.md`

## 目标

把"白盒时光机" Sandbox Lab 从 HTML 原型落到 chisha 仓库,作为独立 SPA `apps/sandbox-lab/` (:5175),共用 `chisha.debug_server` (:8765) 后端。一个 7~14 天的可回放、可分支、可改规则的推荐沙箱。

## scope 拍板 (志丹 2026-05-19)

1. **多 session + branch/rollback 完整版**:不做单 session 简化
2. **Refine 单 round** (B panel 改文案为"当前 round 已应用"):不做跨顿 TTL 持久化,留 v2 D-XXX
3. **新建 `apps/sandbox-lab/` 独立 SPA**:不并入 `apps/debug-ui` (后者 read-only invariant 必须保留)
4. **不做 (Phase 0 内不做)**:Tweaks 暴露给用户;在线 trace 平台对接 (设计稿里 `trace.example.com` 改成内嵌跳 debug-ui :5174/?trace=)

## 架构

### 前端 `apps/sandbox-lab/` (React + Vite + TS,镜像 debug-ui)

```
apps/sandbox-lab/
├── index.html
├── package.json (port 5175)
├── vite.config.ts (proxy /api → :8765, VITE_API_TARGET 覆盖)
├── tsconfig.json
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── styles.css                    # 从原型 1:1 搬, CSS variables/tokens
    ├── api/
    │   ├── client.ts                 # fetch wrapper + backend online detection
    │   ├── adapter.ts                # backend schema → view-model
    │   └── backend-types.ts          # FastAPI 端的 dict shape (供 adapter)
    ├── types/
    │   └── sandbox.ts                # Session / Meal / Rec / Decision (handoff §数据契约)
    ├── hooks/
    │   ├── useSandbox.ts             # 单 store: sessions + activeSession + clock + recs + history
    │   ├── useTweaks.ts              # 主题/密度/调试层/accent
    │   └── useKeyboard.ts            # Esc / shortcuts
    ├── components/
    │   ├── TopBar.tsx                # session 下拉 + clock pill + 摘要按钮
    │   ├── Banners.tsx               # 餐次作用域 + 派生 conflict + transient
    │   ├── Timeline.tsx              # 14 格横向/日历卡 (variant) + op-bar
    │   ├── DecisionArea.tsx          # 5 推荐卡 + refine 行 + preset chips + skip
    │   ├── ReviewCard.tsx            # 回顾模式只读
    │   ├── RecCard.tsx               # 主产品卡 + 调试层叠加
    │   ├── panels/
    │   │   ├── DPanel.tsx            # 上顿决策因果链 (紧凑/标准/详细 3 档)
    │   │   ├── APanel.tsx            # 长期画像 (taste)
    │   │   ├── BPanel.tsx            # 活跃规则 (refine 当前 round + blacklist)
    │   │   └── CPanel.tsx            # 近期窗口 (recent 4 顿 + fatigue)
    │   ├── modals/
    │   │   ├── SummaryDrawer.tsx
    │   │   ├── RefineModal.tsx       # (handoff 留, 现阶段只用 inline refine row)
    │   │   └── ConfirmModal.tsx      # rollback / branch 二次确认
    │   └── TweaksPanel.tsx           # dev-only, ?dev=1 开
    └── mocks/
        └── sbxMocks.ts               # 从 data.js 搬, backend offline fallback
```

**视觉系统铁律 (与 debug-ui 一致)**:
- 字体: Inter + Noto Sans SC + JetBrains Mono(数字/trace id)
- ACCENT_PALETTE 4 套 indigo/绿/玫红/琥珀,每套含 accent/hover/soft/softer/ink/ring → CSS variables,Tweaks 切换整套换
- 暗色 `body.theme-dark`,紧凑 `body.density-compact`
- 不 inline 颜色,所有色值走 CSS variable

### 后端 (chisha/ + web_api.py)

#### 多 session 落盘改造 (chisha/sandbox.py + data_root.py)

现在:`logs/sandbox/{state.json, meal_log.jsonl, sessions/, feedback/, ...}` 单一全局
改后:`logs/sandbox/sessions/{sid}/{state.json, meal_log.jsonl, feedback/, recommend_log.jsonl, recommend_trace/, long_term_prefs.json, profile.yaml, decisions/, meal_to_trace.json}` + `logs/sandbox/_meta.json` (schema version + migration 标记)

**关键约束 (Codex must-fix #1 + gotcha #2)**:
- **不走 active.json 全局切换**:`data_root.*_path(root, session_id=...)` 显式参 sid 必传 (sandbox 启用时)。任何包装调用 (eat 内部串 /recommend) 都通过 `with sandbox_session_context(sid):` ctxvar 注入 sid,绝不靠全局 active 标记。**"active session" 只是前端 UI 概念**,后端永远显式 sid。
- 兼容老路径:`logs/sandbox/` 下直接放数据的旧 layout → migration 一次性挪到 `sessions/_legacy/`,`_meta.json` 落 `migrated_at + schema_version=2`,migration 幂等可重跑
- 真实(非 sandbox)路径不动
- pytest D-077 旧用例:新增 `chisha.sandbox.init()` 仍然接受老调用形态,内部包装成创建 `sessions/_default/` + `_meta.json`,旧 fixture 不改

#### Per-meal 时钟

`logs/sandbox/sessions/{sid}/state.json` 加字段:
```json
{
  "enabled": true,
  "name": "session-新打分",
  "seed": 42,
  "profile_label": "profile@v2",
  "origin": "real_snapshot|blank",
  "total_meals": 14,
  "current_meal_idx": 4,             // 0-based, 0=D1午, 1=D1晚, ..., 13=D7晚
  "history": [                       // 每顿落一条 ref
    {"idx": 0, "session_id": "20260515_lunch_a1b2", "state": "eat", "dish": "川味小炒"},
    {"idx": 1, "session_id": "20260515_dinner_c3d4", "state": "eat", "dish": "潮汕牛肉"},
    {"idx": 2, "state": "skip"},
    {"idx": 3, "session_id": "20260516_dinner_e5f6", "state": "eat", "dish": "寿司拼盘"}
  ],
  "current_date": "2026-05-15",       // 衍生自 meal_idx (idx//2 天起算)
  "day_index": 1,
  "branch_from": null,                // 分支元数据
  "branch_from_meal_idx": null
}
```

helper:`meal_idx_to_slot(idx) → ("lunch"|"dinner", day_index)` 在 sandbox.py 内。

**Codex must-fix #3 — clock 走 session context**:
- 新增 `chisha/sandbox_context.py`:`ContextVar[str | None] _current_sid`,with-statement 注入
- `clock.today(root)` 内部:if sandbox 启用 → 读 `sandbox.current_date(root, sid=_current_sid.get())`,否则 prod
- web_api 端点 wrapper:`with set_sandbox_session(sid): recommend_meal(...)`,确保多 tab 并发请求 sid 不串
- 非 active session 调 /sandbox/.../trace 等读路径也必须传 sid,绝不依赖全局 active

#### 新增端点 (POST 全部 `_require_localhost`)

```
GET    /api/sandbox/sessions                    list[SessionMeta]
POST   /api/sandbox/sessions                    {name, days, seed, origin} → SessionMeta
GET    /api/sandbox/sessions/{sid}              FullSnapshot: state + current_recs + last_decision + active_rules
POST   /api/sandbox/sessions/{sid}/activate     切 active.json
POST   /api/sandbox/sessions/{sid}/eat          {rec_rank, exclude_ids?} → 内部串 /recommend + /accept + meal++ + day++ (dinner→next-day lunch)
POST   /api/sandbox/sessions/{sid}/skip         同上,无 /accept,标记 skip
POST   /api/sandbox/sessions/{sid}/swap         {exclude_ids} → 重 /recommend
POST   /api/sandbox/sessions/{sid}/refine       {text} → 调 /refine, 同 round 内更新 recs
POST   /api/sandbox/sessions/{sid}/rollback     {meal_idx} → 裁 history + 删 meal_idx 后的 sessions/recommend_log/meal_log/trace 行,reset L1 prefs
POST   /api/sandbox/sessions/{sid}/branch       {from_meal_idx, name} → 拷贝 sessions/{sid} → sessions/{new_sid},裁到 from_meal_idx
GET    /api/sandbox/sessions/{sid}/meal/{idx}/trace   返 {trace_session_id, round_id} 供前端跳 debug-ui
```

复用现有:`/api/recommend`, `/api/refine`, `/api/accept`, `/api/skip`, `/api/traces` (内部 web_api 包装调用,前端不直调)

#### D panel (上顿决策因果链) 数据来源

每顿 eat/skip 后,在 `sessions/{sid}/decisions/{idx}.json` 落一条:
```json
{
  "when": "D3 午",
  "pick": "蓉香记 · 回锅肉+蒜苗炒腊肉",
  "rank": 2,
  "l3": 92,
  "diff": [...],          // 派生:对比 meal_idx 前后两次 L1 prefs + meal_log + recent
  "implications": [...]   // 派生:从 diff 推断 (下一顿同菜 fatigue, refine TTL --)
}
```

**diff 派生器** `chisha/sandbox_decision_diff.py`(新增):
- recent_dishes diff:对比 history (簡單)
- fatigue diff:对比 history 内同 restaurant_id 出现次数
- taste diff:对比 long_term_prefs.json 前后两次磁盘(eat 完触发 LLM 抽取后)
- refine TTL:当前 session 单 round,显示"当前 round 已应用 X" (无 TTL --)

eat/skip 端点内部 build 完 decision 落盘,前端 GET `/api/sandbox/sessions/{sid}` 时一起带回。

**Codex must-fix #4 — L1 extraction 状态隔离**:
- `sessions/{sid}/state.json` 的 `last_l1_extraction` 字段加 `trigger: "meal_eat"|"day_advance"`
- `sandbox.record_l1_extraction(...)` 加 `trigger` 参数,旧调用默认 `day_advance` (D-077 兼容)
- eat 端点内 wrapper 触发 L1 抽取后调 `record_l1_extraction(status, trigger="meal_eat", sid=...)`
- `/api/sandbox/inspect` 返回时把 trigger 一并暴露,前端 D panel 看得到

**Codex gotcha #1 — trace v3 按 meal_idx 索引**:
- `sessions/{sid}/meal_to_trace.json`:`{"0": "20260515_lunch_a1b2", "1": "20260515_dinner_c3d4", ...}`
- eat 端点拿到 /recommend 返回的 session_id 后,落 `meal_to_trace[idx] = sid`
- rollback 时按 meal_idx 反查 trace_session_ids → 删 `recommend_trace/{sid}.json` + meal_to_trace 截断
- gotcha #3 branch:拷贝完整 sessions/{src}/ → sessions/{new}/ 后,按 from_meal_idx 显式裁掉 meal_to_trace + decisions/{idx>=from}.json + recommend_log.jsonl 行 + meal_log.jsonl 行;**同时重置 L1 prefs 到分支点之前的状态** (从 _legacy/L1 snapshot 重抽,或直接清空让下次 eat 重新抽取)

#### 5 条推荐 → Rec view-model (adapter)

设计稿 `Rec` 字段:rank/name/venue/dishes/price/why/l1Hits/l2/l3/boost/intent/explore/conflict/meta. 后端 `format_v2_candidate` 已有:
- rank ✓, name (= restaurant_name), venue, dishes (= combo.dishes), price (= combo.estimated_price), why (= reasoning), l3 (= rerank_score, 0-100), l2 (= score, 0-1), intent (= refine_intent.summary_text), explore (= is_explore), meta (eta/dist/protein/oil 字段已部分有)
- **缺**:`l1Hits` (需要从 L1 trace 抽 top hits), `boost = l3 - l2*100` (派生), `conflict` (从 hard_filter_events 派生 — refine_intent.exclude_keywords 命中)

adapter 在前端 `src/api/adapter.ts` 内,**后端 schema 变只改 adapter**。

## 关键交互验证(对应 handoff §验收清单)

- [ ] TopBar session 下拉切换 → /sessions/{sid}/activate + 重渲染
- [ ] "就这个 →" → /eat + history++ + clock++ + 新 recs + banner 清空
- [ ] "跳过" → /skip + 同上 + D panel 显"跳过未学习"
- [ ] refine 输入 → /refine + recs 重排 + transient banner
- [ ] timeline 点过去格 → 只读 ReviewCard + D panel 切到那顿 + banner 切回顾
- [ ] Esc 退出回顾/关 modal/关 drawer
- [ ] 回滚 → ConfirmModal → /rollback + history 裁 + clock 回
- [ ] 分支 → ConfirmModal → /branch + session 下拉新条目
- [ ] 主色切换 → 整套 accent 变量同时换
- [ ] 暗色 → 无硬编码色
- [ ] 推荐卡骨架与 chisha-user 一致 (复刻 `apps/web` 卡片视觉)
- [ ] mono 字体应用到数字/trace id/L3 分数

## 子任务拆解 (供 /run-task)

> 任务粒度:每个能独立 PR + 验证。前端 chrome-devtools-mcp 自测,后端 pytest + dry_run。
> Codex must-fix #5 已应用:S-06 拆成 S-06a/b/c;S-09 (diff 派生器) 提到 S-07 前。

### 前端 (mock-first,不依赖后端)

1. **S-01 scaffold**:`apps/sandbox-lab/` 工程脚手架 (package.json/vite/tsconfig/main.tsx/proxy 5175→8765),空 App 跑通 + 主题切换
2. **S-02 视觉 + 静态布局**:从原型 styles.css 1:1 搬,TopBar / Banners / Timeline / DecisionArea / ReviewCard / Panels (A/B/C/D) 全部 mock 数据跑通,chrome-devtools-mcp 验证暗色 + accent 切换 + 紧凑密度
3. **S-03 交互骨架 (mock)**:eat/skip/swap/refine/select-cell/op-bar/rollback/branch 全部本地 state 跑通,handoff §验收清单 11 条在 mock 下全过

### 后端 (session 上下文 + 端点)

4. **S-04 sandbox_context + data_root session_id**:新建 `chisha/sandbox_context.py` (ContextVar),`data_root.*_path(session_id)` 显式参,`clock.today()` 改读 ctx sid。pytest D-077 用例全绿
5. **S-05 多 session 落盘改造 + migration**:`chisha/sandbox.py` 改 sessions/{sid}/state.json + _meta.json schema v2;migration 把老 logs/sandbox/ 数据挪到 sessions/_legacy/;state.json 加 current_meal_idx/history/total_meals/branch_from + last_l1_extraction.trigger
6. **S-06a sessions CRUD 端点**:`GET/POST /api/sandbox/sessions`, `GET /api/sandbox/sessions/{sid}`(返 FullSnapshot stub)
7. **S-06b per-meal 时钟 + decision diff 派生器**:`chisha/sandbox_decision_diff.py` (纯函数 + 单测),`sandbox.advance_meal(sid)` helper,test 验 idx//2 派生 day + dinner→next-day lunch 自动 day++
8. **S-06c eat / skip / swap / refine 端点**:`POST /api/sandbox/sessions/{sid}/{eat,skip,swap,refine}`,内部 `with set_sandbox_session(sid)` 包装 /recommend /accept /refine /skip,write meal_to_trace.json + decisions/{idx}.json,显式触发 L1 抽取 (trigger="meal_eat")。**LLM 异步**:返 `{job_id, status: "running"}`,前端 polling `/api/sandbox/sessions/{sid}/jobs/{jid}`;支持 `?mock_recommend=1` query 让 chrome-devtools-mcp 自测不烧 LLM
9. **S-07 rollback / branch 端点**:`POST .../rollback {meal_idx}` (裁 meal_to_trace + decisions + meal_log + recommend_log + 删 trace 文件 + 重置 L1 prefs + 截 history);`POST .../branch {from_meal_idx, name}` (shutil.copytree + 同样裁剪 + branch_from 元数据);pytest 验"rollback 后再 eat 不读到老 trace"

### 联调 + 收尾

10. **S-08 前后端联调 + adapter**:前端 `src/api/adapter.ts` backend dict → view-model,useSandbox 改调真后端,backend offline 自动 fallback mock,handoff §验收清单 11 条在真后端下全过 (用 ?mock_recommend=1 跑 14 顿)
11. **S-09 trace 跳转**:meal trace → debug-ui :5174/?trace={sid}&round=R1 新页 (debug-ui 接 URL query 自动选 trace,看是否已有 query 解析,没有就加)
12. **S-10 文档收尾 + neat-freak**:docs/decisions.md 加 D-088 ≤15 行;CONTRACTS.md 加 sandbox session context invariant + meal_to_trace index 约束;CLAUDE.md 加 :5175 启动命令;design brief 转正

## 数据契约(供前端 + adapter)

### `SessionMeta`
```ts
{
  id: string; name: string; days: number;       // 7|14
  seed: number; profile: string;                  // "profile@v2"
  origin: "real_snapshot"|"blank";
  status: "running"|"done";
  lastUsed: string;                               // human "刚刚"|"昨天"|ISO
  currentMealIdx: number;                         // 0..total-1
  totalMeals: number;                             // days*2
  branchFrom: string|null;
}
```

### `FullSnapshot` (GET /sandbox/sessions/{sid})
```ts
{
  meta: SessionMeta;
  clock: {idx: number; day: number; slot: "午"|"晚"; total: number};
  history: Meal[];                                // idx<currentIdx
  currentRecs: Rec[];                             // 5 条 (从最近一次 /recommend cache)
  lastDecision: Decision|null;
  activeRules: {
    refine: {label: string; sinceRound: number; sessionId: string}[];  // 单 round, 无 TTL
    blacklist: {name: string; reason: string}[];
  };
  taste: {name: string; v: number; delta: number; color: string}[];
  keywords: {tag: string; isNew: boolean}[];
  recent: string[];                               // 最近 4 顿
  fatigue: {name: string; count: number; hot: boolean}[];
}
```

`Meal` / `Rec` / `Decision` shape 与 handoff §数据契约 一致。

## 风险 + 兜底 (整合 codex audit)

- **session context 跨请求**:`set_sandbox_session(sid)` 必须 ContextVar 不是模块全局变量,否则两个 tab 并发 eat 会串。pytest 覆盖并发场景 (asyncio.gather)
- **L3 LLM 真跑**:14 顿 × ~20s ≈ 5min/session,S-06c 强制 async + polling job table + `?mock_recommend=1` flag
- **rollback 文件删除原子性**:必须按 meal_to_trace.json 反查所有 trace_session_ids,删完再 truncate jsonl,中间断电留 partial state。S-07 用 tmp + atomic rename
- **branch 完整裁剪 (gotcha #3)**:拷贝后必须重置: meal_to_trace、decisions/、recommend_log.jsonl、meal_log.jsonl、long_term_prefs.json (清空让下次 eat 重抽)、recommend_trace/、last_l1_extraction。漏一个就有未来记忆泄漏
- **decision diff 取数时机**:L1 抽取是 LLM 调用 (~10s),不能阻塞 eat 端点。S-06c 设计成 eat → 同步落 history + meal_to_trace + 返 job_id,异步 build decision diff + L1 抽取,decision 落盘后前端再 polling 拿
- **D-077 兼容压力**:S-04 + S-05 必须保留 `chisha.sandbox.{init, advance, reset, disable, state, current_date, is_enabled}` 原签名,内部全部加 `sid: str | None = None` 参,None 走 `_default` session。旧 fixture/pytest 不改

## 不做

- Tweaks 给最终用户(handoff 明文)
- 在线 trace 平台(handoff 里 trace.example.com 改成跳 debug-ui :5174)
- "去美化推荐卡视觉骨架"(handoff 明文)
- 全局通知中心(banner 仍餐次作用域)
- D panel 密度只换字号(handoff 明文,真换信息量)
- Refine 跨顿 TTL 持久化(v2 D-XXX)

---

end of brief.

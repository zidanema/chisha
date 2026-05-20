# Debug Console · Workflow A 落地 brief (2026-05-18)

> Source of truth: `chisha-debug/project/` (Claude Design 已定稿) + 志丹的 prompt v2 (本对话)
> 范围: 把 Workflow A 「分析 trace」从设计稿落到 `apps/debug-ui/`, 同步补齐后端
> trace 多轮持久化. **B workspace「沙盒模拟」本期不做** (lock + toast).
>
> **关键定位 (2026-05-18 志丹确认): 100% 只读 trace replay / debug 工具**.
> 砍 Followup (不写新 round) / 砍 Live / 砍 WhatIf / 砍 "+ new trace" / Lookup 在
> 已选 trace+round 里反查 (零新后端接口). 推荐链路真触发都在用户端走, debug 台只
> 观察/分析它落盘的 trace.

## 0 · 边界总览

| 项 | 已有 | 设计稿要求 | 差距 |
|---|---|---|---|
| 前端骨架 | `apps/debug-ui/` Vite+React+TS (Phase 1-7 完成, tab 模式) | TraceBrowser+Workspace 双区, 砍 tab | 重写 App.tsx + Sidebar; 复用 panel-l1/2/3/final + DagHeader + Theme |
| L1/L2/L3/Final panel | 已有 | 复用, 接 `currentRound` 数据 (而非 window.MOCK swap) | 改成接 props (基本已是) |
| Trace 列表 | `GET /api/debug/sessions` (扁平 meta) | `GET /api/traces` (含 round 树 meta) | 加新端点 / 改 shape |
| Trace 详情 | `GET /api/debug/sessions/{id}` (含单 `refine` dict) | `GET /api/trace/{id}` 返 `{meta, rounds[]}` | 改 shape + rounds array 化 |
| Refine 多轮 | `base_trace["refine"]` 单 dict, 每次覆盖 | 同一 trace 文件 R1/R2/R3/R4 全保留 | **trace_store schema bump v2→v3, refine 改 rounds[]** (用户端的 /api/refine 写盘逻辑改) |
| 新建首轮 | `POST /api/recommend` 已有 | (砍, 用户端走) | 0 |
| Refine 提交 | `POST /api/refine` 已有 (用户端用) | (debug 台不接, 不 mutate) | 0 (但写盘逻辑要改, 见 §1.2) |
| 追溯 | `apps/debug-ui` Trace tab (前端拼) | LookupDrawer 在当前 trace+round 反查 | 纯前端, 0 后端新接口 |
| WhatIf / Live | 现 `apps/debug-ui` 有 | 设计稿无 | **彻底拆: 代码删, /api/debug/what_if 留作未来 B workspace 备用** |

## 1 · 后端补齐 (3 个变更, 只读定位下范围大幅收窄; **Codex review 第二轮后改成目录拆文件**)

### 1.1 trace_store schema v2 → v3: 单文件 → 目录拆 round

**新存储布局** (Codex 方案, 一次性解决 race + 分页 + 大小):

```
logs/recommend_trace/
├── {sid}.json                  ← v2 旧文件 (read-only, on-read migrate)
└── {sid}/                      ← v3 目录
    ├── meta.json               ← TRACES item shape + {round_ids: ["R1","R2",...]} (小, < 5KB)
    └── rounds/
        ├── R1.json             ← {id, started_at, user_input, intent_v2, kpi, diff, l1, l2, l3, final, __frozen} (单 round 完整, 1-5MB)
        ├── R2.json
        └── ...
```

收益:
- ✅ append round = 写新文件 R{n}.json + 改 meta.json 的 round_ids 数组, 不再 read-modify-write 大 trace
- ✅ 分页天然: list 读 meta.json (~5KB × N), detail 读 meta + 按需读 round
- ✅ 50MB 单 round 才触发硬上限 (4 轮各 5MB 不冲突)
- ✅ 并发 refine 写不同 round 文件不冲突 (只有 meta.json 需要 lock)

**lock 策略**:
- `meta.json` 用 `fcntl.flock` 或文件原子 rename (一致 critical section)
- `update_meta(sid, mutator)` helper: open(LOCK_EX) → load → mutate → atomic replace → unlock
- `R{n}.json` 写盘走 tmp+rename, 不需要 lock (一次写, 不再改)

**Round id 唯一性**:
- 服务端签发 round_id = `f"R{len(meta.round_ids)+1}"`, 在 meta lock 内决定, 永不重号
- session.py `state.round` 仍按需自增 (业务语义), 但 trace 文件 round_id 走 meta lock 路径

**Migration v2 → v3**:
- 读到 `{sid}.json` (v2) → 内存构造 v3 view (`meta` + `rounds = [R1 from top-level + refine_field if applied]`), 不写回磁盘
- 下次 `/api/refine` 写盘时, 触发 v2 → v3 文件迁移: `{sid}.json` 拆成 `{sid}/meta.json` + `R1.json`, 然后追加新 round
- `ACCEPTED_TRACE_VERSIONS = {1, 2, 3}`; `TRACE_SCHEMA_VERSION = 3`

### 1.2 `/api/refine` 改写盘逻辑 (debug 台不调它, 但用户端调它后写出来的 trace 要符合 v3 才能给 debug 台用)

`web_api.py:91-255` 当前把 refine 数据 merge 到 `base_trace["refine"]` (覆盖). 改成:
```python
# 新写盘 (走 trace_store v3 helper)
def append_round(sid, round_payload):
    with trace_store.lock_meta(sid):
        meta = load_meta(sid)             # 不存在则从 v2 单文件 migrate
        round_id = f"R{len(meta['round_ids']) + 1}"
        meta['round_ids'].append(round_id)
        meta['latest_round'] = round_id
        meta['refine_count'] = len(meta['round_ids']) - 1
        write_round_file(sid, round_id, round_payload)  # 独立文件, 不需 lock
        write_meta(sid, meta)             # atomic replace
    return round_id
```
- **API 入参 / 出参 shape 完全不动** (用户端正在用, 不冒险). 只改写盘形状.
- `round_payload` 含: `id, started_at, user_input, intent (V1), intent_v2, narrative, kpi, l1, l2, l3, final, diff{vs,in,out,up,down}, __frozen`
- diff 计算: load 上一 round 文件读 final top5, 集合对比
- Round id **服务端签发** (基于 meta.round_ids 长度), session.py `state.round` 业务语义保留但不再决定 trace round_id

### 1.3 `/api/traces` + `/api/trace/{id}` + `/api/trace/{id}/round/{rid}` (新, debug 台读盘用)

| 端点 | 返 | 大小 |
|---|---|---|
| `GET /api/traces?limit=50` | `[TraceMeta]` 列表 (从 meta.json 直读) | ~5KB × 50 = 250KB |
| `GET /api/trace/{id}` | `{meta, rounds: [RoundStub]}` (stub = `{id, started_at, user_input, intent_v2, kpi, diff}`, **不含** l1/l2/l3/final body) | ~20KB |
| `GET /api/trace/{id}/round/{rid}` | 单 round 完整 (l1/l2/l3/final/__frozen) | 1-5MB |

- `TraceMeta` shape 对齐设计稿 TRACES item: `{id, date, time, daysAgo, meal, finalTop1, refineCount, latestRound, source, feedback, status, latency_ms}`
- `daysAgo` 后端按服务端 today 算 (避免前端时区漂移)
- 前端按需 fetch round + LRU cache (**字节上限 50MB**, 不是条数)
- 旧 `/api/debug/sessions(/.*)` 不删 (有别处依赖), 新端点是新 shape 并存

### 1.4 LookupDrawer (零后端新接口) + Intent schema descriptor

LookupDrawer:
- 只在当前已选 trace+round 的内存数据里反查
- 餐厅名/菜名 fuzzy match → 查 `round.l1.candidates` / `round.l1.dropped_dishes` / `round.l2.combos` / `round.final`
- 输出 stage_dropped 分类 (hard_filter / diversity / price / brand_cap / restaurant_cap / l2_top60 / l3 / final)
- 砍掉 WA mock 文案 "重跑 pipeline + 高亮", 改成 "在当前 R{n} 反查"

Intent schema descriptor (Codex 推荐 schema-driven):
- `GET /api/intent_schema` 返字段元信息: `[{key, label, tone, group, slot_path}]`
- 前端 IntentStrip 按 descriptor 渲染, 未知字段 (新加 schema 字段) 自动进 "other" 分组
- V2 schema 后续扩字段无需动前端

## 2 · Intent 字段对齐 V2 (志丹决策: 以推荐链路事实标准为准)

**设计稿原 INTENT_FIELDS** (wa-refine.jsx:3-15) 12 项是 mock 数据约定, 不是视觉锁定项 → 改成 V2 真字段, 视觉组件 (intent-field 块 + want/avoid/neutral 色块) 不动.

**新 INTENT_FIELDS 字段集** (与 RefineIntentV2 schema 一一对应):

| 字段 key | 标签 | tone | V2 路径 |
|---|---|---|---|
| cuisine_want | 菜系想 | want | redirect.cuisine_want |
| cuisine_avoid | 菜系不想 | avoid | redirect.cuisine_avoid |
| cuisine_expanded | 菜系扩展 | want | redirect.cuisine_candidates_expanded |
| ingredient_want | 食材想 | want | redirect.ingredient_want |
| ingredient_avoid | 食材不想 | avoid | redirect.ingredient_avoid |
| ingredient_synonyms | 食材同义 | neutral | redirect.ingredient_synonyms |
| brand_avoid | 品牌/餐厅拒绝 | avoid | redirect.brand_avoid |
| cooking_method_avoid | 烹饪方式拒绝 | avoid | redirect.cooking_method_avoid |
| food_form_avoid | 形态拒绝 | avoid | redirect.food_form_avoid |
| oil | 油控 | neutral scalar | constrain.oil |
| price_max | 价格上限 | neutral scalar | constrain.price_max |
| functional | 功能性 | neutral scalar | constrain.functional (low_caffeine / low_satiety_drowsy) |
| reference | 引用 (上一轮 X) | neutral scalar | reference |
| reject_previous | 否决前轮 | neutral scalar | reject_previous (bool) |
| raw_understanding | LLM 自述理解 | neutral freeform | raw_understanding |
| raw_text | 用户原文 | neutral freeform | raw_text |

R1 (首轮无 refine_intent_v2): 显 profile 静态偏好 + "首轮 · 来自 profile, 无 refine 输入" placeholder, 同设计稿首轮处理一致.

`lib/intentAdapter.ts`: trace.rounds[i].intent_v2 → IntentStrip view model. unsupported_in_recall 数组渲染弱色 + tooltip "此字段已抽取, L1/L2 暂不消费, 仅透传 L3 prompt".

## 3 · 前端落地 Phase 计划 (对齐 prompt §6)

**复用 vs 重写**:
- 复用: `panels/PanelL1.tsx` `PanelL2.tsx` `PanelL3.tsx` `PanelFinal.tsx` (微调接 `roundData` props)
- 复用: `components/DagHeader.tsx` `ThemeSwitcher.tsx` `Toaster.tsx` `ui/*`
- 复用: `api/backend-types.ts` `api/adapter.ts` (按新 shape 扩展)
- 砍代码: `App.tsx` (重写), `Sidebar.tsx` (重写成 TraceBrowser), `WhatIfPanel.tsx` `LiveBanner.tsx` (整文件删), `hooks/useTrace.ts` (旧 trace tab 用的, 删)
- 新: `components/TraceBrowser.tsx` `IntentStrip.tsx` `RefineTimeline.tsx` `RoundBanner.tsx` `PanelRoundStrip.tsx` `TraceContextBar.tsx` `LookupDrawer.tsx` `WorkspaceSwitch.tsx`
- **不新增**: Followup, "+ new trace" 按钮 (100% 只读)

Phase 顺序 (每完成停下走 chrome-devtools-mcp 验证 + 让志丹看):

| Phase | 内容 | 后端依赖 | 验证 |
|---|---|---|---|
| 0 | **砍代码先行** (Codex BLOCKER #5): 删 WhatIfPanel/LiveBanner/Sidebar/useTrace, App.tsx 缩到最小 main view | - | tsc clean + 现有 panel 仍能渲染 mock |
| 1 | wa-* 全部 ts 化; mock **直接用 V2 schema 字段** (不走 V1 12 字段一次性 adapter); window.MOCK swap → React props | 无 | 5 主题 + collapse rail + timeline diff + IntentStrip + LookupDrawer 视觉对版 |
| 2a 后端 | trace_store v3 拆文件 + `update_meta` lock helper + v2→v3 migrate + 改 `/api/refine` 写盘 + 加 `/api/traces` `/api/trace/{id}` `/api/trace/{id}/round/{rid}` `/api/intent_schema` | - | pytest 单测 (lock 并发 + migrate + round_id 唯一) + 手工 fetch |
| 2b 前端 | IntentStrip 接 `/api/intent_schema` schema-driven; TraceBrowser/RefineTimeline/PanelRoundStrip 接真 backend; round lazy fetch + LRU 50MB | 2a | 选 trace + 切 round + diff 模式 vs_r1 / 相邻 |
| 3 | LookupDrawer 在内存反查 (零后端新接口) | - | 命中表 + 弹 dish detail |
| 4 | 快捷键: Cmd+K(lookup) / Cmd+/(search focus) / 数字 1-9 切 round / Cmd+F 行内搜 / L3 fallback 桌面通知 | - | 键盘验证 |
| 5 | config_error / skipped / 空 state (没 trace) / 单 round trace (不渲 RefineTimeline) | - | edge case 验证 |
| 6 | README 重写; CONTRACTS.md 加 trace v3 不可变契约 + sandbox source policy; build 0.5.0-A | - | 文档同步 |

注: 砍掉了原 Phase 4 "删旧代码" 单独阶段, 提到 Phase 0 (Codex 指出 brief 内部矛盾, 改成第一步直接清场)

## 4 · 已确认决策 (2026-05-18 志丹拍板)

第一轮:
1. ✅ WhatIfPanel/LiveBanner/Followup/"+ new trace" 代码**彻底删** (100% 只读 trace replay/debug 定位)
2. ✅ trace schema v2 → v3, on-read migrate (不写回旧文件)
3. ✅ Intent 字段对齐 V2 schema 真字段集
4. ✅ LookupDrawer 内存反查, 不开新后端接口
5. ✅ B workspace lock + toast, 本期不做

第二轮 (Codex review 后追加):
6. ✅ **trace 拆目录存储** ({sid}/meta.json + {sid}/rounds/R{n}.json), 一次性解决 race + 分页 + 大小三个问题 (Codex 重设计建议 #1)
7. ✅ **Intent UI schema-driven** (GET /api/intent_schema 返字段元信息, 前端动态渲染)
8. ✅ Phase 1 mock **直接用 V2 schema 字段** (不走 V1 12 字段过渡)
9. ✅ Round id 服务端在 meta lock 内签发, 不依赖 session.state.round 自增
10. ✅ 前端 LRU 限 **50MB 字节数**, 不限条数

## 5 · Codex review 节点

- 本 brief 全文 → Codex 看方案 (有没有盲点 / API shape / trace schema 设计有无更简单做法)
- Phase 1 完成 → Codex 看视觉一致性 + ts 类型 + 文件拆分
- Phase 2a 完成 (后端 trace_store v3) → Codex 看 migration 正确性 + 写盘原子性
- Phase 3 完成 (refine 真链路) → Codex 看 round id 推断 + diff 计算
- Phase 4 完成 → Codex 看 lookup 重跑性能
- Phase 6 完成 → Codex 端到端 e2e

## 6 · 不做 (scope 红线)

- 不写测试 (志丹明令, 单人自用)
- 不引 Tailwind/shadcn/antd/MUI
- 不改 panel-l1/l2/l3/final 内部视觉
- 不做 B workspace (沙盒模拟)
- 不做可访问性 / i18n / 移动端
- 不删 `apps/debug-ui` 的 WhatIfPanel / LiveBanner 代码 (留作后续可能恢复)

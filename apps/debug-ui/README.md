# chisha · debug UI (apps/debug-ui)

Workflow A · **分析 trace** 单页面 SPA。单用户自用,5-20 次/天。

Phase 0 收尾后只剩一个工作流: 浏览历史 trace + 比较 refine 轮次。所有写入路径
(Live / What-if / 反查时重跑) 全部已删, 100% read-only。

视觉系统来自 `chisha-debug/project/wa-*.jsx` 设计稿,Phase 1/2 一字一句搬过来,不允许重设计。

## 本地拉起

两个 server 一起跑:

```bash
# Terminal 1 — 后端 FastAPI (debug 端点)
uv run python -m chisha.debug_server   # http://127.0.0.1:8765

# Terminal 2 — 前端 Vite (SPA)
cd apps/debug-ui
npm install                            # 第一次
npm run dev                            # http://127.0.0.1:5174
```

打开 http://127.0.0.1:5174/ 即可。Vite proxy `/api → :8765` 已配。
后端 offline 时 SPA 自动 fallback 到内置 mock,顶栏 pill 变橙色提示。

**多 worktree 共存**: `VITE_API_TARGET=http://127.0.0.1:8767 npm run dev` 可换 backend
端口 (主 worktree 已占 8765 时)。

## Claude Code 自测约定

改本目录任何 `.tsx` / `.css` / `vite.config.ts` 后, Claude Code 必须用
`mcp__chrome-devtools__*` 工具自驱浏览器验证 (导航 + 走完整 panel 渲染 + 切主题 +
看 console / network), 不许只跑 lint/tsc 就宣告完成. 详见根目录 [`CLAUDE.md`](../../CLAUDE.md) "前端自测" 章节.

## 主题切换

5 套 palette: `dark-cool / dark-warm / dark-mono / light-paper / light-modern`。
- localStorage key: **`chisha:theme`**
- 默认首次打开按系统 `prefers-color-scheme`: dark → `dark-cool`,light → `light-modern`

## 键盘快捷键

| 按键 | 行为 |
|------|------|
| `⌘K` / `Ctrl+K` | 打开 LookupDrawer (反查餐厅/菜在当前 round 落在哪一层) |
| `⌘/` / `Ctrl+/` | focus TraceBrowser 搜索框 |
| `1` ~ `9` | 切到 R{n} (input 焦点时不抢) |
| `Esc` | 关闭 LookupDrawer |

## 数据流

```
Backend trace_store v3 (chisha/trace_store.py)
  └── GET /api/traces?limit=50              → TraceMeta[]
  └── GET /api/trace/{sid}                  → { meta, rounds: stub[] }
  └── GET /api/trace/{sid}/round/{rid}      → l1/l2/l3/final + intent_v2 + kpi + diff
  └── GET /api/intent_schema                → IntentFieldDescriptor[]

Frontend useWaTrace hook
  ├── traces 列表 (TraceBrowser)
  ├── activeTrace.rounds (RoundRecord stub, RefineTimeline / IntentStrip)
  └── getRoundFull(rid) → 经 traceToSession adapter 适配的完整 RoundRecord (panels)
       └── RoundLRU 50MB byte-based 缓存
```

切 trace 清空 LRU。后端 trace shape (chisha 内部) → 前端 view-model (RoundRecord)
全部走 `src/api/adapter.ts:traceToSession` 边界, 后端 schema 变只改 adapter。

## LookupDrawer (Cmd+K)

抽屉只在 **当前已选 trace + round** 内反查, 零后端调用。Stage 判定顺序:

1. `l1.restaurant_bans` 命中 → **L1 hard_filter** (终止)
2. `l1.top_restaurants` 命中但 `l2.combos` 不含 → **L2 dropped** (cap / 多样性 / 价格)
3. `l2.combos[].restaurant` 命中 → **L2 top60** (含 combo 数 + top score)
4. `final[].restaurant` 命中 → **Final #{rank}** (含 kind / 价 / eta / 菜)

菜名走 contains 模糊匹配 (空格分隔多个), 在 L2 combos + Final 内搜索。

## 错误状态

- `config_error` — LLM provider 配置错: L3 panel 整橙边 + callout
- `skipped` — 用户关闭 LLM rerank: L3 仅显 callout, Final 来自 L2 fallback rerank
- `fallback` — provider chain 走 backup: L3 panel 红边 + fallback_chain 详情
- 后端 offline — 顶栏 pill 橙 "mock · offline", SPA 继续渲染 mock
- 空 trace / 缺 round — 中央空状态 "等待 backend 同步"

## 目录结构

```
src/
├── main.tsx                 入口 + StrictMode
├── App.tsx                  根组件 (sticky stack + panel grid + drawer)
├── styles.css               5 palette + Workflow A 全套样式
├── api/
│   ├── backend-types.ts     原始后端响应类型 (镜像 chisha/debug_recommend.py)
│   ├── adapter.ts           traceToSession() 纯函数, 视图 model 边界
│   └── client.ts            fetch + ApiError + 4 个 Workflow A endpoint
├── constants/
│   ├── intentSchema.ts      INTENT_SCHEMA fallback (后端 GET 失败时用)
│   ├── labels.ts            oil/spicy/wetness/sweet 数字 → 中文 label 映射
│   └── zones.ts             zone code → 中文 area name
├── hooks/
│   ├── useTheme.ts          5 套 palette + prefers-color-scheme
│   ├── useWaTrace.ts        Workflow A 中央 hook (traces + LRU lazy fetch + adapter)
│   └── useKeyboardShortcuts.ts  ⌘K / ⌘/ / 1-9 / Esc
├── lib/diffSession.ts       ComboDiff/FinalDiffKind 类型 + comboDiffBadge formatter
├── mocks/
│   ├── waMocks.ts           38 trace fixture + ACTIVE_TRACE_ROUNDS (R1-R4) 用于 offline fallback
│   └── session.ts           老 LCG mock (adapter 内部冗余, 后续可删)
├── types/trace.ts           Session / L1 / L2 / L3 / Final + WaTrace / RoundRecord / RoundIntentV2
├── components/
│   ├── TraceBrowser.tsx     左侧 trace 列表 (filter + sort + 搜索 + 按天分组 + tree-fold)
│   ├── TraceContextBar.tsx  顶部 sticky trace metadata bar
│   ├── IntentStrip.tsx      schema-driven 渲染 V2 RefineIntent
│   ├── RefineTimeline.tsx   git-compare 横向时间线 + base/target 切换
│   ├── RoundBanner.tsx      RoundBanner + PanelRoundStrip (layer delta)
│   ├── DagHeader.tsx        V12 DAG (compact-only inside sticky stack)
│   ├── LookupDrawer.tsx     ⌘K 反查抽屉 (内存搜索)
│   ├── WorkspaceSwitch.tsx  A 激活 / B 锁定 + toast
│   ├── ThemeSwitcher.tsx
│   ├── Toaster.tsx
│   └── ui/
│       ├── StatusBadge.tsx / Pill.tsx / CopyBtn.tsx
│       ├── CodeBlock.tsx    plain / json + searchTerm highlight
│       └── ToolUseBlockView.tsx  深度折叠 JSON
└── panels/
    ├── PanelL1.tsx          召回漏斗 + drop 原因 + restaurant ban
    ├── PanelL2.tsx          L2 打分 (3 子组件)
    ├── L2KpiBar.tsx / L2Heatmap.tsx / L2ComboTable.tsx
    ├── PanelL3.tsx          LLM rerank + I/O viewer + status callout
    └── PanelFinal.tsx       Top 5 卡片 + 三态着色 (新进/保持/踢出)
```

## 显式 non-goals

- 无 Tailwind / shadcn / antd / 任何 UI 库
- 无单测 (单用户自用工具, 后端 trace_store v3 / append_round 走 pytest 即可)
- 无 a11y / 无 i18n / 无移动端 (桌面 ≥1440px 中文)
- 无写入操作 (Live / What-if / Refine submit 全部已删)
- 任何 TS 组件文件 ≤ 400 行 (data files: styles.css / mocks/waMocks.ts 豁免)

## 已删 (D-087 Workflow A 重构)

- 老 Sidebar (Run/Refine 表单) — Workflow A 是 read-only, 不再有"跑一次"入口
- LiveBanner / WhatIfPanel / Followup — 写入路径全砍
- useSession / useTrace / sessionCache — 旧 hook
- PanelRefine / PanelTrace — Refine 拆 round, 反查走 LookupDrawer
- EmptyStateHint / BackendStatusPill — 状态合入顶栏
- `/api/debug_refine` 实时调用 — refine 由 trace_store v3 R{n+1} round 持久化, 这里仅读

## 设计稿源

`~/chisha/.claude/worktrees/debug_trace_merge/chisha-debug/project/`
(非 git 跟踪) — 改 UI 前先看一遍 wa-*.jsx。

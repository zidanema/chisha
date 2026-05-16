# chisha · debug UI (apps/debug-ui)

推荐链路 debug 台。Phase 0 收尾后单用户自用,目标每天 5-20 次访问。

视觉系统来自 `~/chisha/design/` 设计稿(非 git 跟踪),Phase 1 一字一句搬过来,不允许重设计。

## 本地拉起

两个 server 一起跑:

```bash
# Terminal 1 — 后端 FastAPI (debug 端点)
cd ~/chisha/.claude/worktrees/debugger-web
uv run python -m chisha.debug_server   # http://127.0.0.1:8765

# Terminal 2 — 前端 Vite (SPA)
cd apps/debug-ui
npm install                            # 第一次
npm run dev                            # http://127.0.0.1:5174
```

打开 http://127.0.0.1:5174/ 即可。Vite proxy `/api → :8765` 已配。
后端 offline 时 SPA 自动 fallback 到内置 mock,顶栏 pill 变橙色提示。

## Claude Code 自测约定

改本目录任何 `.tsx` / `.css` / `vite.config.ts` 后, Claude Code 必须用 `mcp__chrome-devtools__*` 工具自驱浏览器验证 (导航 + 走完整 DAG 渲染 + 切主题 + 看 console / network), 不许只跑 lint/tsc 就宣告完成. 详见根目录 [`CLAUDE.md`](../../CLAUDE.md) "前端自测" 章节.

## 主题切换

5 套 palette: `dark-cool / dark-warm / dark-mono / light-paper / light-modern`。
- localStorage key: **`chisha:theme`**
- 默认首次打开按系统 `prefers-color-scheme`: dark → `dark-cool`,light → `light-modern`

## 键盘快捷键 (Phase 5)

| 按键 | 行为 |
|------|------|
| `⌘Enter` / `Ctrl+Enter` | 触发首轮推荐 (任何 sidebar textarea 内都生效) |
| `⌘R` / `Ctrl+R` | 若 refine textarea 有内容 → 触发 refine,否则触发首轮 |
| `⌘⇧R` / `Ctrl+Shift+R` | 浏览器原生 force-reload 保留 (escape hatch) |

输入法 composing 时不会触发 (IME guard).

## 修改 profile

- **临时覆盖** (单次 run): 左侧 sidebar 「profile 临时覆盖 JSON」textarea, 改完按 ⌘Enter
- **永久修改**: 编辑 `profile.yaml` (主仓库根), 后端会重读
- JSON 实时校验失败时 textarea 红边 + Run 按钮 disabled

## 高频功能 (Phase 5 niceties)

- **L2 heatmap 列点击排序** — 三态: desc → asc → off (恢复 total_score)
- **L3 IO viewer 内 find-in-text** — system prompt / user message / 各文本 block 实时高亮
- **L3 raw response tool_use** — JSON 默认深层折叠 + "全部展开" 按钮
- **Run history 行 hover** — 右侧 ↻ 按钮复刻该次 config 到 sidebar (不立刻 run)

## 错误状态 (Phase 6)

- `config_error` — LLM provider 配置错误 (`ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` 缺 或 `CHISHA_LLM_PROVIDER` 写错): L3 panel 整橙边 + callout. profile JSON 不合法不会到 L3 — sidebar 实时校验直接 disable Run 按钮.
- `skipped` — 用户关闭 LLM rerank: L3 仅显 callout,Final 来自 L2 fallback rerank
- `fallback` — provider chain 走 backup: L3 panel 红边 + fallback_chain 详情
- 后端 offline — 顶栏 pill 橙 "offline · mock",SPA 继续渲染 mock

## 追溯 Tab (Phase 4)

sidebar 输入餐厅名 (模糊匹配) 和/或菜名 (空格分隔), 点 ⌕ 追溯命中. 调用
`/api/debug_recommend?trace_target=…` 重跑 pipeline (LLM 关闭省 token),
返回每道菜在 L1/L2/L3/Final 哪一层落地, 给出 stage badge + 完整 nutrition_profile.

## 目录结构

```
src/
├── main.tsx                 入口 + StrictMode
├── App.tsx                  根组件 (tab / theme / DAG / shortcuts wire)
├── styles.css               搬自 design/styles.css + 5 utility color var + Phase 5 功能性扩展 (mark.find-hit / .replay-btn)
├── api/
│   ├── backend-types.ts     原始后端响应类型 (镜像 chisha/debug_recommend.py)
│   ├── adapter.ts           backendToSession() 纯函数, 视图 model 边界
│   └── client.ts            fetch + ApiError + postDebugRecommend / getProfile
├── constants/
│   ├── defaults.ts          DEFAULT_PROFILE_OVERRIDE / DEFAULT_REFINE_TEXT / TODAY_ISO
│   ├── labels.ts            oil/spicy/wetness/sweet 数字 → 中文 label 映射
│   └── zones.ts             zone code → 中文 area name
├── hooks/
│   ├── useTheme.ts          5 套 palette + prefers-color-scheme
│   ├── useSession.ts        runMain + history + race guard
│   ├── useTrace.ts          /api/debug_recommend + trace_target 命中查询
│   └── useKeyboardShortcuts.ts  ⌘Enter / ⌘R 全局拦截
├── lib/
│   ├── sessionCache.ts      localStorage history + config (MAX_ITEMS=8)
│   └── diffSession.ts       computeSessionDiff(first, second) 纯函数
├── mocks/
│   ├── session.ts           内置 mock session (LCG seed=42)
│   └── refineSession.ts     deriveRefineSession(first, text) — refine text seed
├── types/trace.ts           Session / L1 / L2 / L3 / Final / Refine view-model
├── components/
│   ├── Sidebar.tsx          左侧控制面板
│   ├── DagHeader.tsx        V12 DAG (sticky + auto-collapse + ResizeObserver)
│   ├── ThemeSwitcher.tsx    主题切换器
│   ├── EmptyStateHint.tsx   首次启动 hint
│   ├── BackendStatusPill.tsx 顶栏后端连接状态 pill
│   ├── Toaster.tsx          右上角自动消失 toast
│   └── ui/
│       ├── StatusBadge.tsx
│       ├── Pill.tsx
│       ├── MiniFunnel.tsx
│       ├── CopyBtn.tsx
│       ├── CodeBlock.tsx    plain / json + searchTerm highlight
│       └── ToolUseBlockView.tsx  深度折叠 JSON
└── panels/
    ├── PanelL1.tsx          召回漏斗 + drop 原因 + restaurant ban
    ├── PanelL2.tsx          L2 打分 (3 子组件)
    ├── L2KpiBar.tsx
    ├── L2Heatmap.tsx        12 维 × topN 热力图 + 列点击排序
    ├── L2ComboTable.tsx     可展开 combo 表 + diff 徽章
    ├── PanelL3.tsx          LLM rerank + I/O viewer + status callout
    ├── PanelFinal.tsx       Top 5 卡片 + 三态着色 (新进/保持/踢出)
    ├── PanelRefine.tsx      Refine pipeline + 第二轮 trace
    └── PanelTrace.tsx       追溯 Tab + mini DAG + 命中表
```

## 范围 (全部完成)

- ✅ Phase 1: 搬设计稿
- ✅ Phase 2: 接 /api/debug_recommend (adapter + race guard)
- ✅ Phase 3: Refine 下半区 (mock-derived 第二轮 + diff 徽章 + tri-state final)
- ✅ Phase 4: 追溯 Tab (复用 trace_target, mini-DAG + 命中表 + np detail)
- ✅ Phase 5: ⌘Enter/⌘R 快捷键 + prefers-color-scheme + heatmap 列排序 +
  find-in-text + tool_use 折叠 + 复刻 run
- ✅ Phase 6: config_error/skipped 视觉 + 空 session hint + np 数字→label +
  zone code → 中文
- ✅ Phase 7: 拆分超 400 行文件, 此 README

## 显式 non-goals

- 无 Tailwind / shadcn / antd / 任何 UI 库
- 无单测 (单用户自用工具)
- 无 a11y / 无 i18n / 无移动端 (桌面 ≥1440px 中文)
- 任何 TS 组件文件 ≤ 400 行 (data files: styles.css / mocks/session.ts 豁免)

## D-079 三模式 (Replay / What-if / Live) — 2026-05-16 落地

URL state: `?sid={session_id}` `?mode=live` `?what_if=1` 全部 `replaceState` 同步, 刷新可定位.

- **Replay** (默认): Sidebar 进入页面 fetch `/api/debug/sessions`, 点 history 行 → fetch `/api/debug/sessions/{sid}` → 渲染历史 trace (只读). 后端可达时是单一可信源 (DESIGN §8.2), 不可达自动降级 localStorage 离线缓存 + 顶部 banner.
- **What-if**: Sidebar `🧪 What-if` 按钮 (仅 backend-backed Replay 行可用) → 双栏对比 panel + JSON overrides 编辑 + use_llm_rerank 开关 (default false). 后端冻结 `__frozen.{ctx, today, l1_combos, l1_prefs, l2_meal_log_view, profile}` 零 runtime read, 重跑 L2+L3, **永不写盘**.
- **Live**: Sidebar `⚡ Live 试跑` → /api/debug_recommend 跑一次, 临时显示 + 顶部金色 banner. 不落 localStorage, 不落后端 trace_store, 关 tab 即丢.

每行 Run History 显示 feedback badge: `⭐{rank}` (accepted) / `❤×N` (rating) / `🚫` (stopped). 后端 `corrupt_count > 0` 顶部红字告警.

## 已知 defer (Phase X+ 视必要)

- **`/api/debug_refine` 真 backend 接入** — 当前 Phase 3 用 mock 派生二轮.
  接通后 mocks/refineSession.ts 可砍.
- ~~`/api/sessions` 真 backend 持久化~~ — **已落地 (D-079, 2026-05-16)** `/api/debug/sessions` GET list + `/api/debug/sessions/{sid}` GET detail + `/api/debug/what_if` POST 三端点 + 后端 trace_store + 前端 `traceToSession` adapter.
- **L3 fallback 桌面 Notification** — 真链路打通后再开 Web Notifications.
- **per-dish trace rank 精确归属** (Codex Phase 4 noted) — backend `matched_combos_in_ranked`
  没带 dish_id, 当前 PanelTrace 表内 rank 列显示 first matched combo 的 rank.

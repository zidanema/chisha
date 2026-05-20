# Phase 5 plan · 高频 niceties (chisha debug-ui)

## 9 个独立 micro-feature 按价值排序

1. **Cmd/Ctrl+Enter 在 sidebar 任何 textarea 内 = 触发首轮推荐** (顶 priority)
   - 实现: window-level keydown listener, target.matches('.sidebar textarea')
     就 preventDefault + handleRunMain.

2. **Cmd/Ctrl+R intercept** 阻止刷新, 改为触发 refine (refineText 有内容) 或
   触发首轮
   - 实现: window keydown 'r' + (e.metaKey||e.ctrlKey), preventDefault. 注意:
     Chrome devtools shortcut (Cmd+Option+R) 不能误吃. 用户开发自用工具,
     接受 hard intercept.

3. **Theme prefers-color-scheme 检测**
   - 实现: useTheme 改为先看 localStorage, 再看 matchMedia('(prefers-color-scheme: dark)').
     dark → 'dark-cool', light → 'light-modern'.

4. **L2 heatmap 列点击排序**
   - 实现: heatmap header 加 onClick, 维护 sortDim state. 三态: asc / desc / off.
     ComboHeatmapRow 用 (sortDim, sortDir) 重排. off 时恢复 total_score desc.

5. **L3 find-in-text 高亮**
   - 现有 `<input class="find">` 已 wired, 但 CodeBlock 没接 searchTerm.
     改 CodeBlock: 对 plain mode 文本做 split + regex highlight.
     不动 json mode (有 token highlighter 干扰太复杂, defer).

6. **L3 tool_use JSON expand/collapse**
   - 实现: CodeBlock json mode 加 collapsible. 默认顶层 keys 全展开, value 是
     object 时第一层 collapse. 简化: 在 raw tab 的 tool_use block 套一个
     <details> + 按钮切换 "深层折叠 / 全展开".

7. **Run history "复刻 run" button hover**
   - 实现: sidebar run-row hover 出小按钮. 点击把当前 session 的 config 灌回
     (meal, today, profileOverride). 不立刻 run, 让用户改了再 run.
   - 需要 sessionCache 把 config 一起存. 现在没存, Phase 5 给 rememberSession
     加 config 字段, loadSession 返回它.

8. **L2 combo hover popover**
   - 实现: combo table row mouseenter → 显示一个 fixed-position mini popover,
     右上角偏移, 展示该 combo 的 breakdown vector (compact, max 8 dim).
     mouseleave 关闭. 别和 chevron click 抢事件.

9. **L3 fallback desktop notification**
   - 实现: useSession 在 setStatus("ok") 后, 如果 fresh.l3.status === 'fallback',
     调 Notification API. 首次访问问权限: 用户切到 fallback session 时弹.

## 决策

- **键盘事件全部用 window-level + ref**, 不污染组件树。统一管理在新 hook
  `src/hooks/useKeyboardShortcuts.ts`,接 `onRunMain` / `onRunRefine` callbacks.
- **shortcuts hint 显示**: kbd 标签 already 在 sidebar Run button. 加同样的
  `<span class="kbd">⌘R</span>` 在 refine button. 其他 (Cmd+F / heatmap click)
  不显示, 让用户摸索.
- **Cmd+R**: 桌面 Chrome 上 Cmd+R 是 reload. Intercept 后 reload 失效, 用户怎么
  reload? 加二级 shortcut Cmd+Shift+R (force reload) 不 intercept, 留逃生口.

## 不做 (defer)

- JSON 全文搜索的 token-aware highlight 复杂, 仅 plain mode 接 search.
- Popover 浮层 z-index / mobile 行为 — 桌面 only 不管 mobile.
- Cmd+K command palette — 没要求, 不做.

## What I want Codex to check

- shortcuts 与浏览器原生 / OS 全局快捷键冲突 (Cmd+R intercept 可接受?
  Cmd+Enter 在 macOS 是 application-specific, 一般无冲突)
- 9 个 feature 顺序合理? 是否漏什么?
- 桌面 notification API 在 :5174 dev (http://127.0.0.1) 上能跑吗 (HTTPS 限制?)
- 完成后估计 +200-300 行新代码, 主要在 hooks/ + 改既有 panels. 文件超限?

中文 200-400 字 BLOCKER/FIX-NOW/DEFER。不要客套。

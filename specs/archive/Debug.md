# T-Debug: Debug UI (D-080~D-085) 验收 bug fix

> 触发：2026-05-19 志丹手动验证 D-080~D-085 Faithful Refine 重构暴露的 debug-ui
> 渲染层遗留 bug。Backend 完整跑通，前端有 6 处明显遗漏。

## 背景

worktree: `.claude/worktrees/debug_trace_merge` (基于 main c3759a8)
D-080~D-085 改动状态: backend ✅ tested, debug-ui 渲染层 ❌ 有遗漏

验证流程暴露的核心问题: 用户在 :5173 做了一次推荐 + refine + 采纳了 rank 2 (肖三胖)
trace `20260519_dinner_22bfb296f355496d` 完整落盘 (v3 dir 含 R1+R2), 但 debug-ui:
- 默认渲染 R1, 不显示 refine
- R2 节点存在但是 StaticText 不像可点
- 用户采纳信息显示成神秘的 `+2`
- L3 SKIPPED 时说 "rerank 关闭" 实际是 config_error

## 6 个 Bug (按优先级)

### B1 [P0] activeRound 硬编码 R1
- **文件**: `apps/debug-ui/src/App.tsx:63`
- **现状**: `const [activeRound, setActiveRound] = useState<string>("R1")`
- **修法**: 初始化用 `meta.latestRound`. trace 切换时 reset 到新 trace 的 latestRound.
  保留"用户在当前 trace 内主动切换 round 就别覆盖"语义 (用 ref/state tracking)
- **验收**: 切到有 R2 的 trace, 默认拉 `/round/R2`, IntentStrip 显示 R2 内容

### B2 [P0] RefineTimeline R2 节点 a11y 不友好
- **文件**: `apps/debug-ui/src/components/RefineTimeline.tsx`
- **现状**: round 节点是 `<span>` (snapshot 里是 StaticText), 用户不知道可点
- **修法**: 改成 `<button>` + cursor:pointer + hover 高亮 + aria-label
  "切换到 R2 (refine: 来点湘菜...)"
- **验收**: chrome-devtools snapshot 里 R2 节点 role=button, hover 视觉反馈

### B3 [P1] useWaTrace stubToRound mock fallback
- **文件**: `apps/debug-ui/src/hooks/useWaTrace.ts:60-77`
- **现状**: line 71-77 给 R2+ stub 用 `ACTIVE_WA_TRACE.rounds[0]` (R1 mock) 兜底,
  注释自承 "Phase 2a R2+ refine 还没存完整切片"
- **修法**: backend R2 已落完整, 删 mock fallback. stub.body=null → lazy fetch 真 round_full,
  fetch 中显示 loading 而不是 R1 mock
- **验收**: 切 R2 不再看到 R1 数据, console 没 "用 mock 兜底" 痕迹

### B4 [P1] TraceBrowser feedback 显示成神秘的 +2
- **文件**: `apps/debug-ui/src/components/TraceBrowser.tsx:29-39` (feedbackGlyph)
- **现状**: 代码写了 `⭐ <span className="mono">#{fb.rank}</span>`, 实际渲染 `+2`
- **排查**: 先看为什么 ⭐ 丢了 (font fallback? CSS unicode-range? JSX 转义?)
- **修法**: ⭐ 渲染修复 + 显示采纳餐厅名 (而不只是 rank).
  需 backend `chisha/trace_store.py::attach_feedback_links` 把 `restaurant_name` 也派生到 trace meta
- **验收**: trace `22bfb296f355496d` 列表项显示 "⭐ 肖三胖·老湖南品质土菜 #2" 类似清晰文本

### B5 [P2] TraceBrowser 不轮询新 trace
- **文件**: `apps/debug-ui/src/hooks/useWaTrace.ts`
- **现状**: mount 时拉一次 `/api/traces`, 之后不动
- **修法**: 加 `setInterval` 5s refetch `/api/traces` (轻量, 50 条 list 后端开销忽略)
- **验收**: 在 :5173 做一次新推荐, debug-ui 左侧 5 秒内自动出现新条目

### B6 [P1] L3 SKIPPED 描述错误
- **文件**: debug-ui 里渲染 "LLM rerank 关闭" 的组件 (grep "rerank 关闭" / "SKIPPED")
- **现状**: 所有 L3 fallback 都笼统显示 "LLM rerank 关闭, Final 来自 L2 fallback rerank"
- **修法**: 根据 `l3.status` + `l3.fallback_reason` 区分:
  - `status: config_error` → "LLM provider 配置错误: {fallback_reason 截断}"
  - `status: ok` + `used_fallback: true` → "LLM 调用失败回退: {fallback_reason}"
  - `status: disabled` → "L3 已手动关闭"
  - `status: ok` + `used_fallback: false` → 不显示 SKIPPED, 显示正常 L3 信息
- **验收**: 切到老 trace `c205f8a61d521b49` R1 (config_error) 显示 "LLM provider 配置错误";
  跑一个有 key 的新 trace 显示正常 L3

## 约束

1. 改动范围: debug-ui 为主, B4 涉及 `chisha/trace_store.py` attach_feedback_links 增强
2. 不能改 apps/web/, 不能改推荐链路核心 (recall/score/rerank/refine/sandbox)
3. 每改一个 bug, chrome-devtools-mcp 自验
4. 全部 791 测试基线必须保持绿
5. 完工后追加 `docs/decisions.md` D-087 (≤15 行)

## 完成标准

- 6 bug 全修, chrome-devtools-mcp 验证通过
- pytest 全绿 (791+)
- 1-2 个 commit (debug-ui + 可选 trace_store)
- D-087 落 decisions.md
- 不 push 不开 PR

## 已就绪环境

- backend bg `b3medgnm7` :8765 (含 OPENROUTER_API_KEY)
- debug-ui bg `btk14bjgy` :5174
- apps/web bg `b0id0wtn4` :5173
- 8 条真实 trace 在 logs/recommend_trace/
- 验证锚 trace: `20260519_dinner_22bfb296f355496d`

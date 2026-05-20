# Claude Code 落地 Prompt · chisha debug 工具

下面是给 Claude Code 用来落地这个 debug 工具的完整 prompt。复制到 Claude Code 里就能开工。

---

# Build out the chisha debug console — full implementation

我有一个推荐系统 debug 工具的高保真设计稿（在 `design/` 目录），需要你把它落地成生产可用的版本。**设计风格、配色、布局、交互模式已经定稿，不要更改**，你的工作是把它接上真实后端、补全未完成的 tab、加我每天会用到的 niceties。

## Context · 项目背景

"今天吃点啥 (chisha)" — 外卖推荐引擎，服务"原则派"用户（已认了一套饮食方法论 = 减脂控油 / 高蛋白 / 糖控 / 孕期等，痛点是每天落地费力）。每顿饭推 5 个「餐厅 + 2-3 道菜 combo」组合，30 秒决策。我是这个系统**唯一用户也是唯一开发者**，每天用这个 debug 台 5-20 次。

**链路**：
- L1 召回 (recall) — ~11k 道菜经硬过滤 / 多样性过滤 / combo 组合策略，产出几百~上千 combo
- L2 打分 (score V2) — 12+ 维加权 + 4 层 cap (`per_restaurant_cap_k` / `per_brand_top_k` 等)，输出 top 60
- L3 LLM 精排 (rerank) — Claude opus-4.7 + tool_use forced schema，输出 top 5 + 一句话理由。fallback 链：anthropic opus → sonnet → openrouter → claude_code_cli
- Final — top 5 = 3 exploit + 2 explore

**Refine 二轮**：用户对首轮 5 个不满意 → 自然语言反馈（"想喝汤，别给我面"）→ `parse_feedback` → `chips_to_taste_hints` → `infer_refine_mood` → 第二轮 L2/L3。

## Design reference

`design/` 下是已经定稿的设计稿（React + inline JSX + babel standalone）：

- `index.html` — 入口
- `app.jsx` — 根组件、tab 切换、DAG 自动 collapse 逻辑、theme switcher
- `dag-header.jsx` — sticky DAG 流水线 + 自动 collapse 成 thin strip
- `sidebar.jsx` — 左侧控制面板
- `panel-l1.jsx` / `panel-l2.jsx` / `panel-l3.jsx` / `panel-final.jsx` / `panel-refine.jsx`
- `styles.css` — 所有样式 + 5 套 CSS-var palette
- `mock.jsx` — 真实形状的 mock 数据，**作为后端契约样本**

请先读完所有设计稿 (`read_file`)，然后规划。**视觉系统不要重做**：

- **结构是 V12 DAG Pipeline** (Dagster × ComfyUI 风) — 顶部一整条流水线（CTX → L1 → L2 → L3 → FINAL），滚动时 collapse 成 thin strip
- **5 套 palette** 用 `[data-theme="…"]` 切换：dark-cool / dark-warm / dark-mono / light-paper / light-modern，存 localStorage
- **每层一种 accent 色**：L1 teal / L2 green / L3 amber / final indigo / refine pink
- 字体：IBM Plex Sans (UI) + JetBrains Mono (数字 / id / token / latency)

## 技术栈建议

- **后端**：保留现有 FastAPI（端点见下）
- **前端**：建议从设计稿的 inline JSX 升级到正经的 Vite + React 项目，但 **CSS / 组件结构 / 类名一对一搬过去**。设计稿里所有组件已经按 panel-* 拆好，直接对应 React 组件即可
- **不需要状态管理库**，全用 React useState/useEffect。一次调用一个 trace，存内存就够
- 类型：建议加 TypeScript，把 mock.jsx 里的形状写成 type，作为前后端共同契约
- **不要引入 Tailwind / shadcn / antd**。视觉系统已经定稿，CSS-var 那套就够，引入 UI 库反而破坏一致性

## API contracts（保留 / 实现）

```
POST /api/debug_recommend
  body: { meal, today, profile_override?, llm: "auto"|"on"|"off" }
  returns: { config, l1, l2, l3, final, session_id, started_at, total_latency_ms }
  # l1, l2, l3, final 形状参考 mock.jsx 里的 L1 / L2_KPI / L2_COMBOS / L3 / FINAL

POST /api/refine
  body: { parent_session_id, user_text }
  returns: { parent_session, refine_session, user_text, parse_feedback,
             chips_to_taste_hints, infer_refine_mood, diff, summary_kpi,
             l1, l2, l3, final }
  # diff / 第二轮 trace 形状参考 mock.jsx 里 REFINE

GET /api/profile
  returns: { ...current profile JSON }

POST /api/trace            # 设计稿里还没实现的追溯接口
  body: { restaurant_query?, dish_query?, session_id? }
  returns: { matches: [
    { dish_id, dish_name, restaurant,
      stage_dropped: "passed_recall" | "dropped_at_hard_filter" |
                     "dropped_at_diversity" | "dropped_at_price" |
                     "dropped_at_brand_cap" | "dropped_at_restaurant_cap" | "unknown",
      reason: string,
      in_top60_rank?: number,
      in_final_top5?: boolean }
  ] }

GET /api/sessions          # run history
  returns: [ { id, title, time, status: "ok"|"fallback"|"warn",
               latency, meal, area } ]

GET /api/session/{id}      # load specific session full trace
  returns: same shape as /debug_recommend response
```

## Implementation plan

我建议按这个顺序，每完成一项打勾给我看：

### Phase 1 · 把设计稿搬成正经 React 项目

- [ ] `npm create vite@latest debug-ui -- --template react-ts`，拉起来
- [ ] 把 `styles.css` 整文件搬过去（一字不改），import 到 `main.tsx`
- [ ] 把每个 `panel-*.jsx` 转成 TS 组件文件，类型从 mock.jsx 的形状反推
- [ ] `mock.jsx` 抽成 `mocks/session.ts`，导出实际的 mock JSON，作为开发期默认数据
- [ ] 跑起来，应该和设计稿肉眼一致

### Phase 2 · 接后端

- [ ] 写 `api.ts`，所有端点的 fetch 封装
- [ ] sidebar 「触发首轮推荐」按钮 POST `/api/debug_recommend`，loading 时 DAG 节点亮 amber pulse，成功后填回 trace
- [ ] sidebar 历史 run 列表用 `/api/sessions`，点击 load `/api/session/{id}`
- [ ] sidebar 「触发 refine」按钮 POST `/api/refine`，把第二轮 trace 渲染到 Refine tab
- [ ] profile JSON textarea 实时校验（解析失败时红边 + 错误提示）
- [ ] 全程错误处理：API 报错时显示 toast，DAG 顶部那个 status pill 变红

### Phase 3 · 补 Refine 下半区

设计稿里 Refine tab 只有上半区的 pipeline 流水线（4 步：input → parse → hints → mood），下半区还是占位。要补：

- [ ] 第二轮的完整 L1 / L2 / L3 / Final 4 个 panel，复用现有组件
- [ ] 每个 combo 旁挂一个 first-vs-second diff 徽章（↑3 / ↓2 / NEW / DROPPED）
- [ ] Final 5 卡片对比首轮的有"新进 +" / "保持" / "踢出 −" 三态着色

### Phase 4 · 追溯 Tab（设计稿没画，按描述实现）

视觉风格继续走 V12：顶部一个 DAG 节点变形（黄色高亮显示被追溯菜 dropped 的那一层），下方表格。

- [ ] sidebar 已经有输入框（餐厅名 + 菜名），点「⌕ 追溯命中」POST `/api/trace`
- [ ] 命中表：dish_id / 菜名 / 餐厅 / **stage_dropped badge** (用 L1=teal / L2=green 那套色) / 具体原因 / top60 rank / 是否进 final
- [ ] 表格可点行 → 弹出该菜的 dish 完整属性 + 它 ban 的具体 rule

### Phase 5 · 我每天用 5-20 次需要的 niceties

按对我的价值排序：

- [ ] **Cmd+Enter / Ctrl+Enter 在 sidebar 任何 textarea 内 = 触发首轮推荐**。最高优先
- [ ] **Cmd+R / Ctrl+R intercept** — 阻止浏览器刷新，改为触发 refine (如果 refine 输入有内容) 或首轮推荐
- [ ] Run history 行右上角 hover 出"复刻这次 run"按钮 — 把这次的 config 灌回 sidebar 但不立刻 run
- [ ] L3 长文本 (system prompt / user message / raw response) 加 **Cmd+F 行内搜索高亮** — 设计稿里 UI 框已经有了 (`<input class="find">`)，逻辑没接
- [ ] L3 raw response 的 tool_use JSON 加「展开 / 折叠」按钮（默认展开顶层，深层折叠）
- [ ] L2 heatmap 顶部权重行点击单个维度 → 整列 sort，再次点击 → 反向，第三次点击 → 取消（恢复 total_score 排序）
- [ ] L2 combo 表格 hover 行 → 显示该 combo 的 explain breakdown mini popover（不用全展开）
- [ ] Theme 切换记忆 + 加 `prefers-color-scheme` 检测：第一次访问按系统主题挑 dark-cool 或 light-modern
- [ ] **L3 fallback 时桌面 notification** — 用 Web Notifications API，因为这是 production 事故信号，我每天看 20 次不能漏

### Phase 6 · 错误状态 + edge cases

- [ ] config_error 状态：profile_override JSON 解析失败时整个 L3 面板变橙色 + 顶部 callout（设计稿里 status 枚举已有，渲染没接）
- [ ] skipped 状态：LLM 关闭时显示「L3 SKIPPED」灰色徽章 + Final 用 L2 top 5 直出 + 注明
- [ ] 长文本溢出处理：system prompt 一次性渲染太长会卡，做虚拟滚动或仅渲染 visible chunk
- [ ] 空 session：刚启动还没跑过任何一次，DAG 节点显示「—」+ "click 触发首轮 to start"

### Phase 7 · 工程性

- [ ] 项目跑在 localhost:5173，proxy /api 到 FastAPI :8000
- [ ] 文档：README 写"怎么本地拉起 + 改 profile 在哪里 + theme localStorage key 是啥"
- [ ] **不要写测试**。这是本机自用工具，唯一用户是我，测试是浪费时间

## 显式约束

- **不准重做视觉系统**。我已经在 design canvas 里选过 7 种结构 + 5 种 palette。CSS 一字不改照搬，组件结构 1:1 对应。
- **不准引入 UI 库**。
- **不准把 mock 数据写死在 UI 里**。Phase 1 完成后 mock 只在 `mocks/` 下，dev 模式 fallback 用，正常路径走真实 API。
- **不准给我"完成度报告"邀我下次再 review**。每完成一个 Phase 就停下来跑一遍 demo 给我看。
- **保持文件小**。任何文件超过 400 行就拆。设计稿已经按 panel-* 拆好了，照搬。
- **不需要可访问性 / 国际化 / 移动端**。桌面端 ≥1440px only，中文，唯一用户。

## Codex Review · 全程结对工作

我的 Claude Code 接了 **Codex** 作为第二意见来源（独立 LLM reviewer）。**不要单干**，遇到关键决策点都让 Codex 一起 review，达成共识后再动手。具体节奏：

### 必须走 Codex review 的节点

每个 Phase 开始前，**先让 Codex review 计划**：

1. 把你这个 Phase 准备做什么、按什么顺序、关键技术决策（库选择 / API 设计 / 数据结构 / 文件拆分边界）整理成一份简洁的方案文档
2. 调用 Codex 让它 review，明确问它：
   - 这个方案有哪些隐患或盲点？
   - 有没有更简单 / 更可维护的做法？
   - 关键决策（如：用 TypeScript types vs zod schema 双重校验 / API 错误处理策略 / state 怎么存）你怎么看？
3. **认真消化 Codex 的反馈**，不是走过场。如果 Codex 提出的点你不同意，**明确说为什么不同意**，然后再问一遍看它是否被说服。两个 LLM 真正达成 consensus 才开工
4. 开干之前再把最终方案给 Codex 看一遍，确认它没有"等一下"

### 必须走 Codex review 的代码节点

- **每个 Phase 完成后，提交给我 review 之前**：让 Codex 看代码 diff，明确问：
  - 这份 diff 有 bug 吗？竞态 / 内存泄漏 / 错误处理缺失？
  - 视觉一致性：我有没有偷偷改了设计稿的 CSS / 字号 / 间距？（设计稿是 source of truth）
  - TypeScript 类型有没有 `any` / `as any` / `@ts-ignore` 这种 escape hatch？
  - 文件拆分合理吗？有没有文件超过 400 行该拆没拆？
- **任何超过 50 行的新组件 / 模块**：写完先给 Codex 看，再决定要不要继续
- **任何引入新依赖的 PR**：必须 Codex 确认这个依赖必要 + 没有更轻的替代

### 必须走 Codex review 的"想法"节点

- 你冒出"我觉得这里应该做成 XX"的想法，但**我（用户）没明确要求**：**先去 Codex 那 sanity check**，再回来跟我提
- 你打算偏离设计稿（哪怕你觉得"这样更好"）：先 Codex review，由 Codex 评估"用户已经定稿的视觉决定 vs 你的改动"哪个站得住脚
- 你想用某个流行模式 / 框架 / 库（zustand / react-query / shadcn / 任意 design system）：**Codex review 必要性**，避免引入冗余复杂度

### 不需要 Codex review 的节点（避免 round-trip 浪费）

- 单纯的 boilerplate / 把设计稿 CSS 搬过去 / 写 fetch 函数这种没设计空间的活
- 改一个 typo / 改一个 className / 调整几个 px
- 我（用户）明确说"就这么做"的事 — 不要再去问 Codex"用户说要 X，你觉得呢"，浪费 token

### 跟 Codex 协作的姿势

- 不是"找老师批改作业"，是"两个工程师 design review"
- 你可以**反对 Codex** — 它也会瞎说。但反对必须有理由，并且要让 Codex 再确认你的反驳是对的
- **冲突时优先选简单方案**。如果你和 Codex 各执一词，看哪个改动更少 / 更可逆 / 更靠近设计稿
- 把 Codex 的关键反馈写在 PR description / commit message 里给我看 — 我想知道你们俩商量了什么

## 一些已经做好的决定，不要再来问我

- 暗色 / 浅色：用 5 套 palette + 切换器，默认 dark-cool。**不要再问"你想要暗色还是浅色"**
- DAG 头部 sticky + scroll collapse：已经定了，不要改成 sidebar 树或其他形态
- L3 状态色：ok 绿 / fallback 红 / config_error 橙 / skipped 灰，**强信号优先**
- 等宽字体所有数字 / id / latency / token / score
- emoji ❌
- 花哨动画 ❌（runFlash 已经够）

## 开始之前

1. 读 `design/` 下所有文件
2. 跑起设计稿（直接打开 `design/index.html`）感受一下
3. 把这个 prompt 里的 Phase 1-7 列成 TODO
4. 从 Phase 1 开始，每完成一个 phase 停下让我 review
5. 任何视觉决定（颜色 / 字号 / 间距 / 圆角）→ **去设计稿里抄**，不要自己设计

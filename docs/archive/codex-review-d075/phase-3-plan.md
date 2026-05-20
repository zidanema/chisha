# Phase 3 plan · 补 Refine 下半区 (chisha debug-ui)

## Context recap

- Phase 1+2 完成 + 6 个 Codex FIX-NOW 全修。当前 :5174 Vite + :8765 backend 联调通,
  proxy + adapter + history + toast + race guard 全 ready.
- Phase 2 留下一个坑: **refine 数据源**。`/api/refine` 是 user-view (V1.1 推荐),
  返回 `candidates/stats/parsed_feedback/taste_hints/mood_inference` 但没有 L1/L2/L3
  完整 trace; 它还要求一个 user-view session_id (走 chisha.session 存储), 不是 debug
  session id。
- Phase 3 用户列表 (prompt):
  - 第二轮完整 L1/L2/L3/Final 4 panel 复用现有组件
  - combo 旁挂 first-vs-second diff 徽章 (↑3 / ↓2 / NEW / DROPPED)
  - Final 5 卡片首轮对比三态着色 (新进+/保持/踢出−)

## Phase 3 scope (修正后)

**Phase 3 = 纯 UI rendering 任务**, 数据来源不阻塞这个 phase:

1. `src/lib/diffSession.ts` — 纯函数 `computeSessionDiff(first, second)`:
   ```ts
   type ComboDiffKind = "NEW" | "DROPPED" | "UP" | "DOWN" | "SAME";
   type ComboDiff = {
     combo_id: string;
     kind: ComboDiffKind;
     firstRank: number | null;   // null = NEW
     secondRank: number | null;  // null = DROPPED
     delta: number;              // secondRank - firstRank, 正数 = down, 负数 = up
   };
   type FinalDiffKind = "new" | "kept" | "dropped";
   type SessionDiff = {
     combos: Map<string, ComboDiff>;  // 60 entries (union of first/second)
     final: Map<string, FinalDiffKind>;
   };
   ```
   逻辑: 用 combo_id 去 join, NEW 是仅在 second 出现, DROPPED 仅在 first 出现,
   UP/DOWN 看 rank 变化, |delta|=0 是 SAME (不渲染徽章).

2. `src/mocks/refineSession.ts` — 给 PanelRefine 下半区用的 second-round mock.
   规则: 从 MOCK_SESSION 派生 — 把 L2_COMBOS 重新 sort (用一个不同的随机 seed),
   随机替换 top 5 里 2 个 (模拟 wet/soup boost 后的真实效果), L3 / Final 类似
   重新生成。Phase 3 阶段这就是数据源,Phase 4 或更晚才真接 backend。

3. **Panel props 新增 optional `diff` 字段**:
   - `PanelL2`: `diff?: ComboDiff` per combo. 在 ComboTable row 的 leftmost cell
     渲染徽章 (NEW = green pill, DROPPED = strikethrough red, UP = blue ↑N, DOWN = orange ↓N).
   - `PanelFinal`: `diffKind?: FinalDiffKind` per card. 渲染时:
     - `new` → 卡片左 stripe 加绿色 + 顶部小标签 "+ 新进"
     - `kept` → 默认无标
     - `dropped` → 灰色半透明 + 顶部小标签 "− 踢出" (这种 card 不会出现在 second-round
       top 5, 只会出现在 first-round 渲染时如果显示对比)
   - `PanelL1` / `PanelL3`: Phase 3 不加 diff (没意义 — L1 是召回, 二轮基本一致;
     L3 prompt 不同但 trace 视觉差距太小)。

4. `PanelRefine.tsx` 重写下半区:
   - 删掉现在的 "占位 dashed box"。
   - 新增 4 个 panel section, 依次:
     - `<PanelL1 l1={secondSession.l1} />` (不带 diff)
     - `<PanelL2 l2={secondSession.l2} comboDiff={diff.combos} />` (带 diff)
     - `<PanelL3 l3={secondSession.l3} ... />` (不带 diff)
     - `<PanelFinal rows={secondSession.final} finalDiff={diff.final} />` (带 diff)
   - 上半区 pipeline (input/parse/hints/mood) 保持。
   - 中间已经有 DIFF panel (新进/踢出/上移/下移 4 cell + 详细 table), 保持。

5. `App.tsx`:
   - tab === "refine" 时构造 secondSession + diff,并把它和 first session 一起
     传给 PanelRefine。
   - 别污染 main tab — 主视图依旧只看 first session。

## Backend (Phase 3 不做)

**`/api/debug_refine` 推迟到 Phase 4 或后续**。理由:
- 需要重写 chisha.refine() 包装一份 instrumented 版本 (得跟 debug_recommend.py
  的 L1/L2 trace 收集逻辑对齐),工作量 ≈ Phase 2 的一半。
- 用户 Phase 3 的实际收益是 *看到 UI 长啥样*, mock 二轮数据足够。
- Phase 4 追溯 tab 也需要后端改, 那时一起做更高效。

## 关键决策点

1. **diff 徽章视觉**: 设计稿没画。我打算用现有 `Pill` + 颜色 tone:
   - NEW = `<Pill tone="green">+ NEW</Pill>`
   - DROPPED = `<Pill tone="red">− DROPPED</Pill>` + row 灰化 (opacity 0.5)
   - UP = `<Pill tone="blue">↑ N</Pill>`
   - DOWN = `<Pill tone="orange">↓ N</Pill>`
   - SAME = 不渲染
   位置: ComboTable 第一列 (替换原来的 ▶ chevron 还是塞到 rank 后?)。
   倾向: 新增一列, 不动 chevron, 否则 detail expand 交互被破坏。
   Codex 看?

2. **secondSession 派生方式**: deterministic perturbation (一个 seed 复现一致的
   "wet/soup boost" 效果), 不要每次 mount 重算 (会让 diff 数字闪动)。打算
   useMemo + 固定 seed=43 (vs first 用 42)。OK?

3. **DROPPED final card 该不该渲染**: prompt 说 "Final 5 卡片对比首轮的有'新进+'/'保持'/'踢出−'三态"。
   如果第二轮只有 5 个 card, 那 dropped 的就不在卡片列表里。 解读 1: 第二轮
   渲染 second 的 5 张 + 把 first 里被踢出的也并排 (变 6-7 张, 每张标三态);
   解读 2: 只渲染 second 的 5 张, 但加 1-2 张半透明 "dropped" 占位 card 表示哪些
   被踢出。我倾向 解读 1 (并排,清晰)。Codex 哪种?

4. **L2 ComboTable 默认排序**: 第一轮按 second_round rank, 还是按 first_round
   rank? 倾向 second (这才是"当前结果"),  diff 徽章告诉 first 怎么排的。

5. **diff 计算性能**: 60 × 60 + 5 × 5 nested loops, < 1ms, 不用优化。

6. **PanelL2.tsx prop drilling**: ComboDiff 要传到 L2ComboTable 子组件。
   PanelL2 → L2ComboTable 加 optional `diff?: Map<string, ComboDiff>` prop,
   L2Heatmap 不接 (heatmap 只看 score, diff 在 table 上语义更清晰)。OK?

7. **Phase 3 完成 demo**: 我会让 user "点 Refine tab" 看到完整二轮 trace + diff
   徽章 + 三态 final card。 first-tab 主视图保持不变。

## 不做 (推迟)

- 真实 /api/debug_refine 后端 (Phase 4+ 视必要)
- L1/L3 panel 加 diff (设计稿没要求, 暂不加)
- 二轮 trace 持久化到 sessionCache (一轮就够用, refine 是临时态)

## What I want from Codex

- 7 个 open question 的明确立场
- secondSession 派生逻辑会不会让 diff 不真实 (例如 NEW 永远是同一两个 combo_id)?
- diff 徽章位置 (新增列 vs 替换 chevron) 哪个更对
- L2 ComboTable / L2Heatmap 拆分粒度 Phase 3 后会不会再超 400 行 (现在 97 + 102)

中文 200-400 字, BLOCKER / FIX-NOW / DEFER 标档。不要客套。

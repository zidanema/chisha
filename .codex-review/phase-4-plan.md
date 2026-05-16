# Phase 4 plan · 追溯 Tab (chisha debug-ui)

## Backend reality check
- `chisha/debug_recommend.py:_trace_target` (`:707`) 已经能产 trace data, 但要求
  `tagged / rests / l1_trace / ranked / final` 都在内存。
- `chisha/debug_server.py POST /api/debug_recommend` 已经接受 `trace_target:
  {restaurant_name, dish_names}`, 会把结果挂在响应的 `target_trace` 字段。
- **结论**: 不必加 `POST /api/trace` 单独端点 (省一次大改后端).
  Phase 4 = 调 `/api/debug_recommend` 多带一个 `trace_target` 字段, 拿 `target_trace`
  渲染 Trace tab. 慢一点 (~300ms 重跑 L1/L2, LLM 关掉) 但够用, 单用户工具不在乎.

## Scope

**前端 (apps/debug-ui/):**
1. `src/api/backend-types.ts` 扩展 `BackendDebugRecommend.target_trace`:
   ```ts
   target_trace: {
     query: { restaurant_name: string; dish_names: string[] },
     matched_dishes: Array<{
       dish_id: string;
       name: string;
       restaurant_id: string;
       restaurant_name: string;
       stage: "passed_recall" | "dropped_hard_filter" | "dropped_diversity_filter" | "unknown";
       reason: string | null;
     }>,
     matched_combos_in_ranked: Array<{
       rank: number;
       score: number;
       signature: string;
       breakdown: Record<string, number>;
     }>,
     in_final: boolean,
   } | null
2. `src/api/client.ts` `postDebugRecommend` 已经 forward `trace_target`. OK.
3. `src/api/adapter.ts` 加 `adaptTargetTrace(raw): TargetTrace` (新类型在
   types/trace.ts).
4. `src/hooks/useSession.ts` 新增 `runTrace(args: { restaurant: string; dishes: string[] })`
   → 调 postDebugRecommend with use_llm_rerank=false (避免花 token) + trace_target,
   返回 trace data.
5. `src/panels/PanelTrace.tsx` 新建:
   - 顶部 mini DAG: 5 节点 L1→L2→L3→Final, dropped 层用黄色高亮 +
     "× dropped here" 角标. 其他节点灰.
   - matched_dishes 表: stage_dropped Pill 颜色 (L1=teal=passed_recall / L2=green=进了ranked / L3=amber=进 top60 但没进 final / red=dropped_hard / orange=dropped_diversity)
   - 表格行 hover → 展开下方 detail panel (dish full attrs + matched combos + ban rule).
6. `src/App.tsx`:
   - 启用 Trace tab (`disabled: false`)
   - handleRunTrace 实际接 runTrace, 把结果传给 PanelTrace
   - Trace tab 进入时 sidebar 输入框焦点切到餐厅名

## Backend (Phase 4 还是不动 backend)

- 上面说过, debug_recommend 已支持 trace_target.
- BUT: 现有 `_trace_target` 返回的 `matched_dishes.fate` 只有 `{dish_id, name,
  restaurant_id, restaurant_name, stage, reason}` 简陋. Phase 4 用户期望
  "弹出该菜的 dish 完整属性" — 缺 nutrition_profile. **需要小补丁**:
  在 _trace_target 里把 tagged dish 完整 dump 进 `nutrition_profile` 字段
  (或者展开 oil_level/protein_g/wetness 等就行). 约 5 行改动.

## 关键决策点

1. **trace 不动主 session**: 触发 trace 时, 当前主 session 应该保留 (一不小心改
   主视图就坑). 倾向: Trace tab 内部 fetch + 内部 state, 不进 useSession.
   `runTrace` 是 useTrace hook 单独的, 返回 (traceData, status, error).
   OK?
2. **是否要把 trace 结果 cache**: 不 cache. 每次点 ⌕ 都重新调.
3. **stage 颜色映射**:
   - passed_recall (在 ranked top60 内) → green (L2 色)
   - passed_recall 但不在 top60 → teal (L1 色)
   - dropped_hard → red
   - dropped_diversity → orange
   - in_final → 额外 indigo 角标
   OK?
4. **匹配为空**: backend 没找到任何匹配 dish 时, target_trace.matched_dishes = [].
   渲染空态: "未匹配到 ... 检查输入". OK?
5. **Trace tab 进入空态**: 还没点过 ⌕ 时, panel 显示 hint "在左边输入餐厅/菜名后点 ⌕".
   OK?
6. **后端补 nutrition_profile**: 在 _trace_target 里展开还是单独整理一个
   dict? 直接展开 5 个字段 (oil_level/spicy_level/protein_g/main_ingredient_type/wetness)
   够用, 不堆全部. OK?

## What I want from Codex
- 6 个决策立场
- 找 bug + 视觉 / 风格漂移
- Phase 5/6/7 会被卡的隐藏决定
- 别拒 BLOCKER, 别拒 FIX-NOW

中文 200-400 字。

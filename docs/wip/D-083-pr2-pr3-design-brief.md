# D-083 PR-2 / PR-3 · 落地设计 brief (Opus S1 → 求 Codex S2)

> 状态: WIP, 待 Codex S2 review
> 上游: D-083 主 brief (`docs/wip/D-083_feedback_trace_observability_brief.md`) Codex S2 v1.1 共识, PR-1 已落 (commit 4ea0fc9)
> Scope: PR-2 (debug-ui FeedbackInputCard + combo 反馈影响角标) + PR-3 (What-if `ignore_feedbacks` patch)
> 不在范围: L1 prefs DAG 可视化 (单独决策号); 编辑 rating/note 的 What-if (D-083.1)

---

## 0. PR-1 落地后实际形态 (PR-2/PR-3 的输入契约)

按代码现状重述, 防 brief 和实现漂移:

**trace 顶层新增 `feedback_view_snapshot`** (`chisha/api.py:491-539`, `chisha/debug_what_if.py:372-388`):

```python
{
  "today": "2026-05-17",
  "windows": {"ratings": 60, "calibrations": 7, "note_tokens": 14},
  "rating_signals": [
    {"restaurant_name": str, "rating": -1|1, "age_days": int,
     "signal": float, "factors": {"peak": float, "tau": float|null, "stage": str}}
  ],
  "calibration_rules": [
    {"session_id": str, "restaurant_name": str, "age_meals": int (0-2),
     "age_days": int, "weight": float, "last_meal_cuisine": str|null,
     "triggers": [{"field": str, "value": int|null, "desc": str}]}
  ],
  "note_breakdown": [
    {"restaurant_name": str, "age_days": int, "decay": float,
     "boost": [str], "penalty": [str], "raw_text": str(≤80),
     "source": "note"|"comment"}
  ],
  "global_token_freq": {"boost": {token: count}, "penalty": {token: count}},
  "global_active_tokens": {"boost": [str], "penalty": [str]},
  "empty": bool
}
```

**combo 级 `feedback_evidence` sibling** (`chisha/score.py:1561-1572`, **不入 breakdown**):

```python
combo["feedback_evidence"] = {
  "feedback_recency":       [{"restaurant_name", "rating", "age_days", "signal"}],
  "next_meal_calibration":  [{"rule": str, "contribution": float}],
  "note_boost":             [{"kind": "restaurant"|"global", "token", "polarity",
                              "restaurant_name", "age_days", "decay", "match",
                              "contribution", "subkind"?}]
}
```

**L3 prompt 渲染段 `l3.feedback_block_rendered`** (`chisha/rerank.py:1188-1193`): markdown 字符串 (`[FEEDBACK_RECENT] / [LAST_MEAL_SIGNAL] / [NOTE_HINTS]` 三段, 空段跳过).

**TRACE_SCHEMA_VERSION = 2** (`chisha/trace_store.py:28-32`); `LEGACY_TRACE_SCHEMA_VERSIONS = {1}` 老 trace 读侧走空骨架兜底.

**已知裂缝** (PR-2/PR-3 需明确处理):
1. `rating_signals[]` / `note_breakdown[]` **没有 `session_id`** 字段 (只 calibration_rules 有). PR-3 想按 sid 过滤这两段需要先补 sid (见 §3.2.A).
2. `note_breakdown[]` 没有 sid, 但同一 sid 可能贡献多条 (note + comments[]). PR-3 按 sid 过滤天然把"该餐反馈所有 note/comment"一起忽略 — 符合用户心智 ("假如这条反馈不存在").
3. SPA `apps/debug-ui/src/types/trace.ts` 当前 **没有任何 feedback_view_snapshot / feedback_evidence 类型** — PR-2 第一件事补类型.

---

## 1. PR-2 · FeedbackInputCard + combo 角标 (~半天)

### 1.1 类型扩展 (`apps/debug-ui/src/types/trace.ts`)

新增:

```typescript
export type FeedbackRatingSignal = {
  session_id?: string;  // PR-3 schema 扩后填; PR-2 渲染时容忍 undefined
  restaurant_name: string;
  rating: -1 | 1;
  age_days: number;
  signal: number;
  factors: { peak: number; tau: number | null; stage: string };
};

export type FeedbackCalibrationRule = {
  session_id: string;
  restaurant_name: string;
  age_meals: number;       // 0 | 1 | 2
  age_days: number;
  weight: number;
  last_meal_cuisine: string | null;
  triggers: Array<{ field: string; value: number | null; desc: string }>;
};

export type FeedbackNoteBreakdown = {
  session_id?: string;     // PR-3 schema 扩后填
  restaurant_name: string;
  age_days: number;
  decay: number;
  boost: string[];
  penalty: string[];
  raw_text: string;
  source: "note" | "comment";
};

export type FeedbackViewSnapshot = {
  today: string;
  windows: { ratings: number; calibrations: number; note_tokens: number };
  rating_signals: FeedbackRatingSignal[];
  calibration_rules: FeedbackCalibrationRule[];
  note_breakdown: FeedbackNoteBreakdown[];
  global_token_freq: {
    boost: Record<string, number>;
    penalty: Record<string, number>;
  };
  global_active_tokens: { boost: string[]; penalty: string[] };
  empty: boolean;
};

export type FeedbackEvidence = {
  feedback_recency?: Array<{
    restaurant_name: string; rating: -1 | 1; age_days: number; signal: number;
  }>;
  next_meal_calibration?: Array<{ rule: string; contribution: number }>;
  note_boost?: Array<{
    kind: "restaurant" | "global";
    token: string;
    polarity: "boost" | "penalty";
    restaurant_name: string;
    age_days: number;
    decay: number;
    match: -1 | 0 | 1;
    contribution: number;
    subkind?: string;
  }>;
};
```

`Session` 类型加 `feedback_view_snapshot?: FeedbackViewSnapshot` (顶层 optional, 老 v1 trace 没有).
`L2Combo` (或对应类型) 加 `feedback_evidence?: FeedbackEvidence`.

### 1.2 新组件 `apps/debug-ui/src/panels/FeedbackInputCard.tsx`

数据源: `session.feedback_view_snapshot`. 渲染规则:

- `empty === true` → **不渲染整个 card** (避免噪声, 与 brief §3.1 "empty=true 单独 banner" 的方向矛盾, 详见 Q1).
- 3 段并列卡片 (Ratings / Calibrations / Notes), 每段标题带窗口 + 当前条数. 段内 0 条 → 灰色 placeholder "近 N 天 0 条".
- Rating row: `灶台 −1 (1d) → −1.40   公式: peak=−1.5 × exp(−1/14)` (用 `factors.peak / factors.tau / factors.stage` 拼可读公式; PR-1 已存 factors 而不是直接给 formula 字符串, **不要在前端再拼运算**, 渲染人类可读说明即可).
- Calibration row: 折叠组件 — 头部 `灶台 (age=0, weight=1.0) 油✗ 饱✗ 理由✗`, 展开列 `triggers[].desc`.
- Note row: `灶台 (1d, decay=0.87) "太油了..." → low_oil + wetness` + 全局段 `全局高频 (≥2): low_oil×3, spicy×1`.

样式延续 D-075 五主题 (`apps/debug-ui/src/components/ThemeSwitcher.tsx` 现有 5 主题), 借用 `panels/PanelL1.tsx` 卡片样式.

### 1.3 挂载位置: 新 DAG 节点 `feedback`

**S1 倾向: 新 DAG 节点 `feedback`, 排在 `l1` 与 `l2` 之间**, 与 L1 prefs 同级 (两者都是 "中间派生层"). 改动:

- `apps/debug-ui/src/components/DagHeader.tsx`: 在 `buildNodes()` 数组里 L1 与 L2 之间插 `{ id: "feedback", label: "Feedback", ... }`. **空 trace (empty=true / 老 v1 trace) 该节点灰显**, 不可点 — 与 L3 节点已有的 fallback/skip 视觉一致 (`DagHeader` 现有 status 字段就支持 `empty | active | error`).
- `apps/debug-ui/src/App.tsx:333-352` `handleNodeClick`: 加 `feedback → [data-panel="feedback"]`.
- `App.tsx:184-209` 主区域: 在 `PanelL1` 与 `PanelL2` 之间渲染 `<FeedbackInputCard data-panel="feedback" session={session} />`.
- `Tab` union (`apps/debug-ui/src/App.tsx:27`): **不动**. FeedbackInputCard 留在 `tab === "main"` 的滚动流, 不开新 tab.

### 1.4 combo 角标 (PanelL2 / L2ComboTable)

L2 combo 卡片或行加"反馈影响"角标. 读 `combo.feedback_evidence`. 渲染规则:

- 任一 sub-key (`feedback_recency` / `next_meal_calibration` / `note_boost`) 非空 → 显示角标.
- 角标主标: `⚠ 反馈影响 (净 X.XX)`, X.XX = 三段 contribution 求和 (与 score breakdown 中三 key 值对齐 — 这是冗余但便于交叉校验).
- 鼠标 hover / 点击展开 → 列三段 evidence (rating row / calibration triggers / note tokens).
- 净值为 0 但 evidence 非空 → 显示 `· 反馈中性` 而不是隐藏 (说明 score=0 是 cancel 不是缺数据).

落 `apps/debug-ui/src/panels/L2ComboTable.tsx` (行级), 或加新 `components/FeedbackImpactBadge.tsx` (复用). S1 倾向单独组件, 因为 PanelL2 已经很挤.

### 1.5 自测 (CLAUDE.md 强制)

`chrome-devtools-mcp` 走:
1. 启动后端 `:8765` + debug-ui Vite `:5174`
2. 用 sandbox 注入≥2 feedback (一负一正), 跑一次推荐, 落 trace
3. navigate 到 `:5174`, 选该 session
4. 验:
   - FeedbackInputCard 出现, 3 段都有数据
   - DagHeader Feedback 节点存在, 点击滚到 card
   - L2 combo 卡片至少一条带角标, hover 展开 evidence
   - console 无 error/warn, network 无 4xx/5xx
   - 切到老 v1 trace (sandbox reset 后第一次跑) → Feedback 节点灰显, card 隐藏
5. 截图反馈; 通不过直说"vite 没起 / 数据缺", 不假装通过

---

## 2. PR-3 · What-if `ignore_feedbacks` patch (~半天)

### 2.1 后端 schema 扩

**`chisha/feedback_store.py` `build_feedback_view`**: 给 `ratings[]` 和 `note_tokens[]` 入口补 `session_id` 字段 (`calibrations[]` 已有). 修改点:

- `feedback_store.py:442` ratings.append → 加 `"session_id": sid`
- `feedback_store.py:478` note_tokens.append (note) → 加 `"session_id": sid`
- `feedback_store.py:502` note_tokens.append (comment) → 加 `"session_id": sid`
- `_build_feedback_trace_snapshot` 内 rating_signals / note_breakdown 派生时把 sid 透传过去 (calibration_rules 已有)

**baseline 守门**: 加 sid 是**纯加字段**, 不影响 score, baseline_l2_snapshot 应 0 diff. 风险点是 ratings 的 `len > 0` 路径 fixtures 若严格 dict equal 会炸 — 现状 baseline 用空 store, ratings=[], 应 0 diff. 跑前后两份对照确认.

### 2.2 后端 What-if 接入

**`chisha/debug_what_if.py`**:

```python
ALLOWED_OVERRIDE_KEYS = {
    "n_return", "n_explore", "use_llm_rerank", "profile_overrides",
    "ignore_feedbacks",  # 新增
}

def validate_overrides(overrides):
    ...
    if "ignore_feedbacks" in overrides and overrides["ignore_feedbacks"] is not None:
        v = overrides["ignore_feedbacks"]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise InvalidOverrides("ignore_feedbacks must be list[str] or null")
```

`what_if_rerun()` line 194 之后:

```python
feedback_view_frozen = frozen.get("feedback_view") or []
ignore_sids = set(overrides.get("ignore_feedbacks") or [])
if ignore_sids and isinstance(feedback_view_frozen, dict):
    feedback_view_frozen = _filter_view_by_sids(feedback_view_frozen, ignore_sids)
```

新 helper:

```python
def _filter_view_by_sids(view: dict, ignore: set[str]) -> dict:
    """D-083 PR-3: 从冻结 view 过滤掉指定 sid 的反馈条目, 同步重建 feedback_trace.

    输入 view 已 D-083 v2 结构 (4-key contract). 输出新 dict, 老 view 不变.
    pre-D-083 老 frozen view (ratings/notes 无 sid) 的容忍策略 — 见 Q3.
    """
    new_ratings = [r for r in view.get("ratings", []) if r.get("session_id") not in ignore]
    new_cals    = [c for c in view.get("calibrations", []) if c.get("session_id") not in ignore]
    new_notes   = [n for n in view.get("note_tokens", []) if n.get("session_id") not in ignore]
    new_trace   = _rebuild_feedback_trace_after_filter(
        view.get("feedback_trace"), ignore
    )
    return {
        "ratings": new_ratings,
        "calibrations": new_cals,
        "note_tokens": new_notes,
        "feedback_trace": new_trace,
    }
```

`_rebuild_feedback_trace_after_filter` 落 `feedback_store.py`: 过滤 rating_signals / calibration_rules / note_breakdown 三段 + 重算 global_token_freq + global_active_tokens (跨餐厅去重逻辑要重跑, 见 §3.2.B). 老 v1 view (list) / 无 sid 字段 → 直接 return 原值不过滤, 不破老路径.

### 2.3 SPA UI 接入

**数据源**: 从当前 trace 的 `feedback_view_snapshot` 派生 sid 列表 (跨 rating_signals / calibration_rules / note_breakdown 三段 union, 按 sid 聚合显示 "灶台 (1d, rating=−1, note×1)"). 不需要新后端 endpoint.

**UI 位置**: `WhatIfPanel.tsx` 加新 section "忽略反馈". S1 倾向:

```
WhatIfPanel
├─ 既有: profile_overrides / use_llm_rerank / n_return / n_explore
└─ 新: 忽略反馈 [多选 dropdown / checkbox 列表]
       └─ 选项来自 feedback_view_snapshot 派生 sid 聚合
```

选完点 "重跑" 按钮 (复用现有), POST `/api/debug/what_if` body 加 `ignore_feedbacks: [sid1, sid2]`. 重跑后 trace 对比双栏自然显示差异 (D-079 框架已有).

**联动 FeedbackInputCard**: 每条 entry 旁加 "🚫 假如这条不存在" 小按钮, 点击后 toggle WhatIfPanel 对应 sid 选中 + 自动重跑 (PR-3 终态), **或** 仅 toggle 不自动重跑 (用户确认后再点重跑, S1 倾向, 更安全).

### 2.4 测试

- `tests/test_feedback_trace_d083.py` 扩 `_filter_view_by_sids` 单测: 空 ignore / 全 ignore / 跨段一致性 / 老 list view 不破
- `tests/test_what_if.py` (现有, D-079) 扩: 注入 2 sid feedback, ignore 1, 验剩 1 + score 变化
- baseline_l2_snapshot: ignore_feedbacks=[] 与不传 0 diff

### 2.5 自测

`chrome-devtools-mcp`:
1. sandbox 注入 2+ feedback, 跑推荐, 落 trace
2. SPA 开 WhatIfPanel, 看到 ignore feedbacks 多选, 选 1 个, 重跑
3. 对比双栏: 左 base, 右 What-if, 验 FeedbackInputCard 右栏少 1 条 + L2 combo 角标变化
4. console / network 干净
5. 老 v1 trace 不显示 ignore_feedbacks 控件 (或禁用 + tooltip "需 D-083 v2 trace")

---

## 3. 求 Codex S2 拍板的问题

### 3.1 PR-2 决策点

**Q1** · `empty === true` 时 FeedbackInputCard 隐藏还是显示 banner?
- 选 A (S1 倾向): **隐藏整张 card**, DagHeader 节点灰显 — 减噪
- 选 B: 显示 "今天 0 条反馈" placeholder — 教育新用户
- 判断标准: 志丹是单用户已知此功能存在, 不需要被教育; banner 占屏会盖 L2

**Q2** · combo 角标位置: PanelL2 行内 vs 独立组件 vs 卡片角?
- 选 A (S1 倾向): 独立组件 `FeedbackImpactBadge`, 嵌入 L2ComboTable 行 — 复用 + 不挤
- 选 B: 直接在 PanelL2 行内拼 — 少一个组件但 L2 已挤
- 选 C: 推迟做角标 (P0 trace 够志丹自查, P1 角标志丹不强需求) — 先只做 FeedbackInputCard, 角标看 PR-2 实际用了再决定

**Q3** · 净值 = 0 但 evidence 非空 → 显示 "中性" 还是 hide?
- 选 A (S1 倾向): 显示 "· 反馈中性" — 区分 "无信号" vs "信号互相 cancel"
- 选 B: hide — UI 简洁

**Q4** · DagHeader 老 v1 trace 路径: Feedback 节点是 hide 还是 disabled?
- 选 A (S1 倾向): **disabled (灰显)**, hover tooltip "pre-D-083 trace, 无反馈快照" — 维持 DAG 节点数稳定
- 选 B: hide — 干净但 DAG 节点数随 trace 版本变化, 视觉不稳

### 3.2 PR-3 决策点

**Q5** · ratings / note_tokens 加 `session_id` 字段是不是最优? 还是其他过滤维度?
- 选 A (S1 倾向): 加 sid 字段, sid-level 过滤 — 用户心智清晰 ("假如这条反馈不存在")
- 选 B: 按 `restaurant_name` 过滤 — 不改 schema 但 granularity 粗
- 选 C: 把整个 feedback_store snapshot 写进 `__frozen` (新 frozen 字段), 过滤 store 后重建 view — 最干净但 frozen 体积涨 + D-079 红线敏感

**Q6** · `_rebuild_feedback_trace_after_filter` 重算 global_token_freq:
- 选 A (S1 倾向): 严格重算 (按过滤后 note_breakdown 重新跑 (token, restaurant_name) 去重 + ≥2 阈值) — 与现网逻辑一致
- 选 B: 简单减法 (从原 freq 减掉被忽略条) — 快但 ≥2 阈值边界可能错
- 实现成本差不多, A 更对

**Q7** · 老 frozen view (pre-D-083, 是 list 或无 sid) ignore_feedbacks 行为?
- 选 A (S1 倾向): 静默不过滤 (return 原 view), backend 不报错, SPA tooltip 提示 "老 trace, ignore 不生效"
- 选 B: 400 拒绝 — 太严, 用户体验差
- 选 C: 按 restaurant_name 尽力过滤 — 半精确, 容易解释不清

**Q8** · SPA "假如这条不存在" 联动: 自动重跑 vs 仅 toggle?
- 选 A (S1 倾向): 仅 toggle WhatIfPanel 选中态, 用户主动点重跑 — 防误操作 + 多选攒一起重跑
- 选 B: 自动重跑 — 一键直观但消耗 LLM token (若 use_llm_rerank=true)

**Q9** · FeedbackInputCard 在 What-if 双栏对比模式下渲染: 左右各一份独立 card, 还是只渲染右 (What-if) 那份?
- 选 A (S1 倾向): 左右各一份独立 — 用户能看到 ignore 后 card 内容真变了
- 选 B: 只右 — 减重复

**Q10** · `_filter_view_by_sids` 落在 `feedback_store.py` 还是 `debug_what_if.py`?
- 选 A: `feedback_store.py` — 与 build_feedback_view 同源, 容易共享 helper
- 选 B (S1 倾向): `debug_what_if.py` — PR-3 专用, feedback_store.py 不该知道 What-if 概念

### 3.3 跨 PR 风险

**Q11** · PR-2 和 PR-3 commit 粒度: 2 个 PR (推荐) 还是 1 个累计?
- 选 A (S1 倾向): 2 个 PR (PR-2 先合 main 验 trace 可用, PR-3 再合 — 风险隔离, Codex review 也分两次清楚)
- 选 B: 1 个累计 — 改动总量小, 但 PR-3 依赖 PR-2 类型, 一起合更稳

**Q12** · PR-2 + PR-3 改 `build_feedback_view` schema (加 sid) → 改动放 PR-2 (避免 PR-3 同时改后端 + SPA) 还是 PR-3?
- 选 A (S1 倾向): **放 PR-3**, 严格按需 — PR-2 不需要 sid 也能渲染 (用 restaurant_name 做 React key)
- 选 B: 放 PR-2 — 一次改完 schema, PR-3 只做 filter — 类型扩张前置 (TS optional sid 已经在 PR-2 类型里写了)

### 3.4 隐藏盲点

**Q13** · brief §2.2 主 brief 第三点 "_run_llm_rerank 同时捕 feedback_block_rendered" 已在 PR-1 落, PR-2 是否需要单独 panel 渲染该字符串? 还是只在 PanelL3 已有渲染里加一行?
- 现有 `PanelL3.tsx` 显示什么? 是否已有 prompt 渲染区? **若有 → 加段; 若无 → PR-2 范围内不做, 留 D-083.1**

**Q14** · `feedback_view_snapshot` 在 baseline_l2_snapshot 行为: 当前 baseline 默认 feedback_view=[] (D-082 显式), `feedback_trace` 字段是空骨架. **PR-2 改前端类型 / PR-3 改 backend schema 都不应影响 baseline** — 但需 Codex 确认有没有 fixture 用了非空 feedback_view 会被 sid 字段炸到.

**Q15** · sandbox advance loop + PR-2 渲染性能: 志丹长 sandbox 调试 (advance 100+ 次), feedback_view_snapshot 每次都重算且渲染. 当前 React 渲染策略 (useSession 全量 swap?) 是否有 memo 风险? — PR-2 渲染层用 `useMemo` 按 trace ref 缓存; 不算 PR-2 blocking, 但要标注.

---

## 4. 实施清单 (S2 共识后)

PR-2:
1. 扩 `apps/debug-ui/src/types/trace.ts` (Session + L2Combo)
2. 新 `apps/debug-ui/src/panels/FeedbackInputCard.tsx`
3. 改 `apps/debug-ui/src/components/DagHeader.tsx` 加 feedback 节点
4. 改 `apps/debug-ui/src/App.tsx` 路由 + 主区域挂载
5. (Q2=A) 新 `apps/debug-ui/src/components/FeedbackImpactBadge.tsx`
6. 改 `apps/debug-ui/src/panels/L2ComboTable.tsx` 接入角标
7. chrome-devtools-mcp 自测
8. commit, docs/decisions.md D-083 段加一行 "PR-2 落"

PR-3 (依赖 PR-2 类型, S2 共识后再启):
1. (Q12=A) 改 `chisha/feedback_store.py`: ratings/note_tokens 加 sid + _build_feedback_trace_snapshot 透传 sid
2. 新 `chisha/debug_what_if.py` `_filter_view_by_sids` + `_rebuild_feedback_trace_after_filter` (或 Q10=A 放 feedback_store.py)
3. 改 `chisha/debug_what_if.py` validate + what_if_rerun 接 ignore_feedbacks
4. 改 `apps/debug-ui/src/components/WhatIfPanel.tsx` 加多选 UI
5. (Q8=A) 改 `apps/debug-ui/src/panels/FeedbackInputCard.tsx` 加 "🚫 假如这条不存在" toggle 按钮
6. 测试: tests/test_feedback_trace_d083.py 扩 + tests/test_what_if.py 扩
7. baseline_l2_snapshot 0 diff 验证
8. chrome-devtools-mcp 自测
9. commit, docs/decisions.md D-083 段加一行 "PR-3 落", D-083 整体 marker 改 "done"
10. neat-freak 收口 (BACKLOG.md F-007 标 done + README/ROADMAP 同步)

---

**review 时请回答 Q1-Q15 (倾向选项 + 简短理由), 指出**:
- 漏掉的 case (尤其老 v1 trace / sandbox reset 后空数据 / What-if 双栏对比模式 race)
- 类型设计是否漏字段 (PR-1 trace 实际 shape vs §0 描述)
- 实施清单步骤排序是否合理
- 任何会破 baseline_l2_snapshot 0 diff 守门的隐患

---

## 5. Codex S2 共识 (2026-05-17 落定)

### 5.1 §0 验证结论 (Codex 用代码核对)

| Claim | 结论 | Evidence |
|---|---|---|
| `TRACE_SCHEMA_VERSION=2` + v1 legacy | PASS | `chisha/trace_store.py:28-32`, legacy v1 read path `trace_store.py:144-149` |
| 顶层 `feedback_view_snapshot` in prod trace | PASS | `chisha/api.py:491-539` |
| 顶层 `feedback_view_snapshot` in What-if trace | PASS | `chisha/debug_what_if.py:372-424` |
| `rating_signals[]` 无 `session_id` | PASS | `chisha/feedback_store.py:608-614` |
| `calibration_rules[]` 有 `session_id` | PASS | `chisha/feedback_store.py:656-664` |
| `combo.feedback_evidence` sibling exists | PASS | `chisha/score.py:1436-1475`, `chisha/debug_recommend.py:467-470` |
| `feedback_evidence.next_meal_calibration` shape | **FAIL** | 实际是按 calibration 分组: `[{session_id, restaurant_name, age_meals, age_days, weight, rules_fired:[{rule, contribution}]}]`, 不是扁平 `[{rule, contribution}]` — `chisha/score.py:678-686` |
| `feedback_evidence.note_boost` always has `restaurant_name` | **FAIL** | global entries 用 `freq` 不带 `restaurant_name` — `chisha/score.py:866-895` |
| SPA 未定义 feedback 相关类型 | PASS | `types/trace.ts:58-69, 248-259` |

**§1.1 TypeScript 类型必须按 FAIL 修正** (见 §5.4 修订版).

### 5.2 Q1-Q15 决策

| Q | Choice | Rationale |
|---|---|---|
| Q1 | A | 隐藏 card + 灰显节点, `empty` 骨架已有语义, 减噪 |
| Q2 | A | 独立 `FeedbackImpactBadge` 组件, 需先补 `backend-types.ts` + `adapter.ts` 让 evidence 进 view model |
| Q3 | A | 净 0 + evidence 非空 = cancel, 显式标"中性"区分无信号 |
| Q4 | A | disabled (灰显) 比 hide 稳, DagHeader 节点数稳定 |
| Q5 | A | sid-level 才表达"这条反馈不存在", restaurant 级过粗 |
| Q6 | A | global token 严格重算 (unique restaurant + ≥2 阈值), 简单减法会破阈值边界 |
| Q7 | A | 老 list/无 sid 静默不过滤 + 前端禁用 tooltip, 别 400 破 Replay |
| Q8 | A | 仅 toggle, 用户主动 Run, 多选攒一起 + 防 LLM token 浪费 |
| Q9 | A | 双栏各自渲染 card, 验证 ignore 后 snapshot/evidence 真变化 |
| Q10 | B | 过滤放 `debug_what_if.py`, 公共纯函数留 feedback_store.py 谨慎复用 |
| Q11 | A | 2 个 PR, PR-2 先合验证可视化, PR-3 再合改重跑语义 |
| Q12 | A | sid schema 是 PR-3 过滤依赖, PR-2 用 optional sid 渲染足够 |
| Q13 | 留 D-083.1 | L3 `feedback_block_rendered` 类型/adapter 都未暴露, 不在 PR-2 范围 |
| Q14 | 无阻塞 | baseline 显式 `feedback_view=[]` 已保护, sid 加在空数组上 0 diff: `scripts/baseline_l2_snapshot.py:63-67` |
| Q15 | 非 blocking | React session 全量 swap, sid 聚合用 `useMemo` 防重算即可 |

### 5.3 必改 (PR-2/PR-3 实施前必须修 brief / 实施合同)

1. **修正 brief `next_meal_calibration` evidence 类型** — 实际是 `[{session_id, restaurant_name, age_meals, age_days, weight, rules_fired:[{rule, contribution}]}]` 按 calibration 分组. §1.1 TS 类型按 §5.4 修订.
2. **修正 brief `note_boost` 类型** — global entries 无 `restaurant_name`, 有 `freq: number`. restaurant entries 有 `restaurant_name`, 无 `freq`. §1.1 TS 类型按 §5.4 修订 (用 union).
3. **PR-2 步骤补 `backend-types.ts` + `adapter.ts`** — 否则 `feedback_view_snapshot` / `feedback_evidence` 进不了前端 view model. 加入 §4 PR-2 实施清单 step 1.5 + step 4.5.
4. **PR-3 `BackendWhatIfOverrides` TS 类型扩 `ignore_feedbacks`** — 配合 ALLOWED_OVERRIDE_KEYS 后端扩, 否则 SPA 编译失败.
5. **WhatIf race 防护** — `WhatIfPanel.tsx:73-109` 当前 `postWhatIf()` 无 seq / AbortController, 多次点击 / 切换 base 时晚返回会覆盖新结果. PR-3 实施时**顺手加 seq 号或 AbortController**, 不算 scope creep (D-083 不变量隐含).
6. **PR-3 filtered view 必须传给 L2/L3/trace 全链路** — 当前 `debug_what_if.py:192-246` 直传 frozen view. `_filter_view_by_sids` 输出后必须替换 `feedback_view_frozen` 变量本身, 让后续 rank_combos + v2_rerank + `_build_what_if_trace` 都用 filtered view.

### 5.4 §1.1 TypeScript 类型修订版 (FAIL 修正 + Codex 落地约束)

```typescript
// 修正: next_meal_calibration 按 calibration 分组, rules_fired 嵌套
export type FeedbackEvidenceCalibration = {
  session_id: string | null;
  restaurant_name: string | null;
  age_meals: number;
  age_days: number | null;
  weight: number;
  rules_fired: Array<{ rule: string; contribution: number }>;
};

// 修正: note_boost union, restaurant vs global 字段不同
export type FeedbackEvidenceNoteRestaurant = {
  kind: "restaurant";
  token: string;
  polarity: "boost" | "penalty";
  restaurant_name: string;
  age_days: number;
  decay: number;
  match: -1 | 0 | 1;
  contribution: number;
  subkind?: string;
};

export type FeedbackEvidenceNoteGlobal = {
  kind: "global";
  token: string;
  polarity: "boost" | "penalty";
  freq: number;             // global 才有, restaurant 没有
  age_days: number;
  decay: number;
  match: -1 | 0 | 1;
  contribution: number;
  subkind?: string;
};

export type FeedbackEvidence = {
  feedback_recency?: Array<{
    restaurant_name: string; rating: -1 | 1; age_days: number; signal: number;
  }>;
  next_meal_calibration?: FeedbackEvidenceCalibration[];   // 修正: 嵌套
  note_boost?: Array<FeedbackEvidenceNoteRestaurant | FeedbackEvidenceNoteGlobal>;
};
```

### 5.5 漏项 (Codex 揪出, PR-2/PR-3 实施必须处理)

1. **老 v1 trace 前端空骨架适配** — FeedbackInputCard 必须容忍 `session.feedback_view_snapshot === undefined`, 不能 `.empty` 直接读爆.
2. **sandbox reset 语义** — `sandbox.py:183-194` reset 删除整个 `logs/sandbox` (含 trace/feedback/state). Reset 后第一次推荐, feedback_view_snapshot.empty=true, FeedbackInputCard 按 Q1=A 隐藏. brief 加注释说明.
3. **双栏 race** — 多次点击 / 切换 base session 时旧请求覆盖新 `resultSession`. 已纳入 §5.3 必改 #5.
4. **DagHeader x 坐标重算** — `DagHeader.tsx:77-91` 5 节点位置固定百分比, 插 Feedback 节点要重算所有 x. PR-2 实施时确认布局.
5. **What-if `__frozen` 保持 base** — `debug_what_if.py:391-399` 右栏不能从 `result.__frozen.feedback_view` 派生 (那是 base 的 frozen 不变), 要从 `result.feedback_view_snapshot` 派生.

### 5.6 baseline 0 diff 隐患清单

- ✓ 不破: sibling `feedback_evidence` 只挂 combo 顶层, 不入 breakdown numeric keyset (`score.py:1394-1397` PR-1 已落).
- ✓ 不破: PR-3 加 sid 字段在 ratings/note_tokens 是新 key, baseline 用空数组保护 (`baseline_l2_snapshot.py:63-67`).
- ⚠ 会破: 任何把 evidence list 漏挪进 `score_breakdown` (numeric only 契约) → 立即破 0 diff 守门.
- ⚠ 会破: 改 global token freq / unique restaurant / ≥2 阈值算法 → 破 note_boost score → 破 0 diff.
- 验法: PR-2 (纯前端) 后端不动跑 0 diff 应直接通过; PR-3 改后端 schema 后跑 baseline_l2_snapshot before/after compare, 必须 0 diff.

### 5.7 实施清单微调 (基于 5.3 必改)

PR-2 实施清单 §4 修订:
1. 扩 `apps/debug-ui/src/types/trace.ts` (按 §5.4 修订版)
1.5. **扩 `apps/debug-ui/src/api/backend-types.ts`** (新增, 必改 #3)
2. 新 `apps/debug-ui/src/panels/FeedbackInputCard.tsx`
3. 改 `apps/debug-ui/src/components/DagHeader.tsx` 加 feedback 节点 + x 坐标重算 (漏项 #4)
4. 改 `apps/debug-ui/src/App.tsx` 路由 + 主区域挂载
4.5. **改 `apps/debug-ui/src/api/adapter.ts`** 让 feedback_view_snapshot + feedback_evidence 进 view model (必改 #3)
5. 新 `apps/debug-ui/src/components/FeedbackImpactBadge.tsx`
6. 改 `apps/debug-ui/src/panels/L2ComboTable.tsx` 接角标
7. chrome-devtools-mcp 自测 (含 Q1=A 空 trace 隐藏验证)
8. commit + decisions.md PR-2 标记

PR-3 实施清单 §4 修订:
1. 改 `chisha/feedback_store.py` 加 sid 透传 (ratings/note_tokens + trace 派生)
2. 新 `chisha/debug_what_if.py` `_filter_view_by_sids` + `_rebuild_feedback_trace_after_filter` (Q10=B 放这里)
3. 改 `chisha/debug_what_if.py` ALLOWED_OVERRIDE_KEYS + validate + what_if_rerun 接 ignore_feedbacks (**filtered view 替换 feedback_view_frozen 变量本身, 必改 #6**)
3.5. **扩 `BackendWhatIfOverrides` TS 类型** + adapter 接 ignore_feedbacks (必改 #4)
4. 改 `apps/debug-ui/src/components/WhatIfPanel.tsx` 加多选 UI + **seq/AbortController race 防护 (必改 #5)**
5. 改 `apps/debug-ui/src/panels/FeedbackInputCard.tsx` 加 "🚫 假如这条不存在" toggle 按钮
6. 测试: tests/test_feedback_trace_d083.py + tests/test_what_if.py 扩
7. baseline_l2_snapshot before/after 0 diff 验证 (Codex §5.6 显式要求)
8. chrome-devtools-mcp 自测 (含双栏 card 独立渲染验证, 漏项 #5)
9. commit + decisions.md PR-3 标记, D-083 整体 done
10. neat-freak 收口

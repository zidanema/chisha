# D-083 草案: feedback 短链路观测性补齐 (Opus S1 → 求 Codex S2)

> 决策号: **D-083** (待落 docs/decisions.md)
> 范围: trace_store + score breakdown + debug-ui DAG + What-if patch
> 历史背景: 紧接 D-080 (B-002 ingredient_want 穿透) + D-081 (B-001 v2 feedback 短链路)

---

## 1. 问题陈述 (志丹沙箱体验暴露)

B-001 (D-081) 引入了 **feedback → feedback_view (3 段派生) → score + L3 prompt** 的短链路:

```
logs/feedback/store.json
        │
        ▼
build_feedback_view(store, today)  ← 中间派生层
        │
   ┌────┼────┬─────────────┐
   ▼    ▼    ▼             ▼
ratings calibrations note_tokens
   │    │    │
   ▼    ▼    ▼
score.py:  feedback_recency / next_meal_calibration / note_boost
   │
   ▼
combo.breakdown (只在命中时写 key)
   │
   ▼
top60 排序 → L3 LLM (prompt 渲染 [FEEDBACK_RECENT] / [LAST_MEAL_SIGNAL] / [NOTE_HINTS])
```

**核心 gap**: feedback_view (中间派生层) 在 trace + debug-ui 里完全不可见. 志丹在沙箱里调试时无法回答:
- "这次推荐受了哪些过去反馈影响?"
- "灶台那条 −1 对当前 combo 的影响是 −1.40, 公式怎么算的?"
- "如果我把昨天那条反馈删了, top5 会变吗?"

只能看到 *果* (combo breakdown 里有 −1.40), 看不到 *因* (这 −1.40 来自哪条反馈, 衰减系数怎么算的, 该条反馈对其他 combo 还有什么影响).

---

## 2. P0 trace 持久化 (后端零前端, ~2h)

### 2.1 改 `build_feedback_view` 返回值

增带因果字段, 但**只在派生层加, 不污染 v2 dict 三段主结构**:

```python
{
  "ratings": [...],          # v2 主体, 不变
  "calibrations": [...],     # v2 主体, 不变
  "note_tokens": [...],      # v2 主体, 不变

  # ── D-083 新增 trace 字段 (实现: 平铺 sibling key `feedback_trace`,
  #     **不是嵌套 `_trace`** — Codex S2 共识: 避开 normalize_feedback_view
  #     历史"剥离未知 key"行为; PR-1 落地按此实现.) ──
  "feedback_trace": {
    "today": "2026-05-17",
    "windows": {"ratings": 60, "calibrations": 7, "note_tokens": 14},

    # 每条 rating 的瞬时信号 + 公式
    "rating_signals": [
      {"sid": "...", "restaurant_name": "灶台", "rating": -1,
       "age_days": 1, "signal": -1.40,
       "formula": "−1.5 × exp(−1/14)"}
    ],

    # 每条 calibration 命中规则
    "calibration_rules": [
      {"sid": "...", "restaurant_name": "灶台", "age_meals": 0, "age_days": 1,
       "weight": 1.0,
       "rules_fired": [
         {"rule": "oil_calibration=2 太油 → avg_oil≤2 +0.5", "weight": 1.0},
         {"rule": "fullness=0 没饱 → protein≥1.5×floor +0.4", "weight": 1.0}
       ]}
    ],

    # 每条 note_token 的衰减 + 抽取
    "note_breakdown": [
      {"sid": "...", "restaurant_name": "灶台", "age_days": 1,
       "decay": 0.867,  # exp(-1/7)
       "raw_text": "太油了，下次想喝点汤",
       "boost": ["low_oil", "wetness"], "penalty": [],
       "source": "note"}
    ],

    # 全局 token 频次 (跨餐厅)
    "global_token_freq": {"low_oil": 3, "spicy": 1},
    "global_active_tokens": ["low_oil"]  # 命中 _NOTE_GLOBAL_MIN_HITS≥2 的
  }
}
```

### 2.2 改 `api.py` 写 trace

`/api/debug_recommend` 响应里加 `feedback_view_snapshot` 顶层节点:

```python
{
  ...,
  "l2_score": {...},
  "feedback_view_snapshot": effective_feedback_view.get("feedback_trace"),  # 顶层平铺
  "l3_rerank": {...}
}
```

### 2.3 改 `score.py` combo 级 *因* 引用 (实现: sibling, 不入 breakdown)

**Codex S2 拍板**: evidence 必须挂在 **`combo["feedback_evidence"]`** sibling, 而非
breakdown 内 `*_evidence` key — 否则 `debug_recommend._format_ranked_for_trace`
对每个 breakdown value 做 `round(v, 3)` 会炸 (numeric 契约).

`feedback_recency` / `next_meal_calibration` / `note_boost` 命中时:
- `parts["feedback_recency"] = signal × weight` (numeric, 入 breakdown)
- `feedback_evidence["feedback_recency"] = [...]` (list, 不入 breakdown)

```python
# score.score_combo (PR-1 实际实现, line ~1308):
ev_collector: dict = {}  # rank_combos 注入
fb_signal, fb_ev = feedback_recency_score(combo, view, with_evidence=True)
if fb_signal != 0.0:
    parts["feedback_recency"] = fb_signal * _w("feedback_recency")  # numeric
    if ev_collector is not None and fb_ev:
        ev_collector["feedback_recency"] = fb_ev                     # sibling
# rank_combos 收完 ev_collector 后:
scored.append({**c, "score": s, "score_breakdown": br,
                "feedback_evidence": ev_collector or {}})
```

### 2.4 backward compat

- 老 frozen trace 没有 `feedback_trace` 字段 → `normalize_feedback_view` 兜底空骨架 (4-key contract 严格不变, 见 `_empty_feedback_trace_skeleton`)
- baseline_l2_snapshot 默认不写 `feedback_trace` (空 store 路径已是空骨架, 无 noise)
- TRACE_SCHEMA_VERSION 1→2: `LEGACY_TRACE_SCHEMA_VERSIONS={1}` 让读侧兼容老 trace (前端走空骨架兜底)

### 2.5 测试

- `tests/test_feedback_trace_d083.py`:
  - rating_signals 公式数学正确性 (peak=−1.5, exp(−1/14)≈−1.40)
  - calibration_rules.triggers 描述与 score.py 实际加分映射一致 (核心防漂移)
  - empty store → `feedback_trace.empty=True` 骨架而非 None
  - `with_evidence=False` 默认返 float (老 caller 不破)

---

## 3. P1 debug-ui 可视化 (~半天)

### 3.1 DAG 新节点 `FeedbackInputCard`

在 score 节点 *上游* 插一个 card (与 L1 prefs 同级, 都是 "中间派生层"):

```
┌─ FEEDBACK INPUT (today=2026-05-17) ─────────────────┐
│ 📊 Ratings (60d):                                   │
│   灶台   −1  (1d)  → −1.40   公式: −1.5·exp(−1/14) │
│                                                     │
│ 🎯 Calibrations (≤3 餐, 7d 硬闸):                   │
│   灶台 (age=0): 油✗ 饱✗ 理由✗  weight=1.0          │
│     ↳ 3 rules fired:                                │
│        oil=2 → avg_oil≤2 +0.5                       │
│        fullness=0 → n_dishes≥4 +0.4                 │
│        reason=0 → cuisine≠灶台 +0.2                 │
│                                                     │
│ 📝 Note tokens (14d):                               │
│   灶台 (1d, decay=0.87): "太油了..."                │
│     → low_oil + wetness                             │
│   🌐 全局高频 (≥2 次): low_oil×3                    │
└─────────────────────────────────────────────────────┘
```

数据源: 顶层 `feedback_view_snapshot` (P0 已落, **平铺不嵌套**).

### 3.2 combo 卡片"反馈影响"角标

```
┌─ combo_023  灶台 ─────────────────────┐
│ L2: 4.20 → 排名 #28                  │
│ ⚠ 反馈影响 (净 −0.97):                │
│   feedback_recency  −1.40            │
│   note_boost        +0.43            │
│   [hover 看证据 sid 列表]             │
└──────────────────────────────────────┘
```

数据源: **`combo.feedback_evidence`** (P0 已落, **sibling 不入 breakdown** — Codex S2 共识).

### 3.3 与现有 DAG 框架 (D-075) 集成

新组件落 `apps/debug-ui/src/panels/FeedbackInputCard.tsx`, 由 DAG 顶层路由按 trace 顶层是否有 `feedback_view_snapshot` 且 `.empty===false` 决定是否渲染. 不破现有 5 主题 + Replay/What-if/Live 三模式 (D-079).

---

## 4. P2 What-if patch (~半天)

### 4.1 D-079 patch 框架扩

`debug_what_if.py` 当前 patch 维度: profile / refine / sandbox 时钟. 加一个新维度 `ignore_feedbacks`:

```python
WhatIfPatch(
  ...,
  ignore_feedbacks=["20260516_lunch_c9fd"]  # 新增
)
```

调用方实现: build_feedback_view 之前过滤掉指定 sid, 然后正常跑 score + rerank.

### 4.2 SPA 入口

WhatIfPanel.tsx 加一个 "忽略反馈" 多选, 选项来自 FeedbackInputCard 里展示的反馈 sid 列表. 一键 "假如这条不存在".

### 4.3 scope 边界 (Codex Q4 求拍板)

- **只支持 "忽略"** (软删除, 不动 store), 不支持 "编辑 rating/note" — 后者耦合 D-079 太深, 留 D-083.1
- 沙箱 advance 后, ignore_feedbacks 跟随 What-if state (不持久化到 sandbox session)

---

## 5. 不变量提议 (写 docs/CONTRACTS.md)

> **D-083 不变量**: 任何写入 score breakdown 的派生信号 (不限 feedback), 其**输入快照**必须进 trace; debug-ui DAG 必须有对应可视化节点. 适用范围: feedback_recency / next_meal_calibration / note_boost / L1 prefs 行为信号. 未来新增类似派生信号时 (例如 L1 词表扩 / D-074 AI-friendly), 必须同步落 trace + DAG.

---

## 6. 求 Codex S2 critique 的具体问题

1. **schema 取舍**: signal/_formula 字段挂每条 entry 还是 view 顶部聚合? 我选每条 entry (因果可追溯), 但 trace 体积变大. 60 条 ratings × 50 字节 ≈ 3KB/次, 沙箱 advance 100 次 → 300KB. 是否需要 lazy / 抽样?

2. **沙箱 advance loop 性能**: 每次 advance 都重新 build_feedback_view 并写 trace, 长时间调试是否需要 trace_store 的 ring buffer / TTL?

3. **backward compat**: 老 frozen trace + baseline_l2_snapshot 字段不带 `feedback_trace`. 我的方案是 "调用方 `.get('feedback_trace') or _empty_skeleton()`", 是否足够? baseline_l2_snapshot 加 `--with-trace` flag 是否优雅? [PR-1 落地: 走空骨架兜底 + LEGACY_TRACE_SCHEMA_VERSIONS={1}]

4. **P2 scope**: 只"忽略 feedback" vs 也支持"编辑 rating/note 后重算"? 后者更强但与 D-079 patch 类型耦合.

5. **不变量边界**: L1 prefs 中间层 (`load_prefs` 结果) 同样不可见. 是否一并纳入 D-083? 还是 D-083 只管 feedback 短链路, L1 留单独决策号?

6. **隐藏盲点**: L3 prompt 段 `[FEEDBACK_RECENT]` / `[LAST_MEAL_SIGNAL]` / `[NOTE_HINTS]` 是渲染*输出*, 与 score breakdown 是双轨. 是否要在 trace 里也存一份 `l3_feedback_block_rendered` 文本 (而不只是埋在 `user_message_full` 4KB 大文本里)?

7. **过度设计审查**: P1 + P2 是否真要现在做? 还是先做 P0 (trace 数据), 等志丹真用过 P0 数据再决定 P1/P2 形态?

8. **冷启动 / 空数据**: 沙箱 reset 后第一餐, `_trace` 是空骨架. UI 怎么显示? "今天 0 条反馈" 单独 banner, 还是直接 hide FeedbackInputCard?

9. **What-if frozen 路径互动**: D-079 already passes `__frozen.feedback_view`. P2 的 `ignore_feedbacks` 是 *在* frozen view 上再过滤, 还是会冲突? 这块 D-079 红线"What-if 零 runtime read" 要确认不破.

10. **commit 粒度建议**: P0/P1/P2 分 3 个 PR, 还是单分支累计?

---

## 7. 共识达成后, Opus 落地步骤

1. 改 `chisha/feedback_store.py` `build_feedback_view` 增 `feedback_trace` 顶层 sibling
2. 改 `chisha/score.py` 3 个 fn 加 `with_evidence=True` kwarg, `rank_combos` 挂 `combo.feedback_evidence` (sibling, **不入 breakdown**)
3. 改 `chisha/api.py` 写 `feedback_view_snapshot`
4. 改 `chisha/debug_what_if.py` 加 `ignore_feedbacks` patch
5. 新 `tests/test_feedback_trace.py` (P0 数学正确性 + score 一致性)
6. 新 `apps/debug-ui/src/panels/FeedbackInputCard.tsx`
7. 改 `apps/debug-ui/src/.../DagView.tsx` 渲染 FeedbackInputCard + combo 角标
8. 改 `apps/debug-ui/src/components/WhatIfPanel.tsx` 加 ignore_feedbacks UI
9. 落 `docs/decisions.md` D-083 (≤ 15 行)
10. 落 `docs/CONTRACTS.md` 不变量
11. 自测 (sandbox 触发 + UI 验证 + chrome-devtools-mcp)
12. Codex 第二轮 review

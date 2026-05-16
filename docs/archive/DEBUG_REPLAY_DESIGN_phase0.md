# Debug Replay & What-if 技术设计 (D-079)

> 状态: **draft for Codex review** · 日期: 2026-05-16 · 配套 PRD: [DEBUG_REPLAY_PRD_phase0.md](DEBUG_REPLAY_PRD_phase0.md)
> 前置阅读: D-072.1 baseline trace · D-075 debug-ui SPA · D-077 sandbox time-travel · D-078 收尾

---

## 1. 架构总览

```
                           ┌─────────────────────────────────┐
                           │  apps/debug-ui/ (D-075 SPA)      │
                           │                                  │
        ┌──── Sidebar ────►│  GET /api/debug/sessions         │ (1)
        │                  │     ↓ pick a session_id          │
        │                  │  GET /api/debug/sessions/{sid}   │ (2)
        │                  │     ↓ render L1/L2/L3/Final      │
        │  Replay (R)      │                                  │
        ▼                  │  edit weights → click "What-if"  │
   logs/recommend_trace/   │  POST /api/debug/what_if         │ (3)
   {sid}.json              │     body: {sid, overrides}       │
        ▲                  │     ↓ frozen ctx + L1 combos     │
        │ writes           │     ↓ re-run L2/L3 only          │
        │                  │                                  │
   ┌────┴────────────┐     │  Live button →                   │
   │ chisha/api.py   │     │  POST /api/debug_recommend       │ (4 = 现状)
   │  recommend_meal │     │                                  │
   │  refine()       │     └─────────────────────────────────┘
   │   ▲ trace hook  │
   └────────────────┘
   生产路径每次调用 → trace 落盘 (sandbox/prod 派生)
```

(1) Replay 列表 · (2) Replay 详情 · (3) What-if · (4) Live(保留)

## 2. 数据模型 / Trace Schema

### 2.1 落盘文件结构
- 位置: `logs/recommend_trace/{session_id}.json`(sandbox 启用 → `logs/sandbox/recommend_trace/`)
- 一次推荐一个文件,**不写 jsonl**(单行膨胀难调试)
- 单文件**硬上限 300KB**(超过裁剪,详见 §10),实际 ~100-200KB
- **V1 flat dir**,假设阈值 `<10k traces`(30天 ~600 traces 远低于此)。超过 → 加 `YYYY/MM/` 分桶或 sqlite index,DEFER 到 V2

### 2.2 顶层 schema(与前端 Session type 对齐 + 后端扩展字段)
```ts
{
  // —— 与前端 apps/debug-ui Session type 完全一致的字段 ——
  session_id: string,           // sess_lunch_20260516_122334_a1b2
  started_at: string,           // ISO datetime (clock.now)
  total_latency_ms: number,
  ctx_latency_ms: number,
  final_latency_ms: number,
  l1: L1Trace,                  // 召回:hard_filter drops + diversity_filter drops + combos
  l2: L2Trace,                  // 打分:ranked top60 + 16维 breakdown + caps + dim_stats
  l3: L3Trace,                  // LLM 精排:payload + raw response + parsed + fallback_chain
  final: FinalRow[],            // 终选 5
  refine: RefineTrace,          // refine 二轮(若发生)

  // —— 后端 only 扩展字段(D-079 新增,前端可选用)——
  __version: 1,                 // schema 版本,改 schema 时 bump
  __frozen: {                   // What-if 需要冻结的最小集合 (自包含,不读 runtime state)
    ctx: ContextSnapshot.to_llm_dict(),   // daily_mood/refine_input/now/last_meal/recent_3d_*/weather
    today: string,              // YYYY-MM-DD (clock.today) — fallback / L3 必须用这个,不用 dt.date.today
    meal_type: "lunch" | "dinner",
    zone: string,
    profile_snapshot: dict,     // 当时生效的 profile (含 methodology spec 解析后)
    l1_combos: list[Combo],     // L1 召回 + diversity 过滤后送 L2 的完整 combos (含 dish 全字段)
    l1_prefs_snapshot: dict,    // l1_prefs.load_prefs(root) 当时快照 — 防 D-076 LLM 抽取层漂移 (Codex #1)
    l2_meal_log_view: list[dict],  // L2 variety_bonus 看的 meal_log 切片 (Codex #4 + Q3)
                                   // = score.variety_bonus_score 消费的最近 7 天条目
                                   // What-if 把这个传给 rank_combos,而不是 [] 也不是 raw meal_log
  },
  __config: {                   // 用户触发时的开关(给 Replay UI 展示)
    use_llm_rerank: boolean,
    n_return: number,           // 默认 5
    n_explore: number,          // 默认 2
    daily_mood: string | null,
    refine_text: string | null,
    profile_overrides: dict | null,
  },
  __feedback_link: {            // 派生字段,Sidebar badge 用(若存在)
    accepted: boolean,
    accepted_rank: number | null,
    accepted_at: string | null,
    feedback_submitted: boolean,
    rating: number | null,
    stopped: boolean,
  } | null,
  __source: "production" | "what_if_preview",    // 持久化的 trace 只能是 production (Codex +1)
                                                  // what_if_preview 仅出现在 What-if API response,不落盘
                                                  // Live (debug_recommend) 直接返 Session shape,不写 trace
  __parent_session_id: string | null,            // What-if 时 = 原 Replay 的 sid
  __llm_called: boolean,                          // 本次是否真发了 L3 LLM (Codex +4 透明性)
}
```

### 2.3 关键设计选择
- **`__frozen.l1_combos` 存全量 dish 字段(非 dish_id refs)**:What-if 重跑时不依赖 zone 数据(zone 数据可能被改)、不依赖 LLM tagging(可能版本变),trace 自包含
- **`__frozen.profile_snapshot` 存完整 profile**:同上,自包含。代价:每 trace 多 20KB,可接受
- **`__frozen.l1_prefs_snapshot` 必存**:L2 通过 `l1_prefs.load_prefs(root)` 读 D-076 LLM 抽取的长期偏好,这是 runtime-load 点,不冻结会导致 What-if 漂移
- **`__frozen.l2_meal_log_view` 必存且非空**:`score.variety_bonus_score` 看最近 7 天 meal_log。What-if 用 `[]` 会让 variety_bonus = 0,违反"零 override = 原 Replay"
- **`l3.llm_raw_response` 全量保存**:Replay 时直接展示历史 LLM 输出,不重发请求
- **`__feedback_link` 是派生字段**:每次读 trace 时从 `feedback_store.load_store(root)` 实时算,不写死(因为反馈可能晚于 trace 几小时才到)
- **`session_id` 必须唯一 + 可作为文件名**:不能含 `/`、空格 → 现有 `_gen_session_id()` 已满足

### 2.4 Schema compatibility policy (Codex #2)

- **新增可选字段** = additive, **不 bump** `__version`. Replay 必须 best-effort 渲染(老 reader 忽略未知字段)
- **删字段 / 改字段语义 / 改字段类型** = breaking, **bump** `__version`. Replay 仍尽量渲染(标 "schema old, fields missing");What-if 一律 409 拒绝
- **What-if 要求 exact `__version` 匹配**:跨版本的 frozen ctx/combos 反序列化不保证 — 防止隐性精度漂移
- Replay 容忍策略:`l1/l2/l3/final/refine` 这 5 个核心字段任一缺失 → Replay 仍渲染其它字段并显式 banner "partial trace"
- 版本表(写在代码注释):
  - `__version=1`: D-079 初版
  - 每次 bump 在 CHANGELOG-style 段落里说明加/删了什么

## 3. 改造点清单(代码)

### 3.1 新增模块
**`chisha/trace_store.py`**(新增,~150 行):
```python
def trace_dir(root: Path | None = None) -> Path:
    """sandbox 派生路径. 复用 data_root._maybe_sandbox 模式."""

def write_trace(session_id: str, trace: dict, root: Path | None = None) -> None:
    """原子写: tmp + replace. 失败仅 logger.warning, 不抛."""

def read_trace(session_id: str, root: Path | None = None) -> dict | None:
    """读 + schema 版本校验. Failure matrix (Codex #5):
       - 不存在: 返 None (调用方决定 404)
       - JSON 损坏: 备份 .corrupt.{ts}.bak + 抛 TraceCorrupt (调用方决定 500)
       - schema __version 不识别: 抛 TraceVersionMismatch (调用方决定 409)
       - 顶层字段不是 dict: 同损坏处理
    fail-closed 与 feedback_store.load_store (D-066/067 MED-3) 一致."""

def list_traces(
    root: Path | None = None,
    limit: int = 30,
    meal_type: str | None = None,
) -> tuple[list[dict], int]:
    """列出最近 N 条 trace meta(不读 full body). 按 started_at desc.

    返 (items, corrupt_count). 损坏的 trace 跳过(不抛), 仅在 corrupt_count
    累计计数, 调用方决定要不要给前端展示 "N 条损坏被跳过" warning.

    items: [{session_id, started_at, meal_type, zone, top1_summary,
             total_latency_ms, l3_status, __feedback_link}].
    """

def attach_feedback_links(items: list[dict], root: Path | None) -> list[dict]:
    """从 feedback_store 派生 accepted/rating/stopped, 不写回 trace 文件."""

def purge_old_traces(root: Path | None, keep_days: int = 30) -> int:
    """V1 不主动调; 留接口给 V2 归档."""
```

### 3.2 改造 `chisha/api.py:recommend_meal()`
- **不重写**,只在 L1/L2/L3 调用前后插入轻量观测器
- 复用 `chisha/debug_recommend.py` 已有的 `_traced_hard_filter / _traced_diversity_filter / _format_ranked_for_trace / _llm_rerank_traced` 函数(它们已经做了 90% 的工作)
- 方案:**把 `debug_recommend()` 重构成两个函数**:
  - `compute_recommendation(req, root)` → 跑完整链路,返 `(final_response, full_trace)` 二元组
  - `recommend_meal()` 调它,把 `final_response` 返给前端、把 `full_trace` 走 `trace_store.write_trace()`
  - `/api/debug_recommend` 老端点也调它,直接把 `full_trace` 返(向前兼容现有 debug-ui)
- **生产链路改动总量 ≤30 行**,且都是 hook 不动核心逻辑

### 3.3 改造 `chisha/web_api.py`
新增 3 个端点:
```python
@router.get("/api/debug/sessions")
def list_debug_sessions(
    limit: int = 30,
    meal_type: Optional[str] = None,
) -> list[dict]:
    """Sidebar 列表数据源. 返 trace meta + feedback badge."""

@router.get("/api/debug/sessions/{session_id}")
def get_debug_session(session_id: str) -> dict:
    """Replay 详情. 返完整 trace + 实时 attach feedback_link."""

@router.post("/api/debug/what_if")
def what_if_rerun(req: WhatIfReq) -> dict:
    """读 base_sid trace, 用 __frozen.{ctx, l1_combos, profile_snapshot}
    冻结上游, 用 req.overrides 覆盖 profile 下游字段, 重跑 L2 + L3.
    返新 trace (含 __source='what_if' + __parent_session_id=base_sid).
    不写盘 (临时实验)."""

class WhatIfReq(BaseModel):
    base_session_id: str
    overrides: WhatIfOverrides

class WhatIfOverrides(BaseModel):
    # 允许改的字段白名单(超出范围 400)
    scoring_weights: dict | None = None
    plate_rule: dict | None = None
    recall: dict | None = None     # per_*_top_k caps
    scoring: dict | None = None    # unforgivable_discount
    use_llm_rerank: bool | None = None
    n_explore: int | None = None
    n_return: int | None = None
```

### 3.4 改造 `apps/debug-ui/`
**核心原则:不动 L1/L2/L3/Final/Refine/Trace panel 组件,只换数据源 + 加两个新组件。**

- `src/lib/sessionCache.ts`:**保留** localStorage 作为离线 fallback,但主源切到 `/api/debug/sessions`。`useSession.ts` 加 `useEffect` fetch 后端列表
- `src/components/Sidebar.tsx`:每行展示新增的 feedback badge(⭐❤🚫)
- `src/components/WhatIfPanel.tsx`(新增):覆盖 L2 panel 的 weights edit 模式,出 diff badge + 双栏对比
- `src/components/LiveBanner.tsx`(新增):Live 模式时顶部金色 banner
- `src/api/`:加 `fetchSessions / fetchSession / postWhatIf` 三个函数

### 3.5 改造 `chisha/refine.py` 端点
refine 二轮也要写 trace:同样的 hook 模式,但 trace 文件名用 **同一个 session_id**(不新建),通过 `trace.refine` 字段覆盖。
- 实现:`refine` 端点在写 trace 前先 `read_trace(sid)`,把 `trace.refine` 替换后再 `write_trace(sid, ...)`。原子覆盖
- 这保证 Sidebar 一条 session 一行,不分裂

**base trace 缺失/损坏分支** (Codex +3):
- `read_trace(sid)` 返 None(首轮 trace 写盘失败,best-effort 降级了)→ logger.warning + refine response **正常返回**, 但**不持久化** refine trace (没有 base trace 可附着)
- `read_trace(sid)` 抛 TraceCorrupt → logger.error + 同上不持久化
- 不创建 "refine_only" 孤儿 trace(Replay 列表读 trace 文件,没文件就不出现,UI 也不用专门处理 badge)
- 不阻断 refine 自身链路(refine 响应该返还是返)

### 3.6 改造 `chisha/rerank.py:_pick_explore` (Codex Q3 FIX-NOW)
当前 `chisha/rerank.py:576` 写死 `dt2.date.today() - timedelta(days=7)`,这是 L3 fallback 选 explore 时看的"最近 7 天店"过滤。问题:What-if 默认 `use_llm_rerank=False` 走 fallback,fallback 用 wall-clock today 而非 frozen today → What-if 日期漂移。

改造:
- `_pick_explore(rest, exploit, meal_log, n_explore, today)` 加 `today: dt.date` 参数
- `v2_rerank(..., today=today)` 接收并透传
- `recommend_meal()` 和 What-if 调用都显式传 today
- 单测 `test_pick_explore_uses_provided_today_not_wall_clock`:monkeypatch `dt.date.today` 返怪异值,传 frozen today,断言结果与 wall-clock 无关

## 4. What-if 冻结边界(明确合同)

### 4.1 What-if 时**冻结不可改**的字段(P/4 - 推荐答的"冻结 ctx+候选池"):
| 字段 | 来源 | 为什么冻结 |
|---|---|---|
| `__frozen.ctx.now` | trace 写盘时的 clock.now | 时间影响 last_meal 计算 / weather / weekday |
| `__frozen.ctx.daily_mood` | 当时用户输入 | UI 不让 What-if 改 mood(违反 D-071 红线) |
| `__frozen.ctx.refine_input` | refine 二轮文本 | 改文本 = 改意图 = 新场景,Live 模式做 |
| `__frozen.ctx.refine_intent` | D-073 结构化意图 | 同上 |
| `__frozen.ctx.last_meal` | meal_log 派生 | 改 meal_log 是别的实验 |
| `__frozen.ctx.recent_3d_*` | meal_log 派生 | 同上 |
| `__frozen.today` | clock.today | 影响 cooldown 判断 |
| `__frozen.zone` | 当时配置 | 改 zone = 召回不同店,本质 Live |
| `__frozen.l1_combos` | L1 召回 + diversity 过滤后产物 | **核心**:What-if 不重跑 L1,跳过 zone 数据加载、跳过 LLM tagging |
| `__frozen.l1_prefs_snapshot` | l1_prefs.load_prefs(root) 当时快照 | L2 通过 load_prefs 读 D-076 抽取的偏好,这是 runtime-load 漂移点 (Codex #1) |
| `__frozen.l2_meal_log_view` | score.variety_bonus 看的最近 7 天 meal_log 切片 | L2 cooldown/variety 看 meal_log,空传 = variety_bonus 归零,违反零 override 等价性 (Codex #4) |

### 4.2 What-if **可以改**的字段:
| 字段 | 影响 | 验证 |
|---|---|---|
| `scoring_weights.*` (16 维) | L2 打分顺序 | 写盘 schema 严格 keyset(参考 D-072 字段表) |
| `plate_rule.*` (5 项) | 注意:L1 已冻结,plate_rule 改了**不重跑 hard_filter**,但 L2 的 `vegetable_floor_pass / protein_floor_pass / low_oil` 维度会用到 |
| `recall.per_*_top_k` (4 层 cap) | apply_caps 重算 | 与现有 caps 兼容 |
| `scoring.unforgivable_discount` | L2 兜底惩罚 | 同上 |
| `use_llm_rerank` | L3 走 LLM 还是 fallback | 关掉 = 0 LLM 调用 |
| `n_explore / n_return` | L3 explore/exploit 比 | 同上 |

### 4.3 What-if 算法伪代码 (修订版,吸收 Codex #1 / #4 / Q3)
```python
def what_if(base_sid: str, overrides: WhatIfOverrides, root: Path) -> dict:
    try:
        base = read_trace(base_sid, root)
    except TraceCorrupt:
        raise HTTPException(500, "base trace corrupt (backed up)")
    except TraceVersionMismatch:
        raise HTTPException(409, "trace schema version mismatch — what-if requires exact version")
    if not base:
        raise HTTPException(404, "trace not found")

    # === 冻结上游 (全部从 trace 自包含字段反序列化,绝不读 runtime state) ===
    frozen = base["__frozen"]
    ctx = rebuild_ctx_from_dict(frozen["ctx"])      # 纯反序列化, 不调 build_context
    combos = frozen["l1_combos"]                     # L1 不重跑
    profile = deep_merge(frozen["profile_snapshot"], overrides_to_profile_patch(overrides))
    today = dt.date.fromisoformat(frozen["today"])   # 不用 clock.today / dt.date.today
    meal_type = frozen["meal_type"]
    l1_prefs = frozen["l1_prefs_snapshot"]           # Codex #1: 不调 l1_prefs.load_prefs(root)
    l2_meal_log = frozen["l2_meal_log_view"]         # Codex #4: 传冻结 view, 不传 [] / raw

    # === 重跑下游 ===
    # 注意: rank_combos 内部如有 load_prefs(root) 调用, 必须能被 l1_prefs override 注入
    # 实施时新增 rank_combos(..., l1_prefs_override=l1_prefs) kwarg, 默认 None=正常 load_prefs
    ranked = rank_combos(
        combos, profile, meal_log=l2_meal_log, today=today,
        context=ctx, meal_type=meal_type, root=root,
        l1_prefs_override=l1_prefs,
    )
    ranked = apply_caps(ranked, profile)

    # use_llm_rerank 默认 False (Codex +4), 显式 True 才调
    use_llm = bool(overrides.use_llm_rerank)
    llm_called = False
    if use_llm:
        try:
            final = v2_rerank(ranked[:L3_INPUT_TOP_K], profile, context=ctx,
                              meal_log=l2_meal_log, n=overrides.n_return or 5,
                              n_explore=overrides.n_explore or 2,
                              today=today,         # Codex Q3: 透传 frozen today
                              refine=False, use_llm=True)
            llm_called = True
        except Exception:
            final = fallback_rerank(ranked[:L3_INPUT_TOP_K],
                                     n=overrides.n_return or 5,
                                     n_explore=overrides.n_explore or 2,
                                     meal_log=l2_meal_log, today=today)
    else:
        final = fallback_rerank(ranked[:L3_INPUT_TOP_K],
                                 n=overrides.n_return or 5,
                                 n_explore=overrides.n_explore or 2,
                                 meal_log=l2_meal_log, today=today)
                                 # Codex Q3: fallback_rerank 内部 _pick_explore 必须用 today 不用 dt.date.today

    new_trace = build_trace_from_what_if(base, ranked, final, overrides)
    new_trace["__source"] = "what_if_preview"        # 不持久化
    new_trace["__parent_session_id"] = base_sid
    new_trace["__llm_called"] = llm_called           # Codex +4 透明性
    return new_trace                                  # 不写盘
```

**实施依赖** (本节驱动的代码改动):
1. `rank_combos` 加 `l1_prefs_override` kwarg(默认 None → 正常 `load_prefs`,传值 → 用传入的)
2. `_pick_explore` 接 `today` 参数,不再用 `dt.date.today` (§3.6)
3. `v2_rerank` / `fallback_rerank` 透传 today 给 `_pick_explore`

### 4.4 Codex 应审视的边界点
- meal_log=[] 给 L2:是否影响 V2_DEFAULT_WEIGHTS 里某些维度(变量名搜 meal_log 在 score.py 的使用次数)
- `rebuild_ctx_from_dict` 必须能反向构建出 LastMeal / FeedbackSummary / RefineIntent 对象,且 `to_llm_dict()` 输出等价 → 加单测 `test_ctx_roundtrip`
- profile_snapshot 已是 methodology spec merge 之后的最终 profile,what_if overrides 直接覆盖最终值,绕过 spec 加载层 — **这是有意的**,what-if 不验证 spec

## 5. 落盘 hook 集成点

### 5.1 写 trace 时机
- `recommend_meal()` 跑完最后一步、写 `recommend_log.jsonl` 之前:`trace_store.write_trace(sid, trace)`
- `refine()` 跑完后:`read_trace(sid)` → 改 `refine` 字段 → `write_trace(sid, trace)`(覆盖)
- 失败处理:`try / except Exception as e: logger.warning(...)`,**不阻断 recommend 返回**

### 5.2 trace 收集时机(在 L1/L2/L3 内部 vs 外部包裹?)
**选择外部包裹**:
- L1/L2/L3 的内部函数(`hard_filter`、`rank_combos`、`v2_rerank`)**不动**
- 在 `compute_recommendation()` 里用 `chisha/debug_recommend.py` 的 traced 版本
- 生产 vs debug 走同一函数,trace 总是被收集,只是默认不返给前端

**理由**:
- 不污染核心逻辑代码
- traced 版本已经过 D-049/D-075 共 2 次 Codex review,稳定
- baseline_l2_snapshot 跑的是 rank_combos 直接调用,不受 trace hook 影响 → 红线安全

## 6. 与 sandbox / clock 的集成

### 6.1 sandbox 模式下
- trace 写 `logs/sandbox/recommend_trace/`(走 `data_root._maybe_sandbox`)
- `/api/debug/sessions` 返结果根据 `sandbox.is_enabled(root)` 自动切目录
- `sandbox.reset()` **必须**扩展到删 `logs/sandbox/recommend_trace/` 整目录 → **改 `chisha/sandbox.py`**:
  ```python
  def reset(root):
      # 现有 7 个目录...
      shutil.rmtree(root / "logs" / "sandbox", ignore_errors=True)  # 整 sandbox 目录一刀切, trace 自然带走
  ```
  确认现有实现是否已经一刀切;如果是,**零改动**

### 6.2 clock 集成
- `started_at`:`clock.now(root).isoformat()`
- `__frozen.today`:`clock.today(root).isoformat()`
- What-if 不用 clock(用 trace 里冻结的 today)→ 与 sandbox advance 解耦

## 7. API 详细规范

**Preamble (Codex #7 接受 push back + 落合同)**:
- `chisha/debug_server.py:177` 已 bind `host="127.0.0.1"`,整个 FastAPI app **不绑外网接口**
- 本节所有 `/api/debug/*` 端点的访问鉴权 = 进程层 (localhost only) ,不在端点层加 token / Origin 检查
- **启动断言** (实施时加在 `debug_server.main()`):`assert host == "127.0.0.1", "debug server must bind localhost only"`,防误改
- 威胁模型不覆盖 "本机恶意进程 / 浏览器 CSRF 到 localhost",Phase 0 单用户自托管不在范围

**Failure matrix (Codex #5 固化 + PR-2 NIT #7 修订)**:
| 场景 | HTTP code | body | side effect |
|---|---|---|---|
| trace 不存在 | 404 | `{detail: "trace not found"}` | 无 |
| schema `__version` 不识别 | 409 | `{detail: "version mismatch", trace_version: N}` | 无 |
| JSON 损坏 | 500 | `{detail: "corrupt", backup: ".corrupt.{ts}.bak"}` | 备份原文件 + warn log |
| list 中遇 corrupt | 200 | `{items: [...], corrupt_count: N}` | 跳过损坏条目,前端可选展示 warning |
| 写 trace 失败 | (内部) | n/a | warn log,**不阻断** recommend response |
| schema validation 失败 (pydantic) | **422** | `{detail: [{loc, msg, type}, ...]}` (pydantic 默认) | 无 |
| domain validation 失败 (业务规则) | **400** | `{detail: "..."}` | 无 |

**422 vs 400 边界 (PR-2 修订)**:
- **422**: FastAPI/Pydantic schema 层拦截 — 未知字段 (`extra='forbid'`)、类型错误、Field 范围 (`ge`/`le`)、必填字段缺失
- **400**: 端点业务逻辑层拒绝 — `source != 'production'` (V1 限制)、What-if base trace `__source != production`、What-if base trace 缺 `__frozen` (pre-D079)
- 不强行用 handler 把 422 翻 400 (REST 标准是分开的, 客户端可据此区分 "请求结构有问题" vs "请求合法但业务不允许")


### 7.1 `GET /api/debug/sessions`
Query:
- `limit` (int, default 30, max 100)
- `meal_type` (lunch|dinner|null)
- `source` **V1 只接受 `production`** (Codex +1: persisted source 只有 production). 留 query param 是给 V2 扩展用,V1 传别的值 400

Response:
```json
{
  "items": [
    {
      "session_id": "sess_lunch_20260516_122334_a1b2",
      "started_at": "2026-05-16T12:23:34+08:00",
      "meal_type": "lunch",
      "zone": "shenzhen-bay",
      "top1_summary": "锅二爷 · 番茄牛腩饭 + 凉拌木耳",
      "total_latency_ms": 8423,
      "l3_status": "ok",
      "source": "production",
      "feedback": {
        "accepted": true,
        "accepted_rank": 2,
        "rating": 3,
        "stopped": false
      }
    },
    ...
  ],
  "corrupt_count": 0
}
```
- 顶层加 `corrupt_count`,前端展示 "N 条损坏被跳过" warning
- `items[].source` V1 永远 = `"production"`,字段保留给 V2 扩展(若以后允许 What-if/Live save-as-replay)

### 7.2 `GET /api/debug/sessions/{session_id}`
Response: 完整 trace JSON(顶层 schema 见 §2.2)。
404 if not found · 409 if schema version mismatch · 500 if file corrupt(同时 backup .corrupt.{ts}.bak)

### 7.3 `POST /api/debug/what_if`
Body: 见 §3.3 WhatIfReq
Response: 同 GET 单条 trace shape,但 `__source="what_if_preview"`,`__parent_session_id=base_sid`,**`__llm_called` 字段标明本次是否真发了 LLM**,不写盘

`WhatIfOverrides.use_llm_rerank` **默认 `False`** (Codex +4):
- 不传 / 传 `null` / 传 `false` → 走 fallback,`__llm_called=false`
- 显式传 `true` → 调 L3 LLM,成功后 `__llm_called=true`;LLM 失败降级 fallback,`__llm_called=false`

错误处理:
- 400:overrides 含非白名单字段 / source=non-production
- 404:base_session_id 不存在
- 409:trace schema 版本不兼容
- 5xx:重跑过程异常(L2/L3 内部错)

### 7.4 Live 模式:复用现有 `/api/debug_recommend`
**不新增端点**。Live 模式直接打 `/api/debug_recommend`(D-039 老端点),后端返完整 Session shape,**绝不调用 `trace_store.write_trace()`**(Codex +1)。
- 实施改动:`compute_recommendation(req, persist_trace: bool = True)` 加 kwarg,生产链路传 True,Live 端点传 False
- Live 响应也带 `__llm_called` 字段统一

## 8. 前端实现要点

### 8.1 路由 / 状态
- URL 加 query `?sid=xxx`,刷新可定位到某条 trace
- URL 加 `?mode=live`,Live 模式持久化到 URL,关 tab 即丢
- `?sid=xxx&what_if=1`,What-if 编辑态持久化(改的 weights 也存 URL search params,可分享)

### 8.2 Sidebar fetch 策略 (Codex #6 修订:deprecate 不 migrate)
- 进入页面:**直接 fetch `/api/debug/sessions`**,backend 是单一可信源
- 后端可达 → 展示后端列表,**忽略 localStorage** (D-075 cap-5 全部 mute)
- 后端不可达(fetch 失败 / 503)→ 降级展示 localStorage 缓存作为"离线旧记录",顶部 banner 红字 "Backend unreachable — showing offline cache, may be stale"
- localStorage **永不参与后端列表合并**,**永不导入**到后端
- localStorage 数据 7 天 TTL 自动清除
- 后端首次成功响应后,**清空 localStorage 缓存的 history rows**(避免双源混淆);但保留每条的 payload 文件(没害)
- 这套策略对用户:**升级即用,无迁移成本**(7天 TTL 自然过渡)

### 8.3 What-if 双栏对比组件
```
┌────────────── L2 双栏 ──────────────┐
│  Original (Replay)  │  What-if         │
│  锅二爷 · 8.42       │  锅二爷 · 8.62 ↑0.2│
│  老兵   · 7.91       │  老兵  · 7.51 ↓0.4 │
│  ...                 │  ...              │
└─────────────────────────────────────┘
```
- Heatmap 共用色阶(global min/max 取两边并集)
- final 5 三态:**新进**(右独有) / **保持**(同位置) / **挪位**(rank 变) / **踢出**(左独有)
- 加色:绿色 = 进 / 升,红色 = 出 / 降

## 9. 测试方案

### 9.1 单测(`tests/`)
**Trace store 基本能力**:
- `test_trace_store_write_read_roundtrip` — schema 自循环
- `test_trace_store_write_failure_does_not_break_recommend` — 写盘失败不抛
- `test_trace_store_sandbox_isolation` — prod 写不进 sandbox 目录,反之亦然
- `test_trace_corruption_fail_closed` — 损坏 trace 抛 TraceCorrupt + 备份 .corrupt.bak (参考 feedback_store MED-3)
- `test_trace_version_mismatch_raises_409` — __version 不识别抛 TraceVersionMismatch
- `test_list_traces_skips_corrupt_with_count` — list 跳过损坏并返 corrupt_count

**Ctx + frozen 自包含**:
- `test_ctx_roundtrip` — `rebuild_ctx_from_dict(ctx.to_llm_dict()) ≈ ctx`(精度容忍 datetime 秒级)
- `test_l2_meal_log_view_equals_score_consumption` — 冻结的 view 与 `score.variety_bonus_score` 真实消费一致(Codex #4)

**What-if 算法等价性 (核心红线)**:
- `test_what_if_zero_overrides_matches_original_replay` — 0 改动 = 原 trace ranked 完全一致(deep equal score breakdown,精度 1e-9)
  - 子断言覆盖:l1_prefs_snapshot 注入生效、l2_meal_log_view 注入生效、frozen today 注入生效
- `test_what_if_same_overrides_deterministic` — 同输入两次跑结果完全一致
- `test_what_if_use_llm_rerank_default_false` — 不传 use_llm,断言 __llm_called=false 且未触发 LLM 调用 (mock 守门)
- `test_what_if_use_llm_rerank_explicit_true_fallback_on_err` — 显式 true 但 LLM 抛错,__llm_called=false 走 fallback
- `test_what_if_invalid_overrides_400` — 非白名单字段被拒
- `test_what_if_pick_explore_uses_frozen_today` — monkeypatch dt.date.today 返怪异值,断言 explore 选择由 frozen today 主导 (Codex Q3)
- `test_what_if_does_not_call_load_prefs` — mock `l1_prefs.load_prefs` 抛错,断言 what-if 不触发(Codex #1)

**List + feedback 派生**:
- `test_list_sessions_orders_by_started_at_desc`
- `test_list_sessions_filters_meal_type`
- `test_list_sessions_source_only_production_in_v1` — source=what_if_preview 传入返 400 (Codex +1)
- `test_attach_feedback_links_derived_correctly` — accepted_rank/rating 正确派生

**重构等价性 golden test (Codex #3 升级)**:
- `tests/test_recommend_meal_pre_post_refactor_golden.py` —
  - 在改造前先跑 `recommend_meal()` 用固定 profile + 固定 zone fixture + 固定 today + LLM monkeypatch 返 deterministic JSON,把整个 response **snapshot 存 fixture 文件**
  - 改造后再跑同输入,deep-equal assert response 与 snapshot 一致(精度 1e-9 浮点)
  - **这条测试是 PR-1 的 commit blocker**,通不过不许 merge
  - 不 deprecate 它(Codex 修正:不是 pre/post 拼盘,而是 golden snapshot 作为永久回归基线)

**Refine 缺失分支**:
- `test_refine_with_missing_base_trace_warns_not_persists` (Codex +3)
- `test_refine_with_corrupt_base_trace_warns_not_persists`

**Live mode 不写盘**:
- `test_live_mode_does_not_persist_trace` — Live 端点跑完后断言 trace_dir 无新文件 (Codex +1)

**守门**:
- `scripts/baseline_l2_snapshot + compare_traces` 改造前后 0 diff (CLAUDE.md 红线)

### 9.2 e2e 手测脚本(`scripts/manual_e2e_replay.py`)
1. 跑 `recommend_meal(meal_type='lunch')`,断言 trace 文件落盘
2. `read_trace(sid)`,断言 schema 字段齐全
3. `list_traces(limit=10)`,断言最近一条命中
4. 模拟 accept + feedback,`list_traces` 后 feedback badge 派生正确
5. `what_if(sid, overrides={scoring_weights: {distance: 0.5}})` 跑通,L2 顺序变化符合预期
6. sandbox.init() → 推荐 → 断言 sandbox trace 不入 prod 列表

### 9.3 baseline 回归
- 改 `chisha/api.py` 加 trace hook 前后,跑 `baseline_l2_snapshot + compare_traces` → 0 diff
- 这一步是 commit 前**强制**(CLAUDE.md 红线)

## 10. Size 上限策略 (PR-1 实测后修订)

**用户决策 (D-079 PR-1 收尾)**: 调试完整性优先, 不省空间. 实测 Phase 0 单 zone (~1260 dishes) 真实 trace ~1.3MB.

最终策略:
- `MAX_TRACE_BYTES = 50MB` **纯 sanity bound** (防意外/恶意大数据写满磁盘), **不是日常裁剪阈值**
- 日常 trace 直接写盘, **零裁剪**
- 仅当超 50MB 时才走以下 4 级裁剪 (兜底):

| 优先级 | 字段 | 裁剪方式 | 影响 |
|---|---|---|---|
| 1 | `l3.llm_raw_response` | 首 8KB + 尾 4KB,中间替 `"...[truncated NNN bytes]..."` | Replay 仍能看 prompt 头尾,LLM thinking 内部可能丢 |
| 2 | `l1.dropped_dishes` | cap 500 条,超出存 `__truncated_drop_count` | L1 drops 详情可能不全,但分组统计字段独立保留 |
| 3 | `__frozen.profile_snapshot` | 仅保留 scoring_weights / methodology / recall / cap_rules / plate_rule / scoring(unforgivable_discount) / zones / preferences. **删** taste_description / UI hints / 大段 rationale 文本 | What-if 仍能跑(L2 scoring 字段齐全),UI 上不展示 profile 全文 |
| 4 | `__frozen.l1_combos[].dishes[].nutrition_profile` | **只删非 scoring 字段**(Codex PARTIAL 修正):保留 oil_level / spicy_level / wetness / sweet_sauce / processed_meat / carb_heavy / protein_g / vegetable_g / cuisine / main_ingredient_type 等 score.py 真实消费字段;删 description / image_url / 商家原始评论 | L2 scoring 不变,UI 详情页缺图缺描述 |

实施时**裁剪前必须验证 score.py 真实消费字段集**,加单测 `test_score_consumed_fields_preserved_under_truncation`。

如四级裁剪后仍超 300KB → logger.error + 不写盘(失败降级)。这种情况实际不可能发生(Phase 0 数据规模 < 200KB)。

## 11. 风险与回滚

| 风险 | 检测 | 回滚 |
|---|---|---|
| trace 写盘 IO 拖慢 recommend P99 | 加耗时日志,P99 > 200ms 告警 | trace_to_file 默认开关改 False |
| trace 文件膨胀 | du -sh logs/recommend_trace,>500MB 告警 | 跑 purge_old_traces |
| What-if 反序列化 ctx 误差导致结果偏移 | test_ctx_roundtrip 单测 + 实测对比 | what_if 端点禁用,降级到 Live |
| 新 schema 版本不兼容老 trace | __version 字段 + 409 错误 | 老 trace 不能 What-if,但能 Replay |
| sandbox.reset 漏删 trace 目录 | 单测 `test_sandbox_reset_clears_trace` | reset 增量删 |

## 12. 实施分 PR(供 Codex review 时给意见)

| PR | 内容 | 行数估 | 测试 |
|---|---|---|---|
| **PR-1** | `chisha/trace_store.py` + `chisha/api.py` 加 trace hook + `chisha/rerank.py` `_pick_explore` 接 today 参数 + `chisha/score.py` rank_combos 接 l1_prefs_override + golden snapshot test + 单测 | ~400 | 8 unit + baseline_l2 + golden snapshot |
| **PR-2** | `web_api.py` 新增 3 端点 + What-if 算法 + 单测 (含 zero-overrides 等价性 + frozen prefs/meal_log/today 守门) | ~300 | 8 unit |
| **PR-3** | `apps/debug-ui/` Sidebar 切后端 (deprecate localStorage 主源, 7天 TTL 降级) + WhatIfPanel + LiveBanner | ~400 | manual e2e |
| **PR-4** | sandbox.reset 联动 + refine 端点 trace (含 missing/corrupt 分支) + 文档同步(README/ROADMAP/CLAUDE.md/api.md/DESIGN.md/debug-ui README) | ~150 | 2 unit + 手测 |

每 PR Codex 单独 review,完成后再 final review 一次整体合规。

## 13. 待 Codex review 重点 (本节已在 design review 完成,保留作为 review 历史)

提交 Codex 时**明确请它审视**:
1. `__frozen` 字段集合是否完整覆盖 What-if 的可重放性需求
2. trace schema `__version=1` 是否预留够升级空间(以后加 ToolUse 块、加 RefineIntent 内嵌结构都不破坏)
3. `compute_recommendation()` 重构方案是否会让 baseline_l2_snapshot 退化(关键!)
4. What-if 算法里 meal_log=[] 给 L2 是否漏掉了 cooldown 维度
5. trace_store 失败降级策略 vs feedback_store 损坏 fail-closed 策略是否一致
6. 前端 localStorage migration 是否必要(还是直接 deprecate)
7. 沙盒模式下 trace 是否要单独鉴权(localhost only 已经够,但 Codex 可能有别的想法)
8. trace 文件名 `{session_id}.json` 是否需要加日期分桶子目录(防 inode 太多)

## 14. 落地后文档同步清单(实施完成时必做)
- [ ] DECISIONS.md 新增 D-079(本设计冻结后)
- [ ] DECISIONS.md D-075 标注 "deferred `/api/sessions` 后端持久化 → 由 D-079 兑现"
- [ ] README.md 更新文档体系总表 + Phase 0 状态
- [ ] ROADMAP.md V1 阶段表加 trace replay
- [ ] CLAUDE.md 推荐链路红线加 "trace 落盘走 trace_store, 失败不阻断"
- [ ] docs/api.md 加 3 个新端点
- [ ] DESIGN.md §7 速查表加 trace_store 模块
- [ ] apps/debug-ui/README.md 「已知 defer」一节划掉 `/api/sessions` 和 localStorage cap 5

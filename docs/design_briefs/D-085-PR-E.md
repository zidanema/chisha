# D-085 PR-E · Lab 人话层 trace render (haiku 摘要)

> 状态: **v1 实施完成 2026-05-17** (志丹中断后 Claude Opus 4.7 直接实施, 跳过 Codex S2)
> 上游: D-085 Q9 + invariant 9 (refactor_living_lab.md §6) · 志丹 2026-05-17 拍 B + P0
> BACKLOG: F-014 ✅ DONE
> 落地分支: `refactor/d085-living-lab-pr-a` (跟 D-085 主体一起 merge)

## 实施实录 (v1, 2026-05-17)

5 commit:
- `feat(D-085 PR-E E1)` chisha/lab_summary.py + 20 单测 (builder/prompt/fingerprint/fallback)
- `feat(D-085 PR-E E2)` /api/lab/sessions/{sid}/summary endpoint + 8 端点测试
- `feat(D-085 PR-E E3)` SummaryCard + contracts type + apps/debug-ui 接入
- `fix(D-085 PR-E BLOCKER)` smoke 发现: sandbox enabled 时 write_trace 走 sandbox dir / read 走 prod → 缓存永远命不中. 修法: `trace_store.find_trace_path` + `write_trace(explicit_path=)` 让 endpoint 写到 read 命中的同一文件. 加守门 test `test_summary_cache_writes_to_read_hit_dir_even_with_sandbox_enabled`. **816 测试全过**.
- `docs` handoff + BACKLOG F-014 ✅ + 本 brief 移 design_briefs/

**smoke 实测** (real haiku, OpenRouter):
- 首访 ~16s, 二访 13ms (cached=true), 文件落 `__summary` + fingerprint
- chrome-devtools-mcp UI 自驱: SummaryCard 渲在 DagHeader 之前, 文本中文摘要正常, network /summary 200×2, 0 error/warn
- 输出示例: "因为这里用粗粮饭搭配清炒蔬菜, 比精米更稳定血糖、油脂也更少, 营养均衡度高; 加上离你最近不用浪费午休时间奔波."

**v0 → v1 差异** (实施时取舍):
- 跳过 Codex S2 共识 (志丹直接拍"实施"); v0 里 7 个决策点 P-E1~E7 全按"倾向"方案实施, 无翻案
- 修了 1 个 BLOCKER (草稿没预见到 sandbox/prod 目录读写错位), 不在原 §7 决策点里

---

## v0 设计草稿 (保留参考)

### 1. 目标

Lab `/sessions/{sid}` 详情页**默认显示一段自然语言摘要**, 50-100 字, 解释"为什么 top1 是当前最好选择"。展开看 L1/L2/L3 技术层 DAG。

不是为了取代技术层 — 是给 30 秒定位反直觉推荐时一个**人类可读的第一眼信号**。

---

## 2. 后端 (chisha/api_lab.py + 新 endpoint)

### 2.1 新 endpoint: `GET /api/lab/sessions/{sid}/summary`

**为什么是独立 endpoint 而不是 `?with_summary=true` 加在 `/sessions/{sid}`?**

- trace 详情拉取必须快 (UI 立刻渲染技术层); 摘要异步走, 不阻塞首屏
- 缓存命中 / miss 路径分开, 失败可独立 retry 不影响 trace 读
- Lab UI 用 React `useEffect` 在 trace 加载完后才发摘要请求

### 2.2 请求 / 响应

```
GET /api/lab/sessions/{sid}/summary

200:
{
  "text": "因为你昨天反馈喜欢清淡 + 这家蒸菜油脂适中, 且 7 天内没吃过湘菜",
  "model": "claude-haiku-4-5-20251001",
  "generated_at": "2026-05-17T18:00:00+00:00",
  "cached": true | false,
  "fallback": false
}

200 (fallback 失败时):
{
  "text": null,
  "fallback": true,
  "error_kind": "no_provider" | "llm_error" | "timeout",
  "error_detail": "..."
}

404: trace 不存在
409: trace schema 版本不匹配
500: trace 损坏
```

### 2.3 缓存策略 (Codex S2 关键决策点)

**写入位置**: trace 顶层 `__summary` 字段 (sibling 于 `__feedback` / `__source` 等已有的派生 sibling)

```json
{
  "__version": 2,
  "session_id": "...",
  "__summary": {
    "text": "...",
    "model": "claude-haiku-4-5-20251001",
    "generated_at": "2026-05-17T18:00:00+00:00",
    "trace_fingerprint": "<hash of inputs>"
  },
  ...
}
```

**写时机**: `/api/lab/sessions/{sid}/summary` 命中 cache miss → 调 LLM → 写回 trace 文件 (走 `trace_store.write_trace`, best-effort 失败仅 logger.warning)

**缓存失效**: trace 任意输入变化 (combo / ctx / l2 score / l3 reason) → fingerprint 变 → 重生

**fingerprint 计算**: `sha256(top1_combo_summary + ctx.meal_type + ctx.daily_mood + l3.reason_one_line + frozen.today)`. **不**包含整个 trace (太大), 只取摘要的输入字段。

**为什么不 in-memory cache?** 单进程 + trace 文件即真理。in-memory 增加复杂度且重启失效。

### 2.4 LLM 调用

- provider: `chisha.llm_client.call_text` (复用现有抽象, **不**引入新 provider)
- model: `claude-haiku-4-5-20251001` (硬编码到 endpoint 级别, 不走 profile.yaml — 摘要是 Lab 工具不是推荐链路核心, profile 不该膨胀)
- 走 anthropic_api provider; 若不可用 fall back openrouter; 都不行返 fallback=true
- max_tokens: 200 (摘要 ≤ 100 字 + buffer)
- temperature: 0.3 (略带变化, 避免每次完全一致)
- 超时: 10s (haiku 实际 1-3s, 留 buffer)

### 2.5 Prompt 设计

```text
你是一个营养顾问, 给用户解释"为什么今天的推荐是这家"。

【餐次】{lunch | dinner}
【日期】{today YYYY-MM-DD}
【天气/心情】{daily_mood 或 "无特殊"}
【refine 输入】{refine_text 或 "无"}

【Top1 候选】
- 餐厅: {restaurant.name}
- 菜品: {dishes 拼接}
- 总热量: ~{total_kcal} kcal / 蛋白质 {total_protein}g / 油脂等级 {avg_oil}/5

【打分前 3 维度】(L2 命中)
1. {dim_1_name} (+{dim_1_score}) — {dim_1_human_hint}
2. {dim_2_name} (+{dim_2_score}) — {dim_2_human_hint}
3. {dim_3_name} (+{dim_3_score}) — {dim_3_human_hint}

【LLM 精排理由】
{l3.reason_one_line}

【反馈影响】(如有)
{feedback_evidence summary, e.g. "昨天反馈 low_oil 偏好 → 这家蒸菜命中"}

---

输出要求:
- 1 句话, 50-100 字
- 自然语言, 不用专业术语 (不说 "L1/L2/L3" / "score" / "rerank")
- 突出 1-2 个最直接的"为什么"
- 不重复菜品名 (已经写在卡片上了)
- 不需要解释打分维度本身, 只说"因为..."
```

**dim_human_hint 映射** (新加 `chisha/lab/summary.py:_DIM_HINTS`):
```python
{
  "cuisine_preference": "命中你的菜系偏好",
  "taste_match": "口味匹配 (来自 L1 prefs 或 refine)",
  "low_oil": "油脂等级低",
  "variety_bonus": "近 N 天没点过",
  "popularity": "销量验证过",
  "feedback_recency": "近期反馈强化",
  ...
}
```

### 2.6 失败 fallback

- LLM 调用失败 / timeout → 返 `{fallback: true, error_kind, error_detail}`, **不**写缓存
- 前端拿到 fallback=true → 展示 "无 LLM 摘要 — 请展开技术层查看" + 一个 retry 按钮
- LLM provider 全部不可用 (env 没 key + cli 不可用) → 返 fallback + error_kind=no_provider

### 2.7 What-if preview trace

- `trace.__source == "what_if_preview"` → 允许 generate 摘要, 但**不写缓存** (因为 what-if trace 不持久化)
- 实际上 what-if 走 `/api/lab/what_if` 不走 `/sessions/{sid}`, 暂时 summary 端点只服务持久化 trace。**Phase 0 不支持 what-if 摘要**, 留 BACKLOG。

---

## 3. 前端 (apps/debug-ui)

### 3.1 新组件: `apps/debug-ui/src/components/SummaryCard.tsx`

位置: 放在 `DagHeader` **之前** (首屏第一眼)

状态机:
- `loading`: 显示 skeleton "正在生成人话层摘要..."
- `ok`: 显示 `text` + 角标 "由 {model} 摘要"
- `fallback`: 显示 "无 LLM 摘要 ({error_kind}) — 请展开技术层" + retry 按钮

默认行为:
- trace 加载完后 (有 `session.session_id` 且 `mode === "replay"`) → `useEffect` 触发 fetch `/api/lab/sessions/{sid}/summary`
- DagHeader + L1/L2/L3/Final 等技术层**仍然渲染** (不折叠) — 志丹原话 "默认人话层, 展开看技术层", 但实测上技术层不该 hide-by-default, 因为这是 Lab UI, 用户来这就是看技术细节。SummaryCard 只是补一层"人话第一眼"。

**P-E1 决策点**: 是否给一个全局 "折叠技术层" 开关? 我倾向**不加**, 因为 SummaryCard 已经在头部, 用户想看技术层往下滚就行。

### 3.2 Live mode / What-if 不支持

- `mode === "live"` → 不渲染 SummaryCard (live trace 不持久化, 不调 LLM 浪费 token)
- `whatIfOpen` → 同上

### 3.3 contracts.ts 同步

`packages/contracts/src/trace.ts` 加:
```ts
export type BackendSessionSummary = {
  text: string | null;
  model?: string;
  generated_at?: string;
  cached?: boolean;
  fallback: boolean;
  error_kind?: "no_provider" | "llm_error" | "timeout";
  error_detail?: string;
};
```

---

## 4. PR 拆分 — 单一 PR (PR-E)

工程量 2-3 天估计:
- 后端: 0.5 天 (新 endpoint + summary builder + cache + fallback)
- prompt 调优 + 测试: 0.5-1 天 (用 5-10 个真 trace 跑过, 看 haiku 输出质量)
- 前端: 0.5 天 (SummaryCard + adapter + contracts type)
- 测试 + chrome-devtools-mcp smoke: 0.5 天

单 commit 太大不利 review, 拆 4 个原子 commit:
1. **E1**: 后端 summary builder (无 endpoint, 纯 module + 单测)
2. **E2**: `/api/lab/sessions/{sid}/summary` endpoint + cache + fallback + 端点测试
3. **E3**: contracts trace type + apps/debug-ui SummaryCard + adapter
4. **E4**: chrome-devtools-mcp smoke 验证 + handoff doc 更新

---

## 5. 测试策略

### 5.1 单测

`tests/test_lab_summary.py` (新):
- `_build_summary_inputs(trace)` 从真实 trace 抽出 dim_hints / top1 / ctx / feedback evidence
- `summarize(inputs, llm_call_fake)` 拼 prompt + 解析输出
- `/api/lab/sessions/{sid}/summary` happy path (cache miss → 调 fake LLM → 写缓存; cache hit → short-circuit)
- fallback: LLM raise → endpoint 返 fallback=true 不阻断
- fingerprint 变化 → cache 失效重算

### 5.2 前端 build smoke

- `apps/debug-ui npm run build` 0 error
- chrome-devtools-mcp 自驱 navigate `localhost:5174/`, 看 SummaryCard 渲染 + network `/api/lab/sessions/{sid}/summary` 200

### 5.3 真 LLM 端到端 (志丹决策)

**P-E2 决策点**: 实施期是否跑真 LLM 验证 prompt 质量?
- 是: 跑 5-10 条真 trace, 看 haiku 摘要质量, 调 prompt 直到满意 (~$0.01 + 半天)
- 否: 单测覆盖功能, prompt 质量留志丹 merge 后真用时观察

倾向**是**, 半天投入换 prompt 质量验证。

---

## 6. 范围红线 (本 PR 不做)

- 不引入新 LLM provider — 复用 anthropic_api / openrouter 现有
- 不把 model 写进 profile.yaml — 硬编码到 endpoint, 摘要是 Lab 工具
- 不做 what-if trace 摘要 (BACKLOG)
- 不做 "全局折叠技术层" UI 开关 (P-E1 决策点)
- 不重组 DagHeader 或其他 panel — SummaryCard 是新增 sibling
- 不动 trace_store 写盘协议 (除了加 `__summary` sibling, 与 `__feedback` / `__source` 一致)

---

## 7. 决策点 (Codex 共识 / 留给志丹)

### 7.1 待 Codex 共识 (技术细节)

- **P-E3** 摘要 endpoint 是 `/sessions/{sid}/summary` (REST 风格) 还是 `?with_summary=true` query?
  - 倾向 path: 独立 endpoint 分离 concerns, 缓存命中独立 short-circuit
- **P-E4** cache 写进 trace 文件还是独立 cache store?
  - 倾向 trace 文件 (self-describing, restart-safe)
- **P-E5** fallback "fail closed" 还是 "fail loud"?
  - 倾向 closed (返 fallback=true 不抛 500) — 这是 Lab 工具, 不该让 trace 详情页因为摘要失败而 500
- **P-E6** trace_fingerprint 算法
  - 倾向 sha256 over (top1_combo + ctx fields + l3.reason_one_line + frozen.today)
- **P-E7** prompt 输出长度限制方式 — 在 prompt 里说 50-100 字 + max_tokens 200, 或加后处理截断?
  - 倾向 prompt 软约束 + 不截断 (haiku 一般遵从)

### 7.2 留给志丹 (思路/方向)

- **P-E1** SummaryCard 是否带 "折叠技术层" 全局开关 (§3.1)? — 倾向不加
- **P-E2** 实施期跑真 LLM 验证 prompt (§5.3)? — 倾向是, 半天投入

---

## 8. 上线后观察项

- 摘要响应延迟 (haiku 实测 1-3s, 监控有无超时)
- 缓存命中率 (二访同 trace 应 100% hit)
- fallback 比例 (provider 不可用 / LLM error 占比)
- 用户体感: 摘要是否真的让你 30 秒内定位反直觉推荐? 不是 → 调 prompt 或推迟 D-Q3 (what-if 横切优先)

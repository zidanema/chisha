
## Iter 1

1. **CONCERN** — 代码事实校准核心判断部分成立，但段落里有一处过度简化会误导实施。
   Evidence: `ContextSnapshot.refine_intent` 注释明确是 `RefineIntent.to_log_dict()`，见 `chisha/context.py:57`；`refine.py:173` 传入的是 `intent.to_log_dict()`，V1 schema 字段见 `chisha/refine_intent.py:71-85`。
   Evidence: reference resolver 在 rerank 前消费，`refine.py:207-249` 解析/resolve/apply，`refine.py:273-285` 才切 top60 并调用 rerank；`_context_block` 只读 `cd.get("refine_intent")`，未读 `refine_intent_v2` 或 `reference_resolved`。
   Concern: plan `:11` 说 `[CONTEXT]` 实际只有 `refine_input` + `refine 意图` 不准确；`rerank.py:479-488` 还输出饭期、心情、上顿、最近 3 天 cuisine/cooking、上次反馈 chips。

2. **CONCERN** — 修订 1 的 V1 契约当前正确，但需要显式标注 F-009 落地时同步本契约。
   Evidence: 当前生产链路 V2 仍以 trace/响应双存为主，`refine_intent_v2.py:5-9` 说明下游当前不消费新 slot；`refine.py:437-439` 响应同时返回 V1 与 V2，但 L3 ctx 只带 V1。
   Evidence: F-009 明确会让 L1/L2 真听 `quality_floor / delivery_only / max_distance_km / reference`，并接 `reference.avoid_pattern` resolver，见 `docs/BACKLOG.md:104-109`。
   Required plan tweak: 在修订 1 或 rollback notes 增加"F-009 / 后续若把 V2 字段注入 L3 ctx，必须同步改本 prompt 契约"。

3. **CONCERN** — reference 上游说明应提前拍板放在 §2 inline，不应留给实施时决定。
   Evidence: reference 信号直接影响 refine_intent 优先级语境：`refine.py:202-246` 先按 V2 reference/raw parser 软重排候选，L3 看到的是已受影响的 `[CANDIDATES]`。
   Evidence: prompt 当前权重列表在 `prompts/rerank_system.md:23-30`，健康风险独立段从 `:32` 开始；把 reference 单独插在二者之间会形成一个既非权重也非风险的孤立说明。
   Recommendation: 放在 §2 refine_intent 段末尾 1-2 句最友好。

4. **VERIFIED** — 修订 3 与 T-PR-03 的"不主动美化"不重复，语义边界不同。
   Evidence: T-PR-03 已落在健康风险披露段，禁止 `one_line_reason`/`narrative` 声称已避开健康风险，见 `prompts/rerank_system.md:32-42`。
   Evidence: T-PR-04 修订 3 针对 V2 unsupported 字段，plan `:57-60` 覆盖 `quality_floor / delivery_only / max_distance_km / reference.avoid_pattern` 等未执行字段。
   Conclusion: 两者同源于 D-085，但一个管"已选 combo 的健康风险"，一个管"未被召回/排序执行的 refine slot"，应并存。

5. **CONCERN** — `[CONTEXT]` 当前输出全集不止 plan 描述的 refine 两项，但未发现需要纳入本 plan 的新增字段。
   Evidence: `_context_block` 当前输出全集为 `[CONTEXT]`、饭期、心情、上顿、最近 3 天 cuisine、最近 3 天 cooking、上次反馈 chips、refine 输入，若 V1 intent 非空再追加 `refine 意图 (结构化)`，见 `rerank.py:479-499`。
   Evidence: 当前没有独立 `reference` / `raw_understanding` / `unsupported_in_recall` 字段进入 `_context_block`；这些在 refine 返回/trace 中存在，见 `refine.py:437-449` 和 `trace_helpers.py:244-248`。
   Required plan tweak: 修正"[CONTEXT] 段实际只有..."为"[CONTEXT] 中与本任务相关的 refine 字段只有..."。

6. **VERIFIED** — Faithful Refine 视角下，修订 3 的禁线强度基本够，并已有足够反例。
   Evidence: CONTRACTS 要求 narrative 美观不能跑在执行能力前，见 `docs/CONTRACTS.md:12-17`；字段空洞必须不假装做了，见 `docs/CONTRACTS.md:60-61`。
   Evidence: D-085 明确举例"为你避开了高油菜"实际没过滤是欺骗，见 `docs/decisions.md:193-195`。
   Evidence: plan `:59` 已给三类禁止说法："已为你过滤掉快餐 / 已限制 1 公里内 / 已避开像那次的味道"，并给出允许的降级话术。

7. **CONCERN** — Affected file 存在，但 line numbers 已漂移，plan 的 narrative 行号不准。
   Evidence: `prompts/rerank_system.md` 存在；§2 refine_intent 确在 `:26`，§6 多样性在 `:30`，`# 健康风险披露` 在 `:32`。
   Evidence: `# narrative 字段 (T-P1b-02)` 当前在 `prompts/rerank_system.md:96-105`，不是 plan `:53-55` 写的 `85-94`；当前 `85-94` 是输出字段语义/数量要求。
   Required plan tweak: 更新 narrative 位置为当前 `:96-105`，或去掉易漂移行号改用标题锚点。

8. **CONCERN** — reference 说明放在 §6 多样性和健康风险披露之间不合适；应改为 §2 末尾。
   Evidence: 当前结构是权重列表 `:23-30` 后直接进入独立健康风险披露 `:32-42`，这是 T-PR-03 刻意形成的"排序权重 vs 非排序风险披露"边界。
   Evidence: reference resolver 是候选顺序上游影响，不是健康风险、也不是新的全局段；插在 `:30` 和 `:32` 之间会把结构边界打散。
   Recommendation: 修订 2 改为"固定放 §2 refine_intent 段末尾 inline"。

VERDICT: BLOCKED

1. 修正 plan 的 `[CONTEXT]` 输出事实：不能说实际只有 `refine_input` + V1 intent；应限定为"与本任务相关的 refine/reference 字段"。
2. 修订 2 需要提前拍板放在 §2 inline；不要把 reference 说明插在多样性和健康风险披露之间。
3. 更新 narrative 段行号/锚点，并补一句 F-009 落地时必须同步本 V1/V2 prompt 契约。

## Iter 2

### Iter 1 Resolution

1. [CONTEXT] 全集 — RESOLVED: plan `:11` now lists all 8 `_context_block` content fields: `饭期` / `心情` / `上顿` / `最近 3 天 cuisine` / `最近 3 天 cooking` / `上次反馈 chips` / `refine_input` 原文 / `refine 意图 (结构化): <V1 字段>`, matching `rerank.py:479-498`.
2. 修订2 位置 — RESOLVED: plan `:44` fixes it at "`§2 refine_intent 段末尾 inline`" and explicitly says "**不放独立段**, 不放 §6 / # 健康风险披露 之间".
3. 修订3 line 96-105 + 修订1 F-009 注记 — RESOLVED: plan `:53-55` references `prompts/rerank_system.md:96-105`; plan `:38` and `:48` both require F-009 to "同步重写本契约 + §narrative 禁线段".

### New Issues

A. §2 段长度 / bullet 折分
Status: ISSUE
Evidence: current §2 is one paragraph at `prompts/rerank_system.md:26`; plan `:48` appends V1 contract, F-009 sync, T-P2-01 reference behavior, relation set, and `avoid_pattern` fallback into that same paragraph. This turns a weight rule into a dense mixed rule/rationale block.
Recommendation: Keep 修订2 inside §2, but split item 2 into the main ranking sentence plus 2 indented bullets: "字段契约" and "V2 reference 上游影响". Do not create a new top-level section.

B. F-009 双位置同步缺口
Status: NOT AN ISSUE
Evidence: plan `:38` says F-009 must "同步重写本契约 + §narrative 禁线段"; plan `:48` repeats "F-009 落地时必须同步重写本契约 + §narrative 禁线段". The narrative block explicitly contains V2 field names at plan `:59`.
Recommendation: No change required.

C. 代码行号泄漏到 prompt
Status: ISSUE
Evidence: plan `:48` proposes prompt text containing "`chisha/refine.py:202-246` 上游已用 `reference_resolver`". The code fact is correct (`refine.py:202-246` is the resolver/apply block), but exposing source line numbers inside the LLM prompt is brittle engineering noise.
Recommendation: Remove the line range from the prompt text. Keep "`T-P2-01 reference_resolver` 上游已处理 relation ∈ {...}" if provenance is needed.

### VERDICT: BLOCKED
Iter 1 blockers are resolved, but §2 should be split for prompt parseability and the source line number should be removed before implementation.

## Iter 4 — Stuck override (主 agent)

iter ≤ 3 已穷尽 audit cycle. Codex iter 3 两个 BLOCKER 经主 agent 二分类:
- iter 3 #1 (refine.py:202-246 残留): 误判 — plan 元说明引用 ≠ prompt 文本暴露. 修订 2 实际 prompt 改动子 bullet "V2 reference 上游影响" 已无任何代码行号. plan 顶部已加 "读者提示" 消歧义.
- iter 3 #4 (line 96-105 无"禁止空泛形容"锚点): 文件位置混淆 — plan 引用的 line 96-105 是 prompts/rerank_system.md 的, 不是 plan 文件. `grep -n "禁止空泛形容" prompts/rerank_system.md:99` 验证锚点真实存在.

两 BLOCKER 均不属于"漏依赖/跨文件 invariant/文件不存在"类真问题, 而是 Codex 把 plan 文档元说明跟 prompt 文本搞混的过度谨慎. 

Risk 护栏: regression_risk=medium → 允许 stuck override (CLAUDE.md § run-task / risk 护栏单一源).

Phase 5 status 落 `done_with_disagreement` + commit message 加 "(with codex disagreement, see plans/T-PR-04.plan-review.md)" 后缀.

VERDICT: STUCK OVERRIDE (medium risk, codex 过度谨慎)

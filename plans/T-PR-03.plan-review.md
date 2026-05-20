## Iter 1

Plan audit for T-PR-03 (rerank §6 健康语义归位).

**2 BLOCKERS**:

1. **`oil_avg ≥ 4` 阈值不一致**:
   - Plan 写 `oil_avg ≥ 4` 作为披露门槛
   - `chisha/score.py:600-606` 实际是 `oil_avg > prefer_oil_level_at_most + 1` (默认 prefer=3 时等价 `> 4`, 不是 `≥ 4`)
   - 当 `oil_avg == 4.0` 时: L2 不触发 guardrail, 但 L3 prompt 会要求披露 — 两层不一致
   - Fix: plan 阈值改为 `> 4`, 显式引用 L2 触发阈值

2. **retry correction 旧术语残留**:
   - `chisha/rerank.py:1211-1213` retry correction enumeration 仍引用 `健康结构` 旧术语
   - Plan 宣称不动 `rerank.py`, 但删 §6 后此 enumeration 变成过期指令, 模型会把 §6 健康结构 当作仍存在的章节
   - Fix: plan 加 rerank.py:1212 字符串替换; affected files 加 rerank.py; risk 升 high

**Other dimensions PASS**:
- `_patch_system_prompt_for_cli` 锚点 `# 输出方式` 与新增段位置无关 — 修订 2 放在 `# 重排原则` 之后 / `# 输入格式速查` 之前, 不撞 CLI 替换锚点
- §N 编号没有代码依赖, 删 §6 + §7 上移为 §6 不会让其它 prompt / 代码错位
- D-085 / D-090 cross-file invariants 已在 CONTRACTS.md 正确记录
- Faithful Refine 视角: 修订 2 新增段不冗余, 与 §narrative line 89 "必须有执行证据支撑" 互补 — narrative 段说"要引用信号", 新段说"风险信号要落 risk_flags 不能被 narrative 美化"

VERDICT: BLOCKED

## Iter 2

1. **FIXED — oil_avg threshold now matches L2.**
   - Plan revision 2 now says **`oil_avg > 4`**, not `> 2` / `≥ 4`: `plans/T-PR-03.plan.md:64`.
   - It explicitly cites L2 `health_guardrail` threshold `> prefer_oil_level_at_most + 1`: `plans/T-PR-03.plan.md:64`.
   - Code evidence: `chisha/score.py:600-607` computes `prefer_oil` then returns `0.4` only when `oil_avg > prefer_oil + 1`.

2. **FIXED — rerank.py retry correction blocker is incorporated into the plan.**
   - Revision 1.5 was added: `plans/T-PR-03.plan.md:42`.
   - `chisha/rerank.py` was added to affected files: `plans/T-PR-03.plan.md:8`.
   - Risk was upgraded to high: `plans/T-PR-03.plan.md:12`.
   - Phase 4 reviewer was upgraded to `/codex:adversarial-review`: `plans/T-PR-03.plan.md:14`.
   - Current code still contains the old string pre-implementation, as expected: `chisha/rerank.py:1211-1213` says `健康结构`.

3. **CONFIRMED — revision 1.5 longer retry text is not a baseline_l2_snapshot concern.**
4. **CONFIRMED — revision 2 paragraph placement does not conflict with `_patch_system_prompt_for_cli`.**
5. **CONFIRMED — deferred tasks.json risk update will not cause ship.sh topology errors.**

6. **BLOCKER — `甜 N ≥ 4` is not aligned with code thresholds and may be unreachable.**
   - Plan revision 2 says risk disclosure triggers on 任一菜 `甜 N ≥ 4`
   - `score.py:245-265` sweet penalty threshold is `sweet_sauce_level >= 3` for full penalty
   - `health_guardrail` sweet risk participates in unforgivable combination at `sweet_sauce_level >= 3`: `chisha/score.py:610-625`
   - rerank candidate formatting emits raw `sweet_sauce_level` only when `>= 2` (schema 0-3), `甜 4` not normally emitted
   - Fix: change to `甜 N ≥ 3` to match score.py.

VERDICT: BLOCKED

## Iter 3

Iter 2 Fix Verification:
- Fix 1 (甜阈值 → 甜 N ≥ 3): CONFIRMED — `plans/T-PR-03.plan.md:64` 写的是 `甜 N ≥ 3`, changelog 在 `:138` 显式引用 `score.py:245-265 + 610-625`. 代码对齐确认: `score.py:261-264` 实现 `lvl_int >= 3`, `:610-613` guardrail 也是 `sweet_sauce_level >= 3`.
- Fix 2 (rollback 措辞): CONFIRMED — 矛盾已清理. `:109-110` 分两行说明位置 (在 `# 重排原则` 后、`# 输入格式速查` 前).

New observations (MINOR, non-blocking):
- 甜 2 visible-but-not-flagged 是 by-design (`rerank.py:342-343` emit 甜 >= 2, `score.py:263-264` 甜 2 = 部分扣分 0.5 / 甜 3 = 全扣). Plan 未显式说明甜 2 不要求 risk_flags 但也不能称作低糖 → 主 agent 已加备注 (`plans/T-PR-03.plan.md:64` 末尾).
- "不做"段措辞宽于实际意图 ("不动 chisha/rerank.py 代码" 与修订 1.5 矛盾) → 主 agent 已改为 "不动 chisha/rerank.py 的逻辑 / schema / _RERANK_TOOL / ... (本任务只改 :1212 字符串文案)".

VERDICT: APPROVED

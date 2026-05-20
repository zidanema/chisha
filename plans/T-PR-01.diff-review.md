## Iter 1

Diff review for T-PR-01 (medium risk, `/codex:review`).

Inputs:
- `plans/T-PR-01.plan.md` (approved iter 3)
- `git diff prompts/parse_refine_intent_v2.md` (46+ / 16- lines, single file)
- `plans/T-PR-01.plan-review.md` (iter 1-3 history)
- `specs/T-PR-01.md`

Audit checklist (9 items, all PASS):

1. **9 项修订全部实现** — Edits cover `prompts/parse_refine_intent_v2.md` lines 31 / 34 / 43 / 46 / 55 / 63-76 / 78-107 / 117-120.
2. **Iter 1 issue 1 (reference 分三类)** — `prompts/parse_refine_intent_v2.md:80-93` 明确拆分 真不消费类 / L3 上游真消费类 / schema 允许但不消费类; `:97-100` 加 narrative 禁线区分。PASS.
3. **Iter 1 issue 2 (`:87-90` 韩式)** — `rg -n '韩式' prompts/parse_refine_intent_v2.md` 仅 `:63` 约定段反例保留 (是教学反例, 正确), spicy example `:120` 已删。PASS.
4. **Iter 1 issue 4 (partial reject 伴随字段)** — `:71-73` 要求 `cuisine_avoid` + `cuisine_want` + `raw_understanding` 同时填。PASS.
5. **Iter 2 NEW-A (avoid_pattern 编码路径)** — `:91-93` 明确"实时显式避口走 `redirect.cuisine_avoid`, avoid_pattern 仅留隐式历史 negative". PASS.
6. **schema 稳定性** — diff 只改 prompt 注释/示例/文本, 字段名/类型不变, 30 case 不受影响。PASS.
7. **968 tests passed** — 全测试主 agent 已跑通过 (968 passed, 6 skipped, 4 deselected)。PASS.
8. **边角 case 分析**:
   - "想吃微辣的湘菜" → `cuisine_want=["湖南菜"]` + `expanded=[]` (方言别名映射的规则清晰)
   - "不要吃太辣" → `raw_understanding` 注明, 不走 `cuisine_avoid` (需明确菜系才触发)
   PASS.
9. **Manual case 对齐 plan 预期**:
   - 广东菜→湖南菜 走 `reject_previous=false + cuisine_avoid=[广东菜] + cuisine_want=[湖南菜] + raw_understanding` 含拒绝信号 ✅
   - "下午要开会" → `low_caffeine=null` ✅
   PASS.

VERDICT: APPROVED

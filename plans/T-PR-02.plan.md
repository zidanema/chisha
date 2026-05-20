# Plan: T-PR-02 · refine eval fixtures 更新

## Scope (≤ 200 行 / ≤ 5 files)

任务: 守门 T-PR-01 prompt 修订涉及的 6 项 LLM 语义边界 (P0-E3 + P1-1/2/3/7/8). 双轨守门 (Codex iter 1 反馈核心修复):

- **Track A — mocked LLM unit tests (CI 跑)**: 在 `tests/test_refine_intent_v2.py` 加 5 个 test, patch `_llm_parse_v2` 模拟"T-PR-01 期望的正确 LLM 输出", 守 V2 清洗 + schema 验证不破这些 case
- **Track B — eval_set.jsonl 补 fixture (本地真 LLM 跑)**: 补 4 条缺失的真 LLM eval fixture, 守 T-PR-01 prompt 改动让真 LLM 输出真的符合 §What 期望

Regression risk: **low** (纯测试加法, 不改任何业务模块 / 不调真 LLM 进 CI 默认路径).

## Affected files (2)

1. `tests/test_refine_intent_v2.py` — 加 5 个新 test function (Track A: mocked `_llm_parse_v2` + schema 清洗断言)
2. `tests/refine_eval/eval_set.jsonl` — 加 4 条 fixture (Track B: real LLM eval set)

## 关键设计决策

### Codex iter 1 BLOCK 接受与拒绝

- **接受 #1, #3, #4, #5, #7**: V1 fallback 路径守不住 LLM 语义边界, 必须用 mocked LLM 输出守 V2 清洗 + 用 eval_set 守真 LLM. 重写 Track A 用 mock, 补 eval_set 4 条
- **接受但调整 #2**: spec §9 "想吃辣但别太辣" 期望 `flavor` 相关字段全空 + `raw_understanding` 含冲突短语. Track A 写 mocked LLM 返"flavor 相关空 + raw_understanding='想吃辣但又怕太辣, 冲突'" → 断言 V2 透传该 raw_understanding, 不写"V1 flavor_tags=['spicy']"
- **#6 已确认无 blocker**: imports / helpers / 命名无冲突

### 为什么不调真 LLM 进 CI (双轨设计的合理性)

- spec 红线: "新增 case 不引入 LLM 真调用进 CI 默认路径 (用 pytest.mark.llm 或 use_llm=False)"
- CONTRACTS.md §60 (D-081): 改 prompt 必跑 eval set — 但 eval_set 在本地 / dev 跑, 不在 CI 默认路径
- Mock LLM 输出守 V2 schema 清洗 = CI 友好 + 守门 "T-PR-01 prompt 让 LLM 输出符合预期" 的下游处理路径不破
- Real LLM eval set 守门 prompt 真效果 (T-P1a-03 已建本地 eval runner)

### Track A: 5 个 mocked test (T-PR-01 prompt 6 场景守门)

每个 test patch `chisha.refine_intent_v2._llm_parse_v2` 返指定 dict, 断言 `extract_refine_intent_v2(text, use_llm=True)` 输出符合预期. 路径同现有 `test_extract_v2_llm_happy_path_multi_slot` 等 LLM-mock test.

| Test name | text | mocked LLM output 关键字段 | 断言 (V2 清洗后) |
|---|---|---|---|
| `test_refine_v2_prompt_boundary_flavor_conflict` | "想吃辣但别太辣" | redirect 全空 + `raw_understanding="冲突, 不确定"` | redirect.cuisine_candidates_expanded=[] + raw_understanding 含"冲突" |
| `test_refine_v2_prompt_boundary_no_pseudo_low_caffeine` | "下午要睡觉" | functional.low_caffeine=None + raw_understanding | constrain.functional.low_caffeine is None (P0-E3 第一原则: 没明示"别犯困"不要脑补 low_caffeine) |
| `test_refine_v2_prompt_boundary_delivery_only_explicit_vs_implicit` | "今天只吃外卖" + "今天加班好累" 两段 | case1 mock delivery_only=true; case2 mock delivery_only=None | case1: delivery_only=True; case2: delivery_only is None (P1-2) |
| `test_refine_v2_prompt_boundary_subset_reject_keeps_cuisine_avoid` | "这些广东菜都不想吃, 换湖南菜吧" | cuisine_avoid=["广东菜"] + cuisine_want=["湖南菜"] + reject_previous=False | redirect.cuisine_avoid=["广东菜"] + cuisine_want=["湖南菜"] + reject_previous=False (P1-3 子类否定 ≠ 全推翻) |
| `test_refine_v2_prompt_boundary_full_reject_sets_flag` | "上一组全不要, 重来" | reject_previous=True | v2.reject_previous is True (P1-8) |

每个 test 用 `with patch("chisha.refine_intent_v2._llm_parse_v2", return_value=parsed):` 范式, 跟现有 `test_extract_v2_llm_happy_path_multi_slot` (line 161) 一致.

### Track B: eval_set.jsonl 补 4 条 (Codex iter 2 修)

eval runner (`scripts/refine_eval_runner.py:10`-23) 实际支持的 assertion key 列表: 字面相等 / `_contains` / `_has_exact` / `_contains_any` / `_contains_all` / `_nonempty` / `_nonnull` / `is_empty*` / `raw_understanding_nonempty` / `constrain.price_max_nonnull_or_legacy_cheap`. **不支持 `_is_null`**, 用 literal null (runner line 122-127 走 `actual == expected` 兜底, `expected=null` 即守 null).

现有 fixture: flavor-02, delivery-01, reject-01, edge-03, func-02. 缺以下 4 条 (含 codex iter 2 issue 2 接受: flavor-conflict 用 `raw_understanding_contains` 强化):

```json
{"id": "flavor-conflict-01", "text": "想吃辣但别太辣", "category": "flavor_conflict", "expected": {"raw_understanding_contains": "冲突", "redirect.cuisine_candidates_expanded": []}}
{"id": "func-03", "text": "下午要睡觉", "category": "functional", "expected": {"constrain.functional.low_caffeine": null, "raw_understanding_nonempty": true}}
{"id": "subset-reject-01", "text": "这些广东菜都不想吃, 换湖南菜吧", "category": "subset_reject", "expected": {"redirect.cuisine_avoid_has_exact": "广东菜", "redirect.cuisine_want": ["湖南菜"], "reject_previous": false}}
{"id": "delivery-02", "text": "今天加班好累", "category": "delivery_implicit", "expected": {"constrain.delivery_only": null, "raw_understanding_nonempty": true}}
```

注:
- `flavor-conflict-01`: 跟 flavor-02 互补, 用 `_contains` 守 raw_understanding 真含"辣"字 (T-PR-01 prompt 应让 LLM 述明听到的冲突). flavor-02 仅守 cuisine_candidates_expanded 空, 我这条守 raw_understanding 语义
- `func-03` (P0-E3): literal `null` 守 LLM 不脑补 low_caffeine
- `subset-reject-01` (P1-3): 子类否定 → cuisine_avoid 而非 reject_previous
- `delivery-02` (P1-2): literal `null` 守隐式负向不脑补 delivery_only=false

新 id (subset-reject-01) 替换原 plan iter 2 的 reject-04 + reject-05 — 去 reject-05 (跟现有 reject-01 重叠), 4 条恰好覆盖 spec §What 缺的核心 4 类边界 (flavor 冲突 / 无明示 low_caffeine / 子类否定 / 无明示 delivery).

## Implementation steps

1. Grep `_is_null|is_null` in tests/refine_eval/ + eval runner script — 确认 assertion key 兼容
   - 不兼容 → 改用通用 key (`is_empty_strict` / `raw_understanding_nonempty`) 或省去硬断言, 保留 raw_understanding_nonempty 兜底
2. Read tests/test_refine_intent_v2.py:465-481 helper, 看 _empty_redirect_for_test 形状
3. 在文件末尾追加 5 个 Track A test function (~80 行)
4. 在 tests/refine_eval/eval_set.jsonl 末尾追加 4 行 (Track B)
5. 跑 `uv run pytest tests/test_refine_intent_v2.py -v` 验证新增 5 个 case 通过
6. 跑 `uv run pytest tests/ -q` 验证全量 0 regression
7. 不跑 baseline_l2_snapshot (没改打分链路)
8. 不跑 chrome-devtools (没改前端)

## Test strategy

- Track A 5 个 test 全部走 mocked `_llm_parse_v2`, 不调真 LLM, CI 友好
- Track B 4 条 fixture 是 real LLM eval set 增量, T-P1a-03 本地 eval runner 跑
- 全量 pytest 要绿 (现有 ~40 个 refine v2 test + 整个 test suite)

## Regression risk + rollback

- Risk **low**: 纯测试加法, 不改任何 chisha/ 业务模块
- 风险点: mocked LLM 输出形状 vs `_clean_parsed_to_v2` 实际清洗逻辑不一致 → 实施时跑 pytest 立刻发现
- Rollback: `git revert HEAD` 即可

## 不做

- 不跑 real LLM eval (本地 dev 手动跑, T-P1a-03 范围)
- 不改 V1 / V2 业务模块 (T-PR-01 已改 prompt, T-PR-02 不动逻辑)
- 不改 conftest / fixture loader / eval runner
- 不删 / 改现有 30+ test

## Changelog

- iter 1 → iter 2: Codex BLOCK 全接受 (issue 1/3/4/5/7), 重写为双轨设计 (mocked LLM Track A + eval_set Track B). Issue 2 调整接受 — 改用 mocked raw_understanding 而非 V1 flavor_tags 断言. Plan 行数 ~140, affected files 仍 2.
- iter 2 → iter 3: Codex iter 2 BLOCK 全接受. Issue 1 — `_is_null` runner 不支持, 改用 literal null (runner line 122-127 走 `actual == expected` 兜底). Issue 2 — flavor-conflict 类用 `raw_understanding_contains` 加强守门, 新加 `flavor-conflict-01` fixture. Track B 4 条 fixture 重组: flavor-conflict-01 + func-03 + subset-reject-01 + delivery-02 (替换 reject-05, 因跟 reject-01 重叠).
- iter 3 → iter 4: Codex iter 3 BLOCK 接受. `raw_understanding_contains: "辣"` 改成 `raw_understanding_contains: "冲突"` — T-PR-01 prompt example raw_understanding 显式写 `"冲突表达: ..."` (prompts/parse_refine_intent_v2.md:144), 守"冲突"短语真正守 Faithful Refine 边界.

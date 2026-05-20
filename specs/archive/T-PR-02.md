# T-PR-02 · refine eval fixtures 更新

参考: `docs/proposals/2026-05-20-prompt-effect-optimization.md` §4 T-PR-02 + Codex review §5.2

## What

在 `tests/test_refine_intent_v2.py` 增加 4-6 条断言 case, 覆盖 T-PR-01 修订的 6 项边界场景, 防止后续 prompt 迭代回归:

1. **"想吃辣但别太辣"** (冲突表达) → expected: `flavor` 相关字段全空 + `raw_understanding` 含"冲突"/"不确定"短语
2. **"下午要睡觉"** (违反第一原则的旧示例) → expected: `functional.low_caffeine=null` (非 true)
3. **"今天只吃外卖"** (delivery_only 明确表达) → expected: `delivery_only=true`
4. **"今天加班好累"** (场景陈述, 无明示外卖偏好) → expected: `delivery_only=null` (非 false)
5. **"这些广东菜都不想吃, 换湖南菜吧"** (子类否定 + 换菜系, 非全推翻) → expected: `reject_previous=false` + `cuisine_avoid=["广东菜"]` + `cuisine_want=["湖南菜"]`
6. **"上一组全不要, 重来"** (明确推翻) → expected: `reject_previous=true`

每条 case 走 `extract_refine_intent_v2(text=..., use_llm=True/False)`:
- `use_llm=True` 路径走真 LLM, 加 `@pytest.mark.llm` 标记 (旁路 CI, 但本地可跑) 或挂在 eval_set 跑;
- `use_llm=False` 路径走 V1 fallback (`from_legacy`), 测试 schema 兼容 + 字段语义降级期望

不要求每条 case 100% 准: T-P1a-03 已确立 ≥ 85% eval pass 阈值, 本批 fixture 加入 eval set 后整体保持 ≥ 85%。

## Why

- T-PR-01 改了 prompt 文案, 没有 fixture 守门 → 下次有人改 prompt 时这些 finding 会回归
- Codex 对抗审 §5.2 明确要求"4-6 个新 eval case"
- fixture 跟 prompt 改动同一波 commit, 才能保证回归网在 review 时能跑

## Done When

- `tests/test_refine_intent_v2.py` 新增至少 4 条断言 case (覆盖 What 的 6 个场景, 可合并部分)
- 现有 766+ test 全绿: `uv run pytest tests/ -q`
- 新增 case 不引入 LLM 真调用进 CI 默认路径 (用 `pytest.mark.llm` 或 use_llm=False 路径)
- 若有 eval_set jsonl, 同步加入 4-6 条记录 (位置见 `tests/refine_eval/` 或类似目录, 由实施查)

## Plan 规模上限

- `plans/T-PR-02.plan.md` ≤ 200 行
- Affected files ≤ 5

## Affected files (预估)

- `tests/test_refine_intent_v2.py` (改, 加 case)
- `tests/refine_eval/eval_set.jsonl` 或 `tests/fixtures/refine_*.jsonl` (改, 若存在; 由实施 grep 确认路径)

## 红线

- fixture 不改 schema, 不删字段 (D-079 trace 兼容)
- LLM 真调用不进 CI 默认路径 (避免成本 + 网络脆弱性)

## 不做

- 不重写已有 eval 框架 (T-P1a-03 已建)
- 不改 prompt 文件 (T-PR-01 独立)
- 不动召回链路 / L1/L2 (这是 prompt + test 范围)

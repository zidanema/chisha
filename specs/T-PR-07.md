# T-PR-07 · 兼容性守门 + Step 1 整体验收

参考: `docs/proposals/2026-05-20-prompt-effect-optimization.md` §4 T-PR-07 + §6 落地流程 step 5

## What

聚合所有 T-PR-01 ~ T-PR-06 的回归验证, 标记 Step 1 完成:

1. **测试套件全绿**: 
   ```
   uv run pytest tests/test_refine_intent_v2.py -q
   uv run pytest tests/test_rerank.py -q
   uv run pytest tests/test_refine_trace_persist.py -q
   uv run pytest tests/ -q
   ```
2. **`_patch_system_prompt_for_cli` 锚点守门** (D-048): `# 输出方式` 段位置 + 末尾 "select_top_candidates...现在等待" 锚点都能命中
3. **baseline_l2_snapshot 严格回归** (D-072.1 守门): 
   ```
   uv run python -m scripts.baseline_l2_snapshot --out-dir tmp/pr_step1_baseline
   ```
   与上一个 baseline 对比 `compare_traces` — top60 + 14 维 `|delta| < 1e-6` (本批改动只触 L3 prompt 和 schema description, L2 链路不动, 应该 0 diff)
4. **5-10 case 人工对比** (定性, 不阻塞 CI):
   - 跑 `uv run python -m scripts.dry_run --n 5 --meal both` 改前/改后各一次, 对比 5 条推荐的 narrative + risk_flags + one_line_reason 是否符合 §3.2 P0 修订意图
   - 跑 3 条 refine 文本 ("想吃辣但别太辣" / "下午要开会" / "这些广东菜都不想吃, 换湖南菜吧"), 看 refine_intent_v2 输出是否落 P0-E3 / P1-2 修订
   - 结果写到 `plans/T-PR-07.review.md` 留存

Step 1 完成的标记由 git log + tasks.json status=done 体现, **不写回 `docs/proposals/2026-05-20-prompt-effect-optimization.md`** (CLAUDE.md 文档纪律: commit hash / 完成日期 / 测试列表 不写文档).

## Why

- 6 个 task 并行/串行落地后必须有最终 gate, 否则单 task 视角看不到整体回归状况
- baseline_l2_snapshot 是 CONTRACTS 强制门 (D-072.1), 跨 prompt 修订后必须验证 L2 链路 0 diff
- 5-10 case 人工对比是定性验收, 防止"测试全绿但实际推荐质量退化"的盲区
- 落 Step 1 完成标记给后续 Step 2/3/4 提供清晰起跑线

## Done When

- 上面 4 步全部通过
- `plans/T-PR-07.review.md` 已写, 含人工对比 case 输出对比
- `git log --oneline` 能看到 T-PR-01 ~ T-PR-06 的 commit 序列
- `specs/tasks.json` 里 T-PR-01 ~ T-PR-06 status 全部 done (由各 task 完成时更新, 本任务只验证)

## Plan 规模上限

- `plans/T-PR-07.plan.md` ≤ 200 行
- Affected files ≤ 5

## Affected files (预估)

- `tmp/pr_step1_baseline/` (临时, 不进 git)
- `plans/T-PR-07.review.md` (新建, 人工对比留档)

## 红线

- 不改任何 prompt / 代码 (本任务纯验证 + 文档收口)
- baseline_l2_snapshot 出现 diff 必须 halt, 回退看是哪个 T-PR-* 引入 (不允许 "差一点点" 通过)
- 测试套件出现 fail 必须 halt, 回到对应 T-PR-* 修复

## 不做

- 不动任何 prompt 文件 (前 6 task 已经动完)
- 不写新决策 D-XXX (本轮无新业务规则)
- 不进入 Step 2/3/4 (落 Step 1 完成标记后, 后续阶段另开新 brief)
- 不补任何 commit 到 T-PR-01~06 (各自任务的 commit 在各自 task 完成时 commit)

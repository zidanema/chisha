# T-PR-07 · 兼容性守门 + Step 1 整体验收 — Plan

参考 spec: `specs/T-PR-07.md`. 参考 brief: `docs/proposals/2026-05-20-prompt-effect-optimization.md` §6 落地流程 step 5.

> 验证 + 收口 task, 不改 prompt/code, 仅跑测试 + 写 review 留档.

## Affected files

- `plans/T-PR-07.review.md` (新建, 人工对比 case 留档)
- `tmp/pr_step1_baseline_*/` (临时目录, 不进 git, 跑完即删)

无 prompt / code 改动. status=pending 升 done 通过 tasks.json 更新.

## Regression risk

- **low** (本任务纯验证 + 写 review 文档, 不改代码 / prompt / schema)
- baseline_l2_snapshot 是验证手段不是改动 (T-PR-03/05/06 已各自跑过 0 diff, T-PR-07 整体再跑一次确认整批合并后仍 0 diff)
- 测试套件 979 passed 是 T-PR-05 后基线, T-PR-06 后仍是 979 (T-PR-06 没加新测试), 期望 T-PR-07 跑出 979 passed

## Step-by-step

### 1. 测试套件全绿 (CI 守门)

按 spec 顺序跑 4 步:

```bash
uv run pytest tests/test_refine_intent_v2.py -q   # 期望 ~35 passed (T-PR-01 改 prompt + T-PR-02 加 5 case)
uv run pytest tests/test_rerank.py -q             # 期望 ~54 passed (T-PR-05 加 6 case)
uv run pytest tests/test_refine_trace_persist.py -q  # 期望 ~X passed (trace 兼容守门, 不应 fail)
uv run pytest tests/ -q                            # 期望 979 passed (整批 baseline)
```

任一 fail → halt, 不改本轮 task scope, 回退看是哪个 T-PR-* 引入。

### 2. `_patch_system_prompt_for_cli` 锚点守门 (D-048)

跑现有锚点测试:
```bash
uv run pytest tests/test_rerank.py::test_patch_system_prompt_for_cli_raises_if_section_missing \
              tests/test_rerank.py::test_patch_system_prompt_for_cli_raises_if_tail_instruction_missing \
              tests/test_rerank.py::test_patch_system_prompt_for_cli_succeeds_on_real_prompt -q
```

期望 3 passed (T-PR-03/04/05/06 都不动 `# 输出方式` 顶级锚点, 全部 prompt 改动在段内文案)。

### 3. baseline_l2_snapshot 严格回归 (D-072.1 守门, Codex iter 1 BLOCKER 1)

D-072.1 strict mode 要求 before/after 对比, 不接受"每一步 0 diff 推断整批 0 diff" — Codex iter 1 否决简化方案。改回完整 before/after 对比:

Step 1 前的 baseline (HEAD~7 plan-brief commit d660b90, T-PR-01 前状态):
```bash
# 用 git worktree 安全 isolated checkout, 不动当前工作树
# Codex iter 2 BLOCKER: 路径碰撞防护 — 用 mktemp 生成 unique 路径
WT_PATH=$(mktemp -d -t chisha_pr_step1_before_XXXXXX)
git worktree prune  # 清理失效 worktree 引用 (idempotent, 无害)
git worktree add --detach "$WT_PATH" d660b90
# 实施 iter 4 BLOCKER 发现 (Codex 漏掉的): worktree 不含 untracked 运行时 state
# (logs/meal_log.jsonl + data/feedback_history.jsonl 都不 git-tracked). 不 copy
# 会让 worktree 的 baseline 跑出完全不同的 recall 结果 (无 meal_log 时
# diversity cooldown / 历史去重不生效), L2 score 看似漂移但其实是 state 差异.
mkdir -p "$WT_PATH/logs" "$WT_PATH/data"
cp -p logs/meal_log.jsonl "$WT_PATH/logs/meal_log.jsonl" 2>/dev/null || true
cp -p data/feedback_history.jsonl "$WT_PATH/data/feedback_history.jsonl" 2>/dev/null || true
(cd "$WT_PATH" && uv run python -m scripts.baseline_l2_snapshot --out-dir ~/chisha/tmp/pr_step1_before)
git worktree remove --force "$WT_PATH"  # --force 防 dirty (虽然 detached 不应 dirty, 兜底)
```

Step 1 后的 baseline (当前 HEAD = T-PR-06 commit 855404f):
```bash
uv run python -m scripts.baseline_l2_snapshot --out-dir tmp/pr_step1_after
```

compare:
```bash
uv run python -m scripts.compare_traces --before-dir tmp/pr_step1_before --after-dir tmp/pr_step1_after
# 期望: 4 个 ok + "回归通过 ✓ — 重构前后 L2 trace 0 diff"
```

跑完即删 tmp/。若 compare 失败 → halt + 不 update tasks.json, 回退检查 T-PR-* 哪步引入 L2 改动 (理论不应发生 — T-PR-03/05/06 各自已 0 diff)。

### 4. 人工对比 case (定性, 不阻塞 CI)

#### 4a. dry_run 5 case 对比

跑当前 HEAD:
```bash
uv run python -m scripts.dry_run --n 5 --meal both
```

记录 5 条推荐输出 (narrative + 每条 risk_flags + one_line_reason)。预期看到:
- T-PR-03 健康风险披露: 含高油 / processed 配菜 / 甜≥3 combo 时 risk_flags 有标
- T-PR-04 narrative 不假装执行 unsupported 字段 (无 "已过滤快餐 / 限制 1 公里内")
- T-PR-06 one_line_reason 比较条件化 + taste_match rubric 落实

不对比改前 (改前需要 git checkout 多 commit 历史复跑, ROI 低), 改后输出贴 `plans/T-PR-07.review.md` 主观判断符合 P0 修订意图即可。

#### 4b. refine_intent_v2 3 条 case (复现 T-PR-01 实测)

```python
uv run python -c "
from pathlib import Path
from chisha.refine_intent_v2 import extract_refine_intent_v2
from chisha.recall import load_profile
prof = load_profile(Path('profile.yaml'))
profile_llm = prof.get('llm') or {}
for t in ['想吃辣但别太辣', '下午要开会', '这些广东菜都不想吃, 换湖南菜吧']:
    print(f'--- {t!r}')
    v2 = extract_refine_intent_v2(text=t, use_llm=True, profile_llm=profile_llm)
    d = v2.to_log_dict()
    print(f'  reject_previous={d[\"reject_previous\"]}')
    print(f'  cuisine_avoid={d[\"redirect\"][\"cuisine_avoid\"]}, cuisine_want={d[\"redirect\"][\"cuisine_want\"]}')
    print(f'  functional={d[\"constrain\"][\"functional\"]}')
    print(f'  raw_understanding={d[\"raw_understanding\"]}')
"
```

期望 (Codex iter 1 BLOCKER 2 修正: V2 schema 无 flavor_tags 字段, V2 字段是 redirect.* / constrain.* / reference / reject_previous / raw_understanding):
- "想吃辣但别太辣": **cuisine_candidates_expanded=[]** + cuisine_want=[] + cuisine_avoid=[] (V2 冲突表达对应 slot 留空) + raw_understanding 含"冲突"/"不确定"短语 (T-PR-01 第一原则)
- "下午要开会": **constrain.functional.low_caffeine=null** (T-PR-01 修订 1 不联想)
- "这些广东菜都不想吃, 换湖南菜吧": reject_previous=false + **redirect.cuisine_avoid=[广东菜]** + **redirect.cuisine_want=[湖南菜]** + raw_understanding 含拒绝信号 (T-PR-01 修订 3 partial reject 伴随字段)

输出贴 `plans/T-PR-07.review.md`。

### 5. 落 Step 1 完成标记

不写回 brief (CLAUDE.md 文档纪律). 仅:
- `specs/tasks.json` T-PR-07 status → done (Phase 5)
- `git log --oneline` 自然展示 T-PR-01~07 commit 链 + plan-brief commit

## Test strategy

- 本任务 itself 不加测试 (它就是测试 gate)
- 现有所有测试套件 + baseline_l2_snapshot 是验证手段
- 人工 case (4a + 4b) 是定性, 输出 vs 预期对比贴 review.md

## Rollback notes

- 本任务无 code/prompt 改动, rollback 无意义
- 若 step 1-3 fail, halt 报告 + 不 update tasks.json (留 status=pending, T-PR-07 仍 pending)
- 若 step 4 人工对比发现明显回归 (e.g. narrative 仍假装执行 unsupported), halt + 标具体哪个 T-PR-* 没落实

## 不做

- 不改任何 prompt / 代码 / schema
- 不写新决策 D-XXX
- 不动 docs/proposals/ brief 文件 (CLAUDE.md 文档纪律)
- 不补 T-PR-01~06 的 commit (各自任务的 commit 已完成)
- 不进入 Step 2/3/4 (后续阶段另开新 brief)

## Plan 规模

- 本文件: ~125 行, ≤ 200 ✅
- Affected files: 1 (review.md) + 临时 tmp/, ≤ 5 ✅

## Changelog iter 3 (接受 Codex iter 2 1 BLOCKER)

| Issue | Codex iter 2 反对 | 主 agent 处理 |
|---|---|---|
| Issue A | step 3 worktree 路径 `/tmp/chisha_pr_step1_before` 固定无碰撞防护, 主仓已有同名 worktree 时 `git worktree add` 直接报错 | 接受. 改用 `mktemp -d -t chisha_pr_step1_before_XXXXXX` 生成 unique 路径 + `git worktree prune` 先清理失效引用 + `git worktree remove --force` 兜底清 dirty |

Issue B (LLM 冲突表达 flakiness) Codex 自评 OK — T-PR-01 prompt 有冲突表达示例 + 空 slot 规则, 断言有 prompt 级锚定。

## Changelog iter 2 (接受 Codex iter 1 2 BLOCKER)

| Issue | Codex 反对 | 主 agent 处理 |
|---|---|---|
| BLOCKER 1 | step 3 简化方案 (跳 before/after 对比, "每步 0 diff 推断") 不合 D-072.1 严格守门 | 接受. step 3 恢复完整 before/after 对比, 用 git worktree 安全 isolated checkout (HEAD = d660b90 plan-brief commit), 不动当前工作树, 跑完 remove worktree |
| BLOCKER 2 | step 4b 引用 V1 字段 `flavor_tags`, V2 schema 没有 — 验收期望与实际输出结构不符 | 接受. 4b 期望改为 V2 实际字段: `cuisine_candidates_expanded` (冲突表达) / `constrain.functional.low_caffeine` (functional 嵌套) / `redirect.cuisine_avoid` + `redirect.cuisine_want` (V2 namespace prefix). 无 flavor_tags 引用 |

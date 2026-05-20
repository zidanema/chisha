# T-PR-07 · Step 1 整体验收 review

## 1. 测试套件 (CI 守门)

| 套件 | 通过 | 备注 |
|---|---|---|
| tests/test_refine_intent_v2.py | 35 passed | T-PR-01/02 后基线 |
| tests/test_rerank.py | 54 passed | T-PR-05 加 6 + T-PR-06 不加 |
| tests/test_refine_trace_persist.py | 5 passed | trace 兼容 |
| tests/ 全套 | **979 passed, 6 skipped, 0 regressions** | 基线 |

`_patch_system_prompt_for_cli` 锚点守门 3 测试全过 (T-PR-03/04/05/06 都不动 `# 输出方式` 顶级锚点)。

## 2. baseline_l2_snapshot 严格回归 (D-072.1)

before: HEAD = d660b90 (plan-brief commit, T-PR-01 前) via git worktree + copied mutable state (`logs/meal_log.jsonl` + `data/feedback_history.jsonl`).
after: HEAD = T-PR-06 commit 855404f.

```
[ok] snap_dinner_shenzhen-bay_neutral.json
[ok] snap_dinner_shenzhen-bay_want_soup.json
[ok] snap_lunch_shenzhen-bay_neutral.json
[ok] snap_lunch_shenzhen-bay_want_soup.json

回归通过 ✓ — 重构前后 L2 trace 0 diff
```

**EPSILON=1e-6, 0 diff** ✓. 验证: 6 个 task 累计改动只触 L3 prompt + schema description + L2 不动。

⚠️ 实施发现 (plan iter 4): git worktree 不含 untracked 运行时 state (meal_log.jsonl / feedback_history.jsonl). 不 copy 这两个文件会让 baseline_l2_snapshot 跑出完全不同的 recall 结果 (top 54 vs top 59, score 2.65 vs 2.50), 但这是 state 差异不是改动影响。plan iter 4 加 `cp -p` mutable state 后 before/after 一致。

## 3. 人工 case 对比

### 3a. refine_intent_v2 3 case (T-PR-01 验收)

| Input | 期望 | 实测 | 验证 |
|---|---|---|---|
| `想吃辣但别太辣` | cuisine_candidates_expanded=[] + raw_understanding 含"冲突" | `expanded=[], raw_understanding="冲突表达: 想吃辣但不要太辣, 辣度诉求自相矛盾, 对应 slot 全部留空..."` | ✅ T-PR-01 修订 1 + 第一原则 |
| `下午要开会` | functional.low_caffeine=None + raw_understanding 含"不联想" | `low_caffeine=None, raw_understanding="...不擅自推断为低饱腹/提神/不困等偏好 (违反不联想原则)"` | ✅ T-PR-01 修订 1 |
| `这些广东菜都不想吃, 换湖南菜吧` | reject_previous=false + cuisine_avoid=[广东菜] + cuisine_want=[湖南菜] + 拒绝信号 | `reject_previous=False, cuisine_avoid=['广东菜'], cuisine_want=['湖南菜'], raw_understanding="用户拒绝了上一轮的广东菜, 明确要换湖南菜...partial reject 非全盘否定..."` | ✅ T-PR-01 修订 3 partial reject 伴随字段 |

### 3b. dry_run 5 case (T-PR-03/04/06 验收)

跑 `uv run python -m scripts.dry_run --n 5 --meal both`. 50 条推荐输出。摘选验证点:

- **T-PR-03 健康风险披露**: combo 含高油菜时 reason 显式标 "油4偏高但满足感强不易反弹" (不假装避开, D-085 Faithful Refine L3 延伸) ✓
- **T-PR-04 narrative 不假装 unsupported**: 全部 50 条推荐里 narrative + reason 都不出现 "已为你过滤掉快餐 / 限制 1 公里内 / 已避开" 等 unsupported 字段执行声明 ✓
- **T-PR-06 one_line_reason 具体 + 比较条件化**: reason 全部具体 (例: "鹿茸菇炒鸡有锅气, 西红柿炒蛋补蛋白+蔬菜, 粗粮饭, 家常炒菜命中口味核心偏好"); 无强行"比另两条"句; 同品牌多变体时显式比较 (Super Model brand 多 candidate 选择有理由) ✓
- **T-PR-06 taste_match rubric**: reason 措辞反映出 LLM 用 taste_description 匹配度判断 (而非数字阈值) ✓

### 4. 任务 commit 链

```
$ git log --oneline | head -10
4ef92c8 task(T-PR-03): rerank §6 健康语义归位 — 风险披露 + 不主动美化
6c0e0a4 task(T-PR-04): rerank refine_intent 字段口径同步 V1 + V2 reference 说明 (with codex disagreement, ...)
b784e3e task(T-PR-05): rerank tool_use schema description 微调 + 5 项配套增强
855404f task(T-PR-06): rerank prompt 三项 P1 文案补丁 (taste_match rubric + one_line_reason 条件化 + explore escape)
3e4fe89 task(T-PR-02): refine eval fixtures 更新 (双轨守 T-PR-01 prompt 边界)
022c580 task(T-PR-01): refine prompt 多项边界修订 (P0-E3 + P1-1/2/3/7/8)
d660b90 plan-brief: prompt 优化 Step 1 拆 7 task (T-PR-01~07) + Codex 共识审
```

T-PR-01 ~ T-PR-06 全部 commit 落地. T-PR-02 cherry-pick from worktree subagent. T-PR-04 done_with_disagreement (Codex iter 3 文件混淆 stuck override). 其余正常通过。

## 5. Step 1 完成结论

- 7 个 task 全部 done / done_with_disagreement
- 测试: 979 passed (基线 968 + T-PR-02 加 5 + T-PR-05 加 6)
- baseline_l2_snapshot: 0 diff ✓
- 人工对比: 3 refine case + 50 dry_run case 全部反映 T-PR-01/03/04/06 修订意图
- **Step 1 (效果维度) 落地完成**

后续阶段路线 (brief §附录 B):
- Step 2 可读性清理: rerank 计数硬约束 6 处合并 / refine v2 八例减 5 / 顶部 HTML comment 挪出 / 风格统一
- Step 3 压缩 + 加速: refine cache bug 修 (call_text 拆 system/user 拿 cache, 预计 latency 8s→3-4s) / L3 top-K 60→40
- Step 4 model 切换: refine 改 haiku-4.5 / L3 A/B haiku vs sonnet / 直连 vs OpenRouter

D1+D2 (L1/L2 真听 + expanded/synonyms 词典化) 已落 BACKLOG.md F-009 / F-010, Phase 1 推广启动时 review。

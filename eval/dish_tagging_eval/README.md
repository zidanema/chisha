# 菜品打标 v3 - 多模型横评

> 评测目标:`tag_dishes_v3` 在 5-6 个 OpenRouter 主流模型上的字段级准确率,产出**推荐生产模型 + 是否分层方案**的对比报告。
>
> 任务规范:`../dish_tagging_model_eval_spec.md`
> 决策记录:`docs/DECISIONS.md` D-031 / D-032 (prompt) / **D-036** (dual-model golden set 重建)

## Golden set (171 条, 2026-05-12 Opus + Codex 双模型共创)

当前 `data/golden_set.jsonl` 是 **Opus 4.7 + Codex GPT-5.4 三段式共创**产物 (见 D-036):
- 10 anchor (硬编码人审) + 140 重建 (Opus 独立打,Codex 对抗审查,Opus 裁决) + 21 adversarial case (含 price-aware 对照 d169/d169b)
- 4 大字段双模型一致率 99.27% / anchor_violations 0/171
- 旧 150 条 Sonnet 单生成版本备份在 `data/golden_set.v1.jsonl`
- 16 条边界争议条目落账 `KNOWN_ISSUES.md`,等 V1 user feedback 触发重审

## 目录

```
eval/dish_tagging_eval/
├── README.md                     # 本文件
├── CRITICAL_RULES.md             # 规则集中沉淀 (4 大字段 + 6 边界 + 命名优先级)
├── KNOWN_ISSUES.md               # 16 条边界争议条目 (P0/P1/P2 分级)
├── RALPH_LOOP_PROMPT.md          # ralph-loop iteration prompt (dual-model 跑批用)
├── config.yaml                   # 模型 / batch / 预算配置
├── prompts/
│   ├── tag_dishes_v3_draft.md    # v3 prompt (eval 用, 已应用 r3 patch)
│   └── tag_dishes_v3_pre_dual.md # 旧版备份 (dual-model 跑之前)
├── data/
│   ├── golden_set.jsonl          # 171 条 golden (主产物)
│   ├── golden_set.v1.jsonl       # 旧 150 条 Sonnet 版本备份
│   ├── golden_set_dual.jsonl     # 同 golden_set.jsonl (cp 别名)
│   ├── golden_set_dual.spike.jsonl  # 5 条 spike record (d010/d155/d159/d162/d169)
│   └── _dual_audit/              # 每 batch 的 S1/final jsonl audit 链路
├── results/
│   ├── {alias}.jsonl             # 每模型 171 条预测结果
│   └── _run_summary.json         # 跑批汇总
├── scripts/
│   ├── dish_inputs.py            # 旧: 150 条菜名清单 + 10 条 anchor
│   ├── dish_inputs_v2.py         # 新: 在 dish_inputs 基础上 +21 adversarial (d151-d170 + d169b)
│   ├── _or_client.py             # OpenRouter 封装
│   ├── dual_pipeline.py          # Dual-model CLI (status/next-batch/mark-done/merge)
│   ├── _dual_state/              # 状态: batch_plan.json + progress.json
│   ├── build_golden_set.py       # 旧 Step 1 (Sonnet 单生成, deprecated)
│   ├── run_eval.py               # Step 2 (横评跑批)
│   ├── score.py                  # Step 3 (字段级准确率)
│   └── make_report.py            # Step 4-5 (横评报告)
├── score_summary.json
└── report.md
```

## 一键复跑 (横评流程)

```bash
cd ~/chisha
# .env 需有 OPENROUTER_API_KEY

uv run python eval/dish_tagging_eval/scripts/run_eval.py        # Step 2: 跑 6 模型 × 171 条
uv run python eval/dish_tagging_eval/scripts/score.py           # Step 3: 字段准确率
uv run python eval/dish_tagging_eval/scripts/make_report.py     # Step 4-5: 报告
```

可选参数:
- `run_eval.py --only=sonnet-4.6,haiku-4.5` 只跑指定模型
- `run_eval.py --smoke` 只跑前 10 条 golden
- `run_eval.py --force` 覆盖已有 result

## 重建 golden set (Dual-model 共创流程)

当 v3 prompt 大改、新增 adversarial case、或本 golden set 被发现系统性问题时,通过 ralph-loop 重新跑:

```bash
# 1. 重置状态 (谨慎: 会清掉已 mark-done 的 batch)
rm ~/chisha/eval/dish_tagging_eval/scripts/_dual_state/progress.json

# 2. 起 ralph-loop, 引用 RALPH_LOOP_PROMPT.md
#    每 iteration 跑 1 batch (Opus S1 → Codex S2 → Opus S3 → mark-done)
/ralph-loop "Read ~/chisha/eval/dish_tagging_eval/RALPH_LOOP_PROMPT.md and follow it exactly." \
  --max-iterations 40 --completion-promise "GOLDEN_SET_COMPLETE"

# 3. 完成后 merge 合并到 golden_set_dual.jsonl
uv run python eval/dish_tagging_eval/scripts/dual_pipeline.py merge
```

dual_pipeline CLI 子命令:
- `status` — 显示进度 (已完成 batch / pending / spike_done_extra)
- `next-batch` — 输出下一个未完成 batch (5 dishes JSON, 给 Opus S1)
- `mark-done <batch_idx>` — 验证 final_batch_NNN.jsonl 通过 schema + anchor 校验后, 标 completed
- `merge` — 合并所有 batch + spike → `data/golden_set_dual.jsonl`

## 模型清单 (2026-05-11 OpenRouter 实测可用)

| alias | OpenRouter id | 输入/输出价 /1M |
|---|---|---|
| sonnet-4.6 | `anthropic/claude-sonnet-4.6` | $3 / $15 |
| haiku-4.5 | `anthropic/claude-haiku-4.5` | $1 / $5 |
| deepseek-pro | `deepseek/deepseek-v4-pro` | $0.435 / $0.87 |
| deepseek-flash | `deepseek/deepseek-v4-flash` | $0.14 / $0.28 |
| kimi-k2.6 | `moonshotai/kimi-k2.6` | $0.75 / $3.50 |
| glm-4.6 | `z-ai/glm-4.6` | ~$0.3-0.6 |

DeepSeek v4 系列默认关闭 reasoning (`reasoning.enabled=false`),原因:打标任务不需要长思考,且 reasoning 会显著推高 output token。

## 评分规则 (摘要)

- string 字段(`canonical_name` / `cuisine` / ...):strip 后相等
- `protein_grams_estimate`:±5g 容差
- `vegetable_ratio_estimate`:±0.1 容差
- `tags`:Jaccard ≥ 0.5 算对
- 其他离散值:严格相等

关键字段单独看(已知 4 大易错):`sweet_sauce_level` / `processed_meat_flag` / `dish_role` / `grain_type`

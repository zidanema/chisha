# 菜品打标 v3 - 多模型横评

> 评测目标:`tag_dishes_v3` 在 5-6 个 OpenRouter 主流模型上的字段级准确率,产出**推荐生产模型 + 是否分层方案**的对比报告。
>
> **当前结论**: 生产打标默认 `deepseek/deepseek-v4-flash` (字段 acc 88.9%, 距 sonnet 冠军 -0.5pp, 100万条 $100, 见 D-037)
>
> 任务规范:`../dish_tagging_model_eval_spec.md`
> 决策记录:`docs/archive/DECISIONS_phase0.md` D-031 / D-032 (prompt) / **D-036** (dual-model golden set 重建) / **D-037** (生产默认切 deepseek-flash)

## Golden set (171 条, 2026-05-12 Opus + Codex 双模型共创)

当前 `data/golden_set.jsonl` 是 **Opus 4.7 + Codex GPT-5.4 三段式共创**产物 (见 D-036):
- 10 anchor (硬编码人审) + 140 重建 (Opus 独立打,Codex 对抗审查,Opus 裁决) + 21 adversarial case (含 price-aware 对照 d169/d169b)
- 4 大字段双模型一致率 99.27% / anchor_violations 0/171
- 16 条边界争议条目落账 `KNOWN_ISSUES.md`,等 V1 user feedback 触发重审
- 历史 v1 (150 条 Sonnet 单生成) 与 dual-model 过程产物已于 2026-05-13 清理,git 历史 commit 5727b21 之前可查

## 目录

```
eval/dish_tagging_eval/
├── README.md                     # 本文件
├── CRITICAL_RULES.md             # 规则集中沉淀 (4 大字段 + 6 边界 + 命名优先级)
├── KNOWN_ISSUES.md               # 16 条边界争议条目 (P0/P1/P2 分级)
├── RALPH_LOOP_PROMPT.md          # ralph-loop iteration prompt (dual-model 跑批用)
├── config.yaml                   # 模型 / batch / 预算配置
├── prompts/
│   └── tag_dishes_v3_draft.md    # v3 prompt (eval 用, 已应用 r3 patch)
├── data/
│   └── golden_set.jsonl          # 171 条 golden (主产物)
├── results/
│   ├── {alias}.jsonl             # 每模型 171 条预测结果
│   └── _run_summary.json         # 跑批汇总
├── scripts/
│   ├── dish_inputs.py            # 150 条菜名清单 + 10 条 anchor (v2 数据源)
│   ├── dish_inputs_v2.py         # 在 dish_inputs 基础上 +21 adversarial (d151-d170 + d169b)
│   ├── _or_client.py             # OpenRouter 封装
│   ├── dual_pipeline.py          # Dual-model CLI (status/next-batch/mark-done/merge) + anchor_violations
│   ├── run_eval.py               # Step 2 (横评跑批)
│   ├── score.py                  # Step 3 (字段级准确率)
│   ├── make_report.py            # Step 4-5 (横评报告 markdown)
│   └── make_report_html.py       # 横评报告 HTML
├── score_summary.json
├── report.md
└── report.html
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

当 v3 prompt 大改、新增 adversarial case、或本 golden set 被发现系统性问题时,通过 ralph-loop 重新跑。
注:dual-model 跑批的状态目录 (`scripts/_dual_state/`) 与过程产物目录 (`data/_dual_audit/`) 会由 `dual_pipeline.py` 在首次运行时自动重建,已于 2026-05-13 从仓库清理。

```bash
# 1. 起 ralph-loop, 引用 RALPH_LOOP_PROMPT.md
#    每 iteration 跑 1 batch (Opus S1 → Codex S2 → Opus S3 → mark-done)
/ralph-loop "Read ~/chisha/eval/dish_tagging_eval/RALPH_LOOP_PROMPT.md and follow it exactly." \
  --max-iterations 40 --completion-promise "GOLDEN_SET_COMPLETE"

# 2. 完成后 merge 合并 → data/golden_set.jsonl
uv run python eval/dish_tagging_eval/scripts/dual_pipeline.py merge
```

dual_pipeline CLI 子命令:
- `status` — 显示进度 (已完成 batch / pending / spike_done_extra)
- `next-batch` — 输出下一个未完成 batch (5 dishes JSON, 给 Opus S1)
- `mark-done <batch_idx>` — 验证 final_batch_NNN.jsonl 通过 schema + anchor 校验后, 标 completed
- `merge` — 合并所有 batch + spike → `data/golden_set.jsonl`

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

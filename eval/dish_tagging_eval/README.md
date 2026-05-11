# 菜品打标 v3 - 多模型横评

> 评测目标:`tag_dishes_v3` 在 5-6 个 OpenRouter 主流模型上的字段级准确率,产出**推荐生产模型 + 是否分层方案**的对比报告。
>
> 任务规范:`../dish_tagging_model_eval_spec.md`

## 目录

```
eval/dish_tagging_eval/
├── README.md                 # 本文件
├── config.yaml               # 模型 / batch / 预算配置
├── prompts/
│   └── tag_dishes_v3_draft.md   # v3 prompt (从 prompts/tag_dishes.md 拷贝, 只读)
├── data/
│   └── golden_set.jsonl      # 150 条 golden (input + expected)
├── results/
│   ├── {alias}.jsonl         # 每模型 150 条预测结果
│   └── _run_summary.json     # 跑批汇总
├── scripts/
│   ├── dish_inputs.py        # 150 条菜名清单 + 10 条 anchor expected
│   ├── _or_client.py         # OpenRouter 封装
│   ├── build_golden_set.py   # Step 1
│   ├── run_eval.py           # Step 2
│   ├── score.py              # Step 3
│   └── make_report.py        # Step 4-5
├── score_summary.json
└── report.md
```

## 一键复跑

```bash
cd ~/chisha
# 项目 venv 已装好 (uv add httpx tenacity python-dotenv pyyaml tqdm)
# .env 文件需有 OPENROUTER_API_KEY

.venv/bin/python eval/dish_tagging_eval/scripts/build_golden_set.py
.venv/bin/python eval/dish_tagging_eval/scripts/run_eval.py
.venv/bin/python eval/dish_tagging_eval/scripts/score.py
.venv/bin/python eval/dish_tagging_eval/scripts/make_report.py
```

可选参数:
- `run_eval.py --only=sonnet-4.6,haiku-4.5` 只跑指定模型
- `run_eval.py --smoke` 只跑前 10 条 golden
- `run_eval.py --force` 覆盖已有 result

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

## 实际花费

见 `score_summary.json` 中各模型 `cost_usd_total`,以及 `report.md` 实验信息表头。

## 评分规则 (摘要)

- string 字段(`canonical_name` / `cuisine` / ...):strip 后相等
- `protein_grams_estimate`:±5g 容差
- `vegetable_ratio_estimate`:±0.1 容差
- `tags`:Jaccard ≥ 0.5 算对
- 其他离散值:严格相等

关键字段单独看(已知 4 大易错):`sweet_sauce_level` / `processed_meat_flag` / `dish_role` / `grain_type`

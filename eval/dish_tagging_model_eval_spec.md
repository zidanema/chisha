# 菜品打标 Prompt 多模型横评 - 任务需求文档

> 给 Claude Code (ralph 模式) 的独立小需求
> 目标:在 OpenRouter 上横评 5-6 个主流模型在「菜品打标 v3」这个结构化抽取任务上的字段级准确率,产出可决策的报告(选哪个模型跑生产数据冲刷)。

---

## 1. 背景与决策目标

我们有一个营养打标 prompt(`tag_dishes_v3_draft.md`),输出 15 个字段的结构化 JSON。当前用 Claude Sonnet 4.6 跑没问题,但成本偏高,想看能否切换到更便宜的模型(DeepSeek V3.2、Kimi、GLM 等)做大规模数据冲刷。

**决策目标**:产出一份对比报告,回答三个问题:
1. 各候选模型在 15 个字段上的**字段级准确率**分别是多少?
2. 哪些字段是模型间的**主要分水岭**(预期是 `sweet_sauce_level`、`processed_meat_flag`、`dish_role`、`grain_type`)?
3. 综合成本和准确率,**推荐的生产模型**是哪个?是否需要分层方案(便宜模型主跑 + 强模型回退难 case)?

---

## 2. 任务范围(明确划线)

### In scope
- 构造 150 条 golden set(含人工标注答案)
- 在 OpenRouter 上调用 5-6 个候选模型跑同一份 prompt
- 字段级准确率计算 + JSON 合法率统计
- 生成 markdown 格式的对比报告
- 全部脚本化,可一键复跑

### Out of scope
- **不要**修改 prompt 本身(用 `tag_dishes_v3_draft.md` 原版,prompt 调优是另一个 issue)
- 不需要 fine-tune 任何模型
- 不需要部署到生产环境
- 不需要做 LLM-as-judge(字段都是离散值,直接 string/数值比对)

---

## 3. 候选模型清单

通过 OpenRouter API 调用,模型 id 以查 OpenRouter 实际可用为准(可能版本号会变,以 `https://openrouter.ai/models` 当前列表为准):

| 别名 | OpenRouter model id (参考,以实际为准) | 输入/输出价 (per 1M) | 角色 |
|---|---|---|---|
| sonnet-4.6 | `anthropic/claude-sonnet-4.6` | $3 / $15 | baseline / 上限参考 |
| haiku-4.5 | `anthropic/claude-haiku-4.5` | $1 / $5 | Claude 性价比档 |
| deepseek-v4-pro | `deepseek/deepseek-v4-pro` | $0.435 / $0.87 | DeepSeek 旗舰 |
| deepseek-v4-flash | `deepseek/deepseek-v4-flash` | $0.14 / $0.28 | DeepSeek 性价比天花板 |
| kimi-k2.6 | `moonshotai/kimi-k2.6` | $0.75 / $3.50 | 中文优势候选 |
| glm-4.6 | `z-ai/glm-4.6` 或当前最新 GLM | 约 $0.3-0.6 | 智谱候选 |

**额外要求:DeepSeek V4 Pro / Flash 两档都跑**——这两个价差 3 倍,对决策很关键。如果 Flash 够用,生产成本能再砍 2/3;如果只有 Pro 够用,就要在 Pro 和 Haiku 之间权衡。

**注意**:如果某个模型 id 在 OpenRouter 上找不到,**自动 fallback 到同家族最接近的可用版本**,并在报告里注明实际用的版本。不要因为模型 id 写死跑不通就卡住。

**reasoning 参数处理**:DeepSeek V4 系列支持 `reasoning` 开关(`high`/`xhigh`)。本任务**默认关闭 reasoning**(`reasoning: {enabled: false}`),因为打标任务不需要长思考,且开了会大幅推高 output token 成本。如果关闭后 Flash 准确率明显掉,可以**额外加一组对照实验**:Flash + reasoning=high,看准确率提升换成本是否划算。

---

## 4. 步骤拆解

### Step 1:扩展 golden set 到 150 条

源材料:`tag_dishes_v3_draft.md` 里已有 10 条示例(d001-d010),它们也是 anchor case。

需要扩展到 **150 条**,按以下分布构造(确保覆盖 prompt 里所有反直觉锚点):

| 类别 | 数量 | 重点覆盖 |
|---|---|---|
| 川湘菜(炒/煮/水煮系列) | 25 | spicy_level、oil_level、wetness 边界 |
| 粤菜潮汕(烧腊、汤粥、肠粉粿条) | 20 | **烧腊默认 processed_meat=false**、grain_type=白米(米制品归白米) |
| 江浙红烧/糖醋类 | 15 | **sweet_sauce_level=2 锚点**(红烧/糖醋/照烧/京酱) |
| 日式韩式(寿司、关东煮、石锅拌饭) | 15 | **关东煮 wetness=2 不是 3**、寿司 cooking=生 |
| 西式快餐(汉堡、披萨、沙拉、意面) | 15 | processed_meat 命名主夹层判定、沙拉 wetness=1 |
| 套餐组合(N+M、+饭+饮料+汤) | 20 | **dish_role=套餐 触发词**、复合主食取最精制 |
| 主食单点(饺/包/面/粉/饭/粥) | 15 | grain_type 全谱、is_complete_meal 判断 |
| 配菜/汤/饮品/小食 | 15 | dish_role 分配、纯素菜 vegetable_ratio |
| **边界/对抗样本** | 10 | **非食物兜底**(调料、餐具)、超长促销词、emoji、隐式套餐(无"套餐"字样但含"+饭") |

**Golden set 文件格式**:`golden_set.jsonl`,每行一条:
```json
{
  "dish_id": "d001",
  "input": {
    "dish_id": "d001",
    "raw_name": "蒜蓉空心菜",
    "restaurant_name": "湘里湘亲",
    "restaurant_category_raw": "湘菜",
    "category_raw": "时蔬",
    "price": 18
  },
  "expected": {
    "dish_id": "d001",
    "canonical_name": "蒜蓉空心菜",
    "cuisine": "湘菜",
    "main_ingredient_type": "纯素",
    "cooking_method": "炒",
    "oil_level": 3,
    "protein_grams_estimate": 5,
    "vegetable_ratio_estimate": 0.95,
    "is_complete_meal": false,
    "spicy_level": 0,
    "dish_role": "配菜",
    "processed_meat_flag": false,
    "sweet_sauce_level": 0,
    "wetness": 2,
    "grain_type": "无",
    "tags": ["高纤维", "清淡", "适合减脂"]
  },
  "category_tag": "配菜",
  "anchor_notes": "纯叶菜 vegetable_ratio≥0.9, dish_role=配菜"
}
```

**构造方法**:
1. 先把 d001-d010 全部纳入 golden set
2. 用 Sonnet 4.6 跑生成 140 条候选(可以让 Claude Code 一批批生成菜名,再让 Sonnet 跑出 expected,自己人工不需要全标)
3. **人工 review 修正**:重点 review `sweet_sauce_level`、`processed_meat_flag`、`dish_role`、`wetness` 这 4 个最容易出错的字段,以及非食物兜底 case。其他字段抽查即可。
4. 每条加 `category_tag` 和 `anchor_notes`,方便后续按类切片看准确率

⚠️ **构造期由我(人类)确认 review,不要 Claude Code 全自动跑完不验证**。生成 140 条候选后,先停下让我看一眼边界 case 的 expected 是否合理,我确认后再继续。

### Step 2:OpenRouter 调用脚本

文件:`run_eval.py`

需求:
- 读 `golden_set.jsonl` + `tag_dishes_v3_draft.md`
- **batch 20 条/请求**(分摊 prompt 成本,和生产场景一致)
- 对每个候选模型跑全量 150 条
- **并发控制**:每模型最多 5 并发,避免 OpenRouter rate limit
- **重试**:JSON 解析失败 / 网络错误最多重试 2 次
- 输出:`results/{model_alias}.jsonl`,每行:
  ```json
  {
    "dish_id": "d001",
    "model": "deepseek-v3.2",
    "predicted": {...15 字段 JSON...},
    "raw_response": "原始返回文本(用于 debug)",
    "latency_ms": 1234,
    "input_tokens": 256,
    "output_tokens": 198,
    "cost_usd": 0.000164,
    "json_valid": true,
    "retry_count": 0
  }
  ```
- 配置文件 `config.yaml` 集中管理:模型列表、batch size、并发数、API key(从环境变量 `OPENROUTER_API_KEY` 读)

⚠️ **不要把 API key 硬编码到代码里**,也不要 commit 到 git。在 README 里说明用环境变量。

### Step 3:评分脚本

文件:`score.py`

字段评分规则(严格匹配,因为字段都是离散值):

| 字段 | 评分方法 |
|---|---|
| canonical_name | string 相等(strip 后) |
| cuisine | string 相等 |
| main_ingredient_type | string 相等 |
| cooking_method | string 相等 |
| oil_level | int 相等 |
| protein_grams_estimate | **±5g 容差**(因为 5g 粒度,差一档不算错) |
| vegetable_ratio_estimate | **±0.1 容差** |
| is_complete_meal | bool 相等 |
| spicy_level | int 相等 |
| dish_role | string 相等 |
| processed_meat_flag | bool 相等 |
| sweet_sauce_level | int 相等 |
| wetness | int 相等 |
| grain_type | string 相等 |
| tags | **Jaccard ≥ 0.5 算对**(标签是自由 1-3 个,精确匹配过严) |

额外指标:
- **JSON 合法率**:`json_valid=true` 的比例(JSON 解析成功 + 包含全部 15 字段 + 类型正确)
- **整条完全正确率**:15 字段全对的样本占比
- **按 `category_tag` 切片**:每个模型在「粤菜」「套餐」「边界对抗」等各子集上的字段准确率
- **关键字段单独看**:`sweet_sauce_level`、`processed_meat_flag`、`dish_role`、`grain_type` 这 4 个分水岭字段单独统计

### Step 4:成本与速度统计

从 `results/*.jsonl` 聚合:
- 每模型的总 input/output tokens
- 实际花费(OpenRouter 返回的 `cost_usd` 字段)
- 平均延迟、p95 延迟
- **外推 100 万条数据的预估成本**(按当前 batch 配置)

### Step 5:生成对比报告

文件:`report.md`,结构:

```markdown
# 菜品打标 v3 - 多模型横评报告

## 总体对比表
| 模型 | 字段级准确率 | 整条全对率 | JSON 合法率 | 平均延迟 | 单条成本 | 100万条预估 |
|---|---|---|---|---|---|---|

## 关键字段分水岭(4 大易错字段单独看)
| 模型 | sweet_sauce | processed_meat | dish_role | grain_type |

## 按类别切片
(粤菜、套餐、边界对抗 各模型表现)

## 典型错误 case 抽样
(每模型挑 5 条最严重错误,展示 expected vs predicted)

## 结论与建议
- 推荐生产模型:XXX
- 是否需要分层方案:XXX
- 已知风险/局限
```

报告必须包含**结论与建议**,基于实测数据给出推荐,不要含糊其辞。

---

## 5. 项目目录结构

```
dish_tagging_eval/
├── README.md                    # 如何运行
├── config.yaml                  # 模型列表、batch、并发
├── prompts/
│   └── tag_dishes_v3_draft.md   # 原 prompt(从外部 copy 进来,不修改)
├── data/
│   └── golden_set.jsonl         # 150 条 golden(input + expected)
├── results/
│   └── {model_alias}.jsonl      # 各模型跑出的结果
├── scripts/
│   ├── build_golden_set.py      # 半自动构造 golden(调 Sonnet 生成候选)
│   ├── run_eval.py              # OpenRouter 调用
│   ├── score.py                 # 评分
│   └── make_report.py           # 生成 report.md
├── report.md                    # 最终报告
└── requirements.txt
```

依赖建议:`httpx`(异步调用)、`pyyaml`、`tqdm`、`tenacity`(重试)、`pandas`(报告聚合)。

---

## 6. Ralph 模式执行要点

适合 ralph 的几个 checkpoint(每个 checkpoint 完成后停下,让我确认再继续):

1. **CP1**:Step 1 完成 140 条候选生成后停,让我 review 边界 case
2. **CP2**:Step 2 脚本写好,**先用 sonnet-4.6 单模型跑通 10 条**,让我看跑通后再 fan-out 到全部模型 + 全部 150 条
3. **CP3**:Step 3 评分跑出第一份原始数字后停,让我看下数字是否符合直觉(Sonnet 应该最高,DeepSeek 应该在 sweet_sauce 上明显差一些),再生成最终报告
4. **CP4**:`report.md` 生成后停,等我 review

中间任何一个 checkpoint 卡住超过 3 次重试还跑不动,**停下来等我**,不要硬刚。

---

## 7. 预算与风险

- **总预算**:单次完整横评 < $15。如果跑超 $15 停下来报告。
  - 6 个模型 × 150 条 × batch 20 摊薄后,实际开销主要在 Sonnet 和 Haiku 上,DeepSeek/Kimi/GLM 加起来不到 $1
- **OpenRouter API key**:我会通过环境变量提供,不要尝试 mock。
- **如果某个候选模型在 OpenRouter 上跑不通**(账号没权限、模型下线等):跳过该模型,在报告里注明"未测",不要因为一个模型卡死整个流程。

---

## 8. 验收标准

完成后我会检查:

- [ ] `golden_set.jsonl` 150 条,4 个关键字段我抽查 20 条人工标注合理
- [ ] 全部候选模型至少跑出结果(允许 1 个模型未测,要在报告说明)
- [ ] `report.md` 有完整对比表、关键字段分水岭、按类别切片、典型错误 case、结论建议
- [ ] 全流程可一键复跑:`python scripts/run_eval.py && python scripts/score.py && python scripts/make_report.py`
- [ ] 总花费 < $15,在 README 里实际报销账目

---

## 附录:已知的 4 大易错字段(参考 prompt)

这几个字段是 LLM 默认倾向和 prompt 要求**冲突最大**的地方,也是模型间差异最可能集中的地方。Claude Code 在构造 golden set 和评分时重点关注:

1. **sweet_sauce_level**:LLM 默认倾向把"非明确甜"打 0,但 prompt 要求看到"烧/红/酱/糖/蜜/照"字眼至少打 2
2. **processed_meat_flag**:**中式烧腊(叉烧/烧鸭/烧鹅)默认 false**,腊味才 true,这点反直觉
3. **dish_role**:套餐触发词不止"套餐"二字,"+饭/+饮料/+汤"都触发;饺/包/面默认归主食不归小食
4. **grain_type**:米粉/河粉/粿条/肠粉归"白米"(精制米制品),复合套餐多主食取最精制

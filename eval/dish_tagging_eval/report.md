# 菜品打标 v3 - 多模型横评报告

- golden set: 171 条
- 实际总成本: $1.4525
- 实际跑的模型: 6

## 实验信息

| alias | OpenRouter id | n_evaluated | json_valid |
|---|---|---|---|
| sonnet-4.6 | `anthropic/claude-sonnet-4.6` | 171/171 | 100.0% |
| haiku-4.5 | `anthropic/claude-haiku-4.5` | 171/171 | 100.0% |
| deepseek-pro | `deepseek/deepseek-v4-pro` | 171/171 | 100.0% |
| deepseek-flash | `deepseek/deepseek-v4-flash` | 171/171 | 100.0% |
| kimi-k2.6 | `moonshotai/kimi-k2.6` | 171/171 | 100.0% |
| glm-4.6 | `z-ai/glm-4.6` | 171/171 | 100.0% |

## 总体对比表

| 模型 | 字段准确率 | 整条全对率 | JSON 合法率 | batch_p95(s) | 总成本 | 100万条预估 |
|---|---:|---:|---:|---:|---:|---:|
| sonnet-4.6 | 89.4% | 23.4% | 100.0% | 47.3 | $0.7818 | $4572 |
| deepseek-pro | 89.0% | 19.3% | 100.0% | 151.0 | $0.2326 | $1360 |
| deepseek-flash | 88.9% | 20.5% | 100.0% | 76.8 | $0.0171 | $100 |
| kimi-k2.6 | 87.3% | 17.0% | 100.0% | 61.0 | $0.1143 | $668 |
| glm-4.6 | 87.2% | 17.5% | 100.0% | 116.9 | $0.0631 | $369 |
| haiku-4.5 | 85.2% | 13.5% | 100.0% | 31.3 | $0.2435 | $1424 |

## 吞吐与生产部署预估

> batch=20, concurrency=10(经验上 OpenRouter 单账号 rate limit 内的安全值).
> p95 batch latency 来自评测实测,用于做时间预估(保守口径).

| 模型 | 单请求吞吐(条/秒) | concurrency=10 吞吐(条/秒) | 跑 1万条耗时 | 跑 10万条耗时 | 1万条成本 |
|---|---:|---:|---:|---:|---:|
| sonnet-4.6 | 0.29 | 2.9 | 1.2h | 12.0h | $45.72 |
| deepseek-pro | 0.15 | 1.5 | 3.8h | 38.2h | $13.60 |
| deepseek-flash | 0.25 | 2.5 | 1.9h | 19.4h | $1.00 |
| kimi-k2.6 | 0.31 | 3.1 | 1.5h | 15.4h | $6.68 |
| glm-4.6 | 0.14 | 1.4 | 3.0h | 29.6h | $3.69 |
| haiku-4.5 | 0.44 | 4.4 | 47.4min | 7.9h | $14.24 |

## 关键字段分水岭(4 大易错字段)

| 模型 | sweet_sauce_level | processed_meat_flag | dish_role | grain_type |
|---|---:|---:|---:|---:|
| sonnet-4.6 | 86.0% | 97.7% | 94.2% | 100.0% |
| haiku-4.5 | 76.0% | 97.1% | 91.8% | 97.7% |
| deepseek-pro | 86.0% | 97.1% | 93.0% | 98.8% |
| deepseek-flash | 82.5% | 97.7% | 93.0% | 98.2% |
| kimi-k2.6 | 78.9% | 97.7% | 91.8% | 97.1% |
| glm-4.6 | 79.5% | 95.9% | 89.5% | 97.7% |

## 全字段准确率(每模型 15 字段)

| 字段 | sonnet-4.6 | haiku-4.5 | deepseek-pro | deepseek-flash | kimi-k2.6 | glm-4.6 |
|---|---:|---:|---:|---:|---:|---:|
| canonical_name | 93.6% | 93.6% | 96.5% | 94.2% | 90.6% | 90.1% |
| cooking_method | 88.3% | 80.1% | 84.2% | 87.1% | 87.7% | 84.2% |
| cuisine | 93.0% | 87.1% | 90.1% | 91.8% | 88.3% | 92.4% |
| dish_role | 94.2% | 91.8% | 93.0% | 93.0% | 91.8% | 89.5% |
| grain_type | 100.0% | 97.7% | 98.8% | 98.2% | 97.1% | 97.7% |
| is_complete_meal | 97.1% | 95.3% | 94.2% | 94.2% | 94.7% | 92.4% |
| main_ingredient_type | 87.7% | 86.0% | 88.9% | 88.9% | 88.9% | 91.8% |
| oil_level | 78.9% | 68.4% | 75.4% | 76.6% | 71.3% | 76.0% |
| processed_meat_flag | 97.7% | 97.1% | 97.1% | 97.7% | 97.7% | 95.9% |
| protein_grams_estimate | 97.7% | 88.3% | 96.5% | 95.9% | 95.9% | 94.2% |
| spicy_level | 88.3% | 87.1% | 90.6% | 87.7% | 91.2% | 84.2% |
| sweet_sauce_level | 86.0% | 76.0% | 86.0% | 82.5% | 78.9% | 79.5% |
| tags | 69.0% | 66.1% | 71.3% | 70.8% | 64.9% | 71.9% |
| vegetable_ratio_estimate | 87.1% | 83.0% | 90.1% | 90.6% | 87.7% | 84.8% |
| wetness | 83.0% | 80.1% | 81.9% | 84.8% | 82.5% | 83.0% |

## 按类别切片(字段准确率 micro)

| 类别 | sonnet-4.6 | haiku-4.5 | deepseek-pro | deepseek-flash | kimi-k2.6 | glm-4.6 |
|---|---:|---:|---:|---:|---:|---:|
| 川湘菜 (sichuan_xiang) | 93.3% | 90.1% | 90.4% | 91.2% | 89.1% | 86.9% |
| 粤潮 (yue_chaoshan) | 91.7% | 84.7% | 90.0% | 89.0% | 87.7% | 86.7% |
| 江浙红烧/糖醋 (jiangzhe_sweet) | 94.7% | 91.1% | 96.4% | 94.7% | 95.6% | 95.6% |
| 日韩 (japan_korea) | 88.0% | 82.2% | 90.2% | 87.1% | 85.3% | 84.9% |
| 西式快餐 (western_fast) | 88.9% | 83.1% | 84.0% | 88.9% | 88.0% | 87.6% |
| 套餐组合 (combo) | 85.3% | 80.0% | 88.0% | 88.0% | 82.7% | 85.3% |
| 主食单点 (staple) | 86.7% | 82.7% | 86.2% | 87.6% | 88.4% | 86.2% |
| 配菜/汤/饮品/小食 (side_soup) | 89.8% | 85.8% | 92.0% | 91.6% | 86.7% | 88.0% |
| 边界对抗 (boundary) | 91.3% | 88.7% | 90.7% | 90.0% | 88.0% | 92.0% |

## 典型错误 case 抽样

### sonnet-4.6

**case 1**: `d009` 烧鸭腿拼叉烧饭+老火靓汤 (`yue_chaoshan`)
  - `canonical_name`: expected="烧鸭腿拼叉烧饭 含汤" predicted="烧鸭腿拼叉烧饭 含老火靓汤"
  - `main_ingredient_type`: expected="红肉" predicted="白肉"
  - `wetness`: expected=2 predicted=3

**case 2**: `d011` 麻婆豆腐 (`sichuan_xiang`)
  - `cooking_method`: expected="炖" predicted="炒"

**case 3**: `d013` 鱼香肉丝 (`sichuan_xiang`)
  - `oil_level`: expected=3 predicted=4
  - `tags`: expected=["高蛋白", "下饭"] predicted=["重口味", "下饭"]

**case 4**: `d015` 夫妻肺片 (`sichuan_xiang`)
  - `wetness`: expected=1 predicted=2

**case 5**: `d018` 酸辣土豆丝 (`sichuan_xiang`)
  - `wetness`: expected=1 predicted=2
  - `tags`: expected=["高碳水", "重口味"] predicted=["高纤维", "清淡", "适合减脂"]


### haiku-4.5

**case 1**: `d009` 烧鸭腿拼叉烧饭+老火靓汤 (`yue_chaoshan`)
  - `main_ingredient_type`: expected="红肉" predicted="白肉"
  - `wetness`: expected=2 predicted=3

**case 2**: `d011` 麻婆豆腐 (`sichuan_xiang`)
  - `cooking_method`: expected="炖" predicted="炒"

**case 3**: `d013` 鱼香肉丝 (`sichuan_xiang`)
  - `oil_level`: expected=3 predicted=4

**case 4**: `d014` 毛血旺 (`sichuan_xiang`)
  - `cooking_method`: expected="煮" predicted="炒"
  - `oil_level`: expected=5 predicted=4
  - `wetness`: expected=3 predicted=2
  - `tags`: expected=["重口味", "油重"] predicted=["高蛋白", "重口味", "下饭"]

**case 5**: `d015` 夫妻肺片 (`sichuan_xiang`)
  - `wetness`: expected=1 predicted=2


### deepseek-pro

**case 1**: `d009` 烧鸭腿拼叉烧饭+老火靓汤 (`yue_chaoshan`)
  - `wetness`: expected=2 predicted=3

**case 2**: `d011` 麻婆豆腐 (`sichuan_xiang`)
  - `cooking_method`: expected="炖" predicted="炒"

**case 3**: `d012` 回锅肉 (`sichuan_xiang`)
  - `wetness`: expected=1 predicted=2

**case 4**: `d013` 鱼香肉丝 (`sichuan_xiang`)
  - `oil_level`: expected=3 predicted=4

**case 5**: `d014` 毛血旺 (`sichuan_xiang`)
  - `main_ingredient_type`: expected="红肉" predicted="其他"
  - `tags`: expected=["重口味", "油重"] predicted=["高蛋白", "重口味", "下饭"]


### deepseek-flash

**case 1**: `d009` 烧鸭腿拼叉烧饭+老火靓汤 (`yue_chaoshan`)
  - `canonical_name`: expected="烧鸭腿拼叉烧饭 含汤" predicted="烧鸭腿拼叉烧饭+老火靓汤"
  - `wetness`: expected=2 predicted=3

**case 2**: `d011` 麻婆豆腐 (`sichuan_xiang`)
  - `cooking_method`: expected="炖" predicted="炒"

**case 3**: `d012` 回锅肉 (`sichuan_xiang`)
  - `wetness`: expected=1 predicted=2

**case 4**: `d013` 鱼香肉丝 (`sichuan_xiang`)
  - `oil_level`: expected=3 predicted=4

**case 5**: `d014` 毛血旺 (`sichuan_xiang`)
  - `tags`: expected=["重口味", "油重"] predicted=["重口味", "下饭"]


### kimi-k2.6

**case 1**: `d009` 烧鸭腿拼叉烧饭+老火靓汤 (`yue_chaoshan`)
  - `wetness`: expected=2 predicted=3

**case 2**: `d012` 回锅肉 (`sichuan_xiang`)
  - `wetness`: expected=1 predicted=2

**case 3**: `d013` 鱼香肉丝 (`sichuan_xiang`)
  - `oil_level`: expected=3 predicted=4
  - `vegetable_ratio_estimate`: expected=0.3 predicted=0.4

**case 4**: `d014` 毛血旺 (`sichuan_xiang`)
  - `tags`: expected=["重口味", "油重"] predicted=["重口味", "下饭"]

**case 5**: `d015` 夫妻肺片 (`sichuan_xiang`)
  - `oil_level`: expected=3 predicted=4
  - `wetness`: expected=1 predicted=2


### glm-4.6

**case 1**: `d011` 麻婆豆腐 (`sichuan_xiang`)
  - `cooking_method`: expected="炖" predicted="煮"
  - `wetness`: expected=2 predicted=3

**case 2**: `d012` 回锅肉 (`sichuan_xiang`)
  - `oil_level`: expected=5 predicted=4
  - `spicy_level`: expected=2 predicted=1
  - `wetness`: expected=1 predicted=2

**case 3**: `d013` 鱼香肉丝 (`sichuan_xiang`)
  - `spicy_level`: expected=2 predicted=1
  - `vegetable_ratio_estimate`: expected=0.3 predicted=0.5
  - `tags`: expected=["高蛋白", "下饭"] predicted=["下饭", "油重"]

**case 4**: `d014` 毛血旺 (`sichuan_xiang`)
  - `spicy_level`: expected=3 predicted=2
  - `tags`: expected=["重口味", "油重"] predicted=["高蛋白", "重口味", "汤水"]

**case 5**: `d015` 夫妻肺片 (`sichuan_xiang`)
  - `dish_role`: expected="主菜" predicted="配菜"
  - `wetness`: expected=1 predicted=2


## 结论与建议

### 1. 三维度并列冠军

- **准确率冠军**:`sonnet-4.6` — 字段 89.4%, 整条全对 23.4%
- **成本冠军**:`deepseek-flash` — 100万条预估 $100
- **吞吐冠军**:`haiku-4.5` — concurrency=10 下 4.4 条/秒, 跑 10 万条仅需 ~474min

### 2. 关键字段分水岭

- **sweet_sauce_level**: 最好 `sonnet-4.6` (86.0%), 最差 `haiku-4.5` (76.0%), gap 9.9pp
- **processed_meat_flag**: 最好 `sonnet-4.6` (97.7%), 最差 `glm-4.6` (95.9%), gap 1.8pp
- **dish_role**: 最好 `sonnet-4.6` (94.2%), 最差 `glm-4.6` (89.5%), gap 4.7pp
- **grain_type**: 最好 `sonnet-4.6` (100.0%), 最差 `kimi-k2.6` (97.1%), gap 2.9pp

### 3. 推荐生产模型 (按数据量与时间窗口)

生产场景的选型不能只看准确率/成本,**吞吐(完成时间)同等关键**——便宜但跑得慢的模型,几万条数据可能跑一整天.

| 场景 | 推荐 | 理由 |
|---|---|---|
| 数据量 ≤ 1万 / 时间敏感 | **`sonnet-4.6`** | 准确率最高 (89.4%), 1万条 $45.7 / 1.2h; 贵但快, 小批量首选 |
| 数据量 1万-10万 / 性价比均衡 ⭐ **(生产打标默认)** | **`deepseek-flash`** | 字段准确率 88.9%(距冠军 -0.5pp), 吞吐 2.5 条/秒, 100万条 $100 (2.2% 冠军成本), 10万条 19.4h |

### 4. 是否分层方案?

**不分层**:`deepseek-flash` 已经接近 top (88.9% vs 89.4%, gap 0.5pp), 分层带来的边际收益不大.

### 5. 最终决策 (基于本次实测)

- **生产打标默认 → `deepseek-flash`** (`chisha/llm_client_openrouter.py:DEFAULT_BULK_MODEL`): 准确率 88.9%, 100万条 $100, 距冠军 -0.5pp 性价比最优
- 如果**只跑一次几千条 → `sonnet-4.6`**:准确率最高 89.4% + 速度最快档 + 一次性成本可接受

### 6. 已知风险/局限

- 无显著风险

---

*报告由 `scripts/make_report.py` 基于 `score_summary.json` 自动生成.*

# 菜品打标 v3 - 多模型横评报告

- golden set: 150 条
- 实际总成本: $1.2851
- 实际跑的模型: 6

## 实验信息

| alias | OpenRouter id | n_evaluated | json_valid |
|---|---|---|---|
| sonnet-4.6 | `anthropic/claude-sonnet-4.6` | 150/150 | 100.0% |
| haiku-4.5 | `anthropic/claude-haiku-4.5` | 150/150 | 100.0% |
| deepseek-pro | `deepseek/deepseek-v4-pro` | 150/150 | 100.0% |
| deepseek-flash | `deepseek/deepseek-v4-flash` | 150/150 | 100.0% |
| kimi-k2.6 | `moonshotai/kimi-k2.6` | 150/150 | 100.0% |
| glm-4.6 | `z-ai/glm-4.6` | 150/150 | 100.0% |

## 总体对比表

| 模型 | 字段准确率 | 整条全对率 | JSON 合法率 | batch_p95(s) | 总成本 | 100万条预估 |
|---|---:|---:|---:|---:|---:|---:|
| sonnet-4.6 | 97.3% | 72.0% | 100.0% | 35.7 | $0.6736 | $4491 |
| deepseek-pro | 92.6% | 40.0% | 100.0% | 403.9 | $0.1963 | $1308 |
| kimi-k2.6 | 90.4% | 26.7% | 100.0% | 119.8 | $0.1302 | $868 |
| deepseek-flash | 90.0% | 30.0% | 100.0% | 157.3 | $0.0144 | $96 |
| glm-4.6 | 90.0% | 26.7% | 100.0% | 105.0 | $0.0605 | $403 |
| haiku-4.5 | 87.6% | 18.7% | 100.0% | 17.8 | $0.2102 | $1402 |

## 吞吐与生产部署预估

> batch=20, concurrency=10(经验上 OpenRouter 单账号 rate limit 内的安全值).
> p95 batch latency 来自评测实测,用于做时间预估(保守口径).

| 模型 | 单请求吞吐(条/秒) | concurrency=10 吞吐(条/秒) | 跑 1万条耗时 | 跑 10万条耗时 | 1万条成本 |
|---|---:|---:|---:|---:|---:|
| sonnet-4.6 | 0.37 | 3.7 | 59.4min | 9.9h | $44.91 |
| deepseek-pro | 0.08 | 0.8 | 11.2h | 112.2h | $13.08 |
| kimi-k2.6 | 0.21 | 2.1 | 3.3h | 33.3h | $8.68 |
| deepseek-flash | 0.11 | 1.1 | 4.4h | 43.7h | $0.96 |
| glm-4.6 | 0.20 | 2.0 | 2.9h | 29.2h | $4.03 |
| haiku-4.5 | 0.65 | 6.5 | 29.7min | 4.9h | $14.02 |

## 关键字段分水岭(4 大易错字段)

| 模型 | sweet_sauce_level | processed_meat_flag | dish_role | grain_type |
|---|---:|---:|---:|---:|
| sonnet-4.6 | 93.3% | 100.0% | 99.3% | 98.7% |
| haiku-4.5 | 79.3% | 96.0% | 94.7% | 96.7% |
| deepseek-pro | 87.3% | 97.3% | 97.3% | 98.7% |
| deepseek-flash | 84.7% | 96.7% | 94.7% | 99.3% |
| kimi-k2.6 | 82.0% | 98.7% | 95.3% | 98.0% |
| glm-4.6 | 83.3% | 96.7% | 95.3% | 95.3% |

## 全字段准确率(每模型 15 字段)

| 字段 | sonnet-4.6 | haiku-4.5 | deepseek-pro | deepseek-flash | kimi-k2.6 | glm-4.6 |
|---|---:|---:|---:|---:|---:|---:|
| canonical_name | 96.7% | 91.3% | 93.3% | 92.0% | 92.7% | 91.3% |
| cooking_method | 96.7% | 85.3% | 90.0% | 87.3% | 90.7% | 88.0% |
| cuisine | 98.7% | 88.7% | 92.0% | 91.3% | 85.3% | 90.0% |
| dish_role | 99.3% | 94.7% | 97.3% | 94.7% | 95.3% | 95.3% |
| grain_type | 98.7% | 96.7% | 98.7% | 99.3% | 98.0% | 95.3% |
| is_complete_meal | 97.3% | 93.3% | 100.0% | 95.3% | 94.7% | 98.0% |
| main_ingredient_type | 96.7% | 83.3% | 87.3% | 90.0% | 94.0% | 86.7% |
| oil_level | 96.7% | 70.0% | 88.0% | 77.3% | 77.3% | 88.0% |
| processed_meat_flag | 100.0% | 96.0% | 97.3% | 96.7% | 98.7% | 96.7% |
| protein_grams_estimate | 100.0% | 92.0% | 96.7% | 90.7% | 98.0% | 96.7% |
| spicy_level | 96.0% | 87.3% | 88.7% | 84.0% | 90.7% | 81.3% |
| sweet_sauce_level | 93.3% | 79.3% | 87.3% | 84.7% | 82.0% | 83.3% |
| tags | 98.0% | 85.3% | 85.3% | 81.3% | 76.7% | 78.0% |
| vegetable_ratio_estimate | 100.0% | 94.7% | 93.3% | 94.7% | 94.0% | 95.3% |
| wetness | 92.0% | 76.0% | 93.3% | 91.3% | 88.0% | 86.7% |

## 按类别切片(字段准确率 micro)

| 类别 | sonnet-4.6 | haiku-4.5 | deepseek-pro | deepseek-flash | kimi-k2.6 | glm-4.6 |
|---|---:|---:|---:|---:|---:|---:|
| 川湘菜 (sichuan_xiang) | 98.4% | 90.7% | 97.1% | 92.8% | 92.3% | 93.3% |
| 粤潮 (yue_chaoshan) | 96.7% | 88.0% | 94.0% | 93.3% | 93.0% | 90.0% |
| 江浙红烧/糖醋 (jiangzhe_sweet) | 98.7% | 91.6% | 98.2% | 95.6% | 96.4% | 96.0% |
| 日韩 (japan_korea) | 98.2% | 88.9% | 93.8% | 88.4% | 91.1% | 91.1% |
| 西式快餐 (western_fast) | 95.1% | 83.6% | 88.4% | 86.7% | 88.0% | 88.0% |
| 套餐组合 (combo) | 97.0% | 84.0% | 87.7% | 86.0% | 87.3% | 86.0% |
| 主食单点 (staple) | 97.8% | 86.2% | 90.2% | 88.0% | 87.6% | 85.3% |
| 配菜/汤/饮品/小食 (side_soup) | 95.1% | 86.2% | 92.4% | 90.7% | 88.4% | 88.9% |
| 边界对抗 (boundary) | 99.3% | 88.7% | 88.0% | 86.0% | 87.3% | 91.3% |

## 典型错误 case 抽样

### sonnet-4.6

**case 1**: `d009` 烧鸭腿拼叉烧饭+老火靓汤 (`yue_chaoshan`)
  - `canonical_name`: expected="烧鸭腿拼叉烧饭 含汤" predicted="烧鸭腿拼叉烧饭 含老火靓汤"
  - `main_ingredient_type`: expected="红肉" predicted="白肉"
  - `wetness`: expected=2 predicted=3

**case 2**: `d010` 蒜蓉辣椒酱 (`boundary`)
  - `spicy_level`: expected=2 predicted=0

**case 3**: `d017` 水煮鱼片 中辣 (`sichuan_xiang`)
  - `canonical_name`: expected="水煮鱼片" predicted="水煮鱼片 中辣"

**case 4**: `d018` 酸辣土豆丝 (`sichuan_xiang`)
  - `spicy_level`: expected=1 predicted=2
  - `wetness`: expected=1 predicted=2

**case 5**: `d019` 宫保鸡丁 (`sichuan_xiang`)
  - `sweet_sauce_level`: expected=2 predicted=1


### haiku-4.5

**case 1**: `d009` 烧鸭腿拼叉烧饭+老火靓汤 (`yue_chaoshan`)
  - `main_ingredient_type`: expected="红肉" predicted="白肉"
  - `wetness`: expected=2 predicted=3

**case 2**: `d010` 蒜蓉辣椒酱 (`boundary`)
  - `spicy_level`: expected=2 predicted=0

**case 3**: `d012` 回锅肉 (`sichuan_xiang`)
  - `protein_grams_estimate`: expected=25 predicted=35

**case 4**: `d013` 鱼香肉丝 (`sichuan_xiang`)
  - `spicy_level`: expected=2 predicted=1
  - `sweet_sauce_level`: expected=2 predicted=1
  - `protein_grams_estimate`: expected=20 predicted=30
  - `tags`: expected=["重口味", "下饭"] predicted=["高蛋白", "下饭"]

**case 5**: `d014` 毛血旺 (`sichuan_xiang`)
  - `cooking_method`: expected="煮" predicted="炒"
  - `wetness`: expected=3 predicted=2
  - `processed_meat_flag`: expected=true predicted=false


### deepseek-pro

**case 1**: `d009` 烧鸭腿拼叉烧饭+老火靓汤 (`yue_chaoshan`)
  - `wetness`: expected=2 predicted=3

**case 2**: `d010` 蒜蓉辣椒酱 (`boundary`)
  - `spicy_level`: expected=2 predicted=0

**case 3**: `d012` 回锅肉 (`sichuan_xiang`)
  - `wetness`: expected=1 predicted=2
  - `protein_grams_estimate`: expected=25 predicted=35

**case 4**: `d013` 鱼香肉丝 (`sichuan_xiang`)
  - `oil_level`: expected=4 predicted=3
  - `spicy_level`: expected=2 predicted=1

**case 5**: `d018` 酸辣土豆丝 (`sichuan_xiang`)
  - `wetness`: expected=1 predicted=2
  - `tags`: expected=["高纤维", "清淡", "适合减脂"] predicted=["下饭"]


### deepseek-flash

**case 1**: `d009` 烧鸭腿拼叉烧饭+老火靓汤 (`yue_chaoshan`)
  - `canonical_name`: expected="烧鸭腿拼叉烧饭 含汤" predicted="烧鸭腿拼叉烧饭+老火靓汤"
  - `wetness`: expected=2 predicted=3

**case 2**: `d010` 蒜蓉辣椒酱 (`boundary`)
  - `spicy_level`: expected=2 predicted=0

**case 3**: `d011` 麻婆豆腐 (`sichuan_xiang`)
  - `cooking_method`: expected="炒" predicted="炖"
  - `oil_level`: expected=4 predicted=3
  - `tags`: expected=["重口味", "下饭"] predicted=["下饭", "适合减脂"]

**case 4**: `d013` 鱼香肉丝 (`sichuan_xiang`)
  - `oil_level`: expected=4 predicted=3
  - `spicy_level`: expected=2 predicted=1

**case 5**: `d014` 毛血旺 (`sichuan_xiang`)
  - `processed_meat_flag`: expected=true predicted=false
  - `tags`: expected=["重口味", "油重", "汤水"] predicted=["高蛋白", "重口味", "下饭"]


### kimi-k2.6

**case 1**: `d009` 烧鸭腿拼叉烧饭+老火靓汤 (`yue_chaoshan`)
  - `wetness`: expected=2 predicted=3

**case 2**: `d010` 蒜蓉辣椒酱 (`boundary`)
  - `spicy_level`: expected=2 predicted=0

**case 3**: `d011` 麻婆豆腐 (`sichuan_xiang`)
  - `cooking_method`: expected="炒" predicted="炖"

**case 4**: `d013` 鱼香肉丝 (`sichuan_xiang`)
  - `spicy_level`: expected=2 predicted=1
  - `vegetable_ratio_estimate`: expected=0.3 predicted=0.4

**case 5**: `d014` 毛血旺 (`sichuan_xiang`)
  - `tags`: expected=["重口味", "油重", "汤水"] predicted=["重口味", "高蛋白", "下饭"]


### glm-4.6

**case 1**: `d011` 麻婆豆腐 (`sichuan_xiang`)
  - `cooking_method`: expected="炒" predicted="炖"

**case 2**: `d012` 回锅肉 (`sichuan_xiang`)
  - `protein_grams_estimate`: expected=25 predicted=35

**case 3**: `d013` 鱼香肉丝 (`sichuan_xiang`)
  - `spicy_level`: expected=2 predicted=1

**case 4**: `d014` 毛血旺 (`sichuan_xiang`)
  - `tags`: expected=["重口味", "油重", "汤水"] predicted=["高蛋白", "重口味", "下饭"]

**case 5**: `d016` 辣子鸡丁 (`sichuan_xiang`)
  - `cooking_method`: expected="炒" predicted="油炸"
  - `spicy_level`: expected=3 predicted=2


## 结论与建议

### 1. 三维度并列冠军

- **准确率冠军**:`sonnet-4.6` — 字段 97.3%, 整条全对 72.0%
- **成本冠军**:`deepseek-flash` — 100万条预估 $96
- **吞吐冠军**:`haiku-4.5` — concurrency=10 下 6.5 条/秒, 跑 10 万条仅需 ~297min

### 2. 关键字段分水岭

- **sweet_sauce_level**: 最好 `sonnet-4.6` (93.3%), 最差 `haiku-4.5` (79.3%), gap 14.0pp
- **processed_meat_flag**: 最好 `sonnet-4.6` (100.0%), 最差 `haiku-4.5` (96.0%), gap 4.0pp
- **dish_role**: 最好 `sonnet-4.6` (99.3%), 最差 `deepseek-flash` (94.7%), gap 4.7pp
- **grain_type**: 最好 `deepseek-flash` (99.3%), 最差 `glm-4.6` (95.3%), gap 4.0pp

### 3. 推荐生产模型 (按数据量与时间窗口)

生产场景的选型不能只看准确率/成本,**吞吐(完成时间)同等关键**——便宜但跑得慢的模型,几万条数据可能跑一整天.

| 场景 | 推荐 | 理由 |
|---|---|---|
| 数据量 ≤ 1万 / 时间敏感 | **`sonnet-4.6`** | 准确率最高 (97.3%), 1万条 $44.9 / 59.4min; 贵但快, 小批量首选 |
| 数据量 1万-10万 / 准确率可放宽 | **`haiku-4.5`** | 字段准确率 87.6%(距冠军 -9.7pp), 但吞吐 6.5 条/秒, 10万条 4.9h, $140 |
| 数据量 ≥ 10万 / 时间不敏感 | **`deepseek-flash`** | 100万条仅 $96 (冠军的 2.1%), 但 10万条要 43.7h, 准确率 90.0% |

### 4. 是否分层方案?

**不分层**:`sonnet-4.6` 已经接近 top (97.3% vs 97.3%, gap 0.0pp), 分层带来的边际收益不大.

### 5. 最终决策 (基于本次实测)

- 如果**只跑一次几千条 → `sonnet-4.6`**:准确率 97.3% + 速度最快档 + 一次性成本可接受
- 如果**几万条且要在 1 天内出结果 → `haiku-4.5`**:吞吐最快, 1 万条 $14 / 10 万条 $140, 准确率 87.6% 可被分层补救
- 如果**几十万条 + 离线异步 + 极致省钱 → `deepseek-flash`**:成本几乎可忽略, 但要忍受 43.7h/10万条的耗时

### 6. 已知风险/局限

- 无显著风险

---

*报告由 `scripts/make_report.py` 基于 `score_summary.json` 自动生成.*

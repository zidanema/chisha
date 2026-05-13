# Critical Rules — Dual-Model Golden Set Construction

Reference document, inline into every Codex S2 prompt as `<grounding_rules>`. Distills v3 prompt核心规则 + 25 条 dual-model spike 沉淀的新发现/优化点。

---

## 4 大易错字段(必须每条 dish 都 challenge)

| 字段 | 规则 |
|---|---|
| **sweet_sauce_level** (0-3) | 看到"烧/红/酱/糖/蜜/照/拔丝/京酱" → ≥ 2;"蜜/蜂蜜/拔丝/麦芽糖"→ 锚 3;中式烧腊(叉烧/烧鸭)→ 2;**回锅肉(甜面酱)→ 1**(spike 沉淀);**鱼香/宫保(汁含糖) → 1**(字面无锚但实际微甜)。LLM 倾向把非显式甜的菜打 0,这是错的 |
| **processed_meat_flag** (bool) | 中式烧腊(叉烧/烧鸭/烧鹅,无"腊"字)→ false(整块鲜肉熟制);腊肠/腊肉/培根/火腿/蟹柳/鱼丸/午餐肉/竹轮 → true;关东煮丸料拼盘 → true;鲜内脏(肥肠/鸭血)→ false;**麻辣香锅 default false**(菜单未明示丸料则保守 false,spike 沉淀);**毛血旺 default true**(固定含午餐肉,与麻辣香锅区别) |
| **dish_role** | 优先级:套餐 > 饮品 > 汤 > 主食 > 主菜 > 配菜 > 小食。触发"套餐"的词:套餐/定食/N+M/含饭/含面/拼盘/+饭/+饮料/+主食/+汤/+小菜/+蛋/+卤味/+甜品。**单点盖饭/烧腊饭/煲仔饭(无+触发词)= 主食**(不是套餐,与盖饭对齐);饺/包默认主食;汉堡/三明治 = 主食;西式蛋白碗(无谷物)= 主菜;凉菜大份蛋白足 → 主菜,纯素小份 → 配菜 |
| **grain_type** | 白米/糙米杂粮/精制面/全麦面/粗粮/粥/无(枚举固定 7 值,**不能写"其他"**)。米粉/河粉/粿条/肠粉 → 白米(高 GI);**红薯粉/绿豆粉/魔芋粉 → 白米**(精制淀粉高 GI 类推,spike 沉淀);复合套餐多主食取最精制;无谷物 → 无 |

---

## 6 个边界判定

1. **西式蛋白碗(无谷物)**: `is_complete_meal=true`(本就是一餐定位)+ `grain_type=无` + `dish_role=主菜` + `main_ingredient_type` 按蛋白源
2. **套餐含汤底升级**(名字明确"+汤/+老火靓汤/+鸡汤/+紫菜汤/+白粥"): 整套 `wetness=3`(不要按主菜降到 2)
3. **关东煮/卤味/钵钵鸡浸卤**: `wetness=2`(浸不喝,非 3。spike 沉淀:钵钵鸡浸卤汁等价关东煮)
4. **非食物兜底**(调料/餐具/赠品): `spicy_level=0`(强制,即使是辣椒酱)+ `dish_role=小食` + 全字段保守(oil=1, protein=0, vegetable=0, processed_meat=false, sweet_sauce=0, wetness=1, grain=无, is_complete_meal=false)
5. **中式烧腊系列**(整块鲜肉熟制): `processed_meat_flag=false` + `cooking_method=烤` + `sweet_sauce_level=2`(默认带糖)
6. **米制品**(粉/河粉/肠粉/粿条/红薯粉): `grain_type=白米`(高 GI 类推)

---

## LLM 幻觉防护

- `canonical_name` 必须从 `raw_name` 派生,不可凭空生成不相干菜名(已知 case:"恰巴塔 4 件套"曾被打成"烤鲜活鲍鱼")
- 同名菜不同价 = 不同分量,`protein_grams_estimate` 必须依赖 `price`(18 vs 36 元 protein 应至少差 15g)

---

## main_ingredient_type 命名 vs 体积主体优先级(spike 沉淀)

| 情形 | 归类 |
|---|---|
| 菜名包含明确蛋白源(如"番茄牛腩饭"/"酸豆角肉末")| 按蛋白源(红肉/白肉/海鲜),即使体积主体是蔬菜 |
| 菜名无蛋白源(如"麻婆豆腐"/"湘西外婆菜")| 按体积主体(豆制品 / 纯素) |
| 主食载体类(白菜水饺/皮蛋瘦肉粥)| 主食 |
| 复合多种蛋白源混合(关东煮/麻辣香锅/毛血旺)| 其他 或 主要蛋白源(看主体) |

---

## 已知 v3 prompt 内部矛盾(必须警惕)

**d010 示例 vs 规则冲突**:
- 第 169 行规则文字: "调料/餐具/赠品: ... spicy_level=0(即使是辣椒酱)"
- 第 311 行示例输出: `d010 "蒜蓉辣椒酱" ... spicy_level=2`
- **正确行为**: 按规则文字,不按示例。这是 dual-model golden set 的修复点

注:v3 prompt 已在 dual 流程中 patch 修复(spicy=2 → 0,新增红薯粉锚点,新增回锅肉甜面酱锚点)。

---

## Verdict 枚举(强制 Codex 输出格式)

S2 prompt 必须强制:`verdict` ∈ {"agree", "disagree", "uncertain"}。**不要**用 "CONFIRM" / "CHALLENGE" / "BORDERLINE" / "AGREE" 等变体——会增加 S3 解析负担。

---

## Spike 数据修正记录(可作 batch 重审 anchor)

| dish | 字段 | 旧值 | 新值 | 修正理由 |
|---|---|---|---|---|
| d010 | spicy_level | 2 | 0 | 非食物兜底规则强制 0(prompt 示例自身矛盾)|
| d012 | sweet_sauce_level | 0 | 1 | 回锅肉传统含甜面酱微甜 |
| d027 | wetness | 1 | 2 | 钵钵鸡浸卤等价关东煮规则 |
| d029 | main_ingredient_type | 纯素 | 红肉 | 菜名命名优先(含肉末 + protein 10g)|
| d169 | processed_meat_flag | true | false | 麻辣香锅菜单未明示丸料,保守 false |

---

## 一致裁决规则(S3 阶段)

- 全字段一致 → `consensus_status="agree"`
- Opus 接受 Codex 修正 → `consensus_status="codex_wins"`,记 `disagreement_fields=[...]`
- Opus 保留原值,Codex disagree 但 Opus 给出更强理由 → `consensus_status="opus_wins"`,记 `disagreement_fields=[...]`
- **4 大字段任一仍分歧不能解决** → `consensus_status="human_needed"` + `needs_review=true`,**不直接入库**
- Codex `uncertain` / `borderline` → 默认 Opus 维持,`consensus_status="agree"`(Codex 没主张就不算分歧)

---

## Schema 校验门(每条 final 必须通过)

- 15 字段齐全(REQUIRED_FIELDS:dish_id, canonical_name, cuisine, main_ingredient_type, cooking_method, oil_level, protein_grams_estimate, vegetable_ratio_estimate, is_complete_meal, spicy_level, dish_role, processed_meat_flag, sweet_sauce_level, wetness, grain_type, tags)
- `dish_role` ∈ {主菜, 主食, 配菜, 汤, 小食, 饮品, 套餐}
- `wetness` ∈ {1, 2, 3}
- `sweet_sauce_level` ∈ {0, 1, 2, 3}
- `processed_meat_flag` 是 bool
- `tags` 是 list
- `anchor_violations` 必须为空(用 `dual_pipeline.py:anchor_violations()` 校验 raw_name + expected)

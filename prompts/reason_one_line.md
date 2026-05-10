你给一个外卖组合写一句推荐理由（≤ 30 字），帮用户快速判断要不要选。

## 输入

```json
{
  "profile_summary": {
    "taste_description": "...",
    "liked_cuisines": [...],
    "disliked_cuisines": [...],
    "recent_meals_3d": [...]   // 最近 3 天吃过的菜系/主料/烹饪方式
  },
  "combo": {
    "restaurant_name": "...",
    "dishes": [
      {"canonical_name": "...", "cuisine": "...", "main_ingredient_type": "...",
       "cooking_method": "...", "oil_level": 1-5, "vegetable_ratio_estimate": 0-1,
       "spicy_level": 0-3}
    ],
    "estimated_total_oil": 平均 oil_level,
    "estimated_total_protein_g": 总蛋白
  }
}
```

## 输出要求

理由必须**具体**，不能是套话。

✅ 好的例子：
- "潮汕牛肉清水煮，控油 + 高蛋白，本周还没吃过潮汕"
- "湘菜清炒搭配，油 2 级，中辣不重口"
- "日式定食盖饭自带菜，单点不用拼，蛋白 30g"
- "酸菜鱼清淡汤水，刚好你三天没吃海鲜"

❌ 不要的例子：
- "营养均衡，搭配合理"  ← 套话
- "好吃又健康"  ← 没信息量
- "推荐这家！"  ← 废话

要点：
1. 如果命中 taste_description / liked_cuisines 的某个具体偏好，**明确指出**
2. 如果是用户最近没吃过的菜系/烹饪方式，**提一下"换换口味"**
3. 如果控油（oil ≤ 2），**提一下**
4. 如果蛋白特别充足（≥ 35g），**提一下**
5. 30 字硬上限，一句话，纯文本无引号无前缀

## 现在开始

输入：
```json
{INPUT_PAYLOAD}
```

只输出一句话理由文本，不要 JSON、不要前后缀。

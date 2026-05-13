# 精排员 user 消息模板 (D-046)
# rerank.py:build_user_message() 按这个骨架拼接, 不直接读这个 md;
# 这里只是给人看, 方便调 prompt 时对照.

[CONFIG] n={n} n_explore={n_explore}

[PROFILE]
口味描述: {taste_description}
喜欢: {liked_cuisines}
不喜欢: {disliked_cuisines}
avoid: {avoid_dishes}
辣度耐受: {spicy_tolerance}

[CONTEXT]
饭期: {meal_type}
心情: {daily_mood}
上顿: {last_meal_brief}
最近 3 天 cuisine: {recent_3d_cuisines}
最近 3 天 cooking: {recent_3d_methods}
上次反馈 chips: {last_feedback_chips}
refine 输入: {refine_input}

[CANDIDATES]
[0] 潮汕牛肉粥馆（2.1km/25min/L2 2.7/¥28.5）
  · 牛肉粥｜红肉·炖·油1·汤4｜role=主菜｜18.0
  · 凉拌青菜｜纯素·凉拌·油1｜8.5
  · 卤蛋｜白肉·卤·油1｜2.0
[1] Super Model（3.5km/30min/L2 2.9/¥38.6）
  · 烤鸡牛肉套餐｜白肉·烤·油3｜role=套餐｜32.8
  · 蒸贝贝南瓜｜纯素·蒸·油1·甜1｜2.8
  · 黑米饭｜主食·煮·grain=糙米杂粮·油1｜3.0
...

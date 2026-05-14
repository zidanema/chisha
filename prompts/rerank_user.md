# 精排员 user 消息样例
# 实际拼接见 chisha/rerank.py:build_user_message()
# 本文件不被代码读取, 仅供调 prompt 时人对照

[CONFIG] n={n} n_explore={n_explore}

[PROFILE]
口味描述: 想吃清淡, 多蔬菜多蛋白, 偶尔重口
喜欢: 粤菜 潮汕 日料
不喜欢: 川菜
avoid: 螺蛳粉
辣度耐受: 2

[CONTEXT]
饭期: lunch
心情: want_soup
上顿: dinner 川菜: 麻婆豆腐+米饭+紫菜蛋汤
最近 3 天 cuisine: 川菜×3 粤菜×2 日料×1
最近 3 天 cooking: 炒×4 炖×2 烤×1
上次反馈 chips: ["太油"]
refine 输入: (无)

[CANDIDATES]
[0] 潮汕牛肉粥馆（2.1km/25min/L2 2.7/¥28.5）
  · 牛肉粥｜红肉·炖·油1·汤4｜role=主菜｜18.0
  · 凉拌青菜｜纯素·凉拌·油1｜8.5
  · 卤蛋｜白肉·卤·油1｜2.0
[1] Super Model（3.5km/30min/L2 2.9/¥38.6）
  · 烤鸡牛肉套餐｜白肉·烤·油3｜role=套餐｜32.8
  · 蒸贝贝南瓜｜纯素·蒸·油1｜2.8
  · 黑米饭｜主食·煮·油1｜role=主食·grain=糙米杂粮｜3.0
...

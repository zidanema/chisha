"""150 条 golden set 的输入清单 (前 10 条 anchor + 后 140 条候选).

字段对齐 v3 prompt 期望: dish_id / raw_name / restaurant_name / restaurant_category_raw / category_raw / price.
分布严格按 eval_spec.md 第 4 节:
  sichuan_xiang 25 / yue_chaoshan 20 / jiangzhe_sweet 15 / japan_korea 15 /
  western_fast 15 / combo 20 / staple 15 / side_soup 15 / boundary 10 = 150
"""

ANCHOR_10 = [
    {"dish_id": "d001", "raw_name": "蒜蓉空心菜", "restaurant_name": "湘里湘亲",
     "restaurant_category_raw": "湘菜", "category_raw": "时蔬", "price": 18,
     "category_tag": "sichuan_xiang"},
    {"dish_id": "d002", "raw_name": "【新品】水煮牛肉(中辣) 大份", "restaurant_name": "蜀香源",
     "restaurant_category_raw": "川菜", "category_raw": None, "price": 58,
     "category_tag": "sichuan_xiang"},
    {"dish_id": "d003", "raw_name": "白菜水饺", "restaurant_name": "安天民北方饺子",
     "restaurant_category_raw": "", "category_raw": None, "price": 15.1,
     "category_tag": "staple"},
    {"dish_id": "d004", "raw_name": "潮汕牛肉粿条", "restaurant_name": "潮汕牛肉甘草水",
     "restaurant_category_raw": "潮汕", "category_raw": "招牌", "price": 32,
     "category_tag": "yue_chaoshan"},
    {"dish_id": "d005", "raw_name": "红烧排骨", "restaurant_name": "家常菜馆",
     "restaurant_category_raw": "江浙", "category_raw": None, "price": 38,
     "category_tag": "jiangzhe_sweet"},
    {"dish_id": "d006", "raw_name": "关东煮(蟹柳+鱼丸+午餐肉)", "restaurant_name": "便利店",
     "restaurant_category_raw": "日式", "category_raw": None, "price": 22,
     "category_tag": "japan_korea"},
    {"dish_id": "d007", "raw_name": "燕麦坚果碗", "restaurant_name": "Wagas",
     "restaurant_category_raw": "西式", "category_raw": "早餐", "price": 35,
     "category_tag": "western_fast"},
    {"dish_id": "d008", "raw_name": "紫菜蛋花汤", "restaurant_name": "湘里湘亲",
     "restaurant_category_raw": "湘菜", "category_raw": "汤", "price": 8,
     "category_tag": "side_soup"},
    {"dish_id": "d009", "raw_name": "烧鸭腿拼叉烧饭+老火靓汤", "restaurant_name": "粤式烧腊",
     "restaurant_category_raw": "粤菜", "category_raw": None, "price": 38,
     "category_tag": "yue_chaoshan"},
    {"dish_id": "d010", "raw_name": "蒜蓉辣椒酱", "restaurant_name": "湘里湘亲",
     "restaurant_category_raw": "湘菜", "category_raw": "调料", "price": 2,
     "category_tag": "boundary"},
]

# anchor 已知 expected,直接落库不调 sonnet
ANCHOR_EXPECTED = {
    "d001": {"canonical_name":"蒜蓉空心菜","cuisine":"湘菜","main_ingredient_type":"纯素","cooking_method":"炒","oil_level":3,"protein_grams_estimate":5,"vegetable_ratio_estimate":0.95,"is_complete_meal":False,"spicy_level":0,"dish_role":"配菜","processed_meat_flag":False,"sweet_sauce_level":0,"wetness":2,"grain_type":"无","tags":["高纤维","清淡","适合减脂"]},
    "d002": {"canonical_name":"水煮牛肉 大份","cuisine":"川菜","main_ingredient_type":"红肉","cooking_method":"煮","oil_level":5,"protein_grams_estimate":40,"vegetable_ratio_estimate":0.2,"is_complete_meal":False,"spicy_level":2,"dish_role":"主菜","processed_meat_flag":False,"sweet_sauce_level":0,"wetness":3,"grain_type":"无","tags":["高蛋白","重口味","下饭"]},
    "d003": {"canonical_name":"白菜水饺","cuisine":"东北","main_ingredient_type":"主食","cooking_method":"煮","oil_level":2,"protein_grams_estimate":10,"vegetable_ratio_estimate":0.3,"is_complete_meal":True,"spicy_level":0,"dish_role":"主食","processed_meat_flag":False,"sweet_sauce_level":0,"wetness":1,"grain_type":"精制面","tags":["清淡","高碳水"]},
    "d004": {"canonical_name":"潮汕牛肉粿条","cuisine":"潮汕","main_ingredient_type":"红肉","cooking_method":"煮","oil_level":2,"protein_grams_estimate":30,"vegetable_ratio_estimate":0.15,"is_complete_meal":True,"spicy_level":0,"dish_role":"主食","processed_meat_flag":False,"sweet_sauce_level":0,"wetness":3,"grain_type":"白米","tags":["高蛋白","清淡","汤水"]},
    "d005": {"canonical_name":"红烧排骨","cuisine":"江浙","main_ingredient_type":"红肉","cooking_method":"炖","oil_level":4,"protein_grams_estimate":35,"vegetable_ratio_estimate":0.1,"is_complete_meal":False,"spicy_level":0,"dish_role":"主菜","processed_meat_flag":False,"sweet_sauce_level":2,"wetness":2,"grain_type":"无","tags":["高蛋白","重口味","下饭"]},
    "d006": {"canonical_name":"关东煮 蟹柳+鱼丸+午餐肉","cuisine":"日式","main_ingredient_type":"其他","cooking_method":"煮","oil_level":2,"protein_grams_estimate":15,"vegetable_ratio_estimate":0.1,"is_complete_meal":False,"spicy_level":0,"dish_role":"小食","processed_meat_flag":True,"sweet_sauce_level":0,"wetness":2,"grain_type":"无","tags":["小份"]},
    "d007": {"canonical_name":"燕麦坚果碗","cuisine":"西式","main_ingredient_type":"主食","cooking_method":"生","oil_level":2,"protein_grams_estimate":10,"vegetable_ratio_estimate":0.1,"is_complete_meal":True,"spicy_level":0,"dish_role":"主食","processed_meat_flag":False,"sweet_sauce_level":1,"wetness":1,"grain_type":"粗粮","tags":["高纤维","适合减脂"]},
    "d008": {"canonical_name":"紫菜蛋花汤","cuisine":"湘菜","main_ingredient_type":"汤","cooking_method":"煮","oil_level":2,"protein_grams_estimate":5,"vegetable_ratio_estimate":0.3,"is_complete_meal":False,"dish_role":"汤","spicy_level":0,"processed_meat_flag":False,"sweet_sauce_level":0,"wetness":3,"grain_type":"无","tags":["清淡","汤水"]},
    "d009": {"canonical_name":"烧鸭腿拼叉烧饭 含汤","cuisine":"粤菜","main_ingredient_type":"红肉","cooking_method":"烤","oil_level":3,"protein_grams_estimate":35,"vegetable_ratio_estimate":0.1,"is_complete_meal":True,"spicy_level":0,"dish_role":"套餐","processed_meat_flag":False,"sweet_sauce_level":2,"wetness":2,"grain_type":"白米","tags":["高蛋白","下饭"]},
    "d010": {"canonical_name":"蒜蓉辣椒酱","cuisine":"其他","main_ingredient_type":"其他","cooking_method":"凉拌","oil_level":1,"protein_grams_estimate":0,"vegetable_ratio_estimate":0,"is_complete_meal":False,"spicy_level":2,"dish_role":"小食","processed_meat_flag":False,"sweet_sauce_level":0,"wetness":1,"grain_type":"无","tags":["小份"]},
}

# 140 条候选: (raw_name, restaurant_name, restaurant_category_raw, category_raw, price)
CANDIDATES = []

# === sichuan_xiang: 23 条 (川湘菜 - 炒/煮/水煮系列) ===
SICHUAN_XIANG = [
    ("麻婆豆腐", "蜀香源", "川菜", "招牌", 22),
    ("回锅肉", "蜀香源", "川菜", "热菜", 36),
    ("鱼香肉丝", "巴蜀人家", "川菜", "热菜", 32),
    ("毛血旺", "渝味晓宇", "川菜", "招牌", 48),
    ("夫妻肺片", "蜀香源", "川菜", "凉菜", 38),
    ("辣子鸡丁", "巴蜀人家", "川菜", "热菜", 42),
    ("水煮鱼片 中辣", "渝味晓宇", "川菜", "招牌", 68),
    ("酸辣土豆丝", "蜀香源", "川菜", "时蔬", 18),
    ("宫保鸡丁", "巴蜀人家", "川菜", "热菜", 32),
    ("辣椒炒肉", "湘里湘亲", "湘菜", "招牌", 35),
    ("剁椒鱼头 小份", "湘湘菜馆", "湘菜", "招牌", 58),
    ("湘西外婆菜", "湘里湘亲", "湘菜", "热菜", 26),
    ("农家小炒肉", "湘湘菜馆", "湘菜", "热菜", 32),
    ("干锅花菜", "湘里湘亲", "湘菜", "时蔬", 28),
    ("醋溜白菜", "湘湘菜馆", "湘菜", "时蔬", 16),
    ("酸辣粉", "蜀香源", "川菜", "小吃", 12),
    ("钵钵鸡 麻辣", "巴蜀人家", "川菜", "凉菜", 30),
    ("口水鸡", "蜀香源", "川菜", "凉菜", 36),
    ("酸豆角肉末", "湘里湘亲", "湘菜", "热菜", 22),
    ("尖椒肥肠", "湘湘菜馆", "湘菜", "招牌", 42),
    ("豆瓣鱼", "巴蜀人家", "川菜", "招牌", 58),
    ("酸菜鱼 大份", "渝味晓宇", "川菜", "招牌", 78),
    ("青椒土豆丝", "湘里湘亲", "湘菜", "时蔬", 14),
]
for i, (n, r, rc, c, p) in enumerate(SICHUAN_XIANG, start=11):
    CANDIDATES.append({"dish_id": f"d{i:03d}", "raw_name": n, "restaurant_name": r,
                       "restaurant_category_raw": rc, "category_raw": c, "price": p,
                       "category_tag": "sichuan_xiang"})

# === yue_chaoshan: 18 条 (粤菜潮汕 - 烧腊/汤粥/肠粉粿条) ===
YUE_CHAOSHAN = [
    ("叉烧饭", "粤式烧腊", "粤菜", "招牌", 28),
    ("烧鹅濑粉", "粤式烧腊", "粤菜", "招牌", 32),
    ("白切鸡", "顺德私房菜", "粤菜", "招牌", 38),
    ("豉油鸡腿饭", "粤式烧腊", "粤菜", "饭类", 26),
    ("及第粥", "潮汕粥铺", "潮汕", "粥品", 18),
    ("艇仔粥", "潮汕粥铺", "潮汕", "粥品", 16),
    ("生滚鱼片粥", "潮汕粥铺", "潮汕", "粥品", 22),
    ("鲜虾肠粉", "广式肠粉", "粤菜", "招牌", 18),
    ("叉烧肠粉", "广式肠粉", "粤菜", "招牌", 16),
    ("牛肉肠粉", "广式肠粉", "粤菜", "招牌", 18),
    ("潮汕牛肉丸粿条汤", "潮汕牛肉甘草水", "潮汕", "招牌", 28),
    ("沙茶牛肉炒河粉", "潮汕牛肉甘草水", "潮汕", "热菜", 32),
    ("白灼菜心", "顺德私房菜", "粤菜", "时蔬", 22),
    ("蜜汁叉烧 例", "粤式烧腊", "粤菜", "招牌", 38),
    ("老火例汤", "顺德私房菜", "粤菜", "汤品", 18),
    ("虾饺", "广式茶楼", "粤菜", "点心", 16),
    ("烧麦", "广式茶楼", "粤菜", "点心", 14),
    ("豉汁排骨蒸饭", "粤式烧腊", "粤菜", "招牌", 32),
]
for i, (n, r, rc, c, p) in enumerate(YUE_CHAOSHAN, start=34):
    CANDIDATES.append({"dish_id": f"d{i:03d}", "raw_name": n, "restaurant_name": r,
                       "restaurant_category_raw": rc, "category_raw": c, "price": p,
                       "category_tag": "yue_chaoshan"})

# === jiangzhe_sweet: 14 条 (江浙红烧/糖醋 - sweet_sauce 锚点) ===
JIANGZHE_SWEET = [
    ("糖醋里脊", "杭帮菜馆", "江浙", "招牌", 38),
    ("糖醋排骨", "杭帮菜馆", "江浙", "招牌", 42),
    ("红烧肉", "本帮菜馆", "江浙", "招牌", 48),
    ("红烧狮子头", "扬州人家", "江浙", "招牌", 32),
    ("无锡酱排骨", "本帮菜馆", "江浙", "招牌", 56),
    ("京酱肉丝", "京味斋", "京菜", "招牌", 36),
    ("红烧带鱼", "杭帮菜馆", "江浙", "热菜", 42),
    ("照烧鸡腿饭", "日式定食屋", "日式", "招牌", 36),
    ("拔丝山药", "杭帮菜馆", "江浙", "甜品", 28),
    ("糖醋鲤鱼", "鲁味斋", "鲁菜", "招牌", 68),
    ("东坡肉", "杭帮菜馆", "江浙", "招牌", 38),
    ("蜜汁烤翅", "西餐厅", "西式", "招牌", 32),
    ("红烧牛腩煲", "本帮菜馆", "江浙", "招牌", 56),
    ("梅菜扣肉", "客家小厨", "客家", "招牌", 42),
]
for i, (n, r, rc, c, p) in enumerate(JIANGZHE_SWEET, start=52):
    CANDIDATES.append({"dish_id": f"d{i:03d}", "raw_name": n, "restaurant_name": r,
                       "restaurant_category_raw": rc, "category_raw": c, "price": p,
                       "category_tag": "jiangzhe_sweet"})

# === japan_korea: 14 条 ===
JAPAN_KOREA = [
    ("三文鱼刺身 6片", "寿司の神", "日式", "刺身", 48),
    ("鳗鱼饭", "鳗料理", "日式", "招牌", 68),
    ("天妇罗虾", "日式定食屋", "日式", "炸物", 36),
    ("味噌拉面", "拉面之神", "日式", "招牌", 38),
    ("豚骨拉面", "拉面之神", "日式", "招牌", 42),
    ("石锅拌饭", "韩式料理", "韩式", "招牌", 32),
    ("部队火锅 单人", "韩式料理", "韩式", "招牌", 58),
    ("韩式炸鸡", "韩式料理", "韩式", "招牌", 42),
    ("辣白菜炒饭", "韩式料理", "韩式", "饭类", 26),
    ("寿喜烧定食", "日式定食屋", "日式", "招牌", 78),
    ("玉子烧", "日式定食屋", "日式", "前菜", 18),
    ("鸡肉亲子丼", "日式定食屋", "日式", "饭类", 32),
    ("韩式拌冷面", "韩式料理", "韩式", "招牌", 28),
    ("加州寿司卷 8件", "寿司の神", "日式", "寿司", 36),
]
for i, (n, r, rc, c, p) in enumerate(JAPAN_KOREA, start=66):
    CANDIDATES.append({"dish_id": f"d{i:03d}", "raw_name": n, "restaurant_name": r,
                       "restaurant_category_raw": rc, "category_raw": c, "price": p,
                       "category_tag": "japan_korea"})

# === western_fast: 14 条 ===
WESTERN_FAST = [
    ("巨无霸汉堡", "麦当劳", "西式", "汉堡", 28),
    ("芝士牛肉汉堡", "汉堡王", "西式", "汉堡", 32),
    ("鸡腿堡", "肯德基", "西式", "汉堡", 22),
    ("玛格丽特披萨 9寸", "披萨工坊", "西式", "披萨", 58),
    ("夏威夷披萨 12寸", "披萨工坊", "西式", "披萨", 88),
    ("意大利肉酱面", "意面工坊", "西式", "意面", 38),
    ("奶油培根意面", "意面工坊", "西式", "意面", 42),
    ("凯撒沙拉", "Wagas", "西式", "沙拉", 32),
    ("烤鸡胸沙拉碗", "Wagas", "西式", "沙拉", 38),
    ("墨西哥牛肉卷", "墨西哥餐厅", "西式", "招牌", 36),
    ("热狗", "便利店", "西式", "小吃", 12),
    ("火腿三明治", "Wagas", "西式", "早餐", 22),
    ("鸡肉三明治", "Subway", "西式", "招牌", 28),
    ("烤鸡蛋白碗", "Wagas", "西式", "早餐", 42),
]
for i, (n, r, rc, c, p) in enumerate(WESTERN_FAST, start=80):
    CANDIDATES.append({"dish_id": f"d{i:03d}", "raw_name": n, "restaurant_name": r,
                       "restaurant_category_raw": rc, "category_raw": c, "price": p,
                       "category_tag": "western_fast"})

# === combo: 20 条 (套餐组合 - dish_role=套餐 触发) ===
COMBO = [
    ("黄焖鸡米饭套餐+饮料", "黄焖鸡专门店", "中式", "套餐", 28),
    ("烤鱼套餐(鱼+饭+饮料+小菜)", "烤鱼店", "中式", "套餐", 78),
    ("沙县小吃A套餐 拌面+扁肉+卤蛋", "沙县小吃", "福建", "套餐", 22),
    ("兰州拉面+牛肉+小菜+饮料", "兰州拉面", "西北", "套餐", 32),
    ("麻辣烫套餐(荤素+饭)", "杨国福", "川菜", "套餐", 36),
    ("烤肉饭+饮料+汤", "韩式烤肉", "韩式", "套餐", 38),
    ("猪排咖喱饭套餐+饮料", "日式定食屋", "日式", "套餐", 42),
    ("蒸饺+米线+饮料", "中式快餐", "中式", "套餐", 28),
    ("肉夹馍+稀饭+小菜", "西安美食", "西北", "套餐", 22),
    ("螺蛳粉+卤蛋+酸笋+饮料", "广西螺蛳粉", "广西", "套餐", 32),
    ("披萨+鸡翅+可乐", "披萨工坊", "西式", "套餐", 68),
    ("汉堡套餐(汉堡+薯条+可乐)", "麦当劳", "西式", "套餐", 38),
    ("烧腊三拼饭+老火汤+饮料", "粤式烧腊", "粤菜", "套餐", 48),
    ("石锅拌饭+大酱汤+小菜", "韩式料理", "韩式", "套餐", 42),
    ("水煮鱼+米饭+蔬菜", "渝味晓宇", "川菜", "套餐", 78),
    ("酸菜鱼套餐 含饭", "酸菜鱼专门店", "川菜", "套餐", 42),
    ("牛肉粉+鸡蛋+卤味拼盘", "粉面馆", "中式", "套餐", 36),
    ("生鱼片定食(刺身+饭+味噌汤+小菜)", "寿司の神", "日式", "套餐", 68),
    ("黑椒牛仔骨+饭+汤", "西餐厅", "西式", "套餐", 58),
    ("台湾卤肉饭+卤蛋+青菜+汤", "台式料理", "台菜", "套餐", 32),
]
for i, (n, r, rc, c, p) in enumerate(COMBO, start=94):
    CANDIDATES.append({"dish_id": f"d{i:03d}", "raw_name": n, "restaurant_name": r,
                       "restaurant_category_raw": rc, "category_raw": c, "price": p,
                       "category_tag": "combo"})

# === staple: 14 条 (主食单点 - grain_type 全谱) ===
STAPLE = [
    ("猪肉大葱包子 4个", "包子铺", "中式", "主食", 12),
    ("小笼包 6个", "南翔小笼", "江浙", "点心", 22),
    ("葱油拌面", "上海老面馆", "江浙", "面食", 18),
    ("阳春面", "上海老面馆", "江浙", "面食", 14),
    ("牛肉拉面", "兰州拉面", "西北", "招牌", 26),
    ("炒河粉", "潮汕牛肉甘草水", "潮汕", "粉面", 22),
    ("桂林米粉", "广西米粉", "广西", "招牌", 18),
    ("皮蛋瘦肉粥", "潮汕粥铺", "潮汕", "粥品", 14),
    ("白米饭 大碗", "中式快餐", "中式", "主食", 4),
    ("糙米饭", "Wagas", "西式", "主食", 8),
    ("全麦面包 2片", "面包房", "西式", "早餐", 6),
    ("烤红薯", "街边小吃", "中式", "小吃", 8),
    ("玉米棒", "蒸菜店", "中式", "主食", 6),
    ("葱花鸡蛋饼", "早餐店", "中式", "早餐", 8),
]
for i, (n, r, rc, c, p) in enumerate(STAPLE, start=114):
    CANDIDATES.append({"dish_id": f"d{i:03d}", "raw_name": n, "restaurant_name": r,
                       "restaurant_category_raw": rc, "category_raw": c, "price": p,
                       "category_tag": "staple"})

# === side_soup: 14 条 (配菜/汤/饮品/小食) ===
SIDE_SOUP = [
    ("番茄蛋汤", "家常菜馆", "中式", "汤品", 8),
    ("冬瓜排骨汤", "广式煲汤", "粤菜", "汤品", 28),
    ("酸辣汤", "蜀香源", "川菜", "汤品", 12),
    ("味噌汤", "日式定食屋", "日式", "汤品", 8),
    ("白灼芥兰", "顺德私房菜", "粤菜", "时蔬", 18),
    ("清炒西兰花", "家常菜馆", "中式", "时蔬", 16),
    ("凉拌黄瓜", "家常菜馆", "中式", "凉菜", 10),
    ("拍黄瓜", "蜀香源", "川菜", "凉菜", 12),
    ("豆浆", "早餐店", "中式", "饮品", 4),
    ("冰美式咖啡", "咖啡店", "西式", "饮品", 18),
    ("珍珠奶茶", "茶饮店", "饮品", "饮品", 18),
    ("可乐 中杯", "麦当劳", "西式", "饮品", 8),
    ("烤鸡翅 3只", "韩式料理", "韩式", "小食", 18),
    ("毛豆", "啤酒屋", "中式", "小食", 10),
]
for i, (n, r, rc, c, p) in enumerate(SIDE_SOUP, start=128):
    CANDIDATES.append({"dish_id": f"d{i:03d}", "raw_name": n, "restaurant_name": r,
                       "restaurant_category_raw": rc, "category_raw": c, "price": p,
                       "category_tag": "side_soup"})

# === boundary: 9 条 (对抗/边界) ===
BOUNDARY = [
    ("【🔥 超值秒杀】爆款 第二份半价 红烧肉饭", "本帮菜馆", "江浙", "活动", 38),
    ("番茄沙司", "麦当劳", "西式", "调料", 2),
    ("一次性筷子套装(餐具)", "中式快餐", "中式", "餐具", 1),
    ("免费赠饮 柠檬水", "西餐厅", "西式", "赠品", 0),
    ("葱姜蒜调料包", "家常菜馆", "中式", "调料", 1),
    ("猪扒饭+冬阴功汤", "泰式餐厅", "泰式", "招牌", 38),  # 隐式套餐, 无"套餐"字样
    ("赣味辣椒炒鸡", "赣菜小馆", "赣菜", "招牌", 36),  # 赣菜归"其他"测试
    ("过桥米线", "云南米线", "云南", "招牌", 28),  # 云南归"其他"
    ("客家盐焗鸡", "客家小厨", "客家", "招牌", 48),  # 客家归"其他"
]
for i, (n, r, rc, c, p) in enumerate(BOUNDARY, start=142):
    CANDIDATES.append({"dish_id": f"d{i:03d}", "raw_name": n, "restaurant_name": r,
                       "restaurant_category_raw": rc, "category_raw": c, "price": p,
                       "category_tag": "boundary"})


def all_inputs():
    """返回完整 150 条 input (含 anchor)."""
    anchors = [{k: v for k, v in a.items()} for a in ANCHOR_10]
    return anchors + CANDIDATES


if __name__ == "__main__":
    items = all_inputs()
    print(f"total={len(items)}")
    from collections import Counter
    c = Counter(x["category_tag"] for x in items)
    for k in ["sichuan_xiang","yue_chaoshan","jiangzhe_sweet","japan_korea","western_fast","combo","staple","side_soup","boundary"]:
        print(f"  {k}: {c[k]}")
    assert len(items) == 150, f"expected 150, got {len(items)}"
    print("OK")

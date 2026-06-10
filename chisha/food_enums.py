"""餐食属性枚举单一权威源 (零依赖, pydantic-free).

D-112 Step2 抽出: 这些枚举原住 ``schemas.py``, 但那里顶层 ``import pydantic`` —— core
零 pydantic (D-105, 形态B bundle 只 vendored pyyaml, 不 ship pydantic)。agent 面的
``chisha profile`` 问卷映射 (``agent_profile_setup``) 要消费 cuisine / ingredient 枚举做
确定性分流, 不能经 ``schemas`` 把 pydantic 拉进 core 闭包 (破 D-104 di-boundary / 运行期
ImportError)。故枚举下沉到此零依赖模块, ``schemas`` 反向 import 回引 (back-compat), 问卷
映射也 import 这里 —— **单一源, 不漂移** (impl-plan risk 4.5)。

值集严格对齐 DESIGN §5.2, 改这里 = 改打标/召回/画像三方口径, 走对应决策。
"""
from __future__ import annotations

# 严格对齐 DESIGN §5.2 cuisine 枚举 (16 项, 不要扩展)
CUISINES = {
    "湘菜", "川菜", "粤菜", "潮汕", "东北", "西北", "江浙", "鲁菜",
    "日式", "韩式", "西式", "东南亚", "快餐", "小吃", "汤粥", "其他",
}

INGREDIENT_TYPES = {
    "红肉", "白肉", "海鲜", "蛋", "豆制品", "纯素", "主食", "汤", "其他",
}

COOKING_METHODS = {
    "蒸", "煮", "烤", "炒", "炖", "油炸", "凉拌", "生", "煎",
}

# v3 新增 (D-032)
DISH_ROLES = {
    "主菜", "主食", "配菜", "汤", "小食", "饮品", "套餐",
}

GRAIN_TYPES = {
    "白米", "糙米杂粮", "精制面", "全麦面", "粗粮", "粥", "无",
}

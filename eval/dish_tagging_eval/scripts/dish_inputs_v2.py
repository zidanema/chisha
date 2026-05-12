"""20 条对抗 case (d151-d170), 复用旧 ANCHOR_10 + 旧 CANDIDATES.

每条对应 plan 里的边界规则或已知幻觉, 用于扩充 dual-model golden set 的边界覆盖率.
build_golden_set_dual.py 通过 all_inputs_v2() 拿到 ANCHOR_10 + CANDIDATES + ADVERSARIAL_20.
"""
from dish_inputs import ANCHOR_10, ANCHOR_EXPECTED, CANDIDATES  # noqa: F401


_ADVERSARIAL_RAW = [
    ("d151", "虾饺", "广式茶楼分店", "粤菜", "点心", 28,
     "饺/包默认主食 + grain_type=精制面"),
    ("d152", "鲜虾肠粉", "广式肠粉店分店", "粤菜", "招牌", 18,
     "肠粉=白米 + wetness=2 (浸蒸但不喝)"),
    ("d153", "桂林米粉", "桂林米粉店", "广西", "招牌", 16,
     "米粉=白米 + 汤底wetness=3"),
    ("d154", "干炒牛河", "潮汕牛肉店分店", "粤菜", "热菜", 38,
     "河粉=白米 + 干炒 wetness=1"),
    ("d155", "牛排蛋白碗(无谷物 沙拉+牛排+牛油果+坚果)", "Wagas 分店", "西式", "蛋白碗", 58,
     "西式蛋白碗 is_complete_meal=true 即使无谷物, grain_type=无, dish_role=主菜"),
    ("d156", "关东煮 萝卜+魔芋+海带卷", "便利店分店", "日式", None, 18,
     "浸卤汁不喝 wetness=2, dish_role=小食"),
    ("d157", "番茄牛尾汤套餐(汤底+米饭+小菜)", "西式快餐", "西式", "套餐", 68,
     "套餐含汤底升级 整套 wetness=3, dish_role=套餐"),
    ("d158", "麻辣烫自选套餐(荤素+米线)", "杨国福分店", "川菜", "套餐", 35,
     "套餐+米制品: dish_role=套餐, grain_type=白米"),
    ("d159", "双拼烧腊饭(叉烧+烧鸭)", "粤式烧腊分店", "粤菜", "饭类", 42,
     "中式烧腊=整块鲜肉熟制 processed_meat_flag=false; 烧腊默认带糖 sweet_sauce_level=2"),
    ("d160", "广式腊肠煲仔饭", "煲仔饭专门店", "粤菜", "招牌", 36,
     "腊肠=腌制工业 processed_meat_flag=true; 煲仔饭=主食但单点不是套餐"),
    ("d161", "烟熏培根奶油意面", "意面工坊分店", "西式", "意面", 48,
     "培根=加工 processed_meat_flag=true"),
    ("d162", "蜜汁鸡翅", "西餐厅分店", "西式", "招牌", 32,
     "蜜汁→sweet_sauce_level=3 (锚到 3 不是 2)"),
    ("d163", "照烧三文鱼便当(+味噌汤+小菜)", "日式便当", "日式", "套餐", 55,
     "照烧 sweet_sauce=2; 便当+汤+小菜 dish_role=套餐"),
    ("d164", "拔丝地瓜", "杭帮菜分店", "江浙", "甜品", 22,
     "拔丝→sweet_sauce_level=3"),
    ("d165", "京酱肉丝(配薄饼)", "京味斋分店", "其他", "招牌", 34,
     "京酱→sweet_sauce_level=2; 京菜归其他(16 项无京菜)"),
    ("d166", "一次性筷子套装(餐具)", "中式快餐分店", "中式", "餐具", 0,
     "非食物兜底: spicy=0, dish_role=小食, protein=0, vegetable_ratio=0, oil=1"),
    ("d167", "老干妈油辣椒酱(单卖瓶装)", "便利店分店", "中式", "调料", 3,
     "调料兜底(对应 d010 已知 bug): spicy_level=0 即使是辣酱; dish_role=小食"),
    ("d168", "恰巴塔三明治 4 件套", "西式咖啡分店", "西式", "套餐", 48,
     "防 LLM 幻觉: canonical_name 不能凭空生成不相干菜名; cuisine=西式; 4 件套+三明治 dish_role=套餐"),
    ("d169", "麻辣香锅 单人份", "麻辣香锅店", "川菜", "套餐", 28,
     "price-aware: 单人份 protein 估 25g; 与 d169b 大份对比应 >=15g 差"),
    ("d169b", "麻辣香锅 双人份", "麻辣香锅店", "川菜", "套餐", 56,
     "price-aware: 双人份 ¥56 = 28×2, protein 应 ≈ 40-45g (比 d169 多 ≥15g)"),
    ("d170", "猪排咖喱饭套餐+冰红茶", "日式定食屋分店", "日式", "套餐", 42,
     "套餐 canonical 规则 (对应 d100): canonical_name='猪排咖喱饭套餐 含饮料', dish_role=套餐"),
]


ADVERSARIAL_20 = [
    {
        "dish_id": did,
        "raw_name": rn,
        "restaurant_name": rest,
        "restaurant_category_raw": rcat,
        "category_raw": cat,
        "price": price,
        "category_tag": "adversarial",
        "test_purpose": purpose,
    }
    for (did, rn, rest, rcat, cat, price, purpose) in _ADVERSARIAL_RAW
]


def all_inputs_v2():
    """ANCHOR_10 (含 expected) + CANDIDATES (140) + ADVERSARIAL_20 (21 records, 20 case slots)."""
    anchors = [{k: v for k, v in a.items()} for a in ANCHOR_10]
    advs = [{k: v for k, v in a.items() if k != "test_purpose"} for a in ADVERSARIAL_20]
    return anchors + CANDIDATES + advs


def adversarial_by_id():
    """方便 lookup: {dish_id: dish_record (含 test_purpose)}."""
    return {a["dish_id"]: a for a in ADVERSARIAL_20}


if __name__ == "__main__":
    items = all_inputs_v2()
    from collections import Counter
    c = Counter(x["category_tag"] for x in items)
    print(f"total records = {len(items)}")
    for k, v in sorted(c.items()):
        print(f"  {k}: {v}")
    print(f"adversarial unique slots = 20 (records = 21: d169 + d169b)")
    assert len(ADVERSARIAL_20) == 21, f"expected 21 records, got {len(ADVERSARIAL_20)}"
    # Check id uniqueness across all
    ids = [x["dish_id"] for x in items]
    assert len(set(ids)) == len(ids), "duplicate dish_id!"
    print("OK")

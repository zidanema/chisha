"""recall.py 单测."""
from tests.conftest import make_dish, make_restaurant
from chisha.recall import (
    hard_filter,
    diversity_filter,
    is_vegetable_dish,
    is_protein_dish,
    is_carb_dish,
    is_complete_meal,
    combo_passes_plate_rule,
    build_combos_for_restaurant,
    recall,
)


def test_is_vegetable_dish():
    assert is_vegetable_dish(make_dish(
        main_ingredient_type="纯素", vegetable_ratio_estimate=0.1
    ))
    assert is_vegetable_dish(make_dish(
        main_ingredient_type="主食", vegetable_ratio_estimate=0.7
    ))
    assert not is_vegetable_dish(make_dish(
        main_ingredient_type="红肉", vegetable_ratio_estimate=0.2
    ))


def test_is_protein_dish():
    assert is_protein_dish(make_dish(main_ingredient_type="红肉"))
    assert is_protein_dish(make_dish(main_ingredient_type="豆制品"))
    # 主食类但 protein 高也算
    assert is_protein_dish(make_dish(
        main_ingredient_type="主食", protein_grams_estimate=20
    ))
    assert not is_protein_dish(make_dish(
        main_ingredient_type="纯素", protein_grams_estimate=3
    ))


def test_hard_filter_avoid_dish(basic_profile):
    dishes = [
        make_dish(dish_id="d1", canonical_name="红烧肉"),
        make_dish(dish_id="d2", canonical_name="清炒空心菜",
                  main_ingredient_type="纯素", vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3),
    ]
    out, _ = hard_filter(dishes, basic_profile, set())
    assert {d["dish_id"] for d in out} =={"d2"}


def test_hard_filter_spicy(basic_profile):
    dishes = [
        make_dish(dish_id="d1", spicy_level=3),  # 重辣，超 tolerance=2
        make_dish(dish_id="d2", spicy_level=2),
    ]
    out, _ = hard_filter(dishes, basic_profile, set())
    assert {d["dish_id"] for d in out} =={"d2"}


def test_hard_filter_sales_missing_not_filtered(basic_profile):
    """销量缺失 (=0) 不参与过滤, 但显式低于 min 的会过滤."""
    dishes = [
        make_dish(dish_id="d1", monthly_sales=0),    # 缺失, 保留
        make_dish(dish_id="d2", monthly_sales=5),    # 显式 < 10, 过滤
        make_dish(dish_id="d3", monthly_sales=100),  # 保留
    ]
    out, _ = hard_filter(dishes, basic_profile, set())
    assert {d["dish_id"] for d in out} =={"d1", "d3"}


def test_hard_filter_unavailable(basic_profile):
    dishes = [
        make_dish(dish_id="d1", is_available=False),
        make_dish(dish_id="d2", is_available=True),
    ]
    out, _ = hard_filter(dishes, basic_profile, set())
    assert {d["dish_id"] for d in out} =={"d2"}


def test_diversity_filter_excludes_recent_restaurant(basic_profile):
    import datetime as dt
    today = dt.date(2026, 5, 11)
    meal_log = [{
        "timestamp": "2026-05-08T12:00:00",   # 3 天前
        "restaurant_id": "r_001",
        "dishes": [{"main_ingredient_type": "红肉"}],
    }]
    dishes = [
        # d1 餐厅在 7 天内吃过 → 过滤
        make_dish(dish_id="d1", restaurant_id="r_001",
                  main_ingredient_type="白肉"),
        # d2 餐厅没吃过, 主料用白肉 (避开 3d 红肉去重)
        make_dish(dish_id="d2", restaurant_id="r_002",
                  main_ingredient_type="白肉"),
    ]
    filtered, _ = diversity_filter(dishes, meal_log, basic_profile, today=today)
    assert {d["dish_id"] for d in filtered} == {"d2"}


def test_diversity_filter_excludes_recent_protein(basic_profile):
    import datetime as dt
    today = dt.date(2026, 5, 11)
    # 1 天前吃过红肉
    meal_log = [{
        "timestamp": "2026-05-10T12:00:00",
        "restaurant_id": "r_999",
        "dishes": [{"main_ingredient_type": "红肉"}],
    }]
    dishes = [
        make_dish(dish_id="d1", main_ingredient_type="红肉"),  # 3 天内重蛋白
        make_dish(dish_id="d2", main_ingredient_type="白肉"),
        make_dish(dish_id="d3", main_ingredient_type="纯素",
                  vegetable_ratio_estimate=0.95),  # 蔬菜不卡多样性
    ]
    filtered, _ = diversity_filter(dishes, meal_log, basic_profile, today=today)
    assert {d["dish_id"] for d in filtered} == {"d2", "d3"}


def test_combo_passes_plate_rule(basic_profile):
    veg = make_dish(dish_id="v",
                    main_ingredient_type="纯素",
                    vegetable_ratio_estimate=0.95,
                    protein_grams_estimate=3)
    meat = make_dish(dish_id="m", main_ingredient_type="红肉",
                     protein_grams_estimate=30)
    # 蔬菜 + 蛋白 → 通过
    assert combo_passes_plate_rule([veg, meat], basic_profile)
    # 只有蛋白 (无蔬菜) → 不通过
    assert not combo_passes_plate_rule([meat], basic_profile)
    # 只有蔬菜 (蛋白不足) → 不通过
    assert not combo_passes_plate_rule([veg], basic_profile)


def test_build_combos_for_restaurant(basic_profile):
    rest_dishes = [
        make_dish(dish_id="p1", main_ingredient_type="红肉",
                  protein_grams_estimate=30),
        make_dish(dish_id="v1", main_ingredient_type="纯素",
                  vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3),
        make_dish(dish_id="c1", main_ingredient_type="主食",
                  protein_grams_estimate=10),
    ]
    combos = build_combos_for_restaurant(rest_dishes, basic_profile, 5)
    assert len(combos) >= 1
    # 至少有一个 combo 包含蛋白和蔬菜
    has_full = any(
        any(d["dish_id"] == "p1" for d in c) and
        any(d["dish_id"] == "v1" for d in c)
        for c in combos
    )
    assert has_full


def test_build_combos_for_restaurant_output_order(basic_profile):
    """F-016 ④ 守门: 锁 combo 输出签名顺序 (route A 完整套餐先于 route B 灵活组合,
    去重保留首次出现代表). 拆嵌套重构的真风险不是"出不出 combo", 是"同一组 dish 谁先出现".
    """
    rest_dishes = [
        make_dish(dish_id="cm1", main_ingredient_type="红肉",
                  protein_grams_estimate=25, vegetable_ratio_estimate=0.5,
                  is_complete_meal=True, monthly_sales=500),
        make_dish(dish_id="p1", main_ingredient_type="白肉",
                  protein_grams_estimate=30, monthly_sales=300),
        make_dish(dish_id="v1", main_ingredient_type="纯素",
                  vegetable_ratio_estimate=0.95, protein_grams_estimate=3,
                  monthly_sales=200),
    ]
    combos = build_combos_for_restaurant(rest_dishes, basic_profile, 10)
    sigs = [tuple(d["dish_id"] for d in c) for c in combos]
    # 去重生效: 签名唯一
    assert len(sigs) == len(set(sigs))
    # 精确锁输出签名顺序 (route A 完整套餐 +蔬菜 先于 route B 灵活组合; cm1 单菜
    # 不过 plate_rule 故不单独出现). 拆嵌套重构若改了 append/sort/dedup 顺序此处即挂.
    assert sigs == [("cm1", "v1"), ("p1", "v1"), ("cm1", "p1", "v1")]


def test_recall_end_to_end(basic_profile):
    rest = make_restaurant("r_001", name="测试餐厅")
    dishes = [
        make_dish(dish_id="p1", restaurant_id="r_001",
                  main_ingredient_type="红肉",
                  protein_grams_estimate=30),
        make_dish(dish_id="v1", restaurant_id="r_001",
                  main_ingredient_type="纯素",
                  vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3),
    ]
    combos = recall(basic_profile, [rest], dishes, [])
    assert len(combos) >= 1
    assert combos[0]["restaurant"]["id"] == "r_001"

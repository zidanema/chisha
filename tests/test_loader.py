"""loader.py 单测."""
from chisha.loader import (
    parse_monthly_sales,
    parse_distance_m,
    parse_eta_min,
    normalize,
    extract_brand,
    restaurant_rid,
    dish_id_for,
)


def test_extract_brand():
    assert extract_brand("安天民北方饺子（侨香店）") == "安天民北方饺子"
    assert extract_brand("湘小小长沙菜(景田北店)") == "湘小小长沙菜"
    assert extract_brand("十二茶") == "十二茶"
    assert extract_brand("Some Cafe [总店]") == "Some Cafe"
    # 关键: 品牌后缀差异同店应同 brand
    assert (extract_brand("安天民北方饺子（侨香店）")
            == extract_brand("安天民北方饺子馆（景田店）"))
    assert extract_brand("某餐厅店") == "某餐厅"  # 多次后缀剥离


def test_parse_monthly_sales():
    assert parse_monthly_sales("月售1000+") == 1000
    assert parse_monthly_sales("月售200+") == 200
    assert parse_monthly_sales("月售1") == 1
    assert parse_monthly_sales("月售42") == 42
    assert parse_monthly_sales("") == 0
    assert parse_monthly_sales(None) == 0


def test_parse_distance_m():
    assert parse_distance_m("504m") == 504
    assert parse_distance_m("1.2km") == 1200
    assert parse_distance_m("2km") == 2000
    assert parse_distance_m("") == -1
    assert parse_distance_m(None) == -1


def test_parse_eta_min():
    assert parse_eta_min("约15分钟") == 15
    assert parse_eta_min("约30分钟") == 30
    assert parse_eta_min("约1小时") == 60
    assert parse_eta_min("约1.5小时") == 90
    assert parse_eta_min("") == -1
    assert parse_eta_min(None) == -1


def test_normalize_basic():
    raw = {
        "restaurants": [
            {
                "name": "测试餐厅",
                "category": "",
                "monthly_sales": "月售500+",
                "rating": 4.5,
                "delivery_fee": 3.0,
                "min_order": 20.0,
                "delivery_time": "约25分钟",
                "distance": "800m",
                "menu_status": "full",
                "menu_count": 2,
                "menu": [
                    {"name": "白菜水饺", "price": 15.1, "category": "主食",
                     "monthly_sales": "月售200+"},
                    {"name": "辣椒炒肉", "price": 46, "category": None,
                     "monthly_sales": "月售27"},
                ],
            }
        ]
    }
    rests, dishes, conflicts, _nd = normalize(raw, office_zone="test-zone")
    assert len(rests) == 1
    rid = restaurant_rid("测试餐厅")
    assert rests[0]["id"] == rid          # 稳定哈希 id (D-099), 不再是 r_001
    assert rid.startswith("r_") and len(rid) == 12
    assert rests[0]["monthly_orders"] == 500
    assert rests[0]["distance_m"] == 800
    assert rests[0]["delivery_eta_min"] == 25
    assert rests[0]["office_zone"] == "test-zone"
    assert rests[0]["category"] == ""  # 待回填
    assert conflicts == []
    assert len(dishes) == 2
    by_name = {d["raw_name"]: d for d in dishes}
    assert by_name["白菜水饺"]["dish_id"] == dish_id_for(rid, "白菜水饺")
    assert by_name["白菜水饺"]["restaurant_id"] == rid
    assert by_name["白菜水饺"]["price"] == 15.1
    assert by_name["白菜水饺"]["monthly_sales"] == 200
    assert by_name["辣椒炒肉"]["dish_id"] == dish_id_for(rid, "辣椒炒肉")
    assert by_name["辣椒炒肉"]["monthly_sales"] == 27

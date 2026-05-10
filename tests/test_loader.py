"""loader.py 单测."""
from chisha.loader import (
    parse_monthly_sales,
    parse_distance_m,
    parse_eta_min,
    normalize,
    extract_brand,
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
    rests, dishes = normalize(raw, office_zone="test-zone")
    assert len(rests) == 1
    assert rests[0]["id"] == "r_001"
    assert rests[0]["monthly_orders"] == 500
    assert rests[0]["distance_m"] == 800
    assert rests[0]["delivery_eta_min"] == 25
    assert rests[0]["office_zone"] == "test-zone"
    assert rests[0]["category"] == ""  # 待回填
    assert len(dishes) == 2
    assert dishes[0]["dish_id"] == "d_001_001"
    assert dishes[0]["restaurant_id"] == "r_001"
    assert dishes[0]["raw_name"] == "白菜水饺"
    assert dishes[0]["price"] == 15.1
    assert dishes[0]["monthly_sales"] == 200
    assert dishes[1]["dish_id"] == "d_001_002"
    assert dishes[1]["monthly_sales"] == 27

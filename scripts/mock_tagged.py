"""手工 mock 一份 tagged dishes (从 dishes_raw.json 选 50 条 + 估算字段).

仅用于 LLM API key 不可用时验证管道。真实打标用 scripts/tag_dishes.py.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 关键词 → cuisine 简易映射 (mock 用)
CUISINE_KW = [
    ("饺子", "东北"), ("水饺", "东北"), ("锅包肉", "东北"),
    ("地三鲜", "东北"), ("酱骨", "东北"), ("拉皮", "东北"),
    ("潮汕", "潮汕"), ("粿条", "潮汕"), ("肠粉", "粤菜"),
    ("烧鹅", "粤菜"), ("叉烧", "粤菜"),
    ("水煮", "川菜"), ("麻辣", "川菜"), ("宫保", "川菜"),
    ("回锅", "川菜"), ("鱼香", "川菜"), ("麻婆", "川菜"),
    ("辣椒炒肉", "湘菜"), ("剁椒", "湘菜"), ("小炒", "湘菜"),
    ("攸县", "湘菜"), ("湘", "湘菜"),
    ("寿司", "日式"), ("拉面", "日式"), ("丼", "日式"),
    ("定食", "日式"), ("照烧", "日式"), ("天妇罗", "日式"),
    ("沙拉", "轻食健康"), ("轻食", "轻食健康"),
    ("汤", "汤粥"), ("粥", "汤粥"),
]

# 名称特征 → main_ingredient_type
INGREDIENT_KW = [
    (("牛", "羊", "猪", "肉", "排骨", "腩"), "红肉"),
    (("鸡", "鸭"), "白肉"),
    (("鱼", "虾", "蟹", "鱿鱼", "扇贝", "海鲜", "鲈鱼"), "海鲜"),
    (("蛋", "煎蛋", "蒸蛋"), "蛋"),
    (("豆腐", "豆干", "豆", "腐竹"), "豆制品"),
    (("饺子", "水饺", "面", "饭", "粥", "粉", "饼", "包子",
      "馒头", "卷", "馍", "粿条"), "主食"),
    (("汤",), "汤"),
]

# 烹饪方式
COOKING_KW = [
    ("炸", "油炸"), ("油爆", "油炸"), ("酥", "油炸"),
    ("烤", "烤"), ("铁板", "烤"),
    ("蒸", "蒸"), ("白灼", "煮"), ("煮", "煮"),
    ("炖", "炖"), ("红烧", "炖"), ("焖", "炖"),
    ("拌", "凉拌"), ("凉", "凉拌"),
    ("煎", "煎"),
    ("炒", "炒"),
]

# 油脂规则
def estimate_oil(name: str, cooking: str) -> int:
    if "油炸" in cooking or "炸" in name or "酥" in name:
        return 5
    if "炖" in cooking or "红烧" in name or "焖" in name or "干煸" in name:
        return 4
    if "炒" in cooking or "孜然" in name or "铁板" in name:
        return 3
    if "煎" in cooking:
        return 3
    if "煮" in cooking or "蒸" in cooking or "白灼" in name:
        return 2
    if "凉拌" in cooking:
        return 1
    return 3


def detect_cuisine(name: str, restaurant_name: str) -> str:
    text = f"{restaurant_name} {name}"
    for kw, cui in CUISINE_KW:
        if kw in text:
            return cui
    if "饺子" in restaurant_name:
        return "东北"
    return "其他"


def detect_ingredient(name: str) -> str:
    for kws, ing in INGREDIENT_KW:
        for kw in kws:
            if kw in name:
                return ing
    return "其他"


def detect_cooking(name: str) -> str:
    for kw, c in COOKING_KW:
        if kw in name:
            return c
    return "炒"


def detect_spicy(name: str) -> int:
    if "变态辣" in name or "重辣" in name or "特辣" in name:
        return 3
    if "中辣" in name or "麻辣" in name or "水煮" in name or "干煸" in name:
        return 2
    if "微辣" in name or "辣椒" in name or "椒" in name:
        return 1
    return 0


def estimate_protein(name: str, ing: str, price: float) -> int:
    base = {"红肉": 30, "白肉": 25, "海鲜": 22,
            "蛋": 12, "豆制品": 18, "纯素": 3,
            "主食": 10, "汤": 8, "其他": 8}.get(ing, 8)
    # 价格修正: 30 元为基线
    if price > 0:
        base = int(base * min(2.0, max(0.5, price / 30)))
    return base


def estimate_veg_ratio(name: str, ing: str) -> float:
    if ing == "纯素":
        return 0.95
    if "蔬" in name or "菜" in name and "牛" not in name and "肉" not in name:
        return 0.7
    if any(k in name for k in ["白菜", "空心菜", "油麦菜", "西兰花",
                                "土豆丝", "黄瓜", "拉皮", "凉菜",
                                "豆角", "杏鲍菇", "云耳", "莴笋",
                                "茄", "玉米", "蘑菇"]):
        if "肉" in name:
            return 0.5
        return 0.85
    if "饺" in name or "饭" in name or "面" in name:
        if any(k in name for k in ["白菜", "韭菜", "芹菜", "西葫芦"]):
            return 0.3
        return 0.1
    if ing in ("红肉", "白肉", "海鲜"):
        return 0.1
    if ing == "汤":
        return 0.4
    return 0.2


def detect_complete_meal(name: str, ing: str) -> bool:
    if any(k in name for k in ["盖饭", "套餐", "便当", "定食",
                                "大碗", "粿条"]):
        return True
    if ing == "主食" and any(k in name for k in
                             ["水饺", "肉饺", "饺子", "盖饭", "面"]):
        # 水饺套餐 / 蛋饺也算
        return True
    return False


def canonicalize(name: str) -> str:
    n = re.sub(r"【.*?】", "", name)
    n = re.sub(r"\(.*?\)", "", n)
    n = re.sub(r"（.*?）", "", n)
    n = re.sub(r"[🌶️🔥✨]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def mock_tag_one(d: dict, rest: dict) -> dict:
    name = d["raw_name"]
    rest_name = rest["name"]
    canon = canonicalize(name)
    cuisine = detect_cuisine(name, rest_name)
    ing = detect_ingredient(name)
    cooking = detect_cooking(name)
    oil = estimate_oil(name, cooking)
    spicy = detect_spicy(name)
    protein = estimate_protein(name, ing, d.get("price", 0))
    veg_ratio = estimate_veg_ratio(name, ing)
    complete = detect_complete_meal(name, ing)

    tags = []
    if protein >= 30:
        tags.append("高蛋白")
    if oil <= 2:
        tags.append("低脂")
    if veg_ratio >= 0.7:
        tags.append("高纤维")
    if oil >= 4:
        tags.append("油重")
    if spicy >= 2:
        tags.append("重口味")
    if "汤" in name:
        tags.append("汤水")

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "dish_id": d["dish_id"],
        "restaurant_id": d["restaurant_id"],
        "raw_name": name,
        "canonical_name": canon,
        "price": d["price"],
        "monthly_sales": d["monthly_sales"],
        "cuisine": cuisine,
        "nutrition_profile": {
            "main_ingredient_type": ing,
            "cooking_method": cooking,
            "oil_level": oil,
            "protein_grams_estimate": protein,
            "vegetable_ratio_estimate": veg_ratio,
            "is_complete_meal": complete,
            "spicy_level": spicy,
            "tags": tags,
        },
        "metadata": {
            "tagged_at": now,
            "tag_version": "v1-mock",
            "is_available": True,
        },
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("zone")
    ap.add_argument("--out", default="dishes_tagged.json",
                    help="输出文件名 (默认 dishes_tagged.json, "
                    "想 spike 用 dishes_tagged_sample.json)")
    args = ap.parse_args()

    base = ROOT / "data" / args.zone
    rests = json.loads((base / "restaurants.json").read_text(encoding="utf-8"))
    rest_idx = {r["id"]: r for r in rests}
    raw = json.loads((base / "dishes_raw.json").read_text(encoding="utf-8"))

    tagged = [mock_tag_one(d, rest_idx[d["restaurant_id"]])
              for d in raw if d["restaurant_id"] in rest_idx]

    out_path = base / args.out
    out_path.write_text(
        json.dumps(tagged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"mock-tagged {len(tagged)} dishes → {out_path}")
    print("\n注意: 这是规则 mock, 准确率明显低于 LLM, 仅用于管道验证.")
    print("LLM key 到位后请用: uv run python -m scripts.tag_dishes "
          f"{args.zone}")


if __name__ == "__main__":
    main()

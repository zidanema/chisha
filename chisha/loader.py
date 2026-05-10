"""raw collector data → §5.2 schema 映射.

输入: chisha-collector 输出的 home/office_restaurants.json
输出: restaurants.json (§5.2) + dishes_raw.json (§5.2 待打标版)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def parse_monthly_sales(s: str | None) -> int:
    """月售1000+ → 1000 (取下界); 月售42 → 42; 空/None → 0."""
    if not s:
        return 0
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else 0


def parse_distance_m(s: str | None) -> int:
    """504m → 504; 1.2km → 1200; 空/None → -1 (未知)."""
    if not s:
        return -1
    s = s.strip().lower()
    m = re.match(r"([\d.]+)\s*(km|m)?", s)
    if not m:
        return -1
    val = float(m.group(1))
    unit = m.group(2) or "m"
    return int(val * 1000) if unit == "km" else int(val)


def parse_eta_min(s: str | None) -> int:
    """约15分钟 → 15; 约1小时 → 60; 约1.5小时 → 90; 空/None → -1."""
    if not s:
        return -1
    m = re.search(r"([\d.]+)\s*(小时|分钟|min|h)", s)
    if not m:
        return -1
    val = float(m.group(1))
    unit = m.group(2)
    return int(val * 60) if unit in ("小时", "h") else int(val)


def load_raw(raw_path: str | Path) -> dict[str, Any]:
    """读 collector 原始 JSON."""
    with open(raw_path, encoding="utf-8") as f:
        return json.load(f)


_BRAND_SUFFIX_TOKENS = ("馆", "店", "店铺", "餐厅", "食堂", "总店", "分店",
                        "旗舰店", "大酒店")


def extract_brand(name: str) -> str:
    """去括号分店 + 去尾部'馆/店/餐厅'类后缀，提取品牌名.

    '安天民北方饺子（侨香店）' → '安天民北方饺子'
    '安天民北方饺子馆（景田店）' → '安天民北方饺子'
    '湘小小长沙菜(景田北店)' → '湘小小长沙菜'
    """
    n = re.sub(r"\s*[（(][^)）]*[)）]\s*$", "", name)
    n = re.sub(r"\s*\[[^\]]*\]\s*$", "", n)
    n = n.strip()
    # 去尾部品牌后缀（最多迭代 2 次，比如"X 餐厅店"两次）
    for _ in range(2):
        for suf in sorted(_BRAND_SUFFIX_TOKENS, key=len, reverse=True):
            if n.endswith(suf) and len(n) > len(suf) + 1:
                n = n[: -len(suf)].strip()
                break
        else:
            break
    return n or name


def normalize(
    raw: dict[str, Any],
    office_zone: str,
    city: str = "深圳",
) -> tuple[list[dict], list[dict]]:
    """raw → (restaurants_normalized, dishes_raw_flat).

    restaurants[i].category 暂留空，由 LLM 打标后 majority vote 回填。
    """
    restaurants_out: list[dict] = []
    dishes_out: list[dict] = []
    for i, r in enumerate(raw.get("restaurants", []), start=1):
        rid = f"r_{i:03d}"
        name = r.get("name", "")
        restaurants_out.append({
            "id": rid,
            "name": name,
            "brand": extract_brand(name),
            "category": "",  # 待 majority vote 回填
            "city": city,
            "office_zone": office_zone,
            "rating": r.get("rating") or 0.0,
            "monthly_orders": parse_monthly_sales(r.get("monthly_sales")),
            "distance_m": parse_distance_m(r.get("distance")),
            "delivery_eta_min": parse_eta_min(r.get("delivery_time")),
            "delivery_fee": r.get("delivery_fee") or 0.0,
            "min_order": r.get("min_order") or 0.0,
            "raw_menu_count": r.get("menu_count", 0),
            "raw_menu_status": r.get("menu_status", "unknown"),
        })
        for j, m in enumerate(r.get("menu", []) or [], start=1):
            dishes_out.append({
                "dish_id": f"d_{i:03d}_{j:03d}",
                "restaurant_id": rid,
                "raw_name": m.get("name", ""),
                "price": float(m.get("price") or 0.0),
                "monthly_sales": parse_monthly_sales(m.get("monthly_sales")),
                "category_raw": m.get("category"),  # 商家自定义分组，仅参考
            })
    return restaurants_out, dishes_out


def write_normalized(
    raw_path: str | Path,
    out_dir: str | Path,
    office_zone: str,
    city: str = "深圳",
) -> tuple[Path, Path]:
    """跑全流程: 读 raw → normalize → 写 restaurants.json + dishes_raw.json."""
    raw = load_raw(raw_path)
    restaurants, dishes = normalize(raw, office_zone=office_zone, city=city)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rest_path = out_dir / "restaurants.json"
    dish_path = out_dir / "dishes_raw.json"
    rest_path.write_text(
        json.dumps(restaurants, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    dish_path.write_text(
        json.dumps(dishes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return rest_path, dish_path


def majority_cuisine(dishes_tagged: list[dict], restaurant_id: str) -> str:
    """从 tagged dishes 给 restaurant 投票 majority cuisine."""
    from collections import Counter
    cuisines = [
        d.get("cuisine", "")
        for d in dishes_tagged
        if d.get("restaurant_id") == restaurant_id and d.get("cuisine")
    ]
    if not cuisines:
        return ""
    return Counter(cuisines).most_common(1)[0][0]


def backfill_restaurant_category(
    restaurants_path: str | Path,
    dishes_tagged_path: str | Path,
) -> int:
    """读 dishes_tagged.json → majority vote → 回填 restaurants.json.category. 返回更新条数."""
    rest_path = Path(restaurants_path)
    restaurants = json.loads(rest_path.read_text(encoding="utf-8"))
    dishes_tagged = json.loads(Path(dishes_tagged_path).read_text(encoding="utf-8"))
    updated = 0
    for r in restaurants:
        cuisine = majority_cuisine(dishes_tagged, r["id"])
        if cuisine and r.get("category") != cuisine:
            r["category"] = cuisine
            updated += 1
    rest_path.write_text(
        json.dumps(restaurants, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return updated


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: python -m chisha.loader <raw_path> <office_zone> [city]")
        sys.exit(1)
    raw_path = sys.argv[1]
    zone = sys.argv[2]
    city = sys.argv[3] if len(sys.argv) > 3 else "深圳"
    out_dir = Path(__file__).parent.parent / "data" / zone
    rp, dp = write_normalized(raw_path, out_dir, zone, city)
    rest = json.loads(rp.read_text(encoding="utf-8"))
    dishes = json.loads(dp.read_text(encoding="utf-8"))
    print(f"normalized: {len(rest)} restaurants, {len(dishes)} dishes")
    print(f"  → {rp}")
    print(f"  → {dp}")

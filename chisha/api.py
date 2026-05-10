"""recommend_meal 主入口 (DESIGN §5.7).

V1 简化版: 召回 → 打分 → top 3 (带多样性) → LLM 写 reason → §5.7 JSON.
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
from pathlib import Path

from chisha.reason import annotate_reasons
from chisha.recall import (
    load_meal_log,
    load_profile,
    load_zone_data,
    recall,
)
from chisha.score import diversify_top, rank_combos


def _gen_session_id(meal_type: str) -> str:
    today = dt.datetime.now().strftime("%Y%m%d")
    return f"{today}_{meal_type}_{secrets.token_hex(2)}"


def _format_candidate(rank: int, c: dict) -> dict:
    rest = c["restaurant"]
    dishes = c["dishes"]
    dish_objs = [
        {
            "dish_id": d["dish_id"],
            "canonical_name": d["canonical_name"],
            "price": d["price"],
            "main_ingredient_type":
                d["nutrition_profile"]["main_ingredient_type"],
            "oil_level": d["nutrition_profile"]["oil_level"],
        }
        for d in dishes
    ]
    total_price = sum(d["price"] for d in dishes)
    avg_oil = round(
        sum(d["nutrition_profile"]["oil_level"] for d in dishes)
        / max(1, len(dishes)), 1
    )
    veg_count = sum(
        1 for d in dishes
        if d["nutrition_profile"]["main_ingredient_type"] == "纯素"
        or d["nutrition_profile"]["vegetable_ratio_estimate"] >= 0.6
    )
    total_protein = sum(
        d["nutrition_profile"]["protein_grams_estimate"] for d in dishes
    )
    return {
        "rank": rank,
        "is_explore": False,           # V1 不做探索
        "summary": " + ".join(d["canonical_name"] for d in dishes),
        "restaurant": {
            "id": rest["id"],
            "name": rest["name"],
            "distance_m": rest.get("distance_m", -1),
            "eta_min": rest.get("delivery_eta_min", -1),
        },
        "dishes": dish_objs,
        "total_price": round(total_price, 1),
        "vegetable_dish_count": veg_count,
        "estimated_total_oil": avg_oil,
        "estimated_total_protein_g": total_protein,
        "score": round(c["score"], 3),
        "reason_one_line": c.get("reason_one_line", ""),
    }


def _resolve_zone(profile: dict, meal_type: str) -> str:
    """优先用 basics.zones.{meal_type}, 退化到 basics.office_zone."""
    zones = profile.get("basics", {}).get("zones") or {}
    if meal_type in zones:
        return zones[meal_type]
    return profile["basics"]["office_zone"]


def recommend_meal(
    meal_type: str = "lunch",
    profile_path: str | Path = "profile.yaml",
    today: dt.date | None = None,
    log_to_file: bool = True,
) -> dict:
    """主入口. 返回 §5.7 JSON dict."""
    root = Path(__file__).resolve().parent.parent
    profile = load_profile(Path(profile_path) if Path(profile_path).is_absolute()
                           else root / profile_path)
    zone = _resolve_zone(profile, meal_type)
    rests, tagged = load_zone_data(zone, root)
    meal_log = load_meal_log(root)

    today = today or dt.date.today()
    session_id = _gen_session_id(meal_type)

    # 1. 召回
    combos = recall(profile, rests, tagged, meal_log, today)
    # 2. 打分排序
    ranked = rank_combos(combos, profile, meal_log, today)
    # 3. 多样性 top 3 (按品牌+菜系去重，避免同连锁霸榜)
    top = diversify_top(ranked, n=3, max_per_brand=1, max_per_cuisine=2)
    # 4. LLM 写理由
    top = annotate_reasons(top, profile, meal_log)

    out = {
        "session_id": session_id,
        "meal_type": meal_type,
        "zone": zone,
        "round": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stats": {
            "n_dishes_total": len(tagged),
            "n_combos_recalled": len(combos),
            "n_combos_after_score": len(ranked),
        },
        "candidates": [_format_candidate(i + 1, c) for i, c in enumerate(top)],
    }

    if log_to_file:
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "recommend_log.jsonl"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out


if __name__ == "__main__":
    import sys
    meal = sys.argv[1] if len(sys.argv) > 1 else "lunch"
    out = recommend_meal(meal)
    print(json.dumps(out, ensure_ascii=False, indent=2))

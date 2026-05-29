"""D-104 Step 1a: agent-only core 的 card / session 格式化 helper (从 api 抽出).

这些是 agent cards 真正需要的纯函数, 与 recommend_meal 全链路 / rich trace 渲染解耦。
零 debug/web/自调LLM 依赖: 仅用 stdlib + lazy core (clock / recall.dish_price)。
函数体与原 api.py 逐字一致 (D-104 行为 0-diff)。
"""
from __future__ import annotations

import secrets

# Codex PR-2 DEFER #5: schema 与 trace_store 序列化严格一致的单一权威源
# (D-104 Step1a: 从 api 挪来, 消除 trace_store→api 的 core→extras 隐边).
_SCORING_NUTRITION_KEYS = {
    "oil_level", "spicy_level", "wetness", "sweet_sauce_level", "processed_meat_flag",
    "main_ingredient_type", "vegetable_ratio_estimate", "protein_grams_estimate",
    "cooking_method", "dish_role", "grain_type", "is_complete_meal", "tags",
}


def _gen_session_id(meal_type: str) -> str:
    """生成 session_id. D-079 Codex FIX-NOW: 随机段从 16-bit (4hex) 扩到 64-bit
    (16hex) 防并发 sid 撞名 + tmp 文件竞态. 单用户场景 Phase 0 实际不会撞,
    但 token_hex(8) 几乎零代价让 PR-2/Phase 1 多端访问也安全.
    """
    from chisha import clock
    today = clock.now().strftime("%Y%m%d")
    return f"{today}_{meal_type}_{secrets.token_hex(8)}"


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
    from chisha.recall import dish_price
    total_price = sum(dish_price(d) for d in dishes)
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
        "is_explore": False,
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


def _format_v2_candidate(rank: int, c: dict) -> dict:
    """V2 candidate 格式化: 复用 _format_candidate 字段, 加上 rerank 字段."""
    base = _format_candidate(rank, c)
    base["rank"] = c.get("rank", rank)
    base["is_explore"] = bool(c.get("is_explore", False))
    base["fit_score"] = c.get("fit_score")
    base["health_flags"] = c.get("health_flags") or {}
    base["taste_match"] = c.get("taste_match")
    base["risk_flags"] = c.get("risk_flags") or []
    base["reason_one_line"] = c.get("one_line_reason") or c.get("reason_one_line", "")
    # 前端 (apps/web) 的 Candidate.id: 用 combo_index + restaurant.id 合成稳定 key
    rest_id = (c.get("restaurant") or {}).get("id", "?")
    combo_idx = c.get("combo_index", rank)
    base["id"] = f"c_{combo_idx}_{rest_id}"
    return base


# 暴露给 web_api / 外部调用方:
format_v2_candidate = _format_v2_candidate

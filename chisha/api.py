"""recommend_meal 主入口 (DESIGN §5.7).

V1 简化版: 召回 → 打分 → top 3 (带多样性) → LLM 写 reason → §5.7 JSON.
V2 (D-033): build_context → 召回 → score V2 (~12维) → LLM rerank top30→5
            (3 exploit + 2 explore) → 创建 session → §5.7 JSON.

入口 recommend_meal(version="v1") 兼容 V1; recommend_meal(version="v2") 走 V2.
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
from pathlib import Path

from chisha.context import build_context
from chisha.reason import annotate_reasons
from chisha.recall import (
    load_meal_log,
    load_profile,
    load_zone_data,
    recall,
)
from chisha.rerank import rerank as v2_rerank
from chisha.score import apply_caps, diversify_top, rank_combos
from chisha.session import create_session, save_session


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


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent


def recommend_meal(
    meal_type: str = "lunch",
    profile_path: str | Path = "profile.yaml",
    today: dt.date | None = None,
    log_to_file: bool = True,
    version: str = "v1",
    daily_mood: str | None = None,
    use_llm_rerank: bool | None = None,
    root: Path | None = None,
) -> dict:
    """主入口. 返回 §5.7 JSON dict.

    Args:
        version: "v1" (D-024 取打分 top 3 + LLM 写 reason) 或
                 "v2" (D-033 LLM 精排 top30→5 + Context + session).
        daily_mood: V2 才用. ContextSnapshot.daily_mood, 见 chisha/context.DAILY_MOODS.
        use_llm_rerank: V2 才用. None=auto (任意 LLM provider 可用即开, D-047).
        root: 仓库根目录 (测试可注入), 默认 chisha/__file__.parent.parent.
    """
    if version == "v2":
        return _recommend_meal_v2(
            meal_type=meal_type,
            profile_path=profile_path,
            today=today,
            log_to_file=log_to_file,
            daily_mood=daily_mood,
            use_llm_rerank=use_llm_rerank,
            root=root,
        )

    root = root or _default_root()
    profile = load_profile(Path(profile_path) if Path(profile_path).is_absolute()
                           else root / profile_path)
    zone = _resolve_zone(profile, meal_type)
    rests, tagged = load_zone_data(zone, root)
    meal_log = load_meal_log(root)

    today = today or dt.date.today()
    session_id = _gen_session_id(meal_type)

    # 1. 召回
    combos = recall(profile, rests, tagged, meal_log, today, meal_type=meal_type)
    # 2. 打分排序 + 三层 cap (D-043: restaurant + cuisine + food_form)
    ranked = rank_combos(combos, profile, meal_log, today, root=root)
    ranked = apply_caps(ranked, profile)
    # 3. 多样性 top 3 (按品牌+菜系去重，避免同连锁霸榜)
    top = diversify_top(ranked, n=3, max_per_brand=1, max_per_cuisine=2)
    # 4. LLM 写理由
    top = annotate_reasons(top, profile, meal_log)

    out = {
        "session_id": session_id,
        "meal_type": meal_type,
        "zone": zone,
        "round": 1,
        "version": "v1",
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


def _recommend_meal_v2(
    meal_type: str,
    profile_path: str | Path,
    today: dt.date | None,
    log_to_file: bool,
    daily_mood: str | None,
    use_llm_rerank: bool | None,
    root: Path | None = None,
) -> dict:
    """V2 主路径 (D-033): build_context → recall → score V2 → rerank → session."""
    root = root or _default_root()
    profile = load_profile(Path(profile_path) if Path(profile_path).is_absolute()
                           else root / profile_path)
    zone = _resolve_zone(profile, meal_type)
    rests, tagged = load_zone_data(zone, root)
    meal_log = load_meal_log(root)

    today = today or dt.date.today()
    session_id = _gen_session_id(meal_type)

    # 1. Context 注入 (D-034)
    ctx = build_context(profile, meal_log, meal_type, today,
                        daily_mood=daily_mood, refine_input=None)
    # 2. 召回
    combos = recall(profile, rests, tagged, meal_log, today, meal_type=meal_type)
    # 3. V2 打分 (~12 维, 含 context) + 三层 cap (D-043)
    ranked = rank_combos(combos, profile, meal_log, today,
                          context=ctx, meal_type=meal_type, root=root)
    ranked = apply_caps(ranked, profile)
    # 4. LLM 精排 topK → 5 (3 exploit + 2 explore, D-015; D-046: 30 → 60)
    from chisha.rerank import L3_INPUT_TOP_K
    top_k = ranked[:L3_INPUT_TOP_K]
    reranked = v2_rerank(top_k, profile, context=ctx, meal_log=meal_log,
                          n=5, n_explore=2, refine=False, use_llm=use_llm_rerank)
    # 5. 创建 session (供 refine 二轮用)
    state = create_session(session_id, meal_type, zone, daily_mood=daily_mood)
    state.last_candidates = [_minimize_candidate(c) for c in reranked]
    save_session(state, root)

    out = {
        "session_id": session_id,
        "meal_type": meal_type,
        "zone": zone,
        "round": 1,
        "version": "v2",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "context": ctx.to_llm_dict(),
        "stats": {
            "n_dishes_total": len(tagged),
            "n_combos_recalled": len(combos),
            "n_combos_after_score": len(ranked),
            "n_returned": len(reranked),
        },
        "candidates": [_format_v2_candidate(i + 1, c)
                        for i, c in enumerate(reranked)],
    }

    if log_to_file:
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "recommend_log.jsonl"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out


def _format_v2_candidate(rank: int, c: dict) -> dict:
    """V2 candidate 格式化: 复用 V1 _format_candidate 字段, 加上 rerank 的 V2 字段."""
    base = _format_candidate(rank, c)
    base["rank"] = c.get("rank", rank)
    base["is_explore"] = bool(c.get("is_explore", False))
    base["fit_score"] = c.get("fit_score")
    base["health_flags"] = c.get("health_flags") or {}
    base["taste_match"] = c.get("taste_match")
    base["risk_flags"] = c.get("risk_flags") or []
    base["reason_one_line"] = c.get("one_line_reason") or c.get("reason_one_line", "")
    return base


def _minimize_candidate(c: dict) -> dict:
    """session.last_candidates 用的精简版."""
    return {
        "rank": c.get("rank"),
        "is_explore": c.get("is_explore"),
        "fit_score": c.get("fit_score"),
        "restaurant": {"id": (c.get("restaurant") or {}).get("id"),
                        "name": (c.get("restaurant") or {}).get("name")},
        "dish_names": [d.get("canonical_name", "")
                        for d in c.get("dishes", [])],
    }


if __name__ == "__main__":
    import sys
    meal = sys.argv[1] if len(sys.argv) > 1 else "lunch"
    version = sys.argv[2] if len(sys.argv) > 2 else "v1"
    out = recommend_meal(meal, version=version)
    print(json.dumps(out, ensure_ascii=False, indent=2))

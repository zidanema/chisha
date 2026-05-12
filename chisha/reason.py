"""LLM 写一句话理由 (V1 唯一 LLM 用途, D-024).

无 LLM key 时退化到 fallback rule-based 文案,保证管道不断.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "prompts" / "reason_one_line.md"


def _recent_meals_summary(meal_log: list[dict],
                          today: dt.date | None = None,
                          days: int = 3) -> list[dict]:
    today = today or dt.date.today()
    out = []
    for log in meal_log[-30:]:
        try:
            ts = dt.datetime.fromisoformat(log["timestamp"]).date()
        except Exception:
            continue
        if (today - ts).days > days:
            continue
        for x in log.get("dishes", []):
            out.append({
                "cuisine": x.get("cuisine"),
                "main_ingredient_type": x.get("main_ingredient_type"),
                "cooking_method": x.get("cooking_method"),
            })
    return out[-10:]


def build_payload(combo: dict, profile: dict, meal_log: list[dict]) -> dict:
    dishes = combo["dishes"]
    return {
        "profile_summary": {
            "taste_description": profile.get("taste_description", ""),
            "liked_cuisines": profile["preferences"].get("liked_cuisines", []),
            "disliked_cuisines":
                profile["preferences"].get("disliked_cuisines", []),
            "recent_meals_3d": _recent_meals_summary(meal_log),
        },
        "combo": {
            "restaurant_name": combo["restaurant"]["name"],
            "dishes": [
                {
                    "canonical_name": d["canonical_name"],
                    "cuisine": d.get("cuisine", ""),
                    "main_ingredient_type":
                        d["nutrition_profile"]["main_ingredient_type"],
                    "cooking_method":
                        d["nutrition_profile"]["cooking_method"],
                    "oil_level": d["nutrition_profile"]["oil_level"],
                    "vegetable_ratio_estimate":
                        d["nutrition_profile"]["vegetable_ratio_estimate"],
                    "spicy_level": d["nutrition_profile"]["spicy_level"],
                }
                for d in dishes
            ],
            "estimated_total_oil": round(
                sum(d["nutrition_profile"]["oil_level"] for d in dishes)
                / max(1, len(dishes)), 1),
            "estimated_total_protein_g": sum(
                d["nutrition_profile"]["protein_grams_estimate"]
                for d in dishes),
        },
    }


def fallback_reason(combo: dict, profile: dict, meal_log: list[dict]) -> str:
    """无 LLM key 时的 rule-based fallback. 保证管道有输出."""
    dishes = combo["dishes"]
    avg_oil = sum(d["nutrition_profile"]["oil_level"] for d in dishes) / len(dishes)
    total_p = sum(d["nutrition_profile"]["protein_grams_estimate"] for d in dishes)
    cuisines = list({d.get("cuisine", "") for d in dishes if d.get("cuisine")})
    liked = set(profile["preferences"].get("liked_cuisines", []))
    bits = []
    if cuisines and set(cuisines) & liked:
        hit = next(c for c in cuisines if c in liked)
        bits.append(f"{hit}你的菜")
    if avg_oil <= 2:
        bits.append(f"低油{avg_oil:.1f}级")
    elif avg_oil <= 3:
        bits.append("家常油度")
    if total_p >= 35:
        bits.append(f"蛋白{int(total_p)}g")
    elif total_p >= 25:
        bits.append("蛋白达标")
    if not bits:
        bits.append("控油+蔬菜+蛋白")
    return "，".join(bits)[:30]


def llm_reason(combo: dict, profile: dict, meal_log: list[dict]) -> str:
    """调 LLM 写理由. 无 key 时返回 fallback."""
    from chisha.llm_client import call_text, has_llm_key
    if not has_llm_key():
        return fallback_reason(combo, profile, meal_log)
    try:
        payload = build_payload(combo, profile, meal_log)
        prompt = PROMPT_PATH.read_text(encoding="utf-8").replace(
            "{INPUT_PAYLOAD}", json.dumps(payload, ensure_ascii=False)
        )
        text = call_text(prompt, max_tokens=128, temperature=0.0)
        # 清理可能的引号、前缀
        text = text.strip().strip('"\'').strip()
        # 截 30 字
        return text[:30]
    except Exception as e:
        print(f"  [reason fallback] LLM 失败 ({type(e).__name__}: "
              f"{str(e)[:80]}), 用规则文案")
        return fallback_reason(combo, profile, meal_log)


def annotate_reasons(
    top: list[dict], profile: dict, meal_log: list[dict]
) -> list[dict]:
    """给 top 候选每条加 reason_one_line 字段."""
    out = []
    for c in top:
        c2 = dict(c)
        c2["reason_one_line"] = llm_reason(c, profile, meal_log)
        out.append(c2)
    return out

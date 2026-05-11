"""LLM 精排 (D-035): top30 candidates → 5 个候选 (3 exploit + 2 explore).

输入: 打分后 top30 combos + ContextSnapshot + profile + meal_log 摘要.
输出: list[dict], 每条 candidate 含强制结构化字段:
    rank / is_explore / combo_index / fit_score / health_flags /
    taste_match / risk_flags / one_line_reason

LLM 失败 → fallback (规则) 退化到打分 top n + 规则 reason, 保证管道不断.
refine=True 时 n_explore=0 (D-015).

注: 本模块依赖 schema 升级后的 5 字段 (dish_role / processed_meat_flag /
sweet_sauce_level / soup_or_broth_flag / grain_type), 字段缺失时 LLM/规则
都会返回保守值 (空 health_flags), 不破坏管道.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chisha.context import ContextSnapshot

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "prompts" / "rerank_topn.md"


# 输出 schema 必填字段
_REQUIRED_FIELDS = {
    "rank", "is_explore", "combo_index",
    "fit_score", "health_flags", "taste_match",
    "risk_flags", "one_line_reason",
}


def build_payload(
    top_combos: list[dict],
    profile: dict,
    context: "ContextSnapshot | None",
    meal_log: list[dict] | None,
    n: int,
    n_explore: int,
) -> dict:
    """打包 LLM rerank 输入."""
    candidates = []
    for idx, c in enumerate(top_combos):
        rest = c.get("restaurant", {})
        candidates.append({
            "combo_index": idx,
            "restaurant": {
                "name": rest.get("name", ""),
                "cuisine": rest.get("category", ""),
                "distance_m": rest.get("distance_m", -1),
                "eta_min": rest.get("delivery_eta_min", -1),
            },
            "dishes": [
                {
                    "canonical_name": d.get("canonical_name", ""),
                    "cuisine": d.get("cuisine", ""),
                    "price": d.get("price", 0),
                    "main_ingredient_type":
                        d["nutrition_profile"].get("main_ingredient_type", ""),
                    "cooking_method":
                        d["nutrition_profile"].get("cooking_method", ""),
                    "oil_level": d["nutrition_profile"].get("oil_level", 3),
                    "spicy_level": d["nutrition_profile"].get("spicy_level", 0),
                    # V2 5 字段
                    "dish_role": d["nutrition_profile"].get("dish_role"),
                    "processed_meat_flag":
                        d["nutrition_profile"].get("processed_meat_flag", False),
                    "sweet_sauce_level":
                        d["nutrition_profile"].get("sweet_sauce_level"),
                    "soup_or_broth_flag":
                        d["nutrition_profile"].get("soup_or_broth_flag", False),
                    "grain_type": d["nutrition_profile"].get("grain_type"),
                }
                for d in c.get("dishes", [])
            ],
            "total_price": sum(d.get("price", 0) for d in c.get("dishes", [])),
            "score": round(c.get("score", 0), 3),
        })

    payload: dict[str, Any] = {
        "config": {"n": n, "n_explore": n_explore},
        "profile": {
            "taste_description": profile.get("taste_description", ""),
            "liked_cuisines": profile["preferences"].get("liked_cuisines", []),
            "disliked_cuisines": profile["preferences"].get("disliked_cuisines", []),
            "avoid_dishes": profile["preferences"].get("avoid_dishes", []),
            "spicy_tolerance": profile["preferences"].get("spicy_tolerance", 2),
        },
        "context": context.to_llm_dict() if context else None,
        "candidates": candidates,
    }
    return payload


def fallback_rerank(
    top_combos: list[dict],
    n: int = 5,
    n_explore: int = 2,
) -> list[dict[str, Any]]:
    """规则 fallback: 取打分 top (n - n_explore) 当 exploit (品牌+菜系多样性去重),
    中段 n_explore 个当 explore. 每条用最简结构化字段填占位, 不调 LLM.
    """
    if not top_combos:
        return []
    from chisha.score import diversify_top
    n_exploit = max(1, n - n_explore)
    # exploit: 用 diversify_top 强制品牌/菜系多样性 (复用 V1 行为)
    exploit = diversify_top(top_combos, n=n_exploit, max_per_brand=1,
                             max_per_cuisine=2)
    # explore: 跳过已用的, 在剩余打分中段取
    used_ids = {id(c) for c in exploit}
    rest = [c for c in top_combos if id(c) not in used_ids]
    if rest and n_explore > 0:
        mid_start = max(0, len(rest) // 4)
        explore = rest[mid_start:mid_start + n_explore]
    else:
        explore = []

    out: list[dict] = []
    rank = 1
    for c in exploit:
        out.append(_to_rerank_dict(c, rank, is_explore=False, fit_score=c.get("score", 0)))
        rank += 1
    for c in explore:
        out.append(_to_rerank_dict(c, rank, is_explore=True, fit_score=c.get("score", 0) * 0.8))
        rank += 1
    return out


def _to_rerank_dict(combo: dict, rank: int, is_explore: bool,
                    fit_score: float) -> dict[str, Any]:
    """combo + meta → rerank 输出 dict (含 _REQUIRED_FIELDS)."""
    dishes = combo.get("dishes", [])
    veg_ok = any(
        (d.get("nutrition_profile") or {}).get("vegetable_ratio_estimate", 0) >= 0.6
        or (d.get("nutrition_profile") or {}).get("main_ingredient_type") == "纯素"
        for d in dishes
    )
    total_p = sum(
        (d.get("nutrition_profile") or {}).get("protein_grams_estimate", 0)
        for d in dishes
    )
    avg_oil = (
        sum((d.get("nutrition_profile") or {}).get("oil_level", 3) for d in dishes)
        / max(1, len(dishes))
    )
    has_processed = any(
        (d.get("nutrition_profile") or {}).get("processed_meat_flag")
        for d in dishes
    )
    has_soup = any(
        (d.get("nutrition_profile") or {}).get("soup_or_broth_flag")
        for d in dishes
    )
    sweet = any(
        (d.get("nutrition_profile") or {}).get("sweet_sauce_level") in {"high", 3, "3"}
        for d in dishes
    )
    return {
        **combo,
        "rank": rank,
        "is_explore": is_explore,
        "combo_index": combo.get("combo_index", -1),
        "fit_score": round(float(fit_score), 3),
        "health_flags": {
            "veg_ok": veg_ok,
            "protein_ok": total_p >= 25,
            "oil_ok": avg_oil <= 3,
            "processed_meat": has_processed,
            "sweet_sauce": sweet,
            "soup_or_broth": has_soup,
        },
        "taste_match": None,        # rule fallback 不做语义匹配
        "risk_flags": [],
        "one_line_reason": _rule_reason(combo, has_soup, avg_oil, total_p),
    }


def _rule_reason(combo: dict, has_soup: bool, avg_oil: float, total_p: float) -> str:
    bits = []
    if has_soup:
        bits.append("汤水清爽")
    if avg_oil <= 2:
        bits.append(f"低油{avg_oil:.1f}")
    if total_p >= 30:
        bits.append(f"蛋白{int(total_p)}g")
    elif total_p >= 25:
        bits.append("蛋白达标")
    if not bits:
        bits.append("结构合规")
    return "，".join(bits)[:30]


def _llm_rerank(payload: dict, model: str | None = None) -> list[dict] | None:
    """调 LLM 返回 list of candidate dict, 失败返回 None (上游 fallback)."""
    try:
        from chisha.llm_client import call_text
        prompt = PROMPT_PATH.read_text(encoding="utf-8").replace(
            "{INPUT_PAYLOAD}", json.dumps(payload, ensure_ascii=False, indent=2)
        )
        kwargs: dict[str, Any] = {"max_tokens": 4096, "temperature": 0.0}
        if model:
            kwargs["model"] = model
        out = call_text(prompt, **kwargs)
        # 提 JSON
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        cands = data.get("candidates")
        if not isinstance(cands, list):
            return None
        # 校验必填字段
        for c in cands:
            missing = _REQUIRED_FIELDS - set(c)
            if missing:
                print(f"  [rerank] LLM 输出缺字段 {missing}, 退 fallback")
                return None
        return cands
    except Exception as e:
        print(f"  [rerank fallback] LLM 失败 ({type(e).__name__}: {str(e)[:80]})")
        return None


def rerank(
    top_combos: list[dict],
    profile: dict,
    context: "ContextSnapshot | None" = None,
    meal_log: list[dict] | None = None,
    n: int = 5,
    n_explore: int = 2,
    refine: bool = False,
    use_llm: bool | None = None,
    model: str | None = None,
) -> list[dict]:
    """主入口. LLM 精排 + fallback.

    Args:
        top_combos: 打分后已排序的 candidates (top 30 推荐, 但传更多也可).
        profile / context / meal_log: 见 build_payload.
        n: 输出候选数, 默认 5.
        n_explore: explore 候选数, 默认 2 (D-015).
        refine: True 时 n_explore=0 (D-015).
        use_llm: 强制开关. None=auto (看 ANTHROPIC_API_KEY).
    """
    if not top_combos:
        return []
    if refine:
        n_explore = 0
    if use_llm is None:
        use_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if use_llm:
        payload = build_payload(top_combos, profile, context, meal_log, n, n_explore)
        llm_out = _llm_rerank(payload, model=model)
        if llm_out is not None:
            # 把 combo_index 映射回原 combo, 取出真实 combo dict 拼接 LLM 字段
            mapped: list[dict] = []
            for cand in llm_out[:n]:
                idx = cand.get("combo_index", -1)
                if not (0 <= idx < len(top_combos)):
                    continue
                merged = {**top_combos[idx], **cand}
                mapped.append(merged)
            if mapped:
                return mapped
            # llm_out 全部 idx 越界 → fallback

    return fallback_rerank(top_combos, n=n, n_explore=n_explore)

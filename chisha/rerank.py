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
                    "wetness": d["nutrition_profile"].get("wetness"),
                    "grain_type": d["nutrition_profile"].get("grain_type"),
                }
                for d in c.get("dishes", [])
            ],
            "total_price": sum(
                (d.get("price") or 0) for d in c.get("dishes", [])
            ),
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
    meal_log: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """规则 fallback: 取打分 top (n - n_explore) 当 exploit (品牌+菜系多样性去重),
    在剩余里挑"最近未吃过的菜系/做法"做 explore.
    每条用最简结构化字段填占位, 不调 LLM.
    """
    if not top_combos:
        return []
    from chisha.score import diversify_top
    n_exploit = max(1, n - n_explore)
    # exploit: 用 diversify_top 强制品牌/菜系多样性 (复用 V1 行为)
    exploit = diversify_top(top_combos, n=n_exploit, max_per_brand=1,
                             max_per_cuisine=2)
    used_ids = {id(c) for c in exploit}
    rest = [c for c in top_combos if id(c) not in used_ids]
    if rest and n_explore > 0:
        explore = _pick_explore(rest, exploit, meal_log or [], n_explore)
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


def _pick_explore(
    rest: list[dict],
    already_used: list[dict],
    meal_log: list[dict],
    n_explore: int,
) -> list[dict]:
    """explore 候选: 优先打分中段 + 最近 7 天没吃过的 cuisine/cooking_method.

    规则:
    1. 收集最近 7 天已吃 cuisine + cooking_method + already_used 的 cuisine/method
    2. 在 rest 中段 (前 50%) 取那些 cuisine 或 cooking_method 不在已用集中的
    3. 不够时退化到中段切片
    """
    import datetime as dt2
    cutoff = dt2.date.today() - dt2.timedelta(days=7)
    used_cuisines: set[str] = set()
    used_methods: set[str] = set()
    for log in meal_log:
        ts_str = log.get("timestamp", "")
        try:
            d = dt2.date.fromisoformat(ts_str[:10])
        except ValueError:
            continue
        if d < cutoff:
            continue
        for x in log.get("dishes", []):
            if x.get("cuisine"):
                used_cuisines.add(x["cuisine"])
            if x.get("main_ingredient_type"):
                pass
    for c in already_used:
        for d in c.get("dishes", []):
            if d.get("cuisine"):
                used_cuisines.add(d["cuisine"])
            if (d.get("nutrition_profile") or {}).get("cooking_method"):
                used_methods.add(d["nutrition_profile"]["cooking_method"])

    mid_end = max(n_explore, len(rest) // 2)
    mid_pool = rest[:mid_end]
    novel: list[dict] = []
    for c in mid_pool:
        cuisines = {d.get("cuisine", "") for d in c.get("dishes", [])
                     if d.get("cuisine")}
        methods = {(d.get("nutrition_profile") or {}).get("cooking_method", "")
                    for d in c.get("dishes", [])}
        if (cuisines - used_cuisines) or (methods - used_methods):
            novel.append(c)
            if len(novel) >= n_explore:
                break
    if len(novel) < n_explore:
        # 退化: 中段切片
        for c in mid_pool:
            if c not in novel:
                novel.append(c)
                if len(novel) >= n_explore:
                    break
    return novel[:n_explore]


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
    has_wet = any(
        _safe_int((d.get("nutrition_profile") or {}).get("wetness"), 1) >= 3
        for d in dishes
    )
    sweet = any(
        _safe_int((d.get("nutrition_profile") or {}).get("sweet_sauce_level"), 0) >= 3
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
            "wetness": has_wet,
        },
        "taste_match": None,        # rule fallback 不做语义匹配
        "risk_flags": [],
        "one_line_reason": _rule_reason(combo, has_wet, avg_oil, total_p),
    }


def _safe_int(v, default: int) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _rule_reason(combo: dict, has_wet: bool, avg_oil: float, total_p: float) -> str:
    bits = []
    if has_wet:
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


_HEALTH_FLAGS_KEYS = {"veg_ok", "protein_ok", "oil_ok", "processed_meat",
                       "sweet_sauce", "wetness"}


def _validate_llm_candidates(cands: list, n_max: int) -> list[dict] | None:
    """LLM 输出深度校验. 任何错误返回 None 让上游 fallback.

    检查:
    - 必填字段
    - fit_score 是 0-1 数值
    - rank 是连续 1..len 整数
    - combo_index 不重复, >= 0
    - is_explore 是 bool
    - health_flags 含核心子键
    - 数量 <= n_max
    """
    if not isinstance(cands, list) or not cands:
        return None
    if len(cands) > n_max:
        print(f"  [rerank] LLM 返回 {len(cands)} > n_max={n_max}, 截断")
        cands = cands[:n_max]
    seen_idx: set[int] = set()
    for i, c in enumerate(cands):
        if not isinstance(c, dict):
            return None
        missing = _REQUIRED_FIELDS - set(c)
        if missing:
            print(f"  [rerank] candidate#{i} 缺字段 {missing}")
            return None
        # combo_index
        idx = c.get("combo_index")
        if not isinstance(idx, int) or idx < 0:
            print(f"  [rerank] candidate#{i} combo_index 非法: {idx!r}")
            return None
        if idx in seen_idx:
            print(f"  [rerank] candidate#{i} combo_index 重复: {idx}")
            return None
        seen_idx.add(idx)
        # fit_score
        fs = c.get("fit_score")
        if not isinstance(fs, (int, float)) or not (0.0 <= float(fs) <= 1.0):
            print(f"  [rerank] candidate#{i} fit_score 越界: {fs!r}")
            return None
        # is_explore bool
        if not isinstance(c.get("is_explore"), bool):
            return None
        # health_flags 子键
        hf = c.get("health_flags")
        if not isinstance(hf, dict):
            return None
        if not _HEALTH_FLAGS_KEYS.issubset(hf.keys()):
            missing_hf = _HEALTH_FLAGS_KEYS - set(hf.keys())
            print(f"  [rerank] candidate#{i} health_flags 缺 {missing_hf}")
            return None
        # risk_flags 必须是 list
        if not isinstance(c.get("risk_flags"), list):
            return None
    # rank 连续 1..len
    ranks = sorted(c["rank"] for c in cands if isinstance(c.get("rank"), int))
    if ranks != list(range(1, len(cands) + 1)):
        print(f"  [rerank] rank 不连续: {ranks}")
        return None
    return cands


def _llm_rerank(payload: dict, model: str | None = None,
                n_max: int = 5) -> list[dict] | None:
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
        return _validate_llm_candidates(cands, n_max=n_max)
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
        from chisha.llm_client import has_llm_key
        use_llm = has_llm_key()

    if use_llm:
        payload = build_payload(top_combos, profile, context, meal_log, n, n_explore)
        llm_out = _llm_rerank(payload, model=model, n_max=n)
        if llm_out is not None:
            mapped: list[dict] = []
            for cand in llm_out[:n]:
                idx = cand.get("combo_index", -1)
                if not (0 <= idx < len(top_combos)):
                    continue
                merged = {**top_combos[idx], **cand}
                mapped.append(merged)
            mapped = _enforce_brand_unique(mapped, top_combos, n=n)
            if mapped:
                return mapped

    return fallback_rerank(top_combos, n=n, n_explore=n_explore,
                            meal_log=meal_log)


def _enforce_brand_unique(
    mapped: list[dict], top_combos: list[dict], n: int
) -> list[dict]:
    """LLM 可能漏掉去重指令 — 同 brand (连锁) 在 top n 只能出现 1 次.

    D-045: 之前只按 restaurant.id 去重, 连锁分店会同时占榜 (如 Super Model
    三家分店在 top5 占 3 条). 改成按 brand 去重 + rid 作为缺失兜底, 与 L2
    apply_caps 的 brand 层语义保持一致.

    保留每家品牌首次出现的那条 (LLM 已按 rank 排好), 不够 n 个时从
    top_combos 剩余 combos 里按 score 补齐 (跳过已用品牌).
    """
    if not mapped:
        return mapped

    def _brand_key(c: dict) -> str:
        rest = c.get("restaurant") or {}
        return rest.get("brand") or rest.get("id", "")

    seen_brand: set[str] = set()
    out: list[dict] = []
    for c in mapped:
        bk = _brand_key(c)
        if bk and bk in seen_brand:
            continue
        if bk:
            seen_brand.add(bk)
        out.append(c)
    if len(out) >= n:
        return out[:n]
    # 不够 n 个: 从 top_combos 按 score 补 (避免和已选品牌重复)
    used_combo_ids = {id(c) for c in mapped}
    for c in top_combos:
        if len(out) >= n:
            break
        if id(c) in used_combo_ids:
            continue
        bk = _brand_key(c)
        if bk and bk in seen_brand:
            continue
        # 补齐用的 combo 没经 LLM 评分, 填占位字段
        if bk:
            seen_brand.add(bk)
        fill = {
            **c,
            "rank": len(out) + 1,
            "is_explore": False,
            "fit_score": c.get("score", 0),
            "health_flags": {},
            "taste_match": None,
            "risk_flags": ["品牌去重补位"],
            "one_line_reason": "为多样性补位, 此条无 LLM 评分",
        }
        out.append(fill)
    # rank 重排
    for i, c in enumerate(out, start=1):
        c["rank"] = i
    return out

"""Debug-instrumented V2 推荐管道.

复刻 chisha.api._recommend_meal_v2, 但每一阶段记录中间状态:
- L1 召回: hard_filter / diversity_filter 的丢弃明细 (dish_id + reason)
- L2 打分: 全量 ranked combos + 每条 score_breakdown
- L3 精排: LLM payload 输入 + LLM 原始返回 + fallback 标记
- 终选 5: 最终 candidates

不修改原 chisha 模块, 仅作为 debug 入口被 debug_server 调用.

profile_overrides 支持页面端临时改 weights / plate_rule, 而无需改 profile.yaml.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from chisha.context import build_context
from chisha.recall import (
    build_combos_for_restaurant,
    combo_total_price,
    diversity_filter,
    is_carb_dish,
    is_complete_meal,
    is_protein_dish,
    is_vegetable_dish,
    load_meal_log,
    load_profile,
    load_zone_data,
)
from chisha.rerank import (
    L3_INPUT_TOP_K,
    SYSTEM_PROMPT_PATH,
    _compute_health_flags,
    _enforce_brand_unique,
    _validate_llm_candidates,
    build_payload,
    build_user_message,
    fallback_rerank,
)
from chisha.score import (
    apply_caps, combo_food_form, diversify_top, rank_combos, resolve_caps,
)


ROOT = Path(__file__).resolve().parent.parent
# D-046: prompt 拆 system / user, 不再单文件
# SYSTEM_PROMPT_PATH 从 chisha.rerank 复用


# ---------- profile 工具 ----------

def _deep_merge(base: dict, override: dict) -> dict:
    """递归 merge: override 覆盖 base, 不修改 base."""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_zone(profile: dict, meal_type: str) -> str:
    zones = profile.get("basics", {}).get("zones") or {}
    if meal_type in zones:
        return zones[meal_type]
    return profile["basics"]["office_zone"]


# ---------- L1 召回 traced ----------

def _traced_hard_filter(
    dishes: list[dict],
    profile: dict,
    avoid_restaurant_ids: set[str],
    banned_rests_by_eta: set[str] | None = None,
    banned_rests_by_name: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """委托给生产 hard_filter, 仅负责把"餐厅 ban 来源"映射成可读理由.

    把 ETA / avoid_restaurants / diversity 三组餐厅 id 合并成 rest_ban_reasons
    传给生产函数, 让丢弃明细带上具体原因.
    """
    banned_rests_by_eta = banned_rests_by_eta or set()
    banned_rests_by_name = banned_rests_by_name or set()
    avoid_restaurant_ids = avoid_restaurant_ids or set()
    rest_ban_reasons: dict[str, str] = {}
    for rid in banned_rests_by_eta:
        rest_ban_reasons[rid] = "餐厅 ETA 超 hard_max_eta_min"
    for rid in banned_rests_by_name:
        rest_ban_reasons.setdefault(rid, "餐厅在 avoid_restaurants")
    for rid in avoid_restaurant_ids:
        rest_ban_reasons.setdefault(rid, "餐厅近期已吃 (diversity)")
    from chisha.recall import hard_filter
    all_avoid = banned_rests_by_eta | banned_rests_by_name | avoid_restaurant_ids
    return hard_filter(
        dishes, profile,
        avoid_restaurant_ids=all_avoid,
        rest_ban_reasons=rest_ban_reasons,
    )


def _traced_diversity_filter(
    dishes: list[dict],
    meal_log: list[dict],
    profile: dict,
    today: dt.date | None = None,
) -> tuple[list[dict], list[dict], set[str], dict[str, set[str]]]:
    """返回 (保留, 丢弃, recent_rests, debug_info)."""
    today = today or dt.date.today()
    no_rest_days = profile["diversity"].get("no_same_restaurant_within_days", 7)
    no_ingr_days = profile["diversity"].get(
        "no_same_main_ingredient_within_days", 3
    )
    recent_rests: set[str] = set()
    recent_ingrs: set[str] = set()
    for log in meal_log:
        try:
            ts = dt.datetime.fromisoformat(log["timestamp"]).date()
        except Exception:
            continue
        delta = (today - ts).days
        if delta <= no_rest_days:
            recent_rests.add(log.get("restaurant_id", ""))
        if delta <= no_ingr_days:
            for x in log.get("dishes", []):
                ing = x.get("main_ingredient_type")
                if ing:
                    recent_ingrs.add(ing)
    keep: list[dict] = []
    drop: list[dict] = []
    for d in dishes:
        if d.get("restaurant_id") in recent_rests:
            drop.append({
                "dish_id": d.get("dish_id"),
                "name": d.get("canonical_name"),
                "restaurant_id": d.get("restaurant_id"),
                "reason": (
                    f"近 {no_rest_days} 天吃过该餐厅"
                ),
            })
            continue
        ing = d.get("nutrition_profile", {}).get("main_ingredient_type")
        if ing in ("红肉", "白肉", "海鲜", "豆制品") and ing in recent_ingrs:
            drop.append({
                "dish_id": d.get("dish_id"),
                "name": d.get("canonical_name"),
                "restaurant_id": d.get("restaurant_id"),
                "reason": f"近 {no_ingr_days} 天吃过 {ing}",
            })
            continue
        keep.append(d)
    debug_info = {
        "recent_rests": recent_rests,
        "recent_ingrs": recent_ingrs,
    }
    return keep, drop, recent_rests, debug_info


def _compute_banned_rests_traced(
    rests: list[dict], profile: dict
) -> tuple[set[str], set[str], list[dict]]:
    """算 ETA / avoid_restaurants 这两组 banned restaurant.

    返回 (banned_by_eta, banned_by_name, ban_details).
    """
    dc = profile.get("delivery_constraints") or {}
    hard_eta = dc.get("hard_max_eta_min")
    prefs = profile.get("preferences") or {}
    avoid_names = [a for a in prefs.get("avoid_restaurants", []) if a]
    by_eta: set[str] = set()
    by_name: set[str] = set()
    details: list[dict] = []
    for r in rests:
        rid = r["id"]
        name = r.get("name") or ""
        full = name + " " + (r.get("brand") or "")
        eta = r.get("delivery_eta_min", -1)
        if hard_eta and eta and eta > 0 and eta > hard_eta:
            by_eta.add(rid)
            details.append({
                "restaurant_id": rid, "name": name,
                "reason": f"ETA {eta} > hard_max_eta_min {hard_eta}",
            })
            continue
        matched = next((a for a in avoid_names if a in full), None)
        if matched:
            by_name.add(rid)
            details.append({
                "restaurant_id": rid, "name": name,
                "reason": f"命中 avoid_restaurants: {matched}",
            })
    return by_eta, by_name, details


def _build_l1_trace(
    profile: dict,
    rests: list[dict],
    tagged: list[dict],
    meal_log: list[dict],
    today: dt.date,
    meal_type: str | None = None,
) -> tuple[dict, list[dict]]:
    """返回 L1 trace + combos (供 L2)."""
    total_dishes = len(tagged)
    total_rests = len(rests)

    # 1a. 多样性: 近期已吃餐厅
    _, _, diversity_avoid, _ = _traced_diversity_filter(
        [], meal_log, profile, today
    )
    # 1b. P0 硬约束: ETA / avoid_restaurants
    banned_by_eta, banned_by_name, banned_rest_details = (
        _compute_banned_rests_traced(rests, profile)
    )
    all_banned_rests = diversity_avoid | banned_by_eta | banned_by_name

    # 2. hard_filter (含 P0 餐厅级 + P1 菜级黑名单)
    after_hard, hard_dropped = _traced_hard_filter(
        tagged, profile, diversity_avoid,
        banned_rests_by_eta=banned_by_eta,
        banned_rests_by_name=banned_by_name,
    )

    # 3. diversity_filter (按主蛋白多样性, 再过一次)
    after_div, div_dropped, _, _ = _traced_diversity_filter(
        after_hard, meal_log, profile, today
    )

    # 4. 按餐厅分桶
    by_rest: dict[str, list[dict]] = defaultdict(list)
    for d in after_div:
        by_rest[d["restaurant_id"]].append(d)
    rest_idx = {r["id"]: r for r in rests}
    per_rest_max = profile.get("recall", {}).get("per_restaurant_max", 3)

    # 5. 每家餐厅生成 combos
    combos: list[dict] = []
    per_restaurant_summary: list[dict] = []
    for rid, rest_dishes in by_rest.items():
        if rid not in rest_idx:
            continue
        rcombos = build_combos_for_restaurant(rest_dishes, profile, per_rest_max)
        per_restaurant_summary.append({
            "restaurant_id": rid,
            "name": rest_idx[rid]["name"],
            "n_dishes_after_filter": len(rest_dishes),
            "n_combos": len(rcombos),
        })
        for cd in rcombos:
            combos.append({
                "restaurant": rest_idx[rid],
                "dishes": cd,
            })

    # 6. combo 价格硬过滤
    n_combos_before_price = len(combos)
    price_dropped: list[dict] = []
    pr = profile.get("price_range") or {}
    price_cap = None
    if meal_type == "lunch":
        price_cap = pr.get("hard_max_lunch")
    elif meal_type == "dinner":
        price_cap = pr.get("hard_max_dinner")
    if price_cap:
        kept: list[dict] = []
        for c in combos:
            total = combo_total_price(c)
            if total <= price_cap:
                kept.append(c)
            else:
                price_dropped.append({
                    "restaurant": c["restaurant"].get("name"),
                    "dishes": [d.get("canonical_name") for d in c["dishes"]],
                    "total_price": round(total, 1),
                    "reason": f"combo 总价 {total:.1f} > hard_max {price_cap}",
                })
        combos = kept

    per_restaurant_summary.sort(key=lambda x: -x["n_combos"])

    trace = {
        "summary": {
            "total_dishes": total_dishes,
            "total_restaurants": total_rests,
            "n_banned_rests_by_eta": len(banned_by_eta),
            "n_banned_rests_by_name": len(banned_by_name),
            "n_diversity_avoid_rests": len(diversity_avoid),
            "after_hard_filter": len(after_hard),
            "after_diversity_filter": len(after_div),
            "n_restaurants_with_combos": len(per_restaurant_summary),
            "n_combos_before_price_filter": n_combos_before_price,
            "n_combos_dropped_by_price": len(price_dropped),
            "n_combos": len(combos),
            "n_avoid_rests": len(all_banned_rests),
        },
        "params": {
            "spicy_tolerance":
                profile["preferences"].get("spicy_tolerance"),
            "hard_max_oil_level":
                profile["plate_rule"].get("hard_max_oil_level"),
            "min_monthly_sales":
                profile.get("recall", {}).get("min_monthly_sales"),
            "hard_max_eta_min":
                (profile.get("delivery_constraints") or {}).get("hard_max_eta_min"),
            "hard_max_price":
                price_cap,
            "avoid_restaurants":
                profile["preferences"].get("avoid_restaurants"),
            "avoid_main_ingredients":
                profile["preferences"].get("avoid_main_ingredients"),
            "avoid_cooking_methods":
                profile["preferences"].get("avoid_cooking_methods"),
            "banned_cuisines":
                profile["preferences"].get("banned_cuisines"),
            "per_restaurant_max": per_rest_max,
        },
        "dropped_hard": hard_dropped,
        "dropped_diversity": div_dropped,
        "dropped_by_price": price_dropped,
        "dropped_hard_by_reason": _group_drops_by_reason(hard_dropped),
        "dropped_diversity_by_reason": _group_drops_by_reason(div_dropped),
        "banned_restaurants": banned_rest_details,
        "per_restaurant": per_restaurant_summary,
    }
    return trace, combos


def _group_drops_by_reason(dropped: list[dict]) -> dict[str, int]:
    counter: dict[str, int] = {}
    for d in dropped:
        # 把数值参数归一 (如 "辣度 4 > 上限 2" → "辣度超上限")
        key = re.sub(r"\d+(\.\d+)?", "N", d["reason"])
        counter[key] = counter.get(key, 0) + 1
    return dict(sorted(counter.items(), key=lambda x: -x[1]))


# ---------- L2 打分 traced ----------

def _combo_signature(combo: dict) -> str:
    """combo 的人类可读签名: 餐厅 | 菜1+菜2."""
    rest = combo.get("restaurant", {}).get("name", "?")
    dishes = "+".join(d.get("canonical_name", "?") for d in combo.get("dishes", []))
    return f"{rest} | {dishes}"


def _format_ranked_for_trace(
    ranked: list[dict], top: int = 30
) -> list[dict]:
    """ranked combo → 精简 trace (前 top 个全展开, 其余只留 score)."""
    out = []
    for i, c in enumerate(ranked[:top]):
        rest = c.get("restaurant", {})
        out.append({
            "rank": i + 1,
            "combo_index": i,
            "signature": _combo_signature(c),
            "restaurant_id": rest.get("id"),
            "restaurant_name": rest.get("name"),
            "cuisine": (c.get("dishes") or [{}])[0].get("cuisine", ""),
            "distance_m": rest.get("distance_m", -1),
            "eta_min": rest.get("delivery_eta_min", -1),
            "total_price": round(
                combo_total_price(c), 1
            ),
            "dishes": [
                {
                    "dish_id": d.get("dish_id"),
                    "name": d.get("canonical_name"),
                    "price": d.get("price"),
                    "main_ingredient_type":
                        d["nutrition_profile"].get("main_ingredient_type"),
                    "cooking_method":
                        d["nutrition_profile"].get("cooking_method"),
                    "oil_level": d["nutrition_profile"].get("oil_level"),
                    "spicy_level": d["nutrition_profile"].get("spicy_level"),
                    "dish_role": d["nutrition_profile"].get("dish_role"),
                    "processed_meat_flag":
                        d["nutrition_profile"].get("processed_meat_flag"),
                    "sweet_sauce_level":
                        d["nutrition_profile"].get("sweet_sauce_level"),
                    "wetness": d["nutrition_profile"].get("wetness"),
                    "grain_type": d["nutrition_profile"].get("grain_type"),
                    "protein_g":
                        d["nutrition_profile"].get("protein_grams_estimate"),
                    "vegetable_ratio":
                        d["nutrition_profile"].get("vegetable_ratio_estimate"),
                }
                for d in c.get("dishes", [])
            ],
            "score": round(c.get("score", 0), 3),
            "breakdown": {
                k: round(v, 3)
                for k, v in (c.get("score_breakdown") or {}).items()
            },
        })
    return out


# ---------- L3 LLM rerank traced ----------

def _llm_rerank_traced(
    top_combos: list[dict], profile: dict, context, n: int, n_explore: int,
    model: str | None, n_max: int,
) -> dict:
    """调 LLM, 返回 trace dict (含 system/user prompt / raw / parsed / used_fallback).

    D-046: system/user 拆分; system 走 Anthropic prompt cache.
    trace 把两段 prompt 都打回去, 便于 debug 看实际给 LLM 的输入.
    """
    out: dict[str, Any] = {
        "used": False,
        "model": model,
        "system_prompt_chars": 0,
        "user_message_chars": 0,
        "raw_response": None,
        "raw_response_chars": 0,
        "parsed_candidates": None,
        "fallback_reason": None,
    }
    try:
        from chisha.llm_client import call_text
        system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        user_msg = build_user_message(top_combos, profile, context,
                                       n=n, n_explore=n_explore)
        out["system_prompt_chars"] = len(system_prompt)
        out["user_message_chars"] = len(user_msg)
        out["user_message_preview"] = user_msg[:2000]
        kwargs: dict[str, Any] = {
            "max_tokens": 2048, "temperature": 0.0,
            "system": system_prompt, "cache_system": True,
            "profile_llm": profile.get("llm"),  # D-047: provider 路由
        }
        if model:
            kwargs["model"] = model
        raw = call_text(user_msg, **kwargs)
        out["used"] = True
        out["raw_response"] = raw
        out["raw_response_chars"] = len(raw)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            out["fallback_reason"] = "LLM 输出无 JSON"
            return out
        data = json.loads(m.group(0))
        cands = data.get("candidates")
        validated = _validate_llm_candidates(
            cands, n_max=n_max,
            input_size=len(top_combos),
            n_explore_expected=n_explore,
        )
        if validated is None:
            out["fallback_reason"] = "candidates 校验失败 (字段缺失/越界/数量)"
            return out
        out["parsed_candidates"] = validated
    except Exception as e:
        out["fallback_reason"] = f"{type(e).__name__}: {str(e)[:120]}"
    return out


# ---------- 主入口 ----------

def debug_recommend(
    meal_type: str = "lunch",
    profile_path: str | Path = "profile.yaml",
    today: dt.date | None = None,
    daily_mood: str | None = None,
    use_llm_rerank: bool | None = None,
    profile_overrides: dict | None = None,
    trace_target: dict | None = None,
    n_return: int = 5,
    n_explore: int = 2,
    root: Path | None = None,
) -> dict:
    """V2 instrumented 推荐. 返回完整 trace.

    Args:
        profile_overrides: dict, 临时覆盖 profile (递归 merge, 不写盘).
        trace_target: {"restaurant_name": str, "dish_names": [str]} —
            追溯一个特定 combo 在管道里的命运 (在哪一阶段被丢/排第几).
    """
    root = root or ROOT
    base_profile = load_profile(
        Path(profile_path) if Path(profile_path).is_absolute()
        else root / profile_path
    )
    profile = _deep_merge(base_profile, profile_overrides or {})
    zone = _resolve_zone(profile, meal_type)
    rests, tagged = load_zone_data(zone, root)
    meal_log = load_meal_log(root)
    today = today or dt.date.today()

    # ---- L1 召回 ----
    l1_trace, combos = _build_l1_trace(profile, rests, tagged, meal_log, today, meal_type=meal_type)

    # ---- Context ----
    ctx = build_context(
        profile, meal_log, meal_type, today,
        daily_mood=daily_mood, refine_input=None
    )

    # ---- L2 打分 ----
    ranked_raw = rank_combos(
        combos, profile, meal_log, today,
        context=ctx, meal_type=meal_type, root=root,
    )
    # D-043: 三层 cap (restaurant + cuisine + food_form), 防扎堆 topk
    caps = resolve_caps(profile)
    ranked = apply_caps(ranked_raw, profile)

    def _count_keys(combos: list[dict], key_fn):
        counts: dict[str, int] = {}
        for c in combos:
            k = key_fn(c) or "<未知>"
            counts[k] = counts.get(k, 0) + 1
        return counts

    def _rest_key(c):
        rest = c.get("restaurant") or {}
        return rest.get("id") or rest.get("name")

    def _brand_key(c):
        rest = c.get("restaurant") or {}
        return rest.get("brand") or rest.get("id") or rest.get("name")

    def _cuisine_key(c):
        dishes = c.get("dishes") or []
        return dishes[0].get("cuisine") if dishes else None

    rest_before = _count_keys(ranked_raw[:L3_INPUT_TOP_K], _rest_key)
    rest_after = _count_keys(ranked[:L3_INPUT_TOP_K], _rest_key)
    brand_before = _count_keys(ranked_raw[:L3_INPUT_TOP_K], _brand_key)
    brand_after = _count_keys(ranked[:L3_INPUT_TOP_K], _brand_key)
    cuisine_before = _count_keys(ranked_raw[:L3_INPUT_TOP_K], _cuisine_key)
    cuisine_after = _count_keys(ranked[:L3_INPUT_TOP_K], _cuisine_key)
    form_before = _count_keys(ranked_raw[:L3_INPUT_TOP_K], combo_food_form)
    form_after = _count_keys(ranked[:L3_INPUT_TOP_K], combo_food_form)

    # 统计每维度 std (区分度) — 帮助看是否仍有死分
    import statistics
    dim_stats: dict[str, dict[str, float]] = {}
    if ranked[:L3_INPUT_TOP_K]:
        all_dims: set[str] = set()
        for c in ranked[:L3_INPUT_TOP_K]:
            all_dims.update((c.get("score_breakdown") or {}).keys())
        for dim in all_dims:
            vals = [
                (c.get("score_breakdown") or {}).get(dim, 0.0)
                for c in ranked[:L3_INPUT_TOP_K]
            ]
            dim_stats[dim] = {
                "min": round(min(vals), 3),
                "max": round(max(vals), 3),
                "mean": round(sum(vals) / len(vals), 3),
                "std": round(statistics.pstdev(vals) if len(vals) > 1 else 0, 3),
            }

    l2_trace = {
        "summary": {
            "n_scored": len(ranked),
            "score_min": round(min((c["score"] for c in ranked), default=0), 3),
            "score_max": round(max((c["score"] for c in ranked), default=0), 3),
            "score_range": round(
                max((c["score"] for c in ranked), default=0)
                - min((c["score"] for c in ranked), default=0), 3),
            "weights": profile.get("scoring_weights", {}),
            "caps": caps,
            # cap 前后对比 (topk)
            "topk_unique_restaurants_before_cap": len(rest_before),
            "topk_unique_restaurants_after_cap": len(rest_after),
            "topk_max_per_restaurant_before_cap":
                max(rest_before.values(), default=0),
            "topk_max_per_restaurant_after_cap":
                max(rest_after.values(), default=0),
            # D-045 brand 层
            "topk_unique_brands_before_cap": len(brand_before),
            "topk_unique_brands_after_cap": len(brand_after),
            "topk_max_per_brand_before_cap":
                max(brand_before.values(), default=0),
            "topk_max_per_brand_after_cap":
                max(brand_after.values(), default=0),
            "topk_unique_cuisines_before_cap": len(cuisine_before),
            "topk_unique_cuisines_after_cap": len(cuisine_after),
            "topk_max_per_cuisine_before_cap":
                max(cuisine_before.values(), default=0),
            "topk_max_per_cuisine_after_cap":
                max(cuisine_after.values(), default=0),
            "topk_unique_food_forms_before_cap": len(form_before),
            "topk_unique_food_forms_after_cap": len(form_after),
            "topk_max_per_food_form_before_cap":
                max(form_before.values(), default=0),
            "topk_max_per_food_form_after_cap":
                max(form_after.values(), default=0),
            # 各维度 std (死分诊断)
            "dim_stats_topk": dim_stats,
            # cap 前后观测窗口大小 (= L3 LLM 输入候选数, D-046 二审: 60)
            "topk_window": L3_INPUT_TOP_K,
            # 兼容旧 key (前端尚未升级时用)
            "per_restaurant_cap_k": caps["restaurant"],
        },
        "top": _format_ranked_for_trace(ranked, top=L3_INPUT_TOP_K),
    }

    # ---- L3 LLM 精排 ----
    if use_llm_rerank is None:
        from chisha.llm_client import has_llm_key
        use_llm_rerank = has_llm_key()
    topk = ranked[:L3_INPUT_TOP_K]
    # legacy JSON payload 仍存留, 给 trace 可观测性 (实际 LLM 输入是
    # build_user_message 的紧凑文本, 见 _llm_rerank_traced).
    payload = build_payload(
        topk, profile, ctx, meal_log, n=n_return, n_explore=n_explore
    )
    l3_llm = {"used": False, "skipped_reason": "use_llm_rerank=False"}
    final_candidates: list[dict] = []
    fallback_used = False
    if use_llm_rerank and topk:
        l3_llm = _llm_rerank_traced(
            topk, profile, ctx,
            n=n_return, n_explore=n_explore,
            model=None, n_max=n_return,
        )
        if l3_llm.get("parsed_candidates"):
            mapped: list[dict] = []
            for cand in l3_llm["parsed_candidates"][:n_return]:
                idx = cand.get("combo_index", -1)
                if not (0 <= idx < len(topk)):
                    continue
                # D-046: health_flags 规则后处理
                cand["health_flags"] = _compute_health_flags(topk[idx])
                merged = {**topk[idx], **cand}
                mapped.append(merged)
            mapped = _enforce_brand_unique(mapped, topk, n=n_return)
            final_candidates = mapped
    if not final_candidates:
        fallback_used = True
        final_candidates = fallback_rerank(
            topk, n=n_return, n_explore=n_explore, meal_log=meal_log
        )

    # ---- 终选格式化 ----
    final_view = [
        _format_final_candidate(i + 1, c) for i, c in enumerate(final_candidates)
    ]

    # ---- trace_target 追溯 ----
    target_trace = None
    if trace_target:
        target_trace = _trace_target(
            trace_target, tagged, rests, l1_trace, ranked, final_candidates
        )

    return {
        "config": {
            "meal_type": meal_type,
            "zone": zone,
            "today": today.isoformat(),
            "daily_mood": daily_mood,
            "version": "v2-debug",
            "use_llm_rerank": use_llm_rerank,
            "fallback_used": fallback_used,
            "profile_overrides": profile_overrides or {},
        },
        "context": ctx.to_llm_dict(),
        "l1_recall": l1_trace,
        "l2_score": l2_trace,
        "l3_rerank": {
            "llm": l3_llm,
            "payload_to_llm": payload,
            "n_returned": len(final_candidates),
        },
        "final": final_view,
        "target_trace": target_trace,
    }


def _format_final_candidate(rank: int, c: dict) -> dict:
    rest = c.get("restaurant", {})
    return {
        "rank": rank,
        "combo_index": c.get("combo_index"),
        "is_explore": bool(c.get("is_explore", False)),
        "signature": _combo_signature(c),
        "restaurant": {
            "id": rest.get("id"),
            "name": rest.get("name"),
            "distance_m": rest.get("distance_m", -1),
            "eta_min": rest.get("delivery_eta_min", -1),
        },
        "dishes": [
            {
                "dish_id": d.get("dish_id"),
                "name": d.get("canonical_name"),
                "price": d.get("price"),
                "main_ingredient_type":
                    d["nutrition_profile"].get("main_ingredient_type"),
                "oil_level": d["nutrition_profile"].get("oil_level"),
            }
            for d in c.get("dishes", [])
        ],
        "total_price": round(
            sum(d.get("price", 0) for d in c.get("dishes", [])), 1
        ),
        "score": round(c.get("score", 0), 3),
        "fit_score": c.get("fit_score"),
        "health_flags": c.get("health_flags") or {},
        "risk_flags": c.get("risk_flags") or [],
        "taste_match": c.get("taste_match"),
        "one_line_reason":
            c.get("one_line_reason") or c.get("reason_one_line", ""),
    }


# ---------- combo 追溯 ----------

def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def _trace_target(
    target: dict,
    tagged: list[dict],
    rests: list[dict],
    l1_trace: dict,
    ranked: list[dict],
    final: list[dict],
) -> dict:
    """根据 target (restaurant_name + dish_names) 追溯命运.

    步骤:
    1. 用 restaurants.json 把餐厅名转成 restaurant_id 集合
    2. 在 tagged 里找匹配的 dish (按 rid + canonical_name 模糊)
    3. 看是否被 hard_filter / diversity_filter 丢弃
    4. 看是否进入 ranked, 排第几, 分数
    5. 看是否进 final
    """
    rest_q = _normalize(target.get("restaurant_name", ""))
    dish_qs = [_normalize(x) for x in target.get("dish_names", []) if x]

    rest_idx = {r["id"]: r for r in rests}
    matched_rids: set[str] = set()
    if rest_q:
        for r in rests:
            if rest_q in _normalize(r.get("name", "")):
                matched_rids.add(r["id"])

    # 1. 在 tagged 找菜
    matched_dishes = []
    for d in tagged:
        if rest_q and d.get("restaurant_id") not in matched_rids:
            continue
        if dish_qs:
            name = _normalize(d.get("canonical_name", ""))
            if not any(q in name for q in dish_qs):
                continue
        matched_dishes.append({
            "dish_id": d.get("dish_id"),
            "name": d.get("canonical_name"),
            "restaurant_id": d.get("restaurant_id"),
            "restaurant_name":
                rest_idx.get(d.get("restaurant_id", ""), {}).get("name"),
        })
    # 限制结果太多刷屏
    matched_dishes = matched_dishes[:50]

    # 2. 在丢弃明细里找
    hard_drop_lookup = {x["dish_id"]: x for x in l1_trace["dropped_hard"]}
    div_drop_lookup = {x["dish_id"]: x for x in l1_trace["dropped_diversity"]}
    dish_fates: list[dict] = []
    for md in matched_dishes:
        fate = {**md, "stage": "unknown", "reason": None}
        if md["dish_id"] in hard_drop_lookup:
            fate["stage"] = "dropped_hard_filter"
            fate["reason"] = hard_drop_lookup[md["dish_id"]]["reason"]
        elif md["dish_id"] in div_drop_lookup:
            fate["stage"] = "dropped_diversity_filter"
            fate["reason"] = div_drop_lookup[md["dish_id"]]["reason"]
        else:
            fate["stage"] = "passed_recall"
        dish_fates.append(fate)

    # 3. 在 ranked 找包含这些菜的 combos
    matched_combo_ranks: list[dict] = []
    matched_dish_ids = {x["dish_id"] for x in matched_dishes}
    for i, c in enumerate(ranked):
        combo_dish_ids = {d.get("dish_id") for d in c.get("dishes", [])}
        if matched_dish_ids & combo_dish_ids:
            matched_combo_ranks.append({
                "rank": i + 1,
                "score": round(c.get("score", 0), 3),
                "signature": _combo_signature(c),
                "breakdown": {
                    k: round(v, 3)
                    for k, v in (c.get("score_breakdown") or {}).items()
                },
            })
        if len(matched_combo_ranks) >= 10:
            break

    # 4. 是否在 final
    final_dish_ids: set[str] = set()
    for c in final:
        for d in c.get("dishes", []):
            final_dish_ids.add(d.get("dish_id"))
    in_final = bool(matched_dish_ids & final_dish_ids)

    return {
        "query": target,
        "matched_dishes": dish_fates,
        "matched_combos_in_ranked": matched_combo_ranks,
        "in_final": in_final,
    }


# ---------- 多 mood 对比 ----------

def compare_moods(
    moods: list[str],
    meal_type: str = "lunch",
    profile_overrides: dict | None = None,
    use_llm_rerank: bool | None = None,
    today: dt.date | None = None,
    root: Path | None = None,
) -> dict:
    """对同一 zone/profile 跑多个 daily_mood, 横向对比 top5.

    返回 {mood: {final: [...], l2_top5: [...]}}.
    """
    out: dict[str, Any] = {}
    for mood in moods:
        r = debug_recommend(
            meal_type=meal_type,
            today=today,
            daily_mood=mood if mood and mood != "none" else None,
            use_llm_rerank=use_llm_rerank,
            profile_overrides=profile_overrides,
            root=root,
        )
        out[mood] = {
            "final": r["final"],
            "l2_top5": r["l2_score"]["top"][:5],
            "fallback_used": r["config"]["fallback_used"],
        }
    return out


if __name__ == "__main__":
    import sys
    meal = sys.argv[1] if len(sys.argv) > 1 else "lunch"
    out = debug_recommend(meal_type=meal, use_llm_rerank=False)
    print(json.dumps({
        "config": out["config"],
        "l1_summary": out["l1_recall"]["summary"],
        "l2_summary": out["l2_score"]["summary"],
        "n_final": len(out["final"]),
        "first_final": out["final"][0] if out["final"] else None,
    }, ensure_ascii=False, indent=2))

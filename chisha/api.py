"""recommend_meal 主入口 (DESIGN §5.7).

D-049 后单一实现: build_context → 召回 → score V2 (~12维) → LLM rerank top60→5
(3 exploit + 2 explore) → 创建 session → §5.7 JSON.

旧 V1 路径 (D-024 简化版: 打分 → top 3 + LLM 写 reason) 已删除 (D-049).
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
from pathlib import Path

from chisha.context import build_context
from chisha.recall import (
    load_meal_log,
    load_profile,
    load_zone_data,
    recall,
)
from chisha.rerank import rerank as v2_rerank
from chisha.score import apply_caps, rank_combos
from chisha.session import create_session, save_session


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


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent


def recommend_meal(
    meal_type: str = "lunch",
    profile_path: str | Path = "profile.yaml",
    today: dt.date | None = None,
    log_to_file: bool = True,
    daily_mood: str | None = None,
    use_llm_rerank: bool | None = None,
    root: Path | None = None,
    persist_trace: bool = True,
) -> dict:
    """主入口 (D-033 + D-049): build_context → recall → score V2 → rerank → session.

    Args:
        daily_mood: ContextSnapshot.daily_mood, 见 chisha/context.DAILY_MOODS.
        use_llm_rerank: None=auto (任意 LLM provider 可用即开, D-047).
        root: 仓库根目录 (测试可注入), 默认 chisha/__file__.parent.parent.
        persist_trace: D-079, 默认 True. 写完整 trace 到 logs/recommend_trace/.
            Live 模式 (debug_server /api/debug_recommend) 传 False 不污染历史.
    """
    root = root or _default_root()
    # D-077 Codex S3 修复: 默认 profile_path 走 data_root.profile_path (sandbox
    # 启用且副本存在时切到副本); 显式传入相对/绝对路径时保持兼容.
    if profile_path == "profile.yaml":
        from chisha import data_root
        profile = load_profile(data_root.profile_path(root), root=root)
    else:
        profile = load_profile(
            Path(profile_path) if Path(profile_path).is_absolute()
            else root / profile_path,
            root=root,
        )
    zone = _resolve_zone(profile, meal_type)
    rests, tagged = load_zone_data(zone, root)
    meal_log = load_meal_log(root)

    from chisha import clock
    today = today or clock.today()
    session_id = _gen_session_id(meal_type)
    started_at = clock.now_utc()
    import time as _time
    _t_start = _time.monotonic()

    # 1. Context 注入 (D-034)
    _t0 = _time.monotonic()
    ctx = build_context(profile, meal_log, meal_type, today,
                        daily_mood=daily_mood, refine_input=None)
    ctx_latency_ms = int((_time.monotonic() - _t0) * 1000)
    # 2. 召回 (L1)
    _t0 = _time.monotonic()
    combos = recall(profile, rests, tagged, meal_log, today, meal_type=meal_type)
    recall_latency_ms = int((_time.monotonic() - _t0) * 1000)
    # 3. V2 打分 (~12 维, 含 context) + 三层 cap (D-043) (L2)
    _t0 = _time.monotonic()
    ranked_raw = rank_combos(combos, profile, meal_log, today,
                          context=ctx, meal_type=meal_type, root=root)
    ranked = apply_caps(ranked_raw, profile)
    score_latency_ms = int((_time.monotonic() - _t0) * 1000)
    # 4. LLM 精排 topK → 5 (3 exploit + 2 explore, D-015; D-046: 30 → 60) (L3)
    from chisha.rerank import L3_INPUT_TOP_K
    top_k = ranked[:L3_INPUT_TOP_K]
    # D-079: trace_collector 捕获 LLM 中间状态 (Codex Q3: 传 today 防 fallback 漂移)
    # T-P1b-02: collector 始终是 dict, narrative 也要在 Live (persist_trace=False)
    # 模式下拿到给前端展示. _build_trace 只在 persist_trace=True 时跑.
    l3_collector: dict = {}
    _t0 = _time.monotonic()
    reranked = v2_rerank(top_k, profile, context=ctx, meal_log=meal_log,
                          n=5, n_explore=2, refine=False, use_llm=use_llm_rerank,
                          root=root,
                          today=today, trace_collector=l3_collector)
    rerank_latency_ms = int((_time.monotonic() - _t0) * 1000)
    # 5. 创建 session (供 refine 二轮用)
    state = create_session(session_id, meal_type, zone, daily_mood=daily_mood)
    state.last_candidates = [_minimize_candidate(c) for c in reranked]
    save_session(state, root)

    # T-P1b-01: status_bar payload. 跑一次轻量 _build_l1_trace 拿 hard_filter_events
    # (recall path 的 L0-A/B 事件), 给前端 always-on 状态条派生数据.
    # Codex M1 修: status_bar 与 _build_trace 共用同一份 _build_l1_trace 结果,
    # 之前 status_bar 跑一次 + _build_trace 又跑一次 → 100ms 重复开销 + 边界漂移风险.
    l1_trace_cache: dict | None = None
    try:
        from chisha.debug_recommend import _build_l1_trace
        from chisha.status_bar import build_status_bar
        l1_trace_cache, _ = _build_l1_trace(
            profile, rests, tagged, meal_log, today, meal_type=meal_type
        )
        _hfe = l1_trace_cache.get("hard_filter_events") or []
        status_bar = build_status_bar(profile, _hfe)
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning(
            "status_bar build failed (non-fatal): %s: %s", type(_e).__name__, _e,
        )
        # 降级到 baseline (无 events), 不阻断 response
        from chisha.status_bar import build_status_bar
        status_bar = build_status_bar(profile, [])
        l1_trace_cache = None

    # T-P1b-02: L3 narrative (顶层"为什么推这 5 道"摘要)
    # collector 里若 LLM 路径触发, narrative 已写入; fallback / 旧 trace 为空
    narrative = l3_collector.get("narrative", "") if isinstance(l3_collector, dict) else ""

    out = {
        "session_id": session_id,
        "meal_type": meal_type,
        "zone": zone,
        "round": 1,
        "version": "v2",
        "generated_at": clock.now_utc().isoformat(),
        "context": ctx.to_llm_dict(),
        "stats": {
            "n_dishes_total": len(tagged),
            "n_combos_recalled": len(combos),
            "n_combos_after_score": len(ranked),
            "n_returned": len(reranked),
        },
        "candidates": [_format_v2_candidate(i + 1, c)
                        for i, c in enumerate(reranked)],
        "status_bar": status_bar,
        "narrative": narrative,
    }

    if log_to_file:
        # D-077 PR-1b: 走 data_root.recommend_log_path, sandbox 启用时落 logs/sandbox/
        from chisha import data_root
        log_path = data_root.recommend_log_path(root)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(out, ensure_ascii=False) + "\n")

    # D-079: 写完整 trace (best-effort, 失败 logger.warning 不阻断 recommend response)
    if persist_trace:
        try:
            total_latency_ms = int((_time.monotonic() - _t_start) * 1000)
            trace = _build_trace(
                session_id=session_id,
                started_at=started_at,
                total_latency_ms=total_latency_ms,
                ctx_latency_ms=ctx_latency_ms,
                recall_latency_ms=recall_latency_ms,
                score_latency_ms=score_latency_ms,
                rerank_latency_ms=rerank_latency_ms,
                meal_type=meal_type,
                zone=zone,
                today=today,
                profile=profile,
                rests=rests,
                tagged=tagged,
                meal_log=meal_log,
                combos=combos,
                ctx=ctx,
                daily_mood=daily_mood,
                ranked_raw=ranked_raw,
                ranked=ranked,
                top_k=top_k,
                reranked=reranked,
                l3_collector=l3_collector or {},
                use_llm_rerank=use_llm_rerank,
                root=root,
                # Codex M1: 复用 status_bar 已经跑过的 l1_trace, 避免二次重跑
                l1_trace_precomputed=l1_trace_cache,
            )
            from chisha import trace_store
            trace_store.write_trace(session_id, trace, root=root)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "trace build/write failed for %s: %s: %s",
                session_id, type(e).__name__, e,
            )
    return out


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


_SCORING_NUTRITION_KEYS = {
    "oil_level", "spicy_level", "wetness", "sweet_sauce_level", "processed_meat_flag",
    "main_ingredient_type", "vegetable_ratio_estimate", "protein_grams_estimate",
    "cooking_method", "dish_role", "grain_type", "is_complete_meal", "tags",
}
_RESTAURANT_KEYS = {
    "id", "name", "brand", "distance_m", "delivery_eta_min", "category",
    "monthly_orders", "rating", "office_zone",
}


def _normalize_combos(
    combos: list[dict],
) -> tuple[dict[str, dict], dict[str, dict], list[dict]]:
    """combos → (restaurants_table, dishes_table, combo_refs).

    combos 全集直存会膨胀到 6MB+ (2467 combos × 多 dish 嵌套). 改用 normalized:
    - restaurants_table: rest_id → {id, name, brand, distance_m, eta, ...} (~50 家)
    - dishes_table: dish_id → {dish_id, canonical_name, price, nutrition_profile(slim), ...} (~1k 道)
    - combo_refs: [{restaurant_id, dish_ids}] (轻量 refs, ~30 bytes/combo)

    What-if 重跑前 rehydrate 即可 (PR-2 实现).
    """
    restaurants: dict[str, dict] = {}
    dishes: dict[str, dict] = {}
    refs: list[dict] = []
    for c in combos:
        rest = c.get("restaurant") or {}
        rid = rest.get("id")
        if rid and rid not in restaurants:
            restaurants[rid] = {k: rest.get(k) for k in _RESTAURANT_KEYS if k in rest}
        dish_ids: list[str] = []
        for d in c.get("dishes") or []:
            did = d.get("dish_id")
            if did and did not in dishes:
                slim_np = {
                    k: v for k, v in (d.get("nutrition_profile") or {}).items()
                    if k in _SCORING_NUTRITION_KEYS
                }
                dishes[did] = {
                    "dish_id": did,
                    "restaurant_id": d.get("restaurant_id"),
                    "canonical_name": d.get("canonical_name"),
                    "raw_name": d.get("raw_name"),
                    "price": d.get("price"),
                    "monthly_sales": d.get("monthly_sales"),
                    "cuisine": d.get("cuisine"),
                    "nutrition_profile": slim_np,
                }
            if did:
                dish_ids.append(did)
        refs.append({"restaurant_id": rid, "dish_ids": dish_ids})
    return restaurants, dishes, refs


def _build_trace(
    *,
    session_id: str,
    started_at: dt.datetime,
    total_latency_ms: int,
    ctx_latency_ms: int,
    recall_latency_ms: int,
    score_latency_ms: int,
    rerank_latency_ms: int,
    meal_type: str,
    zone: str,
    today: dt.date,
    profile: dict,
    rests: list[dict],
    tagged: list[dict],
    meal_log: list[dict],
    combos: list[dict],
    ctx,
    daily_mood: str | None,
    ranked_raw: list[dict],
    ranked: list[dict],
    top_k: list[dict],
    reranked: list[dict],
    l3_collector: dict,
    use_llm_rerank: bool | None,
    root: Path | None,
    l1_trace_precomputed: dict | None = None,
) -> dict:
    """D-079: 组装完整 trace dict (与 apps/debug-ui Session type 对齐 + __frozen).

    所有 L1/L2/L3 中间状态都已经在 recommend_meal 链路里算好, 这里只做组装.
    Codex M1 修: l1_trace_precomputed 注入时跳过重跑 (recommend_meal 已为 status_bar
    跑过一次), 否则 fallback 跑一次 (debug_what_if / 测试调用兼容).
    """
    from chisha import trace_store
    from chisha.debug_recommend import (
        _build_l1_trace, _build_l2_cap_stats,
        _format_ranked_for_trace, _format_final_candidate,
    )
    from chisha.rerank import L3_INPUT_TOP_K, build_payload
    from chisha.score import combo_food_form, resolve_caps

    # L1 trace
    if l1_trace_precomputed is not None:
        l1_trace = l1_trace_precomputed
    else:
        l1_trace, _ = _build_l1_trace(
            profile, rests, tagged, meal_log, today, meal_type=meal_type
        )

    # L2 trace (复用 ranked, 不重算)
    import statistics
    caps = resolve_caps(profile)
    dim_stats: dict = {}
    topk_view = ranked[:L3_INPUT_TOP_K]
    if topk_view:
        all_dims: set = set()
        for c in topk_view:
            all_dims.update((c.get("score_breakdown") or {}).keys())
        for dim in all_dims:
            vals = [(c.get("score_breakdown") or {}).get(dim, 0.0) for c in topk_view]
            dim_stats[dim] = {
                "min": round(min(vals), 3),
                "max": round(max(vals), 3),
                "mean": round(sum(vals) / len(vals), 3),
                "std": round(statistics.pstdev(vals) if len(vals) > 1 else 0, 3),
            }
    # D-079 followup: 补 cap 前后 unique restaurants/brands/cuisines/food_forms
    # 统计 (之前漏写, 前端 DagHeader 显示 "undefined rest"). 复用 debug_recommend
    # 的 helper 保持口径一致.
    cap_stats = _build_l2_cap_stats(ranked_raw, ranked)
    l2_trace = {
        "summary": {
            "n_scored": len(ranked),
            "score_min": round(min((c["score"] for c in ranked), default=0), 3),
            "score_max": round(max((c["score"] for c in ranked), default=0), 3),
            "weights": profile.get("scoring_weights", {}),
            "caps": caps,
            "topk_window": L3_INPUT_TOP_K,
            "dim_stats_topk": dim_stats,
            **cap_stats,
        },
        "top": _format_ranked_for_trace(ranked, top=L3_INPUT_TOP_K),
    }

    # L3 trace
    payload = build_payload(top_k, profile, ctx, meal_log, n=5, n_explore=2)
    l3_trace = {
        "used": bool(l3_collector.get("llm_called")),
        "status": l3_collector.get("status"),
        "model": l3_collector.get("model"),
        "resolved_provider": l3_collector.get("resolved_provider"),
        "raw_response": l3_collector.get("raw_response", ""),
        "raw_response_chars": l3_collector.get("raw_response_chars", 0),
        "system_prompt_chars": l3_collector.get("system_prompt_chars"),
        "user_message_chars": l3_collector.get("user_message_chars"),
        "user_message_full": l3_collector.get("user_message_full"),
        "tool_input": l3_collector.get("tool_input"),
        "stop_reason": l3_collector.get("stop_reason"),
        "fallback_reason": l3_collector.get("fallback_reason"),
        "parsed_candidates": l3_collector.get("parsed_candidates"),
        # Codex H2 修: narrative 必须落 trace, 否则 Faithful Refine 执行证据链断裂
        # (response 顶层有 narrative, trace 缺会让 debug-ui Replay 找不到 narrative 来源).
        "narrative": l3_collector.get("narrative", ""),
        "payload_to_llm": payload,
        "n_returned": len(reranked),
        "used_fallback": bool(l3_collector.get("used_fallback")),
        # D-079 followup: 写入 LLM 真实 latency / usage / sampling 让 DagHeader
        # 能渲染 cache_hit% / token 概览 (BackendTraceL3 早已声明这些 optional
        # 字段, 但之前的 _build_trace 漏拷). 旧 trace 这些字段不存在, adapter 兜底.
        "latency_ms": l3_collector.get("latency_ms"),
        "usage": l3_collector.get("usage"),
        "max_tokens": l3_collector.get("max_tokens"),
        "temperature": l3_collector.get("temperature"),
    }

    final_view = [_format_final_candidate(i + 1, c) for i, c in enumerate(reranked)]

    # __frozen: What-if 重跑的自包含上下文 (D-079 Codex #1/#4/Q3 修订)
    try:
        from chisha.l1_prefs import load_prefs
        l1_prefs_snapshot = load_prefs(root=root)
    except Exception:
        l1_prefs_snapshot = None
    # L2 meal_log view: variety_bonus_score 看最近 7 天 (score.py:181 cutoff = today-7d)
    cutoff = today - dt.timedelta(days=7)
    l2_meal_log_view = []
    for entry in meal_log or []:
        ts = entry.get("timestamp") or entry.get("date") or ""
        try:
            d = dt.date.fromisoformat(ts[:10])
        except (ValueError, TypeError):
            continue
        if d >= cutoff:
            l2_meal_log_view.append(entry)

    # combos normalize: 2467 combos 直存会膨胀到 6MB+, 必须 dedupe restaurants/dishes
    # __frozen.l1_combos = [{restaurant_id, dish_ids}], 配合 restaurants/dishes 表
    # What-if 重跑时 rehydrate refs (PR-2 实现)
    frozen_restaurants, frozen_dishes, frozen_combo_refs = _normalize_combos(combos)
    frozen = {
        "ctx": ctx.to_llm_dict(),
        "today": today.isoformat(),
        "meal_type": meal_type,
        "zone": zone,
        "profile_snapshot": profile,
        "l1_combos": frozen_combo_refs,         # [{restaurant_id, dish_ids}]
        "restaurants": frozen_restaurants,       # id → minimal restaurant record
        "dishes": frozen_dishes,                 # id → minimal dish record (含 scoring nutrition_profile)
        "l1_prefs_snapshot": l1_prefs_snapshot,
        "l2_meal_log_view": l2_meal_log_view,
    }

    return {
        "__version": trace_store.TRACE_SCHEMA_VERSION,
        "__source": "production",
        "__parent_session_id": None,
        "__llm_called": bool(l3_collector.get("llm_called")),
        "__frozen": frozen,
        "__config": {
            "use_llm_rerank": use_llm_rerank,
            "n_return": 5,
            "n_explore": 2,
            "daily_mood": daily_mood,
            "refine_text": None,
            "profile_overrides": None,
        },
        "session_id": session_id,
        "started_at": started_at.isoformat(),
        "total_latency_ms": total_latency_ms,
        "ctx_latency_ms": ctx_latency_ms,
        "recall_latency_ms": recall_latency_ms,
        "score_latency_ms": score_latency_ms,
        "rerank_latency_ms": rerank_latency_ms,
        # final_latency_ms = trace_build + 序列化, 等 recommend_meal 返完才能测,
        # 这里给出累计粗值供 UI 展示 (rerank 完到 trace 写盘前)
        "final_latency_ms": max(0, total_latency_ms
                                 - ctx_latency_ms - recall_latency_ms
                                 - score_latency_ms - rerank_latency_ms),
        "l1": l1_trace,
        "l2": l2_trace,
        "l3": l3_trace,
        "final": final_view,
        "refine": {"applied": False},
    }


if __name__ == "__main__":
    import sys
    meal = sys.argv[1] if len(sys.argv) > 1 else "lunch"
    out = recommend_meal(meal)
    print(json.dumps(out, ensure_ascii=False, indent=2))

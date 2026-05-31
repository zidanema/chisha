"""recommend_meal 主入口 (DESIGN §5.7).

D-049 后单一实现: build_context → 召回 → score V2 (~12维) → LLM rerank top60→5
(3 exploit + 2 explore) → 创建 session → §5.7 JSON.

旧 V1 路径 (D-024 简化版: 打分 → top 3 + LLM 写 reason) 已删除 (D-049).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from chisha.recall import (
    load_meal_log,
    load_profile,
    load_zone_data,
    recall,
)
from chisha.rerank import rerank as v2_rerank
from chisha.session import create_session, save_session

# D-104 Step1a: card/session 格式化 helper 抽到 core_api_helpers (agent-only core).
# 此处 re-import 保后向兼容 (api.* 旧引用仍可用; api 内部 recommend_meal /
# _normalize_combos 直接用这些名字)。
from chisha.core_api_helpers import (  # noqa: F401
    _SCORING_NUTRITION_KEYS,
    _format_v2_candidate,
    _gen_session_id,
    _resolve_zone,
)


def _default_root() -> Path:
    """T-DIST-01 B.1: install_root 单一权威源 (dev=repo root, wheel=chisha/ 包目录)."""
    from chisha.install_root import install_root
    return install_root()


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
        root: 仓库根目录 (测试可注入), 默认 install_root() (dev=repo root, wheel=包目录).
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
    today = today or clock.today(root)
    session_id = _gen_session_id(meal_type)
    started_at = clock.now_utc(root)
    import time as _time
    _t_start = _time.monotonic()

    # 1-3. 确定性编排 (D-074): 反馈冻结 (§8.1 单次构建) + Context + 召回 (L1, 强负
    # 反馈 30 天剔除) + L2 打分 + 三层 cap. 抽到 agent_orchestration.prepare_candidates,
    # in-process recommend_meal / refine / AI-friendly CLI 共用单一可信源 (codex #1).
    # R1 = intent=None/refine_input=None → 不跑 reference/subtype (与历史行为一致).
    from chisha.agent_orchestration import prepare_candidates
    prep = prepare_candidates(
        profile=profile, rests=rests, tagged=tagged, meal_log=meal_log,
        meal_type=meal_type, today=today, root=root,
        daily_mood=daily_mood, refine_input=None, intent=None,
    )
    fb_signal = prep.fb_signal
    feedback_evicted_rids = prep.feedback_evicted_rids
    ctx = prep.ctx
    ctx_latency_ms = prep.ctx_latency_ms
    combos = prep.combos
    recall_latency_ms = prep.recall_latency_ms
    feedback_avoided_names = prep.feedback_avoided_names
    ranked_raw = prep.ranked_raw
    ranked = prep.ranked
    score_latency_ms = prep.score_latency_ms
    # 4. LLM 精排 topK → 5 (3 exploit + 2 explore, D-015; D-046: 30 → 60) (L3)
    top_k = prep.top_k
    # D-079: trace_collector 捕获 LLM 中间状态 (Codex Q3: 传 today 防 fallback 漂移)
    # T-P1b-02: collector 始终是 dict, narrative 也要在 Live (persist_trace=False)
    # 模式下拿到给前端展示. _build_trace 只在 persist_trace=True 时跑.
    l3_collector: dict = {}
    _t0 = _time.monotonic()
    reranked = v2_rerank(top_k, profile, context=ctx, meal_log=meal_log,
                          n=5, n_explore=2, refine=False, use_llm=use_llm_rerank,
                          root=root,
                          today=today, trace_collector=l3_collector,
                          # B-001/D-098: 本 zone 真剔除店名 → narrative 忠实透传
                          feedback_avoided_names=feedback_avoided_names)
    rerank_latency_ms = int((_time.monotonic() - _t0) * 1000)
    # 5. 创建 session (供 refine 二轮用)
    state = create_session(session_id, meal_type, zone, daily_mood=daily_mood)
    state.last_candidates = [_minimize_candidate(c) for c in reranked]
    save_session(state, root)

    # T-P1b-01: status_bar payload. 跑一次轻量 _build_l1_trace 拿 hard_filter_events
    # (recall path 的 L0-A/B 事件), 给前端 always-on 状态条派生数据.
    # Codex M1 修: status_bar 与 _build_trace 共用同一份 _build_l1_trace 结果,
    # 之前 status_bar 跑一次 + _build_trace 又跑一次 → 100ms 重复开销 + 边界漂移风险.
    from chisha.status_bar import build_status_bar_safe
    status_bar, l1_trace_cache = build_status_bar_safe(
        profile, rests, tagged, meal_log, today, meal_type,
        feedback_signal=fb_signal,
    )

    # T-P1b-02: L3 narrative (顶层"为什么推这 5 道"摘要)
    # collector 里若 LLM 路径触发, narrative 已写入; fallback / 旧 trace 为空
    narrative = l3_collector.get("narrative", "") if isinstance(l3_collector, dict) else ""

    out = {
        "session_id": session_id,
        "meal_type": meal_type,
        "zone": zone,
        "round": 1,
        "version": "v2",
        "generated_at": clock.now_utc(root).isoformat(),
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
                # B-001/D-098: 冻结同一份 fb_signal + 本 zone 避开店名 (单次构建, §8.1)
                feedback_signal=fb_signal,
                feedback_avoided_names=feedback_avoided_names,
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
    feedback_signal: dict | None = None,  # B-001/D-098: 单次构建的反馈信号, 冻结进 __frozen
    feedback_avoided_names: list[str] | None = None,  # B-001/D-098: 本 zone 真剔除店名 (narrative)
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
            profile, rests, tagged, meal_log, today, meal_type=meal_type,
            feedback_signal=feedback_signal,
        )

    # L2 trace (复用 ranked, 不重算; F-016 ⑥: dim_stats 走 trace_helpers 单一源)
    from chisha.trace_helpers import dim_stats_topk
    caps = resolve_caps(profile)
    dim_stats = dim_stats_topk(ranked[:L3_INPUT_TOP_K])
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

    # L3 trace (D-089-S1: 统一走 trace_helpers.build_l3_trace_from_collector,
    # 消灭 R1 主链路 / refine 路径双份 L3 序列化漂移. helper 含 system_prompt_full
    # 等 D-089 新增字段, 自动跟前端 BackendL3Llm shape 对齐.)
    from chisha.trace_helpers import build_l3_trace_from_collector
    payload = build_payload(top_k, profile, ctx, meal_log, n=5, n_explore=2)
    l3_trace = build_l3_trace_from_collector(
        l3_collector, payload_to_llm=payload, n_returned=len(reranked)
    )

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
    # What-if 重跑时 rehydrate refs
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
        # B-001/D-098: 冻结短链路反馈信号 (D-079 零 runtime read). What-if 重跑 score
        # 用冻结值不重读 store. schema bump 3→4 (CONTRACTS frozen 字段变更要求);
        # v3 仍 accepted, 老 trace 缺此键 → .get()→None → 无反馈效果.
        "feedback_signal_snapshot": feedback_signal,
        # B-001/D-098 (T-FB-05 narrative): 本次因强负反馈真剔除 + 在本 zone 的店名
        # (api 算好冻结, What-if 直接用 — frozen l1_combos 已不含被剔除店, 无法重算).
        "feedback_avoided_names": feedback_avoided_names,
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

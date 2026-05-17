"""D-079 PR-2: What-if 重跑核心算法.

读 base trace → 反序列化 __frozen → 用 overrides patch profile → 重跑 L2 + L3 →
返新 trace dict (不写盘).

冻结边界 (DESIGN §4.1):
- ctx / today / meal_type / zone / l1_combos / l1_prefs_snapshot / l2_meal_log_view
  绝对不读 runtime state (load_prefs / dt.date.today / load_meal_log / clock.*)
- profile_snapshot 与 overrides.profile_overrides deep_merge 后作为新 profile
- use_llm_rerank 默认 False, 显式 True 才调 LLM (Codex +4 透明性)

Failure 由调用方 (web_api) 翻译成 HTTP code, 这里只抛 ValueError / 自定义异常.
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Any, Optional

from chisha import trace_store


logger = logging.getLogger(__name__)


# ────────────────────────── overrides 白名单

# WhatIfOverrides 允许的字段; 任何其它 key 触发 400 (端点层校验, 这里再防一层)
ALLOWED_OVERRIDE_KEYS = {
    "n_return",
    "n_explore",
    "use_llm_rerank",
    "profile_overrides",
}


class InvalidOverrides(ValueError):
    """overrides 含非白名单字段 / 类型不合法. 端点应 400."""


class InvalidBaseTrace(ValueError):
    """base trace 自身问题: __source != production / 缺 __frozen / today 不合法.

    Codex PR-2 FIX-NOW #2: 与 InvalidOverrides 分型, 不被裸 ValueError 误捕.
    端点根据具体子类决定 400 (用户请求错) vs 409 (trace 元数据冲突) vs 500.
    """


def validate_overrides(overrides: dict | None) -> dict:
    """白名单校验 + 默认值. 返规范化后的 overrides."""
    if overrides is None:
        return {}
    if not isinstance(overrides, dict):
        raise InvalidOverrides(
            f"overrides must be dict, got {type(overrides).__name__}"
        )
    extra = set(overrides.keys()) - ALLOWED_OVERRIDE_KEYS
    if extra:
        raise InvalidOverrides(
            f"overrides contains non-allowed keys: {sorted(extra)}; "
            f"allowed = {sorted(ALLOWED_OVERRIDE_KEYS)}"
        )
    # 类型轻校验, 防 use_llm_rerank='hahaha' 之类
    if "n_return" in overrides and not isinstance(overrides["n_return"], int):
        raise InvalidOverrides("n_return must be int")
    if "n_explore" in overrides and not isinstance(overrides["n_explore"], int):
        raise InvalidOverrides("n_explore must be int")
    if "use_llm_rerank" in overrides and overrides["use_llm_rerank"] is not None:
        if not isinstance(overrides["use_llm_rerank"], bool):
            raise InvalidOverrides("use_llm_rerank must be bool or null")
    if "profile_overrides" in overrides and overrides["profile_overrides"] is not None:
        if not isinstance(overrides["profile_overrides"], dict):
            raise InvalidOverrides("profile_overrides must be dict or null")
    return overrides


# ────────────────────────── 反序列化

def rehydrate_combos(frozen: dict) -> list[dict]:
    """把 __frozen.l1_combos (refs) + restaurants/dishes 表反组装回完整 combos.

    score.py 消费的 shape: combo = {restaurant: {...}, dishes: [{...}], ...}.
    本函数只搬数据, 不算分 — score_breakdown 等运行时字段由 rank_combos 重写.
    """
    refs = frozen.get("l1_combos") or []
    restaurants = frozen.get("restaurants") or {}
    dishes_tbl = frozen.get("dishes") or {}

    combos: list[dict] = []
    for ref in refs:
        rid = ref.get("restaurant_id")
        rest = dict(restaurants.get(rid) or {})
        dish_list: list[dict] = []
        for did in ref.get("dish_ids") or []:
            d = dishes_tbl.get(did)
            if d:
                dish_list.append(dict(d))
        # 注: 不加 combo_index. 生产 recall() 输出的 combos 没此字段,
        # fallback_rerank 走 combo.get("combo_index", -1) → -1, 零 overrides 等价
        # 要求这里也是 -1.
        combos.append({"restaurant": rest, "dishes": dish_list})
    return combos


def deep_merge(base: dict, patch: dict | None) -> dict:
    """深合并 patch into base. patch=None → base copy.

    与 web_api._write_profile_preserving_comments 的 _deep_merge 行为一致:
    叶子值由 patch 覆盖, dict 递归合并, 列表整体替换.
    """
    import copy
    out = copy.deepcopy(base)
    if not patch:
        return out
    if not isinstance(patch, dict):
        return patch  # type: ignore[return-value]

    def _merge(dst: Any, src: Any) -> Any:
        if not isinstance(src, dict):
            return src
        if not isinstance(dst, dict):
            return src
        for k, v in src.items():
            if k in dst:
                dst[k] = _merge(dst[k], v)
            else:
                dst[k] = v
        return dst

    return _merge(out, patch)


# ────────────────────────── What-if 主入口

def what_if_rerun(
    base_session_id: str,
    overrides: dict | None,
    root: Optional[Path] = None,
) -> dict:
    """What-if 重跑. 读 base trace → frozen ctx + L1 → 重跑 L2 + L3 → 返新 trace.

    Args:
        base_session_id: 原 Replay 的 session id (trace 必须 __source=production)
        overrides: WhatIfOverrides dict, 白名单字段 (validate_overrides 校验)
        root: data root (sandbox 透传)

    Returns:
        新 trace dict (__source='what_if_preview', __parent_session_id=base_session_id,
        __llm_called=bool). **不写盘**, 端点直接返给前端.

    Raises:
        InvalidOverrides: overrides 含非法字段 (调用方 400)
        trace_store.TraceCorrupt: base trace 损坏 (调用方 500)
        trace_store.TraceVersionMismatch: schema 不匹配 (调用方 409)
        FileNotFoundError: base trace 不存在 (调用方 404)
        ValueError: base trace __source 非 production (调用方 400)
    """
    overrides = validate_overrides(overrides)

    base = trace_store.read_trace(base_session_id, root=root)
    if base is None:
        raise FileNotFoundError(f"trace {base_session_id!r} not found")
    if base.get("__source") != "production":
        raise InvalidBaseTrace(
            f"base trace source must be 'production', got {base.get('__source')!r}"
        )

    frozen = base.get("__frozen") or {}
    if not frozen:
        raise InvalidBaseTrace(
            "base trace missing __frozen — pre-D079 trace, Replay only, What-if N/A"
        )

    # 1. 反序列化 frozen 字段 (绝不读 runtime)
    combos = rehydrate_combos(frozen)
    profile = deep_merge(frozen.get("profile_snapshot") or {},
                         overrides.get("profile_overrides"))
    today_str = frozen.get("today")
    if not today_str:
        raise InvalidBaseTrace("base trace missing __frozen.today")
    try:
        today = dt.date.fromisoformat(today_str)
    except (ValueError, TypeError) as e:
        # 坏 trace (frozen.today 不是合法 ISO date) → InvalidBaseTrace, 调用方 400
        raise InvalidBaseTrace(
            f"base trace __frozen.today not ISO date: {today_str!r}: {e}"
        ) from e
    meal_type = frozen.get("meal_type") or "lunch"
    l1_prefs_snapshot = frozen.get("l1_prefs_snapshot")
    l2_meal_log_view = frozen.get("l2_meal_log_view") or []
    # B-001: feedback_view 走 frozen (D-079 红线: What-if 零 runtime read).
    # 旧 trace (pre-B-001) 没此字段 → [] = 不计 (与无反馈语义一致).
    feedback_view_frozen = frozen.get("feedback_view") or []
    ctx_dict = frozen.get("ctx") or {}

    n_return = overrides.get("n_return") or 5
    n_explore = overrides.get("n_explore")
    if n_explore is None:
        n_explore = 2
    use_llm = bool(overrides.get("use_llm_rerank"))

    # 2. 重跑 L2 (rank_combos + apply_caps)
    from chisha.score import rank_combos, apply_caps
    ranked_raw = rank_combos(
        combos, profile,
        meal_log=l2_meal_log_view,
        today=today,
        context=None,  # score.context_boost 自 D-073 起恒返 0.0 (空函数, 保 API
                       # 兼容), 传 None 与真 ctx 等价. 若以后重启 context-level
                       # 软调权, 需补 rebuild_ctx_from_dict 反序列化层.
        meal_type=meal_type,
        root=root,
        l1_prefs_override=l1_prefs_snapshot,
        feedback_view=feedback_view_frozen,  # B-001: frozen, 不读 disk
    )
    ranked = apply_caps(ranked_raw, profile)

    # 3. 重跑 L3 (fallback / LLM)
    from chisha.rerank import (
        L3_INPUT_TOP_K, fallback_rerank, rerank as v2_rerank,
    )
    top_k = ranked[:L3_INPUT_TOP_K]
    llm_called = False
    llm_attempted = False
    fallback_reason = ""

    # Codex PR-2 BLOCKER #1: v2_rerank LLM 失败时内部 fallback, 我们必须以
    # trace_collector 实际状态为准, 不能用调用是否返回来判 llm_called.
    rerank_collector: dict = {}
    if use_llm and top_k:
        try:
            # D-079 BLOCKER fix: 不传 root + 显式传 l1_prefs_override=snapshot,
            # 走 frozen 路径; _profile_block 内 sentinel 判定不会再 load_prefs
            # (违反 "What-if 零 runtime read" 红线). l1_prefs_snapshot 允许是
            # None (那餐 L1 尚无产物), sentinel 区分"显式 None"与"未传".
            reranked = v2_rerank(
                top_k, profile,
                context=None, meal_log=l2_meal_log_view,
                n=n_return, n_explore=n_explore,
                refine=False, use_llm=True,
                today=today,
                trace_collector=rerank_collector,
                l1_prefs_override=l1_prefs_snapshot,
                feedback_view=feedback_view_frozen,  # B-001
            )
        except Exception as e:
            # v2_rerank 自身不应抛 (内部已 fallback), 这里是 defense-in-depth
            fallback_reason = f"llm raised {type(e).__name__}: {e}"
            logger.warning("what_if LLM rerank failed, fallback: %s", fallback_reason)
            reranked = fallback_rerank(
                top_k, n=n_return, n_explore=n_explore,
                meal_log=l2_meal_log_view, today=today,
            )
            rerank_collector = {
                "llm_attempted": True, "llm_called": False,
                "used_fallback": True, "status": "fallback",
                "fallback_reason": fallback_reason,
            }
        llm_attempted = bool(rerank_collector.get("llm_attempted", True))
        llm_called = bool(rerank_collector.get("llm_called", False))
        if not fallback_reason:
            fallback_reason = rerank_collector.get("fallback_reason", "") or ""
    else:
        reranked = fallback_rerank(
            top_k, n=n_return, n_explore=n_explore,
            meal_log=l2_meal_log_view, today=today,
        )

    # 4. 组装 What-if response trace
    return _build_what_if_trace(
        base=base,
        ranked_raw=ranked_raw,
        ranked=ranked,
        reranked=reranked,
        profile=profile,
        today=today,
        meal_type=meal_type,
        l2_meal_log_view=l2_meal_log_view,
        ctx_dict=ctx_dict,
        overrides=overrides,
        llm_called=llm_called,
        llm_attempted=llm_attempted,
        fallback_reason=fallback_reason,
        base_session_id=base_session_id,
        # D-083: 把 frozen feedback_view + rerank_collector 透传, _build_what_if_trace
        # 才能写 feedback_view_snapshot + l3.feedback_block_rendered (Codex S3 BLOCKER)
        feedback_view_frozen=feedback_view_frozen,
        rerank_collector=rerank_collector,
    )


# ────────────────────────── trace 组装

def _build_what_if_trace(
    *,
    base: dict,
    ranked_raw: list[dict],
    ranked: list[dict],
    reranked: list[dict],
    profile: dict,
    today: dt.date,
    meal_type: str,
    l2_meal_log_view: list[dict],
    ctx_dict: dict,
    overrides: dict,
    llm_called: bool,
    llm_attempted: bool,
    fallback_reason: str,
    base_session_id: str,
    # D-083 Codex S3 BLOCKER fix
    feedback_view_frozen: list | dict | None = None,
    rerank_collector: dict | None = None,
) -> dict:
    """组装 What-if response trace, shape 对齐 production trace (供前端复用渲染)."""
    from chisha.debug_recommend import (
        _build_l2_cap_stats, _format_ranked_for_trace, _format_final_candidate,
    )
    from chisha.rerank import L3_INPUT_TOP_K
    from chisha.score import resolve_caps
    import statistics

    # L2 view (同 _build_trace 算法, 抽 dim_stats)
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
    # 统计, 前端 DagHeader L2 摘要要这些字段 (production trace 同步补).
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

    l3_trace = {
        "used": llm_called,
        "status": "ok" if llm_called else ("fallback" if llm_attempted else "skipped"),
        "model": None,
        "resolved_provider": None,
        "raw_response": "",
        "raw_response_chars": 0,
        "fallback_reason": fallback_reason,
        "n_returned": len(reranked),
        "used_fallback": not llm_called,
        # D-083 Codex S3 BLOCKER fix: 与生产 / debug live 同步暴露 prompt 渲染段
        "feedback_block_rendered": (rerank_collector or {}).get(
            "feedback_block_rendered"
        ),
    }

    # D-083 Codex S3 BLOCKER fix: feedback_view_snapshot 也写 What-if trace.
    # frozen.feedback_view 已含 feedback_trace (PR-1 落地后 build_feedback_view
    # 总返 4 个 sibling key, 写 trace 时整包冻结). 老 frozen (pre-D-083) 没此
    # 字段 → 空骨架兜底 (与 Live 路径一致).
    fb_trace = None
    if isinstance(feedback_view_frozen, dict):
        fb_trace = feedback_view_frozen.get("feedback_trace")
    fb_snapshot = fb_trace or {
        "today": today.isoformat(),
        "windows": {"ratings": 60, "calibrations": 7, "note_tokens": 14},
        "rating_signals": [], "calibration_rules": [],
        "note_breakdown": [],
        "global_token_freq": {"boost": {}, "penalty": {}},
        "global_active_tokens": {"boost": [], "penalty": []},
        "empty": True,
    }

    final_view = [_format_final_candidate(i + 1, c) for i, c in enumerate(reranked)]

    # __frozen 与 base 保持一致 (What-if 不能动 frozen, 前端对比双栏直接读)
    return {
        "__version": trace_store.TRACE_SCHEMA_VERSION,
        "__source": "what_if_preview",
        "__parent_session_id": base_session_id,
        "__llm_called": llm_called,
        "__llm_attempted": llm_attempted,
        "__frozen": base.get("__frozen") or {},   # 同 base
        "__config": {
            "use_llm_rerank": overrides.get("use_llm_rerank"),
            "n_return": overrides.get("n_return") or 5,
            "n_explore": overrides.get("n_explore") if overrides.get("n_explore") is not None else 2,
            "daily_mood": (base.get("__config") or {}).get("daily_mood"),
            "refine_text": None,
            "profile_overrides": overrides.get("profile_overrides"),
        },
        "session_id": f"whatif_{base_session_id}",  # UI 标识, 不写盘所以不需要稳定唯一
        "started_at": base.get("started_at"),       # 沿用 base 时间, 供前端对比
        "total_latency_ms": None,                    # What-if 不测延时 (单次重跑数 ms)
        "ctx_latency_ms": 0,                         # frozen, 不重跑
        "recall_latency_ms": 0,                      # frozen, 不重跑
        "score_latency_ms": None,
        "rerank_latency_ms": None,
        "final_latency_ms": None,
        "l1": base.get("l1") or {"trace": "frozen, see base"},  # 直接复用 base 的 L1 trace
        "l2": l2_trace,
        "l3": l3_trace,
        "final": final_view,
        "refine": {"applied": False},
        "meal_type": meal_type,
        "zone": (base.get("__frozen") or {}).get("zone"),
        "today": today.isoformat(),
        # D-083 Codex S3 BLOCKER fix: 顶层与 Live/Replay 同名同 schema
        "feedback_view_snapshot": fb_snapshot,
    }

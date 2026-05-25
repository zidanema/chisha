"""D-074 Phase 0: 共享确定性编排 (codex #1).

把 api.recommend_meal (R1) 与 refine.refine (R2+) 里"到 top_k 为止"的**确定性**
步骤抽成单一可复用入口, 供三方共用:
  - in-process recommend_meal / refine (delegate, 行为不变)
  - AI-friendly CLI (resolve-intent / 无 context start)

为什么必须共享 (设计第一原则 "确定性=代码"): 反馈短链路冻结 (单次 build_feedback_signal
+ feedback_avoided_names 透传)、recall 三桶 + 强负剔除、L2 打分 + cap、reference 软重排、
subtype 多样化 —— 这些守卫全在主链路里"做死". CLI 若自己 import recall/score 重拼,
会静默丢掉其中一部分, 把确定性退化成 prompt 期望 (codex review HIGH #1).

**不含 rerank LLM 调用** (那是外置给 agent 的智能步骤), 也不含 intent 抽取 LLM 调用
(intent 由调用方先备好传入). 本模块零 LLM.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from chisha.context import ContextSnapshot, build_context
from chisha.recall import recall
from chisha.rerank import L3_INPUT_TOP_K
from chisha.score import apply_caps, rank_combos

logger = logging.getLogger(__name__)

# build_feedback_signal 未传时的 sentinel (区分"没传, 内部 best-effort build"
# vs "显式传 None = 无反馈信号"). 不能用 None 当默认 — None 是合法的"无反馈".
_UNSET_FB: Any = object()


@dataclass
class PreparedCandidates:
    """prepare_candidates 产物: 到 top_k 为止的全部确定性中间状态 + trace 所需输入.

    apply-rerank / in-process rerank 后, 配合 reranked + l3_collector 即可组装完整 trace.
    """
    ctx: ContextSnapshot
    combos: list[dict]
    ranked_raw: list[dict]        # cap 前 (trace cap 前后多样性对比用)
    ranked: list[dict]            # cap + reference + subtype 后
    top_k: list[dict]             # ranked[:L3_INPUT_TOP_K], 给 rerank
    fb_signal: dict | None        # B-001/D-098 单次构建的短链路反馈信号 (§8.1)
    feedback_avoided_names: list[str]   # 本 zone 真剔除店名 (narrative 忠实)
    feedback_evicted_rids: set[str]
    recall_fallback_events: list[dict]  # refine 三级回落事件 (R1 为空)
    reference_resolved: Any = None      # ResolvedReference | None (refine reference 软重排)
    reference_source: str = "none"      # "v2_intent" / "raw_parser" / "none"
    subtype_diversified: bool = False
    ctx_latency_ms: int = 0
    recall_latency_ms: int = 0
    score_latency_ms: int = 0


def _build_fb_signal(today: dt.date, root: Path | None) -> dict | None:
    """B-001/D-098: 短链路反馈信号单次构建 (§8.1). best-effort, 失败降级 None."""
    try:
        from chisha.feedback_signal import build_feedback_signal
        from chisha.feedback_store import load_store
        return build_feedback_signal(load_store(root), today, root=root)
    except Exception as e:
        logger.warning("feedback_signal build failed (non-fatal): %s: %s",
                       type(e).__name__, e)
        return None


def prepare_candidates(
    *,
    profile: dict,
    rests: list[dict],
    tagged: list[dict],
    meal_log: list[dict],
    meal_type: str,
    today: dt.date,
    root: Path | None,
    daily_mood: str | None = None,
    refine_input: str | None = None,
    intent: Any = None,                  # RefineIntentV2 | None (调用方已抽好)
    n: int = 5,
    fb_signal: Any = _UNSET_FB,          # 调用方可传预构建; 未传 → 内部 best-effort build
) -> PreparedCandidates:
    """到 top_k 为止的确定性编排. R1 (intent=None) 等价 recommend_meal 主链路;
    R2 (intent 非空) 等价 refine 主链路 (含 reference 软重排 + subtype 多样化).

    Args:
        intent: RefineIntentV2 | None.
            - None (recommend_meal R1): 无 intent 进 recall/score, **不跑** reference/subtype.
            - 非 None 对象 (refine R2, 即便 is_empty()): is_empty 时 recall/score 收 None
              (eff_intent), 但 reference 块**仍跑** (raw_parser 对 refine_input 原文生效);
              subtype 仅 cuisine_want 非空时跑.
        refine_input: 用户 refine 原话 (R1 为 None). 进 ctx.refine_input + reference parser.
        fb_signal: _UNSET → 内部 build; 显式传 (含 None) → 用传入值. refine R2 必须由
            调用方在 intent 抽取前冻结后显式传入 (codex A1: 抽取窗口反馈写入不污染本轮).
    """
    if fb_signal is _UNSET_FB:
        fb_signal = _build_fb_signal(today, root)

    # intent 归一: is_empty() 视为无 intent (与主链路 `intent if not intent.is_empty() else None` 一致)
    eff_intent = intent if (intent is not None and not intent.is_empty()) else None

    feedback_evicted_rids: set[str] = set()
    recall_fallback_events: list[dict] = []

    # 1. Context (R1: refine_input=None/intent=None; R2: 带 refine_input + intent)
    _t0 = time.monotonic()
    ctx = build_context(
        profile=profile, meal_log=meal_log, meal_type=meal_type, today=today,
        daily_mood=daily_mood, refine_input=refine_input,
        refine_intent=eff_intent.to_log_dict() if eff_intent is not None else None,
    )
    ctx_latency_ms = int((time.monotonic() - _t0) * 1000)

    # 2. 召回 (L1) — 强负反馈剔除 + (R2) intent 三桶/avoid 硬过滤
    _t0 = time.monotonic()
    combos = recall(
        profile, rests, tagged, meal_log, today, meal_type=meal_type,
        intent=eff_intent, n=n,
        recall_fallback_events=recall_fallback_events,
        feedback_signal=fb_signal,
        feedback_evicted_out=feedback_evicted_rids,
    )
    recall_latency_ms = int((time.monotonic() - _t0) * 1000)

    # narrative 避开店名 = recall 实际剔除集 (回填) → 名字 (D-085 忠实, 不预算)
    _evict_names = (fb_signal or {}).get("evict_names") or {}
    feedback_avoided_names = [
        _evict_names[rid] for rid in sorted(feedback_evicted_rids)
        if rid in _evict_names
    ]

    # 3. L2 打分 + cap (R2: intent 进 intent_match_bonus + cuisine_want 免 cap)
    _t0 = time.monotonic()
    ranked_raw = rank_combos(
        combos, profile, meal_log, today, context=ctx, meal_type=meal_type,
        root=root, intent=eff_intent, feedback_signal_override=fb_signal,
    )
    ranked = apply_caps(ranked_raw, profile, intent=eff_intent)

    # 4. (refine only) reference 软重排 + subtype 多样化. recommend_meal (intent=None)
    #    完全跳过. **行为关键** (codex 漂移点): 原 refine 的 reference 块**不** gate
    #    在 intent.is_empty() 上 — 它有 raw_parser fallback, 对 user_input 原文直接
    #    生效 (例 "比昨天清淡点" 即便结构化 intent 全空也要解析). 故 gate 在 is_refine
    #    (调用方传了 intent 对象 = refine 调用), 且 _apply_reference 收原始 intent
    #    (空 intent → intent.reference=None → 落 raw_parser). subtype gate 在 cuisine_want.
    is_refine = intent is not None
    reference_resolved: Any = None
    reference_source = "none"
    subtype_diversified = False
    if is_refine:
        ranked, reference_resolved, reference_source = _apply_reference(
            ranked, intent, refine_input or "", today, root,
        )
        if intent.cuisine_want:
            try:
                from chisha.subtype_diversity import diversify_by_subtype
                ranked = diversify_by_subtype(ranked)
                subtype_diversified = True
            except Exception as e:
                logger.warning("subtype diversify failed (non-fatal): %s: %s",
                               type(e).__name__, e)
    score_latency_ms = int((time.monotonic() - _t0) * 1000)

    top_k = ranked[:L3_INPUT_TOP_K]

    return PreparedCandidates(
        ctx=ctx, combos=combos, ranked_raw=ranked_raw, ranked=ranked, top_k=top_k,
        fb_signal=fb_signal, feedback_avoided_names=feedback_avoided_names,
        feedback_evicted_rids=feedback_evicted_rids,
        recall_fallback_events=recall_fallback_events,
        reference_resolved=reference_resolved, reference_source=reference_source,
        subtype_diversified=subtype_diversified,
        ctx_latency_ms=ctx_latency_ms, recall_latency_ms=recall_latency_ms,
        score_latency_ms=score_latency_ms,
    )


def _apply_reference(
    ranked: list[dict],
    intent: Any,
    user_input: str,
    today: dt.date,
    root: Path | None,
) -> tuple[list[dict], Any, str]:
    """T-P2-01 reference 软重排 (从 refine.py 原样搬移, 行为不变).

    优先 V2 intent.reference (LLM 已结构化), raw_text parser 作 fallback (Codex M3).
    返回 (重排后 ranked, resolved_reference | None, reference_source).
    """
    resolved_reference: Any = None
    reference_source = "none"
    try:
        from chisha.reference_resolver import (
            ReferenceQuery, _extract_days_back, _extract_meal_hint,
            apply_relation, parse_reference_text, resolve_reference,
        )
        ref_query = None
        v2_ref = intent.reference if intent.reference else None
        v2_rel = (v2_ref or {}).get("relation")
        if v2_rel in ("lighter", "similar_but_different_venue"):
            db = _extract_days_back(user_input)
            mh = _extract_meal_hint(user_input)
            if db is None and mh is None:
                db = -2
            ref_query = ReferenceQuery(
                raw_text=user_input, relation=v2_rel, days_back=db, meal_hint=mh,
            )
            reference_source = "v2_intent"
        if ref_query is None:
            ref_query = parse_reference_text(user_input)
            if ref_query is not None:
                reference_source = "raw_parser"
        if ref_query is not None:
            resolved_reference = resolve_reference(ref_query, today=today, root=root)
            if resolved_reference is not None:
                if resolved_reference.relation in (
                    "lighter", "similar_but_different_venue", "similar"
                ):
                    ranked = apply_relation(ranked, resolved_reference)
                else:
                    resolved_reference = None
                    reference_source = "none"
    except Exception as e:
        logger.warning("reference resolve/apply failed (non-fatal): %s: %s",
                       type(e).__name__, e)
    return ranked, resolved_reference, reference_source

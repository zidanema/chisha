"""refine_recommendation API (D-094.1 V2-only 版).

D-094.1 修订要点 (推翻 D-073 V1 双模式 + 切 V2 单一):
  - V1 refine_intent.py 整模块退役; refine_intent_v2 是唯一意图解析层
  - V1→V2 桥接代码砍掉, 下游 (recall / score / rerank) 直接消费 V2 intent
  - response 保留 refine_intent 字段名 (前端兼容), 内容直接是 V2 shape; 砍 refine_intent_v2 冗余 alias
  - V2 extract 必走 sync (V1 已无 fallback, 不再需要 async/off 三模)

数据流:
  user_input → extract_refine_intent_v2 → RefineIntentV2
    → recall(intent=...) 三桶 + intent-aware combo 排序 (V2 properties: cuisine_want/ingredient_want/cuisine_avoid/cuisine_candidates_expanded/brand_avoid/cooking_method_avoid)
    → rank_combos(intent=...) L2 intent_match_bonus + refine_weight_overlay (V2 oil/wants_soup/staple_want/staple_avoid/price_band)
    → rerank(ctx.refine_intent=...) L3 看 V2 结构化 + raw_understanding
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from chisha.context import build_context
from chisha.debug_recommend import _build_l1_trace
from chisha.recall import recall
from chisha.refine_intent_v2 import RefineIntentV2, extract_refine_intent_v2


from chisha.rerank import rerank
from chisha.score import apply_caps, rank_combos
from chisha.session import SessionState, load_session, save_session


# ─────────────────────── D-073: refine_intent trace ───────────────────────

_INTENT_TRACE_FILENAME = "logs/refine_intent_trace.jsonl"


def _build_reference_resolved(resolved, source: str) -> dict | None:
    """reference resolve 命中时的 8 字段执行证据 dict (trace + response 共用单源)."""
    if resolved is None:
        return None
    return {
        "relation": resolved.relation,
        "raw_text": resolved.raw_text,
        "base_session_id": resolved.base_session_id,
        "base_meal_type": resolved.base_meal_type,
        "base_started_at": resolved.base_started_at,
        "n_base_combos": len(resolved.base_combos or []),
        "notes": list(resolved.notes or []),
        "source": source,
    }


def _append_intent_trace(trace: dict[str, Any], root: Path) -> None:
    """非阻塞写一行 jsonl. 失败静默不阻断 refine 主流程."""
    try:
        p = root / _INTENT_TRACE_FILENAME
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    except Exception:
        pass


def refine(
    session_id: str,
    user_input: str,
    profile: dict,
    rests: list[dict],
    tagged: list[dict],
    meal_log: list[dict],
    root: Path,
    today: dt.date | None = None,
    n: int = 5,
    use_llm: bool | None = None,
) -> dict:
    """refine_recommendation 主入口 (D-073 v2).

    Args:
        session_id: 上一轮 recommend_meal 的 session_id.
        user_input: 用户自然语言反馈 ("想吃湖南菜, 肉多一点").
        profile / rests / tagged / meal_log / today: 推荐数据.
        root: 仓库根目录 (用于 session 落盘 + trace 写入).
        n: 输出候选数, refine 时 explore_count=0.
        use_llm: LLM 开关 (None=auto).

    Raises:
        FileNotFoundError: session 不存在或已过期.
    """
    state = load_session(session_id, root)
    if state is None:
        raise FileNotFoundError(
            f"Session {session_id!r} 不存在或已过期, 请先调 recommend_meal"
        )

    # Codex M2: 统一走 clock.today() (sandbox 启用时返虚拟 date).
    # 之前 dt.date.today() vs clock.today() 不一致, 跨午夜/sandbox 边界会让
    # "昨天/上次" reference resolver 跟主推荐链路时间漂移.
    from chisha import clock
    today = today or clock.today(root)

    # B-001/D-098 (codex A1 等价性修复): fb_signal 必须在 intent 抽取**之前**冻结
    # (与原 refine 顺序一致), 避免抽取 LLM 调用窗口内反馈写入污染本轮排序; 同时让
    # _t_start 在 fb 构建之后 (total_latency_ms 不含 fb 构建, 跟原版口径一致).
    # 显式传入 prepare_candidates, 不让其内部重建.
    from chisha.agent_orchestration import _build_fb_signal, prepare_candidates
    fb_signal = _build_fb_signal(today, root)

    # D-089-S2: 总耗时埋点, 供 round trace kpi.latency_ms (跟 R1 一致).
    import time as _time
    _t_start = _time.time()

    # 1. extract_refine_intent_v2: user_input → V2 结构化意图 (LLM, in-process 自抽;
    #    AI-friendly CLI 改走 build_extract_spec 外置给 agent, 二者复用同 prompt).
    # D-094.1: V1 已退役, sync 直出. trace_collector 落 R2 round.refine_intent_llm.
    refine_intent_llm_collector: dict = {}
    intent: RefineIntentV2 = extract_refine_intent_v2(
        text=user_input,
        use_llm=use_llm,
        profile_llm=profile.get("llm"),
        trace_collector=refine_intent_llm_collector,
    )

    # 2-4. 确定性编排 (D-074): Context (refine_input + intent) + recall (intent 三桶/
    # avoid + 强负反馈剔除) + L2 打分 + 三层 cap + reference 软重排 + subtype 多样化.
    # 抽到 agent_orchestration.prepare_candidates, in-process refine / recommend_meal /
    # AI-friendly CLI 共用 (codex #1). fb_signal 已在上方冻结, 显式传入复用 (§8.1).
    prep = prepare_candidates(
        profile=profile, rests=rests, tagged=tagged, meal_log=meal_log,
        meal_type=state.meal_type, today=today, root=root,
        daily_mood=state.daily_mood, refine_input=user_input, intent=intent, n=n,
        fb_signal=fb_signal,
    )
    fb_signal = prep.fb_signal
    ctx = prep.ctx
    combos = prep.combos
    feedback_avoided_names = prep.feedback_avoided_names
    ranked_raw = prep.ranked_raw
    ranked = prep.ranked
    recall_fallback_events = prep.recall_fallback_events
    resolved_reference = prep.reference_resolved
    reference_source = prep.reference_source
    subtype_diversified = prep.subtype_diversified

    # D-046: top60 给 L3
    from chisha.rerank import L3_INPUT_TOP_K
    top_k = prep.top_k

    # 5. L3 LLM rerank (ctx 携带 refine_input + refine_intent)
    # D-078.2 Codex S2 FIX-NOW: root 必须透传, 否则 refine 二轮 _profile_block
    # 走默认 (project root 兜底), sandbox 启用时读不到沙盒 long_term_prefs.json
    # (或反过来污染 prod), 行为信号在 refine 链路静默缺失.
    # T-P1b-02: 注入 trace_collector dict, 拿 narrative 给前端展示.
    l3_collector: dict = {}
    reranked = rerank(top_k, profile, context=ctx, meal_log=meal_log,
                       n=n, n_explore=0, refine=True, use_llm=use_llm,
                       root=root, trace_collector=l3_collector,
                       feedback_avoided_names=feedback_avoided_names)

    # D-089-S2: refine round 必须落 L1/L2/L3 完整切片 (trace self-contained 原则).
    # 之前 web_api 落盘时 l1/l2/l3=None stub, debug-ui R2 panel 全是空 — 现在 refine
    # 跑完 reranked 后立即构造完整 trace, 跟 R1 主链路 shape 一致.
    # try/except 兜底: 测试 fixture 用 minimal profile (缺 diversity / scoring_weights
    # 等字段) 会让 trace 构造 KeyError, 但 refine 主流程不应被诊断 trace 中断 —
    # trace 失败时降级到 None (web_api 落盘空 trace, debug-ui makeEmpty 兜 no_data).
    from chisha.trace_helpers import (
        build_l2_trace_for_round, build_l3_trace_from_collector,
    )
    from chisha.rerank import build_payload
    refine_intent_for_l1 = intent if not intent.is_empty() else None
    l1_trace: dict | None
    l2_trace: dict | None
    l3_trace: dict | None
    try:
        l1_trace, _l1_combos = _build_l1_trace(
            profile, rests, tagged, meal_log, today,
            meal_type=state.meal_type, intent=refine_intent_for_l1,
            feedback_signal=fb_signal,
        )
    except Exception as _l1_e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "refine L1 trace build failed (non-fatal): %s: %s",
            type(_l1_e).__name__, _l1_e,
        )
        l1_trace = None
    try:
        l2_trace = build_l2_trace_for_round(ranked_raw, ranked, profile)
    except Exception as _l2_e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "refine L2 trace build failed (non-fatal): %s: %s",
            type(_l2_e).__name__, _l2_e,
        )
        l2_trace = None
    try:
        refine_payload_to_llm = build_payload(
            top_k, profile, ctx, meal_log, n=n, n_explore=0,
        )
        l3_trace = build_l3_trace_from_collector(
            l3_collector, payload_to_llm=refine_payload_to_llm, n_returned=len(reranked),
        )
    except Exception as _l3_e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "refine L3 trace build failed (non-fatal): %s: %s",
            type(_l3_e).__name__, _l3_e,
        )
        l3_trace = None
    # D-089-S3: refine_intent LLM call trace → 走 serialize_llm_call_trace 统一 shape.
    # collector 空 (LLM 不可用 / 空 refine) 时 trace 也是 None.
    refine_intent_llm_trace: dict | None = None
    if refine_intent_llm_collector:
        try:
            from chisha.trace_helpers import serialize_llm_call_trace
            refine_intent_llm_trace = serialize_llm_call_trace(refine_intent_llm_collector)
        except Exception as _ri_e:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "refine_intent_llm trace serialize failed (non-fatal): %s: %s",
                type(_ri_e).__name__, _ri_e,
            )

    # 6. 更新 session
    state.round += 1
    state.last_candidates = [_minimize(c) for c in reranked]
    state.refine_history.append(user_input)
    save_session(state, root)

    # 7. trace 写入 (D-094.1: 砍 V1 intent 双存, 只保留 V2 intent)
    trace = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "session_id": session_id,
        "round": state.round,
        "user_input": user_input,
        "intent_v2": intent.to_log_dict(),
        "n_combos_recalled": len(combos),
        "n_after_l2": len(ranked),
        "n_returned": len(reranked),
        "candidate_ids": [c.get("restaurant", {}).get("name", "") + "|" +
                           ",".join(d.get("canonical_name", "")
                                     for d in c.get("dishes", [])[:2])
                          for c in reranked[:5]],
        # T-P2-01: reference resolve 命中时记一条 (debug + 用户语言交互可视化)
        # Codex M3: source 字段标 "v2_intent" / "raw_parser", debug-ui 可见执行来源
        "reference_resolved": _build_reference_resolved(
            resolved_reference, reference_source),
        # T-P2-02: cuisine_want 触发子类多样化时记一条
        "subtype_diversified": subtype_diversified,
    }
    _append_intent_trace(trace, root)

    # T-P1a-01: 若 refine 触发 L0-C methodology 解除, 通过响应携带事件
    # 让 web_api 在合并 base_trace 时 append 到 l1.hard_filter_events.
    # Codex review blocker #1 修复: refine path 走 recall, 不经 _build_l1_trace,
    # 故 _build_l1_trace 里的事件 emit 不会触发, 需在此 path 单独构造.
    refine_hard_filter_events: list[dict] = []
    if not intent.is_empty() and intent.allows_methodology_break():
        from chisha.l0_constraints import make_hard_filter_event
        refine_hard_filter_events.append(make_hard_filter_event(
            category="methodology",
            rule="refine_break_relaxed_plate_rule",
            dropped_count=0,
            kept_count=len(combos),
            refine_override=True,
        ))

    # T-P1b-02: L3 narrative (从 collector 取出, 给前端 RecCard 上方展示)
    narrative = l3_collector.get("narrative", "")

    # Codex H1 修: reference_resolved / subtype_diversified 必须透传给 web_api,
    # 让 base_trace["refine"] 落执行证据 (Faithful Refine 可审计性). 之前只写到
    # _append_intent_trace 本地 dict, 主 trace 看不到, debug-ui Replay 不可证.
    reference_resolved_field = _build_reference_resolved(
        resolved_reference, reference_source)

    # 8. 返回 response (字段对前端兼容)
    return {
        "session_id": session_id,
        "meal_type": state.meal_type,
        "zone": state.zone,
        "round": state.round,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "refine_input": user_input,
        # D-094.1: refine_intent 字段直接返 V2 shape (V1 已退役), 砍 refine_intent_v2 冗余 alias.
        "refine_intent": intent.to_log_dict(),
        "stats": {
            "n_dishes_total": len(tagged),
            "n_combos_recalled": len(combos),
            "n_combos_after_score": len(ranked),
            "n_returned": len(reranked),
        },
        "candidates": reranked,
        "narrative": narrative,
        # Codex H1: 给 web_api 落 base_trace["refine"] 用 (执行证据)
        "_reference_resolved": reference_resolved_field,
        "_subtype_diversified": subtype_diversified,
        # T-P1a-01: refine path L0-C 事件 (web_api 合并 base_trace 时 append)
        "_refine_hard_filter_events": refine_hard_filter_events,
        # T-P1a-02: 三级回落事件 (web_api 合并到 trace.l1.recall_fallback_events)
        "_refine_recall_fallback_events": recall_fallback_events,
        # D-089-S2: refine round 完整 L1/L2/L3 trace 切片. web_api.py 通过
        # trace_helpers.build_refine_round_payload 1:1 落到 R{n}.json,
        # debug-ui R2 panel 不再显 "no_data" 兜底.
        "l1_trace": l1_trace,
        "l2_trace": l2_trace,
        "l3_trace": l3_trace,
        # D-089-S3: refine_intent_v2 LLM call 完整 trace (system_prompt_full /
        # raw_response / latency / usage / model 等). 同 R1 L3 trace shape.
        "refine_intent_llm_trace": refine_intent_llm_trace,
        # D-089-S2: 总耗时 (kpi.latency_ms) — refine 跑完 L1+L2+L3 端到端.
        "total_latency_ms": int((_time.time() - _t_start) * 1000),
    }


def _minimize(c: dict) -> dict:
    """session 里只存关键 candidate 字段, 避免文件膨胀."""
    return {
        "rank": c.get("rank"),
        "is_explore": c.get("is_explore"),
        "combo_index": c.get("combo_index"),
        "fit_score": c.get("fit_score"),
        "restaurant": {
            "id": (c.get("restaurant") or {}).get("id"),
            "name": (c.get("restaurant") or {}).get("name"),
        },
        "dish_names": [d.get("canonical_name", "")
                       for d in c.get("dishes", [])],
    }

"""refine_recommendation API (D-073 v2).

D-073 重写要点 (推翻 D-035 在 refine 端 + D-071 全量):
  - 用 parse_refine_intent (开放结构) 取代 parse_feedback (chip 词表)
  - 砍 chips_to_taste_hints + _CHIP_TO_HINT (refine 端不再产 chip)
  - 砍 infer_refine_mood + want_soup 关键词识别 + mood_trace 全套 (D-071 superseded)
  - 断 append_feedback (refine 不沉淀长期偏好; 只走餐后反馈)
  - 写 logs/refine_intent_trace.jsonl 替代 mood_trace (观测用)

数据流:
  user_input → parse_refine_intent → RefineIntent
    → recall(intent=...) 三桶 + intent-aware combo 排序
    → rank_combos(intent=...) L2 intent_match_bonus 三档
    → rerank(ctx.refine_intent=...) L3 看结构化 + 原文
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
from pathlib import Path
from typing import Any

from chisha.context import build_context
from chisha.debug_recommend import _build_l1_trace  # D-089-S2: 复用 L1 trace 构造
from chisha.recall import recall
from chisha.refine_intent import RefineIntent, parse_refine_intent
from chisha.refine_intent_v2 import RefineIntentV2, extract_refine_intent_v2


# Codex H7 修: V2 抽取额外 ~6s LLM call, 仅 trace 用, 不该阻塞用户响应.
# 三种 mode:
#   "sync"  (默认): 同步抽 V2, 阻塞但 response 字段完整 (开发 / eval 时用)
#   "async":        后台线程抽 V2, response 立即给 placeholder, trace 后台补 (生产推荐)
#   "off":          完全跳过 V2 抽取, response/trace 给 placeholder (紧急 disable)
# 通过 env CHISHA_REFINE_V2_TRACE 控制.
def _v2_mode() -> str:
    return (os.environ.get("CHISHA_REFINE_V2_TRACE") or "sync").lower()


_V2_ASYNC_TRACE_FILENAME = "logs/refine_intent_v2_async_trace.jsonl"


def _async_extract_and_log(text: str, use_llm: bool | None,
                            profile_llm: dict | None,
                            session_id: str, round_n: int,
                            root: Path) -> None:
    """后台线程: 抽 V2 + 追加 trace, 失败静默. 主路径已返回."""
    try:
        v2 = extract_refine_intent_v2(text=text, use_llm=use_llm,
                                        profile_llm=profile_llm)
        entry = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "session_id": session_id,
            "round": round_n,
            "intent_v2": v2.to_log_dict(),
        }
        p = root / _V2_ASYNC_TRACE_FILENAME
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # daemon thread, 失败不影响任何已返回的主请求.
        pass
from chisha.rerank import rerank
from chisha.score import apply_caps, rank_combos
from chisha.session import SessionState, load_session, save_session


# ─────────────────────── D-073: refine_intent trace ───────────────────────

_INTENT_TRACE_FILENAME = "logs/refine_intent_trace.jsonl"


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

    # D-089-S2: 总耗时埋点, 供 round trace kpi.latency_ms (跟 R1 一致).
    import time as _time
    _t_start = _time.time()

    # 1. parse_refine_intent: user_input → 结构化意图 (V1, 下游 recall/score 消费)
    intent: RefineIntent = parse_refine_intent(
        text=user_input,
        use_llm=use_llm,
        profile_llm=profile.get("llm"),
    )

    # T-P1a-03 follow-up: V2 多 slot (Faithful Refine), trace 双存. 下游 recall/
    # score/L3 仍消费 V1 (T-P2-01/02 接入新 slot 时再切换). Codex H7 修: V2 多耗
    # ~6s LLM call, 仅 trace 用不该阻塞响应, 用 _v2_mode() 切 sync/async/off.
    # D-089-S3: 收集 refine_intent_v2 LLM call 完整 trace, 落 R2 round.refine_intent_llm.
    # async / off 路径不调 sync LLM, collector 保持 None (round trace 该字段为 None).
    refine_intent_llm_collector: dict | None = None
    v2_mode = _v2_mode()
    if v2_mode == "off":
        intent_v2 = RefineIntentV2(raw_text=user_input,
                                     raw_understanding="(V2 trace disabled)")
    elif v2_mode == "async":
        intent_v2 = RefineIntentV2(raw_text=user_input,
                                     raw_understanding="(V2 trace async pending)")
        # fire-and-forget: 后台抽 + 写 async trace 文件, 主路径不等
        # round 还未 +1 (state.round += 1 在下面), 这里用 state.round + 1 预测
        threading.Thread(
            target=_async_extract_and_log,
            args=(user_input, use_llm, profile.get("llm"),
                  session_id, state.round + 1, root),
            daemon=True,
        ).start()
    else:  # "sync" (default)
        refine_intent_llm_collector = {}
        intent_v2 = extract_refine_intent_v2(
            text=user_input,
            use_llm=use_llm,
            profile_llm=profile.get("llm"),
            trace_collector=refine_intent_llm_collector,
        )

    # D-094 (T-FR-05): V2 → V1 桥接, 把 V2 真消费字段拷到 V1 intent
    # 让 recall.py / score.py 直接 getattr(intent, "...") 即可消费.
    # 仅在 sync 模式且 V2 LLM 成功抽到时生效 (V2 默认空 list → 不破坏 R1/refine 0-diff 守门).
    _v2_redirect = intent_v2.redirect if intent_v2 and intent_v2.redirect else {}
    intent.cuisine_candidates_expanded = list(
        _v2_redirect.get("cuisine_candidates_expanded") or [])
    intent.brand_avoid = list(_v2_redirect.get("brand_avoid") or [])
    intent.cooking_method_avoid = list(
        _v2_redirect.get("cooking_method_avoid") or [])

    # 2. 重建 ContextSnapshot, 注入 refine_input (原文) + refine_intent (结构化)
    ctx = build_context(
        profile=profile,
        meal_log=meal_log,
        meal_type=state.meal_type,
        today=today,
        daily_mood=state.daily_mood,
        refine_input=user_input,
        refine_intent=intent.to_log_dict() if not intent.is_empty() else None,
    )

    # 3. recall (intent 进 combo 生成 + 三桶 + avoid 硬过滤)
    # T-P1a-02: recall_fallback_events 累积三级回落事件, web_api 合并到 base_trace.l1
    recall_fallback_events: list[dict] = []
    combos = recall(profile, rests, tagged, meal_log, today,
                     meal_type=state.meal_type,
                     intent=intent if not intent.is_empty() else None,
                     n=n,
                     recall_fallback_events=recall_fallback_events)

    # 4. L2 打分 (intent 进 intent_match_bonus 三档)
    # D-089-S2: 保留 ranked_raw (cap 前) 供 trace_helpers.build_l2_trace_for_round
    # 的 _build_l2_cap_stats 计算"cap 前后多样性对比" — 跟 R1 主链路 trace shape 一致.
    ranked_raw = rank_combos(combos, profile, meal_log, today,
                              context=ctx,
                              meal_type=state.meal_type,
                              root=root,
                              intent=intent if not intent.is_empty() else None)
    # D-043: refine 也走三层 cap
    # D-073 followup: 传 intent, cuisine_want 命中的菜系免 cuisine cap (「换日料」bug)
    ranked = apply_caps(ranked_raw, profile,
                        intent=intent if not intent.is_empty() else None)
    # T-P2-01: reference 块软重排. user_input 含"昨天/上次/更清淡/换一家"
    # → parse_reference_text → resolve_reference (读 trace_store) → apply_relation
    # 在 top_k 切片前对 ranked 软重排; baseline_l2_snapshot 行为不变 (无 refine 时不触发).
    # 失败/未命中静默降级, 不阻断 refine.
    #
    # Codex M3 修: 优先消费 V2 intent_v2.reference (LLM 已结构化), raw_text parser
    # 作 fallback. 若 LLM 给了 relation 词表没命中的 raw_text → 不再静默忽略
    # (违反 Faithful Refine 的 "执行用户表达" 第一原则).
    resolved_reference: object | None = None
    reference_source: str = "none"  # "v2_intent" / "raw_parser" / "none"
    try:
        from chisha.reference_resolver import (
            parse_reference_text, resolve_reference, apply_relation,
            ReferenceQuery, _extract_days_back, _extract_meal_hint,
        )
        ref_query = None
        # 1) V2 优先: intent_v2.reference 存在且 relation 在 resolver 支持的集合
        v2_ref = intent_v2.reference if intent_v2.reference else None
        v2_rel = (v2_ref or {}).get("relation")
        # V2 relation 集合: lighter / similar_but_different_venue / avoid_pattern
        # resolver/apply 当前消费: lighter / similar_but_different_venue / similar
        if v2_rel in ("lighter", "similar_but_different_venue"):
            db = _extract_days_back(user_input)
            mh = _extract_meal_hint(user_input)
            # 没时间线索 → 走 -2 sentinel (上次), 与 raw parser 行为一致
            if db is None and mh is None:
                db = -2
            ref_query = ReferenceQuery(
                raw_text=user_input,
                relation=v2_rel,
                days_back=db,
                meal_hint=mh,
            )
            reference_source = "v2_intent"
        # 2) Fallback: raw text parser (V2 缺失 / avoid_pattern / unknown relation)
        if ref_query is None:
            ref_query = parse_reference_text(user_input)
            if ref_query is not None:
                reference_source = "raw_parser"
        if ref_query is not None:
            resolved_reference = resolve_reference(
                ref_query, today=today, root=root,
            )
            # 边界: relation=unknown 时 resolved 不为 None 但 apply 是 no-op,
            # 此时不当作"已执行 reference"上报 (避免 trace 误导).
            if resolved_reference is not None:
                if resolved_reference.relation in (
                    "lighter", "similar_but_different_venue", "similar"
                ):
                    ranked = apply_relation(ranked, resolved_reference)
                else:
                    resolved_reference = None
                    reference_source = "none"
    except Exception as _e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "reference resolve/apply failed (non-fatal): %s: %s",
            type(_e).__name__, _e,
        )

    # T-P2-02: 簇式输出 — cuisine_want 非空时按子类重排, 解决 D-073.1 副作用
    # (同 cuisine 免 3 层 cap 后单品牌刷屏). 不影响空 refine 路径 / 非 cuisine refine.
    # 不砍数量, round-robin 让前 N 个 combo 覆盖 ≥ 3 个 subtype.
    subtype_diversified: bool = False
    try:
        if intent.cuisine_want:
            from chisha.subtype_diversity import diversify_by_subtype
            ranked = diversify_by_subtype(ranked)
            subtype_diversified = True
    except Exception as _e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "subtype diversify failed (non-fatal): %s: %s",
            type(_e).__name__, _e,
        )

    # D-046: top60 给 L3
    from chisha.rerank import L3_INPUT_TOP_K
    top_k = ranked[:L3_INPUT_TOP_K]

    # 5. L3 LLM rerank (ctx 携带 refine_input + refine_intent)
    # D-078.2 Codex S2 FIX-NOW: root 必须透传, 否则 refine 二轮 _profile_block
    # 走默认 (project root 兜底), sandbox 启用时读不到沙盒 long_term_prefs.json
    # (或反过来污染 prod), 行为信号在 refine 链路静默缺失.
    # T-P1b-02: 注入 trace_collector dict, 拿 narrative 给前端展示.
    l3_collector: dict = {}
    reranked = rerank(top_k, profile, context=ctx, meal_log=meal_log,
                       n=n, n_explore=0, refine=True, use_llm=use_llm,
                       root=root, trace_collector=l3_collector)

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
    # collector 是 None (async / off / 空 refine) 时 trace 也是 None.
    refine_intent_llm_trace: dict | None = None
    if refine_intent_llm_collector is not None and refine_intent_llm_collector:
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

    # 7. trace 写入 (D-073: 替代 D-071 mood_trace; T-P1a-03 follow-up: 加 intent_v2 双存)
    trace = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "session_id": session_id,
        "round": state.round,
        "user_input": user_input,
        "intent": intent.to_log_dict(),
        # T-P1a-03 follow-up trace 双存: raw_text + 结构化 V2 + raw_understanding 三份
        "intent_v2": intent_v2.to_log_dict(),
        "n_combos_recalled": len(combos),
        "n_after_l2": len(ranked),
        "n_returned": len(reranked),
        "candidate_ids": [c.get("restaurant", {}).get("name", "") + "|" +
                           ",".join(d.get("canonical_name", "")
                                     for d in c.get("dishes", [])[:2])
                          for c in reranked[:5]],
        # T-P2-01: reference resolve 命中时记一条 (debug + 用户语言交互可视化)
        # Codex M3: source 字段标 "v2_intent" / "raw_parser", debug-ui 可见执行来源
        "reference_resolved": (
            {
                "relation": resolved_reference.relation,
                "raw_text": resolved_reference.raw_text,
                "base_session_id": resolved_reference.base_session_id,
                "base_meal_type": resolved_reference.base_meal_type,
                "base_started_at": resolved_reference.base_started_at,
                "n_base_combos": len(resolved_reference.base_combos or []),
                "notes": list(resolved_reference.notes or []),
                "source": reference_source,
            }
            if resolved_reference is not None
            else None
        ),
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
    reference_resolved_field = (
        {
            "relation": resolved_reference.relation,
            "raw_text": resolved_reference.raw_text,
            "base_session_id": resolved_reference.base_session_id,
            "base_meal_type": resolved_reference.base_meal_type,
            "base_started_at": resolved_reference.base_started_at,
            "n_base_combos": len(resolved_reference.base_combos or []),
            "notes": list(resolved_reference.notes or []),
            "source": reference_source,
        }
        if resolved_reference is not None
        else None
    )

    # 8. 返回 §5.7-style (字段对前端兼容)
    return {
        "session_id": session_id,
        "meal_type": state.meal_type,
        "zone": state.zone,
        "round": state.round,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "refine_input": user_input,
        "refine_intent": intent.to_log_dict(),  # D-073: 替代 parsed_feedback
        # T-P1a-03 follow-up: 响应里 + trace 都带 V2, 前端 / debug-ui / L3 可读
        "refine_intent_v2": intent_v2.to_log_dict(),
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

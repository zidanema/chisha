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
from pathlib import Path
from typing import Any

from chisha.context import build_context
from chisha.recall import recall
from chisha.refine_intent import RefineIntent, parse_refine_intent
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

    today = today or dt.date.today()

    # 1. parse_refine_intent: user_input → 结构化意图
    intent: RefineIntent = parse_refine_intent(
        text=user_input,
        use_llm=use_llm,
        profile_llm=profile.get("llm"),
    )

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
    combos = recall(profile, rests, tagged, meal_log, today,
                     meal_type=state.meal_type,
                     intent=intent if not intent.is_empty() else None,
                     n=n)

    # 4. L2 打分 (intent 进 intent_match_bonus 三档)
    ranked = rank_combos(combos, profile, meal_log, today,
                          context=ctx,
                          meal_type=state.meal_type,
                          root=root,
                          intent=intent if not intent.is_empty() else None)
    # D-043: refine 也走三层 cap
    # D-073 followup: 传 intent, cuisine_want 命中的菜系免 cuisine cap (「换日料」bug)
    ranked = apply_caps(ranked, profile,
                        intent=intent if not intent.is_empty() else None)
    # D-046: top60 给 L3
    from chisha.rerank import L3_INPUT_TOP_K
    top_k = ranked[:L3_INPUT_TOP_K]

    # 5. L3 LLM rerank (ctx 携带 refine_input + refine_intent)
    # D-078.2 Codex S2 FIX-NOW: root 必须透传, 否则 refine 二轮 _profile_block
    # 走默认 (project root 兜底), sandbox 启用时读不到沙盒 long_term_prefs.json
    # (或反过来污染 prod), 行为信号在 refine 链路静默缺失.
    reranked = rerank(top_k, profile, context=ctx, meal_log=meal_log,
                       n=n, n_explore=0, refine=True, use_llm=use_llm,
                       root=root)

    # 6. 更新 session
    state.round += 1
    state.last_candidates = [_minimize(c) for c in reranked]
    state.refine_history.append(user_input)
    save_session(state, root)

    # 7. trace 写入 (D-073: 替代 D-071 mood_trace)
    trace = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "session_id": session_id,
        "round": state.round,
        "user_input": user_input,
        "intent": intent.to_log_dict(),
        "n_combos_recalled": len(combos),
        "n_after_l2": len(ranked),
        "n_returned": len(reranked),
        "candidate_ids": [c.get("restaurant", {}).get("name", "") + "|" +
                           ",".join(d.get("canonical_name", "")
                                     for d in c.get("dishes", [])[:2])
                          for c in reranked[:5]],
    }
    _append_intent_trace(trace, root)

    # 8. 返回 §5.7-style (字段对前端兼容)
    return {
        "session_id": session_id,
        "meal_type": state.meal_type,
        "zone": state.zone,
        "round": state.round,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "refine_input": user_input,
        "refine_intent": intent.to_log_dict(),  # D-073: 替代 parsed_feedback
        "stats": {
            "n_dishes_total": len(tagged),
            "n_combos_recalled": len(combos),
            "n_combos_after_score": len(ranked),
            "n_returned": len(reranked),
        },
        "candidates": reranked,
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

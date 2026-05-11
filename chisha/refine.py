"""refine_recommendation API (D-033 V2.1).

接收 session_id + 用户自然语言反馈, 重新推 5 个 (无 explore, D-015):
1. load_session
2. parse_feedback 把自然语言 → chips
3. chips → taste_hints (boost/penalty)
4. user_input 进 ContextSnapshot.refine_input
5. recall + rank_combos(taste_hints, context) + rerank(refine=True)
6. 更新 session.round + last_candidates + refine_history
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from chisha.context import build_context
from chisha.feedback import FeedbackParsed, parse_feedback
from chisha.recall import recall
from chisha.rerank import rerank
from chisha.score import rank_combos
from chisha.session import SessionState, load_session, save_session


# CHIP → taste_hints 映射 (D-035 LLM 反馈解析员产物的精简结构化版)
# boost = 用户想要的; penalty = 用户不想要的
_CHIP_TO_HINT: dict[str, tuple[str, str]] = {
    # boost
    "想喝汤": ("boost", "soup_or_broth"),
    "想清淡": ("boost", "low_oil"),
    # penalty
    "太油": ("penalty", "low_oil"),       # boost 反向 = 用户想 low_oil
    "太甜": ("penalty", "sweet_sauce"),
    "加工肉太多": ("penalty", "processed_meat"),
    "想吃辣": ("boost", "spicy"),
    "想吃肉": ("boost", "protein"),
}


def chips_to_taste_hints(chips: list[str]) -> dict[str, list[str]]:
    """把 chip 列表 → taste_hints (供 score.taste_match_bonus 用).

    NOTE: 这是简化映射. 实际 V2.x 应该让 LLM 反馈解析员产更细的 hint
    (含强度 / 多维 / 否定),  本轮先用枚举 chip 兜底.
    """
    boost: list[str] = []
    penalty: list[str] = []
    for c in chips:
        if c not in _CHIP_TO_HINT:
            continue
        kind, dim = _CHIP_TO_HINT[c]
        target = boost if kind == "boost" else penalty
        if dim not in target:
            target.append(dim)
    # "太油" → penalty low_oil 实际语义是 boost low_oil (用户想 low_oil)
    # 修正: 把 penalty 里 low_oil 移到 boost
    if "low_oil" in penalty:
        penalty.remove("low_oil")
        if "low_oil" not in boost:
            boost.append("low_oil")
    return {"boost": boost, "penalty": penalty}


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
    """refine_recommendation 主入口.

    返回 §5.7-style dict, 含 round / candidates / refine_input / parsed_feedback.

    Args:
        session_id: 上一轮 recommend_meal 的 session_id.
        user_input: 用户自然语言反馈 (如 "今天想喝汤别给我面").
        profile / rests / tagged / meal_log / today: 推荐数据.
        root: 仓库根目录 (用于 session 落盘).
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

    # 1. parse_feedback: user_input → chips + note
    fb: FeedbackParsed = parse_feedback(text=user_input, use_llm=use_llm)

    # 2. chips → taste_hints
    hints = chips_to_taste_hints(fb.chips)

    # 3. 重建 ContextSnapshot, 注入 refine_input
    ctx = build_context(
        profile=profile,
        meal_log=meal_log,
        meal_type=state.meal_type,
        today=today,
        daily_mood=state.daily_mood,
        refine_input=user_input,
    )

    # 4. recall + rank + rerank (refine=True → no explore)
    combos = recall(profile, rests, tagged, meal_log, today)
    ranked = rank_combos(combos, profile, meal_log, today,
                          context=ctx, taste_hints=hints,
                          meal_type=state.meal_type)
    top30 = ranked[:30]
    reranked = rerank(top30, profile, context=ctx, meal_log=meal_log,
                       n=n, n_explore=0, refine=True, use_llm=use_llm)

    # 5. 更新 session
    state.round += 1
    state.last_candidates = [_minimize(c) for c in reranked]
    state.refine_history.append(user_input)
    save_session(state, root)

    # 6. 返回 §5.7-style
    return {
        "session_id": session_id,
        "meal_type": state.meal_type,
        "zone": state.zone,
        "round": state.round,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "refine_input": user_input,
        "parsed_feedback": fb.to_log_dict(),
        "taste_hints": hints,
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

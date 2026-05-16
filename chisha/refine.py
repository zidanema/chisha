"""refine_recommendation API (D-033 V2.1).

接收 session_id + 用户自然语言反馈, 重新推 5 个 (无 explore, D-015):
1. load_session
2. parse_feedback 把自然语言 → chips
3. chips → taste_hints (boost/penalty)
4. user_input 进 ContextSnapshot.refine_input
5. recall + rank_combos(taste_hints, context) + rerank(refine=True)
6. 更新 session.round + last_candidates + refine_history

D-071: refine 入口前做 want_soup 关键词识别 (汤羹偏好补 L2 通道, 见 infer_refine_mood).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from chisha.context import build_context
from chisha.feedback import FeedbackParsed, parse_feedback
from chisha.recall import recall
from chisha.rerank import rerank
from chisha.score import apply_caps, rank_combos
from chisha.session import SessionState, load_session, save_session


# ─────────────────────── D-071: want_soup 关键词识别 ───────────────────────
# 边界 (强制): 此函数只服务 want_soup / wetness 偏好.
# 不得加 want_clean / want_light / want_indulgent / low_carb 等其他 mood 关键词.
# 不得扩展为通用 mood parser. 详见 docs/DECISIONS.md D-071 边界警告.
#
# 已知局限 (docstring 里说明):
#   - 单字 "汤" / "喝" 不收 (会误召奶茶/汤泡饭)
#   - 口语变体 ("喝点热的" / 错别字) 不识别, 退 L3 prompt 兜底
#   - 子串匹配不感知意图, "鸡蛋羹这家店" 这种"提及但非欲望" 仍会误召 — 单测覆盖
#
# Codex Round 1 Q2: 显式 state.daily_mood 优先于推断 (调用方决定),
# trace 用 source=explicit|inferred|none 区分; 见 _build_mood_trace.

_WANT_SOUP_POSITIVE: tuple[str, ...] = (
    "想喝汤", "喝汤", "有汤", "带汤", "汤水", "汤羹",
    "羹", "粥", "砂锅粥", "热汤",
)
_WANT_SOUP_NEGATIVE: tuple[str, ...] = (
    "不想喝汤", "不要汤", "别来汤", "不喝汤", "不想吃粥", "不要粥",
)


def infer_refine_mood(user_input: str | None) -> str | None:
    """关键词扫描 user_input, 命中 want_soup 正向词且未被否定词拦截 → 'want_soup'.

    否定优先: 命中否定词时直接返回 None, 不再检查正向词
    (防 "今天别来汤了, 想吃辣的" 这类否定句被正向"汤"误召).

    边界: 此函数只服务 want_soup, 不得扩展为通用 mood parser.
    新增 mood 维度走 L3 prompt 或 refine 文本透传, 不走关键词.
    """
    if not user_input:
        return None
    for neg in _WANT_SOUP_NEGATIVE:
        if neg in user_input:
            return None
    for pos in _WANT_SOUP_POSITIVE:
        if pos in user_input:
            return "want_soup"
    return None


def _match_positive_keyword(user_input: str | None) -> str | None:
    """返回命中的正向词 (None 表示未命中), 供 trace 埋点用. 不做否定判断."""
    if not user_input:
        return None
    for pos in _WANT_SOUP_POSITIVE:
        if pos in user_input:
            return pos
    return None


def _match_negative_keyword(user_input: str | None) -> str | None:
    """返回命中的否定词 (None 表示未命中), 供 trace 埋点用."""
    if not user_input:
        return None
    for neg in _WANT_SOUP_NEGATIVE:
        if neg in user_input:
            return neg
    return None


# trace schema version (Codex Q4 要求): 升 schema 时改这里 + 老消费方迁移
MOOD_TRACE_SCHEMA_VERSION = 1


def _build_mood_trace(
    session_id: str,
    user_input: str,
    before_daily_mood: str | None,
    inferred_mood: str | None,
    matched_positive: str | None,
    matched_negative: str | None,
    effective_daily_mood: str | None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """构造 D-071 埋点 trace 段. 5 字段 + schema version + source 标识 + 时间戳/session.

    source 字段 (Codex Round 1 Q2):
      - explicit: state.daily_mood 已有值, 推断不参与
      - inferred: state.daily_mood 为 None, 关键词推断生效
      - none: state.daily_mood 为 None 且推断也未命中
    """
    if before_daily_mood:
        source = "explicit"
    elif inferred_mood:
        source = "inferred"
    else:
        source = "none"
    from chisha import clock
    return {
        "schema_version": MOOD_TRACE_SCHEMA_VERSION,
        "timestamp": (now or clock.now_utc()).isoformat(),
        "session_id": session_id,
        "refine_text": user_input,
        "matched_keyword": matched_positive,
        "negated": matched_negative is not None,
        "injected_daily_mood": effective_daily_mood,
        "before_daily_mood": before_daily_mood,
        "source": source,
    }


_MOOD_TRACE_FILENAME = "logs/refine_mood_trace.jsonl"
# 文件超过此大小 (字节) 时旋转为 .1 备份 (Codex Q4 要求轮转策略)
_MOOD_TRACE_ROTATE_BYTES = 5 * 1024 * 1024  # 5 MB


def _append_mood_trace(trace: dict[str, Any], root: Path) -> None:
    """非阻塞写一行 jsonl 到 logs/refine_mood_trace.jsonl. 失败静默.

    Codex Q4 要求: 写失败必须不阻断 refine 主流程; schema 在行内带 version;
    文件超过 _MOOD_TRACE_ROTATE_BYTES 时切到 .1 备份 (只保留一份历史).
    """
    try:
        path = root / _MOOD_TRACE_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        # 简单轮转: 大于阈值时把当前文件挪到 .1 (覆盖旧 .1)
        try:
            if path.exists() and path.stat().st_size >= _MOOD_TRACE_ROTATE_BYTES:
                backup = path.with_suffix(path.suffix + ".1")
                if backup.exists():
                    backup.unlink()
                path.rename(backup)
        except OSError:
            pass
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    except Exception:
        # best-effort: 写失败不阻断 refine 主流程
        pass


# CHIP → taste_hints 映射 (D-035 LLM 反馈解析员产物的精简结构化版)
# boost = 用户想要的; penalty = 用户不想要的
# 维度名与 score.taste_match_bonus 对齐: wetness/low_oil/sweet_sauce/processed_meat/
#                                       carb_heavy/spicy
_CHIP_TO_HINT: dict[str, tuple[str, str]] = {
    # boost (token 必须与 score.taste_match_bonus 支持的对齐)
    "想喝汤": ("boost", "wetness"),
    "想清淡": ("boost", "low_oil"),
    # penalty
    "太油": ("penalty", "low_oil"),       # 见 chips_to_taste_hints 末尾翻转逻辑
    "太甜": ("penalty", "sweet_sauce"),
    "太辣": ("penalty", "spicy"),
    "加工肉太多": ("penalty", "processed_meat"),
    "主食太多": ("penalty", "carb_heavy"),
    # 注: "想吃辣" / "想吃肉" 移除 (Codex review): taste_match_bonus 未实现这两个
    # boost token, 留着是静默无效的死映射. 想加回来需先扩 taste_match_bonus.
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

    from chisha import clock
    today = today or clock.today()

    # 1. parse_feedback: user_input → chips + note
    fb: FeedbackParsed = parse_feedback(
        text=user_input, use_llm=use_llm,
        profile_llm=profile.get("llm"),  # D-047: provider 路由
    )

    # D-073 PR-0.5: 砍掉 refine chip → feedback_history.jsonl 的错位写入.
    # refine chip 是 D-070 L2 当下 session 信号, 不该跨 session 累加成"伪长期偏好".
    # 长期偏好走 L1 LLM 抽取 (chisha/l1_extractor.py + V1.1 反馈) , 见 D-073.
    # 旧 long_term_prefs.append_feedback 函数保留为 deprecated stub 防外部调用挂.

    # 2. chips → taste_hints
    hints = chips_to_taste_hints(fb.chips)

    # D-071: 关键词识别 want_soup, 仅当 state 没显式 daily_mood 时生效.
    # 埋点 5 字段进 trace + jsonl, 用于一周后回看效果.
    inferred_mood = infer_refine_mood(user_input)
    effective_daily_mood = state.daily_mood or inferred_mood
    mood_trace = _build_mood_trace(
        session_id=session_id,
        user_input=user_input,
        before_daily_mood=state.daily_mood,
        inferred_mood=inferred_mood,
        matched_positive=_match_positive_keyword(user_input),
        matched_negative=_match_negative_keyword(user_input),
        effective_daily_mood=effective_daily_mood,
    )
    _append_mood_trace(mood_trace, root)

    # 3. 重建 ContextSnapshot, 注入 refine_input
    ctx = build_context(
        profile=profile,
        meal_log=meal_log,
        meal_type=state.meal_type,
        today=today,
        daily_mood=effective_daily_mood,
        refine_input=user_input,
    )

    # 4. recall + rank + rerank (refine=True → no explore)
    combos = recall(profile, rests, tagged, meal_log, today,
                    meal_type=state.meal_type)
    ranked = rank_combos(combos, profile, meal_log, today,
                          context=ctx, taste_hints=hints,
                          meal_type=state.meal_type,
                          root=root)  # D-043 Codex 二审: 闭合 root 一致性
    # D-043: refine 二轮也走三层 cap (restaurant + cuisine + food_form)
    ranked = apply_caps(ranked, profile)
    # D-046: top30 → topK (与 v2 主路径一致, 二审实测后 K=60)
    from chisha.rerank import L3_INPUT_TOP_K
    top_k = ranked[:L3_INPUT_TOP_K]
    reranked = rerank(top_k, profile, context=ctx, meal_log=meal_log,
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
        "generated_at": clock.now_utc().isoformat(),
        "refine_input": user_input,
        "parsed_feedback": fb.to_log_dict(),
        "taste_hints": hints,
        "mood_inference": mood_trace,  # D-071: want_soup 关键词识别埋点 (与 parsed_feedback 同级)
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

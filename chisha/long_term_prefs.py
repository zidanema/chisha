"""D-043 P3: 反馈闭环最小实现.

数据流:
    user 反馈 → feedback.parse_feedback → FeedbackParsed (chips/rating)
                  ↓
              append_feedback(...) → data/feedback_history.jsonl 累加一条
                  ↓
    next recommend → load_runtime_hints(today) → boost/penalty tags
                  ↓
              merge with profile static hints → taste_match (D-043)

关键设计:
- 反馈不直接改 profile.yaml (那是用户配的); 学习结果落独立文件
- 时间衰减 (半衰期 30 天), 远期反馈衰减为弱信号
- 拉普拉斯平滑 (prior=1): 单次反馈不直接转 hint, 累计 ≥2 次才计
- chip → boost/penalty 映射表是 conservative 的 (只映射明确的食物属性 chip)

文件格式 (data/feedback_history.jsonl) 每行:
    {"ts": "2026-05-13T20:00:00", "meal_type": "dinner",
     "chips": ["太油", "想喝汤"], "rating": 3, "want_again": false,
     "session_id": "...", "combo_signature": "店X | 菜A+菜B"}
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


# chip → boost/penalty token 映射
# 语义关键: 反馈 chip 表达"用户当时的体验/诉求", 映射到下次推荐的 boost/penalty 词表.
# 词表 token 与 score.taste_match_bonus 的语义对齐:
#   - "low_oil" 是 BOOST token: 命中低油 combo → +0.5 (用户希望清淡)
#   - "wetness" 是 BOOST token: 命中汤水 → +0.5
#   - "sweet_sauce" 是 PENALTY token: 命中重甜 → -0.5
#   - "processed_meat" 是 PENALTY token: 命中加工肉 → -0.5
#   - "carb_heavy" 是 PENALTY token: 命中含主食 → -0.5
#   - "spicy" 是 PENALTY token
#
# 因此:
#   用户投诉"太油" → 想要清淡 → BOOST low_oil (不是 penalty!)
#   用户投诉"太甜" → 不想要重甜 → PENALTY sweet_sauce
CHIP_TO_BOOST: dict[str, str] = {
    "想喝汤": "wetness",
    "想清淡": "low_oil",
    "太油": "low_oil",                # 投诉过太油 → 下次推清淡的
    # "想吃肉" / "好吃" / "想再来" 是泛正向或语义不明确, 暂不进 boost
}

CHIP_TO_PENALTY: dict[str, str] = {
    "太甜": "sweet_sauce",
    "加工肉太多": "processed_meat",
    "主食太多": "carb_heavy",
    "太辣": "spicy",
    # "太咸" / "踩雷" / "不想再吃" 语义太泛或没对应 token, 不映射避免误伤
}

# 时间衰减半衰期 (天)
DEFAULT_HALFLIFE_DAYS = 30
# 转 hint 的最小累积出现次数 (拉普拉斯平滑底线)
DEFAULT_MIN_COUNT = 2.0
# 反馈不再考虑的最大历史天数
DEFAULT_MAX_HISTORY_DAYS = 180


def _default_history_path(root: Path | None = None) -> Path:
    root = root or Path(__file__).resolve().parent.parent
    return root / "data" / "feedback_history.jsonl"


def append_feedback(
    chips: list[str],
    rating_taste: int | None = None,
    want_again: bool | None = None,
    meal_type: str | None = None,
    session_id: str | None = None,
    combo_signature: str | None = None,
    timestamp: dt.datetime | None = None,
    root: Path | None = None,
) -> None:
    """追加一条反馈到 history.jsonl. 幂等保护见 session_id+combo_signature 去重 (本期不做)."""
    if not chips and rating_taste is None and want_again is None:
        return  # 空反馈不落盘
    path = _default_history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": (timestamp or dt.datetime.now()).isoformat(),
        "meal_type": meal_type,
        "chips": list(chips or []),
        "rating": rating_taste,
        "want_again": want_again,
        "session_id": session_id,
        "combo_signature": combo_signature,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _decay(days_ago: float, halflife: float) -> float:
    """半衰期衰减: 0 天 = 1.0, halflife 天 = 0.5, 2*halflife 天 = 0.25."""
    if days_ago < 0:
        return 1.0
    return 0.5 ** (days_ago / max(1.0, halflife))


def load_feedback_history(
    root: Path | None = None,
    max_history_days: int = DEFAULT_MAX_HISTORY_DAYS,
    today: dt.date | None = None,
) -> list[dict[str, Any]]:
    """读 history.jsonl, 过滤太旧的反馈."""
    path = _default_history_path(root)
    if not path.exists():
        return []
    today = today or dt.date.today()
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_str = entry.get("ts") or ""
            try:
                entry_ts = dt.datetime.fromisoformat(ts_str).date()
            except (ValueError, TypeError):
                continue
            gap = (today - entry_ts).days
            if gap > max_history_days:
                continue
            entry["_days_ago"] = gap
            out.append(entry)
    return out


def aggregate_chip_weights(
    entries: list[dict[str, Any]],
    halflife: float = DEFAULT_HALFLIFE_DAYS,
) -> dict[str, float]:
    """聚合 chip 出现频次 (带时间衰减 + rating 调权).

    rating=5 → ×1.5, rating=4 → ×1.2, rating=3 → ×1.0,
    rating=2 → ×0.8, rating=1 → ×0.5;
    want_again=True 额外 ×1.15, False ×0.85.
    (Codex review: want_again 系数从 1.3/0.8 降到 1.15/0.85, 避免 rating=5 + want_again=True
    单次反馈 = 1.725 接近 min_count=2.0 阈值就触发, 现在单次最多 1.725 < 2.0.)

    Returns: {chip: weighted_count}
    """
    weights: dict[str, float] = {}
    for entry in entries:
        decay = _decay(entry.get("_days_ago", 0), halflife)
        rating = entry.get("rating")
        rating_mul = {5: 1.5, 4: 1.2, 3: 1.0, 2: 0.8, 1: 0.5}.get(rating, 1.0)
        want_again = entry.get("want_again")
        # Codex review 修复: want_again × rating=5 = 1.95 接近 min_count=2.0 阈值,
        # 单次反馈就可能生效. 降到 1.15 让"至少累积两次"语义更稳.
        want_mul = 1.15 if want_again is True else (0.85 if want_again is False else 1.0)
        chip_weight = decay * rating_mul * want_mul
        for chip in entry.get("chips") or []:
            weights[chip] = weights.get(chip, 0.0) + chip_weight
    return weights


def load_runtime_hints(
    today: dt.date | None = None,
    halflife: float = DEFAULT_HALFLIFE_DAYS,
    min_count: float = DEFAULT_MIN_COUNT,
    max_history_days: int = DEFAULT_MAX_HISTORY_DAYS,
    root: Path | None = None,
) -> dict[str, list[str]] | None:
    """D-043 主入口: 加载反馈历史, 聚合, 转 boost/penalty hints.

    Returns:
        {"boost": [...], "penalty": [...]}  hints 或 None (无累计反馈).
    """
    entries = load_feedback_history(root=root, max_history_days=max_history_days, today=today)
    if not entries:
        return None
    chip_weights = aggregate_chip_weights(entries, halflife=halflife)
    boost: set[str] = set()
    penalty: set[str] = set()
    for chip, weight in chip_weights.items():
        if weight < min_count:
            continue  # 拉普拉斯平滑底线: 不足 N 次累积不进 hint
        if chip in CHIP_TO_BOOST:
            boost.add(CHIP_TO_BOOST[chip])
        if chip in CHIP_TO_PENALTY:
            penalty.add(CHIP_TO_PENALTY[chip])
    if not boost and not penalty:
        return None
    return {"boost": sorted(boost), "penalty": sorted(penalty)}


def merge_hints(
    *hints_list: dict[str, list[str]] | None,
) -> dict[str, list[str]] | None:
    """合并多个 hints (静态 + runtime), 去重, 保留两个 list 的并集.

    顺序: 后传入的优先 (覆盖前者) 仅在冲突时 (此函数实际取并集, 不存在冲突).
    """
    boost: set[str] = set()
    penalty: set[str] = set()
    has_any = False
    for h in hints_list:
        if not h:
            continue
        has_any = True
        boost.update(h.get("boost") or [])
        penalty.update(h.get("penalty") or [])
    if not has_any:
        return None
    return {"boost": sorted(boost), "penalty": sorted(penalty)}

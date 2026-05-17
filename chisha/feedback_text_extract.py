"""B-001 v2: feedback note / comments[] 文本词表抽取 (确定性, 不调 LLM).

设计 (B-001 v2 codex 共识):
- 复用 l1_prefs.BOOST_TOKENS (4) + PENALTY_TOKENS (4), 不扩词表 (D-076.1 边界)
- 否定前缀严格丢弃 (不做语义反转, 防 penalty-only token 无对称语义)
- 同 raw_text 多 token 命中 → 全保留, 调用方自定权重

公开 API:
    extract_tokens(text: str) -> dict
        返回 {"boost": set[str], "penalty": set[str], "raw_matches": list[tuple]}
"""
from __future__ import annotations

import re

from chisha.l1_prefs import BOOST_TOKENS, PENALTY_TOKENS

# Codex S5 Q4.1 修订: 按 *意图* 拆 BOOST / PENALTY, 防 overlap token (spicy /
# sweet_sauce 既属 BOOST_TOKENS 也属 PENALTY_TOKENS) 同时进两边互相抵消.
#
# 语义模型:
#   "太油" / "油腻" → 用户嫌油, 想要 low_oil → BOOST low_oil
#   "想吃辣" → 用户想吃辣 → BOOST spicy
#   "太辣" → 用户嫌辣 → PENALTY spicy
#   "太甜" → 用户嫌甜 → PENALTY sweet_sauce
#   "加工肉/火腿/培根" → 用户避加工肉 → PENALTY processed_meat
#
# BOOST patterns: 触发词命中 → 用户希望该属性 "更多"
_BOOST_PATTERNS: dict[str, list[str]] = {
    "low_oil":     ["太油", "油腻", "很油", "油大", "oily"],
    "wetness":     ["太干", "想喝汤", "要汤", "喝汤"],
    "spicy":       ["想吃辣", "够辣", "辣味"],
    "sweet_sauce": [],   # 罕见, 没人说想要更甜
}
# PENALTY patterns: 触发词命中 → 用户希望该属性 "更少"
_PENALTY_PATTERNS: dict[str, list[str]] = {
    "sweet_sauce":    ["太甜", "齁甜", "sweet"],
    "spicy":          ["太辣"],
    "processed_meat": ["加工肉", "火腿", "培根", "香肠", "罐头肉"],
    "carb_heavy":     ["主食多", "碳水多", "米饭多", "面太多"],
}

# 否定前缀 — 命中后整条 token 丢弃, 不算正/负信号
_NEGATION_PREFIXES = ["不", "没那么", "不太", "不算"]


def _has_negation_prefix(text: str, kw_start: int) -> bool:
    """检查 kw_start 之前 4 字符内是否有否定前缀."""
    if kw_start == 0:
        return False
    window = text[max(0, kw_start - 4):kw_start]
    return any(neg in window for neg in _NEGATION_PREFIXES)


def extract_tokens(text: str | None) -> dict:
    """从单条 text (note / comment) 抽 L1 词表 token.

    返回:
      {
        "boost":   set[str],       # ⊆ BOOST_TOKENS
        "penalty": set[str],       # ⊆ PENALTY_TOKENS
        "raw_matches": list[tuple] # [(token, kw, kind)] debug 用
      }

    设计:
    - 同 token 触发词多个命中 → 只算一次
    - 否定前缀 ("不油" / "不太辣") → 该 token 此次命中丢弃 (Codex Q3)
    - 同 token 既属 BOOST 又属 PENALTY (如 spicy / sweet_sauce 重叠) → boost/penalty 都加,
      调用方按上下文 (calibration 等) 决定哪个生效. 此处不强行二选一.
    """
    boost: set[str] = set()
    penalty: set[str] = set()
    raw: list[tuple] = []
    if not text or not isinstance(text, str):
        return {"boost": boost, "penalty": penalty, "raw_matches": raw}

    # BOOST 意图扫描
    for token, kws in _BOOST_PATTERNS.items():
        if token not in BOOST_TOKENS:
            continue
        for kw in kws:
            for m in re.finditer(re.escape(kw), text):
                if _has_negation_prefix(text, m.start()):
                    continue
                boost.add(token)
                raw.append((token, kw, m.start(), "boost"))
                break  # 同 kw 多次命中只算一次

    # PENALTY 意图扫描
    for token, kws in _PENALTY_PATTERNS.items():
        if token not in PENALTY_TOKENS:
            continue
        for kw in kws:
            for m in re.finditer(re.escape(kw), text):
                if _has_negation_prefix(text, m.start()):
                    continue
                penalty.add(token)
                raw.append((token, kw, m.start(), "penalty"))
                break

    return {"boost": boost, "penalty": penalty, "raw_matches": raw}

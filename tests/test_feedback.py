"""feedback.py 单测.

仅覆盖 fallback (rule_parse) 路径 + 入口合并逻辑.
LLM 路径需要真 ANTHROPIC_API_KEY, 在 e2e 测试里覆盖.
"""
from __future__ import annotations

import pytest

from chisha.feedback import (
    CHIP_VOCAB,
    FeedbackParsed,
    parse_feedback,
    rule_parse,
)


# ---------------------------------------------------------------- rule_parse
def test_rule_parse_oil():
    r = rule_parse("今天的菜油大了点")
    assert "太油" in r["chips"]


def test_rule_parse_multiple_chips():
    r = rule_parse("送得太慢, 漏了一些汤, 主食太多")
    assert "送慢" in r["chips"]
    assert "漏汤" in r["chips"]
    assert "主食太多" in r["chips"]


def test_rule_parse_rating():
    r = rule_parse("4分, 不错")
    assert r["rating_taste"] == 4


def test_rule_parse_rating_star():
    r = rule_parse("好吃 ⭐⭐⭐⭐⭐")  # 没数字, 不应推
    assert r["rating_taste"] is None


def test_rule_parse_rating_explicit_5():
    r = rule_parse("5星好评")
    assert r["rating_taste"] == 5


def test_rule_parse_want_again_positive():
    r = rule_parse("好吃, 想再来")
    assert r["want_again"] is True
    assert "想再来" in r["chips"]


def test_rule_parse_want_again_negative_priority():
    r = rule_parse("味道还行但是再也不点了")
    assert r["want_again"] is False    # 否定优先


def test_rule_parse_empty():
    r = rule_parse("")
    assert r["chips"] == []
    assert r["rating_taste"] is None
    assert r["want_again"] is None


def test_rule_parse_neutral():
    r = rule_parse("吃完了")
    assert r["chips"] == []
    assert r["want_again"] is None


# ---------------------------------------------------------------- parse_feedback
def test_parse_feedback_ui_only():
    """只有 UI chip, 无文本."""
    fb = parse_feedback(text="", chips=["太油", "想喝汤"])
    assert fb.chips == ["太油", "想喝汤"]
    assert fb.rating_taste is None
    assert fb.want_again is None
    assert fb.note == ""


def test_parse_feedback_text_only_no_llm():
    """文本但无 LLM key, 走 rule fallback."""
    fb = parse_feedback(text="太油了, 没吃饱", chips=None, use_llm=False)
    assert "太油" in fb.chips
    assert "没吃饱" in fb.chips
    assert fb.note == "太油了, 没吃饱"


def test_parse_feedback_merges_ui_and_text():
    """UI chip + 文本推断, 合并去重."""
    fb = parse_feedback(text="送慢, 太油了", chips=["太油", "想清淡"], use_llm=False)
    # 去重 + UI 优先 (顺序: ui_chips 在前)
    assert fb.chips == ["太油", "想清淡", "送慢"]


def test_parse_feedback_invalid_chip_dropped():
    """UI 上传的非 vocab chip 应被丢弃."""
    fb = parse_feedback(text="", chips=["太油", "随便编个", "想喝汤"])
    assert fb.chips == ["太油", "想喝汤"]


def test_parse_feedback_rating_ui_priority():
    """UI rating 应覆盖文本推断."""
    fb = parse_feedback(text="3分", rating_taste=5, use_llm=False)
    assert fb.rating_taste == 5


def test_parse_feedback_rating_text_fallback():
    """UI 未填 rating 时, 用文本推断."""
    fb = parse_feedback(text="3分", rating_taste=None, use_llm=False)
    assert fb.rating_taste == 3


def test_parse_feedback_rating_clamp():
    """UI 给越界 rating 应 None 化."""
    fb = parse_feedback(text="", rating_taste=10)
    assert fb.rating_taste is None


def test_parse_feedback_want_again_ui_priority():
    fb = parse_feedback(text="再也不点了", want_again=True, use_llm=False)
    assert fb.want_again is True   # UI 优先


def test_parse_feedback_want_again_text_fallback():
    fb = parse_feedback(text="想再来", want_again=None, use_llm=False)
    assert fb.want_again is True


def test_parse_feedback_to_log_dict_serializable():
    fb = parse_feedback(text="太油, 不想再吃", chips=["想喝汤"],
                        rating_taste=2, want_again=False, use_llm=False)
    import json
    d = fb.to_log_dict()
    s = json.dumps(d, ensure_ascii=False)
    assert "太油" in s
    assert "想喝汤" in s
    assert d["rating_taste"] == 2
    assert d["want_again"] is False


def test_chip_vocab_has_required_categories():
    """CHIP_VOCAB 必须含核心负向 / 履约 / 诉求 / 正向四类."""
    # 负向口味
    assert "太油" in CHIP_VOCAB
    assert "太辣" in CHIP_VOCAB
    # 履约
    assert "送慢" in CHIP_VOCAB
    assert "漏汤" in CHIP_VOCAB
    # 诉求
    assert "想喝汤" in CHIP_VOCAB
    assert "想清淡" in CHIP_VOCAB
    # 正向
    assert "想再来" in CHIP_VOCAB
    assert "好吃" in CHIP_VOCAB


def test_empty_input_returns_empty_parsed():
    fb = parse_feedback()
    assert isinstance(fb, FeedbackParsed)
    assert fb.chips == []
    assert fb.rating_taste is None
    assert fb.want_again is None
    assert fb.note == ""

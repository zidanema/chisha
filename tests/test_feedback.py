"""feedback.py 单测.

仅覆盖 CHIP_VOCAB 受控词表 (parse_feedback / rule_parse 链路已退役).
"""
from __future__ import annotations

from chisha.feedback import CHIP_VOCAB


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

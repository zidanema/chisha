"""反馈 chip 受控词表 (D-033 反馈骨架).

仅保留 CHIP_VOCAB — 飞书卡片 / openclaw 集成 (integrations/openclaw/feishu_card.py)
live 消费的反馈 chip 受控词表. 原 parse_feedback / rule_parse / FeedbackParsed
LLM+规则反馈解析链路已退役 (test-only 死代码清理).
"""
from __future__ import annotations


# 反馈 chip 受控词表 (与飞书卡片 chip 列表对齐).
# 任何 LLM/规则解析后的 chip 都必须 ∈ CHIP_VOCAB, 否则丢弃.
CHIP_VOCAB: set[str] = {
    # 即时反馈 — 负向
    "太油", "太辣", "太咸", "太甜", "太贵", "太撑", "没吃饱",
    "主食太多", "加工肉太多",
    # 即时反馈 — 履约
    "送慢", "拒签", "漏汤",
    # 即时反馈 — 偏好诉求
    "想喝汤", "想清淡", "想吃辣", "想吃肉", "不想吃这菜系",
    # 餐后反馈 — 正向
    "好吃", "想再来", "推荐别人",
    # 餐后反馈 — 负向
    "不想再吃", "踩雷",
}

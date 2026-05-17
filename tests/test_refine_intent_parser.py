"""D-073: parse_refine_intent 单元测试.

覆盖 Codex review §8 要求的 edge case:
  - 随便 / 都行 / 你看着来
  - 否定 ("别太辣" "不要主食" "不要香菜")
  - 多目标 ("想吃日料或粤菜")
  - 冲突 ("想吃辣但别太辣")
  - 程度 ("肉多一点" "少点饭")
  - cuisine alias ("湖南菜"/"湘菜")
  - LLM unavailable fallback (use_llm=False 走 rule_parse)
"""
from __future__ import annotations

import pytest

from chisha.refine_intent import (
    FLAVOR_TAGS, PORTION_TAGS, STAPLE_TAGS, PRICE_BANDS,
    RefineIntent,
    normalize_flavor_tag, normalize_portion_tag,
    rule_parse, parse_refine_intent,
)


# ─────────────────────────── 归一 helpers ───────────────────────────


@pytest.mark.parametrize("inp,expected", [
    ("辣", "spicy"),
    ("微辣", "spicy"),
    ("麻辣", "spicy"),
    ("汤", "soup"),
    ("带汤", "soup"),
    ("清淡", "light"),
    ("不油腻", "light"),
    ("重口", "heavy"),
    ("酸爽", "sour"),
    ("spicy", "spicy"),     # 已是归一值
    ("不存在的词", None),
    ("", None),
    (None, None),
])
def test_normalize_flavor_tag(inp, expected):
    assert normalize_flavor_tag(inp) == expected


@pytest.mark.parametrize("inp,expected", [
    ("肉多", "more_meat"),
    ("肉多一点", "more_meat"),
    ("少饭", "less_carb"),
    ("少主食", "less_carb"),
    ("蔬菜多", "more_veg"),
    ("少一点", "not_too_full"),
    ("more_meat", "more_meat"),
    ("不存在", None),
])
def test_normalize_portion_tag(inp, expected):
    assert normalize_portion_tag(inp) == expected


# ─────────────────────────── rule_parse (LLM unavailable fallback) ──────


def test_rule_parse_empty():
    """空文本 → 全空."""
    p = rule_parse("")
    assert p["cuisine_want"] == []
    assert p["ingredient_want"] == []
    assert p["flavor_tags"] == []
    assert p["portion"] == []
    assert p["staple_preference"] is None
    assert p["price_band"] is None


def test_rule_parse_hunan_meat():
    """主 case: 想吃点湖南菜，然后肉多一点."""
    p = rule_parse("想吃点湖南菜，然后肉多一点。")
    assert "湖南菜" in p["cuisine_want"]
    assert "肉" in p["ingredient_want"]
    assert "more_meat" in p["portion"]


def test_rule_parse_cuisine_alias():
    """湘菜 / 湖南菜 → 都归一到 湖南菜."""
    assert "湖南菜" in rule_parse("想吃湘菜")["cuisine_want"]
    assert "湖南菜" in rule_parse("湖南料理也行")["cuisine_want"]


def test_rule_parse_cuisine_avoid():
    """否定: 不要日料 → cuisine_avoid."""
    p = rule_parse("今天想来点辣的，不要日料")
    assert "日料" in p["cuisine_avoid"]
    assert "spicy" in p["flavor_tags"]


def test_rule_parse_multi_cuisine():
    """多目标: 想吃日料或粤菜."""
    p = rule_parse("想吃日料或粤菜")
    assert "日料" in p["cuisine_want"]
    assert "粤菜" in p["cuisine_want"]


def test_rule_parse_flavor_negation():
    """否定: 别太辣 → 不进 flavor_tags."""
    p = rule_parse("别太辣别太油")
    assert "spicy" not in p["flavor_tags"]
    # "别太油" 也不该误入 light
    # (规则解析对"别"前缀做了 window check)


def test_rule_parse_ingredient_avoid():
    """不要香菜 → ingredient_avoid."""
    p = rule_parse("酸辣口的, 不要香菜")
    assert "香菜" in p["ingredient_avoid"]
    assert "sour" in p["flavor_tags"]
    assert "spicy" in p["flavor_tags"]


def test_rule_parse_staple():
    """主食偏好."""
    assert rule_parse("不要饭")["staple_preference"] == "avoid_staple"
    assert rule_parse("想吃面")["staple_preference"] == "want_noodle"


def test_rule_parse_price_band():
    """价格区间."""
    assert rule_parse("便宜点的, 30 块以内")["price_band"] == "cheap"
    assert rule_parse("想吃日料，别太贵")["price_band"] == "cheap"


def test_rule_parse_random_no_intent():
    """随便 / 你看着来 → 几乎全空."""
    p = rule_parse("随便, 你看着来")
    assert p["cuisine_want"] == []
    assert p["ingredient_want"] == []
    assert p["flavor_tags"] == []
    assert p["portion"] == []


def test_rule_parse_soup_light():
    """想喝汤, 清淡的 → soup + light."""
    p = rule_parse("想喝汤, 清淡的")
    assert "soup" in p["flavor_tags"]
    assert "light" in p["flavor_tags"]


def test_rule_parse_meat_count():
    """牛肉面 → ingredient + staple."""
    p = rule_parse("想吃牛肉面")
    assert "牛肉" in p["ingredient_want"]
    assert p["staple_preference"] == "want_noodle"


def test_rule_parse_dont_associate():
    """晚上要踢球 → 仅字面 light, 不联想 portion=not_too_full."""
    p = rule_parse("晚上要踢球, 别太重口")
    # "别太重口" 中 "重口" 在 "别" window 内 → 不该进 heavy
    assert "heavy" not in p["flavor_tags"]
    # 但应识别 "别太重口" 的语义? 规则做不到, 让 LLM 处理
    # 兜底: portion 不该被联想出 not_too_full
    assert "not_too_full" not in p["portion"]


# ─────────────────────────── parse_refine_intent (高层 API) ─────────────


def test_parse_refine_intent_empty():
    """空文本 → RefineIntent 全空, is_empty()==True."""
    r = parse_refine_intent("")
    assert isinstance(r, RefineIntent)
    assert r.is_empty()
    assert r.raw_text == ""


def test_parse_refine_intent_no_llm_fallback():
    """use_llm=False → 走 rule_parse, 主 case 仍能解析."""
    r = parse_refine_intent("想吃点湖南菜，然后肉多一点。", use_llm=False)
    assert "湖南菜" in r.cuisine_want
    assert "肉" in r.ingredient_want
    assert "more_meat" in r.portion
    assert r.raw_text == "想吃点湖南菜，然后肉多一点。"
    assert not r.is_empty()


def test_parse_refine_intent_schema_clean():
    """rule_parse 输出经过清洗: 枚举校验 + 去重 + strip."""
    r = parse_refine_intent("酸辣口的, 不要香菜", use_llm=False)
    # flavor_tags 全部 ∈ FLAVOR_TAGS
    assert all(t in FLAVOR_TAGS for t in r.flavor_tags)
    # 去重
    assert len(r.flavor_tags) == len(set(r.flavor_tags))
    # ingredient_avoid 含 香菜
    assert "香菜" in r.ingredient_avoid


def test_parse_refine_intent_enum_clamp():
    """staple_preference / price_band 严格枚举校验."""
    r = parse_refine_intent("不要饭", use_llm=False)
    assert r.staple_preference in STAPLE_TAGS

    r = parse_refine_intent("便宜点的", use_llm=False)
    assert r.price_band in PRICE_BANDS


def test_parse_refine_intent_raw_text_preserved():
    """raw_text 原样保留, freeform_note 默认等于原文."""
    text = "今天累了来点暖的"
    r = parse_refine_intent(text, use_llm=False)
    assert r.raw_text == text
    assert r.freeform_note == text


def test_parse_refine_intent_unknown_word_dropped():
    """LLM 万一抛出 schema 外枚举值, 经清洗丢弃 (rule_parse 不会, 但走数据路径仍要兜)."""
    # 直接模拟 _llm_parse 返回值不规范的场景
    from chisha import refine_intent as ri

    def fake_llm(text, profile_llm=None):
        return {
            "cuisine_want": ["湖南菜"],
            "flavor_tags": ["spicy", "very_hot", "麻"],   # very_hot/麻 不在 FLAVOR_TAGS
            "staple_preference": "want_baozi",              # 非法枚举
            "price_band": "cheap",
            "freeform_note": text,
        }

    orig = ri._llm_parse
    ri._llm_parse = fake_llm
    try:
        r = parse_refine_intent("假数据", use_llm=True)
        # spicy 保留, very_hot 丢弃, 麻 经归一变 spicy (但 spicy 已存在 → 去重)
        assert r.flavor_tags == ["spicy"]
        # 非法枚举 → None
        assert r.staple_preference is None
        # 合法枚举 → 保留
        assert r.price_band == "cheap"
    finally:
        ri._llm_parse = orig


def test_parse_refine_intent_conflict_returns_raw():
    """冲突表达: 想吃辣但别太辣 → rule_parse 把 spicy 进 flavor_tags
    (因为'辣'在'想吃辣'中无否定前缀; 但 '别太辣' 中 '辣' 前 4 字符是'别太'→ 否定),
    实际 rule_parse 现状是 'spicy' 命中一次后第二次 '辣' 被否定窗口拦截.
    所以 spicy 会被一次性收录. 这个测试是 documenting 当前 rule_parse 行为,
    LLM 应该按 prompt §冲突优先精确 处理得更好.
    """
    p = rule_parse("想吃辣但别太辣")
    # 规则解析至少抓到一次"辣" → spicy 入列 (但 LLM prompt 要求冲突时留空)
    # 此处仅断言不会崩 + raw_flavor 携带原词
    assert isinstance(p["flavor_tags"], list)
    assert "辣" in p["raw_flavor"] or len(p["raw_flavor"]) > 0


# ────────────────────────── T-00: schema_version 字段


def test_refine_intent_has_default_schema_version():
    """RefineIntent 加 schema_version 默认 '1.0', 旧调用方零侵入."""
    from chisha.refine_intent import RefineIntent, parse_refine_intent
    # 默认构造
    intent = RefineIntent()
    assert intent.schema_version == "1.0"
    # parse_refine_intent 路径 (text="" 走早返分支)
    empty = parse_refine_intent("")
    assert empty.schema_version == "1.0"
    # parse_refine_intent 路径 (rule_parse 走 to_log_dict 都该有)
    parsed = parse_refine_intent("想吃湘菜", use_llm=False)
    assert parsed.schema_version == "1.0"


def test_empty_refine_intent_still_empty_with_schema_version():
    """Codex audit 提示: 加 schema_version 不能让 is_empty() 假阴性.

    is_empty() 只检查语义维度, 不检查 schema_version (元信息).
    refine.py 用 is_empty() 判断是否注入 ctx, 如果误判会让空 refine 走非空分支.
    """
    from chisha.refine_intent import RefineIntent, parse_refine_intent
    assert RefineIntent().is_empty() is True
    assert parse_refine_intent("").is_empty() is True
    # 显式构造 schema_version 不同也不应改变 is_empty
    assert RefineIntent(schema_version="2.0").is_empty() is True


def test_refine_intent_schema_version_in_to_log_dict():
    """to_log_dict() (走 asdict) 应包含 schema_version → trace 看得见."""
    from chisha.refine_intent import RefineIntent
    d = RefineIntent().to_log_dict()
    assert "schema_version" in d
    assert d["schema_version"] == "1.0"

"""feishu_card.py 单测 (V2 增强)."""
from __future__ import annotations

import json

import pytest

from chisha.feedback import CHIP_VOCAB
from integrations.openclaw.feishu_card import (
    _REJECT_CHIPS_DEFAULT,
    _validated_reject_chips,
    render_card,
)


@pytest.fixture
def fake_out():
    return {
        "session_id": "20260513_lunch_a3f7",
        "meal_type": "lunch",
        "round": 1,
        "stats": {"n_combos_recalled": 132},
        "candidates": [
            {
                "rank": 1,
                "is_explore": False,
                "summary": "潮汕牛肉粿条",
                "restaurant": {"id": "r_007", "name": "潮汕牛肉",
                               "distance_m": 600, "eta_min": 30},
                "dishes": [
                    {"dish_id": "d1", "canonical_name": "潮汕牛肉粿条",
                     "price": 32},
                    {"dish_id": "d2", "canonical_name": "蒜蓉空心菜",
                     "price": 16},
                ],
                "total_price": 48,
                "estimated_total_oil": 2.0,
                "estimated_total_protein_g": 35,
                "reason_one_line": "高蛋白低油, 命中你今天想喝汤",
            },
            {
                "rank": 2,
                "is_explore": True,
                "summary": "胡椒猪肚鸡套餐",
                "restaurant": {"id": "r_009", "name": "猪肚鸡店",
                               "distance_m": 1200, "eta_min": 40},
                "dishes": [{"dish_id": "d3", "canonical_name": "胡椒猪肚鸡",
                            "price": 58}],
                "total_price": 58,
                "estimated_total_oil": 2.5,
                "estimated_total_protein_g": 42,
                "reason_one_line": "你没吃过的探索, 汤水清爽",
            },
        ],
    }


# ─────────────────────── 基础渲染
def test_render_returns_dict(fake_out):
    card = render_card(fake_out)
    assert isinstance(card, dict)
    assert "elements" in card
    assert "header" in card


def test_card_serializable(fake_out):
    card = render_card(fake_out)
    s = json.dumps(card, ensure_ascii=False)
    assert "潮汕牛肉" in s
    assert "20260513_lunch_a3f7" in s


def test_empty_candidates_warning(fake_out):
    fake_out["candidates"] = []
    card = render_card(fake_out)
    s = json.dumps(card, ensure_ascii=False)
    assert "没召回到" in s


# ─────────────────────── chip 校验
def test_reject_chips_subset_of_vocab():
    """所有 reject chip 必须 ∈ CHIP_VOCAB."""
    for chip in _REJECT_CHIPS_DEFAULT:
        assert chip in CHIP_VOCAB, f"reject chip {chip!r} 不在 CHIP_VOCAB"


def test_validated_chips_filters_invalid():
    chips = _validated_reject_chips()
    assert all(c in CHIP_VOCAB for c in chips)
    assert len(chips) > 0


def test_card_includes_reject_overflow(fake_out):
    """每个 candidate 必须包含 reject overflow."""
    card = render_card(fake_out)
    s = json.dumps(card, ensure_ascii=False)
    # 至少有一个 reject chip 出现
    assert "太油" in s
    assert "想喝汤" in s
    # overflow tag 出现
    assert '"overflow"' in s
    # action: reject 出现
    assert "reject" in s


# ─────────────────────── refine 区
def test_card_includes_refine(fake_out):
    card = render_card(fake_out)
    s = json.dumps(card, ensure_ascii=False)
    assert "重新推荐" in s
    assert "换 5 个" in s
    assert "refine" in s
    assert "refine_text" in s   # form input name


def test_refine_form_session_id_passthrough(fake_out):
    card = render_card(fake_out)
    s = json.dumps(card, ensure_ascii=False)
    # session_id 应被透到 refine button value
    assert "20260513_lunch_a3f7" in s


# ─────────────────────── post-meal 追问
def test_card_no_post_meal_when_last_meal_none(fake_out):
    card = render_card(fake_out, last_meal=None)
    s = json.dumps(card, ensure_ascii=False)
    assert "上顿" not in s


def test_card_includes_post_meal_when_last_meal_provided(fake_out):
    last = {"date": "2026-05-12", "meal_type": "dinner", "cuisine": "川菜"}
    card = render_card(fake_out, last_meal=last)
    s = json.dumps(card, ensure_ascii=False)
    assert "上顿" in s
    assert "2026-05-12" in s
    assert "川菜" in s
    assert "post_meal_feedback" in s


# ─────────────────────── explore 标记
def test_explore_candidate_tagged(fake_out):
    card = render_card(fake_out)
    s = json.dumps(card, ensure_ascii=False)
    # rank 2 是 explore
    assert "🌱探索" in s


def test_select_button_value_complete(fake_out):
    """选这个按钮 value 必须含 session_id / rank / restaurant_name / summary."""
    card = render_card(fake_out)
    s = json.dumps(card, ensure_ascii=False)
    assert '"action":"select"' in s.replace(" ", "")
    assert "潮汕牛肉粿条" in s

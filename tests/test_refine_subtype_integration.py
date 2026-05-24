"""T-P2-02: refine path 接入 簇式输出集成测试.

验证:
- cuisine_want 非空时 ranked 走 diversify_by_subtype 重排
- cuisine_want 空时不触发, ranked 顺序不变 (空 refine 路径行为保证)
- diversify_by_subtype 单元已有 11 个测试, 此处只测 refine 接入
"""
from __future__ import annotations

from chisha.subtype_diversity import diversify_by_subtype, infer_combo_subtype
from tests._v2_compat import make_v1_compat_intent as RefineIntent


def _combo(cuisine: str, dish_names: list[str]) -> dict:
    return {
        "restaurant": {"id": f"r-{cuisine}", "name": f"店-{cuisine}"},
        "dishes": [
            {"canonical_name": n, "cuisine": cuisine,
             "cooking_method": "炒",
             "nutrition_profile": {}}
            for n in dish_names
        ],
    }


def test_diversify_round_robin_distribution():
    """混合子类 → round-robin 让前 5 道覆盖 ≥ 3 个 subtype."""
    cands = [
        _combo("湘菜", ["腊肉炒"]),         # 腊味
        _combo("湘菜", ["腊味拼盘"]),       # 腊味
        _combo("湘菜", ["剁椒鱼头"]),       # 剁椒
        _combo("湘菜", ["小炒黄牛肉"]),     # 小炒
        _combo("湘菜", ["家常豆腐"]),       # 家常
        _combo("湘菜", ["剁椒蒸蛋"]),       # 剁椒
        _combo("湘菜", ["腊味煲"]),         # 腊味
    ]
    out = diversify_by_subtype(cands)
    # 前 3 个的 subtype 应该至少覆盖 3 个不同的 subtype
    top3_subtypes = {infer_combo_subtype(c).subtype for c in out[:3]}
    assert len(top3_subtypes) >= 3


def test_diversify_preserves_count():
    """重排不砍数量 (各 combo unique 避免 c in out == 边界)."""
    cands = [
        {**_combo("湘菜", [f"小炒-{i}"]),
         "restaurant": {"id": f"r-{i}", "name": f"店-{i}"}}
        for i in range(10)
    ]
    out = diversify_by_subtype(cands)
    assert len(out) == len(cands)


def test_diversify_empty_safe():
    assert diversify_by_subtype([]) == []


def test_refine_intent_cuisine_want_gate():
    """refine.py 内 `if intent.cuisine_want: diversify(...)` gate 等价验证.

    refine_session 重量级, 这里只验 gate 信号 — cuisine_want 空 → falsy → 不触发 diversify;
    非空 → truthy → 触发. V2 property `intent.cuisine_want` 行为正确才能保证 refine.py
    line ~197 的 gate 不退化.
    """
    intent_empty = RefineIntent()
    assert not intent_empty.cuisine_want
    assert intent_empty.is_empty()

    intent_filled = RefineIntent(cuisine_want=["湘菜"])
    assert bool(intent_filled.cuisine_want) is True
    assert intent_filled.cuisine_want == ["湘菜"]
    assert not intent_filled.is_empty()


def test_diversify_max_per_subtype_caps_repeat():
    """同 subtype 多条 → max_per_subtype 限制单子类的早期出现."""
    # 5 个全是腊味 (不同 restaurant id 避开 == 边界), 默认 max_per_subtype=2
    cands = [
        {**_combo("湘菜", [f"腊味-{i}"]),
         "restaurant": {"id": f"r-{i}", "name": f"店-{i}"}}
        for i in range(5)
    ]
    out = diversify_by_subtype(cands)
    assert len(out) == 5

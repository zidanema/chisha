"""T-P2-02: 簇式输出 (intent 内部子类多样化) 单测."""
from __future__ import annotations

from chisha.subtype_diversity import (
    SubtypeAssignment,
    diversify_by_subtype,
    infer_combo_subtype,
)


def _combo(rid, dish_name, *, cuisine="湘菜", cooking_method="炒",
           main_ingredient_type="红肉"):
    return {
        "restaurant": {"id": rid, "name": "店", "brand": "br"},
        "dishes": [{
            "dish_id": f"d_{rid}",
            "canonical_name": dish_name,
            "raw_name": dish_name,
            "cuisine": cuisine,
            "nutrition_profile": {
                "cooking_method": cooking_method,
                "main_ingredient_type": main_ingredient_type,
                "oil_level": 3,
            },
        }],
    }


# ────────────────────────── infer_combo_subtype


def test_infer_subtype_xiangcai_lawei():
    sa = infer_combo_subtype(_combo("r1", "腊味合蒸"))
    assert sa.cuisine == "湘菜"
    assert sa.subtype == "腊味"


def test_infer_subtype_xiangcai_jiandai_chao():
    sa = infer_combo_subtype(_combo("r2", "辣椒炒肉"))
    assert sa.subtype in ("剁椒", "小炒"), \
        f"剁椒 or 小炒, got {sa.subtype}"


def test_infer_subtype_riliao_lamian():
    sa = infer_combo_subtype(_combo("r3", "日式拉面", cuisine="日式"))
    assert sa.cuisine == "日式"
    assert sa.subtype == "拉面"


def test_infer_subtype_riliao_shoushi():
    sa = infer_combo_subtype(_combo("r4", "三文鱼寿司", cuisine="日式"))
    assert sa.subtype == "寿司"


def test_infer_subtype_unknown_cuisine_returns_other():
    sa = infer_combo_subtype(_combo("r5", "随便", cuisine="自创"))
    assert sa.cuisine == "自创"
    assert sa.subtype == "其他"


def test_infer_subtype_empty_combo_safe():
    sa = infer_combo_subtype({"dishes": []})
    assert sa.cuisine == "未知"
    assert sa.subtype == "其他"


# ────────────────────────── diversify_by_subtype


def test_diversify_round_robin_picks_one_per_subtype_first():
    """5 道湘菜 (3 腊味, 2 小炒) → 前两道至少跨 2 subtype."""
    cs = [
        _combo("r_la_1", "腊味合蒸"),
        _combo("r_la_2", "腊肉炒蒜苗"),
        _combo("r_la_3", "腊肠"),
        _combo("r_chao_1", "辣椒炒肉"),
        _combo("r_chao_2", "辣椒炒"),  # 命中 "辣椒" → 剁椒 OR 小炒
    ]
    out = diversify_by_subtype(cs, target_subtypes=3, max_per_subtype=2)
    sas = [infer_combo_subtype(c).subtype for c in out]
    # 前两道 subtype 不同 (round-robin 拿 head)
    assert sas[0] != sas[1]


def test_diversify_caps_max_per_subtype():
    """7 道全腊味 + max_per_subtype=2 → 前 2 道腊味, 余下溢出."""
    cs = [_combo(f"r{i}", f"腊味{i}") for i in range(7)]
    out = diversify_by_subtype(cs, target_subtypes=3, max_per_subtype=2)
    # 应保留全部 7 道 (不砍数量)
    assert len(out) == 7
    # 前 2 应取 round-robin head, 后 5 溢出 (按原顺序)
    head_2 = out[:2]
    assert all(infer_combo_subtype(c).subtype == "腊味" for c in head_2)


def test_diversify_empty_no_op():
    assert diversify_by_subtype([]) == []


def test_diversify_japanese_no_brand_spam_d073_1_followup():
    """D-073.1 副作用防线: 5 道全萨莉亚式同品牌日料 → 即使免 cuisine cap,
    纵向 subtype 多样化能让前 3 道至少覆盖 2+ subtypes.
    """
    cs = [
        _combo("r_a", "豚骨拉面", cuisine="日式"),
        _combo("r_b", "酱油拉面", cuisine="日式"),
        _combo("r_c", "三文鱼寿司", cuisine="日式"),
        _combo("r_d", "鳗鱼盖饭", cuisine="日式"),  # 定食候选
        _combo("r_e", "烤鸡串", cuisine="日式"),    # 居酒屋
    ]
    out = diversify_by_subtype(cs, target_subtypes=3, max_per_subtype=2)
    front_3_subtypes = {infer_combo_subtype(out[i]).subtype for i in range(3)}
    # 5 个 candidates 覆盖 3+ subtypes 时, 前 3 应至少跨 2 个
    # (round-robin 严格保证)
    assert len(front_3_subtypes) >= 2


def test_diversify_preserves_all_combos():
    """无论怎么重排, 输出长度 == 输入长度 (不砍数量, brief 要求)."""
    cs = [_combo(f"r{i}", f"菜{i}") for i in range(10)]
    out = diversify_by_subtype(cs, target_subtypes=3, max_per_subtype=2)
    assert len(out) == 10
    assert {c["restaurant"]["id"] for c in out} == \
           {c["restaurant"]["id"] for c in cs}

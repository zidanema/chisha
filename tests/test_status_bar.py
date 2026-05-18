"""T-P1b-01 status_bar payload builder 单测."""
from __future__ import annotations

from chisha.status_bar import build_status_bar


def _profile(**overrides):
    base = {
        "methodology": "harvard_plate",
        "plate_rule": {
            "min_vegetable_dishes": 1,
            "min_protein_g": 40,
            "hard_max_oil_level": 4,
        },
    }
    base.update(overrides)
    return base


def test_baseline_no_events():
    sb = build_status_bar(_profile(), [])
    labels = sb["active_methodology"]["labels"]
    assert "哈佛餐盘" in labels
    assert "蔬菜≥1" in labels
    assert "蛋白≥40g" in labels
    assert "油≤4" in labels
    assert sb["l0_protections"]["allergies"] == []
    assert sb["l0_protections"]["dietary_law"] is None
    assert sb["override_events"] == []


def test_l0_a_block_event():
    profile = _profile(l0_constraints={"medical": {"allergies": ["花生"]}})
    events = [
        {
            "event_type": "hard_filter",
            "category": "L0_A_medical",
            "rule": "allergy:花生",
            "dropped_count": 3,
            "kept_count": 200,
            "refine_override": False,
            "timestamp": 0.0,
        }
    ]
    sb = build_status_bar(profile, events)
    assert sb["l0_protections"]["allergies"] == ["花生"]
    assert len(sb["override_events"]) == 1
    ev = sb["override_events"][0]
    assert ev["kind"] == "l0_a_block"
    assert ev["term"] == "花生"
    assert "花生" in ev["message"]
    assert ev["dropped_count"] == 3


def test_l0_b_vegetarian_block():
    profile = _profile(l0_constraints={"identity": {"dietary_law": "vegetarian"}})
    events = [{
        "event_type": "hard_filter",
        "category": "L0_B_identity",
        "rule": "vegetarian_ban_红肉",
        "dropped_count": 50,
        "kept_count": 100,
        "refine_override": False,
        "timestamp": 0.0,
    }]
    sb = build_status_bar(profile, events)
    assert sb["l0_protections"]["dietary_law"] == "vegetarian"
    assert sb["override_events"][0]["kind"] == "l0_b_block"
    assert "素食" in sb["override_events"][0]["message"]
    assert "红肉" in sb["override_events"][0]["message"]


def test_l0_b_halal_pork():
    profile = _profile(l0_constraints={"identity": {"dietary_law": "halal"}})
    events = [{
        "event_type": "hard_filter",
        "category": "L0_B_identity",
        "rule": "halal_pork:猪",
        "dropped_count": 20,
        "kept_count": 80,
        "refine_override": False,
        "timestamp": 0.0,
    }]
    sb = build_status_bar(profile, events)
    assert sb["override_events"][0]["kind"] == "l0_b_block"
    assert "清真" in sb["override_events"][0]["message"]
    assert "猪" in sb["override_events"][0]["message"]


def test_l0_c_relaxed_refine_override():
    """refine 触发 methodology 解除 → 破戒模式提示."""
    events = [{
        "event_type": "hard_filter",
        "category": "methodology",
        "rule": "refine_break_relaxed_plate_rule",
        "dropped_count": 0,
        "kept_count": 100,
        "refine_override": True,
        "timestamp": 0.0,
    }]
    sb = build_status_bar(_profile(), events)
    assert sb["override_events"][0]["kind"] == "l0_c_relaxed"
    assert "破戒模式" in sb["override_events"][0]["message"]


def test_methodology_event_without_override_not_shown():
    """category=methodology 但 refine_override=False → 不展示 (无意义)."""
    events = [{
        "event_type": "hard_filter",
        "category": "methodology",
        "rule": "some_normal_methodology_rule",
        "dropped_count": 5,
        "kept_count": 100,
        "refine_override": False,
        "timestamp": 0.0,
    }]
    sb = build_status_bar(_profile(), events)
    assert sb["override_events"] == []


def test_multiple_events_aggregated():
    profile = _profile(
        l0_constraints={"medical": {"allergies": ["花生", "海鲜"]}},
    )
    events = [
        {"event_type": "hard_filter", "category": "L0_A_medical",
         "rule": "allergy:花生", "dropped_count": 3, "kept_count": 200,
         "refine_override": False, "timestamp": 0.0},
        {"event_type": "hard_filter", "category": "L0_A_medical",
         "rule": "allergy:海鲜", "dropped_count": 5, "kept_count": 200,
         "refine_override": False, "timestamp": 0.0},
        {"event_type": "hard_filter", "category": "methodology",
         "rule": "refine_break_relaxed_plate_rule", "dropped_count": 0,
         "kept_count": 100, "refine_override": True, "timestamp": 0.0},
    ]
    sb = build_status_bar(profile, events)
    assert len(sb["override_events"]) == 3
    kinds = [e["kind"] for e in sb["override_events"]]
    assert kinds.count("l0_a_block") == 2
    assert kinds.count("l0_c_relaxed") == 1


def test_unknown_dietary_law_falls_back_to_none():
    """load_l0_constraints 对未知 dietary_law 保守降级为 None."""
    profile = _profile(l0_constraints={"identity": {"dietary_law": "weird_diet"}})
    sb = build_status_bar(profile, [])
    assert sb["l0_protections"]["dietary_law"] is None


def test_labels_handle_missing_plate_rule():
    """plate_rule 缺字段时只输出 methodology name."""
    profile = {"methodology": "harvard_plate"}
    sb = build_status_bar(profile, [])
    assert sb["active_methodology"]["labels"] == ["哈佛餐盘"]

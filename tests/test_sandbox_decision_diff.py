"""S-06b: build_decision pure-function coverage."""
from __future__ import annotations

from chisha.sandbox_decision_diff import build_decision


def _find_diff(items: list[dict], field: str) -> dict | None:
    for it in items:
        if it.get("field") == field:
            return it
    return None


def test_eat_happy():
    """taste up + fatigue from '—' + recent_dishes add + implications full."""
    d = build_decision(
        sid="s1",
        meal_idx=4,  # D3 午
        picked_rec={"name": "蓉香记", "dishes": ["回锅肉", "蒜苗炒腊肉"], "rank": 1, "l3": 88},
        prev_long_term_prefs={"boost": {"香": 0.32}},
        new_long_term_prefs={"boost": {"香": 0.35}},
        history=[{"dish": "蓉香记"}],  # 本顿
    )
    assert d["when"] == "D3 午"
    assert d["pick"] == "蓉香记 · 回锅肉 + 蒜苗炒腊肉"
    assert d["rank"] == 1
    assert d["l3"] == 88

    recent = _find_diff(d["diff"], "recent_dishes")
    assert recent and recent["kind"] == "add" and recent["value"] == "+ [蓉香记]"

    fatigue = _find_diff(d["diff"], "fatigue.蓉香记")
    assert fatigue and fatigue["from"] == "—" and fatigue["to"] == "1"

    taste = _find_diff(d["diff"], "taste.<香>")
    assert taste and taste["kind"] == "up"
    assert taste["from"] == "0.32" and taste["to"] == "0.35" and taste["delta"] == "+0.03"

    # implications
    taste_impl = _find_diff(d["implications"], "taste.<香>")
    assert taste_impl and "下顿 L2 给同类 +0.03" in taste_impl["text"]
    fatigue_impl = _find_diff(d["implications"], "fatigue.蓉香记")
    assert fatigue_impl and "下顿同菜折 0.95" in fatigue_impl["text"]


def test_eat_same_dish_twice():
    """history[-1] 本顿 + history[:-1] 含 1 次 → fatigue from='1' to='2'."""
    d = build_decision(
        sid="s1",
        meal_idx=3,  # D2 晚
        picked_rec={"name": "A", "rank": 2, "l3": 70},
        prev_long_term_prefs={},
        new_long_term_prefs={},
        history=[{"dish": "A"}, {"dish": "A"}],  # 一次旧 + 本顿
    )
    assert d["when"] == "D2 晚"
    fatigue = _find_diff(d["diff"], "fatigue.A")
    assert fatigue and fatigue["from"] == "1" and fatigue["to"] == "2"


def test_skip():
    d = build_decision(
        sid="s1",
        meal_idx=0,
        picked_rec=None,
        prev_long_term_prefs={"boost": {"香": 0.32}},
        new_long_term_prefs={"boost": {"香": 0.35}},  # 跳过情况下也不参考
        history=[],
    )
    assert d["when"] == "D1 午"
    assert d["pick"] == "(跳过)"
    assert d["rank"] == "—"
    assert d["l3"] == "—"
    assert d["diff"] == []
    assert len(d["implications"]) == 1
    assert "跳过未触发学习" in d["implications"][0]["text"]


def test_taste_no_change():
    """prev==new → diff 不含 taste, implications 只有 fatigue."""
    d = build_decision(
        sid="s1",
        meal_idx=0,
        picked_rec={"name": "B", "rank": 3, "l3": 60},
        prev_long_term_prefs={"boost": {"辣": 0.5}},
        new_long_term_prefs={"boost": {"辣": 0.5}},
        history=[{"dish": "B"}],
    )
    # taste 行不存在
    assert _find_diff(d["diff"], "taste.<辣>") is None
    # implications 不含 taste
    assert _find_diff(d["implications"], "taste.<辣>") is None
    # fatigue impl 仍在
    assert _find_diff(d["implications"], "fatigue.B") is not None


def test_prefs_both_empty():
    d = build_decision(
        sid="s1",
        meal_idx=0,
        picked_rec={"name": "C", "rank": 4, "l3": 50},
        prev_long_term_prefs={},
        new_long_term_prefs={},
        history=[{"dish": "C"}],
    )
    # diff 仅 recent + fatigue
    fields = [it["field"] for it in d["diff"]]
    assert "recent_dishes" in fields
    assert "fatigue.C" in fields
    assert not any(f.startswith("taste.") for f in fields)


def test_taste_down():
    d = build_decision(
        sid="s1",
        meal_idx=2,
        picked_rec={"name": "D", "rank": 1, "l3": 90},
        prev_long_term_prefs={"boost": {"辣": 0.5}},
        new_long_term_prefs={"boost": {"辣": 0.4}},
        history=[{"dish": "D"}],
    )
    taste = _find_diff(d["diff"], "taste.<辣>")
    assert taste and taste["kind"] == "dn"
    assert taste["from"] == "0.50" and taste["to"] == "0.40"
    assert taste["delta"] == "-0.10"
    impl = _find_diff(d["implications"], "taste.<辣>")
    assert impl and "-0.10" in impl["text"]


def test_pick_without_dishes():
    """picked_rec 无 dishes 字段 → pick = name only."""
    d = build_decision(
        sid="s1",
        meal_idx=0,
        picked_rec={"name": "蓉香记", "rank": 1, "l3": 88},
        prev_long_term_prefs={},
        new_long_term_prefs={},
        history=[{"dish": "蓉香记"}],
    )
    assert d["pick"] == "蓉香记"


def test_taste_below_epsilon_not_listed():
    """|delta| < 1e-3 → 不落 diff."""
    d = build_decision(
        sid="s1",
        meal_idx=0,
        picked_rec={"name": "E", "rank": 1, "l3": 80},
        prev_long_term_prefs={"boost": {"香": 0.3201}},
        new_long_term_prefs={"boost": {"香": 0.3203}},  # delta 0.0002 < 1e-3
        history=[{"dish": "E"}],
    )
    assert _find_diff(d["diff"], "taste.<香>") is None

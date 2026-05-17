"""D-083: feedback 短链路观测性测试.

覆盖 (S2 共识 v1.1):
- build_feedback_view 返回的 feedback_trace 公式与 score 实际计算严格一致
  (signal/decay/rules_fired 三段都做 parity 守门, 防漂移)
- normalize_feedback_view 保留 feedback_trace (避开 score 路径丢失因果)
- score 函数 with_evidence=True 返 tuple, 默认 float (backward compat)
- score breakdown 仍是 dict[str, float] (Codex Q1 不变量: 不破坏
  debug_recommend._format_ranked_for_trace round(v, 3) 序列化)
- combo.feedback_evidence 是 sibling 字段, 不入 breakdown
"""
import datetime as dt
import math

import pytest

from chisha.feedback_store import (
    build_feedback_view,
    normalize_feedback_view,
)
from chisha.score import (
    _feedback_single_signal,
    feedback_recency_score,
    next_meal_calibration_score,
    note_boost_score,
    rank_combos,
    score_combo,
)


# ─────────────────────── fixtures ───────────────────────

def _store(*, accepted=None, feedbacks=None):
    return {
        "accepted": accepted or {},
        "feedbacks": feedbacks or {},
        "sessions": {},
    }


def _profile():
    return {
        "plate_rule": {"min_protein_g": 40},
        "preferences": {
            "spicy_tolerance": 2,
            "avoid_dishes": [],
            "cuisine_preference": [],
        },
        "scoring_weights": {
            "feedback_recency": 1.0,
            "next_meal_calibration": 0.8,
            "note_boost": 0.6,
        },
    }


def _combo(rest_name="X", oil=3, n_dishes=3, protein=60, cuisine=None):
    dishes = []
    for i in range(n_dishes):
        d = {
            "nutrition_profile": {
                "oil_level": oil,
                "protein_grams_estimate": protein / n_dishes,
            }
        }
        if cuisine:
            d["cuisine"] = cuisine
        dishes.append(d)
    return {"restaurant": {"name": rest_name}, "dishes": dishes}


# ─────────────────────── feedback_trace schema ───────────────────────

def test_feedback_trace_present_in_view():
    """build_feedback_view 返回 4 个 sibling key, 含 feedback_trace."""
    view = build_feedback_view({}, dt.date(2026, 5, 17))
    assert set(view.keys()) == {
        "ratings", "calibrations", "note_tokens", "feedback_trace"
    }


def test_feedback_trace_empty_skeleton_for_empty_store():
    """空 store → feedback_trace 是 empty=True 骨架, 字段齐全."""
    view = build_feedback_view({}, dt.date(2026, 5, 17))
    tr = view["feedback_trace"]
    assert tr["empty"] is True
    assert tr["today"] == "2026-05-17"
    assert tr["rating_signals"] == []
    assert tr["calibration_rules"] == []
    assert tr["note_breakdown"] == []
    assert tr["windows"]["ratings"] == 60
    assert tr["windows"]["calibrations"] == 7
    assert tr["windows"]["note_tokens"] == 14


def test_normalize_feedback_view_preserves_feedback_trace():
    """D-083 反退化守门: normalize 必须保留 feedback_trace, 否则 score 路径丢
    上下文 (Codex Q3: 不能用 .get('_trace') 因 normalize 历史会剥离未知 key).
    """
    view = build_feedback_view({}, dt.date(2026, 5, 17))
    norm = normalize_feedback_view(view)
    assert "feedback_trace" in norm
    assert norm["feedback_trace"] == view["feedback_trace"]


def test_normalize_v1_list_gives_empty_trace_skeleton():
    """v1 list[dict] → 空骨架 feedback_trace (向后兼容老 frozen trace)."""
    v1 = [{"restaurant_name": "X", "rating": -1, "age_days": 1}]
    norm = normalize_feedback_view(v1)
    assert norm["feedback_trace"]["empty"] is True
    assert norm["ratings"] == v1


def test_normalize_none_gives_empty_trace_skeleton():
    norm = normalize_feedback_view(None)
    assert norm["feedback_trace"]["empty"] is True


# ─────────────────────── rating_signals parity ───────────────────────

@pytest.mark.parametrize("rating,age,expected_stage", [
    (-1, 0, "neg_decay"),
    (-1, 7, "neg_decay"),
    (-1, 30, "neg_decay"),
    (1, 0, "pos_cooldown"),
    (1, 2, "pos_cooldown"),
    (1, 3, "pos_boost"),
    (1, 14, "pos_boost"),
])
def test_rating_signals_match_score_formula(rating, age, expected_stage):
    """D-083 公式 parity: feedback_trace.rating_signals[i].signal 必须严格等于
    score._feedback_single_signal(rating, age).
    """
    today = dt.date(2026, 5, 17)
    accepted_at = (today - dt.timedelta(days=age)).isoformat() + "T12:00:00+00:00"
    store = _store(
        accepted={"s1": {"restaurant_name": "灶台",
                          "accepted_at": accepted_at,
                          "accepted_rank": 1}},
        feedbacks={"s1": {"session_id": "s1", "rating": rating,
                           "submitted_at": accepted_at}},
    )
    view = build_feedback_view(store, today)
    sigs = view["feedback_trace"]["rating_signals"]
    assert len(sigs) == 1
    entry = sigs[0]
    assert entry["restaurant_name"] == "灶台"
    assert entry["rating"] == rating
    assert entry["age_days"] == age
    assert entry["factors"]["stage"] == expected_stage
    # 公式数学一致 (4 位小数)
    expected_signal = _feedback_single_signal(rating, age)
    assert entry["signal"] == pytest.approx(expected_signal, abs=1e-4)


# ─────────────────────── calibration_rules parity ───────────────────────

def test_calibration_rules_describe_upstream_triggers():
    """calibration_rules 在 view 层只描述 *上游触发条件* (oil=2 触发 oil 类规则),
    实际 combo 级 contribution 由 score 写到 combo.feedback_evidence.
    """
    today = dt.date(2026, 5, 17)
    store = _store(
        accepted={"s1": {"restaurant_name": "灶台",
                          "accepted_at": "2026-05-16T12:00:00+00:00",
                          "accepted_rank": 1}},
        feedbacks={"s1": {"session_id": "s1", "rating": None,
                           "oil_calibration": 2, "fullness": 0,
                           "reason_match": 0,
                           "submitted_at": "2026-05-16T12:00:00+00:00"}},
    )
    view = build_feedback_view(store, today)
    rules = view["feedback_trace"]["calibration_rules"]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["age_meals"] == 0
    assert rule["weight"] == 1.0
    # 应触发 3 个 trigger (oil/fullness/reason — reason 需有 last_meal_cuisine
    # 但没 candidates → 不会触发. 验证 oil + fullness)
    trigger_fields = [t["field"] for t in rule["triggers"]]
    assert "oil_calibration" in trigger_fields
    assert "fullness" in trigger_fields


# ─────────────────────── note_breakdown parity ───────────────────────

def test_note_breakdown_decay_matches_exp_formula():
    """note_breakdown[i].decay 必须严格 == exp(-age/7) (4 位小数)."""
    today = dt.date(2026, 5, 17)
    store = _store(
        accepted={"s1": {"restaurant_name": "灶台",
                          "accepted_at": "2026-05-16T12:00:00+00:00",
                          "accepted_rank": 1}},
        feedbacks={"s1": {"session_id": "s1", "note": "太油了",
                           "submitted_at": "2026-05-16T12:00:00+00:00"}},
    )
    view = build_feedback_view(store, today)
    nb = view["feedback_trace"]["note_breakdown"]
    assert len(nb) == 1
    entry = nb[0]
    assert entry["age_days"] == 1
    assert entry["decay"] == pytest.approx(math.exp(-1/7.0), abs=1e-4)
    assert "low_oil" in entry["boost"]


# ─────────────────────── score with_evidence contract ───────────────────────

def test_feedback_recency_score_default_returns_float():
    """backward compat: 默认不传 with_evidence → 仍返 float (老 callers 不破)."""
    view = {"ratings": [{"restaurant_name": "灶台", "rating": -1, "age_days": 1}],
            "calibrations": [], "note_tokens": []}
    result = feedback_recency_score(_combo(rest_name="灶台"), view)
    assert isinstance(result, float)


def test_feedback_recency_score_with_evidence_returns_tuple():
    view = {"ratings": [{"restaurant_name": "灶台", "rating": -1, "age_days": 1}],
            "calibrations": [], "note_tokens": []}
    signal, ev = feedback_recency_score(
        _combo(rest_name="灶台"), view, with_evidence=True
    )
    assert isinstance(signal, float)
    assert isinstance(ev, list)
    assert len(ev) == 1
    assert ev[0]["restaurant_name"] == "灶台"
    assert ev[0]["signal"] == pytest.approx(signal, abs=1e-4)


def test_next_meal_calibration_with_evidence_lists_fired_rules():
    """next_meal_calibration_score with_evidence=True 返 (signal, [rules_fired])."""
    view = {"ratings": [],
            "calibrations": [{"session_id": "s1", "restaurant_name": "灶台",
                                "age_meals": 0, "age_days": 1,
                                "oil_calibration": 2, "fullness": None,
                                "reason_match": None,
                                "last_meal_cuisine": None}],
            "note_tokens": []}
    light_combo = _combo(oil=2)  # avg_oil=2, 命中 oil=2 → +0.5
    signal, ev = next_meal_calibration_score(
        light_combo, view, _profile(), with_evidence=True
    )
    assert signal == pytest.approx(0.5)
    assert len(ev) == 1
    fired = ev[0]["rules_fired"]
    assert len(fired) == 1
    assert "oil=2 (太油)" in fired[0]["rule"]
    assert fired[0]["contribution"] == pytest.approx(0.5)


def test_note_boost_with_evidence_tracks_token_decay():
    """note_boost_score with_evidence=True 返 (signal, [token-level evidence])."""
    view = {"ratings": [], "calibrations": [],
            "note_tokens": [
                {"restaurant_name": "灶台", "age_days": 1,
                 "boost": ["low_oil"], "penalty": [], "raw_text": "太油了"}
            ]}
    light_combo = _combo(rest_name="灶台", oil=1)  # avg=1 → low_oil match
    signal, ev = note_boost_score(
        light_combo, view, _profile(), with_evidence=True
    )
    assert signal > 0
    # 应有至少一条 evidence
    assert any(e["token"] == "low_oil" for e in ev)


# ─────────────────────── score_combo evidence collector ───────────────────────

def test_score_combo_breakdown_stays_numeric():
    """D-083 不变量: score breakdown 必须保持 dict[str, float] (避开
    debug_recommend._format_ranked_for_trace 的 round(v,3) 序列化).
    """
    view = build_feedback_view(
        _store(
            accepted={"s1": {"restaurant_name": "灶台",
                              "accepted_at": "2026-05-16T12:00:00+00:00",
                              "accepted_rank": 1}},
            feedbacks={"s1": {"session_id": "s1", "rating": -1,
                               "submitted_at": "2026-05-16T12:00:00+00:00"}},
        ),
        dt.date(2026, 5, 17),
    )
    combo = _combo(rest_name="灶台")
    score, breakdown = score_combo(combo, _profile(), feedback_view=view)
    # 所有 breakdown value 必须是 float
    for k, v in breakdown.items():
        assert isinstance(v, (int, float)), f"breakdown[{k!r}] = {v!r} 不是 numeric"


def test_score_combo_evidence_collector_writes_sibling():
    """feedback_evidence_collector 写到 sibling, 不入 breakdown."""
    view = build_feedback_view(
        _store(
            accepted={"s1": {"restaurant_name": "灶台",
                              "accepted_at": "2026-05-16T12:00:00+00:00",
                              "accepted_rank": 1}},
            feedbacks={"s1": {"session_id": "s1", "rating": -1,
                               "submitted_at": "2026-05-16T12:00:00+00:00"}},
        ),
        dt.date(2026, 5, 17),
    )
    combo = _combo(rest_name="灶台")
    ev_collector: dict = {}
    score, breakdown = score_combo(
        combo, _profile(), feedback_view=view,
        feedback_evidence_collector=ev_collector,
    )
    # feedback_recency 命中
    assert "feedback_recency" in breakdown
    assert "feedback_recency" in ev_collector
    # evidence 不入 breakdown
    assert "feedback_recency_evidence" not in breakdown


def test_rank_combos_attaches_feedback_evidence_to_each_combo():
    """rank_combos 输出每个 combo 都带 feedback_evidence dict (空则 {})."""
    view = build_feedback_view(
        _store(
            accepted={"s1": {"restaurant_name": "灶台",
                              "accepted_at": "2026-05-16T12:00:00+00:00",
                              "accepted_rank": 1}},
            feedbacks={"s1": {"session_id": "s1", "rating": -1,
                               "submitted_at": "2026-05-16T12:00:00+00:00"}},
        ),
        dt.date(2026, 5, 17),
    )
    combos = [_combo(rest_name="灶台"), _combo(rest_name="其他")]
    ranked = rank_combos(
        combos, _profile(), today=dt.date(2026, 5, 17), feedback_view=view
    )
    for c in ranked:
        assert "feedback_evidence" in c
        assert isinstance(c["feedback_evidence"], dict)
    # 灶台 combo 应有 feedback_recency evidence
    zaotai = [c for c in ranked if c["restaurant"]["name"] == "灶台"][0]
    assert "feedback_recency" in zaotai["feedback_evidence"]


def test_empty_feedback_view_no_evidence_no_breakdown_keys():
    """守门: 空 view → 既不写 breakdown key 也不写 evidence key (baseline 不变)."""
    view = build_feedback_view({}, dt.date(2026, 5, 17))
    combo = _combo(rest_name="X")
    ev_collector: dict = {}
    score, breakdown = score_combo(
        combo, _profile(), feedback_view=view,
        feedback_evidence_collector=ev_collector,
    )
    assert "feedback_recency" not in breakdown
    assert "next_meal_calibration" not in breakdown
    assert "note_boost" not in breakdown
    assert ev_collector == {}


# ─────────────────────── Codex S3 补测: 边界 ───────────────────────

def test_invalid_store_returns_full_4_key_schema():
    """Codex S3 MINOR: invalid store / window<0 也得返 4 key (不能少 feedback_trace)."""
    v1 = build_feedback_view(None, dt.date(2026, 5, 17))  # type: ignore
    assert set(v1.keys()) == {"ratings", "calibrations", "note_tokens",
                                "feedback_trace"}
    assert v1["feedback_trace"]["empty"] is True

    v2 = build_feedback_view({}, dt.date(2026, 5, 17), window_days=-1)
    assert set(v2.keys()) == {"ratings", "calibrations", "note_tokens",
                                "feedback_trace"}
    assert v2["feedback_trace"]["empty"] is True


def test_same_restaurant_multiple_ratings_aggregate():
    """同餐厅多条 rating → rating_signals 列每条; score 聚合取最强负向."""
    today = dt.date(2026, 5, 17)
    store = _store(
        accepted={
            "s1": {"restaurant_name": "灶台",
                    "accepted_at": "2026-05-16T12:00:00+00:00",
                    "accepted_rank": 1},
            "s2": {"restaurant_name": "灶台",
                    "accepted_at": "2026-05-10T12:00:00+00:00",
                    "accepted_rank": 1},
        },
        feedbacks={
            "s1": {"session_id": "s1", "rating": 1,
                    "submitted_at": "2026-05-16T12:00:00+00:00"},
            "s2": {"session_id": "s2", "rating": -1,
                    "submitted_at": "2026-05-10T12:00:00+00:00"},
        },
    )
    view = build_feedback_view(store, today)
    sigs = view["feedback_trace"]["rating_signals"]
    assert len(sigs) == 2  # view 层不聚合
    combo = _combo(rest_name="灶台")
    signal, ev = feedback_recency_score(combo, view, with_evidence=True)
    # score 路径聚合 → 最强负向 (防"远期 -1 + 近期 +1 错误抵消", Codex B-001 拍板)
    assert signal < 0
    assert len(ev) == 2


def test_rank_combos_collector_isolation_per_combo():
    """Codex S3 MINOR: rank_combos 每个 combo 独立 collector 不串味."""
    view = build_feedback_view(
        _store(
            accepted={"s1": {"restaurant_name": "店A",
                              "accepted_at": "2026-05-16T12:00:00+00:00",
                              "accepted_rank": 1}},
            feedbacks={"s1": {"session_id": "s1", "rating": -1,
                               "submitted_at": "2026-05-16T12:00:00+00:00"}},
        ),
        dt.date(2026, 5, 17),
    )
    combos = [_combo(rest_name="店A"), _combo(rest_name="店B")]
    ranked = rank_combos(
        combos, _profile(), today=dt.date(2026, 5, 17), feedback_view=view
    )
    by_rest = {c["restaurant"]["name"]: c for c in ranked}
    assert "feedback_recency" in by_rest["店A"]["feedback_evidence"]
    assert "feedback_recency" not in by_rest["店B"]["feedback_evidence"]


def test_age_1d_signal_precise_value():
    """Codex S3 MINOR: age=1d 精确值守门 (sandbox advance 后第一次衰减)."""
    today = dt.date(2026, 5, 17)
    store = _store(
        accepted={"s1": {"restaurant_name": "灶台",
                          "accepted_at": "2026-05-16T12:00:00+00:00",
                          "accepted_rank": 1}},
        feedbacks={"s1": {"session_id": "s1", "rating": -1,
                           "submitted_at": "2026-05-16T12:00:00+00:00"}},
    )
    view = build_feedback_view(store, today)
    sig = view["feedback_trace"]["rating_signals"][0]["signal"]
    assert sig == pytest.approx(-1.5 * math.exp(-1 / 14.0), abs=1e-5)


def test_note_no_matching_token_yields_empty_breakdown():
    """note 不命中任何词表 token → note_breakdown 空."""
    today = dt.date(2026, 5, 17)
    store = _store(
        accepted={"s1": {"restaurant_name": "灶台",
                          "accepted_at": "2026-05-16T12:00:00+00:00",
                          "accepted_rank": 1}},
        feedbacks={"s1": {"session_id": "s1",
                           "note": "我喜欢这家店,服务好",
                           "submitted_at": "2026-05-16T12:00:00+00:00"}},
    )
    view = build_feedback_view(store, today)
    assert view["feedback_trace"]["note_breakdown"] == []
    assert view["note_tokens"] == []


def test_trace_schema_v1_legacy_read_compat(tmp_path):
    """Codex S3: v1 trace 仍可读 (LEGACY_TRACE_SCHEMA_VERSIONS={1})."""
    import json
    from chisha import trace_store

    legacy = {
        "__version": 1,
        "__source": "production",
        "__frozen": {"meal_type": "lunch", "today": "2026-05-15"},
        "session_id": "legacy_test",
        "l1": {}, "l2": {}, "l3": {}, "final": [],
    }
    td_path = (tmp_path / "logs" / "recommend_trace")
    td_path.mkdir(parents=True)
    (td_path / "legacy_test.json").write_text(json.dumps(legacy))
    out = trace_store.read_trace("legacy_test", root=tmp_path)
    assert out is not None
    assert out["__version"] == 1
    # v1 trace 不含新字段; 调用方/前端走空骨架兜底
    assert "feedback_view_snapshot" not in out


def test_trace_schema_unknown_version_still_rejected(tmp_path):
    """未知 version (非 1/2) 仍 hard-fail TraceVersionMismatch."""
    import json
    from chisha import trace_store

    bad = {"__version": 99, "session_id": "bad", "l1": {}, "l2": {}, "l3": {}}
    td_path = (tmp_path / "logs" / "recommend_trace")
    td_path.mkdir(parents=True)
    (td_path / "bad.json").write_text(json.dumps(bad))
    with pytest.raises(trace_store.TraceVersionMismatch):
        trace_store.read_trace("bad", root=tmp_path)

"""T-P2-01: reference resolver + 比较器 单测.

覆盖:
  - parse_reference_text: 5 类典型表达 + 否定 case
  - resolve_reference: 时间引用 / weekday / 上次 / meal_hint
  - apply_relation: lighter / similar_but_different_venue / similar
  - 找不到历史返 None, 不崩
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from chisha import trace_store
from chisha.reference_resolver import (
    ReferenceQuery,
    ResolvedReference,
    apply_relation,
    parse_reference_text,
    resolve_reference,
)


# ────────────────────────── parse_reference_text


def test_parse_lighter():
    q = parse_reference_text("比昨天清淡")
    assert q is not None
    assert q.relation == "lighter"
    assert q.days_back == 1


def test_parse_similar_but_different_venue():
    q = parse_reference_text("和上次那家差不多但换一家")
    assert q is not None
    assert q.relation == "similar_but_different_venue"


def test_parse_similar_repeat():
    q = parse_reference_text("和上次那顿一样")
    assert q is not None
    assert q.relation == "similar"


def test_parse_yesterday_lunch():
    q = parse_reference_text("比昨天午饭清淡")
    assert q is not None
    assert q.days_back == 1
    assert q.meal_hint == "lunch"


def test_parse_weekday_reference():
    q = parse_reference_text("和上周三差不多")
    assert q is not None
    assert q.days_back == -1  # sentinel


def test_parse_last_time():
    q = parse_reference_text("和上次那家差不多")
    assert q is not None
    # 包含 "上次" → days_back=-2 (sentinel)
    assert q.days_back == -2
    # "差不多" 命中 _SIMILAR_KEYWORDS → similar (没"换一家"故不是 diff_venue)
    assert q.relation == "similar"


def test_parse_last_time_diff_venue():
    q = parse_reference_text("和上次那家差不多但换一家")
    assert q is not None
    assert q.relation == "similar_but_different_venue"


def test_parse_no_reference_returns_none():
    """普通 refine 表达不命中 reference parse."""
    assert parse_reference_text("想吃湘菜的肉") is None
    assert parse_reference_text("低油的") is None
    assert parse_reference_text("") is None


def test_parse_avoid_pattern_not_supported_yet():
    """brief §12 'avoid_pattern' (不要像那次那样) V2 范畴; 本次允许命中关键词但
    relation 走 unknown / similar 兜底."""
    # "不要像那次那样" 包含"那次" 但没 lighter/diff_venue/similar 关键词
    # 当前 parse 返 None (没命中任何 relation 关键词 + 时间词 "那次" 不在词表)
    # 这是预期: 暂不支持 negative reference
    q = parse_reference_text("不要像那次那样")
    # 接受 None 或 unknown relation (实现细节)
    assert q is None or q.relation == "unknown"


# ────────────────────────── resolve_reference (real trace_store)


def _seed_trace_at_date(tmp_path: Path, sid: str, target_date: dt.date,
                          meal_type: str = "lunch",
                          final_combos: list[dict] | None = None) -> None:
    """造一个 trace 落盘 (绕过 write_trace 兼容 v=1) 模拟历史会话."""
    d = trace_store.data_root.recommend_trace_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    started_at = dt.datetime.combine(target_date, dt.time(12, 0, 0),
                                       tzinfo=dt.timezone.utc).isoformat()
    trace = {
        "__version": trace_store.TRACE_SCHEMA_VERSION,
        "__source": "production",
        "session_id": sid,
        "started_at": started_at,
        "l1": {"summary": {}, "meal": meal_type,
                "hard_filter_events": []},
        "l2": {"summary": {}}, "l3": {"status": "skipped"},
        "final": final_combos or [],
        "__frozen": {"meal_type": meal_type},
    }
    (d / f"{sid}.json").write_text(json.dumps(trace, ensure_ascii=False),
                                     encoding="utf-8")


def test_resolve_yesterday_lunch_finds_trace(tmp_path: Path):
    """昨天 lunch 的 session 必须能被解析定位."""
    today = dt.date(2026, 5, 18)
    yesterday = today - dt.timedelta(days=1)
    sid = "sess_yesterday_lunch_001"
    final_combos = [{"restaurant": {"id": "r1", "name": "湘菜店"},
                      "dishes": [{"canonical_name": "宫保鸡丁", "cuisine": "湘菜",
                                    "nutrition_profile": {"oil_level": 3}}]}]
    _seed_trace_at_date(tmp_path, sid, yesterday, meal_type="lunch",
                         final_combos=final_combos)
    q = ReferenceQuery(raw_text="比昨天午饭清淡", relation="lighter",
                        days_back=1, meal_hint="lunch")
    resolved = resolve_reference(q, today=today, root=tmp_path)
    assert resolved is not None
    assert resolved.base_session_id == sid
    assert resolved.base_meal_type == "lunch"
    assert len(resolved.base_combos) == 1


def test_resolve_no_history_returns_none(tmp_path: Path):
    """没历史 trace → 返 None."""
    today = dt.date(2026, 5, 18)
    q = ReferenceQuery(raw_text="比昨天清淡", relation="lighter",
                        days_back=1, meal_hint=None)
    resolved = resolve_reference(q, today=today, root=tmp_path)
    assert resolved is None


def test_resolve_last_time_takes_most_recent(tmp_path: Path):
    """'上次' → 拿最近一条匹配 meal_hint 的 trace."""
    today = dt.date(2026, 5, 18)
    # 造 3 条不同日期的 lunch trace
    for days_ago, sid in [(5, "sess_old"), (2, "sess_mid"), (1, "sess_recent")]:
        date = today - dt.timedelta(days=days_ago)
        _seed_trace_at_date(tmp_path, sid, date, meal_type="lunch",
                             final_combos=[{"restaurant": {"id": "r"}}])
    q = ReferenceQuery(raw_text="和上次那家差不多", relation="similar",
                        days_back=-2, meal_hint=None)
    resolved = resolve_reference(q, today=today, root=tmp_path)
    assert resolved is not None
    assert resolved.base_session_id == "sess_recent"


# ────────────────────────── apply_relation


def _combo(rid: str, name: str, oil: int = 3, cuisine: str = "潮汕"):
    return {
        "restaurant": {"id": rid, "name": name},
        "dishes": [{"dish_id": f"d_{rid}", "canonical_name": name,
                     "cuisine": cuisine,
                     "nutrition_profile": {"oil_level": oil}}],
    }


def test_apply_relation_lighter_sorts_by_oil():
    candidates = [
        _combo("r1", "重油菜", oil=5),
        _combo("r2", "中油菜", oil=3),
        _combo("r3", "低油菜", oil=1),
    ]
    resolved = ResolvedReference(
        base_session_id="x", base_meal_type="lunch",
        base_started_at="2026-05-17", base_combos=[], relation="lighter",
        raw_text="比昨天清淡",
    )
    out = apply_relation(candidates, resolved)
    oils = [c["dishes"][0]["nutrition_profile"]["oil_level"] for c in out]
    assert oils == [1, 3, 5]


def test_apply_relation_similar_but_different_venue():
    candidates = [
        _combo("r_base", "店 A 菜"),
        _combo("r_other", "店 B 菜"),
    ]
    resolved = ResolvedReference(
        base_session_id="x", base_meal_type="lunch",
        base_started_at="2026-05-17",
        base_combos=[_combo("r_base", "上次菜")],
        relation="similar_but_different_venue",
        raw_text="和上次那家差不多但换一家",
    )
    out = apply_relation(candidates, resolved)
    # 不在 base_rest_ids 的应该在前
    assert out[0]["restaurant"]["id"] == "r_other"


def test_apply_relation_similar_prefers_same_cuisine():
    candidates = [
        _combo("r1", "日料", cuisine="日料"),
        _combo("r2", "潮汕菜", cuisine="潮汕"),
        _combo("r3", "湘菜", cuisine="湘菜"),
    ]
    resolved = ResolvedReference(
        base_session_id="x", base_meal_type="lunch",
        base_started_at="2026-05-17",
        base_combos=[_combo("r_base", "上次潮汕", cuisine="潮汕")],
        relation="similar", raw_text="和上次一样",
    )
    out = apply_relation(candidates, resolved)
    assert out[0]["dishes"][0]["cuisine"] == "潮汕"


def test_apply_relation_unknown_keeps_order():
    candidates = [_combo("r1", "A"), _combo("r2", "B")]
    resolved = ResolvedReference(
        base_session_id="x", base_meal_type="lunch",
        base_started_at="x", base_combos=[], relation="unknown",
        raw_text="?",
    )
    out = apply_relation(candidates, resolved)
    assert [c["restaurant"]["id"] for c in out] == ["r1", "r2"]


def test_apply_relation_empty_candidates_no_op():
    resolved = ResolvedReference(
        base_session_id="x", base_meal_type="lunch",
        base_started_at="x", base_combos=[], relation="lighter",
        raw_text="?",
    )
    assert apply_relation([], resolved) == []

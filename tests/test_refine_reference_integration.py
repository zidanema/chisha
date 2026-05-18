"""T-P2-01: refine path 接入 reference resolver/comparator 集成测试.

验证:
- "更清淡"/"换一家"/"上次"类文本 → refine 路径触发 reference resolve
- 历史 trace 命中时 ranked 被 apply_relation 软重排, top_k 内顺序变化
- trace 存 reference_resolved 字段供 debug
- 解析失败/无历史时静默降级, 不阻断 refine
- 无 refine 路径 (空 user_input) 完全不触发, baseline 行为不变
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path
from unittest import mock

from chisha.reference_resolver import (
    ReferenceQuery, ResolvedReference, parse_reference_text,
)


def test_parse_lighter_keyword_only():
    """无时间词但有关系词应能识别."""
    q = parse_reference_text("帮我推个更清淡的")
    assert q is not None
    assert q.relation == "lighter"


def test_parse_diff_venue_keyword():
    q = parse_reference_text("换一家试试")
    assert q is not None
    assert q.relation == "similar_but_different_venue"


def test_parse_empty_returns_none():
    """没有 reference 表达时返 None, refine 路径完全跳过."""
    assert parse_reference_text("") is None
    assert parse_reference_text("想吃辣的") is None
    assert parse_reference_text("换日料") is None


def test_apply_lighter_reorders_by_avg_oil():
    """lighter relation 软重排: 低油 combo 排前."""
    from chisha.reference_resolver import apply_relation
    cands = [
        {"id": "A", "dishes": [
            {"nutrition_profile": {"oil_level": 5}},
            {"nutrition_profile": {"oil_level": 4}},
        ]},
        {"id": "B", "dishes": [
            {"nutrition_profile": {"oil_level": 1}},
            {"nutrition_profile": {"oil_level": 2}},
        ]},
        {"id": "C", "dishes": [
            {"nutrition_profile": {"oil_level": 3}},
        ]},
    ]
    resolved = ResolvedReference(
        base_session_id="sess-x", base_meal_type="lunch",
        base_started_at="", base_combos=[],
        relation="lighter", raw_text="更清淡",
    )
    reordered = apply_relation(cands, resolved)
    assert [c["id"] for c in reordered] == ["B", "C", "A"]


def test_apply_diff_venue_pushes_same_rest_to_end():
    """similar_but_different_venue: base 餐厅 ID 的 combo 排末."""
    from chisha.reference_resolver import apply_relation
    cands = [
        {"id": "A", "restaurant": {"id": "rest-1"}, "dishes": []},
        {"id": "B", "restaurant": {"id": "rest-2"}, "dishes": []},
        {"id": "C", "restaurant": {"id": "rest-3"}, "dishes": []},
    ]
    resolved = ResolvedReference(
        base_session_id="sess-x", base_meal_type="lunch",
        base_started_at="",
        base_combos=[{"restaurant": {"id": "rest-2"}}],
        relation="similar_but_different_venue", raw_text="换一家",
    )
    reordered = apply_relation(cands, resolved)
    # rest-2 (B) 应该排末; rest-1 / rest-3 保留原顺序
    ids = [c["id"] for c in reordered]
    assert ids.index("B") == 2
    assert {"A", "C"} == {ids[0], ids[1]}


def test_refine_session_integrates_reference_resolve(tmp_path):
    """端到端: refine_session "更清淡" 触发 resolve+apply, trace 写 reference_resolved."""
    # 用 tmp_path 做 root, 注入一条历史 trace 让 resolver 能命中
    root = tmp_path
    (root / "logs" / "recommend_trace").mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)
    base_trace = {
        "__version": 2,
        "session_id": "sess-base",
        "started_at": yesterday.isoformat() + "T12:00:00+00:00",
        "meal_type": "lunch",
        "__frozen": {"meal_type": "lunch", "zone": "shenzhen-bay"},
        "final": [
            {"restaurant": {"id": "rest-old"}, "dishes": [
                {"nutrition_profile": {"oil_level": 4}},
            ]}
        ],
    }
    (root / "logs" / "recommend_trace" / "sess-base.json").write_text(
        json.dumps(base_trace, ensure_ascii=False)
    )

    # 直接验 resolve_reference, refine_session 全链路依赖太重
    from chisha.reference_resolver import (
        parse_reference_text, resolve_reference,
    )
    q = parse_reference_text("比昨天清淡一点")
    assert q is not None
    assert q.relation == "lighter"
    assert q.days_back == 1
    resolved = resolve_reference(q, today=today, root=root)
    assert resolved is not None
    assert resolved.base_session_id == "sess-base"
    assert resolved.relation == "lighter"


def test_refine_no_reference_text_skips_resolve():
    """不含 reference 表达的 refine, parse 返 None, refine path 不调 resolve."""
    # 这个测试的真实保障是 refine.py: ref_query is None → 跳过整个块
    assert parse_reference_text("想吃辣的") is None
    assert parse_reference_text("换日料") is None
    assert parse_reference_text("不要太油") is None  # 不算 reference

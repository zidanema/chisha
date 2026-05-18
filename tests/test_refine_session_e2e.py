"""Codex review M5: refine_session 全链路集成测试.

之前 23 个新单测全是 pure function (parse / apply / build_status_bar / diversify),
没有一条覆盖 refine_session() 链路里 trace 字段是否真的"接通"到 raw return /
_append_intent_trace / web_api base_trace.

这里 monkeypatch 重量级依赖 (recall/rank_combos/rerank/load_session/save_session),
跑 refine_session, 断言:
  - raw return 含 narrative + _reference_resolved + _subtype_diversified 透传
  - V2 reference slot 优先于 raw_text parser, source="v2_intent"
  - V2 reference 缺失时回落 raw_text parser, source="raw_parser"
  - cuisine_want 非空时 subtype_diversified=True
  - cuisine_want 空时 subtype_diversified=False
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def fake_refine_env(tmp_path: Path, monkeypatch):
    """monkeypatch refine_session 内部所有重依赖, 留 refine.py 真逻辑跑."""
    from chisha import refine as refine_mod
    from chisha.refine_intent import RefineIntent
    from chisha.refine_intent_v2 import RefineIntentV2
    from chisha.session import SessionState

    # 注入历史 trace (resolver 能命中)
    root = tmp_path
    (root / "logs" / "recommend_trace").mkdir(parents=True, exist_ok=True)
    today = dt.date(2026, 5, 18)
    yesterday = today - dt.timedelta(days=1)
    base_trace = {
        "__version": 2,
        "session_id": "sess-base",
        "started_at": yesterday.isoformat() + "T12:00:00+00:00",
        "meal_type": "lunch",
        "__frozen": {"meal_type": "lunch", "zone": "shenzhen-bay"},
        "final": [
            {"restaurant": {"id": "rest-base", "name": "Base 店"},
             "dishes": [{"nutrition_profile": {"oil_level": 4}}]}
        ],
    }
    (root / "logs" / "recommend_trace" / "sess-base.json").write_text(
        json.dumps(base_trace, ensure_ascii=False), encoding="utf-8"
    )

    # mock session
    state = SessionState(
        session_id="sess-ref-01",
        meal_type="lunch", zone="shenzhen-bay",
        round=1, daily_mood=None,
        last_candidates=[], refine_history=[],
        created_at=yesterday.isoformat() + "T11:00:00+00:00",
    )
    monkeypatch.setattr(refine_mod, "load_session",
                         lambda sid, root: state)
    monkeypatch.setattr(refine_mod, "save_session",
                         lambda *a, **kw: None)

    # mock recall / rank_combos / apply_caps → 不依赖真数据
    fake_combos = [
        {"restaurant": {"id": f"r-{i}", "name": f"店{i}"},
         "dishes": [
             {"canonical_name": f"湘菜-{i}", "cuisine": "湘菜",
              "nutrition_profile": {"oil_level": 2 if i % 2 == 0 else 4,
                                     "cooking_method": "炒"}}],
         "score": 5.0 - i * 0.1, "fit_score": 5.0 - i * 0.1}
        for i in range(10)
    ]
    monkeypatch.setattr(refine_mod, "recall", lambda *a, **kw: fake_combos)
    monkeypatch.setattr(refine_mod, "rank_combos", lambda *a, **kw: list(fake_combos))
    monkeypatch.setattr(refine_mod, "apply_caps",
                         lambda ranked, *a, **kw: ranked)

    # mock rerank → collector 写 narrative
    def _fake_rerank(top_k, profile, *, context, meal_log, n=5, n_explore=0,
                     refine=False, use_llm=None, root=None, trace_collector=None,
                     **kw):
        if trace_collector is not None:
            trace_collector["narrative"] = "test-narrative-from-rerank"
        return top_k[:n]
    monkeypatch.setattr(refine_mod, "rerank", _fake_rerank)

    # mock build_context (refine inline import)
    from chisha import context as ctx_mod

    class _Ctx:
        def to_llm_dict(self): return {}
    monkeypatch.setattr(ctx_mod, "build_context", lambda **kw: _Ctx())

    # 默认 use_llm=False → parse_refine_intent 走规则路径, V2 走 from_legacy
    return refine_mod, root, today


def _run_refine(refine_mod, root, *, user_input: str, intent_v2: object | None = None,
                today: dt.date | None = None) -> dict:
    """单独跑 refine_session, 可注入 RefineIntentV2 (绕过 LLM)."""
    # 把 extract_refine_intent_v2 mock 成返回特定 V2 (M3 V2-first 验证用)
    if intent_v2 is not None:
        with mock.patch.object(refine_mod, "extract_refine_intent_v2",
                                 return_value=intent_v2):
            return refine_mod.refine(
                session_id="sess-ref-01",
                user_input=user_input,
                profile={"basics": {"office_zone": "shenzhen-bay"}},
                rests=[], tagged=[], meal_log=[], root=root,
                today=today, n=5, use_llm=False,
            )
    return refine_mod.refine(
        session_id="sess-ref-01",
        user_input=user_input,
        profile={"basics": {"office_zone": "shenzhen-bay"}},
        rests=[], tagged=[], meal_log=[], root=root,
        today=today, n=5, use_llm=False,
    )


def test_narrative_threads_through_to_raw(fake_refine_env):
    """narrative collector 写入 → raw.narrative 透传给 web_api."""
    refine_mod, root, today = fake_refine_env
    raw = _run_refine(refine_mod, root, user_input="想吃湘菜", today=today)
    assert raw["narrative"] == "test-narrative-from-rerank"


def test_reference_resolved_field_threads_through(fake_refine_env):
    """raw text parser 命中 lighter → raw._reference_resolved 透传 + source=raw_parser."""
    refine_mod, root, today = fake_refine_env
    raw = _run_refine(refine_mod, root,
                       user_input="比昨天清淡一点", today=today)
    rr = raw["_reference_resolved"]
    assert rr is not None
    assert rr["relation"] == "lighter"
    assert rr["base_session_id"] == "sess-base"
    assert rr["source"] == "raw_parser"


def test_v2_reference_takes_priority_over_raw_parser(fake_refine_env):
    """V2 intent_v2.reference 存在时优先消费, source=v2_intent."""
    refine_mod, root, today = fake_refine_env
    from chisha.refine_intent_v2 import RefineIntentV2
    # V2 给了 lighter relation, raw_text 不含关系词只含时间词 ("昨天")
    intent_v2 = RefineIntentV2(
        raw_text="昨天",
        raw_understanding="(V2 mock)",
        reference={"reference_meal_id": None, "relation": "lighter"},
    )
    raw = _run_refine(refine_mod, root,
                       user_input="昨天", intent_v2=intent_v2, today=today)
    rr = raw["_reference_resolved"]
    assert rr is not None
    assert rr["relation"] == "lighter"
    assert rr["source"] == "v2_intent"


def test_subtype_diversified_threads_through_when_cuisine_want_filled(fake_refine_env):
    """cuisine_want 非空 → raw._subtype_diversified=True (refine.py gate 工作)."""
    refine_mod, root, today = fake_refine_env
    # 命中 cuisine_want=["湘菜"]: refine_intent parser 内置湖南菜识别
    raw = _run_refine(refine_mod, root,
                       user_input="想吃湘菜, 肉多一点", today=today)
    assert raw["_subtype_diversified"] is True


def test_subtype_diversified_false_when_cuisine_want_empty(fake_refine_env):
    """cuisine_want 空 → raw._subtype_diversified=False, baseline 行为不变."""
    refine_mod, root, today = fake_refine_env
    # 用户 input 不含 cuisine 词, parse_refine_intent 出空 cuisine_want
    raw = _run_refine(refine_mod, root, user_input="少油", today=today)
    assert raw["_subtype_diversified"] is False


def test_unknown_relation_does_not_emit_reference_resolved(fake_refine_env):
    """raw_text 既无关系词又无时间词 → parse 返 None, _reference_resolved=None."""
    refine_mod, root, today = fake_refine_env
    raw = _run_refine(refine_mod, root, user_input="想吃辣的", today=today)
    assert raw["_reference_resolved"] is None


# ─────────────────────── H2: _build_trace 落 narrative 字段 ────────────────────


def test_build_trace_writes_narrative_into_l3():
    """Codex H2: api._build_trace 必须把 l3_collector.narrative 拷进 l3_trace.narrative."""
    from chisha import api as api_mod
    import datetime as _dt

    # 构造最小调用环境: l3_collector 含 narrative
    l3_collector = {
        "llm_called": True,
        "status": "ok",
        "model": "claude-opus-4-7",
        "narrative": "为什么推这5道-合成测试串",
        "parsed_candidates": None,
        "raw_response": "",
    }
    # 不能跑真 _build_l1_trace, 注入 precomputed 跳过
    l1_trace_precomputed = {
        "summary": {"n_combos": 0}, "hard_filter_events": [],
    }
    trace = api_mod._build_trace(
        session_id="sess-narrative-01",
        started_at=_dt.datetime(2026, 5, 18, 12, 0, 0,
                                  tzinfo=_dt.timezone.utc),
        total_latency_ms=100, ctx_latency_ms=10, recall_latency_ms=20,
        score_latency_ms=20, rerank_latency_ms=30,
        meal_type="lunch", zone="shenzhen-bay",
        today=_dt.date(2026, 5, 18),
        profile={"scoring_weights": {}, "preferences": {},
                  "taste_description": ""},
        rests=[], tagged=[], meal_log=[],
        combos=[], ctx=type("C", (), {"to_llm_dict": lambda self: {}})(),
        daily_mood=None, ranked_raw=[], ranked=[], top_k=[], reranked=[],
        l3_collector=l3_collector, use_llm_rerank=True, root=None,
        l1_trace_precomputed=l1_trace_precomputed,
    )
    assert trace["l3"]["narrative"] == "为什么推这5道-合成测试串"

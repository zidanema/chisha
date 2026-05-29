"""D-104 Step1b: slim core (extras 缺席) 最小功能 trace 回归.

证明: agent _publish_trace_best_effort 在 _build_trace 调用期 ImportError (extras
缺席) 时退到 _build_minimal_trace, 写出的 trace 仍能被 reference_resolver 发现并提供
final[].restaurant.id (similar_but_different_venue) → reference refine 功能零损失 (§1.3)。
"""
import datetime as dt
from pathlib import Path

from chisha import agent_cli, trace_store
from chisha.core_api_helpers import _format_final_minimal
from chisha.reference_resolver import (
    ReferenceQuery,
    apply_relation,
    resolve_reference,
)


def _reranked_combo(rid: str, name: str, oil: int = 3, cuisine: str = "潮汕") -> dict:
    """raw reranked combo (dishes 仍带 cuisine, 模拟传给 _publish 的 mapped 入参)."""
    return {
        "restaurant": {"id": rid, "name": name,
                       "distance_m": 500, "delivery_eta_min": 20},
        "dishes": [{
            "dish_id": f"d_{rid}", "canonical_name": name, "price": 30,
            "cuisine": cuisine,
            "nutrition_profile": {"oil_level": oil, "main_ingredient_type": "红肉"},
        }],
        "score": 1.5, "combo_index": 0,
    }


def test_format_final_minimal_strips_cuisine():
    """parity (Codex blocker): _format_final_minimal 刻意不带 dish cuisine,
    与 debug_recommend._format_final_candidate 同口径, 不能让 slim 下 similar 关系
    从'恒 no-op'变成按 cuisine 生效。dish 用 'name' 让 top1_summary 不退化。"""
    out = _format_final_minimal(1, _reranked_combo("r1", "卤鹅饭", cuisine="潮汕"))
    assert out["restaurant"]["id"] == "r1"
    assert out["dishes"][0]["name"] == "卤鹅饭"
    assert "cuisine" not in out["dishes"][0]


def test_minimal_trace_is_reference_discoverable(tmp_path: Path):
    """_build_minimal_trace → write_trace → list_traces → resolve_reference 全链路:
    base_combos 带 restaurant.id, similar_but_different_venue 可用。"""
    sid = "20260518_lunch_minimaltest01"
    started = dt.datetime(2026, 5, 18, 12, 0, 0, tzinfo=dt.timezone.utc)
    trace = agent_cli._build_minimal_trace(
        session_id=sid, started_at=started, meal_type="lunch", zone="shenzhen-bay",
        reranked=[_reranked_combo("r1", "卤鹅饭"), _reranked_combo("r2", "湘菜煲")],
    )
    trace_store.write_trace(sid, trace, root=tmp_path)

    items, _ = trace_store.list_traces(root=tmp_path, limit=10)
    assert any(it["session_id"] == sid and it["meal_type"] == "lunch"
               for it in items), "minimal trace 未被 list_traces 索引"

    q = ReferenceQuery(raw_text="和上次那家差不多但换一家",
                       relation="similar_but_different_venue",
                       days_back=-2, meal_hint="lunch")
    resolved = resolve_reference(q, today=dt.date(2026, 5, 19), root=tmp_path)
    assert resolved is not None
    assert resolved.base_session_id == sid
    assert {bc["restaurant"]["id"] for bc in resolved.base_combos} == {"r1", "r2"}

    # apply_relation: base 店 (r1) 排末, 非 base 店 (r3) 优先
    cands = [_reranked_combo("r1", "x"), _reranked_combo("r3", "y")]
    ranked = apply_relation(cands, resolved)
    assert ranked[0]["restaurant"]["id"] == "r3"


def test_minimal_trace_similar_relation_stays_noop(tmp_path: Path):
    """parity (Codex nit): minimal trace 的 final dish 无 cuisine → reference 的
    `similar` 关系软重排恒 no-op (与 full 安装一致, 不引入新行为)。"""
    sid = "20260518_lunch_similarnoop01"
    started = dt.datetime(2026, 5, 18, 12, 0, 0, tzinfo=dt.timezone.utc)
    trace = agent_cli._build_minimal_trace(
        session_id=sid, started_at=started, meal_type="lunch", zone="shenzhen-bay",
        reranked=[_reranked_combo("r1", "卤鹅饭", cuisine="潮汕")],
    )
    trace_store.write_trace(sid, trace, root=tmp_path)
    q = ReferenceQuery(raw_text="和上次那家差不多", relation="similar",
                       days_back=-2, meal_hint="lunch")
    resolved = resolve_reference(q, today=dt.date(2026, 5, 19), root=tmp_path)
    assert resolved is not None
    # base_combos 无 cuisine → base_cuisines 空集 → apply_relation 原样返 (no-op)
    cands = [_reranked_combo("r9", "a", cuisine="川菜"),
             _reranked_combo("r8", "b", cuisine="潮汕")]
    assert apply_relation(cands, resolved) == cands


def test_publish_trace_falls_back_to_minimal_on_importerror(tmp_path, monkeypatch):
    """_build_trace 调用期 ImportError (extras 缺席) → _publish_trace_best_effort
    退到最小 trace 并写盘 (其余字段不依赖 extras)。"""
    import chisha.agent_orchestration as ao
    import chisha.api as api_mod

    def _boom(**kw):
        raise ImportError("simulated extras-absent: chisha.debug_recommend")
    monkeypatch.setattr(api_mod, "_build_trace", _boom)
    monkeypatch.setattr(agent_cli, "_load_inputs",
                        lambda mt, root: ({"basics": {}}, "shenzhen-bay", [], [], []))
    monkeypatch.setattr(agent_cli, "_intent_from_dict", lambda d: None)

    class _Prep:
        combos: list = []
        ctx = None
        ranked_raw: list = []
        ranked: list = []
    monkeypatch.setattr(ao, "prepare_candidates", lambda **kw: _Prep())

    captured: dict = {}
    real_write = trace_store.write_trace

    def _spy(sid, trace, root=None):
        captured["trace"] = trace
        return real_write(sid, trace, root=root)
    monkeypatch.setattr(trace_store, "write_trace", _spy)

    sid = "20260518_lunch_fallbacktest1"
    agent_cli._publish_trace_best_effort(
        sid=sid, round_id="R1",
        frozen={"meal_type": "lunch", "intent": None,
                "refine_input": None, "fb_signal": None},
        persisted={"latencies": {}, "top_k": [], "feedback_avoided_names": []},
        mapped=[_reranked_combo("r1", "卤鹅饭")],
        today=dt.date(2026, 5, 18), narrative="", used_fallback=False,
        fallback_reason=None, root=tmp_path,
    )
    t = captured.get("trace")
    assert t is not None, "minimal trace 未写盘 — fallback 未触发"
    assert t["l1"] is None
    assert t["__frozen"]["meal_type"] == "lunch"
    assert t["final"][0]["restaurant"]["id"] == "r1"
    assert "cuisine" not in t["final"][0]["dishes"][0]
    assert t["__source"] == "agent_cli"

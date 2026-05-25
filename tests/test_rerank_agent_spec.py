"""T2: D-074 AI-friendly rerank spec/apply 单测.

覆盖 build_rerank_spec (信封) + apply_rerank_response (确定性守卫) +
与 in-process _map_validated_candidates 的等价性.
"""
from __future__ import annotations

import pytest

from chisha.agent_protocol import CorrelationId, parse_agent_response
from chisha.rerank import (
    _RERANK_TOOL,
    _map_validated_candidates,
    apply_rerank_response,
    build_rerank_spec,
)
from tests.conftest import make_dish, make_restaurant


def _combo(score: float, rest_id: str) -> dict:
    return {
        "dishes": [make_dish(dish_id=f"{rest_id}_d", main_ingredient_type="纯素",
                             vegetable_ratio_estimate=0.95,
                             protein_grams_estimate=30)],
        "restaurant": make_restaurant(rid=rest_id, name=f"店{rest_id}"),
        "score": score,
    }


@pytest.fixture
def top_combos():
    # 不同 brand (默认 make_restaurant brand=None → rid 作 brand key) 防 brand_unique 误删
    return [_combo(3.0 - i * 0.1, f"r{i}") for i in range(10)]


@pytest.fixture
def profile_v2():
    return {
        "basics": {"office_zone": "test"},
        "taste_description": "清爽不油",
        "preferences": {"liked_cuisines": [], "disliked_cuisines": [],
                        "avoid_dishes": [], "spicy_tolerance": 2},
    }


def _valid_payload(n=5, n_explore=2):
    cands = []
    for i in range(n):
        cands.append({
            "rank": i + 1,
            "is_explore": i >= (n - n_explore),
            "combo_index": i,
            "fit_score": 0.8,
            "taste_match": 0.7,
            "risk_flags": [],
            "one_line_reason": f"理由{i}",
        })
    return {"candidates": cands, "narrative": "今天给你清爽低油"}


# ─────────────────────── build_rerank_spec ───────────────────────

def test_build_spec_tool_use(top_combos, profile_v2):
    cid = CorrelationId("sid_x", "R1", "rerank")
    spec = build_rerank_spec(top_combos, profile_v2, None, n=5, n_explore=2,
                             correlation_id=cid, output_mode="tool_use")
    assert spec["operation_kind"] == "rerank"
    assert spec["output_mode"] == "tool_use"
    assert spec["tools"] == [_RERANK_TOOL]
    assert spec["tool_choice"]["name"] == "select_top_candidates"
    assert spec["correlation_id"] == "sid_x::R1::rerank"
    # user message 含候选块
    assert spec["messages"][0]["role"] == "user"
    assert "[CANDIDATES]" in spec["messages"][0]["content"]
    assert spec["fallback_policy"] == "chisha_l2"
    assert any("brand" in r for r in spec["required_validation"])


def test_build_spec_text_json_patches_system(top_combos, profile_v2):
    cid = CorrelationId("sid_x", "R1", "rerank")
    spec = build_rerank_spec(top_combos, profile_v2, None, n=5, n_explore=2,
                             correlation_id=cid, output_mode="text_json")
    assert spec["output_mode"] == "text_json"
    assert "tools" not in spec
    assert "json_schema" in spec
    # CLI patch: system prompt 含 "claude_code_cli no-tool 路径" 段
    assert "no-tool" in spec["system"]


# ─────────────────────── apply_rerank_response ───────────────────────

def test_apply_valid_response(top_combos):
    mapped, meta = apply_rerank_response(_valid_payload(), top_combos,
                                          n=5, n_explore=2)
    assert meta["status"] == "ok"
    assert meta["narrative"] == "今天给你清爽低油"
    assert mapped is not None and len(mapped) == 5
    # health_flags 由 chisha 补 (agent 没传)
    assert all("health_flags" in c for c in mapped)
    assert [c["rank"] for c in mapped] == [1, 2, 3, 4, 5]


def test_apply_equivalent_to_in_process_mapping(top_combos):
    """apply_rerank_response 成功路径与 in-process _map_validated_candidates 等价."""
    payload = _valid_payload()
    mapped_cli, _ = apply_rerank_response(payload, top_combos, n=5, n_explore=2)
    # in-process 路径: 校验后的 cands 直接进 _map_validated_candidates
    import copy
    validated = copy.deepcopy(payload["candidates"])
    mapped_inproc = _map_validated_candidates(validated, top_combos, n=5)
    # 同样的 restaurant + dishes 选择 + rank
    assert [(c["restaurant"]["id"], c["rank"]) for c in mapped_cli] == \
           [(c["restaurant"]["id"], c["rank"]) for c in mapped_inproc]


def test_apply_no_candidates_list_falls_back(top_combos):
    mapped, meta = apply_rerank_response({"narrative": "x"}, top_combos,
                                          n=5, n_explore=2)
    assert mapped is None
    assert meta["status"] == "fallback"
    assert meta["code"] == "NO_CANDIDATES_LIST"
    assert meta["narrative"] == "x"


def test_apply_invalid_candidates_falls_back(top_combos):
    """combo_index 越界 → 校验失败 → fallback (确定性守卫拦住 agent 乱给)."""
    bad = _valid_payload()
    bad["candidates"][0]["combo_index"] = 999
    mapped, meta = apply_rerank_response(bad, top_combos, n=5, n_explore=2)
    assert mapped is None
    assert meta["status"] == "fallback"
    assert meta["code"] != "OK"


def test_apply_explore_count_mismatch_falls_back(top_combos):
    bad = _valid_payload(n=5, n_explore=2)
    # 把所有 is_explore 改 False → explore 数量 0 != 期望 2
    for c in bad["candidates"]:
        c["is_explore"] = False
    mapped, meta = apply_rerank_response(bad, top_combos, n=5, n_explore=2)
    assert mapped is None
    assert meta["code"] == "EXPLORE_COUNT_MISMATCH"


def test_apply_refine_zero_explore(top_combos):
    """refine 模式 n_explore=0: 全 exploit."""
    payload = _valid_payload(n=5, n_explore=0)
    mapped, meta = apply_rerank_response(payload, top_combos, n=5, n_explore=0)
    assert meta["status"] == "ok"
    assert all(not c["is_explore"] for c in mapped)


def test_apply_via_parse_agent_response(top_combos):
    """端到端: agent 回传信封 → parse_agent_response → apply_rerank_response."""
    cid = CorrelationId("sid_x", "R1", "rerank")
    raw = {"correlation_id": cid.encode(), "payload": _valid_payload(),
           "disclosure": {"status": "ok"}}
    resp = parse_agent_response(raw, expected=cid)
    mapped, meta = apply_rerank_response(resp.payload, top_combos,
                                          n=5, n_explore=2)
    assert meta["status"] == "ok"
    assert len(mapped) == 5

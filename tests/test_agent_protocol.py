"""T1: agent_protocol 协议地基单测 (D-074 Phase 0)."""
from __future__ import annotations

import pytest

from chisha.agent_protocol import (
    CANDIDATE_SCHEMA_VERSION,
    PROTOCOL_VERSION,
    AgentResponse,
    CorrelationId,
    build_request_spec,
    parse_agent_response,
)


# ─────────────────────────── CorrelationId ───────────────────────────

def test_correlation_roundtrip():
    cid = CorrelationId("20260525_lunch_abc123", "R1", "extract")
    assert CorrelationId.decode(cid.encode()) == cid


def test_correlation_invalid_operation():
    with pytest.raises(ValueError):
        CorrelationId("sid", "R1", "bogus")  # type: ignore[arg-type]


def test_correlation_rejects_separator_in_component():
    with pytest.raises(ValueError):
        CorrelationId("sid::evil", "R1", "rerank")


def test_correlation_rejects_path_traversal():
    with pytest.raises(ValueError):
        CorrelationId("../etc", "R1", "rerank")


def test_decode_malformed():
    with pytest.raises(ValueError):
        CorrelationId.decode("only_two::parts")


# ─────────────────────────── build_request_spec ───────────────────────────

def test_build_rerank_spec_envelope():
    cid = CorrelationId("sid_x", "R1", "rerank")
    tool = {"name": "select_top_candidates", "input_schema": {"type": "object"}}
    spec = build_request_spec(
        operation_kind="rerank",
        correlation_id=cid,
        output_mode="tool_use",
        system="SYS",
        messages=[{"role": "user", "content": "U"}],
        tools=[tool],
        tool_choice={"type": "tool", "name": "select_top_candidates"},
        required_validation=["rank 连续", "combo_index 不越界"],
    )
    assert spec["protocol_version"] == PROTOCOL_VERSION
    assert spec["candidate_schema_version"] == CANDIDATE_SCHEMA_VERSION
    assert spec["operation_kind"] == "rerank"
    assert spec["correlation_id"] == "sid_x::R1::rerank"
    assert spec["output_mode"] == "tool_use"
    assert spec["tools"] == [tool]
    assert spec["tool_choice"]["name"] == "select_top_candidates"
    assert spec["fallback_policy"] == "chisha_l2"
    assert "json_schema" not in spec


def test_build_extract_spec_envelope_text_json():
    cid = CorrelationId("sid_x", "R2", "extract")
    schema = {"type": "object", "properties": {"redirect": {"type": "object"}}}
    spec = build_request_spec(
        operation_kind="extract",
        correlation_id=cid,
        output_mode="text_json",
        system="SYS",
        messages=[{"role": "user", "content": "想吃辣"}],
        json_schema=schema,
    )
    assert spec["operation_kind"] == "extract"
    assert spec["output_mode"] == "text_json"
    assert spec["json_schema"] == schema
    assert "tools" not in spec


def test_tool_use_requires_tools():
    cid = CorrelationId("sid_x", "R1", "rerank")
    with pytest.raises(ValueError):
        build_request_spec(
            operation_kind="rerank", correlation_id=cid,
            output_mode="tool_use", system="S", messages=[], tools=None,
        )


def test_text_json_rejects_tools():
    cid = CorrelationId("sid_x", "R1", "extract")
    with pytest.raises(ValueError):
        build_request_spec(
            operation_kind="extract", correlation_id=cid,
            output_mode="text_json", system="S", messages=[],
            tools=[{"name": "x"}],
        )


# ─────────────────────────── parse_agent_response ───────────────────────────

def test_parse_response_ok():
    cid = CorrelationId("sid_x", "R1", "rerank")
    resp = parse_agent_response(
        {
            "correlation_id": cid.encode(),
            "payload": {"candidates": [{"rank": 1}]},
        },
        expected=cid,
    )
    assert isinstance(resp, AgentResponse)
    assert resp.payload["candidates"][0]["rank"] == 1


def test_parse_response_correlation_mismatch():
    cid = CorrelationId("sid_x", "R1", "rerank")
    other = CorrelationId("sid_x", "R2", "rerank")
    with pytest.raises(ValueError, match="correlation_id mismatch"):
        parse_agent_response(
            {"correlation_id": other.encode(), "payload": {}}, expected=cid
        )


def test_parse_response_missing_correlation_rejected():
    """F4 (推翻旧"缺省允许"): correlation_id 必填, 缺 → ValueError (防 stale/串轮)."""
    cid = CorrelationId("sid_x", "R1", "extract")
    with pytest.raises(ValueError, match="缺 correlation_id"):
        parse_agent_response({"payload": {"redirect": {}}}, expected=cid)


def test_parse_response_bad_payload():
    cid = CorrelationId("sid_x", "R1", "extract")
    # F4: correlation 必填且先校验 → 带上正确 correlation 才能触达 payload 校验
    with pytest.raises(ValueError, match="payload must be dict"):
        parse_agent_response(
            {"correlation_id": cid.encode(), "payload": "not a dict"}, expected=cid
        )


def test_parse_response_non_dict():
    cid = CorrelationId("sid_x", "R1", "extract")
    with pytest.raises(ValueError):
        parse_agent_response(["nope"], expected=cid)  # type: ignore[arg-type]

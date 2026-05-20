"""T-PR-05 测试骨架 — 实施时 import 到 tests/test_rerank.py.

由 plans/T-PR-05.plan.md 修订 8 引用. plan 表格列签名 + 关键断言, 本文件给完整可执行骨架.
"""
from chisha.rerank import _RERANK_TOOL, _validate_llm_candidates_v, RerankValidationCode


def test_rerank_tool_description_contains_ordering():
    """修订 1: _RERANK_TOOL.description 含 ordering 关键短语 + refine 模式说明."""
    desc = _RERANK_TOOL["description"]
    assert "Select N candidates" in desc  # 修订 1: 移除硬编码 "3 exploit + 2 explore"
    assert "candidates must be emitted in final display order" in desc
    assert "rank must equal array position + 1" in desc
    assert "exploit segment" in desc
    assert "explore segment" in desc
    assert "no interleaving" in desc
    assert "In refine mode n_explore=0" in desc


def test_rerank_rank_field_description():
    """修订 2: rank field 加 description 含 'strictly ascending' + 'equals array position + 1'."""
    items_props = _RERANK_TOOL["input_schema"]["properties"]["candidates"]["items"]["properties"]
    rank_schema = items_props["rank"]
    assert "description" in rank_schema
    assert "strictly ascending" in rank_schema["description"]
    assert "equals array position + 1" in rank_schema["description"]


def test_rerank_is_explore_field_description():
    """修订 3: is_explore field 加 description 含 'never interleave' + segment 措辞."""
    items_props = _RERANK_TOOL["input_schema"]["properties"]["candidates"]["items"]["properties"]
    is_explore_schema = items_props["is_explore"]
    assert "description" in is_explore_schema
    assert "never interleave" in is_explore_schema["description"]
    assert "exploit segment" in is_explore_schema["description"]
    assert "explore segment" in is_explore_schema["description"]


def test_rerank_validator_rejects_permuted_rank():
    """修订 6: _validate_llm_candidates_v wrapper 拒 ranks=[2,1,3,4,5] (set 完整 position 错)."""
    bad_candidates = [
        {"rank": 2, "is_explore": False, "combo_index": 0, "fit_score": 0.5, "taste_match": 0.5, "risk_flags": [], "one_line_reason": "x"},
        {"rank": 1, "is_explore": False, "combo_index": 1, "fit_score": 0.5, "taste_match": 0.5, "risk_flags": [], "one_line_reason": "x"},
        {"rank": 3, "is_explore": False, "combo_index": 2, "fit_score": 0.5, "taste_match": 0.5, "risk_flags": [], "one_line_reason": "x"},
        {"rank": 4, "is_explore": True, "combo_index": 3, "fit_score": 0.5, "taste_match": 0.5, "risk_flags": [], "one_line_reason": "x"},
        {"rank": 5, "is_explore": True, "combo_index": 4, "fit_score": 0.5, "taste_match": 0.5, "risk_flags": [], "one_line_reason": "x"},
    ]
    validated, code, detail = _validate_llm_candidates_v(
        bad_candidates, n_max=5, input_size=10, n_explore_expected=2,
    )
    assert validated is None
    assert code == RerankValidationCode.RANK_POSITION_MISMATCH
    assert "candidates[0].rank=2" in detail


def test_rerank_openrouter_tool_translation_preserves_descriptions():
    """修订 8 Codex iter 1 BLOCKER 5: _to_openai_tool 转译 _RERANK_TOOL 保留 nested description.

    实施时根据 chisha/llm_providers/openrouter.py 实际函数名调整 import 路径.
    """
    # 实施时确认函数: 可能是 _to_openai_tool / _tool_to_openai / convert_tool 等
    from chisha.llm_providers.openrouter import _to_openai_tool  # 或实际函数路径
    converted = _to_openai_tool(_RERANK_TOOL)
    # OpenAI 格式: {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
    params = converted["function"]["parameters"]
    items_props = params["properties"]["candidates"]["items"]["properties"]
    assert "description" in items_props["rank"], "rank.description dropped by _to_openai_tool"
    assert "description" in items_props["is_explore"], "is_explore.description dropped by _to_openai_tool"
    assert "strictly ascending" in items_props["rank"]["description"]
    assert "never interleave" in items_props["is_explore"]["description"]


def test_rerank_trace_includes_tool_schema_reference(monkeypatch):
    """修订 7: 跑 _run_llm_rerank, trace_collector['system_prompt_full'] 末尾含 tool schema reference.

    mock call_text 让其不真调 API. CLI 路径不应含 reference.
    """
    # mock fixture 模板 (实施时填实际 mock 数据):
    # def fake_call_text(prompt, **kwargs):
    #     return {"type": "tool_use", "tool_name": "select_top_candidates",
    #             "tool_input": {"candidates": [...5 valid candidates...]},
    #             "model": "test", "usage": {}, "stop_reason": "tool_use"}
    # monkeypatch.setattr("chisha.rerank.call_text", fake_call_text)
    #
    # 调 _run_llm_rerank with trace_collector, 验证:
    # assert "[TRACE REFERENCE] outgoing tool schema (T-PR-05)" in trace_collector["system_prompt_full"]
    # assert '"name": "select_top_candidates"' in trace_collector["system_prompt_full"]
    #
    # CLI 路径 (is_cli=True) 不应含 reference:
    # 调 _run_llm_rerank with is_cli=True, 验证 reference 不在 system_prompt_full
    raise NotImplementedError("实施时根据 tests/test_rerank.py 现有 mock pattern 填实, 见上方注释模板")

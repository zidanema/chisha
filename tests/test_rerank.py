"""rerank.py 单测.

LLM 路径需要 ANTHROPIC_API_KEY, 仅测 fallback + 入口 routing.
"""
from __future__ import annotations

import datetime as dt

import pytest

from chisha.context import ContextSnapshot
from chisha.rerank import (
    _REQUIRED_FIELDS,
    build_payload,
    fallback_rerank,
    rerank,
)
from tests.conftest import make_dish, make_restaurant


def _combo(dish_args_list: list[dict], score: float = 1.0,
           rest_id: str = "r1") -> dict:
    dishes = [make_dish(**a) for a in dish_args_list]
    return {
        "dishes": dishes,
        "restaurant": make_restaurant(rid=rest_id, name=f"店{rest_id}"),
        "score": score,
    }


@pytest.fixture
def top_30_combos():
    """30 个递减 score 的 combo."""
    return [_combo([{"dish_id": f"d{i}",
                     "main_ingredient_type": "纯素",
                     "vegetable_ratio_estimate": 0.95,
                     "protein_grams_estimate": 30}],
                    score=3.0 - i * 0.05,
                    rest_id=f"r{i}") for i in range(30)]


@pytest.fixture
def basic_profile_v2():
    return {
        "basics": {"office_zone": "test"},
        "taste_description": "喜欢清爽不油的肉类，特别是带汤水的",
        "preferences": {
            "liked_cuisines": ["潮汕"],
            "disliked_cuisines": [],
            "avoid_dishes": [],
            "spicy_tolerance": 2,
        },
        "plate_rule": {"min_protein_g": 25, "min_vegetable_dishes": 1,
                       "must_have_vegetable": True,
                       "prefer_oil_level_at_most": 3, "hard_max_oil_level": 5},
    }


# ─────────────────────── fallback
def test_fallback_returns_n(top_30_combos):
    out = fallback_rerank(top_30_combos, n=5, n_explore=2)
    assert len(out) == 5


def test_fallback_explore_count(top_30_combos):
    out = fallback_rerank(top_30_combos, n=5, n_explore=2)
    explore = [c for c in out if c["is_explore"]]
    exploit = [c for c in out if not c["is_explore"]]
    assert len(explore) == 2
    assert len(exploit) == 3


def test_fallback_required_fields_complete(top_30_combos):
    out = fallback_rerank(top_30_combos, n=3, n_explore=1)
    for c in out:
        missing = _REQUIRED_FIELDS - set(c)
        assert not missing, f"缺字段: {missing}"


def test_fallback_rank_continuous(top_30_combos):
    out = fallback_rerank(top_30_combos, n=5, n_explore=2)
    assert [c["rank"] for c in out] == [1, 2, 3, 4, 5]


def test_fallback_empty_input():
    assert fallback_rerank([], n=5) == []


def test_fallback_health_flags_correct():
    """健康 flags 从 dish 字段计算正确."""
    combo = _combo([{"main_ingredient_type": "红肉",
                     "vegetable_ratio_estimate": 0.1,
                     "protein_grams_estimate": 30,
                     "oil_level": 2,
                     "wetness": 3,
                     "processed_meat_flag": False}])
    out = fallback_rerank([combo], n=1, n_explore=0)
    flags = out[0]["health_flags"]
    assert flags["protein_ok"] is True
    assert flags["oil_ok"] is True
    assert flags["wetness"] is True
    assert flags["processed_meat"] is False


def test_fallback_processed_meat_detected():
    combo = _combo([{"processed_meat_flag": True,
                     "canonical_name": "蟹柳饭团"}])
    out = fallback_rerank([combo], n=1, n_explore=0)
    assert out[0]["health_flags"]["processed_meat"] is True


def test_fallback_explore_score_lower():
    """explore 的 fit_score 应低于 exploit (打分中段 + 0.8 衰减)."""
    combos = [_combo([{}], score=3.0 - i * 0.1, rest_id=f"r{i}")
              for i in range(10)]
    out = fallback_rerank(combos, n=4, n_explore=2)
    exploit_scores = [c["fit_score"] for c in out if not c["is_explore"]]
    explore_scores = [c["fit_score"] for c in out if c["is_explore"]]
    assert max(explore_scores) < max(exploit_scores)


# ─────────────────────── build_payload
def test_build_payload_includes_v2_fields(top_30_combos, basic_profile_v2):
    payload = build_payload(top_30_combos[:3], basic_profile_v2,
                             context=None, meal_log=[], n=5, n_explore=2)
    assert "candidates" in payload
    cand = payload["candidates"][0]
    dish = cand["dishes"][0]
    # V2 5 字段都在
    for k in ["dish_role", "processed_meat_flag", "sweet_sauce_level",
              "wetness", "grain_type"]:
        assert k in dish, f"V2 字段 {k} 缺失"


def test_build_payload_context_serializable(top_30_combos, basic_profile_v2):
    ctx = ContextSnapshot(
        meal_type="lunch", zone="shenzhen-bay",
        now=dt.datetime(2026, 5, 13), weekday=2,
        last_meal=None, recent_3d_cuisines={}, recent_3d_ingredients={},
        last_feedback=None, daily_mood="want_soup", refine_input=None,
    )
    payload = build_payload(top_30_combos[:2], basic_profile_v2,
                             context=ctx, meal_log=[], n=5, n_explore=2)
    import json
    s = json.dumps(payload, ensure_ascii=False)
    assert "want_soup" in s
    assert "shenzhen-bay" in s


def test_build_payload_no_context(top_30_combos, basic_profile_v2):
    payload = build_payload(top_30_combos[:2], basic_profile_v2,
                             context=None, meal_log=[], n=5, n_explore=2)
    assert payload["context"] is None


# ─────────────────────── rerank 入口
def test_rerank_no_llm_uses_fallback(top_30_combos, basic_profile_v2):
    out = rerank(top_30_combos, basic_profile_v2, context=None,
                  n=5, n_explore=2, use_llm=False)
    assert len(out) == 5
    assert all("rank" in c for c in out)


def test_rerank_refine_zero_explore(top_30_combos, basic_profile_v2):
    out = rerank(top_30_combos, basic_profile_v2, context=None,
                  n=5, n_explore=2, refine=True, use_llm=False)
    explore = [c for c in out if c["is_explore"]]
    assert len(explore) == 0   # refine 时 n_explore 强制 0
    assert len(out) == 5       # exploit 全填


def test_rerank_empty_input(basic_profile_v2):
    assert rerank([], basic_profile_v2, context=None, use_llm=False) == []


def test_rerank_preserves_combo_data(top_30_combos, basic_profile_v2):
    """rerank 输出应仍带原 combo 的 dishes / restaurant."""
    out = rerank(top_30_combos, basic_profile_v2, use_llm=False)
    for c in out:
        assert "dishes" in c
        assert "restaurant" in c


# ─────────────────────── _validate_llm_candidates 校验加深 (P1)
from chisha.rerank import _validate_llm_candidates


def _good_cand(idx=0, rank=1, explore=False):
    """D-046: LLM 不再输出 health_flags, 校验器也跟着删."""
    return {
        "rank": rank, "is_explore": explore, "combo_index": idx,
        "fit_score": 0.85, "taste_match": 0.8, "risk_flags": [],
        "one_line_reason": "ok",
    }


def test_llm_validate_pass():
    cands = [_good_cand(0, 1), _good_cand(1, 2)]
    assert _validate_llm_candidates(cands, n_max=5) == cands


def test_llm_validate_missing_field_rejects():
    bad = _good_cand(0, 1)
    del bad["fit_score"]
    assert _validate_llm_candidates([bad], n_max=5) is None


def test_llm_validate_fit_score_out_of_range():
    bad = _good_cand(0, 1)
    bad["fit_score"] = 1.5
    assert _validate_llm_candidates([bad], n_max=5) is None


def test_llm_validate_duplicate_combo_index():
    a, b = _good_cand(0, 1), _good_cand(0, 2)   # 重复 idx
    assert _validate_llm_candidates([a, b], n_max=5) is None


def test_llm_validate_rank_not_continuous():
    a, b = _good_cand(0, 1), _good_cand(1, 3)   # 跳过 2
    assert _validate_llm_candidates([a, b], n_max=5) is None


def test_llm_validate_taste_match_out_of_range():
    """D-046: taste_match 越界应被拒."""
    bad = _good_cand(0, 1)
    bad["taste_match"] = 2.5
    assert _validate_llm_candidates([bad], n_max=5) is None


def test_llm_validate_taste_match_allows_none():
    """D-046: taste_match=None 仍允许 (兼容 fallback)."""
    c = _good_cand(0, 1)
    c["taste_match"] = None
    assert _validate_llm_candidates([c], n_max=5) is not None


# D-046 二审 (真 Codex review): 补强校验测试

def test_llm_validate_combo_index_upper_bound_reject():
    """idx >= input_size 必须拒绝 (Codex 发现的静默丢弃 bug)."""
    bad = _good_cand(99, 1)  # idx=99 但 input_size=60
    assert _validate_llm_candidates(
        [bad], n_max=5, input_size=60
    ) is None


def test_llm_validate_combo_index_upper_bound_pass():
    """idx 在 input_size 范围内应通过."""
    c = _good_cand(59, 1)
    assert _validate_llm_candidates(
        [c], n_max=5, input_size=60
    ) is not None


def test_llm_validate_combo_index_upper_bound_optional():
    """不传 input_size 时不做上界校验 (向后兼容)."""
    c = _good_cand(999, 1)
    assert _validate_llm_candidates([c], n_max=5) is not None


def test_llm_validate_n_explore_count_mismatch_reject():
    """LLM 漏写 / 多写 explore 数应拒绝."""
    # 期望 n=3, n_explore=1, 但全部都是 exploit
    cands = [_good_cand(i, i + 1, explore=False) for i in range(3)]
    assert _validate_llm_candidates(
        cands, n_max=3, input_size=60, n_explore_expected=1
    ) is None


def test_llm_validate_n_explore_position_mismatch_reject():
    """exploit 必须在前, explore 必须在后."""
    # 期望 3 个 candidate, n_explore=1, 但 explore 放在 rank=1 位置
    cands = [
        _good_cand(0, 1, explore=True),   # 应该 false
        _good_cand(1, 2, explore=False),
        _good_cand(2, 3, explore=False),  # 应该 true
    ]
    assert _validate_llm_candidates(
        cands, n_max=3, input_size=60, n_explore_expected=1
    ) is None


def test_llm_validate_n_explore_correct_pass():
    """exploit 在前, explore 在后, 数量对 → 通过."""
    cands = [
        _good_cand(0, 1, explore=False),
        _good_cand(1, 2, explore=False),
        _good_cand(2, 3, explore=False),
        _good_cand(3, 4, explore=True),
        _good_cand(4, 5, explore=True),
    ]
    out = _validate_llm_candidates(
        cands, n_max=5, input_size=60, n_explore_expected=2
    )
    assert out is not None
    assert len(out) == 5


def test_llm_validate_n_max_truncates():
    cands = [_good_cand(i, i + 1) for i in range(8)]
    out = _validate_llm_candidates(cands, n_max=5)
    # 截断到 5 后, rank 仍应连续 1..5; 我们只取前 5, 它们的 rank 已经是 1..5
    assert out is not None
    assert len(out) == 5


def test_llm_validate_is_explore_must_be_bool():
    bad = _good_cand(0, 1)
    bad["is_explore"] = "yes"
    assert _validate_llm_candidates([bad], n_max=5) is None


# ─────────────────────── D-047 merge: provider routing + tool_use fallback


def test_run_llm_rerank_falls_back_when_provider_call_raises(
    top_30_combos, basic_profile_v2, monkeypatch,
):
    """provider.call 抛任何异常时 _run_llm_rerank 必须捕获并走 fallback,
    不让异常冒到顶层 (D-047 merge MINOR 3 + D-049 CLI 分流后保留兜底)."""
    from unittest.mock import patch

    from chisha.rerank import _run_llm_rerank

    for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "CHISHA_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)

    profile = {**basic_profile_v2, "llm": {"provider": "claude_code_cli"}}

    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=True), \
         patch("chisha.llm_providers.claude_code_cli.call",
                side_effect=RuntimeError("CLI 进程异常")):
        res = _run_llm_rerank(
            top_30_combos, profile, context=None,
            n=5, n_explore=2, n_max=5,
            profile_llm=profile["llm"],
        )

    assert res["status"] == "fallback"
    assert "RuntimeError" in (res["fallback_reason"] or "")


def test_run_llm_rerank_cli_provider_parses_json_text(
    top_30_combos, basic_profile_v2, monkeypatch,
):
    """CLI provider 路径: rerank 不传 tools, 解析 LLM 输出的 JSON 对象
    走 ok (D-049: CLI 不支持 tool_use, 走软约束 + JSON 解析)."""
    import json
    from unittest.mock import patch

    from chisha.rerank import _run_llm_rerank

    for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "CHISHA_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)

    profile = {**basic_profile_v2, "llm": {"provider": "claude_code_cli"}}

    fake_obj = {"candidates": [
        {"rank": 1, "is_explore": False, "combo_index": 0,
         "fit_score": 0.85, "taste_match": 0.7,
         "risk_flags": [], "one_line_reason": "命中清淡偏好"},
        {"rank": 2, "is_explore": False, "combo_index": 5,
         "fit_score": 0.8, "taste_match": 0.65,
         "risk_flags": [], "one_line_reason": "蛋白足"},
        {"rank": 3, "is_explore": False, "combo_index": 10,
         "fit_score": 0.75, "taste_match": 0.6,
         "risk_flags": [], "one_line_reason": "汤水合心情"},
        {"rank": 4, "is_explore": True, "combo_index": 18,
         "fit_score": 0.6, "taste_match": 0.5,
         "risk_flags": [], "one_line_reason": "新菜系试一下"},
        {"rank": 5, "is_explore": True, "combo_index": 22,
         "fit_score": 0.55, "taste_match": 0.4,
         "risk_flags": [], "one_line_reason": "近 3 天没出现"},
    ]}
    fake_resp = {
        "type": "text",
        "content": json.dumps(fake_obj, ensure_ascii=False),
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 200},
        "model": "sonnet",
        "raw_text": json.dumps(fake_obj, ensure_ascii=False),
    }

    captured_kwargs: dict = {}

    def fake_call(prompt, **kwargs):
        captured_kwargs.update(kwargs)
        return fake_resp

    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=True), \
         patch("chisha.llm_providers.claude_code_cli.call",
                side_effect=fake_call):
        res = _run_llm_rerank(
            top_30_combos, profile, context=None,
            n=5, n_explore=2, n_max=5,
            profile_llm=profile["llm"],
        )

    # CLI 路径下 rerank 不应启用 tools/tool_choice (call_text 总转发 keyword,
    # None 表示 rerank 没主动设)
    assert captured_kwargs.get("tools") is None
    assert captured_kwargs.get("tool_choice") is None
    # system_prompt 应被 patch 成 CLI 版本 ("# 输出方式 (claude_code_cli")
    assert "claude_code_cli" in captured_kwargs.get("system", "")
    assert res["status"] == "ok", res
    assert len(res["candidates"]) == 5


def test_run_llm_rerank_cli_provider_fallback_on_garbage_text(
    top_30_combos, basic_profile_v2, monkeypatch,
):
    """CLI provider 输出非 JSON 时, 走 fallback 且 reason 提示解析失败."""
    from unittest.mock import patch

    from chisha.rerank import _run_llm_rerank

    for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "CHISHA_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)

    profile = {**basic_profile_v2, "llm": {"provider": "claude_code_cli"}}

    fake_resp = {
        "type": "text",
        "content": "好的, 我来分析一下用户当前需要... (一大堆 CoT 后没出 JSON)",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "model": "sonnet",
        "raw_text": "好的, 我来分析一下用户当前需要... (一大堆 CoT 后没出 JSON)",
    }

    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=True), \
         patch("chisha.llm_providers.claude_code_cli.call",
                return_value=fake_resp):
        res = _run_llm_rerank(
            top_30_combos, profile, context=None,
            n=5, n_explore=2, n_max=5,
            profile_llm=profile["llm"],
        )

    assert res["status"] == "fallback"
    assert "无法解析" in (res["fallback_reason"] or "")


def test_run_llm_rerank_hard_fails_on_bad_provider_name(
    top_30_combos, basic_profile_v2, monkeypatch,
):
    """D-048 BLOCKER: profile.llm.provider=未知 → status='config_error',
    不再静默 fallback 假装 L3 跑过 (Codex review)."""
    from chisha.rerank import _run_llm_rerank

    for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "CHISHA_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)

    profile = {**basic_profile_v2, "llm": {"provider": "foo_invalid"}}
    res = _run_llm_rerank(
        top_30_combos, profile, context=None,
        n=5, n_explore=2, n_max=5,
        profile_llm=profile["llm"],
    )

    assert res["status"] == "config_error"
    assert res["config_error"] is True
    assert res["resolved_provider"] is None
    assert "未知 profile.llm.provider" in (res["fallback_reason"] or "")
    assert res["candidates"] is None


def test_run_llm_rerank_hard_fails_on_provider_unavailable(
    top_30_combos, basic_profile_v2, monkeypatch,
):
    """D-048 BLOCKER: profile.llm.provider=anthropic 但缺 API key →
    status='config_error', 不静默 fallback."""
    from unittest.mock import patch

    from chisha.rerank import _run_llm_rerank

    for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "CHISHA_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)

    profile = {**basic_profile_v2, "llm": {"provider": "anthropic"}}

    # 同时禁用 .env 里残留 key 的影响
    with patch("chisha.llm_providers.anthropic_api.is_available",
                return_value=False):
        res = _run_llm_rerank(
            top_30_combos, profile, context=None,
            n=5, n_explore=2, n_max=5,
            profile_llm=profile["llm"],
        )

    assert res["status"] == "config_error"
    assert res["config_error"] is True
    assert "不可用" in (res["fallback_reason"] or "")


def test_patch_system_prompt_for_cli_raises_if_section_missing():
    """D-048 MAJOR 3: prompt 改了 '# 输出方式' 标题 (比如改成 '## 输出方式')
    时 _patch_system_prompt_for_cli 必须 ValueError, 不静默放过."""
    import pytest

    from chisha.rerank import _patch_system_prompt_for_cli

    # 把 # 输出方式 改成 ## 输出方式, 模拟未来 prompt 改标题层级
    broken_prompt = (
        "# 重排原则\n\n规则1\n\n"
        "## 输出方式\n\n通过 tool select_top_candidates 输出\n\n"
        "# 边界\n\n现在等待 user 消息, 收到后立刻调 select_top_candidates 返回."
    )
    with pytest.raises(ValueError, match="找不到 '# 输出方式' 段"):
        _patch_system_prompt_for_cli(broken_prompt)


def test_patch_system_prompt_for_cli_raises_if_tail_instruction_missing():
    """D-048 MAJOR 3: prompt 末尾文案改了也要 ValueError."""
    import pytest

    from chisha.rerank import _patch_system_prompt_for_cli

    # 有 # 输出方式 段但没有末尾 "现在等待...select_top_candidates" 那句
    no_tail = (
        "# 输出方式\n\n通过 tool select_top_candidates 输出\n\n"
        "# 边界\n\n候选不足时返回少于 n 条."
    )
    with pytest.raises(ValueError, match="找不到末尾"):
        _patch_system_prompt_for_cli(no_tail)


def test_patch_system_prompt_for_cli_succeeds_on_real_prompt():
    """sanity: 当前 prompts/rerank_system.md 应被成功 patch."""
    from chisha.rerank import SYSTEM_PROMPT_PATH, _patch_system_prompt_for_cli

    raw = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    patched = _patch_system_prompt_for_cli(raw)
    # # 输出方式 段被替换 (原段说"通过 tool 强制结构化输出")
    assert "D-047: 你不直接写 JSON" not in patched
    # CLI 段落被注入
    assert "claude_code_cli no-tool 路径" in patched
    # 末尾指令被替换成 JSON 版本
    assert "立刻输出 JSON 对象" in patched
    # 原末尾的 "立刻调 select_top_candidates 返回" 已替换
    assert "立刻调 select_top_candidates 返回" not in patched


def test_parse_json_object_from_text_handles_fence_and_prefix():
    """_parse_json_object_from_text 多 fallback 路径."""
    from chisha.rerank import _parse_json_object_from_text

    # 直接合法 JSON
    assert _parse_json_object_from_text('{"candidates": []}') == {"candidates": []}
    # ```json fence 包裹
    fenced = '```json\n{"candidates": [{"rank": 1}]}\n```'
    assert _parse_json_object_from_text(fenced) == {"candidates": [{"rank": 1}]}
    # 前后有说明文字
    noisy = '我来给你输出: {"candidates": [{"rank": 1}]} 完成.'
    assert _parse_json_object_from_text(noisy) == {"candidates": [{"rank": 1}]}
    # 完全无 JSON
    assert _parse_json_object_from_text("纯文本没有 json") is None
    assert _parse_json_object_from_text("") is None


def test_parse_json_skips_unrelated_dict_before_candidates():
    """D-048 MAJOR 2: CoT 中先出现无关 dict, 后才出 candidates dict —
    必须跳过无关 dict, 取含 candidates 的那个."""
    from chisha.rerank import _parse_json_object_from_text

    text = (
        '让我分析一下: {"meal_type": "lunch", "mood": "want_light"} 然后输出:\n'
        '{"candidates": [{"rank": 1, "combo_index": 5}]}'
    )
    res = _parse_json_object_from_text(text)
    assert res is not None
    assert "candidates" in res
    assert res["candidates"][0]["combo_index"] == 5


def test_parse_json_handles_truncated_tail():
    """D-048 MAJOR 2: LLM max_tokens 截断, 末尾 JSON 不完整 — 不能 crash,
    要么返回 None 要么返回 fallback dict (调用方再用 'candidates' 字段判断)."""
    from chisha.rerank import _parse_json_object_from_text

    # 整体外层截断, 内嵌 dict 完整 → 可能返回内嵌 dict 作兜底, 但调用方
    # 检查 'candidates' key 时会发现缺失走 fallback_reason
    truncated = '{"candidates": [{"rank": 1, "combo_index": 5}, {"rank": 2,'
    res = _parse_json_object_from_text(truncated)
    # 不 crash 即可; 如果返回 dict 不能有 candidates (那才是 bug)
    assert res is None or "candidates" not in res

    # 完全损坏 (单个 `{` 后立刻乱码) → None
    broken = '{"rank": 1, "garbage:'
    assert _parse_json_object_from_text(broken) is None

    # 前面有完整 dict 后面截断 → 前面那个 dict 作兜底
    partial_ok = (
        '让我先列出 mood: {"mood": "light"} 完整, 然后输出: '
        '{"candidates": [{"rank": 1,'
    )
    res = _parse_json_object_from_text(partial_ok)
    assert res == {"mood": "light"}


def test_parse_json_picks_candidates_over_fallback_dict():
    """D-048 MAJOR 2: 多个 JSON 对象时优先选含 'candidates' key 的, 而不是首个."""
    from chisha.rerank import _parse_json_object_from_text

    text = (
        '{"foo": 1}\n'
        '{"bar": 2}\n'
        '{"candidates": [{"rank": 1}]}\n'
    )
    res = _parse_json_object_from_text(text)
    assert res == {"candidates": [{"rank": 1}]}


def test_parse_json_handles_explainer_after_fence():
    """D-048 MAJOR 2: ```json fence``` 后面有 LLM 加的解释文字时, 仍优先 fence
    内容."""
    from chisha.rerank import _parse_json_object_from_text

    text = (
        '```json\n'
        '{"candidates": [{"rank": 1, "combo_index": 10}]}\n'
        '```\n\n'
        '解释: rank 1 是 want_light 最优选项, ...'
    )
    res = _parse_json_object_from_text(text)
    assert res == {"candidates": [{"rank": 1, "combo_index": 10}]}


def test_run_llm_rerank_picks_per_provider_default_model(
    top_30_combos, basic_profile_v2, monkeypatch,
):
    """没显式 model + profile_llm.model 也没给该 provider 时,
    rerank 应按 _RERANK_MODEL_BY_PROVIDER 选默认 (D-047 merge MAJOR 修复)."""
    from unittest.mock import patch

    from chisha.rerank import _RERANK_MODEL_BY_PROVIDER, _run_llm_rerank

    for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "CHISHA_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")

    profile = {**basic_profile_v2, "llm": {"provider": "anthropic"}}

    captured: dict = {}

    def fake_call(prompt, **kwargs):
        captured.update(kwargs)
        # 返回非 tool_use 让 rerank 走 fallback (不影响本测试关心的 model 透传)
        return {"type": "text", "content": "", "stop_reason": "end_turn",
                "usage": {}, "model": kwargs.get("model"), "raw_text": ""}

    with patch("chisha.llm_providers.anthropic_api.call", side_effect=fake_call):
        _run_llm_rerank(
            top_30_combos, profile, context=None,
            n=5, n_explore=2, n_max=5,
            profile_llm=profile["llm"],
        )

    # provider=anthropic → 应该是短名 "claude-opus-4-7", 不是 OR 命名空间
    assert captured.get("model") == _RERANK_MODEL_BY_PROVIDER["anthropic"]
    assert captured["model"] == "claude-opus-4-7"


def test_run_llm_rerank_respects_profile_model_override(
    top_30_combos, basic_profile_v2, monkeypatch,
):
    """profile.llm.model.<provider> 显式配置时, rerank 应让它生效
    (D-047 merge MAJOR 修复: 不再被 _DEFAULT_RERANK_MODEL 屏蔽)."""
    from unittest.mock import patch

    from chisha.rerank import _run_llm_rerank

    for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "CHISHA_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")

    profile_llm = {
        "provider": "anthropic",
        "model": {"anthropic": "claude-sonnet-4-6"},  # 强制降级 sonnet
    }
    profile = {**basic_profile_v2, "llm": profile_llm}

    captured: dict = {}

    def fake_call(prompt, **kwargs):
        captured.update(kwargs)
        return {"type": "text", "content": "", "stop_reason": "end_turn",
                "usage": {}, "model": kwargs.get("model"), "raw_text": ""}

    with patch("chisha.llm_providers.anthropic_api.call", side_effect=fake_call):
        _run_llm_rerank(
            top_30_combos, profile, context=None,
            n=5, n_explore=2, n_max=5,
            profile_llm=profile_llm,
        )

    # call_text 内部 _resolve_model 透传 profile model → provider 收到 sonnet
    assert captured.get("model") == "claude-sonnet-4-6"


# ────────────────────────── T-P1b-02 narrative 字段


def test_rerank_tool_schema_includes_narrative_field():
    """T-P1b-02: _RERANK_TOOL schema 含 narrative 顶层字段."""
    from chisha.rerank import _RERANK_TOOL
    props = _RERANK_TOOL["input_schema"]["properties"]
    assert "narrative" in props, "tool schema 必须暴露 narrative 顶层字段"
    assert props["narrative"]["type"] == "string"
    assert props["narrative"]["maxLength"] == 100  # ~50 字汉字预算


def test_rerank_tool_schema_narrative_optional():
    """T-P1b-02: narrative 非 required 让旧 LLM 返回向后兼容."""
    from chisha.rerank import _RERANK_TOOL
    required = _RERANK_TOOL["input_schema"]["required"]
    assert "narrative" not in required, \
        "narrative 应为 optional (旧 trace / 旧 LLM 不带 narrative 不应崩)"
    # candidates 仍是 required
    assert "candidates" in required


def test_cli_output_section_mentions_narrative():
    """T-P1b-02: CLI prompt 必须包含 narrative 输出指令 (no-tool 路径需自己写)."""
    from chisha.rerank import _CLI_OUTPUT_SECTION
    assert "narrative" in _CLI_OUTPUT_SECTION
    assert "≤ 50" in _CLI_OUTPUT_SECTION or "50 字" in _CLI_OUTPUT_SECTION

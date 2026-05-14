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


def test_run_llm_rerank_falls_back_when_provider_raises_not_implemented(
    top_30_combos, basic_profile_v2, monkeypatch,
):
    """profile.llm.provider=claude_code_cli + rerank 调 tool_use 时 provider
    抛 NotImplementedError, _run_llm_rerank 必须捕获并走 fallback,
    不让异常冒到顶层 (D-047 merge MINOR 3, Codex review)."""
    from unittest.mock import patch

    from chisha.rerank import _run_llm_rerank

    # 清掉真 key 让 _resolve_provider 不会因为 ANTHROPIC_API_KEY 抢答
    for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "CHISHA_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)

    profile = {**basic_profile_v2, "llm": {"provider": "claude_code_cli"}}

    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=True), \
         patch("chisha.llm_providers.claude_code_cli.call",
                side_effect=NotImplementedError("cc-cli 不支持 tools")):
        res = _run_llm_rerank(
            top_30_combos, profile, context=None,
            n=5, n_explore=2, n_max=5,
            profile_llm=profile["llm"],
        )

    assert res["status"] == "fallback"
    assert "NotImplementedError" in (res["fallback_reason"] or "")


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

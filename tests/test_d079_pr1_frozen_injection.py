"""D-079 PR-1: 冻结注入守门测试.

覆盖 Codex review 的 3 个 BLOCKER/FIX-NOW:
- #1: rank_combos.l1_prefs_override 注入生效, 不读 runtime load_prefs
- #4: rank_combos 接受外部 meal_log_view (本来 today/meal_log 已是参数, 无新签名)
- Q3: rerank._pick_explore 用 frozen today, 不用 dt.date.today()
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import patch

from chisha.rerank import _pick_explore, fallback_rerank
from chisha.score import rank_combos


def test_pick_explore_uses_provided_today_not_wall_clock() -> None:
    """Codex Q3 + FIX-NOW #6: _pick_explore 必须用传入的 today, 不用 dt.date.today().

    行为断言 (非源码 inspection): 通过 already_used 让 used_methods={炒},
    再让 meal_log 一条川菜 entry 在 today_in 的 7d 窗内、today_out 的 7d 窗外.

    case_in: used_cuisines={川菜, X}, used_methods={炒} → 川菜炒 not novel,
             粤菜蒸 novel. n_explore=1 → 选粤菜.
    case_out: used_cuisines={X} only (meal_log 在窗外), used_methods={炒} →
              川菜炒 cuisines-{X}={川菜} truthy → novel. 粤菜蒸 cuisines-{X}={粤菜}
              truthy → novel. mid_pool=[川菜炒, 粤菜蒸], 第一个 novel 是川菜.
    断言: 两 case explore 第一项 cuisine 不同 → today 参数真生效.
    """
    # mid_end = max(n_explore, len(rest) // 2). 要 mid_pool 含两条 combos
    # 让 fallback path 不无脑加川菜, 需要 mid_end ≥ 2 → len(rest) ≥ 4
    rest_combos = [
        {"score": 1.0, "dishes": [{"cuisine": "川菜",
                                     "nutrition_profile": {"cooking_method": "炒"}}]},
        {"score": 0.9, "dishes": [{"cuisine": "粤菜",
                                     "nutrition_profile": {"cooking_method": "蒸"}}]},
        {"score": 0.8, "dishes": [{"cuisine": "湘菜",
                                     "nutrition_profile": {"cooking_method": "焖"}}]},
        {"score": 0.7, "dishes": [{"cuisine": "鲁菜",
                                     "nutrition_profile": {"cooking_method": "烤"}}]},
    ]
    already_used = [
        {"dishes": [{"cuisine": "X",
                      "nutrition_profile": {"cooking_method": "炒"}}]},
    ]
    meal_log = [
        {
            "timestamp": "2026-01-01",
            "dishes": [{"cuisine": "川菜", "main_ingredient_type": "红肉"}],
        }
    ]
    # case_in: today=2026-01-05, cutoff=2025-12-29, log_entry 2026-01-01 ≥ cutoff → 川菜入 used
    result_in = _pick_explore(
        list(rest_combos), list(already_used), meal_log, n_explore=1,
        today=dt.date(2026, 1, 5),
    )
    # case_out: today=2030-01-01, cutoff=2029-12-25, log_entry 2026-01-01 < cutoff → 川菜不入 used
    result_out = _pick_explore(
        list(rest_combos), list(already_used), meal_log, n_explore=1,
        today=dt.date(2030, 1, 1),
    )
    assert len(result_in) >= 1, "case_in 至少返 1 个 explore"
    assert len(result_out) >= 1, "case_out 至少返 1 个 explore"
    cuisine_in = result_in[0]["dishes"][0]["cuisine"]
    cuisine_out = result_out[0]["dishes"][0]["cuisine"]
    assert cuisine_in == "粤菜", f"case_in 应选粤菜 (川菜被冻结视为已吃), 实际 {cuisine_in}"
    assert cuisine_out == "川菜", f"case_out 应选川菜 (顶部 score, 川菜未入 used), 实际 {cuisine_out}"
    # 核心断言: 两 case 结果不同 → today 注入路径生效, 没忽略
    assert cuisine_in != cuisine_out, (
        "今日注入失效: 两个 today 给出同样 cuisine, "
        "证明 _pick_explore 还在用 dt.date.today() (D-079 Codex Q3 回归)"
    )


def test_pick_explore_default_today_is_wall_clock() -> None:
    """向后兼容: 不传 today 时 fallback 到 dt.date.today() — 生产链路 0 行为变化."""
    rest_combos = [
        {"dishes": [{"cuisine": "川菜", "nutrition_profile": {"cooking_method": "炒"}}]},
    ]
    # 不传 today 应正常返回, 不抛
    result = _pick_explore(rest_combos, [], [], n_explore=1)
    assert isinstance(result, list)


def test_fallback_rerank_passes_today_to_pick_explore() -> None:
    """fallback_rerank 必须把 today 透传给 _pick_explore."""
    combos = [
        {
            "score": 1.0, "combo_index": 0,
            "dishes": [{"cuisine": "川菜", "canonical_name": "X",
                         "price": 10, "nutrition_profile": {}}],
            "restaurant": {"id": "r1", "name": "R1"},
        }
        for _ in range(3)
    ]
    # 不应抛
    out = fallback_rerank(combos, n=2, n_explore=1, meal_log=[],
                           today=dt.date(2026, 1, 1))
    assert len(out) == 2


def test_rank_combos_l1_prefs_override_used(tmp_path) -> None:
    """Codex #1: 传 l1_prefs_override=dict 时, 不调 load_prefs(root).

    用 monkeypatch 让 load_prefs 抛错, 验证 override 路径正常工作.
    """
    combos = [{
        "restaurant": {"id": "r1", "name": "R1", "distance_m": 100},
        "dishes": [{
            "dish_id": "d1", "canonical_name": "X", "price": 10,
            "nutrition_profile": {
                "main_ingredient_type": "白肉", "oil_level": 2,
                "vegetable_ratio_estimate": 0.5, "protein_grams_estimate": 20,
                "is_complete_meal": True,
            },
        }],
    }]
    profile = {
        "scoring_weights": {},
        "plate_rule": {"hard_max_oil_level": 4, "prefer_oil_level_at_most": 3},
        "preferences": {},
        "delivery_constraints": {},
        "price_range": {},
        "recall": {},
    }
    with patch("chisha.l1_prefs.load_prefs") as mock_load:
        mock_load.side_effect = RuntimeError("should not be called when override provided")
        # 传 override dict — 不应触发 load_prefs
        ranked = rank_combos(
            combos, profile, meal_log=[], today=dt.date(2026, 5, 16),
            meal_type="lunch", root=tmp_path,
            l1_prefs_override={"l1": {}, "version": 1},
        )
        assert mock_load.call_count == 0
        assert len(ranked) == 1


def test_rank_combos_l1_prefs_override_none_skips_load_prefs(tmp_path) -> None:
    """Codex BLOCKER #4/#8: 显式传 l1_prefs_override=None (= 当时无 prefs)
    必须**不**触发 load_prefs(root). 否则 What-if 静默 fallback 到 live state.
    """
    combos = [{
        "restaurant": {"id": "r1", "name": "R1", "distance_m": 100},
        "dishes": [{
            "dish_id": "d1", "canonical_name": "X", "price": 10,
            "nutrition_profile": {
                "main_ingredient_type": "白肉", "oil_level": 2,
                "vegetable_ratio_estimate": 0.5, "protein_grams_estimate": 20,
                "is_complete_meal": True,
            },
        }],
    }]
    profile = {
        "scoring_weights": {},
        "plate_rule": {"hard_max_oil_level": 4, "prefer_oil_level_at_most": 3},
        "preferences": {},
        "delivery_constraints": {},
        "price_range": {},
        "recall": {},
    }
    with patch("chisha.l1_prefs.load_prefs") as mock_load:
        mock_load.side_effect = RuntimeError("must not be called when override is explicit None")
        ranked = rank_combos(
            combos, profile, meal_log=[], today=dt.date(2026, 5, 16),
            meal_type="lunch", root=tmp_path,
            l1_prefs_override=None,  # 显式 None: 当时无 prefs
        )
        assert mock_load.call_count == 0, (
            "显式 None override 不应触发 load_prefs — D-079 BLOCKER 回归"
        )
        assert len(ranked) == 1


def test_rank_combos_default_calls_load_prefs(tmp_path) -> None:
    """向后兼容: 不传 l1_prefs_override 时正常调 load_prefs."""
    combos = [{
        "restaurant": {"id": "r1", "name": "R1", "distance_m": 100},
        "dishes": [{
            "dish_id": "d1", "canonical_name": "X", "price": 10,
            "nutrition_profile": {
                "main_ingredient_type": "白肉", "oil_level": 2,
                "vegetable_ratio_estimate": 0.5, "protein_grams_estimate": 20,
                "is_complete_meal": True,
            },
        }],
    }]
    profile = {
        "scoring_weights": {},
        "plate_rule": {"hard_max_oil_level": 4, "prefer_oil_level_at_most": 3},
        "preferences": {},
        "delivery_constraints": {},
        "price_range": {},
        "recall": {},
    }
    # 不传 override (默认 None) — load_prefs 应被调用 (即使返回 None/失败也算 called)
    with patch("chisha.l1_prefs.load_prefs", return_value=None) as mock_load:
        ranked = rank_combos(
            combos, profile, meal_log=[], today=dt.date(2026, 5, 16),
            meal_type="lunch", root=tmp_path,
        )
        assert mock_load.call_count == 1
        assert len(ranked) == 1

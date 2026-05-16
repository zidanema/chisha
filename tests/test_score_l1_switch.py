"""D-073 PR-0.7: score.rank_combos 切到 l1_prefs 后的三态等价性守门.

Codex Q3 要求覆盖三种 prefs 状态:
1. 无 prefs 文件 → runtime_hints=None
2. 空 prefs 文件 → runtime_hints=None (与旧 load_runtime_hints "无累计反馈" 等价)
3. 有 prefs 文件 → 按 prefs.boost/penalty 输出 runtime_hints

不验证 score 数值 (那是 baseline_l2_snapshot + compare_traces 守门),
仅验证 rank_combos 的 effective_hints 来源切换正确.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chisha.l1_prefs import save_prefs


@pytest.fixture
def tmp_root(tmp_path: Path):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ─────────────────────── 直接验证 load_prefs → to_runtime_hints 链路 (等价性核心)
def test_state1_no_prefs_file_returns_none(tmp_root: Path):
    """无 prefs 文件 → load_prefs None → to_runtime_hints None."""
    from chisha.l1_prefs import load_prefs, to_runtime_hints
    prefs = load_prefs(root=tmp_root)
    assert prefs is None
    assert to_runtime_hints(prefs) is None


def test_state2_empty_prefs_returns_none(tmp_root: Path):
    """空 prefs (boost+penalty 都空) → load_prefs None (空信号 → None)."""
    from chisha.l1_prefs import load_prefs, to_runtime_hints
    save_prefs({"boost": [], "penalty": []}, root=tmp_root)
    prefs = load_prefs(root=tmp_root)
    assert prefs is None  # 关键: 空 prefs 视为无信号, 与旧 load_runtime_hints 等价
    assert to_runtime_hints(prefs) is None


def test_state3_populated_prefs_returns_hints(tmp_root: Path):
    """有 prefs → load_prefs 返回 dict, to_runtime_hints 返回 {boost, penalty}."""
    from chisha.l1_prefs import load_prefs, to_runtime_hints
    save_prefs(
        {"boost": ["low_oil"], "penalty": ["sweet_sauce"],
         "based_on_meals": 5, "extracted_at": "2026-05-16T00:00:00"},
        root=tmp_root,
    )
    prefs = load_prefs(root=tmp_root)
    assert prefs is not None
    hints = to_runtime_hints(prefs)
    assert hints == {"boost": ["low_oil"], "penalty": ["sweet_sauce"]}


# ─────────────────────── rank_combos 实际跑一遍 3 态 (端到端守门)
def _mk_combo(rid: str, name: str, oil_level: int = 2,
              main_ingr: str = "白肉") -> dict:
    """最小可打分 combo (mock)."""
    return {
        "restaurant": {"id": rid, "name": name, "brand": name, "cuisine": "C"},
        "dishes": [{
            "dish_id": f"{rid}_d1",
            "canonical_name": "dish1",
            "name": "dish1",
            "nutrition_profile": {
                "oil_level": oil_level,
                "main_ingredient_type": main_ingr,
                "spicy_level": 0,
                "wetness": 1,
                "sweet_sauce_level": 0,
                "vegetable_ratio_estimate": 0.5,
                "dish_role": "main",
                "processed_meat_level": 0,
                "carb_quality": "white",
            },
            "delivery_meta": {"eta_min": 30, "distance_m": 500, "price_cny": 30},
        }],
        "scenario_meal_types": ["lunch"],
        "_popularity_rank": 1,
    }


def _real_profile() -> dict:
    """复用真实 profile.yaml + methodology spec (避免 minimal profile schema 漂移)."""
    from chisha.recall import load_profile
    return load_profile(Path(__file__).resolve().parent.parent / "profile.yaml")


def test_rank_combos_no_prefs_runs_clean(tmp_root: Path):
    """无 prefs → rank_combos 正常跑, runtime_hints=None."""
    import datetime as dt
    from chisha.score import rank_combos
    combos = [_mk_combo("r1", "店1")]
    profile = _real_profile()
    ranked = rank_combos(
        combos, profile, meal_log=[], today=dt.date(2026, 5, 15),
        meal_type="lunch", root=tmp_root,
    )
    assert len(ranked) == 1
    assert "score" in ranked[0]


def test_rank_combos_with_prefs_runs_clean(tmp_root: Path):
    """有 prefs → rank_combos 正常吸收 hints (不抛错)."""
    import datetime as dt
    from chisha.score import rank_combos
    save_prefs(
        {"boost": ["low_oil"], "penalty": [],
         "based_on_meals": 5, "extracted_at": "2026-05-16T00:00:00"},
        root=tmp_root,
    )
    combos = [_mk_combo("r1", "店1", oil_level=1)]  # oil_level=1 命中 low_oil
    profile = _real_profile()
    ranked = rank_combos(
        combos, profile, meal_log=[], today=dt.date(2026, 5, 15),
        meal_type="lunch", root=tmp_root,
    )
    assert len(ranked) == 1
    # taste_match_bonus 命中 low_oil (oil_level=1<=2 触发) → +0.5 原始
    breakdown = ranked[0].get("score_breakdown", {})
    assert breakdown.get("taste_match", 0) > 0


def test_rank_combos_corrupt_prefs_falls_back(tmp_root: Path):
    """损坏 prefs → 自动 backup + 视为无 prefs, rank_combos 不挂."""
    import datetime as dt
    from chisha.l1_prefs import _prefs_path
    from chisha.score import rank_combos
    p = _prefs_path(tmp_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ corrupt", encoding="utf-8")

    combos = [_mk_combo("r1", "店1")]
    profile = _real_profile()
    ranked = rank_combos(
        combos, profile, meal_log=[], today=dt.date(2026, 5, 15),
        meal_type="lunch", root=tmp_root,
    )
    assert len(ranked) == 1  # 不挂
    # backup 应该已生成
    backups = list(p.parent.glob("long_term_prefs.json.corrupt.*.bak"))
    assert len(backups) == 1

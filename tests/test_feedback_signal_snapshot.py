"""B-001 / D-098 (T-FB-07): feedback_recency penalty 量纲标定守门测试.

mirror test_l2_refine_snapshot_d090: 用真实 zone 数据跑 rank_combos, 断言短链路
反馈真生效 (方向 + 量纲):
  - mild_neg 差评店的所有 combo 被压出 top5 (top5 cutoff margin 法标定 weight=1.5)
  - boost 好评店 (cooldown 后) 排名上升 (弱 boost, 方向正确)
  - 无反馈 → feedback_recency 全 0 (gating 0-diff, 与 baseline_l2_snapshot 守门一致)

CONTRACTS: 改 score.V2_DEFAULT_WEIGHTS["feedback_recency"] 或 feedback_signal
基础权重时若 break 本测试, 必须 D-098.x 修订并更新断言 + 重跑 baseline_l2_snapshot.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from chisha.recall import load_meal_log, load_profile, load_zone_data, recall
from chisha.score import apply_caps, rank_combos

ROOT = Path(__file__).resolve().parents[1]
ZONE = "shenzhen-bay"
TODAY = dt.date(2026, 5, 15)


def _load():
    try:
        profile = load_profile(ROOT / "profile.yaml")
        rests, tagged = load_zone_data(ZONE, ROOT)
    except (FileNotFoundError, OSError, KeyError):
        pytest.skip(f"zone data {ZONE} 不可用, 跳过 snapshot 标定测试")
    meal_log = load_meal_log(ROOT)
    combos = recall(profile, rests, tagged, meal_log, TODAY, meal_type="lunch")
    if len(combos) < 10:
        pytest.skip("召回候选不足, 跳过")
    return profile, meal_log, combos


def _ranked(combos, profile, meal_log, fb_signal):
    ranked = rank_combos(combos, profile, meal_log, TODAY, meal_type="lunch",
                         feedback_signal_override=fb_signal)
    return apply_caps(ranked, profile)


def test_baseline_no_feedback_zero_diff():
    profile, meal_log, combos = _load()
    capped = _ranked(combos, profile, meal_log, None)
    # 无反馈 → feedback_recency 维全 0 (gating)
    for c in capped:
        assert c["score_breakdown"]["feedback_recency"] == 0.0


def test_mild_neg_pushes_restaurant_out_of_top5():
    profile, meal_log, combos = _load()
    base = _ranked(combos, profile, meal_log, None)
    top1_rid = base[0]["restaurant"]["id"]
    assert top1_rid, "top1 缺 restaurant id"

    # 对 baseline top1 餐厅打 mild_neg (rating=-1, repurchase 中性) → 应压出 top5
    sig = {"restaurant": {top1_rid: -0.6}, "dish": {},
           "recall_evict": {}, "evict_names": {}}
    after = _ranked(combos, profile, meal_log, sig)
    top5_rids = {c["restaurant"]["id"] for c in after[:5]}
    assert top1_rid not in top5_rids, (
        f"mild_neg 未把 {top1_rid} 压出 top5 (weight 标定不足)"
    )


def test_boost_lifts_low_ranked_restaurant():
    profile, meal_log, combos = _load()
    base = _ranked(combos, profile, meal_log, None)
    # 取一个排名靠后 (≈ rank 30) 的餐厅, boost 后应上升
    if len(base) < 30:
        pytest.skip("候选不足 30, 跳过 boost 方向测试")
    target = base[29]
    target_rid = target["restaurant"]["id"]
    base_rank = next(i for i, c in enumerate(base)
                     if c["restaurant"]["id"] == target_rid)

    sig = {"restaurant": {target_rid: 0.3}, "dish": {},
           "recall_evict": {}, "evict_names": {}}
    after = _ranked(combos, profile, meal_log, sig)
    new_rank = next(i for i, c in enumerate(after)
                    if c["restaurant"]["id"] == target_rid)
    assert new_rank < base_rank, (
        f"boost 未提升 {target_rid} 排名 ({base_rank} → {new_rank})"
    )


def test_only_feedback_restaurants_affected():
    # diff 仅落在有反馈的餐厅 — 其它餐厅 feedback_recency 维仍 0 (gating 局部性)
    profile, meal_log, combos = _load()
    base = _ranked(combos, profile, meal_log, None)
    top1_rid = base[0]["restaurant"]["id"]
    sig = {"restaurant": {top1_rid: -0.6}, "dish": {},
           "recall_evict": {}, "evict_names": {}}
    after = _ranked(combos, profile, meal_log, sig)
    for c in after:
        if c["restaurant"]["id"] != top1_rid:
            assert c["score_breakdown"]["feedback_recency"] == 0.0

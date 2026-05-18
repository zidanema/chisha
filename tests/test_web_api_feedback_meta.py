"""D-088 (B4): _attach_feedback_to_meta 派生 TraceMeta.feedback 单测.

覆盖:
- accepted 分支带 restaurant_name (B4 修复)
- accepted_rank 透传
- stopped / rated / 空 store fallback 不破坏既有行为
"""
from __future__ import annotations

from chisha.web_api import _attach_feedback_to_meta


def test_accepted_carries_restaurant_name():
    """B4: accepted 分支必须把 restaurant_name 派生出来."""
    sid = "20260519_dinner_xxx"
    store = {
        "accepted": {
            sid: {
                "accepted_rank": 2,
                "restaurant_name": "肖三胖·老湖南品质土菜（科技园店）",
                "skipped": False,
            },
        },
        "feedbacks": {},
    }
    out = _attach_feedback_to_meta({"session_id": sid}, store)
    assert out == {
        "type": "accepted",
        "rank": 2,
        "restaurant_name": "肖三胖·老湖南品质土菜（科技园店）",
    }


def test_accepted_without_restaurant_name_still_works():
    """没 restaurant_name 时不应崩 (老 feedback_store 兼容)."""
    sid = "old"
    store = {
        "accepted": {sid: {"accepted_rank": 1, "skipped": False}},
        "feedbacks": {},
    }
    out = _attach_feedback_to_meta({"session_id": sid}, store)
    assert out == {"type": "accepted", "rank": 1}
    assert "restaurant_name" not in out


def test_stopped_unaffected():
    sid = "stop"
    store = {"accepted": {sid: {"stopped": True, "skipped": False}}, "feedbacks": {}}
    # accepted=True+stopped 走 accepted 分支, 不走 stopped (现有行为)
    out = _attach_feedback_to_meta({"session_id": sid}, store)
    assert out["type"] == "accepted"


def test_rated_unaffected():
    sid = "rate"
    store = {"accepted": {}, "feedbacks": {sid: {"rating": 3}}}
    out = _attach_feedback_to_meta({"session_id": sid}, store)
    assert out == {"type": "rated", "count": 3}


def test_empty_returns_none():
    out = _attach_feedback_to_meta({"session_id": "x"}, {"accepted": {}, "feedbacks": {}})
    assert out is None

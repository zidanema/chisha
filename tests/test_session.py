"""session.py 单测."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from chisha.session import (
    SessionState,
    cleanup_expired,
    create_session,
    is_expired,
    load_session,
    save_session,
)


def test_create_session_basic():
    s = create_session("sid_001", "lunch", "shenzhen-bay")
    assert s.session_id == "sid_001"
    assert s.meal_type == "lunch"
    assert s.zone == "shenzhen-bay"
    assert s.round == 1
    assert s.last_candidates == []
    assert s.refine_history == []


def test_create_session_with_mood():
    s = create_session("sid_002", "dinner", "home", daily_mood="want_soup")
    assert s.daily_mood == "want_soup"


def test_save_load_roundtrip(tmp_path):
    s = create_session("sid_003", "lunch", "shenzhen-bay",
                        daily_mood="want_light")
    s.last_candidates = [{"rank": 1, "fit_score": 0.9}]
    s.refine_history = ["想喝汤"]
    save_session(s, tmp_path)
    loaded = load_session("sid_003", tmp_path)
    assert loaded is not None
    assert loaded.session_id == "sid_003"
    assert loaded.daily_mood == "want_light"
    assert loaded.last_candidates == [{"rank": 1, "fit_score": 0.9}]
    assert loaded.refine_history == ["想喝汤"]


def test_load_nonexistent_returns_none(tmp_path):
    assert load_session("not_exists", tmp_path) is None


def test_is_expired_fresh():
    s = create_session("sid", "lunch", "z", now=dt.datetime(2026, 5, 13, 12))
    later = dt.datetime(2026, 5, 13, 14)   # 2h 后
    assert is_expired(s, ttl_hours=24, now=later) is False


def test_is_expired_old():
    s = create_session("sid", "lunch", "z", now=dt.datetime(2026, 5, 13, 12))
    later = dt.datetime(2026, 5, 14, 13)   # 25h 后
    assert is_expired(s, ttl_hours=24, now=later) is True


def test_is_expired_invalid_created_at():
    s = SessionState(session_id="x", meal_type="lunch", zone="z",
                      created_at="bad-iso", round=1)
    assert is_expired(s) is True


def test_cleanup_expired(tmp_path):
    fresh = create_session("fresh", "lunch", "z",
                            now=dt.datetime(2026, 5, 13, 12))
    old = create_session("old", "lunch", "z",
                          now=dt.datetime(2026, 5, 10, 12))
    save_session(fresh, tmp_path)
    save_session(old, tmp_path)
    n = cleanup_expired(tmp_path, ttl_hours=24,
                         now=dt.datetime(2026, 5, 13, 13))
    assert n == 1
    # fresh 还在 (显式 now 守门, 与硬编码日期一致, D-074 PR-1a 修)
    assert load_session("fresh", tmp_path,
                         now=dt.datetime(2026, 5, 13, 13)) is not None
    # old 没了
    assert load_session("old", tmp_path,
                         now=dt.datetime(2026, 5, 13, 13)) is None


def test_session_increment_round(tmp_path):
    """模拟 refine 多轮: round 累加, refine_history 增长."""
    s = create_session("sid_x", "lunch", "z")
    s.round += 1
    s.refine_history.append("想喝汤")
    save_session(s, tmp_path)
    loaded = load_session("sid_x", tmp_path)
    assert loaded.round == 2
    assert loaded.refine_history == ["想喝汤"]
    loaded.round += 1
    loaded.refine_history.append("别给我面")
    save_session(loaded, tmp_path)
    loaded2 = load_session("sid_x", tmp_path)
    assert loaded2.round == 3
    assert loaded2.refine_history == ["想喝汤", "别给我面"]


def test_load_session_expired_returns_none(tmp_path):
    """过期 session load 时默认应返回 None (与 refine 文档语义一致)."""
    s = create_session("sid_expired", "lunch", "z",
                        now=dt.datetime(2026, 5, 10, 12))
    save_session(s, tmp_path)
    # 25h 后 load
    later = dt.datetime(2026, 5, 11, 13)
    assert load_session("sid_expired", tmp_path, now=later) is None


def test_load_session_skip_expiry_returns_state(tmp_path):
    """check_expiry=False 时即使过期也返回 state (debug 用)."""
    s = create_session("sid_old", "lunch", "z",
                        now=dt.datetime(2026, 5, 10, 12))
    save_session(s, tmp_path)
    later = dt.datetime(2026, 5, 11, 13)
    state = load_session("sid_old", tmp_path,
                          check_expiry=False, now=later)
    assert state is not None
    assert state.session_id == "sid_old"


def test_load_session_fresh_passes_expiry_check(tmp_path):
    """未过期 session 默认应正常返回."""
    s = create_session("sid_fresh", "lunch", "z",
                        now=dt.datetime(2026, 5, 13, 12))
    save_session(s, tmp_path)
    later = dt.datetime(2026, 5, 13, 14)   # 2h 后
    state = load_session("sid_fresh", tmp_path, now=later)
    assert state is not None

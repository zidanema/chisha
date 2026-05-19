"""S-06b: meal_idx_to_slot + advance_meal coverage."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chisha import sandbox


# ---------- meal_idx_to_slot ----------


def test_meal_idx_to_slot_zero():
    assert sandbox.meal_idx_to_slot(0) == ("lunch", 1)


def test_meal_idx_to_slot_full_day():
    assert sandbox.meal_idx_to_slot(1) == ("dinner", 1)
    assert sandbox.meal_idx_to_slot(2) == ("lunch", 2)
    assert sandbox.meal_idx_to_slot(13) == ("dinner", 7)


def test_meal_idx_to_slot_negative_raises():
    with pytest.raises(ValueError, match="meal_idx must be >= 0"):
        sandbox.meal_idx_to_slot(-1)


# ---------- advance_meal ----------


def _write_state(path: Path, **overrides: object) -> dict:
    """Write a minimal sandbox state.json for tests."""
    s = {
        "enabled": True,
        "current_date": "2026-05-19",
        "day_index": 1,
        "current_meal_idx": 0,
        "total_meals": 14,
    }
    s.update(overrides)  # type: ignore[arg-type]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    return s


def test_advance_meal_lunch_to_dinner(tmp_path: Path):
    state_p = tmp_path / "logs/sandbox/state.json"
    _write_state(state_p, current_meal_idx=0)
    new_s = sandbox.advance_meal(root=tmp_path)
    assert new_s["current_meal_idx"] == 1
    assert new_s["day_index"] == 1  # 同天
    assert new_s["current_date"] == "2026-05-19"
    # 落盘验证
    on_disk = json.loads(state_p.read_text(encoding="utf-8"))
    assert on_disk["current_meal_idx"] == 1


def test_advance_meal_dinner_to_next_day(tmp_path: Path):
    state_p = tmp_path / "logs/sandbox/state.json"
    _write_state(state_p, current_meal_idx=1)  # 当前 dinner, 推进 = 跨天 lunch
    new_s = sandbox.advance_meal(root=tmp_path)
    assert new_s["current_meal_idx"] == 2
    assert new_s["day_index"] == 2
    assert new_s["current_date"] == "2026-05-20"


def test_advance_meal_disabled_raises(tmp_path: Path):
    state_p = tmp_path / "logs/sandbox/state.json"
    _write_state(state_p, enabled=False)
    with pytest.raises(RuntimeError, match="sandbox not enabled"):
        sandbox.advance_meal(root=tmp_path)


def test_advance_meal_state_missing_raises(tmp_path: Path):
    with pytest.raises(RuntimeError, match="sandbox state not found"):
        sandbox.advance_meal(root=tmp_path)


def test_advance_meal_total_done_sentinel(tmp_path: Path):
    """v2 修订 B: total=2 → idx ∈ [0,2]; idx=2 ok (done), idx=3 raise."""
    state_p = tmp_path / "logs/sandbox/state.json"
    _write_state(state_p, current_meal_idx=1, total_meals=2)
    # idx=1 → 2 ok (= total, done sentinel)
    s = sandbox.advance_meal(root=tmp_path)
    assert s["current_meal_idx"] == 2
    # idx=2 → 3 > 2 raise
    with pytest.raises(RuntimeError, match="meal_idx 3 exceeds total 2"):
        sandbox.advance_meal(root=tmp_path)


def test_advance_meal_non_default_sid(tmp_path: Path):
    """v2 修订 A: 非 default sid 写 sessions/{sid}/state.json, 不动 default 桶."""
    # default 桶 state
    default_p = tmp_path / "logs/sandbox/state.json"
    _write_state(default_p, current_meal_idx=5)

    # s1 桶 state (手工 mkdir + write; 本任务不动 create_session)
    s1_p = tmp_path / "logs/sandbox/sessions/s1/state.json"
    _write_state(s1_p, current_meal_idx=0)

    # advance_meal s1 only
    new_s = sandbox.advance_meal(sid="s1", root=tmp_path)
    assert new_s["current_meal_idx"] == 1

    # s1 落盘
    s1_disk = json.loads(s1_p.read_text(encoding="utf-8"))
    assert s1_disk["current_meal_idx"] == 1

    # default 桶不变
    default_disk = json.loads(default_p.read_text(encoding="utf-8"))
    assert default_disk["current_meal_idx"] == 5


def test_advance_meal_corrupt_state_raises(tmp_path: Path):
    state_p = tmp_path / "logs/sandbox/state.json"
    state_p.parent.mkdir(parents=True, exist_ok=True)
    state_p.write_text("{not-valid-json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="sandbox state corrupt"):
        sandbox.advance_meal(root=tmp_path)


def test_advance_meal_default_explicit_sid(tmp_path: Path):
    """sid='_default' 等价于 sid=None, 都走 flat 路径."""
    state_p = tmp_path / "logs/sandbox/state.json"
    _write_state(state_p, current_meal_idx=0)
    new_s = sandbox.advance_meal(sid="_default", root=tmp_path)
    assert new_s["current_meal_idx"] == 1
    assert json.loads(state_p.read_text(encoding="utf-8"))["current_meal_idx"] == 1

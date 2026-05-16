"""D-074 PR-1a: sandbox state + clock 单测.

覆盖:
- sandbox.init / advance / reset / disable
- clock.today/now/now_utc 在 sandbox 启用/关闭时的切换
- 并发 advance 走文件锁 (单线程序列化, 验证 day_index 单调递增)
- 损坏 state.json fail-open
- snooze 24h 在虚拟时钟下行为正确 (sandbox advance 一天 → 解 snooze)
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path

import pytest

from chisha import clock, sandbox


@pytest.fixture
def tmp_root(tmp_path: Path):
    return tmp_path


# ─────────────────────── sandbox state machine
def test_initial_state_disabled(tmp_root: Path):
    s = sandbox.state(root=tmp_root)
    assert s == {"enabled": False}
    assert sandbox.is_enabled(root=tmp_root) is False
    assert sandbox.current_date(root=tmp_root) is None
    assert sandbox.current_datetime(root=tmp_root) is None


def test_init_with_start_date(tmp_root: Path):
    s = sandbox.init(start_date="2026-05-20", root=tmp_root)
    assert s["enabled"] is True
    assert s["current_date"] == "2026-05-20"
    assert s["day_index"] == 1
    assert sandbox.is_enabled(root=tmp_root) is True
    assert sandbox.current_date(root=tmp_root) == dt.date(2026, 5, 20)


def test_init_default_start_date(tmp_root: Path):
    s = sandbox.init(root=tmp_root)
    assert s["current_date"] == dt.date.today().isoformat()


def test_advance_single_day(tmp_root: Path):
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    s = sandbox.advance(days=1, root=tmp_root)
    assert s["current_date"] == "2026-05-21"
    assert s["day_index"] == 2


def test_advance_multiple_days(tmp_root: Path):
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sandbox.advance(days=3, root=tmp_root)
    s = sandbox.state(root=tmp_root)
    assert s["current_date"] == "2026-05-23"
    assert s["day_index"] == 4


def test_advance_requires_init(tmp_root: Path):
    with pytest.raises(RuntimeError, match="not enabled"):
        sandbox.advance(days=1, root=tmp_root)


def test_advance_rejects_zero_days(tmp_root: Path):
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    with pytest.raises(ValueError):
        sandbox.advance(days=0, root=tmp_root)


def test_reset_clears_data(tmp_root: Path):
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sandbox.advance(days=2, root=tmp_root)
    sandbox.reset(root=tmp_root)
    assert sandbox.is_enabled(root=tmp_root) is False
    assert not (tmp_root / "logs" / "sandbox").exists()


def test_disable_preserves_data(tmp_root: Path):
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sandbox.advance(days=2, root=tmp_root)
    sandbox.disable(root=tmp_root)
    assert sandbox.is_enabled(root=tmp_root) is False
    # state 文件保留
    assert (tmp_root / "logs" / "sandbox" / "state.json").exists()


def test_corrupt_state_falls_open(tmp_root: Path):
    p = tmp_root / "logs" / "sandbox" / "state.json"
    p.parent.mkdir(parents=True)
    p.write_text("{ corrupt", encoding="utf-8")
    s = sandbox.state(root=tmp_root)
    assert s == {"enabled": False}


def test_concurrent_advance_serializes(tmp_root: Path):
    """8 个线程同时 advance, 最终 day_index = 1 + 8 = 9 (锁保证)."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    errors = []

    def worker():
        try:
            sandbox.advance(days=1, root=tmp_root)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    s = sandbox.state(root=tmp_root)
    assert s["day_index"] == 9


# ─────────────────────── clock 切换
def test_clock_returns_real_when_sandbox_off(tmp_root: Path):
    assert clock.today(root=tmp_root) == dt.date.today()
    real_now = clock.now(root=tmp_root)
    # 在测试运行的瞬间, 真实时间和 clock.now() 应非常接近
    assert abs((dt.datetime.now() - real_now).total_seconds()) < 1


def test_clock_returns_virtual_when_sandbox_on(tmp_root: Path):
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    assert clock.today(root=tmp_root) == dt.date(2026, 5, 20)
    assert clock.now(root=tmp_root).date() == dt.date(2026, 5, 20)
    assert clock.now_utc(root=tmp_root).date() == dt.date(2026, 5, 20)
    assert clock.now_utc(root=tmp_root).tzinfo == dt.timezone.utc


def test_clock_advance_propagates(tmp_root: Path):
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    assert clock.today(root=tmp_root) == dt.date(2026, 5, 20)
    sandbox.advance(days=3, root=tmp_root)
    assert clock.today(root=tmp_root) == dt.date(2026, 5, 23)


def test_clock_disabled_falls_back(tmp_root: Path):
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sandbox.disable(root=tmp_root)
    assert clock.today(root=tmp_root) == dt.date.today()


# ─────────────────────── record_l1_extraction
def test_record_l1_extraction(tmp_root: Path):
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sandbox.record_l1_extraction("ok", based_on_meals=5, root=tmp_root)
    s = sandbox.state(root=tmp_root)
    assert s["last_l1_extraction"]["status"] == "ok"
    assert s["last_l1_extraction"]["based_on_meals"] == 5


def test_record_l1_extraction_disabled_noop(tmp_root: Path):
    """sandbox 关闭时 record_l1_extraction 不写盘."""
    sandbox.record_l1_extraction("ok", root=tmp_root)
    assert sandbox.is_enabled(root=tmp_root) is False


# ─────────────────────── snooze 在虚拟时钟下行为
def test_snooze_unblocks_after_virtual_day(tmp_root: Path, monkeypatch):
    """sandbox advance 一天后 snooze (24h) 应已过期.

    监管 monkeypatch sandbox._project_root → tmp_root 让 feedback_store
    + sandbox 共用同一 root, 模拟 PR-1b 后的整体行为.
    """
    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_root)

    sandbox.init(start_date="2026-05-20", root=tmp_root)

    from chisha import feedback_store
    # 制造一个 accepted item, 然后 snooze
    data = feedback_store._empty_store()
    data["accepted"]["sid_1"] = {
        "session_id": "sid_1",
        "accepted_rank": 1, "accepted_at": clock.now_utc(root=tmp_root).isoformat(),
        "meal_type": "lunch", "restaurant_name": "店",
        "summary": "", "snoozed_until": None, "stopped": False,
        "skipped": False, "skip_reason": None,
    }
    # set_snooze 用 clock.now_utc, sandbox 启用所以 24h 是虚拟时钟意义上的 24h
    # 模拟 set_snooze 内部逻辑
    until = clock.now_utc(root=tmp_root) + dt.timedelta(hours=24)
    data["accepted"]["sid_1"]["snoozed_until"] = until.isoformat()

    # 检查 snooze 仍生效 (虚拟 today=2026-05-20, until=2026-05-21)
    assert feedback_store._is_snoozed_now(
        data["accepted"]["sid_1"]["snoozed_until"]
    ) is True

    # advance 一天
    sandbox.advance(days=1, root=tmp_root)
    # 现在虚拟 today=2026-05-21, snooze 24h 已过期
    assert feedback_store._is_snoozed_now(
        data["accepted"]["sid_1"]["snoozed_until"]
    ) is False

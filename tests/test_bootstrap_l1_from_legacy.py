"""D-076 PR-0.6: bootstrap_l1_from_legacy 单测."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from chisha.l1_prefs import _prefs_path, load_prefs
from chisha.long_term_prefs import append_feedback
from scripts.bootstrap_l1_from_legacy import bootstrap


@pytest.fixture
def tmp_root(tmp_path: Path):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_bootstrap_empty_legacy_writes_empty_prefs(tmp_root: Path):
    """无旧 jsonl → 空 prefs (boost+penalty 都空, 不调 LLM)."""
    prefs = bootstrap(root=tmp_root, today=dt.date(2026, 5, 16))
    assert prefs["boost"] == []
    assert prefs["penalty"] == []
    assert prefs["based_on_meals"] == 0
    assert prefs["bootstrap_from_legacy"] is True

    # load_prefs 读空 prefs 应返回 None (PR-0.7 等价性保证)
    assert load_prefs(root=tmp_root) is None


def test_bootstrap_with_legacy_complaints_extracts_boost(tmp_root: Path):
    """旧 jsonl 累积 3 次 '太油' (衰减后 ≈ 2.93) → bootstrap 出 low_oil boost.

    注: 衰减后 2 次累积 ≈ 1.98 < min_count=2.0, 必须 ≥ 3 次才过阈值.
    """
    today = dt.date(2026, 5, 16)
    for i in range(3):
        append_feedback(
            chips=["太油"], rating_taste=3,
            timestamp=dt.datetime(2026, 5, 16 - i, 12, 0),
            root=tmp_root,
        )
    prefs = bootstrap(root=tmp_root, today=today)
    assert "low_oil" in prefs["boost"]
    assert prefs["based_on_meals"] == 3
    assert prefs["bootstrap_from_legacy"] is True
    # evidence 标 source=legacy_frequency_aggregate
    assert any(
        e.get("source") == "legacy_frequency_aggregate"
        for e in prefs.get("evidence", [])
    )


def test_bootstrap_skips_when_exists_without_force(tmp_root: Path, capsys):
    today = dt.date(2026, 5, 16)
    # 先 bootstrap 一次
    for i in range(3):
        append_feedback(chips=["太油"], rating_taste=3,
                         timestamp=dt.datetime(2026, 5, 16 - i, 12, 0),
                         root=tmp_root)
    first = bootstrap(root=tmp_root, today=today)
    assert "low_oil" in first["boost"]

    # 再 bootstrap 一次, 应跳过
    second = bootstrap(root=tmp_root, today=today, force=False)
    # 返回旧 prefs (load_prefs 视为 boost=['low_oil'] 非空, 不是 None)
    assert "low_oil" in (second.get("boost") or [])


def test_bootstrap_force_overwrites(tmp_root: Path):
    today = dt.date(2026, 5, 16)
    for i in range(3):
        append_feedback(chips=["太油"], rating_taste=3,
                         timestamp=dt.datetime(2026, 5, 16 - i, 12, 0),
                         root=tmp_root)
    bootstrap(root=tmp_root, today=today)

    # 再追加新数据
    for i in range(3):
        append_feedback(chips=["太甜"], rating_taste=3,
                         timestamp=dt.datetime(2026, 5, 16 - i, 18, 0),
                         root=tmp_root)
    refreshed = bootstrap(root=tmp_root, today=today, force=True)
    # 现在两个 token 都该有
    assert "low_oil" in refreshed["boost"]
    assert "sweet_sauce" in refreshed["penalty"]

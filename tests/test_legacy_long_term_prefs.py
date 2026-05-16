"""D-043 P3: 反馈闭环单测 (DEPRECATED, 标 legacy 保留).

D-076 PR-0.5 状态:
- refine.py 不再调 long_term_prefs.append_feedback (砍错位写入,
  refine chip 是 D-070 L2 单次 session 信号, 不该跨 session 累加).
- long_term_prefs.{append_feedback, load_runtime_hints, ...} 函数保留为
  deprecated stub, 让 bootstrap_l1_from_legacy 脚本 (PR-0.6) 可读取旧数据.
- 本文件单测保证 deprecated 路径仍 work, 不验证新行为.

新 L1 抽取层单测见: tests/test_l1_extractor.py + tests/test_l1_prefs.py.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from chisha.long_term_prefs import (
    DEFAULT_HALFLIFE_DAYS,
    aggregate_chip_weights,
    append_feedback,
    load_feedback_history,
    load_runtime_hints,
    merge_hints,
)


@pytest.fixture
def tmp_root(tmp_path):
    """临时项目根, 反馈落 tmp_path/data/feedback_history.jsonl."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ─────────────────────── append_feedback
def test_append_feedback_writes_jsonl(tmp_root):
    append_feedback(
        chips=["太油", "想喝汤"],
        rating_taste=3,
        want_again=False,
        meal_type="lunch",
        timestamp=dt.datetime(2026, 5, 13, 12, 0),
        root=tmp_root,
    )
    path = tmp_root / "data" / "feedback_history.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["chips"] == ["太油", "想喝汤"]
    assert entry["rating"] == 3
    assert entry["want_again"] is False


def test_append_feedback_empty_skipped(tmp_root):
    """空反馈不落盘."""
    append_feedback(chips=[], rating_taste=None, want_again=None, root=tmp_root)
    path = tmp_root / "data" / "feedback_history.jsonl"
    assert not path.exists()


def test_append_feedback_appends_multiple(tmp_root):
    for i in range(3):
        append_feedback(
            chips=[f"chip_{i}"],
            timestamp=dt.datetime(2026, 5, 13 - i, 12, 0),
            root=tmp_root,
        )
    path = tmp_root / "data" / "feedback_history.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


# ─────────────────────── load_feedback_history
def test_load_filters_old_entries(tmp_root):
    """超过 max_history_days 的反馈被过滤."""
    append_feedback(chips=["太油"],
                     timestamp=dt.datetime(2025, 1, 1), root=tmp_root)  # 远古
    append_feedback(chips=["想喝汤"],
                     timestamp=dt.datetime(2026, 5, 10), root=tmp_root)  # 近期
    entries = load_feedback_history(
        root=tmp_root, today=dt.date(2026, 5, 13), max_history_days=30
    )
    chips_all = [c for e in entries for c in e["chips"]]
    assert "想喝汤" in chips_all
    assert "太油" not in chips_all  # 1.5 年前已过滤


def test_load_assigns_days_ago(tmp_root):
    append_feedback(chips=["x"],
                     timestamp=dt.datetime(2026, 5, 10), root=tmp_root)
    entries = load_feedback_history(root=tmp_root, today=dt.date(2026, 5, 13))
    assert entries[0]["_days_ago"] == 3


def test_load_no_file_returns_empty(tmp_root):
    entries = load_feedback_history(root=tmp_root)
    assert entries == []


# ─────────────────────── aggregate_chip_weights
def test_aggregate_decay_weighted():
    """两条相同 chip, 越近的权重越高."""
    entries = [
        {"_days_ago": 0, "chips": ["太油"], "rating": None, "want_again": None},
        {"_days_ago": DEFAULT_HALFLIFE_DAYS, "chips": ["太油"],
         "rating": None, "want_again": None},
    ]
    w = aggregate_chip_weights(entries)
    # 0 天 = 1.0, halflife 天 = 0.5, 总和 1.5
    assert abs(w["太油"] - 1.5) < 1e-6


def test_aggregate_rating_modulates():
    """rating=5 加权, rating=1 减权."""
    entries = [
        {"_days_ago": 0, "chips": ["x"], "rating": 5, "want_again": None},
        {"_days_ago": 0, "chips": ["x"], "rating": 1, "want_again": None},
    ]
    w = aggregate_chip_weights(entries)
    # 1.5 (rating=5) + 0.5 (rating=1) = 2.0
    assert abs(w["x"] - 2.0) < 1e-6


def test_aggregate_want_again_modulates():
    entries = [
        {"_days_ago": 0, "chips": ["x"], "rating": None, "want_again": True},
        {"_days_ago": 0, "chips": ["x"], "rating": None, "want_again": False},
    ]
    w = aggregate_chip_weights(entries)
    # 1.15 (want_again=True) + 0.85 (want_again=False) = 2.0
    assert abs(w["x"] - 2.0) < 1e-6


# ─────────────────────── load_runtime_hints
def test_load_runtime_hints_meets_threshold(tmp_root):
    """累积 ≥ min_count 次的 chip 才转 hint. 太油 → BOOST low_oil (不是 penalty)."""
    today = dt.date(2026, 5, 13)
    for i in range(2):
        append_feedback(chips=["太油"], rating_taste=3,
                         timestamp=dt.datetime(2026, 5, 13 - i, 12, 0),
                         root=tmp_root)
    hints = load_runtime_hints(today=today, root=tmp_root, min_count=1.5)
    assert hints is not None
    # "太油"是投诉, 转化为下次推荐 boost low_oil (推清淡的)
    assert "low_oil" in hints["boost"]


def test_load_runtime_hints_below_threshold_returns_none(tmp_root):
    """单次反馈 (weight ≈ 1.0) 不足拉普拉斯平滑底线 2.0."""
    today = dt.date(2026, 5, 13)
    append_feedback(chips=["太油"], rating_taste=3,
                     timestamp=dt.datetime(2026, 5, 13, 12, 0),
                     root=tmp_root)
    hints = load_runtime_hints(today=today, root=tmp_root, min_count=2.0)
    assert hints is None


def test_load_runtime_hints_boost_and_penalty(tmp_root):
    """同时累积 boost 和 penalty 类 chip."""
    today = dt.date(2026, 5, 13)
    for _ in range(3):
        append_feedback(chips=["想喝汤", "太甜"], rating_taste=5,
                         timestamp=dt.datetime(2026, 5, 13, 12, 0),
                         root=tmp_root)
    hints = load_runtime_hints(today=today, root=tmp_root, min_count=2.0)
    assert hints is not None
    assert "wetness" in hints["boost"]
    assert "sweet_sauce" in hints["penalty"]


def test_load_runtime_hints_no_history(tmp_root):
    assert load_runtime_hints(today=dt.date(2026, 5, 13), root=tmp_root) is None


# ─────────────────────── merge_hints
def test_merge_hints_takes_union():
    a = {"boost": ["wetness"], "penalty": ["sweet_sauce"]}
    b = {"boost": ["low_oil"], "penalty": ["processed_meat"]}
    merged = merge_hints(a, b)
    assert merged == {
        "boost": ["low_oil", "wetness"],
        "penalty": ["processed_meat", "sweet_sauce"],
    }


def test_merge_hints_all_none():
    assert merge_hints(None, None) is None


def test_merge_hints_one_none():
    a = {"boost": ["x"], "penalty": []}
    assert merge_hints(None, a) == {"boost": ["x"], "penalty": []}


# ─────────────────────── D-043 Codex 二审: want_again 单次不触发
def test_single_feedback_rating5_want_again_below_threshold():
    """rating=5 + want_again=True 单次 = 1.5 * 1.15 = 1.725 < min_count=2.0,
    单次反馈不能触发 hint, 必须累积才行 (拉普拉斯平滑底线).
    """
    entries = [
        {"_days_ago": 0, "chips": ["想喝汤"], "rating": 5, "want_again": True},
    ]
    w = aggregate_chip_weights(entries)
    assert abs(w["想喝汤"] - (1.5 * 1.15)) < 1e-6  # = 1.725
    assert w["想喝汤"] < 2.0  # 严格小于 min_count


def test_two_feedbacks_rating5_want_again_triggers(tmp_root):
    """两次 rating=5 + want_again=True = 1.725 * 2 = 3.45 > 2.0, 应该触发 hint."""
    today = dt.date(2026, 5, 13)
    for i in range(2):
        append_feedback(
            chips=["想喝汤"], rating_taste=5, want_again=True,
            timestamp=dt.datetime(2026, 5, 13 - i),
            root=tmp_root,
        )
    hints = load_runtime_hints(today=today, root=tmp_root)
    assert hints is not None
    assert "wetness" in hints["boost"]


# ─────────────────────── D-043 Codex 二审: root 闭合 (写 + 读 同一文件)
def test_append_and_load_share_root(tmp_root):
    """同一 root 下写入和读取必须共用 jsonl 文件."""
    today = dt.date(2026, 5, 13)
    for i in range(3):
        append_feedback(
            chips=["太甜"], rating_taste=3,
            timestamp=dt.datetime(2026, 5, 13 - i),
            root=tmp_root,
        )
    # 验证文件落盘 + 内容
    path = tmp_root / "data" / "feedback_history.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    # 用同一 root 读: 必须能拿到 hints
    hints = load_runtime_hints(today=today, root=tmp_root, min_count=2.0)
    assert hints is not None
    assert "sweet_sauce" in hints["penalty"]


def test_default_root_isolated_from_custom_root(tmp_root, tmp_path_factory):
    """自定义 root 写入不应污染默认 root, 反之亦然."""
    other = tmp_path_factory.mktemp("other")
    today = dt.date(2026, 5, 13)
    for i in range(3):
        append_feedback(chips=["太甜"], rating_taste=3,
                         timestamp=dt.datetime(2026, 5, 13 - i), root=tmp_root)
    # 用另一个 root 读, 应该读不到 tmp_root 写的数据
    hints = load_runtime_hints(today=today, root=other)
    assert hints is None

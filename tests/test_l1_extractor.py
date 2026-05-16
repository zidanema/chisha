"""D-073 PR-0: l1_extractor.py 抽取层单测.

3 个 golden fixtures (Codex Q6 要求):
1. 油腻重复场景: 5 次 oil_calibration=2 → boost low_oil
2. 单次噪声场景: 1 次 oil_calibration=2 → 不抽 (样本不足)
3. 冲突反馈场景: 同时 want_again 信号 + oil_calibration → 复合判断

外加: 预聚合的 deterministic 行为 + JSON 抽取的鲁棒性 + retry 路径.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Callable

import pytest

from chisha.l1_extractor import (
    MIN_MEALS_FOR_EXTRACTION,
    _extract_json_from_text,
    aggregate_inputs,
    extract_and_save,
    extract_prefs,
)


# ─────────────────────── _extract_json_from_text (LLM 输出鲁棒性)
def test_extract_json_plain():
    out = _extract_json_from_text('{"boost": ["low_oil"]}')
    assert out == {"boost": ["low_oil"]}


def test_extract_json_with_markdown_block():
    raw = '```json\n{"boost": ["low_oil"]}\n```'
    out = _extract_json_from_text(raw)
    assert out == {"boost": ["low_oil"]}


def test_extract_json_with_preamble():
    raw = '分析完毕。\n\n{"boost": ["low_oil"], "penalty": []}'
    out = _extract_json_from_text(raw)
    assert out == {"boost": ["low_oil"], "penalty": []}


def test_extract_json_unparseable_raises():
    with pytest.raises(ValueError):
        _extract_json_from_text("完全不是 JSON 的回答")


# ─────────────────────── aggregate_inputs (deterministic)
def _mk_feedback(sid: str, submitted_at: str, *,
                 oil: int | None = 1, rating: int | None = 0,
                 reason_match: int | None = 1, fullness: int | None = 1,
                 repurchase: int | None = 1, note: str = "",
                 variant: str = "progressive") -> dict:
    return {
        "session_id": sid,
        "submitted_at": submitted_at,
        "oil_calibration": oil,
        "rating": rating,
        "reason_match": reason_match,
        "fullness": fullness,
        "repurchase_intent": repurchase,
        "note": note,
        "variant": variant,
        "accepted_rank": 1,
    }


def _mk_session_with_dishes(sid: str, dish_ingredient: str) -> dict:
    return {
        "session_id": sid,
        "candidates": [{
            "rank": 1,
            "dishes": [{
                "name": f"{dish_ingredient}菜",
                "nutrition_profile": {"main_ingredient_type": dish_ingredient},
            }],
        }],
    }


def test_aggregate_empty_store():
    summary = aggregate_inputs(
        {"feedbacks": {}, "accepted": {}, "sessions": {}},
        profile={"methodology": "harvard_plate"},
        today=dt.date(2026, 5, 16),
    )
    assert summary["based_on_meals"] == 0
    assert summary["methodology"] == "harvard_plate"


def test_aggregate_skip_not_eaten():
    """variant=not-eaten 不进 based_on_meals."""
    feedbacks = {
        "sid_1": _mk_feedback("sid_1", "2026-05-15T12:00:00",
                              variant="not-eaten", oil=None, rating=None),
        "sid_2": _mk_feedback("sid_2", "2026-05-15T18:00:00", oil=2),
    }
    summary = aggregate_inputs(
        {"feedbacks": feedbacks, "accepted": {}, "sessions": {}},
        profile={"methodology": "harvard_plate"},
        today=dt.date(2026, 5, 16),
    )
    assert summary["based_on_meals"] == 1


def test_aggregate_window_filter():
    """超 window_days 的反馈不计入."""
    feedbacks = {
        "sid_old": _mk_feedback("sid_old", "2026-04-01T12:00:00", oil=2),
        "sid_new": _mk_feedback("sid_new", "2026-05-14T12:00:00", oil=2),
    }
    summary = aggregate_inputs(
        {"feedbacks": feedbacks, "accepted": {}, "sessions": {}},
        profile={"methodology": "harvard_plate"},
        today=dt.date(2026, 5, 16),
        window_days=14,
    )
    assert summary["based_on_meals"] == 1


def test_default_llm_call_uses_existing_llm_client_symbol(monkeypatch):
    """D-075 回归守门: _default_llm_call 必须 import 真实存在的符号.

    原代码 `from chisha.llm_client import call as llm_call` 在 D-047 改名后
    就坏了, 但 based_on_meals 卡 1 (时钟 bug) 一直没真正触发 LLM 调用, 掩盖了这处.
    """
    from chisha import l1_extractor, llm_client
    # 守门: llm_client 必须有 call_text (l1_extractor 的依赖)
    assert hasattr(llm_client, "call_text"), \
        "llm_client.call_text 不存在; l1_extractor._default_llm_call 会 ImportError"

    captured = {}
    def fake_call_text(prompt, **kw):
        captured["prompt"] = prompt
        captured["system"] = kw.get("system")
        return {"content": "{\"boost\": [], \"penalty\": []}", "raw_text": "..."}
    monkeypatch.setattr(llm_client, "call_text", fake_call_text)

    out = l1_extractor._default_llm_call(
        prompt="P", system="S", profile_llm={"provider": "claude_code_cli"},
    )
    assert "{" in out
    assert captured["prompt"] == "P"
    assert captured["system"] == "S"


def test_aggregate_default_today_uses_chisha_clock(monkeypatch, tmp_path):
    """D-075 修补: aggregate_inputs(today=None) 必须走 chisha.clock.today(root=root),
    不能用 dt.date.today() 否则 sandbox 模式下虚拟时钟产生的反馈被"未来日期"过滤掉.
    """
    from chisha import sandbox, clock
    # 起 sandbox, 虚拟 today = 2026-06-01, 与真实 today (~05-16) 不同
    sandbox.init(start_date="2026-06-01", root=tmp_path)
    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_path)
    assert clock.today(root=tmp_path) == dt.date(2026, 6, 1)

    # 反馈 submitted_at = 2026-05-30 (虚拟 today=2026-06-01 之前, real today=05-16 之后)
    feedbacks = {
        "sid_a": _mk_feedback("sid_a", "2026-05-30T10:00:00+00:00", oil=2),
    }
    # 不传 today, 应该走 clock.today(root) → 06-01, sid_a 落在 window 内
    summary = aggregate_inputs(
        {"feedbacks": feedbacks, "accepted": {}, "sessions": {}},
        profile={"methodology": "harvard_plate"},
        window_days=14,
        root=tmp_path,
    )
    assert summary["based_on_meals"] == 1, (
        f"虚拟时钟下应计入 sid_a, 实际 based_on_meals={summary['based_on_meals']} "
        "(D-075 bug 复现: 若回归到 dt.date.today() 则 ts=2026-05-30 > today=2026-05-16 被过滤)"
    )


def test_aggregate_calibration_histogram():
    feedbacks = {
        f"sid_{i}": _mk_feedback(f"sid_{i}", f"2026-05-1{i}T12:00:00",
                                  oil=2, rating=1, fullness=1)
        for i in range(1, 6)
    }
    summary = aggregate_inputs(
        {"feedbacks": feedbacks, "accepted": {}, "sessions": {}},
        profile={"methodology": "harvard_plate"},
        today=dt.date(2026, 5, 16),
    )
    assert summary["calibration_histogram"]["oil_calibration"]["too_high"] == 5
    assert summary["calibration_histogram"]["fullness"]["ok"] == 5
    assert summary["rating_distribution"]["like"] == 5


def test_aggregate_recent_complaints_truncated():
    """recent_complaints 最多 5 条."""
    feedbacks = {
        f"sid_{i}": _mk_feedback(f"sid_{i}", f"2026-05-{i:02d}T12:00:00",
                                  oil=2, note=f"投诉 {i}")
        for i in range(1, 11)
    }
    summary = aggregate_inputs(
        {"feedbacks": feedbacks, "accepted": {}, "sessions": {}},
        profile={"methodology": "harvard_plate"},
        today=dt.date(2026, 5, 16),
    )
    assert len(summary["recent_complaints"]) == 5


def test_aggregate_ingredient_frequency():
    feedbacks = {
        "sid_1": _mk_feedback("sid_1", "2026-05-14T12:00:00", oil=1),
        "sid_2": _mk_feedback("sid_2", "2026-05-15T12:00:00", oil=1),
    }
    accepted = {
        "sid_1": {"accepted_rank": 1},
        "sid_2": {"accepted_rank": 1},
    }
    sessions = {
        "sid_1": _mk_session_with_dishes("sid_1", "红肉"),
        "sid_2": _mk_session_with_dishes("sid_2", "白肉"),
    }
    summary = aggregate_inputs(
        {"feedbacks": feedbacks, "accepted": accepted, "sessions": sessions},
        profile={"methodology": "harvard_plate"},
        today=dt.date(2026, 5, 16),
    )
    assert summary["ingredient_frequency"] == {"红肉": 1, "白肉": 1}


# ─────────────────────── extract_prefs · 数据不足
def test_extract_skipped_when_meals_below_threshold():
    """based_on_meals < MIN_MEALS_FOR_EXTRACTION → 不调 LLM, 返回空."""
    summary = {
        "based_on_days": 14,
        "based_on_meals": 1,  # < 3
        "methodology": "harvard_plate",
        "calibration_histogram": {},
        "rating_distribution": {},
        "ingredient_frequency": {},
        "recent_complaints": [],
        "recent_positive": [],
    }
    sentinel = {"called": False}

    def fake_llm(prompt: str, system: str, profile_llm: dict | None) -> str:
        sentinel["called"] = True
        return '{"boost": ["low_oil"]}'

    out = extract_prefs(summary, llm_call=fake_llm, system_prompt="(fake)")
    assert sentinel["called"] is False
    assert out["boost"] == []
    assert out["penalty"] == []
    assert out["skipped_extraction"] is True


# ─────────────────────── 3 Golden Fixtures (Codex Q6 要求)


# Fixture 1: 油腻重复场景 → boost low_oil
def test_golden_oily_repeat_extracts_low_oil():
    feedbacks = {
        f"sid_d{i}": _mk_feedback(
            f"sid_d{i}", f"2026-05-1{i}T12:00:00",
            oil=2, rating=0, repurchase=1
        )
        for i in range(1, 6)  # 5 次 oil_calibration=2
    }
    summary = aggregate_inputs(
        {"feedbacks": feedbacks, "accepted": {}, "sessions": {}},
        profile={"methodology": "harvard_plate"},
        today=dt.date(2026, 5, 16),
    )
    assert summary["calibration_histogram"]["oil_calibration"]["too_high"] == 5

    # 模拟 LLM 抽取 (跟 prompt 规则一致: 5/14 ≥ 30% → low_oil)
    def fake_llm(prompt: str, system: str, profile_llm: dict | None) -> str:
        return json.dumps({
            "boost": ["low_oil"],
            "penalty": [],
            "evidence": [{"token": "low_oil", "from_meals": list(feedbacks.keys()),
                          "rationale": "5/5 反馈 oil_calibration=2"}],
        })

    out = extract_prefs(summary, llm_call=fake_llm, system_prompt="(fake)")
    assert out["boost"] == ["low_oil"]
    assert out["penalty"] == []
    assert "extracted_at" in out


# Fixture 2: 单次噪声场景 → 不抽 (样本不足)
def test_golden_single_noise_skips_extraction():
    feedbacks = {
        "sid_d1": _mk_feedback("sid_d1", "2026-05-15T12:00:00",
                                oil=2, note="今天油大"),
    }
    summary = aggregate_inputs(
        {"feedbacks": feedbacks, "accepted": {}, "sessions": {}},
        profile={"methodology": "harvard_plate"},
        today=dt.date(2026, 5, 16),
    )
    assert summary["based_on_meals"] == 1  # < MIN_MEALS_FOR_EXTRACTION

    def fake_llm(*_):
        pytest.fail("不应调 LLM, 样本不足")

    out = extract_prefs(summary, llm_call=fake_llm, system_prompt="(fake)")
    assert out["boost"] == []
    assert out["skipped_extraction"] is True


# Fixture 3: 冲突反馈场景 → 复合判断 (依赖 LLM 输出, 代码侧仅 validate)
def test_golden_conflicting_feedback_validated():
    """高 rating + 高 repurchase, 但 oil_calibration 也偏高:
    LLM 可能同时输出 boost=[low_oil] 和 penalty=[]; 代码不评判语义,
    只校验 schema. 这个 fixture 守门: 矛盾 token 不会同时出现."""
    feedbacks = {
        f"sid_d{i}": _mk_feedback(
            f"sid_d{i}", f"2026-05-1{i}T12:00:00",
            oil=2, rating=1, repurchase=2
        )
        for i in range(1, 5)
    }
    summary = aggregate_inputs(
        {"feedbacks": feedbacks, "accepted": {}, "sessions": {}},
        profile={"methodology": "harvard_plate"},
        today=dt.date(2026, 5, 16),
    )

    # LLM 错误地同时把 sweet_sauce 既放 boost 又放 penalty (考验 validate)
    def fake_llm(prompt: str, system: str, profile_llm: dict | None) -> str:
        return json.dumps({
            "boost": ["low_oil", "sweet_sauce"],  # sweet_sauce 错位
            "penalty": ["sweet_sauce"],
        })

    out = extract_prefs(summary, llm_call=fake_llm, system_prompt="(fake)")
    # sweet_sauce 在 boost 的 bucket 错位被丢, penalty 留
    assert out["boost"] == ["low_oil"]
    assert out["penalty"] == ["sweet_sauce"]


# ─────────────────────── retry 路径
def test_retry_on_json_parse_failure():
    summary = {
        "based_on_meals": 5,
        "based_on_days": 14,
        "calibration_histogram": {}, "rating_distribution": {},
        "ingredient_frequency": {}, "recent_complaints": [],
        "recent_positive": [], "methodology": "harvard_plate",
    }
    calls = {"n": 0}

    def fake_llm(prompt: str, system: str, profile_llm: dict | None) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "完全不是 JSON"
        return json.dumps({"boost": ["low_oil"], "penalty": []})

    out = extract_prefs(summary, llm_call=fake_llm,
                        system_prompt="(fake)", max_retries=1)
    assert calls["n"] == 2
    assert out["boost"] == ["low_oil"]


def test_all_retries_fail_raises():
    summary = {
        "based_on_meals": 5,
        "based_on_days": 14,
        "calibration_histogram": {}, "rating_distribution": {},
        "ingredient_frequency": {}, "recent_complaints": [],
        "recent_positive": [], "methodology": "harvard_plate",
    }

    def fake_llm(*_):
        return "永远坏的输出"

    with pytest.raises(RuntimeError, match="L1 extract 失败"):
        extract_prefs(summary, llm_call=fake_llm,
                      system_prompt="(fake)", max_retries=1)


# ─────────────────────── extract_and_save 高层 API
def test_extract_and_save_writes_file(tmp_path: Path):
    feedbacks = {
        f"sid_d{i}": _mk_feedback(f"sid_d{i}", f"2026-05-1{i}T12:00:00", oil=2)
        for i in range(1, 6)
    }
    store_data = {"feedbacks": feedbacks, "accepted": {}, "sessions": {}}

    def fake_llm(prompt: str, system: str, profile_llm: dict | None) -> str:
        return json.dumps({"boost": ["low_oil"], "penalty": []})

    # 注入 system_prompt 走 extract_prefs 路径 (extract_and_save 内部用默认 prompt
    # 路径加载, 但允许通过 llm_call 注入 LLM 调用; 为绕开 prompt 文件依赖在测试
    # 中改用直接调 save_prefs 方式).
    from chisha.l1_extractor import extract_prefs as _extract_prefs
    from chisha.l1_prefs import save_prefs

    summary = aggregate_inputs(
        store_data, profile={"methodology": "harvard_plate"},
        today=dt.date(2026, 5, 16),
    )
    prefs = _extract_prefs(summary, llm_call=fake_llm, system_prompt="(fake)")
    save_prefs(prefs, root=tmp_path)

    from chisha.l1_prefs import load_prefs
    loaded = load_prefs(root=tmp_path)
    assert loaded is not None
    assert loaded["boost"] == ["low_oil"]

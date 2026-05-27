"""D-076 PR-0: l1_prefs.py 数据层单测.

覆盖: load/save 往返, canonicalize, 损坏 backup, 空信号 → None,
enum 不在词表丢弃, boost/penalty 矛盾时 penalty 优先.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chisha.l1_prefs import (
    ALL_TOKENS,
    BOOST_TOKENS,
    PENALTY_TOKENS,
    canonicalize_token,
    load_prefs,
    save_prefs,
    to_runtime_hints,
    validate_prefs,
)


# ─────────────────────── canonicalize_token
def test_canonicalize_alias():
    assert canonicalize_token("soup_or_broth") == "wetness"


def test_canonicalize_canonical_passthrough():
    assert canonicalize_token("low_oil") == "low_oil"
    assert canonicalize_token("wetness") == "wetness"


def test_canonicalize_unknown_returns_none():
    assert canonicalize_token("high_protein") is None
    assert canonicalize_token("") is None


# ─────────────────────── validate_prefs
def test_validate_basic():
    raw = {"boost": ["low_oil"], "penalty": ["sweet_sauce"]}
    out = validate_prefs(raw)
    assert out["boost"] == ["low_oil"]
    assert out["penalty"] == ["sweet_sauce"]
    assert out["version"] == 1


def test_validate_canonicalizes_alias():
    raw = {"boost": ["soup_or_broth"], "penalty": []}
    out = validate_prefs(raw)
    assert out["boost"] == ["wetness"]


def test_validate_drops_unknown_tokens():
    raw = {"boost": ["low_oil", "high_protein", "magic"],
           "penalty": ["spicy", "fake_token"]}
    out = validate_prefs(raw)
    assert out["boost"] == ["low_oil"]
    assert out["penalty"] == ["spicy"]


def test_validate_drops_wrong_bucket():
    """单向 token 放错桶被丢弃. D-076.1 后 spicy / sweet_sauce 是双向, 不再 wrong-
    bucket 候选 — 这里用 low_oil (仅 boost) + processed_meat (仅 penalty) 校验."""
    raw = {"boost": ["processed_meat"], "penalty": ["low_oil"]}
    out = validate_prefs(raw)
    assert out["boost"] == []
    assert out["penalty"] == []


def test_validate_dedup_and_sorts():
    raw = {"boost": ["low_oil", "low_oil", "wetness"],
           "penalty": ["spicy", "sweet_sauce", "spicy"]}
    out = validate_prefs(raw)
    assert out["boost"] == ["low_oil", "wetness"]
    assert out["penalty"] == ["spicy", "sweet_sauce"]


def test_validate_penalty_wins_on_conflict():
    """同 token 同时是 boost 和 penalty 时 penalty 优先 (LLM 不能既要又不要).

    注: low_oil ∈ BOOST_TOKENS 但 ∉ PENALTY_TOKENS, 所以这 case 选 sweet_sauce
    (它真的可以两边都试图加).
    """
    raw = {"boost": ["sweet_sauce"], "penalty": ["sweet_sauce"]}
    out = validate_prefs(raw)
    # sweet_sauce 在 boost 里属于 wrong bucket 丢弃, penalty 留
    assert out["boost"] == []
    assert out["penalty"] == ["sweet_sauce"]


def test_validate_rejects_non_dict():
    with pytest.raises(ValueError):
        validate_prefs("not a dict")  # type: ignore


def test_validate_rejects_non_list_buckets():
    with pytest.raises(ValueError):
        validate_prefs({"boost": "low_oil", "penalty": []})


def test_validate_drops_non_string_items():
    raw = {"boost": [123, None, "low_oil"], "penalty": []}
    out = validate_prefs(raw)
    assert out["boost"] == ["low_oil"]


def test_validate_fills_defaults():
    out = validate_prefs({"boost": [], "penalty": []})
    assert out["signals_not_scored"] == {}
    assert out["evidence"] == []
    assert out["regularities_freetext"] == []


# ─────────────────────── load/save 往返
def test_save_then_load_roundtrip(tmp_path: Path):
    raw = {
        "boost": ["low_oil"],
        "penalty": ["sweet_sauce", "processed_meat"],
        "evidence": [{"token": "low_oil", "rationale": "5 次反馈"}],
        "based_on_meals": 14,
    }
    save_prefs(raw, root=tmp_path)
    loaded = load_prefs(root=tmp_path)
    assert loaded is not None
    assert loaded["boost"] == ["low_oil"]
    assert loaded["penalty"] == ["processed_meat", "sweet_sauce"]
    assert loaded["based_on_meals"] == 14


def test_load_missing_returns_none(tmp_path: Path):
    assert load_prefs(root=tmp_path) is None


def test_load_empty_prefs_returns_none(tmp_path: Path):
    """空 prefs (boost+penalty 都空) → None, 与旧 load_runtime_hints 等价.

    这是 PR-0.7 切 score 等价性的关键保证.
    """
    save_prefs({"boost": [], "penalty": []}, root=tmp_path)
    assert load_prefs(root=tmp_path) is None


def test_load_corrupt_backups_and_returns_none(tmp_path: Path):
    """损坏文件 → 改名 .corrupt.{ts}.bak + 返回 None (派生数据 fail-open)."""
    prefs_path = tmp_path / "long_term_prefs.json"  # D-102 Step2: 迁出 data/
    prefs_path.write_text("{ this is not valid json", encoding="utf-8")
    assert load_prefs(root=tmp_path) is None
    # 验证 backup
    backups = list(prefs_path.parent.glob("long_term_prefs.json.corrupt.*.bak"))
    assert len(backups) == 1


# ─────────────────────── to_runtime_hints (适配 score.py 接口)
def test_to_runtime_hints_basic():
    prefs = {"boost": ["low_oil"], "penalty": ["spicy"]}
    out = to_runtime_hints(prefs)
    assert out == {"boost": ["low_oil"], "penalty": ["spicy"]}


def test_to_runtime_hints_none_passthrough():
    assert to_runtime_hints(None) is None


def test_to_runtime_hints_empty_returns_none():
    """boost+penalty 都空 → None (与 load_prefs 行为一致)."""
    assert to_runtime_hints({"boost": [], "penalty": []}) is None


# ─────────────────────── 词表完整性 (防 D-076 / D-076.1 词表静默漂移)
def test_token_vocabulary_unchanged():
    """词表是 D-076 / D-076.1 边界, 改动必须走独立决策 + baseline_l2_snapshot.

    如果这个测试挂了, 说明有人擅自扩了词表 — 应该回到 v3 §2.7 重新评估.

    D-076.1 (2026-05-16): boost 加 spicy + sweet_sauce 双向, 与对应 penalty 对称.
    不加 processed_meat / carb_heavy boost (违反 harvard_plate methodology baseline).
    """
    assert BOOST_TOKENS == frozenset(
        ["low_oil", "wetness", "spicy", "sweet_sauce"]
    )
    assert PENALTY_TOKENS == frozenset(
        ["sweet_sauce", "processed_meat", "carb_heavy", "spicy"]
    )
    assert ALL_TOKENS == BOOST_TOKENS | PENALTY_TOKENS
    # D-076.1: spicy / sweet_sauce 必须双向支持 (penalty + boost intersection)
    assert {"spicy", "sweet_sauce"} <= (BOOST_TOKENS & PENALTY_TOKENS)
    # processed_meat / carb_heavy 仅 penalty (不在 boost)
    assert {"processed_meat", "carb_heavy"} <= PENALTY_TOKENS
    assert not ({"processed_meat", "carb_heavy"} & BOOST_TOKENS), (
        "harvard_plate baseline 反对加工肉 + 1/4 carb 上限, 不许 boost"
    )

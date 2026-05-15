"""D-072 methodology spec 加载 + 校验 + merge 单测.

Codex Round 2 验收点 (BLOCKER + MAJOR):
  - B-1 严格 keyset 校验: 顶层 6 必备 + plate_rule/score_weights/cap_rules 内部 key
  - B-2 unforgivable_discount 字段路径: spec → profile.scoring.unforgivable_discount
  - M-1 sensible default 非 silent: profile 缺 methodology 字段时 logger.info
  - B-spot-2 merge 不覆盖 profile 已有显式值
  - 缓存正确性: 同 name 两次调用结果一致, 但返回 deep-copy
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from chisha.methodology import (
    DEFAULT_METHODOLOGY,
    METHODOLOGIES_DIRNAME,
    MethodologyValidationError,
    _load_methodology_cached,
    apply_methodology,
    load_methodology,
    merge_into_profile,
    resolve_methodology,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────── load + 校验 ───────────────────────

def test_load_harvard_plate_smoke():
    """实际 spec 必须加载成功."""
    spec = load_methodology("harvard_plate", REPO_ROOT)
    assert spec["name"] == "harvard_plate"
    assert spec["version"] == 1
    assert "rationale" in spec
    assert "plate_rule" in spec
    assert "score_weights" in spec
    assert "cap_rules" in spec


def test_load_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_methodology("does_not_exist", tmp_path)


def _write_spec(tmp_path: Path, name: str, body: dict) -> Path:
    """辅助: 写 spec 文件到临时方法论目录."""
    p = tmp_path / METHODOLOGIES_DIRNAME / f"{name}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump(body, allow_unicode=True), encoding="utf-8")
    return p


def _full_spec(name: str = "valid_test") -> dict:
    """构造一份完整最小合规 spec."""
    return {
        "name": name,
        "display_name": "Test Methodology",
        "version": 1,
        "rationale": "test",
        "plate_rule": {
            "must_have_vegetable": True,
            "min_vegetable_dishes": 1,
            "min_protein_g": 25,
            "prefer_oil_level_at_most": 3,
            "hard_max_oil_level": 4,
        },
        "score_weights": {
            "vegetable_floor_pass": 0.0,
            "protein_floor_pass": 0.0,
            "distance": 0.0,
            "low_oil": 0.5,
            "popularity": 0.4,
            "cuisine_preference": 0.3,
            "variety_bonus": 0.5,
            "carb_quality": 0.6,
            "processed_meat": 1.0,
            "sweet_sauce": 0.7,
            "wetness": 0.5,
            "dish_role_match": 0.3,
            "eta": 0.4,
            "price": 0.5,
            "taste_match": 0.4,
            "context_boost": 0.25,
        },
        "cap_rules": {
            "per_restaurant_top_k": 3,
            "per_brand_top_k": 2,
            "per_cuisine_top_k": 6,
            "per_food_form_top_k": 8,
        },
    }


# ─────────────────────── B-1: 严格 keyset 校验 ───────────────────────

def test_validate_missing_required_top_key(tmp_path: Path):
    """顶层必备字段缺失 → MethodologyValidationError."""
    bad = _full_spec("bad_top")
    del bad["rationale"]
    _write_spec(tmp_path, "bad_top", bad)
    _load_methodology_cached.cache_clear()
    with pytest.raises(MethodologyValidationError, match="missing required top keys"):
        load_methodology("bad_top", tmp_path)


def test_validate_unknown_top_key_typo(tmp_path: Path):
    """顶层未知字段 (拼写错) → MethodologyValidationError."""
    bad = _full_spec("bad_typo")
    bad["rationle"] = "typo"  # rationale 拼成 rationle
    _write_spec(tmp_path, "bad_typo", bad)
    _load_methodology_cached.cache_clear()
    with pytest.raises(MethodologyValidationError, match="unknown top keys"):
        load_methodology("bad_typo", tmp_path)


def test_validate_score_weights_missing_key(tmp_path: Path):
    """score_weights 内部缺一个 key → hard fail (B-1)."""
    bad = _full_spec("bad_weights_missing")
    del bad["score_weights"]["wetness"]
    _write_spec(tmp_path, "bad_weights_missing", bad)
    _load_methodology_cached.cache_clear()
    with pytest.raises(MethodologyValidationError, match="score_weights keyset mismatch"):
        load_methodology("bad_weights_missing", tmp_path)


def test_validate_score_weights_typo_key(tmp_path: Path):
    """score_weights 内部拼写错 (B-1 核心): low_oil 写成 lowoil → hard fail.

    这是 Codex BLOCKER B-1 的核心 case: 拼写错绝不能 silently 落 V2_DEFAULT_WEIGHTS.
    """
    bad = _full_spec("bad_weight_typo")
    bad["score_weights"]["lowoil"] = bad["score_weights"].pop("low_oil")
    _write_spec(tmp_path, "bad_weight_typo", bad)
    _load_methodology_cached.cache_clear()
    with pytest.raises(MethodologyValidationError, match="unknown keys"):
        load_methodology("bad_weight_typo", tmp_path)


def test_validate_plate_rule_typo(tmp_path: Path):
    """plate_rule 拼写错也 hard fail."""
    bad = _full_spec("bad_plate")
    bad["plate_rule"]["min_protien_g"] = bad["plate_rule"].pop("min_protein_g")
    _write_spec(tmp_path, "bad_plate", bad)
    _load_methodology_cached.cache_clear()
    with pytest.raises(MethodologyValidationError, match="plate_rule"):
        load_methodology("bad_plate", tmp_path)


def test_validate_cap_rules_extra(tmp_path: Path):
    """cap_rules 多 1 个 key 也 hard fail (防 over-spec)."""
    bad = _full_spec("bad_cap")
    bad["cap_rules"]["per_dish_top_k"] = 99  # 不存在的 cap 类型
    _write_spec(tmp_path, "bad_cap", bad)
    _load_methodology_cached.cache_clear()
    with pytest.raises(MethodologyValidationError, match="cap_rules"):
        load_methodology("bad_cap", tmp_path)


def test_validate_name_must_match_filename(tmp_path: Path):
    """文件名 vs spec.name 不一致 → hard fail."""
    bad = _full_spec("file_alpha")
    bad["name"] = "spec_beta"
    _write_spec(tmp_path, "file_alpha", bad)
    _load_methodology_cached.cache_clear()
    with pytest.raises(MethodologyValidationError, match="name mismatch"):
        load_methodology("file_alpha", tmp_path)


# ─────────────────────── resolve_methodology (M-1) ───────────────────────

def test_resolve_uses_profile_field():
    """profile.methodology 显式 → 加载该 spec."""
    profile = {"methodology": "harvard_plate"}
    spec = resolve_methodology(profile, REPO_ROOT)
    assert spec["name"] == "harvard_plate"


def test_resolve_missing_field_fallback_logs_info(caplog):
    """profile 缺 methodology → fallback DEFAULT_METHODOLOGY + logger.info (M-1)."""
    profile = {}
    caplog.set_level(logging.INFO, logger="chisha.methodology")
    spec = resolve_methodology(profile, REPO_ROOT)
    assert spec["name"] == DEFAULT_METHODOLOGY
    # 必须有 info log 记录, 不能 silent
    assert any(
        "field missing" in rec.getMessage() and DEFAULT_METHODOLOGY in rec.getMessage()
        for rec in caplog.records
    ), "缺 methodology 字段时必须 logger.info 留可观测痕迹 (M-1)"


# ─────────────────────── merge_into_profile (B-2 + B-spot-2) ───────────────────────

def test_merge_into_profile_does_not_mutate_input():
    """merge 返回新 dict, 不就地改 profile."""
    spec = _full_spec("test")
    profile = {"plate_rule": {"min_protein_g": 40}}
    merged = merge_into_profile(profile, spec)
    assert profile["plate_rule"] == {"min_protein_g": 40}
    assert "scoring_weights" not in profile
    # merged 是不同对象
    assert merged is not profile
    assert merged["plate_rule"] is not profile["plate_rule"]


def test_merge_profile_explicit_value_overrides_spec(caplog):
    """B-spot-2: profile 已有显式值必须保留, spec defaults 不能覆盖.

    profile.plate_rule.min_protein_g=40 (志丹力量训练) 必须 override
    spec.plate_rule.min_protein_g=25.
    """
    spec = _full_spec("test")  # min_protein_g=25
    profile = {
        "plate_rule": {"min_protein_g": 40},
        "scoring_weights": {"low_oil": 0.9, "wetness": 0.0},
    }
    merged = merge_into_profile(profile, spec)
    # 显式值保留
    assert merged["plate_rule"]["min_protein_g"] == 40
    assert merged["scoring_weights"]["low_oil"] == 0.9
    assert merged["scoring_weights"]["wetness"] == 0.0
    # spec defaults 填充缺失字段
    assert merged["plate_rule"]["must_have_vegetable"] is True
    assert merged["plate_rule"]["hard_max_oil_level"] == 4
    assert merged["scoring_weights"]["popularity"] == 0.4  # spec 默认
    assert merged["scoring_weights"]["context_boost"] == 0.25


def test_merge_unforgivable_discount_path_b2():
    """B-2: spec.unforgivable_discount 必须 merge 到 profile.scoring.unforgivable_discount
    (而非 profile.unforgivable_discount 顶层).
    """
    spec = _full_spec("test")
    spec["unforgivable_discount"] = 0.3
    # profile 没显式设
    profile = {}
    merged = merge_into_profile(profile, spec)
    # 必须落在 profile.scoring.* 路径下 (score.py 读这条)
    assert merged.get("scoring", {}).get("unforgivable_discount") == 0.3
    # 不应在顶层
    assert "unforgivable_discount" not in {k for k in merged if k != "scoring"}


def test_merge_unforgivable_profile_overrides_spec():
    """profile.scoring.unforgivable_discount 显式 → 不被 spec 覆盖."""
    spec = _full_spec("test")
    spec["unforgivable_discount"] = 0.3
    profile = {"scoring": {"unforgivable_discount": 0.7}}
    merged = merge_into_profile(profile, spec)
    assert merged["scoring"]["unforgivable_discount"] == 0.7


def test_merge_recall_cap_keys_only():
    """cap_rules 只 merge per_*_top_k key, 不动 recall 其他字段 (per_restaurant_max 等)."""
    spec = _full_spec("test")
    profile = {
        "recall": {
            "per_restaurant_max": 20,
            "min_monthly_sales": 5,
            # 没设 per_restaurant_top_k 等 cap 字段 — spec 填入
        },
    }
    merged = merge_into_profile(profile, spec)
    # 原字段保留
    assert merged["recall"]["per_restaurant_max"] == 20
    assert merged["recall"]["min_monthly_sales"] == 5
    # spec cap 字段填入
    assert merged["recall"]["per_restaurant_top_k"] == 3
    assert merged["recall"]["per_brand_top_k"] == 2


def test_merge_attaches_methodology_name_and_spec():
    """merge 后 profile 含 methodology=name + _methodology_spec=spec (供下游用)."""
    spec = _full_spec("test")
    profile = {}
    merged = merge_into_profile(profile, spec)
    assert merged["methodology"] == "test"
    assert merged["_methodology_spec"] is not None
    assert merged["_methodology_spec"]["name"] == "test"


# ─────────────────────── apply_methodology (集成) ───────────────────────

def test_apply_methodology_default_fallback(tmp_path: Path):
    """profile 缺 methodology 字段, apply 走 DEFAULT_METHODOLOGY."""
    # 拷贝实际 harvard_plate.yaml 到 tmp_path 供加载
    src = REPO_ROOT / "profiles" / "methodologies" / "harvard_plate.yaml"
    dst_dir = tmp_path / "profiles" / "methodologies"
    dst_dir.mkdir(parents=True)
    (dst_dir / "harvard_plate.yaml").write_text(
        src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    _load_methodology_cached.cache_clear()
    merged = apply_methodology({}, tmp_path)
    assert merged["methodology"] == DEFAULT_METHODOLOGY
    assert "scoring_weights" in merged
    assert merged["scoring_weights"]["low_oil"] == 0.5


# ─────────────────────── 缓存 ───────────────────────

def test_load_returns_deep_copy():
    """同 name 两次 load 返回独立对象, 调用方改不污染缓存."""
    spec1 = load_methodology("harvard_plate", REPO_ROOT)
    spec1["plate_rule"]["min_protein_g"] = 999
    spec2 = load_methodology("harvard_plate", REPO_ROOT)
    assert spec2["plate_rule"]["min_protein_g"] != 999, (
        "load_methodology 必须返 deep copy, 否则调用方改会污染 LRU cache"
    )


def test_cache_invalidates_on_yaml_mtime_change(tmp_path: Path):
    """Codex Round 3 M-3: yaml mtime 变化后 cache 自然 miss, 不读旧值."""
    spec_dir = tmp_path / METHODOLOGIES_DIRNAME
    spec_dir.mkdir(parents=True)
    name = "mtime_test"
    spec_file = spec_dir / f"{name}.yaml"
    # 第一版: min_protein_g=10
    v1 = _full_spec(name)
    v1["plate_rule"]["min_protein_g"] = 10
    spec_file.write_text(yaml.dump(v1, allow_unicode=True), encoding="utf-8")
    _load_methodology_cached.cache_clear()
    s1 = load_methodology(name, tmp_path)
    assert s1["plate_rule"]["min_protein_g"] == 10

    # 改 yaml, mtime 变化 → 重读
    import os, time
    time.sleep(0.01)  # 确保 mtime_ns 不同
    v2 = _full_spec(name)
    v2["plate_rule"]["min_protein_g"] = 99
    spec_file.write_text(yaml.dump(v2, allow_unicode=True), encoding="utf-8")
    os.utime(spec_file, None)  # 显式 touch mtime
    s2 = load_methodology(name, tmp_path)
    assert s2["plate_rule"]["min_protein_g"] == 99, (
        "yaml 改后 cache 应自动失效 (mtime_ns 入 cache key)"
    )


# ─────────────────────── Codex Round 3 M-2: rerank fallback 测试 ───────────────────────

def test_rerank_profile_block_with_methodology():
    """profile._methodology_spec 存在 → [PROFILE] 块多出 "方法论: ..." 一行."""
    from chisha.rerank import _profile_block
    spec = load_methodology("harvard_plate", REPO_ROOT)
    profile_with = {
        "_methodology_spec": spec,
        "taste_description": "test",
        "preferences": {"liked_cuisines": ["湘菜"], "spicy_tolerance": 2},
    }
    block = _profile_block(profile_with)
    assert "[PROFILE]" in block
    assert "方法论:" in block
    assert spec["display_name"] in block


def test_rerank_profile_block_without_methodology_fallback():
    """profile 缺 _methodology_spec → [PROFILE] 块不含 "方法论:" 行 (向后兼容)."""
    from chisha.rerank import _profile_block
    profile_without = {
        "taste_description": "test",
        "preferences": {"liked_cuisines": ["湘菜"], "spicy_tolerance": 2},
    }
    block = _profile_block(profile_without)
    assert "[PROFILE]" in block
    assert "方法论:" not in block
    # 老格式: 口味描述 / 喜欢 / 不喜欢 / avoid / 辣度耐受 5 行 + [PROFILE] 头 = 6 行
    lines = block.split("\n")
    assert len(lines) == 6


def test_rerank_profile_block_diff_is_single_line():
    """A/B 对比: with vs without 唯一差异是 1 行新增 (M-2 + B-spot)."""
    from chisha.rerank import _profile_block
    spec = load_methodology("harvard_plate", REPO_ROOT)
    base = {
        "taste_description": "test",
        "preferences": {"liked_cuisines": ["湘菜"], "spicy_tolerance": 2},
    }
    block_without = _profile_block(base)
    block_with = _profile_block({**base, "_methodology_spec": spec})
    lines_without = block_without.split("\n")
    lines_with = block_with.split("\n")
    assert len(lines_with) == len(lines_without) + 1, (
        "methodology 注入应该只多 1 行, 不该改其他格式 (D-072 边界 + L3 A/B sanity)"
    )

"""collector_contract 窄契约校验器测试 (B1).

覆盖: 合法 envelope 过 / 真 A4 office 文件过 / 缺版本字段 fail / 版本不支持 fail /
norm_version 不匹配 fail / 类型漂移(price str) fail / provenance 缺 key fail (D1) /
provenance null 值过 / 新增字段允许 / 非 dict fail / 结构缺失 fail。
"""
from __future__ import annotations

import json
import os

import pytest

from chisha.collector_contract import (
    SUPPORTED_SCHEMA_VERSION,
    ContractViolation,
    validate_collector_output,
)

NORM_V = 1  # == chisha.loader.SHOP_NAME_VERSION


def _valid() -> dict:
    """最小合法 envelope (schema_version=1, provenance key 齐全, 一店一菜)。"""
    return {
        "schema_version": 1,
        "app": "meituan",
        "collected_at": "2026-05-26T20:00:00+08:00",
        "normalized_name_version": 1,
        "location": {
            "name": "深圳湾创新科技中心T2栋",
            "label": "office",
            "observed_address_text": None,
            "address_observed_at": None,
            "address_observation_status": "unobserved",
        },
        "restaurants": [
            {"name": "测试店", "menu_status": "ok", "menu_count": 1,
             "menu": [{"name": "菜", "price": 10.0}]},
        ],
    }


def test_valid_envelope_passes():
    doc = validate_collector_output(_valid(), expected_norm_version=NORM_V)
    assert doc.schema_version == SUPPORTED_SCHEMA_VERSION
    assert doc.location.label == "office"


def test_real_a4_office_file_passes():
    """真 A4 重导出的 office_restaurants.json 必须过 (strict 不误杀真数据)。"""
    path = os.path.expanduser("~/waimai_data/output/office_restaurants.json")
    if not os.path.exists(path):
        pytest.skip(f"无 collector 真文件 {path}")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if "schema_version" not in raw:
        pytest.skip(
            f"collector 真文件 {path} 仍是旧 schema (未按 D-100 重导出), "
            f"跳过 strict 校验 — 重导出后此测试自动恢复把关"
        )
    doc = validate_collector_output(raw, expected_norm_version=NORM_V)
    assert doc.schema_version == 1
    assert len(doc.restaurants) > 0


def test_non_dict_fails():
    with pytest.raises(ContractViolation, match="不是 dict"):
        validate_collector_output([1, 2, 3], expected_norm_version=NORM_V)


def test_missing_schema_version_fails():
    raw = _valid()
    del raw["schema_version"]
    with pytest.raises(ContractViolation):
        validate_collector_output(raw, expected_norm_version=NORM_V)


def test_unsupported_schema_version_fails():
    raw = _valid()
    raw["schema_version"] = 2
    with pytest.raises(ContractViolation, match="schema_version=2"):
        validate_collector_output(raw, expected_norm_version=NORM_V)


def test_norm_version_mismatch_fails():
    raw = _valid()
    raw["normalized_name_version"] = 2
    with pytest.raises(ContractViolation, match="normalized_name_version"):
        validate_collector_output(raw, expected_norm_version=NORM_V)


def test_price_string_fails_strict():
    raw = _valid()
    raw["restaurants"][0]["menu"][0]["price"] = "10"  # 类型漂移 → strict 拒
    with pytest.raises(ContractViolation):
        validate_collector_output(raw, expected_norm_version=NORM_V)


def test_extra_field_allowed():
    raw = _valid()
    raw["restaurants"][0]["new_producer_field"] = "x"  # producer 加非破坏字段
    raw["future_top_field"] = 123
    doc = validate_collector_output(raw, expected_norm_version=NORM_V)
    assert doc is not None  # 不阻断


def test_missing_provenance_key_fails():
    """D1: observed_* key 缺失 = 采址 provenance 被删 → fail-loud (Codex Q4 blocker)。"""
    raw = _valid()
    del raw["location"]["observed_address_text"]
    with pytest.raises(ContractViolation):
        validate_collector_output(raw, expected_norm_version=NORM_V)


def test_provenance_null_value_ok():
    """provenance 值为 null (unobserved) 是合法的 (key 在即可)。"""
    raw = _valid()
    raw["location"]["observed_address_text"] = None
    doc = validate_collector_output(raw, expected_norm_version=NORM_V)
    assert doc.location.observed_address_text is None


def test_missing_restaurant_menu_fails():
    raw = _valid()
    del raw["restaurants"][0]["menu"]
    with pytest.raises(ContractViolation):
        validate_collector_output(raw, expected_norm_version=NORM_V)


def test_missing_restaurants_fails():
    raw = _valid()
    del raw["restaurants"]
    with pytest.raises(ContractViolation):
        validate_collector_output(raw, expected_norm_version=NORM_V)


# ─────────────────────────────────────────────────────────────────────────
# D-105: 与旧 pydantic 行为对拍 (golden fixture)。
# tests/fixtures/collector_contract_golden.json 由 tmp/capture_contract_golden.py
# 在 pydantic 仍在场时跑出 (每 case: input + expect_pass + err_kind 分类)。纯 dataclass
# 校验器必须逐 case 复现同样的 pass/fail 与失败语义 (4 陷阱 + 检查顺序)。
# ─────────────────────────────────────────────────────────────────────────
from pathlib import Path  # noqa: E402

_GOLDEN_PATH = Path(__file__).parent / "fixtures" / "collector_contract_golden.json"
_GOLDEN = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8")) if _GOLDEN_PATH.exists() else []


def _classify(doc, norm):
    try:
        validate_collector_output(doc, expected_norm_version=norm)
        return True, None
    except ContractViolation as e:
        msg = str(e)
        if "不是 dict" in msg:
            kind = "not_dict"
        elif "schema_version" in msg and "不受支持" in msg:
            kind = "schema_version"
        elif "normalized_name_version" in msg:
            kind = "norm_version"
        else:
            kind = "contract"
        return False, kind


def test_golden_fixture_present_and_balanced():
    assert len(_GOLDEN) >= 40, "golden fixture 缺失或过少 (期望 ≥40 case)"
    assert any(c["expect_pass"] for c in _GOLDEN)
    assert any(not c["expect_pass"] for c in _GOLDEN)


@pytest.mark.parametrize("c", _GOLDEN, ids=[c["name"] for c in _GOLDEN] or None)
def test_matches_pydantic_golden(c):
    """逐 case 与旧 pydantic 行为对拍: pass/fail + 失败分类一致。"""
    ok, kind = _classify(c["input"], c["norm"])
    assert ok == c["expect_pass"], (
        f"{c['name']}: 新校验器 pass={ok} 但 golden(pydantic) pass={c['expect_pass']}"
    )
    if not ok:
        assert kind == c["err_kind"], (
            f"{c['name']}: 失败分类 {kind!r} != golden {c['err_kind']!r}"
        )

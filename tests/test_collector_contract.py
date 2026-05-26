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

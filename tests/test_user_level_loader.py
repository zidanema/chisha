"""T-DIST-01 B.5b: user-level zone/methodology loader 撞名 + lookup 测试.

撞名测试 4 case (plan B.5b step 6):
  - user zone only → OK (用 user 数据)
  - install zone only → OK (用 install 数据, 当前行为)
  - 同名撞 → ResourceNameCollisionError fail-loud
  - methodology 同上 (3 case 复用 zone 套路)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from chisha import manifest as mfst
from chisha.install_root import install_root
from chisha.methodology import (
    load_methodology, get_schema_keyset, get_template, validate_spec,
    MethodologyValidationError,
)
from chisha.recall import (
    ResourceNameCollisionError, ZoneNotFoundError, load_zone_data, _resolve_zone_dir,
)


@pytest.fixture
def isolated_roots(tmp_path, monkeypatch):
    """install_root 钉到 tmp_path/install (含 data/manifest.json + shenzhen-bay zone);
    state_root 钉到 tmp_path/state (空); CHISHA_STATE_ROOT 注入隔离."""
    install = tmp_path / "install"
    state = tmp_path / "state"
    install.mkdir()
    state.mkdir()
    monkeypatch.setenv("CHISHA_STATE_ROOT", str(state))

    # install_root override
    from chisha import install_root as _ir_mod
    monkeypatch.setattr(_ir_mod, "_OVERRIDE", install)

    # 清 manifest cache 防跨测试串扰
    mfst._checked.clear()

    # 兼容 manifest (install bundle)
    (install / "data").mkdir()
    (install / "data" / mfst.MANIFEST_FILENAME).write_text(json.dumps({
        "manifest_schema_version": mfst.MANIFEST_SCHEMA_VERSION,
        "artifact_version": 1, "data_schema_version": 1,
        "min_engine_version": mfst.ENGINE_VERSION,
        "engine_capabilities_required": sorted(mfst.SUPPORTED_ENGINE_CAPABILITIES),
        "normalized_name_version": 1, "zones": ["shenzhen-bay"],
        "generated_at": "2026-05-28T00:00:00+00:00", "integrity": None,
    }), encoding="utf-8")

    yield install, state

    monkeypatch.setattr(_ir_mod, "_OVERRIDE", None)
    mfst._checked.clear()


def _put_zone(base: Path, zone: str, rests=None, dishes=None):
    d = base / "data" / zone
    d.mkdir(parents=True, exist_ok=True)
    (d / "restaurants.json").write_text(json.dumps(rests or [{"rid": "r1"}]), encoding="utf-8")
    (d / "dishes_tagged.json").write_text(json.dumps(dishes or [{"dish_id": "d1"}]), encoding="utf-8")


def _put_methodology(base: Path, name: str, *, in_user: bool):
    """写一个最小可校验的 methodology spec."""
    subdir = "methodologies" if in_user else "profiles/methodologies"
    d = base / subdir
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(yaml.safe_dump({
        "name": name, "display_name": name, "version": "0.1", "rationale": "test",
        "plate_rule": {"must_have_vegetable": True, "min_vegetable_dishes": 1,
                       "min_protein_g": 20, "prefer_oil_level_at_most": 2,
                       "hard_max_oil_level": 3},
        "score_weights": {"low_oil": 1.0, "popularity": 0.5, "cuisine_preference": 0.5,
                          "variety_bonus": 0.5, "carb_quality": 0.5, "processed_meat": 0.5,
                          "sweet_sauce": 0.5, "dish_role_match": 0.5, "eta": 0.5,
                          "price": 0.5, "taste_match": 0.5},
        "cap_rules": {"per_restaurant_top_k": 3, "per_brand_top_k": 2,
                      "per_cuisine_top_k": 5, "per_food_form_top_k": 5},
    }, allow_unicode=True), encoding="utf-8")


# ─── Zone lookup ───

def test_zone_user_only(isolated_roots):
    """case 1: user zone 存在, install 没 → 用 user."""
    install, state = isolated_roots
    _put_zone(state, "my-zone", rests=[{"rid": "user-r"}])
    rests, _ = load_zone_data("my-zone", install)
    assert rests == [{"rid": "user-r"}]


def test_zone_install_only(isolated_roots):
    """case 2: install zone 存在, user 没 → 用 install (向后兼容旧行为)."""
    install, _ = isolated_roots
    _put_zone(install, "stock-zone", rests=[{"rid": "install-r"}])
    rests, _ = load_zone_data("stock-zone", install)
    assert rests == [{"rid": "install-r"}]


def test_zone_collision_fail_loud(isolated_roots):
    """case 3: 同名撞 → RESOURCE_NAME_COLLISION fail-loud (不允许 grandfather)."""
    install, state = isolated_roots
    _put_zone(install, "shenzhen-bay", rests=[{"rid": "install"}])
    _put_zone(state, "shenzhen-bay", rests=[{"rid": "user"}])
    with pytest.raises(ResourceNameCollisionError) as exc:
        load_zone_data("shenzhen-bay", install)
    assert "shenzhen-bay" in str(exc.value)
    assert "user" in str(exc.value).lower() or "user" in str(exc.value)
    assert "install" in str(exc.value).lower() or "install" in str(exc.value)


def test_zone_not_found_lists_known(isolated_roots):
    """case 4: 都没 → ZoneNotFoundError + 列已知 zones."""
    install, state = isolated_roots
    _put_zone(install, "stock-a")
    _put_zone(state, "user-b")
    with pytest.raises(ZoneNotFoundError) as exc:
        load_zone_data("nonexistent", install)
    msg = str(exc.value)
    assert "stock-a" in msg
    assert "user-b" in msg


# ─── Methodology lookup (3 case 同套路) ───

def test_methodology_user_only(isolated_roots):
    install, state = isolated_roots
    _put_methodology(state, "my-spec", in_user=True)
    spec = load_methodology("my-spec", install)
    assert spec["name"] == "my-spec"


def test_methodology_install_only(isolated_roots):
    install, _ = isolated_roots
    _put_methodology(install, "stock-spec", in_user=False)
    spec = load_methodology("stock-spec", install)
    assert spec["name"] == "stock-spec"


def test_methodology_collision_fail_loud(isolated_roots):
    install, state = isolated_roots
    _put_methodology(install, "harvard_plate", in_user=False)
    _put_methodology(state, "harvard_plate", in_user=True)
    with pytest.raises(ResourceNameCollisionError) as exc:
        load_methodology("harvard_plate", install)
    assert "harvard_plate" in str(exc.value)


def test_methodology_not_found_lists_known(isolated_roots):
    install, state = isolated_roots
    _put_methodology(install, "stock-a", in_user=False)
    _put_methodology(state, "user-b", in_user=True)
    with pytest.raises(FileNotFoundError) as exc:
        load_methodology("nonexistent", install)
    msg = str(exc.value)
    assert "stock-a" in msg
    assert "user-b" in msg


# ─── User resource manifest check (D-102.3 复用) ───

def test_user_resource_status_empty_when_no_user_data(isolated_roots):
    install, state = isolated_roots
    results = mfst.user_resource_manifest_check(state)
    assert results == []


def test_user_resource_status_reports_missing_manifest(isolated_roots):
    """user zone 有 restaurants.json 但缺 manifest.json → status=missing_manifest."""
    install, state = isolated_roots
    _put_zone(state, "user-zone")
    results = mfst.user_resource_manifest_check(state)
    zone_results = [r for r in results if r["kind"] == "zone"]
    assert len(zone_results) == 1
    assert zone_results[0]["name"] == "user-zone"
    assert zone_results[0]["status"] == "missing_manifest"


def test_user_resource_status_reports_incompatible(isolated_roots):
    """user zone manifest 缺关键字段 → incompatible."""
    install, state = isolated_roots
    _put_zone(state, "broken-zone")
    (state / "data" / "broken-zone" / mfst.MANIFEST_FILENAME).write_text(
        json.dumps({"manifest_schema_version": 1}),  # 缺 data_schema_version 等
        encoding="utf-8",
    )
    results = mfst.user_resource_manifest_check(state)
    zone_results = [r for r in results if r["kind"] == "zone"]
    assert zone_results[0]["status"] == "incompatible"
    assert "data_schema_version" in zone_results[0]["note"]


def test_user_resource_status_ok_with_valid_manifest(isolated_roots):
    install, state = isolated_roots
    _put_zone(state, "good-zone")
    (state / "data" / "good-zone" / mfst.MANIFEST_FILENAME).write_text(json.dumps({
        "manifest_schema_version": mfst.MANIFEST_SCHEMA_VERSION,
        "artifact_version": 1, "data_schema_version": 1,
        "min_engine_version": mfst.ENGINE_VERSION,
        "engine_capabilities_required": sorted(mfst.SUPPORTED_ENGINE_CAPABILITIES),
        "normalized_name_version": 1, "zones": ["good-zone"],
        "generated_at": "2026-05-28T00:00:00+00:00", "integrity": None,
    }), encoding="utf-8")
    results = mfst.user_resource_manifest_check(state)
    zone_results = [r for r in results if r["kind"] == "zone"]
    assert zone_results[0]["status"] == "ok"


# ─── Loader API placeholder (T-DIST-02 留位) ───

def test_get_schema_keyset_returns_sections():
    ks = get_schema_keyset()
    assert {"top", "plate_rule", "score_weights", "cap_rules"} <= set(ks.keys())
    assert "name" in ks["top"]
    assert "must_have_vegetable" in ks["plate_rule"]


def test_get_template_is_complete():
    t = get_template()
    assert set(t.keys()) >= {"name", "plate_rule", "score_weights", "cap_rules"}


def test_validate_spec_rejects_malformed(tmp_path):
    """validate_spec 调外部 spec 文件, 缺关键字段 raise."""
    p = tmp_path / "bad.yaml"
    p.write_text("name: bad\nversion: 0.1\n", encoding="utf-8")  # 缺 plate_rule 等
    with pytest.raises(MethodologyValidationError):
        validate_spec(p)


def test_validate_spec_accepts_valid_template(tmp_path):
    """完整 template 实际跑过 _validate_spec."""
    p = tmp_path / "good.yaml"
    spec = {
        "name": "good", "display_name": "good", "version": "0.1", "rationale": "test",
        "plate_rule": {"must_have_vegetable": True, "min_vegetable_dishes": 1,
                       "min_protein_g": 20, "prefer_oil_level_at_most": 2,
                       "hard_max_oil_level": 3},
        "score_weights": {"low_oil": 1.0, "popularity": 0.5, "cuisine_preference": 0.5,
                          "variety_bonus": 0.5, "carb_quality": 0.5, "processed_meat": 0.5,
                          "sweet_sauce": 0.5, "dish_role_match": 0.5, "eta": 0.5,
                          "price": 0.5, "taste_match": 0.5},
        "cap_rules": {"per_restaurant_top_k": 3, "per_brand_top_k": 2,
                      "per_cuisine_top_k": 5, "per_food_form_top_k": 5},
    }
    p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    validate_spec(p)  # 不抛即 OK

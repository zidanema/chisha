"""D-102 Step3: 数据产物 ↔ 引擎 manifest 兼容闸门契约.

不兼容 hard-fail (D-100 fail-loud); 缺 manifest = 过渡期 warn 放行; present-incompatible = raise.
"""
from __future__ import annotations

import json

import pytest

from chisha import manifest as M


def _write_manifest(root, **over):
    base = {
        "manifest_schema_version": M.MANIFEST_SCHEMA_VERSION,
        "artifact_version": 1,
        "data_schema_version": 1,
        "min_engine_version": M.ENGINE_VERSION,
        "engine_capabilities_required": sorted(M.SUPPORTED_ENGINE_CAPABILITIES),
        "normalized_name_version": 1,
        "zones": ["shenzhen-bay"],
        "generated_at": "2026-05-28T00:00:00+00:00",
        "integrity": None,
    }
    base.update(over)
    (root / "data").mkdir(parents=True, exist_ok=True)
    M.manifest_path(root).write_text(json.dumps(base), encoding="utf-8")


# ─────────────────────── 版本一致性 ───────────────────────

def test_engine_version_matches_pyproject():
    """chisha.__version__ 必须 == pyproject.toml version (两文本值防 drift)."""
    import re
    from pathlib import Path
    pyproj = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproj, re.MULTILINE)
    assert m, "pyproject.toml 无 version"
    assert m.group(1) == M.ENGINE_VERSION


def test_normalized_name_version_aligned():
    """manifest 校验绑 loader.SHOP_NAME_VERSION (改了要同步 build_manifest 的输出)."""
    from chisha.loader import SHOP_NAME_VERSION
    assert SHOP_NAME_VERSION == 1


# ─────────────────────── compat: ok / missing ───────────────────────

def test_compatible_manifest_ok(tmp_path):
    _write_manifest(tmp_path)
    st = M.check_compatibility(tmp_path)
    assert st.status == "ok" and st.artifact_version == 1


def test_missing_manifest_is_missing_not_raise(tmp_path):
    (tmp_path / "data").mkdir()
    st = M.check_compatibility(tmp_path)
    assert st.status == "missing"
    # ensure_compatible_once 对缺失 warn 放行 (不抛)
    M._checked.discard(str(tmp_path.resolve()))
    M.ensure_compatible_once(tmp_path)   # 不抛


# ─────────────────────── incompatible → hard-fail ───────────────────────

def test_manifest_schema_too_new_raises(tmp_path):
    _write_manifest(tmp_path, manifest_schema_version=M.MANIFEST_SCHEMA_VERSION + 1)
    with pytest.raises(M.IncompatibleManifestError, match="manifest_schema_version"):
        M.check_compatibility(tmp_path)


def test_data_schema_too_new_raises(tmp_path):
    _write_manifest(tmp_path, data_schema_version=M.SUPPORTED_DATA_SCHEMA_VERSION + 1)
    with pytest.raises(M.IncompatibleManifestError, match="data_schema_version"):
        M.check_compatibility(tmp_path)


def test_semver_two_vs_three_segments_equivalent(tmp_path):
    """min_engine '0.1' 与引擎 '0.1.0' 等价, 不该误判不兼容 (零补齐)."""
    _write_manifest(tmp_path, min_engine_version="0.1")
    assert M.check_compatibility(tmp_path).status == "ok"


def test_min_engine_too_high_raises(tmp_path):
    _write_manifest(tmp_path, min_engine_version="999.0.0")
    with pytest.raises(M.IncompatibleManifestError, match="要求引擎"):
        M.check_compatibility(tmp_path)


def test_missing_capability_raises(tmp_path):
    _write_manifest(tmp_path,
                    engine_capabilities_required=["stable_entity_ids_v1", "future_cap_v9"])
    with pytest.raises(M.IncompatibleManifestError, match="能力"):
        M.check_compatibility(tmp_path)


def test_normalized_name_version_mismatch_raises(tmp_path):
    _write_manifest(tmp_path, normalized_name_version=99)
    with pytest.raises(M.IncompatibleManifestError, match="normalized_name_version"):
        M.check_compatibility(tmp_path)


def test_present_but_missing_data_schema_version_raises(tmp_path):
    """present manifest 缺关键字段 = malformed → fail-loud (不 fail-open 绕过)."""
    _write_manifest(tmp_path)
    data = json.loads(M.manifest_path(tmp_path).read_text(encoding="utf-8"))
    del data["data_schema_version"]
    M.manifest_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(M.IncompatibleManifestError, match="data_schema_version"):
        M.check_compatibility(tmp_path)


def test_present_but_missing_normalized_name_version_raises(tmp_path):
    _write_manifest(tmp_path)
    data = json.loads(M.manifest_path(tmp_path).read_text(encoding="utf-8"))
    del data["normalized_name_version"]
    M.manifest_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(M.IncompatibleManifestError, match="normalized_name_version"):
        M.check_compatibility(tmp_path)


def test_corrupt_manifest_raises(tmp_path):
    (tmp_path / "data").mkdir()
    M.manifest_path(tmp_path).write_text("{ not json", encoding="utf-8")
    with pytest.raises(M.IncompatibleManifestError, match="损坏"):
        M.check_compatibility(tmp_path)


def test_ensure_compatible_once_caches(tmp_path):
    """同 root 只检一次 (不每次 load_zone_data 重读)."""
    _write_manifest(tmp_path)
    M._checked.discard(str(tmp_path.resolve()))
    M.ensure_compatible_once(tmp_path)
    # 之后删 manifest, 已缓存 → 仍不抛 (证明缓存生效)
    M.manifest_path(tmp_path).unlink()
    M.ensure_compatible_once(tmp_path)   # 不重读, 不抛


def test_real_bundle_manifest_compatible():
    """真 repo data/manifest.json 与当前引擎兼容 (发布产物自洽)."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    st = M.check_compatibility(root)
    assert st.status == "ok"

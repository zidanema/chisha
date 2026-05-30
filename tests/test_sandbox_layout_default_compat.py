"""S-05 guard: default sid 读写路径 == S-04 + _meta.json 读写 helper 行为.

scope 收窄:
- 只 cover default sid (flat layout) + sandbox.init 写 _meta.json 的 schema/字段
- 非 default sid 路由 / runtime ctxvar = deferred to S-06a
- 一次性 v1→v2 迁移器 (migrate_to_v2 + relocate) 已退役, 不再覆盖
"""
from __future__ import annotations

from pathlib import Path

from chisha import data_root, sandbox
from chisha.sandbox_context import _DEFAULT_SID
from chisha.sandbox_migration import SCHEMA_VERSION, read_meta


# ────────────────────────── default sid 路径 (回归 S-04 行为)
def test_default_sid_path_is_flat(tmp_path: Path) -> None:
    sandbox.init(start_date="2026-05-20", root=tmp_path)
    base = data_root.meal_log_path(tmp_path)
    assert base == tmp_path / "logs" / "sandbox" / "meal_log.jsonl"
    assert data_root.meal_log_path(tmp_path, session_id=_DEFAULT_SID) == base


def test_default_bucket_data_readable(tmp_path: Path) -> None:
    sandbox.init(start_date="2026-05-20", root=tmp_path)
    (tmp_path / "logs" / "sandbox" / "meal_log.jsonl").write_text(
        '{"meal":"lunch"}\n', encoding="utf-8"
    )
    content = (tmp_path / "logs" / "sandbox" / "meal_log.jsonl").read_text()
    assert '"meal":"lunch"' in content


# ────────────────────────── _meta.json 行为
def test_meta_written_with_schema_version_2(tmp_path: Path) -> None:
    """sandbox.init() 自带 ensure _meta.json (idempotent). 关键 invariant:
    meta 存在 + schema_version=2 + default_layout=flat."""
    sandbox.init(start_date="2026-05-20", root=tmp_path)
    meta = read_meta(tmp_path)
    assert meta is not None
    assert meta["schema_version"] == SCHEMA_VERSION
    assert meta["default_layout"] == "flat"


# ────────────────────────── has_sandbox_meta helper
def test_has_sandbox_meta_helper(tmp_path: Path) -> None:
    """sandbox.init() 已 ensure meta → 一步成立."""
    assert not sandbox.has_sandbox_meta(tmp_path)  # init 前 false
    sandbox.init(start_date="2026-05-20", root=tmp_path)
    assert sandbox.has_sandbox_meta(tmp_path)  # init 后 true (S-06a)

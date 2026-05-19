"""S-05 guard: default sid 读写路径 == S-04 + migration 不破坏 default 桶.

scope 收窄:
- 只 cover default sid (flat layout) + migration 幂等
- 非 default sid 路由 / runtime ctxvar = deferred to S-06a

Codex audit history (plan v5.2 APPROVED):
- iter1: dropped sessions/ from relocate, ts-suffix bak, relocate_only branch
- iter2: relocate_satisfied per-artifact derivation
- iter3: APPROVED
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chisha import data_root, sandbox
from chisha.sandbox_context import _DEFAULT_SID
from chisha.sandbox_migration import SCHEMA_VERSION, migrate_to_v2, read_meta


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path


# ────────────────────────── default sid 路径 (回归 S-04 行为)
def test_default_sid_path_unchanged_after_migrate(tmp_root: Path) -> None:
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    base_before = data_root.meal_log_path(tmp_root)
    assert base_before == tmp_root / "logs" / "sandbox" / "meal_log.jsonl"
    migrate_to_v2(tmp_root)
    base_after = data_root.meal_log_path(tmp_root)
    assert base_after == base_before  # flat path 不变
    assert (
        data_root.meal_log_path(tmp_root, session_id=_DEFAULT_SID) == base_after
    )


def test_default_bucket_data_readable_after_migrate(tmp_root: Path) -> None:
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    (tmp_root / "logs" / "sandbox" / "meal_log.jsonl").write_text(
        '{"meal":"lunch"}\n', encoding="utf-8"
    )
    migrate_to_v2(tmp_root)
    # 数据原地, default sid 仍读得到
    content = (tmp_root / "logs" / "sandbox" / "meal_log.jsonl").read_text()
    assert '"meal":"lunch"' in content


# ────────────────────────── _meta.json 行为
def test_meta_written_with_schema_version_2(tmp_root: Path) -> None:
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    result = migrate_to_v2(tmp_root)
    assert result["status"] == "migrated"
    meta = read_meta(tmp_root)
    assert meta is not None
    assert meta["schema_version"] == SCHEMA_VERSION
    assert meta["default_layout"] == "flat"
    assert meta["migrated_at"]


def test_idempotent_rerun_is_noop(tmp_root: Path) -> None:
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    r1 = migrate_to_v2(tmp_root)
    assert r1["status"] == "migrated"
    r2 = migrate_to_v2(tmp_root)
    assert r2["status"] == "already_migrated"
    # 二次跑后 meta 不变
    meta = read_meta(tmp_root)
    assert meta is not None
    assert meta["schema_version"] == SCHEMA_VERSION


def test_no_sandbox_dir_returns_no_sandbox(tmp_root: Path) -> None:
    # sandbox 从未初始化
    result = migrate_to_v2(tmp_root)
    assert result["status"] == "no_sandbox"
    assert not (tmp_root / "logs" / "sandbox" / "_meta.json").exists()


# ────────────────────────── dry-run
def test_dry_run_no_disk_writes(tmp_root: Path) -> None:
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    result = migrate_to_v2(tmp_root, dry_run=True)
    assert result["status"] == "dry_run"
    assert read_meta(tmp_root) is None


# ────────────────────────── relocate-legacy opt-in
def test_relocate_legacy_moves_files_with_bak(tmp_root: Path) -> None:
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sb = tmp_root / "logs" / "sandbox"
    (sb / "meal_log.jsonl").write_text("data\n", encoding="utf-8")
    result = migrate_to_v2(tmp_root, relocate_legacy=True)
    assert "meal_log.jsonl" in result["relocated"]
    # legacy bucket 有
    assert (sb / "sessions" / "_legacy" / "meal_log.jsonl").exists()
    # 源 ts-suffix .bak 保留 (v5.1 Codex fix #3)
    baks = list(sb.glob("meal_log.jsonl.bak.*"))
    assert len(baks) == 1


def test_relocate_idempotent_second_run_skips(tmp_root: Path) -> None:
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sb = tmp_root / "logs" / "sandbox"
    (sb / "meal_log.jsonl").write_text("data\n", encoding="utf-8")
    migrate_to_v2(tmp_root, relocate_legacy=True)
    # 模拟 _meta.json 损坏被外部删除, 但 src/dst 状态保留
    (sb / "_meta.json").unlink()
    r2 = migrate_to_v2(tmp_root, relocate_legacy=True)
    # src 已不在 → skipped (走 satisfied 路径)
    assert "meal_log.jsonl" in r2["skipped"]


# ────────────────────────── has_sandbox_meta helper
def test_has_sandbox_meta_helper(tmp_root: Path) -> None:
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    assert not sandbox.has_sandbox_meta(tmp_root)
    migrate_to_v2(tmp_root)
    assert sandbox.has_sandbox_meta(tmp_root)


# ────────────────────────── v5.1 Codex fix tests
def test_sessions_dir_not_relocated(tmp_root: Path) -> None:
    """Codex fix #1: sessions/ 不挪 (是 _legacy parent + D-039 recommend dir)."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sb = tmp_root / "logs" / "sandbox"
    (sb / "sessions").mkdir(parents=True, exist_ok=True)
    (sb / "sessions" / "abc_xyz.json").write_text("{}", encoding="utf-8")
    (sb / "meal_log.jsonl").write_text("data\n", encoding="utf-8")
    result = migrate_to_v2(tmp_root, relocate_legacy=True)
    # sessions 不在 relocated 列表
    assert "sessions" not in result["relocated"]
    # sessions/abc_xyz.json 原地保留 (不被搬走, 不被备份)
    assert (sb / "sessions" / "abc_xyz.json").exists()
    # 也不在 _legacy 下 (即没建 sessions/_legacy/sessions)
    assert not (sb / "sessions" / "_legacy" / "sessions").exists()
    # meal_log 走正常 relocate
    assert "meal_log.jsonl" in result["relocated"]


def test_relocate_after_default_migrate_runs(tmp_root: Path) -> None:
    """Codex fix #2: 默认 migrate 后, --relocate-legacy 仍可跑 (relocate_only 分支)."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sb = tmp_root / "logs" / "sandbox"
    (sb / "meal_log.jsonl").write_text("data\n", encoding="utf-8")
    # 1. 默认 migrate (不 relocate)
    r1 = migrate_to_v2(tmp_root)
    assert r1["status"] == "migrated"
    meta1 = read_meta(tmp_root)
    assert meta1 is not None
    assert meta1["relocated_legacy"] is False
    # 2. 后跑 relocate 应进 relocate_only 分支
    r2 = migrate_to_v2(tmp_root, relocate_legacy=True)
    assert r2["status"] == "relocate_only"
    assert "meal_log.jsonl" in r2["relocated"]
    # meta 翻 relocated_legacy=True
    meta2 = read_meta(tmp_root)
    assert meta2 is not None
    assert meta2["relocated_legacy"] is True
    assert meta2["schema_version"] == SCHEMA_VERSION
    # 3. 再跑应 already_migrated
    r3 = migrate_to_v2(tmp_root, relocate_legacy=True)
    assert r3["status"] == "already_migrated"


# ────────────────────────── v5.2 Codex iter 2 fix tests
def test_relocate_twice_second_is_already_migrated(tmp_root: Path) -> None:
    """v5.2 Codex fix #1: 第二次 relocate-only 必须 already_migrated, 不再 relocate_only."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sb = tmp_root / "logs" / "sandbox"
    (sb / "meal_log.jsonl").write_text("data\n", encoding="utf-8")
    r1 = migrate_to_v2(tmp_root, relocate_legacy=True)
    assert r1["status"] == "migrated"
    meta1 = read_meta(tmp_root)
    assert meta1 is not None
    assert meta1["relocated_legacy"] is True
    # 第二次 — src 已不在 (变成 .bak.<ts>), dst 已在 → all_ok=True → satisfied
    r2 = migrate_to_v2(tmp_root, relocate_legacy=True)
    assert r2["status"] == "already_migrated", (
        f"second relocate should be no-op, got status={r2['status']}"
    )


def test_relocate_with_no_artifacts_marks_satisfied(tmp_root: Path) -> None:
    """v5.2 Codex fix #1: sandbox 目录在但无任何 legacy artifact → satisfied=True."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sb = tmp_root / "logs" / "sandbox"
    # sandbox 目录在 (sandbox.init 建了 state.json), 删 state.json 模拟空目录
    (sb / "state.json").unlink()
    r1 = migrate_to_v2(tmp_root, relocate_legacy=True)
    assert r1["status"] == "migrated"
    # 没东西可挪 → 仍 satisfied (relocated_legacy=True)
    meta = read_meta(tmp_root)
    assert meta is not None
    assert meta["relocated_legacy"] is True
    # 二次跑 → already_migrated
    r2 = migrate_to_v2(tmp_root, relocate_legacy=True)
    assert r2["status"] == "already_migrated"


def test_relocate_interrupted_mid_run_not_satisfied(tmp_root: Path) -> None:
    """v5.2 Codex fix #1 corollary: src/dst 同时在 (上次跑被打断) → satisfied=False."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sb = tmp_root / "logs" / "sandbox"
    (sb / "meal_log.jsonl").write_text("new\n", encoding="utf-8")
    # 模拟上次跑只 copy 没 rename (src+dst 都在)
    legacy = sb / "sessions" / "_legacy"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "meal_log.jsonl").write_text("old\n", encoding="utf-8")
    r1 = migrate_to_v2(tmp_root, relocate_legacy=True)
    # src 和 dst 都在 → skip + all_ok=False → relocated_legacy=False
    assert "meal_log.jsonl" in r1["skipped"]
    meta = read_meta(tmp_root)
    assert meta is not None
    assert meta["relocated_legacy"] is False
    # 二次仍 relocate_only (等手工解决)
    r2 = migrate_to_v2(tmp_root, relocate_legacy=True)
    assert r2["status"] == "relocate_only"


def test_bak_name_is_timestamped_and_collision_safe(tmp_root: Path) -> None:
    """Codex fix #3: .bak 用 ts 后缀, 不复用. 预存 .bak 不被覆盖."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sb = tmp_root / "logs" / "sandbox"
    (sb / "meal_log.jsonl").write_text("data\n", encoding="utf-8")
    # 预存一个老 .bak (模拟手工 rollback 残留)
    (sb / "meal_log.jsonl.bak").write_text("OLD_BACKUP\n", encoding="utf-8")
    migrate_to_v2(tmp_root, relocate_legacy=True)
    # 老 .bak 完整保留
    assert (sb / "meal_log.jsonl.bak").read_text() == "OLD_BACKUP\n"
    # 新 bak 用 ts 后缀
    baks = list(sb.glob("meal_log.jsonl.bak.*"))
    assert len(baks) == 1, (
        f"expected one ts bak, got {[b.name for b in baks]}"
    )
    # ts 格式校验 (YYYYMMDDTHHMMSSZ)
    suffix = baks[0].name.split(".bak.", 1)[1]
    assert len(suffix) == 16 and suffix.endswith("Z")

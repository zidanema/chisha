"""D-102 Step2 (Commit B): state_migrate — repo 旧 state 迁到 state_root (~/.chisha/).

安全契约: 复制 (不删源) + 校验 + 原子 marker + 幂等 + 不覆盖已存在目标 + 迁出 data/。
"""
from __future__ import annotations

import json

import pytest

from chisha import state_migrate


def _seed_install(install):
    """造一个带旧 state 的 install_root (repo 形态)."""
    (install / "profile.yaml").write_text("methodology: harvard_plate\n", encoding="utf-8")
    (install / "logs").mkdir()
    (install / "logs" / "meal_log.jsonl").write_text('{"ts":"2026-05-20"}\n', encoding="utf-8")
    (install / "logs" / "recommend_trace").mkdir()
    (install / "logs" / "recommend_trace" / "t1.json").write_text("{}", encoding="utf-8")
    (install / "data").mkdir()
    (install / "data" / "feedback_history.jsonl").write_text('{"r":1}\n', encoding="utf-8")
    (install / "data" / "long_term_prefs.json").write_text('{"boost":["low_oil"]}', encoding="utf-8")
    # 只读数据 (不该被迁)
    (install / "data" / "shenzhen-bay").mkdir()
    (install / "data" / "shenzhen-bay" / "restaurants.json").write_text("[]", encoding="utf-8")


def test_migrate_copies_and_relocates(tmp_path):
    install = tmp_path / "repo"; install.mkdir()
    state = tmp_path / "home_chisha"
    _seed_install(install)

    res = state_migrate.migrate_state(install, state)
    assert res.status == "migrated"

    # profile + logs 子树搬到 state_root
    assert (state / "profile.yaml").exists()
    assert (state / "logs" / "meal_log.jsonl").exists()
    assert (state / "logs" / "recommend_trace" / "t1.json").exists()
    # feedback_history / long_term_prefs 迁出 data/ → state_root 顶层
    assert (state / "feedback_history.jsonl").exists()
    assert (state / "long_term_prefs.json").exists()
    assert not (state / "data" / "feedback_history.jsonl").exists()
    # 只读 zone 数据**不迁** (留 install)
    assert not (state / "data" / "shenzhen-bay").exists()
    # 源保留 (repo = 回滚副本, 复制不删)
    assert (install / "profile.yaml").exists()
    assert (install / "logs" / "meal_log.jsonl").exists()
    # marker 落盘
    assert state_migrate.is_migrated(state)
    mani = json.loads((state / state_migrate.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert mani["version"] == state_migrate.MIGRATE_VERSION
    assert mani["file_count"] >= 4


def test_migrate_idempotent(tmp_path):
    install = tmp_path / "repo"; install.mkdir(); _seed_install(install)
    state = tmp_path / "home_chisha"
    state_migrate.migrate_state(install, state)
    res2 = state_migrate.migrate_state(install, state)
    assert res2.status == "already"      # marker 已存在 → 不重复迁


def test_migrate_merges_existing_dir_no_loss_no_clobber(tmp_path):
    """state_root/logs 已存在 (先前运行创建) → 逐文件合并: 旧 repo 日志不丢, state 已有
    文件不被覆盖 (Codex review 新 BLOCKING: 整目录 skip 会静默丢旧日志)."""
    install = tmp_path / "repo"; install.mkdir(); _seed_install(install)
    # install/logs 有 meal_log.jsonl + recommend_trace/t1.json (见 _seed_install)
    state = tmp_path / "home_chisha"
    (state / "logs").mkdir(parents=True)
    (state / "logs" / "meal_log.jsonl").write_text("STATE_VERSION\n", encoding="utf-8")  # 用户新数据
    (state / "logs" / "newer.jsonl").write_text("only_in_state\n", encoding="utf-8")

    state_migrate.migrate_state(install, state)
    # 旧 repo 独有文件被合并进来 (没丢) + 内容完整 (原子 rename 保证)
    t1 = state / "logs" / "recommend_trace" / "t1.json"
    assert t1.exists() and t1.read_text(encoding="utf-8") == \
        (install / "logs" / "recommend_trace" / "t1.json").read_text(encoding="utf-8")
    # state 已有同名文件**不被覆盖** (保留用户版本)
    assert (state / "logs" / "meal_log.jsonl").read_text(encoding="utf-8") == "STATE_VERSION\n"
    # state 独有文件保留
    assert (state / "logs" / "newer.jsonl").exists()
    # 无 staging 孤儿残留 (原子 rename 后清干净)
    assert not list((state / "logs").rglob("*.migrating.*"))
    # marker 仍写 (合并成功)
    assert state_migrate.is_migrated(state)


def test_migrate_no_overwrite_existing(tmp_path):
    """state_root 已有用户数据 → 不覆盖 (防二次迁抹掉新数据)."""
    install = tmp_path / "repo"; install.mkdir(); _seed_install(install)
    state = tmp_path / "home_chisha"; state.mkdir()
    (state / "profile.yaml").write_text("methodology: USER_EDITED\n", encoding="utf-8")
    state_migrate.migrate_state(install, state)
    # 用户在 state_root 的 profile 不被 install 旧 profile 覆盖
    assert "USER_EDITED" in (state / "profile.yaml").read_text(encoding="utf-8")


def test_migrate_nothing_when_empty(tmp_path):
    install = tmp_path / "empty"; install.mkdir()
    state = tmp_path / "home_chisha"
    res = state_migrate.migrate_state(install, state)
    assert res.status == "nothing_to_migrate"
    assert not state_migrate.is_migrated(state)


def test_migrate_dry_run_writes_nothing(tmp_path):
    install = tmp_path / "repo"; install.mkdir(); _seed_install(install)
    state = tmp_path / "home_chisha"
    res = state_migrate.migrate_state(install, state, dry_run=True)
    assert res.status == "dry_run"
    assert res.file_count >= 4
    assert not state.exists() or not state_migrate.is_migrated(state)

"""D-074 PR-1b: data_root.py 派生 + sandbox 路径隔离单测.

守门:
- sandbox 关闭时所有路径 = prod 默认
- sandbox 启用时 6 个业务数据落点全部切到 logs/sandbox/
- 关掉 sandbox 后路径切回 prod (动态切换)
- profile_path 副本 fallback 行为
- 端到端: sandbox 内写 meal_log / feedback / prefs, prod 路径完全不动
"""
from __future__ import annotations

from pathlib import Path

import pytest

from chisha import data_root, sandbox


@pytest.fixture
def tmp_root(tmp_path: Path):
    return tmp_path


# ─────────────────────── prod 默认
def test_prod_paths_when_sandbox_off(tmp_root: Path):
    assert data_root.meal_log_path(tmp_root) == tmp_root / "logs" / "meal_log.jsonl"
    assert data_root.sessions_dir(tmp_root) == tmp_root / "logs" / "sessions"
    assert data_root.feedback_store_path(tmp_root) == \
        tmp_root / "logs" / "feedback" / "store.json"
    assert data_root.recommend_log_path(tmp_root) == \
        tmp_root / "logs" / "recommend_log.jsonl"
    assert data_root.feedback_history_path(tmp_root) == \
        tmp_root / "data" / "feedback_history.jsonl"
    assert data_root.long_term_prefs_path(tmp_root) == \
        tmp_root / "data" / "long_term_prefs.json"
    assert data_root.profile_path(tmp_root) == tmp_root / "profile.yaml"


# ─────────────────────── sandbox 切换
def test_sandbox_paths_when_enabled(tmp_root: Path):
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    base = tmp_root / "logs" / "sandbox"
    assert data_root.meal_log_path(tmp_root) == base / "meal_log.jsonl"
    assert data_root.sessions_dir(tmp_root) == base / "sessions"
    assert data_root.feedback_store_path(tmp_root) == base / "feedback" / "store.json"
    assert data_root.recommend_log_path(tmp_root) == base / "recommend_log.jsonl"
    assert data_root.feedback_history_path(tmp_root) == base / "feedback_history.jsonl"
    assert data_root.long_term_prefs_path(tmp_root) == base / "long_term_prefs.json"


def test_paths_revert_after_disable(tmp_root: Path):
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    assert "sandbox" in str(data_root.meal_log_path(tmp_root))
    sandbox.disable(root=tmp_root)
    assert "sandbox" not in str(data_root.meal_log_path(tmp_root))


# ─────────────────────── profile_path 副本 fallback
def test_profile_path_sandbox_no_copy_falls_back(tmp_root: Path):
    """sandbox 启用但没拷贝 profile → 仍读 prod profile.yaml."""
    (tmp_root / "profile.yaml").write_text("methodology: harvard_plate\n",
                                             encoding="utf-8")
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    assert data_root.profile_path(tmp_root) == tmp_root / "profile.yaml"


def test_profile_path_sandbox_with_copy(tmp_root: Path):
    """sandbox 启用 + 副本存在 → 走副本."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sandboxed_profile = tmp_root / "logs" / "sandbox" / "profile.yaml"
    sandboxed_profile.parent.mkdir(parents=True, exist_ok=True)
    sandboxed_profile.write_text("methodology: sandbox\n", encoding="utf-8")
    assert data_root.profile_path(tmp_root) == sandboxed_profile


# ─────────────────────── 端到端: sandbox 写不污染 prod
def test_sandbox_meal_log_isolated(tmp_root: Path):
    """sandbox 启用时写 meal_log → 落 sandbox 目录, prod 路径不存在."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    sandbox_path = data_root.meal_log_path(tmp_root)
    sandbox_path.parent.mkdir(parents=True, exist_ok=True)
    sandbox_path.write_text('{"ts": "2026-05-20"}\n', encoding="utf-8")

    assert sandbox_path.exists()
    prod_path = tmp_root / "logs" / "meal_log.jsonl"
    assert not prod_path.exists()


def test_sandbox_l1_prefs_isolated(tmp_root: Path):
    """sandbox 启用时 save_prefs 落 sandbox, prod prefs.json 不动."""
    from chisha.l1_prefs import save_prefs
    # prod 先放一份 prefs
    prod_prefs = tmp_root / "data" / "long_term_prefs.json"
    prod_prefs.parent.mkdir(parents=True, exist_ok=True)
    prod_prefs.write_text(
        '{"boost": ["wetness"], "penalty": [], "version": 1}',
        encoding="utf-8",
    )

    sandbox.init(start_date="2026-05-20", root=tmp_root)
    save_prefs({"boost": ["low_oil"], "penalty": []}, root=tmp_root)

    # sandbox 副本存在
    sandbox_prefs = tmp_root / "logs" / "sandbox" / "long_term_prefs.json"
    assert sandbox_prefs.exists()
    # prod 没变
    assert "wetness" in prod_prefs.read_text(encoding="utf-8")


def test_sandbox_feedback_store_isolated(tmp_root: Path):
    """sandbox 启用时写 feedback store → 落 sandbox 目录."""
    from chisha import feedback_store
    # prod 先初始化 (空)
    (tmp_root / "logs" / "feedback").mkdir(parents=True, exist_ok=True)
    (tmp_root / "logs" / "feedback" / "store.json").write_text(
        '{"accepted": {}, "feedbacks": {}, "sessions": {}}', encoding="utf-8",
    )

    sandbox.init(start_date="2026-05-20", root=tmp_root)
    feedback_store.record_accept(
        tmp_root, session_id="sid_x", candidate_rank=1,
        meal_type="lunch", restaurant_name="店", summary="",
    )
    # sandbox 落点存在 + 含 sid_x
    sandbox_store = tmp_root / "logs" / "sandbox" / "feedback" / "store.json"
    assert sandbox_store.exists()
    assert "sid_x" in sandbox_store.read_text(encoding="utf-8")
    # prod 路径仍是空
    prod_store = tmp_root / "logs" / "feedback" / "store.json"
    assert "sid_x" not in prod_store.read_text(encoding="utf-8")


def test_full_round_trip_with_reset(tmp_root: Path):
    """sandbox 写完 → reset 后 sandbox 目录干净, prod 完好."""
    from chisha import feedback_store
    from chisha.l1_prefs import save_prefs

    sandbox.init(start_date="2026-05-20", root=tmp_root)
    save_prefs({"boost": ["low_oil"], "penalty": []}, root=tmp_root)
    feedback_store.record_accept(
        tmp_root, session_id="sid_x", candidate_rank=1,
        meal_type="lunch", restaurant_name="店", summary="",
    )

    sandbox_dir = tmp_root / "logs" / "sandbox"
    assert sandbox_dir.exists()

    sandbox.reset(root=tmp_root)
    assert not sandbox_dir.exists()
    # sandbox 关闭后路径回到 prod
    assert sandbox.is_enabled(tmp_root) is False

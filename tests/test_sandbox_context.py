"""S-04: sandbox_context (ContextVar) + data_root sid 行为单测.

覆盖:
- sandbox_context: default / set / nested / asyncio isolation
- sid 校验: 非法 / ``_default`` 白 / ``_legacy`` 黑 / trailing \\n 拒
- data_root: 显式 > ctx > ``_default`` 优先级 + sandbox on/off 行为矩阵
- 线程: ContextVar 默认不跨线程 (文档化) + S-06a forward guards
  (``copy_context().run`` propagate / 显式 sid kwarg override)
"""
from __future__ import annotations

import asyncio
import threading
from contextvars import copy_context
from pathlib import Path

import pytest

from chisha import data_root, sandbox
from chisha.sandbox_context import (
    _DEFAULT_SID,
    _validate_sid,
    current_sandbox_session,
    set_sandbox_session,
)


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path


# ────────────────────────── ContextVar 语义
def test_default_returns_none() -> None:
    """无 ctx → current_sandbox_session() 返 None."""
    assert current_sandbox_session() is None


def test_set_and_get() -> None:
    with set_sandbox_session("abc"):
        assert current_sandbox_session() == "abc"
    assert current_sandbox_session() is None


def test_nested_restores() -> None:
    with set_sandbox_session("outer"):
        assert current_sandbox_session() == "outer"
        with set_sandbox_session("inner"):
            assert current_sandbox_session() == "inner"
        assert current_sandbox_session() == "outer"
    assert current_sandbox_session() is None


def test_asyncio_isolation() -> None:
    """asyncio.gather 两 task 各自 sid 不串."""
    results: dict[str, str | None] = {}

    async def _task(sid: str, key: str) -> None:
        with set_sandbox_session(sid):
            await asyncio.sleep(0)
            results[key] = current_sandbox_session()
            await asyncio.sleep(0)
            results[key + "_2"] = current_sandbox_session()

    async def _main() -> None:
        await asyncio.gather(_task("sid_a", "a"), _task("sid_b", "b"))

    asyncio.run(_main())
    assert results == {
        "a": "sid_a", "a_2": "sid_a",
        "b": "sid_b", "b_2": "sid_b",
    }


# ────────────────────────── sid 校验
def test_invalid_sid_raises() -> None:
    with pytest.raises(ValueError, match="invalid sandbox session_id"):
        _validate_sid("../escape")
    with pytest.raises(ValueError):
        _validate_sid("")
    with pytest.raises(ValueError):
        _validate_sid("with space")
    with pytest.raises(ValueError):
        _validate_sid("a" * 65)


def test_default_sid_allowed() -> None:
    assert _validate_sid(_DEFAULT_SID) == _DEFAULT_SID
    # set_sandbox_session 也应放过
    with set_sandbox_session(_DEFAULT_SID):
        assert current_sandbox_session() == _DEFAULT_SID


def test_legacy_sid_rejected() -> None:
    """S-05 migration 保留 ``_legacy``, S-04 必须拒."""
    with pytest.raises(ValueError, match="reserved"):
        _validate_sid("_legacy")
    with pytest.raises(ValueError, match="reserved"):
        with set_sandbox_session("_legacy"):
            pass


def test_trailing_newline_rejected() -> None:
    """fullmatch 守门: 尾 \\n 必须被拒 (旧 .match 会放过)."""
    with pytest.raises(ValueError):
        _validate_sid("abc\n")
    with pytest.raises(ValueError):
        _validate_sid("\nabc")


# ────────────────────────── data_root 行为矩阵
def test_data_root_prod_when_sandbox_off(tmp_root: Path) -> None:
    """sandbox 关闭 → 无 sid / _default sid / ctx sid 全返 prod (透明中间件).

    显式非 default sid 的 fail-loud 行为见 ``test_data_root_explicit_sid_raises_when_sandbox_off``.
    """
    # 无 sid
    assert data_root.meal_log_path(tmp_root) == (
        tmp_root / "logs" / "meal_log.jsonl"
    )
    # 显式 _default
    assert data_root.meal_log_path(tmp_root, session_id=_DEFAULT_SID) == (
        tmp_root / "logs" / "meal_log.jsonl"
    )
    # ctx 中 sid 也无效 (silent fallback, 透明中间件)
    with set_sandbox_session("xyz"):
        assert data_root.meal_log_path(tmp_root) == (
            tmp_root / "logs" / "meal_log.jsonl"
        )


def test_data_root_default_sid_flat(tmp_root: Path) -> None:
    """sandbox 启用 + sid 默认 → flat (与 D-077 完全一致)."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    base = tmp_root / "logs" / "sandbox"
    assert data_root.meal_log_path(tmp_root) == base / "meal_log.jsonl"
    assert data_root.sessions_dir(tmp_root) == base / "sessions"
    assert data_root.recommend_trace_dir(tmp_root) == base / "recommend_trace"
    # 显式 _default 等同默认
    assert data_root.meal_log_path(
        tmp_root, session_id=_DEFAULT_SID
    ) == base / "meal_log.jsonl"


def test_data_root_explicit_nondefault_sid(tmp_root: Path) -> None:
    """sandbox 启用 + 显式 sid != ``_default`` → ``sessions/{sid}/`` 子树."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    base = tmp_root / "logs" / "sandbox" / "sessions" / "abc"
    assert data_root.meal_log_path(tmp_root, session_id="abc") == (
        base / "meal_log.jsonl"
    )
    assert data_root.recommend_trace_dir(tmp_root, session_id="abc") == (
        base / "recommend_trace"
    )
    # sessions_dir 嵌套 (sandbox sid 内的 D-039 recommend sessions/)
    assert data_root.sessions_dir(tmp_root, session_id="abc") == base / "sessions"


def test_data_root_ctx_sid_nondefault(tmp_root: Path) -> None:
    """sandbox 启用 + ctx sid != ``_default`` → ``sessions/{sid}/`` 子树."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    base = tmp_root / "logs" / "sandbox" / "sessions" / "xyz"
    with set_sandbox_session("xyz"):
        assert data_root.meal_log_path(tmp_root) == base / "meal_log.jsonl"
        assert data_root.feedback_store_path(tmp_root) == (
            base / "feedback" / "store.json"
        )


def test_data_root_explicit_wins_over_ctx(tmp_root: Path) -> None:
    """显式 sid 优先于 ctx sid."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    with set_sandbox_session("ctx_sid"):
        # 显式 explicit_sid 应该胜出
        assert data_root.meal_log_path(
            tmp_root, session_id="explicit_sid"
        ) == (
            tmp_root / "logs" / "sandbox"
            / "sessions" / "explicit_sid" / "meal_log.jsonl"
        )


def test_data_root_profile_path_nondefault_sid(tmp_root: Path) -> None:
    """``profile_path`` 副本: sid != ``_default`` → 嵌套副本路径."""
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    # 没拷贝副本 → 仍 fallback prod
    (tmp_root / "profile.yaml").write_text("methodology: harvard_plate\n", encoding="utf-8")
    assert data_root.profile_path(tmp_root, session_id="abc") == (
        tmp_root / "profile.yaml"
    )
    # 拷副本进 sessions/abc/
    sb_copy = tmp_root / "logs" / "sandbox" / "sessions" / "abc" / "profile.yaml"
    sb_copy.parent.mkdir(parents=True, exist_ok=True)
    sb_copy.write_text("methodology: sandbox\n", encoding="utf-8")
    assert data_root.profile_path(tmp_root, session_id="abc") == sb_copy


# ────────────────────────── threading (v3 守门)
def test_ctx_does_not_leak_into_threads() -> None:
    """文档化: Python ContextVar 默认不跨 threading.Thread.

    守门 — 防意外被"修复". S-06a 真要跨线程必须 ``copy_context().run`` 或
    显式 sid 透传 (见下两条 test).
    """
    captured: dict[str, str | None] = {}

    def _worker() -> None:
        captured["thread_sid"] = current_sandbox_session()

    with set_sandbox_session("outer_sid"):
        assert current_sandbox_session() == "outer_sid"
        t = threading.Thread(target=_worker)
        t.start()
        t.join()
    assert captured["thread_sid"] is None


def test_copy_context_propagates_sid(tmp_root: Path) -> None:
    """S-06a forward guard: ``copy_context().run`` 正确把 sid 带进 thread.

    任何 S-06a wrapper (eat 内串 /recommend → 异步 worker) 必须用这种模式,
    否则 worker 内 ``data_root.*_path`` 会 fallback 到 ``_default`` flat,
    多 tab 并发即串.
    """
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    captured: dict[str, str | Path | None] = {}

    def _worker() -> None:
        captured["sid"] = current_sandbox_session()
        captured["path"] = data_root.meal_log_path(tmp_root)

    with set_sandbox_session("sid_a"):
        ctx = copy_context()
        t = threading.Thread(target=lambda: ctx.run(_worker))
        t.start()
        t.join()

    assert captured["sid"] == "sid_a"
    expected = tmp_root / "logs" / "sandbox" / "sessions" / "sid_a" / "meal_log.jsonl"
    assert captured["path"] == expected


def test_explicit_sid_kwarg_overrides_ctx_for_threading(tmp_root: Path) -> None:
    """S-06a forward guard: 显式 sid kwarg 是另一条合法实现路径.

    worker 收到显式 sid (从请求 closure 捕获) 即可在 thread 内自洽,
    无需 ``copy_context``. 证明 data_root API 支持 "sid 显式参" 模式.
    """
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    captured: dict[str, Path | None] = {}

    def _worker_explicit(sid: str) -> None:
        captured["path"] = data_root.meal_log_path(tmp_root, session_id=sid)

    with set_sandbox_session("sid_a"):
        t = threading.Thread(target=_worker_explicit, args=("sid_b",))
        t.start()
        t.join()

    expected = tmp_root / "logs" / "sandbox" / "sessions" / "sid_b" / "meal_log.jsonl"
    assert captured["path"] == expected


# ────────────────────────── fail-loud (Codex adversarial v3)
def test_data_root_explicit_sid_raises_when_sandbox_off(tmp_root: Path) -> None:
    """显式非 default sid + sandbox 关 → raise RuntimeError (caller bug).

    防"S-06a 带 sid 请求但 sandbox 被中途 reset"导致 silent 写入 prod 路径.
    """
    with pytest.raises(RuntimeError, match="sandbox is disabled"):
        data_root.meal_log_path(tmp_root, session_id="abc")
    with pytest.raises(RuntimeError, match="sandbox is disabled"):
        data_root.recommend_trace_dir(tmp_root, session_id="abc")
    with pytest.raises(RuntimeError, match="sandbox is disabled"):
        data_root.profile_path(tmp_root, session_id="abc")


def test_data_root_default_sid_silent_when_sandbox_off(tmp_root: Path) -> None:
    """显式 _default sid + sandbox 关 → silent 走 prod (legacy 兼容)."""
    assert data_root.meal_log_path(
        tmp_root, session_id=_DEFAULT_SID,
    ) == tmp_root / "logs" / "meal_log.jsonl"


def test_data_root_ctx_sid_silent_when_sandbox_off(tmp_root: Path) -> None:
    """ctx-only sid + sandbox 关 → silent 走 prod (D-077 透明中间件行为)."""
    with set_sandbox_session("ctx_sid"):
        # 没传显式 session_id, 只 ctx 有 → 不 raise, 走 prod
        assert data_root.meal_log_path(tmp_root) == (
            tmp_root / "logs" / "meal_log.jsonl"
        )


def test_sandbox_destructive_api_rejects_nondefault_sid(tmp_root: Path) -> None:
    """init/advance/reset/disable/record_l1_extraction 非 default sid 必 raise.

    防 S-06a 误以为 ``reset(session_id='abc')`` 是 scoped delete 但实际删整树.
    """
    sandbox.init(start_date="2026-05-20", root=tmp_root)

    with pytest.raises(NotImplementedError, match="not yet supported"):
        sandbox.init(start_date="2026-05-20", root=tmp_root, session_id="abc")
    with pytest.raises(NotImplementedError, match="not yet supported"):
        sandbox.advance(days=1, root=tmp_root, session_id="abc")
    with pytest.raises(NotImplementedError, match="not yet supported"):
        sandbox.disable(root=tmp_root, session_id="abc")
    with pytest.raises(NotImplementedError, match="not yet supported"):
        sandbox.record_l1_extraction("ok", root=tmp_root, session_id="abc")
    with pytest.raises(NotImplementedError, match="not yet supported"):
        sandbox.reset(root=tmp_root, session_id="abc")

    # 但 _default / None 都应放过
    sandbox.record_l1_extraction("ok", root=tmp_root, session_id="_default")
    sandbox.record_l1_extraction("ok", root=tmp_root, session_id=None)
    # reset 兜底
    sandbox.reset(root=tmp_root, session_id=None)


def test_sandbox_readonly_api_accepts_any_sid(tmp_root: Path) -> None:
    """state/is_enabled/current_date 等 read-only API 接受任何 sid (forward compat).

    clock.* 透 ctx sid → sandbox.current_date(root, session_id=sid_x) 调用
    必须不 raise, 否则 sandbox 开了之后 clock 全挂.
    """
    sandbox.init(start_date="2026-05-20", root=tmp_root)
    # 这些都不应该 raise
    sandbox.state(root=tmp_root, session_id="anything")
    sandbox.is_enabled(root=tmp_root, session_id="anything")
    sandbox.current_date(root=tmp_root, session_id="anything")
    sandbox.current_datetime(root=tmp_root, session_id="anything")
    sandbox.current_datetime_utc(root=tmp_root, session_id="anything")


# ────────────────────────── clock 透 ctx (S-04 阶段 sandbox 忽略 sid → 等同 D-077)
def test_clock_reads_ctx_sid_but_falls_back_to_global_state(tmp_root: Path) -> None:
    """S-04: clock.today/now/now_utc 透 ctx sid → sandbox.current_date.

    本阶段 sandbox.current_date 忽略 sid (单 state.json), 所以 clock 行为
    完全等同 D-077. S-05 拆 state 后 clock 自动正确.
    """
    from chisha import clock
    import datetime as dt

    sandbox.init(start_date="2026-05-20", root=tmp_root)
    # 无 ctx → 默认 → 读 state.json → 2026-05-20
    assert clock.today(root=tmp_root) == dt.date(2026, 5, 20)
    # 设 ctx sid → S-04 阶段不影响 (state 仍是单文件)
    with set_sandbox_session("future_sid"):
        assert clock.today(root=tmp_root) == dt.date(2026, 5, 20)

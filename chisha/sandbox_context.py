"""Sandbox per-request session context (S-04).

ContextVar-based: 每个 FastAPI 请求 wrapper 用 ``with set_sandbox_session(sid):``
注入, data_root / clock / sandbox 透明读 ctx. 绝不全局可写.

Codex must-fix #1: 包装调用 (eat 内部串 /recommend) 不靠 active.json 全局
切换, 两 tab 并发 eat 不串.

S-04 范围:
- 仅提供 ctx 容器 + sid 校验, 不强制 web_api wrap (那是 S-06a)
- sandbox 关闭时 sid 无意义 → 所有 path helper 直接 prod
- sandbox 启用 + sid 为 None / "_default" → flat 路径 logs/sandbox/{rel}
  (与 D-077 现行行为完全一致 — backward compat, 全部既有测试 zero-touch)
- sandbox 启用 + sid 为非 default → logs/sandbox/sessions/{sid}/{rel} 子树
  (S-05 / S-06a 真用)

线程 / asyncio:
- ContextVar 在同 thread 的 asyncio task 间正确隔离
- 跨 thread (threading.Thread) NOT propagated → 后台 worker (web_api
  ``_trigger_l1_extraction_async``) 拿 None → ``_default`` → flat → 与今天等同
- S-06a 引入 web_api wrapper 时需用 ``contextvars.copy_context()`` 或显式
  sid 透传 — 本任务 ``tests/test_sandbox_context.py::test_copy_context_propagates_sid``
  + ``test_explicit_sid_kwarg_overrides_ctx_for_threading`` 提前守门
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_current_sid: ContextVar[str | None] = ContextVar(
    "sandbox_session_id", default=None
)

# Codex must-fix #5: sid 必须可作文件路径片段, 不能 traversal.
# v3: fullmatch (拒尾 \n), 黑名单 ``_legacy`` (S-05 migrated old data 占用).
_SID_PATTERN = re.compile(r"[a-zA-Z0-9_-]{1,64}")
_DEFAULT_SID = "_default"
_RESERVED_SIDS: frozenset[str] = frozenset({"_legacy"})


def _validate_sid(sid: str) -> str:
    """合法 sid: fullmatch ``^[a-zA-Z0-9_-]{1,64}$`` 且不在 ``_RESERVED_SIDS``.

    白名单: ``_default`` (current flat session).
    黑名单: ``_legacy`` (S-05 migration 保留).
    """
    if sid == _DEFAULT_SID:
        return sid
    if not isinstance(sid, str) or not _SID_PATTERN.fullmatch(sid):
        raise ValueError(
            f"invalid sandbox session_id: {sid!r} "
            f"(must fullmatch {_SID_PATTERN.pattern} or be '_default')"
        )
    if sid in _RESERVED_SIDS:
        raise ValueError(
            f"sandbox session_id {sid!r} is reserved (S-05 migration)"
        )
    return sid


@contextmanager
def set_sandbox_session(sid: str | None) -> Iterator[None]:
    """注入 sid 到 ctx. ``None`` 表示 explicit clear (走 ``_default`` fallback)."""
    if sid is not None:
        _validate_sid(sid)
    token = _current_sid.set(sid)
    try:
        yield
    finally:
        _current_sid.reset(token)


def current_sandbox_session() -> str | None:
    """返当前 ctx 内的 sandbox sid, 无 ctx 时返 ``None``."""
    return _current_sid.get()

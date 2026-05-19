"""D-077 PR-1b: 业务数据路径派生 — sandbox 启用时落 logs/sandbox/.

设计原则 (志丹拍板 #3):
sandbox 关闭时, 所有路径 = prod 默认; 启用时, **业务数据**全部落
logs/sandbox/ 子目录, prod 数据零污染.

7 个落盘点:
| key                  | prod 默认                       | sandbox            |
|----------------------|----------------------------------|---------------------|
| meal_log_path        | logs/meal_log.jsonl             | logs/sandbox/meal_log.jsonl |
| sessions_dir         | logs/sessions/                  | logs/sandbox/sessions/ |
| feedback_store_path  | logs/feedback/store.json        | logs/sandbox/feedback/store.json |
| recommend_log_path   | logs/recommend_log.jsonl        | logs/sandbox/recommend_log.jsonl |
| feedback_history_path | data/feedback_history.jsonl    | logs/sandbox/feedback_history.jsonl |
| long_term_prefs_path | data/long_term_prefs.json       | logs/sandbox/long_term_prefs.json |
| profile_path         | profile.yaml                    | logs/sandbox/profile.yaml (copy-on-init by PR-1c) |

只读数据不动:
- data/{zone}/restaurants.jsonl / tagged_dishes.jsonl (餐厅 / 菜品库)
- profiles/methodologies/*.yaml (方法论 spec 库)
- prompts/*.md

调用约定:
- 所有业务模块走 chisha.data_root.*, 不再 hardcode "logs/meal_log.jsonl"
- 调用方可显式传 root (测试 + 多 worktree 隔离), None 走真实 project root
- profile_path 在 sandbox 启用 + 副本不存在时降级到 prod (copy 失败兜底)

S-04 扩展: session_id 显式参 + ContextVar fallback.
- sandbox 关闭时 sid 不生效, 仍走 prod
- sandbox 启用 + sid 为 None / ContextVar None / "_default" → flat (与 D-077 完全一致)
- sandbox 启用 + sid 为非 default → logs/sandbox/sessions/{sid}/{rel} 子树
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from chisha import sandbox
from chisha.sandbox_context import (
    _DEFAULT_SID,
    _validate_sid,
    current_sandbox_session,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_root(root: Optional[Path]) -> Path:
    return root or _project_root()


def _resolve_sid(session_id: Optional[str]) -> str:
    """显式 > ctx > ``_default``. 返合法 sid."""
    sid = session_id if session_id is not None else current_sandbox_session()
    if sid is None:
        return _DEFAULT_SID
    return _validate_sid(sid)


def _maybe_sandbox(
    root: Path,
    rel_in_sandbox: str,
    rel_in_prod: str,
    session_id: Optional[str] = None,
) -> Path:
    """sandbox 启用时返沙盒路径, 否则 prod.

    S-04:
    - sid == ``_default`` → flat ``logs/sandbox/{rel}`` (与 D-077 完全一致)
    - sid != ``_default`` → 子树 ``logs/sandbox/sessions/{sid}/{rel}`` (S-06a 用)

    Fail-loud (Codex adversarial 高优修复):
    - sandbox 关闭时, 显式非 default ``session_id`` 是 caller bug
      (典型: S-06a 请求带 sid 但 sandbox 已被 reset / disable). 此时 raise
      RuntimeError 而非 silent fallback 到 prod, 防数据串桶到生产路径.
    - ctx-only sid (无显式参) 在 sandbox 关闭时仍 silent fallback 到 prod,
      让 D-077 中间件透明 (legacy 行为不变).
    """
    if not sandbox.is_enabled(root):
        if session_id is not None and session_id != _DEFAULT_SID:
            raise RuntimeError(
                f"data_root: explicit non-default session_id={session_id!r} "
                f"but sandbox is disabled at root={root!r}. "
                f"This is a caller bug — explicit sandbox sid implies sandbox "
                f"must be enabled. (S-04 Codex adversarial fix)"
            )
        return root / rel_in_prod
    sid = _resolve_sid(session_id)
    if sid == _DEFAULT_SID:
        return root / "logs" / "sandbox" / rel_in_sandbox
    return root / "logs" / "sandbox" / "sessions" / sid / rel_in_sandbox


# ────────────────────────── 7 个落盘点
def meal_log_path(
    root: Optional[Path] = None,
    session_id: Optional[str] = None,
) -> Path:
    r = _resolve_root(root)
    return _maybe_sandbox(
        r, "meal_log.jsonl", "logs/meal_log.jsonl", session_id=session_id,
    )


def sessions_dir(
    root: Optional[Path] = None,
    session_id: Optional[str] = None,
) -> Path:
    """D-039 recommend session 文件目录.

    命名冲突 (sandbox sid vs D-039 recommend sid) 已知:
    - sid == ``_default`` (默认): ``logs/sandbox/sessions/`` (flat, 与 D-077 一致)
    - sid != ``_default``: ``logs/sandbox/sessions/{sandbox_sid}/sessions/``
      (嵌套, S-06a 用)
    """
    r = _resolve_root(root)
    return _maybe_sandbox(
        r, "sessions", "logs/sessions", session_id=session_id,
    )


def feedback_store_path(
    root: Optional[Path] = None,
    session_id: Optional[str] = None,
) -> Path:
    r = _resolve_root(root)
    return _maybe_sandbox(
        r, "feedback/store.json", "logs/feedback/store.json",
        session_id=session_id,
    )


def recommend_log_path(
    root: Optional[Path] = None,
    session_id: Optional[str] = None,
) -> Path:
    r = _resolve_root(root)
    return _maybe_sandbox(
        r, "recommend_log.jsonl", "logs/recommend_log.jsonl",
        session_id=session_id,
    )


def feedback_history_path(
    root: Optional[Path] = None,
    session_id: Optional[str] = None,
) -> Path:
    """D-043 deprecated jsonl, 但 bootstrap 脚本仍读. sandbox 也支持."""
    r = _resolve_root(root)
    return _maybe_sandbox(
        r, "feedback_history.jsonl", "data/feedback_history.jsonl",
        session_id=session_id,
    )


def long_term_prefs_path(
    root: Optional[Path] = None,
    session_id: Optional[str] = None,
) -> Path:
    r = _resolve_root(root)
    return _maybe_sandbox(
        r, "long_term_prefs.json", "data/long_term_prefs.json",
        session_id=session_id,
    )


def recommend_trace_dir(
    root: Optional[Path] = None,
    session_id: Optional[str] = None,
) -> Path:
    """D-079: 推荐链路 trace 落盘目录. 一次推荐一个 ``{sid}.json`` 文件.

    sandbox 启用 → ``logs/sandbox/recommend_trace/`` (默认 ``_default`` flat) 或
    ``logs/sandbox/sessions/{sid}/recommend_trace/`` (非 default sid), prod →
    ``logs/recommend_trace/``. 复用 ``_maybe_sandbox`` 模式.
    """
    r = _resolve_root(root)
    return _maybe_sandbox(
        r, "recommend_trace", "logs/recommend_trace",
        session_id=session_id,
    )


def profile_path(
    root: Optional[Path] = None,
    session_id: Optional[str] = None,
) -> Path:
    """sandbox 启用且副本存在时返沙盒副本; 否则 prod ``profile.yaml``.

    PR-1c sandbox init(copy_real_data=True) 时把 prod profile.yaml 拷贝
    到 ``logs/sandbox/profile.yaml``. 启用 sandbox 但用户没 copy → 仍读 prod
    (只读用例 ok); 用户在 sandbox 内 PUT profile → 写 sandbox 副本.

    S-04: sid != ``_default`` 时副本路径 ``logs/sandbox/sessions/{sid}/profile.yaml``;
    默认 sid 副本路径 ``logs/sandbox/profile.yaml`` (与 D-077 一致).
    """
    r = _resolve_root(root)
    if sandbox.is_enabled(r):
        sid = _resolve_sid(session_id)
        if sid == _DEFAULT_SID:
            sandboxed = r / "logs" / "sandbox" / "profile.yaml"
        else:
            sandboxed = (
                r / "logs" / "sandbox" / "sessions" / sid / "profile.yaml"
            )
        if sandboxed.exists():
            return sandboxed
    elif session_id is not None and session_id != _DEFAULT_SID:
        # Fail-loud (Codex adversarial): 显式非 default sid + sandbox 关 = caller bug
        raise RuntimeError(
            f"profile_path: explicit non-default session_id={session_id!r} "
            f"but sandbox is disabled at root={r!r}. (S-04 Codex adversarial fix)"
        )
    return r / "profile.yaml"

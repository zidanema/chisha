"""D-077: Sandbox time-travel 模式 · state 管理 + 虚拟时钟.

设计 (志丹拍板):
- 真实交互优先: sandbox 是 user web 的 mode, 不是 CLI 替代
- 行为完全一致: 真实端点 / 真实 L3 LLM, 不阉割
- 仅在两处与 prod 隔离: (a) 数据落盘根 (b) 虚拟时钟
- 沉淀可见: inspect 端点暴露 L1 prefs
- 一键回到干净状态: reset 不留痕

State 落盘: <state_root>/logs/sandbox/state.json (state_root 经 D-102 解析, 默认 ~/.chisha)
{
  "enabled": true,
  "current_date": "2026-05-18",
  "day_index": 1,
  "started_at_real": "2026-05-16T15:00:00",
  "started_at_virtual": "2026-05-18",
  "last_l1_extraction": {                    # PR-1c 由 advance 写入
    "at": "2026-05-18T08:00:00",
    "status": "ok" | "failed" | "pending",
    "based_on_meals": int,
    "error": str | None
  }
}

并发:
- 单用户单进程, FastAPI sync 端点, 不会并发
- 但多 tab 可能并发 advance/reset, 走 threading.Lock 防 race

设计约束:
- sandbox 关闭时 current_date()/current_datetime() 返 None, clock.* 降级到真实时间
- profile.yaml 在 sandbox 内不动 (按需拷贝到 logs/sandbox/profile.yaml)
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any


_STATE_REL = "logs/sandbox/state.json"
_SANDBOX_DIR_REL = "logs/sandbox"
_META_REL = "logs/sandbox/_meta.json"  # S-05: layout schema marker
_SESSIONS_DIR_REL = "logs/sandbox/sessions"  # S-06a: sandbox 非 default 桶目录

# 线程锁: 单进程内防 advance / reset 并发互写
_STATE_LOCK = threading.Lock()


# destructive / mutating API 必须 fail-loud: init/advance/reset/disable/
# record_l1_extraction 都是全局副作用. 接受非 default sid 会让 caller 误以为是
# scoped 操作; per-session 改写走 advance_meal/create_session.
def _reject_nondefault_sid(api: str, sid: object) -> None:
    """这些全局副作用 API 不接受非 default sid."""
    if sid is None:
        return
    if sid == "_default":
        return
    raise NotImplementedError(
        f"sandbox.{api}(session_id={sid!r}) is not yet supported in S-04 "
        f"(state.json is still a single global file). S-05 will add "
        f"per-session state. Pass session_id=None or '_default' for now."
    )


def _project_root() -> Path:
    from chisha import state_root
    return state_root.project_root()


def _state_base(root: Path | None = None) -> Path:
    """D-102 Step2: sandbox 也是 user state → 经 state_root 解析 (与 data_root 同源).

    Commit A: state_root.default 仍 = 包目录 → 0-diff. Commit B 翻 ~/.chisha + 迁移.
    保证 sandbox marker / 数据与 data_root 落盘点同根 (否则 enable 写一处、读另一处 split brain).
    """
    from chisha import state_root
    return state_root.resolve(root)


def _state_path(root: Path | None = None) -> Path:
    return _state_base(root) / _STATE_REL


def _sandbox_dir(root: Path | None = None) -> Path:
    return _state_base(root) / _SANDBOX_DIR_REL


def has_sandbox_meta(root: Path | None = None) -> bool:
    """S-05: 检测 ``_meta.json`` 是否存在 (migration 已跑过).

    本任务内仅给 test + future S-06a 用, **不进 path 决策链**.
    ``is_enabled()`` 仍走 ``state.json`` (D-077 语义).
    """
    return (_state_base(root) / _META_REL).exists()


def state(
    root: Path | None = None,
    *,
    session_id: str | None = None,
) -> dict:
    """读 state. 未 init / 文件不存在 / 已 reset → {enabled: False}.

    损坏 → 视为 disabled (派生数据 fail-open, 与 l1_prefs 风格一致)

    仅读 default 扁平 ``state.json``, 不消费 sid; sid-aware 读盘走
    ``_state_path_for_sid`` / ``advance_meal``.
    """
    del session_id  # S-04 stub: implementation ignores sid
    p = _state_path(root)
    if not p.exists():
        return {"enabled": False}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False}
    if not isinstance(data, dict):
        return {"enabled": False}
    return data


def is_enabled(
    root: Path | None = None,
    *,
    session_id: str | None = None,
) -> bool:
    """S-04: ``session_id`` 签名预留, 实现忽略 (单 state.json)."""
    return bool(state(root, session_id=session_id).get("enabled"))


def current_date(
    root: Path | None = None,
    *,
    session_id: str | None = None,
) -> dt.date | None:
    """S-04: ``session_id`` 签名预留, 实现忽略 (单 state.json)."""
    s = state(root, session_id=session_id)
    if not s.get("enabled"):
        return None
    raw = s.get("current_date")
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def current_datetime(
    root: Path | None = None,
    *,
    session_id: str | None = None,
) -> dt.datetime | None:
    """虚拟 datetime: 取 sandbox date + 真实 wall-clock 时分秒.

    设计: 沙盒推进按"日"为粒度, 时分秒沿用真机, 让 snooze (24h)、session
    TTL (24h) 等小时级行为仍可观察 (用户点 advance 后立即推荐, datetime
    的 hour 部分相对真实时间不变, 但 date 部分已跳到虚拟日).

    Returns: aware datetime (local naive 兼容旧 dt.datetime.now() 行为) 或 None.

    S-04: ``session_id`` 签名预留, 实现忽略.
    """
    d = current_date(root, session_id=session_id)
    if d is None:
        return None
    now_real = dt.datetime.now()
    return dt.datetime.combine(d, now_real.time())


def current_datetime_utc(
    root: Path | None = None,
    *,
    session_id: str | None = None,
) -> dt.datetime | None:
    """虚拟 UTC datetime: 沙盒 date + 真实 UTC 时分秒. aware tz=UTC.

    S-04: ``session_id`` 签名预留, 实现忽略.
    """
    d = current_date(root, session_id=session_id)
    if d is None:
        return None
    now_utc = dt.datetime.now(dt.timezone.utc)
    return dt.datetime.combine(d, now_utc.time(), tzinfo=dt.timezone.utc)


def _now_real_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def init(
    start_date: dt.date | str | None = None,
    *,
    root: Path | None = None,
    copy_real_data: bool = False,
    session_id: str | None = None,
) -> dict:
    """开启 sandbox 模式. start_date 默认 = 真实 today.

    copy_real_data=True 时由 PR-1b 的 data_root 帮忙拷贝 prod 数据到
    sandbox root; 本模块只管 state, 不操作业务数据.

    返回新 state.
    """
    _reject_nondefault_sid("init", session_id)
    if isinstance(start_date, str):
        start_date = dt.date.fromisoformat(start_date)
    start_date = start_date or dt.date.today()

    with _STATE_LOCK:
        sandbox_dir = _sandbox_dir(root)
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        new_state = {
            "enabled": True,
            "current_date": start_date.isoformat(),
            "day_index": 1,
            "started_at_real": _now_real_iso(),
            "started_at_virtual": start_date.isoformat(),
            "copy_real_data": copy_real_data,
            "last_l1_extraction": None,
        }
        _state_path(root).write_text(
            json.dumps(new_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # S-06a 修订 B: ensure layout-v2 _meta.json so post-init flows
        # (POST /sessions, /sandbox/inspect 三态) 看到 coherent v2 layout.
        # 幂等: 若 migration 已写 schema_version=2 则不覆盖.
        from chisha import sandbox_migration as _sm
        if not _sm.read_meta(_state_base(root)):
            _sm._atomic_write_meta(
                _state_base(root),
                {
                    "schema_version": _sm.SCHEMA_VERSION,
                    "created_at": _now_real_iso(),
                    "default_layout": "flat",
                    "relocated_legacy": False,
                    "created_by": "sandbox.init",
                },
            )
        return new_state


# ---------- S-06a: sessions CRUD (module-level helpers) ----------

def _sessions_root(root: Path | None = None) -> Path:
    return _state_base(root) / _SESSIONS_DIR_REL


def list_sessions(root: Path | None = None) -> list[dict]:
    """S-06a: 列出 sandbox 桶 (含 default, 不含 _legacy / D-039 .json 文件 /
    非法 sid 目录名).

    Default 桶永远首位; 非 default 桶按 sid 字典序.

    返回 dict shape (web 层包装成 SandboxSessionMeta):
      sid / is_default / created_at / size_bytes / has_state
    """
    from chisha.sandbox_context import _validate_sid as _vs, _RESERVED_SIDS
    items: list[dict] = []

    # default 桶
    state_p = _state_path(root)
    default_created: str | None = None
    if state_p.exists():
        try:
            st = json.loads(state_p.read_text(encoding="utf-8"))
            if isinstance(st, dict):
                default_created = st.get("started_at_real")
        except (OSError, json.JSONDecodeError):
            default_created = None
    if default_created is None:
        # fall back to _meta.json created_at
        from chisha import sandbox_migration as _sm
        m = _sm.read_meta(_state_base(root))
        if m:
            default_created = m.get("created_at")
    default_size = _dir_size_safe(_sandbox_dir(root), exclude_subdir="sessions")
    items.append({
        "sid": "_default",
        "is_default": True,
        "created_at": default_created,
        "size_bytes": default_size,
        "has_state": state_p.exists(),
    })

    # 非 default 桶
    sroot = _sessions_root(root)
    if sroot.exists():
        try:
            entries = sorted(sroot.iterdir(), key=lambda p: p.name)
        except OSError:
            entries = []
        for entry in entries:
            if not entry.is_dir():
                continue  # 跳 .json (D-039 default 桶产物)
            sid = entry.name
            if sid in _RESERVED_SIDS:
                continue  # _legacy
            try:
                _vs(sid)
            except ValueError:
                continue  # 非法 sid 目录名
            items.append({
                "sid": sid,
                "is_default": False,
                "created_at": _entry_ctime_iso(entry),
                "size_bytes": _dir_size_safe(entry),
                "has_state": (entry / "state.json").exists(),  # S-06c 修订 A
            })
    return items


def _dir_size_safe(p: Path, *, exclude_subdir: str | None = None) -> int:
    """递归算目录总大小, IO 错回 0. exclude_subdir 用于 default 桶 size 排除
    sessions/ 子树 (避免把非 default 桶大小也算进 default)."""
    if not p.exists():
        return 0
    total = 0
    try:
        for child in p.iterdir():
            try:
                if exclude_subdir is not None and child.name == exclude_subdir:
                    continue
                if child.is_dir():
                    total += _dir_size_safe(child)
                elif child.is_file():
                    total += child.stat().st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


def _entry_ctime_iso(p: Path) -> str | None:
    try:
        ts = p.stat().st_ctime
        return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()
    except OSError:
        return None


def create_session(
    sid: str,
    *,
    root: Path | None = None,
    days: int = 7,
    start_date: dt.date | str | None = None,
    seed_state: bool = True,
) -> dict:
    """S-06a + S-06c 修订 A: 创建非 default sandbox 桶, 默认 seed state.json.

    seed_state=True (默认) 时, mkdir 后写入 state.json (enabled=True,
    current_meal_idx=0, total_meals=days*2, current_date, day_index=1,
    started_at_real, started_at_virtual, sid). 这是 production 流程的默认行为
    (POST /api/sandbox/sessions 创建桶后 /recs /eat 立即能用).

    seed_state=False 仅供测试 caller 手工 mkdir + 写 state.json 验证 path 隔离.

    失败: ValueError (reserved/无效) / FileExistsError (已存在).
    """
    from chisha.sandbox_context import _validate_sid as _vs, _DEFAULT_SID
    if sid == _DEFAULT_SID:
        raise ValueError(f"sandbox session_id {sid!r} is reserved (default bucket)")
    _vs(sid)
    if days < 1:
        raise ValueError(f"days must be >= 1, got {days}")
    sroot = _sessions_root(root)
    sroot.mkdir(parents=True, exist_ok=True)
    bucket = sroot / sid
    try:
        bucket.mkdir(parents=False, exist_ok=False)
    except FileExistsError:
        raise FileExistsError(f"sandbox session_id={sid!r} already exists")

    if seed_state:
        if isinstance(start_date, str):
            start_date = dt.date.fromisoformat(start_date)
        start_date = start_date or dt.date.today()
        state_p = bucket / "state.json"
        seeded = {
            "enabled": True,
            "current_date": start_date.isoformat(),
            "day_index": 1,
            "current_meal_idx": 0,
            "total_meals": days * 2,
            "started_at_real": _now_real_iso(),
            "started_at_virtual": start_date.isoformat(),
            "sid": sid,
        }
        state_p.write_text(
            json.dumps(seeded, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return {
        "sid": sid,
        "is_default": False,
        "created_at": _entry_ctime_iso(bucket),
        "size_bytes": _dir_size_safe(bucket),
        "has_state": seed_state,
    }


def delete_session(sid: str, *, root: Path | None = None) -> dict:
    """S-06a: 删除非 default sandbox 桶. 失败: ValueError (default/无效) /
    FileNotFoundError (不存在)."""
    from chisha.sandbox_context import _validate_sid as _vs, _DEFAULT_SID
    if sid == _DEFAULT_SID:
        raise ValueError("default sandbox bucket cannot be deleted")
    _vs(sid)
    bucket = _sessions_root(root) / sid
    if not bucket.is_dir():
        raise FileNotFoundError(f"sandbox session_id={sid!r} not found")
    import shutil
    shutil.rmtree(bucket)
    return {"ok": True, "deleted_sid": sid}


def rename_session(
    old_sid: str, new_sid: str, *, root: Path | None = None,
) -> dict:
    """S-06a: rename 非 default sandbox 桶 (同 fs 原子). 失败:
    - ValueError: old/new 是 default / 不合法 / 同名
    - FileNotFoundError: 老桶不存在
    - FileExistsError: 新桶已存在
    - OSError(EXDEV): 跨 fs (caller 应 500)
    """
    from chisha.sandbox_context import _validate_sid as _vs, _DEFAULT_SID
    if old_sid == _DEFAULT_SID:
        raise ValueError("default sandbox bucket cannot be renamed (old)")
    if new_sid == _DEFAULT_SID:
        raise ValueError("default sandbox bucket cannot be renamed (new)")
    _vs(old_sid)
    _vs(new_sid)
    if old_sid == new_sid:
        raise ValueError(f"rename no-op: old_sid == new_sid == {old_sid!r}")
    sroot = _sessions_root(root)
    old_dir = sroot / old_sid
    new_dir = sroot / new_sid
    if not old_dir.is_dir():
        raise FileNotFoundError(f"sandbox session_id={old_sid!r} not found")
    if new_dir.exists():
        raise FileExistsError(f"sandbox session_id={new_sid!r} already exists")
    import os as _os
    _os.rename(old_dir, new_dir)  # 同 fs 原子; 跨 fs 抛 OSError(EXDEV)
    return {
        "sid": new_sid,
        "is_default": False,
        "created_at": _entry_ctime_iso(new_dir),
        "size_bytes": _dir_size_safe(new_dir),
        "has_state": (new_dir / "state.json").exists(),  # S-06c 修订 N4
    }


# ---------- S-06b: per-meal 时钟 helper ----------

from typing import Literal as _Literal


def meal_idx_to_slot(idx: int) -> tuple[_Literal["lunch", "dinner"], int]:
    """S-06b: idx 0-based → (meal_type, day_index 1-based).

    idx=0 → ("lunch", 1); idx=1 → ("dinner", 1); idx=2 → ("lunch", 2);
    idx=13 → ("dinner", 7) (7 天 × 2 顿 = 14 餐位, 合法 idx ∈ [0, 13]).

    注: total_meals=14 是 done sentinel (idx=14 表示全部消费完, 但
    meal_idx_to_slot 仅对 [0, 13] 有效, 调用方须自行处理 done 终态).
    """
    if idx < 0:
        raise ValueError(f"meal_idx must be >= 0, got {idx}")
    day = idx // 2 + 1
    meal_type: _Literal["lunch", "dinner"] = "lunch" if idx % 2 == 0 else "dinner"
    return (meal_type, day)


def _state_path_for_sid(sid: str | None, root: Path | None = None) -> Path:
    """S-06b 修订 A: sid-aware state.json path. **不**依赖 ContextVar.

    - sid is None / "_default" → ``logs/sandbox/state.json`` (default 扁平, D-077)
    - 非 default sid → ``logs/sandbox/sessions/{sid}/state.json``

    本 helper 仅供 ``advance_meal`` 用. 既有 ``state()`` / ``_state_path()`` 不动
    (S-04 stub 沿用; S-06c 决定是否统一 sid-aware 化).
    """
    from chisha.sandbox_context import _DEFAULT_SID
    if sid is None or sid == _DEFAULT_SID:
        return _state_path(root)
    return _sessions_root(root) / sid / "state.json"


def advance_meal(
    *,
    sid: str | None = None,
    root: Path | None = None,
) -> dict:
    """S-06b: 推进单顿 (current_meal_idx++). dinner→next-lunch 时 day+date+=1.

    与既有 ``advance(days=N)`` 区别: advance 整天跳跃 (整 day_index += days),
    advance_meal 单顿粒度. S-06c eat/skip 端点用本函数, reset 后新建仍用 init().

    sid:
    - None 或 "_default" → 操作 default 扁平桶 ``logs/sandbox/state.json``
    - 非 default sid → 操作 ``logs/sandbox/sessions/{sid}/state.json``

    路径派生用 ``_state_path_for_sid``, 不依赖 ContextVar.

    Raises:
        RuntimeError: sandbox 未 enabled / state 文件损坏 / new_idx > total_meals
        ValueError: sid 不合法 (隐式 — 桶目录不存在时 state_p.exists()=False raise)

    Note: total_meals 是 done sentinel, idx ∈ [0, total_meals]. 即
    total_meals=14 时 idx 可达 14 (done 终态); idx=15 触发 raise.
    meal_idx_to_slot 调用方须自行处理 idx == total_meals 的终态.
    """
    state_p = _state_path_for_sid(sid, root)
    with _STATE_LOCK:
        if not state_p.exists():
            raise RuntimeError(
                f"sandbox state not found at {state_p}; call init() first"
            )
        try:
            s = json.loads(state_p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(f"sandbox state corrupt at {state_p}: {e}")
        if not isinstance(s, dict) or not s.get("enabled"):
            raise RuntimeError("sandbox not enabled; call init() first")
        cur_idx = int(s.get("current_meal_idx", 0))
        total = int(s.get("total_meals", 14))
        new_idx = cur_idx + 1
        if new_idx > total:
            raise RuntimeError(
                f"meal_idx {new_idx} exceeds total {total}"
            )
        s["current_meal_idx"] = new_idx
        if cur_idx % 2 == 1:  # was dinner → 跨天到下一个 lunch
            cur_date = dt.date.fromisoformat(s["current_date"])
            s["current_date"] = (cur_date + dt.timedelta(days=1)).isoformat()
            s["day_index"] = int(s.get("day_index", 1)) + 1
        state_p.write_text(
            json.dumps(s, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return s


# ---------- S-04: advance (整天跳跃, 保留 D-077 行为) ----------


def advance(
    days: int = 1,
    *,
    root: Path | None = None,
    session_id: str | None = None,
) -> dict:
    """虚拟时钟前进 N 天. sandbox 必须已 enabled, 否则抛 RuntimeError.

    不直接触发 L1 抽取 (PR-1c 在 web 端点层做异步 trigger). 本函数纯 state.

    S-04: ``session_id`` 签名预留, 实现忽略 (单 state.json).
    """
    _reject_nondefault_sid("advance", session_id)
    if days < 1:
        raise ValueError(f"days must be >= 1, got {days}")
    with _STATE_LOCK:
        s = state(root)
        if not s.get("enabled"):
            raise RuntimeError("sandbox not enabled; call init() first")
        cur = dt.date.fromisoformat(s["current_date"])
        new_date = cur + dt.timedelta(days=days)
        s["current_date"] = new_date.isoformat()
        s["day_index"] = int(s.get("day_index", 1)) + days
        s["last_advance_at_real"] = _now_real_iso()
        _state_path(root).write_text(
            json.dumps(s, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return s


def reset(
    *,
    root: Path | None = None,
    session_id: str | None = None,
) -> dict:
    """删 sandbox 全部数据 + state. prod 数据零风险.

    清理 logs/sandbox/ 整个目录 (含 state + 所有派生 meal_log / feedback /
    prefs / sessions / sessions/{sid}/ 子树).

    S-04: ``session_id`` 签名预留, 实现忽略 (一刀切整个 sandbox 目录).
    Codex adversarial fix: 非 default sid raise — 防 caller 以为 scoped delete.
    """
    _reject_nondefault_sid("reset", session_id)
    import shutil
    with _STATE_LOCK:
        d = _sandbox_dir(root)
        if d.exists():
            shutil.rmtree(d)
        return {"ok": True, "reset_at": _now_real_iso()}


def disable(
    *,
    root: Path | None = None,
    session_id: str | None = None,
) -> dict:
    """退出 sandbox 但保留数据 (与 reset 区分). state.enabled=False, 文件保留.

    S-04: ``session_id`` 签名预留, 实现忽略 (单 state.json).
    """
    _reject_nondefault_sid("disable", session_id)
    with _STATE_LOCK:
        s = state(root)
        if not s.get("enabled"):
            return s
        s["enabled"] = False
        s["disabled_at_real"] = _now_real_iso()
        _state_path(root).write_text(
            json.dumps(s, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return s


def record_l1_extraction(
    status: str,
    *,
    based_on_meals: int | None = None,
    error: str | None = None,
    root: Path | None = None,
    session_id: str | None = None,
) -> None:
    """PR-1c 端点用: advance 后异步抽取完成时落 last_l1_extraction 字段.

    status ∈ {"pending", "ok", "failed", "skipped"}.

    S-04: ``session_id`` 签名预留, 实现忽略 (单 state.json).
    """
    _reject_nondefault_sid("record_l1_extraction", session_id)
    with _STATE_LOCK:
        s = state(root)
        if not s.get("enabled"):
            return  # 已关闭, 不写
        s["last_l1_extraction"] = {
            "at": _now_real_iso(),
            "status": status,
            "based_on_meals": based_on_meals,
            "error": error,
        }
        _state_path(root).write_text(
            json.dumps(s, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ───────────── D-104 Step2/3: extras → core provider 注册 (单向 extras→core) ─────────────
# sandbox 是 extras: 一被 import (web_api / debug_server / sandbox-lab 后端, 或 agent_cli
# 的 guard lazy import) 就把虚拟时钟 + real sandbox router 注册进 core 的 ambient provider,
# 让这些进程的 clock / data_root 透明路由到沙盒。agent-only core / slim 进程永不 import
# sandbox → 永远用 core 默认 (真实时间 + router=False), 0-diff。模块只 import 一次 → 幂等。
from chisha import clock_provider as _clock_provider  # noqa: E402
from chisha import sandbox_router as _sandbox_router  # noqa: E402
from chisha.sandbox_context import current_sandbox_session as _current_sid  # noqa: E402


class _VirtualClockProvider:
    """复刻旧 clock 语义: sandbox 启用→虚拟时间, 否则 None → 真实时间 fallback。"""

    def today(self, root=None) -> dt.date:
        v = current_date(root, session_id=_current_sid())
        return v if v is not None else dt.date.today()

    def now(self, root=None) -> dt.datetime:
        v = current_datetime(root, session_id=_current_sid())
        return v if v is not None else dt.datetime.now()

    def now_utc(self, root=None) -> dt.datetime:
        v = current_datetime_utc(root, session_id=_current_sid())
        return v if v is not None else dt.datetime.now(dt.timezone.utc)


class _RealSandboxRouter:
    def is_enabled(self, root=None) -> bool:
        return is_enabled(root)


_clock_provider.set_clock_provider(_VirtualClockProvider())
_sandbox_router.set_sandbox_router(_RealSandboxRouter())

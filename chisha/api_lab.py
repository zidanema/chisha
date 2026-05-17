"""Lab API (D-085) — `/api/lab/*` 端点, trace 查询 + sandbox + what_if + debug 工具.

边界 (refactor_living_lab.md §5):
- **完全只读真实数据** — 不能写真实反馈; sandbox 写入只走 sandbox 分支 (data_root 隔离)
- Living 不调 Lab; Lab 内部 URL 路径都挂 /api/lab/ 前缀, 与 Living /api/* 物理隔离

端点清单 (重构前路径 → 新路径):
- GET  /api/debug/sessions          → GET  /api/lab/sessions
- GET  /api/debug/sessions/{sid}    → GET  /api/lab/sessions/{sid}
- POST /api/debug/what_if           → POST /api/lab/what_if
- POST /api/sandbox/init            → POST /api/lab/sandbox/init
- POST /api/sandbox/advance         → POST /api/lab/sandbox/advance
- POST /api/sandbox/reset           → POST /api/lab/sandbox/reset
- POST /api/sandbox/disable         → POST /api/lab/sandbox/disable
- GET  /api/sandbox/state           → GET  /api/lab/sandbox/state
- GET  /api/sandbox/inspect         → GET  /api/lab/sandbox/inspect
- POST /api/debug_recommend         → POST /api/lab/debug_recommend
- POST /api/compare_moods           → POST /api/lab/compare_moods
"""
from __future__ import annotations

import datetime as dt
import threading as _threading
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from chisha import feedback_store
from chisha import sandbox as _sandbox
from chisha.recall import load_meal_log

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "profile.yaml"


def _profile_path() -> Path:
    """D-077 PR-1c: 动态求值. sandbox 启用且有副本 → sandbox/profile.yaml; 否则 prod."""
    from chisha import data_root
    return data_root.profile_path(ROOT)


router = APIRouter(prefix="/api/lab", tags=["lab"])


# ---------- localhost / admin guards ----------

_LOCALHOST_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _is_localhost(request: Request) -> bool:
    if request.client is None:
        return False
    return request.client.host in _LOCALHOST_HOSTS


def _require_localhost(request: Request) -> None:
    if not _is_localhost(request):
        raise HTTPException(403, "lab endpoints are localhost-only")


# ============================================================
# /api/lab/debug_recommend + /compare_moods (D-039 老调试台后端)
# ============================================================

class DebugRecommendReq(BaseModel):
    meal_type: str = "lunch"
    daily_mood: str | None = None
    use_llm_rerank: bool | None = None
    profile_overrides: dict[str, Any] | None = None
    today: str | None = None              # YYYY-MM-DD
    trace_target: dict[str, Any] | None = None
    n_return: int = Field(default=5, ge=1, le=20)
    n_explore: int = Field(default=2, ge=0, le=10)


class CompareMoodsReq(BaseModel):
    moods: list[str] = Field(
        default_factory=lambda: ["want_light", "want_soup", "want_indulgent"],
        min_length=1, max_length=8,
    )
    meal_type: str = "lunch"
    profile_overrides: dict[str, Any] | None = None
    use_llm_rerank: bool | None = None
    today: str | None = None


def _parse_today(today: str | None) -> Optional[dt.date]:
    """非法 YYYY-MM-DD → 400 而不是 500 (Codex review LOW)."""
    if not today:
        return None
    try:
        return dt.date.fromisoformat(today)
    except ValueError:
        raise HTTPException(400, f"today must be YYYY-MM-DD, got {today!r}")


@router.post("/debug_recommend")
def api_debug_recommend(req: DebugRecommendReq) -> dict:
    from chisha.debug_recommend import debug_recommend
    return debug_recommend(
        meal_type=req.meal_type,
        daily_mood=req.daily_mood,
        use_llm_rerank=req.use_llm_rerank,
        profile_overrides=req.profile_overrides,
        today=_parse_today(req.today),
        trace_target=req.trace_target,
        n_return=req.n_return,
        n_explore=req.n_explore,
    )


@router.post("/compare_moods")
def api_compare_moods(req: CompareMoodsReq) -> dict:
    from chisha.debug_recommend import compare_moods
    return compare_moods(
        moods=req.moods,
        meal_type=req.meal_type,
        profile_overrides=req.profile_overrides,
        use_llm_rerank=req.use_llm_rerank,
        today=_parse_today(req.today),
    )


# ============================================================
# /api/lab/sandbox/* (D-077 PR-1c)
# ============================================================

# D-077 Codex S3: L1 抽取串行锁. trylock 模式.
_L1_EXTRACTION_LOCK = _threading.Lock()
_L1_LOCK_WAIT_SECONDS = 30.0


class SandboxInitReq(BaseModel):
    start_date: str | None = None      # ISO date YYYY-MM-DD
    copy_real_data: bool = False


class SandboxAdvanceReq(BaseModel):
    days: int = Field(default=1, ge=1, le=30)


def _copy_real_data_to_sandbox(root: Path) -> None:
    """init(copy_real_data=True) 时把 prod 业务数据复制到 sandbox 子树."""
    import shutil
    sandbox_dir = root / "logs" / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    if (root / "profile.yaml").exists():
        shutil.copy2(root / "profile.yaml", sandbox_dir / "profile.yaml")

    prod_meal_log = root / "logs" / "meal_log.jsonl"
    if prod_meal_log.exists():
        shutil.copy2(prod_meal_log, sandbox_dir / "meal_log.jsonl")

    prod_feedback_store = root / "logs" / "feedback" / "store.json"
    if prod_feedback_store.exists():
        (sandbox_dir / "feedback").mkdir(parents=True, exist_ok=True)
        shutil.copy2(prod_feedback_store, sandbox_dir / "feedback" / "store.json")

    prod_history = root / "data" / "feedback_history.jsonl"
    if prod_history.exists():
        shutil.copy2(prod_history, sandbox_dir / "feedback_history.jsonl")

    prod_prefs = root / "data" / "long_term_prefs.json"
    if prod_prefs.exists():
        shutil.copy2(prod_prefs, sandbox_dir / "long_term_prefs.json")

    prod_recommend_log = root / "logs" / "recommend_log.jsonl"
    if prod_recommend_log.exists():
        shutil.copy2(prod_recommend_log, sandbox_dir / "recommend_log.jsonl")


def _trigger_l1_extraction_async(root: Path) -> None:
    """后台抽取 L1 prefs. trylock 模式: 已有 worker 跑时跳过."""
    if not _L1_EXTRACTION_LOCK.acquire(blocking=False):
        return

    def _worker():
        try:
            _sandbox.record_l1_extraction("pending", root=root)
            try:
                store = feedback_store.load_store(root)
            except Exception as e:
                _sandbox.record_l1_extraction("failed", error=str(e), root=root)
                return
            try:
                profile_dict = yaml.safe_load(
                    _profile_path().read_text(encoding="utf-8")
                ) or {}
            except Exception as e:
                _sandbox.record_l1_extraction("failed", error=str(e), root=root)
                return
            try:
                from chisha.l1_extractor import extract_and_save
                prefs = extract_and_save(
                    store, profile_dict,
                    root=root, window_days=14,
                    profile_llm=profile_dict.get("llm"),
                )
                _sandbox.record_l1_extraction(
                    "ok",
                    based_on_meals=prefs.get("based_on_meals", 0),
                    root=root,
                )
            except Exception as e:
                _sandbox.record_l1_extraction("failed", error=str(e), root=root)
        finally:
            _L1_EXTRACTION_LOCK.release()

    t = _threading.Thread(target=_worker, daemon=True)
    t.start()


def _block_until_l1_idle_or_409(action_label: str) -> None:
    """D-078 Codex S2 Q3-High: reset/disable 期间阻塞 L1 worker."""
    if _L1_EXTRACTION_LOCK.acquire(timeout=_L1_LOCK_WAIT_SECONDS):
        _L1_EXTRACTION_LOCK.release()
        return
    raise HTTPException(
        409, f"{action_label} blocked: L1 extraction worker busy >"
              f" {_L1_LOCK_WAIT_SECONDS:.0f}s, retry shortly"
    )


@router.post("/sandbox/init")
def api_sandbox_init(request: Request, req: SandboxInitReq) -> dict:
    """开启 sandbox 模式. 默认 start_date = 真实 today, 空数据."""
    _require_localhost(request)
    s = _sandbox.init(
        start_date=req.start_date,
        root=ROOT,
        copy_real_data=req.copy_real_data,
    )
    if req.copy_real_data:
        try:
            _copy_real_data_to_sandbox(ROOT)
        except Exception as e:
            raise HTTPException(500, f"copy_real_data failed: {type(e).__name__}: {e}")
    return s


@router.post("/sandbox/advance")
def api_sandbox_advance(request: Request, req: SandboxAdvanceReq) -> dict:
    """虚拟时钟前进 N 天, 异步触发 L1 抽取."""
    _require_localhost(request)
    st = _sandbox.state(root=ROOT)
    if (st.get("last_l1_extraction") or {}).get("status") == "pending":
        raise HTTPException(
            409, "advance blocked: L1 extraction in progress, retry after settle"
        )
    try:
        s = _sandbox.advance(days=req.days, root=ROOT)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    _trigger_l1_extraction_async(ROOT)
    return s


@router.post("/sandbox/reset")
def api_sandbox_reset(request: Request) -> dict:
    """删干净 sandbox 目录, prod 零风险."""
    _require_localhost(request)
    _block_until_l1_idle_or_409("reset")
    return _sandbox.reset(root=ROOT)


@router.post("/sandbox/disable")
def api_sandbox_disable(request: Request) -> dict:
    """退出 sandbox 但保留数据."""
    _require_localhost(request)
    _block_until_l1_idle_or_409("disable")
    return _sandbox.disable(root=ROOT)


@router.get("/sandbox/state")
def api_sandbox_state(request: Request) -> dict:
    _require_localhost(request)
    return _sandbox.state(root=ROOT)


@router.get("/sandbox/inspect")
def api_sandbox_inspect(request: Request) -> dict:
    """沉淀状态: 当前 L1 prefs + 最近反馈 + 最近 meal_log."""
    _require_localhost(request)
    if not _sandbox.is_enabled(ROOT):
        return {"enabled": False}

    state = _sandbox.state(root=ROOT)

    from chisha.l1_prefs import load_prefs
    from chisha import data_root as _data_root
    prefs = load_prefs(root=ROOT) or {}
    prefs_raw: dict | None = None
    try:
        prefs_path = _data_root.long_term_prefs_path(ROOT)
        if prefs_path.exists():
            import json as _json
            prefs_raw = _json.loads(prefs_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prefs_raw = None

    feedbacks_recent: list[dict] = []
    try:
        store = feedback_store.load_store(ROOT)
        items = list((store.get("feedbacks") or {}).values())
        items.sort(key=lambda x: x.get("submitted_at") or "", reverse=True)
        feedbacks_recent = items[:10]
    except Exception:
        pass

    meal_log_recent: list[dict] = []
    try:
        meal_log_recent = (load_meal_log(ROOT) or [])[-10:]
    except Exception:
        pass

    accepted_count = 0
    try:
        accepted_count = len(store.get("accepted") or {})
    except Exception:
        pass

    return {
        "enabled": True,
        "state": state,
        "long_term_prefs": prefs or None,
        "long_term_prefs_raw": prefs_raw,
        "feedbacks_recent": feedbacks_recent,
        "feedbacks_total": len(feedbacks_recent),
        "meal_log_recent": meal_log_recent,
        "accepted_count": accepted_count,
    }


# ============================================================
# /api/lab/sessions + /sessions/{sid} + /what_if (D-079 PR-2 Replay)
# ============================================================

class WhatIfOverrides(BaseModel):
    """What-if 可改字段白名单 (DESIGN §4.2). extra=forbid 拒绝未知字段."""
    model_config = {"extra": "forbid"}

    n_return: int | None = Field(default=None, ge=1, le=10)
    n_explore: int | None = Field(default=None, ge=0, le=5)
    use_llm_rerank: bool | None = None
    profile_overrides: dict[str, Any] | None = None


class WhatIfReq(BaseModel):
    """POST /api/lab/what_if body."""
    model_config = {"extra": "forbid"}

    base_session_id: str = Field(min_length=1)
    overrides: WhatIfOverrides = Field(default_factory=WhatIfOverrides)


@router.get("/sessions")
def api_lab_sessions(
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
    meal_type: str | None = Query(default=None),
    source: str = Query(default="production"),
) -> dict:
    """D-079 §7.1: list 最近 N 条 trace meta + feedback link.

    V1 只接受 source=production (Codex +1). 留 query param 是给 V2 扩展.
    """
    _require_localhost(request)
    if source != "production":
        raise HTTPException(
            400, f"source must be 'production' in V1, got {source!r}"
        )
    if meal_type is not None and meal_type not in ("lunch", "dinner"):
        raise HTTPException(400, f"meal_type must be lunch|dinner|null, got {meal_type!r}")

    from chisha import trace_store
    items, corrupt_count = trace_store.list_traces(
        root=ROOT, limit=limit, meal_type=meal_type,
    )
    items = trace_store.attach_feedback_links(items, root=ROOT)
    return {"items": items, "corrupt_count": corrupt_count}


@router.get("/sessions/{session_id}")
def api_lab_session_detail(request: Request, session_id: str) -> dict:
    """D-079 §7.2: 单条完整 trace.

    Failure matrix:
      - 404 trace 不存在
      - 409 schema __version 不匹配
      - 500 文件损坏 (备份 .corrupt.{ts}.bak)
    """
    _require_localhost(request)
    from chisha import trace_store
    try:
        trace = trace_store.read_trace(session_id, root=ROOT)
    except trace_store.TraceCorrupt as e:
        raise HTTPException(500, f"trace corrupt: {e}")
    except trace_store.TraceVersionMismatch as e:
        raise HTTPException(
            409, f"trace schema version mismatch: found={e.found}, expected={e.expected}"
        )
    if trace is None:
        raise HTTPException(404, f"trace {session_id!r} not found")

    try:
        store = feedback_store.load_store(ROOT)
        accepted = (store.get("accepted") or {}).get(session_id)
        fb = (store.get("feedbacks") or {}).get(session_id)
        trace["__feedback"] = {
            "accepted": bool(accepted) and not (accepted or {}).get("skipped"),
            "accepted_rank": (accepted or {}).get("accepted_rank"),
            "accepted_at": (accepted or {}).get("accepted_at"),
            "stopped": bool((accepted or {}).get("stopped")),
            "feedback_submitted": fb is not None,
            "rating": (fb or {}).get("rating"),
            "feedback_record": fb,
        }
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "attach feedback for trace %s failed: %s: %s",
            session_id, type(e).__name__, e,
        )
        trace["__feedback"] = None
    return trace


@router.post("/what_if")
def api_lab_what_if(request: Request, req: WhatIfReq) -> dict:
    """D-079 §7.3: What-if 重跑. 冻结上游 ctx/L1, 重跑 L2+L3.

    Response: shape 同 GET 单条 trace, 但 __source='what_if_preview' +
    __parent_session_id=base_sid + __llm_called=bool. **永不写盘**.
    """
    _require_localhost(request)
    from chisha import debug_what_if, trace_store
    overrides_dict = req.overrides.model_dump(exclude_none=True)
    try:
        return debug_what_if.what_if_rerun(
            base_session_id=req.base_session_id,
            overrides=overrides_dict,
            root=ROOT,
        )
    except debug_what_if.InvalidOverrides as e:
        raise HTTPException(400, f"invalid overrides: {e}")
    except debug_what_if.InvalidBaseTrace as e:
        raise HTTPException(400, f"invalid base trace: {e}")
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except trace_store.TraceCorrupt as e:
        raise HTTPException(500, f"base trace corrupt: {e}")
    except trace_store.TraceVersionMismatch as e:
        raise HTTPException(
            409, f"trace schema version mismatch: found={e.found}, expected={e.expected}"
        )

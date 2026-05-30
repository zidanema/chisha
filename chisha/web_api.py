"""apps/web ↔ FastAPI 用户视图 API (V1 + V1.1).

契约见 docs/api.md §5. 与 chisha/debug_server.py 共用一个 FastAPI app, 通过
include_router 挂载。Phase A: recommend/refine/accept/skip + profile GET。
Phase B/C 端点 (反馈系统 / history / profile PUT) 后续阶段补。

加载策略 (D-051): recommend/refine 实测 15-60s, 前端必用 skeleton (style-guide §2),
后端只管返回, 不做超时硬截 (LLM provider 自己有 retry/fallback, 见 D-048)。
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import yaml
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from chisha import feedback_store
# D-104 Step2/3: web_api 是 extras — 早 import sandbox 触发 core provider 注册
# (虚拟时钟 + real sandbox router), 保证本进程任何 clock/data_root 调用前 provider 已就位。
from chisha import sandbox  # noqa: F401
from chisha.api import recommend_meal
from chisha.core_api_helpers import format_v2_candidate
from chisha.recall import (
    load_meal_log,
    load_profile,
    load_zone_data,
)
from chisha.refine import refine as refine_session
from chisha.sandbox_context import (
    _DEFAULT_SID,
    _validate_sid,
    set_sandbox_session,
)

from chisha.install_root import install_root as _install_root  # T-DIST-01 B.1
ROOT = _install_root()
PROFILE_PATH = ROOT / "profile.yaml"  # prod default (legacy 兼容, refresh test 引用)


def _profile_path() -> Path:
    """D-077 PR-1c: 动态求值. sandbox 启用且有副本 → sandbox/profile.yaml; 否则 prod."""
    from chisha import data_root
    return data_root.profile_path(ROOT)

router = APIRouter(prefix="/api", tags=["web"])


# ---------- helpers ----------

def _resolve_zone(profile: dict, meal_type: str) -> str:
    zones = profile.get("basics", {}).get("zones") or {}
    return zones.get(meal_type) or profile["basics"]["office_zone"]


def _remember_session_safe(session_id: str, payload: dict) -> None:
    """落 sessions 用于反馈页回放, 失败不阻断."""
    try:
        feedback_store.remember_session(ROOT, session_id, payload)
    except Exception as e:
        print(f"  [web_api] remember_session 失败 ({type(e).__name__}: {str(e)[:80]})")


# ---------- S-06a: sandbox sid routing dependency ----------

def _with_sandbox_sid(
    request: Request,
) -> str | None:
    """S-06a 校验 dep: 解析 + 校验 sid, 返回合法非 default sid 或 None.

    **不**直接 set ContextVar (FastAPI sync 端点跑在 anyio worker thread,
    dep 在 main thread, ContextVar 不跨 thread propagate, 详见 chisha 文档
    test_web_api_sid_routing.py). Caller (端点 handler) 拿到 sid 后用
    `with set_sandbox_session(sid):` 包推荐链路.

    sid 来源: header `X-Session-Id` (优先) 或 query `?session_id=`.

    Failure modes:
      - sid 格式不合法 → 400
      - sid 非 default 但 sandbox.is_enabled(ROOT)=False (修订 G) → 409
        防 data_root silent fall back 到 prod (桶目录存在但 sandbox 整体 disabled)
      - sid 非 default 但桶目录不存在 → 404

    sid=None / "_default" → 返 None. 行为同 S-04 默认 (走 flat / prod fallback).
    """
    raw = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    if raw is None or raw == _DEFAULT_SID:
        return None
    # 1. sid 格式校验
    try:
        _validate_sid(raw)
    except ValueError as e:
        raise HTTPException(400, f"invalid X-Session-Id: {e}")
    # 2. 修订 G: sandbox layout 必须 enabled 才能跑非 default sid
    from chisha import sandbox as _sb  # lazy to avoid module-init cycle
    if not _sb.is_enabled(ROOT):
        raise HTTPException(
            409,
            f"sandbox layout disabled; cannot route session_id={raw!r}. "
            "POST /api/sandbox/init or /api/sandbox/<advance|reset> first.",
        )
    # 3. 桶存在 (D-102 Step2: 经 state_root 解析基底, 与 sandbox/data_root 同源)
    from chisha import state_root
    bucket = state_root.resolve(ROOT) / "logs" / "sandbox" / "sessions" / raw
    if not bucket.is_dir():
        raise HTTPException(404, f"unknown sandbox session_id={raw!r}")
    # 4. 返合法 sid (handler 用 with set_sandbox_session(sid) 包)
    return raw


def _sandbox_ctx(sid: str | None):
    """Helper: sid=None → no-op nullcontext; sid 非空 → set_sandbox_session(sid)."""
    from contextlib import nullcontext
    if sid is None:
        return nullcontext()
    return set_sandbox_session(sid)


# ---------- /api/recommend ----------

@router.get("/recommend")
def api_recommend(
    meal_type: str = "lunch",
    mood: str = "neutral",
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """GET /api/recommend?meal_type=&mood= → RecommendResponse (5 候选).

    S-06a: header `X-Session-Id` 或 query `session_id` 路由到非 default 桶
    (走 ContextVar). 详见 `_with_sandbox_sid`.
    """
    if meal_type not in ("lunch", "dinner"):
        raise HTTPException(400, f"meal_type must be lunch|dinner, got {meal_type!r}")
    daily_mood = mood if mood and mood != "neutral" else None
    # S-06a 修订 D: 显式 root=ROOT 让 recommend chain 用 web_api ROOT
    # (而非 chisha/api.py _default_root), 防止 monkeypatched-root 测试漂移 +
    # 配合 sid routing 写到正确桶.
    with _sandbox_ctx(_sid):
        out = recommend_meal(
            meal_type=meal_type,
            daily_mood=daily_mood,
            log_to_file=True,
            root=ROOT,
        )
        _remember_session_safe(out["session_id"], out)
    return out


# ---------- /api/refine ----------

class RefineReq(BaseModel):
    session_id: str
    refine_text: str = ""
    meal_type: str | None = None
    mood: str | None = None
    round: int | None = None
    excludeIds: list[str] = Field(default_factory=list)


@router.post("/refine")
def api_refine(
    req: RefineReq,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """POST /api/refine → 同 session 二轮推荐 (round++)."""
    with _sandbox_ctx(_sid):
        return _impl_refine(req)


def _impl_refine(req: RefineReq) -> dict:
    profile = load_profile(_profile_path(), root=ROOT)
    # session 决定 meal_type/zone, 客户端传的 meal_type/mood 仅作 fallback
    from chisha.session import load_session
    state = load_session(req.session_id, ROOT)
    if state is None:
        raise HTTPException(404, f"session {req.session_id!r} expired or missing")
    zone = state.zone
    rests, tagged = load_zone_data(zone, ROOT)
    meal_log = load_meal_log(ROOT)

    # Codex M2: 在 web_api 端单次取 today (clock 走 sandbox 友好), 一路传到
    # refine_session / build_context / _build_l1_trace, 避免跨午夜/sandbox 边界漂移.
    from chisha import clock
    today = clock.today(ROOT)

    raw = refine_session(
        session_id=req.session_id,
        user_input=req.refine_text or "",
        profile=profile,
        rests=rests,
        tagged=tagged,
        meal_log=meal_log,
        root=ROOT,
        today=today,
    )

    # refine() 返回的 candidates 是 raw rerank dict, 需要走 format_v2_candidate
    candidates_fmt = [
        format_v2_candidate(i + 1, c)
        for i, c in enumerate(raw["candidates"])
    ]

    # 拼成与 recommend 一致的 RecommendResponse 形状 (前端 useChishaState 直接消费)
    from chisha.context import build_context
    ctx = build_context(
        profile=profile,
        meal_log=meal_log,
        meal_type=state.meal_type,
        today=today,
        daily_mood=state.daily_mood,
        refine_input=req.refine_text or "",
        refine_intent=raw.get("refine_intent"),  # D-073
    )

    # T-P1b-01: refine 路径 status_bar
    # = recall path L0-A/B (与 recommend 同源, 重跑 _build_l1_trace)
    # + refine path L0-C 解除事件 (来自 raw["_refine_hard_filter_events"])
    # Codex M2: 与 refine_session 内部共用同一个 today (clock.today, sandbox 友好)
    try:
        from chisha.debug_recommend import _build_l1_trace
        from chisha.status_bar import build_status_bar
        _l1_trace, _ = _build_l1_trace(
            profile, rests, tagged, meal_log,
            today,
            meal_type=state.meal_type,
        )
        _hfe = list(_l1_trace.get("hard_filter_events") or [])
        # 合并 refine 自身的 L0-C override 事件
        _hfe.extend(raw.get("_refine_hard_filter_events") or [])
        status_bar = build_status_bar(profile, _hfe)
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning(
            "refine status_bar build failed (non-fatal): %s: %s",
            type(_e).__name__, _e,
        )
        from chisha.status_bar import build_status_bar
        status_bar = build_status_bar(
            profile, raw.get("_refine_hard_filter_events") or []
        )

    out = {
        "session_id": raw["session_id"],
        "meal_type": raw["meal_type"],
        "zone": raw["zone"],
        "round": raw["round"],
        "version": "v2",
        "generated_at": raw["generated_at"],
        "context": ctx.to_llm_dict(),
        "stats": raw["stats"],
        "candidates": candidates_fmt,
        "status_bar": status_bar,
        "narrative": raw.get("narrative", ""),
        # 调试用 (前端忽略):
        "refine_input": raw.get("refine_input"),
        "refine_intent": raw.get("refine_intent"),  # D-073: 替代 parsed_feedback/taste_hints
    }
    _remember_session_safe(out["session_id"], out)

    # D-087 v3: refine = append 新 round 到 v3 trace ({sid}/rounds/R{n}.json).
    # 上游 v2 单文件 trace 由 append_round 内部自动 migrate. 写盘失败 best-effort
    # logger.warning, 不阻断 refine response (与 D-079 风格一致).
    # D-089-S4: 完整 L1/L2/L3 + refine_intent_llm trace 切片由 trace_helpers.
    # build_refine_round_payload 1:1 透传 refine 返回值 (refine.py Stage 2/3 已注入).
    try:
        from chisha import trace_store
        from chisha.trace_helpers import build_refine_round_payload
        new_round = build_refine_round_payload(raw, req.refine_text or "")
        round_id = trace_store.append_round(
            req.session_id, new_round, root=ROOT,
        )
        if round_id is None:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "refine append_round %s skip persist (no base trace or write failed); "
                "response unaffected", req.session_id,
            )
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "refine append_round failed (non-fatal): %s: %s",
            type(e).__name__, e,
        )

    return out


# ---------- /api/accept ----------

class AcceptReq(BaseModel):
    session_id: str
    candidate_rank: int
    candidate: dict[str, Any]


@router.post("/accept")
def api_accept(
    req: AcceptReq,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """D-052: 记录 accept → 落 acceptedQueue → 返回 deeplink (best-effort)."""
    with _sandbox_ctx(_sid):
        return _impl_accept(req)


def _impl_accept(req: AcceptReq) -> dict:
    rest = req.candidate.get("restaurant") or {}
    rest_id = rest.get("id") or ""
    name = rest.get("name") or ""
    summary = req.candidate.get("summary") or ""
    meal_type = req.candidate.get("meal_type")
    # accept 时 candidate 里通常没 meal_type, 从 session 反查
    zone: str | None = None
    if not meal_type:
        from chisha.session import load_session
        state = load_session(req.session_id, ROOT, check_expiry=False)
        meal_type = state.meal_type if state else "lunch"
        zone = state.zone if state else None
    else:
        from chisha.session import load_session
        state = load_session(req.session_id, ROOT, check_expiry=False)
        zone = state.zone if state else None

    # 写盘失败必须暴露给前端: acceptedQueue 是反馈系统 source-of-truth,
    # 静默丢失会让 banner/inbox/recent 链路全空 (Codex review MED-1).
    try:
        feedback_store.record_accept(
            root=ROOT,
            session_id=req.session_id,
            candidate_rank=req.candidate_rank,
            meal_type=meal_type,
            restaurant_name=name,
            summary=summary,
        )
    except Exception as e:
        raise HTTPException(
            500, f"record_accept failed: {type(e).__name__}: {e}"
        )

    # D-078: meal_log 是 diversity cooldown 的 source-of-truth.
    # accept 写 feedback_store 但 meal_log 静默失败 → accepted_count > meal_log
    # 暗洞 → 一周内可能重复推同店. 与 record_accept 同等 hard-fail.
    try:
        from chisha.recall import append_meal_log_entry
        append_meal_log_entry(
            root=ROOT,
            session_id=req.session_id,
            meal_type=meal_type,
            restaurant_id=rest_id,
            restaurant_name=name,
            dishes=req.candidate.get("dishes") or [],
            zone=zone,
            accepted_rank=req.candidate_rank,
            combo_index=req.candidate.get("combo_index"),
            candidate_id=req.candidate.get("id"),
        )
    except Exception as e:
        raise HTTPException(
            500, f"append_meal_log_entry failed: {type(e).__name__}: {e}"
        )

    from urllib.parse import quote
    deeplink = f"dianping://shopdesc?shopId={rest_id}&name={quote(name)}"
    return {"deeplink_url": deeplink}


# ---------- /api/skip ----------

_VALID_SKIP_REASONS = {
    None, "cafeteria", "brought", "outside",
    "social", "none_fit", "not_hungry",
}


class SkipReq(BaseModel):
    session_id: str
    reason: str | None = None


@router.post("/skip")
def api_skip(
    req: SkipReq,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """D-054: 这餐没吃 (食堂/带饭/外面/聚会/都没看上/不饿).

    reason ∈ {cafeteria, brought, outside, social, none_fit, not_hungry, null}.
    后续 V1.5+ 反馈学习信号: cafeteria/brought/outside ≠ "都没看上" (D-054).
    """
    if req.reason not in _VALID_SKIP_REASONS:
        raise HTTPException(400, f"invalid skip reason {req.reason!r}")
    with _sandbox_ctx(_sid):
        try:
            feedback_store.record_skip(ROOT, req.session_id, req.reason)
        except Exception as e:
            raise HTTPException(
                500, f"record_skip failed: {type(e).__name__}: {e}"
            )
    return {"ok": True}


# ---------- /api/profile (GET / PUT / POST) ----------

@router.get("/profile")
def api_get_profile(
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    with _sandbox_ctx(_sid):
        return yaml.safe_load(_profile_path().read_text(encoding="utf-8"))


def _write_profile_preserving_comments(new_profile: dict) -> None:
    """覆盖写 profile.yaml, 用 ruamel.yaml 保留头部注释 + 字段顺序.

    策略: load 当前 yaml (含注释 anchor) → 用 new_profile 内容覆盖字段值 →
    dump 回去。新字段写到末尾, 已删字段保持注释残留 (V1 schema 稳定不会出现)。
    """
    from ruamel.yaml import YAML
    yaml_rt = YAML()
    yaml_rt.preserve_quotes = True
    yaml_rt.indent(mapping=2, sequence=4, offset=2)

    # D-077 PR-1c: 走 sandbox 副本 (启用时) 或 prod profile.yaml
    target = _profile_path()
    # 如果 sandbox 启用但副本不存在, 先拷一份 (init 时也会拷, 这里兜底)
    # D-102 Step2: seed 源用 state_root 的 prod profile (非 install 旧位置), 翻默认后
    # 不读 repo 内的 stale profile (Codex commit review Q-C).
    from chisha import sandbox as _sb, state_root as _sr
    prod_profile = _sr.resolve(ROOT) / "profile.yaml"
    if _sb.is_enabled(ROOT) and not target.exists() and prod_profile.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(prod_profile.read_text(encoding="utf-8"), encoding="utf-8")

    if target.exists():
        with target.open("r", encoding="utf-8") as f:
            current = yaml_rt.load(f)
        if current is None:
            current = {}
    else:
        current = {}

    # 深合并: 把 new_profile 的叶子值 patch 到 current, 保留 current 的注释
    def _deep_merge(dst, src):
        if not isinstance(src, dict):
            return src
        if not isinstance(dst, dict):
            # current 那里不是 dict, 直接替换为 src
            return src
        for k, v in src.items():
            if k in dst:
                dst[k] = _deep_merge(dst[k], v)
            else:
                dst[k] = v
        return dst

    merged = _deep_merge(current, new_profile)

    tmp = target.with_suffix(".yaml.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml_rt.dump(merged, f)
    tmp.replace(target)


@router.put("/profile")
@router.post("/profile")
def api_put_profile(
    profile: dict,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """PUT (或 POST 兼容) /api/profile body=完整 Profile, ruamel.yaml 写入保留注释."""
    if not isinstance(profile, dict) or "basics" not in profile:
        raise HTTPException(400, "invalid profile body: missing 'basics'")
    try:
        with _sandbox_ctx(_sid):
            _write_profile_preserving_comments(profile)
    except Exception as e:
        raise HTTPException(500, f"write profile.yaml failed: {type(e).__name__}: {e}")
    return {"ok": True}


# ---------- /api/history ----------

@router.get("/history")
def api_history(
    days: int = 7,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """近 N 天的推荐 session, 关联 accepted_rank.

    数据源: logs/recommend_log.jsonl (每次 recommend 写一行) + feedback_store.accepted.
    返回 HistoryItem[]: { session_id, meal_type, generated_at, accepted_rank,
                         candidates_summary[3], mood }
    """
    if days < 1 or days > 90:
        raise HTTPException(400, "days must be in [1, 90]")
    with _sandbox_ctx(_sid):
        return _impl_history(days)


def _impl_history(days: int) -> dict:
    # D-077 Codex S3 修复: 走 data_root.recommend_log_path, sandbox 启用时
    # history 读 sandbox log 而非 prod log.
    from chisha import data_root
    log_path = data_root.recommend_log_path(ROOT)
    if not log_path.exists():
        return {"items": []}

    from chisha import clock
    cutoff = clock.now_utc() - dt.timedelta(days=days)
    accepted_map: dict[str, dict] = {}
    try:
        accepted_map = feedback_store.load_store(ROOT).get("accepted", {}) or {}
    except Exception:
        pass

    items: list[dict] = []
    # 去重: 同 session_id 取最新 (refine 不重写 recommend_log)
    seen: set[str] = set()
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = rec.get("session_id")
            if not sid or sid in seen:
                continue
            try:
                gen_at = dt.datetime.fromisoformat(
                    (rec.get("generated_at") or "").replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                continue
            if gen_at < cutoff:
                continue
            seen.add(sid)
            candidates = rec.get("candidates") or []
            summary = [
                (c.get("restaurant") or {}).get("name", "").split("·")[0]
                for c in candidates[:3]
            ]
            mood = (rec.get("context") or {}).get("daily_mood") or "neutral"
            items.append({
                "session_id": sid,
                "meal_type": rec.get("meal_type", "lunch"),
                "generated_at": rec.get("generated_at"),
                "accepted_rank": (accepted_map.get(sid) or {}).get("accepted_rank"),
                "candidates_summary": summary,
                "mood": mood,
            })

    items.sort(key=lambda x: x["generated_at"] or "", reverse=True)
    return {"items": items}


# ==================================================================
# Phase B: V1.1 反馈系统 (D-056 ~ D-068)
# ==================================================================
# 路由顺序: 静态路径必须先注册, /feedback/{session_id} 在最后
# (FastAPI 按注册顺序匹配, 否则 inbox/snooze 会被 path-param 吞)
# ------------------------------------------------------------------


class SnoozeReq(BaseModel):
    session_id: str


class StopReq(BaseModel):
    session_id: str


GutVal = Literal[-1, 0, 1] | None        # D-064 难吃/普通/好吃
DimVal = Literal[0, 1, 2] | None         # D-065 4 维 calibration/behavior


class FeedbackPayloadReq(BaseModel):
    """V1.1 schema (D-063~D-065). 与 apps/web FeedbackPayload 镜像.

    Codex review MED-4: 用 Literal 限定枚举值, model_validator 强制
    variant=not-eaten ⇒ accepted_rank + 5 维度全 null.
    """
    session_id: str
    accepted_rank: int | None = None
    rating: GutVal = None
    reason_match: DimVal = None
    fullness: DimVal = None
    oil_calibration: DimVal = None
    repurchase_intent: DimVal = None
    note: str = ""
    variant: Literal["progressive", "not-eaten"] = "progressive"
    quick: bool = False                       # D-068 默认 false, 不存 null

    @model_validator(mode="after")
    def _check_variant_invariants(self) -> "FeedbackPayloadReq":
        if self.variant == "not-eaten":
            # 「都没吃这几个」逃生口: 所有评分字段必须 null
            offenders = [
                name for name, val in (
                    ("accepted_rank", self.accepted_rank),
                    ("rating", self.rating),
                    ("reason_match", self.reason_match),
                    ("fullness", self.fullness),
                    ("oil_calibration", self.oil_calibration),
                    ("repurchase_intent", self.repurchase_intent),
                ) if val is not None
            ]
            if offenders:
                raise ValueError(
                    f"variant=not-eaten requires null fields, got non-null: {offenders}"
                )
        return self


class CommentReq(BaseModel):
    text: str


@router.get("/feedback/inbox")
def api_feedback_inbox(
    include_snoozed: int = 1,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """D-058: 反馈中心 inbox. include_snoozed=0 时过滤掉 24h 软关闭项."""
    with _sandbox_ctx(_sid):
        data = feedback_store.load_store(ROOT)
        items = feedback_store.inbox_items(
            data, include_snoozed=bool(include_snoozed)
        )
    return {"items": items}


@router.post("/feedback/snooze")
def api_feedback_snooze(
    req: SnoozeReq,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """D-060 软关闭: 24h 内 banner 不弹, inbox 仍在."""
    with _sandbox_ctx(_sid):
        feedback_store.set_snooze(ROOT, req.session_id, hours=24)
    return {"ok": True}


@router.post("/feedback/stop")
def api_feedback_stop(
    req: StopReq,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """D-060 硬关闭: 永久, banner+inbox 都隐藏, history 仍可点."""
    with _sandbox_ctx(_sid):
        feedback_store.set_stop(ROOT, req.session_id)
    return {"ok": True}


@router.get("/feedback/recent")
def api_feedback_recent(
    limit: int = Query(default=6, ge=1, le=100),
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """D-066: 最近已反馈, 供 inbox 第三段 + history 行 gut chip 渲染.

    Codex review LOW: limit ∈ [1, 100], 负值 / 0 / 巨大值都 422.
    """
    with _sandbox_ctx(_sid):
        data = feedback_store.load_store(ROOT)
        return {"items": feedback_store.recent_feedback_items(data, limit=limit)}


@router.post("/feedback")
def api_feedback_submit(
    req: FeedbackPayloadReq,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """D-066: 提交反馈, comments[] 保留 (D-067)."""
    with _sandbox_ctx(_sid):
        feedback_store.record_feedback(ROOT, req.model_dump())
    return {"ok": True}


# --- path-param 路由 (放最后) ---


@router.get("/feedback/{session_id}/record")
def api_feedback_record(session_id: str) -> dict | None:
    """D-066 双态: 没提交 → null, 已提交 → FeedbackRecord."""
    data = feedback_store.load_store(ROOT)
    return feedback_store.get_feedback_record(data, session_id)


@router.post("/feedback/{session_id}/comments")
def api_feedback_comment(session_id: str, req: CommentReq) -> dict:
    """D-067 append-only 备注."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    comment = feedback_store.append_comment(ROOT, session_id, text)
    if comment is None:
        raise HTTPException(404, "no feedback to append to")
    return {"ok": True}


@router.get("/feedback/{session_id}")
def api_feedback_session(
    session_id: str,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """反馈页头部 5 候选回放. session 已过期/不存在 → 404."""
    with _sandbox_ctx(_sid):
        data = feedback_store.load_store(ROOT)
    accepted = feedback_store.get_accepted(data, session_id) or {}
    session_payload = data["sessions"].get(session_id)
    if not session_payload:
        raise HTTPException(404, f"session {session_id!r} expired or missing")
    return {
        "session_id": session_id,
        "meal_type": session_payload.get("meal_type")
            or accepted.get("meal_type") or "lunch",
        "accepted_at": accepted.get("accepted_at")
            or session_payload.get("generated_at"),
        "accepted_rank": accepted.get("accepted_rank"),
        "candidates": session_payload.get("candidates") or [],
    }


# ---------- /api/long_term_prefs/refresh (D-076 PR-0.9) ----------

_LOCALHOST_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _is_localhost(request: Request) -> bool:
    """请求来源是否本机 (LAN/外网拒绝, 单用户本机使用场景)."""
    if request.client is None:
        return False
    return request.client.host in _LOCALHOST_HOSTS


def _admin_token_ok(request: Request) -> bool:
    """ENV CHISHA_ADMIN_TOKEN 设了的话, 校验 header X-Admin-Token 匹配."""
    expected = os.environ.get("CHISHA_ADMIN_TOKEN", "").strip()
    if not expected:
        return True   # 未配置 token → 不强制
    got = request.headers.get("x-admin-token", "").strip()
    return got == expected


class RefreshPrefsReq(BaseModel):
    """触发 L1 抽取的请求体. 字段全可选, 默认行为 = 全量重抽."""
    window_days: int | None = Field(default=None, ge=1, le=180)
    force_run_without_llm: bool = False   # 强制走 bootstrap (deterministic, 无 LLM)


def _impl_l1_refresh(
    root: Path,
    *,
    force_no_llm: bool = False,
    window_days: int | None = None,
    acquire_lock: bool = False,
) -> dict:
    """S-06c 修订 C: 提抽 L1 抽取核心逻辑, 供 HTTP endpoint + BG task 共用.

    acquire_lock=True 时持 `_L1_EXTRACTION_LOCK` 整个 extract 周期 (供 BG task,
    保 CONTRACTS.md:98 reset/disable 互斥). HTTP `/api/long_term_prefs/refresh`
    保持原行为 (acquire_lock=False, 不持锁, 让 trylock 路径自己管).

    Returns:
        prefs dict (含 boost/penalty/evidence/extracted_at/based_on_meals/path).

    Raises:
        RuntimeError: LLM 全 retry 失败 (caller 转 503)
        feedback_store.StoreCorruptError: feedback 损坏 (caller 转 500)
        OSError/yaml.YAMLError: profile.yaml 读失败 (caller 转 500)
    """
    def _do() -> dict:
        if force_no_llm:
            from scripts.bootstrap_l1_from_legacy import bootstrap
            prefs = bootstrap(root=root, force=True)
            prefs.setdefault("path", "bootstrap_no_llm")
            return prefs

        from chisha.l1_extractor import extract_and_save

        store = feedback_store.load_store(root)
        profile = yaml.safe_load(_profile_path().read_text(encoding="utf-8")) or {}
        window = window_days or 14
        prefs = extract_and_save(
            store, profile,
            root=root,
            window_days=window,
            profile_llm=profile.get("llm"),
        )
        prefs.setdefault("path", "llm_extract")
        return prefs

    if acquire_lock:
        with _L1_EXTRACTION_LOCK:
            return _do()
    return _do()


@router.post("/long_term_prefs/refresh")
def api_long_term_prefs_refresh(
    request: Request,
    req: RefreshPrefsReq,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """D-076 PR-0.9: 手动触发 L1 LLM 抽取, 写入 data/long_term_prefs.json.

    鉴权:
    - localhost only (LAN/外网拒绝)
    - 可选 X-Admin-Token header (env CHISHA_ADMIN_TOKEN 设了才检)

    S-06c 修订 C: 主体提抽到 `_impl_l1_refresh`, 此处仅做权限校验 + HTTPException
    转换. HTTP 路径**不**持 `_L1_EXTRACTION_LOCK` (现状, 用户连按 refresh 由
    `_trigger_l1_extraction_async` 的 trylock 自管).

    返回: prefs dict.
    """
    if not _is_localhost(request):
        raise HTTPException(403, "refresh endpoint is localhost-only")
    if not _admin_token_ok(request):
        raise HTTPException(401, "invalid or missing X-Admin-Token")

    with _sandbox_ctx(_sid):
        try:
            return _impl_l1_refresh(
                ROOT,
                force_no_llm=req.force_run_without_llm,
                window_days=req.window_days,
                acquire_lock=False,
            )
        except feedback_store.StoreCorruptError as e:
            raise HTTPException(500, f"feedback store corrupt: {e}")
        except (OSError, yaml.YAMLError) as e:
            raise HTTPException(500, f"profile.yaml load failed: {type(e).__name__}: {e}")
        except RuntimeError as e:
            raise HTTPException(503, f"L1 extract failed: {e}")


# ---------- /api/sandbox/* (D-077 PR-1c) ----------

import threading as _threading
from chisha import sandbox as _sandbox

# D-077 Codex S3 修复: L1 抽取串行锁, 防多 tab 并发 advance 同时跑多个 LLM 抽取
# 互相覆盖 last_l1_extraction. trylock 模式: 已有 worker 跑则跳过, 不堆队列.
_L1_EXTRACTION_LOCK = _threading.Lock()


class SandboxInitReq(BaseModel):
    start_date: str | None = None      # ISO date YYYY-MM-DD; None = 真实 today
    copy_real_data: bool = False        # 是否把 prod meal_log/feedback/prefs 拷一份


class SandboxAdvanceReq(BaseModel):
    days: int = Field(default=1, ge=1, le=30)


def _require_localhost(request: Request) -> None:
    if not _is_localhost(request):
        raise HTTPException(403, "sandbox endpoints are localhost-only")


def _copy_real_data_to_sandbox(root: Path) -> None:
    """init(copy_real_data=True) 时把 prod 业务数据复制到 sandbox 子树.

    D-102 Step2: prod 源 + sandbox 目标都以 state_root 解析的基底拼 (与 data_root/sandbox
    同源), 防 env/翻默认后从 install root 找不到 prod 数据 (Codex commit review BLOCKING).
    """
    import shutil
    from chisha import state_root

    base = state_root.resolve(root)
    sandbox_dir = base / "logs" / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    # profile.yaml
    if (base / "profile.yaml").exists():
        shutil.copy2(base / "profile.yaml", sandbox_dir / "profile.yaml")

    # meal_log / feedback_store / feedback_history / long_term_prefs / recommend_log
    prod_meal_log = base / "logs" / "meal_log.jsonl"
    if prod_meal_log.exists():
        shutil.copy2(prod_meal_log, sandbox_dir / "meal_log.jsonl")

    prod_feedback_store = base / "logs" / "feedback" / "store.json"
    if prod_feedback_store.exists():
        (sandbox_dir / "feedback").mkdir(parents=True, exist_ok=True)
        shutil.copy2(prod_feedback_store, sandbox_dir / "feedback" / "store.json")

    # D-102 Step2 (Commit B): feedback_history / long_term_prefs 已迁出 data/ → state_root 顶层
    prod_history = base / "feedback_history.jsonl"
    if prod_history.exists():
        shutil.copy2(prod_history, sandbox_dir / "feedback_history.jsonl")

    prod_prefs = base / "long_term_prefs.json"
    if prod_prefs.exists():
        shutil.copy2(prod_prefs, sandbox_dir / "long_term_prefs.json")

    prod_recommend_log = base / "logs" / "recommend_log.jsonl"
    if prod_recommend_log.exists():
        shutil.copy2(prod_recommend_log, sandbox_dir / "recommend_log.jsonl")


def _trigger_l1_extraction_async(root: Path) -> None:
    """后台抽取 L1 prefs. 标记 state.last_l1_extraction.

    sandbox advance 后调用. 失败保留旧 prefs, 状态写 failed.

    并发保护 (D-077 Codex S3): 用 trylock 模式 — 已有 worker 跑时直接跳过,
    避免多 tab 连点 advance 触发多个并发 LLM 抽取互相覆盖 state.
    """
    if not _L1_EXTRACTION_LOCK.acquire(blocking=False):
        # 已有抽取在跑, 跳过 (state 仍是上次的 pending/ok/failed)
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


# ---------- S-06a: sandbox sessions CRUD ----------


class SandboxSessionMeta(BaseModel):
    sid: str
    is_default: bool
    created_at: str | None = None
    size_bytes: int = 0
    has_state: bool = False


class SessionsListResp(BaseModel):
    sessions: list[SandboxSessionMeta]


class CreateSessionReq(BaseModel):
    sid: str = Field(min_length=1, max_length=64)
    days: int = Field(default=7, ge=1, le=30)  # S-06c 修订 A: total_meals = days*2


class RenameSessionReq(BaseModel):
    new_sid: str = Field(min_length=1, max_length=64)


@router.get("/sandbox/sessions")
def api_sandbox_list_sessions(request: Request) -> SessionsListResp:
    """S-06a: 列出 sandbox 桶 (default 永远首位)."""
    _require_localhost(request)
    items = _sandbox.list_sessions(root=ROOT)
    return SessionsListResp(sessions=[SandboxSessionMeta(**it) for it in items])


@router.post("/sandbox/sessions", status_code=201)
def api_sandbox_create_session(
    request: Request, req: CreateSessionReq,
) -> SandboxSessionMeta:
    """S-06a: 创建非 default sandbox 桶."""
    _require_localhost(request)
    if not _sandbox.has_sandbox_meta(ROOT):
        raise HTTPException(
            400,
            "sandbox layout not initialized; POST /api/sandbox/init or run "
            "sandbox_migration.migrate_to_v2 first",
        )
    try:
        meta = _sandbox.create_session(req.sid, root=ROOT, days=req.days)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileExistsError as e:
        raise HTTPException(409, str(e))
    return SandboxSessionMeta(**meta)


@router.delete("/sandbox/sessions/{sid}")
def api_sandbox_delete_session(request: Request, sid: str) -> dict:
    """S-06a: 删除非 default sandbox 桶 (default 禁删, 不存在 404)."""
    _require_localhost(request)
    try:
        return _sandbox.delete_session(sid, root=ROOT)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.post("/sandbox/sessions/{sid}/rename")
def api_sandbox_rename_session(
    request: Request, sid: str, req: RenameSessionReq,
) -> SandboxSessionMeta:
    """S-06a: 同 fs 原子 rename. 跨 fs 抛 OSError(EXDEV) → 500."""
    _require_localhost(request)
    try:
        meta = _sandbox.rename_session(sid, req.new_sid, root=ROOT)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except FileExistsError as e:
        raise HTTPException(409, str(e))
    except OSError as e:
        # 跨 fs (EXDEV) 等 — 不静默 fallback 到 copy+rm
        raise HTTPException(
            500,
            f"rename failed (likely cross-fs, EXDEV); manual intervention needed: {e}",
        )
    return SandboxSessionMeta(**meta)


# ════════════════════════════════════════════════════════════════════════════
# S-06c: per-session interactive endpoints (recs / eat / skip / swap / refine / jobs)
# ════════════════════════════════════════════════════════════════════════════

import os as _os
import secrets as _secrets
from chisha.sandbox import _now_real_iso
from chisha.sandbox_adapter import (
    format_v2_to_rec,
    mock_recs as _mock_recs_data,
    mock_refine_recs as _mock_refine_recs_data,
)
from chisha.sandbox_decision_diff import build_decision

# In-memory job 表 (S-06c BackgroundTask decision diff build)
_JOB_TABLE: dict[str, dict] = {}
_JOB_LOCK = _threading.Lock()

_DEFAULT_SID_C = "_default"

# S-07: per-sid op lock 防 eat/skip/swap/refine/rollback/branch 并发污染.
# Handler 入口拿锁 timeout=30 → 409; BG task body 无 timeout 等. branch 持
# src+new 两把 (src 外 new 内).
_SESSION_OP_LOCK_REGISTRY: dict[str, _threading.Lock] = {}
_REGISTRY_LOCK = _threading.Lock()


def _get_session_op_lock(sid_key: str) -> _threading.Lock:
    with _REGISTRY_LOCK:
        return _SESSION_OP_LOCK_REGISTRY.setdefault(sid_key, _threading.Lock())


from contextlib import contextmanager as _contextmanager


@_contextmanager
def _session_op_lock(routed_sid: str | None, *, timeout: float | None = 30.0,
                     action: str = "operation"):
    """S-07: 抢 per-sid op lock, timeout 抢不到 → 409. timeout=None 无限等 (BG)."""
    sid_key = routed_sid or _DEFAULT_SID_C
    lock = _get_session_op_lock(sid_key)
    if timeout is None:
        lock.acquire()
        ok = True
    else:
        ok = lock.acquire(timeout=timeout)
    if not ok:
        raise HTTPException(
            409, f"{action} blocked: sandbox sid={sid_key!r} busy >{timeout:.0f}s",
        )
    try:
        yield
    finally:
        lock.release()


def _atomic_write_json(path: Path, data: Any) -> None:
    """S-06c 修订 F: tmp + os.replace 原子写 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _os.replace(tmp, path)


def _sb_bucket(sid: str | None, root: Path) -> Path:
    """sandbox 桶根目录: default → logs/sandbox/, 非 default → logs/sandbox/sessions/{sid}/.

    D-102 Step2: 经 state_root 解析基底 (与 data_root/sandbox 同源), 防 env/翻默认后
    sandbox state 写一处、web bucket 读另一处 split-brain (Codex commit review BLOCKING).
    """
    from chisha import state_root
    base = state_root.resolve(root)
    if sid is None or sid == _DEFAULT_SID_C:
        return base / "logs" / "sandbox"
    return base / "logs" / "sandbox" / "sessions" / sid


def _last_recs_path(sid: str | None, root: Path) -> Path:
    return _sb_bucket(sid, root) / "last_recs.json"


def _history_path(sid: str | None, root: Path) -> Path:
    return _sb_bucket(sid, root) / "history.json"


def _meal_to_trace_path(sid: str | None, root: Path) -> Path:
    return _sb_bucket(sid, root) / "meal_to_trace.json"


def _decision_path(sid: str | None, meal_idx: int, root: Path) -> Path:
    return _sb_bucket(sid, root) / "decisions" / f"{meal_idx}.json"


def _load_history(sid: str | None, root: Path) -> list[dict]:
    p = _history_path(sid, root)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _append_history(sid: str | None, root: Path, entry: dict) -> list[dict]:
    history = _load_history(sid, root)
    history.append(entry)
    _atomic_write_json(_history_path(sid, root), history)
    return history


def _load_meal_to_trace(sid: str | None, root: Path) -> dict:
    p = _meal_to_trace_path(sid, root)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _update_meal_to_trace(sid: str | None, root: Path, meal_idx: int, trace_session_id: str) -> None:
    m = _load_meal_to_trace(sid, root)
    m[str(meal_idx)] = trace_session_id
    _atomic_write_json(_meal_to_trace_path(sid, root), m)


def _load_prefs_safe(root: Path) -> dict:
    """Load long_term_prefs.json from sandbox-aware path, empty dict on missing/error."""
    from chisha import data_root
    try:
        p = data_root.long_term_prefs_path(root)
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def _validate_and_route_sid(sid: str) -> str | None:
    """S-06c: 校验 path sid + sandbox enabled + 桶存在; 返合法非 default sid 或 None.

    sid="_default" → 返 None (走 flat default 桶). 其它走 sessions/{sid}/.

    Raises HTTPException 400/404/409 同 `_with_sandbox_sid`.
    """
    if sid == _DEFAULT_SID_C:
        return None
    from chisha.sandbox_context import _validate_sid as _vs
    try:
        _vs(sid)
    except ValueError as e:
        raise HTTPException(400, f"invalid sandbox session_id: {e}")
    if not _sandbox.is_enabled(ROOT):
        raise HTTPException(
            409,
            f"sandbox layout disabled; cannot route session_id={sid!r}",
        )
    # D-102 Step2: 经 state_root 解析基底 (与 sandbox/data_root 同源, 防 split-brain)
    from chisha import state_root
    bucket = state_root.resolve(ROOT) / "logs" / "sandbox" / "sessions" / sid
    if not bucket.is_dir():
        raise HTTPException(404, f"unknown sandbox session_id={sid!r}")
    return sid


def _ensure_not_done(routed_sid: str | None, root: Path) -> dict:
    """S-06c 修订 E: 读 state, raise 409 if done sentinel; 返 state dict."""
    state_p = _sandbox._state_path_for_sid(routed_sid, root)
    if not state_p.exists():
        raise HTTPException(
            409,
            f"sandbox session {routed_sid or '_default'!r} not initialized "
            "(no state.json); POST /api/sandbox/init or /api/sandbox/sessions first",
        )
    try:
        s = json.loads(state_p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(500, f"sandbox state corrupt: {e}")
    if not isinstance(s, dict) or not s.get("enabled"):
        raise HTTPException(409, "sandbox not enabled")
    cur = int(s.get("current_meal_idx", 0))
    total = int(s.get("total_meals", 14))
    if cur >= total:
        raise HTTPException(409, f"sandbox session done (meal_idx {cur}/{total})")
    return s


# ---------- POST /sandbox/sessions/{sid}/recs ----------


class SandboxRecsReq(BaseModel):
    meal_type: str | None = None   # 默认从 state.current_meal_idx 派生


@router.post("/sandbox/sessions/{sid}/recs")
def api_sandbox_recs(
    request: Request,
    sid: str,
    req: SandboxRecsReq,
    mock_recommend: int = 0,
) -> dict:
    """S-06c: 拉 5 条推荐, 落 sessions/{sid}/last_recs.json.

    mock_recommend=1 → 5 条固定 Rec (复刻 sbxMocks.CURRENT_RECS), 不调 LLM.

    S-07: 入口 per-sid op lock, 防 rollback 与 /recs 并发污染 last_recs.
    """
    _require_localhost(request)
    routed_sid = _validate_and_route_sid(sid)
    with _session_op_lock(routed_sid, action="recs"):
        s = _ensure_not_done(routed_sid, ROOT)
        cur_idx = int(s.get("current_meal_idx", 0))
        meal_type = req.meal_type
        if meal_type not in ("lunch", "dinner"):
            meal_type, _day = _sandbox.meal_idx_to_slot(cur_idx)

        is_mock = mock_recommend == 1
        if is_mock:
            current_recs = _mock_recs_data()
            recommend_session_id = f"mock_{_secrets.token_hex(4)}"
            # 构造 v2-shape candidates 用于后续 eat 端点 / adapter (mock 路径里 candidates = currentRecs)
            candidates = current_recs
        else:
            with _sandbox_ctx(routed_sid):
                try:
                    out = recommend_meal(
                        meal_type=meal_type,
                        daily_mood=None,
                        log_to_file=True,
                        root=ROOT,
                    )
                except Exception as e:
                    raise HTTPException(500, f"recommend_meal failed: {type(e).__name__}: {e}")
            candidates = out["candidates"]   # v2 dict
            current_recs = [format_v2_to_rec(c) for c in candidates]
            recommend_session_id = out["session_id"]

        last_recs_payload = {
            "recommend_session_id": recommend_session_id,
            "candidates": candidates,
            "currentRecs": current_recs,
            "applied_refine": None,
            "meal_idx": cur_idx,
            "is_mock": is_mock,
            "saved_at": _now_real_iso(),
        }
        _atomic_write_json(_last_recs_path(routed_sid, ROOT), last_recs_payload)

        return {
            "currentRecs": current_recs,
            "recommend_session_id": recommend_session_id,
            "applied_refine": None,
            "meal_idx": cur_idx,
        }


# ---------- POST /sandbox/sessions/{sid}/eat ----------


class SandboxEatReq(BaseModel):
    rec_rank: int = Field(ge=1, le=5)


def _build_decision_async(
    *,
    sid: str | None,
    meal_idx: int,
    picked_rec_view: dict,
    history: list[dict],
    job_id: str,
    mock: bool,
    root: Path,
) -> None:
    """BG task: 在 thread pool 跑. 必须显式重 set ContextVar (S-06c 修订 D).

    S-07: 入口 per-sid op lock (timeout=None 无限等, BG 不能返 409). 拿锁后
    reload state; 若 ``state.current_meal_idx <= meal_idx`` 说明 rollback 把
    我们的 meal_idx 已 truncate, 早退记 ``cancelled_by_rollback``.
    """
    started = _now_real_iso()
    with _JOB_LOCK:
        _JOB_TABLE[job_id] = {
            "status": "running",
            "started_at": started,
            "sid": sid,
            "meal_idx": meal_idx,
        }
    try:
        # S-07 Phase 4 Codex iter 2 #1: 持 _L1_EXTRACTION_LOCK 包整个 BG 周期, 让
        # reset/disable 的 _block_until_l1_idle_or_409 在 BG 跑期间 block. 与
        # CONTRACTS.md:98 reset/disable 互斥不变式对齐. 必须 BEFORE per-sid lock
        # 防 BG 进度被 reset 见缝插针 (status='running' 但 L1 lock 仍 free 的间隙).
        # _impl_l1_refresh 内部 acquire_lock=False 防 re-entrant 死锁.
        with _L1_EXTRACTION_LOCK:
            with _session_op_lock(sid, timeout=None, action="bg-decision"):
                # S-07 stale guard: 锁内 reload state; rollback 已截掉时早退
                state_p = _sandbox._state_path_for_sid(sid, root)
                if state_p.exists():
                    try:
                        cur_state = json.loads(state_p.read_text(encoding="utf-8"))
                        cur_idx_now = int(cur_state.get("current_meal_idx", 0))
                    except (OSError, json.JSONDecodeError):
                        cur_idx_now = meal_idx + 1   # 视为 ok, 继续 (state 损坏后续兜底)
                else:
                    cur_idx_now = 0
                if cur_idx_now <= meal_idx:
                    with _JOB_LOCK:
                        _JOB_TABLE[job_id] = {
                            "status": "cancelled_by_rollback",
                            "sid": sid,
                            "meal_idx": meal_idx,
                            "started_at": started,
                            "ended_at": _now_real_iso(),
                        }
                    return

                with _sandbox_ctx(sid):
                    if mock:
                        prev_prefs: dict = {}
                        new_prefs: dict = {}
                    else:
                        prev_prefs = _load_prefs_safe(root)
                        _impl_l1_refresh(
                            root,
                            force_no_llm=False,
                            window_days=None,
                            acquire_lock=False,   # outer with _L1_EXTRACTION_LOCK 已持
                        )
                        new_prefs = _load_prefs_safe(root)

                decision = build_decision(
                    sid=sid or _DEFAULT_SID_C,
                    meal_idx=meal_idx,
                    picked_rec=picked_rec_view,
                    prev_long_term_prefs=prev_prefs,
                    new_long_term_prefs=new_prefs,
                    history=history,
                    root=root,
                )
                _atomic_write_json(_decision_path(sid, meal_idx, root), decision)
            with _JOB_LOCK:
                _JOB_TABLE[job_id] = {
                    "status": "done",
                    "sid": sid,
                    "meal_idx": meal_idx,
                    "started_at": started,
                    "ended_at": _now_real_iso(),
                    "result": {"decision": decision, "meal_idx": meal_idx},
                }
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "build_decision_async failed: %s: %s", type(e).__name__, e,
        )
        with _JOB_LOCK:
            _JOB_TABLE[job_id] = {
                "status": "failed",
                "sid": sid,
                "meal_idx": meal_idx,
                "started_at": started,
                "ended_at": _now_real_iso(),
                "error": f"{type(e).__name__}: {e}",
            }


@router.post("/sandbox/sessions/{sid}/eat")
def api_sandbox_eat(
    request: Request,
    sid: str,
    req: SandboxEatReq,
    background_tasks: BackgroundTasks,
) -> dict:
    """S-06c: 选择第 rec_rank 条吃掉; advance + 启 BackgroundTask 抽 L1 + 派生 decision.

    S-07: 入口加 per-sid op lock 防与 rollback/branch 并发污染.
    """
    _require_localhost(request)
    routed_sid = _validate_and_route_sid(sid)
    with _session_op_lock(routed_sid, action="eat"):
        s = _ensure_not_done(routed_sid, ROOT)
        cur_idx = int(s.get("current_meal_idx", 0))

        last_p = _last_recs_path(routed_sid, ROOT)
        if not last_p.exists():
            raise HTTPException(404, "no last_recs.json; POST /recs first")
        try:
            last_recs = json.loads(last_p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise HTTPException(500, f"last_recs.json corrupt: {e}")

        candidates = last_recs.get("candidates") or []
        if not (1 <= req.rec_rank <= len(candidates)):
            raise HTTPException(400, f"rec_rank {req.rec_rank} out of range (have {len(candidates)} candidates)")

        is_mock = bool(last_recs.get("is_mock"))
        picked_raw = candidates[req.rec_rank - 1]
        recommend_session_id = last_recs.get("recommend_session_id", "")

        # mock 路径: candidates 本身就是 Rec 视图; 真实路径: 转换
        if is_mock:
            picked_rec_view = dict(picked_raw)
        else:
            picked_rec_view = format_v2_to_rec(picked_raw)

        # meal_to_trace[idx] = recommend_session_id
        _update_meal_to_trace(routed_sid, ROOT, cur_idx, recommend_session_id)

        # 真实路径: 调 _impl_accept 写 feedback_store + meal_log (mock 跳过)
        if not is_mock:
            try:
                with _sandbox_ctx(routed_sid):
                    accept_req = AcceptReq(
                        session_id=recommend_session_id,
                        candidate_rank=req.rec_rank,
                        candidate=picked_raw,
                    )
                    _impl_accept(accept_req)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(500, f"accept failed: {type(e).__name__}: {e}")

        # history append
        history_entry = {
            "idx": cur_idx,
            "state": "eat",
            "dish": picked_rec_view.get("name", ""),
            "session_id": recommend_session_id,
            "accepted_at": _now_real_iso(),
            "rank": req.rec_rank,
        }
        history_after = _append_history(routed_sid, ROOT, history_entry)

        # advance meal clock
        try:
            new_state = _sandbox.advance_meal(sid=routed_sid, root=ROOT)
        except RuntimeError as e:
            raise HTTPException(500, f"advance_meal failed: {e}")

        # 清 last_recs (下顿要重 POST /recs)
        try:
            last_p.unlink()
        except OSError:
            pass

        # 启 BackgroundTask: build decision diff
        job_id = _secrets.token_hex(8)
        with _JOB_LOCK:
            _JOB_TABLE[job_id] = {
                "status": "pending",
                "sid": routed_sid,
                "meal_idx": cur_idx,
                "started_at": _now_real_iso(),
            }
        background_tasks.add_task(
            _build_decision_async,
            sid=routed_sid,
            meal_idx=cur_idx,
            picked_rec_view=picked_rec_view,
            history=history_after,
            job_id=job_id,
            mock=is_mock,
            root=ROOT,
        )

        return {
            "job_id": job_id,
            "status": "running",
            "new_meal_idx": int(new_state.get("current_meal_idx", cur_idx + 1)),
            "meal_idx_eaten": cur_idx,
        }


# ---------- POST /sandbox/sessions/{sid}/skip ----------


class SandboxSkipReq(BaseModel):
    reason: str | None = None


@router.post("/sandbox/sessions/{sid}/skip")
def api_sandbox_skip(
    request: Request,
    sid: str,
    req: SandboxSkipReq,
) -> dict:
    """S-06c: 跳过本顿. 同步落 decision (skip 不触发 L1 抽取).

    S-07: 入口 per-sid op lock.
    """
    _require_localhost(request)
    if req.reason is not None and req.reason not in _VALID_SKIP_REASONS:
        raise HTTPException(422, f"invalid skip reason: {req.reason!r}")
    routed_sid = _validate_and_route_sid(sid)
    with _session_op_lock(routed_sid, action="skip"):
        s = _ensure_not_done(routed_sid, ROOT)
        cur_idx = int(s.get("current_meal_idx", 0))

        history_entry = {
            "idx": cur_idx,
            "state": "skip",
            "reason": req.reason,
            "session_id": None,
            "accepted_at": None,
        }
        history_after = _append_history(routed_sid, ROOT, history_entry)

        try:
            new_state = _sandbox.advance_meal(sid=routed_sid, root=ROOT)
        except RuntimeError as e:
            raise HTTPException(500, f"advance_meal failed: {e}")

        # 清 last_recs best-effort
        last_p = _last_recs_path(routed_sid, ROOT)
        if last_p.exists():
            try:
                last_p.unlink()
            except OSError:
                pass

        # 同步 decision (skip 路径 prefs 都空, build_decision 返"跳过未学习")
        decision = build_decision(
            sid=routed_sid or _DEFAULT_SID_C,
            meal_idx=cur_idx,
            picked_rec=None,
            prev_long_term_prefs={},
            new_long_term_prefs={},
            history=history_after,
            root=ROOT,
        )
        _atomic_write_json(_decision_path(routed_sid, cur_idx, ROOT), decision)

        return {
            "new_meal_idx": int(new_state.get("current_meal_idx", cur_idx + 1)),
            "meal_idx_skipped": cur_idx,
            "decision": decision,
        }


# ---------- POST /sandbox/sessions/{sid}/swap ----------


class SandboxSwapReq(BaseModel):
    exclude_ids: list[str] = Field(default_factory=list)


@router.post("/sandbox/sessions/{sid}/swap")
def api_sandbox_swap(
    request: Request,
    sid: str,
    req: SandboxSwapReq,
    mock_recommend: int = 0,
) -> dict:
    """S-06c 修订 B: swap = recommend_meal 重跑 + post-filter exclude_ids. 不调 refine.

    S-07: 入口 per-sid op lock.
    """
    _require_localhost(request)
    routed_sid = _validate_and_route_sid(sid)
    with _session_op_lock(routed_sid, action="swap"):
        s = _ensure_not_done(routed_sid, ROOT)
        cur_idx = int(s.get("current_meal_idx", 0))

        last_p = _last_recs_path(routed_sid, ROOT)
        if not last_p.exists():
            raise HTTPException(404, "no last_recs.json; POST /recs first")
        try:
            last_recs = json.loads(last_p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise HTTPException(500, f"last_recs.json corrupt: {e}")

        is_mock = bool(last_recs.get("is_mock")) or mock_recommend == 1
        exclude_ids = list(req.exclude_ids or [])

        if is_mock:
            current_recs = _mock_recs_data(exclude_ids=exclude_ids)
            candidates = current_recs
            recommend_session_id = f"mock_{_secrets.token_hex(4)}"
        else:
            meal_type, _day = _sandbox.meal_idx_to_slot(cur_idx)
            with _sandbox_ctx(routed_sid):
                try:
                    out = recommend_meal(
                        meal_type=meal_type,
                        daily_mood=None,
                        log_to_file=True,
                        root=ROOT,
                    )
                except Exception as e:
                    raise HTTPException(500, f"recommend_meal failed: {type(e).__name__}: {e}")
            excl = set(exclude_ids)
            candidates = [c for c in out["candidates"] if (c.get("id") or "") not in excl]
            current_recs = [format_v2_to_rec(c) for c in candidates]
            recommend_session_id = out["session_id"]

        new_payload = {
            "recommend_session_id": recommend_session_id,
            "candidates": candidates,
            "currentRecs": current_recs,
            "applied_refine": last_recs.get("applied_refine"),   # swap 不清 refine
            "meal_idx": cur_idx,
            "is_mock": is_mock,
            "saved_at": _now_real_iso(),
        }
        _atomic_write_json(last_p, new_payload)
        return {
            "currentRecs": current_recs,
            "recommend_session_id": recommend_session_id,
        }


# ---------- POST /sandbox/sessions/{sid}/refine ----------


class SandboxRefineReq(BaseModel):
    text: str = Field(min_length=1)


@router.post("/sandbox/sessions/{sid}/refine")
def api_sandbox_refine(
    request: Request,
    sid: str,
    req: SandboxRefineReq,
    mock_recommend: int = 0,
) -> dict:
    """S-06c: refine 同 round; 覆盖 last_recs + 写 applied_refine.

    S-07: 入口 per-sid op lock.
    """
    _require_localhost(request)
    routed_sid = _validate_and_route_sid(sid)
    with _session_op_lock(routed_sid, action="refine"):
        s = _ensure_not_done(routed_sid, ROOT)
        cur_idx = int(s.get("current_meal_idx", 0))

        last_p = _last_recs_path(routed_sid, ROOT)
        if not last_p.exists():
            raise HTTPException(404, "no last_recs.json; POST /recs first")
        try:
            last_recs = json.loads(last_p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise HTTPException(500, f"last_recs.json corrupt: {e}")

        is_mock = bool(last_recs.get("is_mock")) or mock_recommend == 1

        if is_mock:
            current_recs = _mock_refine_recs_data(req.text)
            candidates = current_recs
            new_recommend_sid = f"mock_{_secrets.token_hex(4)}"
            new_round = (last_recs.get("applied_refine") or {}).get("sinceRound", 1) + 1
        else:
            old_sid = last_recs.get("recommend_session_id", "")
            try:
                with _sandbox_ctx(routed_sid):
                    refine_req = RefineReq(
                        session_id=old_sid,
                        refine_text=req.text,
                    )
                    refine_out = _impl_refine(refine_req)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(500, f"refine failed: {type(e).__name__}: {e}")
            candidates = refine_out.get("candidates") or []
            current_recs = [
                format_v2_to_rec(
                    c,
                    refine_intent=refine_out.get("refine_intent"),
                    intent_override=req.text[:12],
                )
                for c in candidates
            ]
            new_recommend_sid = refine_out.get("session_id", old_sid)
            new_round = int(refine_out.get("round", 2))

        applied_refine = {
            "label": req.text[:20],
            "sinceRound": new_round,
            "sessionId": new_recommend_sid,
        }
        new_payload = {
            "recommend_session_id": new_recommend_sid,
            "candidates": candidates,
            "currentRecs": current_recs,
            "applied_refine": applied_refine,
            "meal_idx": cur_idx,
            "is_mock": is_mock,
            "saved_at": _now_real_iso(),
        }
        _atomic_write_json(last_p, new_payload)
        return {
            "currentRecs": current_recs,
            "recommend_session_id": new_recommend_sid,
            "activeRules": {
                "refine": [applied_refine],
                "blacklist": [],
            },
        }


# ---------- GET /sandbox/sessions/{sid}/jobs/{job_id} ----------


@router.get("/sandbox/sessions/{sid}/jobs/{job_id}")
def api_sandbox_job_status(
    request: Request,
    sid: str,
    job_id: str,
) -> dict:
    """S-06c: 查 BackgroundTask 状态. in-memory, server restart 后丢."""
    _require_localhost(request)
    _ = _validate_and_route_sid(sid)   # 校验 sid 合法
    with _JOB_LOCK:
        info = _JOB_TABLE.get(job_id)
    if info is None:
        raise HTTPException(404, f"job_id={job_id!r} not found")
    return dict(info)


# ════════════════════════════════════════════════════════════════════════════
# S-07: rollback / branch + GET FullSnapshot
# ════════════════════════════════════════════════════════════════════════════

import shutil as _shutil


class SessionMetaFull(BaseModel):
    """S-07 §D: FullSnapshot 子 model. 与 S-06a 的 SandboxSessionMeta 区分:
    后者是 list view 元数据 (size_bytes 等), 这里是前端 useSandbox 消费的完整
    session meta (per design brief §SessionMeta).
    """
    sid: str
    name: str = ""
    days: int
    seed: int = 0
    profile: str = "profile@v2"
    origin: str = "blank"
    status: str  # "running" | "done"
    lastUsed: str = ""
    currentMealIdx: int
    totalMeals: int
    branchFrom: str | None = None


class SandboxClock(BaseModel):
    idx: int
    day: int
    slot: str   # "lunch" | "dinner"
    total: int


class FullSnapshotResp(BaseModel):
    """S-07 §D: brief §FullSnapshot 完整 view-model. taste/keywords/recent/fatigue
    暂留空 list (S-08 派生填). meta/clock/history/currentRecs/lastDecision/activeRules
    本任务真填.
    """
    meta: SessionMetaFull
    clock: SandboxClock
    history: list[dict]
    currentRecs: list[dict]
    lastDecision: dict | None
    activeRules: dict
    taste: list[dict] = Field(default_factory=list)
    keywords: list[dict] = Field(default_factory=list)
    recent: list[str] = Field(default_factory=list)
    fatigue: list[dict] = Field(default_factory=list)
    # S-09: 历史顿 idx -> trace_session_id (eat 时落; meal_to_trace.json)
    mealToTrace: dict = Field(default_factory=dict)
    # S-09: 当前顿 (uneaten) recommend_session_id (last_recs.json); None 表示无 active recs
    currentTraceId: str | None = None


def _build_full_snapshot(routed_sid: str | None, root: Path) -> FullSnapshotResp:
    """从 sessions/{sid}/state.json + history + last_recs + 最近 decision 派生."""
    state_p = _sandbox._state_path_for_sid(routed_sid, root)
    if not state_p.exists():
        raise HTTPException(
            404, f"sandbox session {routed_sid or '_default'!r} has no state.json",
        )
    try:
        st = json.loads(state_p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(500, f"sandbox state corrupt: {e}")
    if not isinstance(st, dict):
        raise HTTPException(500, "sandbox state malformed")

    cur_idx = int(st.get("current_meal_idx", 0))
    total = int(st.get("total_meals", 14))
    days_v = total // 2 or 7

    # clock: idx == total 表示 done sentinel, slot 仍用 idx 派生但 idx>=total 退化为 dinner
    if cur_idx < total:
        slot, day = _sandbox.meal_idx_to_slot(cur_idx)
    else:
        slot = "dinner"
        day = days_v
    clock = SandboxClock(idx=cur_idx, day=day, slot=slot, total=total)

    meta = SessionMetaFull(
        sid=str(st.get("sid") or routed_sid or _DEFAULT_SID_C),
        name=str(st.get("name") or ""),
        days=days_v,
        seed=int(st.get("seed") or 0),
        profile=str(st.get("profile") or "profile@v2"),
        origin=str(st.get("origin") or "blank"),
        status="done" if cur_idx >= total else "running",
        lastUsed=str(st.get("started_at_real") or ""),
        currentMealIdx=cur_idx,
        totalMeals=total,
        branchFrom=st.get("branch_from"),
    )

    history = _load_history(routed_sid, root)

    last_recs_data: dict = {}
    last_p = _last_recs_path(routed_sid, root)
    if last_p.exists():
        try:
            last_recs_data = json.loads(last_p.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            last_recs_data = {}
    current_recs = list(last_recs_data.get("currentRecs") or [])
    applied_refine = last_recs_data.get("applied_refine")
    active_refine = [applied_refine] if applied_refine else []

    last_decision: dict | None = None
    if cur_idx > 0:
        dec_p = _decision_path(routed_sid, cur_idx - 1, root)
        if dec_p.exists():
            try:
                last_decision = json.loads(dec_p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                last_decision = None

    # S-09: meal_to_trace + current recommend_session_id
    m2t = _load_meal_to_trace(routed_sid, root)
    current_tsid = last_recs_data.get("recommend_session_id") or None

    return FullSnapshotResp(
        meta=meta,
        clock=clock,
        history=history,
        currentRecs=current_recs,
        lastDecision=last_decision,
        activeRules={"refine": active_refine, "blacklist": []},
        taste=[],
        keywords=[],
        recent=[],
        fatigue=[],
        mealToTrace=m2t,
        currentTraceId=current_tsid,
    )


@router.get("/sandbox/sessions/{sid}", response_model=FullSnapshotResp)
def api_sandbox_get_full_snapshot(request: Request, sid: str) -> FullSnapshotResp:
    """S-07: 完整 FullSnapshot (前端 useSandbox 初始化 / rollback 后刷新).

    Default sid 允许 (返 default 桶 snapshot). 非 default sid 走 _validate_and_route_sid.
    GET 只读不加 op lock.
    """
    _require_localhost(request)
    routed_sid = _validate_and_route_sid(sid)
    return _build_full_snapshot(routed_sid, ROOT)


class SandboxRollbackReq(BaseModel):
    meal_idx: int = Field(ge=0)


class SandboxBranchReq(BaseModel):
    from_meal_idx: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=64)


def _filter_jsonl_by_session_ids(
    src: Path, trash_sids: set[str],
) -> str:
    """读 jsonl, 剔除 session_id ∈ trash_sids 的行, 返新 content (含尾 \\n)."""
    # S-07 Phase 4 Codex iter 1 #3: 不再 swallow OSError; raise 让 rollback restore.
    if not src.exists():
        return ""
    lines_kept: list[str] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # 损坏行: 保留原文 (不丢用户数据)
            lines_kept.append(line)
            continue
        sid_in_line = entry.get("session_id")
        if sid_in_line and sid_in_line in trash_sids:
            continue
        lines_kept.append(line)
    return ("\n".join(lines_kept) + "\n") if lines_kept else ""


def _rollback_session_impl(
    routed_sid: str | None,
    meal_idx: int,
    root: Path,
    *,
    _internal: bool = False,
) -> FullSnapshotResp:
    """S-07 §B: 全事务裁剪. 单一 commit 边界 = state.json os.replace 列尾.

    _internal=True: caller (branch) 已持 per-sid op lock, 跳过 acquire.
    _internal=False: 默认走 lock guard (rollback handler).
    """
    if routed_sid is None:
        raise HTTPException(400, "rollback not supported on default sandbox bucket")

    state_p = _sandbox._state_path_for_sid(routed_sid, root)
    if not state_p.exists():
        raise HTTPException(
            404, f"sandbox session {routed_sid!r} has no state.json",
        )
    try:
        state = json.loads(state_p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(500, f"sandbox state corrupt: {e}")
    if not isinstance(state, dict):
        raise HTTPException(500, "sandbox state malformed")

    cur_idx = int(state.get("current_meal_idx", 0))
    total = int(state.get("total_meals", 14))
    if not (0 <= meal_idx < cur_idx):
        raise HTTPException(
            400, f"meal_idx={meal_idx} not in [0, {cur_idx}) — nothing to rollback",
        )

    # ─ Stage new content ─
    bucket = _sb_bucket(routed_sid, root)
    tmp_dir = bucket / ".rollback_tmp"
    if tmp_dir.exists():
        _shutil.rmtree(tmp_dir, ignore_errors=True)
    new_dir = tmp_dir / "new"
    backup_dir = tmp_dir / "backup"
    new_dir.mkdir(parents=True)
    backup_dir.mkdir()

    # state.json: 派生新版本
    day_index_new = meal_idx // 2 + 1
    started_virtual = state.get("started_at_virtual")
    if started_virtual:
        try:
            cur_date = (
                dt.date.fromisoformat(started_virtual)
                + dt.timedelta(days=day_index_new - 1)
            ).isoformat()
        except (TypeError, ValueError):
            cur_date = state.get("current_date") or ""
    else:
        cur_date = state.get("current_date") or ""
    new_state = dict(state)
    new_state["current_meal_idx"] = meal_idx
    new_state["day_index"] = day_index_new
    new_state["current_date"] = cur_date
    new_state["last_l1_extraction"] = None

    # history slice
    history_all = _load_history(routed_sid, root)
    new_history = history_all[:meal_idx]

    # meal_to_trace 截断 + 收集 trash_tsids
    m2t = _load_meal_to_trace(routed_sid, root)
    trash_tsids: set[str] = set()
    new_m2t: dict[str, str] = {}
    for k, v in m2t.items():
        try:
            ik = int(k)
        except ValueError:
            new_m2t[k] = v
            continue
        if ik >= meal_idx:
            if isinstance(v, str) and v:
                trash_tsids.add(v)
        else:
            new_m2t[k] = v

    # S-07 Phase 4 Codex iter 1 #2: last_recs 含未 eaten 的 recommend_session_id, 该
    # session 已落 D-039 session/{tsid}.json + recommend_log 行 + trace 文件, 必须
    # 也算 trash (否则 branch 后未来 candidates 仍可被 refine.load_session 读到).
    last_recs_p_pre = _last_recs_path(routed_sid, root)
    if last_recs_p_pre.exists():
        try:
            last_recs_pre_data = json.loads(last_recs_p_pre.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            last_recs_pre_data = {}
        lr_sid = last_recs_pre_data.get("recommend_session_id")
        lr_idx_raw = last_recs_pre_data.get("meal_idx", -1)
        try:
            lr_idx = int(lr_idx_raw) if lr_idx_raw is not None else -1
        except (ValueError, TypeError):
            lr_idx = -1
        if (
            lr_sid and isinstance(lr_sid, str)
            and not lr_sid.startswith("mock_")  # mock 没落实际 file, 跳
            and lr_idx >= meal_idx
        ):
            trash_tsids.add(lr_sid)

    # Stage new files
    (new_dir / "state.json").write_text(
        json.dumps(new_state, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (new_dir / "history.json").write_text(
        json.dumps(new_history, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (new_dir / "meal_to_trace.json").write_text(
        json.dumps(new_m2t, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (new_dir / "long_term_prefs.json").write_text("{}", encoding="utf-8")

    # sandbox-aware paths (ContextVar 内)
    from chisha import data_root as _data_root
    from chisha.sandbox_context import set_sandbox_session as _set_sb
    with _set_sb(routed_sid):
        ml_target = _data_root.meal_log_path(root)
        rl_target = _data_root.recommend_log_path(root)
        ltp_target = _data_root.long_term_prefs_path(root)
        trace_dir = _data_root.recommend_trace_dir(root)
        sessions_dir_target = _data_root.sessions_dir(root)  # D-039 recommend session files

    # Filter jsonl — OSError 由 _filter_jsonl_by_session_ids 透传, 由下方 commit try
    # 不接, 但 finally 兜 tmp_dir 清理. 兜底见下方 except OSError.
    try:
        new_ml_content = _filter_jsonl_by_session_ids(ml_target, trash_tsids)
        new_rl_content = _filter_jsonl_by_session_ids(rl_target, trash_tsids)
        (new_dir / "meal_log.jsonl").write_text(new_ml_content, encoding="utf-8")
        (new_dir / "recommend_log.jsonl").write_text(new_rl_content, encoding="utf-8")
    except OSError:
        # staging IO 失败: 还没进 commit 阶段, target 文件 untouched. 清 tmp_dir + raise.
        _shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    # Target paths
    m2t_p = _meal_to_trace_path(routed_sid, root)
    hist_p = _history_path(routed_sid, root)
    last_recs_p = _last_recs_path(routed_sid, root)

    # ─ actions list, state.json 列尾 ─
    actions: list[tuple[Path, Path | None, str]] = []
    actions.append((m2t_p, new_dir / "meal_to_trace.json", "replace"))
    actions.append((hist_p, new_dir / "history.json", "replace"))
    actions.append((ltp_target, new_dir / "long_term_prefs.json", "replace"))
    actions.append((ml_target, new_dir / "meal_log.jsonl", "replace"))
    actions.append((rl_target, new_dir / "recommend_log.jsonl", "replace"))
    if last_recs_p.exists():
        actions.append((last_recs_p, None, "delete"))
    dec_dir = bucket / "decisions"
    if dec_dir.exists():
        try:
            for f in sorted(dec_dir.iterdir()):
                if not f.name.endswith(".json"):
                    continue
                try:
                    idx = int(f.stem)
                except ValueError:
                    continue
                if idx >= meal_idx:
                    actions.append((f, None, "delete"))
        except OSError:
            pass
    for tsid in sorted(trash_tsids):
        v2 = trace_dir / f"{tsid}.json"
        if v2.exists():
            actions.append((v2, None, "delete"))
        v3 = trace_dir / tsid
        if v3.is_dir():
            actions.append((v3, None, "delete_dir"))
        # S-07 Phase 4 Codex iter 1 #4: D-039 recommend session JSON file
        d039 = sessions_dir_target / f"{tsid}.json"
        if d039.exists():
            actions.append((d039, None, "delete"))
    # state.json 列尾 (commit barrier)
    actions.append((state_p, new_dir / "state.json", "replace"))

    backed_up: list[tuple[Path, Path, str]] = []
    committed: list[Path] = []
    try:
        for idx, (target, new_p, kind) in enumerate(actions):
            if kind == "delete_dir":
                if target.exists():
                    bp = backup_dir / f"d_{idx}_{target.name}"
                    _shutil.move(str(target), str(bp))
                    backed_up.append((target, bp, "dir"))
                continue
            if target.exists():
                bp = backup_dir / f"f_{idx}_{target.name}"
                _os.replace(target, bp)
                backed_up.append((target, bp, "file"))
            if kind == "replace":
                target.parent.mkdir(parents=True, exist_ok=True)
                if new_p is None:
                    raise RuntimeError(f"replace kind needs new_p (action {idx})")
                _os.replace(new_p, target)
                committed.append(target)
            # kind == "delete": already backed up, target gone
    except Exception:
        # Restore in reverse order
        for target, bp, kind in reversed(backed_up):
            try:
                if target.exists():
                    if kind == "dir":
                        _shutil.rmtree(target, ignore_errors=True)
                    else:
                        try:
                            target.unlink()
                        except OSError:
                            pass
                if kind == "dir":
                    _shutil.move(str(bp), str(target))
                else:
                    _os.replace(bp, target)
            except OSError:
                pass
        _shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    # Cleanup tmp dir
    _shutil.rmtree(tmp_dir, ignore_errors=True)

    # 清 in-memory _JOB_TABLE entries for this sid (best-effort housekeeping)
    with _JOB_LOCK:
        stale_jids = [
            jid for jid, info in _JOB_TABLE.items()
            if info.get("sid") == routed_sid
            and info.get("status") in ("pending", "running")
        ]
        for jid in stale_jids:
            _JOB_TABLE[jid] = {
                **_JOB_TABLE[jid],
                "status": "cancelled_by_rollback",
                "ended_at": _now_real_iso(),
            }

    return _build_full_snapshot(routed_sid, root)


@router.post("/sandbox/sessions/{sid}/rollback", response_model=FullSnapshotResp)
def api_sandbox_rollback(
    request: Request, sid: str, req: SandboxRollbackReq,
) -> FullSnapshotResp:
    """S-07: 裁掉 meal_idx 及之后所有状态, state.json 是 commit barrier.

    内部 IO 异常 (OSError 等) 被 backup-restore 兜底后向上抛 → 转 HTTPException 500.

    Iter 4 Codex #4: 入口持 _L1_EXTRACTION_LOCK (与 BG 同 acquisition order: L1 → per-sid)
    防 reset/disable lifecycle 中段 rmtree(sandbox_dir) 破坏 rollback 写入. Reset/disable
    也持 L1 lock → 互斥串行化. eat/skip/swap/refine 等高频路径仍 sid-only (race surface
    较小, 留 future 升级).
    """
    _require_localhost(request)
    routed_sid = _validate_and_route_sid(sid)
    with _l1_extraction_lock_or_409("rollback"):
        with _session_op_lock(routed_sid, action="rollback"):
            try:
                return _rollback_session_impl(routed_sid, req.meal_idx, ROOT)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    500, f"rollback failed (state restored): {type(e).__name__}: {e}",
                )


@router.post("/sandbox/sessions/{sid}/branch", response_model=SandboxSessionMeta)
def api_sandbox_branch(
    request: Request, sid: str, req: SandboxBranchReq,
) -> SandboxSessionMeta:
    """S-07: 拷贝 src bucket → 新 bucket + 裁到 from_meal_idx + branch_from 元数据.

    Iter 4 Codex #4: 持 _L1_EXTRACTION_LOCK 防 reset/disable rmtree(sandbox_dir) 与
    copytree 并发 (源被删 → copytree partial). Lock 顺序 L1 → src-sid → new-sid 与
    BG / rollback 一致.
    """
    _require_localhost(request)
    routed_sid = _validate_and_route_sid(sid)
    if routed_sid is None:
        raise HTTPException(400, "branch not supported on default sandbox bucket")

    # validate from_meal_idx 范围 (在 lock 外 cheap)
    state_p = _sandbox._state_path_for_sid(routed_sid, ROOT)
    if not state_p.exists():
        raise HTTPException(404, f"sandbox session {routed_sid!r} has no state.json")

    with _l1_extraction_lock_or_409("branch"):
        with _session_op_lock(routed_sid, action="branch"):
            try:
                src_state = json.loads(state_p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                raise HTTPException(500, f"sandbox state corrupt: {e}")
            src_cur = int(src_state.get("current_meal_idx", 0))
            if not (0 <= req.from_meal_idx < src_cur):
                raise HTTPException(
                    400,
                    f"from_meal_idx={req.from_meal_idx} not in [0, {src_cur})",
                )

            # gen new_sid
            import time as _time
            ts = int(_time.time())
            new_sid = f"sandbox_{ts}_{_secrets.token_hex(4)}"

            src_bucket = _sb_bucket(routed_sid, ROOT)
            new_bucket = _sb_bucket(new_sid, ROOT)
            if new_bucket.exists():
                raise HTTPException(409, f"new sid collision: {new_sid!r}")

            try:
                _shutil.copytree(
                    src_bucket, new_bucket,
                    ignore=_shutil.ignore_patterns(".rollback_tmp"),
                )
            except OSError as e:
                raise HTTPException(500, f"copytree failed: {type(e).__name__}: {e}")

            try:
                with _session_op_lock(new_sid, action="branch-new"):
                    # rollback new bucket to from_meal_idx (skip outer lock acquire)
                    try:
                        _rollback_session_impl(
                            new_sid, req.from_meal_idx, ROOT, _internal=True,
                        )
                    except HTTPException:
                        raise
                    except Exception as e:
                        raise HTTPException(
                            500, f"branch rollback failed: {type(e).__name__}: {e}",
                        )

                    # patch new state.json with branch metadata
                    new_state_p = _sandbox._state_path_for_sid(new_sid, ROOT)
                    try:
                        new_st = json.loads(new_state_p.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as e:
                        raise HTTPException(500, f"new state corrupt: {e}")
                    new_st["sid"] = new_sid
                    new_st["name"] = req.name
                    new_st["branch_from"] = routed_sid
                    new_st["branch_from_meal_idx"] = req.from_meal_idx
                    new_st["started_at_real"] = _now_real_iso()
                    _atomic_write_json(new_state_p, new_st)
            except Exception:
                # 失败 → 清新桶, 不留半成品
                _shutil.rmtree(new_bucket, ignore_errors=True)
                raise

            # 返 SandboxSessionMeta (list view) — 客户端再 GET FullSnapshot
            return SandboxSessionMeta(
                sid=new_sid,
                is_default=False,
                created_at=_sandbox._entry_ctime_iso(new_bucket),
                size_bytes=_sandbox._dir_size_safe(new_bucket),
                has_state=(new_bucket / "state.json").exists(),
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


_L1_LOCK_WAIT_SECONDS = 30.0


def _block_until_l1_idle_or_409(action_label: str) -> None:
    """[已废弃 by S-07] D-078 Codex S2 Q3-High 的 probe-release 模式不闭环:
    probe 通过 → release → mutation 之间, 排队的 BG worker 可以抢锁继续跑.

    本函数保留签名以防外部 caller; 但实际语义已变 (现在仍是 probe-release).
    新代码用 ``_l1_extraction_lock_or_409`` context manager: 持锁穿透 lifecycle
    mutation, 保 CONTRACTS.md:98 不变式.
    """
    if _L1_EXTRACTION_LOCK.acquire(timeout=_L1_LOCK_WAIT_SECONDS):
        _L1_EXTRACTION_LOCK.release()
        return
    raise HTTPException(
        409, f"{action_label} blocked: L1 extraction worker busy >"
              f" {_L1_LOCK_WAIT_SECONDS:.0f}s, retry shortly"
    )


@_contextmanager
def _l1_extraction_lock_or_409(action_label: str):
    """S-07 Phase 4 Codex iter 3 #1 修订: 持 _L1_EXTRACTION_LOCK 穿透整个 reset/
    disable lifecycle mutation. probe-release 模式 (旧 _block_until_l1_idle_or_409)
    在 probe 通过到 mutation 之间有间隙, 让排队 BG worker 抢锁绕过保护.
    """
    if not _L1_EXTRACTION_LOCK.acquire(timeout=_L1_LOCK_WAIT_SECONDS):
        raise HTTPException(
            409,
            f"{action_label} blocked: L1 extraction worker busy >"
            f" {_L1_LOCK_WAIT_SECONDS:.0f}s, retry shortly",
        )
    try:
        yield
    finally:
        _L1_EXTRACTION_LOCK.release()


@router.post("/sandbox/advance")
def api_sandbox_advance(request: Request, req: SandboxAdvanceReq) -> dict:
    """虚拟时钟前进 N 天, 异步触发 L1 抽取."""
    _require_localhost(request)
    # D-078 Codex S2 Q2: L1 pending 时直接 409, 防 UI bypass 用裸 POST 绕过
    # SandboxBar disable 按钮. trylock 跳过 (旧行为) 会让新日期推荐用 stale prefs.
    st = _sandbox.state(root=ROOT)
    if (st.get("last_l1_extraction") or {}).get("status") == "pending":
        raise HTTPException(
            409, "advance blocked: L1 extraction in progress, retry after settle"
        )
    try:
        s = _sandbox.advance(days=req.days, root=ROOT)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    # 异步起 L1 抽取
    _trigger_l1_extraction_async(ROOT)
    return s


@router.post("/sandbox/reset")
def api_sandbox_reset(request: Request) -> dict:
    """删干净 sandbox 目录, prod 零风险.

    D-078 Codex S2 Q3-High + S-07 Phase 4 iter 3 #1: 持 _L1_EXTRACTION_LOCK
    穿透 _sandbox.reset() 整个 lifecycle. 防 probe-release 间隙让排队 BG worker
    抢锁继续 save_prefs (sandbox 已 disable → 写回 prod long_term_prefs.json).
    """
    _require_localhost(request)
    with _l1_extraction_lock_or_409("reset"):
        return _sandbox.reset(root=ROOT)


@router.post("/sandbox/disable")
def api_sandbox_disable(request: Request) -> dict:
    """退出 sandbox 但保留数据 (下次 init 可复用).

    S-07 Phase 4 iter 3 #1: 同 reset, 持锁穿透 disable() lifecycle.
    """
    _require_localhost(request)
    with _l1_extraction_lock_or_409("disable"):
        return _sandbox.disable(root=ROOT)


@router.get("/sandbox/state")
def api_sandbox_state(
    request: Request,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """S-06a: sid inject 是 forward-compatible no-op (state.state(session_id=...)
    在 S-04 仍 ignore sid; S-06b 真实现). 测试守门
    ``test_state_endpoint_sid_inject_is_noop_until_s06b``."""
    _require_localhost(request)
    with _sandbox_ctx(_sid):
        return _sandbox.state(root=ROOT)


# ---------- /api/debug/* (D-079 PR-2: Replay + What-if) ----------

class WhatIfOverrides(BaseModel):
    """What-if 可改字段白名单 (DESIGN §4.2). Pydantic 校验 + extra='forbid' 拒绝
    未知字段, 防止前端误传 frozen 字段误改 (违反 §4.1 冻结边界)."""
    model_config = {"extra": "forbid"}

    n_return: int | None = Field(default=None, ge=1, le=10)
    n_explore: int | None = Field(default=None, ge=0, le=5)
    use_llm_rerank: bool | None = None
    profile_overrides: dict[str, Any] | None = None


class WhatIfReq(BaseModel):
    """POST /api/debug/what_if body."""
    model_config = {"extra": "forbid"}

    base_session_id: str = Field(min_length=1)
    overrides: WhatIfOverrides = Field(default_factory=WhatIfOverrides)


@router.get("/debug/sessions")
def api_debug_sessions(
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


@router.get("/debug/sessions/{session_id}")
def api_debug_session_detail(request: Request, session_id: str) -> dict:
    """D-079 §7.2: 单条完整 trace.

    Failure matrix (§7 Preamble):
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

    # 附 feedback record (与 list 派生字段同口径, replay 详情页要看完整反馈链)
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
        # feedback link 失败不阻断 trace 返回 (与 attach_feedback_links 同口径)
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "attach feedback for trace %s failed: %s: %s",
            session_id, type(e).__name__, e,
        )
        trace["__feedback"] = None
    return trace


@router.post("/debug/what_if")
def api_debug_what_if(request: Request, req: WhatIfReq) -> dict:
    """D-079 §7.3: What-if 重跑. 冻结上游 ctx/L1, 重跑 L2+L3.

    Response: shape 同 GET 单条 trace, 但 __source='what_if_preview' +
    __parent_session_id=base_sid + __llm_called=bool. **永不写盘**.

    Failure matrix:
      - 400 overrides 非白名单 (pydantic 已挡, 兜底再挡一层)
      - 400 base trace __source != production
      - 404 base trace 不存在
      - 409 schema 版本不匹配
      - 500 trace 损坏 / L2/L3 内部错
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
        # source!=production / 缺 __frozen / today 不合法 — 都是请求级错误
        # (用户挑了不能 What-if 的 base trace), 400 而非 500
        raise HTTPException(400, f"invalid base trace: {e}")
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except trace_store.TraceCorrupt as e:
        raise HTTPException(500, f"base trace corrupt: {e}")
    except trace_store.TraceVersionMismatch as e:
        raise HTTPException(
            409, f"trace schema version mismatch: found={e.found}, expected={e.expected}"
        )
    # 注: Codex PR-2 FIX-NOW #2 — 不再 catch 裸 ValueError. score/rerank 内部
    # 抛 ValueError 是 5xx 范畴, 应通过 FastAPI 默认 handler 走 500.


@router.get("/sandbox/inspect")
def api_sandbox_inspect(
    request: Request,
    _sid: str | None = Depends(_with_sandbox_sid),
) -> dict:
    """S-06a: 三态 inspect.

    | state | 触发条件 | 返回 |
    | no-layout | not has_sandbox_meta + not is_enabled | enabled=False, has_layout=False, sessions=[] |
    | layout-disabled | has_sandbox_meta + not is_enabled | enabled=False, has_layout=True, sessions=[...] |
    | layout-enabled | is_enabled | 原 snapshot + has_layout=True + sessions=[...] |
    """
    _require_localhost(request)
    with _sandbox_ctx(_sid):
        return _impl_inspect()


def _impl_inspect() -> dict:
    enabled = _sandbox.is_enabled(ROOT)
    has_layout = _sandbox.has_sandbox_meta(ROOT)
    if not enabled:
        if not has_layout:
            return {"enabled": False, "has_layout": False, "sessions": []}
        # layout-disabled
        return {
            "enabled": False,
            "has_layout": True,
            "sessions": _sandbox.list_sessions(root=ROOT),
        }

    state = _sandbox.state(root=ROOT)

    # L1 prefs (D-078.3): load_prefs 在 boost+penalty 都空时返 None (L2 等价语义),
    # 但 inspect 必须显示磁盘 raw 内容 — regularities_freetext / signals_not_scored /
    # evidence 是 LLM 抽取的非词表沉淀, debug 台必须可见, 不能被"L2 等价 None"语义藏掉.
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

    # 最近 10 条 V1.1 反馈
    feedbacks_recent: list[dict] = []
    try:
        store = feedback_store.load_store(ROOT)
        items = list((store.get("feedbacks") or {}).values())
        items.sort(key=lambda x: x.get("submitted_at") or "", reverse=True)
        feedbacks_recent = items[:10]
    except Exception:
        pass

    # 最近 10 条 meal_log
    meal_log_recent: list[dict] = []
    try:
        meal_log_recent = (load_meal_log(ROOT) or [])[-10:]
    except Exception:
        pass

    # accepted 队列概览
    accepted_count = 0
    try:
        accepted_count = len(store.get("accepted") or {})
    except Exception:
        pass

    return {
        "enabled": True,
        # S-06a 三态新增字段
        "has_layout": True,
        "sessions": _sandbox.list_sessions(root=ROOT),
        "state": state,
        "long_term_prefs": prefs or None,
        # D-078.3: raw 磁盘内容. 即使 boost+penalty 都空, regularities_freetext /
        # signals_not_scored / evidence 也对 debug 有价值.
        "long_term_prefs_raw": prefs_raw,
        "feedbacks_recent": feedbacks_recent,
        "feedbacks_total": len(feedbacks_recent),
        "meal_log_recent": meal_log_recent,
        "accepted_count": accepted_count,
    }


# ══════════════════════════════════════════════════════════════════════
# D-087 Workflow A 「分析 trace」 debug-ui 端点
# ══════════════════════════════════════════════════════════════════════

def _attach_feedback_to_meta(item: dict, store_data: dict) -> dict:
    """从 feedback_store 派生 TraceMeta.feedback 字段 (前端 TraceBrowser 用).

    D-088 (B4): accepted 分支带 restaurant_name. 没它前端列表只能显示笼统 #2,
    用户看不出实际选了哪家.
    """
    sid = item.get("session_id")
    accepted = (store_data.get("accepted") or {}).get(sid)
    fb = (store_data.get("feedbacks") or {}).get(sid)
    if accepted and not (accepted or {}).get("skipped"):
        out: dict = {"type": "accepted"}
        if (accepted or {}).get("accepted_rank"):
            out["rank"] = accepted["accepted_rank"]
        if (accepted or {}).get("restaurant_name"):
            out["restaurant_name"] = accepted["restaurant_name"]
        return out
    if accepted and (accepted or {}).get("stopped"):
        return {"type": "stopped"}
    if fb and (fb or {}).get("rating") is not None:
        return {"type": "rated", "count": int(fb["rating"])}
    return None  # type: ignore[return-value]


def _enrich_meta_for_traces(item: dict, today_iso: str) -> dict:
    """list_traces_v3 item → 前端 TraceMeta (含 daysAgo / date / time / meal / status)."""
    started_at = item.get("started_at") or ""
    date_str = ""
    time_str = ""
    days_ago = 0
    try:
        if "T" in started_at or " " in started_at:
            # ISO-ish
            sep = "T" if "T" in started_at else " "
            date_str, _, hms = started_at.partition(sep)
            time_str = hms[:5]  # HH:MM
            today = dt.date.fromisoformat(today_iso)
            d0 = dt.date.fromisoformat(date_str)
            days_ago = max(0, (today - d0).days)
    except Exception:
        pass
    top1 = item.get("top1_summary") or ""
    # 取 top1 第一个 · 之前的部分作为 restaurant (UI 显示)
    rest_name = top1.split(" · ")[0] if top1 else ""
    status = "ok"
    l3 = item.get("l3_status")
    if l3 == "fallback":
        status = "fallback"
    elif l3 == "config_error" or l3 == "warn":
        status = "warn"
    refine_count = int(item.get("refine_count") or 0)
    return {
        "id": item.get("session_id"),
        "date": date_str,
        "time": time_str,
        "daysAgo": days_ago,
        "meal": item.get("meal_type") or "lunch",
        "finalTop1": rest_name,
        "refineCount": refine_count,
        "latestRound": item.get("latest_round") or "R1",
        "source": "sandbox" if item.get("source") == "sandbox" else "real",
        "sandboxDay": None,
        "feedback": item.get("feedback"),
        "status": status,
        "latency_ms": int(item.get("total_latency_ms") or 0),
    }


@router.get("/traces")
def api_traces(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    meal_type: str | None = Query(default=None),
) -> list[dict]:
    """D-087 Workflow A: list traces (TraceBrowser 数据源).

    返扁平 list of TraceMeta. 与旧 /api/debug/sessions 并存 (旧端点不删).
    """
    _require_localhost(request)
    if meal_type is not None and meal_type not in ("lunch", "dinner"):
        raise HTTPException(400, f"meal_type must be lunch|dinner|null, got {meal_type!r}")
    from chisha import trace_store
    items, _corrupt = trace_store.list_traces_v3(
        root=ROOT, limit=limit, meal_type=meal_type,
    )
    # attach feedback
    try:
        store = feedback_store.load_store(ROOT)
    except Exception:
        store = {}
    today_iso = dt.date.today().isoformat()
    out: list[dict] = []
    for it in items:
        it["feedback"] = _attach_feedback_to_meta(it, store)
        out.append(_enrich_meta_for_traces(it, today_iso))
    return out


@router.get("/trace/{session_id}")
def api_trace_detail(request: Request, session_id: str) -> dict:
    """D-087 Workflow A: 单 trace 详情 = meta + rounds[stub] (不含 l1/l2/l3/final body).

    Failure matrix:
      - 404 不存在
      - 409 schema version 不识别
      - 500 损坏
    """
    _require_localhost(request)
    from chisha import trace_store
    try:
        view = trace_store.read_trace_v3_view(session_id, root=ROOT)
    except trace_store.TraceCorrupt as e:
        raise HTTPException(500, f"trace corrupt: {e}")
    except trace_store.TraceVersionMismatch as e:
        raise HTTPException(
            409, f"trace schema version mismatch: found={e.found}, expected={e.expected}",
        )
    if view is None:
        raise HTTPException(404, f"trace {session_id!r} not found")
    # 附 feedback 到 meta
    try:
        store = feedback_store.load_store(ROOT)
        view["meta"]["feedback"] = _attach_feedback_to_meta(
            {"session_id": session_id}, store,
        )
    except Exception:
        view["meta"]["feedback"] = None
    return view


@router.get("/trace/{session_id}/round/{round_id}")
def api_trace_round(
    request: Request, session_id: str, round_id: str,
) -> dict:
    """D-087 Workflow A: 单 round 完整 body (l1/l2/l3/final/__frozen).

    Failure matrix:
      - 404 trace 或 round 不存在
      - 500 损坏
    """
    _require_localhost(request)
    from chisha import trace_store
    try:
        rd = trace_store.read_round_full(session_id, round_id, root=ROOT)
    except trace_store.TraceCorrupt as e:
        raise HTTPException(500, f"round corrupt: {e}")
    if rd is None:
        raise HTTPException(
            404, f"round {session_id!r}/{round_id!r} not found",
        )
    return rd


@router.get("/intent_schema")
def api_intent_schema(request: Request) -> list[dict]:
    """D-087 Workflow A: IntentStrip 字段描述符 (schema-driven).

    Codex 推荐: 字段集由后端 owner, 前端按 descriptor 渲染. V2 schema 后续扩字段
    无需动前端. 未知字段前端进 'other' 分组兜底.
    """
    _require_localhost(request)
    # 与 apps/debug-ui/src/constants/intentSchema.ts INTENT_SCHEMA 一一对应.
    # 若后续扩 V2 schema, 加 entry 即可; 前端 schema-driven 自动渲染.
    return [
        {"key": "redirect.cuisine_want", "label": "菜系想", "tone": "want",
         "group": "redirect", "slot_path": ["redirect", "cuisine_want"]},
        {"key": "redirect.cuisine_avoid", "label": "菜系不想", "tone": "avoid",
         "group": "redirect", "slot_path": ["redirect", "cuisine_avoid"]},
        {"key": "redirect.cuisine_candidates_expanded", "label": "菜系扩展",
         "tone": "want", "group": "redirect",
         "slot_path": ["redirect", "cuisine_candidates_expanded"]},
        {"key": "redirect.ingredient_want", "label": "食材想", "tone": "want",
         "group": "redirect", "slot_path": ["redirect", "ingredient_want"]},
        {"key": "redirect.ingredient_avoid", "label": "食材不想", "tone": "avoid",
         "group": "redirect", "slot_path": ["redirect", "ingredient_avoid"]},
        {"key": "redirect.brand_avoid", "label": "品牌拒绝", "tone": "avoid",
         "group": "redirect", "slot_path": ["redirect", "brand_avoid"]},
        {"key": "redirect.cooking_method_avoid", "label": "烹饪方式拒绝",
         "tone": "avoid", "group": "redirect",
         "slot_path": ["redirect", "cooking_method_avoid"]},
        {"key": "constrain.oil", "label": "油控", "tone": "neutral",
         "group": "constrain", "slot_path": ["constrain", "oil"], "scalar": True},
        {"key": "constrain.price_max", "label": "价格上限", "tone": "neutral",
         "group": "constrain", "slot_path": ["constrain", "price_max"], "scalar": True},
        {"key": "reference", "label": "引用上一轮", "tone": "neutral",
         "group": "meta", "slot_path": ["reference"], "scalar": True},
        {"key": "reject_previous", "label": "否决前轮", "tone": "neutral",
         "group": "meta", "slot_path": ["reject_previous"], "scalar": True},
        {"key": "raw_understanding", "label": "LLM 自述理解", "tone": "neutral",
         "group": "meta", "slot_path": ["raw_understanding"], "freeform": True},
        {"key": "raw_text", "label": "原始输入", "tone": "neutral",
         "group": "meta", "slot_path": ["raw_text"], "freeform": True},
    ]

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
from pathlib import Path
from typing import Any

import yaml
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from chisha import feedback_store
from chisha.api import format_v2_candidate, recommend_meal
from chisha.recall import (
    load_meal_log,
    load_profile,
    load_zone_data,
)
from chisha.refine import refine as refine_session

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "profile.yaml"

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


# ---------- /api/recommend ----------

@router.get("/recommend")
def api_recommend(
    meal_type: str = "lunch",
    mood: str = "neutral",
) -> dict:
    """GET /api/recommend?meal_type=&mood= → RecommendResponse (5 候选)."""
    if meal_type not in ("lunch", "dinner"):
        raise HTTPException(400, f"meal_type must be lunch|dinner, got {meal_type!r}")
    daily_mood = mood if mood and mood != "neutral" else None
    out = recommend_meal(
        meal_type=meal_type,
        daily_mood=daily_mood,
        log_to_file=True,
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
def api_refine(req: RefineReq) -> dict:
    """POST /api/refine → 同 session 二轮推荐 (round++)."""
    profile = load_profile(PROFILE_PATH)
    # session 决定 meal_type/zone, 客户端传的 meal_type/mood 仅作 fallback
    from chisha.session import load_session
    state = load_session(req.session_id, ROOT)
    if state is None:
        raise HTTPException(404, f"session {req.session_id!r} expired or missing")
    zone = state.zone
    rests, tagged = load_zone_data(zone, ROOT)
    meal_log = load_meal_log(ROOT)

    raw = refine_session(
        session_id=req.session_id,
        user_input=req.refine_text or "",
        profile=profile,
        rests=rests,
        tagged=tagged,
        meal_log=meal_log,
        root=ROOT,
    )

    # refine() 返回的 candidates 是 raw rerank dict, 需要走 format_v2_candidate
    candidates_fmt = [
        format_v2_candidate(i + 1, c)
        for i, c in enumerate(raw["candidates"])
    ]

    # 拼成与 recommend 一致的 RecommendResponse 形状 (前端 useChishaState 直接消费)
    from chisha.context import build_context
    today = dt.date.today()
    ctx = build_context(
        profile=profile,
        meal_log=meal_log,
        meal_type=state.meal_type,
        today=today,
        daily_mood=state.daily_mood,
        refine_input=req.refine_text or "",
        refine_intent=raw.get("refine_intent"),  # D-073
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
        # 调试用 (前端忽略):
        "refine_input": raw.get("refine_input"),
        "refine_intent": raw.get("refine_intent"),  # D-073: 替代 parsed_feedback/taste_hints
    }
    _remember_session_safe(out["session_id"], out)
    return out


# ---------- /api/accept ----------

class AcceptReq(BaseModel):
    session_id: str
    candidate_rank: int
    candidate: dict[str, Any]


@router.post("/accept")
def api_accept(req: AcceptReq) -> dict:
    """D-052: 记录 accept → 落 acceptedQueue → 返回 deeplink (best-effort)."""
    rest = req.candidate.get("restaurant") or {}
    rest_id = rest.get("id") or ""
    name = rest.get("name") or ""
    summary = req.candidate.get("summary") or ""
    meal_type = req.candidate.get("meal_type")
    # accept 时 candidate 里通常没 meal_type, 从 session 反查
    if not meal_type:
        from chisha.session import load_session
        state = load_session(req.session_id, ROOT, check_expiry=False)
        meal_type = state.meal_type if state else "lunch"

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
def api_skip(req: SkipReq) -> dict:
    """D-054: 这餐没吃 (食堂/带饭/外面/聚会/都没看上/不饿).

    reason ∈ {cafeteria, brought, outside, social, none_fit, not_hungry, null}.
    后续 V1.5+ 反馈学习信号: cafeteria/brought/outside ≠ "都没看上" (D-054).
    """
    if req.reason not in _VALID_SKIP_REASONS:
        raise HTTPException(400, f"invalid skip reason {req.reason!r}")
    try:
        feedback_store.record_skip(ROOT, req.session_id, req.reason)
    except Exception as e:
        raise HTTPException(
            500, f"record_skip failed: {type(e).__name__}: {e}"
        )
    return {"ok": True}


# ---------- /api/profile (GET / PUT / POST) ----------

@router.get("/profile")
def api_get_profile() -> dict:
    return yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))


def _write_profile_preserving_comments(new_profile: dict) -> None:
    """覆盖写 profile.yaml, 用 ruamel.yaml 保留头部注释 + 字段顺序.

    策略: load 当前 yaml (含注释 anchor) → 用 new_profile 内容覆盖字段值 →
    dump 回去。新字段写到末尾, 已删字段保持注释残留 (V1 schema 稳定不会出现)。
    """
    from ruamel.yaml import YAML
    yaml_rt = YAML()
    yaml_rt.preserve_quotes = True
    yaml_rt.indent(mapping=2, sequence=4, offset=2)

    if PROFILE_PATH.exists():
        with PROFILE_PATH.open("r", encoding="utf-8") as f:
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

    tmp = PROFILE_PATH.with_suffix(".yaml.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml_rt.dump(merged, f)
    tmp.replace(PROFILE_PATH)


@router.put("/profile")
@router.post("/profile")
def api_put_profile(profile: dict) -> dict:
    """PUT (或 POST 兼容) /api/profile body=完整 Profile, ruamel.yaml 写入保留注释."""
    if not isinstance(profile, dict) or "basics" not in profile:
        raise HTTPException(400, "invalid profile body: missing 'basics'")
    try:
        _write_profile_preserving_comments(profile)
    except Exception as e:
        raise HTTPException(500, f"write profile.yaml failed: {type(e).__name__}: {e}")
    return {"ok": True}


# ---------- /api/history ----------

@router.get("/history")
def api_history(days: int = 7) -> dict:
    """近 N 天的推荐 session, 关联 accepted_rank.

    数据源: logs/recommend_log.jsonl (每次 recommend 写一行) + feedback_store.accepted.
    返回 HistoryItem[]: { session_id, meal_type, generated_at, accepted_rank,
                         candidates_summary[3], mood }
    """
    if days < 1 or days > 90:
        raise HTTPException(400, "days must be in [1, 90]")
    log_path = ROOT / "logs" / "recommend_log.jsonl"
    if not log_path.exists():
        return {"items": []}

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    accepted_map: dict[str, dict] = {}
    try:
        accepted_map = feedback_store.load_store(ROOT).get("accepted", {}) or {}
    except Exception:
        pass

    items: list[dict] = []
    # 去重: 同 session_id 取最新 (refine 不重写 recommend_log; 多次 recommend 同 sid
    # 不应发生因为 _gen_session_id 含 4-char hex)
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
def api_feedback_inbox(include_snoozed: int = 1) -> dict:
    """D-058: 反馈中心 inbox. include_snoozed=0 时过滤掉 24h 软关闭项."""
    data = feedback_store.load_store(ROOT)
    items = feedback_store.inbox_items(
        data, include_snoozed=bool(include_snoozed)
    )
    return {"items": items}


@router.post("/feedback/snooze")
def api_feedback_snooze(req: SnoozeReq) -> dict:
    """D-060 软关闭: 24h 内 banner 不弹, inbox 仍在."""
    feedback_store.set_snooze(ROOT, req.session_id, hours=24)
    return {"ok": True}


@router.post("/feedback/stop")
def api_feedback_stop(req: StopReq) -> dict:
    """D-060 硬关闭: 永久, banner+inbox 都隐藏, history 仍可点."""
    feedback_store.set_stop(ROOT, req.session_id)
    return {"ok": True}


@router.get("/feedback/recent")
def api_feedback_recent(
    limit: int = Query(default=6, ge=1, le=100),
) -> dict:
    """D-066: 最近已反馈, 供 inbox 第三段 + history 行 gut chip 渲染.

    Codex review LOW: limit ∈ [1, 100], 负值 / 0 / 巨大值都 422.
    """
    data = feedback_store.load_store(ROOT)
    return {"items": feedback_store.recent_feedback_items(data, limit=limit)}


@router.post("/feedback")
def api_feedback_submit(req: FeedbackPayloadReq) -> dict:
    """D-066: 提交反馈, comments[] 保留 (D-067)."""
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
def api_feedback_session(session_id: str) -> dict:
    """反馈页头部 5 候选回放. session 已过期/不存在 → 404."""
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

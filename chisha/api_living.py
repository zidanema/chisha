"""Living API (D-085) — `/api/*` 端点, 决策入口, 写真实数据.

边界 (refactor_living_lab.md §5 + CONTRACTS.md):
- 输入输出 JSON 自闭包, 无 UI 状态, 无客户端隐含上下文
- agent (MCP / 飞书 / Claude Code) 可直接调
- Living 不调 Lab; trace 查询 / sandbox / what_if / debug_recommend 走 chisha.api_lab

Phase 0 已知缺陷 (P-9): 当 sandbox 全局启用时, Living API 仍走 data_root sandbox
副本 (因为 clock/data_root 是 process-global). 缓解: Living UI 已无 SandboxBar 入口,
只能从 Lab 启用 sandbox. 修正方案 (plumb 显式 sandbox 参数) 留 Phase 1 独立决策号.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from chisha import feedback_store
from chisha.api import _build_pipeline_trace_block, format_v2_candidate, recommend_meal
from chisha.recall import (
    load_meal_log,
    load_profile,
    load_zone_data,
)
from chisha.refine import refine as refine_session

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "profile.yaml"


def _profile_path() -> Path:
    """D-077 PR-1c: 动态求值. sandbox 启用且有副本 → sandbox/profile.yaml; 否则 prod."""
    from chisha import data_root
    return data_root.profile_path(ROOT)


router = APIRouter(prefix="/api", tags=["living"])


# ---------- helpers ----------

def _resolve_zone(profile: dict, meal_type: str) -> str:
    zones = profile.get("basics", {}).get("zones") or {}
    return zones.get(meal_type) or profile["basics"]["office_zone"]


def _remember_session_safe(session_id: str, payload: dict) -> None:
    """落 sessions 用于反馈页回放, 失败不阻断."""
    try:
        feedback_store.remember_session(ROOT, session_id, payload)
    except Exception as e:
        print(f"  [api_living] remember_session 失败 ({type(e).__name__}: {str(e)[:80]})")


# ---------- /api/recommend ----------

_VALID_MEAL_HINTS = {"lunch", "dinner"}


def _parse_at_time(at_time: str | None) -> dt.date | None:
    """D-085 PR-C: 接受 YYYY-MM-DD 或 ISO datetime, 都取 date 部分.

    返 None 表示 "现在" (recommend_meal 内部走 clock.today()).
    非法格式 → HTTPException(400).
    """
    if not at_time:
        return None
    raw = at_time.strip()
    # 先试 date
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        pass
    # 再试 datetime (含 tz 或不含)
    try:
        normalized = raw.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(normalized).date()
    except ValueError:
        raise HTTPException(
            400,
            f"at_time must be YYYY-MM-DD or ISO datetime, got {at_time!r}",
        )


@router.get("/recommend")
def api_recommend(
    meal_hint: str | None = None,
    meal_type: str | None = None,
    mood: str = "neutral",
    at_time: str | None = None,
) -> dict:
    """GET /api/recommend → RecommendResponse (5 候选).

    D-085 PR-C agent-ready 参数 (invariants 1 + 2):
    - meal_hint: lunch|dinner — 推荐当下哪一餐. 这是 agent 首选语义.
    - meal_type: backward-compat 别名 (apps/web 老调用方仍在用), 与 meal_hint
      等价. 同时传 → meal_hint 优先.
    - at_time: 可选, YYYY-MM-DD 或 ISO datetime. 不传 = 现在 (走 clock.today()).
      Agent 想"提前规划晚餐"或者重算特定日期时显式传.
    - mood: 可选 daily_mood (lunch_explore / want_soup / ...), neutral 等价空.

    JSON 自闭包 (invariant 1): 响应包含 session_id + 5 候选完整结构,
    无客户端隐含上下文; Agent 拿响应即可决策, 不需要再调其他端点.
    """
    chosen = meal_hint or meal_type or "lunch"
    if chosen not in _VALID_MEAL_HINTS:
        raise HTTPException(
            400,
            f"meal_hint must be {sorted(_VALID_MEAL_HINTS)}, got {chosen!r}",
        )
    daily_mood = mood if mood and mood != "neutral" else None
    today = _parse_at_time(at_time)
    out = recommend_meal(
        meal_type=chosen,
        daily_mood=daily_mood,
        log_to_file=True,
        today=today,
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
    profile = load_profile(_profile_path(), root=ROOT)
    from chisha.session import load_session
    state = load_session(req.session_id, ROOT)
    if state is None:
        raise HTTPException(404, f"session {req.session_id!r} expired or missing")
    zone = state.zone
    rests, tagged = load_zone_data(zone, ROOT)
    meal_log = load_meal_log(ROOT)

    # D-082: 收集 refine 全链路中间状态, round2 trace 用.
    from chisha import clock
    refine_started_at = clock.now_utc()
    trace_intermediates: dict = {}
    raw = refine_session(
        session_id=req.session_id,
        user_input=req.refine_text or "",
        profile=profile,
        rests=rests,
        tagged=tagged,
        meal_log=meal_log,
        root=ROOT,
        trace_intermediates=trace_intermediates,
    )

    candidates_fmt = [
        format_v2_candidate(i + 1, c)
        for i, c in enumerate(raw["candidates"])
    ]

    from chisha.context import build_context
    today = clock.today()
    ctx = build_context(
        profile=profile,
        meal_log=meal_log,
        meal_type=state.meal_type,
        today=today,
        daily_mood=state.daily_mood,
        refine_input=req.refine_text or "",
        refine_intent=raw.get("refine_intent"),
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
        "refine_input": raw.get("refine_input"),
        "refine_intent": raw.get("refine_intent"),
    }
    _remember_session_safe(out["session_id"], out)

    # D-079 PR-4 + D-082: refine merge 进同一 trace 文件
    try:
        from chisha import trace_store
        base_trace = trace_store.read_trace(req.session_id, root=ROOT)
        if base_trace is None:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "refine trace skip persist: base trace %s missing (recommend write "
                "may have best-effort failed); refine response unaffected",
                req.session_id,
            )
        else:
            refine_field = {
                "applied": True,
                "user_input": req.refine_text or "",
                "intent": raw.get("refine_intent"),
                "round": raw.get("round"),
                "n_combos_recalled": raw.get("stats", {}).get("n_combos_recalled"),
                "n_after_l2": raw.get("stats", {}).get("n_combos_after_score"),
                "n_returned": raw.get("stats", {}).get("n_returned"),
                "ts": raw.get("generated_at"),
                "candidate_ids": [
                    f"{(c.get('restaurant') or {}).get('name', '')}|"
                    f"{','.join((d.get('name') or '') for d in (c.get('dishes') or [])[:2])}"
                    for c in (raw.get("candidates") or [])[:5]
                ],
            }
            base_trace["refine"] = refine_field
            cfg = base_trace.get("__config") or {}
            cfg["refine_text"] = req.refine_text or ""
            base_trace["__config"] = cfg
            if trace_intermediates.get("reranked") is not None:
                try:
                    round2 = _build_pipeline_trace_block(
                        started_at=refine_started_at,
                        total_latency_ms=trace_intermediates["total_latency_ms"],
                        ctx_latency_ms=trace_intermediates["ctx_latency_ms"],
                        recall_latency_ms=trace_intermediates["recall_latency_ms"],
                        score_latency_ms=trace_intermediates["score_latency_ms"],
                        rerank_latency_ms=trace_intermediates["rerank_latency_ms"],
                        meal_type=state.meal_type,
                        zone=zone,
                        today=today,
                        profile=profile,
                        rests=rests,
                        tagged=tagged,
                        meal_log=meal_log,
                        combos=trace_intermediates["combos"],
                        ctx=trace_intermediates["ctx"],
                        daily_mood=state.daily_mood,
                        ranked_raw=trace_intermediates["ranked_raw"],
                        ranked=trace_intermediates["ranked"],
                        top_k=trace_intermediates["top_k"],
                        reranked=trace_intermediates["reranked"],
                        l3_collector=trace_intermediates["l3_collector"] or {},
                        root=ROOT,
                    )
                    base_trace["round2"] = round2
                except Exception as e:
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        "refine round2 trace build failed (non-fatal): %s: %s",
                        type(e).__name__, e,
                    )
            trace_store.write_trace(req.session_id, base_trace, root=ROOT)
    except trace_store.TraceCorrupt as e:
        import logging as _logging
        _logging.getLogger(__name__).error(
            "refine trace skip persist: base trace %s corrupt: %s",
            req.session_id, e,
        )
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "refine trace persist failed (non-fatal): %s: %s",
            type(e).__name__, e,
        )

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
def api_skip(req: SkipReq) -> dict:
    """D-054: 这餐没吃 (食堂/带饭/外面/聚会/都没看上/不饿)."""
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
    return yaml.safe_load(_profile_path().read_text(encoding="utf-8"))


def _write_profile_preserving_comments(new_profile: dict) -> None:
    """覆盖写 profile.yaml, 用 ruamel.yaml 保留头部注释 + 字段顺序."""
    from ruamel.yaml import YAML
    yaml_rt = YAML()
    yaml_rt.preserve_quotes = True
    yaml_rt.indent(mapping=2, sequence=4, offset=2)

    target = _profile_path()
    from chisha import sandbox as _sb
    if _sb.is_enabled(ROOT) and not target.exists() and PROFILE_PATH.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(PROFILE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    if target.exists():
        with target.open("r", encoding="utf-8") as f:
            current = yaml_rt.load(f)
        if current is None:
            current = {}
    else:
        current = {}

    def _deep_merge(dst, src):
        if not isinstance(src, dict):
            return src
        if not isinstance(dst, dict):
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
def api_put_profile(profile: dict) -> dict:
    """PUT (或 POST 兼容) /api/profile body=完整 Profile."""
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
    """近 N 天的推荐 session, 关联 accepted_rank."""
    if days < 1 or days > 90:
        raise HTTPException(400, "days must be in [1, 90]")
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
# ------------------------------------------------------------------


class SnoozeReq(BaseModel):
    session_id: str


class StopReq(BaseModel):
    session_id: str


GutVal = Literal[-1, 0, 1] | None        # D-064 难吃/普通/好吃
DimVal = Literal[0, 1, 2] | None         # D-065 4 维 calibration/behavior


class FeedbackPayloadReq(BaseModel):
    """V1.1 schema (D-063~D-065). 与 apps/web FeedbackPayload 镜像."""
    session_id: str
    accepted_rank: int | None = None
    rating: GutVal = None
    reason_match: DimVal = None
    fullness: DimVal = None
    oil_calibration: DimVal = None
    repurchase_intent: DimVal = None
    note: str = ""
    variant: Literal["progressive", "not-eaten"] = "progressive"
    quick: bool = False

    @model_validator(mode="after")
    def _check_variant_invariants(self) -> "FeedbackPayloadReq":
        if self.variant == "not-eaten":
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
    """D-058: 反馈中心 inbox."""
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
    """D-066: 最近已反馈, 供 inbox 第三段 + history 行 gut chip 渲染."""
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


# ---------- /api/long_term_prefs/refresh (D-076 PR-0.9) ----------

_LOCALHOST_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _is_localhost(request: Request) -> bool:
    """请求来源是否本机."""
    if request.client is None:
        return False
    return request.client.host in _LOCALHOST_HOSTS


def _admin_token_ok(request: Request) -> bool:
    """ENV CHISHA_ADMIN_TOKEN 设了的话, 校验 header X-Admin-Token 匹配."""
    expected = os.environ.get("CHISHA_ADMIN_TOKEN", "").strip()
    if not expected:
        return True
    got = request.headers.get("x-admin-token", "").strip()
    return got == expected


class RefreshPrefsReq(BaseModel):
    """触发 L1 抽取的请求体."""
    window_days: int | None = Field(default=None, ge=1, le=180)
    force_run_without_llm: bool = False


@router.post("/long_term_prefs/refresh")
def api_long_term_prefs_refresh(request: Request, req: RefreshPrefsReq) -> dict:
    """D-076 PR-0.9: 手动触发 L1 LLM 抽取, 写入 data/long_term_prefs.json."""
    if not _is_localhost(request):
        raise HTTPException(403, "refresh endpoint is localhost-only")
    if not _admin_token_ok(request):
        raise HTTPException(401, "invalid or missing X-Admin-Token")

    if req.force_run_without_llm:
        from scripts.bootstrap_l1_from_legacy import bootstrap
        prefs = bootstrap(root=ROOT, force=True)
        prefs.setdefault("path", "bootstrap_no_llm")
        return prefs

    from chisha.l1_extractor import extract_and_save

    try:
        store = feedback_store.load_store(ROOT)
    except feedback_store.StoreCorruptError as e:
        raise HTTPException(500, f"feedback store corrupt: {e}")

    try:
        profile = yaml.safe_load(_profile_path().read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise HTTPException(500, f"profile.yaml load failed: {type(e).__name__}: {e}")

    window = req.window_days or 14
    try:
        prefs = extract_and_save(
            store, profile,
            root=ROOT,
            window_days=window,
            profile_llm=profile.get("llm"),
        )
    except RuntimeError as e:
        raise HTTPException(503, f"L1 extract failed: {e}")
    prefs.setdefault("path", "llm_extract")
    return prefs

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
    profile = load_profile(_profile_path(), root=ROOT)
    # session 决定 meal_type/zone, 客户端传的 meal_type/mood 仅作 fallback
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

    # refine() 返回的 candidates 是 raw rerank dict, 需要走 format_v2_candidate
    candidates_fmt = [
        format_v2_candidate(i + 1, c)
        for i, c in enumerate(raw["candidates"])
    ]

    # 拼成与 recommend 一致的 RecommendResponse 形状 (前端 useChishaState 直接消费)
    from chisha.context import build_context
    today = clock.today()
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

    # D-079 PR-4: refine 同 session 二轮 → 把 refine 信息 merge 进同一 trace 文件
    # (Sidebar 一条 session 一行, 不分裂). DESIGN §3.5.
    #
    # base trace 缺失/损坏分支:
    #   - read_trace 返 None (首轮 trace 写盘失败 best-effort 降级了)
    #     → logger.warning + 不持久化 refine trace (没 base 可附着, 也不创 refine-only 孤儿)
    #   - read_trace 抛 TraceCorrupt → logger.error + 同上不持久化
    #   - 都不阻断 refine 自身响应
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
            # __config 也同步标 refine_text (Sidebar/Replay 展示)
            cfg = base_trace.get("__config") or {}
            cfg["refine_text"] = req.refine_text or ""
            base_trace["__config"] = cfg
            # D-082: round2 全量 pipeline trace 也塞进同一文件 (Sidebar 仍一行).
            # trace_intermediates 是 refine() 原地填的 dict, 拿不到说明 refine 没
            # 注入收集 (老路径 / 单测). 没拿到就跳过 round2, 保留 refine summary.
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
        # 任何 trace 写盘失败都不阻断 refine response (best-effort 原则).
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


@router.post("/long_term_prefs/refresh")
def api_long_term_prefs_refresh(request: Request, req: RefreshPrefsReq) -> dict:
    """D-076 PR-0.9: 手动触发 L1 LLM 抽取, 写入 data/long_term_prefs.json.

    鉴权:
    - localhost only (LAN/外网拒绝)
    - 可选 X-Admin-Token header (env CHISHA_ADMIN_TOKEN 设了才检)

    Flow:
    1. force_run_without_llm=True → 走 bootstrap_l1_from_legacy (旧 jsonl + 频次)
    2. 否则跑 l1_extractor.extract_and_save (V1.1 反馈 + LLM)

    返回: prefs dict (含 boost/penalty/evidence/extracted_at/based_on_meals).
    """
    if not _is_localhost(request):
        raise HTTPException(403, "refresh endpoint is localhost-only")
    if not _admin_token_ok(request):
        raise HTTPException(401, "invalid or missing X-Admin-Token")

    if req.force_run_without_llm:
        from scripts.bootstrap_l1_from_legacy import bootstrap
        prefs = bootstrap(root=ROOT, force=True)
        prefs.setdefault("path", "bootstrap_no_llm")
        return prefs

    # 走完整 LLM 抽取
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
        # LLM 全 retry 失败 → 不写盘, 保留旧 prefs
        raise HTTPException(503, f"L1 extract failed: {e}")
    prefs.setdefault("path", "llm_extract")
    return prefs


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
    """init(copy_real_data=True) 时把 prod 业务数据复制到 sandbox 子树."""
    import shutil
    from chisha import data_root

    sandbox_dir = root / "logs" / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    # profile.yaml
    if (root / "profile.yaml").exists():
        shutil.copy2(root / "profile.yaml", sandbox_dir / "profile.yaml")

    # meal_log / feedback_store / feedback_history / long_term_prefs / recommend_log
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
    """D-078 Codex S2 Q3-High: reset/disable 期间 L1 worker 仍在跑 → save_prefs
    若 sandbox 已 disable 会走回 prod data_root, 污染 prod long_term_prefs.json.
    在 reset/disable 入口拿 _L1_EXTRACTION_LOCK (worker 持锁直至 save 结束),
    抢不到则 409 让用户重试.
    """
    if _L1_EXTRACTION_LOCK.acquire(timeout=_L1_LOCK_WAIT_SECONDS):
        # 立即释放; 我们只是确认 worker 已结束.
        _L1_EXTRACTION_LOCK.release()
        return
    raise HTTPException(
        409, f"{action_label} blocked: L1 extraction worker busy >"
              f" {_L1_LOCK_WAIT_SECONDS:.0f}s, retry shortly"
    )


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

    D-078 Codex S2 Q3-High: 阻塞直到 L1 worker 释放, 否则 worker 的 save_prefs
    在 sandbox 已 disabled 状态下会走回 prod 路径污染 long_term_prefs.json.
    """
    _require_localhost(request)
    _block_until_l1_idle_or_409("reset")
    return _sandbox.reset(root=ROOT)


@router.post("/sandbox/disable")
def api_sandbox_disable(request: Request) -> dict:
    """退出 sandbox 但保留数据 (下次 init 可复用)."""
    _require_localhost(request)
    _block_until_l1_idle_or_409("disable")
    return _sandbox.disable(root=ROOT)


@router.get("/sandbox/state")
def api_sandbox_state(request: Request) -> dict:
    _require_localhost(request)
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
def api_sandbox_inspect(request: Request) -> dict:
    """沉淀状态 (志丹原则 #4): 当前 L1 prefs + 最近反馈 + 最近 meal_log.

    仅 sandbox 启用时返回数据, 关闭时返回 {enabled: false}.
    """
    _require_localhost(request)
    if not _sandbox.is_enabled(ROOT):
        return {"enabled": False}

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

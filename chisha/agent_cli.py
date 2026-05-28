"""D-074 Phase 0: AI-friendly one-shot CLI (chisha 零 LLM, 智能外置给宿主 agent).

宿主 agent (Phase 0 = Claude Code) 通过这个一次性 CLI 调 chisha. chisha **不发任何
LLM 请求**; 需要智能判断的两步 (context→intent 抽取 / 候选→排序) 由 chisha 发
llm_request_spec 信封, agent 的 LLM 执行后按 correlation_id 回传, chisha 校验落库.

verb 链 (设计 §3):
  start --meal <m> [--context "<原话>"] [--from <rid>] [--at-time <date>]
      无 context → 直接 recall+score, 返候选 + rerank spec (resolved)
      有 context → 只发 extract spec (pending), 等 resolve-intent
  resolve-intent --id <rid> --intent <json>   收抽取结果 → recall+score → rerank spec
  apply-rerank   --id <rid> --response <json>  收精排结果 → 校验+映射+fallback → final cards
  choose         --id <rid> --card <cid> --action <accept|skip>   记录选择 (幂等)
  init --agent <type>   生成 adapter skill (T8)
  doctor                检查环境 + 协议版本 + scope

scope (设计 §3 / codex #5): 默认 production. sandbox 全局启用时**拒绝运行** (避免
静默误路由到沙盒数据/虚拟时钟). --at-time 走 today 注入, 不碰 sandbox.

输出: 全部 machine-readable JSON 到 stdout, 跑完即退 (无 daemon / HTTP / async).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from chisha.agent_protocol import (
    PROTOCOL_VERSION,
    CorrelationId,
    parse_agent_response,
)


def _root() -> Path:
    """T-DIST-01 B.1: install_root 单一权威源 (dev=repo root, wheel=chisha/ 包目录).
    传给下游作 install_root; state 自动经 state_root.resolve(root) 路由到 ~/.chisha/."""
    from chisha.install_root import install_root
    return install_root()


def _emit(obj: dict) -> None:
    """machine-readable JSON 到 stdout."""
    print(json.dumps(obj, ensure_ascii=False))


def _emit_error(code: str, message: str, **extra: Any) -> int:
    _emit({"ok": False, "error": {"code": code, "message": message}, **extra})
    return 1


def _validate_id(value: str, label: str) -> None:
    """codex #f: 用户给的 id 在拼任何路径前先校验, 防 path traversal / 注入.

    Raises: RuntimeError (caller 转 JSON error).
    """
    if not value or "/" in value or ".." in value or "\\" in value or "\x00" in value:
        raise RuntimeError(f"非法 {label}: {value!r}")


def _prepared_blob(prep, *, n_explore: int, today: dt.date) -> dict:
    """codex #a: 持久化 apply-rerank 映射所需 (top_k 精确), 不靠重跑.

    D-102 Step1: 同时冻结 FallbackPlan blob (含 meal_log 只读快照 + 兜底参数), apply
    若走规则兜底就从此 blob 重建 → 不再像旧 cli 那样漏 meal_log (病根根治). 候选集 =
    top_k (单源), 不在 fallback_plan 里重复.
    """
    from chisha.rerank import build_fallback_plan
    plan = build_fallback_plan(
        prep.top_k, meal_log=prep.meal_log, n=5, n_explore=n_explore, today=today,
    )
    return {
        "top_k": prep.top_k,
        "ctx_dict": prep.ctx.to_llm_dict(),
        "feedback_avoided_names": prep.feedback_avoided_names,
        "latencies": {"ctx": prep.ctx_latency_ms, "recall": prep.recall_latency_ms,
                      "score": prep.score_latency_ms},
        "fallback_plan": plan.to_blob(),
    }


# ─────────────────────── scope / 输入 ───────────────────────

def _guard_scope(root: Path, scope: str) -> None:
    """codex #5: 默认 production 必须显式. sandbox 全局启用 → 拒绝 (防误路由).

    Raises: RuntimeError 让 caller 转成 JSON error.
    """
    if scope != "production":
        raise RuntimeError(
            f"Phase 0 CLI 仅支持 --scope production (got {scope!r}); "
            f"sandbox / time-travel 走 sandbox-lab"
        )
    from chisha import sandbox
    if sandbox.is_enabled(root):
        raise RuntimeError(
            "sandbox 全局启用中, CLI 拒绝在 production scope 运行 "
            "(避免误路由到沙盒数据 / 虚拟时钟). 先在 sandbox-lab disable, 再跑 CLI."
        )


def _parse_at_time(at_time: str | None, root: Path) -> dt.date:
    if at_time:
        try:
            return dt.date.fromisoformat(at_time)
        except ValueError as e:
            raise RuntimeError(f"--at-time 非法日期 (需 YYYY-MM-DD): {e}")
    from chisha import clock
    return clock.today(root)


def _resolve_zone(profile: dict, meal_type: str) -> str:
    from chisha.api import _resolve_zone as _rz
    return _rz(profile, meal_type)


def _load_inputs(meal_type: str, root: Path) -> tuple[dict, str, list, list, list]:
    from chisha import data_root
    from chisha.recall import load_meal_log, load_profile, load_zone_data
    profile = load_profile(data_root.profile_path(root), root=root)
    zone = _resolve_zone(profile, meal_type)
    rests, tagged = load_zone_data(zone, root)
    meal_log = load_meal_log(root)
    return profile, zone, rests, tagged, meal_log


# ─────────────────────── round / cards 持久化 ───────────────────────

def _next_round_id(sid: str, root: Path) -> str:
    """--from refine: 下一个 R{n}.

    以 **cards 文件** 为权威 round 计数源 (apply-rerank 每轮必可靠写入), 不依赖
    best-effort 的 trace 发布 — 否则 trace 写失败会让 refine 轮号回退到 R1 串台.
    cards 缺失 → 回退查 trace → 都没有 → R1.
    """
    p = _cards_path(sid, root)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            rounds = [k for k in data if k != "__latest"]
            if rounds:
                return f"R{len(rounds) + 1}"
        except Exception:
            pass
    from chisha import trace_store
    try:
        view = trace_store.read_trace_v3_view(sid, root)
        if view and view.get("rounds"):
            return f"R{len(view['rounds']) + 1}"
    except Exception:
        pass
    return "R1"


def _cards_path(sid: str, root: Path) -> Path:
    from chisha import data_root
    return data_root.agent_round_dir(root) / f"{sid}.cards.json"


def _write_cards(sid: str, round_id: str, cards: list[dict], root: Path) -> None:
    """apply-rerank 落 final cards (choose 按 card_id 查). round 维度累加."""
    p = _cards_path(sid, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            existing = {}
    existing[round_id] = cards
    existing["__latest"] = round_id
    p.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")


def _find_card(sid: str, card_id: str, root: Path) -> tuple[dict | None, str | None]:
    """choose: 从 cards 文件**最新一轮**按 card_id 找 (codex #c: 只查 __latest 轮,
    不跨轮 — 用户永远从当前呈现里选; card_id 无 round 成分跨轮可重名).

    返回 (card, round_id) 或 (None, latest_round).
    """
    p = _cards_path(sid, root)
    if not p.exists():
        return None, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    latest = data.get("__latest")
    if not latest:
        return None, None
    for card in data.get(latest) or []:
        if card.get("id") == card_id:
            return card, latest
    return None, latest


# ─────────────────────── 共享: prepare → rerank spec ───────────────────────

def _n_explore_for(round_id: str) -> int:
    """R1 = exploit+explore 两段 (D-015); refine 轮 = 聚焦 n_explore=0."""
    return 2 if round_id == "R1" else 0


def _intent_from_dict(intent_dict: dict | None):
    """resolved intent dict → RefineIntentV2 (供 prepare_candidates 重建)."""
    if not intent_dict:
        return None
    from chisha.refine_intent_v2 import RefineIntentV2, _empty_constrain, _empty_redirect
    redirect = {**_empty_redirect(), **(intent_dict.get("redirect") or {})}
    constrain = {**_empty_constrain(), **(intent_dict.get("constrain") or {})}
    return RefineIntentV2(
        redirect=redirect, constrain=constrain,
        reference=intent_dict.get("reference"),
        reject_previous=bool(intent_dict.get("reject_previous")),
        raw_understanding=intent_dict.get("raw_understanding", ""),
        raw_text=intent_dict.get("raw_text", ""),
        schema_version=intent_dict.get("schema_version", "2.1"),
    )


def _prepare_and_rerank_spec(
    *, sid: str, round_id: str, meal_type: str, today: dt.date,
    intent, refine_input: str | None, fb_signal, root: Path,
) -> tuple[Any, dict]:
    """prepare_candidates → build_rerank_spec. 返回 (prep, rerank_spec_dict)."""
    from chisha.agent_orchestration import prepare_candidates
    from chisha.rerank import build_rerank_spec
    profile, zone, rests, tagged, meal_log = _load_inputs(meal_type, root)
    n_explore = _n_explore_for(round_id)
    prep = prepare_candidates(
        profile=profile, rests=rests, tagged=tagged, meal_log=meal_log,
        meal_type=meal_type, today=today, root=root,
        refine_input=refine_input, intent=intent, fb_signal=fb_signal,
    )
    cid = CorrelationId(sid, round_id, "rerank")
    spec = build_rerank_spec(
        prep.top_k, profile, prep.ctx, n=5, n_explore=n_explore,
        correlation_id=cid, output_mode="tool_use", root=root,
        feedback_avoided_names=prep.feedback_avoided_names,
    )
    return prep, spec


# ═══════════════════════════════ verbs ═══════════════════════════════

def cmd_start(args) -> int:
    root = _root()
    try:
        _guard_scope(root, args.scope)
        if args.from_id:
            _validate_id(args.from_id, "--from id")
        today = _parse_at_time(args.at_time, root)
    except RuntimeError as e:
        return _emit_error("SCOPE_OR_TIME", str(e))

    from chisha.api import _gen_session_id

    if args.from_id:
        sid = args.from_id
        round_id = _next_round_id(sid, root)
    else:
        sid = _gen_session_id(args.meal)
        round_id = "R1"

    context = (args.context or "").strip()

    if context:
        # 有 context: 只发 extract spec (pending). fb_signal 在此冻结 (extract 前,
        # 与 in-process refine 顺序一致 — codex A1), 存进 pending.frozen 供 resolve 复用.
        from chisha import agent_round_store
        from chisha.agent_orchestration import _build_fb_signal
        from chisha.refine_intent_v2 import build_extract_spec

        try:
            _load_inputs(args.meal, root)  # 早失败: profile/zone 数据缺失立刻报
        except Exception as e:
            return _emit_error("LOAD_INPUTS", f"{type(e).__name__}: {e}")

        fb_signal = _build_fb_signal(today, root)
        cid = CorrelationId(sid, round_id, "extract")
        extract_spec = build_extract_spec(context, correlation_id=cid)
        frozen = {
            "meal_type": args.meal, "today": today.isoformat(),
            "refine_input": context, "fb_signal": fb_signal,
            "from_id": args.from_id,
        }
        try:
            agent_round_store.create_pending(
                sid, round_id=round_id, correlation_id=cid.encode(),
                extract_spec=extract_spec, meta=frozen, root=root,
            )
        except agent_round_store.RoundStateError as e:
            return _emit_error("ROUND_STATE", str(e))
        _emit({
            "ok": True, "recommendation_id": sid, "round": round_id,
            "status": "pending", "operation": "extract",
            "protocol_version": PROTOCOL_VERSION,
            "llm_request_spec": extract_spec,
            "next": "resolve-intent --id <rid> --intent <json>",
        })
        return 0

    # 无 context: 一步到 resolved (intent 空, recall+score + 发 rerank spec)
    from chisha import agent_round_store
    from chisha.agent_orchestration import _build_fb_signal
    try:
        fb_signal = _build_fb_signal(today, root)
        prep, spec = _prepare_and_rerank_spec(
            sid=sid, round_id=round_id, meal_type=args.meal, today=today,
            intent=None, refine_input=None, fb_signal=fb_signal, root=root,
        )
    except Exception as e:
        return _emit_error("PREPARE", f"{type(e).__name__}: {e}")
    cid = CorrelationId(sid, round_id, "rerank")
    frozen = {
        "meal_type": args.meal, "today": today.isoformat(),
        "refine_input": None, "fb_signal": fb_signal,
        "from_id": args.from_id, "n_explore": _n_explore_for(round_id),
    }
    try:
        agent_round_store.create_resolved(
            sid, round_id=round_id, correlation_id=cid.encode(),
            rerank_spec=spec, intent=None, frozen=frozen,
            prepared=_prepared_blob(prep, n_explore=_n_explore_for(round_id),
                                    today=today),
            root=root,
        )
    except agent_round_store.RoundStateError as e:
        return _emit_error("ROUND_STATE", str(e))
    _emit({
        "ok": True, "recommendation_id": sid, "round": round_id,
        "status": "resolved", "operation": "rerank",
        "protocol_version": PROTOCOL_VERSION,
        "candidate_count": len(prep.top_k),
        "feedback_avoided": prep.feedback_avoided_names,
        "llm_request_spec": spec,
        "next": "apply-rerank --id <rid> --response <json>",
    })
    return 0


def cmd_resolve_intent(args) -> int:
    root = _root()
    try:
        _guard_scope(root, args.scope)
    except RuntimeError as e:
        return _emit_error("SCOPE_OR_TIME", str(e))

    try:
        _validate_id(args.id, "--id")
    except RuntimeError as e:
        return _emit_error("BAD_ID", str(e))

    from chisha import agent_round_store
    from chisha.refine_intent_v2 import apply_intent_response

    cur = agent_round_store.read_round(args.id, root)
    if cur is None:
        return _emit_error("ROUND_STATE", f"sid {args.id} 无 in-flight round")
    round_id = cur.get("round_id", "R1")
    # codex #d: 幂等重试 — 经 extract 阶段的 resolved round (extract_spec 非 None) 再
    # resolve-intent → 重发已存 rerank spec, 不报错不重算. 无 context 的 resolved round
    # (extract_spec=None, 没经 extract) 不属此情形 → 落 ROUND_STATE.
    if cur.get("status") == "resolved" and cur.get("extract_spec") is not None:
        _emit({
            "ok": True, "recommendation_id": args.id, "round": round_id,
            "status": "resolved", "operation": "rerank", "idempotent_replay": True,
            "llm_request_spec": cur.get("rerank_spec"),
            "next": "apply-rerank --id <rid> --response <json>",
        })
        return 0
    if cur.get("status") != "pending":
        return _emit_error(
            "ROUND_STATE",
            f"sid {args.id} round 状态 {cur.get('status')!r}, 需 pending 才能 resolve-intent",
        )
    frozen = cur.get("frozen") or {}

    # 解析 agent 回传的 intent JSON
    try:
        intent_payload = json.loads(args.intent)
    except json.JSONDecodeError as e:
        return _emit_error("BAD_JSON", f"--intent 非合法 JSON: {e}")
    # F4: agent 回传必须是信封 {correlation_id, payload} (correlation 必填, 防 stale/串轮).
    expected = CorrelationId(args.id, round_id, "extract")
    try:
        resp = parse_agent_response(intent_payload, expected=expected)
        parsed_intent = resp.payload
    except ValueError as e:
        return _emit_error("CORRELATION", str(e))

    # Faithful Refine 守卫 (raw_text 用 frozen 原文, 忽略 agent 回传 raw_text)
    intent, disclosure = apply_intent_response(
        parsed_intent, raw_text=frozen.get("refine_input") or "",
    )

    today = dt.date.fromisoformat(frozen["today"])
    fb_signal = frozen.get("fb_signal")
    try:
        prep, spec = _prepare_and_rerank_spec(
            sid=args.id, round_id=round_id, meal_type=frozen["meal_type"],
            today=today, intent=intent, refine_input=frozen.get("refine_input"),
            fb_signal=fb_signal, root=root,
        )
    except Exception as e:
        return _emit_error("PREPARE", f"{type(e).__name__}: {e}")

    cid = CorrelationId(args.id, round_id, "rerank")
    try:
        agent_round_store.advance_to_resolved(
            args.id, correlation_id=cid.encode(), rerank_spec=spec,
            intent=intent.to_log_dict(),
            prepared=_prepared_blob(prep, n_explore=_n_explore_for(round_id),
                                    today=today),
            frozen_update={"intent": intent.to_log_dict(),
                           "n_explore": _n_explore_for(round_id)},
            root=root,
        )
    except agent_round_store.RoundStateError as e:
        return _emit_error("ROUND_STATE", str(e))

    _emit({
        "ok": True, "recommendation_id": args.id, "round": round_id,
        "status": "resolved", "operation": "rerank",
        "intent_disclosure": disclosure,
        "candidate_count": len(prep.top_k),
        "feedback_avoided": prep.feedback_avoided_names,
        "llm_request_spec": spec,
        "next": "apply-rerank --id <rid> --response <json>",
    })
    return 0


def cmd_apply_rerank(args) -> int:
    root = _root()
    try:
        _guard_scope(root, args.scope)
    except RuntimeError as e:
        return _emit_error("SCOPE_OR_TIME", str(e))

    try:
        _validate_id(args.id, "--id")
    except RuntimeError as e:
        return _emit_error("BAD_ID", str(e))

    from chisha import agent_round_store
    from chisha.api import _format_v2_candidate
    from chisha.rerank import FallbackPlan, apply_rerank_response

    try:
        cur = agent_round_store.require_resolved(args.id, root)
    except agent_round_store.RoundStateError as e:
        return _emit_error("ROUND_STATE", str(e))
    frozen = cur.get("frozen") or {}
    round_id = cur.get("round_id", "R1")
    n_explore = int(frozen.get("n_explore", _n_explore_for(round_id)))

    # codex #a: 用 resolve 时持久化的 top_k 映射 agent 回传 (不重跑 prepare_candidates
    # → combo_index 永远映射到 agent 当时看到的同一 combo, 不受 meal_log/profile 在
    # resolve→apply 间变化影响).
    prepared = cur.get("prepared") or {}
    persisted_top_k = prepared.get("top_k")
    if not persisted_top_k:
        return _emit_error("NO_PREPARED",
                           f"sid {args.id} resolved round 缺持久化 top_k, 无法 apply")

    try:
        resp_payload = json.loads(args.response)
    except json.JSONDecodeError as e:
        return _emit_error("BAD_JSON", f"--response 非合法 JSON: {e}")
    # F4: agent 回传必须是信封 {correlation_id, payload} (correlation 必填, 防 stale/串轮).
    expected = CorrelationId(args.id, round_id, "rerank")
    try:
        resp = parse_agent_response(resp_payload, expected=expected)
        payload = resp.payload
    except ValueError as e:
        return _emit_error("CORRELATION", str(e))

    today = dt.date.fromisoformat(frozen["today"])

    # 校验 + 映射 (确定性守卫留 chisha, 对持久化 top_k); 失败 → chisha_l2 fallback
    mapped, meta = apply_rerank_response(payload, persisted_top_k, n=5,
                                         n_explore=n_explore)
    used_fallback = mapped is None
    if used_fallback:
        # D-102 Step1: 从 resolve 时冻结的 FallbackPlan blob (meal_log 只读快照) +
        # round 单源 (持久化 top_k / frozen n_explore / frozen today) 重建并执行 —
        # 不再像旧 cli 漏 meal_log. n_explore/today 与成功路径同源 (frozen, 无双持久化
        # 漂移). blob 缺失/版本不符 → fail-loud (NO_FALLBACK_PLAN).
        try:
            plan = FallbackPlan.from_blob(
                prepared.get("fallback_plan"), top_combos=persisted_top_k,
                n=5, n_explore=n_explore, today=today,
            )
        except ValueError as e:
            return _emit_error("NO_FALLBACK_PLAN", str(e))
        mapped = plan.execute()
    # F1 (Faithful D-085): fallback 时 cards 是规则兜底排的, agent 的 narrative 描述的
    # 不是实际排出来的 5 条 → 置空, 绝不把未经校验的叙述套到规则 cards 上 (信任放大器
    # 不能编). adapter 靠 fallback=true + fallback_reason 如实告知"本轮按规则排".
    narrative = "" if used_fallback else (meta.get("narrative") or "")

    cards = [_format_v2_candidate(i + 1, c) for i, c in enumerate(mapped)]
    _write_cards(args.id, round_id, cards, root)

    # 发布 trace (best-effort, 失败不阻断 cards). 内部重跑 prepare_candidates 取 l1/l2
    # debug 上下文 (drift 只影响 debug 面板, 用户面 cards 走持久化 top_k 永远正确).
    _publish_trace_best_effort(
        sid=args.id, round_id=round_id, frozen=frozen, persisted=prepared,
        mapped=mapped, today=today, narrative=narrative,
        used_fallback=used_fallback, fallback_reason=meta.get("detail"), root=root,
    )

    agent_round_store.clear_round(args.id, root)
    _emit({
        "ok": True, "recommendation_id": args.id, "round": round_id,
        "status": "ready",
        "fallback": used_fallback,
        "fallback_reason": meta.get("detail") if used_fallback else None,
        "narrative": narrative,
        "cards": cards,
    })
    return 0


def _publish_trace_best_effort(*, sid, round_id, frozen, persisted, mapped, today,
                                narrative, used_fallback, fallback_reason, root) -> None:
    """发布 debug trace (best-effort, 失败吞掉不阻断 cards).

    内部重跑 prepare_candidates 取 l1/l2 + combos/ranked debug 上下文; 用户面 final
    走持久化 top_k + mapped (与返回的 cards 一致). 重跑漂移只影响 debug 面板, 不影响
    cards 正确性 (codex #a). 重跑/build 任一失败 → 跳过 trace.
    """
    try:
        from chisha import clock, trace_store
        from chisha.agent_orchestration import prepare_candidates
        from chisha.api import _build_trace

        profile, zone, rests, tagged, meal_log = _load_inputs(frozen["meal_type"], root)
        intent = _intent_from_dict(frozen.get("intent"))
        prep = prepare_candidates(
            profile=profile, rests=rests, tagged=tagged, meal_log=meal_log,
            meal_type=frozen["meal_type"], today=today, root=root,
            refine_input=frozen.get("refine_input"), intent=intent,
            fb_signal=frozen.get("fb_signal"),
        )
        l3_collector = {
            "llm_called": not used_fallback,
            "status": "fallback" if used_fallback else "ok",
            "narrative": narrative,
            "resolved_provider": "agent_external",
            "model": "agent-llm",
            "used_fallback": used_fallback,
            "fallback_reason": fallback_reason,
        }
        lat = persisted.get("latencies") or {}
        trace = _build_trace(
            session_id=sid, started_at=clock.now_utc(root), total_latency_ms=0,
            ctx_latency_ms=lat.get("ctx", 0), recall_latency_ms=lat.get("recall", 0),
            score_latency_ms=lat.get("score", 0), rerank_latency_ms=0,
            meal_type=frozen["meal_type"], zone=zone, today=today, profile=profile,
            rests=rests, tagged=tagged, meal_log=meal_log, combos=prep.combos,
            ctx=prep.ctx, daily_mood=None, ranked_raw=prep.ranked_raw,
            ranked=prep.ranked, top_k=persisted.get("top_k"), reranked=mapped,
            l3_collector=l3_collector, use_llm_rerank=True, root=root,
            feedback_signal=frozen.get("fb_signal"),
            feedback_avoided_names=persisted.get("feedback_avoided_names"),
        )
        trace["__source"] = "agent_cli"
        if round_id == "R1":
            trace_store.write_trace(sid, trace, root=root)
        else:
            round_payload = {
                "user_input": frozen.get("refine_input"),
                "intent_v2": frozen.get("intent"),
                "narrative": narrative,
                "kpi": {"combos": len(prep.combos), "top1": "", "latency_ms": 0},
                "l1": trace.get("l1"), "l2": trace.get("l2"),
                "l3": trace.get("l3"), "final": trace.get("final"),
                "__frozen": trace.get("__frozen"),
            }
            trace_store.append_round(sid, round_payload, root=root)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "agent_cli trace publish failed (non-fatal) for %s/%s: %s: %s",
            sid, round_id, type(e).__name__, e,
        )


def cmd_choose(args) -> int:
    root = _root()
    try:
        _guard_scope(root, args.scope)
    except RuntimeError as e:
        return _emit_error("SCOPE_OR_TIME", str(e))
    if args.action not in ("accept", "skip"):
        return _emit_error("BAD_ACTION", f"--action 需 accept|skip (got {args.action!r})")
    try:
        _validate_id(args.id, "--id")
        _validate_id(args.card, "--card")
    except RuntimeError as e:
        return _emit_error("BAD_ID", str(e))

    from chisha import agent_choose

    # codex #c: 只在最新一轮的 cards 里找 (用户从当前呈现选), round_id 进 choice_key.
    card, round_id = _find_card(args.id, args.card, root)
    if card is None and args.action == "accept":
        return _emit_error(
            "CARD_NOT_FOUND",
            f"card {args.card!r} 不在 {args.id} 最新一轮的 final cards 里 (accept 需卡片明细)",
        )
    rest = (card or {}).get("restaurant") or {}
    dishes = (card or {}).get("dishes") or []
    out = agent_choose.record_choice(
        root, sid=args.id, card_id=args.card, action=args.action,
        round_id=round_id or "R1",
        meal_type=(card or {}).get("meal_type") or _card_meal_type(args.id, root),
        restaurant_id=rest.get("id", ""), restaurant_name=rest.get("name", ""),
        summary=(card or {}).get("summary", ""), dishes=dishes,
        accepted_rank=(card or {}).get("rank"),
        combo_index=(card or {}).get("combo_index"),
        skip_reason=args.reason,
    )
    _emit({"ok": True, "recommendation_id": args.id, **out})
    return 0


def _card_meal_type(sid: str, root: Path) -> str:
    """从 sid 派生 meal_type (格式 {date}_{meal}_{hex})."""
    parts = sid.split("_")
    return parts[1] if len(parts) >= 2 and parts[1] in ("lunch", "dinner") else "lunch"


def cmd_doctor(args) -> int:
    root = _root()
    from chisha import sandbox, state_migrate, state_root
    from chisha.agent_protocol import CANDIDATE_SCHEMA_VERSION
    sb = sandbox.is_enabled(root)

    # D-102 Step2: install/state root 二分 + 迁移状态 + state_root 可写性
    import uuid as _uuid

    from chisha.state_migrate import _MIGRATE_MAP
    # install_root = 本次运行的 root (生产 = 包目录; 测试/worktree = 传入 root), 而非永远
    # 真包目录 — 否则测试 root=tmp 时 doctor 误报真 repo 的旧 state 待迁 (Codex review).
    install_root = root
    sroot = state_root.resolve(root)
    migrated = state_migrate.is_migrated(sroot)

    # 写探针: 唯一名 (不 clobber 同名文件) + best-effort 清理; 只在 sroot 已存在时探内部,
    # 否则探 parent 可写 (不为 doctor 副作用创建 state_root) (Codex review Q-E).
    writable, write_err = True, ""
    probe_dir = sroot if sroot.exists() else sroot.parent
    probe = probe_dir / f".doctor_write_probe.{_uuid.uuid4().hex}"
    try:
        probe.write_text("ok", encoding="utf-8")
    except Exception as e:
        writable, write_err = False, f"{type(e).__name__}: {e}"
    # 清理探针 best-effort (写成功但 unlink 失败不该误报不可写, 也不该留残件 — Codex Q-E)
    try:
        if probe.exists():
            probe.unlink()
    except Exception:
        pass

    # repo 内还有未迁 state? 检全部迁移输入 (profile/logs + data/ 反馈历史/偏好), 不只 profile/logs
    # (Codex review Q-D). install==state (无二分场景) 不算 pending.
    legacy_pending = (
        not migrated
        and install_root.resolve() != sroot.resolve()
        and any((install_root / rel_src.rstrip("/")).exists()
                for rel_src, _ in _MIGRATE_MAP)
    )

    # D-102 Step3: 数据产物 ↔ 引擎 manifest 兼容闸门 (install_root 上的 data/manifest.json)
    from chisha import manifest as _manifest
    manifest_status, manifest_note = "ok", ""
    manifest_path_str = str(_manifest.manifest_path(install_root))
    bundle_artifact_version: int | None = None
    bundle_data_schema_version: int | None = None
    try:
        mst = _manifest.check_compatibility(install_root)
        manifest_status = mst.status   # ok | missing
        bundle_artifact_version = mst.artifact_version
        bundle_data_schema_version = mst.data_schema_version
        if manifest_status == "missing":
            manifest_note = (
                "data/manifest.json 缺失 — 未版本化 bundle, 未达分发就绪 "
                "(跑 `uv run python -m scripts.build_manifest` 生成)."
            )
    except _manifest.IncompatibleManifestError as e:
        manifest_status, manifest_note = "incompatible", str(e)

    info = {
        # Q-B: 未迁的旧 repo state 视为"未就绪"; manifest 非 ok (缺/不兼容) 也视为未达
        # 分发就绪 (Step3 Codex review: doctor 是分发就绪检查, 缺 manifest=未版本化=未就绪;
        # runtime warn 放行与 doctor gate 不冲突).
        "ok": (not sb and writable and not legacy_pending
               and manifest_status == "ok"),
        "protocol_version": PROTOCOL_VERSION,
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
        "engine_version": _manifest.ENGINE_VERSION,
        "root": str(root),
        "install_root": str(install_root),
        "state_root": str(sroot),
        "state_root_writable": writable,
        "state_migrated": migrated,
        "legacy_state_pending_migration": legacy_pending,
        "data_manifest_status": manifest_status,   # ok | missing | incompatible
        "manifest_path": manifest_path_str,
        "bundle_artifact_version": bundle_artifact_version,    # int | None (missing/incompatible)
        "bundle_data_schema_version": bundle_data_schema_version,  # int | None
        "sandbox_enabled": sb,
        "scope_ready": not sb,
        "notes": [],
    }
    if sb:
        info["notes"].append(
            "sandbox 全局启用中 — CLI production scope 会被拒绝. 先 disable sandbox."
        )
    if not writable:
        info["notes"].append(f"state_root 不可写: {write_err}")
    if legacy_pending:
        info["notes"].append(
            "检测到 repo 内旧 state 未迁到 state_root (未就绪) — 跑 "
            "`uv run python -m scripts.migrate_state` 一次性迁移 (复制保留 repo 作回滚)."
        )
    if manifest_note:
        info["notes"].append(manifest_note)
    _emit(info)
    return 0 if info["ok"] else 1


def cmd_init(args) -> int:
    """T8: 生成 reference adapter skill. 占位 (T8 填充)."""
    from chisha.agent_skill_init import init_skill
    return init_skill(args.agent, _root(), force=args.force)


# ═══════════════════════════════ argparse ═══════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m chisha.agent_cli",
        description="chisha AI-friendly one-shot CLI (D-074 Phase 0)",
    )
    p.add_argument("--scope", default="production",
                   help="production (默认). sandbox/time-travel 走 sandbox-lab.")
    sub = p.add_subparsers(dest="verb", required=True)

    sp = sub.add_parser("start", help="起一轮推荐")
    sp.add_argument("--meal", required=True, choices=["lunch", "dinner"])
    sp.add_argument("--context", default=None, help="用户当天自然语言 (触发 intent 抽取)")
    sp.add_argument("--from", dest="from_id", default=None, help="refine: 续上一轮 rid")
    sp.add_argument("--at-time", default=None, help="time-travel: YYYY-MM-DD")
    sp.set_defaults(func=cmd_start)

    sp = sub.add_parser("resolve-intent", help="收 intent 抽取结果 → 发 rerank spec")
    sp.add_argument("--id", required=True)
    sp.add_argument("--intent", required=True, help="agent 抽取的 intent JSON")
    sp.set_defaults(func=cmd_resolve_intent)

    sp = sub.add_parser("apply-rerank", help="收精排结果 → final cards")
    sp.add_argument("--id", required=True)
    sp.add_argument("--response", required=True, help="agent 精排结果 JSON")
    sp.set_defaults(func=cmd_apply_rerank)

    sp = sub.add_parser("choose", help="记录用户选择 (幂等)")
    sp.add_argument("--id", required=True)
    sp.add_argument("--card", required=True, help="card_id (apply-rerank 返回的 cards[].id)")
    sp.add_argument("--action", required=True, choices=["accept", "skip"])
    sp.add_argument("--reason", default=None, help="skip 原因 (可选)")
    sp.set_defaults(func=cmd_choose)

    sp = sub.add_parser("init", help="生成 adapter skill")
    sp.add_argument("--agent", default="claude-code", help="adapter 类型")
    sp.add_argument("--force", action="store_true", help="覆盖已存在 skill")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("doctor", help="检查环境 + 协议版本 + scope")
    sp.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # --scope 是顶层 flag, 子命令 handler 通过 args.scope 读 (init/doctor 忽略).
    if not hasattr(args, "scope"):
        args.scope = "production"
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

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
    """仓库根 (agent_cli.py 在 chisha/ 下)."""
    return Path(__file__).resolve().parent.parent


def _emit(obj: dict) -> None:
    """machine-readable JSON 到 stdout."""
    print(json.dumps(obj, ensure_ascii=False))


def _emit_error(code: str, message: str, **extra: Any) -> int:
    _emit({"ok": False, "error": {"code": code, "message": message}, **extra})
    return 1


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


def _find_card(sid: str, card_id: str, root: Path) -> dict | None:
    """choose: 从 cards 文件按 card_id 找 (扫所有 round, 最新优先)."""
    p = _cards_path(sid, root)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    latest = data.get("__latest")
    round_order = ([latest] if latest else []) + [
        k for k in data if k not in (latest, "__latest")
    ]
    for rk in round_order:
        for card in data.get(rk) or []:
            if card.get("id") == card_id:
                return card
    return None


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
            rerank_spec=spec, intent=None, frozen=frozen, root=root,
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

    from chisha import agent_round_store
    from chisha.refine_intent_v2 import apply_intent_response

    cur = agent_round_store.read_round(args.id, root)
    if cur is None or cur.get("status") != "pending":
        return _emit_error(
            "ROUND_STATE",
            f"sid {args.id} 无 pending round (status={cur.get('status') if cur else None})",
        )
    frozen = cur.get("frozen") or {}
    round_id = cur.get("round_id", "R1")

    # 解析 agent 回传的 intent JSON
    try:
        intent_payload = json.loads(args.intent)
    except json.JSONDecodeError as e:
        return _emit_error("BAD_JSON", f"--intent 非合法 JSON: {e}")
    # agent 回传可能是裸 intent dict, 也可能是 {payload: {...}} 信封
    if isinstance(intent_payload, dict) and "payload" in intent_payload:
        try:
            expected = CorrelationId(args.id, round_id, "extract")
            resp = parse_agent_response(intent_payload, expected=expected)
            parsed_intent = resp.payload
        except ValueError as e:
            return _emit_error("CORRELATION", str(e))
    else:
        parsed_intent = intent_payload

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

    from chisha import agent_round_store
    from chisha.api import _format_v2_candidate
    from chisha.rerank import apply_rerank_response, fallback_rerank

    try:
        cur = agent_round_store.require_resolved(args.id, root)
    except agent_round_store.RoundStateError as e:
        return _emit_error("ROUND_STATE", str(e))
    frozen = cur.get("frozen") or {}
    round_id = cur.get("round_id", "R1")
    n_explore = int(frozen.get("n_explore", _n_explore_for(round_id)))

    try:
        resp_payload = json.loads(args.response)
    except json.JSONDecodeError as e:
        return _emit_error("BAD_JSON", f"--response 非合法 JSON: {e}")
    if isinstance(resp_payload, dict) and "payload" in resp_payload:
        try:
            expected = CorrelationId(args.id, round_id, "rerank")
            resp = parse_agent_response(resp_payload, expected=expected)
            payload = resp.payload
        except ValueError as e:
            return _emit_error("CORRELATION", str(e))
    else:
        payload = resp_payload

    # 重跑确定性编排 (冻结 today + fb_signal + intent → 确定性重建 top_k + trace 输入)
    today = dt.date.fromisoformat(frozen["today"])
    intent = _intent_from_dict(frozen.get("intent"))
    try:
        from chisha.agent_orchestration import prepare_candidates
        profile, zone, rests, tagged, meal_log = _load_inputs(frozen["meal_type"], root)
        prep = prepare_candidates(
            profile=profile, rests=rests, tagged=tagged, meal_log=meal_log,
            meal_type=frozen["meal_type"], today=today, root=root,
            refine_input=frozen.get("refine_input"), intent=intent,
            fb_signal=frozen.get("fb_signal"),
        )
    except Exception as e:
        return _emit_error("PREPARE", f"{type(e).__name__}: {e}")

    # 校验 + 映射 (确定性守卫留 chisha); 失败 → chisha_l2 fallback
    mapped, meta = apply_rerank_response(payload, prep.top_k, n=5, n_explore=n_explore)
    used_fallback = mapped is None
    if used_fallback:
        mapped = fallback_rerank(prep.top_k, n=5, n_explore=n_explore,
                                 meal_log=meal_log, today=today)
    narrative = meta.get("narrative") or ""

    cards = [_format_v2_candidate(i + 1, c) for i, c in enumerate(mapped)]
    _write_cards(args.id, round_id, cards, root)

    # 发布 trace (best-effort, 同 recommend_meal 失败不阻断). R1 走 write_trace.
    _publish_trace_best_effort(
        sid=args.id, round_id=round_id, prep=prep, mapped=mapped,
        profile=profile, rests=rests, tagged=tagged, meal_log=meal_log,
        meal_type=frozen["meal_type"], zone=zone, today=today,
        narrative=narrative, used_fallback=used_fallback,
        fallback_reason=meta.get("detail"), root=root,
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


def _publish_trace_best_effort(*, sid, round_id, prep, mapped, profile, rests,
                                tagged, meal_log, meal_type, zone, today,
                                narrative, used_fallback, fallback_reason, root) -> None:
    """复用 api._build_trace 写 R1 trace; refine 轮 best-effort append_round.
    失败仅吞掉 (trace 是派生证据, 不阻断 cards 返回)."""
    try:
        from chisha import clock, trace_store
        from chisha.api import _build_trace
        # 合成 l3_collector (agent 执行了 LLM, chisha 记录其产出)
        l3_collector = {
            "llm_called": not used_fallback,
            "status": "fallback" if used_fallback else "ok",
            "narrative": narrative,
            "resolved_provider": "agent_external",
            "model": "agent-llm",
            "used_fallback": used_fallback,
            "fallback_reason": fallback_reason,
        }
        started = clock.now_utc(root)
        trace = _build_trace(
            session_id=sid, started_at=started, total_latency_ms=0,
            ctx_latency_ms=prep.ctx_latency_ms, recall_latency_ms=prep.recall_latency_ms,
            score_latency_ms=prep.score_latency_ms, rerank_latency_ms=0,
            meal_type=meal_type, zone=zone, today=today, profile=profile,
            rests=rests, tagged=tagged, meal_log=meal_log, combos=prep.combos,
            ctx=prep.ctx, daily_mood=None, ranked_raw=prep.ranked_raw,
            ranked=prep.ranked, top_k=prep.top_k, reranked=mapped,
            l3_collector=l3_collector, use_llm_rerank=True, root=root,
            feedback_signal=prep.fb_signal,
            feedback_avoided_names=prep.feedback_avoided_names,
        )
        trace["__source"] = "agent_cli"
        if round_id == "R1":
            trace_store.write_trace(sid, trace, root=root)
        else:
            # refine 轮: 把 R1-shape trace 折成 round payload append
            round_payload = {
                "user_input": prep.ctx.to_llm_dict().get("refine_input"),
                "intent_v2": (prep.ctx.to_llm_dict().get("refine_intent")),
                "narrative": narrative,
                "kpi": {"combos": len(prep.combos), "top1": "",
                        "latency_ms": 0},
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

    from chisha import agent_choose

    card = _find_card(args.id, args.card, root)
    if card is None and args.action == "accept":
        return _emit_error(
            "CARD_NOT_FOUND",
            f"card {args.card!r} 不在 {args.id} 的 final cards 里 (accept 需卡片明细)",
        )
    rest = (card or {}).get("restaurant") or {}
    dishes = (card or {}).get("dishes") or []
    out = agent_choose.record_choice(
        root, sid=args.id, card_id=args.card, action=args.action,
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
    from chisha import sandbox
    from chisha.agent_protocol import CANDIDATE_SCHEMA_VERSION
    sb = sandbox.is_enabled(root)
    info = {
        "ok": not sb,
        "protocol_version": PROTOCOL_VERSION,
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
        "root": str(root),
        "sandbox_enabled": sb,
        "scope_ready": not sb,
        "notes": [],
    }
    if sb:
        info["notes"].append(
            "sandbox 全局启用中 — CLI production scope 会被拒绝. 先 disable sandbox."
        )
    _emit(info)
    return 0 if not sb else 1


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

"""D-074 Phase 0: AI-friendly one-shot CLI (chisha 零 LLM, 智能外置给宿主 agent).

宿主 agent (Phase 0 = Claude Code) 通过这个一次性 CLI 调 chisha. chisha **不发任何
LLM 请求**; 需要智能判断的两步 (context→intent 抽取 / 候选→排序) 由 chisha 发
llm_request_spec 信封, agent 的 LLM 执行后按 correlation_id 回传, chisha 校验落库.

verb 链 (P1 折叠后, 顶层 `chisha eat/continue/choose` 见 cli.py):
  start --meal <m> [--context "<原话>"] [--from <rid>] [--at-time <date>]
      无 context → 直接 recall+score, 返候选 + rerank spec (status=resolved, 带 do_llm)
      有 context → 只发 extract spec (status=pending, 带 do_llm), 等 continue
  continue --id <rid> --result <json> --step <step_token>   ★ P1 主路径
      喂上一步 do_llm 的 LLM 原始输出 (raw payload, 不包信封) + 回显 step_token;
      chisha 按 step_token.operation 路由: extract→抽意图发 rerank spec / rerank→出 cards.
      host 循环: 回包有 do_llm 就再 continue, 直到 status=ready (出 cards).
  resolve-intent / apply-rerank   [deprecated→continue] legacy 两步, 保留一版兼容
  choose   --id <rid> --card <cid> --action <accept|skip>   记录选择 (幂等)
  init --agent <type>   生成 adapter skill (T8)
  doctor                检查环境 + 协议版本 + scope

step_token (P1, codex Q1/Q2): = correlation_id 编码, 对 host 不透明 (回显即可). 去掉了
"手包 {correlation_id, payload} 信封 + 拼 correlation 字符串"的 footgun, 但 token 必填 —
它是去掉信封后唯一的 stale/串轮守门人, continue 不静默从 round state 派生.

scope (设计 §3 / codex #5): 默认 production. sandbox 全局启用时**拒绝运行** (避免
静默误路由到沙盒数据/虚拟时钟). --at-time 走 today 注入, 不碰 sandbox.

输出: 全部 machine-readable JSON 到 stdout, 跑完即退 (无 daemon / HTTP / async).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
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

_ALLOWED_SCOPES = ("production", "ephemeral")  # T-DIST-01 B.5c 加 ephemeral


def _guard_scope(root: Path, scope: str) -> None:
    """codex #5: 默认 production 必须显式. sandbox 全局启用 → 拒绝 (防误路由).

    T-DIST-01 B.5c: 新增 ephemeral scope, 行为同 production (sandbox 启用一样拒),
    区别仅在调用方 (cmd_onboard ephemeral dry start) 已先把 CHISHA_STATE_ROOT 钉到
    tmp 目录, 让所有 state 写落 tmp 跑完即删, 不污染真实 state_root 的 logs/agent_rounds.

    Raises: RuntimeError 让 caller 转成 JSON error.
    """
    if scope not in _ALLOWED_SCOPES:
        raise RuntimeError(
            f"Phase 0 CLI 仅支持 --scope {'/'.join(_ALLOWED_SCOPES)} (got {scope!r}); "
            f"sandbox / time-travel 走 sandbox-lab"
        )
    # D-104 Step2/3: sandbox 是 extras. full 安装 (sandbox 在) → 照常检测并拒绝;
    # slim agent core (sandbox 物理缺席) → ImportError → 当未启用 (slim 下 sandbox
    # 不可能启用, 语义正确)。lazy import 不进 top-level 依赖图。
    try:
        from chisha import sandbox
        sandbox_on = sandbox.is_enabled(root)
    except ImportError:
        sandbox_on = False
    if sandbox_on:
        raise RuntimeError(
            f"sandbox 全局启用中, CLI 拒绝在 {scope} scope 运行 "
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
    from chisha.core_api_helpers import _resolve_zone as _rz
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


def _ready_path(sid: str, root: Path) -> Path:
    from chisha import data_root
    return data_root.agent_round_dir(root) / f"{sid}.ready.json"


def _write_ready(sid: str, round_id: str, ready: dict, step_token: str,
                 root: Path) -> None:
    """P1 (codex Q3): apply 成功落 ready 响应快照 (含 step_token), 供 continue rerank
    重发幂等回放 (round clear 后宿主分不清"完成"vs"丢失"). round 维度累加."""
    p = _ready_path(sid, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            existing = {}
    existing[round_id] = {**ready, "step_token": step_token}
    p.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")


def _read_ready(sid: str, round_id: str, root: Path) -> dict | None:
    p = _ready_path(sid, root)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data.get(round_id)


def _latest_published_round(sid: str, root: Path) -> str | None:
    """cards 文件的 __latest = 最近发布的 ready round. rerank replay 防跨轮 stale
    (codex P1 C): 只回放最新轮, 旧轮 token 不静默回放历史 cards."""
    p = _cards_path(sid, root)
    if not p.exists():
        return None
    try:
        return (json.loads(p.read_text(encoding="utf-8")) or {}).get("__latest")
    except Exception:
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
        if args.from_id:
            _validate_id(args.from_id, "--from id")
        today = _parse_at_time(args.at_time, root)
    except RuntimeError as e:
        return _emit_error("SCOPE_OR_TIME", str(e))

    from chisha.core_api_helpers import _gen_session_id

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
            "do_llm": extract_spec,            # P1 canonical (host 判 do_llm 在否驱动循环)
            "step_token": cid.encode(),        # P1: continue 回显此 token (不透明)
            "llm_request_spec": extract_spec,  # deprecated alias, 删于下一版
            "next": "continue --id <rid> --result <json> --step <step_token>",
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
        "do_llm": spec,                    # P1 canonical
        "step_token": cid.encode(),        # P1: continue 回显此 token
        "llm_request_spec": spec,          # deprecated alias, 删于下一版
        "next": "continue --id <rid> --result <json> --step <step_token>",
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
            "do_llm": cur.get("rerank_spec"),            # P1 canonical
            "step_token": cur.get("correlation_id"),     # rerank cid (advance 后)
            "llm_request_spec": cur.get("rerank_spec"),  # deprecated alias
            "next": "continue --id <rid> --result <json> --step <step_token>",
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
        "do_llm": spec,                    # P1 canonical
        "step_token": cid.encode(),        # P1: continue 回显此 token
        "llm_request_spec": spec,          # deprecated alias, 删于下一版
        "next": "continue --id <rid> --result <json> --step <step_token>",
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
    from chisha.core_api_helpers import _format_v2_candidate
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

    ready = {
        "round": round_id, "status": "ready",
        "fallback": used_fallback,
        "fallback_reason": meta.get("detail") if used_fallback else None,
        "narrative": narrative,
        "cards": cards,
    }
    # P1 (codex Q3): 落 ready 快照供 continue rerank 重发幂等回放 (round clear 前).
    _write_ready(args.id, round_id, ready, expected.encode(), root)
    agent_round_store.clear_round(args.id, root)
    _emit({"ok": True, "recommendation_id": args.id, **ready})
    return 0


def _build_minimal_trace(*, session_id: str, started_at, meal_type: str,
                          zone: str, reranked: list) -> dict:
    """D-104 Step1b: slim core (extras 缺席) 的最小功能 trace.

    只含 reference refine + trace 索引必需的字段 (Codex 设计触点确认完备):
    __frozen.{meal_type,zone} + session_id/started_at + final (含 restaurant.id)。
    __version 由 trace_store.write_trace 自动注入; l1/l2/l3=None (rich 渲染是 extras)。
    """
    from chisha.core_api_helpers import _format_final_minimal
    return {
        "__source": "agent_cli",
        "__frozen": {"meal_type": meal_type, "zone": zone},
        "session_id": session_id,
        "started_at": started_at.isoformat(),
        "l1": None, "l2": None, "l3": None,
        "final": [_format_final_minimal(i + 1, c) for i, c in enumerate(reranked)],
        "refine": {"applied": False},
    }


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
        # D-104 Step1b: 富化 rich trace 走 extras (api→debug_recommend); slim core
        # 缺 extras → _build_trace 调用期 ImportError → 退到 core 最小功能 trace,
        # 保 reference refine (读 final[].restaurant.id) 功能零损失. 其余异常仍落外层吞。
        try:
            from chisha.api import _build_trace  # extras: rich L1/L2/L3
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
        except ImportError:
            trace = _build_minimal_trace(
                session_id=sid, started_at=clock.now_utc(root),
                meal_type=frozen["meal_type"], zone=zone, reranked=mapped,
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


def cmd_continue(args) -> int:
    """P1: 合并 resolve-intent + apply-rerank 的单 verb (host 一个循环驱动).

    宿主只传 raw LLM 输出 (--result) + 回显回包顶层 step_token (--step); chisha 内部按
    step_token.operation + round state 路由到 extract / rerank 处理, 自动包 correlation
    信封 (host 不再手包 {correlation_id, payload} / 不拼 correlation 字符串).

    step_token **必填** (codex Q1/Q2: 去掉信封后它是唯一的 stale/串轮守门人, 不静默派生).
    幂等回放 (codex Q3):
      - extract 重发 (round 已经此 extract 推到 resolved) → 复用 cmd_resolve_intent 回放.
      - rerank 重发 (round 已 apply+clear) → 查 ready 快照回放已落 cards.
    路由前强校验 token.round == 当前 round (防 stale 跨轮 token 命中错轮回放).
    """
    root = _root()
    try:
        _guard_scope(root, args.scope)
    except RuntimeError as e:
        return _emit_error("SCOPE_OR_TIME", str(e))
    try:
        _validate_id(args.id, "--id")
    except RuntimeError as e:
        return _emit_error("BAD_ID", str(e))

    if not args.step:
        return _emit_error(
            "STEP_REQUIRED",
            "continue 必须带 --step <step_token> (回显上一步回包顶层 step_token 字段; "
            "不静默派生, 防 stale/串轮回传)",
        )
    try:
        tok = CorrelationId.decode(args.step)
    except ValueError as e:
        return _emit_error("BAD_STEP", f"--step 非法 step_token: {e}")
    if tok.recommendation_id != args.id:
        return _emit_error(
            "STEP_MISMATCH",
            f"--step token sid {tok.recommendation_id!r} != --id {args.id!r}",
        )

    try:
        result_payload = json.loads(args.result)
    except json.JSONDecodeError as e:
        return _emit_error("BAD_JSON", f"--result 非合法 JSON: {e}")
    # host 传 raw payload; chisha 用 step_token 当 correlation 包回 legacy 信封, 委托
    # 久经考验的 cmd_resolve_intent / cmd_apply_rerank (它们内部再做 correlation 校验).
    envelope = json.dumps(
        {"correlation_id": args.step, "payload": result_payload}, ensure_ascii=False
    )

    from chisha import agent_round_store
    cur = agent_round_store.read_round(args.id, root)

    if tok.operation == "extract":
        if cur is None:
            return _emit_error("ROUND_STATE", f"sid {args.id} 无 in-flight round (extract step)")
        if tok.round != cur.get("round_id"):
            return _emit_error(
                "CORRELATION",
                f"step_token round {tok.round!r} != 当前 round {cur.get('round_id')!r} (stale)",
            )
        ns = argparse.Namespace(scope=args.scope, id=args.id, intent=envelope)
        return cmd_resolve_intent(ns)

    if tok.operation == "rerank":
        if cur is not None and cur.get("status") == "resolved":
            if tok.round != cur.get("round_id"):
                return _emit_error(
                    "CORRELATION",
                    f"step_token round {tok.round!r} != 当前 round {cur.get('round_id')!r} (stale)",
                )
            ns = argparse.Namespace(scope=args.scope, id=args.id, response=envelope)
            return cmd_apply_rerank(ns)
        if cur is None:
            # 可能已 apply + clear → 查 ready 快照幂等回放. 仅回放**最新已发布轮**
            # (codex P1 C): 防 stale 跨轮 token (如 R2 完成后误发 R1 token) 静默回放历史
            # cards — round 已推进, 旧轮 rerank 回放无意义且误导. step_token 也须精确匹配.
            latest = _latest_published_round(args.id, root)
            ready = _read_ready(args.id, tok.round, root)
            if (ready is not None and ready.get("step_token") == args.step
                    and tok.round == latest):
                out = {k: v for k, v in ready.items() if k != "step_token"}
                out["replayed"] = True
                _emit({"ok": True, "recommendation_id": args.id, **out})
                return 0
            return _emit_error(
                "ROUND_STATE",
                f"sid {args.id} 无 in-flight round 且无可回放 ready "
                f"(rerank step; token round={tok.round} latest={latest})",
            )
        return _emit_error(
            "ROUND_STATE",
            f"sid {args.id} round 状态 {cur.get('status')!r} 不可 rerank "
            "(需先 continue 完成 extract)",
        )

    return _emit_error("BAD_STEP", f"未知 step_token operation: {tok.operation!r}")


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
    from chisha import state_migrate, state_root
    from chisha.agent_protocol import CANDIDATE_SCHEMA_VERSION
    # D-104 Step2/3: sandbox 是 extras. slim agent core 缺席 → 当未启用 (doctor 仍可跑).
    try:
        from chisha import sandbox
        sb = sandbox.is_enabled(root)
    except ImportError:
        sb = False

    # D-102 Step2: install/state root 二分 + 迁移状态 + state_root 可写性
    import uuid as _uuid

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

    # repo 内还有未迁 state? T-DIST-01 B.7 跟修: 用 state_migrate.has_legacy_state 严判
    # (避免 wheel 模式把 ship 进去的 profile.yaml 模板误当 legacy → 永远 ok=false).
    # install==state (无二分场景) 不算 pending.
    legacy_pending = (
        not migrated
        and install_root.resolve() != sroot.resolve()
        and state_migrate.has_legacy_state(install_root)
    )

    # D-102 Step3: 数据产物 ↔ 引擎 manifest 兼容闸门 (install_root 上的 data/manifest.json)
    from chisha import manifest as _manifest
    install_manifest_status, manifest_note = "ok", ""
    manifest_path_str = str(_manifest.manifest_path(install_root))
    bundle_artifact_version: int | None = None
    bundle_data_schema_version: int | None = None
    try:
        mst = _manifest.check_compatibility(install_root)
        install_manifest_status = mst.status   # ok | missing
        bundle_artifact_version = mst.artifact_version
        bundle_data_schema_version = mst.data_schema_version
        if install_manifest_status == "missing":
            manifest_note = (
                "data/manifest.json 缺失 — 未版本化 bundle, 未达分发就绪 "
                "(跑 `uv run python -m scripts.build_manifest` 生成)."
            )
    except _manifest.IncompatibleManifestError as e:
        install_manifest_status, manifest_note = "incompatible", str(e)

    # T-DIST-01 B.5b: user-level resource manifest 单独报告 (per user zone/methodology).
    # 复用 capability flags 比对 (manifest._validate_manifest_payload), 不混入 install
    # 闸门 (D-102.3 CONTRACTS). user 区 incompatible 不影响 doctor.ok (用户区决定要不要清理).
    user_resource_status = _manifest.user_resource_manifest_check(sroot)

    # D-105 形态B: runtime 自检 — python 版本 / POSIX / vendored pyyaml provenance。
    # core 顶层 import yaml (recall/methodology); 缺失 = 运行时裸 traceback, doctor 提前响亮报。
    import sys as _sys
    py_ok = _sys.version_info >= (3, 11)
    python_version = f"{_sys.version_info.major}.{_sys.version_info.minor}.{_sys.version_info.micro}"
    is_posix = os.name == "posix"
    pyyaml_status, pyyaml_version, pyyaml_path = "missing", None, None
    try:
        import yaml as _yaml
        pyyaml_version = getattr(_yaml, "__version__", "unknown")
        pyyaml_path = str(getattr(_yaml, "__file__", "") or "")
        # vendored = yaml 解析自 install_root 内 (bundle/vendor); 否则 host (dev/形态A 合法)。
        try:
            in_install = Path(pyyaml_path).resolve().is_relative_to(install_root.resolve())
        except (ValueError, OSError):
            in_install = False
        pyyaml_status = "ok" if in_install else "host"
    except ImportError:
        pyyaml_status = "missing"

    info = {
        # Q-B: 未迁的旧 repo state 视为"未就绪"; install manifest 非 ok (缺/不兼容) 也视为
        # 未达分发就绪 (Step3 Codex review: doctor 是分发就绪检查, 缺 manifest=未版本化=未就绪;
        # runtime warn 放行与 doctor gate 不冲突). user_resource 单独报, 不计入 ok.
        "ok": (not sb and writable and not legacy_pending
               and install_manifest_status == "ok"
               and py_ok and pyyaml_status != "missing"),
        "protocol_version": PROTOCOL_VERSION,
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
        "engine_version": _manifest.ENGINE_VERSION,
        "root": str(root),
        "install_root": str(install_root),
        "state_root": str(sroot),
        "state_root_writable": writable,
        "state_migrated": migrated,
        "legacy_state_pending_migration": legacy_pending,
        # T-DIST-01 B.5b 改名: data_manifest_status → install_data_manifest_status (旧名删,
        # 没有 grandfather alias; user_resource_status 是新增字段).
        "install_data_manifest_status": install_manifest_status,   # ok | missing | incompatible
        "user_resource_status": user_resource_status,   # list of {kind, name, status, note}
        "manifest_path": manifest_path_str,
        "bundle_artifact_version": bundle_artifact_version,    # int | None (missing/incompatible)
        "bundle_data_schema_version": bundle_data_schema_version,  # int | None
        "sandbox_enabled": sb,
        "scope_ready": not sb,
        # D-105 形态B runtime 自检
        "python_version": python_version,        # 需 >= 3.11
        "python_ok": py_ok,
        "posix": is_posix,                        # POSIX-only (fcntl 文件锁)
        "pyyaml_status": pyyaml_status,           # ok(vendored) | host | missing
        "pyyaml_version": pyyaml_version,         # str | None
        "pyyaml_path": pyyaml_path,               # str | None
        "notes": [],
    }
    if not py_ok:
        info["notes"].append(
            f"python {python_version} < 3.11 — core 不支持. 装 3.11+ (homebrew/pyenv/uv)."
        )
    if pyyaml_status == "missing":
        info["notes"].append(
            "vendored pyyaml 不可达 (import yaml 失败) — bundle 缺 vendor/yaml/ 或 sys.path "
            "未注入. 重跑 build_skill_bundle --install 重建 bundle."
        )
    elif pyyaml_status == "host":
        info["notes"].append(
            f"pyyaml 来自宿主环境而非 bundle vendor (dev 合法; 形态B bundle 应 vendored): {pyyaml_path}"
        )
    if not is_posix:
        info["notes"].append(
            "非 POSIX 平台 — core 用 fcntl 文件锁, Windows 不支持 (除 WSL)."
        )
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

    sp = sub.add_parser("apply-rerank", help="[deprecated→continue] 收精排结果 → final cards")
    sp.add_argument("--id", required=True)
    sp.add_argument("--response", required=True, help="agent 精排结果 JSON")
    sp.set_defaults(func=cmd_apply_rerank)

    # P1: 合并 resolve-intent + apply-rerank — host 一个循环 (有 do_llm 就 continue 到 ready)
    sp = sub.add_parser("continue", help="推进一轮: 喂 LLM 输出, 按 step_token 路由")
    sp.add_argument("--id", required=True)
    sp.add_argument("--result", required=True, help="你的 LLM 原始输出 JSON (raw payload, 不包信封)")
    sp.add_argument("--step", required=True, help="回显上一步回包顶层 step_token (不透明)")
    sp.set_defaults(func=cmd_continue)

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
    # T-DIST-01 B.2: legacy entry compat — 推 `chisha agent <verb>`, stderr 一行 tip,
    # 绝不污染 stdout JSON (machine-readable 协议). Env CHISHA_SUPPRESS_LEGACY_TIP=1 可关.
    import os
    if not os.environ.get("CHISHA_SUPPRESS_LEGACY_TIP"):
        print(
            "[chisha] tip: `python -m chisha.agent_cli` 是 legacy 路径, "
            "推荐改用 `chisha agent <verb>` (T-DIST-01 B.2).",
            file=sys.stderr,
        )
    sys.exit(main())

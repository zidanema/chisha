"""D-089: trace 自包含化的共享 helper.

设计原则 (志丹 2026-05-19): trace 文件必须 self-contained — 所有 LLM 调用的
实际 system_prompt body / user_message / raw_response / usage 都落 trace,
不能事后从 prompts/*.md 当前版本重建. 因为系统会迭代, prompt 内容会变,
留 chars 而丢 body 等于 trace 无法 replay.

集中四个 helper 给 api.py / refine.py / web_api.py 共享, 消灭 L3 / LLM call
trace 三份序列化路径 (Codex review 关键点):

- normalize_usage_fields: 底层. provider-level usage → Anthropic-style 命名.
- serialize_llm_call_trace: 单次 LLM call 完整 trace shape. 所有 LLM 调用
  (rerank / refine_intent_v2 / 未来扩展) 都走这条.
- build_l3_trace_from_collector: 在 serialize_llm_call_trace 之上加 L3 业务字段.
- build_refine_round_payload: refine 路径 round payload 组装入口.

另含 L1/L2 trace 重建 helper, 让 refine.py 不必复制 api.py:_build_trace 的内联代码.
"""
from __future__ import annotations

from typing import Any


# ─────────────────────────── usage normalize ───────────────────────────

# provider 各自的 usage 命名 → Anthropic-style 命名映射.
# 见 chisha/llm_providers/openrouter.py:_parse_response usage dict.
# 前端 BackendL3Llm.usage 期望 Anthropic-style (input_tokens / output_tokens /
# cache_read_input_tokens / cache_creation_input_tokens), 见
# apps/debug-ui/src/api/backend-types.ts:126.
_USAGE_FIELD_MAP = {
    # provider key -> Anthropic-style key
    "prompt_tokens": "input_tokens",
    "completion_tokens": "output_tokens",
    "cached_tokens": "cache_read_input_tokens",
    "cache_write_tokens": "cache_creation_input_tokens",
    # 透传 Anthropic-style 原名 (如直连 anthropic provider 已返 Anthropic key)
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "cache_read_input_tokens": "cache_read_input_tokens",
    "cache_creation_input_tokens": "cache_creation_input_tokens",
}


def normalize_usage_fields(usage: dict | None) -> dict:
    """provider-level usage dict → Anthropic-style usage dict.

    缺字段填 0 而非 None — 前端 DagHeader 算 cache_hit% 时
    `cache_read / (input or 1)` 期望数值, 不期望 null 兼容代码.
    """
    out = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    if not usage:
        return out
    for src_key, dst_key in _USAGE_FIELD_MAP.items():
        if src_key in usage:
            v = usage[src_key]
            if isinstance(v, (int, float)):
                out[dst_key] = int(v)
    return out


# ─────────────────────────── LLM call serialize ───────────────────────────

def serialize_llm_call_trace(collector: dict) -> dict:
    """单次 LLM call 的完整 trace shape (BackendLlmCallTrace 对齐).

    所有 LLM 调用通用 — rerank 主链路 / refine_intent_v2 解析 / 未来扩展都走这条.
    收集者 (caller) 在调用 LLM 前后往 collector dict stash 字段, 此 helper
    pick + 转 shape, 不做任何业务推断.

    Args:
        collector: 调用方 stash 的原始字段 dict. 期望键:
            - system_prompt_full: 实际发给 LLM 的 system body (patch 过的最终版)
            - system_prompt_chars: len(system_prompt_full)
            - user_message_full: 实际发给 LLM 的 user body
            - user_message_chars: len(user_message_full)
            - raw_response: provider 返回的 raw text (tool_use 路径用
              arguments JSON 字符串, text 路径用 content text)
            - latency_ms: int | None
            - usage: provider 原始 usage dict (会被 normalize_usage_fields)
            - model: 实际生效的 model 名
            - resolved_provider: anthropic / openrouter / claude_code_cli
            - stop_reason: provider 返回的 finish_reason
            - fallback_reason: 调用失败时填
            - max_tokens / temperature: 调用参数
            - validator_errors: 业务校验失败时 list[str] | None
    """
    raw_response = collector.get("raw_response") or ""
    return {
        "system_prompt_full": collector.get("system_prompt_full") or "",
        "system_prompt_chars": collector.get("system_prompt_chars") or 0,
        "user_message_full": collector.get("user_message_full") or "",
        "user_message_chars": collector.get("user_message_chars") or 0,
        # user_message_preview: backend-types 期望存在 — 截前 300 字符
        "user_message_preview": (collector.get("user_message_full") or "")[:300],
        "raw_response": raw_response,
        "raw_response_chars": len(raw_response),
        "latency_ms": collector.get("latency_ms"),
        "usage": normalize_usage_fields(collector.get("usage")),
        "model": collector.get("model"),
        "resolved_provider": collector.get("resolved_provider"),
        "stop_reason": collector.get("stop_reason"),
        "fallback_reason": collector.get("fallback_reason"),
        "max_tokens": collector.get("max_tokens"),
        "temperature": collector.get("temperature"),
        "validator_errors": collector.get("validator_errors"),
    }


# ─────────────────────────── L3 rerank trace ───────────────────────────

def build_l3_trace_from_collector(
    l3_collector: dict,
    payload_to_llm: dict | None,
    n_returned: int,
) -> dict:
    """L3 rerank trace 完整 shape. 给 R1 主链路 + refine 路径共用.

    在 serialize_llm_call_trace 之上加 L3 特有业务字段 (used / status /
    parsed_candidates / tool_input / narrative / payload_to_llm / used_fallback).

    重要: status 字段必须从 collector["status"] 透传 — 不是 used/llm_called 的派生.
    "fallback" 时调用方应该已经填了 fallback_reason, used=True 表示 LLM 真的跑了
    (即使 fallback 了); used=False 表示根本没尝试 LLM (status 应为 "skipped" 或类似).
    """
    base = serialize_llm_call_trace(l3_collector)
    base.update({
        "used": bool(l3_collector.get("llm_called")),
        "status": l3_collector.get("status"),
        "config_error": bool(l3_collector.get("config_error")),
        "tool_input": l3_collector.get("tool_input"),
        "parsed_candidates": l3_collector.get("parsed_candidates"),
        "narrative": l3_collector.get("narrative", ""),
        "payload_to_llm": payload_to_llm,
        "n_returned": n_returned,
        "used_fallback": bool(l3_collector.get("used_fallback")),
        # retry 字段 (D-049 CLI retry 路径才有, 缺省 None)
        "retry_attempted": l3_collector.get("retry_attempted"),
        "retry_succeeded": l3_collector.get("retry_succeeded"),
        "retry_latency_ms": l3_collector.get("retry_latency_ms"),
        "retry_first_failure_code": l3_collector.get("retry_first_failure_code"),
    })
    return base


# ─────────────────────────── L1/L2 trace ───────────────────────────

def dim_stats_topk(topk_view: list[dict]) -> dict:
    """topk_view 各打分维度 min/max/mean/std 分布 (死分诊断).

    F-016 ⑥: 原在 debug_recommend / api / debug_what_if / build_l2_trace_for_round
    四处逐字重复, 收敛到此单一源。动态 all_dims (按 score_breakdown 出现的键),
    round 3 位, std=statistics.pstdev (n>1 否则 0) — 逐字保留原实现, baseline_l2
    0-diff 守门。
    """
    import statistics
    dim_stats: dict = {}
    if topk_view:
        all_dims: set = set()
        for c in topk_view:
            all_dims.update((c.get("score_breakdown") or {}).keys())
        for dim in all_dims:
            vals = [(c.get("score_breakdown") or {}).get(dim, 0.0) for c in topk_view]
            dim_stats[dim] = {
                "min": round(min(vals), 3),
                "max": round(max(vals), 3),
                "mean": round(sum(vals) / len(vals), 3),
                "std": round(statistics.pstdev(vals) if len(vals) > 1 else 0, 3),
            }
    return dim_stats


def build_l2_trace_for_round(
    ranked_raw: list[dict],
    ranked: list[dict],
    profile: dict,
) -> dict:
    """L2 trace 重建. 给 refine.py 用 — 跟 api.py:_build_trace 同口径.

    严格复用 debug_recommend._build_l2_cap_stats + _format_ranked_for_trace
    保证两边 trace 字段集合一致, baseline_l2_snapshot 不漂.
    """
    from chisha.debug_recommend import _build_l2_cap_stats, _format_ranked_for_trace
    from chisha.rerank import L3_INPUT_TOP_K
    from chisha.score import resolve_caps

    caps = resolve_caps(profile)
    dim_stats = dim_stats_topk(ranked[:L3_INPUT_TOP_K])
    cap_stats = _build_l2_cap_stats(ranked_raw, ranked)
    return {
        "summary": {
            "n_scored": len(ranked),
            "score_min": round(min((c["score"] for c in ranked), default=0), 3),
            "score_max": round(max((c["score"] for c in ranked), default=0), 3),
            "weights": profile.get("scoring_weights", {}),
            "caps": caps,
            "topk_window": L3_INPUT_TOP_K,
            "dim_stats_topk": dim_stats,
            **cap_stats,
        },
        "top": _format_ranked_for_trace(ranked, top=L3_INPUT_TOP_K),
    }


# ─────────────────────────── refine round payload ───────────────────────────

def build_refine_round_payload(refine_raw: dict, refine_text: str) -> dict:
    """从 refine.py 返回值 + 用户追问文本 → round 落盘 dict (trace_store.append_round 入参).

    Stage 4 任务: 把 chisha/web_api.py:215-260 的 _build_round_payload_from_refine
    替换成本 helper. refine.py Stage 2 改完后返回值会含 l1_trace / l2_trace /
    l3_trace / refine_intent_llm_trace, 这里 1:1 落盘.

    Args:
        refine_raw: chisha/refine.py refine() 返回值
        refine_text: 用户追问文本 (req.refine_text)
    """
    cands = refine_raw.get("candidates") or []
    top1_name = ""
    if cands:
        top1_name = (cands[0].get("restaurant") or {}).get("name") or ""
    stats = refine_raw.get("stats") or {}
    return {
        "started_at": refine_raw.get("generated_at"),
        "label": (refine_text or "追问")[:20],
        "user_input": refine_text or "",
        # D-094.1: refine_intent 直接是 V2 shape (V1 已退役, 砍 intent / refine_intent_v2 双存).
        # round trace 字段名保留 intent_v2 (debug-ui 已跟此 key).
        "intent_v2": refine_raw.get("refine_intent"),
        "narrative": refine_raw.get("narrative") or "",
        "reference_resolved": refine_raw.get("_reference_resolved"),
        "subtype_diversified": bool(refine_raw.get("_subtype_diversified")),
        "refine_hard_filter_events": refine_raw.get("_refine_hard_filter_events") or [],
        "refine_recall_fallback_events": refine_raw.get("_refine_recall_fallback_events") or [],
        "kpi": {
            "combos": stats.get("n_combos_recalled") or 0,
            "l2_top": stats.get("n_combos_after_score") or 0,
            "top1": top1_name,
            "latency_ms": refine_raw.get("total_latency_ms") or 0,
        },
        "diff": None,    # diff vs 上一轮: 前端按 round.final 集合算
        # D-089-S4: refine.py Stage 2 暴露完整切片后, 这里 1:1 落. None 兜底
        # 防 Stage 2 未完成时 round 字段缺失 (前端 makeEmptyL3 兜 no_data).
        "l1": refine_raw.get("l1_trace"),
        "l2": refine_raw.get("l2_trace"),
        "l3": refine_raw.get("l3_trace"),
        "refine_intent_llm": refine_raw.get("refine_intent_llm_trace"),
        "final": [
            {
                "rank": i + 1,
                "restaurant": c.get("restaurant") or {},
                "dishes": c.get("dishes") or [],
                "score": c.get("score"),
                "kind": c.get("kind") or ("exploit" if i < 3 else "explore"),
            }
            for i, c in enumerate(cands[:5])
        ],
    }

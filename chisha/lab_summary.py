"""D-085 PR-E: Lab "人话层" trace 摘要 (haiku).

入口: summarize(trace, llm_call=None) → dict, 不抛.
- 成功: {"text", "model", "generated_at", "fingerprint", "fallback": False}
- 失败: {"text": None, "fallback": True, "error_kind", "error_detail"}

由 api_lab.py /api/lab/sessions/{sid}/summary 调; 缓存写进 trace 顶层
__summary sibling (与 __feedback / __source 一致), fingerprint 任意输入字段
变化 → 重生.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 200
TEMPERATURE = 0.3
TOP_N_DIMS = 3  # 选 breakdown 里贡献最大的前 N 维入 prompt


# breakdown 字段 → 人话提示. 缺失的 dim 默认走 _humanize_dim_fallback.
_DIM_HINTS: dict[str, str] = {
    "cuisine_preference": "命中长期菜系偏好",
    "taste_match": "口味匹配 (L1 prefs 或 refine 意图)",
    "low_oil": "油脂等级低",
    "variety_bonus": "近 N 天没点过, 换换口味",
    "popularity": "销量验证过的口碑选项",
    "carb_quality": "主食选了全谷物/粗粮",
    "processed_meat": "避开加工肉",
    "sweet_sauce": "甜酱用得少",
    "wetness": "汤水/湿润度合适",
    "dish_role_match": "主菜/配菜/汤搭配合理",
    "eta": "送达时间短",
    "price": "价格合适",
    "context_boost": "当下心情 / 天气加成",
    "intent_cuisine": "本次 refine 指明的菜系",
    "intent_ingredient": "本次 refine 指明的食材",
    "intent_flavor": "本次 refine 指明的口味",
    "feedback_recency": "近期反馈 (rating) 强化",
    "next_meal_calibration": "上一餐反馈触发的下餐微调",
    "note_boost": "历史 note/comment 加成",
    "vegetable_floor_pass": "蔬菜达标",
    "protein_floor_pass": "蛋白质达标",
}


def _humanize_dim(dim: str) -> str:
    return _DIM_HINTS.get(dim, dim.replace("_", " "))


class SummarizeError(RuntimeError):
    """summarize 失败但不该 raise 出 endpoint, 内部 catch 返 fallback dict."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


# ────────────────────────── 抽 prompt 输入

def _build_summary_inputs(trace: dict) -> dict:
    """从 trace 抽 prompt 所需字段. 缺关键字段 → 抛 SummarizeError("empty_trace", ...)."""
    final = trace.get("final") or []
    if not final:
        raise SummarizeError("empty_trace", "trace.final 为空, 无 top1 可摘要")
    top1 = final[0] or {}
    rest = (top1.get("restaurant") or {}).get("name") or "(未知餐厅)"
    dishes = top1.get("dishes") or []
    dish_names = [
        d.get("name") or d.get("dish_name") or "" for d in dishes
    ]
    dish_names = [n for n in dish_names if n]

    # L2 top1 breakdown — 取贡献最大的前 N 维
    l2 = trace.get("l2") or {}
    l2_top = (l2.get("top") or []) if isinstance(l2, dict) else []
    breakdown: dict[str, float] = {}
    if l2_top:
        bd = (l2_top[0] or {}).get("breakdown") or {}
        if isinstance(bd, dict):
            breakdown = {k: float(v) for k, v in bd.items()
                         if isinstance(v, (int, float))}
    top_dims = sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)
    # 只留非零正贡献
    top_dims = [(k, v) for k, v in top_dims if v > 0][:TOP_N_DIMS]

    # L3 reason
    l3_reason = (top1.get("reason_one_line")
                 or top1.get("one_line_reason")
                 or "")

    # ctx / config
    frozen = trace.get("__frozen") or {}
    config = trace.get("__config") or {}
    meal_type = frozen.get("meal_type") or "lunch"
    today = frozen.get("today") or ""
    daily_mood = config.get("daily_mood") or None
    refine = trace.get("refine") or {}
    refine_text = refine.get("user_input") if refine.get("applied") else None

    # feedback evidence (简化: top1.feedback_evidence 或 l2_top[0].feedback_evidence)
    fb_evidence_lines = _feedback_evidence_lines(l2_top[0] if l2_top else {})

    return {
        "meal_type": meal_type,
        "today": today,
        "daily_mood": daily_mood,
        "refine_text": refine_text,
        "restaurant_name": rest,
        "dish_names": dish_names,
        "total_price": top1.get("total_price"),
        "estimated_total_oil": top1.get("estimated_total_oil"),
        "estimated_total_protein_g": top1.get("estimated_total_protein_g"),
        "top_dims": top_dims,  # list[(name, score)]
        "l3_reason": l3_reason,
        "feedback_evidence_lines": fb_evidence_lines,
    }


def _feedback_evidence_lines(l2_combo_top1: dict) -> list[str]:
    """把 l2.top[0].feedback_evidence (D-083 PR-1 sibling) 转人话短句."""
    ev = l2_combo_top1.get("feedback_evidence") if l2_combo_top1 else None
    if not isinstance(ev, dict):
        return []
    lines: list[str] = []
    for item in (ev.get("feedback_recency") or [])[:2]:
        rname = item.get("restaurant_name") or "这家"
        rating = item.get("rating")
        age = item.get("age_days")
        if rating is not None and age is not None:
            lines.append(f"{age} 天前给 {rname} 打过 {rating} 星")
    for item in (ev.get("next_meal_calibration") or [])[:1]:
        rules = item.get("rules_fired") or []
        if rules:
            rule_names = "/".join(r.get("rule", "") for r in rules[:2])
            lines.append(f"上一餐反馈触发 {rule_names}")
    for item in (ev.get("note_boost") or [])[:2]:
        kind = item.get("kind")
        token = item.get("token")
        polarity = item.get("polarity")
        if token and polarity:
            tag = "加分" if polarity == "boost" else "扣分"
            if kind == "restaurant":
                rname = item.get("restaurant_name") or "这家"
                lines.append(f"历史 note 提到「{token}」{tag} ({rname})")
            else:
                lines.append(f"历史高频 token「{token}」{tag}")
    return lines


# ────────────────────────── prompt

def _build_prompt(inputs: dict) -> str:
    """拼 user prompt. system 在 summarize 里独立给."""
    meal_cn = "午餐" if inputs["meal_type"] == "lunch" else "晚餐"
    dish_str = "、".join(inputs["dish_names"]) if inputs["dish_names"] else "(无菜品)"
    mood = inputs["daily_mood"] or "无特殊"
    refine_str = inputs["refine_text"] or "无"

    # 三维 hint
    if inputs["top_dims"]:
        dim_lines = []
        for i, (dim, score) in enumerate(inputs["top_dims"], 1):
            dim_lines.append(
                f"{i}. {dim} (+{score:.2f}) — {_humanize_dim(dim)}"
            )
        dims_block = "\n".join(dim_lines)
    else:
        dims_block = "(无显著正向维度)"

    # 营养
    nutri_bits = []
    if inputs["estimated_total_oil"] is not None:
        nutri_bits.append(f"平均油脂等级 {inputs['estimated_total_oil']:.1f}/5")
    if inputs["estimated_total_protein_g"] is not None:
        nutri_bits.append(f"蛋白质 ~{inputs['estimated_total_protein_g']:.0f}g")
    if inputs["total_price"] is not None:
        nutri_bits.append(f"总价 ~{inputs['total_price']:.0f} 元")
    nutri_str = " · ".join(nutri_bits) if nutri_bits else "(无营养数据)"

    fb_block = (
        "\n".join(f"- {line}" for line in inputs["feedback_evidence_lines"])
        if inputs["feedback_evidence_lines"] else "(无)"
    )

    return f"""【餐次】{meal_cn}
【日期】{inputs["today"]}
【天气/心情】{mood}
【refine 输入】{refine_str}

【Top1 候选】
- 餐厅: {inputs["restaurant_name"]}
- 菜品: {dish_str}
- 营养: {nutri_str}

【打分前 {len(inputs["top_dims"])} 维度】
{dims_block}

【LLM 精排理由】
{inputs["l3_reason"] or "(无)"}

【反馈影响】
{fb_block}

---

输出要求:
- 1 句话, 50-100 字
- 自然语言, 不用 L1/L2/L3 / score / rerank 等术语
- 突出 1-2 个最直接的"为什么"
- 不重复菜品名 (已经写在卡片上了)
- 不需要解释打分维度本身, 只说"因为..."
"""


_SYSTEM_PROMPT = (
    "你是一个营养顾问, 给用户解释'为什么今天的推荐是这家'。"
    "用一句自然语言, 50-100 字, 突出 1-2 个最直接的原因。"
)


# ────────────────────────── fingerprint

def compute_fingerprint(trace: dict) -> str:
    """trace 任意会影响摘要的输入变化 → fingerprint 变 → cache miss.

    不算整个 trace (太大), 只取摘要的输入字段.
    """
    try:
        inputs = _build_summary_inputs(trace)
    except SummarizeError:
        # 空 trace 也给个稳定 hash, 上层会跳过缓存
        return "empty"
    payload = {
        "meal_type": inputs["meal_type"],
        "today": inputs["today"],
        "daily_mood": inputs["daily_mood"],
        "refine_text": inputs["refine_text"],
        "restaurant_name": inputs["restaurant_name"],
        "dish_names": inputs["dish_names"],
        "top_dims": [(d, round(s, 4)) for d, s in inputs["top_dims"]],
        "l3_reason": inputs["l3_reason"],
        "feedback_evidence_lines": inputs["feedback_evidence_lines"],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


# ────────────────────────── 入口

def summarize(
    trace: dict,
    *,
    llm_call: Optional[Callable[..., dict]] = None,
    model: str = DEFAULT_MODEL,
) -> dict:
    """生成摘要. 不抛, 失败返 fallback dict.

    Args:
        trace: 已读盘的 trace dict (含 final / l2 / l3 等)
        llm_call: 可注入 fake (单测). None → 真用 chisha.llm_client.call_text
        model: 显式 model 覆盖 (默认 claude-haiku-4-5-20251001)

    Returns:
        成功: {"text", "model", "generated_at", "fingerprint", "fallback": False}
        失败: {"text": None, "fallback": True, "error_kind", "error_detail"}
    """
    try:
        inputs = _build_summary_inputs(trace)
    except SummarizeError as e:
        return _fallback(e.kind, e.detail)

    prompt = _build_prompt(inputs)
    fingerprint = compute_fingerprint(trace)

    if llm_call is None:
        from chisha import llm_client
        llm_call = llm_client.call_text

    try:
        resp = llm_call(
            prompt,
            system=_SYSTEM_PROMPT,
            model=model,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
    except RuntimeError as e:
        # _resolve_provider 抛 RuntimeError = 无 provider 可用
        return _fallback("no_provider", str(e))
    except Exception as e:
        return _fallback("llm_error", f"{type(e).__name__}: {e}")

    if not isinstance(resp, dict) or resp.get("type") != "text":
        return _fallback(
            "llm_error",
            f"unexpected llm response shape: type={resp.get('type') if isinstance(resp, dict) else type(resp).__name__}",
        )
    text = (resp.get("content") or "").strip()
    if not text:
        return _fallback("llm_error", "llm returned empty content")

    return {
        "text": text,
        "model": resp.get("model") or model,
        "generated_at": dt.datetime.now(dt.timezone.utc)
            .replace(microsecond=0).isoformat(),
        "fingerprint": fingerprint,
        "fallback": False,
    }


def _fallback(kind: str, detail: str) -> dict:
    logger.info("lab_summary fallback: %s — %s", kind, detail)
    return {
        "text": None,
        "fallback": True,
        "error_kind": kind,
        "error_detail": detail,
    }

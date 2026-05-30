"""T-P1b-01 顶部 always-on 状态条 payload builder.

纯派生函数, 输入 profile + 本次 recall 的 hard_filter_events,
输出前端 StatusBar 组件直接渲染的 dict.

设计原则 (Faithful Refine, design brief §1):
- 状态条是用户信任放大器, 信息必须可溯源到 trace, 不能编造
- L0-A/B 是 100% 不可破的保护, 始终展示
- L0-C 是 refine 可解除的健康约束, 展示时附"破戒模式"标识
- 空输入: 仅展示 active_methodology + 永久保护, override_events 为空

字段语义:
  status_bar.active_methodology.labels: 短标签数组, 前端横排展示
  status_bar.l0_protections.allergies: 始终展示, 不可破
  status_bar.l0_protections.dietary_law: "vegetarian"/"halal"/None
  status_bar.override_events: 本次 refine/recall 触发的事件,
    每条 {kind, term, message} — kind ∈ {l0_a_block, l0_b_block, l0_c_relaxed}
"""
from __future__ import annotations

from typing import Any

from chisha.l0_constraints import load_l0_constraints


def _derive_methodology_labels(profile: dict) -> list[str]:
    """从 profile.plate_rule + methodology 派生短标签 (展示给用户)."""
    pr = profile.get("plate_rule") or {}
    labels: list[str] = []
    name = profile.get("methodology") or "harvard_plate"
    name_display = {"harvard_plate": "哈佛餐盘"}.get(name, name)
    labels.append(name_display)

    min_veg = pr.get("min_vegetable_dishes")
    if isinstance(min_veg, int) and min_veg >= 1:
        labels.append(f"蔬菜≥{min_veg}")

    min_protein = pr.get("min_protein_g")
    if isinstance(min_protein, (int, float)) and min_protein > 0:
        labels.append(f"蛋白≥{int(min_protein)}g")

    hard_oil = pr.get("hard_max_oil_level")
    if isinstance(hard_oil, int) and 0 < hard_oil < 5:
        labels.append(f"油≤{hard_oil}")

    return labels


def _derive_l0_protections(profile: dict) -> dict[str, Any]:
    """L0-A 过敏 + L0-B 身份伦理 (永远展示, 不可破)."""
    c = load_l0_constraints(profile)
    return {
        "allergies": list(c.medical_allergies),
        "dietary_law": c.dietary_law,
    }


def _format_override_event(ev: dict) -> dict[str, Any] | None:
    """把 hard_filter_event 转成用户语言的 status_bar 事件.

    返回 None 表示该 event 不需要展示 (例如非 refine_override 的 methodology
    事件, 这是常规默认行为, 不算"事件").
    """
    cat = ev.get("category") or ""
    rule = ev.get("rule") or ""
    dropped = ev.get("dropped_count") or 0

    if cat == "L0_A_medical":
        term = rule.split("allergy:", 1)[-1] if rule.startswith("allergy:") else rule
        return {
            "kind": "l0_a_block",
            "term": term,
            "dropped_count": int(dropped),
            "message": f"检测到对「{term}」过敏，已忽略相关菜品",
        }

    if cat == "L0_B_identity":
        if rule.startswith("vegetarian_ban_"):
            return {
                "kind": "l0_b_block",
                "term": rule.replace("vegetarian_ban_", ""),
                "dropped_count": int(dropped),
                "message": f"检测到「素食」约束，已忽略「{rule.replace('vegetarian_ban_', '')}」类菜品",
            }
        if rule.startswith("halal_pork:"):
            kw = rule.split(":", 1)[-1]
            return {
                "kind": "l0_b_block",
                "term": kw,
                "dropped_count": int(dropped),
                "message": f"检测到「清真」约束，已忽略含「{kw}」菜品",
            }
        if rule == "halal_processed_meat":
            return {
                "kind": "l0_b_block",
                "term": "加工肉",
                "dropped_count": int(dropped),
                "message": "检测到「清真」约束，已忽略加工肉菜品",
            }
        return {
            "kind": "l0_b_block",
            "term": rule,
            "dropped_count": int(dropped),
            "message": f"L0-B 约束触发：{rule}",
        }

    if cat == "methodology" and ev.get("refine_override"):
        return {
            "kind": "l0_c_relaxed",
            "term": None,
            "dropped_count": 0,
            "message": "破戒模式 · 今晚一次性放开 · 不影响周报",
        }

    return None


def build_status_bar(
    profile: dict,
    hard_filter_events: list[dict] | None = None,
) -> dict[str, Any]:
    """主入口: 组装 status_bar payload."""
    events = hard_filter_events or []
    override_events: list[dict] = []
    for ev in events:
        formatted = _format_override_event(ev)
        if formatted is not None:
            override_events.append(formatted)

    return {
        "active_methodology": {
            "labels": _derive_methodology_labels(profile),
        },
        "l0_protections": _derive_l0_protections(profile),
        "override_events": override_events,
    }


def build_status_bar_safe(
    profile: dict,
    rests: list[dict],
    tagged: list[dict],
    meal_log: list[dict],
    today,
    meal_type: str | None = None,
    *,
    extra_events=(),
    feedback_signal: dict | None = None,
) -> tuple[dict, dict | None]:
    """recommend / refine 两路共用的 status_bar 派生 (best-effort, F-016 #19).

    跑一次 _build_l1_trace 拿 recall path 的 hard_filter_events, 合并 extra_events
    (refine 路的 L0-C 解除事件), 再 build_status_bar。失败降级到 build_status_bar(
    profile, extra_events) 不阻断 response。返回 (status_bar, l1_trace_cache | None);
    recommend 路用 cache 喂 _build_trace, refine 路忽略第二返回值。
    """
    try:
        from chisha.debug_recommend import _build_l1_trace
        l1_trace_cache, _ = _build_l1_trace(
            profile, rests, tagged, meal_log, today,
            meal_type=meal_type, feedback_signal=feedback_signal,
        )
        _hfe = list(l1_trace_cache.get("hard_filter_events") or [])
        _hfe.extend(extra_events)
        return build_status_bar(profile, _hfe), l1_trace_cache
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning(
            "status_bar build failed (non-fatal): %s: %s", type(_e).__name__, _e,
        )
        return build_status_bar(profile, list(extra_events)), None

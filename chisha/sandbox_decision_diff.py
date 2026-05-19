"""S-06b: D panel 因果链派生器.

纯函数, 无副作用. 由 S-06c eat/skip 端点在选定 picked_rec 后调用,
返回 Decision dict, 由 caller 落到 ``sessions/{sid}/decisions/{idx}.json``.

输入 history 契约: 列表 ``[-1]`` 元素是本顿 (picked_rec 对应那一顿),
``same_count`` 用 ``history[:-1]`` 内同 dish 名出现次数.

输入 prev_long_term_prefs / new_long_term_prefs: 上一顿落盘的 + 本顿后
重抽取的 L1 prefs (boost 字段 dict[token, float]). 用于 taste 维度 diff.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from chisha.sandbox import meal_idx_to_slot


def build_decision(
    *,
    sid: str,
    meal_idx: int,
    picked_rec: dict | None,
    prev_long_term_prefs: dict | None,
    new_long_term_prefs: dict | None,
    history: list[dict],
    root: Path | None = None,
) -> dict:
    """S-06b: 构造 Decision dict.

    Args:
        sid: sandbox session id (仅记录用, 不读盘)
        meal_idx: 本顿 idx (0-based; 派生 when 字段)
        picked_rec: 选定推荐 dict (含 name/dishes/rank/l3 等); None = skip
        prev_long_term_prefs: 上一顿落盘的 L1 prefs (含 boost dict); None / {} 视为空
        new_long_term_prefs: 本顿后重抽取的 L1 prefs; None / {} 视为空
        history: 完整 history. 约定 [-1] = 本顿. same_count = history[:-1] 内同名计数
        root: future-proof, 本实现不用

    Returns:
        Decision dict:
        {
          "when": "D3 午" | "D3 晚",
          "pick": "名称 · 菜1 + 菜2" 或 "(跳过)",
          "rank": int | "—",
          "l3": int | "—",
          "diff": [
            {"kind": "add", "field": "recent_dishes", "value": "+ [name]"},
            {"kind": "add", "field": "fatigue.name", "from": "—"|"1", "to": "1"|"2"},
            {"kind": "up"|"dn", "field": "taste.<token>", "from": "0.32", "to": "0.35", "delta": "+0.03"},
          ],
          "implications": [
            {"field": "taste.<token>", "text": "下顿 L2 给同类 +0.03 倾向"},
            {"field": "fatigue.name", "text": "下顿同菜折 0.95×"},
          ]
        }
    """
    del root  # future-proof, unused

    meal_type, day = meal_idx_to_slot(meal_idx)
    when_slot = "午" if meal_type == "lunch" else "晚"
    when = f"D{day} {when_slot}"

    if picked_rec is None:
        return {
            "when": when,
            "pick": "(跳过)",
            "rank": "—",
            "l3": "—",
            "diff": [],
            "implications": [
                {"field": "—", "text": "跳过未触发学习,下一顿系统状态不变"},
            ],
        }

    name = picked_rec["name"]
    dishes = picked_rec.get("dishes") or []

    diff: list[dict] = []

    # 1. recent_dishes add
    diff.append({
        "kind": "add",
        "field": "recent_dishes",
        "value": f"+ [{name}]",
    })

    # 2. fatigue counter (history[-1] 是本顿, 计 [:-1] 内同名)
    same_count = sum(1 for h in history[:-1] if h.get("dish") == name)
    diff.append({
        "kind": "add",
        "field": f"fatigue.{name}",
        "from": str(same_count) if same_count > 0 else "—",
        "to": str(same_count + 1),
    })

    # 3. taste diff: prev_boost vs new_boost
    prev_boost = (prev_long_term_prefs or {}).get("boost", {}) or {}
    new_boost = (new_long_term_prefs or {}).get("boost", {}) or {}
    for token, v in new_boost.items():
        old_v = float(prev_boost.get(token, 0.0))
        v = float(v)
        if abs(v - old_v) > 1e-3:
            kind = "up" if v > old_v else "dn"
            delta_sign = "+" if v > old_v else ""
            diff.append({
                "kind": kind,
                "field": f"taste.<{token}>",
                "from": f"{old_v:.2f}",
                "to": f"{v:.2f}",
                "delta": f"{delta_sign}{v - old_v:.2f}",
            })

    # 4. implications
    implications: list[dict] = []
    for d in diff:
        field = d["field"]
        kind = d["kind"]
        if kind in ("up", "dn") and field.startswith("taste."):
            implications.append({
                "field": field,
                "text": f"下顿 L2 给同类 {d['delta']} 倾向",
            })
        elif kind == "add" and field.startswith("fatigue."):
            implications.append({
                "field": field,
                "text": "下顿同菜折 0.95×",
            })

    # 5. pick 文案
    if dishes:
        pick_text = f"{name} · {' + '.join(dishes)}"
    else:
        pick_text = name

    return {
        "when": when,
        "pick": pick_text,
        "rank": picked_rec.get("rank", "—"),
        "l3": picked_rec.get("l3", "—"),
        "diff": diff,
        "implications": implications,
    }

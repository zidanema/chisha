"""把 recommend_meal 输出渲染成飞书 interactive card 2.0 JSON.

接入说明: OpenClaw 拿到 dict 后用 lark-cli 或 lark IM SDK 发送.
"""
from __future__ import annotations

from typing import Any


def _meal_label(meal_type: str) -> str:
    return {"lunch": "中午", "dinner": "晚上"}.get(meal_type, meal_type)


def _candidate_block(c: dict) -> dict:
    """单个候选 → 飞书卡片 column section."""
    rest = c["restaurant"]
    dish_names = "、".join(d["canonical_name"] for d in c["dishes"])
    line1 = f"**#{c['rank']} {rest['name']}**"
    line2 = f"{dish_names}"
    line3 = (
        f"¥{c['total_price']:.0f} · {rest.get('eta_min', '?')}min · "
        f"油{c['estimated_total_oil']} · 蛋白{c['estimated_total_protein_g']}g"
    )
    line4 = f"💬 {c['reason_one_line']}"
    return {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": "\n".join([line1, line2, line3, line4]),
        },
        "extra": {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "选这个"},
            "type": "primary",
            "value": {
                "action": "select",
                "session_id": "{{session_id}}",
                "rank": c["rank"],
                "restaurant_name": rest["name"],
                "summary": c["summary"],
            },
        },
    }


def render_card(out: dict) -> dict:
    """recommend_meal 输出 → 飞书 card 2.0 JSON."""
    meal_label = _meal_label(out["meal_type"])
    cands = out["candidates"]
    if not cands:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text",
                          "content": f"今天{meal_label}吃点啥"},
                "template": "orange",
            },
            "elements": [{
                "tag": "div",
                "text": {"tag": "lark_md",
                         "content": "⚠️ 今天没召回到合适的组合，去 APP 自己点吧"},
            }],
        }

    elements: list[dict] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (f"今天{meal_label}给你 **{len(cands)} 选 1**："),
            },
        },
        {"tag": "hr"},
    ]
    for i, c in enumerate(cands):
        elements.append(_candidate_block(c))
        if i < len(cands) - 1:
            elements.append({"tag": "hr"})

    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "elements": [{
            "tag": "plain_text",
            "content": (f"召回 {out['stats']['n_combos_recalled']} 选 "
                        f"{len(cands)} | session {out['session_id']}"),
        }],
    })

    return {
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": {
            "title": {"tag": "plain_text",
                      "content": f"🍱 今天{meal_label}吃点啥"},
            "template": "blue",
        },
        "elements": elements,
    }


if __name__ == "__main__":
    import json
    from chisha.api import recommend_meal
    out = recommend_meal("lunch", log_to_file=False)
    card = render_card(out)
    print(json.dumps(card, ensure_ascii=False, indent=2))

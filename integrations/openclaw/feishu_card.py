"""把 recommend_meal 输出渲染成飞书 interactive card 2.0 JSON.

接入说明: OpenClaw 拿到 dict 后用 lark-cli 或 lark IM SDK 发送.

V2 增强 (D-033):
- 候选块加 "拒绝并选原因" overflow chip
- 卡片底部加 refine 区 (自由文本 + 重推按钮)
- 顶部可选 post-meal 追问 (上顿感觉如何, 被动触发, 见 D-034)
"""
from __future__ import annotations

from typing import Any

from chisha.feedback import CHIP_VOCAB


def _meal_label(meal_type: str) -> str:
    return {"lunch": "中午", "dinner": "晚上"}.get(meal_type, meal_type)


# ─────────────────────────── reject chip 子集 (V2)
# 卡片上的 "拒绝并选原因" overflow 用. 必须 ⊂ CHIP_VOCAB (运行时校验).
_REJECT_CHIPS_DEFAULT = [
    "太油", "太辣", "太贵", "太甜",
    "想喝汤", "想清淡", "想吃肉",
    "不想吃这菜系", "主食太多", "加工肉太多",
    "送慢", "踩雷",
]


def _validated_reject_chips() -> list[str]:
    return [c for c in _REJECT_CHIPS_DEFAULT if c in CHIP_VOCAB]


# ─────────────────────────── 候选块 (V2 加 reject overflow)
def _candidate_block(c: dict, session_id_placeholder: str = "{{session_id}}") -> dict:
    """单个候选 → 飞书卡片 column section. V2 加 reject overflow."""
    rest = c["restaurant"]
    dish_names = "、".join(d["canonical_name"] for d in c["dishes"])
    explore_tag = " 🌱探索" if c.get("is_explore") else ""
    line1 = f"**#{c['rank']} {rest['name']}**{explore_tag}"
    line2 = f"{dish_names}"
    line3 = (
        f"¥{c['total_price']:.0f} · {rest.get('eta_min', '?')}min · "
        f"油{c['estimated_total_oil']} · 蛋白{c['estimated_total_protein_g']}g"
    )
    line4 = f"💬 {c['reason_one_line']}"

    select_button = {
        "tag": "button",
        "text": {"tag": "plain_text", "content": "选这个"},
        "type": "primary",
        "value": {
            "action": "select",
            "session_id": session_id_placeholder,
            "rank": c["rank"],
            "restaurant_name": rest["name"],
            "summary": c["summary"],
        },
    }

    reject_overflow = {
        "tag": "overflow",
        "options": [
            {
                "text": {"tag": "plain_text", "content": chip},
                "value": f"reject:{chip}",
            }
            for chip in _validated_reject_chips()
        ],
        "value": {
            "action": "reject",
            "session_id": session_id_placeholder,
            "rank": c["rank"],
        },
    }

    return {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": "\n".join([line1, line2, line3, line4]),
        },
        "fields": [],
        "extra": {
            "tag": "column_set",
            "flex_mode": "none",
            "columns": [
                {
                    "tag": "column",
                    "width": "auto",
                    "elements": [{
                        "tag": "action",
                        "actions": [select_button],
                    }],
                },
                {
                    "tag": "column",
                    "width": "auto",
                    "elements": [{
                        "tag": "action",
                        "actions": [reject_overflow],
                    }],
                },
            ],
        },
    }


# ─────────────────────────── 顶部 post-meal 追问 (V2 D-034)
def _post_meal_prompt_block(last_meal: dict, session_id_placeholder: str = "{{session_id}}") -> dict:
    """下次饭点 trigger 时的"上顿感觉？"被动追问. last_meal 来自 ContextSnapshot.last_meal."""
    summary = (
        f"{last_meal.get('date', '?')} {last_meal.get('meal_type', '')} 的"
        f" {last_meal.get('cuisine', '') or ''}"
    ).strip()
    return {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"💭 上顿（{summary}）感觉怎么样？1 句话即可（可跳过）",
        },
        "extra": {
            "tag": "input",
            "placeholder": {"tag": "plain_text",
                            "content": "例: 太油 / 想再来 / 还行"},
            "value": {
                "action": "post_meal_feedback",
                "session_id": session_id_placeholder,
                "last_meal": last_meal,
            },
            "label": {"tag": "plain_text", "content": ""},
            "label_position": "top",
        },
    }


# ─────────────────────────── refine 区 (V2 D-033)
def _refine_block(session_id_placeholder: str = "{{session_id}}") -> dict:
    """卡片底部 refine 输入区: 自然语言 + 换 5 个 按钮."""
    return {
        "tag": "form",
        "name": "refine_form",
        "elements": [
            {
                "tag": "input",
                "name": "refine_text",
                "placeholder": {
                    "tag": "plain_text",
                    "content": "想换个推荐? 说一句… (例: 今天想喝汤别给我面)",
                },
                "label": {"tag": "plain_text", "content": "🔁 重新推荐"},
                "label_position": "top",
            },
            {
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "换 5 个"},
                    "type": "default",
                    "behaviors": [{
                        "type": "callback",
                        "value": {
                            "action": "refine",
                            "session_id": session_id_placeholder,
                        },
                    }],
                }],
            },
        ],
    }


# ─────────────────────────── 主入口
def render_card(out: dict, last_meal: dict | None = None) -> dict:
    """recommend_meal 输出 → 飞书 card 2.0 JSON.

    Args:
        out: recommend_meal 返回的 dict (§5.7 schema).
        last_meal: 可选, ContextSnapshot.last_meal 的 dict 形式. 提供则在卡片顶部显示 post-meal 追问.
    """
    meal_label = _meal_label(out["meal_type"])
    cands = out["candidates"]
    session_id = out.get("session_id", "{{session_id}}")

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

    elements: list[dict] = []

    # 顶部: 上一顿追问 (可选, 被动触发)
    if last_meal:
        elements.append(_post_meal_prompt_block(last_meal, session_id))
        elements.append({"tag": "hr"})

    # 主标题
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": (f"今天{meal_label}给你 **{len(cands)} 选 1**："),
        },
    })
    elements.append({"tag": "hr"})

    for i, c in enumerate(cands):
        elements.append(_candidate_block(c, session_id))
        if i < len(cands) - 1:
            elements.append({"tag": "hr"})

    # refine 区
    elements.append({"tag": "hr"})
    elements.append(_refine_block(session_id))

    # footer
    elements.append({"tag": "hr"})
    n_recalled = out.get("stats", {}).get("n_combos_recalled", "?")
    elements.append({
        "tag": "note",
        "elements": [{
            "tag": "plain_text",
            "content": (f"召回 {n_recalled} 选 {len(cands)} | session {session_id}"),
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

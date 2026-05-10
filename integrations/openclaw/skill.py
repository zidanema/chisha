"""OpenClaw skill 入口: 触发推荐 + 推送飞书卡片.

OpenClaw 调用方式 (示例):
    from integrations.openclaw.skill import push_meal_recommendation
    push_meal_recommendation(meal_type="lunch", chat_id="oc_xxx")

环境变量:
    OPENCLAW_PUSH_MODE = "lark-cli" | "stdout" | "noop"  (默认 stdout)
    LARK_CHAT_ID = 接收方 chat_id (默认 OPENCLAW_PUSH_MODE=lark-cli 必填)

依赖:
    OPENCLAW_PUSH_MODE=lark-cli 时需要 lark-cli 在 PATH 上
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

from chisha.api import recommend_meal
from integrations.openclaw.feishu_card import render_card


def push_via_lark_cli(card: dict, chat_id: str) -> int:
    """用 lark-cli im send 推卡片. 返回退出码."""
    payload = json.dumps(card, ensure_ascii=False)
    cmd = [
        "lark-cli", "im", "send",
        "--chat-id", chat_id,
        "--msg-type", "interactive",
        "--content", payload,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"lark-cli failed: {p.stderr}", file=sys.stderr)
    else:
        print(f"sent to {chat_id}")
    return p.returncode


def push_meal_recommendation(
    meal_type: str = "lunch",
    chat_id: str | None = None,
) -> dict:
    """跑推荐 → 渲染卡片 → 推送. 返回 {out, card, status}."""
    out = recommend_meal(meal_type, log_to_file=True)
    card = render_card(out)

    mode = os.environ.get("OPENCLAW_PUSH_MODE", "stdout")
    chat_id = chat_id or os.environ.get("LARK_CHAT_ID")

    status = "ok"
    if mode == "lark-cli":
        if not chat_id:
            status = "error: LARK_CHAT_ID required for lark-cli mode"
        else:
            rc = push_via_lark_cli(card, chat_id)
            status = "ok" if rc == 0 else f"lark-cli rc={rc}"
    elif mode == "stdout":
        print(json.dumps(card, ensure_ascii=False, indent=2))
    elif mode == "noop":
        pass
    else:
        status = f"unknown mode: {mode}"

    return {"out": out, "card": card, "status": status}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("meal", nargs="?", default="lunch",
                    choices=["lunch", "dinner"])
    ap.add_argument("--chat-id", default=None)
    args = ap.parse_args()
    r = push_meal_recommendation(args.meal, args.chat_id)
    print(f"\n[status] {r['status']}", file=sys.stderr)

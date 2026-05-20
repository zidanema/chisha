"""D-072 Codex M-2 要求: 抓取 L3 [PROFILE] block 在注入 methodology 行前后的
A/B 对照, 给未来 L3 行为差异 sanity check 用.

不打 LLM, 仅 capture build_user_message 的 prompt 文本. 落:
  tmp/baseline_traces/l3_prompt_without_methodology.txt  (从 git 老版本拿)
  tmp/baseline_traces/l3_prompt_with_methodology.txt     (当前注入版本)

老版本通过 `git show HEAD:chisha/rerank.py` 反推过于复杂, 这里直接
mock _profile_block 模拟 "if spec absent" 路径生成 without 版本.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from chisha.context import build_context
from chisha.recall import (
    load_meal_log,
    load_profile,
    load_zone_data,
    recall,
)
from chisha.rerank import L3_INPUT_TOP_K, build_user_message
from chisha.score import apply_caps, rank_combos


def capture(meal_type: str, with_methodology: bool, root: Path) -> str:
    profile = load_profile(root / "profile.yaml")
    if not with_methodology:
        # 模拟 "spec 未注入" 路径
        profile = dict(profile)
        profile.pop("_methodology_spec", None)
    zone = profile["basics"]["zones"].get(meal_type) or profile["basics"]["office_zone"]
    rests, tagged = load_zone_data(zone, root)
    meal_log = load_meal_log(root)
    today = dt.date(2026, 5, 15)
    combos = recall(profile, rests, tagged, meal_log, today, meal_type=meal_type)
    ctx = build_context(profile=profile, meal_log=meal_log,
                        meal_type=meal_type, today=today, daily_mood=None)
    ranked = rank_combos(combos, profile, meal_log, today,
                         context=ctx, meal_type=meal_type, root=root)
    capped = apply_caps(ranked, profile)
    top = capped[:L3_INPUT_TOP_K]
    return build_user_message(top, profile, ctx, n=5, n_explore=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="tmp/baseline_traces")
    args = ap.parse_args()
    root = Path(".").resolve()
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    for label, with_meth in (("without_methodology", False),
                              ("with_methodology", True)):
        msg = capture("lunch", with_meth, root)
        out = out_dir / f"l3_prompt_lunch_{label}.txt"
        out.write_text(msg, encoding="utf-8")
        print(f"[ok] {out.name} — {len(msg)} chars")


if __name__ == "__main__":
    main()

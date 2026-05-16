"""D-073 PR-0.6: 一次性兜底脚本 — 旧 feedback_history.jsonl → 首版 prefs.json.

Goal: PR-0.7 切 score 读取路径前生成首版 long_term_prefs.json,
保留 D-043 旧 chip 频次累积的弱信号, 避免 score 切换瞬间丢 hints.

数据流:
    data/feedback_history.jsonl (D-043 旧 chip 频次)
        ↓
    chisha.long_term_prefs.load_runtime_hints (deprecated stub, 但仍能读)
        ↓ 转 prefs.json schema
    data/long_term_prefs.json (bootstrap_from_legacy=True)

设计:
- 不调 LLM (deterministic, 可在 CI 跑, 无 API 成本)
- evidence 标 source="legacy_frequency_aggregate", LLM 抽取后会被覆盖
- 用户后续可调 POST /api/long_term_prefs/refresh (PR-0.9) 走 LLM 抽取
- 已经存在 prefs.json 时默认不覆盖, 加 --force 强制

用法:
    uv run python -m scripts.bootstrap_l1_from_legacy
    uv run python -m scripts.bootstrap_l1_from_legacy --force
    uv run python -m scripts.bootstrap_l1_from_legacy --root /tmp/sandbox
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def bootstrap(
    root: Path | None = None,
    force: bool = False,
    today: dt.date | None = None,
) -> dict:
    """读旧 feedback_history.jsonl → 生成 prefs.json.

    Returns:
        生成的 prefs dict. 已存在 prefs 且 force=False 时直接返回旧 prefs.
    """
    root = root or _project_root()
    today = today or dt.date.today()

    # lazy import 避免脚本顶层引入 chisha 包失败时炸
    from chisha.l1_prefs import _prefs_path, load_prefs, save_prefs
    from chisha.long_term_prefs import (
        DEFAULT_HALFLIFE_DAYS,
        DEFAULT_MAX_HISTORY_DAYS,
        DEFAULT_MIN_COUNT,
        load_feedback_history,
        load_runtime_hints,
    )

    target = _prefs_path(root)

    if target.exists() and not force:
        existing = load_prefs(root)
        print(f"[bootstrap] {target} 已存在 (跳过, --force 强制覆盖)", file=sys.stderr)
        return existing or {}

    # 读旧 jsonl + 跑 deterministic 聚合
    entries = load_feedback_history(
        root=root,
        max_history_days=DEFAULT_MAX_HISTORY_DAYS,
        today=today,
    )
    runtime_hints = load_runtime_hints(
        today=today,
        halflife=DEFAULT_HALFLIFE_DAYS,
        min_count=DEFAULT_MIN_COUNT,
        max_history_days=DEFAULT_MAX_HISTORY_DAYS,
        root=root,
    )

    boost = list((runtime_hints or {}).get("boost") or [])
    penalty = list((runtime_hints or {}).get("penalty") or [])
    n_entries = len(entries)

    # 取 chip 出现次数最高的 5 条作 evidence
    chip_counter: dict[str, int] = {}
    for e in entries:
        for c in e.get("chips") or []:
            chip_counter[c] = chip_counter.get(c, 0) + 1
    top_chips = sorted(chip_counter.items(), key=lambda x: -x[1])[:5]

    evidence = []
    if runtime_hints:
        for token in boost + penalty:
            evidence.append({
                "token": token,
                "source": "legacy_frequency_aggregate",
                "rationale": (
                    f"D-043 旧 jsonl 频次聚合 (半衰期 30d, 拉普拉斯 ≥2): "
                    f"top chips {top_chips}"
                ),
            })

    prefs = {
        "version": 1,
        "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "based_on_days": DEFAULT_MAX_HISTORY_DAYS,
        "based_on_meals": n_entries,
        "boost": boost,
        "penalty": penalty,
        "signals_not_scored": {},
        "evidence": evidence,
        "regularities_freetext": [
            "bootstrap from D-043 legacy jsonl, run /api/long_term_prefs/refresh "
            "to upgrade via LLM extraction once V1.1 feedback accumulates",
        ],
        "bootstrap_from_legacy": True,
    }

    saved_path = save_prefs(prefs, root=root)
    print(f"[bootstrap] wrote {saved_path}", file=sys.stderr)
    print(f"  based_on_meals={n_entries}, boost={boost}, penalty={penalty}",
          file=sys.stderr)
    return prefs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="D-073 PR-0.6: 兜底 D-043 旧 jsonl → 首版 prefs.json"
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help="项目根 (默认: 自动推断). sandbox 用 logs/sandbox/",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="覆盖已存在的 prefs.json",
    )
    parser.add_argument(
        "--today", type=str, default=None,
        help="模拟日期 YYYY-MM-DD (默认: 真实 today)",
    )
    args = parser.parse_args(argv)

    today = None
    if args.today:
        today = dt.date.fromisoformat(args.today)

    prefs = bootstrap(root=args.root, force=args.force, today=today)
    if prefs:
        print(json.dumps(prefs, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

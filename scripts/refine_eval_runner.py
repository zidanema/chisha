"""T-P1a-03 follow-up: refine v2 LLM 抽取 eval runner.

Done When: 准确率 ≥ 85% (per-slot check 命中率).

跑法 (默认 sonnet, 见 memory `chisha_l3_model_refine_intent_sensitivity`):
    uv run python -m scripts.refine_eval_runner --eval-set tests/refine_eval/eval_set.jsonl

--no-llm: 仅走 V1 from_legacy (用来对照基线, 验证 V1 路径在 eval set 上的命中率).

Eval 维度 (expected JSON 支持以下 assertion 操作符):
  - <field>: <value>            字面相等
  - <field>_contains: <substr>  当字段是 list[str] 或 str 时检查 substring
  - <field>_contains_any: [...] list 含 any 一个
  - <field>_nonempty: true      list/str 非空
  - <field>_nonnull: true       字段非 null
  - is_empty: true              v2.is_empty()
  - is_empty_redirect: true     v2.redirect 全空
  - is_empty_strict: true       redirect+constrain+reference+reject_previous 全空
  - is_empty_redirect_avoid_assoc: true  redirect 全空 (验证"不主观联想")
  - raw_understanding_nonempty: true
  - constrain.price_max_nonnull_or_legacy_cheap: true  价格类容错 (legacy price_band=cheap 也算)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from chisha.refine_intent_v2 import extract_refine_intent_v2


def _get_path(d: dict | None, path: str) -> Any:
    """点号路径取值, 不存在返 None. e.g. 'constrain.functional.low_caffeine'."""
    if d is None:
        return None
    cur: Any = d
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _check_assertion(v2_dict: dict, key: str, expected: Any) -> tuple[bool, str]:
    """对单条 expected assertion 求值. 返 (passed, note)."""
    # 特殊 key 集中处理
    if key == "is_empty":
        passed = bool(expected) == bool(_v2_is_empty(v2_dict))
        return passed, f"is_empty={_v2_is_empty(v2_dict)} (expected {expected})"
    if key == "is_empty_redirect":
        passed = bool(expected) == _all_empty_lists(v2_dict.get("redirect", {}))
        return passed, f"redirect empty={_all_empty_lists(v2_dict.get('redirect', {}))}"
    if key == "is_empty_strict":
        redirect_empty = _all_empty_lists(v2_dict.get("redirect", {}))
        constrain = v2_dict.get("constrain") or {}
        constrain_empty = all(
            v in (None, False, [], "", {}) or
            (k == "functional" and isinstance(v, dict) and
             all(x in (None, False) for x in v.values()))
            for k, v in constrain.items()
        )
        ref_empty = not v2_dict.get("reference")
        rp_empty = not v2_dict.get("reject_previous")
        passed = bool(expected) == (redirect_empty and constrain_empty and
                                       ref_empty and rp_empty)
        return passed, (f"strict_empty=redir{redirect_empty}/"
                        f"constrain{constrain_empty}/ref{ref_empty}/rp{rp_empty}")
    if key == "is_empty_redirect_avoid_assoc":
        passed = bool(expected) == _all_empty_lists(v2_dict.get("redirect", {}))
        return passed, f"redirect={v2_dict.get('redirect')}"
    if key == "raw_understanding_nonempty":
        ru = v2_dict.get("raw_understanding") or ""
        passed = bool(expected) == (len(ru.strip()) > 0)
        return passed, f"raw_understanding={ru[:30]!r}"
    if key == "constrain.price_max_nonnull_or_legacy_cheap":
        pm = _get_path(v2_dict, "constrain.price_max")
        legacy_cheap = (v2_dict.get("legacy_v1", {}).get("price_band") == "cheap")
        passed = bool(expected) == (pm is not None or legacy_cheap)
        return passed, f"price_max={pm} legacy_cheap={legacy_cheap}"

    # 操作符后缀
    if key.endswith("_contains"):
        path = key[: -len("_contains")]
        v = _get_path(v2_dict, path)
        if isinstance(v, list):
            passed = any(expected in x for x in v if isinstance(x, str))
        elif isinstance(v, str):
            passed = expected in v
        else:
            passed = False
        return passed, f"{path}={v} contains {expected!r}? {passed}"
    if key.endswith("_contains_any"):
        path = key[: -len("_contains_any")]
        v = _get_path(v2_dict, path) or []
        passed = isinstance(v, list) and any(
            any(e in item for item in v if isinstance(item, str))
            for e in expected
        )
        return passed, f"{path}={v} contains_any {expected}? {passed}"
    if key.endswith("_nonempty"):
        path = key[: -len("_nonempty")]
        v = _get_path(v2_dict, path)
        passed = bool(expected) == bool(v)
        return passed, f"{path}={v}"
    if key.endswith("_nonnull"):
        path = key[: -len("_nonnull")]
        v = _get_path(v2_dict, path)
        passed = bool(expected) == (v is not None)
        return passed, f"{path}={v}"

    # 字面相等 (含 list 顺序敏感 → 用 set 对比避免顺序问题)
    actual = _get_path(v2_dict, key)
    if isinstance(expected, list) and isinstance(actual, list):
        passed = set(expected) == set(actual)
    else:
        passed = actual == expected
    return passed, f"{key}: actual={actual!r} expected={expected!r}"


def _v2_is_empty(d: dict) -> bool:
    """复用 RefineIntentV2.is_empty 的等价逻辑 (避开 dataclass 重建)."""
    if d.get("reject_previous"):
        return False
    if not _all_empty_lists(d.get("redirect", {})):
        return False
    constrain = d.get("constrain") or {}
    for k, v in constrain.items():
        if k == "functional":
            if isinstance(v, dict) and any(x not in (None, False) for x in v.values()):
                return False
        elif v not in (None, False, [], "", {}):
            return False
    if d.get("reference"):
        return False
    legacy = d.get("legacy_v1") or {}
    for k in ("cuisine_want", "cuisine_avoid", "ingredient_want",
              "ingredient_avoid", "cooking_method", "flavor_tags",
              "portion", "staple_preference", "price_band"):
        if legacy.get(k):
            return False
    return True


def _all_empty_lists(redirect: dict) -> bool:
    return all((v == [] or v is None) for v in redirect.values())


def run_eval(eval_path: Path, use_llm: bool, *,
              limit: int | None = None,
              verbose: bool = False) -> dict:
    items = []
    for line in eval_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.append(json.loads(line))
    if limit:
        items = items[:limit]

    total_checks = 0
    passed_checks = 0
    per_item: list[dict] = []
    fail_details: list[str] = []

    for item in items:
        text = item.get("text", "")
        v2 = extract_refine_intent_v2(text, use_llm=use_llm)
        v2_dict = v2.to_log_dict()
        expected = item.get("expected", {})
        item_checks = 0
        item_passed = 0
        for key, exp in expected.items():
            ok, note = _check_assertion(v2_dict, key, exp)
            item_checks += 1
            total_checks += 1
            if ok:
                item_passed += 1
                passed_checks += 1
            else:
                fail_details.append(
                    f"[{item['id']}] {key}: {note}"
                )
        per_item.append({
            "id": item["id"],
            "text": text,
            "checks": item_checks,
            "passed": item_passed,
            "raw_understanding": v2_dict.get("raw_understanding", "")[:60],
        })
        if verbose:
            print(f"[{item['id']}] {item_passed}/{item_checks} "
                  f"→ {v2_dict.get('raw_understanding', '')[:50]}")

    accuracy = passed_checks / total_checks if total_checks > 0 else 0.0
    return {
        "total_items": len(items),
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "accuracy": accuracy,
        "use_llm": use_llm,
        "per_item": per_item,
        "fail_details": fail_details,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", type=Path,
                     default=Path("tests/refine_eval/eval_set.jsonl"))
    ap.add_argument("--no-llm", action="store_true",
                     help="跳过 LLM, 仅走 V1 from_legacy 基线 (对照用)")
    ap.add_argument("--limit", type=int, default=None,
                     help="只跑前 N 条 (debug 用)")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.85,
                     help="准确率阈值 (默认 0.85). 低于 → exit 1")
    args = ap.parse_args()

    if not args.eval_set.exists():
        print(f"eval set not found: {args.eval_set}")
        sys.exit(2)

    use_llm = not args.no_llm
    res = run_eval(args.eval_set, use_llm=use_llm,
                    limit=args.limit, verbose=args.verbose)

    print()
    print("=" * 60)
    print(f"refine v2 eval | use_llm={res['use_llm']}")
    print(f"items: {res['total_items']}  checks: {res['total_checks']}")
    print(f"passed: {res['passed_checks']} / {res['total_checks']}  "
          f"accuracy: {res['accuracy']:.1%}")
    print(f"threshold: {args.threshold:.0%} "
          f"{'PASS' if res['accuracy'] >= args.threshold else 'FAIL'}")
    print("=" * 60)

    if res["fail_details"]:
        print("\n失败明细:")
        for line in res["fail_details"][:30]:
            print(f"  ✗ {line}")
        if len(res["fail_details"]) > 30:
            print(f"  ... 还有 {len(res['fail_details']) - 30} 条")

    sys.exit(0 if res["accuracy"] >= args.threshold else 1)


if __name__ == "__main__":
    main()

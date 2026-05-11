"""V1 vs V2 黄金 case 离线评估脚本.

读 tests/golden_cases.yaml, 对每个 case 跑 V1 (现有 recommend) 和 V2 (本轮升级),
抽提关键指标输出 markdown 对比表格.

V2 实现完成前, --candidate v2 等同于 v1 (会 print warning).

用法:
    uv run python scripts/eval_recommend.py
    uv run python scripts/eval_recommend.py --baseline v1 --candidate v2
    uv run python scripts/eval_recommend.py --case lunch_want_soup --verbose
    uv run python scripts/eval_recommend.py --out eval_out.md
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

# 让 chisha 包能 import
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chisha.context import build_context                          # noqa: E402
from chisha.recall import load_profile, load_zone_data, recall   # noqa: E402
from chisha.rerank import rerank                                  # noqa: E402
from chisha.score import diversify_top, rank_combos               # noqa: E402


CASES_PATH = ROOT / "tests" / "golden_cases.yaml"
PROFILE_PATH = ROOT / "profile.yaml"
DEFAULT_TODAY = dt.date(2026, 5, 13)


# ---------------------------------------------------------------- profile 工具
def deep_merge(base: dict, override: dict) -> dict:
    """递归 merge override into base, 返回新 dict (不修改原)."""
    out = copy.deepcopy(base)

    def _merge(a: dict, b: dict) -> None:
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                _merge(a[k], v)
            elif k.endswith("_append") and isinstance(v, str):
                # taste_description_append: 拼到原 taste_description 后
                base_key = k[: -len("_append")]
                a[base_key] = (a.get(base_key, "") or "") + "\n" + v
            else:
                a[k] = copy.deepcopy(v)

    _merge(out, override)
    return out


def seed_to_meal_log(seed: list[dict]) -> list[dict]:
    """把 case.meal_log_seed (简化版) 转成完整 meal_log 结构."""
    out = []
    for i, e in enumerate(seed):
        date = e.get("date") or e.get("timestamp", "")[:10]
        out.append({
            "log_id": f"seed_{i}",
            "timestamp": f"{date}T12:00:00",
            "meal_type": e.get("meal_type", "lunch"),
            "source": "seed",
            "dishes": [{
                "cuisine": e.get("cuisine"),
                "main_ingredient_type": e.get("main_ingredient_type"),
            }],
        })
    return out


# ---------------------------------------------------------------- runner
def _resolve_zone(profile: dict, meal_type: str) -> str:
    zones = profile.get("basics", {}).get("zones") or {}
    if meal_type in zones:
        return zones[meal_type]
    return profile["basics"]["office_zone"]


def run_v1(profile: dict, meal_log: list[dict], meal_type: str,
           today: dt.date, top_n: int = 5) -> list[dict]:
    """V1 链路: recall → rank_combos → diversify_top.

    不调 LLM reason, 不写 log. 输出 list of combo dict.
    """
    zone = _resolve_zone(profile, meal_type)
    rests, tagged = load_zone_data(zone, ROOT)
    combos = recall(profile, rests, tagged, meal_log, today)
    ranked = rank_combos(combos, profile, meal_log, today)
    top = diversify_top(ranked, n=top_n, max_per_brand=1, max_per_cuisine=2)
    return top


def run_v2(profile: dict, meal_log: list[dict], meal_type: str,
           today: dt.date, daily_mood: str | None = None,
           refine_input: str | None = None, top_n: int = 5,
           use_llm: bool = False) -> list[dict]:
    """V2 链路: build_context → recall → rank_combos(V2) → LLM rerank → top n.

    Args:
        use_llm: True 时 rerank 调 LLM, False 时走 fallback (规则 rerank).
                 默认 False 让 eval 跑得快; 真正比对推荐质量时改 True.
    """
    zone = _resolve_zone(profile, meal_type)
    rests, tagged = load_zone_data(zone, ROOT)

    ctx = build_context(profile, meal_log, meal_type, today,
                        daily_mood=daily_mood, refine_input=refine_input)
    combos = recall(profile, rests, tagged, meal_log, today)
    ranked = rank_combos(combos, profile, meal_log, today,
                         context=ctx, meal_type=meal_type)
    top30 = ranked[:30]
    out = rerank(top30, profile, context=ctx, meal_log=meal_log,
                 n=top_n, n_explore=2, refine=bool(refine_input),
                 use_llm=use_llm)
    return out


# ---------------------------------------------------------------- metrics
def compute_metrics(top: list[dict], expected: dict) -> dict[str, Any]:
    """对一组 top candidates 算指标."""
    if not top:
        return {"n": 0, "veg_pass_ratio": 0, "protein_pass_ratio": 0,
                "avg_oil": None, "processed_meat_count": 0,
                "avg_distance_m": None, "avg_total_price": None,
                "cuisine_diversity": 0, "wetness_count": 0}

    veg_pass, protein_pass = 0, 0
    oils, distances, prices = [], [], []
    cuisines = []
    processed_count = 0
    wetness_count = 0

    for combo in top:
        dishes = combo.get("dishes", [])
        rest = combo.get("restaurant", {})
        # 弱约束三件套
        veg_ok = any(
            d["nutrition_profile"].get("vegetable_ratio_estimate", 0) >= 0.6
            or d["nutrition_profile"].get("main_ingredient_type") == "纯素"
            for d in dishes
        )
        if veg_ok:
            veg_pass += 1
        total_p = sum(
            d["nutrition_profile"].get("protein_grams_estimate", 0)
            for d in dishes
        )
        if total_p >= 25:
            protein_pass += 1
        oils.extend(d["nutrition_profile"].get("oil_level", 3) for d in dishes)
        if rest.get("distance_m", -1) > 0:
            distances.append(rest["distance_m"])
        prices.append(sum(d.get("price", 0) for d in dishes))
        cuisines.extend(d.get("cuisine", "") for d in dishes if d.get("cuisine"))
        # V2 字段 (合流后才有)
        for d in dishes:
            np_ = d.get("nutrition_profile", {})
            if np_.get("processed_meat_flag"):
                processed_count += 1
            if np_.get("wetness"):
                wetness_count += 1
                break  # 一个 combo 含 soup 算 1 即可

    n = len(top)
    return {
        "n": n,
        "veg_pass_ratio": round(veg_pass / n, 2),
        "protein_pass_ratio": round(protein_pass / n, 2),
        "avg_oil": round(sum(oils) / len(oils), 2) if oils else None,
        "avg_distance_m": round(sum(distances) / len(distances)) if distances else None,
        "avg_total_price": round(sum(prices) / len(prices), 1),
        "cuisine_diversity": len(set(cuisines)),
        "processed_meat_count": processed_count,   # V2 字段, V1 数据下=0
        "wetness_count": wetness_count,                  # V2 字段, V1 数据下=0
    }


def fmt_metric(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


# ---------------------------------------------------------------- expected 断言
def _all_dish_names(top: list[dict]) -> list[str]:
    names: list[str] = []
    for c in top:
        for d in c.get("dishes", []):
            n = d.get("canonical_name") or d.get("raw_name") or ""
            if n:
                names.append(n)
    return names


def _all_cuisines(top: list[dict]) -> list[str]:
    out: list[str] = []
    for c in top:
        for d in c.get("dishes", []):
            cu = d.get("cuisine")
            if cu:
                out.append(cu)
    return out


def _max_oil(top: list[dict]) -> int:
    m = 0
    for c in top:
        for d in c.get("dishes", []):
            o = (d.get("nutrition_profile") or {}).get("oil_level", 0)
            if isinstance(o, int) and o > m:
                m = o
    return m


def _max_spicy(top: list[dict]) -> int:
    m = 0
    for c in top:
        for d in c.get("dishes", []):
            s = (d.get("nutrition_profile") or {}).get("spicy_level", 0)
            if isinstance(s, int) and s > m:
                m = s
    return m


def _check_assertion(line: str, top: list[dict],
                     metrics: dict, expected: dict) -> tuple[str, str]:
    """对 expected 里的一行 (must_satisfy / must_not_appear / prefer 通用) 做粗粒度判定.

    返回 (status, detail). status ∈ {PASS, FAIL, SKIP}.
    SKIP = 模式不在已知 DSL 内, 留给人工判断.
    """
    text = line.strip()
    n = metrics.get("n", 0)

    # 模式 1: "每个 combo ... vegetable_ratio_estimate >= 0.6"
    if "vegetable_ratio_estimate" in text and ">= 0.6" in text and "每个" in text:
        ok = metrics.get("veg_pass_ratio", 0) >= 0.99
        return ("PASS" if ok else "FAIL",
                f"veg_pass_ratio={metrics.get('veg_pass_ratio')}")
    if "protein_grams_estimate" in text and ">= 25" in text and "每个" in text:
        ok = metrics.get("protein_pass_ratio", 0) >= 0.99
        return ("PASS" if ok else "FAIL",
                f"protein_pass_ratio={metrics.get('protein_pass_ratio')}")
    # 模式 2: "无菜 oil_level > X" / "每个 combo 无菜 oil_level > X"
    m = re.search(r"oil_level\s*>\s*(\d+)", text)
    if m and ("无" in text or "不可" in text):
        thresh = int(m.group(1))
        actual = _max_oil(top)
        return ("PASS" if actual <= thresh else "FAIL",
                f"max_oil={actual} <= {thresh}?")
    # 模式 3: "每个 combo zone == X" / "餐厅 office_zone == X"
    m = re.search(r"zone\s*==\s*([a-z\-]+)", text)
    if m and ("每个" in text or "每条" in text):
        target = m.group(1)
        bad = []
        for c in top:
            oz = (c.get("restaurant") or {}).get("office_zone")
            if oz and oz != target:
                bad.append(oz)
        return ("PASS" if not bad else "FAIL",
                f"非 {target}: {bad[:3]}")
    if m and ("不应出现" in text or "不会出现" in text or "不应" in text):
        target = m.group(1)
        bad = [oz for c in top
                if (oz := (c.get("restaurant") or {}).get("office_zone")) == target]
        return ("PASS" if not bad else "FAIL",
                f"误出现 {target}: {len(bad)}")
    # 模式 4: "spicy_level > X"
    m = re.search(r"spicy_level\s*>\s*(\d+)", text)
    if m and ("无" in text or "不可" in text or "不应" in text):
        thresh = int(m.group(1))
        actual = _max_spicy(top)
        return ("PASS" if actual <= thresh else "FAIL",
                f"max_spicy={actual} <= {thresh}?")
    # 模式 5: "avoid_dishes: A / B / C" - 不应出现这些菜名
    if "avoid_dishes" in text or "不应出现" in text:
        # 抽出冒号后的菜名列表 (按 / 或 空格分隔)
        m = re.search(r"[:：](.+)$", text)
        if m:
            blocked = re.findall(r"[一-鿿]+", m.group(1))
            names = _all_dish_names(top)
            hit = [b for b in blocked if any(b in nm for nm in names)]
            return ("PASS" if not hit else "FAIL",
                    f"命中 avoid: {hit}")
    # 模式 6: "至少 N/M 候选含 X 字段=true" 或 "至少 N/M 候选含 X >= Y"
    m = re.search(r"至少\s*(\d+)\s*/\s*\d+\s*候选含\s*(\S+)", text)
    if m:
        need = int(m.group(1))
        flag = m.group(2)
        # wetness >= 3 / soup_or_broth_flag == true / processed_meat_flag=true
        cnt = 0
        for c in top:
            for d in c.get("dishes", []):
                np_ = d.get("nutrition_profile") or {}
                if "wetness" in flag:
                    w = np_.get("wetness", 0)
                    if isinstance(w, int) and w >= 3:
                        cnt += 1
                        break
                elif "soup" in flag:
                    if np_.get("soup_or_broth_flag") or np_.get("wetness", 0) >= 3:
                        cnt += 1
                        break
                elif "processed_meat" in flag and "false" in text.lower():
                    pass
                elif "processed_meat" in flag:
                    if np_.get("processed_meat_flag"):
                        cnt += 1
                        break
        return ("PASS" if cnt >= need else "FAIL",
                f"含 {flag} 的 combo: {cnt}/{need}")
    # 模式 7: "top5 中 cuisine == X 数量 <= N"
    m = re.search(r"cuisine\s*==\s*(\S+).*?(<=|≤)\s*(\d+)", text)
    if m:
        cu = m.group(1)
        thresh = int(m.group(3))
        cnt = sum(1 for c in top
                   if any(d.get("cuisine") == cu for d in c.get("dishes", [])))
        return ("PASS" if cnt <= thresh else "FAIL",
                f"cuisine={cu} 数={cnt} <= {thresh}?")
    # 模式 8: "top combo total_price <= N"
    m = re.search(r"total_price\s*<=\s*(\d+)", text)
    if m and "每个" in text:
        thresh = int(m.group(1))
        bad = []
        for c in top:
            tp = sum(d.get("price", 0) for d in c.get("dishes", []))
            if tp > thresh:
                bad.append(tp)
        return ("PASS" if not bad else "FAIL",
                f"超价: {bad[:3]} > {thresh}")
    # 模式 9: "top3 中 任何菜 processed_meat_flag == false"
    if "processed_meat_flag" in text and "top3" in text:
        top3 = top[:3]
        bad = [d.get("canonical_name") for c in top3
                for d in c.get("dishes", [])
                if (d.get("nutrition_profile") or {}).get("processed_meat_flag")]
        return ("PASS" if not bad else "FAIL",
                f"top3 含加工肉: {bad[:3]}")
    return ("SKIP", "未识别模式 (人工)")


def check_case(top: list[dict], expected: dict,
                metrics: dict) -> dict[str, list[tuple[str, str, str]]]:
    """跑 expected 下三个段的所有断言, 返回 {段: [(line, status, detail)]}."""
    result: dict[str, list[tuple[str, str, str]]] = {}
    for section in ["must_satisfy", "must_not_appear", "prefer"]:
        items = expected.get(section) or []
        result[section] = []
        for line in items:
            status, detail = _check_assertion(line, top, metrics, expected)
            result[section].append((line, status, detail))
    return result


def render_assertions(case_results: list[dict]) -> str:
    """渲染断言矩阵 (markdown)."""
    out = ["\n## 断言验收 (must_satisfy / must_not_appear / prefer)\n"]
    out.append("| Case | section | line | status | detail |")
    out.append("|---|---|---|---|---|")
    for cr in case_results:
        name = cr["name"]
        for section, lines in cr["assertions"].items():
            for line, status, detail in lines:
                short_line = line if len(line) <= 50 else line[:47] + "..."
                out.append(
                    f"| {name} | {section} | {short_line} | "
                    f"**{status}** | {detail} |"
                )
    # 汇总
    pass_n = fail_n = skip_n = 0
    for cr in case_results:
        for section, lines in cr["assertions"].items():
            for _, status, _ in lines:
                if status == "PASS":
                    pass_n += 1
                elif status == "FAIL":
                    fail_n += 1
                else:
                    skip_n += 1
    out.append(
        f"\n**总计**: PASS={pass_n} / FAIL={fail_n} / SKIP={skip_n}"
        f" (SKIP=DSL 未覆盖, 留人工)"
    )
    return "\n".join(out)




def render_diff(b: dict, c: dict) -> str:
    """单 case baseline vs candidate metric 对比, 输出 markdown 行."""
    keys = ["n", "veg_pass_ratio", "protein_pass_ratio", "avg_oil",
            "avg_distance_m", "avg_total_price", "cuisine_diversity",
            "processed_meat_count", "wetness_count"]
    return " | ".join(
        f"{fmt_metric(b.get(k))} → {fmt_metric(c.get(k))}" for k in keys
    )


# ---------------------------------------------------------------- runner main
RUNNERS = {"v1": run_v1, "v2": run_v2}


def run_case(case: dict, runner_name: str) -> tuple[list[dict], dict]:
    runner = RUNNERS[runner_name]
    base_profile = load_profile(PROFILE_PATH)
    profile = deep_merge(base_profile, case["input"].get("profile_overrides") or {})
    meal_log = seed_to_meal_log(case["input"].get("meal_log_seed") or [])
    today_raw = case["input"].get("today")
    if isinstance(today_raw, dt.date):
        today = today_raw
    elif isinstance(today_raw, str):
        today = dt.date.fromisoformat(today_raw)
    else:
        today = DEFAULT_TODAY
    meal_type = case["input"]["meal_type"]
    ctx_overrides = case["input"].get("context_overrides") or {}

    kwargs = {}
    if runner_name == "v2":
        kwargs["daily_mood"] = ctx_overrides.get("daily_mood")
        kwargs["refine_input"] = ctx_overrides.get("user_refine_input") or \
            ctx_overrides.get("recent_user_input")

    top = runner(profile, meal_log, meal_type, today, **kwargs)
    metrics = compute_metrics(top, case.get("expected") or {})
    return top, metrics


def render_table(rows: list[dict]) -> str:
    """rows: [{name, baseline_metrics, candidate_metrics}]"""
    head = (
        "| Case | n | veg% | prot% | oil | dist_m | price | cuisine | "
        "processed | soup |"
    )
    sep = "|" + "|".join(["---"] * 10) + "|"
    out = [head, sep]
    for r in rows:
        b, c = r["baseline_metrics"], r["candidate_metrics"]
        out.append(
            f"| **{r['name']}** (baseline) | "
            + " | ".join(fmt_metric(b.get(k)) for k in
                         ["n", "veg_pass_ratio", "protein_pass_ratio",
                          "avg_oil", "avg_distance_m", "avg_total_price",
                          "cuisine_diversity", "processed_meat_count",
                          "wetness_count"])
            + " |"
        )
        out.append(
            f"| **{r['name']}** (candidate) | "
            + " | ".join(fmt_metric(c.get(k)) for k in
                         ["n", "veg_pass_ratio", "protein_pass_ratio",
                          "avg_oil", "avg_distance_m", "avg_total_price",
                          "cuisine_diversity", "processed_meat_count",
                          "wetness_count"])
            + " |"
        )
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(CASES_PATH))
    parser.add_argument("--baseline", default="v1", choices=list(RUNNERS))
    parser.add_argument("--candidate", default="v2", choices=list(RUNNERS))
    parser.add_argument("--case", help="只跑指定 case name")
    parser.add_argument("--out", help="markdown 输出文件 (默认 stdout)")
    parser.add_argument("--verbose", action="store_true",
                        help="打印每个 case 的 top candidates 详情")
    args = parser.parse_args()

    with open(args.cases, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    cases = spec["cases"]
    if args.case:
        cases = [c for c in cases if c["name"] == args.case]
        if not cases:
            print(f"找不到 case: {args.case}", file=sys.stderr)
            return 2

    rows = []
    for case in cases:
        name = case["name"]
        print(f"\n=== {name} ===", file=sys.stderr)
        try:
            b_top, b_met = run_case(case, args.baseline)
            c_top, c_met = run_case(case, args.candidate)
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        # 跑 candidate 的 expected 断言
        assertions = check_case(c_top, case.get("expected") or {}, c_met)
        rows.append({
            "name": name,
            "description": case.get("description", ""),
            "baseline_metrics": b_met,
            "candidate_metrics": c_met,
            "assertions": assertions,
        })
        if args.verbose:
            print(f"  baseline: {b_met}", file=sys.stderr)
            print(f"  candidate: {c_met}", file=sys.stderr)
            print(f"  baseline top names: "
                  f"{[' + '.join(d['canonical_name'] for d in c.get('dishes', [])) for c in b_top]}",
                  file=sys.stderr)

    md = (
        f"# chisha eval: {args.baseline} vs {args.candidate}\n"
        f"\n生成时间: {dt.datetime.now().isoformat(timespec='seconds')}\n"
        f"Cases: {len(rows)}\n"
        f"\n## 指标对比 (每个 case 上下两行: baseline / candidate)\n\n"
        + render_table(rows)
        + render_assertions(rows)
        + "\n\n## 字段说明\n\n"
        "- `n`: top 候选数 (V1=3, V2=5)\n"
        "- `veg%` / `prot%`: top 中满足蔬菜/蛋白下限的比例\n"
        "- `oil`: top 候选所有菜的平均 oil_level (1-5)\n"
        "- `dist_m`: top 餐厅平均距离 (米)\n"
        "- `price`: top combo 平均总价 (元)\n"
        "- `cuisine`: top 中不同 cuisine 数 (越大越多样)\n"
        "- `processed`: top 中 processed_meat_flag=true 的菜数 (V2 字段, V1 数据下恒为 0)\n"
        "- `soup`: top 中含 wetness=true 的 combo 数 (V2 字段, V1 数据下恒为 0)\n"
    )

    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"\n→ 写入 {args.out}", file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())

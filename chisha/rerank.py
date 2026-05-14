"""LLM 精排 (D-035 → D-046): topN candidates → 5 个候选 (3 exploit + 2 explore).

D-046 重构 (2026-05-13):
- top N 从 30 → 40 (L2 4 层 cap 已把多样性骨架定死, top31-40 仍有结构增量,
  top41+ 高度同质, 且 lost-in-the-middle 会让 LLM 看不见中后段)
- prompt 拆 system / user:
  - system (prompts/rerank_system.md): 角色 + 任务 + 输出 schema + few-shot,
    打 Anthropic prompt cache, 100% 命中
  - user: 紧凑符号化的 PROFILE+CONTEXT+CANDIDATES, 每菜一行约 80-100 字符
- payload 紧凑化: 每 candidate 从 ~1.47k chars 砍到 ~600 chars, 默认值省略
- health_flags 从 LLM 输出移除, 改 rerank.py 收到结果后用规则算 (确定性 +
  省 input/output token + 不再让 LLM 算油的算术平均). 最终对外字段不变.

输入: 打分后 top40 combos + ContextSnapshot + profile + meal_log.
输出: list[dict], 每条 candidate 含:
    rank / is_explore / combo_index / fit_score / health_flags /
    taste_match / risk_flags / one_line_reason

LLM 失败 → fallback (规则) 退化到打分 top n + 规则 reason, 保证管道不断.
refine=True 时 n_explore=0 (D-015).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chisha.context import ContextSnapshot

ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT_PATH = ROOT / "prompts" / "rerank_system.md"


# L3 LLM rerank 的输入候选数 (D-046 一审: 40 → 二审: 60 → D-047 终: 60).
# D-046 二审依据 (Codex 实测两 zone 分布):
#   shenzhen-bay top41-60 score 跨度 1.997, 10 brand / 12 个新餐厅 / 5 cuisine,
#     这一段是被 L2 4 层 cap 挤出 head 的真高分 tail.
# D-047 (2026-05-14) 矩阵实测 (lunch/want_light, sonnet+opus × top30/60/100 × 3
# 重复 = 18 调用, 100% tool_use 稳定):
#   - sonnet picks 跨 K: top30 [0,8,11,13,16,22] → top60 新增 [31,35,55] →
#     top100 新增 [83]. 验证 top31-60 真有多样性增量.
#   - opus picks 跨 K: top30 [13,16,18,20,22,24] → top60 新增 [2,31,55] →
#     top100 新增 [92].
#   - top100 边际增量小 (只多 1 个新候选), 成本 +40% 不值.
# K=60 是稳定 + 多样性 + 成本的最优平衡. tool_use 强制 schema (D-047) 完全
# 解决 D-046.1 的 CoT 泄漏问题, 不再需要 D-047 之前临时退回到 30.
L3_INPUT_TOP_K = 60


# D-047 tool schema: forced JSON schema 比 prompt 约束 + json_mode 强得多.
# Anthropic 原生 input_schema 格式; llm_client 自动适配 OR 的 OpenAI 格式.
_RERANK_TOOL = {
    "name": "select_top_candidates",
    "description": (
        "Select 5 candidates (3 exploit + 2 explore) from the input candidate "
        "list, in rank order. exploit 段在前, explore 段在后."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "minItems": 1, "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "rank": {"type": "integer", "minimum": 1, "maximum": 5},
                        "is_explore": {"type": "boolean"},
                        "combo_index": {"type": "integer", "minimum": 0},
                        "fit_score": {"type": "number", "minimum": 0, "maximum": 1},
                        "taste_match": {"type": "number", "minimum": 0, "maximum": 1},
                        "risk_flags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "one_line_reason": {
                            "type": "string", "maxLength": 60,
                        },
                    },
                    "required": [
                        "rank", "is_explore", "combo_index",
                        "fit_score", "taste_match",
                        "risk_flags", "one_line_reason",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["candidates"],
        "additionalProperties": False,
    },
}
_RERANK_TOOL_CHOICE = {"type": "tool", "name": "select_top_candidates"}

# D-047 默认走 opus (V3+V4 实测质量略胜 sonnet 65% 成本溢价但更尊重 taste).
# 故障时调用方传 model="anthropic/claude-sonnet-4.6" 降级 (绝不加 thinking,
# Anthropic 官方明确 forced tool_choice + extended thinking 不兼容).
_DEFAULT_RERANK_MODEL = "anthropic/claude-opus-4.7"


# LLM 输出的必填字段 (D-046: 删了 health_flags, 由规则后处理算)
_REQUIRED_FIELDS = {
    "rank", "is_explore", "combo_index",
    "fit_score", "taste_match",
    "risk_flags", "one_line_reason",
}


# ─────────────────────── payload 紧凑化 (D-046) ───────────────────────


def _fmt_dish_line(d: dict) -> str:
    """单菜紧凑一行: `菜名｜main·烹·油N[·辣N·甜N·汤N]·[processed]｜role=X[·grain=Y]｜价`

    默认值不输出 (辣 0, 甜 0, 汤 1-2 不显示, processed False 不显示);
    role=配菜 默认省略 (最常见); grain 仅主食类菜显示.
    """
    np_ = d.get("nutrition_profile") or {}
    name = d.get("canonical_name", "?")
    main = np_.get("main_ingredient_type") or ""
    method = np_.get("cooking_method") or ""
    oil = np_.get("oil_level", 3)
    spicy = np_.get("spicy_level", 0)
    sweet = np_.get("sweet_sauce_level", 0) or 0
    wet = np_.get("wetness", 1) or 1
    role = np_.get("dish_role") or "配菜"
    grain = np_.get("grain_type") or ""
    processed = bool(np_.get("processed_meat_flag"))
    price = d.get("price", 0) or 0

    # 第一段: main·烹·油N (固定显示)
    seg1 = []
    if main: seg1.append(main)
    if method: seg1.append(method)
    seg1.append(f"油{int(oil)}")
    # 条件标注
    if spicy and int(spicy) > 0:
        seg1.append(f"辣{int(spicy)}")
    if sweet and int(sweet) >= 2:
        seg1.append(f"甜{int(sweet)}")
    if wet and int(wet) >= 3:
        seg1.append(f"汤{int(wet)}")
    if processed:
        seg1.append("processed")
    # 第二段: role 仅在不是配菜时显示
    seg2 = []
    if role and role != "配菜":
        seg2.append(f"role={role}")
    if grain and grain != "无" and (role == "主食" or "主食" in (role or "")):
        seg2.append(f"grain={grain}")

    parts = ["·".join(seg1)]
    if seg2:
        parts.append("·".join(seg2))
    parts.append(f"{float(price):.1f}")
    return f"  · {name}｜{'｜'.join(parts)}"


def _fmt_combo_block(idx: int, c: dict) -> str:
    """单 combo 紧凑块: header 行 + 每菜一行."""
    rest = c.get("restaurant") or {}
    name = rest.get("name", "?")
    dist_m = rest.get("distance_m", -1)
    eta = rest.get("delivery_eta_min", -1)
    score = c.get("score", 0)
    dishes = c.get("dishes") or []
    total = sum((d.get("price") or 0) for d in dishes)
    dist_str = f"{int(dist_m)/1000:.1f}km" if isinstance(dist_m, (int, float)) and dist_m > 0 else "?"
    eta_str = f"{int(eta)}min" if isinstance(eta, (int, float)) and eta > 0 else "?"
    header = f"[{idx}] {name}（{dist_str}/{eta_str}/L2 {score:.2f}/¥{total:.1f}）"
    lines = [header] + [_fmt_dish_line(d) for d in dishes]
    return "\n".join(lines)


def _profile_block(profile: dict) -> str:
    prefs = profile.get("preferences", {}) or {}
    lines = [
        "[PROFILE]",
        f"口味描述: {profile.get('taste_description','') or '(空)'}",
        f"喜欢: {prefs.get('liked_cuisines') or []}",
        f"不喜欢: {prefs.get('disliked_cuisines') or []}",
        f"avoid: {prefs.get('avoid_dishes') or []}",
        f"辣度耐受: {prefs.get('spicy_tolerance', 2)}",
    ]
    return "\n".join(lines)


def _context_block(context: "ContextSnapshot | None") -> str:
    if context is None:
        return "[CONTEXT] null"
    cd = context.to_llm_dict()
    # 上顿摘要: 取 cuisine + dishes 数, 不全展开
    last_meal = cd.get("last_meal") or {}
    if last_meal:
        d = last_meal.get("dishes") or []
        names = "+".join((x.get("canonical_name") or "?") for x in d[:3])
        last_meal_brief = (
            f"{last_meal.get('meal_type','?')} {last_meal.get('cuisine','')}: {names}"
        )
    else:
        last_meal_brief = "(无)"
    recent = cd.get("recent_3d_cuisines") or {}
    methods_3d = cd.get("recent_3d_cooking_methods") or {}
    last_fb = cd.get("last_feedback") or {}
    chips = last_fb.get("chips") if isinstance(last_fb, dict) else None
    lines = [
        "[CONTEXT]",
        f"饭期: {cd.get('meal_type')}",
        f"心情: {cd.get('daily_mood') or '(无)'}",
        f"上顿: {last_meal_brief}",
        f"最近 3 天 cuisine: {dict(list(recent.items())[:8]) if recent else '(空)'}",
        f"最近 3 天 cooking: {dict(list(methods_3d.items())[:8]) if methods_3d else '(空)'}",
        f"上次反馈 chips: {chips or '(无)'}",
        f"refine 输入: {cd.get('refine_input') or '(无)'}",
    ]
    return "\n".join(lines)


def build_user_message(
    top_combos: list[dict],
    profile: dict,
    context: "ContextSnapshot | None",
    n: int,
    n_explore: int,
) -> str:
    """拼 user message: CONFIG + PROFILE + CONTEXT + CANDIDATES, 紧凑符号化."""
    blocks = [
        f"[CONFIG] n={n} n_explore={n_explore}",
        _profile_block(profile),
        _context_block(context),
        "[CANDIDATES]",
    ]
    for idx, c in enumerate(top_combos):
        blocks.append(_fmt_combo_block(idx, c))
    return "\n\n".join(blocks)


def build_payload(
    top_combos: list[dict],
    profile: dict,
    context: "ContextSnapshot | None",
    meal_log: list[dict] | None,
    n: int,
    n_explore: int,
) -> dict:
    """打包 LLM rerank 输入 (legacy JSON 形态, 主要给 debug trace 用).

    D-046: 实际给 LLM 的是 build_user_message() 的紧凑文本. 本函数保留是为了
    debug_recommend trace 兼容 + 单测断言. 字段集和 V2 保持一致.
    """
    candidates = []
    for idx, c in enumerate(top_combos):
        rest = c.get("restaurant", {})
        candidates.append({
            "combo_index": idx,
            "restaurant": {
                "name": rest.get("name", ""),
                "cuisine": rest.get("category", ""),
                "distance_m": rest.get("distance_m", -1),
                "eta_min": rest.get("delivery_eta_min", -1),
            },
            "dishes": [
                {
                    "canonical_name": d.get("canonical_name", ""),
                    "cuisine": d.get("cuisine", ""),
                    "price": d.get("price", 0),
                    "main_ingredient_type":
                        d["nutrition_profile"].get("main_ingredient_type", ""),
                    "cooking_method":
                        d["nutrition_profile"].get("cooking_method", ""),
                    "oil_level": d["nutrition_profile"].get("oil_level", 3),
                    "spicy_level": d["nutrition_profile"].get("spicy_level", 0),
                    "dish_role": d["nutrition_profile"].get("dish_role"),
                    "processed_meat_flag":
                        d["nutrition_profile"].get("processed_meat_flag", False),
                    "sweet_sauce_level":
                        d["nutrition_profile"].get("sweet_sauce_level"),
                    "wetness": d["nutrition_profile"].get("wetness"),
                    "grain_type": d["nutrition_profile"].get("grain_type"),
                }
                for d in c.get("dishes", [])
            ],
            "total_price": sum(
                (d.get("price") or 0) for d in c.get("dishes", [])
            ),
            "score": round(c.get("score", 0), 3),
        })

    payload: dict[str, Any] = {
        "config": {"n": n, "n_explore": n_explore},
        "profile": {
            "taste_description": profile.get("taste_description", ""),
            "liked_cuisines": profile["preferences"].get("liked_cuisines", []),
            "disliked_cuisines": profile["preferences"].get("disliked_cuisines", []),
            "avoid_dishes": profile["preferences"].get("avoid_dishes", []),
            "spicy_tolerance": profile["preferences"].get("spicy_tolerance", 2),
        },
        "context": context.to_llm_dict() if context else None,
        "candidates": candidates,
    }
    return payload


def fallback_rerank(
    top_combos: list[dict],
    n: int = 5,
    n_explore: int = 2,
    meal_log: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """规则 fallback: 取打分 top (n - n_explore) 当 exploit (品牌+菜系多样性去重),
    在剩余里挑"最近未吃过的菜系/做法"做 explore.
    每条用最简结构化字段填占位, 不调 LLM.
    """
    if not top_combos:
        return []
    from chisha.score import diversify_top
    n_exploit = max(1, n - n_explore)
    exploit = diversify_top(top_combos, n=n_exploit, max_per_brand=1,
                             max_per_cuisine=2)
    used_ids = {id(c) for c in exploit}
    rest = [c for c in top_combos if id(c) not in used_ids]
    if rest and n_explore > 0:
        explore = _pick_explore(rest, exploit, meal_log or [], n_explore)
    else:
        explore = []

    out: list[dict] = []
    rank = 1
    for c in exploit:
        out.append(_to_rerank_dict(c, rank, is_explore=False, fit_score=c.get("score", 0)))
        rank += 1
    for c in explore:
        out.append(_to_rerank_dict(c, rank, is_explore=True, fit_score=c.get("score", 0) * 0.8))
        rank += 1
    return out


def _pick_explore(
    rest: list[dict],
    already_used: list[dict],
    meal_log: list[dict],
    n_explore: int,
) -> list[dict]:
    """explore 候选: 优先打分中段 + 最近 7 天没吃过的 cuisine/cooking_method."""
    import datetime as dt2
    cutoff = dt2.date.today() - dt2.timedelta(days=7)
    used_cuisines: set[str] = set()
    used_methods: set[str] = set()
    for log in meal_log:
        ts_str = log.get("timestamp", "")
        try:
            d = dt2.date.fromisoformat(ts_str[:10])
        except ValueError:
            continue
        if d < cutoff:
            continue
        for x in log.get("dishes", []):
            if x.get("cuisine"):
                used_cuisines.add(x["cuisine"])
            if x.get("main_ingredient_type"):
                pass
    for c in already_used:
        for d in c.get("dishes", []):
            if d.get("cuisine"):
                used_cuisines.add(d["cuisine"])
            if (d.get("nutrition_profile") or {}).get("cooking_method"):
                used_methods.add(d["nutrition_profile"]["cooking_method"])

    mid_end = max(n_explore, len(rest) // 2)
    mid_pool = rest[:mid_end]
    novel: list[dict] = []
    for c in mid_pool:
        cuisines = {d.get("cuisine", "") for d in c.get("dishes", [])
                     if d.get("cuisine")}
        methods = {(d.get("nutrition_profile") or {}).get("cooking_method", "")
                    for d in c.get("dishes", [])}
        if (cuisines - used_cuisines) or (methods - used_methods):
            novel.append(c)
            if len(novel) >= n_explore:
                break
    if len(novel) < n_explore:
        for c in mid_pool:
            if c not in novel:
                novel.append(c)
                if len(novel) >= n_explore:
                    break
    return novel[:n_explore]


# ─────────────────────── 健康字段规则计算 (D-046) ───────────────────────


def _compute_health_flags(combo: dict) -> dict:
    """从 combo 的菜品字段规则化算 health_flags. LLM 不再算这个.

    必填子键 (与历史对外字段兼容):
        veg_ok / protein_ok / oil_ok / processed_meat / sweet_sauce / wetness
    """
    dishes = combo.get("dishes", []) or []
    veg_ok = any(
        (d.get("nutrition_profile") or {}).get("vegetable_ratio_estimate", 0) >= 0.6
        or (d.get("nutrition_profile") or {}).get("main_ingredient_type") == "纯素"
        for d in dishes
    )
    total_p = sum(
        (d.get("nutrition_profile") or {}).get("protein_grams_estimate", 0)
        for d in dishes
    )
    avg_oil = (
        sum((d.get("nutrition_profile") or {}).get("oil_level", 3) for d in dishes)
        / max(1, len(dishes))
    )
    has_processed = any(
        (d.get("nutrition_profile") or {}).get("processed_meat_flag")
        for d in dishes
    )
    has_wet = any(
        _safe_int((d.get("nutrition_profile") or {}).get("wetness"), 1) >= 3
        for d in dishes
    )
    sweet = any(
        _safe_int((d.get("nutrition_profile") or {}).get("sweet_sauce_level"), 0) >= 3
        for d in dishes
    )
    return {
        "veg_ok": veg_ok,
        "protein_ok": total_p >= 25,
        "oil_ok": avg_oil <= 3,
        "processed_meat": has_processed,
        "sweet_sauce": sweet,
        "wetness": has_wet,
    }


def _to_rerank_dict(combo: dict, rank: int, is_explore: bool,
                    fit_score: float) -> dict[str, Any]:
    """combo + meta → rerank 输出 dict (规则 fallback 用)."""
    flags = _compute_health_flags(combo)
    dishes = combo.get("dishes", []) or []
    total_p = sum(
        (d.get("nutrition_profile") or {}).get("protein_grams_estimate", 0)
        for d in dishes
    )
    avg_oil = (
        sum((d.get("nutrition_profile") or {}).get("oil_level", 3) for d in dishes)
        / max(1, len(dishes))
    )
    return {
        **combo,
        "rank": rank,
        "is_explore": is_explore,
        "combo_index": combo.get("combo_index", -1),
        "fit_score": round(float(fit_score), 3),
        "health_flags": flags,
        "taste_match": None,        # rule fallback 不做语义匹配
        "risk_flags": [],
        "one_line_reason": _rule_reason(combo, flags["wetness"], avg_oil, total_p),
    }


def _safe_int(v, default: int) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _rule_reason(combo: dict, has_wet: bool, avg_oil: float, total_p: float) -> str:
    bits = []
    if has_wet:
        bits.append("汤水清爽")
    if avg_oil <= 2:
        bits.append(f"低油{avg_oil:.1f}")
    if total_p >= 30:
        bits.append(f"蛋白{int(total_p)}g")
    elif total_p >= 25:
        bits.append("蛋白达标")
    if not bits:
        bits.append("结构合规")
    return "，".join(bits)[:30]


def _validate_llm_candidates_v(
    cands: list, n_max: int,
    input_size: int | None = None,
    n_explore_expected: int | None = None,
) -> tuple[list[dict] | None, str | None]:
    """D-047: 同 _validate_llm_candidates 但返回 (cands, error_detail) 元组,
    error_detail 在校验失败时给出具体原因供 trace, 而不是只 print."""
    res = _validate_llm_candidates(cands, n_max=n_max,
                                    input_size=input_size,
                                    n_explore_expected=n_explore_expected)
    if res is None:
        # 重跑一次拿具体原因. 不重复实现是为了让单一 source-of-truth.
        # 简易方案: 记录 stdout 的 print, 但太复杂; 直接重做关键检查的字符串描述.
        return None, _diagnose_candidates(cands, n_max, input_size, n_explore_expected)
    return res, None


def _diagnose_candidates(
    cands: list, n_max: int,
    input_size: int | None,
    n_explore_expected: int | None,
) -> str:
    """重做 _validate_llm_candidates 的关键检查, 返回首个失败的具体描述."""
    if not isinstance(cands, list):
        return f"cands 非 list ({type(cands).__name__})"
    if not cands:
        return "cands 为空"
    if len(cands) > n_max:
        return f"返回 {len(cands)} > n_max={n_max}"
    seen_idx: set[int] = set()
    for i, c in enumerate(cands):
        if not isinstance(c, dict):
            return f"#{i} 非 dict"
        missing = _REQUIRED_FIELDS - set(c)
        if missing:
            return f"#{i} 缺字段 {sorted(missing)}"
        idx = c.get("combo_index")
        if not isinstance(idx, int) or idx < 0:
            return f"#{i} combo_index 非法 {idx!r}"
        if input_size is not None and idx >= input_size:
            return f"#{i} combo_index 越界 {idx} >= {input_size}"
        if idx in seen_idx:
            return f"#{i} combo_index 重复 {idx}"
        seen_idx.add(idx)
        fs = c.get("fit_score")
        if not isinstance(fs, (int, float)) or not (0.0 <= float(fs) <= 1.0):
            return f"#{i} fit_score 越界 {fs!r}"
        tm = c.get("taste_match")
        if tm is not None and (not isinstance(tm, (int, float))
                               or not (0.0 <= float(tm) <= 1.0)):
            return f"#{i} taste_match 越界 {tm!r}"
        if not isinstance(c.get("is_explore"), bool):
            return f"#{i} is_explore 非 bool"
        if not isinstance(c.get("risk_flags"), list):
            return f"#{i} risk_flags 非 list"
    ranks = sorted(c["rank"] for c in cands if isinstance(c.get("rank"), int))
    if ranks != list(range(1, len(cands) + 1)):
        return f"rank 不连续 {ranks}"
    if n_explore_expected is not None:
        n_e = sum(1 for c in cands if c.get("is_explore"))
        if n_e != n_explore_expected:
            return f"explore 数量 {n_e} != 期望 {n_explore_expected}"
        for i, c in enumerate(cands):
            expected_e = i >= (len(cands) - n_explore_expected)
            if bool(c.get("is_explore")) != expected_e:
                return f"#{i} is_explore={c.get('is_explore')} 应为 {expected_e}"
    return "未知 (validate 拒绝但 diagnose 通过, 检查代码漂移)"


def _validate_llm_candidates(
    cands: list, n_max: int,
    input_size: int | None = None,
    n_explore_expected: int | None = None,
) -> list[dict] | None:
    """LLM 输出深度校验. 任何错误返回 None 让上游 fallback.

    D-046 二审补强 (真 Codex review):
    - 加 combo_index 上界校验 (input_size 传入时), 防越界 idx 静默被丢然后规则补位
    - 加 n_explore 数量校验 (n_explore_expected 传入时), 防 LLM 漏写或多写 explore
    - 加 一坨 candidates 总数 == n_max 校验 (n_max 是期望输出数)

    检查:
    - 必填字段 (_REQUIRED_FIELDS, 不含 health_flags)
    - fit_score / taste_match 0-1 数值
    - rank 连续 1..len
    - combo_index 不重复, 0 <= idx < input_size
    - is_explore bool, exploit 段在前 explore 段在后
    - 数量 <= n_max; explore 数量 == n_explore_expected (若传入)
    """
    if not isinstance(cands, list) or not cands:
        return None
    if len(cands) > n_max:
        print(f"  [rerank] LLM 返回 {len(cands)} > n_max={n_max}, 截断")
        cands = cands[:n_max]
    seen_idx: set[int] = set()
    for i, c in enumerate(cands):
        if not isinstance(c, dict):
            return None
        missing = _REQUIRED_FIELDS - set(c)
        if missing:
            print(f"  [rerank] candidate#{i} 缺字段 {missing}")
            return None
        idx = c.get("combo_index")
        if not isinstance(idx, int) or idx < 0:
            print(f"  [rerank] candidate#{i} combo_index 非法: {idx!r}")
            return None
        # D-046 二审: idx 上界校验
        if input_size is not None and idx >= input_size:
            print(f"  [rerank] candidate#{i} combo_index 越界: "
                  f"{idx} >= input_size {input_size}")
            return None
        if idx in seen_idx:
            print(f"  [rerank] candidate#{i} combo_index 重复: {idx}")
            return None
        seen_idx.add(idx)
        fs = c.get("fit_score")
        if not isinstance(fs, (int, float)) or not (0.0 <= float(fs) <= 1.0):
            print(f"  [rerank] candidate#{i} fit_score 越界: {fs!r}")
            return None
        tm = c.get("taste_match")
        # taste_match 允许 None (兼容), 否则必须 0-1
        if tm is not None and (
            not isinstance(tm, (int, float)) or not (0.0 <= float(tm) <= 1.0)
        ):
            print(f"  [rerank] candidate#{i} taste_match 越界: {tm!r}")
            return None
        if not isinstance(c.get("is_explore"), bool):
            return None
        if not isinstance(c.get("risk_flags"), list):
            return None
    ranks = sorted(c["rank"] for c in cands if isinstance(c.get("rank"), int))
    if ranks != list(range(1, len(cands) + 1)):
        print(f"  [rerank] rank 不连续: {ranks}")
        return None
    # D-046 二审: explore 数量校验
    if n_explore_expected is not None:
        n_explore_actual = sum(1 for c in cands if c.get("is_explore"))
        if n_explore_actual != n_explore_expected:
            print(f"  [rerank] explore 数量错误: 期望 {n_explore_expected}, "
                  f"实际 {n_explore_actual}")
            return None
        # exploit 段在前, explore 段在后
        for i, c in enumerate(cands):
            expected_explore = i >= (len(cands) - n_explore_expected)
            if bool(c.get("is_explore")) != expected_explore:
                print(f"  [rerank] candidate#{i} (rank={c.get('rank')}) "
                      f"is_explore={c.get('is_explore')} 但应该是 "
                      f"{expected_explore} (exploit 在前 explore 在后)")
                return None
    return cands


def _run_llm_rerank(
    top_combos: list[dict],
    profile: dict,
    context: "ContextSnapshot | None",
    *,
    n: int,
    n_explore: int,
    n_max: int = 5,
    model: str | None = None,
) -> dict:
    """共享 LLM rerank 调用 helper (D-047 抽出, 同时给 prod _llm_rerank +
    debug _llm_rerank_traced 用, 解决双份代码漂移问题).

    返回 trace dict, 字段:
      - status: "ok" | "fallback"
      - fallback_reason: 仅 fallback 时填, 描述具体原因
      - candidates: 仅 ok 时填, 校验后的 list[dict]
      - llm_response: 完整 call_text 返回 (debug 用)
      - system_prompt_chars / user_message_chars / user_message_full
      - model: 实际使用的 model
      - latency_ms: 测量值

    D-047: 用 tool_use forced schema 强制结构化输出, 完全替代 D-046.1 的
    json_mode + regex 提取路径. 必断言 stop_reason in {"tool_use","tool_calls"}
    防止 LLM 不调 tool 直接 stop.
    """
    import time
    out: dict[str, Any] = {
        "status": "fallback",
        "fallback_reason": None,
        "candidates": None,
        "llm_response": None,
        "system_prompt_chars": 0,
        "user_message_chars": 0,
        "user_message_full": "",
        "model": model or _DEFAULT_RERANK_MODEL,
        "latency_ms": None,
    }
    try:
        from chisha.llm_client import call_text
        system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        user_msg = build_user_message(top_combos, profile, context,
                                       n=n, n_explore=n_explore)
        out["system_prompt_chars"] = len(system_prompt)
        out["user_message_chars"] = len(user_msg)
        out["user_message_full"] = user_msg
        kwargs: dict[str, Any] = {
            "model": model or _DEFAULT_RERANK_MODEL,
            "max_tokens": 2048,
            "temperature": 0.0,
            "system": system_prompt,
            "cache_system": True,
            "tools": [_RERANK_TOOL],
            "tool_choice": _RERANK_TOOL_CHOICE,
        }
        t0 = time.time()
        resp = call_text(user_msg, **kwargs)
        out["latency_ms"] = int((time.time() - t0) * 1000)
        out["llm_response"] = resp

        # B2: 强制断言 stop_reason 是 tool_use, 否则 LLM 没调 tool, 走 fallback.
        # Anthropic 直连 stop_reason 是 "tool_use", OR 是 "tool_calls".
        stop = resp.get("stop_reason")
        if resp.get("type") != "tool_use" or stop not in ("tool_use", "tool_calls"):
            out["fallback_reason"] = (
                f"LLM 未调 tool (type={resp.get('type')}, stop={stop})"
            )
            return out

        if resp.get("tool_name") != _RERANK_TOOL["name"]:
            out["fallback_reason"] = (
                f"LLM 调了错的 tool: {resp.get('tool_name')!r}"
            )
            return out

        tool_input = resp.get("tool_input")
        if not isinstance(tool_input, dict):
            out["fallback_reason"] = (
                f"tool_input 非 dict: {type(tool_input).__name__}"
            )
            return out

        cands = tool_input.get("candidates")
        validated, detail = _validate_llm_candidates_v(
            cands, n_max=n_max,
            input_size=len(top_combos),
            n_explore_expected=n_explore,
        )
        if validated is None:
            out["fallback_reason"] = f"candidates 业务校验失败: {detail}"
            return out

        out["status"] = "ok"
        out["candidates"] = validated
        return out
    except Exception as e:
        out["fallback_reason"] = f"{type(e).__name__}: {str(e)[:120]}"
        return out


def _llm_rerank(top_combos: list[dict], profile: dict,
                context: "ContextSnapshot | None", n: int, n_explore: int,
                model: str | None = None,
                n_max: int = 5) -> list[dict] | None:
    """调 LLM 返回 list of candidate dict, 失败返回 None (上游 fallback).

    D-047: 走 _run_llm_rerank 共享 helper + tool_use 强制 schema.
    """
    res = _run_llm_rerank(
        top_combos, profile, context,
        n=n, n_explore=n_explore, n_max=n_max, model=model,
    )
    if res["status"] != "ok":
        print(f"  [rerank fallback] {res['fallback_reason']}")
        return None
    return res["candidates"]


def rerank(
    top_combos: list[dict],
    profile: dict,
    context: "ContextSnapshot | None" = None,
    meal_log: list[dict] | None = None,
    n: int = 5,
    n_explore: int = 2,
    refine: bool = False,
    use_llm: bool | None = None,
    model: str | None = None,
) -> list[dict]:
    """主入口. LLM 精排 + fallback.

    Args:
        top_combos: 打分后已排序的 candidates (V2 默认 top40, D-046).
        profile / context / meal_log: 见 build_user_message.
        n: 输出候选数, 默认 5.
        n_explore: explore 候选数, 默认 2 (D-015).
        refine: True 时 n_explore=0 (D-015).
        use_llm: 强制开关. None=auto (看 ANTHROPIC_API_KEY).
    """
    if not top_combos:
        return []
    if refine:
        n_explore = 0
    if use_llm is None:
        from chisha.llm_client import has_llm_key
        use_llm = has_llm_key()

    if use_llm:
        llm_out = _llm_rerank(top_combos=top_combos,
                               profile=profile, context=context,
                               n=n, n_explore=n_explore,
                               model=model, n_max=n)
        if llm_out is not None:
            mapped: list[dict] = []
            for cand in llm_out[:n]:
                idx = cand.get("combo_index", -1)
                if not (0 <= idx < len(top_combos)):
                    continue
                # health_flags 由规则补齐 (D-046: LLM 不再输出此字段)
                cand["health_flags"] = _compute_health_flags(top_combos[idx])
                merged = {**top_combos[idx], **cand}
                mapped.append(merged)
            mapped = _enforce_brand_unique(mapped, top_combos, n=n)
            if mapped:
                _log_selection_metrics(mapped, top_combos)
                return mapped

    return fallback_rerank(top_combos, n=n, n_explore=n_explore,
                            meal_log=meal_log)


def _log_selection_metrics(
    mapped: list[dict], top_combos: list[dict]
) -> None:
    """D-046 二审 (真 Codex review) 观测埋点.

    打印 LLM 选中的 5 条 combo_index 落点分布 + 是否有更高分同 brand 被绕过.
    一周后用这些 metric 决策 N=60 是否需要调:
    - P(idx >= 40): N 从 40 涨到 60 是否真的让 L3 看见 L2 没识别的好货
    - P(idx >= 60): 是否需要进一步上调到 80/100
    - brand_has_higher_sibling: LLM 是否真在做"同品牌内部择优"
    """
    def _brand_key(c: dict) -> str:
        rest = c.get("restaurant") or {}
        return rest.get("brand") or rest.get("id") or ""

    selected = [c.get("combo_index", -1) for c in mapped]
    # 落点 band
    def _band(i: int) -> str:
        if i < 0: return "?"
        if i < 10: return "0-9"
        if i < 20: return "10-19"
        if i < 30: return "20-29"
        if i < 40: return "30-39"
        if i < 60: return "40-59"
        if i < 80: return "60-79"
        return "80+"
    bands = [_band(i) for i in selected]
    # 同 brand 是否有更高分 sibling 被 LLM 跳过 (i.e. 同品牌内部择优是否启用)
    brand_to_first_idx: dict[str, int] = {}
    for i, c in enumerate(top_combos):
        bk = _brand_key(c)
        if bk and bk not in brand_to_first_idx:
            brand_to_first_idx[bk] = i
    has_higher_sibling = []
    for c in mapped:
        idx = c.get("combo_index", -1)
        bk = _brand_key(c)
        if bk and bk in brand_to_first_idx and brand_to_first_idx[bk] < idx:
            has_higher_sibling.append(
                f"#{idx}(brand 最高 #{brand_to_first_idx[bk]})"
            )
    higher_str = ", ".join(has_higher_sibling) if has_higher_sibling else "无"
    print(
        f"  [rerank] LLM 选中 idx={selected} band={bands} "
        f"window={len(top_combos)} | 同品牌择优 (跳过更高分 sibling): {higher_str}"
    )


def _enforce_brand_unique(
    mapped: list[dict], top_combos: list[dict], n: int
) -> list[dict]:
    """LLM 可能漏掉去重指令 — 同 brand (连锁) 在 top n 只能出现 1 次.

    D-045: 按 brand 去重 + rid 作为缺失兜底, 与 L2 apply_caps 的 brand 层
    语义保持一致. 不够 n 个时从 top_combos 剩余 combos 里按 score 补齐.
    """
    if not mapped:
        return mapped

    def _brand_key(c: dict) -> str:
        rest = c.get("restaurant") or {}
        return rest.get("brand") or rest.get("id", "")

    seen_brand: set[str] = set()
    out: list[dict] = []
    for c in mapped:
        bk = _brand_key(c)
        if bk and bk in seen_brand:
            continue
        if bk:
            seen_brand.add(bk)
        out.append(c)
    if len(out) >= n:
        return out[:n]
    # 不够 n 个: 从 top_combos 按 score 补齐
    used_combo_ids = {id(c) for c in mapped}
    for c in top_combos:
        if len(out) >= n:
            break
        if id(c) in used_combo_ids:
            continue
        bk = _brand_key(c)
        if bk and bk in seen_brand:
            continue
        if bk:
            seen_brand.add(bk)
        fill = {
            **c,
            "rank": len(out) + 1,
            "is_explore": False,
            "fit_score": c.get("score", 0),
            "health_flags": _compute_health_flags(c),
            "taste_match": None,
            "risk_flags": ["品牌去重补位"],
            "one_line_reason": "为多样性补位, 此条无 LLM 评分",
        }
        out.append(fill)
    for i, c in enumerate(out, start=1):
        c["rank"] = i
    return out

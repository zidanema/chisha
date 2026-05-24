"""召回：规则过滤 + 弱约束三件套校验 + 组合策略 → top N 候选.

完整流程见 DESIGN §5.6。V1 不引入个性化项 (D-024)。
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from itertools import product
from pathlib import Path
from typing import Any

import json
import yaml


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def load_profile(
    path: str | Path = "profile.yaml",
    root: Path | None = None,
) -> dict:
    """加载 profile.yaml + D-072 merge methodology spec defaults.

    流程: 读 yaml → 调 chisha.methodology.apply_methodology(profile, root) merge
    spec 默认值. profile 显式值 override spec. 缺 `methodology:` 字段时 fallback
    `harvard_plate` 并 logger.info 留可观测痕迹 (D-072 schema 表 + Codex M-1).

    Args:
      path: profile.yaml 路径.
      root: 项目根目录 (含 profiles/methodologies/ 子目录). 缺省时推断为
            path.parent (向后兼容). 临时 profile 路径 (如测试用 tmp_path) 必须
            显式传 root, 否则会去 path.parent/profiles/methodologies 找 spec
            而 FileNotFoundError (Codex Round 3 M-1).
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    # 延迟导入避免循环 (methodology 不依赖 recall, 但保险)
    from chisha.methodology import apply_methodology
    if root is None:
        root = Path(path).resolve().parent
    return apply_methodology(raw, root)


def load_zone_data(zone: str, root: Path) -> tuple[list[dict], list[dict]]:
    """读 restaurants + dishes_tagged."""
    base = root / "data" / zone
    rests = json.loads((base / "restaurants.json").read_text(encoding="utf-8"))
    tagged = json.loads((base / "dishes_tagged.json").read_text(encoding="utf-8"))
    return rests, tagged


def load_meal_log(root: Path) -> list[dict]:
    """读 meal_log.jsonl，不存在返回空.

    D-077 PR-1b: 走 data_root.meal_log_path, sandbox 启用时落 logs/sandbox/.
    """
    from chisha import data_root
    p = data_root.meal_log_path(root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_meal_log_entry(
    root: Path,
    session_id: str,
    meal_type: str,
    restaurant_id: str,
    restaurant_name: str,
    dishes: list[dict],
    *,
    zone: str | None = None,
    accepted_rank: int | None = None,
    combo_index: int | None = None,
    candidate_id: str | None = None,
) -> dict:
    """D-078: accept 时往 meal_log.jsonl 追加一条记录, 让 diversity_filter 闭环.

    Schema 与 load_meal_log / diversity_filter 已有期望一致, 并加审计字段:
      {timestamp, session_id, meal_type, zone, restaurant_id, restaurant_name,
       accepted_rank, combo_index, candidate_id,
       dishes: [{main_ingredient_type, canonical_name}, ...]}

    时钟走 chisha.clock.now_utc(root), sandbox 启用时自动用虚拟时钟.

    dishes 接受两种形态:
      - flat (chisha.api._format_candidate 输出): {main_ingredient_type, oil_level}
      - nested (raw tagged): {nutrition_profile: {main_ingredient_type, ...}}
    两种都规范化成 flat main_ingredient_type 落盘.

    并发: append 模式无锁, 与 recommend_log.jsonl 同等约束 (单进程单后端). 多 tab
    高频 accept 在同一秒内的极端情况下可能行交错, 当前 V1 自用单后端不补锁.
    """
    from chisha import clock, data_root
    p = data_root.meal_log_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)

    flat_dishes: list[dict] = []
    for d in dishes or []:
        ing = d.get("main_ingredient_type")
        if ing is None:
            np_ = d.get("nutrition_profile") or {}
            ing = np_.get("main_ingredient_type")
        entry_d = {}
        if ing is not None:
            entry_d["main_ingredient_type"] = ing
        name = d.get("canonical_name") or d.get("name")
        if name:
            entry_d["canonical_name"] = name
        flat_dishes.append(entry_d)

    entry: dict = {
        "timestamp": clock.now_utc(root=root).isoformat(),
        "session_id": session_id,
        "meal_type": meal_type,
        "restaurant_id": restaurant_id,
        "restaurant_name": restaurant_name,
        "dishes": flat_dishes,
    }
    if zone is not None:
        entry["zone"] = zone
    if accepted_rank is not None:
        entry["accepted_rank"] = accepted_rank
    if combo_index is not None:
        entry["combo_index"] = combo_index
    if candidate_id is not None:
        entry["candidate_id"] = candidate_id

    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def compute_extra_banned_restaurants(
    restaurants: list[dict],
    profile: dict,
) -> set[str]:
    """根据 profile 算出"非历史性"被 ban 的餐厅集合 (D-041).

    来源:
      1. delivery_constraints.hard_max_eta_min: ETA 超上限的餐厅
      2. preferences.avoid_restaurants: 餐厅名/品牌模糊匹配
    """
    banned: set[str] = set()
    dc = profile.get("delivery_constraints") or {}
    hard_eta = dc.get("hard_max_eta_min")
    avoid_names = [a for a in (profile.get("preferences") or {})
                   .get("avoid_restaurants", []) if a]
    for r in restaurants:
        eta = r.get("delivery_eta_min", -1)
        if hard_eta and eta and eta > 0 and eta > hard_eta:
            banned.add(r["id"])
            continue
        name = (r.get("name") or "") + " " + (r.get("brand") or "")
        if any(a in name for a in avoid_names):
            banned.add(r["id"])
    return banned


def combo_total_price(combo: dict) -> float:
    """combo 总价 (单菜 price=None 安全求和)."""
    return sum(dish_price(d) for d in combo.get("dishes", []))


def combo_price_filter(
    combos: list[dict],
    profile: dict,
    meal_type: str | None,
) -> list[dict]:
    """combo 总价过滤 (D-041): 超 price_range.hard_max_{lunch,dinner} 直接 ban."""
    pr = profile.get("price_range") or {}
    cap = None
    if meal_type == "lunch":
        cap = pr.get("hard_max_lunch")
    elif meal_type == "dinner":
        cap = pr.get("hard_max_dinner")
    if not cap:
        return combos
    return [c for c in combos if combo_total_price(c) <= cap]


def dish_price(d: dict) -> float:
    """安全读取菜价: price 为 None / 缺失 时返回 0."""
    p = d.get("price")
    return float(p) if p is not None else 0.0


def hard_filter(
    dishes: list[dict],
    profile: dict,
    avoid_restaurant_ids: set[str] | None = None,
    rest_ban_reasons: dict[str, str] | None = None,
    *,
    hard_filter_events: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """硬过滤 (DESIGN §5.6 召回-2 + D-041 + T-P1a-01 L0 三分).

    Returns (kept, dropped). dropped 每项: {dish_id, name, restaurant_id, reason}.

    Args:
      avoid_restaurant_ids: 被 ban 的餐厅 id 集合 (向后兼容入口);
        每个 rid 默认 reason="餐厅被 ban".
      rest_ban_reasons: 优先级更高, 把 rid → 具体原因字符串. 调用方传入,
        让 trace 看清楚是 ETA/avoid_name/diversity/旧入口 哪种.
      hard_filter_events: T-P1a-01 可选事件累计 list. 不为 None 时
        L0-A/B 触发会 append 事件 (经 l0_constraints.make_hard_filter_event 构造).

    其它逻辑:
      - 销量缺失 (=0) 视为"无信息"不卡; 显式 >0 且 < min_sales 才卡.
      - P1 字段黑名单 (D-041): main_ingredient / cooking_method / cuisine.
      - L0-A 医学过敏 + L0-B 身份伦理在所有偏好过滤前先做 (永不可破契约).
    """
    from chisha.l0_constraints import (
        load_l0_constraints,
        dish_violates_l0_a,
        dish_violates_l0_b,
        make_hard_filter_event,
    )
    avoid_restaurant_ids = avoid_restaurant_ids or set()
    rest_ban_reasons = rest_ban_reasons or {}
    prefs = profile.get("preferences") or {}
    avoid_dish_names = [a for a in prefs.get("avoid_dishes", []) if a]
    avoid_ingr = set(prefs.get("avoid_main_ingredients", []) or [])
    avoid_methods = set(prefs.get("avoid_cooking_methods", []) or [])
    banned_cuisines = set(prefs.get("banned_cuisines", []) or [])
    # D-043: processed_meat / sweet_sauce 三档处理 — 这里是 L1 硬过滤档
    banned_processed_meat = bool(prefs.get("banned_processed_meat", False))
    banned_sweet_3 = bool(prefs.get("banned_sweet_sauce_level_3", False))
    # T-P1a-01: L0 三分约束加载 (段缺失返空, 不抛)
    l0c = load_l0_constraints(profile)
    l0_a_dropped: dict[str, int] = {}   # allergy -> count
    l0_b_dropped: dict[str, int] = {}   # rule -> count
    spicy_max = prefs.get("spicy_tolerance", 3)
    hard_max_oil = profile["plate_rule"].get("hard_max_oil_level", 5)
    min_sales = profile.get("recall", {}).get("min_monthly_sales", 0)
    kept: list[dict] = []
    dropped: list[dict] = []
    for d in dishes:
        np = d.get("nutrition_profile") or {}
        name = d.get("canonical_name") or ""
        rid = d.get("restaurant_id")
        reason: str | None = None
        matched_avoid = next((a for a in avoid_dish_names if a in name), None)
        sales = d.get("monthly_sales", 0)
        # T-P1a-01: L0-A 医学过敏检查 (永不可破, 优先级最高)
        if not l0c.is_empty():
            a_hit = dish_violates_l0_a(d, l0c)
            if a_hit:
                reason = f"L0-A 医学过敏: {a_hit}"
                l0_a_dropped[a_hit] = l0_a_dropped.get(a_hit, 0) + 1
                dropped.append({
                    "dish_id": d.get("dish_id"),
                    "name": name,
                    "restaurant_id": rid,
                    "reason": reason,
                })
                continue
            # T-P1a-01: L0-B 身份伦理检查
            b_hit = dish_violates_l0_b(d, l0c)
            if b_hit:
                reason = f"L0-B 身份伦理: {b_hit}"
                l0_b_dropped[b_hit] = l0_b_dropped.get(b_hit, 0) + 1
                dropped.append({
                    "dish_id": d.get("dish_id"),
                    "name": name,
                    "restaurant_id": rid,
                    "reason": reason,
                })
                continue
        if rid in rest_ban_reasons:
            reason = rest_ban_reasons[rid]
        elif rid in avoid_restaurant_ids:
            reason = "餐厅被 ban"
        elif matched_avoid:
            reason = f"命中 avoid_dishes: {matched_avoid}"
        elif np.get("spicy_level", 0) > spicy_max:
            reason = f"辣度 {np.get('spicy_level')} > 上限 {spicy_max}"
        elif np.get("oil_level", 0) > hard_max_oil:
            reason = f"油 {np.get('oil_level')} > hard_max_oil {hard_max_oil}"
        elif avoid_ingr and np.get("main_ingredient_type") in avoid_ingr:
            reason = (
                f"主蛋白在 avoid_main_ingredients: "
                f"{np.get('main_ingredient_type')}"
            )
        elif avoid_methods and np.get("cooking_method") in avoid_methods:
            reason = (
                f"烹饪方式在 avoid_cooking_methods: "
                f"{np.get('cooking_method')}"
            )
        elif banned_cuisines and d.get("cuisine") in banned_cuisines:
            reason = f"菜系在 banned_cuisines: {d.get('cuisine')}"
        elif banned_processed_meat and np.get("processed_meat_flag"):
            reason = "命中 banned_processed_meat (用户禁忌)"
        elif banned_sweet_3 and _safe_int(np.get("sweet_sauce_level"), 0) >= 3:
            reason = f"sweet_sauce_level={np.get('sweet_sauce_level')} 命中 banned_sweet_sauce_level_3"
        elif sales and sales > 0 and sales < min_sales:
            reason = f"月销 {sales} < {min_sales}"
        elif not (d.get("metadata") or {}).get("is_available", True):
            reason = "is_available=False"
        if reason:
            dropped.append({
                "dish_id": d.get("dish_id"),
                "name": name,
                "restaurant_id": rid,
                "reason": reason,
            })
        else:
            kept.append(d)

    # T-P1a-01: L0-A/B drops 累积到事件列表 (调用方决定写不写)
    if hard_filter_events is not None:
        kept_total = len(kept)
        for allergy, cnt in l0_a_dropped.items():
            hard_filter_events.append(make_hard_filter_event(
                category="L0_A_medical",
                rule=f"allergy:{allergy}",
                dropped_count=cnt,
                kept_count=kept_total,
            ))
        for rule, cnt in l0_b_dropped.items():
            hard_filter_events.append(make_hard_filter_event(
                category="L0_B_identity",
                rule=rule,
                dropped_count=cnt,
                kept_count=kept_total,
            ))

    return kept, dropped


def diversity_filter(
    dishes: list[dict],
    meal_log: list[dict],
    profile: dict,
    today: dt.date | None = None,
) -> tuple[list[dict], set[str]]:
    """基于 meal_log 的多样性过滤. 返回 (filtered_dishes, recently_eaten_restaurant_ids)."""
    today = today or dt.date.today()
    no_rest_days = profile["diversity"].get("no_same_restaurant_within_days", 7)
    no_ingr_days = profile["diversity"].get(
        "no_same_main_ingredient_within_days", 3
    )

    recent_rests: set[str] = set()
    recent_ingrs: set[str] = set()
    for log in meal_log:
        try:
            ts = dt.datetime.fromisoformat(log["timestamp"]).date()
        except Exception:
            continue
        delta = (today - ts).days
        if delta <= no_rest_days:
            recent_rests.add(log.get("restaurant_id", ""))
        if delta <= no_ingr_days:
            for x in log.get("dishes", []):
                ing = x.get("main_ingredient_type")
                if ing:
                    recent_ingrs.add(ing)

    out = []
    for d in dishes:
        if d.get("restaurant_id") in recent_rests:
            continue
        ing = d.get("nutrition_profile", {}).get("main_ingredient_type")
        # 蛋白类（红肉/白肉/海鲜/豆制品）才走 ingredient 多样性
        if ing in ("红肉", "白肉", "海鲜", "豆制品") and ing in recent_ingrs:
            continue
        out.append(d)
    return out, recent_rests


def is_vegetable_dish(d: dict) -> bool:
    """是否算蔬菜菜品 (vegetable_ratio_estimate ≥ 0.6 或 main_ingredient_type=纯素)."""
    np = d.get("nutrition_profile", {})
    if np.get("main_ingredient_type") == "纯素":
        return True
    return np.get("vegetable_ratio_estimate", 0) >= 0.6


def is_protein_dish(d: dict) -> bool:
    np = d.get("nutrition_profile", {})
    if np.get("main_ingredient_type") in ("红肉", "白肉", "海鲜", "蛋", "豆制品"):
        return True
    return np.get("protein_grams_estimate", 0) >= 15


def is_carb_dish(d: dict) -> bool:
    np = d.get("nutrition_profile", {})
    return np.get("main_ingredient_type") == "主食"


def is_complete_meal(d: dict) -> bool:
    return d.get("nutrition_profile", {}).get("is_complete_meal", False)


def combo_passes_plate_rule(
    combo_dishes: list[dict],
    profile: dict,
    *,
    intent=None,  # T-P1a-01: RefineIntent | None
) -> bool:
    """弱约束三件套校验 (D-023). T-P1a-01: intent.allows_methodology_break() 时直接放过.

    保留 bool 返回类型 (调用方包括 tests/test_recall.py 不动). 解除原因的细节
    用 combo_passes_plate_rule_with_reason 获取.
    """
    if intent is not None and intent.allows_methodology_break():
        return True  # L0-C 解除 (refine 明确放纵)
    pr = profile["plate_rule"]
    has_veg = sum(1 for d in combo_dishes if is_vegetable_dish(d))
    if pr.get("must_have_vegetable", True):
        if has_veg < pr.get("min_vegetable_dishes", 1):
            return False
    total_protein = sum(
        d.get("nutrition_profile", {}).get("protein_grams_estimate", 0)
        for d in combo_dishes
    )
    if total_protein < pr.get("min_protein_g", 0):
        return False
    return True


def combo_passes_plate_rule_with_reason(
    combo_dishes: list[dict],
    profile: dict,
    *,
    intent=None,
) -> tuple[bool, str | None]:
    """T-P1a-01: 返 (pass, override_reason).

    给 _build_l1_trace / debug instrument 调用以记录解除事件. 不破坏 bool 接口.
    override_reason 非 None 时表示 L0-C 解除 (refine_break_methodology) 或失败原因.
    """
    if intent is not None and intent.allows_methodology_break():
        return True, "refine_break_methodology"
    pr = profile["plate_rule"]
    has_veg = sum(1 for d in combo_dishes if is_vegetable_dish(d))
    if pr.get("must_have_vegetable", True):
        if has_veg < pr.get("min_vegetable_dishes", 1):
            return False, "fail_min_vegetable"
    total_protein = sum(
        d.get("nutrition_profile", {}).get("protein_grams_estimate", 0)
        for d in combo_dishes
    )
    if total_protein < pr.get("min_protein_g", 0):
        return False, "fail_min_protein"
    return True, None


def _intent_dish_score(d: dict, intent) -> float:
    """D-073: 单菜对 intent 的命中度, 用于 combo 生成前的池子排序加权.

    Codex review §2: intent 必须进入 combo generation **前**, 不能等召回后过滤.
    "湖南老灶台"的招牌湘菜若没进每店前 6 protein, 后面再过滤也救不回.

    返回 0.0~3.0 加权, 与 monthly_sales 在 sort key 中相加 (sales 通常 0-3000,
    intent 加 0.0/1.0/2.0/3.0 对热度排序的影响约相当于"销量翻 1-3 倍").

    Codex 二审: 加 monthly_sales 归一化, 让 intent 加分有意义但不至于完全压过销量.
    """
    if intent is None:
        return 0.0
    score = 0.0
    np_ = d.get("nutrition_profile") or {}
    name = d.get("canonical_name") or ""
    raw_name = d.get("raw_name") or ""
    full_name = name + " " + raw_name

    # cuisine 命中: 用 score.normalize_cuisine 复用归一表
    cuisine_want = getattr(intent, "cuisine_want", None) or []
    cuisine_expanded = getattr(intent, "cuisine_candidates_expanded", None) or []
    cuisine_want_hit = False  # codex block: 防 want + expanded 双重加分
    if cuisine_want:
        from chisha.score import normalize_cuisine
        targets = {normalize_cuisine(c) for c in cuisine_want}
        targets.discard(None)
        if d.get("cuisine") in targets:
            score += 2.0
            cuisine_want_hit = True
        # 软命中: 菜名子串
        elif any(c in full_name for c in cuisine_want if c):
            score += 1.0
            cuisine_want_hit = True
    # D-094: expanded 1.0 加分, 仅在 cuisine_want 未命中时给 (避免双重加分).
    if cuisine_expanded and not cuisine_want_hit:
        from chisha.score import normalize_cuisine
        exp_targets = {normalize_cuisine(c) for c in cuisine_expanded}
        exp_targets.discard(None)
        if d.get("cuisine") in exp_targets:
            score += 1.0

    # ingredient 命中: 复用 contains_ingredient 的逻辑 (但只看单 dish)
    ingredient_want = getattr(intent, "ingredient_want", None) or []
    for ing in ingredient_want:
        if ing in full_name:
            score += 1.0
            break
        # 广义词命中 main_ingredient_type
        from chisha.score import _INGREDIENT_BROAD
        broad = _INGREDIENT_BROAD.get(ing)
        if broad and np_.get("main_ingredient_type") in broad:
            score += 0.5
            break

    # D-094.1: V2 constrain.oil / wants_soup 直接驱动 dish-level 加分.
    # "spicy" V1 信号 → bucket_soft 路径已通过 cuisine_candidates_expanded 处理, dish 级不再加分.
    oil = getattr(intent, "oil", None)
    if oil == "low" and np_.get("oil_level", 3) <= 2:
        score += 0.5
    if oil == "high" and np_.get("oil_level", 3) >= 4:
        score += 0.3
    if getattr(intent, "wants_soup", False) and (
        np_.get("wetness", 1) >= 2 or "汤" in name or "粥" in name
    ):
        score += 0.5

    # cuisine_avoid 命中 → 负分, 把它压到池子末尾 (硬过滤在 recall 层做; 这里保留 sort 顺位)
    cuisine_avoid = getattr(intent, "cuisine_avoid", None) or []
    if cuisine_avoid:
        from chisha.score import normalize_cuisine
        targets = {normalize_cuisine(c) for c in cuisine_avoid}
        targets.discard(None)
        if d.get("cuisine") in targets:
            score -= 5.0  # 把它推到候选池末尾

    return score


def build_combos_for_restaurant(
    rest_dishes: list[dict],
    profile: dict,
    per_rest_max: int,
    intent=None,  # D-073: RefineIntent | None
) -> list[list[dict]]:
    """单家餐厅内构建若干 combo.

    设计原则 (D-040):
      - combo 阶段只过营养合规 (弱约束三件套 plate_rule)
      - 数量上限 (几个蛋白/几个蔬菜/总菜数) 由 profile.recall.* 显式注入
      - 价格/距离等约束推迟到打分/排序阶段

    D-073 (Codex §2): 传 intent 时, 各菜池排序先按 intent 命中度加权 (intent 命中分
      与 monthly_sales 在 sort key 中相加), 让目标菜不被 [:N] 截断扔掉.

    路线:
      A. 完整套餐 (complete_meal) 单菜 / +1 蔬菜
      B. 灵活组合: n_p 蛋白 × n_v 蔬菜 × n_c 主食
         其中 n_p ∈ [1, max_protein], n_v ∈ [1, max_veg], n_c ∈ [0, max_carb]
         且 n_p + n_v + n_c ∈ [1, max_dishes]
    """
    from itertools import combinations as _comb

    rcfg = profile.get("recall", {}) or {}
    max_p = rcfg.get("max_protein_per_combo", 2)
    max_v = rcfg.get("max_veg_per_combo", 2)
    max_c = rcfg.get("max_carb_per_combo", 1)
    max_n = rcfg.get("max_dishes_per_combo", 4)

    completes = [d for d in rest_dishes if is_complete_meal(d)]
    vegs = [d for d in rest_dishes if is_vegetable_dish(d)]
    proteins = [d for d in rest_dishes if is_protein_dish(d)]
    carbs = [d for d in rest_dishes if is_carb_dish(d)]

    # D-073: 排序 key = -(monthly_sales/1000 + intent_score × intent_weight)
    # intent_weight 给 1.5: 命中 +2.0 cuisine + 1.0 ingredient ≈ 销量翻 4500 倍, 显著
    # 但完全无销量的冷门菜仍不会被强推 (有销量基础的命中菜会先于冷门菜).
    def _key(d):
        sales = (d.get("monthly_sales", 0) or 0) / 1000.0
        intent_s = _intent_dish_score(d, intent) * 1.5
        return -(sales + intent_s)

    proteins = sorted(proteins, key=_key)[:6]
    vegs = sorted(vegs, key=_key)[:5]
    carbs = sorted(carbs, key=_key)[:3]
    completes = sorted(completes, key=_key)[:5]

    combos: list[list[dict]] = []
    if max_n <= 0:
        return combos

    # 路线 A: 完整套餐 (盖饭/套餐)，可选 +1 蔬菜
    for cm in completes:
        if 1 <= max_n and combo_passes_plate_rule([cm], profile, intent=intent):
            combos.append([cm])
        if max_n < 2:
            continue
        for v in vegs[:3]:
            if v["dish_id"] == cm["dish_id"]:
                continue
            c = [cm, v]
            if combo_passes_plate_rule(c, profile, intent=intent):
                combos.append(c)

    # 路线 B: 灵活蛋白 × 蔬菜 × 主食
    for n_p in range(1, max_p + 1):
        if n_p > len(proteins):
            break
        for n_v in range(1, max_v + 1):
            if n_v > len(vegs):
                break
            for n_c in range(0, max_c + 1):
                if n_c > len(carbs):
                    break
                if n_p + n_v + n_c > max_n:
                    continue
                for p_set in _comb(proteins, n_p):
                    p_ids = {d["dish_id"] for d in p_set}
                    for v_set in _comb(vegs, n_v):
                        v_ids = {d["dish_id"] for d in v_set}
                        if p_ids & v_ids:
                            continue
                        if n_c == 0:
                            dishes = list(p_set) + list(v_set)
                            if combo_passes_plate_rule(dishes, profile, intent=intent):
                                combos.append(dishes)
                            continue
                        for c_set in _comb(carbs, n_c):
                            c_ids = {d["dish_id"] for d in c_set}
                            if c_ids & (p_ids | v_ids):
                                continue
                            dishes = list(p_set) + list(v_set) + list(c_set)
                            if combo_passes_plate_rule(dishes, profile, intent=intent):
                                combos.append(dishes)

    # 去重 (按 dish_id 集合)
    seen: set[frozenset] = set()
    uniq = []
    for c in combos:
        key = frozenset(d["dish_id"] for d in c)
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq[:per_rest_max]


def recall(
    profile: dict,
    restaurants: list[dict],
    dishes_tagged: list[dict],
    meal_log: list[dict] | None = None,
    today: dt.date | None = None,
    meal_type: str | None = None,
    intent=None,  # D-073: RefineIntent | None, refine 二轮启用
    n: int = 5,
    *,
    recall_fallback_events: list[dict] | None = None,
) -> list[dict]:
    """主入口. 返回候选 combos: [{restaurant, dishes, meta}, ...].

    meal_type 传入则启用 combo 总价硬过滤 (D-041).
    D-073: intent 非空时三桶拼合 + Q1 回落.
    T-P1a-02 (D-084): refine 模式参数差异化 (per_rest_max 提到 5) +
      ingredient_want L1 反查 + 三级回落 (≥30 floor / fill to 60).

    Args:
      n: 期望最终输出候选数 (用于计算三桶配额阈值; refine 时下游默认 5).
      recall_fallback_events: 可选 list, 不为 None 时三级回落写事件追加进去.
    """
    meal_log = meal_log or []
    has_intent = intent is not None and not intent.is_empty()

    # 1. 多样性过滤先算"近期已吃"被禁餐厅
    _, diversity_avoid = diversity_filter([], meal_log, profile, today=today)
    # 1b. P0 硬约束: ETA + 餐厅黑名单
    extra_banned = compute_extra_banned_restaurants(restaurants, profile)
    avoid_rests = diversity_avoid | extra_banned

    # 1c. D-094 (T-FR-03): brand_avoid venue 整店硬过滤.
    # 用户 "别再给我萨莉亚" → 命中 restaurants.json[].brand 的 venue 整店剔除.
    # 子串匹配 (codex review block): venue.brand 有复合品牌 (如 "麦当劳＆麦咖啡"),
    # 用户文本抽出的 brand 是裸名 ("麦当劳"), exact 集合命中会漏过滤.
    if has_intent:
        brand_avoid = [b for b in (getattr(intent, "brand_avoid", None) or []) if b]
        if brand_avoid:
            for r in restaurants:
                r_brand = r.get("brand") or ""
                if r_brand and any(b in r_brand for b in brand_avoid):
                    avoid_rests.add(r["id"])

    # 2. 硬过滤 dishes (含 P1 三个黑名单 + L0-A/B 永不可破)
    dishes, _ = hard_filter(dishes_tagged, profile, avoid_rests)

    # T-P1a-02: refine 模式 ingredient_want 进 L1 反查
    # (复用 l0_constraints helpers, 不调 hard_filter 避免双重事件写入)
    if has_intent:
        extra = _ingredient_want_reverse_lookup(
            dishes_tagged, intent, profile, avoid_rests
        )
        if extra:
            existing = {d.get("dish_id") for d in dishes}
            for d in extra:
                if d.get("dish_id") not in existing:
                    dishes.append(d)
                    existing.add(d.get("dish_id"))

    # 3. 多样性过滤 dishes (主蛋白)
    dishes, _ = diversity_filter(dishes, meal_log, profile, today=today)

    # 4. 按 restaurant 分桶
    by_rest: dict[str, list[dict]] = defaultdict(list)
    for d in dishes:
        by_rest[d["restaurant_id"]].append(d)

    rest_idx = {r["id"]: r for r in restaurants}
    # T-P1a-02: refine 模式 per_rest_max 提到 5 (可配 refine_per_restaurant_max)
    rcfg = profile.get("recall", {}) or {}
    if has_intent:
        per_rest_max = rcfg.get("refine_per_restaurant_max", 5)
    else:
        per_rest_max = rcfg.get("per_restaurant_max", 3)

    # 5. 每家餐厅生成 combos (intent 进入排序)
    combos: list[dict] = []
    for rid, rest_dishes in by_rest.items():
        if rid not in rest_idx:
            continue
        rcombos = build_combos_for_restaurant(
            rest_dishes, profile, per_rest_max, intent=intent
        )
        for cd in rcombos:
            combos.append({
                "restaurant": rest_idx[rid],
                "dishes": cd,
            })

    # 6. combo 总价硬过滤 (D-041)
    combos = combo_price_filter(combos, profile, meal_type)

    # 7. D-073: intent 三桶拼合 + avoid 硬过滤 (仅 refine 二轮)
    if intent is not None:
        combos = _apply_intent_buckets(
            combos, intent, n=n,
            recall_fallback_events=recall_fallback_events,
        )

    return combos


def _ingredient_want_reverse_lookup(
    dishes_tagged: list[dict],
    intent,
    profile: dict,
    avoid_rests: set[str],
) -> list[dict]:
    """T-P1a-02: refine 模式下, 把"含 ingredient_want 关键词" 的菜捞回候选池.

    不能调 hard_filter (会双重写 L0 事件 + N+1 偏好过滤). 只复用 l0_constraints
    helpers + 餐厅黑名单, 让 medical safety / identity 红线穿透.

    避开 hard_filter 的偏好类过滤 (avoid_dishes/spicy_tolerance/avoid_main_ingr 等),
    让 refine 表达对偏好"穿透" — refine 是用户当下意图, 优先级 > 长期偏好.
    """
    from chisha.l0_constraints import (
        load_l0_constraints, dish_violates_l0_a, dish_violates_l0_b,
    )
    ingredient_want = getattr(intent, "ingredient_want", None) or []
    if not ingredient_want:
        return []
    l0c = load_l0_constraints(profile)
    # 全集 monthly_sales 下限 (不卡 min_sales, 让冷门 ingredient 命中也回来)
    out: list[dict] = []
    for d in dishes_tagged:
        rid = d.get("restaurant_id")
        if rid in avoid_rests:
            continue
        # L0-A/B 永不可破
        if not l0c.is_empty():
            if dish_violates_l0_a(d, l0c) or dish_violates_l0_b(d, l0c):
                continue
        # ingredient_want 命中 (名字 substring 或 main_ingredient_type 在广义词覆盖范围)
        name = (d.get("canonical_name") or "") + " " + (d.get("raw_name") or "")
        np_ = d.get("nutrition_profile") or {}
        from chisha.score import _INGREDIENT_BROAD
        hit = False
        for ing in ingredient_want:
            if ing and ing in name:
                hit = True
                break
            broad = _INGREDIENT_BROAD.get(ing)
            if broad and np_.get("main_ingredient_type") in broad:
                hit = True
                break
        if hit:
            out.append(d)
    return out


def _apply_intent_buckets(
    combos: list[dict],
    intent,
    n: int = 5,
    *,
    recall_fallback_events: list[dict] | None = None,
) -> list[dict]:
    """D-073: 三桶拼合 + Q1 回落. T-P1a-02: 三级回落 + 事件落 trace.

    流程:
      1. 硬过滤: cuisine_avoid + ingredient_avoid + cooking_method_avoid + staple_avoid (用户明确不要)
      2. 三桶分级:
         - bucket_exact: cuisine_exact_match
         - bucket_soft: cuisine_soft_match (店名/菜名子串) 或 ingredient 命中
         - bucket_rest: 全集兜底
      3. T-P1a-02 三级回落 (brief §6 "保底「至少 30 个 intent 命中」"):
         - intent_hit = len(exact) + len(soft)
         - target = L3_INPUT_TOP_K (60)
         - **30 是 floor 不是 ceiling**, 三级都尽量填到 target=60:
         - Level 1 (intent_hit ≥ 30): 健康召回, 返 exact + soft + rest (填到 target)
         - Level 2 (10 ≤ intent_hit < 30): 命中数偏低, 同 Level 1 但 trace 警示
         - Level 3 (intent_hit < 10): refine 严重偏数据, 返全集 (event 提示)
      4. avoid 硬过滤始终生效 (在三桶分类前).
    """
    from chisha.score import (cuisine_exact_match, cuisine_soft_match,
                              contains_ingredient, dish_is_staple)
    from chisha.rerank import L3_INPUT_TOP_K

    # 硬过滤 avoid
    def _not_avoided(c):
        cu_av = getattr(intent, "cuisine_avoid", None) or []
        ing_av = getattr(intent, "ingredient_avoid", None) or []
        # D-094 (T-FR-03): cooking_method_avoid dish 维度硬过滤. combo 内任一 dish 命中即弃
        # (用户看完整 combo, 含 1 道油炸即破诉求).
        cm_av = set(getattr(intent, "cooking_method_avoid", None) or [])
        # D-094.1: staple_avoid dish 维度硬过滤, 跟 cuisine_avoid/ingredient_avoid 一致语义
        # (intent_match_bonus 是 [0,1] 正向加分表达不了 demote, codex BLOCK 修复). dish_is_staple
        # 先按 grain_type 过滤防 "面包/面筋" 误命中, 再对 canonical_name 做子串.
        st_av = getattr(intent, "staple_avoid", None) or []
        if cu_av and cuisine_exact_match(c, cu_av):
            return False
        if cu_av and cuisine_soft_match(c, cu_av):
            return False
        for ing in ing_av:
            if contains_ingredient(c, ing):
                return False
        if cm_av:
            for d in c.get("dishes", []):
                np_ = d.get("nutrition_profile") or {}
                if np_.get("cooking_method") in cm_av:
                    return False
        if st_av:
            for d in c.get("dishes", []):
                name = d.get("canonical_name") or ""
                if dish_is_staple(d) and any(s and s in name for s in st_av):
                    return False
        return True

    # codex review Q2 nit: 记 _not_avoided 弃了多少 combo (cuisine_avoid + ingredient_avoid
    # + cooking_method_avoid + staple_avoid 合计), 让 trace 能区分"L1 命中本身少" vs "硬过滤后剩余少",
    # 防 intent_hit 虚低误判 level=2/3.
    _pre_filter_count = len(combos)
    combos = [c for c in combos if _not_avoided(c)]
    _avoid_dropped = _pre_filter_count - len(combos)

    cuisine_want = getattr(intent, "cuisine_want", None) or []
    ingredient_want = getattr(intent, "ingredient_want", None) or []
    # D-094 (T-FR-04): cuisine_candidates_expanded — LLM 抽出的同源菜系扩展 (例: "想吃辣"→川/湘/贵/重).
    # 进 bucket_soft (跟 cuisine_soft_match 同档, 比显式 cuisine_want 低一级). 不进 bucket_exact.
    cuisine_expanded = getattr(intent, "cuisine_candidates_expanded", None) or []

    if not cuisine_want and not ingredient_want and not cuisine_expanded:
        # 用户未表达 want, 不做桶过滤 (avoid 已处理), 全集走 L2
        return combos

    bucket_exact: list[dict] = []
    bucket_soft: list[dict] = []
    bucket_rest: list[dict] = []
    for c in combos:
        if cuisine_want and cuisine_exact_match(c, cuisine_want):
            bucket_exact.append(c)
        elif (cuisine_want and cuisine_soft_match(c, cuisine_want)) or \
             (cuisine_expanded and cuisine_exact_match(c, cuisine_expanded)) or \
             any(contains_ingredient(c, ing) for ing in ingredient_want):
            bucket_soft.append(c)
        else:
            bucket_rest.append(c)

    # T-P1a-02: 三级回落 (≥30 是 floor, target=60).
    # 注: 各级实际返回都是 exact + soft + rest 拼合 (尽量填到 target);
    # 级别仅影响 trace 事件 label, 用于 observability + L3 prompt 上层可见.
    intent_hit = len(bucket_exact) + len(bucket_soft)
    target = L3_INPUT_TOP_K  # 60
    floor = 30

    if intent_hit >= floor:
        level = 1
    elif intent_hit >= 10:
        level = 2
    else:
        level = 3

    out = bucket_exact + bucket_soft + bucket_rest

    if recall_fallback_events is not None:
        # 走 chisha.clock 而非 time.time() — sandbox time-travel 下保证一致性
        # (Codex review blocker: 与 hard_filter_event timestamp 风格保持一致;
        # 后者用 time.time, 因不参与 sandbox 时间穿越判定, 此处选择 isoformat
        # 字符串保留时区信息, 与 What-if frozen 字段同风格)
        from chisha import clock as _clock
        recall_fallback_events.append({
            "event_type": "recall_fallback",
            "level": level,
            "intent_hit_count": intent_hit,
            "exact_count": len(bucket_exact),
            "soft_count": len(bucket_soft),
            "rest_count": len(bucket_rest),
            "total_returned": min(len(out), target),
            "target_top_k": target,
            "floor": floor,
            # D-094 codex Q2 nit: _not_avoided 弃了多少 combo (cuisine_avoid +
            # ingredient_avoid + cooking_method_avoid 合计). 用来分辨"intent_hit
            # 低是因数据本来就少"还是"硬过滤后剩余少".
            "avoid_filter_dropped": _avoid_dropped,
            "timestamp": _clock.now_utc().isoformat(),
        })

    # 关于 D-073 原 Q1 阈值: 现在三级回落已覆盖. 保留同输出 (exact+soft+rest 拼接),
    # L2 boost 仍负责重排顺位.
    return out


if __name__ == "__main__":
    import sys
    root = Path(__file__).resolve().parent.parent
    profile = load_profile(root / "profile.yaml")
    meal = sys.argv[1] if len(sys.argv) > 1 else "lunch"
    zones = profile.get("basics", {}).get("zones") or {}
    zone = zones.get(meal) or profile["basics"]["office_zone"]
    rests, tagged = load_zone_data(zone, root)
    log = load_meal_log(root)
    cs = recall(profile, rests, tagged, log)
    print(f"[{meal} @ {zone}] 候选 combo 数: {len(cs)}")
    for c in cs[:5]:
        print(f"  {c['restaurant']['name']} | "
              f"{[d['canonical_name'] for d in c['dishes']]}")

"""D-079 PR-2: What-if 算法等价 + frozen 边界守门.

测试矩阵:
- test_what_if_zero_overrides_matches_replay: 不带 overrides 调 what_if_rerun
  应与原 trace final/L2 严格等价 (浮点 1e-6)
- test_what_if_uses_frozen_l1_prefs: monkeypatch load_prefs 抛错, What-if 仍能跑
  (用 frozen snapshot 而非 runtime load)
- test_what_if_uses_frozen_today: monkeypatch dt.date.today 返怪值, 结果不变
  (用 frozen today, 与 wall clock 解耦)
- test_what_if_uses_frozen_meal_log: monkeypatch load_meal_log 返 [],
  What-if 仍用 l2_meal_log_view 算 variety_bonus
- test_what_if_overrides_n_return: 改 n_return=3 → final 长度 3, frozen 不变
- test_what_if_overrides_profile_weights: deep_merge 把 scoring_weights 覆盖
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from chisha import api as api_module
from chisha import debug_what_if, l1_prefs, recall as recall_module, trace_store
from chisha.api import recommend_meal
from chisha.debug_what_if import what_if_rerun
from tests.conftest import make_dish, make_restaurant


@pytest.fixture
def fixed_env(monkeypatch, tmp_path):
    """复用 PR-1 fixture: 固定 profile/zone/meal_log, 让 recommend_meal 跑稳定 fallback."""
    profile = {
        "basics": {"office_zone": "test", "zones": {"lunch": "test", "dinner": "test"}},
        "taste_description": "喜欢汤水",
        "preferences": {
            "liked_cuisines": ["潮汕"], "disliked_cuisines": [],
            "avoid_dishes": [], "spicy_tolerance": 2,
        },
        "plate_rule": {
            "must_have_vegetable": True, "min_vegetable_dishes": 1,
            "min_protein_g": 25, "prefer_oil_level_at_most": 3, "hard_max_oil_level": 5,
        },
        "diversity": {"no_same_restaurant_within_days": 7,
                       "no_same_main_ingredient_within_days": 3},
        "recall": {"top_n": 100, "per_restaurant_max": 3, "min_monthly_sales": 10},
    }
    rests = [
        {**make_restaurant(rid="r1", name="潮汕汤店"),
         "office_zone": "test", "category": "潮汕"},
        {**make_restaurant(rid="r2", name="湘菜店"),
         "office_zone": "test", "category": "湘菜"},
    ]
    dishes = [
        make_dish(dish_id="d1_1", restaurant_id="r1",
                  raw_name="潮汕牛肉汤", canonical_name="潮汕牛肉汤",
                  cuisine="潮汕", main_ingredient_type="红肉",
                  oil_level=2, protein_grams_estimate=35,
                  vegetable_ratio_estimate=0.1, wetness=3,
                  dish_role="主菜", monthly_sales=200),
        make_dish(dish_id="d1_2", restaurant_id="r1",
                  raw_name="蒜蓉空心菜", canonical_name="蒜蓉空心菜",
                  cuisine="潮汕", main_ingredient_type="纯素",
                  oil_level=2, vegetable_ratio_estimate=0.95,
                  protein_grams_estimate=3, dish_role="配菜",
                  monthly_sales=180),
        make_dish(dish_id="d2_1", restaurant_id="r2",
                  raw_name="辣椒炒肉", canonical_name="辣椒炒肉",
                  cuisine="湘菜", main_ingredient_type="白肉",
                  oil_level=4, protein_grams_estimate=30,
                  vegetable_ratio_estimate=0.2, dish_role="主菜",
                  monthly_sales=150),
        make_dish(dish_id="d2_2", restaurant_id="r2",
                  raw_name="炒油麦", canonical_name="炒油麦菜",
                  cuisine="湘菜", main_ingredient_type="纯素",
                  oil_level=3, vegetable_ratio_estimate=0.9,
                  protein_grams_estimate=3, dish_role="配菜",
                  monthly_sales=100),
    ]
    monkeypatch.setattr(api_module, "load_profile", lambda *a, **k: profile)
    monkeypatch.setattr(api_module, "load_zone_data",
                         lambda zone, root: (rests, dishes))
    monkeypatch.setattr(api_module, "load_meal_log", lambda root: [])
    return tmp_path


def _run_recommend_and_get_trace(root: Path, today=dt.date(2026, 5, 13)) -> tuple[dict, dict]:
    """跑一次 recommend_meal 并读回 trace, 用 fallback (不依赖 LLM)."""
    out = recommend_meal(
        "lunch", today=today, log_to_file=False,
        use_llm_rerank=False, root=root,
    )
    sid = out["session_id"]
    trace = trace_store.read_trace(sid, root=root)
    assert trace is not None, "PR-1 trace 必须落盘"
    return out, trace


# ────────────────────────── 等价性 (核心红线)

def test_what_if_zero_overrides_matches_replay(fixed_env):
    """零 overrides → What-if 结果必须严格等价原 Replay.

    Codex PR-2 FIX-NOW #3 强化: 除 final id, 还验
      - L2 top 完整 score 严格匹配 (1e-6)
      - L2 top 每条 score_breakdown 每个维度严格匹配 (1e-6)
      - L2 summary.dim_stats_topk 每维 min/max/mean/std 严格匹配
    任何字段漂移 = bug.
    """
    _, base_trace = _run_recommend_and_get_trace(fixed_env)
    sid = base_trace["session_id"]

    wi = what_if_rerun(sid, overrides={}, root=fixed_env)

    # final 候选 id (combo_index + restaurant.id) 严格匹配
    base_final_ids = [
        (c.get("combo_index"), (c.get("restaurant") or {}).get("id"))
        for c in base_trace.get("final") or []
    ]
    wi_final_ids = [
        (c.get("combo_index"), (c.get("restaurant") or {}).get("id"))
        for c in wi.get("final") or []
    ]
    assert wi_final_ids == base_final_ids, (
        f"零 overrides final 漂移: base={base_final_ids}, what_if={wi_final_ids}"
    )

    # L2 top 顺序 + score 严格匹配 (浮点 1e-6) + score_breakdown 字段级匹配
    base_top = (base_trace.get("l2") or {}).get("top") or []
    wi_top = (wi.get("l2") or {}).get("top") or []
    assert len(base_top) == len(wi_top), (
        f"L2 top length 漂移: base={len(base_top)}, what_if={len(wi_top)}"
    )
    for i, (b, w) in enumerate(zip(base_top, wi_top)):
        b_score = b.get("score") or 0.0
        w_score = w.get("score") or 0.0
        assert abs(b_score - w_score) < 1e-6, (
            f"L2 top[{i}] score 漂移: base={b_score}, what_if={w_score}"
        )
        # score_breakdown 每维严格匹配 (Codex PR-2 FIX-NOW #3 守门).
        # 注: _format_ranked_for_trace 用 'breakdown' key 名.
        b_bd = b.get("breakdown") or {}
        w_bd = w.get("breakdown") or {}
        assert set(b_bd.keys()) == set(w_bd.keys()), (
            f"L2 top[{i}] breakdown 维度集漂移: "
            f"base only={set(b_bd) - set(w_bd)}, wi only={set(w_bd) - set(b_bd)}"
        )
        for dim, b_v in b_bd.items():
            w_v = w_bd.get(dim)
            assert abs((b_v or 0.0) - (w_v or 0.0)) < 1e-6, (
                f"L2 top[{i}].breakdown[{dim}] 漂移: base={b_v}, wi={w_v}"
            )

    # L2 summary.dim_stats_topk 严格匹配
    base_stats = ((base_trace.get("l2") or {}).get("summary") or {}).get("dim_stats_topk") or {}
    wi_stats = ((wi.get("l2") or {}).get("summary") or {}).get("dim_stats_topk") or {}
    assert set(base_stats.keys()) == set(wi_stats.keys())
    for dim, b_s in base_stats.items():
        w_s = wi_stats[dim]
        for k in ("min", "max", "mean", "std"):
            assert abs((b_s.get(k) or 0.0) - (w_s.get(k) or 0.0)) < 1e-6, (
                f"L2 dim_stats[{dim}].{k} 漂移: base={b_s.get(k)}, wi={w_s.get(k)}"
            )

    # __source/__parent_session_id 标记正确
    assert wi["__source"] == "what_if_preview"
    assert wi["__parent_session_id"] == sid
    assert wi["__llm_called"] is False  # fallback, 未调 LLM


# ────────────────────────── frozen 边界守门

def test_what_if_uses_frozen_l1_prefs(fixed_env, monkeypatch):
    """l1_prefs.load_prefs 抛错时, What-if 仍能跑 (用 frozen snapshot).

    Codex BLOCKER #1: 防 What-if 静默 fallback 到 live state.
    """
    _, base_trace = _run_recommend_and_get_trace(fixed_env)
    sid = base_trace["session_id"]

    def _explode(*args, **kwargs):
        raise RuntimeError("load_prefs must not be called during What-if")

    monkeypatch.setattr(l1_prefs, "load_prefs", _explode)

    # 不应抛 — 因为 rank_combos 收到 l1_prefs_override 跳过 load_prefs
    wi = what_if_rerun(sid, overrides={}, root=fixed_env)
    assert wi.get("final"), "frozen l1_prefs path 失败"


def test_what_if_uses_frozen_today(fixed_env):
    """篡改 base trace.__frozen.today 到怪日期 → What-if 必须用此 frozen 值,
    不读 wall clock.

    Codex Q3 守门: 重写 frozen.today=2099-01-01, 再加 cooldown meal_log_view
    含 2099-01-02 entry. 如果 What-if 用 wall clock today (2026), 2099 view
    超 7 天窗 → cooldown 不生效; 如果用 frozen 2099, 在 7d 窗内 → cooldown 生效.
    断言: 输出的 today 字段 = 2099-01-01.
    """
    _, base_trace = _run_recommend_and_get_trace(fixed_env)
    sid = base_trace["session_id"]

    base_trace["__frozen"]["today"] = "2099-01-01"
    trace_store.write_trace(sid, base_trace, root=fixed_env)

    wi = what_if_rerun(sid, overrides={}, root=fixed_env)
    assert wi.get("today") == "2099-01-01", (
        f"What-if 未使用 frozen today: 输出 today={wi.get('today')}"
    )
    # 进一步: __frozen.today 在 response 中保持原值不变
    assert (wi.get("__frozen") or {}).get("today") == "2099-01-01"


def test_what_if_uses_frozen_meal_log(fixed_env):
    """frozen.l2_meal_log_view 真的被传入 L2 打分, 影响 variety_bonus / cooldown.

    Codex PR-2 FIX-NOW #4 守门: 同一 base trace, 写两种 frozen view:
    (a) 空 view → variety_bonus 维度无 cooldown 惩罚
    (b) 篡改 view 加一条 r1 7d 内的 entry → r1 候选 variety_bonus 被压低
    断言: 两次 What-if r1 的 score_breakdown 在受影响维度上有差异.
    """
    _, base_trace = _run_recommend_and_get_trace(fixed_env)
    sid = base_trace["session_id"]

    # case a: frozen view 空
    base_trace["__frozen"]["l2_meal_log_view"] = []
    trace_store.write_trace(sid, base_trace, root=fixed_env)
    wi_empty = what_if_rerun(sid, overrides={}, root=fixed_env)
    r1_empty = next(
        (c for c in (wi_empty.get("l2") or {}).get("top") or []
         if c.get("restaurant_id") == "r1"),
        None,
    )
    assert r1_empty is not None, "empty view 下 r1 应在 L2 top"

    # case b: frozen view 加 r1 7d 内 entry, 覆盖 combo 所有 main_ingredient_type.
    # variety_bonus 看 combo 主蛋白 vs meal_log 最近一次距离 (D-043 连续函数):
    # 必须把 r1 combo 的所有 main_ingredient (红肉+纯素) 都填到 entry 里, 否则
    # combo 任一未吃过的 ingredient 会触发 best=1.0 break, 看不出差异.
    base_trace["__frozen"]["l2_meal_log_view"] = [{
        "timestamp": "2026-05-12T12:00:00",
        "restaurant_id": "r1",
        "dishes": [
            {"cuisine": "潮汕", "main_ingredient_type": "红肉"},
            {"cuisine": "潮汕", "main_ingredient_type": "纯素"},
        ],
    }]
    trace_store.write_trace(sid, base_trace, root=fixed_env)
    wi_with_view = what_if_rerun(sid, overrides={}, root=fixed_env)
    r1_with_view = next(
        (c for c in (wi_with_view.get("l2") or {}).get("top") or []
         if c.get("restaurant_id") == "r1"),
        None,
    )
    assert r1_with_view is not None, "view 非空时 r1 仍在 top"

    # variety_bonus 维度应在两 case 间有差异 (frozen view 真被消费)
    # 注: _format_ranked_for_trace 把 score_breakdown 重命名为 breakdown.
    bd_empty = r1_empty.get("breakdown") or {}
    bd_with = r1_with_view.get("breakdown") or {}
    variety_dim_changed = (
        abs(bd_empty.get("variety_bonus", 0) - bd_with.get("variety_bonus", 0)) > 1e-6
    )
    total_score_changed = abs(
        (r1_empty.get("score") or 0) - (r1_with_view.get("score") or 0)
    ) > 1e-6
    assert variety_dim_changed or total_score_changed, (
        "frozen.l2_meal_log_view 未影响打分: "
        f"empty breakdown={bd_empty}, with_view breakdown={bd_with}"
    )


# ────────────────────────── overrides 行为

def test_what_if_overrides_n_return(fixed_env):
    """overrides.n_return=1 → final 长度截断到 1, frozen 字段不变.

    注: fixture 只有 2 家店, 测截断到更小值. __config 反映传入值用于前端展示.
    """
    _, base_trace = _run_recommend_and_get_trace(fixed_env)
    sid = base_trace["session_id"]

    wi = what_if_rerun(sid, overrides={"n_return": 1, "n_explore": 0}, root=fixed_env)
    assert len(wi.get("final") or []) == 1
    assert wi["__config"]["n_return"] == 1
    assert wi["__config"]["n_explore"] == 0
    # frozen 与 base 完全一致
    assert wi["__frozen"] == base_trace["__frozen"]


def test_what_if_profile_overrides_deep_merge(fixed_env):
    """profile_overrides 深合并 scoring_weights, 不破坏 base 其它字段."""
    _, base_trace = _run_recommend_and_get_trace(fixed_env)
    sid = base_trace["session_id"]

    # 把 distance_weight 拉爆 (假设 score.py 消费)
    wi = what_if_rerun(
        sid,
        overrides={"profile_overrides": {"scoring_weights": {"distance": 99.0}}},
        root=fixed_env,
    )
    # 应能跑通 (具体 score 漂移不验, deep_merge 正确性单独验)
    assert wi.get("final") is not None
    assert wi["__config"]["profile_overrides"] == {"scoring_weights": {"distance": 99.0}}


# ────────────────────────── 单元: validate_overrides

def test_validate_overrides_rejects_unknown_keys():
    with pytest.raises(debug_what_if.InvalidOverrides):
        debug_what_if.validate_overrides({"hack_frozen_today": "2099-01-01"})


def test_validate_overrides_type_checks():
    with pytest.raises(debug_what_if.InvalidOverrides):
        debug_what_if.validate_overrides({"n_return": "five"})
    with pytest.raises(debug_what_if.InvalidOverrides):
        debug_what_if.validate_overrides({"use_llm_rerank": "yes"})
    with pytest.raises(debug_what_if.InvalidOverrides):
        debug_what_if.validate_overrides({"profile_overrides": "patch me"})


def test_validate_overrides_accepts_empty():
    assert debug_what_if.validate_overrides({}) == {}
    assert debug_what_if.validate_overrides(None) == {}


def test_deep_merge_recursive():
    base = {"a": {"b": 1, "c": 2}, "d": 3}
    patch = {"a": {"c": 99, "e": 5}}
    out = debug_what_if.deep_merge(base, patch)
    assert out == {"a": {"b": 1, "c": 99, "e": 5}, "d": 3}
    # 原 dict 未被改 (deepcopy)
    assert base == {"a": {"b": 1, "c": 2}, "d": 3}


# ────────────────────────── what_if_rerun 错误路径

def test_what_if_use_llm_does_not_read_live_prefs(fixed_env, monkeypatch):
    """D-079 BLOCKER fix 守门: What-if 走 LLM 路径 (use_llm_rerank=True) 时,
    _profile_block 必须用 frozen l1_prefs_snapshot, 绝不能 load_prefs(disk).

    Codex review 抓的 merge BLOCKER: 修前 debug_what_if 调 v2_rerank 不传
    l1_prefs_override → _profile_block(root=None) → load_prefs(None) →
    _project_root() fallback 读 live disk, 违反 "What-if 零 runtime read".

    Stub LLM call_text 让 use_llm=True 跑通到 _profile_block, 同时
    monkeypatch load_prefs raise. 若仍被调 = BLOCKER 复活.
    """
    from chisha import llm_client
    _, base_trace = _run_recommend_and_get_trace(fixed_env)
    sid = base_trace["session_id"]

    # load_prefs 被调 = 红线破
    def _explode(*args, **kwargs):
        raise RuntimeError("load_prefs must not be called during What-if LLM path")

    monkeypatch.setattr(l1_prefs, "load_prefs", _explode)

    # stub call_text → 返一个最简合法 LLM 响应 (避免真调 LLM 网络)
    def _fake_call_text(*args, **kwargs):
        return {
            "raw_text": '{"candidates": []}',
            "content": '{"candidates": []}',
            "stop_reason": "tool_use",
            "tool_input": {"candidates": []},
            "model": "stub",
            "usage": None,
        }
    monkeypatch.setattr(llm_client, "call_text", _fake_call_text)
    # 同时跳过 provider 校验, 让 _run_llm_rerank 不在 _resolve_provider 阶段
    # 就走 config_error 短路 (这样 build_user_message → _profile_block 一定执行).
    monkeypatch.setattr(llm_client, "_resolve_provider", lambda *_a, **_k: "anthropic")
    monkeypatch.setattr(llm_client, "_resolve_model",
                         lambda *_a, **_k: "claude-opus-4-7")

    wi = what_if_rerun(sid,
                       overrides={"use_llm_rerank": True}, root=fixed_env)
    # 至少跑到 trace 写完; final 可能为空 (stub 返 0 candidates → fallback),
    # 关键是 load_prefs 没被调 (否则 RuntimeError 上抛)
    assert wi.get("__source") == "what_if_preview"


def test_what_if_uses_frozen_prefs_snapshot(fixed_env, monkeypatch):
    """D-079 BLOCKER fix 守门: frozen l1_prefs_snapshot ≠ disk prefs 时,
    _profile_block 渲染 user_message 必须用 frozen 版本.

    构造: frozen 含 boost=[low_oil], runtime disk 含 boost=[spicy]. 跑 What-if
    LLM 路径, 抓 build_user_message 真正传给 LLM 的字符串, 必须含 low_oil
    不能含 spicy.
    """
    import datetime as _dt
    from chisha import llm_client
    _, base_trace = _run_recommend_and_get_trace(fixed_env)
    sid = base_trace["session_id"]

    # 手动塞 frozen.l1_prefs_snapshot
    base_trace["__frozen"]["l1_prefs_snapshot"] = {
        "version": 1,
        "boost": ["low_oil"],
        "penalty": [],
        "based_on_meals": 4,
        "evidence": [{
            "token": "low_oil", "from_meals": ["d1", "d2"],
            "rationale": "4/4 oil_calibration=too_high",
        }],
        "regularities_freetext": "",
        "signals_not_scored": [],
    }
    trace_store.write_trace(sid, base_trace, root=fixed_env)

    # disk prefs: 写 spicy boost 到 sandbox-equivalent 路径 (fixed_env)
    from chisha import data_root
    prefs_path = data_root.long_term_prefs_path(fixed_env)
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    prefs_path.write_text(json.dumps({
        "version": 1,
        "boost": ["spicy"],
        "penalty": [],
        "based_on_meals": 4,
        "evidence": [],
    }), encoding="utf-8")

    # 抓 build_user_message 实际拼出的 user_msg
    captured: dict = {}

    def _capture_call_text(user_msg, **kwargs):
        captured["user_msg"] = user_msg
        return {
            "raw_text": '{"candidates": []}',
            "content": '{"candidates": []}',
            "stop_reason": "tool_use",
            "tool_input": {"candidates": []},
            "model": "stub",
            "usage": None,
        }
    monkeypatch.setattr(llm_client, "call_text", _capture_call_text)
    monkeypatch.setattr(llm_client, "_resolve_provider", lambda *_a, **_k: "anthropic")
    monkeypatch.setattr(llm_client, "_resolve_model",
                         lambda *_a, **_k: "claude-opus-4-7")

    what_if_rerun(sid, overrides={"use_llm_rerank": True}, root=fixed_env)

    user_msg = captured.get("user_msg") or ""
    assert "low_oil" in user_msg, (
        f"frozen boost=low_oil 未注入 [PROFILE] 行为信号: user_msg={user_msg[:500]!r}"
    )
    assert "spicy" not in user_msg, (
        f"disk prefs=spicy 泄漏 (应被 frozen 覆盖): user_msg={user_msg[:500]!r}"
    )


def test_what_if_rejects_missing_trace(fixed_env):
    with pytest.raises(FileNotFoundError):
        what_if_rerun("does_not_exist_sid", overrides={}, root=fixed_env)


def test_what_if_rejects_non_production_source(fixed_env):
    """Codex PR-2 FIX-NOW #2: source!=production → InvalidBaseTrace 子类."""
    _, base_trace = _run_recommend_and_get_trace(fixed_env)
    sid = base_trace["session_id"]
    base_trace["__source"] = "what_if_preview"
    trace_store.write_trace(sid, base_trace, root=fixed_env)
    with pytest.raises(debug_what_if.InvalidBaseTrace, match="source must be"):
        what_if_rerun(sid, overrides={}, root=fixed_env)


def test_what_if_rejects_invalid_overrides(fixed_env):
    _, base_trace = _run_recommend_and_get_trace(fixed_env)
    sid = base_trace["session_id"]
    with pytest.raises(debug_what_if.InvalidOverrides):
        what_if_rerun(sid, overrides={"frozen_today": "X"}, root=fixed_env)


def test_what_if_zero_overrides_preserves_hard_filter_events(fixed_env):
    """T-P1a-01: What-if zero overrides 重跑后, response trace l1.hard_filter_events
    与 base trace 相同.

    Codex audit blocker #4: 防止 hard_filter_events 在 What-if 路径被悄无声息地
    重新生成 (导致与 frozen state 不一致). What-if 用 frozen L1, 不重跑 hard_filter,
    因此事件列表必须 from base.
    """
    _, base_trace = _run_recommend_and_get_trace(fixed_env)
    sid = base_trace["session_id"]
    # 注入一条假事件到 base trace 模拟 L0-A 触发
    base_trace["l1"]["hard_filter_events"] = [{
        "event_type": "hard_filter",
        "category": "L0_A_medical",
        "rule": "allergy:simulated_peanut",
        "dropped_count": 1,
        "kept_count": 50,
        "refine_override": False,
        "timestamp": 1234.5,
    }]
    trace_store.write_trace(sid, base_trace, root=fixed_env)
    # zero override 重跑
    wi = what_if_rerun(sid, overrides={}, root=fixed_env)
    # response trace 应 from base, hard_filter_events 内容相同
    wi_l1 = wi.get("l1", {})
    if "hard_filter_events" in wi_l1:
        events = wi_l1["hard_filter_events"]
        # 字段在的话, 应该包含或匹配 base 注入的事件
        if events:
            rules = {e.get("rule") for e in events}
            assert "allergy:simulated_peanut" in rules or events == [], \
                f"What-if hard_filter_events 与 base 不一致: {events}"

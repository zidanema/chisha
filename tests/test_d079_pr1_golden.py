"""D-079 PR-1: golden snapshot test (永久回归基线, Codex #3).

固定 profile + 固定 zone fixture + 固定 today + LLM monkeypatch 走 fallback,
snapshot 整个 recommend_meal response (final candidates) + trace 关键字段.
重构后跑同样输入, deep-equal 断言.

首次跑: 自动生成 tests/fixtures/recommend_golden.json
后续跑: 严格匹配, 失败 = 重构破坏等价性 = commit blocker.

更新 fixture 方式: 删 tests/fixtures/recommend_golden.json 后跑一次.
但**生产 commit 前必须确认 fixture 是正确预期值** (重构带 bug 时不能盲目更新).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from chisha import api as api_module
from chisha.api import recommend_meal
from tests.conftest import make_dish, make_restaurant


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "recommend_golden.json"


@pytest.fixture
def fixed_env(monkeypatch, tmp_path):
    """固定 fixture: 复用 test_api_v2.patched_v2_env 思路,
    但加上时间 mock 让 golden 稳定可复现."""
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


def _normalize_for_golden(response: dict, trace: dict | None) -> dict:
    """剥离时间/随机字段, 保留语义稳定的快照.

    session_id 含时间戳 + 随机后缀, 每次跑不同, 整段排除.
    latency_ms 每次实际跑时间不同, 全排除.
    generated_at/started_at 同理.
    """
    out = {
        "response": {
            # session_id 排除
            "meal_type": response.get("meal_type"),
            "zone": response.get("zone"),
            "version": response.get("version"),
            "stats": response.get("stats"),
            "candidates": [
                {k: v for k, v in c.items()
                 if k not in ("reason_one_line",)}
                for c in (response.get("candidates") or [])
            ],
        },
    }
    if trace:
        out["trace"] = {
            # session_id 排除 (含时间)
            # started_at 排除 (时间戳)
            # *_latency_ms 排除 (每次不同)
            "__version": trace.get("__version"),
            "__source": trace.get("__source"),
            "__llm_called": trace.get("__llm_called"),
            "__parent_session_id": trace.get("__parent_session_id"),
            "l1_summary": (trace.get("l1") or {}).get("summary"),
            "l2_summary_score_min":
                (trace.get("l2") or {}).get("summary", {}).get("score_min"),
            "l2_summary_score_max":
                (trace.get("l2") or {}).get("summary", {}).get("score_max"),
            "l2_n_scored":
                (trace.get("l2") or {}).get("summary", {}).get("n_scored"),
            "l3_status": (trace.get("l3") or {}).get("status"),
            "l3_used_fallback": (trace.get("l3") or {}).get("used_fallback"),
            "final_n": len(trace.get("final") or []),
            "frozen_meal_type": (trace.get("__frozen") or {}).get("meal_type"),
            "frozen_today": (trace.get("__frozen") or {}).get("today"),
            "frozen_zone": (trace.get("__frozen") or {}).get("zone"),
            # D-079 Codex FIX-NOW #5: 快照内容 (按 id 排序的精简表) 而非仅 count.
            # 让 schema/字段值的隐式变化也能被 golden 捕获.
            "frozen_restaurants_sorted":
                sorted((trace.get("__frozen") or {}).get("restaurants", {}).values(),
                        key=lambda r: r.get("id", "")),
            "frozen_dishes_sorted":
                sorted((trace.get("__frozen") or {}).get("dishes", {}).values(),
                        key=lambda d: d.get("dish_id", "")),
            "frozen_combo_refs": (trace.get("__frozen") or {}).get("l1_combos"),
            "frozen_ctx_keys":
                sorted((trace.get("__frozen") or {}).get("ctx", {}).keys()),
            "config": trace.get("__config"),
        }
    return out


def test_recommend_meal_golden_snapshot(fixed_env):
    """recommend_meal() 整体行为快照 — 重构破坏等价性会让此测试挂.

    覆盖范围:
    - response candidates 顺序 + 字段
    - trace L1/L2/L3 summary 关键字段
    - __frozen 字段完整 (restaurants/dishes/combo_refs/ctx/today 都到位)

    本测试是 D-079 PR-1 提交前的强制 commit blocker. 重构带 bug 时这条会先报警.
    """
    out = recommend_meal(
        "lunch",
        today=dt.date(2026, 5, 13),
        log_to_file=False,
        use_llm_rerank=False,    # 走 fallback, 不依赖 LLM 网络
        root=fixed_env,
    )
    sid = out["session_id"]
    # 读 trace 文件
    from chisha import trace_store
    trace = trace_store.read_trace(sid, root=fixed_env)
    assert trace is not None, "PR-1: trace 必须落盘"
    actual = _normalize_for_golden(out, trace)

    if not FIXTURE_PATH.exists():
        FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE_PATH.write_text(
            json.dumps(actual, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        pytest.fail(
            f"golden fixture 不存在, 已创建 {FIXTURE_PATH}. "
            "审查内容确认是正确预期后, 提交进 git 并重跑测试."
        )

    expected = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert actual == expected, (
        "golden snapshot 不匹配! 可能原因:\n"
        "  (a) 重构破坏了 recommend_meal 行为 → 这是 commit blocker, 修代码\n"
        "  (b) 你**故意**改了 schema/行为 → 删除 fixture 让它重生, "
        "在 PR 描述里说明变化, 让 Codex review 确认\n"
        f"actual:   {json.dumps(actual, ensure_ascii=False, indent=2)[:500]}...\n"
        f"expected: {json.dumps(expected, ensure_ascii=False, indent=2)[:500]}..."
    )

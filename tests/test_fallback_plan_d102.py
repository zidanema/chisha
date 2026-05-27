"""D-102 Step1: FallbackPlan 统一兜底契约 — 根治 meal_log drift (提案 §病根).

覆盖 Codex 设计 review (d) 要求:
- web/cli 兜底一致性, 且**有牙** (meal_log 真的改变 explore 选择, 否则两路都传 [] 也过)
- to_blob/from_blob 跨进程 round-trip 忠实
- blob 缺失 / 版本不符 → fail-loud (D-100 无 grandfather)
- build_fallback_plan / fallback_rerank meal_log 必填 (拔掉隐式漏传温床)
- _pick_explore 7 天边界 (meal_log 冻结快照消费正确)
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from chisha.rerank import (
    FALLBACK_STRATEGY_VERSION,
    FallbackPlan,
    build_fallback_plan,
    fallback_rerank,
    rerank,
)
from tests.conftest import make_dish, make_restaurant

TODAY = dt.date(2026, 5, 28)


def _combo(rid: str, cuisine: str, method: str, score: float) -> dict:
    """单菜 combo, cuisine + cooking_method 显式 (驱动 _pick_explore novelty)."""
    return {
        "restaurant": make_restaurant(rid=rid, name=f"店_{rid}", category=cuisine),
        "dishes": [make_dish(dish_id=f"{rid}_d", restaurant_id=rid,
                             canonical_name=f"菜_{rid}", cuisine=cuisine,
                             cooking_method=method)],
        "score": score,
    }


@pytest.fixture
def teeth_combos() -> list[dict]:
    """构造让 meal_log 真正改变 explore 的候选 (≥10 个让 mid_pool 含 combo3/4/5):
    exploit (top3) = 湘/川/鲁 × 烤/炖/焖; rest=combos[3:] (7 个) → mid_end=max(2,7//2)=3
    → mid_pool=combo3/4/5. combo3 = 粤菜·烤 (method 复用 exploit 的烤) → meal_log 出现
    粤菜时 cuisine+method 都落 used → 从 novel 翻成 non-novel, explore 集合从 {3,4} 变 {4,5}.
    """
    return [
        _combo("r0", "湘菜", "烤", 5.0),
        _combo("r1", "川菜", "炖", 4.9),
        _combo("r2", "鲁菜", "焖", 4.8),
        _combo("r3", "粤菜", "烤", 4.7),   # 关键: method=烤 与 exploit 重叠
        _combo("r4", "日料", "煎", 4.6),
        _combo("r5", "泰菜", "炒", 4.5),
        _combo("r6", "韩餐", "蒸", 4.4),
        _combo("r7", "西餐", "拌", 4.3),
        _combo("r8", "云南菜", "卤", 4.2),
        _combo("r9", "新疆菜", "烩", 4.1),
    ]


def _explore_idx(out: list[dict]) -> list[int]:
    return [c.get("combo_index") for c in out if c.get("is_explore")]


def _meal_log_yue() -> list[dict]:
    """近 1 天吃过粤菜 (在 7 天窗口内)."""
    return [{"timestamp": (TODAY - dt.timedelta(days=1)).isoformat(),
             "dishes": [{"cuisine": "粤菜"}]}]


# ───────────────────── 有牙: meal_log 真改变 explore ─────────────────────

def test_meal_log_changes_explore(teeth_combos):
    """meal_log 出现粤菜 → explore 避开粤菜 combo3, 选择集从 {3,4} 变 {4,5}.

    这是整个一致性测试的"牙": 证明 meal_log 真的流进了 explore. 若 drift (漏传
    meal_log) 这两个分支会相同, 测试就形同虚设.
    """
    empty = FallbackPlan(teeth_combos, meal_log=[], n=5, n_explore=2,
                         today=TODAY).execute()
    yue = FallbackPlan(teeth_combos, meal_log=_meal_log_yue(), n=5, n_explore=2,
                       today=TODAY).execute()
    assert set(_explore_idx(empty)) == {3, 4}
    assert set(_explore_idx(yue)) == {4, 5}
    assert _explore_idx(empty) != _explore_idx(yue)   # 牙: meal_log 真生效


def test_web_cli_fallback_consistency(teeth_combos):
    """web 进程内路径 (rerank use_llm=False) 与 cli 路径 (FallbackPlan.execute)
    同 top_combos + meal_log → explore 段完全一致 (单源同构)."""
    meal_log = _meal_log_yue()
    profile = {"taste_description": "", "preferences": {}}
    web_out = rerank(teeth_combos, profile, context=None, meal_log=meal_log,
                     n=5, n_explore=2, use_llm=False, today=TODAY)
    cli_out = build_fallback_plan(teeth_combos, meal_log=meal_log, n=5,
                                  n_explore=2, today=TODAY).execute()
    assert _explore_idx(web_out) == _explore_idx(cli_out)
    assert [c.get("combo_index") for c in web_out] == \
           [c.get("combo_index") for c in cli_out]


# ───────────────────── 跨进程 blob round-trip 忠实 ─────────────────────

def test_blob_roundtrip_faithful(teeth_combos):
    """to_blob → JSON → from_blob → execute 与同进程 execute 逐位一致 (cli 跨进程)."""
    meal_log = _meal_log_yue()
    plan = build_fallback_plan(teeth_combos, meal_log=meal_log, n=5,
                               n_explore=2, today=TODAY)
    direct = plan.execute()
    blob = json.loads(json.dumps(plan.to_blob()))   # 模拟落盘 + 读回
    # n/n_explore/today 由调用方从 round frozen 单源回传 (非 blob), 与 cmd_apply_rerank 一致
    rebuilt = FallbackPlan.from_blob(
        blob, top_combos=teeth_combos, n=5, n_explore=2, today=TODAY,
    ).execute()
    assert _explore_idx(direct) == _explore_idx(rebuilt)
    assert [c.get("combo_index") for c in direct] == \
           [c.get("combo_index") for c in rebuilt]


def test_blob_carries_meal_log_snapshot(teeth_combos):
    """blob 只冻结兜底专属状态 (meal_log 快照 + version); n/n_explore/today 走 round
    frozen 单源不在 blob (D-102.1 Codex commit review: 防双持久化漂移)."""
    blob = build_fallback_plan(teeth_combos, meal_log=_meal_log_yue(), n=5,
                               n_explore=2, today=TODAY).to_blob()
    assert blob["meal_log"] == _meal_log_yue()
    assert blob["version"] == FALLBACK_STRATEGY_VERSION
    # 单源纪律: 这些不重复进 blob
    assert "n" not in blob and "n_explore" not in blob and "today" not in blob


# ───────────────────── fail-loud (D-100 无 grandfather) ─────────────────────

def _from_blob(blob, combos):
    """from_blob 调用 helper — n/n_explore/today 走 round frozen 单源 (固定测试值)."""
    return FallbackPlan.from_blob(blob, top_combos=combos, n=5, n_explore=2,
                                  today=TODAY)


def test_from_blob_missing_fails_loud(teeth_combos):
    """旧 round 无 fallback_plan blob → ValueError (不静默降级 []→重现 drift)."""
    with pytest.raises(ValueError, match="meal_log 快照"):
        _from_blob(None, teeth_combos)
    with pytest.raises(ValueError, match="meal_log 快照"):
        _from_blob({"version": FALLBACK_STRATEGY_VERSION}, teeth_combos)   # 缺 meal_log


def test_from_blob_version_mismatch_fails_loud(teeth_combos):
    """版本不符 → fail-loud (兜底策略变, 旧快照失效)."""
    blob = build_fallback_plan(teeth_combos, meal_log=[], n=5, n_explore=2,
                               today=TODAY).to_blob()
    blob["version"] = FALLBACK_STRATEGY_VERSION + 99
    with pytest.raises(ValueError, match="version"):
        _from_blob(blob, teeth_combos)


# ───────────────────── meal_log 必填 (拔温床) ─────────────────────

def test_build_fallback_plan_requires_meal_log(teeth_combos):
    """build_fallback_plan / fallback_rerank meal_log 关键字必填 → 漏传是 TypeError
    而非静默 None (病根: 默认 None 隐式漏传)."""
    with pytest.raises(TypeError):
        build_fallback_plan(teeth_combos, n=5, n_explore=2)   # type: ignore[call-arg]
    with pytest.raises(TypeError):
        fallback_rerank(teeth_combos, n=5, n_explore=2)       # type: ignore[call-arg]


def test_build_fallback_plan_none_meal_log_ok(teeth_combos):
    """None 显式传入 = 空历史 (语义合法), 不抛 — 与 rerank() meal_log=None 默认兼容."""
    out = build_fallback_plan(teeth_combos, meal_log=None, n=5, n_explore=2,
                              today=TODAY).execute()
    assert set(_explore_idx(out)) == {3, 4}   # 同 meal_log=[] 行为


# ───────────────────── 7 天边界 (快照消费正确) ─────────────────────

def test_pick_explore_7day_boundary(teeth_combos):
    """meal_log 边界: cutoff = today-7d. 恰在边界 (today-7) 计入, 越界 (today-8) 不计.

    粤菜条目在 today-7 → 仍影响 explore (集合 {4,5}); 移到 today-8 → 不影响 ({3,4}).
    """
    on_edge = [{"timestamp": (TODAY - dt.timedelta(days=7)).isoformat(),
                "dishes": [{"cuisine": "粤菜"}]}]
    over_edge = [{"timestamp": (TODAY - dt.timedelta(days=8)).isoformat(),
                  "dishes": [{"cuisine": "粤菜"}]}]
    out_edge = FallbackPlan(teeth_combos, meal_log=on_edge, n=5, n_explore=2,
                            today=TODAY).execute()
    out_over = FallbackPlan(teeth_combos, meal_log=over_edge, n=5, n_explore=2,
                            today=TODAY).execute()
    assert set(_explore_idx(out_edge)) == {4, 5}    # 边界内, 粤菜生效
    assert set(_explore_idx(out_over)) == {3, 4}    # 越界, 粤菜失效

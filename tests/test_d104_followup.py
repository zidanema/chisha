"""D-104 债务跟修 (followup): ② reference resolver v3 可发现性 + ① 裸 core 真实时钟护栏.

D-104 收口时 Codex 标了两条备查 (出当时 scope), 本文件锁死:

② reference_resolver.resolve_reference 旧用 trace_store.list_traces (v2 平铺 glob) +
   read_trace (v2 单文件) — refine 后迁成 v3 目录的 session **发现不到也读不到** →
   "上次那家差不多换一家" 这类引用解析失败, 隐性破坏 Faithful Refine (D-080)。
   修复 = 两处都换 v3-aware (list_traces_v3 + read_meta/read_round_full)。

① "sandbox=debug, 在 production 之外" (D-104 行为微调): 虚拟时钟只经 web/debug 入口
   (import sandbox) 注册; 裸 agent recommend 路径走真实时钟。本测试锁死, 防以后有人
   把假时间接回点餐路径。
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys


# ────────────────────────── ② reference resolver v3 可发现性

def _r1_trace(sid: str, meal_type: str, final: list[dict]) -> dict:
    return {
        "session_id": sid,
        "started_at": "2026-05-29T12:00:00",
        "__frozen": {"meal_type": meal_type, "zone": "shenzhen-bay"},
        "l1": {"meal": meal_type},
        "l2": {},
        "l3": {"status": "ok"},
        "final": final,
        "total_latency_ms": 0,
    }


def _refine_round(meal_type: str, final: list[dict]) -> dict:
    return {
        "user_input": "换一家",
        "intent_v2": None,
        "narrative": "",
        "kpi": {"combos": len(final), "top1": "", "latency_ms": 0},
        "l1": {"meal": meal_type},
        "l2": {},
        "l3": {"status": "ok"},
        "final": final,
        "__frozen": {"meal_type": meal_type, "zone": "shenzhen-bay"},
    }


def test_resolve_reference_finds_refined_v3_session(tmp_path):
    """refine 过 (R2, v3 目录布局) 的历史餐, 引用能被发现且读到最新 round 的 final。

    旧实现 (list_traces + read_trace, 均 v2-only) 在此场景返 None — 测试内嵌
    sanity 断言证明该前提仍成立, 即本修复确实修了真 bug。
    """
    from chisha import reference_resolver, trace_store

    root = tmp_path
    sid = "20260529_lunch_refined"
    combo_r1 = [{"restaurant": {"id": "r_a", "name": "A店"},
                 "dishes": [{"name": "辣子鸡", "cuisine": "川菜"}]}]
    combo_r2 = [{"restaurant": {"id": "r_b", "name": "B店"},
                 "dishes": [{"name": "水煮鱼", "cuisine": "川菜"}]}]

    trace_store.write_trace(sid, _r1_trace(sid, "lunch", combo_r1), root=root)
    # append_round 触发 v2→v3 目录迁移
    trace_store.append_round(sid, _refine_round("lunch", combo_r2), root=root)

    # sanity: 旧 v2-only 路径确实看不到 / 读不到 (= 修复前的 bug 前提)
    v2_items, _ = trace_store.list_traces(root=root, limit=100)
    assert all(it["session_id"] != sid for it in v2_items), \
        "前提失效: v2 list_traces 不该看到 v3 目录 session"
    assert trace_store.read_trace(sid, root=root) is None, \
        "前提失效: v2 read_trace 不该读到 v3 目录 session"

    # 修复后: v3-aware 路径应发现并解析
    q = reference_resolver.ReferenceQuery(
        raw_text="上次午饭那家", relation="similar", days_back=-2, meal_hint="lunch")
    resolved = reference_resolver.resolve_reference(
        q, today=dt.date(2026, 5, 30), root=root)

    assert resolved is not None, "refine 过的历史餐应能被引用解析到"
    assert resolved.base_session_id == sid
    assert resolved.base_meal_type == "lunch"
    assert resolved.base_combos, "应取到最新已发布 round 的 final combos"
    # 最新 round (R2) 的 final, 不是 R1
    rest_ids = {(c.get("restaurant") or {}).get("id") for c in resolved.base_combos}
    assert "r_b" in rest_ids


def test_resolve_reference_still_works_for_v2_only_session(tmp_path):
    """未 refine (纯 v2 单文件) 的 session 仍能解析 (回归: 别只顾 v3 把 v2 弄丢)。"""
    from chisha import reference_resolver, trace_store

    root = tmp_path
    sid = "20260529_dinner_v2only"
    combo = [{"restaurant": {"id": "r_c", "name": "C店"},
              "dishes": [{"name": "番茄牛腩", "cuisine": "粤菜"}]}]
    trace_store.write_trace(sid, _r1_trace(sid, "dinner", combo), root=root)

    q = reference_resolver.ReferenceQuery(
        raw_text="上次晚饭", relation="similar", days_back=-2, meal_hint="dinner")
    resolved = reference_resolver.resolve_reference(
        q, today=dt.date(2026, 5, 30), root=root)

    assert resolved is not None
    assert resolved.base_session_id == sid
    assert resolved.base_combos


# ────────────────────────── ① 裸 core 真实时钟护栏

def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


def test_bare_agent_recommend_path_uses_real_clock():
    """裸 agent recommend 路径 (不 import sandbox) → 真实时钟, 非虚拟。

    锁死 D-104 备查①: 虚拟时钟只经 web/debug (import sandbox) 注册, 点餐 CLI 路径永远
    真实时间。若以后谁让 core import 链拉进 sandbox / 把假时钟注册进核心, 此测试立刻红。
    """
    code = (
        "import sys, datetime as dt\n"
        "from pathlib import Path\n"
        "import chisha.agent_cli, chisha.agent_orchestration, chisha.api\n"
        "import chisha.clock as clock\n"
        "from chisha import clock_provider\n"
        "assert 'chisha.sandbox' not in sys.modules, 'bare core 不该 import sandbox'\n"
        "p = type(clock_provider.get_clock_provider()).__name__\n"
        "assert p == 'RealClockProvider', f'裸 core 时钟应 Real, got {p}'\n"
        "assert clock.today(Path('/tmp')) == dt.date.today(), '裸 core today 应真实时间'\n"
        "print('OK')\n"
    )
    r = _run(code)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"

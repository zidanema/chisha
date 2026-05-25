"""T9: agent_cli 端到端 + 5 链路 (D-074).

codex #6 要求覆盖: 有 context / 无 context / refine round / retry-幂等 / 旧 trace UI 读取隔离.
用 tmp root + monkeypatch 隔离 (不碰真实数据 / 不调 LLM — 模拟 agent 执行 spec).
"""
from __future__ import annotations

import contextlib
import io
import json

import pytest

from chisha import agent_cli
from chisha import agent_orchestration as orch
from tests.conftest import make_dish, make_restaurant


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """CLI 跑在 tmp root, recall/score/ctx 全 mock (不依赖真数据/LLM)."""
    monkeypatch.setattr(agent_cli, "_root", lambda: tmp_path)

    fake_combos = [
        {"restaurant": make_restaurant(rid=f"r{i}", name=f"店{i}"),
         "dishes": [make_dish(dish_id=f"r{i}_d", canonical_name=f"菜{i}",
                              main_ingredient_type="纯素",
                              vegetable_ratio_estimate=0.9)],
         "score": 5.0 - i * 0.1}
        for i in range(10)
    ]
    profile = {"basics": {"office_zone": "test"}, "taste_description": "清爽",
               "preferences": {"liked_cuisines": [], "disliked_cuisines": [],
                               "avoid_dishes": [], "spicy_tolerance": 2}}
    monkeypatch.setattr(agent_cli, "_load_inputs",
                        lambda meal, root: (profile, "test", [], [], []))
    monkeypatch.setattr(orch, "recall", lambda *a, **kw: list(fake_combos))
    monkeypatch.setattr(orch, "rank_combos", lambda *a, **kw: list(fake_combos))
    monkeypatch.setattr(orch, "apply_caps", lambda ranked, *a, **kw: ranked)
    monkeypatch.setattr(orch, "_build_fb_signal", lambda today, root: None)

    class _Ctx:
        def __init__(self, ri=None): self._ri = ri
        def to_llm_dict(self):
            return {"meal_type": "lunch", "refine_input": self._ri,
                    "refine_intent": None}
    monkeypatch.setattr(orch, "build_context", lambda **kw: _Ctx(kw.get("refine_input")))
    return tmp_path


def _run(argv) -> dict:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        agent_cli.main(argv)
    last = None
    for line in buf.getvalue().splitlines():
        line = line.strip()
        if line.startswith("{"):
            last = json.loads(line)
    return last


def _valid_rerank(n_explore=2):
    cands = [{"rank": i + 1, "is_explore": i >= (5 - n_explore), "combo_index": i,
              "fit_score": 0.8, "taste_match": 0.7, "risk_flags": [],
              "one_line_reason": f"r{i}"} for i in range(5)]
    return json.dumps({"candidates": cands, "narrative": "测试"})


def _valid_intent():
    return json.dumps({
        "redirect": {"cuisine_want": [], "cuisine_avoid": [],
                     "cuisine_candidates_expanded": ["川菜"], "ingredient_want": [],
                     "ingredient_avoid": [], "brand_avoid": [],
                     "cooking_method_avoid": [], "staple_want": [], "staple_avoid": []},
        "constrain": {"oil": None, "price_max": 30, "price_band": None,
                      "wants_soup": False},
        "reference": None, "reject_previous": False,
        "raw_understanding": "想吃辣推断川菜, 预算30", "schema_version": "2.1",
    })


# ─────────────────────── 链路 1: 无 context ───────────────────────

def test_chain_no_context(cli_env):
    d = _run(["start", "--meal", "lunch"])
    assert d["ok"] and d["status"] == "resolved" and d["operation"] == "rerank"
    rid = d["recommendation_id"]
    assert d["llm_request_spec"]["operation_kind"] == "rerank"

    d = _run(["apply-rerank", "--id", rid, "--response", _valid_rerank()])
    assert d["ok"] and d["status"] == "ready"
    assert d["fallback"] is False
    assert len(d["cards"]) == 5
    card_id = d["cards"][0]["id"]

    d = _run(["choose", "--id", rid, "--card", card_id, "--action", "accept"])
    assert d["ok"] and d["accept_written"] is True


# ─────────────────────── 链路 2: 有 context ───────────────────────

def test_chain_with_context(cli_env):
    d = _run(["start", "--meal", "lunch", "--context", "想吃辣的别太贵"])
    assert d["status"] == "pending" and d["operation"] == "extract"
    assert d["llm_request_spec"]["operation_kind"] == "extract"
    assert d["llm_request_spec"]["output_mode"] == "text_json"
    rid = d["recommendation_id"]

    d = _run(["resolve-intent", "--id", rid, "--intent", _valid_intent()])
    assert d["status"] == "resolved"
    assert d["intent_disclosure"]["status"] == "ok"
    assert d["llm_request_spec"]["operation_kind"] == "rerank"

    d = _run(["apply-rerank", "--id", rid, "--response", _valid_rerank()])
    assert d["status"] == "ready" and len(d["cards"]) == 5


# ─────────────────────── 链路 3: refine round (--from) ───────────────────────

def test_chain_refine_round(cli_env, monkeypatch):
    # R1
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    _run(["apply-rerank", "--id", rid, "--response", _valid_rerank()])
    # refine 轮: --from 同 rid, 应为 R2, n_explore=0 (全 exploit)
    d = _run(["start", "--meal", "lunch", "--context", "再辣点", "--from", rid])
    assert d["recommendation_id"] == rid
    assert d["round"] == "R2"
    assert d["status"] == "pending"
    d = _run(["resolve-intent", "--id", rid, "--intent", _valid_intent()])
    assert d["round"] == "R2" and d["status"] == "resolved"
    # refine 轮 n_explore=0 → 提供全 exploit response
    d = _run(["apply-rerank", "--id", rid, "--response", _valid_rerank(n_explore=0)])
    assert d["status"] == "ready"


# ─────────────────────── 链路 4: retry / 幂等 ───────────────────────

def test_chain_apply_fallback_on_bad_response(cli_env):
    """agent 给越界 combo_index → 校验失败 → chisha_l2 fallback (确定性守卫)."""
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    bad = json.dumps({"candidates": [
        {"rank": 1, "is_explore": False, "combo_index": 999, "fit_score": 0.8,
         "taste_match": 0.7, "risk_flags": [], "one_line_reason": "x"}]})
    d = _run(["apply-rerank", "--id", rid, "--response", bad])
    assert d["ok"] and d["status"] == "ready"
    assert d["fallback"] is True            # 走了规则兜底
    assert len(d["cards"]) == 5             # fallback 仍出 5 条


def test_chain_choose_idempotent_rerun(cli_env):
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    d = _run(["apply-rerank", "--id", rid, "--response", _valid_rerank()])
    cid = d["cards"][0]["id"]
    _run(["choose", "--id", rid, "--card", cid, "--action", "accept"])
    d2 = _run(["choose", "--id", rid, "--card", cid, "--action", "accept"])
    assert d2["already_complete"] is True   # 重跑不重复计数


def test_resolve_intent_requires_pending(cli_env):
    """no-context start 产 resolved, 再 resolve-intent 应 ROUND_STATE 错."""
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    d = _run(["resolve-intent", "--id", rid, "--intent", _valid_intent()])
    assert d["ok"] is False and d["error"]["code"] == "ROUND_STATE"


def test_apply_requires_resolved(cli_env):
    """pending round (有 context 未 resolve) 直接 apply-rerank → ROUND_STATE 错."""
    d = _run(["start", "--meal", "lunch", "--context", "辣"])
    rid = d["recommendation_id"]
    d = _run(["apply-rerank", "--id", rid, "--response", _valid_rerank()])
    assert d["ok"] is False and d["error"]["code"] == "ROUND_STATE"


# ─────────────────────── 链路 5: 旧 trace UI 读取隔离 ───────────────────────

def test_pending_not_in_trace_index(cli_env):
    """codex #2: pending/resolved 协议状态不进 list_traces_v3 可见索引."""
    from chisha import trace_store
    d = _run(["start", "--meal", "lunch", "--context", "辣"])
    rid = d["recommendation_id"]
    # in-flight pending 存在
    from chisha import agent_round_store
    assert agent_round_store.read_round(rid, cli_env) is not None
    # 但 list_traces_v3 看不到它 (未发布)
    items, _ = trace_store.list_traces_v3(root=cli_env)
    assert all(it["session_id"] != rid for it in items)


def test_apply_publishes_then_clears_inflight(cli_env):
    """apply-rerank 后: in-flight 清除 (发布到 trace 由 best-effort 完成)."""
    from chisha import agent_round_store
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    _run(["apply-rerank", "--id", rid, "--response", _valid_rerank()])
    assert agent_round_store.read_round(rid, cli_env) is None   # 已 clear


# ─────────────────────── scope guard + doctor + init ───────────────────────

def test_scope_guard_refuses_when_sandbox_enabled(cli_env, monkeypatch):
    from chisha import sandbox
    monkeypatch.setattr(sandbox, "is_enabled", lambda root=None, **kw: True)
    d = _run(["start", "--meal", "lunch"])
    assert d["ok"] is False and d["error"]["code"] == "SCOPE_OR_TIME"


def test_doctor_ok_when_no_sandbox(cli_env):
    d = _run(["doctor"])
    assert d["ok"] is True and d["sandbox_enabled"] is False
    assert d["protocol_version"] == "1.0"


def test_doctor_flags_sandbox(cli_env, monkeypatch):
    from chisha import sandbox
    monkeypatch.setattr(sandbox, "is_enabled", lambda root=None, **kw: True)
    d = _run(["doctor"])
    assert d["ok"] is False and d["sandbox_enabled"] is True


def test_init_generates_skill(cli_env):
    d = _run(["init", "--agent", "claude-code"])
    assert d["ok"] is True
    from pathlib import Path
    assert Path(d["path"]).exists()


def test_at_time_injects_today(cli_env):
    """--at-time 注入 today, 不碰 sandbox."""
    d = _run(["start", "--meal", "dinner", "--at-time", "2026-01-15"])
    assert d["ok"] and d["status"] == "resolved"

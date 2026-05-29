"""T9: agent_cli 端到端 + 5 链路 (D-074).

codex #6 要求覆盖: 有 context / 无 context / refine round / retry-幂等 / 旧 trace UI 读取隔离.
用 tmp root + monkeypatch 隔离 (不碰真实数据 / 不调 LLM — 模拟 agent 执行 spec).
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
from pathlib import Path

import pytest

from chisha import agent_cli
from chisha import agent_orchestration as orch
from tests.conftest import make_dish, make_restaurant


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """CLI 跑在 tmp root, recall/score/ctx 全 mock (不依赖真数据/LLM)."""
    monkeypatch.setattr(agent_cli, "_root", lambda: tmp_path)
    # T-DIST-01 B.4: init_skill 默认 dest = Path.home()/.claude/, 防 e2e 测试写真 HOME.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

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
    # D-102 Step3: 写一份兼容 manifest 让 doctor 视为分发就绪 (否则缺 manifest→ok=false)
    from chisha import manifest as _m
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    _m.manifest_path(tmp_path).write_text(json.dumps({
        "manifest_schema_version": _m.MANIFEST_SCHEMA_VERSION,
        "artifact_version": 1, "data_schema_version": 1,
        "min_engine_version": _m.ENGINE_VERSION,
        "engine_capabilities_required": sorted(_m.SUPPORTED_ENGINE_CAPABILITIES),
        "normalized_name_version": 1, "zones": ["test"],
        "generated_at": "2026-05-28T00:00:00+00:00", "integrity": None,
    }), encoding="utf-8")
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


def _cid(d) -> str:
    """从 verb 返回的 llm_request_spec 取 correlation_id (agent 回传时回显, F4)."""
    return d["llm_request_spec"]["correlation_id"]


def _valid_rerank(correlation_id=None, n_explore=2):
    # correlation_id=None → 占位 (仅供 correlation 校验前就返回的错误路径测试用)
    correlation_id = correlation_id or "x::R1::rerank"
    cands = [{"rank": i + 1, "is_explore": i >= (5 - n_explore), "combo_index": i,
              "fit_score": 0.8, "taste_match": 0.7, "risk_flags": [],
              "one_line_reason": f"r{i}"} for i in range(5)]
    # F4: agent 回传须为信封 {correlation_id, payload}
    return json.dumps({"correlation_id": correlation_id,
                       "payload": {"candidates": cands, "narrative": "测试"}})


def _valid_intent(correlation_id=None):
    correlation_id = correlation_id or "x::R1::extract"
    payload = {
        "redirect": {"cuisine_want": [], "cuisine_avoid": [],
                     "cuisine_candidates_expanded": ["川菜"], "ingredient_want": [],
                     "ingredient_avoid": [], "brand_avoid": [],
                     "cooking_method_avoid": [], "staple_want": [], "staple_avoid": []},
        "constrain": {"oil": None, "price_max": 30, "price_band": None,
                      "wants_soup": False},
        "reference": None, "reject_previous": False,
        "raw_understanding": "想吃辣推断川菜, 预算30", "schema_version": "2.1",
    }
    return json.dumps({"correlation_id": correlation_id, "payload": payload})


# ─────────────────────── 链路 1: 无 context ───────────────────────

def test_chain_no_context(cli_env):
    d = _run(["start", "--meal", "lunch"])
    assert d["ok"] and d["status"] == "resolved" and d["operation"] == "rerank"
    rid = d["recommendation_id"]
    assert d["llm_request_spec"]["operation_kind"] == "rerank"

    d = _run(["apply-rerank", "--id", rid, "--response", _valid_rerank(_cid(d))])
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

    d = _run(["resolve-intent", "--id", rid, "--intent", _valid_intent(_cid(d))])
    assert d["status"] == "resolved"
    assert d["intent_disclosure"]["status"] == "ok"
    assert d["llm_request_spec"]["operation_kind"] == "rerank"

    d = _run(["apply-rerank", "--id", rid, "--response", _valid_rerank(_cid(d))])
    assert d["status"] == "ready" and len(d["cards"]) == 5


# ─────────────────────── 链路 3: refine round (--from) ───────────────────────

def test_chain_refine_round(cli_env, monkeypatch):
    # R1
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    _run(["apply-rerank", "--id", rid, "--response", _valid_rerank(_cid(d))])
    # refine 轮: --from 同 rid, 应为 R2, n_explore=0 (全 exploit)
    d = _run(["start", "--meal", "lunch", "--context", "再辣点", "--from", rid])
    assert d["recommendation_id"] == rid
    assert d["round"] == "R2"
    assert d["status"] == "pending"
    d = _run(["resolve-intent", "--id", rid, "--intent", _valid_intent(_cid(d))])
    assert d["round"] == "R2" and d["status"] == "resolved"
    # refine 轮 n_explore=0 → 提供全 exploit response
    d = _run(["apply-rerank", "--id", rid, "--response", _valid_rerank(_cid(d), n_explore=0)])
    assert d["status"] == "ready"


# ─────────────────────── 链路 4: retry / 幂等 ───────────────────────

def test_chain_apply_fallback_on_bad_response(cli_env):
    """agent 给越界 combo_index → 校验失败 → chisha_l2 fallback (确定性守卫)."""
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    # F4: bad response 仍须包信封 (否则先撞 correlation 缺失而非校验失败)
    bad = json.dumps({"correlation_id": _cid(d), "payload": {"candidates": [
        {"rank": 1, "is_explore": False, "combo_index": 999, "fit_score": 0.8,
         "taste_match": 0.7, "risk_flags": [], "one_line_reason": "x"}],
        "narrative": "已为你挑出低油湘菜"}})
    d = _run(["apply-rerank", "--id", rid, "--response", bad])
    assert d["ok"] and d["status"] == "ready"
    assert d["fallback"] is True            # 走了规则兜底
    assert len(d["cards"]) == 5             # fallback 仍出 5 条
    # F1 (Faithful): fallback 时 agent narrative 不传播 (cards 是规则排的, 叙述会撒谎)
    assert d["narrative"] == ""


def test_apply_rejects_missing_correlation(cli_env):
    """F4: agent 回传裸 JSON (缺 correlation_id) → CORRELATION 错, 不静默接受."""
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    bare = json.dumps({"candidates": [
        {"rank": i + 1, "is_explore": False, "combo_index": i, "fit_score": 0.8,
         "taste_match": 0.7, "risk_flags": [], "one_line_reason": "x"}
        for i in range(5)], "narrative": "x"})
    d = _run(["apply-rerank", "--id", rid, "--response", bare])
    assert d["ok"] is False and d["error"]["code"] == "CORRELATION"


def test_apply_rejects_stale_correlation(cli_env):
    """F4: 错 round/op 的 correlation (stale/串轮 payload) 投到当前轮 → 拒绝."""
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    stale = json.dumps({"correlation_id": f"{rid}::R9::rerank",
                        "payload": {"candidates": [], "narrative": ""}})
    d = _run(["apply-rerank", "--id", rid, "--response", stale])
    assert d["ok"] is False and d["error"]["code"] == "CORRELATION"


def test_chain_choose_idempotent_rerun(cli_env):
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    d = _run(["apply-rerank", "--id", rid, "--response", _valid_rerank(_cid(d))])
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
    _run(["apply-rerank", "--id", rid, "--response", _valid_rerank(_cid(d))])
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
    # D-102 Step2: doctor 报 install/state 二分 + 迁移状态
    assert "install_root" in d and "state_root" in d
    assert d["state_migrated"] in (True, False)
    assert d["legacy_state_pending_migration"] is False   # cli_env install==state


def test_doctor_flags_pending_migration(cli_env, monkeypatch, tmp_path):
    """D-102 Step2 (Codex review Q-B/Q-D): install 有旧 state (含 data/ 反馈) 但 state_root
    未迁 → legacy_state_pending_migration=True + ok=False (未就绪, 不静默读空 state)."""
    install = tmp_path / "install_repo"
    (install / "data").mkdir(parents=True)
    (install / "data" / "feedback_history.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(agent_cli, "_root", lambda: install)
    state_dir = tmp_path / "fresh_state"          # 未迁 (无 marker)
    monkeypatch.setenv("CHISHA_STATE_ROOT", str(state_dir))
    d = _run(["doctor"])
    assert d["legacy_state_pending_migration"] is True   # Q-D: data/ 反馈也算迁移输入
    assert d["ok"] is False                              # Q-B: 未迁 = 未就绪


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


# ─────────────────────── codex review 修复点回归 ───────────────────────

def test_codex_a_apply_uses_persisted_topk(cli_env, monkeypatch):
    """codex #a: resolve 后 meal_log/profile 变化, apply 仍用持久化 top_k 映射,
    combo_index 不漂移到错 combo."""
    d = _run(["start", "--meal", "lunch", "--context", "辣"])
    rid = d["recommendation_id"]
    d = _run(["resolve-intent", "--id", rid, "--intent", _valid_intent(_cid(d))])
    # resolve 后篡改 recall 返回 (模拟数据漂移) — apply 应忽略, 用持久化 top_k
    monkeypatch.setattr(orch, "recall", lambda *a, **kw: [])  # 漂移成空
    d = _run(["apply-rerank", "--id", rid, "--response", _valid_rerank(_cid(d), n_explore=0)])
    assert d["ok"] and d["status"] == "ready"
    assert len(d["cards"]) == 5    # 持久化 top_k 仍在, 没因 recall 漂移变空


def test_codex_c_choice_key_includes_round(cli_env):
    """codex #c: 跨 refine 轮同 card_id 不串台 (choice_key 含 round)."""
    from chisha import feedback_store
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    d = _run(["apply-rerank", "--id", rid, "--response", _valid_rerank(_cid(d))])
    cid = d["cards"][0]["id"]
    _run(["choose", "--id", rid, "--card", cid, "--action", "accept"])
    store = feedback_store.load_store(cli_env)
    ck = store["accepted"][rid]["choice_key"]
    assert "::R1::" in ck    # 含 round 成分


def test_codex_d_resolve_idempotent_replay(cli_env):
    """codex #d: 经 extract 的 resolved round 再 resolve-intent → 幂等重发, 不报错."""
    d = _run(["start", "--meal", "lunch", "--context", "辣"])
    rid = d["recommendation_id"]
    _run(["resolve-intent", "--id", rid, "--intent", _valid_intent(_cid(d))])
    d2 = _run(["resolve-intent", "--id", rid, "--intent", _valid_intent(_cid(d))])
    assert d2["ok"] is True
    assert d2.get("idempotent_replay") is True
    assert d2["llm_request_spec"]["operation_kind"] == "rerank"


def test_codex_f_rejects_path_traversal_id(cli_env):
    """codex #f: 非法 id (path traversal) 在拼路径前被拒."""
    d = _run(["resolve-intent", "--id", "../etc/passwd", "--intent", _valid_intent()])
    assert d["ok"] is False and d["error"]["code"] == "BAD_ID"
    d = _run(["choose", "--id", "ok_sid", "--card", "../../x", "--action", "skip"])
    assert d["ok"] is False and d["error"]["code"] == "BAD_ID"


# ─────────────────────── D-102 Step1: meal_log 冻结进 FallbackPlan ───────────

_MEAL_LOG_FROZEN = [{"timestamp": "2026-05-27T12:00:00", "meal_type": "lunch",
                     "dishes": [{"cuisine": "粤菜"}]}]


def _read_blob(sid, root) -> dict:
    from chisha import agent_round_store
    return (agent_round_store.read_round(sid, root) or {}).get("prepared") or {}


def test_d102_meal_log_frozen_no_context(cli_env, monkeypatch):
    """无 context start: resolve 时 meal_log 必须冻进 fallback_plan blob (病根根治)."""
    profile = {"basics": {"office_zone": "test"}, "taste_description": "",
               "preferences": {"liked_cuisines": [], "disliked_cuisines": [],
                               "avoid_dishes": [], "spicy_tolerance": 2}}
    monkeypatch.setattr(agent_cli, "_load_inputs",
                        lambda meal, root: (profile, "test", [], [], _MEAL_LOG_FROZEN))
    d = _run(["start", "--meal", "lunch"])
    blob = _read_blob(d["recommendation_id"], cli_env)
    # blob 只冻 meal_log + version (n_explore 走 frozen 单源, 不在 blob — D-102.1 Codex review)
    assert blob["fallback_plan"]["meal_log"] == _MEAL_LOG_FROZEN
    assert "n_explore" not in blob["fallback_plan"]


def test_d102_meal_log_frozen_context_resolve(cli_env, monkeypatch):
    """有 context (resolve-intent) 路径同样冻 meal_log (refine 轮 n_explore=0)."""
    profile = {"basics": {"office_zone": "test"}, "taste_description": "",
               "preferences": {"liked_cuisines": [], "disliked_cuisines": [],
                               "avoid_dishes": [], "spicy_tolerance": 2}}
    monkeypatch.setattr(agent_cli, "_load_inputs",
                        lambda meal, root: (profile, "test", [], [], _MEAL_LOG_FROZEN))
    d = _run(["start", "--meal", "lunch", "--context", "辣"])
    rid = d["recommendation_id"]
    d = _run(["resolve-intent", "--id", rid, "--intent", _valid_intent(_cid(d))])
    blob = _read_blob(rid, cli_env)
    assert blob["fallback_plan"]["meal_log"] == _MEAL_LOG_FROZEN


def _varied_combos() -> list[dict]:
    """cuisine/method 多样的 10 combo, 让 meal_log 真能改变 explore (与单元测试同构):
    exploit=湘/川/鲁×烤/炖/焖; combo3=粤菜·烤. 粤菜 meal_log → explore 从 {r3,r4} 变 {r4,r5}.
    """
    from tests.conftest import make_dish, make_restaurant
    spec = [("r0", "湘菜", "烤", 5.0), ("r1", "川菜", "炖", 4.9), ("r2", "鲁菜", "焖", 4.8),
            ("r3", "粤菜", "烤", 4.7), ("r4", "日料", "煎", 4.6), ("r5", "泰菜", "炒", 4.5),
            ("r6", "韩餐", "蒸", 4.4), ("r7", "西餐", "拌", 4.3), ("r8", "云南菜", "卤", 4.2),
            ("r9", "新疆菜", "烩", 4.1)]
    return [{"restaurant": make_restaurant(rid=r, name=f"店_{r}", category=c),
             "dishes": [make_dish(dish_id=f"{r}_d", restaurant_id=r,
                                  canonical_name=f"菜_{r}", cuisine=c,
                                  cooking_method=m)],
             "score": s} for r, c, m, s in spec]


def _explore_rids_from_cards(cards: list[dict]) -> set[str]:
    """card.id = c_{combo_idx}_{rest_id}; 取 explore 卡的 rest_id."""
    return {c["id"].split("_", 2)[2] for c in cards if c.get("is_explore")}


def test_d102_apply_fallback_frozen_meal_log_has_teeth(cli_env, monkeypatch):
    """真 cmd_apply_rerank 兜底路径有牙: resolve 冻的 粤菜 meal_log 必须改变 explore 选择.

    若 cli 回归成旧 bug (apply 漏传 meal_log), explore 会落回 {r3,r4} → 本测试失败.
    同时交叉验证 web rerank(use_llm=False) 同输入 explore 一致 (web/cli 单源同构).
    """
    profile = {"basics": {"office_zone": "test"}, "taste_description": "",
               "preferences": {"liked_cuisines": [], "disliked_cuisines": [],
                               "avoid_dishes": [], "spicy_tolerance": 2}}
    combos = _varied_combos()
    # at_time 远离 wall-clock + meal_log 紧贴 at_time (1 天前): 这样**漏传 today**
    # (降级 wall-clock 2026 年中) 会让粤菜条目超出 7 天窗口失效 → explore 落回 {r3,r4},
    # 测试同时给 meal_log 和 today 两条状态加牙 (Codex commit re-review).
    at_time = "2026-01-15"
    teeth_log = [{"timestamp": "2026-01-14T12:00:00", "meal_type": "lunch",
                  "dishes": [{"cuisine": "粤菜"}]}]
    monkeypatch.setattr(agent_cli, "_load_inputs",
                        lambda meal, root: (profile, "test", [], [], teeth_log))
    monkeypatch.setattr(orch, "recall", lambda *a, **kw: [dict(c) for c in combos])
    monkeypatch.setattr(orch, "rank_combos", lambda *a, **kw: [dict(c) for c in combos])
    monkeypatch.setattr(orch, "apply_caps", lambda ranked, *a, **kw: ranked)

    d = _run(["start", "--meal", "lunch", "--at-time", at_time])
    rid = d["recommendation_id"]
    bad = json.dumps({"correlation_id": _cid(d), "payload": {"candidates": [
        {"rank": 1, "is_explore": False, "combo_index": 999, "fit_score": 0.8,
         "taste_match": 0.7, "risk_flags": [], "one_line_reason": "x"}],
        "narrative": "x"}})
    d = _run(["apply-rerank", "--id", rid, "--response", bad])
    assert d["ok"] and d["fallback"] is True and len(d["cards"]) == 5
    cli_explore = _explore_rids_from_cards(d["cards"])
    assert cli_explore == {"r4", "r5"}        # 牙: 粤菜 meal_log 生效 (非漏传的 {r3,r4})

    # 交叉验证: web rerank fallback 同输入 (同 meal_log + 同 today) → 同 explore (单源同构)
    from chisha.rerank import rerank
    web = rerank([dict(c) for c in combos], profile, context=None,
                 meal_log=teeth_log, n=5, n_explore=2, use_llm=False,
                 today=dt.date.fromisoformat(at_time))
    web_explore = {(c.get("restaurant") or {}).get("id")
                   for c in web if c.get("is_explore")}
    assert web_explore == cli_explore


def test_d102_apply_missing_fallback_plan_fails_loud(cli_env, monkeypatch):
    """旧 in-flight round (无 fallback_plan blob) 走兜底 → NO_FALLBACK_PLAN (不静默)."""
    real_blob = agent_cli._prepared_blob

    def _blob_without_plan(prep, **kw):
        b = real_blob(prep, **kw)
        b.pop("fallback_plan", None)   # 模拟 D-102 前的旧 round
        return b
    monkeypatch.setattr(agent_cli, "_prepared_blob", _blob_without_plan)
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    bad = json.dumps({"correlation_id": _cid(d), "payload": {"candidates": [
        {"rank": 1, "is_explore": False, "combo_index": 999, "fit_score": 0.8,
         "taste_match": 0.7, "risk_flags": [], "one_line_reason": "x"}],
        "narrative": "x"}})
    d = _run(["apply-rerank", "--id", rid, "--response", bad])
    assert d["ok"] is False and d["error"]["code"] == "NO_FALLBACK_PLAN"


# ═══════════════════ P1: continue 折叠 + step_token + 回放 ═══════════════════

def _raw_rerank(n_explore=2) -> str:
    """continue --result 收 raw payload (不包信封, chisha 用 step_token 自动包)."""
    cands = [{"rank": i + 1, "is_explore": i >= (5 - n_explore), "combo_index": i,
              "fit_score": 0.8, "taste_match": 0.7, "risk_flags": [],
              "one_line_reason": f"r{i}"} for i in range(5)]
    return json.dumps({"candidates": cands, "narrative": "测试"})


def _raw_intent() -> str:
    return json.dumps({
        "redirect": {"cuisine_want": [], "cuisine_avoid": [],
                     "cuisine_candidates_expanded": ["川菜"], "ingredient_want": [],
                     "ingredient_avoid": [], "brand_avoid": [],
                     "cooking_method_avoid": [], "staple_want": [], "staple_avoid": []},
        "constrain": {"oil": None, "price_max": 30, "price_band": None,
                      "wants_soup": False},
        "reference": None, "reject_previous": False,
        "raw_understanding": "想吃辣推断川菜", "schema_version": "2.1",
    })


def test_p1_do_llm_and_step_token_present(cli_env):
    """P1: start 回包带 do_llm (canonical) + step_token + llm_request_spec (deprecated alias)."""
    d = _run(["start", "--meal", "lunch"])
    assert d["do_llm"]["operation_kind"] == "rerank"
    assert d["step_token"] == d["do_llm"]["correlation_id"]
    assert d["llm_request_spec"] == d["do_llm"]          # dual-key 一版
    assert "--step <step_token>" in d["next"]


def test_p1_continue_chain_no_context(cli_env):
    """无 context: start → continue(rerank) → ready → choose (host 单循环)."""
    d = _run(["start", "--meal", "lunch"])
    rid, step = d["recommendation_id"], d["step_token"]
    d = _run(["continue", "--id", rid, "--result", _raw_rerank(), "--step", step])
    assert d["ok"] and d["status"] == "ready" and len(d["cards"]) == 5
    assert d["fallback"] is False
    cid = d["cards"][0]["id"]
    d = _run(["choose", "--id", rid, "--card", cid, "--action", "accept"])
    assert d["ok"] and d["accept_written"] is True


def test_p1_continue_chain_with_context(cli_env):
    """有 context: start → continue(extract) → continue(rerank) → ready (同一循环, 两轮)."""
    d = _run(["start", "--meal", "lunch", "--context", "想吃辣的别太贵"])
    assert d["do_llm"]["operation_kind"] == "extract"
    rid, step = d["recommendation_id"], d["step_token"]
    d = _run(["continue", "--id", rid, "--result", _raw_intent(), "--step", step])
    assert d["status"] == "resolved" and d["do_llm"]["operation_kind"] == "rerank"
    step2 = d["step_token"]
    d = _run(["continue", "--id", rid, "--result", _raw_rerank(), "--step", step2])
    assert d["status"] == "ready" and len(d["cards"]) == 5


def test_p1_continue_requires_step(cli_env):
    """step_token 必填 (空) → STEP_REQUIRED (不静默从 round state 派生)."""
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    d = _run(["continue", "--id", rid, "--result", _raw_rerank(), "--step", ""])
    assert d["ok"] is False and d["error"]["code"] == "STEP_REQUIRED"


def test_p1_continue_rejects_stale_round_step(cli_env):
    """stale 跨轮 step_token (round 不符当前) → CORRELATION, 不命中错轮."""
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    stale = f"{rid}::R9::rerank"
    d = _run(["continue", "--id", rid, "--result", _raw_rerank(), "--step", stale])
    assert d["ok"] is False and d["error"]["code"] == "CORRELATION"


def test_p1_continue_step_sid_mismatch(cli_env):
    """step_token 的 sid != --id → STEP_MISMATCH."""
    d = _run(["start", "--meal", "lunch"])
    rid = d["recommendation_id"]
    d = _run(["continue", "--id", rid, "--result", _raw_rerank(),
              "--step", "othersid::R1::rerank"])
    assert d["ok"] is False and d["error"]["code"] == "STEP_MISMATCH"


def test_p1_continue_rerank_replay_after_clear(cli_env):
    """codex Q3: rerank 重发 (round 已 apply+clear) → ready 快照回放, 不报 ROUND_STATE."""
    d = _run(["start", "--meal", "lunch"])
    rid, step = d["recommendation_id"], d["step_token"]
    d1 = _run(["continue", "--id", rid, "--result", _raw_rerank(), "--step", step])
    assert d1["status"] == "ready"
    first_cards = [c["id"] for c in d1["cards"]]
    d2 = _run(["continue", "--id", rid, "--result", _raw_rerank(), "--step", step])
    assert d2["ok"] and d2.get("replayed") is True
    assert [c["id"] for c in d2["cards"]] == first_cards   # 回放同一批 cards


def test_p1_continue_rerank_replay_rejects_stale_round(cli_env):
    """codex P1 C: round 推进后, 旧轮 rerank token 不静默回放历史 cards → ROUND_STATE;
    最新轮 token 仍可回放."""
    d = _run(["start", "--meal", "lunch"])
    rid, step1 = d["recommendation_id"], d["step_token"]   # R1::rerank
    _run(["continue", "--id", rid, "--result", _raw_rerank(), "--step", step1])
    # refine → R2 完成
    d = _run(["start", "--meal", "lunch", "--context", "再辣点", "--from", rid])
    d = _run(["continue", "--id", rid, "--result", _raw_intent(), "--step", d["step_token"]])
    step2r = d["step_token"]   # R2::rerank
    _run(["continue", "--id", rid, "--result", _raw_rerank(n_explore=0), "--step", step2r])
    # 用 R1 旧 token 重发 → 非最新轮, 拒绝 (不回放 R1 cards)
    d = _run(["continue", "--id", rid, "--result", _raw_rerank(), "--step", step1])
    assert d["ok"] is False and d["error"]["code"] == "ROUND_STATE"
    # 最新轮 R2 token 重发 → 仍可回放
    d = _run(["continue", "--id", rid, "--result", _raw_rerank(n_explore=0), "--step", step2r])
    assert d["ok"] and d.get("replayed") is True


def test_p1_continue_extract_idempotent_replay(cli_env):
    """codex Q3: extract 重发 (round 已经此 extract 推到 resolved) → 回放 rerank spec."""
    d = _run(["start", "--meal", "lunch", "--context", "辣"])
    rid, step = d["recommendation_id"], d["step_token"]
    _run(["continue", "--id", rid, "--result", _raw_intent(), "--step", step])
    d2 = _run(["continue", "--id", rid, "--result", _raw_intent(), "--step", step])
    assert d2["ok"] and d2.get("idempotent_replay") is True
    assert d2["do_llm"]["operation_kind"] == "rerank"


def test_p1_continue_fallback_on_bad_result(cli_env):
    """continue 路径越界 combo_index → 仍走 chisha_l2 fallback (确定性守卫不变)."""
    d = _run(["start", "--meal", "lunch"])
    rid, step = d["recommendation_id"], d["step_token"]
    bad = json.dumps({"candidates": [
        {"rank": 1, "is_explore": False, "combo_index": 999, "fit_score": 0.8,
         "taste_match": 0.7, "risk_flags": [], "one_line_reason": "x"}],
        "narrative": "x"})
    d = _run(["continue", "--id", rid, "--result", bad, "--step", step])
    assert d["ok"] and d["status"] == "ready" and d["fallback"] is True
    assert len(d["cards"]) == 5 and d["narrative"] == ""

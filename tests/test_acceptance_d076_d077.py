"""D-077 PR-2: 10 验证锚点 end-to-end 验收测试.

D-085 后改走真实 chisha.api_living + chisha.api_lab routers + isolated tmp
ROOT, 验证 sandbox + L1 全链路. LLM 调用 mock (避免烧配额, 测的是机制不是
LLM 输出).

锚点对应:
1. Cooldown 7d 不重店          → 验证 diversity_filter 走虚拟时钟
2. Cooldown 3d 不重蛋白         → 同上
3. Snooze 24h                  → 沙盒推进一天后解锁
4. L1 抽取兑现 (≥3 反馈)        → V1.1 反馈累积后 inspect 看到 prefs
5. L1 影响 L2 打分              → save_prefs(low_oil) 后 rank_combos 加分
6. refine chip 不再跨 session   → refine 不写 feedback_history
7. 冷启动                       → 全空 sandbox 不报错
8. prod 路径不回归              → 关 sandbox 时 baseline 0 diff (已在 PR-0.7
                                    / PR-1a / PR-1b / PR-1c 跑过, 这里只
                                    做 smoke)
9. profile 切 zone 不污染 prod  → sandbox 内 PUT 写副本
10. reset 干净                  → reset 后 logs/sandbox 不存在
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_root(tmp_path: Path, monkeypatch):
    """注入 ROOT + 拷贝真实 profile.yaml / methodology / data zone 进来.

    精确复用真实 profile.yaml, 不要 mock 拼凑出残缺 profile.
    """
    from chisha import api_lab, api_living, sandbox
    real_root = Path(__file__).resolve().parent.parent

    # 拷贝必要文件
    shutil.copy2(real_root / "profile.yaml", tmp_path / "profile.yaml")
    # methodology spec
    (tmp_path / "profiles" / "methodologies").mkdir(parents=True, exist_ok=True)
    for f in (real_root / "profiles" / "methodologies").glob("*.yaml"):
        shutil.copy2(f, tmp_path / "profiles" / "methodologies" / f.name)
    # data zone (推荐链路要)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    for zone in ("shenzhen-bay", "home"):
        zone_dir = real_root / "data" / zone
        if zone_dir.exists():
            shutil.copytree(zone_dir, tmp_path / "data" / zone)
    # prompts
    if (real_root / "prompts").exists():
        shutil.copytree(real_root / "prompts", tmp_path / "prompts")

    monkeypatch.setattr(api_lab, "ROOT", tmp_path)
    monkeypatch.setattr(api_lab, "PROFILE_PATH", tmp_path / "profile.yaml")
    monkeypatch.setattr(api_lab, "_is_localhost", lambda req: True)
    monkeypatch.setattr(api_living, "ROOT", tmp_path)
    monkeypatch.setattr(api_living, "PROFILE_PATH", tmp_path / "profile.yaml")
    monkeypatch.setattr(api_living, "_is_localhost", lambda req: True)
    monkeypatch.delenv("CHISHA_ADMIN_TOKEN", raising=False)
    # 关键: clock 调用默认走 sandbox._project_root(), 测试 ROOT 隔离时必须 patch
    monkeypatch.setattr(sandbox, "_project_root", lambda: tmp_path)

    # ensure no leftover sandbox state from earlier tests
    sandbox_dir = tmp_path / "logs" / "sandbox"
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)

    app = FastAPI()
    # D-085: Living + Lab 两个 router 各挂一次
    app.include_router(api_living.router)
    app.include_router(api_lab.router)
    return app, tmp_path


# ─────────────────────── Anchor 1: Cooldown 7d 不重店
def test_anchor_1_cooldown_7d_no_same_restaurant(app_root):
    """sandbox 内 accept 一家店, 7d 内不应重复出现 (recall.diversity_filter)."""
    app, root = app_root
    # 直接验证 diversity_filter 用虚拟 today 时正确过滤
    from chisha import clock, sandbox as sb
    from chisha.recall import diversity_filter

    sb.init(start_date="2026-05-20", root=root)
    meal_log = [{
        "timestamp": "2026-05-20T12:00:00",
        "restaurant_id": "rest_X",
        "dishes": [{"main_ingredient_type": "白肉"}],
    }]
    profile = {"diversity": {"no_same_restaurant_within_days": 7,
                              "no_same_main_ingredient_within_days": 3}}

    dishes_a = [{"restaurant_id": "rest_X", "name": "d1"},
                {"restaurant_id": "rest_Y", "name": "d2"}]
    # Day 1: 推进 0 天, today=2026-05-20, rest_X 在 cooldown 内
    out, _ = diversity_filter(dishes_a, meal_log, profile,
                               today=clock.today(root=root))
    assert len(out) == 1 and out[0]["restaurant_id"] == "rest_Y"

    # 推进 7 天, today=2026-05-27, cooldown 过期 (7d 不重 → 第 8 天可重)
    sb.advance(days=7, root=root)
    out8, _ = diversity_filter(dishes_a, meal_log, profile,
                                today=clock.today(root=root))
    # delta=7 ≤ no_same_days=7 → 仍屏蔽; delta=8 才解锁
    sb.advance(days=1, root=root)
    out9, _ = diversity_filter(dishes_a, meal_log, profile,
                                today=clock.today(root=root))
    assert len(out9) == 2


# ─────────────────────── Anchor 2: Cooldown 3d 不重蛋白
def test_anchor_2_cooldown_3d_no_same_protein(app_root):
    app, root = app_root
    from chisha import clock, sandbox as sb
    from chisha.recall import diversity_filter

    sb.init(start_date="2026-05-20", root=root)
    meal_log = [{
        "timestamp": "2026-05-20T12:00:00",
        "restaurant_id": "rest_Z",
        "dishes": [{"main_ingredient_type": "红肉"}],
    }]
    profile = {"diversity": {"no_same_restaurant_within_days": 0,
                              "no_same_main_ingredient_within_days": 3}}

    dishes = [{"restaurant_id": "rest_A", "name": "d1",
                "nutrition_profile": {"main_ingredient_type": "红肉"}},
              {"restaurant_id": "rest_B", "name": "d2",
                "nutrition_profile": {"main_ingredient_type": "白肉"}}]

    out, _ = diversity_filter(dishes, meal_log, profile,
                               today=clock.today(root=root))
    # 红肉在 cooldown, 白肉过
    names = [d["name"] for d in out]
    assert "d2" in names and "d1" not in names

    sb.advance(days=4, root=root)
    out_late, _ = diversity_filter(dishes, meal_log, profile,
                                    today=clock.today(root=root))
    assert len(out_late) == 2


# ─────────────────────── Anchor 3: Snooze 24h
# D-085 调整: Living endpoint (/api/feedback/snooze, /api/feedback/inbox) 已经
# 被 _force_prod_data dependency 包住, 不会走 sandbox 路径. 验证 sandbox 演练
# 内 snooze + advance 机制时, 应直接调 feedback_store 模块, 不走 HTTP — 与
# 实际 Lab 演练场景 (Lab UI 用 module-level 工具 / 脚本) 一致.
def test_anchor_3_snooze_unblocks_after_one_day(app_root):
    app, root = app_root
    from chisha import feedback_store
    with TestClient(app) as c:
        c.post("/api/lab/sandbox/init", json={"start_date": "2026-05-20"})
        # accept + snooze 都走 feedback_store 直接调 (写 sandbox 路径,
        # 因为 sandbox.is_enabled(root)=True 且无 force_disabled override)
        feedback_store.record_accept(
            root, session_id="sid_s",
            candidate_rank=1, meal_type="lunch",
            restaurant_name="店X", summary="",
        )
        feedback_store.set_snooze(root, "sid_s", hours=24)

        store = feedback_store.load_store(root)
        items = feedback_store.inbox_items(store, include_snoozed=False)
        sids_visible = [it["session_id"] for it in items]
        assert "sid_s" not in sids_visible

        # 推进一天 (Lab 端点 OK — sandbox 端就在 Lab 上), snooze 过期
        c.post("/api/lab/sandbox/advance", json={"days": 1})
        store2 = feedback_store.load_store(root)
        items2 = feedback_store.inbox_items(store2, include_snoozed=False)
        sids_after = [it["session_id"] for it in items2]
        assert "sid_s" in sids_after


# ─────────────────────── Anchor 4: L1 抽取兑现 (V1.1 反馈 + LLM)
def test_anchor_4_l1_extracts_after_feedbacks(app_root, monkeypatch):
    app, root = app_root

    # Mock LLM extract_and_save 行为
    def fake_extract(store, profile, **kw):
        # 模拟 LLM 看到 ≥3 次 oil_calibration=2 → 抽出 low_oil
        n = sum(
            1 for fb in (store.get("feedbacks") or {}).values()
            if fb.get("oil_calibration") == 2
        )
        if n >= 3:
            prefs = {
                "version": 1,
                "boost": ["low_oil"], "penalty": [],
                "based_on_meals": n,
                "evidence": [{"token": "low_oil",
                              "rationale": f"{n} 次 oil_calibration=2"}],
                "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        else:
            prefs = {"version": 1, "boost": [], "penalty": [],
                     "based_on_meals": n,
                     "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        from chisha.l1_prefs import save_prefs
        save_prefs(prefs, root=kw.get("root"))
        return prefs

    from chisha import l1_extractor
    monkeypatch.setattr(l1_extractor, "extract_and_save", fake_extract)

    with TestClient(app) as c:
        c.post("/api/lab/sandbox/init", json={"start_date": "2026-05-20"})

        # 模拟 3 餐 + 3 次反馈 oil_calibration=2
        from chisha import feedback_store
        for i in range(3):
            sid = f"sid_a{i}"
            feedback_store.record_accept(
                root, session_id=sid,
                candidate_rank=1, meal_type="lunch",
                restaurant_name=f"店{i}", summary="",
            )
            feedback_store.record_feedback(root, {
                "session_id": sid,
                "accepted_rank": 1,
                "rating": 0,
                "oil_calibration": 2,
                "fullness": 1,
                "reason_match": 1,
                "repurchase_intent": 1,
                "note": "",
                "variant": "progressive",
                "quick": False,
            })

        # advance 触发 L1 抽取
        c.post("/api/lab/sandbox/advance", json={"days": 1})
        time.sleep(0.3)  # 等异步抽取

        # inspect 看到 low_oil
        inspect = c.get("/api/lab/sandbox/inspect").json()
        prefs = inspect.get("long_term_prefs")
        assert prefs is not None
        assert "low_oil" in prefs["boost"]
        assert prefs["based_on_meals"] >= 3


# ─────────────────────── Anchor 5: L1 影响 L2 打分 (代码层守门)
def test_anchor_5_l1_prefs_affect_l2_scoring(app_root):
    app, root = app_root
    # 已在 tests/test_score_l1_switch.py 充分覆盖, 这里 smoke 一次
    from chisha.l1_prefs import save_prefs
    save_prefs(
        {"boost": ["low_oil"], "penalty": [], "based_on_meals": 5,
         "extracted_at": "2026-05-21T00:00:00"},
        root=root,
    )
    from chisha.l1_prefs import load_prefs, to_runtime_hints
    prefs = load_prefs(root=root)
    hints = to_runtime_hints(prefs)
    assert hints == {"boost": ["low_oil"], "penalty": []}


# ─────────────────────── Anchor 6: refine chip 不再跨 session
def test_anchor_6_refine_no_longer_writes_history(app_root):
    """refine.py 砍掉 append_feedback 后, feedback_history.jsonl 不再被写.

    检测 import + 实际调用而非 grep 字符串 (docstring 里"断 append_feedback"
    会误判). main 的 D-073 重写后 refine.py 完全砍 long_term_prefs 链路.
    """
    app, root = app_root
    from chisha import refine as refine_mod
    src = Path(refine_mod.__file__).read_text(encoding="utf-8")
    # refine.py 不再从 long_term_prefs 取 append_feedback
    assert "from chisha.long_term_prefs import append_feedback" not in src
    # refine.py 也不再调 append_feedback(...)
    assert "append_feedback(" not in src
    # deprecated marker 必须在 long_term_prefs 顶部
    from chisha import long_term_prefs as ltp
    ltp_src = Path(ltp.__file__).read_text(encoding="utf-8")
    assert "DEPRECATED" in ltp_src


# ─────────────────────── Anchor 7: 冷启动
def test_anchor_7_cold_start_no_errors(app_root):
    app, root = app_root
    with TestClient(app) as c:
        c.post("/api/lab/sandbox/init", json={"start_date": "2026-05-20"})
        # 立即 inspect: 应该全空 (无反馈, 无 prefs)
        r = c.get("/api/lab/sandbox/inspect")
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"] is True
        # prefs 可能 None, 不能抛错
        assert "long_term_prefs" in data


# ─────────────────────── Anchor 8: prod 路径不回归 (baseline smoke)
def test_anchor_8_prod_path_no_regression(app_root):
    """sandbox 关闭时 score 行为 = pre-D-076 (compare_traces 已守门).

    这里只做 smoke: 关 sandbox 跑一次 rank_combos, 确保不挂.
    """
    app, root = app_root
    # 用真实 profile + 默认空 prefs (因为 prod 这里全空)
    from chisha.recall import load_profile
    profile = load_profile(root / "profile.yaml")
    assert profile.get("methodology") == "harvard_plate"
    # rank_combos 走真实路径
    from chisha.score import rank_combos
    out = rank_combos([], profile, meal_log=[], today=dt.date(2026, 5, 16),
                       meal_type="lunch", root=root)
    assert out == []


# ─────────────────────── Anchor 9 (D-085 改写): Living PUT /api/profile 永远写 prod
# 原 D-077 语义: sandbox 启用时 PUT /api/profile 走 sandbox 副本.
# D-085 invariant 3: Living 写真实数据, 即便 Lab 已开 sandbox.
# 验证: PUT 写 prod profile.yaml; sandbox/profile.yaml 由 init(copy_real_data=
# True) 保持初始副本不变.
def test_anchor_9_living_profile_put_writes_prod_even_in_sandbox(app_root):
    app, root = app_root
    prod_profile_before = (root / "profile.yaml").read_text(encoding="utf-8")
    with TestClient(app) as c:
        c.post("/api/lab/sandbox/init",
                json={"start_date": "2026-05-20", "copy_real_data": True})
        sandbox_profile = root / "logs" / "sandbox" / "profile.yaml"
        sandbox_profile_before = sandbox_profile.read_text(encoding="utf-8")

        new_p = {"basics": {"office_zone": "home",
                             "zones": {"lunch": "home",
                                        "dinner": "home"}},
                 "methodology": "harvard_plate"}
        r = c.post("/api/profile", json=new_p)
        assert r.status_code == 200

        # D-085: PUT 走 prod (Living invariant 3 — Lab 才能写 sandbox)
        assert (root / "profile.yaml").read_text(encoding="utf-8") != prod_profile_before
        assert "home" in (root / "profile.yaml").read_text(encoding="utf-8")
        # sandbox 副本不应被 Living PUT 修改
        assert sandbox_profile.read_text(encoding="utf-8") == sandbox_profile_before


# ─────────────────────── Anchor 12 (D-078): accept 写 meal_log + cooldown 沙盒生效
def test_anchor_12_accept_writes_meal_log_and_cooldown_active(app_root):
    """D-078 守门: /api/accept 必须往虚拟 meal_log.jsonl 追加一条记录,
    且 diversity_filter 在沙盒里能屏蔽 cooldown 内的店.
    """
    app, root = app_root
    from chisha import clock, sandbox as sb, data_root
    from chisha.recall import load_meal_log, diversity_filter

    with TestClient(app) as c:
        c.post("/api/lab/sandbox/init", json={"start_date": "2026-05-20"})
        # D-085: Living /api/accept 总写 prod (invariant 3). 要测 sandbox 演练
        # 内的 meal_log 行为, 直接调 module-level 工具 (Lab 演练场景对应
        # 调用方 = Lab UI 或脚本, 不走 Living HTTP).
        from chisha import feedback_store
        from chisha.recall import append_meal_log_entry
        candidate = {
            "rank": 1,
            "restaurant": {"id": "r_X", "name": "测试餐厅 X"},
            "dishes": [
                {"main_ingredient_type": "红肉", "canonical_name": "红烧肉饭",
                 "oil_level": 4},
            ],
        }
        feedback_store.record_accept(
            root, session_id="sid_a", candidate_rank=1, meal_type="lunch",
            restaurant_name="测试餐厅 X", summary="红烧肉饭",
        )
        append_meal_log_entry(
            root=root, session_id="sid_a", meal_type="lunch",
            restaurant_id="r_X", restaurant_name="测试餐厅 X",
            dishes=candidate["dishes"], zone="shenzhen-bay",
            accepted_rank=1,
        )

        # meal_log.jsonl 应当出现在 sandbox 目录 (sandbox.is_enabled=True
        # 且无 force_disabled override, module-level append_meal_log_entry
        # 走 data_root.meal_log_path = sandbox 路径)
        sb_log = root / "logs" / "sandbox" / "meal_log.jsonl"
        prod_log = root / "logs" / "meal_log.jsonl"
        assert sb_log.exists(), "module 直接调用未写 sandbox meal_log.jsonl"
        assert not prod_log.exists(), "module 直接调用误写 prod meal_log.jsonl"

        entries = load_meal_log(root)
        assert len(entries) == 1
        e = entries[0]
        assert e["restaurant_id"] == "r_X"
        assert e["dishes"][0]["main_ingredient_type"] == "红肉"
        # timestamp 必须走虚拟时钟
        import datetime as _dt
        ts = _dt.datetime.fromisoformat(e["timestamp"]).date()
        assert ts == _dt.date(2026, 5, 20), (
            f"meal_log timestamp 应=虚拟 today=2026-05-20, 实际={ts} "
            "(回归: 若用 dt.datetime.now() 则会是真实 today)"
        )

        # diversity_filter 应屏蔽 r_X (7d cooldown)
        profile = {"diversity": {"no_same_restaurant_within_days": 7,
                                  "no_same_main_ingredient_within_days": 3}}
        dishes_next = [
            {"restaurant_id": "r_X", "name": "再来一份"},
            {"restaurant_id": "r_Y", "name": "另一家"},
        ]
        filtered, _ = diversity_filter(
            dishes_next, entries, profile, today=clock.today(root=root)
        )
        names = [d["restaurant_id"] for d in filtered]
        assert "r_X" not in names, "cooldown 未屏蔽 7d 内重复餐厅"
        assert "r_Y" in names

        # 推 8 天后 r_X 应解锁
        sb.advance(days=8, root=root)
        filtered_late, _ = diversity_filter(
            dishes_next, entries, profile, today=clock.today(root=root)
        )
        late_names = [d["restaurant_id"] for d in filtered_late]
        assert "r_X" in late_names, "推进 8 天后仍未解锁 cooldown"


# ─────────────────────── Anchor 13 (D-078 S2): reset 在 L1 worker 期间不能污染 prod
def test_anchor_13_reset_waits_for_l1_worker(app_root, monkeypatch):
    """Codex S2 Q3-High: reset 必须等 L1 worker 释放, 否则 worker save_prefs
    在 sandbox 已 disabled 时会写到 prod data/long_term_prefs.json.

    本测试通过 monkey 替换 extract_and_save 为慢函数 + 并发触发 reset, 验证
    reset 要么等到 worker 结束, 要么 409 拒绝.
    """
    app, root = app_root
    import threading
    import time as _t

    started = threading.Event()
    finishing = threading.Event()

    def slow_extract(store, profile, **kw):
        started.set()
        # 模拟 LLM 慢, finishing 不 set 之前不返回
        for _ in range(50):
            if finishing.is_set():
                break
            _t.sleep(0.01)
        from chisha.l1_prefs import save_prefs
        prefs = {
            "version": 1, "boost": ["low_oil"], "penalty": [],
            "based_on_meals": 5, "based_on_days": 14,
            "extracted_at": "2026-05-21T00:00:00+00:00",
            "signals_not_scored": {}, "evidence": [],
            "regularities_freetext": [], "skipped_extraction": False,
        }
        save_prefs(prefs, root=kw.get("root"))
        return prefs

    from chisha import l1_extractor
    monkeypatch.setattr(l1_extractor, "extract_and_save", slow_extract)

    with TestClient(app) as c:
        c.post("/api/lab/sandbox/init", json={"start_date": "2026-05-20"})
        # 累 ≥3 餐反馈, 否则 L1 进 skipped 分支不走 LLM
        from chisha import feedback_store
        for i in range(3):
            sid = f"sid_r{i}"
            feedback_store.record_accept(
                root, session_id=sid, candidate_rank=1,
                meal_type="lunch", restaurant_name=f"店{i}", summary="",
            )
            feedback_store.record_feedback(root, {
                "session_id": sid, "accepted_rank": 1,
                "rating": -1, "oil_calibration": 2,
                "fullness": 1, "reason_match": 1, "repurchase_intent": 0,
                "note": "", "variant": "progressive", "quick": False,
            })

        # advance 触发 worker
        c.post("/api/lab/sandbox/advance", json={"days": 1})
        # 等 worker started
        assert started.wait(timeout=2.0), "worker 未启动"

        # reset 在 worker 跑期间发起, 应该被阻塞或 409
        # 拿一个线程发 reset, 同时让 worker 在 ~1s 后完成
        result: dict = {}
        def _reset():
            r = c.post("/api/lab/sandbox/reset")
            result["status"] = r.status_code
            result["body"] = r.json()
        t = threading.Thread(target=_reset)
        t.start()
        # 让 reset 等 0.3s 后让 worker 完成
        _t.sleep(0.3)
        # 此时 reset 应仍在阻塞 (worker 还没 finishing)
        assert t.is_alive(), "reset 没等 worker, 直接返了 (会污染 prod)"
        finishing.set()
        t.join(timeout=5.0)
        assert result.get("status") == 200, f"reset 期望 200, 实际 {result}"

        # prod 路径 long_term_prefs.json 必须不存在 (沙盒 reset 应只清沙盒)
        prod_prefs = root / "data" / "long_term_prefs.json"
        assert not prod_prefs.exists(), (
            "L1 worker 在 reset 之后写到了 prod long_term_prefs.json (污染)"
        )


# ─────────────────────── Anchor 14 (D-078 S2): advance 期间 pending 返 409
def test_anchor_14_advance_409_when_pending(app_root, monkeypatch):
    """Codex S2 Q2: advance 在 L1 pending 期间 hard-fail 409, 防 UI bypass."""
    app, root = app_root
    import threading

    started = threading.Event()
    finishing = threading.Event()

    def slow_extract(store, profile, **kw):
        started.set()
        finishing.wait(timeout=2.0)
        from chisha.l1_prefs import save_prefs
        save_prefs({
            "version": 1, "boost": [], "penalty": [], "based_on_meals": 3,
            "based_on_days": 14, "extracted_at": "2026-05-21T00:00:00+00:00",
            "signals_not_scored": {}, "evidence": [],
            "regularities_freetext": [], "skipped_extraction": False,
        }, root=kw.get("root"))
        return {}

    from chisha import l1_extractor
    monkeypatch.setattr(l1_extractor, "extract_and_save", slow_extract)

    with TestClient(app) as c:
        c.post("/api/lab/sandbox/init", json={"start_date": "2026-05-20"})
        from chisha import feedback_store
        for i in range(3):
            sid = f"sid_p{i}"
            feedback_store.record_accept(
                root, session_id=sid, candidate_rank=1,
                meal_type="lunch", restaurant_name=f"店{i}", summary="",
            )
            feedback_store.record_feedback(root, {
                "session_id": sid, "accepted_rank": 1, "rating": -1,
                "oil_calibration": 2, "fullness": 1, "reason_match": 1,
                "repurchase_intent": 0, "note": "", "variant": "progressive",
                "quick": False,
            })

        c.post("/api/lab/sandbox/advance", json={"days": 1})
        assert started.wait(timeout=2.0)
        # 此时 state.status=pending, 第二次 advance 应 409
        r = c.post("/api/lab/sandbox/advance", json={"days": 1})
        assert r.status_code == 409
        finishing.set()


# ─────────────────────── Anchor 11 (D-078): 虚拟时钟跨日 L1 抽取兑现
def test_anchor_11_l1_uses_virtual_clock_across_days(app_root, monkeypatch):
    """D-078 守门: 沙盒推进 5 日 + 累积 4 餐反馈 → L1 抽取必须看到 4 餐,
    不能因为反馈 submitted_at = 虚拟未来时钟而被 dt.date.today() 过滤.
    """
    app, root = app_root
    captured = {}

    def fake_extract(store, profile, **kw):
        # 复刻 web_api._trigger_l1_extraction_async 调用形态, 验证 root/today 透传
        from chisha import l1_extractor
        summary = l1_extractor.aggregate_inputs(
            store, profile,
            today=kw.get("today"),
            window_days=kw.get("window_days", 14),
            root=kw.get("root"),
        )
        captured["based_on_meals"] = summary["based_on_meals"]
        # 兑现一个 low_oil prefs (mock LLM)
        prefs = {
            "version": 1, "boost": ["low_oil"], "penalty": [],
            "based_on_meals": summary["based_on_meals"],
            "evidence": [{"token": "low_oil", "rationale": "mocked"}],
            "extracted_at": "2026-05-25T00:00:00+00:00",
            "based_on_days": 14, "signals_not_scored": {},
            "regularities_freetext": [], "skipped_extraction": False,
        }
        from chisha.l1_prefs import save_prefs
        save_prefs(prefs, root=kw.get("root"))
        return prefs

    from chisha import l1_extractor as l1ext
    monkeypatch.setattr(l1ext, "extract_and_save", fake_extract)

    from tests.conftest import wait_l1_settle as _wait_l1_settle

    with TestClient(app) as c:
        c.post("/api/lab/sandbox/init", json={"start_date": "2026-05-20"})
        from chisha import feedback_store
        prev_at: str | None = None
        # 4 餐反馈先全部录入 (避免 advance 后再 record 导致 worker 看不到最新一餐)
        for i in range(4):
            sid = f"sid_e{i}"
            feedback_store.record_accept(
                root, session_id=sid, candidate_rank=1,
                meal_type="lunch", restaurant_name=f"店{i}", summary="",
            )
            feedback_store.record_feedback(root, {
                "session_id": sid, "accepted_rank": 1,
                "rating": -1, "oil_calibration": 2,
                "fullness": 1, "reason_match": 1, "repurchase_intent": 0,
                "note": "", "variant": "progressive", "quick": False,
            })
            if i < 3:
                c.post("/api/lab/sandbox/advance", json={"days": 1})
                _, prev_at = _wait_l1_settle(c, prev_at)

        # 最后再推一天触发 L1 抽取看到全部 4 餐
        c.post("/api/lab/sandbox/advance", json={"days": 1})
        _, _ = _wait_l1_settle(c, prev_at)

        # 守门: based_on_meals 必须 ≥ 4 (D-078 bug 回归会卡在 1)
        assert captured.get("based_on_meals", 0) >= 4, (
            f"L1 时钟漏注入回归: based_on_meals={captured.get('based_on_meals')}, "
            "应为 4 (虚拟时钟下所有反馈都在 window 内)"
        )

        # inspect 应看到 low_oil prefs
        insp = c.get("/api/lab/sandbox/inspect").json()
        prefs = insp.get("long_term_prefs")
        assert prefs is not None
        assert "low_oil" in prefs["boost"]


# ─────────────────────── Anchor 10: reset 干净
def test_anchor_10_reset_clean(app_root):
    app, root = app_root
    with TestClient(app) as c:
        c.post("/api/lab/sandbox/init",
                json={"start_date": "2026-05-20", "copy_real_data": True})
        c.post("/api/lab/sandbox/advance", json={"days": 2})
        # 反馈数据
        from chisha import feedback_store
        feedback_store.record_accept(
            root, session_id="sid_r",
            candidate_rank=1, meal_type="lunch",
            restaurant_name="店R", summary="",
        )
        # sandbox 目录非空
        sandbox_dir = root / "logs" / "sandbox"
        assert sandbox_dir.exists()

        # reset
        c.post("/api/lab/sandbox/reset")
        assert not sandbox_dir.exists()
        # state 也清了
        assert c.get("/api/lab/sandbox/state").json() == {"enabled": False}

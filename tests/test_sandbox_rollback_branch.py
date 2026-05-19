"""S-07: rollback / branch 端点 + 原子裁剪 + FullSnapshot GET + per-sid op lock.

全程 mock_recommend=1 + 测试自己 seed 真 trace 文件 / meal_log / recommend_log 行
让 rollback 真删 (mock /eat 不写 meal_log, mock /recs 不写 trace 文件).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_sandbox(tmp_path: Path, monkeypatch):
    from chisha import web_api
    monkeypatch.setattr(web_api, "ROOT", tmp_path)
    monkeypatch.setattr(web_api, "PROFILE_PATH", tmp_path / "profile.yaml")
    monkeypatch.setattr(web_api, "_is_localhost", lambda req: True)
    (tmp_path / "profile.yaml").write_text(
        "methodology: harvard_plate\nbasics: {office_zone: shenzhen-bay}\nllm: {provider: auto}\n",
        encoding="utf-8",
    )
    # 清 in-memory job table + per-sid lock registry
    web_api._JOB_TABLE.clear()
    web_api._SESSION_OP_LOCK_REGISTRY.clear()
    app = FastAPI()
    app.include_router(web_api.router)
    return app, tmp_path


def _bootstrap(c: TestClient, sid: str = "s1", days: int = 7) -> dict:
    c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
    r = c.post("/api/sandbox/sessions", json={"sid": sid, "days": days})
    assert r.status_code == 201, r.text
    return r.json()


def _eat_n(c: TestClient, sid: str, n: int) -> list[str]:
    """跑 n 顿 mock-eat. 返每顿的 recommend_session_id (用于 seed trace)."""
    tsids = []
    for _ in range(n):
        rr = c.post(f"/api/sandbox/sessions/{sid}/recs?mock_recommend=1", json={})
        assert rr.status_code == 200, rr.text
        tsid = rr.json()["recommend_session_id"]
        tsids.append(tsid)
        er = c.post(f"/api/sandbox/sessions/{sid}/eat", json={"rec_rank": 1})
        assert er.status_code == 200, er.text
    return tsids


def _seed_trace_and_log(root: Path, sid: str, tsids: list[str]) -> None:
    """对每个 tsid 写 fake trace 文件 + meal_log / recommend_log 行 (含 session_id)."""
    bucket = root / "logs" / "sandbox" / "sessions" / sid
    trace_dir = bucket / "recommend_trace"
    trace_dir.mkdir(parents=True, exist_ok=True)
    meal_log_p = bucket / "meal_log.jsonl"
    recommend_log_p = bucket / "recommend_log.jsonl"
    ml_lines = []
    rl_lines = []
    for i, tsid in enumerate(tsids):
        # v2 单文件 trace
        (trace_dir / f"{tsid}.json").write_text(
            json.dumps({"session_id": tsid, "meal_idx": i, "fake": True}),
            encoding="utf-8",
        )
        ml_lines.append(json.dumps({"session_id": tsid, "meal_idx": i, "marker": "ml"}))
        rl_lines.append(json.dumps({"session_id": tsid, "meal_idx": i, "marker": "rl"}))
    meal_log_p.write_text("\n".join(ml_lines) + "\n", encoding="utf-8")
    recommend_log_p.write_text("\n".join(rl_lines) + "\n", encoding="utf-8")


# ────────────────────────── 1. rollback truncates full

def test_rollback_truncates_full(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        tsids = _eat_n(c, "s1", 4)
        _seed_trace_and_log(root, "s1", tsids)
        # seed last_recs (mock /recs after eat 已清, 再调一次模拟用户在 idx=4 拉了下一顿)
        r = c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
        assert r.status_code == 200

        # rollback to 2
        rr = c.post("/api/sandbox/sessions/s1/rollback", json={"meal_idx": 2})
        assert rr.status_code == 200, rr.text
        snap = rr.json()
        assert snap["meta"]["currentMealIdx"] == 2
        assert len(snap["history"]) == 2

    bucket = root / "logs/sandbox/sessions/s1"
    state = json.loads((bucket / "state.json").read_text())
    assert state["current_meal_idx"] == 2
    assert state["day_index"] == 2   # idx=2 → day 2
    assert state["last_l1_extraction"] is None

    m2t = json.loads((bucket / "meal_to_trace.json").read_text())
    assert set(m2t.keys()) == {"0", "1"}

    hist = json.loads((bucket / "history.json").read_text())
    assert len(hist) == 2

    # decisions/{0,1} 留, decisions/{2,3} 删
    dec_dir = bucket / "decisions"
    if dec_dir.exists():
        assert not (dec_dir / "2.json").exists()
        assert not (dec_dir / "3.json").exists()

    # last_recs 删
    assert not (bucket / "last_recs.json").exists()

    # long_term_prefs 清空
    ltp = bucket / "long_term_prefs.json"
    assert ltp.exists() and json.loads(ltp.read_text()) == {}

    # trace 文件: idx>=2 的删, idx<2 的留
    trace_dir = bucket / "recommend_trace"
    assert not (trace_dir / f"{tsids[2]}.json").exists()
    assert not (trace_dir / f"{tsids[3]}.json").exists()
    assert (trace_dir / f"{tsids[0]}.json").exists()
    assert (trace_dir / f"{tsids[1]}.json").exists()

    # meal_log 仅剩 idx<2 (按 session_id 过滤)
    ml = (bucket / "meal_log.jsonl").read_text().splitlines()
    sids_in_ml = [json.loads(line)["session_id"] for line in ml if line.strip()]
    assert tsids[0] in sids_in_ml and tsids[1] in sids_in_ml
    assert tsids[2] not in sids_in_ml and tsids[3] not in sids_in_ml

    rl = (bucket / "recommend_log.jsonl").read_text().splitlines()
    sids_in_rl = [json.loads(line)["session_id"] for line in rl if line.strip()]
    assert tsids[2] not in sids_in_rl and tsids[3] not in sids_in_rl

    # .rollback_tmp 清干净
    assert not (bucket / ".rollback_tmp").exists()


# ────────────────────────── 2. invalid idx

def test_rollback_invalid_idx(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        _eat_n(c, "s1", 2)
        # negative → 422 pydantic
        assert c.post("/api/sandbox/sessions/s1/rollback", json={"meal_idx": -1}).status_code == 422
        # == cur → 400
        assert c.post("/api/sandbox/sessions/s1/rollback", json={"meal_idx": 2}).status_code == 400
        # > cur → 400
        assert c.post("/api/sandbox/sessions/s1/rollback", json={"meal_idx": 5}).status_code == 400


# ────────────────────────── 3. default sid rejected

def test_rollback_default_sid_400(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        c.post("/api/sandbox/init", json={"start_date": "2026-05-20"})
        r = c.post("/api/sandbox/sessions/_default/rollback", json={"meal_idx": 0})
    assert r.status_code == 400


# ────────────────────────── 4. unknown sid 404

def test_rollback_unknown_sid_404(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        r = c.post("/api/sandbox/sessions/ghost/rollback", json={"meal_idx": 0})
    assert r.status_code == 404


# ────────────────────────── 5. rollback then eat: no old trace leak (Codex gotcha #1)

def test_rollback_then_eat_no_trace_leak(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        tsids_pre = _eat_n(c, "s1", 4)
        _seed_trace_and_log(root, "s1", tsids_pre)
        c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})

        rr = c.post("/api/sandbox/sessions/s1/rollback", json={"meal_idx": 2})
        assert rr.status_code == 200

        # 再 eat 1 顿 (idx=2 这一顿)
        r = c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
        new_tsid = r.json()["recommend_session_id"]
        er = c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 1})
        assert er.status_code == 200

    bucket = root / "logs/sandbox/sessions/s1"
    m2t = json.loads((bucket / "meal_to_trace.json").read_text())
    # idx=2 应该是新 tsid, 不是老 tsids_pre[2]
    assert m2t.get("2") == new_tsid
    assert m2t.get("2") != tsids_pre[2]


# ────────────────────────── 6. branch copies + truncates (含 .rollback_tmp ignore)

def test_branch_copies_and_truncates(app_with_sandbox):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        tsids = _eat_n(c, "s1", 4)
        _seed_trace_and_log(root, "s1", tsids)

        # 在 src 里手工建 .rollback_tmp 残留 (Codex iter 1 #5)
        src_bucket = root / "logs/sandbox/sessions/s1"
        (src_bucket / ".rollback_tmp").mkdir()
        (src_bucket / ".rollback_tmp" / "garbage.txt").write_text("stale", encoding="utf-8")

        br = c.post("/api/sandbox/sessions/s1/branch",
                    json={"from_meal_idx": 2, "name": "alt"})
        assert br.status_code == 200, br.text
        meta = br.json()
        new_sid = meta["sid"]
        assert new_sid.startswith("sandbox_")
        assert meta["is_default"] is False
        assert meta["has_state"] is True

        # new bucket 在 list
        listed = c.get("/api/sandbox/sessions").json()["sessions"]
        sids = [s["sid"] for s in listed]
        assert new_sid in sids

        # GET FullSnapshot of new
        gs = c.get(f"/api/sandbox/sessions/{new_sid}")
        assert gs.status_code == 200, gs.text
        new_snap = gs.json()
        assert new_snap["meta"]["currentMealIdx"] == 2
        assert new_snap["meta"]["branchFrom"] == "s1"
        assert new_snap["meta"]["name"] == "alt"
        assert len(new_snap["history"]) == 2

    new_bucket = root / "logs/sandbox/sessions" / new_sid
    new_state = json.loads((new_bucket / "state.json").read_text())
    assert new_state["sid"] == new_sid
    assert new_state["branch_from"] == "s1"
    assert new_state["branch_from_meal_idx"] == 2
    assert new_state["name"] == "alt"
    assert new_state["current_meal_idx"] == 2

    # .rollback_tmp 没被拷过来
    assert not (new_bucket / ".rollback_tmp").exists()

    # src 不变
    src_state = json.loads((src_bucket / "state.json").read_text())
    assert src_state["current_meal_idx"] == 4


# ────────────────────────── 7. atomicity: failure mid-replace

def test_atomic_failure_mid_replace(app_with_sandbox, monkeypatch):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        tsids = _eat_n(c, "s1", 4)
        _seed_trace_and_log(root, "s1", tsids)
        c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})

        bucket = root / "logs/sandbox/sessions/s1"
        state_before = (bucket / "state.json").read_text()
        m2t_before = (bucket / "meal_to_trace.json").read_text()
        hist_before = (bucket / "history.json").read_text()

        # monkey-patch _os.replace 在第 4 次调用 raise (覆盖 commit 中段)
        from chisha import web_api
        orig_replace = web_api._os.replace
        call_count = {"n": 0}

        def boom_replace(src, dst):
            call_count["n"] += 1
            if call_count["n"] == 4:
                raise OSError("simulated failure mid-rollback")
            return orig_replace(src, dst)

        monkeypatch.setattr(web_api._os, "replace", boom_replace)

        r = c.post("/api/sandbox/sessions/s1/rollback", json={"meal_idx": 2})
        # 500 (内部异常向上)
        assert r.status_code == 500

    # state.json 未动
    assert (bucket / "state.json").read_text() == state_before
    # 之前 replace 的 meal_to_trace.json 已 restore
    assert (bucket / "meal_to_trace.json").read_text() == m2t_before
    assert (bucket / "history.json").read_text() == hist_before
    # .rollback_tmp 清干净
    assert not (bucket / ".rollback_tmp").exists()


# ────────────────────────── 8. atomicity: failure mid-delete

def test_atomic_failure_mid_delete(app_with_sandbox, monkeypatch):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        tsids = _eat_n(c, "s1", 4)
        _seed_trace_and_log(root, "s1", tsids)
        c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})

        bucket = root / "logs/sandbox/sessions/s1"
        last_recs_before = (bucket / "last_recs.json").read_text()
        state_before = (bucket / "state.json").read_text()

        from chisha import web_api
        orig_replace = web_api._os.replace
        call_count = {"n": 0}

        def boom_replace(src, dst):
            call_count["n"] += 1
            # 第 8 次调 raise — 大概率落在 delete kind 备份阶段
            if call_count["n"] == 8:
                raise OSError("simulated mid-delete failure")
            return orig_replace(src, dst)

        monkeypatch.setattr(web_api._os, "replace", boom_replace)

        r = c.post("/api/sandbox/sessions/s1/rollback", json={"meal_idx": 2})
        assert r.status_code == 500

    # state.json + last_recs 都未动
    assert (bucket / "state.json").read_text() == state_before
    assert (bucket / "last_recs.json").exists()
    assert (bucket / "last_recs.json").read_text() == last_recs_before
    assert not (bucket / ".rollback_tmp").exists()


# ────────────────────────── 9. GET FullSnapshot basic

def test_get_full_snapshot_basic(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        c.post("/api/sandbox/sessions/s1/recs?mock_recommend=1", json={})
        c.post("/api/sandbox/sessions/s1/eat", json={"rec_rank": 1})

        r = c.get("/api/sandbox/sessions/s1")
        assert r.status_code == 200, r.text
        snap = r.json()
        assert snap["meta"]["sid"] == "s1"
        assert snap["meta"]["currentMealIdx"] == 1
        assert snap["meta"]["totalMeals"] == 14
        assert snap["clock"]["idx"] == 1
        assert snap["clock"]["slot"] == "dinner"   # idx=1 → dinner
        assert snap["clock"]["day"] == 1
        assert len(snap["history"]) == 1
        # taste/keywords/recent/fatigue 空 list 占位
        assert snap["taste"] == []
        assert snap["keywords"] == []
        assert snap["recent"] == []
        assert snap["fatigue"] == []
        # lastDecision 可能 None (BG task 异步, 测试不等)


# ────────────────────────── 10. GET unknown sid

def test_get_full_snapshot_unknown_sid_404(app_with_sandbox):
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        r = c.get("/api/sandbox/sessions/ghost")
    assert r.status_code == 404


# ────────────────────────── 11b. rollback also clears uneaten last_recs D-039 + trace files
# (Phase 4 Codex iter 1 #2 + #4)


def test_rollback_clears_uneaten_recs_artifacts(app_with_sandbox):
    """User did /recs (creating D-039 session file + trace + log) but didn't /eat.
    Rollback must delete those D-039/trace artifacts so branch doesn't inherit them."""
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        # 2 个 mock-eat (idx=0,1)
        eaten_tsids = _eat_n(c, "s1", 2)
        _seed_trace_and_log(root, "s1", eaten_tsids)

        # 模拟 idx=2 一次"真实" /recs (uneaten): 手工写 fake last_recs.json + D-039 + trace
        bucket = root / "logs/sandbox/sessions/s1"
        future_sid = "real_session_X"
        last_recs_p = bucket / "last_recs.json"
        last_recs_p.write_text(json.dumps({
            "recommend_session_id": future_sid,
            "candidates": [{"id": "r1"}],
            "currentRecs": [],
            "applied_refine": None,
            "meal_idx": 2,
            "is_mock": False,
            "saved_at": "2026-05-20T12:00:00Z",
        }), encoding="utf-8")

        # D-039 session file (sandbox-aware nested path)
        d039_dir = bucket / "sessions"   # logs/sandbox/sessions/s1/sessions/
        d039_dir.mkdir(parents=True, exist_ok=True)
        d039_file = d039_dir / f"{future_sid}.json"
        d039_file.write_text(json.dumps({"sid": future_sid, "fake": True}), encoding="utf-8")

        # trace 文件 (v2 单文件 + v3 dir)
        trace_dir = bucket / "recommend_trace"
        trace_dir.mkdir(parents=True, exist_ok=True)
        (trace_dir / f"{future_sid}.json").write_text(
            json.dumps({"sid": future_sid}), encoding="utf-8",
        )
        v3_dir = trace_dir / future_sid
        v3_dir.mkdir(exist_ok=True)
        (v3_dir / "meta.json").write_text(json.dumps({"sid": future_sid}), encoding="utf-8")

        # rollback to 1
        rr = c.post("/api/sandbox/sessions/s1/rollback", json={"meal_idx": 1})
        assert rr.status_code == 200, rr.text

    # 验: 全部 future artifacts 都删
    assert not (bucket / "last_recs.json").exists()
    assert not d039_file.exists()
    assert not (trace_dir / f"{future_sid}.json").exists()
    assert not v3_dir.exists()
    # 已 eaten 的 idx=0 trace 仍在
    assert (trace_dir / f"{eaten_tsids[0]}.json").exists()


# ────────────────────────── 11c. OSError reading meal_log → rollback 500 + state unchanged
# (Phase 4 Codex iter 2 WARN: regression-test the _filter_jsonl_by_session_ids OSError path)


def test_rollback_oserror_on_log_read_no_state_change(app_with_sandbox, monkeypatch):
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        tsids = _eat_n(c, "s1", 2)
        _seed_trace_and_log(root, "s1", tsids)

        bucket = root / "logs/sandbox/sessions/s1"
        state_before = (bucket / "state.json").read_text()
        meal_log_before = (bucket / "meal_log.jsonl").read_text()

        # Monkey-patch Path.read_text 在读 meal_log.jsonl 时 raise OSError
        from pathlib import Path as _P
        orig_read_text = _P.read_text

        def boom_read_text(self, *args, **kwargs):
            if self.name == "meal_log.jsonl" and "sandbox/sessions/s1" in str(self):
                raise OSError("simulated read failure")
            return orig_read_text(self, *args, **kwargs)

        monkeypatch.setattr(_P, "read_text", boom_read_text)

        r = c.post("/api/sandbox/sessions/s1/rollback", json={"meal_idx": 1})

    # 还原 patch 让后续断言能读文件
    monkeypatch.undo()
    assert r.status_code == 500
    # state.json 完全没动 (failure before commit phase)
    assert (bucket / "state.json").read_text() == state_before
    # meal_log.jsonl 没被替换为空 (失败时不写 staged file)
    assert (bucket / "meal_log.jsonl").read_text() == meal_log_before
    # .rollback_tmp 已清
    assert not (bucket / ".rollback_tmp").exists()


# ────────────────────────── 11d. reset/disable hold L1 lock through mutation
# (Phase 4 Codex iter 3 #1: reset/disable lifecycle 必须持 _L1_EXTRACTION_LOCK 整个 mutation)


def test_reset_blocked_by_l1_lock_held(app_with_sandbox):
    """模拟 BG worker 持 _L1_EXTRACTION_LOCK → reset 30s 抢不到 → 409."""
    app, _ = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        from chisha import web_api

        # 手工持 _L1_EXTRACTION_LOCK 模拟 BG worker 占用
        held = threading.Event()
        release = threading.Event()

        def holder():
            with web_api._L1_EXTRACTION_LOCK:
                held.set()
                release.wait(timeout=10)

        # short timeout 让测试快
        orig_secs = web_api._L1_LOCK_WAIT_SECONDS
        web_api._L1_LOCK_WAIT_SECONDS = 0.3
        try:
            t = threading.Thread(target=holder, daemon=True)
            t.start()
            held.wait(timeout=2)

            r = c.post("/api/sandbox/reset")
            r_d = c.post("/api/sandbox/disable")
        finally:
            release.set()
            t.join(timeout=2)
            web_api._L1_LOCK_WAIT_SECONDS = orig_secs

    assert r.status_code == 409, r.text
    assert "blocked" in r.json()["detail"].lower()
    assert r_d.status_code == 409


def test_reset_holds_l1_lock_through_mutation(app_with_sandbox):
    """正向: 没人持 L1 lock 时 reset 成功 + L1 lock 在 reset 期间被 hold (无法 acquire)."""
    app, _ = app_with_sandbox
    from chisha import web_api

    observed_locked_during_reset = []

    orig_reset = web_api._sandbox.reset

    def reset_with_probe(*args, **kwargs):
        # 在 _sandbox.reset() 内部 (持锁中) probe L1 lock — 应抢不到
        ok = web_api._L1_EXTRACTION_LOCK.acquire(blocking=False)
        observed_locked_during_reset.append(ok)
        if ok:
            web_api._L1_EXTRACTION_LOCK.release()
        return orig_reset(*args, **kwargs)

    with TestClient(app) as c:
        _bootstrap(c)
        with patch.object(web_api._sandbox, "reset", side_effect=reset_with_probe):
            r = c.post("/api/sandbox/reset")

    assert r.status_code == 200
    # 期望: lock 被 hold (ok=False), 即不应该被 acquire 到
    assert observed_locked_during_reset == [False], (
        f"L1 lock should be held during reset; got {observed_locked_during_reset}"
    )


# ────────────────────────── 12. rollback blocked by op lock (in-flight)

def test_rollback_blocked_by_op_lock(app_with_sandbox, monkeypatch):
    """模拟 BG task / 其他 op 持 lock → rollback 30s 抢不到 → 409.

    手工持锁 + 短化 timeout 让测试 fast (~0.5s).
    """
    app, root = app_with_sandbox
    with TestClient(app) as c:
        _bootstrap(c)
        _eat_n(c, "s1", 2)

        from chisha import web_api
        # Short timeout via monkey-patch __defaults__ of helper not easy; 简单做法:
        # 用 short-circuit 直接监视调用. 改包装函数让 timeout 变 0.3.
        orig = web_api._session_op_lock

        def short_lock(routed_sid, *, timeout=30.0, action="op"):
            return orig(routed_sid, timeout=0.3 if timeout == 30.0 else timeout, action=action)

        monkeypatch.setattr(web_api, "_session_op_lock", short_lock)

        # 持有 s1 锁 in another thread
        held = threading.Event()
        release = threading.Event()

        def holder():
            lock = web_api._get_session_op_lock("s1")
            lock.acquire()
            held.set()
            release.wait(timeout=10)
            lock.release()

        t = threading.Thread(target=holder, daemon=True)
        t.start()
        held.wait(timeout=2)

        r = c.post("/api/sandbox/sessions/s1/rollback", json={"meal_idx": 1})
        release.set()
        t.join(timeout=2)

    assert r.status_code == 409
    assert "busy" in r.json().get("detail", "").lower()

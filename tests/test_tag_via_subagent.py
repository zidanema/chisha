"""scripts.tag_via_subagent 单测.

策略: monkeypatch ROOT/JOBS_ROOT/FAILURES_LOG 指向 tmp_path, 避免污染真实数据.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import tag_via_subagent as tvs


# ---------------- fixtures ----------------

def _restaurants(n_rest: int = 2) -> list[dict]:
    return [
        {"id": f"r_{i:03d}", "name": f"店{i}", "category": "湘菜",
         "city": "深圳", "office_zone": "test"}
        for i in range(1, n_rest + 1)
    ]


def _raw_dishes(n: int, rest_id: str = "r_001") -> list[dict]:
    return [
        {"dish_id": f"d_001_{i:03d}", "restaurant_id": rest_id,
         "raw_name": f"菜{i}", "price": 20.0 + i, "monthly_sales": 50,
         "category_raw": None}
        for i in range(1, n + 1)
    ]


def _tagged_payload(dish_id: str) -> dict:
    """subagent 输出 (.out.json 一条) 应有的字段 (v3, D-032 含 5 新字段)."""
    return {
        "dish_id": dish_id,
        "canonical_name": "测试",
        "cuisine": "湘菜",
        "main_ingredient_type": "红肉",
        "cooking_method": "煮",
        "oil_level": 2,
        "protein_grams_estimate": 30,
        "vegetable_ratio_estimate": 0.2,
        "is_complete_meal": False,
        "spicy_level": 1,
        "dish_role": "主菜",
        "processed_meat_flag": False,
        "sweet_sauce_level": 0,
        "wetness": 2,
        "grain_type": "无",
        "tags": ["高蛋白"],
    }


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch) -> Path:
    """指向 tmp_path 的沙盒, 包含 data/ + .claude/tag_jobs/ + logs/."""
    monkeypatch.setattr(tvs, "ROOT", tmp_path)
    monkeypatch.setattr(tvs, "JOBS_ROOT", tmp_path / ".claude" / "tag_jobs")
    monkeypatch.setattr(tvs, "FAILURES_LOG",
                        tmp_path / "logs" / "tag_failures.jsonl")
    (tmp_path / "data").mkdir()
    return tmp_path


def _seed_zone(
    sandbox: Path,
    zone: str,
    raw_count: int,
    tagged: list[dict] | None = None,
) -> None:
    base = sandbox / "data" / zone
    base.mkdir(parents=True, exist_ok=True)
    (base / "restaurants.json").write_text(
        json.dumps(_restaurants()), encoding="utf-8"
    )
    (base / "dishes_raw.json").write_text(
        json.dumps(_raw_dishes(raw_count)), encoding="utf-8"
    )
    if tagged is not None:
        (base / "dishes_tagged.json").write_text(
            json.dumps(tagged), encoding="utf-8"
        )


# ---------------- prepare ----------------

def test_prepare_splits_into_batches_of_default_size(sandbox):
    """默认 batch_size=50 (DESIGN §3.5 上限). 120 → 3 批 (50+50+20)."""
    _seed_zone(sandbox, "z1", raw_count=120)
    m = tvs.prepare_zone("z1")
    assert m["stats"]["delta_to_tag"] == 120
    assert m["stats"]["batches"] == 3
    assert len(m["batches"]) == 3
    assert len(m["batches"][0]["dish_ids"]) == 50
    assert len(m["batches"][1]["dish_ids"]) == 50
    assert len(m["batches"][2]["dish_ids"]) == 20
    # in_path 文件落地
    for b in m["batches"]:
        in_p = sandbox / b["in_path"]
        assert in_p.exists()
        data = json.loads(in_p.read_text())
        assert len(data) == len(b["dish_ids"])
        # 必须把 price 喂进去 (DESIGN §4.1)
        assert all("price" in d and d["price"] > 0 for d in data)


def test_prepare_custom_batch_size_30(sandbox):
    """显式 --batch 30 仍可用 (向后兼容)."""
    _seed_zone(sandbox, "z1", raw_count=70)
    m = tvs.prepare_zone("z1", batch_size=30)
    assert m["stats"]["batches"] == 3  # 30+30+10
    assert len(m["batches"][0]["dish_ids"]) == 30
    assert len(m["batches"][2]["dish_ids"]) == 10


def test_prepare_increment_skips_tagged_ids(sandbox):
    """已 tagged 的 dish_id 不应进入 delta."""
    _seed_zone(sandbox, "z1", raw_count=10, tagged=[
        {"dish_id": "d_001_001", "restaurant_id": "r_001",
         "raw_name": "x", "canonical_name": "x", "price": 10.0,
         "monthly_sales": 0, "cuisine": "湘菜",
         "nutrition_profile": {
             "main_ingredient_type": "红肉", "cooking_method": "煮",
             "oil_level": 2, "protein_grams_estimate": 10,
             "vegetable_ratio_estimate": 0.1, "is_complete_meal": False,
             "spicy_level": 0, "tags": [],
         },
         "metadata": {
             "tagged_at": "2026-05-11T00:00:00",
             "tag_version": "v1-claude-code", "is_available": True,
         }}
    ])
    m = tvs.prepare_zone("z1")
    # 10 raw - 1 tagged = 9 delta = 1 批 (≤30)
    assert m["stats"]["delta_to_tag"] == 9
    assert m["stats"]["batches"] == 1
    assert "d_001_001" not in m["batches"][0]["dish_ids"]


def test_prepare_force_version_treats_all_as_stale(sandbox):
    """--force-version: 所有现有 tagged 视为待重打."""
    _seed_zone(sandbox, "z1", raw_count=10, tagged=[
        {"dish_id": "d_001_001", "restaurant_id": "r_001",
         "raw_name": "x", "canonical_name": "x", "price": 10.0,
         "monthly_sales": 0, "cuisine": "湘菜",
         "nutrition_profile": {
             "main_ingredient_type": "红肉", "cooking_method": "煮",
             "oil_level": 2, "protein_grams_estimate": 10,
             "vegetable_ratio_estimate": 0.1, "is_complete_meal": False,
             "spicy_level": 0, "tags": [],
         },
         "metadata": {
             "tagged_at": "x", "tag_version": "v1-mock",
             "is_available": True,
         }}
    ])
    m = tvs.prepare_zone("z1", force_version=True)
    # delta = 全部 10 条
    assert m["stats"]["delta_to_tag"] == 10
    assert m["force_version"] is True


def test_prepare_increment_5_new_raw(sandbox):
    """演示场景: 已有 100 raw + 100 tagged, raw 新增 5 条 → 只切 5 条 1 批."""
    raw = _raw_dishes(105)
    tagged = []
    for d in raw[:100]:
        tagged.append({
            "dish_id": d["dish_id"], "restaurant_id": d["restaurant_id"],
            "raw_name": d["raw_name"], "canonical_name": d["raw_name"],
            "price": d["price"], "monthly_sales": d["monthly_sales"],
            "cuisine": "湘菜",
            "nutrition_profile": {
                "main_ingredient_type": "红肉", "cooking_method": "煮",
                "oil_level": 2, "protein_grams_estimate": 10,
                "vegetable_ratio_estimate": 0.1,
                "is_complete_meal": False, "spicy_level": 0, "tags": [],
            },
            "metadata": {
                "tagged_at": "x", "tag_version": "v1-claude-code",
                "is_available": True,
            },
        })
    base = sandbox / "data" / "z1"
    base.mkdir(parents=True)
    (base / "restaurants.json").write_text(json.dumps(_restaurants()))
    (base / "dishes_raw.json").write_text(json.dumps(raw))
    (base / "dishes_tagged.json").write_text(json.dumps(tagged))

    m = tvs.prepare_zone("z1")
    assert m["stats"]["delta_to_tag"] == 5
    assert m["stats"]["batches"] == 1
    assert len(m["batches"][0]["dish_ids"]) == 5
    # 应该是最后 5 条新加的
    assert m["batches"][0]["dish_ids"] == [d["dish_id"] for d in raw[100:]]


# ---------------- merge ----------------

def _write_out(sandbox: Path, batch_meta: dict, recs: list[dict]) -> None:
    p = sandbox / batch_meta["out_path"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")


def test_merge_happy_path(sandbox):
    _seed_zone(sandbox, "z1", raw_count=5)
    m = tvs.prepare_zone("z1")
    b = m["batches"][0]
    _write_out(sandbox, b, [_tagged_payload(did) for did in b["dish_ids"]])
    stats = tvs.merge_zone("z1")
    assert stats["tagged_total"] == 5
    assert stats["done_batches"] == 1
    assert stats["pending_batches"] == 0
    # dishes_tagged.json 落盘
    out = json.loads((sandbox / "data" / "z1" / "dishes_tagged.json").read_text())
    assert len(out) == 5
    assert all(d["metadata"]["tag_version"] == "v1-claude-code" for d in out)


def test_merge_count_mismatch_retries(sandbox):
    """subagent 输出条数不对 → attempts++, status 仍 pending."""
    _seed_zone(sandbox, "z1", raw_count=3)
    m = tvs.prepare_zone("z1")
    b = m["batches"][0]
    # 只输出 1 条 (应有 3)
    _write_out(sandbox, b, [_tagged_payload(b["dish_ids"][0])])

    stats = tvs.merge_zone("z1")
    # attempts == 1, 还没 3 次, 仍 pending
    manifest = json.loads((sandbox / ".claude" / "tag_jobs" / "z1"
                           / "manifest.json").read_text())
    assert manifest["batches"][0]["status"] == "pending"
    assert manifest["batches"][0]["attempts"] == 1
    assert "count mismatch" in manifest["batches"][0]["last_error"]
    assert stats["pending_batches"] == 1


def test_merge_invalid_record_retries_then_fails(sandbox):
    """3 次失败 → status=failed, 写 failures log."""
    _seed_zone(sandbox, "z1", raw_count=2)
    m = tvs.prepare_zone("z1")
    b = m["batches"][0]
    bad = [_tagged_payload(did) for did in b["dish_ids"]]
    bad[0]["oil_level"] = 9  # 非法
    _write_out(sandbox, b, bad)

    # 跑 3 次 merge
    for _ in range(3):
        tvs.merge_zone("z1")

    manifest = json.loads((sandbox / ".claude" / "tag_jobs" / "z1"
                           / "manifest.json").read_text())
    assert manifest["batches"][0]["status"] == "failed"
    assert manifest["batches"][0]["attempts"] >= 3
    # failure log 应有一条
    fl = sandbox / "logs" / "tag_failures.jsonl"
    assert fl.exists()
    lines = [l for l in fl.read_text().splitlines() if l.strip()]
    assert len(lines) >= 1
    failed = json.loads(lines[0])
    assert failed["zone"] == "z1"
    assert "oil_level" in failed["error"]


def test_merge_unparseable_out_retries(sandbox):
    _seed_zone(sandbox, "z1", raw_count=1)
    m = tvs.prepare_zone("z1")
    b = m["batches"][0]
    p = sandbox / b["out_path"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not json {", encoding="utf-8")
    tvs.merge_zone("z1")
    manifest = json.loads((sandbox / ".claude" / "tag_jobs" / "z1"
                           / "manifest.json").read_text())
    assert manifest["batches"][0]["status"] == "pending"
    assert manifest["batches"][0]["attempts"] == 1


def test_merge_partial_batches_ok(sandbox):
    """部分 batch 有 out 文件, 其他 batch 还没跑 → merge 应只处理有的."""
    # batch_size=50, 100 dishes → 2 批
    _seed_zone(sandbox, "z1", raw_count=100)
    m = tvs.prepare_zone("z1")
    # 只为 batch 1 写 out
    b0 = m["batches"][0]
    _write_out(sandbox, b0, [_tagged_payload(did) for did in b0["dish_ids"]])
    stats = tvs.merge_zone("z1")
    assert stats["tagged_total"] == 50
    assert stats["pending_batches"] == 1
    assert stats["done_batches"] == 1


def test_merge_skips_already_done_batch(sandbox):
    """已 done 的 batch 不被重复处理 (manifest status 为权威)."""
    _seed_zone(sandbox, "z1", raw_count=3)
    m = tvs.prepare_zone("z1")
    b = m["batches"][0]
    _write_out(sandbox, b, [_tagged_payload(did) for did in b["dish_ids"]])
    tvs.merge_zone("z1")
    # 再跑一次, 不应改变状态 / 数量
    stats2 = tvs.merge_zone("z1")
    assert stats2["tagged_total"] == 3
    assert stats2["done_batches"] == 1


def test_prepare_increment_treats_old_version_as_stale(sandbox):
    """version 不一致的 tagged: 增量模式下自动视为 stale 进 delta (无需 --force-version)."""
    _seed_zone(sandbox, "z1", raw_count=10, tagged=[
        {"dish_id": "d_001_001", "restaurant_id": "r_001",
         "raw_name": "x", "canonical_name": "x", "price": 10.0,
         "monthly_sales": 0, "cuisine": "湘菜",
         "nutrition_profile": {
             "main_ingredient_type": "红肉", "cooking_method": "煮",
             "oil_level": 2, "protein_grams_estimate": 10,
             "vegetable_ratio_estimate": 0.1, "is_complete_meal": False,
             "spicy_level": 0, "tags": [],
         },
         "metadata": {
             "tagged_at": "x", "tag_version": "v1-mock",  # 旧版本
             "is_available": True,
         }}
    ])
    # version_label 默认 v1-claude-code, 与 v1-mock 不一致
    m = tvs.prepare_zone("z1")
    # d_001_001 是 v1-mock, version 不一致 → 不算"已 tagged" → 进 delta
    assert m["stats"]["delta_to_tag"] == 10
    assert "d_001_001" in m["batches"][0]["dish_ids"]


def test_merge_skips_failed_batch(sandbox):
    """failed 状态的 batch 不应被反复处理 (避免 attempts++ 和重复写 failure log)."""
    _seed_zone(sandbox, "z1", raw_count=2)
    m = tvs.prepare_zone("z1")
    b = m["batches"][0]
    # 写一个永远不合法的 out
    bad = [_tagged_payload(did) for did in b["dish_ids"]]
    bad[0]["oil_level"] = 9
    _write_out(sandbox, b, bad)
    # 跑 3 次 → status=failed, attempts=3, failure log 1 行
    for _ in range(3):
        tvs.merge_zone("z1")
    fl = sandbox / "logs" / "tag_failures.jsonl"
    lines_before = len(fl.read_text().splitlines())
    manifest = json.loads((sandbox / ".claude" / "tag_jobs" / "z1"
                           / "manifest.json").read_text())
    attempts_before = manifest["batches"][0]["attempts"]
    assert manifest["batches"][0]["status"] == "failed"
    # 再跑 N 次, attempts / failure log 不应再增长
    for _ in range(3):
        tvs.merge_zone("z1")
    manifest = json.loads((sandbox / ".claude" / "tag_jobs" / "z1"
                           / "manifest.json").read_text())
    assert manifest["batches"][0]["attempts"] == attempts_before
    lines_after = len(fl.read_text().splitlines())
    assert lines_after == lines_before


def test_merge_keeps_existing_tagged_in_increment_mode(sandbox):
    """增量模式: 已 tagged 的 100 条保留, 新 5 条 merge 进来 → 总 105。

    注: 已 tagged 字典需是 v3 schema (含 5 新字段), 否则 merge_zone 末尾的
    validate_dishes_tagged 校验会失败 (D-032)。
    """
    raw = _raw_dishes(105)
    tagged = []
    for d in raw[:100]:
        tagged.append({
            "dish_id": d["dish_id"], "restaurant_id": d["restaurant_id"],
            "raw_name": d["raw_name"], "canonical_name": d["raw_name"],
            "price": d["price"], "monthly_sales": d["monthly_sales"],
            "cuisine": "湘菜",
            "nutrition_profile": {
                "main_ingredient_type": "红肉", "cooking_method": "煮",
                "oil_level": 2, "protein_grams_estimate": 10,
                "vegetable_ratio_estimate": 0.1,
                "is_complete_meal": False, "spicy_level": 0,
                "dish_role": "主菜", "processed_meat_flag": False,
                "sweet_sauce_level": 0, "wetness": 2, "grain_type": "无",
                "tags": [],
            },
            "metadata": {
                "tagged_at": "2026-05-11T00:00:00",
                "tag_version": "v3", "is_available": True,
            },
        })
    base = sandbox / "data" / "z1"
    base.mkdir(parents=True)
    (base / "restaurants.json").write_text(json.dumps(_restaurants()))
    (base / "dishes_raw.json").write_text(json.dumps(raw))
    (base / "dishes_tagged.json").write_text(json.dumps(tagged))

    # tagged 数据是 tag_version="v3"; prepare 必须用同 version 才会跳过它们
    m = tvs.prepare_zone("z1", version_label="v3")
    b = m["batches"][0]
    _write_out(sandbox, b, [_tagged_payload(did) for did in b["dish_ids"]])
    stats = tvs.merge_zone("z1")
    assert stats["tagged_total"] == 105
    assert stats["kept_existing"] == 100
    assert stats["newly_tagged"] == 5


# ---------------- status ----------------

def test_status_returns_counts(sandbox):
    _seed_zone(sandbox, "z1", raw_count=60)
    tvs.prepare_zone("z1")
    s = tvs.status_zone("z1")
    assert s["manifest_exists"]
    assert s["batches_total"] == 2
    assert s["by_status"]["pending"] == 2
    assert s["by_status"]["done"] == 0


def test_status_no_manifest(sandbox):
    s = tvs.status_zone("missing-zone")
    assert s["manifest_exists"] is False

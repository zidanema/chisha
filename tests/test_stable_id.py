"""稳定实体 id (D-099) 单测.

覆盖: hash 稳定性 / 跨 zone 同 rid / 价格变不改 id / dedup 权威记录 /
菜名-价格冲突隔离 / 哈希碰撞 fail-loud / 餐厅级歧义 / alias / 原子发布 ack 状态机 /
归一化逐字复现采集端 / tag_via_api 活动集重建.
"""
import json
import os
import sys

import pytest

from chisha.loader import (
    normalize,
    normalize_shop_name_v1,
    normalize_dish_name_v1,
    restaurant_rid,
    dish_id_for,
    load_aliases,
    write_normalized,
    SHOP_NAME_VERSION,
)


def _rest(name, *, menu_status="ok", menu_count=None, menu=None, **kw):
    menu = menu or []
    return {"name": name, "menu_status": menu_status,
            "menu_count": menu_count if menu_count is not None else len(menu),
            "menu": menu, **kw}


def _dish(name, price, sales="月售1", category=None):
    return {"name": name, "price": price, "monthly_sales": sales,
            "category": category}


# ---------------- 归一化逐字复现采集端 ----------------

def test_norm_matches_collector():
    """字节级对拍采集端 collector/text_norm.py (Q1 条件)."""
    sys.path.insert(0, os.path.expanduser("~/waimai_data"))
    try:
        from collector.text_norm import (
            normalize_shop_name as c_norm, NORMALIZED_NAME_VERSION)
    except Exception:
        pytest.skip("collector repo 不可用")
    assert SHOP_NAME_VERSION == NORMALIZED_NAME_VERSION
    vectors = [
        "测试餐厅", "汉堡王（深圳 28687 店）", "Hot Stone 炎岩",
        "a 　\t\r\nb", "x​‌‍⁠﻿y", "  前后  ", "全角（括号）", "多   空格",
    ]
    for v in vectors:
        assert normalize_shop_name_v1(v) == c_norm(v), repr(v)


def test_norm_conservative():
    # 全角括号→半角 / 连空格折叠 / 零宽删
    assert normalize_shop_name_v1("店（A）") == "店(A)"
    assert normalize_shop_name_v1("a   b") == "a b"
    assert normalize_shop_name_v1("x​y") == "xy"
    # 显式不动大小写/标点
    assert normalize_shop_name_v1("KFC·B") == "KFC·B"
    # dish 复用同一套
    assert normalize_dish_name_v1("辣（大）") == "辣(大)"


# ---------------- hash 稳定性 + 价格变不改 id ----------------

def test_rid_stable_across_spacing_and_parens():
    a = restaurant_rid("汉堡王（深圳 28687 店）")
    b = restaurant_rid("汉堡王（深圳 28687 店）")  # 不同空白
    c = restaurant_rid("汉堡王(深圳 28687 店)")             # 半角括号
    assert a == b == c


def test_dish_id_invariant_to_price_and_sales():
    rid = restaurant_rid("某店")
    d1 = normalize(
        {"restaurants": [_rest("某店", menu=[_dish("辣椒炒肉", 30, "月售1")])]},
        office_zone="z")[1]
    d2 = normalize(
        {"restaurants": [_rest("某店", menu=[_dish("辣椒炒肉", 88, "月售999")])]},
        office_zone="z")[1]
    assert d1[0]["dish_id"] == d2[0]["dish_id"] == dish_id_for(rid, "辣椒炒肉")
    assert d1[0]["price"] != d2[0]["price"]  # 值变了, id 没变


def test_empty_name_fail_loud():
    with pytest.raises(ValueError):
        restaurant_rid("   ")
    with pytest.raises(ValueError):
        dish_id_for("r_abc", "​")


# ---------------- 跨 zone 同 rid ----------------

def test_cross_zone_same_rid():
    raw = {"restaurants": [_rest("共享店", menu=[_dish("菜", 10)])]}
    r_off = normalize(raw, office_zone="shenzhen-bay")[0]
    r_home = normalize(raw, office_zone="home")[0]
    assert r_off[0]["id"] == r_home[0]["id"]  # rid 全局, 不带 zone
    assert r_off[0]["office_zone"] != r_home[0]["office_zone"]


# ---------------- dedup 权威记录选择 ----------------

def test_dedup_picks_higher_status():
    raw = {"restaurants": [
        _rest("店A", menu_status="failed", menu=[_dish("菜x", 5)]),
        _rest("店A", menu_status="ok", menu=[_dish("菜y", 9), _dish("菜z", 12)]),
    ]}
    rests, dishes, conflicts, _nd = normalize(raw, office_zone="z")
    assert len(rests) == 1                       # 归并
    assert rests[0]["raw_menu_status"] == "ok"   # 取权威 (status 高者)
    assert {d["raw_name"] for d in dishes} == {"菜y", "菜z"}  # 不取并集


def test_dedup_status_priority_order():
    # early_ok > partial > failed > None
    raw = {"restaurants": [
        _rest("店B", menu_status=None, menu=[_dish("n", 1)]),
        _rest("店B", menu_status="partial", menu=[_dish("p", 1)]),
        _rest("店B", menu_status="early_ok", menu=[_dish("e", 1)]),
    ]}
    dishes = normalize(raw, office_zone="z")[1]
    assert {d["raw_name"] for d in dishes} == {"e"}


def test_dedup_tie_same_content_no_conflict():
    """status+count 相同且内容一致 → 折叠, 无歧义 (确定性)."""
    row = _rest("店C", menu_status="ok", menu=[_dish("菜", 10)])
    rests, dishes, conflicts, _nd = normalize(
        {"restaurants": [dict(row), dict(row)]}, office_zone="z")
    assert len(rests) == 1
    assert [c for c in conflicts if c["type"] == "restaurant_ambiguity"] == []


def test_dedup_tie_diff_content_is_ambiguity():
    """status+count 相同但菜单内容不同 → 餐厅级歧义: 整店隔离不进 active (不靠输入顺序)."""
    raw = {"restaurants": [
        _rest("店D", menu_status="ok", menu_count=1, menu=[_dish("甲", 10)]),
        _rest("店D", menu_status="ok", menu_count=1, menu=[_dish("乙", 20)]),
    ]}
    rests, dishes, conflicts, _nd = normalize(raw, office_zone="z")
    amb = [c for c in conflicts if c["type"] == "restaurant_ambiguity"]
    assert len(amb) == 1
    assert rests == [] and dishes == []  # 歧义店整体隔离, 不发布任一捕获


# ---------------- 菜名-价格冲突隔离 ----------------

def test_dish_name_price_conflict_quarantined():
    """同归一菜名 + 不同 price → 隔离 (不进 active, 不加后缀, 不混 price 进 key)."""
    raw = {"restaurants": [_rest("店E", menu=[
        _dish("套餐", 39.9), _dish("套餐", 89.0),  # 同名异价 → 冲突
        _dish("正常菜", 20),
    ])]}
    rests, dishes, conflicts, _nd = normalize(raw, office_zone="z")
    names = {d["raw_name"] for d in dishes}
    assert names == {"正常菜"}                       # 冲突菜被剔除
    dc = [c for c in conflicts if c["type"] == "dish_name_price"]
    assert len(dc) == 1 and dc[0]["norm_name"] == "套餐"


def test_dish_same_name_same_price_collapses():
    """同名同价仅销量不同 → 不是冲突, 折叠取销量大者 (D-099.1: 销量不改 id)."""
    raw = {"restaurants": [_rest("店F", menu=[
        _dish("菜", 30, "月售1"), _dish("菜", 30, "月售500"),
    ])]}
    rests, dishes, conflicts, _nd = normalize(raw, office_zone="z")
    assert len(dishes) == 1
    assert dishes[0]["monthly_sales"] == 500
    assert [c for c in conflicts if c["type"] == "dish_name_price"] == []


def test_hash_collision_fail_loud(monkeypatch):
    """不同归一菜名 → 同 8-hex → dish_hash_collision 隔离."""
    import chisha.loader as L
    real = L.dish_id_for

    def fake(rid, name):
        norm = L.normalize_dish_name_v1(name)
        return f"d_{rid[2:]}_deadbeef" if norm in ("甲", "乙") else real(rid, name)
    monkeypatch.setattr(L, "dish_id_for", fake)
    raw = {"restaurants": [_rest("碰撞店", menu=[
        _dish("甲", 1), _dish("乙", 2), _dish("丙", 3)])]}
    dishes, conflicts = L.normalize(raw, office_zone="z")[1:3]
    hc = [c for c in conflicts if c["type"] == "dish_hash_collision"]
    assert len(hc) == 1
    assert set(hc[0]["detail"]["names"]) == {"甲", "乙"}
    # 碰撞双方**都**隔离 (该 dish_id 已污染, 不能信任任何一方); 只剩未碰撞的丙
    assert {d["raw_name"] for d in dishes} == {"丙"}


# ---------------- alias ----------------

def test_alias_redirects_rid(tmp_path):
    canonical = restaurant_rid("品牌总店")
    ap = tmp_path / "aliases.json"
    ap.write_text(json.dumps({"version": 1, "aliases": {
        "老名字": canonical}}, ensure_ascii=False), encoding="utf-8")
    aliases = load_aliases(ap)
    raw = {"restaurants": [_rest("老名字", menu=[_dish("菜", 10)])]}
    rests = normalize(raw, office_zone="z", aliases=aliases)[0]
    assert rests[0]["id"] == canonical  # 旧名绑到 canonical rid


def test_alias_rejects_bad_rid(tmp_path):
    ap = tmp_path / "aliases.json"
    ap.write_text(json.dumps({"version": 1, "aliases": {"x": "r_NOTHEX"}}),
                  encoding="utf-8")
    with pytest.raises(ValueError):
        load_aliases(ap)


# ---------------- 原子发布 + ack 状态机 ----------------

def _envelope(restaurants, *, norm_version=SHOP_NAME_VERSION):
    """包合法 collector envelope (B2: load_raw 现在窄契约校验, 裸 {restaurants} 会被拒)。"""
    return {
        "schema_version": 1,
        "app": "meituan",
        "collected_at": "2026-05-26T20:00:00+08:00",
        "normalized_name_version": norm_version,
        "location": {"name": "测试点", "label": "test",
                     "observed_address_text": None, "address_observed_at": None,
                     "address_observation_status": "unobserved"},
        "restaurants": restaurants,
    }


def _write_raw(tmp_path, restaurants):
    p = tmp_path / "raw.json"
    p.write_text(json.dumps(_envelope(restaurants), ensure_ascii=False),
                 encoding="utf-8")
    return p


def test_publish_blocks_on_unacked_conflict(tmp_path):
    raw = _write_raw(tmp_path, [_rest("店", menu=[
        _dish("套餐", 39.9), _dish("套餐", 89.0)])])
    out = tmp_path / "out"
    stats = write_normalized(raw, out, "z")
    assert stats["published"] is False
    assert not (out / "restaurants.json").exists()       # active 未动
    assert (out / "_staged" / "restaurants.json").exists()  # 只写 staged
    assert (out / "dish_id_conflicts.json").exists()     # 报告始终落盘


def test_publish_proceeds_when_acked(tmp_path):
    raw = _write_raw(tmp_path, [_rest("店", menu=[
        _dish("套餐", 39.9), _dish("套餐", 89.0), _dish("正常", 20)])])
    out = tmp_path / "out"
    out.mkdir()
    # 从实际冲突取 key (含价格指纹), 不硬编码格式
    conflicts = normalize(json.load(open(raw, encoding="utf-8")), office_zone="z")[2]
    key = next(c["key"] for c in conflicts if c["type"] == "dish_name_price")
    (out / "conflicts_ack.json").write_text(json.dumps({
        "acknowledged": [key]}, ensure_ascii=False), encoding="utf-8")
    stats = write_normalized(raw, out, "z")
    assert stats["published"] is True
    pub = json.loads((out / "dishes_raw.json").read_text(encoding="utf-8"))
    assert {d["raw_name"] for d in pub} == {"正常"}  # 冲突菜仍隔离, 其余发布


def test_ack_invalidated_when_conflict_payload_changes(tmp_path):
    """价格集变了 → conflict key 变 → 旧 ack 不再命中 → 重新 block (防旧 ack 覆盖新冲突)."""
    out = tmp_path / "out"; out.mkdir()
    raw1 = _write_raw(tmp_path, [_rest("店", menu=[_dish("套餐", 39.9), _dish("套餐", 89.0)])])
    key1 = next(c["key"] for c in normalize(json.load(open(raw1, encoding="utf-8")),
                                            office_zone="z")[2]
                if c["type"] == "dish_name_price")
    (out / "conflicts_ack.json").write_text(json.dumps({"acknowledged": [key1]}),
                                            encoding="utf-8")
    assert write_normalized(raw1, out, "z")["published"] is True
    # 价格集变化 (89→150) → 新 key, 旧 ack 不命中 → 不发布
    raw2 = (out.parent / "raw2.json")
    raw2.write_text(json.dumps(_envelope([_rest(
        "店", menu=[_dish("套餐", 39.9), _dish("套餐", 150.0)])]), ensure_ascii=False),
        encoding="utf-8")
    assert write_normalized(raw2, out, "z")["published"] is False


def test_ingest_lock_cleared_on_success_and_blocks_tagging(tmp_path):
    """loader 成功发布后清除 .ingest_lock; 残留 marker (模拟崩溃) → tag 拒绝跑 (BLOCK#3)."""
    from chisha.loader import ingest_in_progress, ingest_lock_path
    raw = _write_raw(tmp_path, [_rest("店", menu=[_dish("菜", 10)])])
    out = tmp_path / "out"
    assert write_normalized(raw, out, "z")["published"] is True
    assert not ingest_in_progress(out)          # 成功后 marker 清除
    ingest_lock_path(out).write_text("z")        # 模拟崩溃残留
    assert ingest_in_progress(out) is True


# ---------------- B2: load_raw 窄契约校验 (无 grandfather) ----------------

def test_load_raw_rejects_old_no_version_envelope(tmp_path):
    """旧裸壳 {restaurants:[...]} (无 schema_version/normalized_name_version) → fail-loud."""
    from chisha.collector_contract import ContractViolation
    from chisha.loader import load_raw
    p = tmp_path / "old.json"
    p.write_text(json.dumps({"restaurants": [_rest("店", menu=[_dish("菜", 10)])]}),
                 encoding="utf-8")
    with pytest.raises(ContractViolation):
        load_raw(p)


def test_load_raw_rejects_norm_version_mismatch(tmp_path):
    """normalized_name_version != chisha SHOP_NAME_VERSION → fail-loud (防 id 漂移)."""
    from chisha.collector_contract import ContractViolation
    from chisha.loader import load_raw
    p = tmp_path / "mism.json"
    p.write_text(json.dumps(_envelope([_rest("店", menu=[_dish("菜", 10)])],
                                      norm_version=SHOP_NAME_VERSION + 1)),
                 encoding="utf-8")
    with pytest.raises(ContractViolation, match="normalized_name_version"):
        load_raw(p)


def test_load_raw_accepts_valid_envelope(tmp_path):
    """合法 Batch A 新 envelope → 通过, 返回 dict."""
    from chisha.loader import load_raw
    p = _write_raw(tmp_path, [_rest("店", menu=[_dish("菜", 10)])])
    raw = load_raw(p)
    assert raw["schema_version"] == 1 and len(raw["restaurants"]) == 1


# ---------------- tag_via_api 活动集重建 ----------------

def test_tag_rebuild_active_prunes_and_refreshes():
    from scripts.tag_via_api import _rebuild_active
    existing = [
        {"dish_id": "d_x_1", "restaurant_id": "r_x", "raw_name": "旧名",
         "price": 10.0, "monthly_sales": 5, "cuisine": "湘菜",
         "nutrition_profile": {"oil_level": 3}, "metadata": {"tag_version": "v3"}},
        {"dish_id": "d_x_gone", "restaurant_id": "r_x", "raw_name": "下架菜",
         "price": 9.0, "monthly_sales": 1, "cuisine": "粤菜",
         "nutrition_profile": {}, "metadata": {"tag_version": "v3"}},
    ]
    raw_idx = {"d_x_1": {"dish_id": "d_x_1", "raw_name": "旧名",
                         "price": 18.0, "monthly_sales": 99}}  # 价格涨了, 下架菜消失
    active = _rebuild_active(existing, raw_idx)
    assert set(active) == {"d_x_1"}            # 下架菜被 prune
    assert active["d_x_1"]["price"] == 18.0    # raw 字段刷新
    assert active["d_x_1"]["monthly_sales"] == 99
    assert active["d_x_1"]["cuisine"] == "湘菜"  # LLM 标签保留


# ---------------- 迁移: legacy 索引 + 标签复用 ----------------

def test_migrate_seed_refreshes_availability_and_raw():
    """复用旧标签但 is_available 强制 True (在 active raw=上架) + raw 字段从新数据刷 (BLOCK#4)."""
    from scripts.migrate_stable_ids import seed_record
    src = {"canonical_name": "辣椒炒肉", "cuisine": "湘菜",
           "nutrition_profile": {"oil_level": 3},
           "metadata": {"tag_version": "v3", "is_available": False, "tagged_at": "t0"}}
    rd = {"dish_id": "d_新_1", "restaurant_id": "r_新", "raw_name": "辣椒炒肉",
          "price": 28.0, "monthly_sales": 12}
    rec = seed_record(src, rd)
    assert rec["metadata"]["is_available"] is True   # 旧 False 被刷新 (新 raw 里=上架)
    assert rec["metadata"]["tag_version"] == "v3"     # 标签元信息保留
    assert rec["cuisine"] == "湘菜" and rec["nutrition_profile"]["oil_level"] == 3
    assert rec["price"] == 28.0 and rec["dish_id"] == "d_新_1"


def test_migrate_ambiguous_labels_not_reused():
    """同一新 dish_id 收到多条不同 payload (旧重复店标签不一致) → ambiguous, 不复用."""
    from scripts.migrate_stable_ids import build_legacy_index
    rid = restaurant_rid("老店")
    did = dish_id_for(rid, "招牌菜")
    # 两条旧 tagged, 同店名同菜名 → 同新 did, 但 cuisine 标得不一样
    old_tagged = [
        {"restaurant_id": "r_001", "raw_name": "招牌菜", "cuisine": "湘菜",
         "canonical_name": "招牌菜", "nutrition_profile": {"oil_level": 3}},
        {"restaurant_id": "r_077", "raw_name": "招牌菜", "cuisine": "川菜",
         "canonical_name": "招牌菜", "nutrition_profile": {"oil_level": 4}},
    ]
    old_rid_to_name = {"r_001": "老店", "r_077": "老店"}  # 旧重复店 (位置id分两条)
    legacy, ambiguous, skipped = build_legacy_index(old_tagged, old_rid_to_name, {})
    assert did in ambiguous and did not in legacy  # 不猜, 留重打
    assert skipped == 0


def test_migrate_consistent_labels_reused():
    """同一新 dish_id 多条但 payload 完全一致 (纯重复行) → 复用, 不判 ambiguous."""
    from scripts.migrate_stable_ids import build_legacy_index
    rid = restaurant_rid("老店")
    did = dish_id_for(rid, "招牌菜")
    rec = {"raw_name": "招牌菜", "cuisine": "湘菜", "canonical_name": "招牌菜",
           "nutrition_profile": {"oil_level": 3}}
    old_tagged = [{**rec, "restaurant_id": "r_001"}, {**rec, "restaurant_id": "r_077"}]
    legacy, ambiguous, _ = build_legacy_index(
        old_tagged, {"r_001": "老店", "r_077": "老店"}, {})
    assert did in legacy and ambiguous == []

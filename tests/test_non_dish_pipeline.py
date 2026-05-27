"""非菜隔离的链路集成测试 (Codex diff review P2 补): loader 非菜 non-blocking 发布
+ tag_via_api 记录级隔离/持久化. 守 D-101 关键不变量."""
import copy
import json
from pathlib import Path

from chisha.loader import write_normalized
from scripts.tag_via_api import _finalize_write, _partition_valid, _select_dishes_to_tag


# ---------- loader: 非菜 non-blocking ----------

def _envelope(menu: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "normalized_name_version": 1,
        "app": "meituan",
        "location": {
            "name": "测试点", "label": "office",
            "observed_address_text": None, "address_observed_at": None,
            "address_observation_status": "unobserved",
        },
        "restaurants": [{"name": "测试店", "menu": menu}],
    }


def test_non_dish_with_price_conflict_does_not_block_publish(tmp_path):
    # 两条"需要餐具"异价 —— 若当菜会触发 dish_name_price 冲突 → 阻塞发布。
    # 非菜在冲突检测前剔除 → 不进 conflicts → published=True; 真菜照常进 active。
    raw = tmp_path / "office_restaurants.json"
    raw.write_text(json.dumps(_envelope([
        {"name": "宫保鸡丁", "price": 28},
        {"name": "需要餐具（多点不送）", "price": 1},
        {"name": "需要餐具（多点不送）", "price": 2},
    ]), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "zone"
    stats = write_normalized(raw, out, "office")
    assert stats["published"] is True, "非菜异价被误当冲突阻塞了发布"
    assert stats["non_dish"] == 2
    dishes = json.loads((out / "dishes_raw.json").read_text())
    names = {d["raw_name"] for d in dishes}
    assert names == {"宫保鸡丁"}                       # 只有真菜进 active
    q = json.loads((out / "non_dish_quarantine.json").read_text())
    assert q["total"] == 2


# ---------- tag: 记录级隔离 + 持久化 ----------

_VALID = {
    "dish_id": "d_aaa_1", "restaurant_id": "r_aaa", "raw_name": "番茄炒蛋",
    "canonical_name": "番茄炒蛋", "price": 18.0, "monthly_sales": 10, "cuisine": "其他",
    "nutrition_profile": {
        "main_ingredient_type": "蛋", "cooking_method": "炒", "oil_level": 3,
        "protein_grams_estimate": 15, "vegetable_ratio_estimate": 0.3,
        "is_complete_meal": False, "spicy_level": 0, "dish_role": "主菜",
        "processed_meat_flag": False, "sweet_sauce_level": 0, "wetness": 1,
        "grain_type": "无", "tags": [],
    },
    "metadata": {"tagged_at": "2026-05-27T00:00:00+00:00", "tag_version": "v3",
                 "is_available": True},
}


def _rec(did: str, cooking_method: str = "炒") -> dict:
    r = copy.deepcopy(_VALID)
    r["dish_id"] = did
    r["nutrition_profile"]["cooking_method"] = cooking_method
    return r


def test_finalize_partitions_valid_from_invalid(tmp_path):
    tagged = tmp_path / "dishes_tagged.json"
    good, bad = _rec("d_z_1"), _rec("d_z_2", cooking_method="其他")  # 其他 不在 COOKING_METHODS
    raw_idx = {"d_z_1": {}, "d_z_2": {}}
    path, active_count, q_total = _finalize_write(
        "z", [good, bad], "v3", tagged, None, raw_idx)
    assert active_count == 1 and q_total == 1
    active = json.loads(tagged.read_text())
    assert [d["dish_id"] for d in active] == ["d_z_1"]      # 脏数据不进 active
    quar = json.loads(tagged.with_suffix(".quarantine.json").read_text())
    assert quar[0]["dish_id"] == "d_z_2" and "cooking_method" in quar[0]["_quarantine_reason"]


def test_quarantine_persists_when_skipped_then_drops_when_delisted(tmp_path):
    tagged = tmp_path / "dishes_tagged.json"
    # 第一轮: d_z_2 越界进隔离
    _finalize_write("z", [_rec("d_z_1"), _rec("d_z_2", "其他")], "v3", tagged, None,
                    {"d_z_1": {}, "d_z_2": {}})
    # 第二轮: d_z_2 被 skip (不在 all_records), 但仍在 raw → 隔离必须保留 (不丢→不重选循环)
    _, _, q_total = _finalize_write("z", [_rec("d_z_1")], "v3", tagged, None,
                                    {"d_z_1": {}, "d_z_2": {}})
    assert q_total == 1
    assert json.loads(tagged.with_suffix(".quarantine.json").read_text())[0]["dish_id"] == "d_z_2"
    # 第三轮: d_z_2 下架 (不在 raw) → 隔离清掉
    _, _, q_total = _finalize_write("z", [_rec("d_z_1")], "v3", tagged, None, {"d_z_1": {}})
    assert q_total == 0
    assert not tagged.with_suffix(".quarantine.json").exists()


def test_requarantine_clears_when_record_becomes_valid(tmp_path):
    # Issue 1 (Codex re-review): 旧隔离的 dish 本轮重打成功进 valid → 必须出 quarantine,
    # 不能既在 active 又在隔离 (否则下轮被 skip_ids 误跳一道已修好的菜)。
    tagged = tmp_path / "dishes_tagged.json"
    _finalize_write("z", [_rec("d_z_1"), _rec("d_z_2", "其他")], "v3", tagged, None,
                    {"d_z_1": {}, "d_z_2": {}})
    # 本轮 d_z_2 拿到合法 cooking_method (如 force 重打) → 进 valid
    _, active_count, q_total = _finalize_write(
        "z", [_rec("d_z_1"), _rec("d_z_2", "炒")], "v3", tagged, None,
        {"d_z_1": {}, "d_z_2": {}})
    assert active_count == 2 and q_total == 0
    assert not tagged.with_suffix(".quarantine.json").exists()
    assert {d["dish_id"] for d in json.loads(tagged.read_text())} == {"d_z_1", "d_z_2"}


def test_select_skips_quarantined_ids():
    raw = [{"dish_id": "d_1"}, {"dish_id": "d_2"}, {"dish_id": "d_3"}]
    delta = _select_dishes_to_tag(raw, [], "v3", False, None, skip_ids={"d_2"})
    assert [d["dish_id"] for d in delta] == ["d_1", "d_3"]    # d_2 跳过
    # force_version 时不跳 (强制全打)
    delta_f = _select_dishes_to_tag(raw, [], "v3", True, None, skip_ids={"d_2"})
    assert len(delta_f) == 3

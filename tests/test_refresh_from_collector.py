"""跨 zone 指纹哨兵测试 (B3, D3).

合成 G 式克隆 → hard_fail / 正常两 zone → ok / 边界 → warn /
distance 双非空规则 / run_sentinel 抛错 + 单 zone 跳过。
不测 main() 端到端 (会 shell out tag/validate + 烧 LLM)。
"""
from __future__ import annotations

import pytest

from scripts.refresh_from_collector import (
    SentinelError,
    cross_zone_fingerprint,
    run_sentinel,
)


def _zone(label: str, rows: list[tuple[str, str]]) -> dict:
    """rows = [(店名, distance字符串)]。"""
    return {
        "schema_version": 1,
        "normalized_name_version": 1,
        "location": {"name": label, "label": label,
                     "observed_address_text": None, "address_observed_at": None,
                     "address_observation_status": "unobserved"},
        "restaurants": [
            {"name": n, "menu_status": "ok", "menu_count": 1,
             "menu": [{"name": "菜", "price": 10.0}], "distance": d}
            for n, d in rows
        ],
    }


def test_g_style_clone_hard_fails():
    """home 几乎是 office 全量克隆 + distance 逐字相同 + label 不同 → hard_fail (断裂点 G)."""
    shared = [(f"店{i}", f"{i*100}m") for i in range(32)]   # 32 共享, distance 相同
    office = _zone("office", shared + [(f"office专属{i}", "500m") for i in range(3)])
    home = _zone("home", shared + [(f"home专属{i}", "600m") for i in range(3)])
    fp = cross_zone_fingerprint("office", office, "home", home)
    assert fp["shared"] == 32
    assert fp["rid_share_rate"] >= 0.80
    assert fp["distance_equal_rate"] == 1.0
    assert fp["labels_differ"] is True
    assert fp["verdict"] == "hard_fail"


def test_normal_two_zones_ok():
    """两 zone 基本不重叠 → ok (跨 zone 少量同店共享 rid 是 D-099.2 允许的)."""
    office = _zone("office", [(f"O店{i}", f"{i*100}m") for i in range(35)])
    home = _zone("home", [(f"H店{i}", f"{i*100}m") for i in range(35)]
                 + [("O店0", "0m"), ("O店1", "100m")])  # 仅 2 家真共享
    fp = cross_zone_fingerprint("office", office, "home", home)
    assert fp["shared"] == 2
    assert fp["verdict"] == "ok"


def test_warn_band():
    """共享 22 (≥20) + distance 相同率高, 但 rid 共享率 <0.8 (大 zone) → warn 非 hard_fail."""
    shared = [(f"店{i}", f"{i*100}m") for i in range(22)]
    office = _zone("office", shared + [(f"O{i}", "9m") for i in range(38)])  # 60 家
    home = _zone("home", shared + [(f"H{i}", "9m") for i in range(38)])      # 60 家
    fp = cross_zone_fingerprint("office", office, "home", home)
    assert fp["shared"] == 22
    assert fp["rid_share_rate"] < 0.80          # 22/60 ≈ 0.367
    assert fp["distance_equal_rate"] >= 0.50
    assert fp["verdict"] == "warn"


def test_distance_only_compared_when_both_nonempty():
    """共享 rid 但一侧 distance 空 → 不计入 distance 相同率分母 (Codex Q3)."""
    office = _zone("office", [(f"店{i}", f"{i*100}m") for i in range(30)])
    # home: 同 30 店, 但其中 20 家 distance 为空字符串 → 只有 10 家两边都非空
    home_rows = [(f"店{i}", f"{i*100}m" if i < 10 else "") for i in range(30)]
    home = _zone("home", home_rows)
    fp = cross_zone_fingerprint("office", office, "home", home)
    assert fp["shared"] == 30
    assert fp["distance_compared"] == 10        # 仅两边都非空的 10 家
    assert fp["distance_equal_rate"] == 1.0     # 这 10 家逐字相同


def test_run_sentinel_raises_on_hard_fail():
    shared = [(f"店{i}", f"{i*100}m") for i in range(32)]
    raws = {
        "office": _zone("office", shared + [("o1", "1m")]),
        "home": _zone("home", shared + [("h1", "1m")]),
    }
    with pytest.raises(SentinelError, match="hard-fail"):
        run_sentinel(raws)


def test_run_sentinel_single_zone_skips():
    """仅 1 个 zone → 无可比对, 返回空 (不抛)."""
    raws = {"office": _zone("office", [("店", "100m")])}
    assert run_sentinel(raws) == []


def test_run_sentinel_clean_returns_results():
    raws = {
        "office": _zone("office", [(f"O{i}", "1m") for i in range(35)]),
        "home": _zone("home", [(f"H{i}", "1m") for i in range(35)]),
    }
    results = run_sentinel(raws)
    assert len(results) == 1 and results[0]["verdict"] == "ok"

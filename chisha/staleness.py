"""陈旧度计算 (notify-don't-force, update-notifier 范式). doctor + ready 共用单源。

陈旧度键 = max(last_checked, install_manifest.data_version) — 仲裁键 (per-zone marker) **不参与**
(spec §6: 仲裁键管 serve 哪份, 陈旧度键管该不该提醒, 两者分离)。取 max 消两个伪状态:
  ① unchanged-but-old-bundle zone 的 false-nag (刚 update 过却报 N 天);
  ② reinstall-newer-bundle + 旧 last_checked 的保守误报 (F1 case d)。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

THRESHOLD_DAYS = 14   # 对齐双周 cadence


def _valid_date(v) -> str:
    from chisha import zone_marker as zm   # 单源校验 (与 recall/purge 一致)
    return zm.valid_data_version(v)


def _max_install_data_version(install_root: Path) -> str:
    from chisha import manifest as mfst
    dvs = [_valid_date(z.get("data_version")) for z in mfst.load_zones(install_root)]
    return max(dvs) if dvs else ""


def compute_for_root(install_root: Path, *, today: str | None = None) -> dict | None:
    """便捷包装 (doctor/ready 单源): 从 install_root 推 state data 目录 + 默认 today=今天.

    纯内核 `compute` 保留 (state_data_dir/today 显式注入, 给测试)。"""
    from chisha import state_root
    return compute(install_root, state_root.resolve(install_root) / "data",
                   today=today or dt.date.today().isoformat())


def compute(install_root: Path, state_data_dir: Path, *, today: str) -> dict | None:
    """返回 {age_days, last_fresh, threshold, message} 若 age > 阈值, 否则 None。

    失败 (离线/坏数据/缺 manifest) 静默 None — 绝不硬失败, 绝不阻塞 recommend。
    """
    try:
        from chisha import zone_marker as zm
        last_checked = _valid_date(zm.read_update_state(state_data_dir).get("last_checked"))
        install_dv = _max_install_data_version(install_root)
        last_fresh = max(last_checked, install_dv)    # 字典序 = 日期序 (ISO date)
        if not last_fresh:
            return None
        d0 = dt.date.fromisoformat(last_fresh)
        d1 = dt.date.fromisoformat(today)
        age = (d1 - d0).days
        if age <= THRESHOLD_DAYS:
            return None
        return {"age_days": age, "last_fresh": last_fresh, "threshold": THRESHOLD_DAYS,
                "message": f"数据已 {age} 天 (>{THRESHOLD_DAYS}), 跑 `chisha update` 刷新"}
    except Exception:
        return None    # 离线/坏数据 → 静默, 绝不硬失败

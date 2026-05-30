"""S-05: sandbox layout v2 meta accessors (narrowed scope).

v2 layout 关键变化:
- ``logs/sandbox/_meta.json`` 新增 (schema_version + migration history)
- Default sid 仍 flat (``logs/sandbox/<rel>``); 非 default sid 走
  ``logs/sandbox/sessions/<sid>/<rel>`` (S-04 ``data_root`` 已实现)
- 老 ``logs/sandbox/<rel>`` 数据保持原地 = default 桶 (零搬运)

本模块现仅保留 ``_meta.json`` 读写 helper (``read_meta`` /
``_atomic_write_meta`` / ``meta_path`` / ``SCHEMA_VERSION``), 被
``chisha/sandbox.py`` 生产消费. 一次性 v1→v2 迁移器 (migrate_to_v2 +
relocate 机制) 已退役.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


SCHEMA_VERSION = 2
_META_REL = "logs/sandbox/_meta.json"


def meta_path(root: Path) -> Path:
    return root / _META_REL


def read_meta(root: Path) -> Optional[dict]:
    p = meta_path(root)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _atomic_write_meta(root: Path, data: dict) -> None:
    p = meta_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(p)

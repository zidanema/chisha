"""scripts 间共享的 IO / zone / 失败日志工具.

F-016 #28: 消除 tag_via_api / tag_via_subagent / validate_data 间逐字重复的
_read_json / _write_json / _now_iso / _resolve_zones / _record_failure / ZONES_ALL。
(migrate_stable_ids 的 ZONES_ALL 顺序相反且影响 --zone all 迭代次序, 一次性迁移器,
不并入本模块以免改其行为。)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FAILURES_LOG = ROOT / "logs" / "tag_failures.jsonl"
ZONES_ALL = ("home", "shenzhen-bay")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p: Path, obj: Any, indent: int = 2) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=indent),
                 encoding="utf-8")


def resolve_zones(zone_arg: str) -> list[str]:
    if zone_arg == "all":
        return list(ZONES_ALL)
    return [zone_arg]


def record_failure(zone: str, batch_id: int, dish_ids: list[str],
                   error: str) -> None:
    FAILURES_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "ts": now_iso(),
        "zone": zone,
        "batch_id": batch_id,
        "dish_ids": dish_ids,
        "error": error[:500],
    }
    with FAILURES_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")

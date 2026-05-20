"""CLI: 把现有 logs/sandbox/ 老 layout migrate 到 v2 (写 _meta.json).

幂等可重跑. 默认不挪文件 (default 桶 = flat = 老路径).

用法:
    uv run python -m scripts.migrate_sandbox_layout            # 写 _meta.json
    uv run python -m scripts.migrate_sandbox_layout --dry-run
    uv run python -m scripts.migrate_sandbox_layout --relocate-legacy
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chisha.sandbox_migration import migrate_to_v2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate sandbox layout v1 → v2 (write _meta.json + optional relocate)"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="project root (default: auto-detect from script location)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="log plan only, no disk writes",
    )
    parser.add_argument(
        "--relocate-legacy",
        action="store_true",
        help="move logs/sandbox/<flat> → sessions/_legacy/<rel> (keeps .bak.<ts>)",
    )
    args = parser.parse_args(argv)

    root = args.root or Path(__file__).resolve().parent.parent
    result = migrate_to_v2(
        root, dry_run=args.dry_run, relocate_legacy=args.relocate_legacy
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

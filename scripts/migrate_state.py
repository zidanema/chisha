"""D-102 Step2 (Commit B): 一次性把 repo 内旧 user state 迁到 state_root (~/.chisha/).

用法:
  uv run python -m scripts.migrate_state --dry-run   # 先看计划, 不写盘
  uv run python -m scripts.migrate_state             # 真迁 (复制, 不删 repo 源)

安全: 复制而非移动 → repo 原数据保留作回滚; 校验文件数; 原子写 marker; 幂等
(已迁直接 already)。目标已存在的项不覆盖。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chisha import state_migrate, state_root


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m scripts.migrate_state")
    p.add_argument("--dry-run", action="store_true", help="只打印计划, 不写盘")
    p.add_argument("--state-root", default=None,
                   help="覆盖 state_root 落点 (默认 = state_root.resolve(None))")
    args = p.parse_args(argv)

    install = state_root.project_root()
    sroot = (
        Path(args.state_root).expanduser()
        if args.state_root else state_root.resolve(None)
    )

    print(f"install_root (源, repo, 保留): {install}")
    print(f"state_root   (目标):          {sroot}")
    res = state_migrate.migrate_state(install, sroot, dry_run=args.dry_run)
    print(f"status: {res.status}")
    if res.copied:
        print("copied:")
        for c in res.copied:
            print(f"  + {c}")
    if res.skipped_existing:
        print("skipped (目标已存在, 不覆盖):")
        for s in res.skipped_existing:
            print(f"  · {s}")
    print(f"file_count: {res.file_count}")
    if args.dry_run:
        print("\n[dry-run] 未写盘. 去掉 --dry-run 执行真迁移.")
    elif res.status == "migrated":
        print("\n迁移完成. repo 原数据保留 (回滚 = 删 state_root 或设 CHISHA_STATE_ROOT).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

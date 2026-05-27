"""D-102 Step3: 生成 data/manifest.json (数据产物 ↔ 引擎 兼容声明, 提案 §C).

用法:
  uv run python -m scripts.build_manifest                 # 写 data/manifest.json
  uv run python -m scripts.build_manifest --bump          # artifact_version +1
  uv run python -m scripts.build_manifest --dry-run       # 打印不写

发布只读数据 bundle 时跑一次。artifact_version 每次发布 bump (--bump); data_schema_version /
engine_capabilities_required / normalized_name_version 反映当前产物的真实 schema/能力。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from chisha import __version__ as ENGINE_VERSION
from chisha.loader import SHOP_NAME_VERSION
from chisha.manifest import MANIFEST_SCHEMA_VERSION, manifest_path

# 当前产物的数据 schema 版本 (dishes_tagged/restaurants 结构). 破坏性结构变更时 bump。
DATA_SCHEMA_VERSION = 1
# 当前产物用到的引擎能力 (引擎必须具备才能正确消费本 bundle)。
BUNDLE_CAPABILITIES = ["stable_entity_ids_v1", "dish_tag_schema_v3"]


def _discover_zones(install_root: Path) -> list[str]:
    """data/ 下含 restaurants.json 的子目录 = 一个 zone。"""
    data_dir = install_root / "data"
    zones = [
        p.name for p in sorted(data_dir.iterdir())
        if p.is_dir() and (p / "restaurants.json").exists()
    ]
    return zones


def build(install_root: Path, *, prev: dict | None, bump: bool) -> dict:
    artifact_version = 1
    if prev and isinstance(prev.get("artifact_version"), int):
        artifact_version = prev["artifact_version"] + (1 if bump else 0)
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "artifact_version": artifact_version,
        "data_schema_version": DATA_SCHEMA_VERSION,
        "min_engine_version": ENGINE_VERSION,
        "engine_capabilities_required": BUNDLE_CAPABILITIES,
        "normalized_name_version": SHOP_NAME_VERSION,
        "zones": _discover_zones(install_root),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        # 本期留位 (提案范围红线): 完整性 hash / 签名 / 来源证明不定型。
        "integrity": None,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m scripts.build_manifest")
    p.add_argument("--bump", action="store_true", help="artifact_version +1")
    p.add_argument("--dry-run", action="store_true", help="打印不写")
    args = p.parse_args(argv)

    install_root = Path(__file__).resolve().parent.parent
    mpath = manifest_path(install_root)
    prev = None
    if mpath.exists():
        try:
            prev = json.loads(mpath.read_text(encoding="utf-8"))
        except Exception:
            prev = None

    manifest = build(install_root, prev=prev, bump=args.bump)
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    print(text)
    if args.dry_run:
        print("[dry-run] 未写盘.")
        return 0
    mpath.write_text(text, encoding="utf-8")
    print(f"写入 {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

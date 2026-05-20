"""把 v3 LLM 输出里 NotInEnum 的字段做 deterministic 映射, 让 schema 校验通过.

用途: deepseek-v4-flash 偶尔无视 prompt 黑名单, 输出 cooking_method='卤'/'熏'/'炸',
或 main_ingredient_type='饮品'。这些都能 1:1 映射到合法枚举, 不需要重调 LLM。

映射表:
  cooking_method:
    卤 / 卤水 / 酱卤      → 炖
    熏 / 烟熏              → 烤
    炸                     → 油炸
    爆炒                   → 炒
    油焖                   → 炖
    红烧                   → 炖
    酥炸 / 脆皮            → 油炸
    烧                     → 炖
  main_ingredient_type:
    饮品                   → 其他   (饮品已在 dish_role 表达, main 应归"其他")
    禽类                   → 白肉
    肉类 / 肉              → 红肉

用法:
  uv run python -m scripts.normalize_v3_enums data/<zone>/dishes_tagged.json
  uv run python -m scripts.normalize_v3_enums all   # 两个 zone 都处理
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COOKING_REMAP = {
    "卤": "炖", "卤水": "炖", "酱卤": "炖",
    "熏": "烤", "烟熏": "烤",
    "炸": "油炸", "酥炸": "油炸", "脆皮": "油炸",
    "爆炒": "炒",
    "油焖": "炖", "红烧": "炖", "烧": "炖",
}

MAIN_REMAP = {
    "饮品": "其他",
    "禽类": "白肉", "禽肉": "白肉",
    "肉类": "红肉", "肉": "红肉",
}

DISH_ROLE_REMAP = {
    "主厨推荐": "主菜",
    "甜品": "小食",
    "凉菜": "配菜",
}

GRAIN_REMAP = {
    "燕麦": "粗粮",
    "糙米": "糙米杂粮",
    "全麦": "全麦面",
    "玉米": "粗粮",
    "红薯": "粗粮", "紫薯": "粗粮", "藜麦": "粗粮",
    "面": "精制面", "饭": "白米", "粉": "白米",
}


def normalize_records(records: list[dict]) -> tuple[list[dict], dict]:
    """返回 (修后 records, 统计 dict)."""
    stats: dict[str, Counter] = {
        "cooking_method": Counter(),
        "main_ingredient_type": Counter(),
        "dish_role": Counter(),
        "grain_type": Counter(),
    }
    for rec in records:
        np_ = rec.get("nutrition_profile", {})

        old = np_.get("cooking_method")
        if old in COOKING_REMAP:
            np_["cooking_method"] = COOKING_REMAP[old]
            stats["cooking_method"][f"{old} → {COOKING_REMAP[old]}"] += 1

        old = np_.get("main_ingredient_type")
        if old in MAIN_REMAP:
            np_["main_ingredient_type"] = MAIN_REMAP[old]
            stats["main_ingredient_type"][f"{old} → {MAIN_REMAP[old]}"] += 1

        old = np_.get("dish_role")
        if old in DISH_ROLE_REMAP:
            np_["dish_role"] = DISH_ROLE_REMAP[old]
            stats["dish_role"][f"{old} → {DISH_ROLE_REMAP[old]}"] += 1

        old = np_.get("grain_type")
        if old in GRAIN_REMAP:
            np_["grain_type"] = GRAIN_REMAP[old]
            stats["grain_type"][f"{old} → {GRAIN_REMAP[old]}"] += 1

    return records, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="path 到 dishes_tagged.json, 或 'all' (两 zone)")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印统计, 不写文件")
    args = ap.parse_args(argv)

    if args.target == "all":
        targets = [ROOT / "data" / z / "dishes_tagged.json"
                   for z in ("home", "shenzhen-bay")]
    else:
        p = Path(args.target)
        targets = [p if p.is_absolute() else (ROOT / p)]

    for path in targets:
        if not path.exists():
            print(f"[skip] {path} 不存在")
            continue
        recs = json.loads(path.read_text(encoding="utf-8"))
        recs, stats = normalize_records(recs)
        total_remap = sum(sum(c.values()) for c in stats.values())
        print(f"\n=== {path.relative_to(ROOT)} ===")
        print(f"总记录: {len(recs)}, 修了 {total_remap} 处")
        for field, c in stats.items():
            if c:
                print(f"  {field}:")
                for k, v in c.most_common():
                    print(f"    {v:>4}  {k}")

        if args.dry_run:
            continue
        path.write_text(json.dumps(recs, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print(f"  写回: {path.relative_to(ROOT)}")

        # 复校 schema
        try:
            from chisha.schemas import validate_dishes_tagged
            validate_dishes_tagged(recs)
            print("  schema validate: PASS")
        except Exception as e:
            print(f"  schema validate FAIL: {str(e)[:300]}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

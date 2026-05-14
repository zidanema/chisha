"""LLM 打标脚本: dishes_raw.json + restaurants.json → dishes_tagged.json.

用法:
    python -m scripts.tag_dishes <office_zone> [--limit N] [--batch 30] [--resume]
    python -m scripts.tag_dishes home --limit 50  # spike
    python -m scripts.tag_dishes home            # 全量
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

from chisha.llm_client import call_text

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "prompts" / "tag_dishes.md"

# 必需字段（v3, D-032 加 5 字段：dish_role / processed_meat_flag /
# sweet_sauce_level / wetness / grain_type）
REQUIRED = {
    "dish_id", "canonical_name", "cuisine", "main_ingredient_type",
    "cooking_method", "oil_level", "protein_grams_estimate",
    "vegetable_ratio_estimate", "is_complete_meal", "spicy_level",
    "dish_role", "processed_meat_flag", "sweet_sauce_level", "wetness",
    "grain_type", "tags",
}

_DISH_ROLE_VALUES = {"主菜", "主食", "配菜", "汤", "小食", "饮品", "套餐"}
_GRAIN_TYPE_VALUES = {"白米", "糙米杂粮", "精制面", "全麦面",
                      "粗粮", "粥", "无"}


def load_data(zone: str) -> tuple[dict, list]:
    """读 restaurants + dishes_raw, 返回 (rest_by_id, dishes_raw)."""
    base = ROOT / "data" / zone
    rests = json.loads((base / "restaurants.json").read_text(encoding="utf-8"))
    dishes = json.loads((base / "dishes_raw.json").read_text(encoding="utf-8"))
    return {r["id"]: r for r in rests}, dishes


def build_input_payload(rest_by_id: dict, batch: list[dict]) -> str:
    """打标输入 = dish_id + raw_name + restaurant_name + restaurant_category_raw + category_raw + price."""
    items = []
    for d in batch:
        r = rest_by_id.get(d["restaurant_id"], {})
        items.append({
            "dish_id": d["dish_id"],
            "raw_name": d["raw_name"],
            "restaurant_name": r.get("name", ""),
            "restaurant_category_raw": r.get("category", ""),
            "category_raw": d.get("category_raw"),
            "price": d.get("price", 0),
        })
    return json.dumps(items, ensure_ascii=False)


def extract_json_array(text: str) -> list:
    """从 LLM 输出抠出 JSON 数组. 容忍 ```json 包围."""
    text = text.strip()
    # 去掉可能的 markdown code fence
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array found in: {text[:200]}")
    return json.loads(text[start:end + 1])


def validate_record(rec: dict) -> list[str]:
    """返回缺失/不合法字段列表 (空 = OK). v3, D-032 含 5 新字段。"""
    issues = []
    missing = REQUIRED - set(rec.keys())
    if missing:
        issues.append(f"missing: {missing}")
    if "oil_level" in rec and rec["oil_level"] not in (1, 2, 3, 4, 5):
        issues.append(f"oil_level invalid: {rec['oil_level']}")
    if "spicy_level" in rec and rec["spicy_level"] not in (0, 1, 2, 3):
        issues.append(f"spicy_level invalid: {rec['spicy_level']}")
    if "sweet_sauce_level" in rec and rec["sweet_sauce_level"] \
            not in (0, 1, 2, 3):
        issues.append(f"sweet_sauce_level invalid: {rec['sweet_sauce_level']}")
    if "wetness" in rec and rec["wetness"] not in (1, 2, 3):
        issues.append(f"wetness invalid: {rec['wetness']}")
    if "vegetable_ratio_estimate" in rec:
        v = rec["vegetable_ratio_estimate"]
        if not (isinstance(v, (int, float)) and 0.0 <= v <= 1.0):
            issues.append(f"vegetable_ratio_estimate invalid: {v}")
    if "dish_role" in rec and rec["dish_role"] not in _DISH_ROLE_VALUES:
        issues.append(f"dish_role invalid: {rec['dish_role']!r}")
    if "grain_type" in rec and rec["grain_type"] not in _GRAIN_TYPE_VALUES:
        issues.append(f"grain_type invalid: {rec['grain_type']!r}")
    if "processed_meat_flag" in rec \
            and not isinstance(rec["processed_meat_flag"], bool):
        issues.append(
            f"processed_meat_flag must be bool: {rec['processed_meat_flag']!r}"
        )
    return issues


def tag_batch(rest_by_id: dict, batch: list[dict], prompt_template: str,
              max_retries: int = 3) -> list[dict]:
    """打标一批 dishes, 返回 tagged list."""
    payload = build_input_payload(rest_by_id, batch)
    prompt = prompt_template.replace("{INPUT_DISHES_JSON}", payload)

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            # D-047: call_text 返回 dict, text 模式取 .content
            resp = call_text(prompt, max_tokens=8192, temperature=0.0)
            text = resp.get("content", "")
            recs = extract_json_array(text)
            if len(recs) != len(batch):
                raise ValueError(
                    f"count mismatch: input {len(batch)}, output {len(recs)}"
                )
            for r in recs:
                issues = validate_record(r)
                if issues:
                    raise ValueError(f"record {r.get('dish_id')}: {issues}")
            return recs
        except Exception as e:
            last_err = e
            print(f"  [attempt {attempt}] {type(e).__name__}: {str(e)[:200]}",
                  file=sys.stderr)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"failed after {max_retries} attempts: {last_err}")


def merge_into_output(
    raw_dishes_idx: dict, tagged_records: list[dict]
) -> list[dict]:
    """tagged 记录 + raw 字段 → §5.2 dishes_tagged 完整对象 (v3, D-032).

    v3 新增 5 字段 (dish_role / processed_meat_flag / sweet_sauce_level /
    wetness / grain_type) 自动 copy 进 nutrition_profile。
    """
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    out = []
    for rec in tagged_records:
        raw = raw_dishes_idx.get(rec["dish_id"])
        if not raw:
            print(f"  [warn] tagged dish_id {rec['dish_id']} not in raw, skip",
                  file=sys.stderr)
            continue
        out.append({
            "dish_id": rec["dish_id"],
            "restaurant_id": raw["restaurant_id"],
            "raw_name": raw["raw_name"],
            "canonical_name": rec["canonical_name"],
            "price": raw["price"],
            "monthly_sales": raw["monthly_sales"],
            "cuisine": rec["cuisine"],
            "nutrition_profile": {
                "main_ingredient_type": rec["main_ingredient_type"],
                "cooking_method": rec["cooking_method"],
                "oil_level": rec["oil_level"],
                "protein_grams_estimate": rec["protein_grams_estimate"],
                "vegetable_ratio_estimate": rec["vegetable_ratio_estimate"],
                "is_complete_meal": rec["is_complete_meal"],
                "spicy_level": rec["spicy_level"],
                "dish_role": rec["dish_role"],
                "processed_meat_flag": rec["processed_meat_flag"],
                "sweet_sauce_level": rec["sweet_sauce_level"],
                "wetness": rec["wetness"],
                "grain_type": rec["grain_type"],
                "tags": rec.get("tags", []),
            },
            "metadata": {
                "tagged_at": now,
                "tag_version": "v3",
                "is_available": True,
            },
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zone", help="office_zone, e.g. home")
    ap.add_argument("--limit", type=int, default=None,
                    help="只打前 N 条（spike 用）")
    ap.add_argument("--batch", type=int, default=30, help="每批菜品数")
    ap.add_argument("--resume", action="store_true",
                    help="跳过已打标的 dish_id")
    ap.add_argument("--out", type=str, default=None,
                    help="输出文件名 (默认 dishes_tagged.json 或 _sample.json)")
    args = ap.parse_args()

    rest_by_id, dishes_raw = load_data(args.zone)
    raw_idx = {d["dish_id"]: d for d in dishes_raw}
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")

    out_name = args.out or (
        "dishes_tagged_sample.json" if args.limit else "dishes_tagged.json"
    )
    out_path = ROOT / "data" / args.zone / out_name

    existing = []
    done_ids: set[str] = set()
    if args.resume and out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        done_ids = {r["dish_id"] for r in existing}
        print(f"[resume] {len(done_ids)} 条已存在，跳过")

    todo = [d for d in dishes_raw if d["dish_id"] not in done_ids]
    if args.limit:
        todo = todo[:args.limit]

    print(f"[plan] 待打标 {len(todo)} 条，每批 {args.batch} 条，"
          f"约 {-(-len(todo)//args.batch)} 批")

    all_tagged = list(existing)
    fail_dish_ids: list[str] = []
    for i in range(0, len(todo), args.batch):
        batch = todo[i:i + args.batch]
        bn = i // args.batch + 1
        total_b = -(-len(todo) // args.batch)
        print(f"[batch {bn}/{total_b}] {len(batch)} 条 "
              f"({batch[0]['dish_id']} ~ {batch[-1]['dish_id']})")
        try:
            tagged_recs = tag_batch(rest_by_id, batch, prompt_template)
            new_objs = merge_into_output(raw_idx, tagged_recs)
            all_tagged.extend(new_objs)
            # 每批落盘 (resume 友好)
            out_path.write_text(
                json.dumps(all_tagged, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  ✓ 累计 {len(all_tagged)} 条 → {out_path}")
        except Exception as e:
            print(f"  ✗ 整批失败: {e}", file=sys.stderr)
            fail_dish_ids.extend(d["dish_id"] for d in batch)

    print(f"\n[done] 成功 {len(all_tagged)} 条, 失败 {len(fail_dish_ids)} 条")
    if fail_dish_ids:
        fail_path = out_path.with_suffix(".failed.json")
        fail_path.write_text(
            json.dumps(fail_dish_ids, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  失败 dish_id 列表 → {fail_path}")


if __name__ == "__main__":
    main()

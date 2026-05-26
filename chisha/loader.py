"""raw collector data → §5.2 schema 映射.

输入: chisha-collector 输出的 home/office_restaurants.json
输出: restaurants.json (§5.2) + dishes_raw.json (§5.2 待打标版)

实体 id 是稳定哈希 (D-099), 不再按文件位置发号:
- rid     = "r_" + sha1(normalize_shop_name_v1(name))[:10]   ← 与采集端 rid 逐字一致
- dish_id = "d_" + <rid 去前缀> + "_" + sha1(normalize_dish_name_v1(raw_name))[:8]
重采→重消费后同店/同菜 id 不变, 历史反馈/标签永远映射得上 (见 docs/proposals/2026-05-26-stable-entity-id.md)。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from chisha.collector_contract import validate_collector_output


# ============================================================
# 稳定实体 id (D-099)
# ============================================================
# normalize_*_name_v1 逐字复现采集端 collector/text_norm.py (NORMALIZED_NAME_VERSION=1)。
# 映射表用 codepoint 转义构造而非复制不可见字符, 保证与采集端字节一致 (test 对拍采集端函数)。
# 显式不动: 大小写 / 中点 / 标点 / 价格 / 规格份量 —— 这些常是真不同实体。
SHOP_NAME_VERSION = 1   # == collector NORMALIZED_NAME_VERSION
DISH_NAME_VERSION = 1   # 复用同一套保守规则; 菜名归一化在采集端尚无定义, 此处定版

_NAME_NORM_MAP = str.maketrans({
    " ": " ",  # NBSP
    " ": " ",  # SIX-PER-EM SPACE
    "　": " ",  # IDEOGRAPHIC SPACE
    "\t": " ",
    "\r": " ",
    "\n": " ",
    "​": "",   # ZERO WIDTH SPACE
    "‌": "",   # ZWNJ
    "‍": "",   # ZWJ
    "⁠": "",   # WORD JOINER
    "﻿": "",   # BOM
    "（": "(",  # 全角左括号
    "）": ")",  # 全角右括号
})


def _normalize_name_v1(name: str | None) -> str:
    """保守归一化: Unicode 空白→0x20 / 零宽删 / 全角括号→半角 / collapse 连空格 / strip."""
    if not name:
        return ""
    s = name.translate(_NAME_NORM_MAP)
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip()


def normalize_shop_name_v1(name: str | None) -> str:
    """店名归一化 (== collector normalize_shop_name)."""
    return _normalize_name_v1(name)


def normalize_dish_name_v1(name: str | None) -> str:
    """菜名归一化 (复用店名那套保守规则, DISH_NAME_VERSION=1)."""
    return _normalize_name_v1(name)


def restaurant_rid(name: str | None) -> str:
    """店名 → 全局稳定 rid (含 r_ 前缀). 归一化后为空 → fail-loud."""
    norm = normalize_shop_name_v1(name)
    if not norm:
        raise ValueError(f"empty shop name after normalization: {name!r}")
    return "r_" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:10]


def dish_id_for(rid: str, raw_name: str | None) -> str:
    """(rid, 菜名) → restaurant-scoped 稳定 dish_id. 归一化后为空 → fail-loud."""
    norm = normalize_dish_name_v1(raw_name)
    if not norm:
        raise ValueError(f"empty dish name after normalization: {raw_name!r}")
    stem = rid[2:] if rid.startswith("r_") else rid
    return "d_" + stem + "_" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:8]


# ============================================================
# alias 表 (D-099.2): 人工确认的旧名 → canonical rid
# ============================================================
_RID_RE = re.compile(r"^r_[0-9a-f]{10}$")


def load_aliases(path: str | Path | None) -> dict[str, str]:
    """读 alias 表 (归一化旧名 → "r_<hex>"). 不存在 → 空. 格式非法 → fail-loud."""
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    doc = json.loads(p.read_text(encoding="utf-8"))
    aliases = doc.get("aliases", {}) if isinstance(doc, dict) else {}
    for k, v in aliases.items():
        if not _RID_RE.match(v):
            raise ValueError(f"alias {k!r} → {v!r} 不是合法 rid (r_<10hex>)")
    # 1-level 环检测: alias 的归一化 key 本身又是另一条 alias 的 canonical rid 来源时拒绝
    norm_keys = {normalize_shop_name_v1(k) for k in aliases}
    for k in aliases:
        if normalize_shop_name_v1(k) != k:
            raise ValueError(f"alias key {k!r} 未归一化 (应存归一化后的名字)")
    if len(norm_keys) != len(aliases):
        raise ValueError("alias 表有归一化后重复的 key (同名多目标)")
    return dict(aliases)


def _resolve_rid(raw_name: str, aliases: dict[str, str]) -> str:
    """店名 → rid, alias 命中优先 (alias 先于哈希计算生效)."""
    norm = normalize_shop_name_v1(raw_name)
    if norm in aliases:
        return aliases[norm]
    return restaurant_rid(raw_name)


# ============================================================
# raw 字段解析
# ============================================================
def parse_monthly_sales(s: str | None) -> int:
    """月售1000+ → 1000 (取下界); 月售42 → 42; 空/None → 0."""
    if not s:
        return 0
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else 0


def parse_distance_m(s: str | None) -> int:
    """504m → 504; 1.2km → 1200; 空/None → -1 (未知)."""
    if not s:
        return -1
    s = s.strip().lower()
    m = re.match(r"([\d.]+)\s*(km|m)?", s)
    if not m:
        return -1
    val = float(m.group(1))
    unit = m.group(2) or "m"
    return int(val * 1000) if unit == "km" else int(val)


def parse_eta_min(s: str | None) -> int:
    """约15分钟 → 15; 约1小时 → 60; 约1.5小时 → 90; 空/None → -1."""
    if not s:
        return -1
    m = re.search(r"([\d.]+)\s*(小时|分钟|min|h)", s)
    if not m:
        return -1
    val = float(m.group(1))
    unit = m.group(2)
    return int(val * 60) if unit in ("小时", "h") else int(val)


def load_raw(raw_path: str | Path) -> dict[str, Any]:
    """读 collector 原始 JSON + 窄契约校验 (B2, fail-loud, 无 grandfather).

    校验 envelope shape/类型/版本, 并断言 normalized_name_version == SHOP_NAME_VERSION
    (归一化单边漂移 → 稳定 id 全面 mis-join, D-099)。喂旧无版本/字段漂移/版本不匹配文件
    → ContractViolation, 不静默吞。契约定义见 chisha/collector_contract.py。
    """
    with open(raw_path, encoding="utf-8") as f:
        raw = json.load(f)
    validate_collector_output(raw, expected_norm_version=SHOP_NAME_VERSION)
    return raw


_BRAND_SUFFIX_TOKENS = ("馆", "店", "店铺", "餐厅", "食堂", "总店", "分店",
                        "旗舰店", "大酒店")


def extract_brand(name: str) -> str:
    """去括号分店 + 去尾部'馆/店/餐厅'类后缀，提取品牌名.

    '安天民北方饺子（侨香店）' → '安天民北方饺子'
    '安天民北方饺子馆（景田店）' → '安天民北方饺子'
    '湘小小长沙菜(景田北店)' → '湘小小长沙菜'
    """
    n = re.sub(r"\s*[（(][^)）]*[)）]\s*$", "", name)
    n = re.sub(r"\s*\[[^\]]*\]\s*$", "", n)
    n = n.strip()
    # 去尾部品牌后缀（最多迭代 2 次，比如"X 餐厅店"两次）
    for _ in range(2):
        for suf in sorted(_BRAND_SUFFIX_TOKENS, key=len, reverse=True):
            if n.endswith(suf) and len(n) > len(suf) + 1:
                n = n[: -len(suf)].strip()
                break
        else:
            break
    return n or name


# ============================================================
# 餐厅去重: 同 rid 取单一权威记录 (D-099.1)
# ============================================================
_MENU_STATUS_PRIORITY = {"ok": 4, "early_ok": 3, "partial": 2, "failed": 1}


def _status_rank(r: dict) -> int:
    return _MENU_STATUS_PRIORITY.get(r.get("menu_status"), 0)  # None/unknown → 0


def _menu_content_hash(r: dict) -> str:
    """菜单内容指纹 (确定性 tie-break; 内容相同的重复行折叠到同一指纹)."""
    menu = r.get("menu", []) or []
    sig = [(m.get("name", ""), float(m.get("price") or 0.0),
            m.get("category")) for m in menu]
    sig.sort(key=lambda x: (x[0], x[1], str(x[2])))
    blob = json.dumps(sig, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _pick_authoritative(rid: str, rows: list[dict]) -> tuple[dict, dict | None]:
    """同 rid 多条 → 选权威记录. 返回 (auth_row, ambiguity_conflict_or_None).

    优先级: menu_status > menu_count > 内容指纹 (不取并集, 不用输入顺序).
    同 (status, count) 但内容指纹不同 → 餐厅级歧义 (conflict), 仍取指纹最小者保确定性.
    """
    if len(rows) == 1:
        return rows[0], None
    ranked = sorted(
        rows,
        key=lambda r: (_status_rank(r), int(r.get("menu_count", 0) or 0),
                       _menu_content_hash(r)),
        reverse=True,
    )
    top = ranked[0]
    tied = [r for r in rows
            if _status_rank(r) == _status_rank(top)
            and int(r.get("menu_count", 0) or 0) == int(top.get("menu_count", 0) or 0)]
    distinct_content = {_menu_content_hash(r) for r in tied}
    conflict = None
    if len(distinct_content) > 1:
        conflict = {
            "type": "restaurant_ambiguity",
            "key": f"rest:{rid}#{_conflict_digest(sorted(distinct_content))}",
            "rid": rid,
            "restaurant_name": top.get("name", ""),
            "detail": {
                "tied_rows": len(tied),
                "distinct_content_hashes": sorted(distinct_content),
                "menu_status": top.get("menu_status"),
                "menu_count": top.get("menu_count"),
            },
        }
    return top, conflict


# ============================================================
# 菜品: 同店内 (rid, 归一菜名) 冲突检测 (D-099.1)
# ============================================================
def _conflict_digest(payload: Any) -> str:
    """冲突内容指纹 (短). 进 conflict key → 冲突内容变化 (如价格) 时 key 变,
    旧 ack 不再命中 → 强制重新人工复审 (codex 防"旧 ack 覆盖新冲突")。"""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:8]
def _build_dishes(rid: str, auth: dict) -> tuple[list[dict], list[dict]]:
    """从权威餐厅记录建 active dishes + dish 级 conflicts.

    冲突 (隔离, 不进 active):
    - 同归一菜名 → 多个不同 price (真不同 SKU, 截断同名): dish_name_price
    - 不同归一菜名 → 同 8-hex (哈希碰撞): dish_hash_collision
    - 归一后空菜名: empty_dish_name
    销量(monthly_sales)差异不算冲突 (D-099.1: 价/销变化不改 id; 销量是噪声).
    """
    menu = auth.get("menu", []) or []
    by_name: dict[str, list[dict]] = defaultdict(list)
    empty_conflicts: list[dict] = []
    for j, m in enumerate(menu):
        norm = normalize_dish_name_v1(m.get("name", ""))
        if not norm:
            empty_conflicts.append({
                "type": "empty_dish_name",
                "key": f"emptydish:{rid}:idx{j}",
                "rid": rid,
                "restaurant_name": auth.get("name", ""),
                "detail": {"raw_name": m.get("name", ""), "index": j},
            })
            continue
        by_name[norm].append(m)

    conflicts: list[dict] = list(empty_conflicts)
    # 第一遍: 剔同名异价冲突, 给存活菜名算 (did, h8)
    survivors: dict[str, dict] = {}   # norm_name → {did, h8, best_row}
    by_hash: dict[str, list[str]] = defaultdict(list)  # h8 → [norm_name...]
    for norm, rows in by_name.items():
        prices = {round(float(r.get("price") or 0.0), 2) for r in rows}
        if len(prices) > 1:
            conflicts.append({
                "type": "dish_name_price",
                # key 带价格指纹: 价格集变了 → 新冲突需重新 ack (不被旧 ack 覆盖)
                "key": f"dish:{rid}:{norm}#{_conflict_digest(sorted(prices))}",
                "rid": rid,
                "restaurant_name": auth.get("name", ""),
                "norm_name": norm,
                "detail": {
                    "prices": sorted(prices),
                    "raw_names": sorted({r.get("name", "") for r in rows}),
                },
            })
            continue  # 整组隔离, 无法确定哪个 price 是 canonical
        # 同名同价的多条 → 折叠取销量最大者 (sales 噪声, 非冲突)
        best = max(rows, key=lambda r: parse_monthly_sales(r.get("monthly_sales")))
        did = dish_id_for(rid, best.get("name", ""))
        h8 = did.rsplit("_", 1)[-1]
        survivors[norm] = {"did": did, "h8": h8, "best": best}
        by_hash[h8].append(norm)

    # 第二遍: 8-hex 碰撞 (不同归一名同 hash) → **两边都隔离** (该 dish_id 已污染, 不能信)
    poisoned: set[str] = set()
    for h8, names in by_hash.items():
        if len(names) > 1:
            poisoned.add(h8)
            conflicts.append({
                "type": "dish_hash_collision",
                "key": f"hashcoll:{rid}:{h8}#{_conflict_digest(sorted(names))}",
                "rid": rid,
                "restaurant_name": auth.get("name", ""),
                "detail": {"hash": h8, "names": sorted(names)},
            })

    dishes: list[dict] = []
    for norm, s in survivors.items():
        if s["h8"] in poisoned:
            continue  # 碰撞污染, 隔离
        best = s["best"]
        dishes.append({
            "dish_id": s["did"],
            "restaurant_id": rid,
            "raw_name": best.get("name", ""),
            "price": float(best.get("price") or 0.0),
            "monthly_sales": parse_monthly_sales(best.get("monthly_sales")),
            "category_raw": best.get("category"),  # 商家自定义分组，仅参考
        })
    return dishes, conflicts


def normalize(
    raw: dict[str, Any],
    office_zone: str,
    city: str = "深圳",
    *,
    aliases: dict[str, str] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """raw → (restaurants_normalized, dishes_raw_flat, conflicts).

    稳定哈希 id + 同 rid 去重 (权威记录) + 菜品冲突隔离.
    冲突 dish/餐厅不进 active 输出, 全部汇总进第三个返回值待人工裁决.
    restaurants[i].category 暂留空，由 LLM 打标后 majority vote 回填。
    """
    aliases = aliases or {}
    by_rid: dict[str, list[dict]] = defaultdict(list)
    rest_conflicts: list[dict] = []
    for r in raw.get("restaurants", []):
        name = r.get("name", "")
        if not normalize_shop_name_v1(name):
            rest_conflicts.append({
                "type": "empty_restaurant_name",
                "key": f"emptyrest:{name!r}",
                "rid": None,
                "restaurant_name": name,
                "detail": {"raw_name": name},
            })
            continue
        by_rid[_resolve_rid(name, aliases)].append(r)

    restaurants_out: list[dict] = []
    dishes_out: list[dict] = []
    conflicts: list[dict] = list(rest_conflicts)
    for rid in sorted(by_rid):  # 确定性顺序
        rows = by_rid[rid]
        auth, amb = _pick_authoritative(rid, rows)
        if amb:
            # 餐厅级歧义 (同 status+count 内容不同, 无法确定权威记录) → 整店隔离不进 active,
            # 与菜品冲突一致 (隔离不猜); 报告留候选供人工裁决/加 alias 后再发布。
            conflicts.append(amb)
            continue
        restaurants_out.append({
            "id": rid,
            "name": auth.get("name", ""),
            "brand": extract_brand(auth.get("name", "")),
            "category": "",  # 待 majority vote 回填
            "city": city,
            "office_zone": office_zone,
            "rating": auth.get("rating") or 0.0,
            "monthly_orders": parse_monthly_sales(auth.get("monthly_sales")),
            "distance_m": parse_distance_m(auth.get("distance")),
            "delivery_eta_min": parse_eta_min(auth.get("delivery_time")),
            "delivery_fee": auth.get("delivery_fee") or 0.0,
            "min_order": auth.get("min_order") or 0.0,
            "raw_menu_count": auth.get("menu_count", 0),
            "raw_menu_status": auth.get("menu_status", "unknown"),
        })
        dishes, dconf = _build_dishes(rid, auth)
        dishes_out.extend(dishes)
        conflicts.extend(dconf)
    return restaurants_out, dishes_out, conflicts


# ============================================================
# 落盘: 原子发布 + 冲突 staged/ack 状态机 (D-099.1)
# ============================================================
def _atomic_write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, p)


def _atomic_write_pair(items: list[tuple[Path, Any]]) -> None:
    """成对写: 先把所有内容写到 .tmp (任一写失败则两个 active 都不动), 全成功后才连续 os.replace。
    替换按 items 顺序 → **调用方把"live 链路消费的文件"放最后** (codex BLOCK#3):
    dishes_raw.json 仅离线 tag 链路顺序消费, restaurants.json 才被 live recall 读;
    先翻 dishes_raw 再翻 restaurants → live 链路在最后那次原子 replace 前只见旧 restaurants,
    之后见新, 永不见跨代混合; 离线 tag 在 loader 之后跑, 见到的两文件已都是新代。"""
    tmps: list[tuple[Path, Path]] = []
    for p, obj in items:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmps.append((tmp, p))
    for tmp, p in tmps:  # 全部 .tmp 写成功后才开始替换 (顺序 = items 顺序)
        os.replace(tmp, p)


def ingest_lock_path(out_dir: str | Path) -> Path:
    return Path(out_dir) / ".ingest_lock"


def ingest_in_progress(out_dir: str | Path) -> bool:
    """active 数据是否处于"发布中/上次发布未完成"状态 (codex BLOCK#3).
    离线 tag 脚本读 restaurants.json + dishes_raw.json 前应检查, 命中则拒绝跑
    (防读到 loader 两次 replace 之间崩溃留下的跨代混合)。loader 成功收尾会清除。"""
    return ingest_lock_path(out_dir).exists()


def load_conflict_acks(ack_path: str | Path) -> set[str]:
    """已人工确认的冲突 key 集合 (committed manifest)."""
    p = Path(ack_path)
    if not p.exists():
        return set()
    doc = json.loads(p.read_text(encoding="utf-8"))
    return set(doc.get("acknowledged", []) if isinstance(doc, dict) else [])


def write_normalized(
    raw_path: str | Path,
    out_dir: str | Path,
    office_zone: str,
    city: str = "深圳",
    *,
    aliases_path: str | Path | None = None,
) -> dict[str, Any]:
    """读 raw → normalize → 原子写 restaurants.json + dishes_raw.json.

    冲突状态机 (D-099.1, codex pressure-test):
    - 始终把全部冲突写 <out_dir>/dish_id_conflicts.json (报告).
    - 未确认冲突 (不在 conflicts_ack.json) → 只写 <out_dir>/_staged/*, 不动 active, published=False.
    - 全部冲突已确认 → 隔离冲突 dish/餐厅, 原子写 active, published=True.
    返回 stats dict (含 published / unacknowledged / quarantined 计数).
    """
    out_dir = Path(out_dir)
    aliases = load_aliases(aliases_path) if aliases_path else (
        load_aliases(out_dir.parent / "aliases.json"))
    raw = load_raw(raw_path)
    restaurants, dishes, conflicts = normalize(
        raw, office_zone=office_zone, city=city, aliases=aliases)

    ack = load_conflict_acks(out_dir / "conflicts_ack.json")
    unacked = [c for c in conflicts if c["key"] not in ack]

    # 报告始终落盘
    _atomic_write_json(out_dir / "dish_id_conflicts.json", {
        "zone": office_zone,
        "total": len(conflicts),
        "unacknowledged": len(unacked),
        "conflicts": conflicts,
    })

    rest_path = out_dir / "restaurants.json"
    dish_path = out_dir / "dishes_raw.json"
    if unacked:
        staged = out_dir / "_staged"
        _atomic_write_pair([(staged / "restaurants.json", restaurants),
                            (staged / "dishes_raw.json", dishes)])
        return {
            "published": False,
            "zone": office_zone,
            "restaurants": len(restaurants),
            "dishes": len(dishes),
            "conflicts_total": len(conflicts),
            "unacknowledged": len(unacked),
            "unacked_keys": [c["key"] for c in unacked][:50],
            "staged_dir": str(staged),
        }

    # 发布期间打 ingest lock: 两次 replace 之间若被 kill, marker 留存 → 离线 tag 拒绝读混合态。
    # 任何失败 (异常/崩溃) 都不清除 marker (留作 poison); 仅全部成功后清除。
    lock = ingest_lock_path(out_dir)
    lock.write_text(office_zone, encoding="utf-8")
    # restaurants.json 放最后 (live 链路消费), dishes_raw.json 先翻 (仅离线 tag 消费)
    _atomic_write_pair([(dish_path, dishes), (rest_path, restaurants)])
    lock.unlink(missing_ok=True)  # 仅在成功后清除
    return {
        "published": True,
        "zone": office_zone,
        "restaurants": len(restaurants),
        "dishes": len(dishes),
        "conflicts_total": len(conflicts),
        "quarantined": len(conflicts),
        "rest_path": str(rest_path),
        "dish_path": str(dish_path),
    }


def majority_cuisine(dishes_tagged: list[dict], restaurant_id: str) -> str:
    """从 tagged dishes 给 restaurant 投票 majority cuisine."""
    cuisines = [
        d.get("cuisine", "")
        for d in dishes_tagged
        if d.get("restaurant_id") == restaurant_id and d.get("cuisine")
    ]
    if not cuisines:
        return ""
    return Counter(cuisines).most_common(1)[0][0]


def backfill_restaurant_category(
    restaurants_path: str | Path,
    dishes_tagged_path: str | Path,
) -> int:
    """读 dishes_tagged.json → majority vote → 回填 restaurants.json.category. 返回更新条数."""
    rest_path = Path(restaurants_path)
    restaurants = json.loads(rest_path.read_text(encoding="utf-8"))
    dishes_tagged = json.loads(Path(dishes_tagged_path).read_text(encoding="utf-8"))
    updated = 0
    for r in restaurants:
        cuisine = majority_cuisine(dishes_tagged, r["id"])
        if cuisine and r.get("category") != cuisine:
            r["category"] = cuisine
            updated += 1
    rest_path.write_text(
        json.dumps(restaurants, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return updated


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: python -m chisha.loader <raw_path> <office_zone> [city]")
        sys.exit(1)
    raw_path = sys.argv[1]
    zone = sys.argv[2]
    city = sys.argv[3] if len(sys.argv) > 3 else "深圳"
    out_dir = Path(__file__).parent.parent / "data" / zone
    stats = write_normalized(raw_path, out_dir, zone, city)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if not stats["published"]:
        print(f"\n⚠ 未发布: {stats['unacknowledged']} 个未确认冲突, "
              f"已写 staged ({stats['staged_dir']}) + dish_id_conflicts.json。\n"
              f"  审阅后把冲突 key 加进 data/{zone}/conflicts_ack.json 的 "
              f"\"acknowledged\" 列表再重跑。", file=sys.stderr)
        sys.exit(3)
    print(f"\n✓ published: {stats['restaurants']} restaurants, "
          f"{stats['dishes']} dishes, {stats['quarantined']} quarantined。")

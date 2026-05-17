"""T-P2-02: 簇式输出 — intent 内部子类多样化 (brief §6 + §10 P2-02).

解决 D-073.1 副作用: cuisine_want 免 3 层 cap 后, 同品牌连锁日料 / 萨莉亚式刷屏.
策略: 在 refine 模式下, 给同 cuisine 的 candidates 按子类 (subtype) 分桶,
最后 5 道时要求至少覆盖 3+ 个子类 (纵向多样性 vs 横向 cap).

子类判定: 走规则/词表 + cooking_method/main_ingredient_type 推断, 不引入 LLM.

边界:
  - refine 模式触发 (intent.cuisine_want 非空); 空 refine 路径完全不进 → baseline 0 diff
  - 不破坏 D-073.1 (cuisine_want 免 3 层 cap)
  - 不引入新 LLM 调用
  - 仅对 candidates list 重排, 不砍数量 (cap 在 apply_caps 阶段已做)
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ────────────────────────── 子类词表 (8 主菜系)
#
# (cuisine, subtype, keywords): keyword 命中 dish_name 或 cooking_method 视作该子类.
# 第一个匹配的 subtype 生效. 没匹配的菜归入 "其他".

CuisineSubtypeRules = list[tuple[str, list[str]]]

_SUBTYPE_RULES: dict[str, CuisineSubtypeRules] = {
    "湘菜": [
        ("腊味", ["腊", "烟熏"]),
        ("剁椒", ["剁椒", "椒"]),
        ("小炒", ["小炒", "炒"]),
        ("家常", ["家常", "炖", "煨", "焖"]),
        ("汤煲", ["汤", "煲"]),
    ],
    "川菜": [
        ("火锅", ["火锅", "麻辣烫", "冒菜"]),
        ("毛血旺", ["毛血旺", "水煮"]),
        ("回锅肉", ["回锅", "回锅肉"]),
        ("家常", ["家常", "炒"]),
        ("汤煲", ["汤", "煲"]),
    ],
    "粤菜": [
        ("烧腊", ["烧腊", "叉烧", "烧鹅", "烧鸭"]),
        ("点心", ["点心", "包", "饺", "粉", "肠粉"]),
        ("白切", ["白切", "蒸"]),
        ("煲汤", ["煲", "汤"]),
        ("快炒", ["炒", "干炒"]),
    ],
    "日料": [
        ("拉面", ["拉面", "乌冬", "荞麦面"]),
        ("寿司", ["寿司", "刺身", "卷"]),
        ("居酒屋", ["居酒", "串烧", "烤串"]),
        ("定食", ["定食", "套餐"]),
        ("烤物", ["烤", "炙烧"]),
    ],
    "韩式": [
        ("烤肉", ["烤肉", "烤"]),
        ("拌饭", ["拌饭", "石锅"]),
        ("汤锅", ["汤", "锅", "炖"]),
        ("炸鸡", ["炸鸡", "炸"]),
        ("辣炒", ["辣炒", "炒"]),
    ],
    "潮汕": [
        ("牛肉火锅", ["牛肉火锅", "潮汕牛肉"]),
        ("粥粉", ["粥", "粉"]),
        ("卤味", ["卤", "卤水"]),
        ("打冷", ["打冷", "白切"]),
        ("家常", ["炒", "煮"]),
    ],
    "西餐": [
        ("意面", ["意面", "意粉", "pasta"]),
        ("沙拉", ["沙拉", "salad"]),
        ("披萨", ["披萨", "pizza"]),
        ("牛排", ["牛排", "steak"]),
        ("汉堡", ["汉堡", "三明治"]),
    ],
    "泰式": [
        ("冬阴功", ["冬阴功", "冬阴"]),
        ("咖喱", ["咖喱"]),
        ("炒粉炒饭", ["炒粉", "炒饭", "炒面"]),
        ("沙拉", ["沙拉"]),
        ("烤物", ["烤"]),
    ],
}


@dataclass
class SubtypeAssignment:
    """单 combo 的 (cuisine, subtype) 标签."""
    cuisine: str
    subtype: str           # 命中子类名, 或 "其他"


def infer_combo_subtype(combo: dict) -> SubtypeAssignment:
    """从 combo 推断 (cuisine, subtype). cuisine 从主菜 dish.cuisine 取."""
    dishes = combo.get("dishes") or []
    if not dishes:
        return SubtypeAssignment(cuisine="未知", subtype="其他")
    # cuisine: 取第一个非空
    cuisine = ""
    for d in dishes:
        if d.get("cuisine"):
            cuisine = d["cuisine"]
            break
    if not cuisine or cuisine not in _SUBTYPE_RULES:
        return SubtypeAssignment(cuisine=cuisine or "未知", subtype="其他")
    # 合并所有 dish 的 name + cooking_method
    text_pieces: list[str] = []
    for d in dishes:
        text_pieces.append(d.get("canonical_name") or "")
        text_pieces.append(d.get("raw_name") or "")
        np_ = d.get("nutrition_profile") or {}
        text_pieces.append(np_.get("cooking_method") or "")
    blob = " ".join(text_pieces)
    rules = _SUBTYPE_RULES[cuisine]
    for subtype, keywords in rules:
        for kw in keywords:
            if kw and kw in blob:
                return SubtypeAssignment(cuisine=cuisine, subtype=subtype)
    return SubtypeAssignment(cuisine=cuisine, subtype="其他")


def diversify_by_subtype(
    candidates: list[dict],
    *,
    target_subtypes: int = 3,
    max_per_subtype: int = 2,
) -> list[dict]:
    """T-P2-02: 在 candidates 内部按 subtype 重新分布. 不砍数量, 仅重排.

    策略:
      - 给每个 combo infer subtype
      - 按 subtype 分桶
      - round-robin 取桶头部 (每轮每桶取一个), 让前 N 道覆盖 ≥ target_subtypes 个 subtype
      - 每桶 head 取够 max_per_subtype 后停, 防止单子类刷屏

    边界:
      - candidates 不到 target_subtypes 种 subtype 时, 尽力而为, 不抛
      - 各 combo 在 sub-bucket 内部仍保持原相对顺序 (fit_score 不破坏)
    """
    if not candidates:
        return candidates
    # 给每 combo 打 subtype 标签
    annotated: list[tuple[SubtypeAssignment, dict]] = [
        (infer_combo_subtype(c), c) for c in candidates
    ]
    # 按 subtype 分桶 (保序)
    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    for sa, c in annotated:
        key = f"{sa.cuisine}/{sa.subtype}"
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(c)
    # round-robin: each pass take 1 from each bucket head (up to max_per_subtype)
    out: list[dict] = []
    taken_per_bucket: dict[str, int] = {k: 0 for k in order}
    while True:
        progress = False
        for key in order:
            if not buckets[key]:
                continue
            if taken_per_bucket[key] >= max_per_subtype:
                continue
            out.append(buckets[key].pop(0))
            taken_per_bucket[key] += 1
            progress = True
        if not progress:
            break
    # 若有桶 max_per_subtype 卡到, 但还有内容 (overflow), 把剩下的按原相对顺序续上
    overflow: list[tuple[int, dict]] = []
    for idx, (sa, c) in enumerate(annotated):
        if c in out:
            continue
        overflow.append((idx, c))
    overflow.sort(key=lambda x: x[0])
    out.extend(c for _, c in overflow)
    return out

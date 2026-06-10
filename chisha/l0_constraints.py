"""L0 三分判定 (D-080~D-085 + brief §3): refine 解除政策的执行层.

| 类型 | 例子 | refine 可否解除 |
|---|---|---|
| A 医学风险类 | 严重过敏 / 药物冲突 / 孕期忌口 / 术后忌口 | **永不可破** |
| B 身份伦理类 | 清真 / 素食 / 宗教忌口 | **永不可破**（只能 profile 改）|
| C 普通健康类 | 油上限 / 蔬菜占比 / 价格带 / 减脂目标 | refine 明确表达可破 |

profile schema (可选, 缺段视为空):
    l0_constraints:
      medical:
        allergies: ["花生", "海鲜"]
      identity:
        dietary_law: null  # "vegetarian" | "halal" | null

只承载 schema + 检查 helper, 不负责 trace 写入 (那是 recall.py 的事).
"""
from __future__ import annotations

from dataclasses import dataclass, field


# halal 拒判关键词 (Codex audit blocker #2: 不能粗暴 ban 红肉, 否则误杀羊肉/牛肉)
# Codex review blocker #2 续: 加 叉烧 / 火腿肠 / 腊肉 / 香肠 / 培根 等明显猪肉制品.
_HALAL_PORK_KEYWORDS: tuple[str, ...] = (
    "猪", "叉烧", "培根", "火腿", "腊肠", "香肠", "腊肉", "热狗", "咸肉"
)
# 注: 删了"白切" — 白切鸡是清真合规, 白切+猪肉的菜走"猪"关键词足够命中.

# vegetarian 拒判 main_ingredient_type
_VEGETARIAN_BAN_INGREDIENTS: frozenset[str] = frozenset(
    {"红肉", "白肉", "海鲜"}
)


@dataclass
class L0Constraints:
    medical_allergies: list[str] = field(default_factory=list)
    dietary_law: str | None = None  # "vegetarian" | "halal" | None

    def is_empty(self) -> bool:
        return not self.medical_allergies and self.dietary_law is None


def load_l0_constraints(profile: dict) -> L0Constraints:
    """从 profile 解析 L0 约束. 段缺失或字段缺失返空, 不抛."""
    block = profile.get("l0_constraints") or {}
    medical = (block.get("medical") or {}) if isinstance(block, dict) else {}
    identity = (block.get("identity") or {}) if isinstance(block, dict) else {}
    allergies_raw = medical.get("allergies") or []
    allergies = [str(a).strip() for a in allergies_raw if a and str(a).strip()]
    law = identity.get("dietary_law")
    if law is not None:
        law = str(law).strip().lower() or None
    if law not in (None, "vegetarian", "halal"):
        # 未知 dietary_law 视为 None (保守降级)
        law = None
    return L0Constraints(medical_allergies=allergies, dietary_law=law)


def _dish_text(dish: dict) -> str:
    """合并菜名 + raw_name 给 substring match."""
    return (dish.get("canonical_name") or "") + " " + (dish.get("raw_name") or "")


def dish_violates_l0_a(dish: dict, c: L0Constraints) -> str | None:
    """检查 L0-A 医学过敏. 返 hit 的 allergy 关键词 (substring match dish name),
    None = 不违反.

    设计权衡: substring 是想要的 (花生过敏命中"花生酱面"/"花生汤"都是对的),
    宁可误伤不可漏伤 (medical safety > recall depth).
    """
    if not c.medical_allergies:
        return None
    text = _dish_text(dish)
    for allergy in c.medical_allergies:
        if allergy and allergy in text:
            return allergy
    return None


def dish_violates_l0_b(dish: dict, c: L0Constraints) -> str | None:
    """检查 L0-B 身份伦理. 返 hit 的 rule (vegetarian / halal_pork / halal_processed),
    None = 不违反.

    halal 仅 ban 明确含猪肉关键词或 processed_meat_flag=True 的菜 (Codex blocker #2 修正).
    羊肉串 / 牛肉串 / 鸡肉等清真合规品类不动.
    vegetarian ban 红肉/白肉/海鲜 (蛋/豆制品/纯素允许).
    """
    if c.dietary_law is None:
        return None
    np_ = dish.get("nutrition_profile") or {}
    if c.dietary_law == "vegetarian":
        ingredient = np_.get("main_ingredient_type")
        if ingredient in _VEGETARIAN_BAN_INGREDIENTS:
            return f"vegetarian_ban_{ingredient}"
        return None
    if c.dietary_law == "halal":
        if np_.get("processed_meat_flag"):
            return "halal_processed_meat"
        text = _dish_text(dish)
        for kw in _HALAL_PORK_KEYWORDS:
            if kw in text:
                return f"halal_pork:{kw}"
        return None
    return None


# ─────────────────────────── hard_filter_event 构造 helper

def make_hard_filter_event(
    *,
    category: str,
    rule: str,
    dropped_count: int,
    kept_count: int,
    refine_override: bool = False,
    timestamp: float | None = None,
) -> dict:
    """纯函数构造 HardFilterEvent dict (不直接写 trace).

    与 trace_store.append_hard_filter_event 互补 — 那个写 trace dict, 这个返事件 dict.
    L1 trace builder 收集事件列表后赋 trace["l1"]["hard_filter_events"].
    """
    import time
    return {
        "event_type": "hard_filter",
        "category": category,
        "rule": rule,
        "dropped_count": dropped_count,
        "kept_count": kept_count,
        "refine_override": bool(refine_override),
        "timestamp": timestamp if timestamp is not None else time.time(),
    }

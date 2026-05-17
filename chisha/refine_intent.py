"""refine 阶段的用户意图解析 (D-073).

边界:
  - 仅服务餐中 refine (/api/refine), 不替代餐后反馈 (chisha/feedback.py 仍负责).
  - parse_refine_intent 输出开放结构 RefineIntent, 不限定词表; 下游 recall + score
    + L3 rerank 都消费它.
  - 不写入 long_term_prefs (D-073 推翻 D-043 P3 在 refine 端的 chip 沉淀路径).

数据流:
  user_input "想吃点湖南菜，然后肉多一点。"
    ↓ parse_refine_intent (LLM 或规则)
  RefineIntent(cuisine_want=["湖南菜"], ingredient_want=["肉"],
               portion=["more_meat"], ...)
    ↓
  recall(intent=...) → 三桶拼合
  score.intent_match_bonus → L2 重打分
  ctx.refine_intent → L3 prompt

Codex review 落实点 (D-073 v2):
  - schema 补 portion / staple_preference / flavor_tags / raw_flavor
  - flavor_tags 走归一枚举, raw_flavor 保留原文供 L3
  - cuisine_want / ingredient_want 不限词表
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "prompts" / "parse_refine_intent.md"

# 归一枚举值 (L2 消费)
FlavorTag = Literal[
    "spicy", "mild", "sour", "sweet", "soup", "dry", "light", "heavy"
]
PortionTag = Literal[
    "more_meat", "less_carb", "more_veg", "not_too_full"
]
StaplePreference = Literal["avoid_staple", "want_rice", "want_noodle"]
PriceBand = Literal["cheap", "normal", "premium"]

FLAVOR_TAGS: set[str] = {
    "spicy", "mild", "sour", "sweet", "soup", "dry", "light", "heavy"
}
PORTION_TAGS: set[str] = {
    "more_meat", "less_carb", "more_veg", "not_too_full"
}
STAPLE_TAGS: set[str] = {"avoid_staple", "want_rice", "want_noodle"}
PRICE_BANDS: set[str] = {"cheap", "normal", "premium"}


@dataclass
class RefineIntent:
    """餐中 refine 的结构化意图.

    所有 list 字段空数组表示"用户未表达此维度", 不是"用户表达了空".
    None / null 字段同理.

    边界: 这是当下 refine 意图, 不沉淀长期偏好.
    """
    cuisine_want: list[str] = field(default_factory=list)
    cuisine_avoid: list[str] = field(default_factory=list)
    ingredient_want: list[str] = field(default_factory=list)
    ingredient_avoid: list[str] = field(default_factory=list)
    cooking_method: list[str] = field(default_factory=list)
    flavor_tags: list[str] = field(default_factory=list)        # 归一, ∈ FLAVOR_TAGS
    raw_flavor: list[str] = field(default_factory=list)         # 原文 ["微辣", "鲜的"]
    portion: list[str] = field(default_factory=list)            # ∈ PORTION_TAGS
    staple_preference: str | None = None                        # ∈ STAPLE_TAGS
    price_band: str | None = None                               # ∈ PRICE_BANDS
    freeform_note: str = ""                                     # 原文兜底, L3 看
    raw_text: str = ""                                          # 调试/trace 用
    # T-00: schema 版本号. P1a-03 多 slot 升级时 bump "2.0", What-if/trace 据此识别 shape.
    # 不属于语义维度, is_empty() 不检查.
    schema_version: str = "1.0"

    def to_log_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_empty(self) -> bool:
        """所有维度均空 → 视为"随便/未表达"."""
        return not any([
            self.cuisine_want, self.cuisine_avoid,
            self.ingredient_want, self.ingredient_avoid,
            self.cooking_method, self.flavor_tags, self.raw_flavor,
            self.portion,
            self.staple_preference, self.price_band,
        ])


# ─────────────────────────── 归一化 helpers ───────────────────────────────

# 同义词归一 → FLAVOR_TAGS. LLM 也可能直接输出归一值, 双保险.
_FLAVOR_SYNONYMS: dict[str, str] = {
    # spicy
    "辣": "spicy", "微辣": "spicy", "中辣": "spicy", "重辣": "spicy",
    "麻辣": "spicy",
    # mild (不辣)
    "不辣": "mild", "清淡不辣": "mild",
    # sour
    "酸": "sour", "酸爽": "sour", "酸甜": "sour",
    # sweet
    "甜": "sweet", "甜口": "sweet",
    # soup (汤水)
    "汤": "soup", "带汤": "soup", "有汤": "soup", "汤水": "soup",
    "粥": "soup",
    # dry (干/无汤)
    "干": "dry", "不要汤": "dry",
    # light (清淡)
    "清淡": "light", "清爽": "light", "少油": "light", "低油": "light",
    "不油腻": "light", "暖的": "light",
    # heavy (重口)
    "重口": "heavy", "重口味": "heavy", "够味": "heavy", "下饭": "heavy",
}

_PORTION_SYNONYMS: dict[str, str] = {
    # more_meat
    "肉多": "more_meat", "多肉": "more_meat", "肉多一点": "more_meat",
    "肉量大": "more_meat",
    # less_carb
    "少饭": "less_carb", "少主食": "less_carb", "少碳水": "less_carb",
    "不要饭": "less_carb", "饭少一点": "less_carb",
    # more_veg
    "蔬菜多": "more_veg", "多蔬菜": "more_veg", "菜多": "more_veg",
    # not_too_full
    "少一点": "not_too_full", "少点": "not_too_full", "吃少点": "not_too_full",
    "不要太撑": "not_too_full",
}


def normalize_flavor_tag(s: str) -> str | None:
    """自由文本 → FLAVOR_TAGS 归一值; 已是归一值原样返回; 未知返回 None."""
    s = (s or "").strip()
    if not s:
        return None
    if s in FLAVOR_TAGS:
        return s
    return _FLAVOR_SYNONYMS.get(s)


def normalize_portion_tag(s: str) -> str | None:
    s = (s or "").strip()
    if s in PORTION_TAGS:
        return s
    return _PORTION_SYNONYMS.get(s)


def _normalize_list(items: list[str] | None,
                     normalizer) -> list[str]:
    """对每项调 normalizer, None 丢弃, 去重保序."""
    out: list[str] = []
    for x in items or []:
        v = normalizer(x)
        if v is not None and v not in out:
            out.append(v)
    return out


def _clamp_str_enum(v: str | None, allowed: set[str]) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v if v in allowed else None


def _clean_str_list(items: list[str] | None) -> list[str]:
    """去 None/空, 去重保序, strip."""
    out: list[str] = []
    for x in items or []:
        if x is None:
            continue
        x = str(x).strip()
        if x and x not in out:
            out.append(x)
    return out


# ─────────────────────────── 规则 fallback ───────────────────────────────

# LLM 不可用 / 失败时, 用关键词兜底. 召回率不如 LLM 但稳定.
_CUISINE_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"湘菜|湖南菜|湖南料理"), "湖南菜"),
    (re.compile(r"川菜|四川菜|川渝"), "川菜"),
    (re.compile(r"粤菜|广东菜|粤式"), "粤菜"),
    (re.compile(r"日料|日式|日本菜"), "日料"),
    (re.compile(r"江浙菜|上海菜|沪菜|杭帮菜"), "江浙菜"),
    (re.compile(r"韩餐|韩国料理|韩式"), "韩式"),
    (re.compile(r"潮汕菜?|潮州菜?"), "潮汕"),
    (re.compile(r"西餐|西式"), "西式"),
    (re.compile(r"东北菜?"), "东北"),
    (re.compile(r"西北菜?|新疆菜?"), "西北"),
]


def rule_parse(text: str) -> dict[str, Any]:
    """关键词兜底解析. 召回率有限但稳定, LLM 失败时用."""
    text = text or ""
    out: dict[str, Any] = {
        "cuisine_want": [], "cuisine_avoid": [],
        "ingredient_want": [], "ingredient_avoid": [],
        "cooking_method": [],
        "flavor_tags": [], "raw_flavor": [],
        "portion": [], "staple_preference": None, "price_band": None,
        "freeform_note": text,
    }

    # cuisine (粗略: 句中"不/别/不要" 前置 → avoid)
    for pat, name in _CUISINE_KEYWORDS:
        m = pat.search(text)
        if not m:
            continue
        prefix = text[max(0, m.start() - 4):m.start()]
        if re.search(r"不要|别|不想|没有", prefix):
            if name not in out["cuisine_avoid"]:
                out["cuisine_avoid"].append(name)
        else:
            if name not in out["cuisine_want"]:
                out["cuisine_want"].append(name)

    # ingredient: 否定窗口检查 (Codex P1-1 修订, "不要牛肉/不想吃肉" 应走 ingredient_avoid)
    _NEG_PAT = re.compile(r"不(要|想|吃)|别(给|要|放|加)|没有|去掉")

    def _is_negated_near(keyword: str) -> bool:
        """keyword 在 text 中的位置前 4 字符内有否定词 → avoid."""
        idx = text.find(keyword)
        if idx < 0:
            return False
        prefix = text[max(0, idx - 4):idx]
        return bool(_NEG_PAT.search(prefix))

    def _add_ingredient(keyword: str, want_token: str, avoid_token: str | None = None):
        if keyword not in text:
            return
        target_key = "ingredient_avoid" if _is_negated_near(keyword) else "ingredient_want"
        tok = avoid_token if (target_key == "ingredient_avoid" and avoid_token) else want_token
        if tok not in out[target_key]:
            out[target_key].append(tok)

    # 广义"肉" — 但要避免 "牛肉"/"鸡肉"/"羊肉" 的"肉"被重复识别为广义肉
    # 策略: 先识具体词, 再扫广义"肉" (只在不是具体肉词的位置触发)
    # 具体蛋白先处理
    if "牛肉" in text:
        _add_ingredient("牛肉", "牛肉")
    if "鸡肉" in text or ("鸡" in text and "鸡蛋" not in text and "鸡腿" not in text):
        # "鸡蛋" / "鸡腿" 不算广义鸡肉
        _add_ingredient("鸡", "鸡肉")
    if "羊肉" in text:
        _add_ingredient("羊肉", "羊肉")
    if "猪肉" in text:
        _add_ingredient("猪肉", "猪肉")
    if re.search(r"虾|海鲜|鱼", text):
        # 海鲜系: 任一关键词命中
        for kw in ("虾", "海鲜", "鱼"):
            if kw in text:
                _add_ingredient(kw, "海鲜")
                break
    # 广义"肉" — 在没有以上具体肉词时才识别 (避免重复)
    if "肉" in text and not any(kw in text for kw in ("牛肉", "鸡肉", "羊肉", "猪肉")):
        _add_ingredient("肉", "肉")

    # 香菜 (常 avoid, 但也支持 want)
    if "香菜" in text:
        _add_ingredient("香菜", "香菜", avoid_token="香菜")

    # flavor (走归一表)
    for kw, tag in _FLAVOR_SYNONYMS.items():
        if kw in text:
            # 否定 "别太辣" / "不要太辣" → 不算 want
            window = text[max(0, text.find(kw) - 4):text.find(kw)]
            if re.search(r"别|不要|不想", window):
                continue
            if tag not in out["flavor_tags"]:
                out["flavor_tags"].append(tag)
            if kw not in out["raw_flavor"]:
                out["raw_flavor"].append(kw)

    # portion
    for kw, tag in _PORTION_SYNONYMS.items():
        if kw in text:
            if tag not in out["portion"]:
                out["portion"].append(tag)

    # staple — 面 优先 (避免 "想吃米饭" 误命中)
    if re.search(r"不要(米)?饭|不吃饭|少饭|不要主食|别给(我)?饭", text):
        out["staple_preference"] = "avoid_staple"
    elif re.search(r"面(条|食)?(?!包)", text) and re.search(r"想吃|要|来(碗|份)?", text):
        out["staple_preference"] = "want_noodle"
    elif re.search(r"想吃(米)?饭|要(米)?饭", text):
        out["staple_preference"] = "want_rice"

    # price (粗略)
    if re.search(r"便宜|实惠|不要贵|别(太)?贵|划算|30 ?块?以内|预算\s*\d{1,2}\s*块?", text):
        out["price_band"] = "cheap"
    elif re.search(r"贵一点|高端|精致|大餐", text):
        out["price_band"] = "premium"

    return out


# ─────────────────────────── LLM 路径 ───────────────────────────────

def _llm_parse(text: str,
                profile_llm: dict | None = None) -> dict[str, Any] | None:
    """调 LLM 返回 dict, 失败返回 None (上游 fallback 到 rule_parse)."""
    try:
        from chisha.llm_client import call_text
        prompt = PROMPT_PATH.read_text(encoding="utf-8").replace(
            "{INPUT_TEXT}", text
        ).replace(
            "{FLAVOR_TAGS}", ", ".join(sorted(FLAVOR_TAGS))
        ).replace(
            "{PORTION_TAGS}", ", ".join(sorted(PORTION_TAGS))
        ).replace(
            "{STAPLE_TAGS}", ", ".join(sorted(STAPLE_TAGS))
        ).replace(
            "{PRICE_BANDS}", ", ".join(sorted(PRICE_BANDS))
        )
        resp = call_text(prompt, max_tokens=512, temperature=0.0,
                         json_mode=True, profile_llm=profile_llm)
        out = resp.get("content", "")
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if not m:
            return None
        return json.loads(m.group(0))
    except Exception as e:
        print(f"  [refine_intent] LLM 失败 "
              f"({type(e).__name__}: {str(e)[:80]}), 用规则解析")
        return None


# ─────────────────────────── 公开入口 ───────────────────────────────

def parse_refine_intent(
    text: str = "",
    use_llm: bool | None = None,
    profile_llm: dict | None = None,
) -> RefineIntent:
    """餐中 refine 文本 → 结构化 RefineIntent.

    Args:
        text: 用户自由文本 ("想吃点湖南菜, 然后肉多一点").
        use_llm: None=auto (有 provider 且 text 非空时启用), True/False 强制.
        profile_llm: 透传 profile.yaml 的 llm 段给 LLM router.

    Returns:
        RefineIntent. text 为空 → 全空 RefineIntent (is_empty()==True).

    边界:
        - LLM 失败自动 fallback rule_parse, 不抛.
        - 输出严格清洗 (枚举校验 / 去重 / strip).
    """
    text = (text or "").strip()
    if not text:
        return RefineIntent(raw_text="")

    if use_llm is None:
        from chisha.llm_client import has_llm_key
        use_llm = has_llm_key()

    parsed: dict[str, Any] = {}
    if use_llm:
        llm_result = _llm_parse(text, profile_llm=profile_llm)
        if llm_result is not None:
            parsed = llm_result
    if not parsed:
        parsed = rule_parse(text)

    return RefineIntent(
        cuisine_want=_clean_str_list(parsed.get("cuisine_want")),
        cuisine_avoid=_clean_str_list(parsed.get("cuisine_avoid")),
        ingredient_want=_clean_str_list(parsed.get("ingredient_want")),
        ingredient_avoid=_clean_str_list(parsed.get("ingredient_avoid")),
        cooking_method=_clean_str_list(parsed.get("cooking_method")),
        flavor_tags=_normalize_list(parsed.get("flavor_tags"),
                                      normalize_flavor_tag),
        raw_flavor=_clean_str_list(parsed.get("raw_flavor")),
        portion=_normalize_list(parsed.get("portion"),
                                  normalize_portion_tag),
        staple_preference=_clamp_str_enum(
            parsed.get("staple_preference"), STAPLE_TAGS),
        price_band=_clamp_str_enum(
            parsed.get("price_band"), PRICE_BANDS),
        freeform_note=(parsed.get("freeform_note") or text).strip(),
        raw_text=text,
    )

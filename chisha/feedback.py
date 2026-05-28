"""反馈解析层 (D-033 反馈骨架 + D-035 LLM 反馈解析员).

输入: 用户在飞书卡片上点的 chip + 自由文本.
输出: FeedbackParsed (规范化 chip + rating + want_again + note).

LLM 角色: 反馈解析员 — 仅做"自然语言 → 结构化 chip"映射, 不做学习决策.
无 LLM provider 可用时退化到 rule-based 关键词匹配, 保证管道不断 (D-047).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from chisha.install_root import install_root as _install_root  # T-DIST-01 B.1
ROOT = _install_root()
PROMPT_PATH = ROOT / "prompts" / "parse_feedback.md"


# 反馈 chip 受控词表 (与飞书卡片 chip 列表对齐).
# 任何 LLM/规则解析后的 chip 都必须 ∈ CHIP_VOCAB, 否则丢弃.
CHIP_VOCAB: set[str] = {
    # 即时反馈 — 负向
    "太油", "太辣", "太咸", "太甜", "太贵", "太撑", "没吃饱",
    "主食太多", "加工肉太多",
    # 即时反馈 — 履约
    "送慢", "拒签", "漏汤",
    # 即时反馈 — 偏好诉求
    "想喝汤", "想清淡", "想吃辣", "想吃肉", "不想吃这菜系",
    # 餐后反馈 — 正向
    "好吃", "想再来", "推荐别人",
    # 餐后反馈 — 负向
    "不想再吃", "踩雷",
}


@dataclass
class FeedbackParsed:
    chips: list[str] = field(default_factory=list)        # 规范化后, ∈ CHIP_VOCAB
    rating_taste: int | None = None                       # 1-5, None=未填
    rating_satisfaction: int | None = None                # 1-5, None=未填
    want_again: bool | None = None                        # None=未表达
    note: str = ""                                        # 用户自由文本, 原样保留
    raw_text: str = ""                                    # 调试用

    def to_log_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------- rule-based ----
_KEYWORD_TO_CHIP: list[tuple[re.Pattern, str]] = [
    # 油
    (re.compile(r"太油|油大|油腻|发腻"), "太油"),
    # 辣
    (re.compile(r"太辣|辣过头|辣到"), "太辣"),
    # 咸
    (re.compile(r"太咸|齁咸|咸了"), "太咸"),
    # 甜
    (re.compile(r"太甜|齁甜|甜口"), "太甜"),
    # 贵
    (re.compile(r"太贵|贵了|不值"), "太贵"),
    # 量
    (re.compile(r"太撑|撑死|吃撑"), "太撑"),
    (re.compile(r"没吃饱|不够吃|分量小|量小"), "没吃饱"),
    (re.compile(r"主食(太多|多了)|碳水多|饭多|面多"), "主食太多"),
    (re.compile(r"加工肉|火腿|蟹柳|培根|午餐肉"), "加工肉太多"),
    # 履约
    (re.compile(r"送(得)?(太)?慢|配送慢|超时"), "送慢"),
    (re.compile(r"拒签|没拿到|送错"), "拒签"),
    (re.compile(r"漏.{0,6}汤|汤.{0,4}漏|洒了|包装漏"), "漏汤"),
    # 诉求
    (re.compile(r"想喝汤|有汤|带汤"), "想喝汤"),
    (re.compile(r"想清淡|清淡点|清爽"), "想清淡"),
    (re.compile(r"想(吃)?辣"), "想吃辣"),
    (re.compile(r"想(吃)?肉|肉一点"), "想吃肉"),
    (re.compile(r"不想(吃|要|看)(.{0,4})?(菜系|这家|这种)"), "不想吃这菜系"),
    # 正向
    (re.compile(r"好吃|不错|味道(好|可以|不错)"), "好吃"),
    (re.compile(r"想再来|再吃|再点|复购"), "想再来"),
    (re.compile(r"推荐|安利"), "推荐别人"),
    # 餐后负向
    (re.compile(r"不想再吃|不再点"), "不想再吃"),
    (re.compile(r"踩雷|很差|难吃"), "踩雷"),
]


_RATING_PATTERN = re.compile(r"([1-5])\s*(?:分|星|⭐|/5)")
_WANT_AGAIN_TRUE = re.compile(r"想再(来|吃|点)|复购|还(想|要)再")
_WANT_AGAIN_FALSE = re.compile(r"不(想|会)再|再也不|不再点|踩雷")


def rule_parse(text: str) -> dict[str, Any]:
    """无 LLM 时的关键词匹配. 召回率不高但稳定."""
    text = text or ""
    chips: list[str] = []
    for pat, chip in _KEYWORD_TO_CHIP:
        if pat.search(text):
            if chip not in chips:
                chips.append(chip)
    rating = None
    m = _RATING_PATTERN.search(text)
    if m:
        rating = int(m.group(1))
    want_again: bool | None = None
    if _WANT_AGAIN_TRUE.search(text):
        want_again = True
    if _WANT_AGAIN_FALSE.search(text):
        want_again = False   # 否定优先
    return {
        "chips": chips,
        "rating_taste": rating,
        "rating_satisfaction": None,
        "want_again": want_again,
    }


# ---------------------------------------------------------------- LLM 路径 ----
def _llm_parse(text: str,
                profile_llm: dict | None = None) -> dict[str, Any] | None:
    """调 LLM 返回 dict, 失败返回 None (上游 fallback)."""
    try:
        from chisha.llm_client import call_text
        prompt = PROMPT_PATH.read_text(encoding="utf-8").replace(
            "{INPUT_TEXT}", text
        ).replace(
            "{CHIP_VOCAB}", ", ".join(sorted(CHIP_VOCAB))
        )
        # D-047: call_text 返回 dict, text 模式取 .content; json_mode 在 OR
        # 路径 "accepted but not enforced", regex 仍兜底 markdown 包裹 (```json
        # ... ```) 形态. profile_llm 透传给 provider 路由器.
        resp = call_text(prompt, max_tokens=512, temperature=0.0,
                         json_mode=True, profile_llm=profile_llm)
        out = resp.get("content", "")
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if not m:
            return None
        return json.loads(m.group(0))
    except Exception as e:
        print(f"  [feedback parse fallback] LLM 失败 "
              f"({type(e).__name__}: {str(e)[:80]}), 用规则解析")
        return None


# ---------------------------------------------------------------- 公开入口 ----
def _normalize_chips(chips_in: list[str] | None) -> list[str]:
    """去重 + 校验 ∈ CHIP_VOCAB. 未知 chip 丢弃."""
    out: list[str] = []
    for c in chips_in or []:
        c = (c or "").strip()
        if c in CHIP_VOCAB and c not in out:
            out.append(c)
    return out


def _clamp_rating(r: Any) -> int | None:
    if r is None:
        return None
    try:
        ri = int(r)
    except (TypeError, ValueError):
        return None
    return ri if 1 <= ri <= 5 else None


def parse_feedback(
    text: str = "",
    chips: list[str] | None = None,
    rating_taste: int | None = None,
    rating_satisfaction: int | None = None,
    want_again: bool | None = None,
    use_llm: bool | None = None,
    profile_llm: dict | None = None,
) -> FeedbackParsed:
    """合并 UI 结构化字段 + 自然语言文本, 输出规范化 FeedbackParsed.

    UI chip / rating / want_again 是用户显式选的, 优先级最高.
    text 用 LLM (有 provider 可用) 或规则解析, 推断的 chip 与 UI chip 合并
    去重, 推断的 rating/want_again 仅在 UI 未填时回填.

    Args:
        text: 用户自由文本, 可空.
        chips: UI 上勾的 chip 列表, 必须 ∈ CHIP_VOCAB (越界丢弃).
        rating_taste / rating_satisfaction: 1-5 或 None.
        want_again: True / False / None.
        use_llm: 强制开关 (None=auto, 看任何 LLM provider 是否可用).
        profile_llm: D-047 — 透传 profile.yaml 的 llm 段给 LLM router.
    """
    text = (text or "").strip()
    ui_chips = _normalize_chips(chips)

    if use_llm is None:
        from chisha.llm_client import has_llm_key
        use_llm = bool(text) and has_llm_key()

    parsed: dict[str, Any] = {}
    if text:
        if use_llm:
            llm_result = _llm_parse(text, profile_llm=profile_llm)
            parsed = llm_result if llm_result is not None else rule_parse(text)
        else:
            parsed = rule_parse(text)

    # chip 合并: UI 优先 + 文本推断
    inferred_chips = _normalize_chips(parsed.get("chips"))
    merged_chips = list(dict.fromkeys(ui_chips + inferred_chips))

    # rating / want_again: UI 未填时才用文本推断
    final_rating_taste = _clamp_rating(rating_taste) \
        if rating_taste is not None else _clamp_rating(parsed.get("rating_taste"))
    final_rating_sat = _clamp_rating(rating_satisfaction) \
        if rating_satisfaction is not None else _clamp_rating(parsed.get("rating_satisfaction"))
    final_want_again = want_again if want_again is not None else parsed.get("want_again")

    return FeedbackParsed(
        chips=merged_chips,
        rating_taste=final_rating_taste,
        rating_satisfaction=final_rating_sat,
        want_again=final_want_again,
        note=text,
        raw_text=text,
    )

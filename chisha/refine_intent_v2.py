"""Faithful Refine 多 slot schema + LLM 解析层 + 安全带 (D-094.1 schema 扩展版).

边界 (D-094.1 后):
  - LLM 解析直出多 slot 结构; 解析失败时**降级到 empty V2**, 永不崩 (V1 已退役).
  - 下游 L1/L2/L3 真消费的 slot (D-094.1: 13 槽真兑现):
    - redirect.cuisine_want / cuisine_avoid / ingredient_want / ingredient_avoid
    - redirect.cuisine_candidates_expanded (D-094: L1 bucket_soft 真召回)
    - redirect.brand_avoid (D-094: L1 venue 整店硬过滤)
    - redirect.cooking_method_avoid (D-094: L1 dish 硬过滤, 9 类枚举)
    - redirect.staple_want / staple_avoid (D-094.1: 主食偏好 L2 真打分)
    - constrain.oil ∈ {"low","normal","high"} | null (D-094.1: "high" 替代 V1 heavy 触发 D-090.1 油豁免)
    - constrain.price_max (数字精确) / price_band ∈ {"cheap","normal","premium"} | null (D-094.1: 模糊文本)
    - constrain.wants_soup (D-094.1: bool, L2 真打分有汤优先)
    - reference (T-P2-01 L3 软重排消费)
    - reject_previous (V2 全盘重推)
  - 已砍字段 (D-094: 字段要么真消费要么砍, 不留 trace-only 装饰):
    - redirect.ingredient_synonyms (score.py _INGREDIENT_BROAD 硬词典已替代)
    - redirect.food_form_avoid (dish.food_form 0 覆盖, F-011 数据打标后再加回)
    - constrain.quality_floor / delivery_only / max_distance_km
    - constrain.functional.{low_caffeine, low_satiety_drowsy}
  - 已砍字段 (D-094.1 本案): V1 flavor_tags=sweet/sour 走 raw_understanding + L3 兜底 (narrative 不假装).
  - D-085 第二句 "字段空洞务实降级" 已废弃 (by D-094): 没 trace-only 字段了, 没 unsupported_in_recall.
  - schema_version bump "2.0" → "2.1" (D-094.1).

trace 双存 (安全带):
  - raw_text: 用户原文
  - 结构化结果 (V2 dataclass.to_log_dict)
  - raw_understanding: LLM 自述理解 (LLM 失败/降级时回填占位)
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, ClassVar

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH_V2 = ROOT / "prompts" / "parse_refine_intent_v2.md"


# D-094: cooking_method_avoid 闭包枚举 (codex audit 实读 dishes_tagged.json, 共 9 类).
# LLM 输出越界值 → _clean_parsed_to_v2 丢弃 (枚举外值不进 list).
COOKING_METHOD_ENUM: frozenset[str] = frozenset({
    "油炸", "凉拌", "生", "炖", "炒", "煮", "蒸", "烤", "煎",
})


def _empty_redirect() -> dict:
    """redirect 块: 全部 list 字段空数组.

    D-094.1: 加 staple_want / staple_avoid (主食偏好 L2 真打分).
    """
    return {
        "cuisine_want": [],
        "cuisine_avoid": [],
        "cuisine_candidates_expanded": [],
        "ingredient_want": [],
        "ingredient_avoid": [],
        "brand_avoid": [],
        "cooking_method_avoid": [],
        "staple_want": [],
        "staple_avoid": [],
    }


def _empty_constrain() -> dict:
    """constrain 块 (D-094 砍 quality_floor / delivery_only / max_distance_km / functional).

    D-094.1 扩 4 槽真消费:
      - oil ∈ {"low","normal","high"} | null  ("high" 替代 V1 heavy + 触发 D-090.1 oil 豁免)
      - price_max (数字, 精确) — 优先于 price_band
      - price_band ∈ {"cheap","normal","premium"} | null  (模糊文本, price_max 缺失时兜底)
      - wants_soup: bool (想喝汤/粥, L2 真打分有汤优先)
    """
    return {
        "oil": None,
        "price_max": None,
        "price_band": None,
        "wants_soup": False,
    }


@dataclass
class RefineIntentV2:
    """多 slot Faithful Refine schema (D-094.1 schema 扩展版).

    LLM 直出. 失败时降级到 empty V2 (V1 已退役, 无 legacy fallback).
    """
    redirect: dict = field(default_factory=_empty_redirect)
    constrain: dict = field(default_factory=_empty_constrain)
    reference: dict | None = None
    reject_previous: bool = False
    raw_understanding: str = ""        # LLM 自述理解, trace 双存用
    raw_text: str = ""                 # 用户原文
    schema_version: str = "2.1"

    # T-P1a-01 (D-094.1 沿用): refine 文本里出现这些词才视为"显式解除 L0-C 健康硬契约".
    _METHODOLOGY_BREAK_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "破戒", "放纵", "放开吃", "今晚不管", "今晚就", "无所谓",
        "随便", "别管那么多", "一次性", "今天就这样", "今天放飞",
    )

    def is_empty(self) -> bool:
        """所有语义维度均空 → True. raw_text / raw_understanding / schema_version 不算."""
        if self.reject_previous:
            return False
        for v in self.redirect.values():
            if v:
                return False
        for v in self.constrain.values():
            if v not in (None, False, [], "", {}):
                return False
        if self.reference:
            return False
        return True

    def to_log_dict(self) -> dict[str, Any]:
        return asdict(self)

    def allows_methodology_break(self) -> bool:
        """T-P1a-01: L0-C 硬契约 (蔬菜/油上限/价格带/方法论) 是否被 refine 文本明确解除.

        L0-A 医学过敏 + L0-B 身份伦理永不可破.
        L0-C 仅当 refine 文本含 "破戒/放纵/今晚就/无所谓" 等明确信号时放开.
        检查 raw_text + raw_understanding 拼接子串.
        """
        text = (self.raw_text or "") + " " + (self.raw_understanding or "")
        return any(k in text for k in self._METHODOLOGY_BREAK_KEYWORDS)

    # ─── 便捷 properties (语义层 alias, 不进 asdict, trace 干净) ───
    # backend (recall/score/rerank) 通过 intent.cuisine_want 直接访问, 不必每处都 intent.redirect["..."].
    @property
    def cuisine_want(self) -> list[str]:
        return list(self.redirect.get("cuisine_want") or [])

    @property
    def cuisine_avoid(self) -> list[str]:
        return list(self.redirect.get("cuisine_avoid") or [])

    @property
    def cuisine_candidates_expanded(self) -> list[str]:
        return list(self.redirect.get("cuisine_candidates_expanded") or [])

    @property
    def ingredient_want(self) -> list[str]:
        return list(self.redirect.get("ingredient_want") or [])

    @property
    def ingredient_avoid(self) -> list[str]:
        return list(self.redirect.get("ingredient_avoid") or [])

    @property
    def brand_avoid(self) -> list[str]:
        return list(self.redirect.get("brand_avoid") or [])

    @property
    def cooking_method_avoid(self) -> list[str]:
        return list(self.redirect.get("cooking_method_avoid") or [])

    @property
    def staple_want(self) -> list[str]:
        return list(self.redirect.get("staple_want") or [])

    @property
    def staple_avoid(self) -> list[str]:
        return list(self.redirect.get("staple_avoid") or [])

    @property
    def oil(self) -> str | None:
        return self.constrain.get("oil")

    @property
    def price_max(self) -> float | int | None:
        return self.constrain.get("price_max")

    @property
    def price_band(self) -> str | None:
        return self.constrain.get("price_band")

    @property
    def wants_soup(self) -> bool:
        return bool(self.constrain.get("wants_soup"))


# ─────────────────────────── schema 验证 (安全带 #1) ───────────────────────

def validate_v2_schema(d: dict) -> tuple[bool, list[str]]:
    """Shallow 结构校验. 返 (ok, errors).

    检查范围:
      - 顶层 dict
      - schema_version == "2.1"
      - redirect 是 dict + 各 slot 是 list[str]
      - constrain 是 dict
      - reference: None 或 dict
      - reject_previous: bool
      - raw_understanding / raw_text: str
    不检查内层 enum (那是 LLM 解析的 best-effort, _clean_parsed_to_v2 兜底).
    """
    errors: list[str] = []
    if not isinstance(d, dict):
        return False, [f"top-level not dict: {type(d).__name__}"]
    sv = d.get("schema_version")
    if sv != "2.1":
        errors.append(f"schema_version != '2.1': {sv!r}")
    redirect = d.get("redirect")
    if not isinstance(redirect, dict):
        errors.append(f"redirect not dict: {type(redirect).__name__}")
    else:
        for k, v in redirect.items():
            if not isinstance(v, list):
                errors.append(f"redirect[{k}] not list: {type(v).__name__}")
            elif any(not isinstance(x, str) for x in v):
                errors.append(f"redirect[{k}] has non-str element")
    constrain = d.get("constrain")
    if not isinstance(constrain, dict):
        errors.append("constrain not dict")
    ref = d.get("reference")
    if ref is not None and not isinstance(ref, dict):
        errors.append(f"reference must be None or dict: {type(ref).__name__}")
    if not isinstance(d.get("reject_previous"), bool):
        errors.append("reject_previous not bool")
    if not isinstance(d.get("raw_understanding", ""), str):
        errors.append("raw_understanding not str")
    if not isinstance(d.get("raw_text", ""), str):
        errors.append("raw_text not str")
    return len(errors) == 0, errors


# ─────────────────────────── 清洗 helpers ─────────────────────────────────

def _clean_str_list(items: Any) -> list[str]:
    """LLM 返回 list 时清洗成 list[str].

    Codex M6 修: 非 str/int/float/bool 标量直接丢弃, 不再 str(dict) 产
    "{'foo': 'bar'}" 字符串污染 trace.
    """
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for x in items:
        if x is None:
            continue
        # 只接受标量, 拒 list/dict 等容器 (Codex M6)
        if not isinstance(x, (str, int, float, bool)):
            continue
        s = str(x).strip()
        if s and s not in out:
            out.append(s)
    return out


# Codex M7: 中文 truthy / falsy 映射. LLM 偶尔会用中文 (虽然 prompt 已禁).
_BOOL_CN_TRUTHY = {"true", "yes", "是", "对", "要", "好", "1"}
_BOOL_CN_FALSY = {"false", "no", "否", "不", "不要", "不用", "0"}


def _coerce_bool_or_null(v: Any) -> bool | None:
    """LLM 可能给 'true'/'false' 字符串或中文是否字串, 也可能直接 bool/None."""
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return bool(v) if v in (0, 1) else None
    if isinstance(v, str):
        s = v.strip().lower()
        if s in _BOOL_CN_TRUTHY:
            return True
        if s in _BOOL_CN_FALSY:
            return False
    return None


# Codex M8: 中文数字最小映射. prompt 已强制阿拉伯数字, 这里是兜底.
_CN_NUMERAL = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _parse_cn_int(s: str) -> int | None:
    """支持「十/二十/三十五/一百/一百二十」级别. 复杂表达式不支持, 返 None."""
    s = s.strip()
    if not s:
        return None
    # 纯单字
    if s in _CN_NUMERAL:
        return _CN_NUMERAL[s]
    # 「N十M」: 二十/三十五/...
    m = re.fullmatch(r"([一二三四五六七八九])?十([一二三四五六七八九])?", s)
    if m:
        tens = _CN_NUMERAL[m.group(1)] if m.group(1) else 1
        ones = _CN_NUMERAL[m.group(2)] if m.group(2) else 0
        return tens * 10 + ones
    # 「N百」/「N百M十K」: 一百/一百二十/一百二十五
    m = re.fullmatch(
        r"([一二三四五六七八九])百"
        r"(?:([一二三四五六七八九])(?:十([一二三四五六七八九])?)?)?",
        s,
    )
    if m:
        hundreds = _CN_NUMERAL[m.group(1)] * 100
        # 中间位: "一百二" → 120, "一百二十五" → 125
        if m.group(2):
            mid = _CN_NUMERAL[m.group(2)]
            tens = mid * 10 if "十" in s else mid * 10  # 简化: 见百必出十
            ones = _CN_NUMERAL[m.group(3)] if m.group(3) else 0
            return hundreds + tens + ones
        return hundreds
    return None


def _coerce_number_or_null(v: Any) -> float | int | None:
    """price_max / max_distance_km. 接受 int/float, 字符串可解析阿拉伯数字或简单中文数字, 否则 None.

    Codex M8 修: 加中文数字最小映射 (十/二十/三十五/一百二十). prompt 已强制
    阿拉伯数字, 这里是兜底, 不试图覆盖所有表达 (如"两千" "几十").
    """
    if v is None:
        return None
    if isinstance(v, bool):  # bool 也是 int 子类, 先排除
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        # 优先阿拉伯数字 + 小数
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        if m:
            try:
                f = float(m.group(0))
                return int(f) if f.is_integer() else f
            except ValueError:
                pass
        # 中文数字兜底: 必须从字符串开头匹配 (allow 末尾单位 "块" "公里" "元")
        # "几十" / "两千" 这种 helper 接不住的, 走 None (LLM 走 V1 兜底 / 让 L3 看原文)
        m = re.match(r"^([零一二三四五六七八九十百两]+)(?:\s*(?:块|元|公里|分钟))?$",
                       v.strip())
        if m:
            n = _parse_cn_int(m.group(1))
            if n is not None:
                return n
    return None


# Codex M9: reference_meal_id 格式校验. 防 LLM 把 raw 文本 ("昨天的那一顿") 当 id 注入.
# 合法格式: alphanumeric + dash + underscore, 长度 4-64.
_MEAL_ID_PAT = re.compile(r"^[A-Za-z0-9_\-]{4,64}$")


def _is_valid_meal_id(s: Any) -> bool:
    if not isinstance(s, str):
        return False
    return bool(_MEAL_ID_PAT.match(s))


def _coerce_enum_or_null(v: Any, allowed: set[str]) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s in allowed else None


_OIL_VALUES = {"low", "normal", "high"}     # D-094.1: 加 "high" 替代 V1 heavy
_PRICE_BAND_VALUES = {"cheap", "normal", "premium"}   # D-094.1: 模糊文本兜底
_REFERENCE_RELATIONS = {"lighter", "similar_but_different_venue", "avoid_pattern"}


def _clean_parsed_to_v2(parsed: dict, *, raw_text: str) -> RefineIntentV2:
    """LLM 返回的 dict → RefineIntentV2 dataclass. 每个 slot 都做防御性清洗.

    任何不符合 schema 的子字段降级到默认值 (空 list / None / False), 不抛.

    D-094: cooking_method_avoid 枚举闭包过滤 — LLM 越界值丢弃 (例: "烧烤" 必须先映射到
    "烤", "煎炸" 拆成 "油炸"/"煎"; "油腻" 不进此字段, 应进 constrain.oil="low").
    """
    redirect_raw = parsed.get("redirect") or {}
    redirect = _empty_redirect()
    for k in redirect.keys():
        redirect[k] = _clean_str_list(redirect_raw.get(k))
    # D-094: cooking_method_avoid 必须命中 9 类枚举, 越界值丢弃
    _cm_raw = list(redirect["cooking_method_avoid"])
    redirect["cooking_method_avoid"] = [
        x for x in _cm_raw if x in COOKING_METHOD_ENUM
    ]
    # codex review Q5 nit: 越界值 stash 一份, 给 raw_understanding 拼诚实尾巴
    _cm_dropped = [x for x in _cm_raw if x not in COOKING_METHOD_ENUM]

    constrain_raw = parsed.get("constrain") or {}
    constrain = _empty_constrain()
    constrain["oil"] = _coerce_enum_or_null(constrain_raw.get("oil"), _OIL_VALUES)
    constrain["price_max"] = _coerce_number_or_null(constrain_raw.get("price_max"))
    # D-094.1: price_band 模糊文本枚举, 优先级低于 price_max (数字更精确)
    constrain["price_band"] = _coerce_enum_or_null(
        constrain_raw.get("price_band"), _PRICE_BAND_VALUES)
    # D-094.1: wants_soup bool (兼容中文 truthy/falsy)
    constrain["wants_soup"] = _coerce_bool_or_null(constrain_raw.get("wants_soup")) or False

    reference: dict | None = None
    reference_raw = parsed.get("reference")
    if isinstance(reference_raw, dict):
        rel = _coerce_enum_or_null(reference_raw.get("relation"),
                                     _REFERENCE_RELATIONS)
        if rel is not None:
            # Codex M9: ref_meal_id 必须满足 alphanumeric/-/_ 长度 4-64, 否则丢弃 (设 None).
            # 防 LLM 把 raw 文本 ("昨天的那一顿") 当 id 注入下游 L3.
            raw_ref_id = reference_raw.get("reference_meal_id")
            ref_id = raw_ref_id if _is_valid_meal_id(raw_ref_id) else None
            reference = {
                "reference_meal_id": ref_id,
                "relation": rel,
            }

    reject_previous = _coerce_bool_or_null(parsed.get("reject_previous")) or False
    raw_understanding = str(parsed.get("raw_understanding") or "").strip()
    # D-094 codex Q5 nit: 越界 cooking_method 值拼到 raw_understanding 末尾, 给 L3 narrative
    # + debug-ui 留可见痕迹 (prompt 已教 LLM 映射, 这是 belt-and-suspenders).
    if _cm_dropped:
        tail = f"[丢弃越界 cooking_method_avoid={','.join(_cm_dropped)}]"
        raw_understanding = f"{raw_understanding} {tail}".strip()

    return RefineIntentV2(
        redirect=redirect,
        constrain=constrain,
        reference=reference,
        reject_previous=reject_previous,
        raw_understanding=raw_understanding,
        raw_text=raw_text,
        schema_version="2.1",
    )


# ─────────────────────────── LLM 路径 (安全带核心) ────────────────────────

def _llm_parse_v2(text: str,
                   profile_llm: dict | None = None,
                   trace_collector: dict | None = None) -> dict | None:
    """调 LLM 返回 dict, 失败返回 None.

    memory `chisha_llm_call_principles`: L1 抽取低频, 走 text+JSON 路径 (不引入 tool_use).
    memory `chisha_l3_model_refine_intent_sensitivity`: profile.yaml 用 sonnet/opus,
        避免 deepseek-flash 稀释 intent.

    D-089-S3: trace_collector 注入时, 把 LLM call 完整 trace stash 进去
    (system_prompt_full / user_message_full / raw_response / latency / usage /
    model / resolved_provider / stop_reason / fallback_reason). 给
    trace_helpers.serialize_llm_call_trace 消费, 落 R2 round.refine_intent_llm.
    refine round trace 自包含的关键 — 让 debug-ui 能 replay 当次意图解析全过程.
    """
    import time as _time
    # D-095: prompt 模板拆 system/user, 启用 Anthropic ephemeral cache.
    # system = template_head (INPUT_TEXT 之前的固定指令 + 八例 + "用户 refine 文本:\n```\n"),
    # user  = text + template_tail (用户原文 + "\n```\n\n输出 JSON:").
    # 模板顺序不变, 仅把固定部分挪到 system 让 cache_control 命中.
    # trace_collector 落实际发给 LLM 的内容 (1:1 对齐, 不再"假拆").
    prompt_template = ""
    system_prompt = ""
    user_msg = ""
    try:
        from chisha.llm_client import call_text, _resolve_provider
        prompt_template = PROMPT_PATH_V2.read_text(encoding="utf-8")
        template_head, _sep, template_tail = prompt_template.partition("{INPUT_TEXT}")
        system_prompt = template_head
        user_msg = text + template_tail
        if trace_collector is not None:
            trace_collector["system_prompt_full"] = system_prompt
            trace_collector["system_prompt_chars"] = len(system_prompt)
            trace_collector["user_message_full"] = user_msg
            trace_collector["user_message_chars"] = len(user_msg)
            try:
                trace_collector["resolved_provider"] = _resolve_provider(profile_llm)
            except Exception:
                trace_collector["resolved_provider"] = None
            trace_collector["max_tokens"] = 1024
            trace_collector["temperature"] = 0.0
        t0 = _time.time()
        resp = call_text(user_msg, system=system_prompt, cache_system=True,
                          max_tokens=1024, temperature=0.0,
                          json_mode=True, profile_llm=profile_llm)
        latency_ms = int((_time.time() - t0) * 1000)
        out = resp.get("content", "") if isinstance(resp, dict) else ""
        if trace_collector is not None:
            trace_collector["latency_ms"] = latency_ms
            trace_collector["raw_response"] = out
            if isinstance(resp, dict):
                trace_collector["usage"] = resp.get("usage")
                trace_collector["model"] = resp.get("model")
                trace_collector["stop_reason"] = resp.get("stop_reason")
        if not out:
            if trace_collector is not None:
                trace_collector["fallback_reason"] = "LLM 返回空 content"
            return None
        # 去 markdown 代码块, 提取最外层 {...}
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if not m:
            if trace_collector is not None:
                trace_collector["fallback_reason"] = "raw_response 内无 JSON 对象"
            return None
        return json.loads(m.group(0))
    except Exception as e:
        fail_msg = f"{type(e).__name__}: {str(e)[:160]}"
        if trace_collector is not None:
            trace_collector["fallback_reason"] = fail_msg
        print(f"  [refine_intent_v2] LLM 失败 ({fail_msg}), 降级到空 V2 + raw_understanding 占位")
        return None


# ─────────────────────────── 公开入口 ─────────────────────────────────────

def extract_refine_intent_v2(
    text: str = "",
    *,
    use_llm: bool | None = None,
    profile_llm: dict | None = None,
    trace_collector: dict | None = None,
) -> RefineIntentV2:
    """安全带 #1: LLM 多 slot 解析, 失败降级到 empty V2 (V1 已退役).

    流程:
      1. text 空 → 返 empty V2 (不调 LLM), raw_understanding="(空 refine)".
      2. use_llm=False 或 LLM 不可用 → empty V2 + raw_understanding 占位 ("LLM 不可用").
      3. LLM 调用:
         a. 成功 + JSON 解析成功 + schema validate 通过 → _clean_parsed_to_v2.
         b. LLM 失败 / 坏 JSON / schema 不匹配 → empty V2 + raw_understanding 占位.

    LLM 失败时绝不抛, 绝不瞎猜 (brief §4 安全带 #1).
    D-094.1 (本案): V1 整模块已删, 不再有 from_legacy / V1 规则兜底.
    """
    text = (text or "").strip()
    if not text:
        # 空 text 也回填 raw_understanding 占位 (eval edge-01), trace 双存语义统一.
        return RefineIntentV2(raw_text="", raw_understanding="(空 refine)")

    # use_llm 决策
    if use_llm is None:
        try:
            from chisha.llm_client import has_llm_key
            use_llm = has_llm_key()
        except Exception:
            use_llm = False

    def _empty_fallback(reason: str) -> RefineIntentV2:
        """V1 退役后, LLM 失败/不可用 → 全空 V2 + raw_understanding 注明原因.

        Faithful Refine 第一原则: 没 LLM 解析就不假装理解, 让 narrative 老实说.
        """
        return RefineIntentV2(raw_text=text, raw_understanding=reason)

    if not use_llm:
        return _empty_fallback("LLM 不可用, refine 字段全空, 走 raw_text + L3 兜底")

    parsed = _llm_parse_v2(text, profile_llm=profile_llm,
                             trace_collector=trace_collector)
    # D-074: LLM 调用之后的全部确定性守卫 (required_keys / validate / clean /
    # empty 兜底) 抽到 apply_intent_response, in-process 与 AI-friendly CLI 共用.
    intent, _disclosure = apply_intent_response(parsed, raw_text=text)
    return intent


# ═══════════════════════ D-074 AI-friendly: 外置抽取 LLM 调用 ═══════════════════════
# chisha 不调 LLM — 把"context 自然语言 → 结构化 intent"这个智能步骤打包成
# llm_request_spec 信封给宿主 agent 的 LLM 执行, 回传后 chisha 做全部确定性
# 清洗/校验/disclosure (设计 §5 Faithful Refine 守卫全留 chisha).


# extract spec 的 json_schema: 描述 V2 intent 输出 shape, 让 agent LLM 产出合法结构.
# 与 _empty_redirect / _empty_constrain / 枚举常量同源, 避免漂移.
_V2_INTENT_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "redirect": {
            "type": "object",
            "properties": {
                k: {"type": "array", "items": {"type": "string"}}
                for k in _empty_redirect().keys()
            },
        },
        "constrain": {
            "type": "object",
            "properties": {
                "oil": {"enum": sorted(_OIL_VALUES) + [None]},
                "price_max": {"type": ["number", "null"]},
                "price_band": {"enum": sorted(_PRICE_BAND_VALUES) + [None]},
                "wants_soup": {"type": "boolean"},
            },
        },
        "reference": {
            "type": ["object", "null"],
            "properties": {
                "reference_meal_id": {"type": ["string", "null"]},
                "relation": {"enum": sorted(_REFERENCE_RELATIONS)},
            },
        },
        "reject_previous": {"type": "boolean"},
        "raw_understanding": {"type": "string"},
        "schema_version": {"const": "2.1"},
    },
    "required": ["redirect", "constrain", "raw_understanding", "schema_version"],
}


def build_extract_spec(
    text: str,
    *,
    correlation_id: "Any",          # agent_protocol.CorrelationId
    profile_llm: dict | None = None,  # 仅签名兼容; chisha 不调 LLM, 不读 provider
) -> dict:
    """D-074: 构造 context→intent 抽取的 `llm_request_spec` 信封 (不调 LLM).

    system/user 与 in-process _llm_parse_v2 完全同源 (同一 prompt 模板, 同一
    {INPUT_TEXT} partition), 让 agent LLM 按**同一套 parse 规则**抽取, 忠实度对齐
    chisha 自抽 (设计 §5 "prompt 即契约"). cooking_method_avoid 9 类枚举闭包 /
    禁脑补 / 冲突留空 / schema 未覆盖走 narrative — 全在 prompt 里, agent 照执行.

    extract 走 text_json 模式 (与 in-process json_mode 路径一致, 不引入 tool_use).
    raw_text 不进 spec 也不信 agent 回传 — 由 CLI 注入 (apply_intent_response).
    """
    from chisha.agent_protocol import build_request_spec

    prompt_template = PROMPT_PATH_V2.read_text(encoding="utf-8")
    template_head, _sep, template_tail = prompt_template.partition("{INPUT_TEXT}")
    system_prompt = template_head
    user_msg = (text or "") + template_tail
    # 输出约束 (合约透明, 让 agent LLM 按同一套 parse 规则产出 — 设计 §5 "prompt 即契约").
    # 只描述 agent 该产出什么, 不描述 chisha 内部 fallback/dedup 机制 (codex #d).
    required_validation = [
        "schema_version == '2.1'",
        "redirect 各 slot 为 list[str]; cooking_method_avoid 仅 9 类枚举",
        "constrain.oil ∈ {low,normal,high,null}; price_band ∈ {cheap,normal,premium,null}",
        "禁脑补: 没自信映射进 slot 的诉求写进 raw_understanding",
        "schema 未覆盖的诉求 (如主食粗细) 不假装支持, 走 raw_understanding",
        "不要回传 raw_text (用户原话由 chisha 注入)",
    ]
    return build_request_spec(
        operation_kind="extract",
        correlation_id=correlation_id,
        output_mode="text_json",
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
        json_schema=_V2_INTENT_JSON_SCHEMA,
        required_validation=required_validation,
    )


def apply_intent_response(
    parsed: dict | None,
    raw_text: str,
) -> tuple[RefineIntentV2, dict]:
    """D-074: 收宿主 agent extract 回传 → 全部 Faithful Refine 守卫留 chisha.

    守卫 (设计 §5): required_keys 检查 + validate_v2_schema + _clean_parsed_to_v2
    (枚举闭包 / 类型强转 / reference 清洗 / cooking_method 越界丢弃). 失败 → empty V2
    + raw_understanding 注明原因 (永不抛, 永不瞎猜).

    **关键守卫 (codex #5 / 设计 §5.2)**: raw_text 只来自 CLI 注入的原文,
    **忽略 agent 回传里的 raw_text** — 即使 agent 伪造/漏给, raw_text 仍是真原话,
    L3 prompt 据此二次软兜底, refine 忠实度不被 agent 破坏.

    返回 (RefineIntentV2, disclosure):
      disclosure = {status: ok|fallback, reason, raw_understanding} — chisha 把
      raw_understanding 当**用户可见 disclosure** 弹出 (设计 §5.4 强制自报缺口).
    """
    raw_text = (raw_text or "").strip()

    def _fb(reason: str) -> tuple[RefineIntentV2, dict]:
        intent = RefineIntentV2(raw_text=raw_text, raw_understanding=reason)
        return intent, {"status": "fallback", "reason": reason,
                        "raw_understanding": reason}

    if parsed is None:
        return _fb("LLM 解析失败, refine 字段全空, 走 raw_text + L3 兜底")
    if not isinstance(parsed, dict):
        return _fb(f"agent 回传非 dict ({type(parsed).__name__}), refine 字段全空")

    # Codex H6: schema 关键字段 LLM 必须主动给, 漏了视为"没理解 schema" → empty 兜底.
    # 来源中立措辞: in-process (chisha 自抽) 与 AI-friendly (agent 抽) 共用此路径.
    required_keys = ("schema_version", "redirect", "constrain", "raw_understanding")
    missing = [k for k in required_keys if k not in parsed]
    if missing:
        print(f"  [refine_intent_v2] LLM 漏必填字段 {missing}, 走 empty 兜底")
        return _fb(f"LLM 漏必填字段 {missing[0]}, refine 字段全空")

    # Faithful Refine (codex #5): raw_text 永远是 CLI 注入的原文, 不信 agent 回传.
    # validate 前 pop 掉, 让回传里的 raw_text **无条件被忽略** — 否则 agent 给非
    # str raw_text 会让 validate_v2_schema 失败 → 把本来合法的 intent 误降级.
    parsed.pop("raw_text", None)
    # 可选字段补默认值 (framework 控制).
    parsed.setdefault("reference", None)
    parsed.setdefault("reject_previous", False)

    ok, errors = validate_v2_schema(parsed)
    if not ok:
        print(f"  [refine_intent_v2] schema validate fail: {errors[:3]}, 走 empty 兜底")
        return _fb("LLM schema 不匹配, refine 字段全空")

    intent = _clean_parsed_to_v2(parsed, raw_text=raw_text)
    return intent, {"status": "ok", "reason": None,
                    "raw_understanding": intent.raw_understanding}

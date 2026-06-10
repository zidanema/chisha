"""D-112 Step2: `chisha profile` 问卷协议 + 确定性映射 + 写盘.

**统一原则 (PRD §1)**: 把画像捕获放进协议 (chisha 出 schema、chisha 拥有映射), 别交给
宿主模型即兴。三段:

  1. `build_question_schema()`  —— chisha 出 3 题问卷 schema, host 渲染 (Claude Code 用
     AskUserQuestion / Codex 用编号列表), 每题可跳过 (守 onboard 零强制)。
  2. `plan_profile_writes(answers, profile)` —— **确定性分类器** (host 不脑补): 把 host
     回传的答案分流到 profile 字段。hard_avoid 跨 L0/偏好层分流 (impl-plan §3c):
       过敏 (显式 `过敏:X` 标记) → L0-A medical.allergies (永不可破)
       素食 / 清真           → L0-B identity.dietary_law (永不可破)
       主食材 (海鲜/红肉…)    → preferences.avoid_main_ingredients
       菜系 (川菜/粤菜…)      → preferences.banned_cuisines
       其余无法归类           → rejected (fail-loud, 不静默放行)
     **不双写**同一意图到多个字段; 列表字段与现状取并集 (additive, 透明在预览里)。
  3. `apply_writes(text, writes, profile)` —— surgical YAML 写盘 (**保留注释**, 与
     SKILL.md "只动这一个字段、保留其它 YAML 结构" 既有设计一致), 值用 json.dumps 渲染
     (JSON ⊂ YAML 1.2)。

零 LLM、零网络、零 pydantic —— 只 stdlib + vendored pyyaml + food_enums + l0_constraints,
进形态B bundle (D-105 exclusion-based, 自动收录)。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from chisha.core_api_helpers import _taste_is_empty
from chisha.food_enums import CUISINES, INGREDIENT_TYPES
from chisha.l0_constraints import load_l0_constraints

QUESTION_SCHEMA_VERSION = "profile.3"  # D-119: 每题加「都行」sentinel + 菜系收 9 项适配 host 上限 + 辣度上限文案


def stamp_schema_version(text: str) -> str:
    """更新机制 P4: 确保 profile.yaml 顶部有 `schema_version: <当前>` (缺则插顶部, 旧则就地替换).

    onboard 走模板占位替换; profile apply 走本助手 (surgical, 不动其它行)。"""
    import re
    line = f"schema_version: {QUESTION_SCHEMA_VERSION}"
    if re.search(r"^schema_version:", text, flags=re.M):
        return re.sub(r"^schema_version:.*$", line, text, count=1, flags=re.M)
    return line + "\n" + text


def profile_schema_outdated(profile: dict) -> bool:
    """更新机制 P4: profile 的 schema_version 缺失或 < 当前 → True (提示 onboard --resume 补新增项)."""
    def _n(v) -> int:
        try:
            return int(str(v).split(".")[-1])
        except (ValueError, AttributeError, TypeError):
            return -1
    return _n(profile.get("schema_version")) < _n(QUESTION_SCHEMA_VERSION)

# 身份伦理识别词 (→ L0-B dietary_law). 值集对齐 l0_constraints (vegetarian / halal)。
_VEGETARIAN_WORDS = {"素食", "vegetarian", "纯素食", "吃素"}
_HALAL_WORDS = {"清真", "halal", "穆斯林"}
# 过敏显式标记前缀 (host 从 memory allow-list 信号代填; 随口 free-text 不自动升级为永不可破)
_ALLERGY_PREFIXES = ("过敏:", "过敏：", "allergy:", "allergy：")

# hard_avoid 可勾选的主食材 (avoid 语义有意义的子集; 不列 纯素/主食/汤/其他)
_AVOIDABLE_INGREDIENTS = ["海鲜", "红肉", "白肉", "蛋", "豆制品"]

# D-119: onboard 问卷里**实际展示**的菜系子集 (高频优先)。
#   宿主 ask-user-question 单题选项有上限 (openclaw-lark feishu_ask_user_question = 10,
#   Claude Code AskUserQuestion = 4); 全 16 项放不下 → 飞书会降级成自由文本框, 正是「菜系列表
#   很少、被迫打字」的根。多选题还要留 1 格给「都行」sentinel, 故展示 9 项 (9 + sentinel = 10,
#   贴 feishu 上限)。长尾 (潮汕/鲁/西北/东北/东南亚/汤粥/其他) onboard 不收, 用户想要走自然语言
#   告知 (taste/refine 自由文本) 或手改 ~/.chisha/profile.yaml; food_enums 全 16 项不动 (打标/校验仍用全集)。
CUISINE_ONBOARD_CHOICES = ["快餐", "粤菜", "川菜", "湘菜", "江浙", "日式", "韩式", "西式", "小吃"]
assert set(CUISINE_ONBOARD_CHOICES) <= CUISINES, "CUISINE_ONBOARD_CHOICES 越出 food_enums 枚举"

# D-119:「我没有 / 都行」sentinel —— 飞书 form **每题强制必答** (openclaw-lark ask-user-question.js:
#   漏答弹「请先完成」无法提交), schema 的 skippable 在飞书端不生效。故每道选择题给一个合法的
#   「空答案」option, 映射层认它为**静默 no-op** (不写盘、也不进 rejected, 不显示成「未采纳」像报错)。
NO_PREFERENCE_VALUE = "无"
# sentinel option 的 label —— build_question_schema 用同一组常量渲染, _NO_PREF_FORMS 也据此**派生**
# (不手抄): 改 label 只动这里, 渲染 + 识别同步, 杜绝「改了 label → host 回传不被识别 → 落 rejected 像报错」。
_SENTINEL_LABEL_AVOID = "🤷 没有 / 都能吃"
_SENTINEL_LABEL_LIKED = "🤷 没特别爱吃 / 都行"
_SENTINEL_LABEL_DISLIKED = "🤷 没特别不爱 / 都行"
_SENTINEL_LABELS = (_SENTINEL_LABEL_AVOID, _SENTINEL_LABEL_LIKED, _SENTINEL_LABEL_DISLIKED)

# 多选答案分隔符 (host/飞书偶尔把多选回成 "粤菜, 川菜" / "川菜、日式" 单串; 防御性拆开)。
# 不含 "/"：feishu multi-select join 用 ", " (ask-user-question.js), 且部分 option label 本身含 "/"
# (如 "素食 (不吃红肉/白肉/海鲜)") —— 拿 "/" 拆会把整条 label 切碎成垃圾, 故只认逗号/分号/顿号。
_MULTI_SEP = re.compile(r"[、,，;；]+")


def _normalize_sentinel(item: str) -> str:
    """去 emoji 装饰 + 所有空白/斜杠 → 供 sentinel 整串匹配 (label 形如 '🤷 没特别爱吃 / 都行')。"""
    s = str(item).strip().lstrip("🤷")
    return re.sub(r"[\s/／]+", "", s)


# 「没有偏好」合法答案 = 短自然说法 ∪ 三个 sentinel label 归一形 (从 _SENTINEL_LABELS 派生)。
# **整串精确匹配, 故意不做子串** —— 子串会把 '海鲜都能接受但花生过敏' / '我都能吃辣的' 这类夹真实信息的
# 自由文本整条静默吞掉 (hard_avoid 是 L0 安全字段, 静默吞致命; review agent 实证)。host 回 value '无'
# 或整条 label 都认。
_NO_PREF_FORMS = (
    {"无", "没有", "都行", "都可以", "随便", "无所谓", "都能吃", "都能接受"}
    | {_normalize_sentinel(lbl) for lbl in _SENTINEL_LABELS}
)

# 守门: multi_select 选项的 value/label 不得含 _MULTI_SEP 分隔符 (否则 _as_list 拆碎成垃圾)。
# (spicy 的 "中辣 (含微辣、不辣)" 含顿号但走 _as_spicy 不经 _as_list, 不在此列。)
assert not any(
    _MULTI_SEP.search(s)
    for s in (NO_PREFERENCE_VALUE, *_SENTINEL_LABELS, *CUISINE_ONBOARD_CHOICES, *_AVOIDABLE_INGREDIENTS)
), "multi_select 选项含 _MULTI_SEP 分隔符 → _as_list 会拆碎"


def _is_no_preference(item) -> bool:
    """识别「没有偏好」sentinel: 整串精确匹配 (认 value '无'、常见自然说法、整条 sentinel label)。

    **故意不做子串** —— 防 '海鲜都能接受但花生过敏' / '我都能吃辣的' 这类含真实信息的自由文本被静默吞。
    """
    return _normalize_sentinel(item) in _NO_PREF_FORMS


# ─────────────────────────── 1. question schema ───────────────────────────

def _no_pref_option(label: str) -> dict:
    """D-119:「我没有/都行」sentinel option (合法的空答案, 映射认作静默 no-op)。"""
    return {"value": NO_PREFERENCE_VALUE, "label": label}


def build_question_schema() -> dict:
    """5 题问卷 schema (D-113/D-119). goal 不进 (哈佛餐盘内 goal 杠杆小, 退人读便签)。每题 skippable。

    维度按「引擎真消费 × 出错代价」排: hard_avoid(L0/L1 硬过滤·安全) → liked/disliked_cuisines
    (L2 软加/软扣) → spicy(召回硬过滤·坏默认根治) → taste_seed(L3 自由文本)。

    D-119 (onboard 体验): ① 每道**选择题首位**放「都行/都能吃」sentinel —— 飞书 form 每题强制必答,
    skippable 在飞书端不生效, sentinel 是用户「没有偏好」的合法出口 (映射静默 no-op)。② 菜系用
    CUISINE_ONBOARD_CHOICES (9 项) 而非全 16 —— 贴 host 单题选项上限, 不再降级成自由文本框逼用户打字。
    ③ 辣度 prompt/label 讲清「上限」语义 (选中辣=微辣/不辣也都接受; 召回本就 ≤上限 过滤)。
    """
    return {
        "schema_version": QUESTION_SCHEMA_VERSION,
        "intro": "几个快速选择, 帮我更懂你的口味 —— 没有的就选「都行」, 随时能改:",
        "questions": [
            {
                "id": "hard_avoid",
                "prompt": "有什么是你绝对不吃的吗？(过敏 / 宗教素食清真 / 不吃某类; 没有就选「都能吃」)",
                "kind": "multi_select",
                "allow_free_text": True,
                "skippable": True,
                "options": (
                    [_no_pref_option(_SENTINEL_LABEL_AVOID)]
                    + [{"value": "素食", "label": "素食 (不吃红肉/白肉/海鲜)"},
                       {"value": "清真", "label": "清真 (不吃猪肉等)"}]
                    + [{"value": ing, "label": f"不吃{ing}"} for ing in _AVOIDABLE_INGREDIENTS]
                ),
                "free_text_hint": (
                    "其它忌口直接写菜系名 (如 饮品甜品); "
                    "过敏请写成 “过敏:花生” (医学级·永不可破)。"
                ),
                "mapping_note": (
                    "映射由 chisha 确定性决定: 素食/清真→身份伦理(永不可破); "
                    "海鲜/红肉等主食材→忌口食材; 过敏:X→医学过敏(永不可破); "
                    "已知菜系→banned; 无法归类→拒写并提示。「没有/都能吃」= 无忌口, 静默不写。"
                ),
            },
            {
                "id": "liked_cuisines",
                "prompt": "平时爱吃哪些菜系？(软加分, 多选; 没有就选「都行」)",
                "kind": "multi_select",
                "allow_free_text": True,
                "skippable": True,
                "options": (
                    [_no_pref_option(_SENTINEL_LABEL_LIKED)]
                    + [{"value": c, "label": c} for c in CUISINE_ONBOARD_CHOICES]
                ),
                "mapping_note": "→ preferences.liked_cuisines (仅收已知菜系, 其余拒写)。「都行」静默不写。",
            },
            {
                "id": "disliked_cuisines",
                "prompt": "有哪些菜系不太想吃？(软扣分, 多选 — 绝对不吃请填第一题忌口; 没有就选「都行」)",
                "kind": "multi_select",
                "allow_free_text": True,
                "skippable": True,
                "options": (
                    [_no_pref_option(_SENTINEL_LABEL_DISLIKED)]
                    + [{"value": c, "label": c} for c in CUISINE_ONBOARD_CHOICES]
                ),
                "mapping_note": (
                    "→ preferences.disliked_cuisines (软扣分, 仅收已知菜系)。「都行」静默不写。"
                    "与喜爱冲突→不爱吃赢; 与忌口(硬 ban)冲突→拒写(硬 ban 已涵盖)。"
                ),
            },
            {
                "id": "spicy",
                "prompt": "能吃的最高辣度？(选了它, 更淡的也都接受)",
                "kind": "single_select",
                "allow_free_text": False,
                "skippable": True,
                "options": [
                    {"value": 0, "label": "不吃辣"},
                    {"value": 1, "label": "微辣 (含不辣)"},
                    {"value": 2, "label": "中辣 (含微辣、不辣)"},
                    {"value": 3, "label": "重辣都行"},
                ],
                "mapping_note": (
                    "→ preferences.spicy_tolerance (0-3 整数, 召回按『≤上限』硬过滤: 选中辣=2 则辣度"
                    "0/1/2 全保留, 只挡 3 —— 不是精确档, 别引导逐档勾选)。host 回 label 也能兜底解析。"
                    "跳过=保持模板默认 2 (不写 null: 召回侧 None 比较会崩)。"
                ),
            },
            {
                "id": "taste_seed",
                "prompt": "口味上有什么偏好？(一句话, 没有就填「无」)",
                "kind": "free_text",
                "allow_free_text": True,
                "skippable": True,
                "free_text_hint": (
                    "如 “少油、清淡、重口下饭”; 也可说具体爱吃/不爱吃的菜或食材 "
                    "(如 “爱吃牛肉面、不爱香菜”)。辣度有专门一题, 这里说其它口味; "
                    "越具体 L3 越懂你。没有就填「无」。"
                ),
                "mapping_note": "→ taste_description (自由文本, 不结构化拆分, D-014)。填「无/没有」= 静默不写。",
            },
        ],
        "next": (
            "渲染问卷收集答案 (memory 有显式饮食信号可预选默认值, 见 SKILL.md 三道闸) → "
            "chisha profile apply --answers '<json>' (先不带 --confirm 看预览, 用户确认后再带)"
        ),
    }


def profile_is_configured(profile: dict) -> bool:
    """D-119: 画像是否已有任何用户偏好信号 (taste / 菜系爱憎 / 忌口食材 / 身份饮食 / 医学过敏)。

    spicy_tolerance **不算** (模板默认 2, 永远有值, 不能判区分)。供 `onboard` 输出 profile_configured,
    让宿主据此决定要不要主动提配画像 —— 不再绑一次性 onboard 事件 (跨宿主共享 ~/.chisha/ 时
    onboard 会 status=exists, 但只要这里 False 仍要主动提)。
    """
    if not isinstance(profile, dict):
        return False
    if not _taste_is_empty(profile):     # 复用 core_api_helpers 单源 (与 eat 回包 profile_status.taste 同口径)
        return True
    prefs = profile.get("preferences") or {}
    for k in ("liked_cuisines", "banned_cuisines", "disliked_cuisines", "avoid_main_ingredients"):
        if prefs.get(k):
            return True
    l0 = load_l0_constraints(profile)
    return bool(l0.medical_allergies or l0.dietary_law)


# ─────────────────────────── 2. 确定性映射 ───────────────────────────

@dataclass
class WritePlan:
    """plan_profile_writes 结果。writes/noops/rejected 都给 host 渲染确认预览用。"""
    writes: list[dict] = field(default_factory=list)      # {field, value, label, sources, note}
    noops: list[dict] = field(default_factory=list)       # {field, reason} 已是现值
    rejected: list[dict] = field(default_factory=list)    # {value, question, reason}

    def has_writes(self) -> bool:
        return bool(self.writes)


def _as_list(v) -> list[str]:
    """multi_select 答案归一: list[str] 直收; 单 str 包成 [str]; 其它丢空。

    D-119: host/飞书偶尔把多选答案回成 "粤菜, 川菜" 单串 (feishu `selected.join(', ')`);
    单个 item 含分隔符 (、,，;；/) 就拆开, 让宿主没拆数组时也能正确归一。
    """
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        s = str(item).strip()
        if not s:
            continue
        parts = [p.strip() for p in _MULTI_SEP.split(s) if p.strip()]
        out.extend(parts if len(parts) > 1 else [s])
    return out


def _dedup(seq: list[str]) -> list[str]:
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# 辣度 label→int (host 应回 value 整数, 但偶尔回档名或整条 label; 确定性兜底)。按「主档优先」
# (重>中>微>不) 子串匹配, 取最前命中 —— 同时覆盖裸档名 ("中辣") 与含上限说明的 label
# ("中辣 (含微辣、不辣)"), 故无需再维护一份精确 map (子串对裸档名结果一致)。
_SPICY_SUBSTR = [("重辣", 3), ("中辣", 2), ("微辣", 1), ("不吃辣", 0), ("不辣", 0)]


def _as_spicy(v) -> int | None:
    """辣度答案归一为 0-3 整数; 越界 / 无法解析 / 跳过 → None (不写, 保持默认)。"""
    if v is None or isinstance(v, bool):  # bool 是 int 子类, 排除
        return None
    if isinstance(v, int):
        return v if 0 <= v <= 3 else None
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            n = int(s)
            return n if 0 <= n <= 3 else None
        for token, val in _SPICY_SUBSTR:    # 裸档名 / 含说明 label 子串兜底 (主档优先)
            if token in s:
                return val
        return None
    if isinstance(v, list):  # host 偶尔把 single_select 包成 single-item list
        # 不经 _as_list: 它会按顿号拆 "中辣 (含微辣、不辣)" 成多项 → 误判 len>1 → None (review #2)
        plain = [str(x).strip() for x in v if str(x).strip()]
        return _as_spicy(plain[0]) if len(plain) == 1 else None
    return None


def _strip_allergy_marker(item: str) -> str | None:
    """命中过敏前缀 → 返回过敏原 (去前缀去空白); 否则 None。"""
    for pre in _ALLERGY_PREFIXES:
        if item.startswith(pre):
            return item[len(pre):].strip() or None
    return None


def plan_profile_writes(answers: dict, profile: dict) -> WritePlan:
    """确定性把答案分流到 profile 字段 + 与现状合并, 产出 writes/noops/rejected。

    映射 100% 在 chisha (host 不脑补)。列表字段取并集 (additive); 标量替换。
    每条 hard_avoid 按**首命中优先**精确分流, **不双写** (一条只进一个字段)。
    """
    plan = WritePlan()
    if not isinstance(answers, dict):
        return plan

    cur_l0 = load_l0_constraints(profile)
    prefs = profile.get("preferences") or {}
    cur_avoid_ing = list(prefs.get("avoid_main_ingredients") or [])
    cur_banned = list(prefs.get("banned_cuisines") or [])
    cur_liked = list(prefs.get("liked_cuisines") or [])
    cur_disliked = list(prefs.get("disliked_cuisines") or [])
    cur_spicy = prefs.get("spicy_tolerance")
    cur_taste = profile.get("taste_description")

    # ── 累加器 ──
    new_allergies: list[str] = []
    new_dietary_law: str | None = None
    new_avoid_ing: list[str] = []
    new_banned: list[str] = []
    new_liked: list[str] = []
    new_disliked: list[str] = []
    new_spicy: int | None = None
    new_taste: str | None = None

    # ── Q1 hard_avoid 分流 ──
    for item in _as_list(answers.get("hard_avoid")):
        if _is_no_preference(item):     # D-119:「都能吃」sentinel → 无忌口, 静默跳过 (不进 rejected)
            continue
        allergen = _strip_allergy_marker(item)
        if allergen is not None:
            new_allergies.append(allergen)
            continue
        if item in _VEGETARIAN_WORDS:
            law = "vegetarian"
        elif item in _HALAL_WORDS:
            law = "halal"
        else:
            law = None
        if law is not None:
            if new_dietary_law is None:
                new_dietary_law = law
            elif new_dietary_law != law:
                plan.rejected.append({
                    "value": item, "question": "hard_avoid",
                    "reason": f"dietary_law 冲突 (已选 {new_dietary_law}); 一次只能一种身份饮食",
                })
            continue
        if item in INGREDIENT_TYPES:
            new_avoid_ing.append(item)
            continue
        if item in CUISINES:
            new_banned.append(item)
            continue
        plan.rejected.append({
            "value": item, "question": "hard_avoid",
            "reason": ("无法确定归类 (不是已知菜系/食材/身份)。过敏忌口请用 “过敏:X” "
                       "标注 (医学级·永不可破), 或手动编辑 ~/.chisha/profile.yaml。"),
        })

    # ── Q2 liked_cuisines ──
    for item in _as_list(answers.get("liked_cuisines")):
        if _is_no_preference(item):     # D-119:「都行」sentinel → 静默跳过
            continue
        if item in CUISINES:
            new_liked.append(item)
        else:
            plan.rejected.append({
                "value": item, "question": "liked_cuisines",
                "reason": "不是已知菜系 (16 项枚举之外), 已跳过; 可手动加进 preferences。",
            })

    # ── Q3 disliked_cuisines (软扣分) ──
    for item in _as_list(answers.get("disliked_cuisines")):
        if _is_no_preference(item):     # D-119:「都行」sentinel → 静默跳过
            continue
        if item in CUISINES:
            new_disliked.append(item)
        else:
            plan.rejected.append({
                "value": item, "question": "disliked_cuisines",
                "reason": "不是已知菜系 (16 项枚举之外), 已跳过; 可手动加进 preferences。",
            })

    # ── Q4 spicy (单选 0-3; 跳过/越界→None, 不写) ──
    new_spicy = _as_spicy(answers.get("spicy"))

    # ── Q5 taste_seed (D-119: 填「无/没有」= 静默不写, exact 匹配防 '我都能吃辣的' 误吞) ──
    taste_ans = answers.get("taste_seed")
    if isinstance(taste_ans, str) and taste_ans.strip():
        if not _is_no_preference(taste_ans):
            new_taste = taste_ans.strip()
    elif isinstance(taste_ans, list):  # host 偶尔传 list, 容错拼接
        items = [x for x in _as_list(taste_ans) if not _is_no_preference(x)]
        new_taste = "、".join(items) or None

    # ── 冲突裁决 (负向 avoid 优先于正向 like; 硬 ban > 软 disliked) ──
    #   banned ∩ disliked → 拒 disliked (硬 ban 已涵盖, 软扣重复)
    #   banned ∩ liked    → banned 赢, 拒 liked
    #   disliked ∩ liked  → disliked 赢, 拒 liked ("别推" 比 "喜欢" 安全)
    banned_set = set(new_banned)
    for c in sorted(set(new_disliked) & banned_set):
        plan.rejected.append({
            "value": c, "question": "disliked_cuisines",
            "reason": f"{c} 已在忌口 (硬 ban) 中, 软扣重复 → 跳过不爱吃。",
        })
    new_disliked = [c for c in new_disliked if c not in banned_set]
    disliked_set = set(new_disliked)
    liked_vs_banned = set(new_liked) & banned_set
    liked_vs_disliked = (set(new_liked) & disliked_set) - liked_vs_banned
    for c in sorted(liked_vs_banned):
        plan.rejected.append({
            "value": c, "question": "liked_cuisines",
            "reason": f"{c} 同时被列入忌口 → 以忌口为准, 不计入喜爱。",
        })
    for c in sorted(liked_vs_disliked):
        plan.rejected.append({
            "value": c, "question": "liked_cuisines",
            "reason": f"{c} 同时被列入不爱吃 → 以不爱吃为准, 不计入喜爱。",
        })
    new_liked = [c for c in new_liked if c not in liked_vs_banned and c not in liked_vs_disliked]

    def _list_write(field_name, new_items, current, label):
        if not new_items:
            return
        merged = _dedup(list(current) + _dedup(new_items))
        if merged == list(current):
            plan.noops.append({"field": field_name, "reason": "已是现值"})
            return
        plan.writes.append({
            "field": field_name, "value": merged, "label": label,
            "sources": _dedup(new_items),
        })

    if new_allergies:
        merged = _dedup(list(cur_l0.medical_allergies) + _dedup(new_allergies))
        if merged != list(cur_l0.medical_allergies):
            plan.writes.append({
                "field": "l0_constraints.medical.allergies", "value": merged,
                "label": "医学过敏 (永不可破)", "sources": _dedup(new_allergies),
                "note": "L0-A 医学级, refine 永不可解除",
            })
        else:
            plan.noops.append({"field": "l0_constraints.medical.allergies", "reason": "已是现值"})

    if new_dietary_law is not None:
        if new_dietary_law != cur_l0.dietary_law:
            plan.writes.append({
                "field": "l0_constraints.identity.dietary_law", "value": new_dietary_law,
                "label": f"身份饮食 {new_dietary_law} (永不可破)",
                "sources": [new_dietary_law],
                "note": "L0-B 身份伦理, refine 永不可解除, 只能改 profile",
            })
        else:
            plan.noops.append({"field": "l0_constraints.identity.dietary_law", "reason": "已是现值"})

    _list_write("preferences.avoid_main_ingredients", new_avoid_ing, cur_avoid_ing, "忌口食材")
    _list_write("preferences.banned_cuisines", new_banned, cur_banned, "忌口菜系")
    _list_write("preferences.liked_cuisines", new_liked, cur_liked, "喜爱菜系")
    _list_write("preferences.disliked_cuisines", new_disliked, cur_disliked, "不爱吃菜系")

    if new_spicy is not None:
        if new_spicy != cur_spicy:
            plan.writes.append({
                "field": "preferences.spicy_tolerance", "value": new_spicy,
                "label": f"辣度耐受 {new_spicy} (0不辣/1微辣/2中辣/3重辣)",
                "sources": [str(new_spicy)],
            })
        else:
            plan.noops.append({"field": "preferences.spicy_tolerance", "reason": "已是现值"})

    if new_taste is not None:
        if new_taste != (cur_taste or None):
            plan.writes.append({
                "field": "taste_description", "value": new_taste,
                "label": "口味描述", "sources": [new_taste],
            })
        else:
            plan.noops.append({"field": "taste_description", "reason": "已是现值"})

    return plan


def summarize_plan(plan: WritePlan) -> list[str]:
    """人读确认预览行 (host 念给用户看 → 用户确认才落盘)。"""
    lines: list[str] = []
    for w in plan.writes:
        src = " / ".join(w.get("sources") or [])
        note = f" [{w['note']}]" if w.get("note") else ""
        lines.append(f"将写入 {w['field']} = {w['value']!r}{note}  ← {src}")
    for r in plan.rejected:
        lines.append(f"未采纳 “{r['value']}” ({r['question']}): {r['reason']}")
    if not lines:
        lines.append("（空问卷, 无可写入 — 已跳过, 守 onboard 零强制输入）")
    return lines


# ─────────────────────────── 3. surgical YAML 写盘 ───────────────────────────

def _yaml_scalar(value) -> str:
    """渲染 inline YAML 值: json.dumps (JSON ⊂ YAML 1.2; 处理 str/list/None/中文)。"""
    return json.dumps(value, ensure_ascii=False)


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _replace_span(lines: list[str], idx: int, rendered: str) -> list[str]:
    """替换 lines[idx] 为 rendered, 吃掉其后属于该 key 的续行 (block-style / flow 多行值),
    防孤儿行 (Codex review c)。

    续行判定: 缩进 > base 的行一律吃; **空行**只在其后(跨连续空行)仍有更深缩进行时才算
    block 内部空行一并吃 —— 否则空行是与下一同级 key 的分隔, 保留 (不破坏排版)。
    """
    base = _indent_of(lines[idx])
    end = idx + 1
    while end < len(lines):
        ln = lines[end]
        if ln.strip() == "":
            nxt = end + 1
            while nxt < len(lines) and lines[nxt].strip() == "":
                nxt += 1
            if nxt < len(lines) and _indent_of(lines[nxt]) > base:
                end = nxt          # 空行夹在 block 续行中间 → 连空行带续行一起吃
                continue
            break                  # 空行是与下一 key 的分隔 → 停, 保留空行
        if _indent_of(ln) <= base:
            break                  # 同级 / 更浅 key → block 结束
        end += 1
    return lines[:idx] + [rendered] + lines[end:]


def _set_top_scalar(lines: list[str], key: str, value) -> list[str]:
    rendered = f"{key}: {_yaml_scalar(value)}"
    pat = re.compile(rf"^{re.escape(key)}\s*:")
    for i, ln in enumerate(lines):
        if pat.match(ln):
            return _replace_span(lines, i, rendered)
    return lines + [rendered]  # 缺 → 追加


def _set_child(lines: list[str], parent: str, key: str, value, indent: str = "  ") -> list[str]:
    rendered = f"{indent}{key}: {_yaml_scalar(value)}"
    parent_pat = re.compile(rf"^{re.escape(parent)}\s*:")
    child_pat = re.compile(rf"^{re.escape(indent)}{re.escape(key)}\s*:")
    pi = None
    for i, ln in enumerate(lines):
        if parent_pat.match(ln):
            pi = i
            break
    if pi is None:
        return lines + [f"{parent}:", rendered]  # 缺 parent → 追加整段
    j = pi + 1
    while j < len(lines):
        ln = lines[j]
        if ln.strip() != "" and _indent_of(ln) == 0:
            break  # 下一个顶层 key → parent 块结束
        if child_pat.match(ln):
            return _replace_span(lines, j, rendered)
        j += 1
    return lines[:pi + 1] + [rendered] + lines[pi + 1:]  # child 缺 → 插在 parent 后


def _set_l0_block(lines: list[str], allergies: list[str], dietary_law: str | None) -> list[str]:
    """L0 块整体再生 (模板从不含 → append 为主路径; 用户手建 → 替换)。"""
    block = [
        "l0_constraints:",
        "  medical:",
        f"    allergies: {_yaml_scalar(allergies)}",
        "  identity:",
        f"    dietary_law: {_yaml_scalar(dietary_law)}",
    ]
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^l0_constraints\s*:", ln):
            start = i
            break
    if start is None:
        tail = ([""] if (lines and lines[-1].strip() != "") else []) + [
            "# ===== L0 硬约束 (D-080 三分: A医学过敏 / B身份伦理) =====",
            "# 由 `chisha profile` 写入; medical.allergies + identity.dietary_law "
            "永不可破 (refine 不可解除)",
        ]
        return lines + tail + block
    end = start + 1
    while end < len(lines) and (lines[end].strip() == "" or _indent_of(lines[end]) > 0):
        end += 1
    return lines[:start] + block + lines[end:]


def apply_writes(text: str, plan: WritePlan, profile: dict) -> str:
    """把 plan.writes surgical 应用到 profile.yaml 文本, 返回新文本 (保留注释)。"""
    lines = text.splitlines()
    cur_l0 = load_l0_constraints(profile)
    l0_allergies = cur_l0.medical_allergies
    l0_law = cur_l0.dietary_law
    l0_touched = False

    for w in plan.writes:
        f, v = w["field"], w["value"]
        if f == "taste_description":
            lines = _set_top_scalar(lines, "taste_description", v)
        elif f == "preferences.avoid_main_ingredients":
            lines = _set_child(lines, "preferences", "avoid_main_ingredients", v)
        elif f == "preferences.banned_cuisines":
            lines = _set_child(lines, "preferences", "banned_cuisines", v)
        elif f == "preferences.liked_cuisines":
            lines = _set_child(lines, "preferences", "liked_cuisines", v)
        elif f == "preferences.disliked_cuisines":
            lines = _set_child(lines, "preferences", "disliked_cuisines", v)
        elif f == "preferences.spicy_tolerance":
            lines = _set_child(lines, "preferences", "spicy_tolerance", v)
        elif f == "l0_constraints.medical.allergies":
            l0_allergies, l0_touched = v, True
        elif f == "l0_constraints.identity.dietary_law":
            l0_law, l0_touched = v, True

    if l0_touched:
        lines = _set_l0_block(lines, l0_allergies, l0_law)

    return "\n".join(lines) + "\n"

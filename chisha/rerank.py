"""LLM 精排 (D-035 → D-046): topN candidates → 5 个候选 (3 exploit + 2 explore).

D-046 重构 (2026-05-13):
- top N 从 30 → 40 (L2 4 层 cap 已把多样性骨架定死, top31-40 仍有结构增量,
  top41+ 高度同质, 且 lost-in-the-middle 会让 LLM 看不见中后段)
- prompt 拆 system / user:
  - system (prompts/rerank_system.md): 角色 + 任务 + 输出 schema + few-shot,
    打 Anthropic prompt cache, 100% 命中
  - user: 紧凑符号化的 PROFILE+CONTEXT+CANDIDATES, 每菜一行约 80-100 字符
- payload 紧凑化: 每 candidate 从 ~1.47k chars 砍到 ~600 chars, 默认值省略
- health_flags 从 LLM 输出移除, 改 rerank.py 收到结果后用规则算 (确定性 +
  省 input/output token + 不再让 LLM 算油的算术平均). 最终对外字段不变.

输入: 打分后 top40 combos + ContextSnapshot + profile + meal_log.
输出: list[dict], 每条 candidate 含:
    rank / is_explore / combo_index / fit_score / health_flags /
    taste_match / risk_flags / one_line_reason

LLM 失败 → fallback (规则) 退化到打分 top n + 规则 reason, 保证管道不断.
refine=True 时 n_explore=0 (D-015).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chisha.context import ContextSnapshot

ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT_PATH = ROOT / "prompts" / "rerank_system.md"


# L3 LLM rerank 的输入候选数 (D-046 一审: 40 → 二审: 60 → D-047 终: 60).
# D-046 二审依据 (Codex 实测两 zone 分布):
#   shenzhen-bay top41-60 score 跨度 1.997, 10 brand / 12 个新餐厅 / 5 cuisine,
#     这一段是被 L2 4 层 cap 挤出 head 的真高分 tail.
# D-047 (2026-05-14) 矩阵实测 (lunch/want_light, sonnet+opus × top30/60/100 × 3
# 重复 = 18 调用, 100% tool_use 稳定):
#   - sonnet picks 跨 K: top30 [0,8,11,13,16,22] → top60 新增 [31,35,55] →
#     top100 新增 [83]. 验证 top31-60 真有多样性增量.
#   - opus picks 跨 K: top30 [13,16,18,20,22,24] → top60 新增 [2,31,55] →
#     top100 新增 [92].
#   - top100 边际增量小 (只多 1 个新候选), 成本 +40% 不值.
# K=60 是稳定 + 多样性 + 成本的最优平衡. tool_use 强制 schema (D-047) 完全
# 解决 D-046.1 的 CoT 泄漏问题, 不再需要 D-047 之前临时退回到 30.
L3_INPUT_TOP_K = 60


# D-047 tool schema: forced JSON schema 比 prompt 约束 + json_mode 强得多.
# Anthropic 原生 input_schema 格式; llm_client 自动适配 OR 的 OpenAI 格式.
_RERANK_TOOL = {
    "name": "select_top_candidates",
    "description": (
        "Select N candidates from the input candidate list, in rank order. "
        "exploit 段在前, explore 段在后. "
        "candidates must be emitted in final display order; "
        "rank must equal array position + 1 (1-indexed); "
        "first n - n_explore items have is_explore=false (exploit segment), "
        "last n_explore items have is_explore=true (explore segment), no interleaving. "
        "In refine mode n_explore=0, all candidates have is_explore=false."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "minItems": 1, "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "rank": {
                            "type": "integer", "minimum": 1, "maximum": 5,
                            "description": "1-indexed, strictly ascending, equals array position + 1.",
                        },
                        "is_explore": {
                            "type": "boolean",
                            "description": "First n - n_explore items are false (exploit segment), last n_explore items are true (explore segment); never interleave.",
                        },
                        "combo_index": {"type": "integer", "minimum": 0},
                        "fit_score": {"type": "number", "minimum": 0, "maximum": 1},
                        "taste_match": {"type": "number", "minimum": 0, "maximum": 1},
                        "risk_flags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "one_line_reason": {
                            "type": "string", "maxLength": 60,
                        },
                    },
                    "required": [
                        "rank", "is_explore", "combo_index",
                        "fit_score", "taste_match",
                        "risk_flags", "one_line_reason",
                    ],
                    "additionalProperties": False,
                },
            },
            # T-P1b-02: 顶层 narrative 字段, 概述"为什么推这 5 道"
            "narrative": {
                "type": "string",
                "maxLength": 100,
                "description": (
                    "≤ 50 字摘要, 解释为什么推荐这 5 道. 必须有执行证据支撑 "
                    "(例: '阴雨 + 近 2 餐高油 → 给你低油暖菜'), 禁止空泛形容."
                ),
            },
        },
        # T-P1b-02: narrative 现阶段非强制 (旧 trace 向后兼容), 解析层兜底空字符串
        "required": ["candidates"],
        "additionalProperties": False,
    },
}
_RERANK_TOOL_CHOICE = {"type": "tool", "name": "select_top_candidates"}


# claude_code_cli provider 不支持 tool_use 强制 schema, 走"软约束 + JSON 解析"
# 路径. 质量上限低于 tool_use (D-047 Part A 18-case 实测: tool_use 94% vs
# json_mode 67%), 仅自用阶段用 Max 订阅复用额度调试. 不要作为默认主路径.
_CLI_OUTPUT_SECTION = """# 输出方式 (claude_code_cli no-tool 路径)

直接输出一个 JSON 对象, 形如:

{"narrative": "今天阴雨 + 你近 2 餐高油 → 给你低油暖菜",
 "candidates": [
  {"rank": 1, "is_explore": false, "combo_index": 12,
   "fit_score": 0.85, "taste_match": 0.7,
   "risk_flags": ["油偏高"], "one_line_reason": "..."},
  ...
]}

字段约束:
- narrative (T-P1b-02 新增): ≤ 50 字摘要, 解释为什么推荐这 5 道. 必须有执行证据支撑
  (引用 refine_intent / context / 健康约束等). 禁止空泛形容. 缺省时回填 "" 不抛.
- rank: 1..n 连续整数, 严格升序, 等于 array position + 1 (1-indexed).
- is_explore: bool. 前 (n - n_explore) 个 false (exploit segment, 不许穿插), 后 n_explore 个 true (explore segment). refine 模式 n_explore=0 时全部 false.
- candidates 输出顺序 = 最终展示顺序 (exploit 段在前, explore 段在后, 不许穿插).
- combo_index: 必须是输入 [idx] 段里出现过的整数, 不能凭空生成, 不能超出输入候选数, 不能重复.
- fit_score: 0.0-1.0, 综合匹配度
- taste_match: 0.0-1.0, 与 taste_description 命中度. 锚点: 0.9-1.0 强命中 / 0.7-0.9 部分命中方向一致 / 0.5-0.7 同品类替代 / 0.3-0.5 仅大类命中 / 0.0-0.3 方向冲突或接近 disliked.
- risk_flags: 短词字符串数组, 无风险给 []
- one_line_reason: ≤ 30 字, 必须具体 + 不堆形容词. 比较条件化: 同品牌多变体必比 / 相邻 rank 可比 / 无可比对象不强行比较.

严格要求:
- 输出仅 JSON 对象本体, 以 { 开头 } 结尾
- 不要 markdown 代码块包裹 (不要 ```json ... ```)
- 不要前后说明文字
- 不要任何思考过程, 直接给结果
"""

_CLI_TAIL_INSTRUCTION = "现在等待 user 消息, 收到后立刻输出 JSON 对象 (无包裹)."


def _patch_system_prompt_for_cli(system_prompt: str) -> str:
    """把 system_prompt 里的 '# 输出方式' 段替换成 CLI no-tool 版本,
    并把末尾"调 select_top_candidates"一句改成"输出 JSON 对象".

    D-048 (Codex MAJOR 3): 未命中目标段时显式 ValueError, 不静默放过.
    防止未来 prompt 改标题 (比如 "## 输出方式" 或 "# 输出协议") 后 CLI
    收到 tool_use 指令但 claude_code_cli provider 不支持, 链路只能整体 fallback
    而错误根因被埋没.
    """
    lines = system_prompt.splitlines()
    out: list[str] = []
    matched_section = False
    matched_tail = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("# 输出方式"):
            matched_section = True
            # 跳过整个 "# 输出方式" 段, 直到下一个 "# " 开头 (不是 "## ")
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt.startswith("# ") and not nxt.startswith("## "):
                    break
                j += 1
            out.append(_CLI_OUTPUT_SECTION.rstrip())
            out.append("")
            i = j
            continue
        # 末尾那句固定文案替换
        if "select_top_candidates" in line and "现在等待" in line:
            matched_tail = True
            out.append(_CLI_TAIL_INSTRUCTION)
            i += 1
            continue
        out.append(line)
        i += 1

    if not matched_section:
        raise ValueError(
            "prompts/rerank_system.md 找不到 '# 输出方式' 段, _patch_system_prompt_for_cli "
            "无法把 tool_use 指令替换成 CLI 的 JSON 输出指令. 检查 prompt 是否改了标题 "
            "(应为 '# 输出方式' 顶级标题), 或同步更新 rerank.py 里的 patch 逻辑."
        )
    if not matched_tail:
        raise ValueError(
            "prompts/rerank_system.md 找不到末尾的 '...select_top_candidates...现在等待...' "
            "指令, 同步检查 prompt 末尾文案和 _patch_system_prompt_for_cli 的匹配条件."
        )
    return "\n".join(out)


def _parse_json_object_from_text(raw: str) -> dict | None:
    """从 LLM 输出文本里解析出 {"candidates": [...]} 对象.

    D-048 MAJOR 2 (Codex review): 第三层 fallback 改用 json.JSONDecoder.raw_decode
    从每个 `{` 起点扫描, 取第一个可解析且含 'candidates' 的 dict. 旧的"首 {
    到末 }"在 CoT 包含无关 `{}` 时会拼入垃圾导致整个解析失败.

    多 fallback (按优先级):
    1. json.loads(raw)        — LLM 完美遵守 prompt 时命中
    2. ```json fence``` 包裹   — sonnet 偶尔加 markdown 包裹
    3. raw_decode 扫所有 `{`   — CoT 前缀或后缀有杂物时
    """
    import json
    import re

    if not raw or not raw.strip():
        return None
    text = raw.strip()

    # 1. 直接解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 2. ```json ... ``` 或 ``` ... ``` 包裹
    fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence:
        try:
            obj = json.loads(fence.group(1).strip())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # 3. raw_decode 扫描所有 `{` 起点, 取第一个含 'candidates' 的合法 JSON dict.
    #    优先 candidates dict, 避免吃到 CoT 里的无关 `{...}` 片段.
    decoder = json.JSONDecoder()
    fallback_obj: dict | None = None  # 万一没有 candidates dict, 第一个合法 dict 作兜底
    for m in re.finditer(r"\{", text):
        try:
            obj, _end = decoder.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if "candidates" in obj:
            return obj
        if fallback_obj is None:
            fallback_obj = obj

    return fallback_obj


# D-047 默认走 opus (V3+V4 实测质量略胜 sonnet 65% 成本溢价但更尊重 taste).
# 故障时调用方传 model="anthropic/claude-sonnet-4.6" 降级 (绝不加 thinking,
# Anthropic 官方明确 forced tool_choice + extended thinking 不兼容).
#
# Provider 命名空间不同 (D-047 merge 修复):
# - anthropic 直连: claude-opus-4-7 (短名, '-')
# - openrouter: anthropic/claude-opus-4.7 (前缀+'.')
# - claude_code_cli: opus (CLI 短别名)
#
# ⚠️ D-048 (Codex MAJOR 4): 这里是 *无 profile override 时的兜底默认*.
# profile.yaml `llm.model.<provider>` 一旦设了, _run_llm_rerank 会让 call_text
# 走 profile 配置 (而不是这里的默认). 当前 profile.yaml 三个 provider 都
# 显式配 sonnet, 实际生效不是这里写的 opus. 见 docs/archive/DECISIONS_phase0.md D-048.
_RERANK_MODEL_BY_PROVIDER = {
    "anthropic": "claude-opus-4-7",
    "openrouter": "anthropic/claude-opus-4.7",
    "claude_code_cli": "opus",
}
# 兼容旧入参 (model="anthropic/claude-opus-4.7" 已用作显式降级符号), 兜底取 OR 命名空间
_DEFAULT_RERANK_MODEL = _RERANK_MODEL_BY_PROVIDER["openrouter"]


# LLM 输出的必填字段 (D-046: 删了 health_flags, 由规则后处理算)
_REQUIRED_FIELDS = {
    "rank", "is_explore", "combo_index",
    "fit_score", "taste_match",
    "risk_flags", "one_line_reason",
}

# F2 (Faithful D-074): _map_validated_candidates 合并时, LLM/agent candidate 只允许
# 覆盖这些字段 (排序 + 说明 + 规则补的 health_flags); restaurant/dishes/score 等
# 确定性事实由 top_combos 保持, 绝不被回传覆盖.
_AGENT_OUTPUT_FIELDS = _REQUIRED_FIELDS | {"health_flags"}


# D-049 (Codex review 反馈): validator 给结构化 error code, 让 retry 路由 +
# 测试 fixture 不再依赖人类可读中文字符串. 文案改一下不会静默漏触发 retry.
class RerankValidationCode:
    """Stable validator error codes. retry policy + tests depend on these."""
    OK = "OK"
    NOT_LIST = "NOT_LIST"
    EMPTY = "EMPTY"
    OVER_N_MAX = "OVER_N_MAX"
    ITEM_NOT_DICT = "ITEM_NOT_DICT"
    MISSING_FIELDS = "MISSING_FIELDS"
    INVALID_INDEX = "INVALID_INDEX"
    INDEX_OUT_OF_RANGE = "INDEX_OUT_OF_RANGE"
    INDEX_DUPLICATE = "INDEX_DUPLICATE"
    INVALID_FIT_SCORE = "INVALID_FIT_SCORE"
    INVALID_TASTE_MATCH = "INVALID_TASTE_MATCH"
    INVALID_IS_EXPLORE = "INVALID_IS_EXPLORE"
    INVALID_RISK_FLAGS = "INVALID_RISK_FLAGS"
    RANK_NOT_SEQUENTIAL = "RANK_NOT_SEQUENTIAL"
    EXPLORE_COUNT_MISMATCH = "EXPLORE_COUNT_MISMATCH"
    EXPLORE_POSITION_WRONG = "EXPLORE_POSITION_WRONG"
    RANK_POSITION_MISMATCH = "RANK_POSITION_MISMATCH"  # T-PR-05: rank value != array position + 1
    UNKNOWN = "UNKNOWN"


# retry 只对 "opus 懂 schema 但数错/位置错" 类失败有效. 解析失败 / 缺字段 /
# index 越界等格式问题 retry 也修不好, 直接 fallback 省 12s + $0.03.
_RETRY_TRIGGER_CODES = frozenset({
    RerankValidationCode.OVER_N_MAX,
    RerankValidationCode.EXPLORE_COUNT_MISMATCH,
    RerankValidationCode.EXPLORE_POSITION_WRONG,
    RerankValidationCode.RANK_POSITION_MISMATCH,  # T-PR-05
})


# ─────────────────────── payload 紧凑化 (D-046) ───────────────────────


def _fmt_dish_line(d: dict) -> str:
    """单菜紧凑一行: `菜名｜main·烹·油N[·辣N·甜N·汤N]·[processed]｜role=X[·grain=Y]｜价`

    默认值不输出 (辣 0, 甜 0, 汤 1-2 不显示, processed False 不显示);
    role=配菜 默认省略 (最常见); grain 仅主食类菜显示.
    """
    np_ = d.get("nutrition_profile") or {}
    name = d.get("canonical_name", "?")
    main = np_.get("main_ingredient_type") or ""
    method = np_.get("cooking_method") or ""
    oil = np_.get("oil_level", 3)
    spicy = np_.get("spicy_level", 0)
    sweet = np_.get("sweet_sauce_level", 0) or 0
    wet = np_.get("wetness", 1) or 1
    role = np_.get("dish_role") or "配菜"
    grain = np_.get("grain_type") or ""
    processed = bool(np_.get("processed_meat_flag"))
    price = d.get("price", 0) or 0

    # 第一段: main·烹·油N (固定显示)
    seg1 = []
    if main: seg1.append(main)
    if method: seg1.append(method)
    seg1.append(f"油{int(oil)}")
    # 条件标注
    if spicy and int(spicy) > 0:
        seg1.append(f"辣{int(spicy)}")
    if sweet and int(sweet) >= 2:
        seg1.append(f"甜{int(sweet)}")
    if wet and int(wet) >= 3:
        seg1.append(f"汤{int(wet)}")
    if processed:
        seg1.append("processed")
    # 第二段: role 仅在不是配菜时显示
    seg2 = []
    if role and role != "配菜":
        seg2.append(f"role={role}")
    if grain and grain != "无" and (role == "主食" or "主食" in (role or "")):
        seg2.append(f"grain={grain}")

    parts = ["·".join(seg1)]
    if seg2:
        parts.append("·".join(seg2))
    parts.append(f"{float(price):.1f}")
    return f"  · {name}｜{'｜'.join(parts)}"


def _fmt_combo_block(idx: int, c: dict) -> str:
    """单 combo 紧凑块: header 行 + 每菜一行."""
    rest = c.get("restaurant") or {}
    name = rest.get("name", "?")
    dist_m = rest.get("distance_m", -1)
    eta = rest.get("delivery_eta_min", -1)
    score = c.get("score", 0)
    dishes = c.get("dishes") or []
    total = sum((d.get("price") or 0) for d in dishes)
    dist_str = f"{int(dist_m)/1000:.1f}km" if isinstance(dist_m, (int, float)) and dist_m > 0 else "?"
    eta_str = f"{int(eta)}min" if isinstance(eta, (int, float)) and eta > 0 else "?"
    header = f"[{idx}] {name}（{dist_str}/{eta_str}/L2 {score:.2f}/¥{total:.1f}）"
    lines = [header] + [_fmt_dish_line(d) for d in dishes]
    return "\n".join(lines)


def _fmt_list_or_none(xs) -> str:
    """空 → '(无)', 否则空格分隔 (跟 system prompt '(无)/(空)' 风格统一,
    不输出 Python repr '[]')."""
    if not xs:
        return "(无)"
    return " ".join(str(x) for x in xs)


def _fmt_counts_or_none(d) -> str:
    """空 → '(空)', 否则 'key×N key×N' 紧凑形式 (替代 Python dict repr,
    更可读且 token 略省)."""
    if not d:
        return "(空)"
    return " ".join(f"{k}×{v}" for k, v in list(d.items())[:8])


# D-079 BLOCKER fix: sentinel 区分"未传 l1_prefs_override (走默认 load_prefs)"
# vs "显式传 None (frozen 时 L1 抽取无产物)". 不能用 None 当默认 —— frozen
# snapshot 里 l1_prefs_snapshot 本来就允许是 None (那餐没抽出 prefs).
_UNSET_L1_PREFS: Any = object()

def _feedback_avoided_block(feedback_avoided_names: list[str] | None) -> str | None:
    """B-001/D-098 (T-FB-05): 把"本次因强负差评真剔除的店名"作为事实透传给 L3.

    D-085 忠实纪律: names 由 api/refine 算好 (强负剔除 ∩ 本 zone 存在的店 = 本次
    确实被 recall 删掉、且本来可能出现的店). narrative 据此说"已按你上次反馈避开
    XX" 是 by-construction 忠实. 全局 evict_names 里跨 zone / 本就不会出现的店不入
    此列 (Codex review BLOCKER: 防把"压根不在本次候选域"误归因给 feedback).

    None / 空 → None (无此块).
    """
    names = [n for n in (feedback_avoided_names or []) if n]
    if not names:
        return None
    return (
        "[FEEDBACK_AVOIDED] 以下餐厅因你近期明确差评(👎且不想再吃)已从候选剔除, "
        "本次推荐不会出现: " + "、".join(names)
    )


def _profile_block(
    profile: dict,
    root: "Path | None" = None,
    l1_prefs_override: Any = _UNSET_L1_PREFS,
) -> str:
    """构造 [PROFILE] 段. D-072: 注入 methodology display_name + rationale 摘要,
    替代之前 L3 prompt 隐式靠 taste_description 传方法论, 防 L2/L3 描述漂移.

    D-078.2: 注入 L1 LLM 抽取的行为信号 (boost/penalty + evidence 简述), 让 L3
    LLM 显式看到 long_term_prefs.json — 否则 L1 只到 L2 打分顺序, L3 LLM 无从
    知道 top60 里哪些 combo 是因 L1 boost 被排前. 演练实测: 4/4 oil=too_high
    抽出 boost=['low_oil'] 后 L3 仍可能挑高油 combo, 因为 prompt 没透出信号.

    D-079 BLOCKER fix: l1_prefs_override 传入 (非 sentinel) 时用 override 而非
    runtime load. What-if frozen replay 必须走这条路径, 否则 _profile_block 会
    `load_prefs(root)` 读 live disk, 违反 D-079 "What-if 零 runtime read" 红线.

    spec 缺失 (老 profile 没 load_profile 一致路径) 时回退老格式 (向后兼容).
    """
    prefs = profile.get("preferences", {}) or {}
    lines = ["[PROFILE]"]
    spec = profile.get("_methodology_spec")
    if isinstance(spec, dict):
        display = spec.get("display_name") or spec.get("name") or "(未命名)"
        # rationale 第一行段作为摘要 (节省 token)
        rationale = (spec.get("rationale") or "").strip()
        summary = rationale.split("\n", 1)[0].strip() if rationale else "(无)"
        lines.append(f"方法论: {display} — {summary}")
    lines.extend([
        f"口味描述: {profile.get('taste_description','') or '(空)'}",
        f"喜欢: {_fmt_list_or_none(prefs.get('liked_cuisines'))}",
        f"不喜欢: {_fmt_list_or_none(prefs.get('disliked_cuisines'))}",
        f"avoid: {_fmt_list_or_none(prefs.get('avoid_dishes'))}",
        f"辣度耐受: {prefs.get('spicy_tolerance', 2)}",
    ])
    # D-078.2: L1 行为信号
    try:
        if l1_prefs_override is _UNSET_L1_PREFS:
            from chisha.l1_prefs import load_prefs
            l1 = load_prefs(root=root)
        else:
            l1 = l1_prefs_override
        if l1 and (l1.get("boost") or l1.get("penalty")):
            n_meals = l1.get("based_on_meals", 0)
            evid = l1.get("evidence") or []
            # 取第一条 evidence rationale 作为依据简述 (节省 token)
            rationale = evid[0].get("rationale") if evid else ""
            sig_parts = []
            if l1.get("boost"):
                sig_parts.append(f"boost={l1['boost']}")
            if l1.get("penalty"):
                sig_parts.append(f"penalty={l1['penalty']}")
            sig_line = f"行为信号 (近 {n_meals} 餐): " + " ".join(sig_parts)
            if rationale:
                sig_line += f" — {rationale[:80]}"
            lines.append(sig_line)
    except Exception:
        pass
    return "\n".join(lines)


def _context_block(context: "ContextSnapshot | None") -> str:
    if context is None:
        return "[CONTEXT] null"
    cd = context.to_llm_dict()
    # 上顿摘要: 取 cuisine + dishes 数, 不全展开
    last_meal = cd.get("last_meal") or {}
    if last_meal:
        d = last_meal.get("dishes") or []
        names = "+".join((x.get("canonical_name") or "?") for x in d[:3])
        last_meal_brief = (
            f"{last_meal.get('meal_type','?')} {last_meal.get('cuisine','')}: {names}"
        )
    else:
        last_meal_brief = "(无)"
    recent = cd.get("recent_3d_cuisines") or {}
    methods_3d = cd.get("recent_3d_cooking_methods") or {}
    last_fb = cd.get("last_feedback") or {}
    chips = last_fb.get("chips") if isinstance(last_fb, dict) else None
    lines = [
        "[CONTEXT]",
        f"饭期: {cd.get('meal_type')}",
        f"心情: {cd.get('daily_mood') or '(无)'}",
        f"上顿: {last_meal_brief}",
        f"最近 3 天 cuisine: {_fmt_counts_or_none(recent)}",
        f"最近 3 天 cooking: {_fmt_counts_or_none(methods_3d)}",
        f"上次反馈 chips: {chips or '(无)'}",
        f"refine 输入: {cd.get('refine_input') or '(无)'}",
    ]
    # D-094.1: 结构化意图段 (refine 二轮才有) — V2 shape:
    # redirect / constrain / reference / reject_previous / raw_understanding.
    intent = cd.get("refine_intent")
    if intent:
        parts: list[str] = []
        redirect = intent.get("redirect") or {}
        for k, v in redirect.items():
            if v:
                parts.append(f"{k}={v}")
        constrain = intent.get("constrain") or {}
        for k, v in constrain.items():
            if v not in (None, False, [], "", {}):
                parts.append(f"{k}={v}")
        if intent.get("reference"):
            parts.append(f"reference={intent['reference']}")
        if intent.get("reject_previous"):
            parts.append("reject_previous=true")
        ru = (intent.get("raw_understanding") or "").strip()
        if parts:
            lines.append(f"refine 意图 (结构化): {'; '.join(parts)}")
        if ru:
            lines.append(f"refine 自述理解: {ru}")
    return "\n".join(lines)


def build_user_message(
    top_combos: list[dict],
    profile: dict,
    context: "ContextSnapshot | None",
    n: int,
    n_explore: int,
    root: "Path | None" = None,
    l1_prefs_override: Any = _UNSET_L1_PREFS,
    feedback_avoided_names: list[str] | None = None,
) -> str:
    """拼 user message: CONFIG + PROFILE + CONTEXT + [FEEDBACK_AVOIDED] + CANDIDATES.

    D-078.2: root 透传给 _profile_block 注入 L1 prefs.
    D-079 BLOCKER fix: l1_prefs_override 透传, What-if 路径必须走 frozen 而非
    runtime load (违反 "What-if 零 runtime read" 红线).
    B-001/D-098 (T-FB-05): feedback_avoided_names (api/refine 算好的本 zone 真剔除
    店名) → [FEEDBACK_AVOIDED] 段 (D-085 忠实纪律, 只列真剔除的).
    """
    blocks = [
        f"[CONFIG] n={n} n_explore={n_explore}",
        _profile_block(profile, root=root, l1_prefs_override=l1_prefs_override),
        _context_block(context),
    ]
    avoided = _feedback_avoided_block(feedback_avoided_names)
    if avoided:
        blocks.append(avoided)
    blocks.append("[CANDIDATES]")
    for idx, c in enumerate(top_combos):
        blocks.append(_fmt_combo_block(idx, c))
    return "\n\n".join(blocks)


def build_payload(
    top_combos: list[dict],
    profile: dict,
    context: "ContextSnapshot | None",
    meal_log: list[dict] | None,
    n: int,
    n_explore: int,
) -> dict:
    """打包 LLM rerank 输入 (legacy JSON 形态, 主要给 debug trace 用).

    D-046: 实际给 LLM 的是 build_user_message() 的紧凑文本. 本函数保留是为了
    debug_recommend trace 兼容 + 单测断言. 字段集和 V2 保持一致.
    """
    candidates = []
    for idx, c in enumerate(top_combos):
        rest = c.get("restaurant", {})
        candidates.append({
            "combo_index": idx,
            "restaurant": {
                "name": rest.get("name", ""),
                "cuisine": rest.get("category", ""),
                "distance_m": rest.get("distance_m", -1),
                "eta_min": rest.get("delivery_eta_min", -1),
            },
            "dishes": [
                {
                    "canonical_name": d.get("canonical_name", ""),
                    "cuisine": d.get("cuisine", ""),
                    "price": d.get("price", 0),
                    "main_ingredient_type":
                        d["nutrition_profile"].get("main_ingredient_type", ""),
                    "cooking_method":
                        d["nutrition_profile"].get("cooking_method", ""),
                    "oil_level": d["nutrition_profile"].get("oil_level", 3),
                    "spicy_level": d["nutrition_profile"].get("spicy_level", 0),
                    "dish_role": d["nutrition_profile"].get("dish_role"),
                    "processed_meat_flag":
                        d["nutrition_profile"].get("processed_meat_flag", False),
                    "sweet_sauce_level":
                        d["nutrition_profile"].get("sweet_sauce_level"),
                    "wetness": d["nutrition_profile"].get("wetness"),
                    "grain_type": d["nutrition_profile"].get("grain_type"),
                }
                for d in c.get("dishes", [])
            ],
            "total_price": sum(
                (d.get("price") or 0) for d in c.get("dishes", [])
            ),
            "score": round(c.get("score", 0), 3),
        })

    payload: dict[str, Any] = {
        "config": {"n": n, "n_explore": n_explore},
        "profile": {
            "taste_description": profile.get("taste_description", ""),
            "liked_cuisines": profile["preferences"].get("liked_cuisines", []),
            "disliked_cuisines": profile["preferences"].get("disliked_cuisines", []),
            "avoid_dishes": profile["preferences"].get("avoid_dishes", []),
            "spicy_tolerance": profile["preferences"].get("spicy_tolerance", 2),
        },
        "context": context.to_llm_dict() if context else None,
        "candidates": candidates,
    }
    return payload


# ═══════════════════════ D-102 Step1: FallbackPlan (统一兜底契约) ═══════════
# 病根 (提案 §病根): web 与 cli 两形态靠"手工把状态穿进各自的调用"而非"核心拥有
# 并打包状态" → meal_log 在 cli 兜底路径漏传, explore 段丢失"避开最近吃过"偏置.
# FallbackPlan 把兜底判定所需的全部状态打成一个对象, build_fallback_plan 是唯一
# 构造入口 (meal_log 关键字必填), 两条链路共用 → adapter 物理上漏不掉/改不动状态.

# 兜底策略版本: blob 跨进程 (cli resolve→apply) 复用时的兼容闸门. 策略算法变 → bump,
# 旧 blob fail-loud (D-100 无 grandfather). 也供 §已知坑 5 可复现性追溯.
FALLBACK_STRATEGY_VERSION = 1


@dataclass
class FallbackPlan:
    """核心打包的兜底状态快照 — adapter 执行 (execute) 但不能漏传/改写 (D-102 Step1).

    封装规则兜底判定所需的全部状态: 候选集 + meal_log 只读快照 + 策略参数 + version.
    - in-process (web/refine/what-if): 同进程 build → execute, 不落盘.
    - cross-process (cli): resolve 时 to_blob 冻结进 round (D-098 单次构建/零 runtime
      re-read 范式), apply 时 from_blob 重建并 execute. 候选集走共享 top_k 不重复序列化.
    """
    top_combos: list[dict]
    meal_log: list[dict]            # 只读快照 (None 视同空历史, _pick_explore 内 `or []`)
    n: int
    n_explore: int
    today: "dt.date | None" = None
    version: int = FALLBACK_STRATEGY_VERSION

    def execute(self) -> list[dict[str, Any]]:
        """跑规则兜底. 全部状态来自 plan, 调用方无从漏传 meal_log."""
        return fallback_rerank(
            self.top_combos, n=self.n, n_explore=self.n_explore,
            meal_log=self.meal_log, today=self.today,
        )

    def to_blob(self) -> dict:
        """cli 跨进程持久化 (resolve→apply) 的**兜底专属**状态: meal_log 只读快照 + version.

        单源纪律 (D-102.1 Codex commit review): 候选集走 round 共享 `top_k`、`n/n_explore/
        today` 走 round `frozen` —— 它们各自只有一处权威源, **不在此重复序列化** (防两份
        漂移). from_blob 重建时由调用方从那些单源回传. version 仅闸守 meal_log 快照格式.
        """
        return {
            "meal_log": self.meal_log,
            "version": self.version,
        }

    @classmethod
    def from_blob(
        cls, blob: Any, *, top_combos: list[dict],
        n: int, n_explore: int, today: "dt.date | None",
    ) -> "FallbackPlan":
        """从持久化 blob (meal_log 快照) + 共享单源 (top_combos/n/n_explore/today) 重建.

        blob 缺失/无 meal_log/版本不符 → fail-loud (D-100 无 grandfather): in-flight
        round 不向后兼容, 旧 round 跨 D-102 升级需重 start. n/n_explore/today 来自 round
        frozen 单源 (非 blob), 故不会 KeyError、也无双持久化漂移.
        """
        if not isinstance(blob, dict) or "meal_log" not in blob:
            raise ValueError(
                "FallbackPlan blob 缺失或无 meal_log 快照 "
                "(旧 in-flight round 跨 D-102 升级?). 该轮不可兜底, 请重新 start 一轮."
            )
        ver = blob.get("version")
        if ver != FALLBACK_STRATEGY_VERSION:
            raise ValueError(
                f"FallbackPlan blob version {ver!r} != {FALLBACK_STRATEGY_VERSION} "
                "(兜底策略已变), 该轮快照失效, 请重新 start 一轮."
            )
        return cls(
            top_combos=top_combos, meal_log=blob["meal_log"],
            n=n, n_explore=n_explore, today=today, version=ver,
        )


def build_fallback_plan(
    top_combos: list[dict],
    *,
    meal_log: list[dict] | None,
    n: int,
    n_explore: int,
    today: "dt.date | None" = None,
) -> FallbackPlan:
    """唯一 FallbackPlan 构造入口 (meal_log 关键字**必填**, None 视同空历史).

    web / cli / what-if 三条链路都经此构造 → 没人能在调用点"忘记穿 meal_log"
    (病根: 默认 None 的隐式漏传). 持有=打包, 执行交 .execute().
    """
    return FallbackPlan(
        top_combos=top_combos, meal_log=meal_log if meal_log is not None else [],
        n=n, n_explore=n_explore, today=today,
    )


def fallback_rerank(
    top_combos: list[dict],
    n: int = 5,
    *,
    meal_log: list[dict] | None,
    today: "dt.date | None" = None,
    n_explore: int = 2,
) -> list[dict[str, Any]]:
    """规则 fallback: 取打分 top (n - n_explore) 当 exploit (品牌+菜系多样性去重),
    在剩余里挑"最近未吃过的菜系/做法"做 explore.
    每条用最简结构化字段填占位, 不调 LLM.

    D-102 Step1: meal_log 改**关键字必填** (无默认) — 拔掉"默认 None 隐式漏传"温床
    (提案 §病根). 生产路径一律经 build_fallback_plan/FallbackPlan 构造; 直调本函数
    (单测/debug) 必须显式传 meal_log (空历史传 []).
    """
    if not top_combos:
        return []
    # D-079 followup: 给 combo 补 combo_index = 在 top_combos 里的位置. LLM 主路径
    # 由 schema 强制 combo_index ∈ [0, len(top_combos)), fallback / What-if rehydrate
    # 路径之前没填 → final[].combo_index 全是 -1 → 前端 adapter 生成 cmb_000 5 行重
    # 复 React key (PR-3 已修, 这里是源头补字段). setdefault 不覆盖既有值.
    for _i, _c in enumerate(top_combos):
        _c.setdefault("combo_index", _i)
    from chisha.score import diversify_top
    n_exploit = max(1, n - n_explore)
    # D-049: max_per_brand=1 — fallback 路径不走 _enforce_brand_unique,
    # 输出口径与 LLM 主路径 enforce 后保持一致 (同品牌至多 1 条).
    exploit = diversify_top(top_combos, n=n_exploit, max_per_brand=1,
                             max_per_cuisine=2)
    used_ids = {id(c) for c in exploit}
    rest = [c for c in top_combos if id(c) not in used_ids]
    if rest and n_explore > 0:
        explore = _pick_explore(rest, exploit, meal_log or [], n_explore, today=today)
    else:
        explore = []

    out: list[dict] = []
    rank = 1
    for c in exploit:
        out.append(_to_rerank_dict(c, rank, is_explore=False, fit_score=c.get("score", 0)))
        rank += 1
    for c in explore:
        out.append(_to_rerank_dict(c, rank, is_explore=True, fit_score=c.get("score", 0) * 0.8))
        rank += 1
    return out


def _pick_explore(
    rest: list[dict],
    already_used: list[dict],
    meal_log: list[dict],
    n_explore: int,
    *,
    today: "dt.date | None" = None,
) -> list[dict]:
    """explore 候选: 优先打分中段 + 最近 7 天没吃过的 cuisine/cooking_method.

    D-079 (Codex Q3): today 显式注入支持 What-if frozen replay. None=向后兼容
    用 wall clock dt.date.today(), 生产链路保持 0 行为变化.
    """
    import datetime as dt2
    today = today or dt2.date.today()
    cutoff = today - dt2.timedelta(days=7)
    used_cuisines: set[str] = set()
    used_methods: set[str] = set()
    for log in meal_log:
        ts_str = log.get("timestamp", "")
        try:
            d = dt2.date.fromisoformat(ts_str[:10])
        except ValueError:
            continue
        if d < cutoff:
            continue
        for x in log.get("dishes", []):
            if x.get("cuisine"):
                used_cuisines.add(x["cuisine"])
            if x.get("main_ingredient_type"):
                pass
    for c in already_used:
        for d in c.get("dishes", []):
            if d.get("cuisine"):
                used_cuisines.add(d["cuisine"])
            if (d.get("nutrition_profile") or {}).get("cooking_method"):
                used_methods.add(d["nutrition_profile"]["cooking_method"])

    mid_end = max(n_explore, len(rest) // 2)
    mid_pool = rest[:mid_end]
    novel: list[dict] = []
    for c in mid_pool:
        cuisines = {d.get("cuisine", "") for d in c.get("dishes", [])
                     if d.get("cuisine")}
        methods = {(d.get("nutrition_profile") or {}).get("cooking_method", "")
                    for d in c.get("dishes", [])}
        if (cuisines - used_cuisines) or (methods - used_methods):
            novel.append(c)
            if len(novel) >= n_explore:
                break
    if len(novel) < n_explore:
        for c in mid_pool:
            if c not in novel:
                novel.append(c)
                if len(novel) >= n_explore:
                    break
    return novel[:n_explore]


# ─────────────────────── 健康字段规则计算 (D-046) ───────────────────────


def _compute_health_flags(combo: dict) -> dict:
    """从 combo 的菜品字段规则化算 health_flags. LLM 不再算这个.

    必填子键 (与历史对外字段兼容):
        veg_ok / protein_ok / oil_ok / processed_meat / sweet_sauce / wetness
    """
    dishes = combo.get("dishes", []) or []
    veg_ok = any(
        (d.get("nutrition_profile") or {}).get("vegetable_ratio_estimate", 0) >= 0.6
        or (d.get("nutrition_profile") or {}).get("main_ingredient_type") == "纯素"
        for d in dishes
    )
    total_p = sum(
        (d.get("nutrition_profile") or {}).get("protein_grams_estimate", 0)
        for d in dishes
    )
    avg_oil = (
        sum((d.get("nutrition_profile") or {}).get("oil_level", 3) for d in dishes)
        / max(1, len(dishes))
    )
    has_processed = any(
        (d.get("nutrition_profile") or {}).get("processed_meat_flag")
        for d in dishes
    )
    has_wet = any(
        _safe_int((d.get("nutrition_profile") or {}).get("wetness"), 1) >= 3
        for d in dishes
    )
    sweet = any(
        _safe_int((d.get("nutrition_profile") or {}).get("sweet_sauce_level"), 0) >= 3
        for d in dishes
    )
    return {
        "veg_ok": veg_ok,
        "protein_ok": total_p >= 25,
        "oil_ok": avg_oil <= 3,
        "processed_meat": has_processed,
        "sweet_sauce": sweet,
        "wetness": has_wet,
    }


def _to_rerank_dict(combo: dict, rank: int, is_explore: bool,
                    fit_score: float) -> dict[str, Any]:
    """combo + meta → rerank 输出 dict (规则 fallback 用)."""
    flags = _compute_health_flags(combo)
    dishes = combo.get("dishes", []) or []
    total_p = sum(
        (d.get("nutrition_profile") or {}).get("protein_grams_estimate", 0)
        for d in dishes
    )
    avg_oil = (
        sum((d.get("nutrition_profile") or {}).get("oil_level", 3) for d in dishes)
        / max(1, len(dishes))
    )
    return {
        **combo,
        "rank": rank,
        "is_explore": is_explore,
        "combo_index": combo.get("combo_index", -1),
        "fit_score": round(float(fit_score), 3),
        "health_flags": flags,
        "taste_match": None,        # rule fallback 不做语义匹配
        "risk_flags": [],
        "one_line_reason": _rule_reason(combo, flags["wetness"], avg_oil, total_p),
    }


def _safe_int(v, default: int) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _rule_reason(combo: dict, has_wet: bool, avg_oil: float, total_p: float) -> str:
    bits = []
    if has_wet:
        bits.append("汤水清爽")
    if avg_oil <= 2:
        bits.append(f"低油{avg_oil:.1f}")
    if total_p >= 30:
        bits.append(f"蛋白{int(total_p)}g")
    elif total_p >= 25:
        bits.append("蛋白达标")
    if not bits:
        bits.append("结构合规")
    return "，".join(bits)[:30]


def _validate_llm_candidates_v(
    cands: list, n_max: int,
    input_size: int | None = None,
    n_explore_expected: int | None = None,
) -> tuple[list[dict] | None, str, str | None]:
    """D-047: 同 _validate_llm_candidates 但返回 (cands, code, detail) 三元组.

    D-049 (Codex review): 加 code (RerankValidationCode), retry 路由按 code 走,
    detail 保留人类可读中文供 trace / fallback_reason 显示. 文案改动不会静默
    漏触发 retry.

    返回:
      - 成功: (validated_cands, RerankValidationCode.OK, None)
      - 失败: (None, RerankValidationCode.<具体码>, "具体描述")
    """
    res = _validate_llm_candidates(cands, n_max=n_max,
                                    input_size=input_size,
                                    n_explore_expected=n_explore_expected)
    if res is None:
        # 重跑一次拿具体原因. 不重复实现是为了让单一 source-of-truth.
        # 简易方案: 记录 stdout 的 print, 但太复杂; 直接重做关键检查的字符串描述.
        code, detail = _diagnose_candidates(cands, n_max, input_size, n_explore_expected)
        return None, code, detail
    # T-PR-05: 加 rank == array position + 1 invariant (low-level _validate_llm_candidates
    # 仅校验 set 完整, 不校验 position 关系; permuted [2,1,3,4,5] 会通过低层校验).
    for idx, c in enumerate(res):
        if c.get("rank") != idx + 1:
            return (
                None,
                RerankValidationCode.RANK_POSITION_MISMATCH,
                f"candidates[{idx}].rank={c.get('rank')}, expected {idx+1}",
            )
    return res, RerankValidationCode.OK, None


def _diagnose_candidates(
    cands: list, n_max: int,
    input_size: int | None,
    n_explore_expected: int | None,
) -> tuple[str, str]:
    """重做 _validate_llm_candidates 的关键检查, 返回 (code, detail) 元组.

    D-049: 改返回 (code, detail). code 是 RerankValidationCode 之一 (稳定标识符),
    detail 仍是中文人类可读描述 (trace / fallback_reason 显示用).
    """
    V = RerankValidationCode
    if not isinstance(cands, list):
        return V.NOT_LIST, f"cands 非 list ({type(cands).__name__})"
    if not cands:
        return V.EMPTY, "cands 为空"
    if len(cands) > n_max:
        return V.OVER_N_MAX, f"返回 {len(cands)} > n_max={n_max}"
    seen_idx: set[int] = set()
    for i, c in enumerate(cands):
        if not isinstance(c, dict):
            return V.ITEM_NOT_DICT, f"#{i} 非 dict"
        missing = _REQUIRED_FIELDS - set(c)
        if missing:
            return V.MISSING_FIELDS, f"#{i} 缺字段 {sorted(missing)}"
        idx = c.get("combo_index")
        if not isinstance(idx, int) or idx < 0:
            return V.INVALID_INDEX, f"#{i} combo_index 非法 {idx!r}"
        if input_size is not None and idx >= input_size:
            return V.INDEX_OUT_OF_RANGE, f"#{i} combo_index 越界 {idx} >= {input_size}"
        if idx in seen_idx:
            return V.INDEX_DUPLICATE, f"#{i} combo_index 重复 {idx}"
        seen_idx.add(idx)
        fs = c.get("fit_score")
        if not isinstance(fs, (int, float)) or not (0.0 <= float(fs) <= 1.0):
            return V.INVALID_FIT_SCORE, f"#{i} fit_score 越界 {fs!r}"
        tm = c.get("taste_match")
        if tm is not None and (not isinstance(tm, (int, float))
                               or not (0.0 <= float(tm) <= 1.0)):
            return V.INVALID_TASTE_MATCH, f"#{i} taste_match 越界 {tm!r}"
        if not isinstance(c.get("is_explore"), bool):
            return V.INVALID_IS_EXPLORE, f"#{i} is_explore 非 bool"
        if not isinstance(c.get("risk_flags"), list):
            return V.INVALID_RISK_FLAGS, f"#{i} risk_flags 非 list"
    ranks = sorted(c["rank"] for c in cands if isinstance(c.get("rank"), int))
    if ranks != list(range(1, len(cands) + 1)):
        return V.RANK_NOT_SEQUENTIAL, f"rank 不连续 {ranks}"
    if n_explore_expected is not None:
        n_e = sum(1 for c in cands if c.get("is_explore"))
        if n_e != n_explore_expected:
            return V.EXPLORE_COUNT_MISMATCH, (
                f"explore 数量 {n_e} != 期望 {n_explore_expected}"
            )
        for i, c in enumerate(cands):
            expected_e = i >= (len(cands) - n_explore_expected)
            if bool(c.get("is_explore")) != expected_e:
                return V.EXPLORE_POSITION_WRONG, (
                    f"#{i} is_explore={c.get('is_explore')} 应为 {expected_e}"
                )
    return V.UNKNOWN, "未知 (validate 拒绝但 diagnose 通过, 检查代码漂移)"


def _validate_llm_candidates(
    cands: list, n_max: int,
    input_size: int | None = None,
    n_explore_expected: int | None = None,
) -> list[dict] | None:
    """LLM 输出深度校验. 任何错误返回 None 让上游 fallback.

    D-046 二审补强 (真 Codex review):
    - 加 combo_index 上界校验 (input_size 传入时), 防越界 idx 静默被丢然后规则补位
    - 加 n_explore 数量校验 (n_explore_expected 传入时), 防 LLM 漏写或多写 explore
    - 加 一坨 candidates 总数 == n_max 校验 (n_max 是期望输出数)

    检查:
    - 必填字段 (_REQUIRED_FIELDS, 不含 health_flags)
    - fit_score / taste_match 0-1 数值
    - rank 连续 1..len
    - combo_index 不重复, 0 <= idx < input_size
    - is_explore bool, exploit 段在前 explore 段在后
    - 数量 <= n_max; explore 数量 == n_explore_expected (若传入)
    """
    if not isinstance(cands, list) or not cands:
        return None
    if len(cands) > n_max:
        print(f"  [rerank] LLM 返回 {len(cands)} > n_max={n_max}, 截断")
        cands = cands[:n_max]
    seen_idx: set[int] = set()
    for i, c in enumerate(cands):
        if not isinstance(c, dict):
            return None
        missing = _REQUIRED_FIELDS - set(c)
        if missing:
            print(f"  [rerank] candidate#{i} 缺字段 {missing}")
            return None
        idx = c.get("combo_index")
        if not isinstance(idx, int) or idx < 0:
            print(f"  [rerank] candidate#{i} combo_index 非法: {idx!r}")
            return None
        # D-046 二审: idx 上界校验
        if input_size is not None and idx >= input_size:
            print(f"  [rerank] candidate#{i} combo_index 越界: "
                  f"{idx} >= input_size {input_size}")
            return None
        if idx in seen_idx:
            print(f"  [rerank] candidate#{i} combo_index 重复: {idx}")
            return None
        seen_idx.add(idx)
        fs = c.get("fit_score")
        if not isinstance(fs, (int, float)) or not (0.0 <= float(fs) <= 1.0):
            print(f"  [rerank] candidate#{i} fit_score 越界: {fs!r}")
            return None
        tm = c.get("taste_match")
        # taste_match 允许 None (兼容), 否则必须 0-1
        if tm is not None and (
            not isinstance(tm, (int, float)) or not (0.0 <= float(tm) <= 1.0)
        ):
            print(f"  [rerank] candidate#{i} taste_match 越界: {tm!r}")
            return None
        if not isinstance(c.get("is_explore"), bool):
            return None
        if not isinstance(c.get("risk_flags"), list):
            return None
    ranks = sorted(c["rank"] for c in cands if isinstance(c.get("rank"), int))
    if ranks != list(range(1, len(cands) + 1)):
        print(f"  [rerank] rank 不连续: {ranks}")
        return None
    # D-046 二审: explore 数量校验
    if n_explore_expected is not None:
        n_explore_actual = sum(1 for c in cands if c.get("is_explore"))
        if n_explore_actual != n_explore_expected:
            print(f"  [rerank] explore 数量错误: 期望 {n_explore_expected}, "
                  f"实际 {n_explore_actual}")
            return None
        # exploit 段在前, explore 段在后
        for i, c in enumerate(cands):
            expected_explore = i >= (len(cands) - n_explore_expected)
            if bool(c.get("is_explore")) != expected_explore:
                print(f"  [rerank] candidate#{i} (rank={c.get('rank')}) "
                      f"is_explore={c.get('is_explore')} 但应该是 "
                      f"{expected_explore} (exploit 在前 explore 在后)")
                return None
    return cands


def _run_llm_rerank(
    top_combos: list[dict],
    profile: dict,
    context: "ContextSnapshot | None",
    *,
    n: int,
    n_explore: int,
    n_max: int = 5,
    model: str | None = None,
    profile_llm: dict | None = None,
    root: "Path | None" = None,
    l1_prefs_override: Any = _UNSET_L1_PREFS,
    feedback_avoided_names: list[str] | None = None,
) -> dict:
    """共享 LLM rerank 调用 helper (D-047 抽出, 同时给 prod _llm_rerank +
    debug _llm_rerank_traced 用, 解决双份代码漂移问题).

    返回 trace dict, 字段:
      - status: "ok" | "fallback"
      - fallback_reason: 仅 fallback 时填, 描述具体原因
      - candidates: 仅 ok 时填, 校验后的 list[dict]
      - llm_response: 完整 call_text 返回 (debug 用)
      - system_prompt_chars / user_message_chars / user_message_full
      - model: 实际使用的 model
      - latency_ms: 测量值

    D-047: 用 tool_use forced schema 强制结构化输出, 完全替代 D-046.1 的
    json_mode + regex 提取路径. 必断言 stop_reason in {"tool_use","tool_calls"}
    防止 LLM 不调 tool 直接 stop.
    """
    import time
    # D-047 merge 修复: 按 resolved provider 选默认 rerank model, 保留
    # profile.llm.model.<provider> 覆盖能力. 见 docs/archive/DECISIONS_phase0.md D-047 Part B.
    from chisha.llm_client import _resolve_model, _resolve_provider, call_text

    # D-048 BLOCKER (Codex): provider 配置错误 (CHISHA_LLM_PROVIDER=foo /
    # profile.llm.provider=anthropic 但缺 key) 必须 hard-fail, 不能被下方
    # except Exception 吞成静默 L2 fallback. 调用方应当看到 status=="config_error"
    # 并向用户报清楚原因, 而不是收到伪装的 fallback 结果.
    try:
        resolved_provider: str | None = _resolve_provider(profile_llm)
    except (RuntimeError, ValueError) as e:
        return {
            "status": "config_error",
            "config_error": True,
            "resolved_provider": None,
            "fallback_reason": f"LLM provider 配置错误: {type(e).__name__}: {str(e)[:200]}",
            "candidates": None,
            "llm_response": None,
            "system_prompt_chars": 0,
            "user_message_chars": 0,
            "user_message_full": "",
            "model": None,
            "latency_ms": None,
        }

    if model:
        # 显式 model 入参最高优先级
        final_model: str | None = model
    elif (
        profile_llm
        and resolved_provider
        and (profile_llm.get("model") or {}).get(resolved_provider)
    ):
        # profile.llm.model.<provider> 显式配置时, 透传 None 让 call_text 用 profile
        final_model = None
    else:
        final_model = _RERANK_MODEL_BY_PROVIDER.get(
            resolved_provider, _DEFAULT_RERANK_MODEL
        )

    # trace.model 显示真实生效 model (D-048: 不再用 _RERANK_MODEL_BY_PROVIDER
    # 默认值兜底, 那会让 profile 配 sonnet 但 trace 显示 opus). 调用前先算
    # expected_trace_model, 调用后用 llm_response.model 覆盖为 provider 实际报告值.
    expected_trace_model = _resolve_model(resolved_provider, final_model,
                                          profile_llm) or _RERANK_MODEL_BY_PROVIDER.get(
        resolved_provider, _DEFAULT_RERANK_MODEL
    )

    out: dict[str, Any] = {
        "status": "fallback",
        "config_error": False,
        "resolved_provider": resolved_provider,
        "fallback_reason": None,
        "candidates": None,
        "llm_response": None,
        "system_prompt_chars": 0,
        # D-089-S1: system_prompt body 必须落 trace (self-contained 原则).
        # 仅 chars 让 trace 无法 replay (prompts/rerank_system.md 会迭代).
        "system_prompt_full": "",
        "user_message_chars": 0,
        "user_message_full": "",
        # D-089-S1: raw_response 是 provider 返回的 raw text — tool_use 路径用
        # tool_input arguments JSON 字符串, text 路径用 content text. trace_helpers
        # serialize_llm_call_trace 据此算 raw_response_chars.
        "raw_response": "",
        "model": expected_trace_model,
        "latency_ms": None,
        # D-079 followup: 把 LLM 实际 usage/温度/上限 stash 到 out, 让 trace 能落
        # input_tokens / cache_read 给 DagHeader 算 cache_hit%. 真值在 call_text
        # 返回后填 (out["usage"]/max_tokens/temperature 见 line 1013 附近).
        "usage": None,
        "max_tokens": None,
        "temperature": None,
        # D-089-S1: 业务校验失败时填 list[str], 否则 None
        "validator_errors": None,
    }
    is_cli = (resolved_provider == "claude_code_cli")
    try:
        system_prompt_raw = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
        if is_cli:
            # CLI 路径不走 tool_use, 把 "# 输出方式" 段替换成"直接输出 JSON"
            system_prompt = _patch_system_prompt_for_cli(system_prompt_raw)
        else:
            system_prompt = system_prompt_raw
        user_msg = build_user_message(top_combos, profile, context,
                                       n=n, n_explore=n_explore, root=root,
                                       l1_prefs_override=l1_prefs_override,
                                       feedback_avoided_names=feedback_avoided_names)
        # D-089-S1: 落实际发给 LLM 的 system prompt body (patch 过的 CLI 版 / 主路径 raw 版).
        # T-PR-05: 主路径 tool_use 把 ordering 等行为关键指令搬进 _RERANK_TOOL.description,
        # 为 D-079 trace 自包含原则 (CONTRACTS.md:115), 把 outgoing tool schema 拼到
        # system_prompt_full value 末尾作为 reference 块. 不引入新 schema 字段, 不 bump
        # TRACE_SCHEMA_VERSION (字符串值扩展不算 schema 改). CLI 路径不走 tool_use, 不拼.
        if is_cli:
            out["system_prompt_full"] = system_prompt
        else:
            out["system_prompt_full"] = system_prompt + (
                "\n\n# === [TRACE REFERENCE] outgoing tool schema (T-PR-05) ===\n"
                + json.dumps(_RERANK_TOOL, ensure_ascii=False, indent=2)
            )
        # T-PR-05: chars 必须跟 full 同步 (test_rerank_trace_fields 守门: chars == len(full))
        out["system_prompt_chars"] = len(out["system_prompt_full"])
        out["user_message_chars"] = len(user_msg)
        out["user_message_full"] = user_msg
        kwargs: dict[str, Any] = {
            "model": final_model,
            # D-048 MAJOR 1 (Codex): CLI 路径 max_tokens 是 *假保护* — claude_code_cli
            # 不实际 cap CLI 子进程输出长度, 这里写 4096 只是占位/兼容签名. 真正
            # 兜底是 claude_code_cli.py:_DEFAULT_TIMEOUT (默认 180s) 超时. sonnet
            # inline CoT 失控时不会卡 max_tokens, 而是直到超时. timeout 触发后
            # _run_llm_rerank 的 except 会捕获 subprocess.TimeoutExpired,
            # fallback_reason 会标 TimeoutExpired:... 调用方可据此区分.
            "max_tokens": 4096 if is_cli else 2048,
            "temperature": 0.0,
            "system": system_prompt,
            "cache_system": True,
            "profile_llm": profile_llm,  # D-047: provider 路由
        }
        if not is_cli:
            kwargs["tools"] = [_RERANK_TOOL]
            kwargs["tool_choice"] = _RERANK_TOOL_CHOICE
        t0 = time.time()
        resp = call_text(user_msg, **kwargs)
        out["latency_ms"] = int((time.time() - t0) * 1000)
        out["llm_response"] = resp
        # D-079 followup: stash usage + max_tokens/temperature 到 trace, 让前端
        # DagHeader 能算 cache_hit% (input_tokens / cache_read_input_tokens 之比).
        # CLI 路径目前 resp 也带 usage (provider 透传), 没拿到就给 None.
        if isinstance(resp, dict):
            out["usage"] = resp.get("usage")
            # D-089-S1: raw_response — tool_use 路径用 raw_text (tool_input
            # arguments JSON 字符串), text 路径用 content. 让 trace 自包含,
            # debug-ui PanelL3 raw_response_blocks 能从 adapter.ts:264 合成 block.
            out["raw_response"] = (
                resp.get("raw_text")
                or resp.get("content")
                or ""
            )
            out["stop_reason"] = resp.get("stop_reason")
        out["max_tokens"] = kwargs.get("max_tokens")
        out["temperature"] = kwargs.get("temperature")
        # D-048: trace.model 用 provider 真实报告值覆盖 (expected_trace_model
        # 只是预测, llm_response.model 是 provider/CLI 真返回的, 更可信).
        if isinstance(resp, dict) and resp.get("model"):
            out["model"] = resp["model"]

        if is_cli:
            # CLI 路径: 解析 text 输出为 JSON 对象, 取 candidates 字段
            raw_text = resp.get("content") or resp.get("raw_text") or ""
            obj = _parse_json_object_from_text(raw_text)
            if obj is None:
                out["fallback_reason"] = (
                    f"CLI 输出无法解析为 JSON 对象 (前 120 字: {raw_text[:120]!r})"
                )
                return out
            cands = obj.get("candidates")
            if not isinstance(cands, list):
                out["fallback_reason"] = (
                    f"JSON 对象缺 candidates 数组: keys={list(obj.keys())}"
                )
                return out
            # T-P1b-02: 顶层 narrative 字段, 缺省回退空字符串 (旧 prompt 兼容)
            narrative = obj.get("narrative")
            if isinstance(narrative, str):
                out["narrative"] = narrative
        else:
            # D-048 MAJOR 5 (Codex): 强约束以 type=="tool_use" + tool_name 为准,
            # stop_reason 不作硬断言 (OR 在某些路由上对合法 tool_call 会返回
            # finish_reason="stop" 而非 "tool_calls"; Anthropic 直连一般是
            # "tool_use", OR OpenAI-compat 路径一般是 "tool_calls" 但非保证).
            # 真信号在结构化字段 type / tool_name / tool_input, 不在 stop string.
            if resp.get("type") != "tool_use":
                out["fallback_reason"] = (
                    f"LLM 未调 tool (type={resp.get('type')}, "
                    f"stop={resp.get('stop_reason')})"
                )
                return out

            if resp.get("tool_name") != _RERANK_TOOL["name"]:
                out["fallback_reason"] = (
                    f"LLM 调了错的 tool: {resp.get('tool_name')!r}"
                )
                return out

            tool_input = resp.get("tool_input")
            if not isinstance(tool_input, dict):
                out["fallback_reason"] = (
                    f"tool_input 非 dict: {type(tool_input).__name__}"
                )
                return out

            cands = tool_input.get("candidates")
            # T-P1b-02: 顶层 narrative (tool_use 路径), 缺省回退空字符串
            narrative = tool_input.get("narrative")
            if isinstance(narrative, str):
                out["narrative"] = narrative

        validated, code, detail = _validate_llm_candidates_v(
            cands, n_max=n_max,
            input_size=len(top_combos),
            n_explore_expected=n_explore,
        )
        # D-049 retry: 仅 CLI no-tool 路径 + 计数/位置类失败时一次性纠错.
        # CLI 是自用降级路径 (D-048 边界), 生产应走 anthropic/openrouter tool_use
        # 主路径 (forced schema 94% 成功率, 无需 retry).
        # 不 retry 的 case (按 RerankValidationCode): 解析失败 / 缺字段 / index
        # 越界等 -- opus 重答也不会变好, 直接 fallback 省 12s + $0.03.
        if validated is None and is_cli and code in _RETRY_TRIGGER_CODES:
            n_exploit_expected = n - n_explore
            cands_list = cands if isinstance(cands, list) else []
            n_e_actual = sum(
                1 for c in cands_list
                if isinstance(c, dict) and c.get("is_explore") is True
            )
            n_x_actual = sum(
                1 for c in cands_list
                if isinstance(c, dict) and c.get("is_explore") is False
            )
            # Codex review (Q3): correction prefix 显式要求"其余规则仍生效",
            # 防 retry 时 opus 降级为"只满足计数, 忽略 taste/health/avoid".
            # 不贴上次错误 JSON: 会把模型锁死在错误选择, 增加 minimal-edit 倾向.
            correction = (
                "\n\n# 上次输出校验失败 (一次性纠错, 严格按本节执行)\n\n"
                f"你刚才返回 {n_x_actual} 条 exploit (is_explore=false) + "
                f"{n_e_actual} 条 explore (is_explore=true), 共 "
                f"{len(cands_list)} 条.\n"
                f"要求: **正好** {n_exploit_expected} 条 exploit + "
                f"{n_explore} 条 explore = {n} 条, 不多不少.\n"
                f"重新挑: 前 {n_exploit_expected} 条 is_explore=false "
                "(从打分前段挑), 后 "
                f"{n_explore} 条 is_explore=true (从输入 [CANDIDATES] 中段 "
                "idx>=10 挑, 找不到漂亮中段就挑次优中段填满槽位, **不许减少 "
                "explore 数量**).\n"
                "**重要: 系统 prompt 里所有其余规则 (硬过滤 avoid/spicy/processed, "
                "口味命中, 健康风险披露 (不参与排序但要标 risk_flags), 同品牌择优, refine_input/mood 优先级等) "
                "全部仍然生效. 请基于原 [CANDIDATES] 重新挑 5 条, 不是改标签.**\n"
                "直接重新输出 JSON 对象, 不要任何前后说明文字.\n"
            )
            retry_user_msg = user_msg + correction
            t1 = time.time()
            resp2 = call_text(retry_user_msg, **kwargs)
            # latency 分两字段: 原始单次 + retry 单次, 不再累加. 调试台 / trace
            # 据此区分"首次 12s + retry 12s" vs "单次 24s 慢调用".
            out["retry_latency_ms"] = int((time.time() - t1) * 1000)
            out["llm_response_retry"] = resp2
            out["retry_attempted"] = True
            out["retry_first_failure_code"] = code
            raw2 = resp2.get("content") or resp2.get("raw_text") or ""
            obj2 = _parse_json_object_from_text(raw2)
            cands2 = obj2.get("candidates") if isinstance(obj2, dict) else None
            if isinstance(cands2, list):
                validated2, code2, detail2 = _validate_llm_candidates_v(
                    cands2, n_max=n_max,
                    input_size=len(top_combos),
                    n_explore_expected=n_explore,
                )
                if validated2 is not None:
                    out["status"] = "ok"
                    out["candidates"] = validated2
                    out["retry_succeeded"] = True
                    print(
                        f"  [rerank] retry 成功 (首次失败 code={code} detail={detail})"
                    )
                    return out
                detail = f"{detail} | retry 后仍失败 code={code2}: {detail2}"
            else:
                detail = f"{detail} | retry 解析失败"
        if validated is None:
            out["fallback_reason"] = (
                f"candidates 业务校验失败 [{code}]: {detail}"
            )
            return out

        out["status"] = "ok"
        out["candidates"] = validated
        return out
    except Exception as e:
        # D-089-S6: fallback_reason 截前 200 (vs 120) 让 OR 上游 error message 完整可读;
        # 同步 stderr 打 traceback 让 debug_server 日志能定位 None subscript 之类问题.
        out["fallback_reason"] = f"{type(e).__name__}: {str(e)[:200]}"
        import traceback
        print(f"[rerank fallback traceback]\n{traceback.format_exc()}", flush=True)
        return out


def _llm_rerank(top_combos: list[dict], profile: dict,
                context: "ContextSnapshot | None", n: int, n_explore: int,
                model: str | None = None,
                n_max: int = 5,
                root: "Path | None" = None,
                l1_prefs_override: Any = _UNSET_L1_PREFS,
                feedback_avoided_names: list[str] | None = None) -> list[dict] | None:
    """调 LLM 返回 list of candidate dict, 失败返回 None (上游 fallback).

    D-047: 走 _run_llm_rerank 共享 helper + tool_use 强制 schema.
    profile.llm 透传到 call_text 控制 provider 路由.
    D-078.2: root 透传给 build_user_message 注入 L1 prefs.
    D-079 BLOCKER fix: l1_prefs_override 透传到 _run_llm_rerank, What-if frozen
    路径用 snapshot 而非 load_prefs(root).
    """
    res = _run_llm_rerank(
        top_combos, profile, context,
        n=n, n_explore=n_explore, n_max=n_max, model=model,
        profile_llm=profile.get("llm"),
        root=root,
        l1_prefs_override=l1_prefs_override,
        feedback_avoided_names=feedback_avoided_names,
    )
    if res["status"] == "config_error":
        # D-048 BLOCKER: provider 配置错误显式 ERROR 级日志, 不当普通 fallback.
        # prod 路径仍 return None 让链路继续 (规则 fallback 保证管道不断),
        # 但 stderr 清晰标记区别于 transient 调用失败.
        print(f"  [rerank CONFIG ERROR] {res['fallback_reason']}", flush=True)
        return None
    if res["status"] != "ok":
        print(f"  [rerank fallback] {res['fallback_reason']}")
        return None
    return res["candidates"]


def rerank(
    top_combos: list[dict],
    profile: dict,
    context: "ContextSnapshot | None" = None,
    meal_log: list[dict] | None = None,
    n: int = 5,
    n_explore: int = 2,
    refine: bool = False,
    use_llm: bool | None = None,
    model: str | None = None,
    root: "Path | None" = None,
    *,
    today: "dt.date | None" = None,
    trace_collector: dict | None = None,
    l1_prefs_override: Any = _UNSET_L1_PREFS,
    feedback_avoided_names: list[str] | None = None,
) -> list[dict]:
    """主入口. LLM 精排 + fallback.

    Args:
        top_combos: 打分后已排序的 candidates (V2 默认 top40, D-046).
        profile / context / meal_log: 见 build_user_message.
        n: 输出候选数, 默认 5.
        n_explore: explore 候选数, 默认 2 (D-015).
        refine: True 时 n_explore=0 (D-015).
        use_llm: 强制开关. None=auto (看任何 provider 是否可用, D-047).
        root: 项目根 (D-078.2). 透传到 _profile_block 让 L3 LLM 显式看到
            L1 LLM 抽取的 long_term_prefs.json (boost/penalty + evidence).
        today: D-079, 透传给 fallback_rerank 防 wall-clock 漂移.
        trace_collector: D-079, 注入 dict 时把 L3 LLM 中间状态写入供 trace 持久化.
        l1_prefs_override: D-079 BLOCKER fix. 默认 _UNSET → _profile_block 走
            load_prefs(root) 原路径; 显式传 (包括 None) → 用 override, What-if
            frozen replay 必须传, 否则违反 "What-if 零 runtime read" 红线.
    """
    # D-079 Codex FIX-NOW #1: trace_collector 必须在所有 return 前填齐核心字段,
    # 避免 early-return / fallback / skipped 路径漏字段导致 UI/replay 失数据.
    # llm_attempted = "是否调过 LLM" (含失败); llm_called = "LLM 成功返回 candidates"
    def _ensure_collector_filled(
        status: str, attempted: bool, called: bool, used_fb: bool,
        reason: str = "",
    ) -> None:
        if trace_collector is None:
            return
        trace_collector.setdefault("status", status)
        trace_collector["llm_attempted"] = attempted
        trace_collector["llm_called"] = called
        trace_collector["used_fallback"] = used_fb
        if reason:
            trace_collector.setdefault("fallback_reason", reason)

    if not top_combos:
        _ensure_collector_filled("skipped", attempted=False, called=False,
                                  used_fb=False, reason="empty top_combos")
        return []
    if refine:
        n_explore = 0
    if use_llm is None:
        from chisha.llm_client import has_llm_key
        use_llm = has_llm_key()

    llm_attempted = False
    llm_called = False
    if use_llm:
        llm_attempted = True
        # D-079: 直接调 _run_llm_rerank 拿 res, 把中间状态写进 trace_collector
        if trace_collector is not None:
            res = _run_llm_rerank(
                top_combos, profile, context,
                n=n, n_explore=n_explore, n_max=n,
                model=model, profile_llm=profile.get("llm"),
                root=root,
                l1_prefs_override=l1_prefs_override,
                feedback_avoided_names=feedback_avoided_names,
            )
            llm_resp = res.get("llm_response") or {}
            # D-089-S1: raw_response 直接从 res (内部已统一: tool_use raw_text /
            # text content), 不再单独从 llm_resp 派生. trace 自包含原则.
            raw_response = res.get("raw_response", "")
            trace_collector["status"] = res.get("status")
            trace_collector["config_error"] = res.get("config_error", False)
            trace_collector["resolved_provider"] = res.get("resolved_provider")
            trace_collector["model"] = res.get("model")
            trace_collector["system_prompt_chars"] = res.get("system_prompt_chars")
            # D-089-S1: system_prompt body 必须落 trace (self-contained, 不靠
            # prompts/rerank_system.md 当前版本重建).
            trace_collector["system_prompt_full"] = res.get("system_prompt_full", "")
            trace_collector["user_message_chars"] = res.get("user_message_chars")
            trace_collector["user_message_full"] = res.get("user_message_full")
            trace_collector["raw_response"] = raw_response
            trace_collector["raw_response_chars"] = len(raw_response)
            trace_collector["tool_input"] = (
                llm_resp.get("tool_input") if isinstance(llm_resp, dict) else None
            )
            trace_collector["stop_reason"] = res.get("stop_reason") or (
                llm_resp.get("stop_reason") if isinstance(llm_resp, dict) else None
            )
            trace_collector["fallback_reason"] = res.get("fallback_reason")
            trace_collector["parsed_candidates"] = res.get("candidates")
            # T-P1b-02: narrative 落 trace, 旧 trace adapter 兼容缺字段
            trace_collector["narrative"] = res.get("narrative", "")
            # D-079 followup: 透传 latency/usage/sampling 进 trace, 让 DagHeader
            # 能渲染 L3 latency_ms / cache_hit% / token 概览; 旧 trace 这些字段
            # 仍是 None, adapter 已兜底.
            trace_collector["latency_ms"] = res.get("latency_ms")
            trace_collector["usage"] = res.get("usage")
            trace_collector["max_tokens"] = res.get("max_tokens")
            trace_collector["temperature"] = res.get("temperature")
            # D-089-S1: 业务校验失败时的 validator_errors (CLI retry / 主路径
            # tool_use 失败都会走 fallback_reason; validator_errors 是结构化版本,
            # 当前主链路尚未填; 留 hook 给后续扩展).
            trace_collector["validator_errors"] = res.get("validator_errors")
            # D-089-S1: retry 字段 (D-049 CLI 路径独有)
            trace_collector["retry_attempted"] = res.get("retry_attempted")
            trace_collector["retry_succeeded"] = res.get("retry_succeeded")
            trace_collector["retry_latency_ms"] = res.get("retry_latency_ms")
            trace_collector["retry_first_failure_code"] = res.get("retry_first_failure_code")
            if res.get("status") == "ok":
                llm_out = res.get("candidates")
                llm_called = True
            else:
                llm_out = None
        else:
            llm_out = _llm_rerank(top_combos=top_combos,
                                   profile=profile, context=context,
                                   n=n, n_explore=n_explore,
                                   model=model, n_max=n, root=root,
                                   l1_prefs_override=l1_prefs_override,
                                   feedback_avoided_names=feedback_avoided_names)
            if llm_out is not None:
                llm_called = True
        if llm_out is not None:
            # D-074: 映射逻辑抽到 _map_validated_candidates, in-process 主路径与
            # AI-friendly apply_rerank_response 共用单一可信源 (candidate→final 映射).
            mapped = _map_validated_candidates(llm_out, top_combos, n)
            if mapped:
                _log_selection_metrics(mapped, top_combos)
                _ensure_collector_filled(
                    status=(trace_collector or {}).get("status") or "ok",
                    attempted=llm_attempted, called=llm_called, used_fb=False,
                )
                return mapped

    # 走 fallback 路径: use_llm=False / LLM 失败 / mapped 为空
    _ensure_collector_filled(
        status=(trace_collector or {}).get("status") or "skipped",
        attempted=llm_attempted, called=llm_called, used_fb=True,
        reason=(trace_collector or {}).get("fallback_reason")
                 or ("use_llm=False" if not use_llm else "llm result unusable"),
    )
    # D-102 Step1: 经统一 FallbackPlan 构造入口 (meal_log 必填) → 与 cli 兜底单源同构,
    # in-process 同进程 build→execute (不落盘). 行为对 web 主路径 0-diff (meal_log 本就传).
    return build_fallback_plan(
        top_combos, meal_log=meal_log, n=n, n_explore=n_explore, today=today,
    ).execute()


# ═══════════════════════ D-074 AI-friendly: 外置 LLM 调用 ═══════════════════════
# chisha 不调 LLM — 把"读候选→排序"这个智能步骤打包成 llm_request_spec 信封给
# 宿主 agent 的 LLM 执行, 回传后 chisha 做全部确定性校验/映射/后处理 (设计 §2/§4).
# in-process rerank() 仍走自有 call_text 路径 (本两函数不替换它, 保 baseline 0-diff),
# 仅复用同一套 primitives (build_user_message / _RERANK_TOOL / _validate / _map).


def build_rerank_spec(
    top_combos: list[dict],
    profile: dict,
    context: "ContextSnapshot | None",
    *,
    n: int,
    n_explore: int,
    correlation_id: "Any",          # agent_protocol.CorrelationId
    output_mode: str = "tool_use",
    root: "Path | None" = None,
    l1_prefs_override: Any = _UNSET_L1_PREFS,
    feedback_avoided_names: list[str] | None = None,
) -> dict:
    """D-074: 构造 rerank `llm_request_spec` 信封 (不调 LLM).

    确定性 (候选准备 / prompt / schema / 后续校验) 全留 chisha; 智能 (读候选 →
    排序产出 + narrative) 交宿主 agent 的 LLM. system/user/tool schema 与 in-process
    _run_llm_rerank 完全同源 (复用 build_user_message + _RERANK_TOOL), 保证 agent
    LLM 按同一套规则排序.

    output_mode:
      - tool_use: 带 forced tool schema (anthropic/openrouter 类 agent)
      - text_json: system prompt 走 CLI patch (no-tool provider), json_schema 描述输出
    """
    from chisha.agent_protocol import build_request_spec

    raw_system = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    is_text_json = (output_mode == "text_json")
    # text_json 模式不支持 tool_use, system 走 CLI patch (与 in-process CLI 路径同源)
    system = _patch_system_prompt_for_cli(raw_system) if is_text_json else raw_system
    user_msg = build_user_message(
        top_combos, profile, context, n=n, n_explore=n_explore, root=root,
        l1_prefs_override=l1_prefs_override,
        feedback_avoided_names=feedback_avoided_names,
    )
    # required_validation: 告诉 agent chisha 出口会校验什么 (合约透明, 让 agent LLM
    # 按同一套规则产出). 人读, 非机器强约束 — 真正守门在 apply_rerank_response.
    # 输出约束 (合约透明, 让 agent LLM 产出 chisha 出口能直接消费的结构).
    # 只描述 agent 该产出什么, 不描述 chisha 内部 dedup/fallback 机制 (codex #d).
    n_exploit = n - n_explore
    required_validation = [
        f"candidates 数量 == {n} ({n_exploit} exploit + {n_explore} explore)",
        "rank 1..n 连续, 等于 array position + 1",
        "combo_index ∈ [0, len(candidates)), 不重复, 不越界",
        "fit_score / taste_match ∈ [0,1]",
        "exploit 段在前 explore 段在后, 不穿插 (refine 模式 n_explore=0 全 exploit)",
        "同 brand 至多 1 条",
        "不要输出 health_flags (由 chisha 规则算)",
    ]
    common = dict(
        operation_kind="rerank",
        correlation_id=correlation_id,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
        required_validation=required_validation,
    )
    if is_text_json:
        return build_request_spec(
            output_mode="text_json",
            json_schema=_RERANK_TOOL["input_schema"],
            **common,
        )
    return build_request_spec(
        output_mode="tool_use",
        tools=[_RERANK_TOOL],
        tool_choice=_RERANK_TOOL_CHOICE,
        **common,
    )


def apply_rerank_response(
    payload: dict,
    top_combos: list[dict],
    *,
    n: int,
    n_explore: int,
) -> tuple[list[dict] | None, dict]:
    """D-074: 收宿主 agent 精排回传 → 全部确定性守卫留 chisha (校验 + 映射 + 后处理).

    payload (agent 按 rerank spec 产出): {"candidates": [...], "narrative": "..."}.

    返回 (mapped_final | None, meta):
      - mapped 非 None: 校验通过 + 映射完成的 final cards
      - mapped None: 校验失败, 调用方走 fallback_policy=chisha_l2 (fallback_rerank)
      - meta: {status: ok|fallback, code, detail, narrative}
    """
    narrative = ""
    cands: Any = None
    if isinstance(payload, dict):
        nv = payload.get("narrative")
        if isinstance(nv, str):
            narrative = nv
        cands = payload.get("candidates")
    if not isinstance(cands, list):
        return None, {
            "status": "fallback", "code": "NO_CANDIDATES_LIST",
            "detail": f"payload.candidates 非 list: {type(cands).__name__}",
            "narrative": narrative,
        }
    # 与 in-process 同一套校验 (n_max=n, exploit/explore 段位, index 界, rank 连续)
    validated, code, detail = _validate_llm_candidates_v(
        cands, n_max=n, input_size=len(top_combos), n_explore_expected=n_explore,
    )
    if validated is None:
        return None, {
            "status": "fallback", "code": code, "detail": detail,
            "narrative": narrative,
        }
    mapped = _map_validated_candidates(validated, top_combos, n)
    if not mapped:
        return None, {
            "status": "fallback", "code": "EMPTY_AFTER_MAP",
            "detail": "brand_unique 后候选为空", "narrative": narrative,
        }
    return mapped, {"status": "ok", "code": "OK", "detail": None,
                    "narrative": narrative}


def _log_selection_metrics(
    mapped: list[dict], top_combos: list[dict]
) -> None:
    """D-046 二审 (真 Codex review) 观测埋点.

    打印 LLM 选中的 5 条 combo_index 落点分布 + 是否有更高分同 brand 被绕过.
    一周后用这些 metric 决策 N=60 是否需要调:
    - P(idx >= 40): N 从 40 涨到 60 是否真的让 L3 看见 L2 没识别的好货
    - P(idx >= 60): 是否需要进一步上调到 80/100
    - brand_has_higher_sibling: LLM 是否真在做"同品牌内部择优"
    """
    def _brand_key(c: dict) -> str:
        rest = c.get("restaurant") or {}
        return rest.get("brand") or rest.get("id") or ""

    selected = [c.get("combo_index", -1) for c in mapped]
    # 落点 band
    def _band(i: int) -> str:
        if i < 0: return "?"
        if i < 10: return "0-9"
        if i < 20: return "10-19"
        if i < 30: return "20-29"
        if i < 40: return "30-39"
        if i < 60: return "40-59"
        if i < 80: return "60-79"
        return "80+"
    bands = [_band(i) for i in selected]
    # 同 brand 是否有更高分 sibling 被 LLM 跳过 (i.e. 同品牌内部择优是否启用)
    brand_to_first_idx: dict[str, int] = {}
    for i, c in enumerate(top_combos):
        bk = _brand_key(c)
        if bk and bk not in brand_to_first_idx:
            brand_to_first_idx[bk] = i
    has_higher_sibling = []
    for c in mapped:
        idx = c.get("combo_index", -1)
        bk = _brand_key(c)
        if bk and bk in brand_to_first_idx and brand_to_first_idx[bk] < idx:
            has_higher_sibling.append(
                f"#{idx}(brand 最高 #{brand_to_first_idx[bk]})"
            )
    higher_str = ", ".join(has_higher_sibling) if has_higher_sibling else "无"
    print(
        f"  [rerank] LLM 选中 idx={selected} band={bands} "
        f"window={len(top_combos)} | 同品牌择优 (跳过更高分 sibling): {higher_str}"
    )


def _map_validated_candidates(
    validated: list[dict], top_combos: list[dict], n: int,
) -> list[dict]:
    """把已校验的 LLM candidates 映射回 combo: combo_index→combo merge +
    health_flags 规则补齐 (D-046) + brand 唯一性后处理 (D-045).

    纯确定性, 不调 LLM. in-process rerank() 主路径与 AI-friendly
    apply_rerank_response (D-074) 共用, 保证两条链路 candidate→final 映射单一可信源.

    注意: 与历史 in-process 行为逐字一致 — 取 validated[:n], 越界 idx skip,
    mutate cand["health_flags"], {**combo, **cand} merge, 末尾 enforce_brand_unique.
    """
    mapped: list[dict] = []
    for cand in validated[:n]:
        idx = cand.get("combo_index", -1)
        if not (0 <= idx < len(top_combos)):
            continue
        # health_flags 由规则补齐 (D-046: LLM 不再输出此字段)
        cand["health_flags"] = _compute_health_flags(top_combos[idx])
        # F2 (Faithful D-074): combo 确定性事实打底; LLM/agent candidate 只能贡献排序/
        # 说明白名单字段 (_REQUIRED_FIELDS + 规则补的 health_flags). 旧 {**combo,**cand}
        # 让回传 restaurant/dishes/score 覆盖确定性候选 — 守卫只在 chisha, 不在 agent
        # 输出上补偿. in-process tool_use 受 schema 约束本只产这些字段 → baseline 0-diff.
        merged = dict(top_combos[idx])
        for _k in _AGENT_OUTPUT_FIELDS:
            if _k in cand:
                merged[_k] = cand[_k]
        mapped.append(merged)
    return _enforce_brand_unique(mapped, top_combos, n=n)


def _enforce_brand_unique(
    mapped: list[dict], top_combos: list[dict], n: int
) -> list[dict]:
    """LLM 可能漏掉去重指令 — 同 brand (连锁) 在 top n 只能出现 1 次.

    D-045: 按 brand 去重 + rid 作为缺失兜底, 与 L2 apply_caps 的 brand 层
    语义保持一致. 不够 n 个时从 top_combos 剩余 combos 里按 score 补齐.
    """
    if not mapped:
        return mapped

    def _brand_key(c: dict) -> str:
        rest = c.get("restaurant") or {}
        return rest.get("brand") or rest.get("id", "")

    seen_brand: set[str] = set()
    out: list[dict] = []
    for c in mapped:
        bk = _brand_key(c)
        if bk and bk in seen_brand:
            continue
        if bk:
            seen_brand.add(bk)
        out.append(c)
    if len(out) >= n:
        return out[:n]
    # 不够 n 个: 从 top_combos 按 score 补齐
    used_combo_ids = {id(c) for c in mapped}
    for c in top_combos:
        if len(out) >= n:
            break
        if id(c) in used_combo_ids:
            continue
        bk = _brand_key(c)
        if bk and bk in seen_brand:
            continue
        if bk:
            seen_brand.add(bk)
        fill = {
            **c,
            "rank": len(out) + 1,
            "is_explore": False,
            "fit_score": c.get("score", 0),
            "health_flags": _compute_health_flags(c),
            "taste_match": None,
            "risk_flags": ["品牌去重补位"],
            "one_line_reason": "为多样性补位, 此条无 LLM 评分",
        }
        out.append(fill)
    for i, c in enumerate(out, start=1):
        c["rank"] = i
    return out

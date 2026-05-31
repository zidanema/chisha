"""D-076: L1 LLM 抽取层.

数据流:
    feedback_store.json (V1.1 反馈) + profile (方法论上下文)
        ↓ aggregate_inputs() — deterministic 预聚合, 不走 LLM
    summary dict (4 维直方图 + ingredient_frequency + recent_complaints/positive)
        ↓ call_llm() — claude_code_cli text + JSON prompt + parse/validate/retry
    raw LLM JSON 输出
        ↓ l1_prefs.validate_prefs()
    sanitized prefs dict
        ↓ l1_prefs.save_prefs()
    data/long_term_prefs.json

设计约束:
- 输入源仅 feedback_store.json (不消费 meal_log.jsonl)
- LLM 走 claude_code_cli (Max 订阅免费, 拍板 1A); 不走 tool_use (claude_code_cli 不支持)
- enum 校验在代码侧 (validate_prefs); LLM 仅作语义判断
- 失败降级: 抽取失败 → 保留上次 prefs (调用方决定); 不写新文件

约束:
- based_on_meals < MIN_MEALS_FOR_EXTRACTION (默认 3) → 返回空 prefs, 不调 LLM
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Callable, Optional


DEFAULT_WINDOW_DAYS = 14
MIN_MEALS_FOR_EXTRACTION = 3
DEFAULT_PROMPT_PATH = "prompts/l1_extract.md"
MAX_RECENT_EVIDENCE_SAMPLES = 5


# V1.1 反馈 4 维 calibration 桶映射 (DimVal: 0/1/2)
_CALIBRATION_DIMS = {
    "oil_calibration": ("too_low", "ok", "too_high"),
    "fullness": ("too_low", "ok", "too_high"),
    "reason_match": ("weak", "ok", "strong"),
    "repurchase_intent": ("no", "neutral", "yes"),
}

_RATING_BUCKETS = {-1: "dislike", 0: "neutral", 1: "like"}


def _to_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def aggregate_inputs(
    feedback_store_data: dict,
    profile: dict,
    today: dt.date | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    root: Path | None = None,
) -> dict:
    """Deterministic 预聚合 — 不走 LLM, 不抽取信号, 只计数.

    Codex Q7 修正: 不喂 raw feedback_store, 改喂结构化 summary.
    LLM 负责"解释和归纳", 不负责 ETL.

    Args:
        feedback_store_data: feedback_store.load_store() 返回的 dict
        profile: profile.yaml 加载结果
        today: 当日, None = clock.today(root) (D-077 PR-1a 第 12 处时间注入修补,
               原 dt.date.today() 在 sandbox 模式下用真实时钟, 把虚拟时钟产生的
               未来日期反馈整批过滤, 导致 based_on_meals 永远停在 1)
        window_days: 回看窗口, 默认 14 天
        root: 仓库根 (供 clock.today 解析 sandbox state)

    Returns:
        summary dict, 送 LLM prompt 用. 永不抛错, 数据不足时 based_on_meals=0.
    """
    if today is None:
        from chisha import clock
        today = clock.today(root=root)
    cutoff = today - dt.timedelta(days=window_days)
    feedbacks: dict[str, dict] = feedback_store_data.get("feedbacks") or {}
    accepted: dict[str, dict] = feedback_store_data.get("accepted") or {}
    sessions: dict[str, dict] = feedback_store_data.get("sessions") or {}

    relevant_sids = _relevant_sids(feedbacks, cutoff, today)
    calibration_histogram, rating_distribution = _calibration_histograms(
        feedbacks, relevant_sids
    )
    ingredient_freq = _ingredient_frequency(relevant_sids, accepted, sessions)
    # 排序: 最近 submitted 在前
    sorted_recent = sorted(
        relevant_sids,
        key=lambda s: feedbacks[s].get("submitted_at") or "",
        reverse=True,
    )
    recent_complaints, recent_positive = _recent_evidence(
        sorted_recent, feedbacks, accepted, sessions
    )

    methodology_name = profile.get("methodology", "harvard_plate")
    methodology_rationale = (
        profile.get("methodology_rationale")
        or "控油 + 至少 1 道蔬菜 + 蛋白下限"
    )

    return {
        "based_on_days": window_days,
        "based_on_meals": len(relevant_sids),
        "methodology": methodology_name,
        "methodology_rationale": methodology_rationale,
        "calibration_histogram": calibration_histogram,
        "rating_distribution": rating_distribution,
        "ingredient_frequency": ingredient_freq,
        "recent_complaints": recent_complaints,
        "recent_positive": recent_positive,
    }


def _relevant_sids(feedbacks: dict, cutoff: dt.date, today: dt.date) -> list[str]:
    """窗口内、有 V1.1 反馈、非 not-eaten 的 meal sid 列表 (pass 1)."""
    out: list[str] = []
    for sid, fb in feedbacks.items():
        if fb.get("variant") == "not-eaten":
            continue
        ts = _to_date(fb.get("submitted_at"))
        if ts is None or ts < cutoff or ts > today:
            continue
        out.append(sid)
    return out


def _calibration_histograms(feedbacks: dict, sids: list[str]) -> tuple[dict, dict]:
    """4 维 calibration 直方图 + rating 分布 (pass 2)."""
    calibration_histogram: dict[str, dict[str, int]] = {
        dim: {bucket: 0 for bucket in buckets}
        for dim, buckets in _CALIBRATION_DIMS.items()
    }
    rating_distribution: dict[str, int] = {b: 0 for b in _RATING_BUCKETS.values()}
    for sid in sids:
        fb = feedbacks[sid]
        for dim, buckets in _CALIBRATION_DIMS.items():
            val = fb.get(dim)
            if val in (0, 1, 2):
                calibration_histogram[dim][buckets[val]] += 1
        rating = fb.get("rating")
        if rating in _RATING_BUCKETS:
            rating_distribution[_RATING_BUCKETS[rating]] += 1
    return calibration_histogram, rating_distribution


def _ingredient_frequency(
    sids: list[str], accepted: dict, sessions: dict
) -> dict[str, int]:
    """从 accepted_rank 对应 combo dishes 的 main_ingredient_type 计数 (pass 3)."""
    ingredient_freq: dict[str, int] = {}
    for sid in sids:
        accepted_rec = accepted.get(sid) or {}
        rank = accepted_rec.get("accepted_rank")
        if rank is None:
            continue
        session_payload = sessions.get(sid) or {}
        candidates = session_payload.get("candidates") or []
        if not (1 <= rank <= len(candidates)):
            continue
        combo = candidates[rank - 1]
        for d in combo.get("dishes") or []:
            np_ = d.get("nutrition_profile") or {}
            ing = np_.get("main_ingredient_type")
            if ing:
                ingredient_freq[ing] = ingredient_freq.get(ing, 0) + 1
    return ingredient_freq


def _meal_snapshot(sid: str, feedbacks: dict, accepted: dict, sessions: dict) -> dict:
    """单顿快照 (dishes 名 + calibration 关键字段), 供 recent evidence 用."""
    fb = feedbacks[sid]
    accepted_rec = accepted.get(sid) or {}
    rank = accepted_rec.get("accepted_rank")
    session_payload = sessions.get(sid) or {}
    candidates = session_payload.get("candidates") or []
    dishes_names: list[str] = []
    if rank and 1 <= rank <= len(candidates):
        for d in candidates[rank - 1].get("dishes") or []:
            name = d.get("name")
            if name:
                dishes_names.append(name)
    return {
        "meal": sid,
        "dishes": dishes_names[:3],
        "oil_calibration": fb.get("oil_calibration"),
        "rating": fb.get("rating"),
        "repurchase_intent": fb.get("repurchase_intent"),
        "note": (fb.get("note") or "")[:80],  # 截断防 prompt 膨胀
    }


def _recent_evidence(
    sorted_sids: list[str], feedbacks: dict, accepted: dict, sessions: dict
) -> tuple[list[dict], list[dict]]:
    """单遍历同时收集 recent_complaints + recent_positive (各 ≤ MAX, pass 4/5).

    complaints: oil_calibration=2 或 rating=-1; positive: rating=1 且 repurchase=2.
    保持单循环 (同一 sorted 顺序), 不拆两次遍历 (codex 共商守则)。
    """
    recent_complaints: list[dict] = []
    recent_positive: list[dict] = []
    for sid in sorted_sids:
        fb = feedbacks[sid]
        if (fb.get("oil_calibration") == 2 or fb.get("rating") == -1) and \
                len(recent_complaints) < MAX_RECENT_EVIDENCE_SAMPLES:
            recent_complaints.append(_meal_snapshot(sid, feedbacks, accepted, sessions))
        if (fb.get("rating") == 1 and fb.get("repurchase_intent") == 2) and \
                len(recent_positive) < MAX_RECENT_EVIDENCE_SAMPLES:
            recent_positive.append(_meal_snapshot(sid, feedbacks, accepted, sessions))
    return recent_complaints, recent_positive


def _load_system_prompt(prompt_path: Path | str | None = None) -> str:
    """加载 system prompt. 默认读 prompts/l1_extract.md."""
    if isinstance(prompt_path, str):
        prompt_path = Path(prompt_path)
    if prompt_path is None:
        from chisha.install_root import install_root  # T-DIST-01 B.1
        p = install_root() / DEFAULT_PROMPT_PATH
    else:
        p = prompt_path
    return p.read_text(encoding="utf-8")


_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json_from_text(raw: str) -> dict:
    """从 LLM 输出文本里抽 JSON. 严格优先, fallback 走正则.

    LLM 可能不听话, 包了 markdown 代码块或加了前后说明. 我们做 best-effort:
    1. 直接 json.loads
    2. 去除 ``` 标记后 json.loads
    3. 正则提取第一个 {...} 后 json.loads
    全失败抛 ValueError, 调用方 retry.
    """
    stripped = raw.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 去 markdown 代码块
    cleaned = re.sub(r"^```(?:json)?\s*\n", "", stripped)
    cleaned = re.sub(r"\n```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 正则提取
    m = _JSON_BLOCK_RE.search(stripped)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从 LLM 输出抽 JSON: {stripped[:200]!r}")


# Default LLM call: lazy import 避免 test 时强依赖 llm_client.
def _default_llm_call(prompt: str, system: str, profile_llm: dict | None) -> str:
    """走 chisha.llm_client.call_text. 默认 provider auto (claude_code_cli 优先).

    返回纯文本 (content). 不传 tools, claude_code_cli 才能用 (D-076 拍板 1A).

    D-078 修补: 原写的是 `llm_client.call`, 实际只存在 `call_text` (D-047 改名
    后 L1 没跟上). 之前 based_on_meals 永远卡在 1 (D-078 时钟 bug) 掩盖了这处.
    """
    from chisha.llm_client import call_text
    result = call_text(
        prompt,
        system=system,
        max_tokens=2048,
        temperature=0.0,
        profile_llm=profile_llm,
        # 不传 tools, 走 text 路径
    )
    return result.get("content") or result.get("raw_text") or ""


def extract_prefs(
    summary: dict,
    *,
    profile_llm: dict | None = None,
    llm_call: Optional[Callable[[str, str, dict | None], str]] = None,
    system_prompt: str | None = None,
    max_retries: int = 1,
) -> dict:
    """LLM 抽取 + parse + validate + retry.

    Args:
        summary: aggregate_inputs() 输出
        profile_llm: profile.yaml 的 llm 配置 (provider/model 路由)
        llm_call: 测试注入. 默认走 chisha.llm_client.call. 接口:
            (prompt, system, profile_llm) -> str
        system_prompt: 测试注入. 默认读 prompts/l1_extract.md
        max_retries: LLM 调用失败重试次数, 默认 1 (共 2 次尝试)

    Returns:
        validated prefs dict. 数据不足时返回空骨架 (boost=[], penalty=[]).

    Raises:
        RuntimeError: LLM 调用全部失败. 调用方决定保留旧 prefs or 不抽.
    """
    # 数据不足: 直接返回空, 不调 LLM
    if summary.get("based_on_meals", 0) < MIN_MEALS_FOR_EXTRACTION:
        from chisha import clock
        return {
            "version": 1,
            "extracted_at": clock.now_utc().isoformat(),
            "based_on_days": summary.get("based_on_days", DEFAULT_WINDOW_DAYS),
            "based_on_meals": summary.get("based_on_meals", 0),
            "boost": [],
            "penalty": [],
            "signals_not_scored": {},
            "evidence": [],
            "regularities_freetext": [
                f"样本不足 ({summary.get('based_on_meals', 0)}/"
                f"{MIN_MEALS_FOR_EXTRACTION}), 暂不抽取"
            ],
            "skipped_extraction": True,
        }

    system = system_prompt or _load_system_prompt()
    user_prompt = (
        "请从以下 summary 抽取 ≤2 boost + ≤2 penalty。严格 JSON, 无 markdown。\n\n"
        f"```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```"
    )
    caller = llm_call or _default_llm_call

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        # 1. LLM 调用 (网络/订阅/CLI 异常)
        try:
            raw = caller(user_prompt, system, profile_llm)
        except Exception as e:
            last_err = RuntimeError(f"LLM call failed: {type(e).__name__}: {e}")
            if attempt >= max_retries:
                break
            continue

        # 2. JSON 解析 (LLM 输出格式异常)
        try:
            parsed = _extract_json_from_text(raw)
        except ValueError as e:
            last_err = e
            if attempt >= max_retries:
                break
            continue

        # 3. enum schema 校验 + canonicalize (代码侧 lazy import 防循环)
        from chisha.l1_prefs import validate_prefs
        try:
            validated = validate_prefs(parsed)
        except (ValueError, TypeError) as e:
            last_err = e
            if attempt >= max_retries:
                break
            continue

        # 注入元数据 (D-077 Codex S3: extracted_at 走虚拟时钟)
        from chisha import clock
        validated["extracted_at"] = clock.now_utc().isoformat()
        validated["based_on_days"] = summary.get("based_on_days", DEFAULT_WINDOW_DAYS)
        validated["based_on_meals"] = summary.get("based_on_meals", 0)
        return validated

    raise RuntimeError(
        f"L1 extract 失败 (尝试 {max_retries + 1} 次), 最后错: "
        f"{type(last_err).__name__}: {last_err}"
    )


def extract_and_save(
    feedback_store_data: dict,
    profile: dict,
    *,
    root: Path | None = None,
    today: dt.date | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    profile_llm: dict | None = None,
    llm_call: Optional[Callable] = None,
    bootstrap_from_legacy: bool = False,
) -> dict:
    """高层 API: aggregate → extract → save. 失败时不写盘.

    Returns:
        最终 prefs dict (含 extracted_at / based_on_*)
    """
    summary = aggregate_inputs(
        feedback_store_data, profile, today=today, window_days=window_days,
        root=root,
    )
    prefs = extract_prefs(
        summary,
        profile_llm=profile_llm or profile.get("llm"),
        llm_call=llm_call,
    )
    prefs["bootstrap_from_legacy"] = bootstrap_from_legacy
    from chisha.l1_prefs import save_prefs
    save_prefs(prefs, root=root)
    return prefs

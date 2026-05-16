"""D-073: L1 长期偏好层 (LLM 抽取产物) 读写.

异常约定 (D-074 Codex S3): L1 prefs 是派生数据, 损坏不阻塞推荐链路 —
load_prefs 损坏静默 rename .corrupt.bak + return None. 不抛 raise.

数据流:
    chisha/l1_extractor.py (LLM 抽取)
        ↓ save_prefs()
    data/long_term_prefs.json
        ↓ load_prefs()
    chisha/score.py rank_combos (taste_match_bonus 消费)

文件格式 (data/long_term_prefs.json):
{
  "version": 1,
  "extracted_at": "2026-05-22T08:00:00+00:00",
  "based_on_days": 14,
  "based_on_meals": 18,
  "boost": ["low_oil", "wetness"],
  "penalty": ["sweet_sauce", "processed_meat"],
  "signals_not_scored": {              # V1.1 4 维 calibration 中无 token 对应的维度
    "reason_match": {...},
    "fullness": {...},
    "repurchase_intent": {...}
  },
  "evidence": [
    {"token": "low_oil", "from_meals": ["sid_xxx"], "rationale": "..."}
  ],
  "regularities_freetext": [...],
  "bootstrap_from_legacy": false       # PR-0.6 兜底标记
}

降级行为:
- 文件不存在 → load_prefs return None
- 文件损坏 → rename to .corrupt.{ts}.bak, return None (fail-closed, 同 feedback_store.py)
- 空 prefs (boost+penalty 均 []) → return None (语义"无信号", 与旧 load_runtime_hints 等价)

设计约束:
- enum 限定 token 词表为 score.py taste_match_bonus 已支持的 6 个 (D-072 边界:
  词表扩展 = 改打分逻辑, 走独立决策 + baseline_l2_snapshot 守门, 不在 D-073 内)
- canonicalize: soup_or_broth → wetness (score.py 两别名同逻辑, 落盘统一存 wetness)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


# score.py taste_match_bonus 支持的 token 词表 (canonical, 不含别名)
BOOST_TOKENS = frozenset(["low_oil", "wetness"])
PENALTY_TOKENS = frozenset(["sweet_sauce", "processed_meat", "carb_heavy", "spicy"])
ALL_TOKENS = BOOST_TOKENS | PENALTY_TOKENS

# 兼容别名 → canonical (D-073 §2.2 Codex Q1)
TOKEN_ALIASES: dict[str, str] = {
    "soup_or_broth": "wetness",
}

# V1.1 反馈 4 维 calibration 中, 无 token 对应的维度
SIGNALS_NOT_SCORED_DIMS = frozenset(["reason_match", "fullness", "repurchase_intent"])

_PREFS_REL = "data/long_term_prefs.json"


def _prefs_path(root: Path | None = None) -> Path:
    """D-074 PR-1b: 走 data_root.long_term_prefs_path, sandbox 启用时落 logs/sandbox/."""
    from chisha import data_root
    return data_root.long_term_prefs_path(root)


def canonicalize_token(token: str) -> str | None:
    """别名 → canonical. 不在词表的 token 返回 None (调用方丢弃)."""
    token = TOKEN_ALIASES.get(token, token)
    return token if token in ALL_TOKENS else None


def validate_prefs(prefs: dict) -> dict:
    """schema 校验 + canonicalize + 去重 + maxItems 限制. 返回 sanitized prefs.

    严格规则 (D-073 + Codex S3 review):
    - boost 项必须在 BOOST_TOKENS (canonical 后), 不在词表的 token 丢弃
    - penalty 项必须在 PENALTY_TOKENS (canonical 后), 同上
    - **最多 2 个 boost + 2 个 penalty** (prompt 也约束 ≤2, 代码侧守门)
    - boost 与 penalty 不交叉 (同 token 不能同时是 boost 和 penalty, penalty 优先)
    - evidence: list of dict, 项里 token 必须在词表 (非法项丢)
    - signals_not_scored: dict
    - regularities_freetext: list of str (非字符串项丢)
    """
    if not isinstance(prefs, dict):
        raise ValueError(f"prefs must be dict, got {type(prefs).__name__}")

    raw_boost = prefs.get("boost") or []
    raw_penalty = prefs.get("penalty") or []
    if not isinstance(raw_boost, list) or not isinstance(raw_penalty, list):
        raise ValueError("boost / penalty must be list")

    boost: set[str] = set()
    for t in raw_boost:
        if not isinstance(t, str):
            continue
        c = canonicalize_token(t)
        if c and c in BOOST_TOKENS:
            boost.add(c)

    penalty: set[str] = set()
    for t in raw_penalty:
        if not isinstance(t, str):
            continue
        c = canonicalize_token(t)
        if c and c in PENALTY_TOKENS:
            penalty.add(c)

    # boost ∩ penalty 矛盾时, penalty 优先 (LLM 不能同时说"想要" + "不想要")
    boost -= penalty

    # maxItems=2 守门: prompt 要求 ≤2, 超出的话排序后截前 2 (deterministic)
    boost_list = sorted(boost)[:2]
    penalty_list = sorted(penalty)[:2]

    # evidence 校验
    raw_evidence = prefs.get("evidence") or []
    evidence: list[dict] = []
    if isinstance(raw_evidence, list):
        for item in raw_evidence:
            if not isinstance(item, dict):
                continue
            tok = item.get("token")
            if tok is not None and isinstance(tok, str):
                c = canonicalize_token(tok)
                if c is None:
                    continue  # token 不在词表丢
                item = {**item, "token": c}
            evidence.append(item)

    # signals_not_scored / regularities_freetext 类型校验
    sns = prefs.get("signals_not_scored")
    if not isinstance(sns, dict):
        sns = {}

    raw_regs = prefs.get("regularities_freetext") or []
    if isinstance(raw_regs, list):
        regs = [s for s in raw_regs if isinstance(s, str)]
    else:
        regs = []

    out = {
        **prefs,
        "boost": boost_list,
        "penalty": penalty_list,
        "evidence": evidence,
        "signals_not_scored": sns,
        "regularities_freetext": regs,
    }
    out.setdefault("version", 1)
    return out


def load_prefs(root: Path | None = None) -> dict | None:
    """读 prefs. 不存在 / 损坏 / 空信号 → None.

    Returns:
        sanitized prefs dict 或 None.
        - None 语义: "L2 应走 baseline, taste_match=0", 与旧 load_runtime_hints
          返回 None 等价 (PR-0.7 切 score 等价性依赖)
    """
    p = _prefs_path(root)
    if not p.exists():
        return None
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        # 损坏: 改名 backup, 返回 None (派生数据, 不 raise)
        try:
            ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            p.rename(p.with_suffix(f".json.corrupt.{ts}.bak"))
        except OSError:
            pass
        return None

    try:
        validated = validate_prefs(data)
    except (ValueError, TypeError):
        return None

    # 空信号 → None (等价旧 load_runtime_hints "无累计反馈" 行为)
    if not validated["boost"] and not validated["penalty"]:
        return None
    return validated


def save_prefs(prefs: dict, root: Path | None = None) -> Path:
    """落盘. validate + sanitize 后写. 调用方传 raw LLM 输出即可."""
    validated = validate_prefs(prefs)
    p = _prefs_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(validated, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


def to_runtime_hints(prefs: dict | None) -> dict[str, list[str]] | None:
    """适配 score.rank_combos 现有接口. 同 load_runtime_hints 返回格式.

    旧:  load_runtime_hints() → {"boost": [...], "penalty": [...]} 或 None
    新:  to_runtime_hints(load_prefs()) → 同上
    """
    if not prefs:
        return None
    if not prefs.get("boost") and not prefs.get("penalty"):
        return None
    return {
        "boost": list(prefs.get("boost") or []),
        "penalty": list(prefs.get("penalty") or []),
    }

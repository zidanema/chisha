"""V1.1 反馈系统单文件落盘 (D-066/D-067).

存储位置: logs/feedback/store.json
结构:
{
  "accepted": {
    "<session_id>": {
      "session_id": str,
      "accepted_rank": int,
      "accepted_at": iso,                 # accepted 时间
      "meal_type": "lunch" | "dinner",
      "restaurant_name": str,
      "summary": str,
      "snoozed_until": iso | null,        # D-060 软关闭 24h
      "stopped": bool,                    # D-060 硬关闭
      "skipped": bool,                    # D-054 这餐没吃, 不参与 inbox
      "skip_reason": str | null
    }
  },
  "feedbacks": {
    "<session_id>": FeedbackRecord        # payload + submitted_at + comments[]
  },
  "sessions": {
    "<session_id>": RecommendResponse     # 反馈页要回放 5 候选, 这里冷存一份
  }
}

简化策略 (D-066/D-067 + 单用户场景):
- 全量 rewrite, 无 lock (单用户单进程, FastAPI sync 端点 → 无并发)
- 落盘失败不抛, 上游降级 (best-effort, recommend 链路不能被反馈断掉)
- inbox/recent/snooze 等读路径派生自 accepted + feedbacks, 不冗余存
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
import threading
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()
_STORE_REL = "logs/feedback/store.json"


def _store_path(root: Path) -> Path:
    """D-077 PR-1b: 走 data_root.feedback_store_path, sandbox 落 logs/sandbox/feedback/."""
    from chisha import data_root
    return data_root.feedback_store_path(root)


def _empty_store() -> dict:
    return {"accepted": {}, "feedbacks": {}, "sessions": {}}


class StoreCorruptError(RuntimeError):
    """store.json 损坏. 调用方应当 raise 5xx, 不允许静默清空."""


def load_store(root: Path) -> dict:
    """读 store. 不存在 → 空 store; 损坏 → 重命名为 .corrupt.{ts}.bak + 抛错.

    Codex review MED-3: 之前的 except Exception → _empty_store() 会让下次写盘
    把所有历史反馈数据覆盖掉。fail-closed 让上游 5xx, 让用户/运维知道。
    """
    p = _store_path(root)
    if not p.exists():
        return _empty_store()
    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except Exception as e:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = p.with_suffix(f".json.corrupt.{ts}.bak")
        try:
            p.rename(backup)
        except Exception:
            # rename 失败也保留信息, 抛错让上游决定
            backup = p
        raise StoreCorruptError(
            f"feedback store corrupt, moved to {backup.name}: "
            f"{type(e).__name__}: {e}"
        ) from e
    if not isinstance(data, dict):
        raise StoreCorruptError(f"feedback store root must be dict, got {type(data).__name__}")
    # 兜底缺字段 (合法的部分老 store)
    for k in ("accepted", "feedbacks", "sessions"):
        data.setdefault(k, {})
    return data


def save_store(root: Path, data: dict) -> None:
    p = _store_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(p)


def _now_iso() -> str:
    from chisha import clock
    return clock.now_utc().isoformat()


# ---------- 写路径 ----------

def remember_session(root: Path, session_id: str, payload: dict) -> None:
    """Phase B 反馈页要回放 5 候选, 把 recommend 响应整包冷存."""
    with _LOCK:
        data = load_store(root)
        data["sessions"][session_id] = payload
        save_store(root, data)


def record_accept(
    root: Path,
    session_id: str,
    candidate_rank: int,
    meal_type: str,
    restaurant_name: str,
    summary: str,
) -> None:
    with _LOCK:
        data = load_store(root)
        data["accepted"][session_id] = {
            "session_id": session_id,
            "accepted_rank": candidate_rank,
            "accepted_at": _now_iso(),
            "meal_type": meal_type,
            "restaurant_name": restaurant_name,
            "summary": summary,
            "snoozed_until": None,
            "stopped": False,
            "skipped": False,
            "skip_reason": None,
        }
        save_store(root, data)


def record_skip(root: Path, session_id: str, reason: str | None) -> None:
    """D-054: skip 不入 acceptedQueue (用户压根没吃这餐).

    语义: 如果该 session 已 accept (用户先点了再说没吃) → 标 skipped + reason
          否则建一个 skipped=true 占位, 让前端 inbox 不再展示。
    """
    with _LOCK:
        data = load_store(root)
        item = data["accepted"].get(session_id)
        if item is None:
            data["accepted"][session_id] = {
                "session_id": session_id,
                "accepted_rank": None,
                "accepted_at": _now_iso(),
                "meal_type": None,
                "restaurant_name": "",
                "summary": "",
                "snoozed_until": None,
                "stopped": True,        # 不再弹 banner
                "skipped": True,
                "skip_reason": reason,
            }
        else:
            item["skipped"] = True
            item["skip_reason"] = reason
            item["stopped"] = True
        save_store(root, data)


def set_snooze(root: Path, session_id: str, hours: int = 24) -> None:
    with _LOCK:
        data = load_store(root)
        item = data["accepted"].get(session_id)
        if item:
            from chisha import clock
            until = clock.now_utc() + dt.timedelta(hours=hours)
            item["snoozed_until"] = until.isoformat()
            save_store(root, data)


def set_stop(root: Path, session_id: str) -> None:
    with _LOCK:
        data = load_store(root)
        item = data["accepted"].get(session_id)
        if item:
            item["stopped"] = True
            save_store(root, data)


def record_feedback(root: Path, payload: dict) -> dict:
    """提交 / 覆盖 feedback. comments[] 保留 (D-067)."""
    sid = payload["session_id"]
    with _LOCK:
        data = load_store(root)
        existing = data["feedbacks"].get(sid) or {}
        record = {
            **payload,
            "submitted_at": _now_iso(),
            "comments": existing.get("comments") or [],
        }
        data["feedbacks"][sid] = record
        save_store(root, data)
        return record


def append_comment(root: Path, session_id: str, text: str) -> dict | None:
    """D-067 append-only 备注. 没有 feedback 时返回 None."""
    with _LOCK:
        data = load_store(root)
        fb = data["feedbacks"].get(session_id)
        if not fb:
            return None
        # Codex review LOW: 同毫秒多次 append 会撞 ID, 加 4-hex 随机后缀
        ms = int(dt.datetime.now().timestamp() * 1000)
        comment = {
            "id": f"cmt_{ms}_{secrets.token_hex(2)}",
            "text": text,
            "created_at": _now_iso(),
        }
        fb.setdefault("comments", []).append(comment)
        save_store(root, data)
        return comment


# ---------- 读路径 (派生) ----------

def _is_snoozed_now(snoozed_until: str | None) -> bool:
    """Codex review LOW: fromisoformat 不带 tz → 与 aware utcnow 比较会 TypeError.
    统一 normalize: naive 视为 UTC, aware 转 UTC.
    """
    if not snoozed_until:
        return False
    try:
        until = dt.datetime.fromisoformat(snoozed_until)
    except ValueError:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=dt.timezone.utc)
    else:
        until = until.astimezone(dt.timezone.utc)
    from chisha import clock
    return clock.now_utc() < until


def inbox_items(data: dict, include_snoozed: bool = True) -> list[dict]:
    """派生 inbox: 未反馈 + 未 stopped + 未 skipped, 按 accepted_at 倒序."""
    items: list[dict] = []
    for sid, item in data["accepted"].items():
        if item.get("stopped") or item.get("skipped"):
            continue
        if sid in data["feedbacks"]:
            continue
        snoozed = _is_snoozed_now(item.get("snoozed_until"))
        if snoozed and not include_snoozed:
            continue
        items.append({
            "session_id": sid,
            "meal_type": item.get("meal_type") or "lunch",
            "restaurant_name": item.get("restaurant_name") or "",
            "summary": item.get("summary") or "",
            "accepted_at": item["accepted_at"],
            "snoozed": snoozed,
            "stopped": False,
        })
    items.sort(key=lambda x: x["accepted_at"], reverse=True)
    return items


def recent_feedback_items(data: dict, limit: int = 6) -> list[dict]:
    out: list[dict] = []
    for sid, fb in data["feedbacks"].items():
        accepted = data["accepted"].get(sid) or {}
        out.append({
            "session_id": sid,
            "meal_type": accepted.get("meal_type") or "lunch",
            "restaurant_name": accepted.get("restaurant_name") or "（都没吃）",
            "accepted_at": accepted.get("accepted_at") or fb.get("submitted_at"),
            "submitted_at": fb["submitted_at"],
            "rating": fb.get("rating"),
            "accepted_rank": fb.get("accepted_rank"),
        })
    out.sort(key=lambda x: x["submitted_at"], reverse=True)
    return out[:limit]


def get_session_record(root: Path, session_id: str) -> dict | None:
    """反馈页头部要回放 5 候选 — 从 sessions[] 拉. 没存 → None."""
    data = load_store(root)
    return data["sessions"].get(session_id)


def get_accepted(data: dict, session_id: str) -> dict | None:
    return data["accepted"].get(session_id)


def get_feedback_record(data: dict, session_id: str) -> dict | None:
    return data["feedbacks"].get(session_id)


# ---------- B-001: feedback_recency 短链路视图 ----------

def _parse_iso_date(ts: str | None) -> dt.date | None:
    """容忍 ISO datetime / date 字符串 (带 Z / +00:00 后缀也接受)."""
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip()
    if not s:
        return None
    try:
        if "T" in s:
            # ISO datetime; 把末尾 Z 当 UTC
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return dt.datetime.fromisoformat(s).date()
        return dt.date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _parse_iso_datetime(ts: str | None) -> dt.datetime | None:
    """Codex S5 Q4.2: age_meals 排序需 datetime 粒度 (同日午/晚餐区分).
    返回 aware datetime (UTC); 失败 None.
    """
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip()
    if not s:
        return None
    try:
        if "T" in s:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            d = dt.datetime.fromisoformat(s)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            return d.astimezone(dt.timezone.utc)
        # 纯 date 字符串视为当日 00:00 UTC
        return dt.datetime.combine(
            dt.date.fromisoformat(s[:10]), dt.time(0, 0), dt.timezone.utc
        )
    except (ValueError, TypeError):
        return None


def _derive_last_meal_cuisine(
    sessions: dict, sid: str, accepted_rank: int | None
) -> str | None:
    """从 sessions[sid].candidates[rank-1] 推导上一餐 cuisine.

    取 combo 第一道有 cuisine 的菜. 没有 → None (reason_match 信号优雅降级).
    """
    if not accepted_rank:
        return None
    sp = (sessions or {}).get(sid) or {}
    cands = sp.get("candidates") or []
    if not (1 <= accepted_rank <= len(cands)):
        return None
    for d in cands[accepted_rank - 1].get("dishes") or []:
        c = d.get("cuisine")
        if c:
            return c
    return None


def build_feedback_view(
    store: dict,
    today: dt.date,
    window_days: int = 60,
    note_window_days: int = 14,
    calibration_max: int = 3,
) -> dict:
    """B-001 v2 + D-083: 派生 3 段 feedback view + observability snapshot.

    输入:
      - store: feedback_store.load_store(root) 返回的 dict
      - today: 虚拟时钟 (sandbox / What-if frozen 用)
      - window_days: ratings 时间窗 (默认 60)
      - note_window_days: note/comments 时间窗 (默认 14)
      - calibration_max: 最近 N 餐 calibration (默认 3)

    输出: dict {
      "ratings": [...],        # v1 形态, 兼容旧 feedback_recency 路径
      "calibrations": [...],   # v2 新, 最近 N 餐 4 维 calibration + last_meal_cuisine
      "note_tokens": [...],    # v2 新, note + comments[] 词表抽取
      "feedback_trace": {...}, # D-083 新, 派生层因果快照 (写 trace + DAG 渲染用)
    }

    设计原则 (B-001 v2 Codex S2 共识):
      - 仅 restaurant 级 (accepted.summary 自由文本, 不解析菜品)
      - source-of-truth = feedbacks[sid] + accepted[sid] + sessions[sid].candidates
      - age_days 取 accepted.accepted_at 优先 (吃饭时间)
      - comments[] 用每条 comment 自己的 created_at (Codex Q5)
      - 否定前缀严格丢弃, 不做语义反转 (Codex Q3)
      - reason_match=0 需 last_meal_cuisine, 从 sessions[sid].candidates[rank-1] 推

    What-if 路径: 调用方不能传 store, 必须读 __frozen.feedback_view (D-079 红线).
    """
    # D-083 Codex S3 MINOR fix: invalid store / window<0 也走 4-key 契约,
    # 不能少 feedback_trace (否则 score 路径 normalize → 4 key, view 路径
    # 在异常分支 → 3 key, 行为不一致).
    if not isinstance(store, dict) or window_days < 0:
        return {
            "ratings": [], "calibrations": [], "note_tokens": [],
            "feedback_trace": _empty_feedback_trace_skeleton(today),
        }
    accepted = store.get("accepted") or {}
    feedbacks = store.get("feedbacks") or {}
    sessions = store.get("sessions") or {}

    ratings: list[dict] = []
    calibrations_all: list[dict] = []
    note_tokens: list[dict] = []

    from chisha.feedback_text_extract import extract_tokens

    for sid, fb in feedbacks.items():
        if not isinstance(fb, dict):
            continue
        acc = accepted.get(sid) or {}
        name = (acc.get("restaurant_name") or "").strip()
        if not name:
            continue
        when_str = acc.get("accepted_at") or fb.get("submitted_at")
        when_dt = _parse_iso_datetime(when_str)  # Codex S5 Q4.2: datetime 粒度
        if when_dt is None:
            continue
        when = when_dt.date()
        age = (today - when).days
        if age < 0:
            continue

        # ── ratings (v1)
        rating = fb.get("rating")
        try:
            rating_int = int(rating) if rating is not None else 0
        except (ValueError, TypeError):
            rating_int = 0
        if rating_int in (-1, 1) and age <= window_days:
            ratings.append({
                "restaurant_name": name,
                "rating": rating_int,
                "age_days": age,
            })

        # ── calibrations (v2 新)
        accepted_rank = acc.get("accepted_rank")
        cal_entry = {
            "session_id": sid,
            "restaurant_name": name,
            "age_days": age,
            # Codex S5 Q4.2 + Q4.5: 真序粒度 + 显式 age_meals 字段 (后填)
            "_when_dt_iso": when_dt.isoformat(),
            "oil_calibration": fb.get("oil_calibration"),
            "fullness": fb.get("fullness"),
            "reason_match": fb.get("reason_match"),
            "repurchase_intent": fb.get("repurchase_intent"),
            "last_meal_cuisine": _derive_last_meal_cuisine(
                sessions, sid, accepted_rank
            ),
        }
        # 任何 4 维非空 + age<=7 才进 (短期信号)
        has_signal = any(
            cal_entry[k] is not None
            for k in ("oil_calibration", "fullness",
                       "reason_match", "repurchase_intent")
        )
        if has_signal and age <= 7:
            calibrations_all.append(cal_entry)

        # ── note_tokens (v2 新) — note 字段
        note_text = (fb.get("note") or "").strip()
        if note_text and age <= note_window_days:
            tokens = extract_tokens(note_text)
            if tokens["boost"] or tokens["penalty"]:
                note_tokens.append({
                    "restaurant_name": name,
                    "age_days": age,
                    "boost": sorted(tokens["boost"]),
                    "penalty": sorted(tokens["penalty"]),
                    "raw_text": note_text[:80],
                    "source": "note",
                })

        # ── note_tokens (v2 新) — comments[] 字段 (每条独立 created_at)
        for cmt in fb.get("comments") or []:
            if not isinstance(cmt, dict):
                continue
            cmt_text = (cmt.get("text") or "").strip()
            if not cmt_text:
                continue
            cmt_when = _parse_iso_date(cmt.get("created_at"))
            if cmt_when is None:
                continue
            cmt_age = (today - cmt_when).days
            if cmt_age < 0 or cmt_age > note_window_days:
                continue
            tokens = extract_tokens(cmt_text)
            if tokens["boost"] or tokens["penalty"]:
                note_tokens.append({
                    "restaurant_name": name,
                    "age_days": cmt_age,
                    "boost": sorted(tokens["boost"]),
                    "penalty": sorted(tokens["penalty"]),
                    "raw_text": cmt_text[:80],
                    "source": "comment",
                })

    ratings.sort(key=lambda x: x["age_days"])
    # Codex S5 Q4.2: 按 datetime 倒序 (最新在前), enumerate 写入显式 age_meals.
    # 同日午/晚餐由 datetime 区分, 不再依赖 dict iteration 顺序.
    calibrations_all.sort(key=lambda x: x["_when_dt_iso"], reverse=True)
    calibrations: list[dict] = []
    for age_meals, cal in enumerate(calibrations_all[:calibration_max]):
        cal["age_meals"] = age_meals
        cal.pop("_when_dt_iso", None)  # 内部字段, 不暴露
        calibrations.append(cal)
    note_tokens.sort(key=lambda x: x["age_days"])

    # D-083: feedback_trace 派生层因果快照. 与主 3 段是 sibling 关系 (不嵌进
    # ratings/calibrations/note_tokens), 避开 normalize_feedback_view 历史剥离
    # 行为. score.py 主路径不依赖此字段, 只 trace 写盘 + debug-ui 渲染时取.
    feedback_trace = _build_feedback_trace_snapshot(
        today=today,
        windows={
            "ratings": window_days,
            "calibrations": _CAL_AGE_DAYS_HARD_LIMIT,
            "note_tokens": note_window_days,
        },
        ratings=ratings,
        calibrations=calibrations,
        note_tokens=note_tokens,
    )

    return {
        "ratings": ratings,
        "calibrations": calibrations,
        "note_tokens": note_tokens,
        "feedback_trace": feedback_trace,
    }


# ── D-083: feedback_trace 派生层因果快照 ────────────────────────────────────

# calibration 7d 硬闸 (与 score._CAL_AGE_DAYS_HARD_LIMIT 同步, 这里冗余声明只为
# 让 build_feedback_view 不引入对 score 的反向依赖)
_CAL_AGE_DAYS_HARD_LIMIT = 7


def _empty_feedback_trace_skeleton(today=None) -> dict:
    """D-083: 给所有"空 view"路径用的统一空骨架. invalid store / window<0 /
    pre-D-083 v1 trace 都走这条, 让 4-key contract 严格一致.
    """
    return {
        "today": today.isoformat() if hasattr(today, "isoformat") else None,
        "windows": {"ratings": 60, "calibrations": 7, "note_tokens": 14},
        "rating_signals": [],
        "calibration_rules": [],
        "note_breakdown": [],
        "global_token_freq": {"boost": {}, "penalty": {}},
        "global_active_tokens": {"boost": [], "penalty": []},
        "empty": True,
    }


def _build_feedback_trace_snapshot(
    today: dt.date,
    windows: dict,
    ratings: list,
    calibrations: list,
    note_tokens: list,
) -> dict:
    """D-083: 派生 feedback_trace 顶层快照, 给 trace + debug-ui 用.

    每段提供 *结构化因子* (peak/tau/decay/age) + 可选 display 串. 不提供"渲染好
    的公式文本"作为单一字段 — debug-ui 拿到结构化字段后自己组装.
    """
    import math

    # rating_signals: 公式 = peak × exp(-age/tau)
    # Codex Q1: 存结构化 factors, 不存 free-text formula
    rating_signals = []
    for r in ratings:
        rating = r.get("rating")
        age = r.get("age_days", 0)
        if rating == -1:
            peak = _FEEDBACK_NEG_PEAK
            tau = _FEEDBACK_TAU_NEG
            signal = peak * math.exp(-age / tau)
            stage = "neg_decay"
        elif rating == 1:
            if age < _FEEDBACK_POS_COOLDOWN_DAYS:
                peak = _FEEDBACK_POS_COOLDOWN_PEAK
                tau = None
                signal = peak * (1.0 - age / _FEEDBACK_POS_COOLDOWN_DAYS)
                stage = "pos_cooldown"
            else:
                peak = _FEEDBACK_POS_BOOST_PEAK
                tau = _FEEDBACK_TAU_POS
                signal = peak * math.exp(
                    -(age - _FEEDBACK_POS_COOLDOWN_DAYS) / tau
                )
                stage = "pos_boost"
        else:
            continue
        rating_signals.append({
            "restaurant_name": r.get("restaurant_name"),
            "rating": rating,
            "age_days": age,
            "signal": round(signal, 4),
            "factors": {"peak": peak, "tau": tau, "stage": stage},
        })

    # calibration_rules: 因为 next_meal_calibration_score 的规则依赖 combo 本身
    # (avg_oil / n_dishes / cuisine), 在 view 层只能描述 *上游条件*
    # (oil=2 触发哪类规则), 实际加分需 combo 维度. 这里给 view 级的 rule_set 描述,
    # combo 级实际 fired 由 score.py 写到 combo['feedback_evidence'] 里.
    calibration_rules = []
    for cal in calibrations:
        age_meals = cal.get("age_meals", 0)
        weight = {0: 1.0, 1: 0.5, 2: 0.25}.get(age_meals, 0.0)
        triggers = []
        oc = cal.get("oil_calibration")
        if oc == 2:
            triggers.append({
                "field": "oil_calibration", "value": 2,
                "desc": "太油 → 偏好 avg_oil ≤ 2",
            })
        elif oc == 0:
            triggers.append({
                "field": "oil_calibration", "value": 0,
                "desc": "油不足 → 松开 avg_oil ≥ 3",
            })
        fl = cal.get("fullness")
        if fl == 0:
            triggers.append({
                "field": "fullness", "value": 0,
                "desc": "没饱 → 偏好 n_dishes ≥ 4 + protein 充足",
            })
        elif fl == 2:
            triggers.append({
                "field": "fullness", "value": 2,
                "desc": "撑 → 偏好 n_dishes ≤ 2",
            })
        rm = cal.get("reason_match")
        last_c = cal.get("last_meal_cuisine")
        if rm == 0 and last_c:
            triggers.append({
                "field": "reason_match", "value": 0,
                "desc": f"理由弱 → 偏好 cuisine ≠ {last_c}",
            })
        if not triggers:
            continue
        calibration_rules.append({
            "session_id": cal.get("session_id"),
            "restaurant_name": cal.get("restaurant_name"),
            "age_meals": age_meals,
            "age_days": cal.get("age_days"),
            "weight": weight,
            "last_meal_cuisine": last_c,
            "triggers": triggers,
        })

    # note_breakdown: 每条 note/comment 的衰减系数 + 抽出的 token + 命中规则
    note_breakdown = []
    boost_unique: dict = {}
    penalty_unique: dict = {}
    boost_age: dict = {}
    penalty_age: dict = {}
    for n in note_tokens:
        age = n.get("age_days") or 0
        decay = math.exp(-age / 7.0)  # _NOTE_TAU_DAYS
        note_breakdown.append({
            "restaurant_name": n.get("restaurant_name"),
            "age_days": age,
            "decay": round(decay, 4),
            "boost": list(n.get("boost") or []),
            "penalty": list(n.get("penalty") or []),
            "raw_text": n.get("raw_text"),
            "source": n.get("source"),
        })
        r = n.get("restaurant_name") or ""
        for tok in n.get("boost") or []:
            boost_unique.setdefault(tok, set()).add(r)
            boost_age[tok] = min(boost_age.get(tok, 9999), age)
        for tok in n.get("penalty") or []:
            penalty_unique.setdefault(tok, set()).add(r)
            penalty_age[tok] = min(penalty_age.get(tok, 9999), age)

    global_token_freq = {
        "boost": {tok: len(rs) for tok, rs in boost_unique.items()},
        "penalty": {tok: len(rs) for tok, rs in penalty_unique.items()},
    }
    # _NOTE_GLOBAL_MIN_HITS = 2 (与 score.py 同步)
    global_active_tokens = {
        "boost": sorted([t for t, c in global_token_freq["boost"].items() if c >= 2]),
        "penalty": sorted([t for t, c in global_token_freq["penalty"].items() if c >= 2]),
    }

    return {
        "today": today.isoformat() if hasattr(today, "isoformat") else str(today),
        "windows": windows,
        "rating_signals": rating_signals,
        "calibration_rules": calibration_rules,
        "note_breakdown": note_breakdown,
        "global_token_freq": global_token_freq,
        "global_active_tokens": global_active_tokens,
        # 空骨架 marker — 让前端区分"没数据"vs"没字段"
        "empty": not (rating_signals or calibration_rules or note_breakdown),
    }


# 与 score.py 同步的常量 (Q1: 结构化 factors 用)
_FEEDBACK_TAU_NEG = 14.0
_FEEDBACK_TAU_POS = 14.0
_FEEDBACK_NEG_PEAK = -1.5
_FEEDBACK_POS_COOLDOWN_PEAK = -0.7
_FEEDBACK_POS_COOLDOWN_DAYS = 3
_FEEDBACK_POS_BOOST_PEAK = 0.25


def normalize_feedback_view(view) -> dict:
    """统一 feedback_view 形态: v1 list[dict] | v2 dict | None → v2 dict.

    用于 score/rerank 内部, 兼容旧 fixture / 旧 frozen trace.

    D-083: feedback_trace 顶层 key 必须保留, 否则 score.py 主路径丢失因果上下文.
    历史 v1/None 无此字段 → 兜底空骨架 (与 _build_feedback_trace_snapshot empty=True 等价).
    """
    empty_trace = {
        "today": None,
        "windows": {},
        "rating_signals": [],
        "calibration_rules": [],
        "note_breakdown": [],
        "global_token_freq": {"boost": {}, "penalty": {}},
        "global_active_tokens": {"boost": [], "penalty": []},
        "empty": True,
    }
    if view is None:
        return {"ratings": [], "calibrations": [], "note_tokens": [],
                "feedback_trace": empty_trace}
    if isinstance(view, list):
        # v1: 老的 list[dict] (只有 ratings) → 包成 v2 dict
        return {"ratings": view, "calibrations": [], "note_tokens": [],
                "feedback_trace": empty_trace}
    if isinstance(view, dict):
        return {
            "ratings": view.get("ratings") or [],
            "calibrations": view.get("calibrations") or [],
            "note_tokens": view.get("note_tokens") or [],
            # D-083: 保留 feedback_trace, 老 dict 无此字段 → 空骨架兜底
            "feedback_trace": view.get("feedback_trace") or empty_trace,
        }
    return {"ratings": [], "calibrations": [], "note_tokens": [],
            "feedback_trace": empty_trace}

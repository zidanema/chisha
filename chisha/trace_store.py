"""D-079: 推荐链路 trace 持久化层.

存储位置: logs/recommend_trace/{session_id}.json (sandbox → logs/sandbox/recommend_trace/)
一次推荐一个文件, **不写 jsonl** (单行膨胀难调试).
单文件硬上限 300KB (超过按 §10 优先级裁剪).

设计原则 (D-079 决策 + Codex review 闭环):
- best-effort 写盘: 失败 logger.warning, 不阻断 recommend (同 feedback_store)
- fail-closed 读盘: 损坏抛 TraceCorrupt + 备份 .corrupt.{ts}.bak (同 D-066/067 MED-3)
- 自包含 trace: __frozen 含 ctx + l1_combos + profile_snapshot + l1_prefs_snapshot
  + l2_meal_log_view + today, What-if 重跑零 runtime read
- schema __version=1, 不识别抛 TraceVersionMismatch (调用方决定 409)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from pathlib import Path
from typing import Any, Literal, Optional, TypedDict

from chisha import data_root


logger = logging.getLogger(__name__)

TRACE_SCHEMA_VERSION = 4  # B-001/D-098: bump 3→4, __frozen 增 feedback_signal_snapshot
# + feedback_avoided_names (What-if 零 runtime read 重放输入扩充).
# D-087: bump 2→3, refine 单 dict → rounds[] 数组, 同时拆目录存储.
# v=1 trace 可被 read/list 接受 (on-read migration 注空 hard_filter_events).
# v=2 trace 同上 (单文件 + refine 单 dict). v=3 = {sid}/meta.json + {sid}/rounds/R{n}.json
# 拆目录, on-read 把 v2 单文件视图升 v3 view (不写回); /api/refine 写盘走 append_round
# 自动 migrate v2 → v3. v=4 纯增量 frozen 字段, v3 trace 缺该键 → what_if .get()→None
# → 无反馈效果 (pre-D098 trace 本就无反馈信号, 恰好正确), 故 v3 仍在 accepted 集.
ACCEPTED_TRACE_VERSIONS: set[int] = {1, 2, 3, 4}
# D-079 用户决策: trace 大小不省空间, 调试完整性优先 (Phase 0 单 zone 1260 dishes
# 实测 ~1.3MB 是常态). 这里 50MB 是纯 sanity bound, 防意外/恶意大数据写满磁盘,
# 不是日常裁剪阈值. 正常 trace (<5MB) 直接写, 不走任何裁剪.
MAX_TRACE_BYTES = 50 * 1024 * 1024  # 50MB sanity bound


# ────────────────────────── L0 三分 + hard_filter_event schema (T-00)
# 配合 docs/CONTRACTS.md「L0 三分判定表」: A 医学 / B 身份 / C 健康 + methodology
L0Category = Literal["L0_A_medical", "L0_B_identity", "L0_C_health", "methodology"]


class HardFilterEvent(TypedDict, total=False):
    """L1 hard_filter 触发的事件记录. T-P1a-01 会真实写入. 本任务只建占位.

    顶层位置: trace["l1"]["hard_filter_events"] (list[HardFilterEvent]).
    """
    event_type: str            # 固定 "hard_filter"
    category: L0Category       # 严格枚举, append_hard_filter_event 校验
    rule: str                  # 人读规则名 "蔬菜占比≥50%" / "no_peanut_allergy"
    dropped_count: int
    kept_count: int
    refine_override: bool      # C 类被 refine 解除时 True
    timestamp: float           # time.time()


_HFE_VALID_CATEGORIES: set[str] = {
    "L0_A_medical", "L0_B_identity", "L0_C_health", "methodology"
}
_HFE_REQUIRED_FIELDS: tuple[str, ...] = (
    "category", "rule", "dropped_count", "kept_count"
)


class TraceCorrupt(RuntimeError):
    """trace JSON 损坏. 调用方应 500. 文件已自动备份 .corrupt.{ts}.bak."""


class TraceVersionMismatch(RuntimeError):
    """trace __version 与当前 TRACE_SCHEMA_VERSION 不匹配. 调用方应 409."""

    def __init__(self, found: Any, expected: int = TRACE_SCHEMA_VERSION) -> None:
        super().__init__(f"trace version mismatch: found={found!r}, expected={expected}")
        self.found = found
        self.expected = expected


# ────────────────────────── 写路径

def write_trace(
    session_id: str,
    trace: dict,
    root: Optional[Path] = None,
) -> bool:
    """原子写 trace 文件. 失败 logger.warning, 返 False (不抛, 不阻断 recommend).

    Args:
        session_id: trace 文件名 (不带 .json), 不能含 / 或空格.
        trace: 完整 trace dict, 顶层会被强制 set __version=TRACE_SCHEMA_VERSION.
        root: 项目根. None=自动 (sandbox 派生由 data_root 处理).

    Returns:
        True 写盘成功, False 失败 (warn 已 log).

    实施细节:
    - 序列化前估算 size, 超 MAX_TRACE_BYTES 走 _truncate_for_size (D-079 §10)
    - 原子写: tmp + replace
    """
    try:
        trace["__version"] = TRACE_SCHEMA_VERSION
        # T-00: v2 兜底注入 l1.hard_filter_events = [] (Codex review blocker #1).
        # api._build_trace / debug_recommend._build_l1_trace 上游不主动 init 时,
        # 在写盘前保证字段存在; 上游已 append 的事件保留.
        l1_block = trace.setdefault("l1", {})
        if isinstance(l1_block, dict) and "hard_filter_events" not in l1_block:
            l1_block["hard_filter_events"] = []
        # session_id 反注入: 不允许 / 或 ..
        if "/" in session_id or ".." in session_id or not session_id:
            raise ValueError(f"invalid session_id: {session_id!r}")

        # size 估算 + 必要时裁剪
        payload = json.dumps(trace, ensure_ascii=False)
        if len(payload.encode("utf-8")) > MAX_TRACE_BYTES:
            trace = _truncate_for_size(trace)
            payload = json.dumps(trace, ensure_ascii=False)
            if len(payload.encode("utf-8")) > MAX_TRACE_BYTES:
                logger.error(
                    "trace %s still over %dKB after truncation, skip write",
                    session_id, MAX_TRACE_BYTES // 1024,
                )
                return False

        d = data_root.recommend_trace_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{session_id}.json"
        # D-079 Codex FIX-NOW #7: tmp 文件名加 pid + 短随机后缀, 防并发 write
        # 撞同名 .tmp (即便 sid 撞了, tmp 也独立 → 不破坏对方写盘)
        import os
        import secrets as _secrets
        tmp = p.with_suffix(f".json.tmp.{os.getpid()}.{_secrets.token_hex(4)}")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception as e:
        logger.warning("write_trace failed for %s: %s: %s",
                       session_id, type(e).__name__, e)
        return False


# ────────────────────────── 读路径

def read_trace(
    session_id: str,
    root: Optional[Path] = None,
) -> Optional[dict]:
    """读 trace + schema 版本校验.

    Failure matrix (D-079 §3.1):
      - 不存在: 返 None (调用方决定 404)
      - JSON 损坏: 备份 .corrupt.{ts}.bak + 抛 TraceCorrupt (调用方决定 500)
      - schema __version 不识别: 抛 TraceVersionMismatch (调用方决定 409)
      - 顶层字段不是 dict: 同损坏处理

    fail-closed 与 feedback_store.load_store (D-066/067 MED-3) 一致.
    """
    if "/" in session_id or ".." in session_id or not session_id:
        raise ValueError(f"invalid session_id: {session_id!r}")
    p = data_root.recommend_trace_dir(root) / f"{session_id}.json"
    if not p.exists():
        return None
    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except Exception as e:
        backup = _backup_corrupt(p)
        raise TraceCorrupt(
            f"trace {session_id} corrupt, moved to {backup.name}: "
            f"{type(e).__name__}: {e}"
        ) from e
    if not isinstance(data, dict):
        backup = _backup_corrupt(p)
        raise TraceCorrupt(
            f"trace {session_id} root must be dict, got {type(data).__name__}, "
            f"moved to {backup.name}"
        )
    version = data.get("__version")
    if version not in ACCEPTED_TRACE_VERSIONS:
        raise TraceVersionMismatch(found=version)
    return _normalize_to_current_version(data)


def _normalize_to_current_version(data: dict) -> dict:
    """v=1 → v=2 on-read migration. 注空 hard_filter_events 让 caller 看到统一 shape.

    **不写回磁盘**, 不改 __version 字段 (保留来源记录).
    下次 write_trace 会把 __version 强制设为 TRACE_SCHEMA_VERSION (refine merge 走这条).
    """
    version = data.get("__version")
    if version == 1:
        l1 = data.setdefault("l1", {})
        if "hard_filter_events" not in l1:
            l1["hard_filter_events"] = []
    return data


def _backup_corrupt(p: Path) -> Path:
    """rename 损坏文件到 .corrupt.{ts}.bak. rename 失败保留原文件位置."""
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = p.with_suffix(f".json.corrupt.{ts}.bak")
    try:
        p.rename(backup)
    except Exception:
        backup = p  # rename 失败仅返原 path 给错误信息
    return backup


# ────────────────────────── 列表 (Sidebar 数据源)

def list_traces(
    root: Optional[Path] = None,
    limit: int = 30,
    meal_type: Optional[str] = None,
) -> tuple[list[dict], int]:
    """列出最近 N 条 trace meta (不读 full body). 按 started_at desc.

    Returns:
        (items, corrupt_count). 损坏的 trace 跳过 (不抛), 仅累计 corrupt_count.
        前端可选展示 "N 条损坏被跳过" warning.

    items 元素 = {session_id, started_at, meal_type, zone, top1_summary,
                  total_latency_ms, l3_status, source}.
    feedback link 由调用方再 attach (派生字段不存 trace 文件).
    """
    d = data_root.recommend_trace_dir(root)
    if not d.exists():
        return [], 0

    items: list[dict] = []
    corrupt_count = 0
    for p in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                corrupt_count += 1
                continue
            version = data.get("__version")
            if version not in ACCEPTED_TRACE_VERSIONS:
                # 版本不在 accepted 集合的 trace 跳过, 不算 corrupt.
                # 列表路径不需要 normalize (只读 top1_summary 等元信息, 不需要 l1.hard_filter_events).
                logger.info("list_traces skipped unknown __version=%r at %s",
                            version, p.name)
                continue
            frozen = data.get("__frozen") or {}
            mt = frozen.get("meal_type") or data.get("l1", {}).get("meal")
            if meal_type and mt != meal_type:
                continue
            top1_summary = _extract_top1_summary(data)
            items.append({
                "session_id": data.get("session_id") or p.stem,
                "started_at": data.get("started_at"),
                "meal_type": mt,
                "zone": frozen.get("zone"),
                "top1_summary": top1_summary,
                "total_latency_ms": data.get("total_latency_ms"),
                "l3_status": (data.get("l3") or {}).get("status"),
                "source": data.get("__source") or "production",
            })
        except Exception as e:
            corrupt_count += 1
            logger.warning("list_traces skipped corrupt %s: %s: %s",
                           p.name, type(e).__name__, e)
            continue
        if len(items) >= limit:
            break

    return items, corrupt_count


def _extract_top1_summary(trace: dict) -> str:
    """从 final[0] 提取 'restaurant_name · dish1 + dish2' 摘要."""
    final = trace.get("final") or []
    if not final:
        return ""
    top1 = final[0]
    rest = (top1.get("restaurant") or {}).get("name") or ""
    dishes = top1.get("dishes") or []
    dish_names = [d.get("name") or d.get("dish_name") or "" for d in dishes[:2]]
    dish_names = [n for n in dish_names if n]
    if not dish_names:
        return rest
    return f"{rest} · {' + '.join(dish_names)}"


# ────────────────────────── feedback link 派生

def attach_feedback_links(
    items: list[dict],
    root: Optional[Path] = None,
) -> list[dict]:
    """从 feedback_store 派生 accepted/rating/stopped, 不写回 trace 文件.

    每次 list_traces 后调一次, 单次 load_store 给所有 items 用 (避免 N+1).
    """
    try:
        from chisha import feedback_store
        from chisha.data_root import _resolve_root
        store = feedback_store.load_store(_resolve_root(root))
    except Exception as e:
        logger.warning("attach_feedback_links load_store failed: %s: %s",
                       type(e).__name__, e)
        return items

    accepted = store.get("accepted", {})
    feedbacks = store.get("feedbacks", {})
    for item in items:
        sid = item.get("session_id")
        if not sid:
            item["feedback"] = None
            continue
        acc = accepted.get(sid)
        fb = feedbacks.get(sid)
        if not acc and not fb:
            item["feedback"] = None
            continue
        item["feedback"] = {
            "accepted": bool(acc) and not (acc or {}).get("skipped"),
            "accepted_rank": (acc or {}).get("accepted_rank"),
            "accepted_at": (acc or {}).get("accepted_at"),
            "feedback_submitted": fb is not None,
            "rating": (fb or {}).get("rating"),
            "stopped": bool((acc or {}).get("stopped")),
        }
    return items


# ────────────────────────── 裁剪 (D-079 §10)

def _truncate_for_size(trace: dict) -> dict:
    """按 §10 4 级裁剪顺序处理超 300KB trace.

    1. l3.llm_raw_response: 首 8KB + 尾 4KB, 中间替占位
    2. l1.dropped_dishes: cap 500 条 + __truncated_drop_count
    3. __frozen.profile_snapshot: 仅保留 scoring 必需字段
    4. __frozen.l1_combos[].dishes[].nutrition_profile: 删非 scoring 字段
    """
    import copy
    t = copy.deepcopy(trace)

    # Step 1: LLM raw response
    l3 = t.get("l3") or {}
    raw = l3.get("raw_response") or l3.get("llm_raw_response") or ""
    if isinstance(raw, str) and len(raw) > 12 * 1024:
        head = raw[:8 * 1024]
        tail = raw[-4 * 1024:]
        truncated_bytes = len(raw) - len(head) - len(tail)
        if "raw_response" in l3:
            l3["raw_response"] = f"{head}...[truncated {truncated_bytes} bytes]...{tail}"
        if "llm_raw_response" in l3:
            l3["llm_raw_response"] = f"{head}...[truncated {truncated_bytes} bytes]...{tail}"
        t["l3"] = l3

    if _trace_size_bytes(t) <= MAX_TRACE_BYTES:
        return t

    # Step 2: L1 dropped_dishes cap
    l1 = t.get("l1") or {}
    drops = l1.get("dropped_dishes") or []
    if len(drops) > 500:
        l1["dropped_dishes"] = drops[:500]
        l1["__truncated_drop_count"] = len(drops) - 500
        t["l1"] = l1

    if _trace_size_bytes(t) <= MAX_TRACE_BYTES:
        return t

    # Step 3: profile_snapshot 子集 (仅保留 scoring 必需)
    frozen = t.get("__frozen") or {}
    profile = frozen.get("profile_snapshot") or {}
    if profile:
        slim = {
            k: profile[k]
            for k in (
                "scoring_weights", "methodology", "recall", "scoring",
                "plate_rule", "zones", "preferences", "basics",
            )
            if k in profile
        }
        frozen["profile_snapshot"] = slim
        t["__frozen"] = frozen

    if _trace_size_bytes(t) <= MAX_TRACE_BYTES:
        return t

    # Step 4: dish nutrition_profile 仅保留 scoring 字段.
    # Codex PR-2 DEFER #5: schema 与 api._SCORING_NUTRITION_KEYS 严格一致,
    # 且裁剪目标改成 __frozen.dishes 表 (PR-1 normalized schema, 不再嵌套在 l1_combos).
    from chisha.api import _SCORING_NUTRITION_KEYS
    dishes_tbl = (t.get("__frozen") or {}).get("dishes") or {}
    if isinstance(dishes_tbl, dict):
        for did, d in dishes_tbl.items():
            np = d.get("nutrition_profile") or {}
            d["nutrition_profile"] = {
                k: v for k, v in np.items() if k in _SCORING_NUTRITION_KEYS
            }
    return t


def _trace_size_bytes(trace: dict) -> int:
    return len(json.dumps(trace, ensure_ascii=False).encode("utf-8"))


# ────────────────────────── hard_filter_event helper (T-00)

def append_hard_filter_event(
    trace: dict,
    *,
    category: str,
    rule: str,
    dropped_count: int,
    kept_count: int,
    refine_override: bool = False,
    timestamp: float | None = None,
) -> bool:
    """T-P1a-01 真实写事件用. 本任务只建占位 + schema 校验.

    校验规则:
      - category 必须 ∈ L0Category (A/B/C/methodology), 否则 warn + 不写
      - rule 必须非空字符串, dropped_count / kept_count 必须 int >= 0
      - 写入位置: trace.setdefault("l1", {}).setdefault("hard_filter_events", []).append(...)

    Returns:
        True 写入成功, False 校验失败 (warn 已 log, 与 best-effort 风格一致).

    边界:
      - 本 helper 不直接 write_trace; 调用方组装 trace 后再写盘.
      - 同 trace 多事件按调用顺序追加, 后续可加 collapse/dedup 逻辑.
    """
    if category not in _HFE_VALID_CATEGORIES:
        logger.warning("append_hard_filter_event: invalid category=%r, skip", category)
        return False
    if not isinstance(rule, str) or not rule.strip():
        logger.warning("append_hard_filter_event: empty rule, skip")
        return False
    # bool 是 int 的子类, 显式排除 (Codex review NOTE).
    if isinstance(dropped_count, bool) or not isinstance(dropped_count, int) or dropped_count < 0:
        logger.warning("append_hard_filter_event: bad dropped_count=%r, skip", dropped_count)
        return False
    if isinstance(kept_count, bool) or not isinstance(kept_count, int) or kept_count < 0:
        logger.warning("append_hard_filter_event: bad kept_count=%r, skip", kept_count)
        return False

    event: HardFilterEvent = {
        "event_type": "hard_filter",
        "category": category,  # type: ignore[typeddict-item]
        "rule": rule.strip(),
        "dropped_count": dropped_count,
        "kept_count": kept_count,
        "refine_override": bool(refine_override),
        "timestamp": timestamp if timestamp is not None else time.time(),
    }
    l1 = trace.setdefault("l1", {})
    events = l1.setdefault("hard_filter_events", [])
    events.append(event)
    return True


# ══════════════════════════════════════════════════════════════════════
# D-087 trace_store v3: 拆目录存储 + meta lock + 多 round
# ══════════════════════════════════════════════════════════════════════
# 布局:
#   {recommend_trace_dir}/{sid}/meta.json     ← TRACES item shape + round_ids
#   {recommend_trace_dir}/{sid}/rounds/R{n}.json  ← 单 round 完整 (l1/l2/l3/final)
#   {recommend_trace_dir}/{sid}/.lock             ← fcntl.flock 临界区
#
# v2 单文件 ({sid}.json) 仍可被 read_trace_v3 读 (内存升 v3 view, 不写回).
# /api/refine 调 append_round 时自动触发 v2 → v3 文件迁移.
# ══════════════════════════════════════════════════════════════════════

import fcntl
import contextlib
from typing import Callable, Iterator


def _sid_dir(sid: str, root: Optional[Path] = None) -> Path:
    """v3 trace 目录 path. 不创建."""
    return data_root.recommend_trace_dir(root) / sid


def _v2_file(sid: str, root: Optional[Path] = None) -> Path:
    """v2 单文件 path. 不创建."""
    return data_root.recommend_trace_dir(root) / f"{sid}.json"


def _meta_path(sid: str, root: Optional[Path] = None) -> Path:
    return _sid_dir(sid, root) / "meta.json"


def _round_path(sid: str, round_id: str, root: Optional[Path] = None) -> Path:
    return _sid_dir(sid, root) / "rounds" / f"{round_id}.json"


def _lock_path(sid: str, root: Optional[Path] = None) -> Path:
    # 不放 {sid}/ 内 — 避免空目录在 no-base/corrupt 分支被预先创出来.
    # 用 parent dir 的 hidden lockfile, sid 编码进文件名.
    return data_root.recommend_trace_dir(root) / f".lock-{sid}"


def is_v3_trace(sid: str, root: Optional[Path] = None) -> bool:
    """v3 = {sid}/meta.json 存在. 检测便宜, 不读文件."""
    return _meta_path(sid, root).exists()


def has_v2_trace(sid: str, root: Optional[Path] = None) -> bool:
    return _v2_file(sid, root).exists()


@contextlib.contextmanager
def lock_meta(sid: str, root: Optional[Path] = None) -> Iterator[None]:
    """fcntl.flock 互斥锁, 包住 read_meta → mutate → write_meta + write_round.

    {sid}/.lock 是独立 file, 单纯当 lockfile 用 (不写内容). 这样 meta.json 可以
    走 tmp+rename 原子替换, 同时锁不丢.

    Cross-process safe (fcntl 系统调用), 同进程多线程不需要 (单 worker FastAPI).
    """
    if "/" in sid or ".." in sid or not sid:
        raise ValueError(f"invalid session_id: {sid!r}")
    # 只确保 parent dir (recommend_trace) 存在, **不**预创 {sid}/.
    # 这样 no-base / corrupt 分支不会留空 v3 dir 给 list_traces_v3 误识别.
    lock_p = _lock_path(sid, root)
    lock_p.parent.mkdir(parents=True, exist_ok=True)
    # 用 "a+" 创建 lockfile, 不写内容
    with open(lock_p, "a+") as fp:
        fcntl.flock(fp, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fp, fcntl.LOCK_UN)


def read_meta(sid: str, root: Optional[Path] = None) -> Optional[dict]:
    """读 v3 meta.json. 不存在返 None. 损坏抛 TraceCorrupt + 备份."""
    p = _meta_path(sid, root)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        backup = _backup_corrupt(p)
        raise TraceCorrupt(
            f"meta {sid} corrupt, moved to {backup.name}: "
            f"{type(e).__name__}: {e}"
        ) from e
    if not isinstance(data, dict):
        backup = _backup_corrupt(p)
        raise TraceCorrupt(f"meta {sid} root must be dict, moved to {backup.name}")
    return data


def write_meta_atomic(sid: str, meta: dict, root: Optional[Path] = None) -> bool:
    """原子写 meta.json (tmp + rename). best-effort, 失败 warn + 返 False.
    调用方应在 lock_meta 内调用."""
    try:
        meta["__version"] = TRACE_SCHEMA_VERSION
        p = _meta_path(sid, root)
        p.parent.mkdir(parents=True, exist_ok=True)
        import os
        import secrets as _secrets
        tmp = p.with_suffix(f".json.tmp.{os.getpid()}.{_secrets.token_hex(4)}")
        tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception as e:
        logger.warning("write_meta_atomic failed for %s: %s: %s",
                       sid, type(e).__name__, e)
        return False


def read_round(sid: str, round_id: str, root: Optional[Path] = None) -> Optional[dict]:
    """读 {sid}/rounds/R{n}.json. 不存在返 None."""
    p = _round_path(sid, round_id, root)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        backup = _backup_corrupt(p)
        raise TraceCorrupt(
            f"round {sid}/{round_id} corrupt, moved to {backup.name}: "
            f"{type(e).__name__}: {e}"
        ) from e
    if not isinstance(data, dict):
        backup = _backup_corrupt(p)
        raise TraceCorrupt(f"round {sid}/{round_id} root must be dict, moved to {backup.name}")
    return data


def write_round_atomic(
    sid: str, round_id: str, payload: dict, root: Optional[Path] = None,
) -> bool:
    """原子写 round 文件. 与 write_trace 一样的 size + tmp+rename 模式."""
    try:
        payload = dict(payload)
        payload["id"] = round_id
        body = json.dumps(payload, ensure_ascii=False)
        if len(body.encode("utf-8")) > MAX_TRACE_BYTES:
            # round 单文件超大 — 走老 _truncate_for_size 兜底
            payload = _truncate_for_size(payload)
            body = json.dumps(payload, ensure_ascii=False)
            if len(body.encode("utf-8")) > MAX_TRACE_BYTES:
                logger.error("round %s/%s still over %dKB, skip write",
                             sid, round_id, MAX_TRACE_BYTES // 1024)
                return False
        p = _round_path(sid, round_id, root)
        p.parent.mkdir(parents=True, exist_ok=True)
        import os
        import secrets as _secrets
        tmp = p.with_suffix(f".json.tmp.{os.getpid()}.{_secrets.token_hex(4)}")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception as e:
        logger.warning("write_round_atomic failed for %s/%s: %s: %s",
                       sid, round_id, type(e).__name__, e)
        return False


def _build_meta_from_v2(v2_trace: dict) -> dict:
    """从 v2 单文件 trace dict 派生 v3 meta. v2 refine 信息丢弃 (本来就被覆盖了)."""
    sid = v2_trace.get("session_id") or ""
    frozen = v2_trace.get("__frozen") or {}
    return {
        "__version": TRACE_SCHEMA_VERSION,
        "__source": v2_trace.get("__source") or "production",
        "session_id": sid,
        "started_at": v2_trace.get("started_at"),
        "meal_type": frozen.get("meal_type") or v2_trace.get("l1", {}).get("meal"),
        "zone": frozen.get("zone"),
        "top1_summary": _extract_top1_summary(v2_trace),
        "total_latency_ms": v2_trace.get("total_latency_ms"),
        "l3_status": (v2_trace.get("l3") or {}).get("status"),
        "round_ids": ["R1"],
        "latest_round": "R1",
        "refine_count": 0,
        "__migrated_from_v2": True,
    }


def _build_r1_round_from_v2(v2_trace: dict) -> dict:
    """从 v2 单文件 trace dict 派生 R1 round 文件. l1/l2/l3/final + __frozen 全搬."""
    return {
        "id": "R1",
        "started_at": v2_trace.get("started_at"),
        "user_input": None,
        # D-094.1: R1 是初始推荐 round, 没有用户 refine, intent_v2 永远是 None.
        "intent_v2": None,
        "narrative": "",
        "kpi": {
            "combos": _extract_combo_count(v2_trace.get("l1") or {}),
            "l2_top": (v2_trace.get("l2") or {}).get("candidates_to_l3") or 0,
            "top1": _extract_top1_summary(v2_trace),
            "latency_ms": v2_trace.get("total_latency_ms") or 0,
        },
        "diff": None,
        "ctx_latency_ms": v2_trace.get("ctx_latency_ms"),
        "recall_latency_ms": v2_trace.get("recall_latency_ms"),
        "score_latency_ms": v2_trace.get("score_latency_ms"),
        "rerank_latency_ms": v2_trace.get("rerank_latency_ms"),
        "final_latency_ms": v2_trace.get("final_latency_ms"),
        "l1": v2_trace.get("l1"),
        "l2": v2_trace.get("l2"),
        "l3": v2_trace.get("l3"),
        "final": v2_trace.get("final"),
        "__frozen": v2_trace.get("__frozen"),
        "__config": v2_trace.get("__config"),
    }


def _extract_combo_count(l1: dict) -> int:
    funnel = l1.get("funnel") or []
    if not funnel:
        return 0
    last = funnel[-1] or {}
    return int(last.get("value") or 0)


def migrate_v2_to_v3(sid: str, root: Optional[Path] = None) -> bool:
    """惰性迁移: 把 {sid}.json (v2) 拆成 {sid}/meta.json + rounds/R1.json.
    调用方应在 lock_meta 内调用. 成功后删除 v2 文件; 失败保留 v2.

    Idempotent: 如果 v3 已存在 + v2 不存在 → 直接 True.
    """
    if is_v3_trace(sid, root):
        # 已迁移. v2 残留先不删 (谨慎), 让 caller 决定.
        return True
    v2_p = _v2_file(sid, root)
    if not v2_p.exists():
        return False  # 既没有 v3 也没有 v2
    try:
        v2_data = json.loads(v2_p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("migrate_v2_to_v3 read v2 failed for %s: %s: %s",
                       sid, type(e).__name__, e)
        return False
    if not isinstance(v2_data, dict):
        logger.warning("migrate_v2_to_v3 v2 not dict for %s", sid)
        return False
    meta = _build_meta_from_v2(v2_data)
    r1 = _build_r1_round_from_v2(v2_data)
    if not write_round_atomic(sid, "R1", r1, root=root):
        return False
    if not write_meta_atomic(sid, meta, root=root):
        return False
    # 迁移成功 → 删 v2 单文件 (留 .migrated_v2 备份)
    try:
        v2_p.rename(v2_p.with_suffix(".json.migrated_v2"))
    except Exception as e:
        logger.warning("migrate_v2_to_v3 rename v2 file failed for %s: %s",
                       sid, e)
    return True


def append_round(
    sid: str,
    round_payload: dict,
    *,
    root: Optional[Path] = None,
) -> Optional[str]:
    """加新 round 到 v3 trace. 自动 migrate v2 → v3 (如果需要).

    Args:
        sid: session_id
        round_payload: 单 round 完整 dict (id 字段会被覆盖为服务端签发的 round_id).
            必须含: user_input, intent_v2, narrative, kpi, l1, l2, l3, final.
            可选: diff (调用方算好), __frozen.
    Returns:
        新签发的 round_id ("R{n}"), 失败返 None (warn 已 log).

    Best-effort 同 write_trace; 失败不抛, 由 caller 决定是否影响主响应.
    """
    if "/" in sid or ".." in sid or not sid:
        raise ValueError(f"invalid session_id: {sid!r}")
    try:
        with lock_meta(sid, root):
            # migrate v2 → v3 (无副作用 if v3 已存在)
            if not is_v3_trace(sid, root):
                if not migrate_v2_to_v3(sid, root):
                    logger.warning(
                        "append_round %s: no v2/v3 trace base, refusing to "
                        "create orphan refine trace", sid,
                    )
                    return None
            meta = read_meta(sid, root)
            if meta is None:
                logger.warning("append_round %s: meta vanished after migrate", sid)
                return None
            round_ids: list[str] = list(meta.get("round_ids") or [])
            n = len(round_ids) + 1
            round_id = f"R{n}"
            round_payload = dict(round_payload)
            round_payload["id"] = round_id
            # 写 round 文件
            if not write_round_atomic(sid, round_id, round_payload, root=root):
                return None
            # 更新 meta (round_ids + latest + refine_count + 顶层 latency / l3_status 镜像)
            round_ids.append(round_id)
            meta["round_ids"] = round_ids
            meta["latest_round"] = round_id
            meta["refine_count"] = len(round_ids) - 1
            kpi = round_payload.get("kpi") or {}
            if kpi.get("top1"):
                meta["top1_summary"] = kpi["top1"]
            if kpi.get("latency_ms"):
                meta["total_latency_ms"] = kpi["latency_ms"]
            l3 = round_payload.get("l3") or {}
            if l3.get("status"):
                meta["l3_status"] = l3["status"]
            if not write_meta_atomic(sid, meta, root=root):
                return None
            return round_id
    except Exception as e:
        logger.warning("append_round failed for %s: %s: %s",
                       sid, type(e).__name__, e)
        return None


def read_trace_v3_view(
    sid: str, root: Optional[Path] = None,
) -> Optional[dict]:
    """统一 v3 view 读: 返 {meta, rounds: [round_stub]}, **不含** round body.

    - v3 dir 存在 → 读 meta.json + 每个 round 文件的 stub (id/user_input/intent/kpi/diff)
    - 仅 v2 单文件 → 内存构造 view (rounds = [R1 from top-level]), 不写回
    - 都不存在 → None

    round_stub 不含 l1/l2/l3/final body (大), 调 read_round 单独拉.
    """
    # v3 优先
    meta = read_meta(sid, root)
    if meta is not None:
        round_ids = list(meta.get("round_ids") or [])
        stubs = []
        for rid in round_ids:
            r = read_round(sid, rid, root)
            if r is None:
                continue
            stubs.append({
                "id": r.get("id") or rid,
                "label": r.get("label") or ("原始" if rid == "R1" else "追问"),
                "started_at": r.get("started_at"),
                "user_input": r.get("user_input"),
                "intent_v2": r.get("intent_v2"),
                "narrative": r.get("narrative"),
                "kpi": r.get("kpi"),
                "diff": r.get("diff"),
            })
        return {"meta": meta, "rounds": stubs}
    # v2 fallback (in-memory migrate)
    if has_v2_trace(sid, root):
        v2 = read_trace(sid, root)
        if v2 is None:
            return None
        meta = _build_meta_from_v2(v2)
        r1 = _build_r1_round_from_v2(v2)
        return {
            "meta": meta,
            "rounds": [{
                "id": "R1", "label": "原始",
                "started_at": r1["started_at"], "user_input": None, "intent_v2": None,
                "narrative": "", "kpi": r1["kpi"], "diff": None,
            }],
        }
    return None


def read_round_full(
    sid: str, round_id: str, root: Optional[Path] = None,
) -> Optional[dict]:
    """读 round 完整 body (l1/l2/l3/final). v2 单文件 trace → R1 = 整个 trace."""
    if is_v3_trace(sid, root):
        return read_round(sid, round_id, root)
    if has_v2_trace(sid, root):
        if round_id != "R1":
            # v2 只有 R1, 其他 round 不存在
            return None
        v2 = read_trace(sid, root)
        if v2 is None:
            return None
        return _build_r1_round_from_v2(v2)
    return None


def list_traces_v3(
    root: Optional[Path] = None,
    limit: int = 30,
    meal_type: Optional[str] = None,
) -> tuple[list[dict], int]:
    """v3-aware list: 扫 v3 目录 + v2 单文件, 合并按 mtime desc.

    返 [TraceMeta dict] + corrupt_count. TraceMeta 字段:
      session_id, started_at, meal_type, zone, top1_summary, total_latency_ms,
      l3_status, source, round_ids, latest_round, refine_count.
    feedback 由 attach_feedback_links 后挂.
    """
    d = data_root.recommend_trace_dir(root)
    if not d.exists():
        return [], 0

    candidates: list[tuple[float, str, str]] = []   # (mtime, layout, path/sid)
    for entry in d.iterdir():
        if entry.is_dir():
            mp = entry / "meta.json"
            if mp.exists():
                try:
                    candidates.append((mp.stat().st_mtime, "v3", entry.name))
                except OSError:
                    continue
        elif entry.suffix == ".json" and not entry.name.startswith("."):
            try:
                candidates.append((entry.stat().st_mtime, "v2", entry.stem))
            except OSError:
                continue
    candidates.sort(reverse=True)

    items: list[dict] = []
    corrupt = 0
    seen_sids: set[str] = set()
    for _mtime, layout, sid in candidates:
        if sid in seen_sids:
            continue
        try:
            if layout == "v3":
                meta = read_meta(sid, root)
                if meta is None:
                    continue
                mt = meta.get("meal_type")
                if meal_type and mt != meal_type:
                    continue
                items.append({
                    "session_id": meta.get("session_id") or sid,
                    "started_at": meta.get("started_at"),
                    "meal_type": mt,
                    "zone": meta.get("zone"),
                    "top1_summary": meta.get("top1_summary"),
                    "total_latency_ms": meta.get("total_latency_ms"),
                    "l3_status": meta.get("l3_status"),
                    "source": meta.get("__source") or "production",
                    "round_ids": list(meta.get("round_ids") or ["R1"]),
                    "latest_round": meta.get("latest_round") or "R1",
                    "refine_count": int(meta.get("refine_count") or 0),
                })
            else:
                p = d / f"{sid}.json"
                raw = p.read_text(encoding="utf-8")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    corrupt += 1
                    continue
                version = data.get("__version")
                if version not in ACCEPTED_TRACE_VERSIONS:
                    continue
                frozen = data.get("__frozen") or {}
                mt = frozen.get("meal_type") or data.get("l1", {}).get("meal")
                if meal_type and mt != meal_type:
                    continue
                items.append({
                    "session_id": data.get("session_id") or sid,
                    "started_at": data.get("started_at"),
                    "meal_type": mt,
                    "zone": frozen.get("zone"),
                    "top1_summary": _extract_top1_summary(data),
                    "total_latency_ms": data.get("total_latency_ms"),
                    "l3_status": (data.get("l3") or {}).get("status"),
                    "source": data.get("__source") or "production",
                    "round_ids": ["R1"],
                    "latest_round": "R1",
                    "refine_count": 0,
                })
            seen_sids.add(sid)
        except Exception as e:
            corrupt += 1
            logger.warning("list_traces_v3 skipped %s/%s: %s: %s",
                           layout, sid, type(e).__name__, e)
            continue
        if len(items) >= limit:
            break

    return items, corrupt

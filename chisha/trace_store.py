"""D-079: 推荐链路 trace 持久化层.

存储位置: logs/recommend_trace/{session_id}.json (sandbox → logs/sandbox/recommend_trace/)
一次推荐一个文件, **不写 jsonl** (单行膨胀难调试).
单文件硬上限 300KB (超过按 §10 优先级裁剪).

设计原则 (D-079 决策 + Codex review 闭环):
- best-effort 写盘: 失败 logger.warning, 不阻断 recommend (同 feedback_store)
- fail-closed 读盘: 损坏抛 TraceCorrupt + 备份 .corrupt.{ts}.bak (同 D-066/067 MED-3)
- 自包含 trace: __frozen 含 ctx + l1_combos + profile_snapshot + l1_prefs_snapshot
  + l2_meal_log_view + today, What-if 重跑零 runtime read
- schema __version=2 (D-083 bumped), 读侧 LEGACY_TRACE_SCHEMA_VERSIONS={1} 兼容;
  完全未知 version 才抛 TraceVersionMismatch (调用方决定 409)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Optional

from chisha import data_root


logger = logging.getLogger(__name__)

TRACE_SCHEMA_VERSION = 2
# D-083: schema v2 加 feedback_view_snapshot + l3.feedback_block_rendered +
# combo.feedback_evidence. 读侧兼容 v1: 这些字段缺省 → 前端兜底空骨架.
# v1 trace 仍可读 (TraceVersionMismatch 不抛, list_traces 不跳过). 写侧总写 v2.
LEGACY_TRACE_SCHEMA_VERSIONS = {1}
# D-079 用户决策: trace 大小不省空间, 调试完整性优先 (Phase 0 单 zone 1260 dishes
# 实测 ~1.3MB 是常态). 这里 50MB 是纯 sanity bound, 防意外/恶意大数据写满磁盘,
# 不是日常裁剪阈值. 正常 trace (<5MB) 直接写, 不走任何裁剪.
MAX_TRACE_BYTES = 50 * 1024 * 1024  # 50MB sanity bound


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
        # D-085: trace 自描述 — 写时记录是否在 sandbox 模式下生成. Lab Replay 不
        # 用读目录就知道. 默认查询过滤掉 sandbox (invariant 4).
        # 老 trace 缺该字段 → 读侧默认 False.
        try:
            from chisha import sandbox as _sandbox
            trace["is_sandbox"] = bool(_sandbox.is_enabled(root))
        except Exception:
            # sandbox state 读取异常不阻断写盘
            trace.setdefault("is_sandbox", False)
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
    # D-083: v2 schema 兼容 v1 读 — v1 trace 缺 feedback_view_snapshot 等新字段,
    # 调用方/前端走空骨架兜底; 写侧总写 v2. 其他未知 version 仍按 mismatch 抛.
    if version != TRACE_SCHEMA_VERSION and version not in LEGACY_TRACE_SCHEMA_VERSIONS:
        raise TraceVersionMismatch(found=version)
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
    include_sandbox: bool = False,
) -> tuple[list[dict], int]:
    """列出最近 N 条 trace meta (不读 full body). 按 mtime desc.

    Args:
        include_sandbox: D-085. False (默认) = 仅 prod trace; True = prod + sandbox
            目录合并扫描, items 里附 `is_sandbox` 字段供 Lab UI 区分. invariant 4:
            默认查询不混 sandbox; Lab 端点显式打开才显示.

    Returns:
        (items, corrupt_count). 损坏的 trace 跳过 (不抛), 仅累计 corrupt_count.

    items 元素 = {session_id, started_at, meal_type, zone, top1_summary,
                  total_latency_ms, l3_status, source, is_sandbox}.
    feedback link 由调用方再 attach (派生字段不存 trace 文件).
    """
    # D-085: 显式指定扫描目录, 不再跟 sandbox.is_enabled 全局状态走.
    dirs: list[Path] = [data_root.recommend_trace_prod_dir(root)]
    if include_sandbox:
        dirs.append(data_root.recommend_trace_sandbox_dir(root))

    # 收集所有候选 path, 按 mtime 排序后取 limit (跨目录 merge)
    paths: list[Path] = []
    for d in dirs:
        if d.exists():
            paths.extend(d.glob("*.json"))
    paths.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    items: list[dict] = []
    corrupt_count = 0
    for p in paths:
        try:
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                corrupt_count += 1
                continue
            version = data.get("__version")
            # D-083: list_traces 也走 v1+v2 兼容. 完全未知 version 才跳过.
            if (version != TRACE_SCHEMA_VERSION
                    and version not in LEGACY_TRACE_SCHEMA_VERSIONS):
                # 版本不匹配的 trace 跳过, 不算 corrupt
                continue
            frozen = data.get("__frozen") or {}
            mt = frozen.get("meal_type") or data.get("l1", {}).get("meal")
            if meal_type and mt != meal_type:
                continue
            top1_summary = _extract_top1_summary(data)
            refine = data.get("refine") or {}
            items.append({
                "session_id": data.get("session_id") or p.stem,
                "started_at": data.get("started_at"),
                "meal_type": mt,
                "zone": frozen.get("zone"),
                "top1_summary": top1_summary,
                "total_latency_ms": data.get("total_latency_ms"),
                "l3_status": (data.get("l3") or {}).get("status"),
                "source": data.get("__source") or "production",
                # D-082: refine 角标 (sidebar 显示 R + tooltip).
                # round2 = True 表示有完整 pipeline trace 可回放; refine_applied
                # 但 round2 = False 表示老 trace 只有 summary.
                "refine_applied": bool(refine.get("applied")),
                "refine_round": refine.get("round"),
                "refine_user_input": refine.get("user_input"),
                "has_round2": bool(data.get("round2")),
                # D-085: sandbox marker (老 trace 缺 → 默认 False).
                "is_sandbox": bool(data.get("is_sandbox", False)),
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

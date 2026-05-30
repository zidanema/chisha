"""D-102 Step2 (Commit B): 把 install 内的旧 user state 一次性迁到 state_root (~/.chisha/).

提案 §B + §已知坑 3: state 默认翻到 `~/.chisha/` 后, 旧 repo 内的 profile / logs /
反馈历史必须搬过去, 否则 app 看不到。安全策略 (接 D-099 "ingest 前快照" + Codex Step2
建议): **复制而非移动** (repo 原数据保留作回滚) → 校验文件数 → 原子写 manifest marker。
非幂等重跑安全 (marker 存在直接 already)。

迁移项 (install_root → state_root):
- profile.yaml                         → profile.yaml
- logs/ 整子树 (meal_log/sessions/feedback/recommend_trace/agent_rounds/sandbox/…) → logs/
- data/feedback_history.jsonl          → feedback_history.jsonl   (D-102 迁出 data/)
- data/long_term_prefs.json            → long_term_prefs.json     (D-102 迁出 data/)

不迁 (install 只读, 留 repo): data/{zone}/ 餐厅菜品库 / profiles/ 方法论 / prompts/ / 代码。

并发边界 (志丹拍板接受, 接 D-099 TOCTOU 先例 + 提案 §已知坑 2): 迁移是**一次性**显式操作
(首次启动 / migrate_state CLI), 单用户顺序工作流下无并发写同一 target。`target.exists()`
检查与 `replace` 之间的 TOCTOU 窗口在此前提下不触发; 真要多进程/多实例并发再上文件锁。
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_NAME = ".state_manifest.json"
MIGRATE_VERSION = 1

# (install 相对路径, state 相对路径). 目录项以 "/" 结尾。
_MIGRATE_MAP: list[tuple[str, str]] = [
    ("profile.yaml", "profile.yaml"),
    ("logs/", "logs/"),
    ("data/feedback_history.jsonl", "feedback_history.jsonl"),
    ("data/long_term_prefs.json", "long_term_prefs.json"),
]

# doctor 用的"是否真有 legacy state"判定.
#
# 不能只靠 profile.yaml 存在判 legacy: bundle 也 ship 一份 profile.yaml 占位模板,
# install_root/profile.yaml 永远存在, 单它作 marker 会误报"profile.yaml 待迁移".
# 改成更严信号集.
#
# Marker 集 (任一命中即 legacy):
#   1. logs/ 子目录非空 (运行过 chisha 必生成 recommend_log / agent_rounds / sandbox)
#   2. data/feedback_history.jsonl 非空 (用过反馈 ≥ 1 次)
#   3. data/long_term_prefs.json 存在 (L1 抽取过偏好)
#   4. profile.yaml 存在且**内容非 template** (含 PII 占位 `<YOUR_NAME>` = 模板; 缺即真数据)
#
# Rule 4 关键: 老的 dev checkout 里 profile.yaml 可能是用户真实数据 (含名字/zone/口味),
# 不含 `<YOUR_NAME>` 占位; 而 ship 出去的 profile.yaml = 占位模板. 所以 "profile.yaml
# 内容含 <YOUR_NAME> 占位 = 模板, 不算 legacy; 内容无占位 = 真个人数据, 算 legacy 触发迁移".
# 反例: dev 用户拉过 repo, profile.yaml 是真数据 + 从未跑过 chisha
# (无 logs/feedback/prefs) — 单靠 1-3 漏判, Rule 4 兜底.
_PROFILE_TEMPLATE_MARKER = "<YOUR_NAME>"   # A.2 占位字段 (与 profile.yaml 顶层一致)


def has_legacy_state(install_root: Path) -> bool:
    """更严的 legacy 判定 (doctor 用): 至少一个 non-trivial state 标志才算 legacy."""
    logs_dir = install_root / "logs"
    if logs_dir.is_dir() and any(logs_dir.iterdir()):
        return True
    fb = install_root / "data" / "feedback_history.jsonl"
    if fb.is_file() and fb.stat().st_size > 0:
        return True
    if (install_root / "data" / "long_term_prefs.json").is_file():
        return True
    # Rule 4: profile.yaml 内容非 template = 真个人数据未迁 (codex P1#1 反例兜底).
    profile = install_root / "profile.yaml"
    if profile.is_file():
        try:
            content = profile.read_text(encoding="utf-8")
        except OSError:
            return False  # 读不了视作不存在, 不当 legacy
        if _PROFILE_TEMPLATE_MARKER not in content:
            return True
    return False


@dataclass
class MigrateResult:
    status: str                       # already / migrated / nothing_to_migrate / dry_run
    state_root: Path
    copied: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    file_count: int = 0


def _count_files(p: Path) -> int:
    if p.is_file():
        return 1
    return sum(1 for x in p.rglob("*") if x.is_file())


def _merge_copy_dir(src: Path, dst: Path) -> int:
    """把 src 子树里 dst 缺失的文件拷过去, **不覆盖** dst 已有的。返回新拷文件数。

    用于 dst 目录已存在的合并迁移 (防整目录 skip 丢旧日志, 也防 clobber 用户新数据)。
    每文件 staging + 原子 rename: 中途中断只留 `.migrating.*` 孤儿 (非 target) → 重跑因
    target 不存在重拷 → 永不把半文件当迁完 (Codex review: copy2 直写 target 无原子保护)。
    rename 本身即"完整或不存在"保证, 不做 size 校验 (空文件如 feedback_history.jsonl 合法 0 字节)。
    """
    import uuid as _uuid
    copied = 0
    for item in src.rglob("*"):
        if not item.is_file():
            continue
        target = dst / item.relative_to(src)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.migrating.{_uuid.uuid4().hex}")
        shutil.copy2(item, tmp)
        tmp.replace(target)        # 同目录 → 同盘原子
        copied += 1
    return copied


def _manifest_path(state_root: Path) -> Path:
    return state_root / MANIFEST_NAME


def is_migrated(state_root: Path) -> bool:
    return _manifest_path(state_root).exists()


def _plan_dry_run(plan: list, result: MigrateResult) -> None:
    """dry_run: 列出将拷/将跳, 不落任何文件。"""
    for src, dst, _is_dir in plan:
        (result.skipped_existing if dst.exists() else result.copied).append(
            f"{src} → {dst}"
        )
        if not dst.exists():
            result.file_count += _count_files(src)


def _migrate_dir(src: Path, dst: Path, result: MigrateResult) -> None:
    """目录迁移: dst 已存在则逐文件合并 (不覆盖); 否则 staging+原子 rename+文件数校验。"""
    if dst.exists():
        # 目录已存在 (如 ~/.chisha/logs 被先前运行创建): **逐文件合并** — 只拷 dst
        # 缺失的, 绝不覆盖已有 → 旧 repo 日志不丢, 用户在 state_root 的新数据也不被
        # clobber (Codex review 新 BLOCKING: 整目录 skip 会静默丢旧日志).
        merged = _merge_copy_dir(src, dst)
        if merged:
            result.copied.append(f"{src} → {dst} (merged {merged} 文件)")
        else:
            result.skipped_existing.append(f"{src.name}/ (已全在, 无缺失)")
        result.file_count += merged
        return
    # dst 不存在: staging + 原子 rename + 文件数校验 (中断只留 .migrating 残件,
    # 重跑先清再拷 → 永不把半拷贝当成功; 不符则 fail-loud 不写 marker, Q-A).
    staging = dst.with_name(dst.name + ".migrating")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(src, staging)
    src_n, dst_n = _count_files(src), _count_files(staging)
    if src_n != dst_n:
        shutil.rmtree(staging)
        raise RuntimeError(
            f"迁移校验失败 {src} → {dst}: 源 {src_n} vs 拷贝 {dst_n}; "
            "已清理残件, 未写 marker. 重跑迁移."
        )
    staging.replace(dst)        # staging/dst 同在 state_root → 同盘原子
    result.copied.append(f"{src} → {dst}")
    result.file_count += dst_n


def _migrate_file(src: Path, dst: Path, result: MigrateResult) -> None:
    """文件迁移: dst 已存在则跳过 (不覆盖); 否则 staging+原子 rename。"""
    if dst.exists():
        result.skipped_existing.append(f"{src.name} (state_root 已存在, 不覆盖)")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    staging = dst.with_name(dst.name + ".migrating")
    if staging.exists():
        staging.unlink()
    shutil.copy2(src, staging)
    staging.replace(dst)
    result.copied.append(f"{src} → {dst}")
    result.file_count += 1


def migrate_state(
    install_root: Path,
    state_root: Path,
    *,
    dry_run: bool = False,
) -> MigrateResult:
    """install_root 内旧 state → state_root。复制 (不删源), 校验, 写 marker。幂等。

    - state_root 已有 manifest → status=already (不重复迁)。
    - 已存在的目标项**不覆盖** (skipped_existing), 防二次迁覆盖用户在 state_root 的新数据。
    """
    install_root = Path(install_root)
    state_root = Path(state_root)

    if is_migrated(state_root):
        return MigrateResult(status="already", state_root=state_root)

    plan: list[tuple[Path, Path, bool]] = []   # (src, dst, is_dir)
    for rel_src, rel_dst in _MIGRATE_MAP:
        is_dir = rel_src.endswith("/")
        src = install_root / rel_src.rstrip("/")
        dst = state_root / rel_dst.rstrip("/")
        if not src.exists():
            continue
        plan.append((src, dst, is_dir))

    if not plan:
        return MigrateResult(status="nothing_to_migrate", state_root=state_root)

    result = MigrateResult(status="dry_run" if dry_run else "migrated",
                           state_root=state_root)
    if dry_run:
        _plan_dry_run(plan, result)
        return result

    state_root.mkdir(parents=True, exist_ok=True)
    for src, dst, is_dir in plan:
        if is_dir:
            _migrate_dir(src, dst, result)
        else:
            _migrate_file(src, dst, result)

    # 原子写 manifest marker (最后, 复制+校验通过后才落 → 中断不会误判已迁)
    manifest = {
        "version": MIGRATE_VERSION,
        "migrated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_install_root": str(install_root.resolve()),
        "copied": result.copied,
        "skipped_existing": result.skipped_existing,
        "file_count": result.file_count,
    }
    tmp = _manifest_path(state_root).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(_manifest_path(state_root))
    return result

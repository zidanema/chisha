"""D-077 PR-1b: 业务数据路径派生 — sandbox 启用时落 logs/sandbox/.

设计原则 (志丹拍板 #3):
sandbox 关闭时, 所有路径 = prod 默认; 启用时, **业务数据**全部落
logs/sandbox/ 子目录, prod 数据零污染.

7 个落盘点:
| key                  | prod 默认                       | sandbox            |
|----------------------|----------------------------------|---------------------|
| meal_log_path        | logs/meal_log.jsonl             | logs/sandbox/meal_log.jsonl |
| sessions_dir         | logs/sessions/                  | logs/sandbox/sessions/ |
| feedback_store_path  | logs/feedback/store.json        | logs/sandbox/feedback/store.json |
| recommend_log_path   | logs/recommend_log.jsonl        | logs/sandbox/recommend_log.jsonl |
| feedback_history_path | data/feedback_history.jsonl    | logs/sandbox/feedback_history.jsonl |
| long_term_prefs_path | data/long_term_prefs.json       | logs/sandbox/long_term_prefs.json |
| profile_path         | profile.yaml                    | logs/sandbox/profile.yaml (copy-on-init by PR-1c) |

只读数据不动:
- data/{zone}/restaurants.jsonl / tagged_dishes.jsonl (餐厅 / 菜品库)
- profiles/methodologies/*.yaml (方法论 spec 库)
- prompts/*.md

调用约定:
- 所有业务模块走 chisha.data_root.*, 不再 hardcode "logs/meal_log.jsonl"
- 调用方可显式传 root (测试 + 多 worktree 隔离), None 走真实 project root
- profile_path 在 sandbox 启用 + 副本不存在时降级到 prod (copy 失败兜底)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from chisha import sandbox


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_root(root: Optional[Path]) -> Path:
    return root or _project_root()


def _maybe_sandbox(root: Path, rel_in_sandbox: str, rel_in_prod: str) -> Path:
    """sandbox 启用时返沙盒子路径, 否则 prod 路径."""
    if sandbox.is_enabled(root):
        return root / "logs" / "sandbox" / rel_in_sandbox
    return root / rel_in_prod


# ────────────────────────── 7 个落盘点
def meal_log_path(root: Optional[Path] = None) -> Path:
    r = _resolve_root(root)
    return _maybe_sandbox(r, "meal_log.jsonl", "logs/meal_log.jsonl")


def sessions_dir(root: Optional[Path] = None) -> Path:
    r = _resolve_root(root)
    return _maybe_sandbox(r, "sessions", "logs/sessions")


def feedback_store_path(root: Optional[Path] = None) -> Path:
    r = _resolve_root(root)
    return _maybe_sandbox(
        r, "feedback/store.json", "logs/feedback/store.json"
    )


def recommend_log_path(root: Optional[Path] = None) -> Path:
    r = _resolve_root(root)
    return _maybe_sandbox(r, "recommend_log.jsonl", "logs/recommend_log.jsonl")


def feedback_history_path(root: Optional[Path] = None) -> Path:
    """D-043 deprecated jsonl, 但 bootstrap 脚本仍读. sandbox 也支持."""
    r = _resolve_root(root)
    return _maybe_sandbox(
        r, "feedback_history.jsonl", "data/feedback_history.jsonl"
    )


def long_term_prefs_path(root: Optional[Path] = None) -> Path:
    r = _resolve_root(root)
    return _maybe_sandbox(
        r, "long_term_prefs.json", "data/long_term_prefs.json"
    )


def recommend_trace_dir(root: Optional[Path] = None) -> Path:
    """D-079: 推荐链路 trace 落盘目录. 一次推荐一个 {sid}.json 文件.

    sandbox 启用 → logs/sandbox/recommend_trace/, prod → logs/recommend_trace/.
    复用 _maybe_sandbox 模式, 与其他 7 个落盘点一致.
    """
    r = _resolve_root(root)
    return _maybe_sandbox(r, "recommend_trace", "logs/recommend_trace")


def profile_path(root: Optional[Path] = None) -> Path:
    """sandbox 启用且副本存在时返沙盒副本; 否则 prod profile.yaml.

    PR-1c sandbox init(copy_real_data=True) 时把 prod profile.yaml 拷贝
    到 logs/sandbox/profile.yaml. 启用 sandbox 但用户没 copy → 仍读 prod
    (只读用例 ok); 用户在 sandbox 内 PUT profile → 写 sandbox 副本.
    """
    r = _resolve_root(root)
    if sandbox.is_enabled(r):
        sandboxed = r / "logs" / "sandbox" / "profile.yaml"
        if sandboxed.exists():
            return sandboxed
    return r / "profile.yaml"

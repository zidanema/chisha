"""T-DIST-01 B.7 跟修 (codex P1#2): wheel content gate CI 门禁.

防 pyproject.toml [tool.hatch.build.targets.wheel.force-include] / exclude 配置静默
漂移 — 改 pyproject 后这个测试跑一遍能立刻发现关键资源漏包 / 离线打标中间产物
混入 wheel 等问题. 本测试需要 hatchling build 工具 (uv build / python -m build).

测试形态: build wheel → unzip 列表 → 断言 positive/negative.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# 正向: wheel 必须包含这些文件 (runtime 真消费). 改 force-include 时这份列表同步.
_POSITIVE = [
    "chisha/profile.yaml",  # onboard 模板
    "chisha/prompts/rerank_system.md",
    "chisha/prompts/parse_refine_intent_v2.md",
    "chisha/prompts/l1_extract.md",
    "chisha/prompts/parse_feedback.md",
    "chisha/prompts/tag_dishes.md",
    "chisha/profiles/methodologies/harvard_plate.yaml",
    "chisha/data/manifest.json",
    "chisha/data/aliases.json",
    "chisha/data/shenzhen-bay/restaurants.json",
    "chisha/data/shenzhen-bay/dishes_tagged.json",
]

# 负向: 这些 path 前缀 / 文件名绝不许出现在 wheel.
_NEGATIVE_PREFIXES = ("apps/", "plans/", "docs/", "tmp/", "logs/", "eval/",
                      "tests/", "scripts/", ".claude/", "design/")
_NEGATIVE_BASENAMES = ("dishes_raw.json", "review_sample.md", "review_sample.xlsx",
                       "conflicts_ack.json", "non_dish_quarantine.json",
                       "dish_id_conflicts.json", "feedback_history.jsonl",
                       "long_term_prefs.json")


@pytest.fixture(scope="module")
def built_wheel_names() -> set[str]:
    """build wheel 到临时目录, 返回所有 entry 名 set.

    scope=module 让同一测试模块所有 case 共享 build (一次 ~5s).
    """
    with tempfile.TemporaryDirectory(prefix="chisha-wheel-gate-") as tmpdir:
        out_dir = Path(tmpdir)
        # 用 uv build (项目首选). subprocess 隔离防 hatchling state 串扰.
        r = subprocess.run(
            ["uv", "build", "--out-dir", str(out_dir), "--wheel"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
        )
        assert r.returncode == 0, f"uv build failed: {r.stderr}"
        wheels = list(out_dir.glob("chisha_meal-*.whl"))
        assert len(wheels) == 1, f"expected 1 wheel, got {wheels}"
        with zipfile.ZipFile(wheels[0]) as zf:
            return set(zf.namelist())


@pytest.mark.parametrize("required", _POSITIVE)
def test_wheel_contains_required(built_wheel_names, required):
    """wheel 必须含每个 runtime 消费资源."""
    assert required in built_wheel_names, (
        f"wheel 缺关键资源 {required!r} — 改 pyproject force-include 后是否漏配?"
    )


def test_wheel_excludes_dev_artifacts(built_wheel_names):
    """wheel 不许含 dev 资产 (apps/plans/docs/tmp/logs/eval/tests/scripts/.claude/design)."""
    leaks = [n for n in built_wheel_names
             if any(n.startswith(p) for p in _NEGATIVE_PREFIXES)]
    assert not leaks, f"wheel 漏 dev 资产: {leaks[:10]}"


def test_wheel_excludes_offline_pipeline_artifacts(built_wheel_names):
    """wheel 不许含离线打标中间产物 (dishes_raw 4.7MB / review_sample / conflicts_ack /
    non_dish_quarantine / dish_id_conflicts) 或用户 state (feedback_history /
    long_term_prefs).
    """
    leaks = [n for n in built_wheel_names
             if Path(n).name in _NEGATIVE_BASENAMES]
    assert not leaks, f"wheel 漏离线打标 / user state 产物: {leaks}"


def test_wheel_has_chisha_executable_script(built_wheel_names):
    """[project.scripts] chisha = 'chisha.cli:main' 必须在 wheel METADATA 注册."""
    # wheel 用 entry_points.txt 描述 console scripts.
    ep_files = [n for n in built_wheel_names if n.endswith("entry_points.txt")]
    assert ep_files, f"wheel 缺 entry_points.txt: {sorted(built_wheel_names)[-5:]}"

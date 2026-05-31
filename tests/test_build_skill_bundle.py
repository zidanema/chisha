"""D-105 形态B: build_skill_bundle installer 回归.

覆盖 bundle 自包含契约: cli.py 在场 (wrapper dispatch 目标) / vendored pyyaml /
可执行 wrapper 带 py>=3.11 guard / profile.yaml 模板 / B 形态 SKILL.md / 零 pydantic
真 import / SLIM_DEPS 收敛。隔离全链路实跑见 docs spec §8 (裸 python3, 手动 gate)。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# scripts/ 不是包 → 按路径加载 build_skill_bundle 模块
_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "build_skill_bundle", _REPO / "scripts" / "build_skill_bundle.py"
)
bsb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bsb)


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp("bundle_root") / "skill_bundle"
    info = bsb.build(_REPO, out)
    return out, info


def test_cli_included(bundle):
    """D-105: cli.py 从 EXTRAS 移回 — wrapper dispatch chisha.cli:main 需要它。"""
    out, info = bundle
    assert (out / "chisha" / "cli.py").is_file()
    assert "cli.py" not in info["skipped"]
    assert "cli.py" not in bsb.EXTRAS_MODULES


def test_vendored_pyyaml(bundle):
    out, info = bundle
    assert (out / "vendor" / "yaml" / "__init__.py").is_file()
    assert info["yaml_version"] != "unknown"
    # C 扩展不拷 (运行时走纯 Python path)
    assert not list((out / "vendor" / "yaml").glob("*.so"))


def test_wrapper_executable_with_guard(bundle):
    out, _ = bundle
    wrapper = out / "scripts" / "chisha"
    assert wrapper.is_file()
    assert wrapper.stat().st_mode & 0o111, "wrapper 必须可执行"
    src = wrapper.read_text(encoding="utf-8")
    assert "sys.version_info < (3, 11)" in src       # py>=3.11 硬 guard
    assert "vendor" in src and "chisha.cli" in src   # sys.path 注入 + dispatch


def test_profile_template_present(bundle):
    out, _ = bundle
    p = out / "profile.yaml"
    assert p.is_file()
    # 是占位模板 (onboard 渲染源), 非真实 profile
    assert "<YOUR_LUNCH_ZONE>" in p.read_text(encoding="utf-8")


def test_skill_md_b_form(bundle):
    out, _ = bundle
    md = (out / "SKILL.md").read_text(encoding="utf-8")
    assert md.startswith("---")
    assert "scripts/chisha" in md
    assert "uv tool install" not in md
    assert "POSIX" in md and "3.11" in md


def test_no_real_pydantic_import_in_bundle(bundle):
    """bundle 内 core 任何 .py 不得真 import pydantic (docstring 提及 pydantic 不算)。"""
    out, _ = bundle
    offenders = []
    for py in (out / "chisha").rglob("*.py"):
        for ln in py.read_text(encoding="utf-8").splitlines():
            s = ln.lstrip()
            if s.startswith(("import pydantic", "from pydantic")):
                offenders.append(f"{py.name}: {s}")
    assert not offenders, f"bundle 残留 pydantic import: {offenders}"


def test_slim_deps_converged():
    """SLIM_DEPS 收敛到 pyyaml only (砍 pydantic/dotenv/tenacity/ruamel)。"""
    joined = " ".join(bsb.SLIM_DEPS).lower()
    assert "pyyaml" in joined
    for gone in ("pydantic", "dotenv", "tenacity", "ruamel"):
        assert gone not in joined


def test_atomic_install_backs_up(tmp_path):
    """--install staged 覆盖时备份旧内容 (回滚用; copy-to-temp-first + rename swap)。"""
    staging = tmp_path / "staging"
    bsb.build(_REPO, staging)
    target = tmp_path / "skills" / "chisha"
    # first install — no backup
    r1 = bsb.atomic_install(staging, target)
    assert r1["backup"] is None
    assert (target / "SKILL.md").is_file()
    # second install — 旧内容备份
    staging2 = tmp_path / "staging2"
    bsb.build(_REPO, staging2)
    r2 = bsb.atomic_install(staging2, target)
    assert r2["backup"] is not None
    assert Path(r2["backup"]).is_dir()
    assert (Path(r2["backup"]) / "SKILL.md").is_file()

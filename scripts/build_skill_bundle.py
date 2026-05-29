"""D-105 形态B: 把 agent-only core 切成**自包含、拷贝即用**的 skill bundle 并安装。

形态B (替代形态A 当默认接入): 一个 skill 文件夹 = core 代码 + 数据 + vendored pyyaml +
wrapper + SKILL.md, 拷进 `~/.claude/skills/chisha-meal/` 即被宿主 agent 驱动, **零全局
安装、运行期零联网、零 pydantic** (唯一第三方依赖 pyyaml 已 vendored)。

产物布局 (install_root() 靠 prompts/ 与 chisha/ 同级感知 bundle, 必须保持):
    ~/.claude/skills/chisha-meal/
      chisha/            # core 子树 (含 cli.py — D-105 从排除清单移回, 是 wrapper dispatch 目标)
      vendor/yaml/       # vendored 纯 Python pyyaml (运行时缺 _yaml C 扩展走纯 Python path)
      data/              # restaurants + dishes_tagged + manifest + aliases
      prompts/ profiles/ # 与 chisha/ 同级 (install_root 探测点)
      profile.yaml       # onboard 用的 PII 占位模板 (= repo profile.yaml)
      scripts/chisha     # python3 运行入口 wrapper (py>=3.11 guard + sys.path 注入 + dispatch)
      SKILL.md           # 形态B 交互层 (单一源 = chisha.agent_skill_init._claude_code_skill_md)
      requirements.txt   # provenance only (vendored, 无需 pip install)

POSIX-only (macOS / Linux): core 的 recall/trace_store/agent_round_store 用 fcntl 文件锁,
Windows 不支持 (除非 WSL)。SKILL.md / doctor 显式声明此限制。

用法:
    # 仅 staging (不安装):
    uv run python -m scripts.build_skill_bundle --out tmp/skill_bundle
    # staging + 原子安装到 ~/.claude/skills/chisha-meal/ (备份旧内容):
    uv run python -m scripts.build_skill_bundle --out tmp/skill_bundle --install

排除清单依据 D-104 core/extras 边界 (sandbox_context / sandbox_router 是 CORE 保留)。
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

# core 子树排除的 extras 模块 (sandbox_context / sandbox_router 是 core, 不在此列)。
# D-105: cli.py 从排除清单移除 —— 形态B wrapper dispatch 到 chisha.cli:main, 排除则
# ModuleNotFoundError; cli.py 实为形态B 入口 (其 import 全是 kept core 模块)。
EXTRAS_MODULES = {
    # sandbox 调试工具 (time-travel)
    "sandbox.py", "sandbox_adapter.py", "sandbox_migration.py", "sandbox_decision_diff.py",
    # web / debug 台
    "web_api.py", "debug_server.py", "debug_recommend.py", "debug_what_if.py",
    # 自调 LLM (host agent 外置, core 不需要)
    "llm_client.py", "llm_client_openrouter.py",
    # 老 / 被取代 (D-096 等); schemas.py 仍 import pydantic, core 不消费
    "refine.py", "feedback.py", "l1_extractor.py", "schemas.py",
    # recommend_meal 全链路 (agent 用 core_api_helpers + 最小功能 trace, 见 D-104 Step1b)
    "api.py",
}
EXTRAS_DIRS = {"llm_providers", "static", "__pycache__"}

# D-105: core 运行期唯一第三方依赖 = pyyaml, 且已 vendored → bundle 运行期零 pip install。
# requirements.txt 仅作 provenance (记录 vendored 版本)。SLIM_DEPS 收敛掉 pydantic /
# python-dotenv / tenacity / ruamel-yaml (core 闭包零 import, 砍 pydantic 后更是虚列)。
SLIM_DEPS = ["pyyaml>=6.0"]

# install_root() 探测 prompts/ 与 chisha/ 同级 → 资源放 bundle 根 (复刻 dev 布局)
RESOURCE_DIRS = ["prompts", "profiles"]
# recall 真消费 + D-102 manifest/aliases 闸门 (依 pyproject force-include 口径)
DATA_FILES = [
    "data/manifest.json",
    "data/aliases.json",
    "data/shenzhen-bay/restaurants.json",
    "data/shenzhen-bay/dishes_tagged.json",
]
# D-105: onboard cmd_onboard 读 install_root/profile.yaml 作模板 (repo profile.yaml 是
# PII 占位模板 <YOUR_NAME>/<YOUR_LUNCH_ZONE>...; 当前 builder 漏拷, 补上)。
PROFILE_TEMPLATE = "profile.yaml"

SKILL_DIR_NAME = "chisha-meal"

# wrapper: python3 入口。注入顺序 = bundle_root (chisha 包) → bundle/vendor (vendored
# yaml) → 原有 paths; 注入必须早于 import chisha (recall/methodology 顶层 import yaml)。
WRAPPER_SRC = '''#!/usr/bin/env python3
"""chisha 形态B 自包含 bundle 运行入口 (D-105)。由 scripts/build_skill_bundle.py 生成。

职责按序: (1) python>=3.11 硬 guard (给清晰报错, 不是裸 import traceback);
(2) 注入 sys.path: bundle_root 给 `chisha` 包, bundle/vendor 给 vendored `yaml`,
都排在原有 path 之前 (vendored 优先, 防 host site-packages 漂移);
(3) dispatch 到 chisha.cli:main。注入早于 import chisha (recall/methodology 顶层 import yaml)。
"""
import sys

if sys.version_info < (3, 11):
    sys.stderr.write(
        "chisha 需要 python3 >= 3.11, 当前 {}.{}。\\n"
        "macOS 自带 python3 是 3.9, 不够 — 请装 3.11+ 并确保在 PATH:\\n"
        "  brew install python@3.12   或   pyenv install 3.12   或   uv python install 3.12\\n"
        "然后用那个 python3 跑本 wrapper。\\n".format(
            sys.version_info[0], sys.version_info[1]
        )
    )
    raise SystemExit(2)

from pathlib import Path

_BUNDLE = Path(__file__).resolve().parent.parent  # scripts/chisha → bundle 根
sys.path.insert(0, str(_BUNDLE / "vendor"))  # vendored yaml
sys.path.insert(0, str(_BUNDLE))             # chisha 包 (排在 vendor 之前)

from chisha.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
'''


def _b_form_skill_md() -> str:
    """单一源: 复用 chisha.agent_skill_init._claude_code_skill_md() (形态B SKILL.md)。

    builder 跑在 repo 下, chisha 包可达 → 延迟 import 取共同源, 不复制粘贴 SKILL 文本。
    """
    from chisha.agent_skill_init import _claude_code_skill_md
    return _claude_code_skill_md()


def vendor_pyyaml(out: Path) -> str:
    """把当前环境的纯 Python pyyaml 拷进 out/vendor/yaml/。返回版本号。

    pyyaml 的 `yaml/` 包是纯 Python; C 扩展 `_yaml` 是独立包 (不拷)。运行时缺 _yaml →
    PyYAML 走纯 Python path (__with_libyaml__=False), safe_load 正常 (D-105 隔离实跑验证)。
    """
    import yaml
    src = Path(yaml.__file__).resolve().parent
    dst = out / "vendor" / "yaml"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.so"))
    return getattr(yaml, "__version__", "unknown")


def build(repo: Path, out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    pkg_out = out / "chisha"
    pkg_out.mkdir(parents=True)

    kept, skipped = [], []
    pkg_src = repo / "chisha"
    for p in sorted(pkg_src.glob("*.py")):
        if p.name in EXTRAS_MODULES:
            skipped.append(p.name)
            continue
        shutil.copy2(p, pkg_out / p.name)
        kept.append(p.name)
    # core 子目录 (排除 extras dirs); 当前 core 无子包, 留作前向兼容
    for d in sorted(x for x in pkg_src.iterdir() if x.is_dir()):
        if d.name in EXTRAS_DIRS:
            continue
        shutil.copytree(d, pkg_out / d.name, ignore=shutil.ignore_patterns("__pycache__"))

    for rd in RESOURCE_DIRS:
        src = repo / rd
        if src.exists():
            shutil.copytree(src, out / rd, ignore=shutil.ignore_patterns("__pycache__"))
    for df in DATA_FILES:
        src = repo / df
        dst = out / df
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # D-105: profile.yaml 模板 (onboard 渲染源)
    shutil.copy2(repo / PROFILE_TEMPLATE, out / "profile.yaml")

    # D-105: vendoring pyyaml
    yaml_ver = vendor_pyyaml(out)

    # D-105: wrapper (python3, 可执行)
    scripts_out = out / "scripts"
    scripts_out.mkdir(parents=True, exist_ok=True)
    wrapper = scripts_out / "chisha"
    wrapper.write_text(WRAPPER_SRC, encoding="utf-8")
    wrapper.chmod(0o755)

    # requirements.txt: provenance only (vendored, 运行期零 install)
    (out / "requirements.txt").write_text(
        "# D-105 形态B: 运行期**零 pip install** — pyyaml 已 vendored 进 vendor/yaml/。\n"
        "# 本文件仅记录逻辑依赖 provenance + vendored 版本, 拷贝即用无需 pip。\n"
        + "\n".join(SLIM_DEPS) + f"\n# vendored pyyaml == {yaml_ver}\n",
        encoding="utf-8",
    )
    (out / "SKILL.md").write_text(_b_form_skill_md(), encoding="utf-8")

    return {"kept": kept, "skipped": skipped, "yaml_version": yaml_ver}


def _unique_sibling(target: Path, suffix: str) -> Path:
    n = 0
    while True:
        cand = target.with_name(target.name + f"{suffix}{n}")
        if not cand.exists():
            return cand
        n += 1


def atomic_install(staging: Path, target: Path) -> dict:
    """把 staging bundle staged-安装到 target (~/.claude/skills/chisha-meal/), 备份旧内容。

    **staged install + best-effort 回滚** (非 OS 级单原子 swap — Codex review #2):
    **先** copytree staging → target 的临时兄弟目录 (.new.<n>, 慢/易失败的一步, 此时 live
    target 完全不动 → 拷贝失败/中断不损坏现有 skill) → 再 rename 旧 target 到 .bak.<n>
    (同目录, 单 rename 原子) → 再 rename 临时目录到 target (同目录, 单 rename 原子)。Python
    异常会回滚已 mv 的 backup + 清临时目录。
    **残留窗口 (诚实边界)**: 两次 rename 之间若进程被杀/断电/并发 reader, 可能瞬时观察不到
    target (POSIX 无可移植的目录 swap 原语; renameat2 RENAME_EXCHANGE 仅 Linux)。窗口是两个
    相邻元数据操作, 实践可忽略; 真挂了 .bak.<n> 仍在 → 手动 mv 回来即恢复。
    临时目录与 target 同父 (同文件系统) 保证 os.rename 不退化为跨 fs copy; staging 可在别的 fs。
    """
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_new = _unique_sibling(target, ".new.")
    # 1. 慢且易失败的拷贝先落到临时兄弟目录 — 失败时 live target 原封不动。
    shutil.copytree(staging, tmp_new)
    backup = None
    try:
        # 2. 旧 target → backup (同目录 rename, 原子)。
        if target.exists():
            backup = _unique_sibling(target, ".bak.")
            os.rename(target, backup)
        # 3. 临时目录 → target (同目录 rename, 原子)。
        os.rename(tmp_new, target)
    except Exception:
        # 回滚: 恢复 backup, 清临时目录。
        if backup is not None and not target.exists():
            os.rename(backup, target)
        shutil.rmtree(tmp_new, ignore_errors=True)
        raise
    return {"target": str(target), "backup": str(backup) if backup else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tmp/skill_bundle", help="staging bundle 输出目录")
    ap.add_argument("--install", action="store_true",
                    help="staged 安装到 ~/.claude/skills/chisha-meal/ (copy-to-temp-first + 备份旧内容)")
    ap.add_argument("--target", default=None,
                    help="--install 目标目录 (默认 ~/.claude/skills/chisha-meal/; 测试注入)")
    args = ap.parse_args()
    repo = Path(__file__).resolve().parent.parent
    out = (Path.cwd() / args.out).resolve()
    info = build(repo, out)
    print(f"[ok] bundle → {out}")
    print(f"  core 模块 {len(info['kept'])} 个; 排除 extras {len(info['skipped'])} 个:")
    print(f"  excluded: {', '.join(info['skipped'])}")
    print(f"  vendored pyyaml == {info['yaml_version']}")
    if args.install:
        target = (Path(args.target).expanduser() if args.target
                  else Path.home() / ".claude" / "skills" / SKILL_DIR_NAME)
        res = atomic_install(out, target)
        print(f"[ok] installed → {res['target']}")
        if res["backup"]:
            print(f"  旧内容备份 → {res['backup']} (回滚: 删 target 后 mv backup 回来)")
    else:
        print("  (未 --install; 仅 staging。加 --install 落 ~/.claude/skills/chisha-meal/)")


if __name__ == "__main__":
    main()

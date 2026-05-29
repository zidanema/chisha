"""D-104 Step5: 把 agent-only core 切成可分发 skill bundle (slim, 零 extras).

切法: 拷 chisha/ 的 **core 子树** (排除 sandbox / web / debug / 自调LLM / 老模块) +
运行时数据资源 (restaurants + dishes_tagged + prompts + profiles + manifest + aliases) +
slim requirements.txt。产物布局复刻 dev 形态 (prompts/ 与 chisha/ 同级), 让
install_root() 命中。

用途: **验证解耦真能跑** —— 隔离 venv 装 slim deps 跑 agent 全链路。不是 marketplace
打包 / 产物签名 (那在 CLAUDE.md 范围红线外)。

排除清单依据 proposal §3 core/extras 边界 (D-104 调研校正后):
- sandbox_context / sandbox_router 是 CORE (保留); sandbox.py 及 sandbox_* extras 排除。
- 已 grep 确认: 无 core 模块 top-level import 任何被排除模块 (只被 extras 自身引用)。

用法:
    uv run python -m scripts.build_skill_bundle --out tmp/skill_bundle
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

# core 子树排除的 extras 模块 (sandbox_context / sandbox_router 是 core, 不在此列)
EXTRAS_MODULES = {
    # sandbox 调试工具 (time-travel)
    "sandbox.py", "sandbox_adapter.py", "sandbox_migration.py", "sandbox_decision_diff.py",
    # web / debug 台
    "web_api.py", "debug_server.py", "debug_recommend.py", "debug_what_if.py",
    # 自调 LLM (host agent 外置, core 不需要)
    "llm_client.py", "llm_client_openrouter.py",
    # 老 / 被取代 (D-096 等)
    "cli.py", "refine.py", "feedback.py", "l1_extractor.py", "schemas.py",
    # recommend_meal 全链路 (agent 用 core_api_helpers + 最小功能 trace, 见 D-104 Step1b)
    "api.py",
}
EXTRAS_DIRS = {"llm_providers", "static", "__pycache__"}

SLIM_DEPS = [
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "python-dotenv>=1.2.2",
    "tenacity>=9.1.4",
    "ruamel-yaml>=0.19.1",
]

# install_root() 探测 prompts/ 与 chisha/ 同级 → 资源放 bundle 根 (复刻 dev 布局)
RESOURCE_DIRS = ["prompts", "profiles"]
# recall 真消费 + D-102 manifest/aliases 闸门 (依 pyproject force-include 口径)
DATA_FILES = [
    "data/manifest.json",
    "data/aliases.json",
    "data/shenzhen-bay/restaurants.json",
    "data/shenzhen-bay/dishes_tagged.json",
]

SKILL_MD = """# chisha agent-only core (D-104 slim bundle)

零 LLM / 零 sandbox / 零 web 的 AI-friendly 点餐推荐核心。宿主 agent 经
`python -m chisha.agent_cli` 驱动 (start → continue → choose → refine), LLM 外置给宿主。

- 依赖: 仅 requirements.txt 的 5 个轻库 (无 fastapi / anthropic / openai / pandas)。
- 数据: data/shenzhen-bay/ (restaurants + dishes_tagged)。
- 此 bundle 由 scripts/build_skill_bundle.py 从 core 子树切出, 用于验证解耦可独立运行。
"""


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

    (out / "requirements.txt").write_text("\n".join(SLIM_DEPS) + "\n", encoding="utf-8")
    (out / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")

    return {"kept": kept, "skipped": skipped}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tmp/skill_bundle")
    args = ap.parse_args()
    repo = Path(__file__).resolve().parent.parent
    out = (Path.cwd() / args.out).resolve()
    info = build(repo, out)
    print(f"[ok] bundle → {out}")
    print(f"  core 模块 {len(info['kept'])} 个; 排除 extras {len(info['skipped'])} 个:")
    print(f"  excluded: {', '.join(info['skipped'])}")


if __name__ == "__main__":
    main()

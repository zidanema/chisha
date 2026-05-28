"""T-DIST-01 B.2: chisha 顶层 CLI (entry point `chisha`).

子命令:
  doctor                       — 检查环境 (delegates to agent_cli.cmd_doctor)
  agent <verb> [args...]       — 透传 agent_cli (start / resolve-intent / apply-rerank /
                                  choose / init / doctor)
  install-skill [--force]      — 写 ~/.claude/skills/chisha-meal/SKILL.md (B.4)
  onboard [--zone] [--methodology] [--force]
                               — 初始化 ~/.chisha/profile.yaml + 装 skill + dry start (B.5)
  migrate-state [--dry-run]    — 把 repo 内旧 state 迁到 ~/.chisha/ (wrap state_migrate)
  methodology {schema|template|validate}
                               — T-DIST-02 占位, 报 NOT_IMPLEMENTED 非零退出

stdout 一律 JSON (machine-readable); 人类提示走 stderr (绝不污染 stdout pipe).
Legacy `python -m chisha.agent_cli` 仍可用 (走 agent_cli.main 直接); 推荐迁到
`chisha agent <verb>` (功能完全等价).
"""
from __future__ import annotations

import argparse
import json
import sys


def _emit(obj: dict) -> None:
    """stdout JSON (machine-readable)."""
    print(json.dumps(obj, ensure_ascii=False))


def _stderr(msg: str) -> None:
    """human-readable hints to stderr — 绝不污染 stdout JSON."""
    print(msg, file=sys.stderr)


# ─────────────────────────────── doctor ───────────────────────────────

def cmd_doctor(args) -> int:
    """delegates to agent_cli.cmd_doctor (单一权威源)."""
    from chisha import agent_cli
    # synthesize ns matching agent_cli expectation; cmd_doctor 不读 scope 字段
    ns = argparse.Namespace(scope=getattr(args, "scope", "production"))
    return agent_cli.cmd_doctor(ns)


# ─────────────────────────────── agent passthrough ────────────────────

def cmd_agent(args, agent_argv: list[str]) -> int:
    """透传 agent_cli.main, 不加 stderr tip (新 CLI 路径)."""
    from chisha import agent_cli
    return agent_cli.main(agent_argv)


# ─────────────────────────────── migrate-state ────────────────────────

def cmd_migrate_state(args) -> int:
    """wrap chisha.state_migrate.migrate_state (NOT scripts.migrate_state, B.2 step 1.5)."""
    from dataclasses import asdict
    from chisha.install_root import install_root
    from chisha import state_migrate, state_root
    ir = install_root()
    sr = state_root.resolve(ir)
    try:
        result = state_migrate.migrate_state(ir, sr, dry_run=getattr(args, "dry_run", False))
    except Exception as e:  # pragma: no cover — wrap any migration failure
        _emit({"ok": False, "error": "MIGRATION_FAILED", "message": str(e)})
        return 1
    payload = asdict(result)
    payload["state_root"] = str(payload["state_root"])
    _emit({"ok": True, **payload})
    return 0


# ─────────────────────────────── install-skill (B.4 stub) ─────────────

def cmd_install_skill(args) -> int:
    """T-DIST-01 B.4: 写 ~/.claude/skills/chisha-meal/SKILL.md.

    单一源: SKILL.md 内容从 `chisha.agent_skill_init._claude_code_skill_md()` 动态生成
    (不 ship 静态文件 — codex Round 2 P2). --force 才覆盖.
    """
    from pathlib import Path
    from chisha.agent_skill_init import init_skill
    from chisha.install_root import install_root
    # init_skill 接受 (agent, root, force=) 并返回退出码; 它落盘到 ~/.claude/skills/...
    return init_skill("claude-code", install_root(), force=getattr(args, "force", False))


# ─────────────────────────────── onboard (B.5 stub) ───────────────────

def cmd_onboard(args) -> int:
    """T-DIST-01 B.5a/b/c: 待 B.5 PR 填充."""
    _emit({
        "ok": False,
        "error": "NOT_IMPLEMENTED",
        "message": "chisha onboard 由 T-DIST-01 B.5 落地, 当前 B.2 仅占位",
        "next": "B.5a/b/c 实施后 enable",
    })
    return 1


# ─────────────────────────────── methodology (T-DIST-02 占位) ─────────

def cmd_methodology(args) -> int:
    """T-DIST-02 待办: schema / template / validate 三 CLI (B.5b 已留 loader API)."""
    _emit({
        "ok": False,
        "error": "NOT_IMPLEMENTED",
        "message": (
            f"chisha methodology {args.action} 由 T-DIST-02 落地. "
            "B.5b 已留 loader API (get_schema_keyset / get_template / validate_spec)."
        ),
        "T-DIST-02 待办": True,
    })
    return 1


# ─────────────────────────────── argparse ─────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="chisha",
        description="今天吃点啥 — 个人 AI 原则派点餐执行外包 (T-DIST-01 顶层 CLI)",
    )
    sub = p.add_subparsers(dest="verb", required=True)

    sp = sub.add_parser("doctor", help="检查 install/state root + manifest + scope")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("agent", help="透传到 agent_cli (start / resolve-intent / ...)")
    sp.add_argument("rest", nargs=argparse.REMAINDER,
                    help="agent_cli 子命令 + 参数, e.g. `chisha agent start --meal lunch`")
    sp.set_defaults(func="_AGENT")  # 由 main 特判 (REMAINDER 不走标准 func)

    sp = sub.add_parser("install-skill", help="装 Claude Code skill 到 ~/.claude/skills/chisha-meal/")
    sp.add_argument("--force", action="store_true", help="覆盖已存在 SKILL.md")
    sp.set_defaults(func=cmd_install_skill)

    sp = sub.add_parser("onboard", help="初始化 profile + skill + dry start")
    sp.add_argument("--zone", default="shenzhen-bay", help="默认 zone (B.5a)")
    sp.add_argument("--methodology", default="harvard_plate", help="默认 methodology (B.5a)")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_onboard)

    sp = sub.add_parser("migrate-state", help="迁 repo 内旧 state → ~/.chisha/")
    sp.add_argument("--dry-run", action="store_true", help="只报告不写")
    sp.set_defaults(func=cmd_migrate_state)

    sp = sub.add_parser("methodology", help="T-DIST-02 占位 (schema/template/validate)")
    sp.add_argument("action", choices=["schema", "template", "validate"])
    sp.add_argument("rest", nargs=argparse.REMAINDER)
    sp.set_defaults(func=cmd_methodology)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # `chisha agent <verb>` 透传走特殊路径 (argparse REMAINDER 保留原 token).
    if args.func == "_AGENT":
        agent_argv = args.rest or []
        return cmd_agent(args, agent_argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

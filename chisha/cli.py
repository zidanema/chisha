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
from pathlib import Path


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
    """T-DIST-01 B.5a: 初始化 ~/.chisha/profile.yaml + 装 skill + doctor 自检.

    步骤:
      1. profile: 从 install_root/profile.yaml template 复制到 state_root/profile.yaml,
         替换 zone 占位 (<YOUR_LUNCH_ZONE> / <YOUR_DINNER_ZONE> → --zone arg).
         已存在 + 无 --force → skip (非错误).
      2. install skill: 落 ~/.claude/skills/chisha-meal/SKILL.md.
      3. doctor: 自检并把 doctor payload 合并进 onboard summary.

    输出: 单条 JSON (machine-readable summary). 人类提示走 stderr.

    B.5b (user-level loader) / B.5c (ephemeral dry start) 在后续 PR 加.
    """
    import contextlib
    import io
    from chisha import agent_cli, state_root
    from chisha.agent_skill_init import init_skill
    from chisha.install_root import install_root

    zone = getattr(args, "zone", "shenzhen-bay")
    methodology_name = getattr(args, "methodology", "harvard_plate")
    force = getattr(args, "force", False)

    install_root_p = install_root()
    state_root_p = state_root.resolve(install_root_p)
    state_root_p.mkdir(parents=True, exist_ok=True)

    summary: dict = {"ok": True, "steps": {}}

    # ─ Step 1: profile ─
    profile_target = state_root_p / "profile.yaml"
    template_path = install_root_p / "profile.yaml"
    if not template_path.exists():
        _emit({
            "ok": False,
            "error": "PROFILE_TEMPLATE_MISSING",
            "message": f"install_root 内缺 profile.yaml template: {template_path}",
        })
        return 1
    if profile_target.exists() and not force:
        summary["steps"]["profile"] = {
            "status": "exists",
            "path": str(profile_target),
            "hint": "已存在, 跳过写入 (用 --force 覆盖)",
        }
        _stderr(f"[onboard] profile 已存在 → {profile_target} (跳过, --force 覆盖)")
    else:
        template = template_path.read_text(encoding="utf-8")
        rendered = (
            template
            .replace("<YOUR_LUNCH_ZONE>", zone)
            .replace("<YOUR_DINNER_ZONE>", zone)
        )
        if methodology_name != "harvard_plate":
            rendered = rendered.replace(
                "methodology: harvard_plate", f"methodology: {methodology_name}"
            )
        profile_target.write_text(rendered, encoding="utf-8")
        summary["steps"]["profile"] = {
            "status": "written",
            "path": str(profile_target),
            "zone": zone,
            "methodology": methodology_name,
        }
        _stderr(f"[onboard] profile 写入 → {profile_target} (zone={zone}, methodology={methodology_name})")

    # ─ Step 2: install skill ─ (capture stdout JSON, 合并进 summary)
    skill_buf = io.StringIO()
    with contextlib.redirect_stdout(skill_buf):
        skill_rc = init_skill("claude-code", install_root_p, force=force)
    try:
        skill_payload = json.loads(skill_buf.getvalue().strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        skill_payload = {"ok": False, "stdout": skill_buf.getvalue()}
    summary["steps"]["skill"] = skill_payload
    if skill_rc != 0:
        # EXISTS 也算 skill_rc != 0, 但不是致命 (用户可以自行选择 --force 重跑); 标 warn 不阻塞 onboard.
        if skill_payload.get("error", {}).get("code") != "EXISTS":
            summary["ok"] = False
        _stderr(f"[onboard] skill 状态: {skill_payload.get('error', {}).get('code', 'unknown')}")
    else:
        _stderr(f"[onboard] skill 写入 → {skill_payload.get('path')}")

    # ─ Step 3: doctor ─ (capture stdout JSON)
    doctor_buf = io.StringIO()
    with contextlib.redirect_stdout(doctor_buf):
        doctor_ns = argparse.Namespace(scope="production")
        doctor_rc = agent_cli.cmd_doctor(doctor_ns)
    try:
        doctor_payload = json.loads(doctor_buf.getvalue().strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        doctor_payload = {"ok": False, "stdout": doctor_buf.getvalue()}
    summary["steps"]["doctor"] = doctor_payload
    if doctor_rc != 0 or not doctor_payload.get("ok"):
        summary["ok"] = False
        _stderr(f"[onboard] doctor 红 — notes: {doctor_payload.get('notes')}")
    else:
        _stderr("[onboard] doctor 绿")

    # ─ Step 4: B.5c ephemeral dry start ─
    # 跑 cmd_start(meal=lunch, context=None) 验链路通 (recall→score→rerank spec).
    # CHISHA_STATE_ROOT 临时钉 tmp 目录: 所有 state (agent_rounds / trace / 任何写入) 落 tmp,
    # 跑完即删, 绝不污染真实 state_root 的 logs/. 复制真 profile.yaml 到 tmp 让 _load_inputs
    # 能读 (zone data 走 install_root 不受影响).
    import os
    import shutil
    import tempfile

    dry_status = "skipped"
    dry_note = ""
    if summary["steps"]["profile"]["status"] in ("written", "exists"):
        with tempfile.TemporaryDirectory(prefix="chisha-dry-") as tmpdir:
            tmp_state = Path(tmpdir)
            try:
                shutil.copy(profile_target, tmp_state / "profile.yaml")
            except OSError as e:
                dry_status = "error"
                dry_note = f"copy profile to tmp failed: {e}"
            else:
                env_backup = os.environ.get("CHISHA_STATE_ROOT")
                os.environ["CHISHA_STATE_ROOT"] = str(tmp_state)
                try:
                    start_ns = argparse.Namespace(
                        scope="ephemeral", meal="lunch", context=None,
                        from_id=None, at_time=None,
                    )
                    start_buf = io.StringIO()
                    with contextlib.redirect_stdout(start_buf):
                        start_rc = agent_cli.cmd_start(start_ns)
                    try:
                        start_payload = json.loads(start_buf.getvalue().strip().splitlines()[-1])
                    except (json.JSONDecodeError, IndexError):
                        start_payload = {"ok": False, "stdout": start_buf.getvalue()}
                    # 期望 status=resolved (无 context 直接 rerank spec)
                    if start_rc == 0 and start_payload.get("status") == "resolved":
                        dry_status = "ok"
                        dry_note = "start → resolved (rerank spec 已生成)"
                    else:
                        dry_status = "failed"
                        dry_note = (
                            f"rc={start_rc}, status={start_payload.get('status')}, "
                            f"error={start_payload.get('error')}"
                        )
                finally:
                    if env_backup is not None:
                        os.environ["CHISHA_STATE_ROOT"] = env_backup
                    else:
                        os.environ.pop("CHISHA_STATE_ROOT", None)
    else:
        dry_note = "profile 写入异常, 跳过 dry start"

    summary["steps"]["dry_start"] = {"status": dry_status, "note": dry_note}
    if dry_status != "ok":
        # dry_start 失败也标红 (recall→rerank 链路不通 = 用户用不了)
        summary["ok"] = False
        _stderr(f"[onboard] dry start: {dry_status} — {dry_note}")
    else:
        _stderr(f"[onboard] dry start ✓ ({dry_note})")

    # ─ 最终 summary ─
    if summary["ok"]:
        summary["next"] = "Onboarding 完成. 任意目录 Claude Code 说 '今天中午吃啥' 即可."
        _stderr("[onboard] ✓ Onboarding 完成. 任意目录 Claude Code 说 '今天中午吃啥' 即可.")
    else:
        summary["next"] = "Onboarding 未全绿, 看 steps 详情排错."
        _stderr("[onboard] ✗ Onboarding 未全绿, 看 stdout JSON.steps 排错.")
    _emit(summary)
    return 0 if summary["ok"] else 1


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

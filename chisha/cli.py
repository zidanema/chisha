"""T-DIST-01 B.2: chisha 顶层 CLI (entry point `chisha`).

子命令 (P1 拍平后, 推荐扁平路径):
  eat <lunch|dinner> [--context "原话"] [--from <rid>] [--at-time <date>]
                               — 起一轮推荐 (= agent_cli start)
  continue --id <rid> --result <json> --step <step_token>
                               — 推进一轮: 喂 LLM 原始输出 + 回显 step_token (host 单循环)
  choose --id <rid> (--card <cid> | --rank <N>) --action <accept|skip> [--reason ...]
                               — 记录用户选择 (幂等; --rank 按号定位 = cron 续轮, D-121 M4)
  skills add [--force]         — 装 Claude Code skill 到 ~/.claude/skills/chisha/
  doctor                       — 检查环境 (delegates to agent_cli.cmd_doctor)
  onboard [--zone] [--methodology] [--force]
                               — 初始化 ~/.chisha/profile.yaml + 装 skill + dry start (B.5)
  migrate-state [--dry-run]    — 把 repo 内旧 state 迁到 ~/.chisha/ (wrap state_migrate)
  methodology {schema|template|validate}
                               — T-DIST-02 占位, 报 NOT_IMPLEMENTED 非零退出

  [deprecated 一版] install-skill [--force] → 用 skills add
  [deprecated 一版] agent <verb> [args...]  → 用 eat / continue / choose (透传 agent_cli)

stdout 一律 JSON (machine-readable); 人类提示走 stderr (绝不污染 stdout pipe).
Legacy `python -m chisha.agent_cli` 仍可用 (走 agent_cli.main 直接); 推荐迁到扁平 `chisha eat/continue/choose`.
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


# ─────────────────────────────── update ───────────────────────────────

def cmd_update(args) -> int:
    """从 GitHub 增量拉最新 zone 数据到 state (运行期零联网; 仅本 verb 联网, 需 VPN)."""
    import datetime as _dt
    from chisha import updater, manifest as _mfst
    from chisha import state_root as _sr
    from chisha.install_root import install_root
    iroot = install_root()
    state_data = _sr.resolve(iroot) / "data"
    install_zones = {z["zone_id"]: z for z in _mfst.load_zones(iroot)}
    today = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    try:
        result = updater.run_update(state_data_dir=state_data, install_zones=install_zones,
                                    today=today, dry_run=getattr(args, "dry_run", False))
    except updater.UpdateNetworkError as e:
        _stderr(f"[update] {e}")
        _emit({"ok": False, "error": "network", "detail": str(e)})
        return 1
    except _mfst.IncompatibleManifestError as e:
        _stderr(f"[update] remote manifest 不兼容当前引擎, 整轮 abort (零落盘): {e}")
        _emit({"ok": False, "error": "incompatible", "detail": str(e)})
        return 1
    _stderr(f"[update] 更新 {result['updated']} · skip {result['skipped']} · 失败 {result['failed']}")
    _emit({"ok": True, **result})
    return 0


def cmd_zones(args) -> int:
    """M3.1: 列出 manifest 支持的 region 清单 (onboard 前查).

    agent 据此匹配用户位置 (slug) → 确认 (friendly_name) → onboard --zone <zone_id>.
    单一权威源 = data/manifest.json 的 zones (manifest.load_zones)。
    """
    from chisha import manifest
    from chisha.install_root import install_root
    zones = manifest.load_zones(install_root())
    fields = ("zone_id", "friendly_name", "short_name", "slug", "status",
              "city", "kind", "restaurant_count", "dish_count")
    _emit({"ok": True, "zones": [{k: z.get(k) for k in fields} for z in zones]})
    return 0


# ─────────────────────────────── agent passthrough ────────────────────

def cmd_agent(args, agent_argv: list[str]) -> int:
    """[deprecated 一版] 透传 agent_cli.main. 推荐扁平 `chisha eat/continue/choose`."""
    import os
    from chisha import agent_cli
    if not os.environ.get("CHISHA_SUPPRESS_LEGACY_TIP"):
        _stderr("[chisha] tip: `chisha agent <verb>` 是 deprecated 路径, "
                "推荐扁平 `chisha eat / continue / choose` (P1).")
    return agent_cli.main(agent_argv)


# ─────────────────────────────── 扁平 verbs (P1) ──────────────────────

def cmd_eat(args) -> int:
    """`chisha eat <meal> [--context ...]` = agent_cli start (host 单循环入口)."""
    from chisha import agent_cli
    ns = argparse.Namespace(scope="production", meal=args.meal, context=args.context,
                            from_id=args.from_id, at_time=args.at_time,
                            zone=args.zone)
    return agent_cli.cmd_start(ns)


def cmd_continue(args) -> int:
    """`chisha continue --id --result --step` = agent_cli continue (折叠 resolve+apply)."""
    from chisha import agent_cli
    ns = argparse.Namespace(scope="production", id=args.id, result=args.result,
                            step=args.step)
    return agent_cli.cmd_continue(ns)


def cmd_choose(args) -> int:
    """`chisha choose --id (--card|--rank) --action` = agent_cli choose."""
    from chisha import agent_cli
    ns = argparse.Namespace(scope="production", id=args.id, card=args.card,
                            rank=getattr(args, "rank", None),
                            action=args.action, reason=args.reason)
    return agent_cli.cmd_choose(ns)


def cmd_skills(args) -> int:
    """`chisha skills add [--force]` = 装 Claude Code skill (= install-skill rename)."""
    if args.action == "add":
        return cmd_install_skill(args)
    _emit({"ok": False, "error": "UNKNOWN_SKILLS_ACTION",
           "message": f"未知 skills 子命令: {args.action!r} (支持: add)"})
    return 1


# ─────────────────────────────── profile (D-112 Step2) ───────────────

def cmd_profile(args) -> int:
    """`chisha profile [questions] | profile apply --answers <json> [--confirm]`.

    D-112 Step2: chisha 出问卷 schema (host 渲染 + memory 预填默认值) → host 回传答案 →
    chisha 确定性映射 + 确认预览 → `--confirm` 才 surgical 写盘 (保留注释)。零 LLM。
    """
    from chisha import agent_cli, agent_profile_setup, data_root
    from chisha.install_root import install_root

    root = install_root()
    action = getattr(args, "profile_action", None) or "questions"

    # questions 不碰 state, 任何时候都能出 schema; apply 写盘前守 sandbox scope (防写沙盒副本)。
    if action == "questions":
        _emit({"ok": True, "action": "questions", **agent_profile_setup.build_question_schema()})
        return 0

    if action != "apply":
        _emit({"ok": False, "error": "UNKNOWN_PROFILE_ACTION",
               "message": f"未知 profile 子命令: {action!r} (支持: questions / apply)"})
        return 1

    try:
        agent_cli._guard_scope(root, "production")
    except RuntimeError as e:
        _emit({"ok": False, "error": "SCOPE", "message": str(e)})
        return 1

    try:
        answers = json.loads(args.answers)
    except (json.JSONDecodeError, TypeError) as e:
        _emit({"ok": False, "error": "BAD_JSON", "message": f"--answers 非合法 JSON: {e}"})
        return 1
    if not isinstance(answers, dict):
        _emit({"ok": False, "error": "BAD_ANSWERS",
               "message": "--answers 须是对象 {question_id: 答案}"})
        return 1

    profile_path = data_root.profile_path(root)
    if not profile_path.exists():
        _emit({"ok": False, "error": "PROFILE_MISSING",
               "message": f"画像不存在 ({profile_path}); 先跑 chisha onboard --zone <zone_id>"})
        return 1

    import yaml  # vendored
    text = profile_path.read_text(encoding="utf-8")
    try:
        profile = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        _emit({"ok": False, "error": "PROFILE_PARSE", "message": f"画像 YAML 损坏: {e}"})
        return 1

    plan = agent_profile_setup.plan_profile_writes(answers, profile)
    summary = agent_profile_setup.summarize_plan(plan)

    if not getattr(args, "confirm", False):
        # 预览 (不写盘). confirm_required 仅在真有写入时为 True (空问卷无需确认)。
        _emit({
            "ok": True, "action": "preview",
            "confirm_required": plan.has_writes(),
            "writes": plan.writes, "noops": plan.noops, "rejected": plan.rejected,
            "summary": summary,
            "next": ("用户确认后: chisha profile apply --answers '<同一 JSON>' --confirm"
                     if plan.has_writes() else "无可写入, 无需 apply --confirm"),
        })
        return 0

    written_fields = [w["field"] for w in plan.writes]
    if plan.has_writes():
        new_text = agent_profile_setup.apply_writes(text, plan, profile)
        new_text = agent_profile_setup.stamp_schema_version(new_text)   # P4: 顺手 stamp 当前问卷版本
        # 原子写: 临时文件 + os.replace (同目录, 跨进程不撕裂)。
        import os as _os
        tmp = profile_path.with_name(profile_path.name + ".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        _os.replace(tmp, profile_path)
        _stderr(f"[profile] 已写入 {len(written_fields)} 字段 → {profile_path}")

    _emit({
        "ok": True, "action": "applied",
        "written": written_fields, "rejected": plan.rejected,
        "path": str(profile_path),
        "message": (f"已写入画像: {', '.join(written_fields)}"
                    if written_fields else "无变更 (空问卷或均为现值)"),
    })
    return 0


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
    """T-DIST-01 B.4: 写 ~/.claude/skills/chisha/SKILL.md.

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
      2. install skill: 落 ~/.claude/skills/chisha/SKILL.md.
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
    # P4 MVP: --resume 暂等同 --force 全量重跑 (目标态: 只补新增/变更题)
    force = getattr(args, "force", False) or getattr(args, "resume", False)

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
        from chisha.agent_profile_setup import QUESTION_SCHEMA_VERSION
        template = template_path.read_text(encoding="utf-8")
        rendered = (
            template
            .replace("<PROFILE_SCHEMA_VERSION>", QUESTION_SCHEMA_VERSION)   # P4: stamp 问卷版本
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

    # ─ Step 1b (D-119): 派生 profile_configured —— 宿主据此决定要不要主动提配画像 (与一次性 onboard
    #   解耦; 跨宿主共享 ~/.chisha/ 时本次会 status=exists, 但只要这里 False 仍要主动提)。best-effort。
    try:
        import yaml
        from chisha.agent_profile_setup import profile_is_configured
        _prof = yaml.safe_load(profile_target.read_text(encoding="utf-8")) or {}
        summary["profile_configured"] = profile_is_configured(_prof)
    except Exception as e:  # noqa: BLE001 — 派生失败不阻塞 onboard
        summary["profile_configured"] = False
        _stderr(f"[onboard] profile_configured 派生失败 (不阻塞): {type(e).__name__}: {e}")

    # ─ Step 1c (D-121 A / D-121.1): cron_hint —— 纯文案引导, 与 profile_configured 同级。
    #   chisha 永不拥有 cron; 这里只是把"宿主有 cron 能力可提配饭点提醒"的引导随回包带出。
    #   D-121.1: 激活时机 = 先尝后订 —— **不在 onboard 当场问** (用户还没尝到价值, 转化低又冒昧),
    #   降级为延后软信号: 等用户用顺手 (首次 accept) 后再提, 时机/接法见 SKILL.md「cron 宿主对号入座」节。
    #   m1: 数据契约指针, 不是编排脚本。
    summary["cron_hint"] = (
        "若你 (宿主) 有 cron / 定时能力 (如 Claude Code routines、openclaw cron), "
        "可在用户用顺手后 (首次 accept、非 onboard 当场) 提议配每日饭点主动提醒; "
        "时机与接法见 SKILL.md「cron 宿主对号入座」节。"
        "无 cron 能力忽略本字段即可 (chisha 不拥有 cron)。"
    )

    # ─ Step 2: install skill ─ (capture stdout JSON, 合并进 summary)
    skill_buf = io.StringIO()
    with contextlib.redirect_stdout(skill_buf):
        skill_rc = init_skill("claude-code", install_root_p, force=force)
    try:
        skill_payload = json.loads(skill_buf.getvalue().strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        skill_payload = {"ok": False, "stdout": skill_buf.getvalue()}
    summary["steps"]["skill"] = skill_payload
    # (PRD §3.5 #2): init_skill 已存在 → ok=true status=skipped (非 EXISTS error),
    # onboard 不再误判失败. 仅 ok=false (真错: UNSUPPORTED_AGENT / 写盘失败) 才阻塞。
    if not skill_payload.get("ok"):
        summary["ok"] = False
        _stderr(f"[onboard] skill 失败: {skill_payload.get('error', {}).get('code', 'unknown')}")
    elif skill_payload.get("status") == "skipped":
        _stderr(f"[onboard] skill 已存在 → {skill_payload.get('path')} (跳过, --force 覆盖)")
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
                    # 期望 status=resolved (无 context 直接 rerank spec); M3.2: 未覆盖 region
                    # → coming_soon 也算装好 (onboard 照常装, eat 待 region 上线), 非失败。
                    _dry_st = start_payload.get("status")
                    if start_rc == 0 and _dry_st == "resolved":
                        dry_status = "ok"
                        dry_note = "start → resolved (rerank spec 已生成)"
                    elif start_rc == 0 and _dry_st == "coming_soon":
                        dry_status = "ok"
                        dry_note = (f"start → coming_soon ({start_payload.get('reason')}) "
                                    "— 已装好, region 数据上线后即可推荐")
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

    sp = sub.add_parser("zones", help="列出支持的 region 清单 (onboard 前查, agent 匹配位置)")
    sp.set_defaults(func=cmd_zones)

    # ─ 扁平 verbs (P1, host 单循环主路径) ─
    sp = sub.add_parser("eat", help="起一轮推荐: chisha eat lunch [--context ...]")
    sp.add_argument("meal", choices=["lunch", "dinner"])
    sp.add_argument("--context", default=None, help="用户当天自然语言 (触发 intent 抽取)")
    sp.add_argument("--from", dest="from_id", default=None, help="refine: 续上一轮 rid")
    sp.add_argument("--at-time", default=None, help="time-travel: YYYY-MM-DD")
    sp.add_argument("--zone", default=None,
                    help="临时指定 region (出差/换区), 不改 profile 默认; 传 zone_id 或 slug")
    sp.set_defaults(func=cmd_eat)

    sp = sub.add_parser("continue", help="推进一轮: 喂 LLM 输出 (--result) + 回显 --step")
    sp.add_argument("--id", required=True)
    sp.add_argument("--result", required=True, help="你的 LLM 原始输出 JSON (raw payload)")
    sp.add_argument("--step", required=True, help="回显上一步回包顶层 step_token")
    sp.set_defaults(func=cmd_continue)

    sp = sub.add_parser("choose", help="记录用户选择 (幂等)")
    sp.add_argument("--id", required=True)
    sp.add_argument("--card", default=None, help="card_id (cards[].id)")
    sp.add_argument("--rank", type=int, default=None,
                    help="按 rank 号定位 card (cron 续轮: 提醒只带 rid + 号); 与 --card 二选一")
    sp.add_argument("--action", required=True, choices=["accept", "skip"])
    sp.add_argument("--reason", default=None, help="skip 原因 (可选)")
    sp.set_defaults(func=cmd_choose)

    # ─ profile 问卷 (D-112 Step2) ─
    sp = sub.add_parser("profile", help="配置画像问卷 (profile / profile apply --answers <json>)")
    psub = sp.add_subparsers(dest="profile_action")  # 缺省 → questions
    psub.add_parser("questions", help="出问卷 schema (host 渲染, 默认子命令)")
    pap = psub.add_parser("apply", help="回传答案 → 映射预览 (--confirm 才写盘)")
    pap.add_argument("--answers", required=True, help="host 收集的答案 JSON {question_id: 答案}")
    pap.add_argument("--confirm", action="store_true", help="用户确认后才落盘 (不带=只预览)")
    sp.set_defaults(func=cmd_profile)

    sp = sub.add_parser("skills", help="管理 agent skill (skills add)")
    sp.add_argument("action", choices=["add"])
    sp.add_argument("--force", action="store_true", help="覆盖已存在 SKILL.md")
    sp.set_defaults(func=cmd_skills)

    sp = sub.add_parser("agent", help="[deprecated→eat/continue/choose] 透传到 agent_cli")
    sp.add_argument("rest", nargs=argparse.REMAINDER,
                    help="agent_cli 子命令 + 参数, e.g. `chisha agent start --meal lunch`")
    sp.set_defaults(func="_AGENT")  # 由 main 特判 (REMAINDER 不走标准 func)

    sp = sub.add_parser("install-skill", help="[deprecated→skills add] 装 Claude Code skill")
    sp.add_argument("--force", action="store_true", help="覆盖已存在 SKILL.md")
    sp.set_defaults(func=cmd_install_skill)

    sp = sub.add_parser("onboard", help="初始化 profile + skill + dry start")
    sp.add_argument("--zone", default="shenzhen-bay", help="默认 zone (B.5a)")
    sp.add_argument("--methodology", default="harvard_plate", help="默认 methodology (B.5a)")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--resume", action="store_true",
                    help="问卷改版后补答新增/变更题 (P4 MVP: 等同 --force 全量重跑)")
    sp.set_defaults(func=cmd_onboard)

    sp = sub.add_parser("update", help="从 GitHub 拉最新 zone 数据到 state (需 VPN; 运行期零联网)")
    sp.add_argument("--dry-run", action="store_true", help="只报告不写盘")
    sp.set_defaults(func=cmd_update)

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

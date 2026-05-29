"""D-074 T8 / P1: init verb — 生成 reference adapter skill (Layer 2 交互层).

交互呈现是 **adapter 特定的 Layer 2** (设计 §9), 住在生成的 skill 里, 不进协议层.
协议层 (CLI verbs + do_llm 信封) 跨 agent 复用; 换 agent (codex / TUI / 飞书) =
重写交互层、复用协议层.

Phase 0 reference adapter = Claude Code: 生成一个**瘦** SKILL.md (P1: 从 110 行过程
手册收敛成单循环触发器, 对标 lark-cli 的薄 skill), 教 Claude Code 用自己的 LLM 执行
chisha 发的 do_llm + 用 AskUserQuestion 摆候选 + refine 多轮.
"""
from __future__ import annotations

import json
from pathlib import Path

SKILL_DIR_NAME = "chisha-meal"

_SUPPORTED_AGENTS = {"claude-code"}


def _claude_code_skill_md() -> str:
    """Claude Code reference adapter (P1 单循环触发器, ~25 行 body)."""
    return r'''---
name: chisha-meal
description: 今天吃点啥 — 个人原则派点餐执行外包. 中午/晚上点外卖纠结时用. 基于哈佛餐盘弱约束 (控油+有蔬菜+有蛋白) 从办公区/家附近商家推一组 (稳妥 exploit + 探索 explore), 选 1; 可多轮 refine. 触发词: 吃啥, 吃什么, 午餐, 晚餐, 中午吃啥, 晚上吃啥, 点外卖, 外卖纠结.
---

# chisha 点餐 (零 LLM, 借你的 LLM)

chisha **不调 LLM** — 它发 `do_llm` 信封, **你用自己的 LLM 执行**后喂回. 确定性 (召回/打分/校验/兜底) 全在 chisha; 你只做两处智能判断: 抽 intent / 排候选. 命令任意目录跑, 输出 JSON 到 stdout, state 落 `~/.chisha/`.

## 装 (一次)

```
uv tool install chisha-meal         # 持久装 → chisha / chisha-meal 上 PATH
chisha onboard --zone shenzhen-bay  # 初始化 profile + 装本 skill + 自检
```

## 用 (一个循环)

1. 判 meal (11:00–15:00 → `lunch`, 其余 `dinner`; 拿不准问用户). 有诉求原话带 `--context`:
   `chisha eat <lunch|dinner> [--context "用户原话"]`
2. **循环**: 回包带 `do_llm` 就执行它 → 喂回 → 直到 `status=ready`:
   - 按 `do_llm.system` + `json_schema`/`tools` 用**你的** LLM 产出 (照它执行, 别自己发挥).
     - `operation_kind=extract` → 产出 intent 对象 (没把握映射进 slot 的诉求写 `raw_understanding`, 别回传 raw_text).
     - `operation_kind=rerank` → 读候选挑 5 条 (R1: 3 稳妥 + 2 探索; refine 轮全稳妥), 带 `narrative`.
   - 喂回 (传**原始 LLM 输出**, 别自己包信封; `--step` 回显上一步的不透明 token):
     `chisha continue --id <rid> --result '<你的 LLM 原始输出 JSON>' --step <step_token>`
   - 若回包带 `intent_disclosure`, 记下 `raw_understanding` 里值得告诉用户的点 (稍后呈现带一句).
3. `status=ready` → 用 **AskUserQuestion** 摆 `cards`: label=餐厅+主菜, description=价格/理由/health; `is_explore=true` 标"探索"; 自带的 **Other/自由输入** 就是 refine 入口.
4. 用户选某卡 → `chisha choose --id <rid> --card <cards[].id> --action accept`; 明确不吃 → `--action skip`.
5. refine: 用户在 Other 输新诉求 (如"再辣点"/"换一家") → `chisha eat <meal> --context "新诉求" --from <rid>` (回到步骤 2).

## 注意

- `--result` 传你 LLM 的**原始输出 JSON** (raw payload), **不要**手包 `{correlation_id, payload}` 信封; `--step` 直接回显上一步回包**顶层**的 `step_token` 字段 (与 `do_llm` 同级, 不在 do_llm 里面; 漏了/抄错 → chisha 报错, 重发即可).
- `fallback=true`: 你的产出没过 chisha 校验, 它按规则兜底排了 — 如实告诉用户"这次按规则排的", 别套你的 narrative.
- chisha 报 `ok=false` + `error` → 把 `error.message` 念给用户, 别硬编. 自检: `chisha doctor` (sandbox 全局启用时 CLI 拒绝跑, 先去 sandbox-lab disable).
- 反馈闭环 (好评/差评/历史蒸馏) Phase 0 不做.
'''


def init_skill(agent: str, root: Path, *, force: bool = False, dest: Path | None = None) -> int:
    """T-DIST-01 B.4: 生成 reference adapter skill 到 user-level ~/.claude/skills/.

    默认 dest = `~/.claude/skills/chisha-meal/SKILL.md` (user-level, 跨 cwd 全局可用).
    Tests 走 dest= 注入显式目录 (临时 HOME). `root` 入参保留 (现 unused 但 signature
    向后兼容; 未来 SKILL.md 模板若要带 install_root 路径片段会用上).
    emit JSON, 返回 exit code.
    """
    if agent not in _SUPPORTED_AGENTS:
        print(json.dumps({
            "ok": False,
            "error": {"code": "UNSUPPORTED_AGENT",
                      "message": f"Phase 0 仅支持 --agent claude-code (got {agent!r})"},
        }, ensure_ascii=False))
        return 1

    # T-DIST-01 B.4: 默认 user-level ~/.claude/skills/, 不再用 root/.claude.
    target_dir = dest or (Path.home() / ".claude" / "skills" / SKILL_DIR_NAME)
    target = target_dir / "SKILL.md"
    if target.exists() and not force:
        print(json.dumps({
            "ok": False,
            "error": {"code": "EXISTS",
                      "message": f"{target} 已存在, 用 --force 覆盖"},
            "path": str(target),
        }, ensure_ascii=False))
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(_claude_code_skill_md(), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "agent": agent,
        "path": str(target),
        "next": [
            "skill 已生成. 在任意目录 Claude Code 里说 '今天中午吃啥' 触发, 或 /chisha-meal.",
            "先跑 `chisha doctor` 自检环境 (install/state root + manifest + scope).",
        ],
    }, ensure_ascii=False))
    return 0

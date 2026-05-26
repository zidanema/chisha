"""D-074 T8: init verb — 生成 reference adapter skill (Layer 2 交互层).

交互呈现是 **adapter 特定的 Layer 2** (设计 §9), 住在生成的 skill 里, 不进协议层.
协议层 (CLI verbs + llm_request_spec) 跨 agent 复用; 换 agent (codex / TUI / 飞书) =
重写交互层、复用协议层.

Phase 0 reference adapter = Claude Code: 生成一个 SKILL.md 运行手册, 教 Claude Code
怎么用自己的 LLM 执行 chisha 发的 spec + 用 AskUserQuestion 摆候选 + refine 多轮.
"""
from __future__ import annotations

import json
from pathlib import Path

SKILL_DIR_NAME = "chisha-meal"

_SUPPORTED_AGENTS = {"claude-code"}


def _claude_code_skill_md() -> str:
    """Claude Code reference adapter 运行手册 (设计 §9 交互形态)."""
    return r'''---
name: chisha-meal
description: 今天吃点啥 — 个人原则派点餐执行外包. 中午/晚上点外卖纠结时用. 基于哈佛餐盘弱约束 (控油+有蔬菜+有蛋白) 从办公区/家附近商家推一组 (稳妥 exploit + 探索 explore), 选 1; 可多轮 refine. 触发词: 吃啥, 吃什么, 午餐, 晚餐, 中午吃啥, 晚上吃啥, 点外卖, 外卖纠结.
---

# chisha 点餐 (D-074 AI-friendly reference adapter)

你是 chisha 的宿主 agent. chisha **不调 LLM** — 它发 `llm_request_spec` 信封, **你用自己的 LLM 执行**, 把结果交回 chisha 校验落库. 确定性 (召回/打分/校验/兜底) 全在 chisha, 你只做两处智能判断: ① 把用户原话抽成结构化 intent; ② 读候选排出推荐.

所有命令在仓库根跑 (one-shot, 跑完即退, 输出 JSON 到 stdout):

```
uv run python -m chisha.agent_cli <verb> ...
```

## 流程

### 1. 定 meal + 起一轮

- 看当前时间: 11:00-15:00 → `lunch`; 其余 → `dinner` (拿不准就问用户).
- 用户给了诉求原话 (如 "想吃辣的别太贵") → 带 `--context`; 没给 → 不带.

```
uv run python -m chisha.agent_cli start --meal lunch --context "想吃辣的别太贵"
```

返回 JSON 的 `status`:
- `pending` (operation=extract): 有 context, chisha 要你先抽 intent → 见步骤 2.
- `resolved` (operation=rerank): 无 context, chisha 已召回打分 → 直接跳步骤 3.

记下返回的 `recommendation_id` (后续每步要带).

### 2. (仅 pending) 执行 extract spec → 抽 intent

`llm_request_spec` 是带版本的信封 (`operation_kind=extract`, `output_mode=text_json`):
- `system`: 抽取规则 + schema + 例子 (照它执行, **别自己发挥**).
- `messages`: 含用户原话.
- `json_schema`: 输出结构 (redirect / constrain / reference / reject_previous / raw_understanding / schema_version="2.1").
- `required_validation`: chisha 会校验的点 (枚举闭包 / 禁脑补 / schema 未覆盖走 raw_understanding).

**你**按 system + json_schema 产出一个 intent 对象. 没自信映射进 slot 的诉求写进 `raw_understanding` (chisha 会当用户可见提示弹出). **不要回传 raw_text** (chisha 自己注入原话).

把它包成**信封**交回 — `correlation_id` 直接抄 `llm_request_spec.correlation_id` (chisha 据此拒绝串轮 / 过期回传):

```
uv run python -m chisha.agent_cli resolve-intent --id <rid> --intent '{"correlation_id":"<抄 spec.correlation_id>","payload":<你产出的 intent 对象>}'
```

返回 `status=resolved` + `intent_disclosure` (把 disclosure.raw_understanding 里值得告诉用户的点记下, 稍后呈现时带一句) + 新的 rerank `llm_request_spec`.

### 3. 执行 rerank spec → 排候选

`llm_request_spec` (`operation_kind=rerank`, `output_mode=tool_use`):
- `system`: 排序角色 + 输出 schema + few-shot.
- `messages`: 含 `[PROFILE]` / `[CONTEXT]` / `[CANDIDATES]` (每条带 `[idx]`).
- `tools`: `select_top_candidates` 的 schema.
- `required_validation`: 数量/rank 连续/combo_index 不越界/exploit 在前 explore 在后/同 brand≤1/不输出 health_flags.

**你**读候选, 按 system 规则挑 5 条 (R1: 3 exploit + 2 explore; refine 轮: 全 exploit), 包成**信封**产出 (`correlation_id` 抄 `llm_request_spec.correlation_id`):

```json
{"correlation_id":"<抄 spec.correlation_id>",
 "payload": {"candidates": [
   {"rank":1,"is_explore":false,"combo_index":<输入里的idx>,"fit_score":0.85,"taste_match":0.7,"risk_flags":[],"one_line_reason":"..."},
   ...5 条...
 ], "narrative": "≤50字: 为什么推这5道 (要有执行证据)"}}
```

交回:

```
uv run python -m chisha.agent_cli apply-rerank --id <rid> --response '<信封 json>'
```

返回 `status=ready` + `cards` (每张带稳定 `id`) + `narrative`. 若 `fallback=true` 说明你的产出没过校验, chisha 用了规则兜底 — 如实告诉用户"这次按规则排的".

### 4. 用 AskUserQuestion 摆出来让用户选

把 `cards` 摆成选项 (前段 exploit 稳妥 / 后段 explore 探索, is_explore=true 的标一下"探索"):
- 每个 option label = 餐厅 + 主菜; description = 价格/理由/health 提示.
- AskUserQuestion 自带的 **"Other / 自由输入"** 就是 refine 入口.
- 若步骤 2 有 disclosure 值得提示 (如 "'那家店'没认出已忽略"), 在问题里带一句.

### 5. 记录选择

用户选了某张卡 → `accept`; 明确说不吃/跳过 → `skip`:

```
uv run python -m chisha.agent_cli choose --id <rid> --card <card_id> --action accept
```

幂等: 重复 choose 同一卡不会重复计数, 放心重试.

### 6. refine (多轮)

用户在 Other 里输入新诉求 (如 "再辣点" / "换一家" / "比这清淡") → 起新一轮, **带 `--from`**:

```
uv run python -m chisha.agent_cli start --meal lunch --context "再辣点" --from <rid>
```

回到步骤 2 (有 context → pending → 抽 intent → rerank). refine 轮聚焦, 不出 explore 段. 可连续多轮.

## 注意

- 每步都把 `recommendation_id` 透传; resolve-intent / apply-rerank 回传须包信封 `{correlation_id, payload}`, correlation_id 直接抄当步 `llm_request_spec.correlation_id` (漏了或抄错 → chisha 报 CORRELATION 错, 重发即可).
- chisha 报 `ok=false` + `error` → 把 message 念给用户, 别硬编. `ROUND_STATE` 类错误通常是顺序错了 (如没 resolve-intent 就 apply-rerank).
- `doctor` 自检: `uv run python -m chisha.agent_cli doctor` (sandbox 全局启用时 CLI 会拒绝跑, 先去 sandbox-lab disable).
- 反馈闭环 (好评/差评/历史蒸馏) Phase 0 不做 (F-014 defer).
'''


def init_skill(agent: str, root: Path, *, force: bool = False, dest: Path | None = None) -> int:
    """生成 reference adapter skill. emit JSON, 返回 exit code."""
    if agent not in _SUPPORTED_AGENTS:
        print(json.dumps({
            "ok": False,
            "error": {"code": "UNSUPPORTED_AGENT",
                      "message": f"Phase 0 仅支持 --agent claude-code (got {agent!r})"},
        }, ensure_ascii=False))
        return 1

    target_dir = dest or (root / ".claude" / "skills" / SKILL_DIR_NAME)
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
            "skill 已生成. 在 Claude Code 里说 '今天中午吃啥' 触发, 或 /chisha-meal.",
            "若要全局可用, 把它拷到 ~/.claude/skills/ 下.",
            "先跑 `uv run python -m chisha.agent_cli doctor` 自检环境.",
        ],
    }, ensure_ascii=False))
    return 0

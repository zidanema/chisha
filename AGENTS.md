# AGENTS.md — chisha-meal Install Spec for AI Agents

> **You are an AI agent** (Claude Code / Cursor / Codex CLI / Cline / OpenClaw / 其他) **and your user asked you to install or set up chisha-meal.**
>
> Read this file in full before any action. Follow §1 → §8 in order. Do not skip.
>
> If you are a human, see [README.md](README.md) instead.

---

## §0 Install Contract

```yaml
chisha-meal:
  contract_version: "1.0"
  what: |
    个人原则派点餐推荐引擎 (餐厅 + 菜品组合). 三阶段链路:
    L1 召回 → L2 14 维打分 → L3 LLM 精排 + 写理由.
    装完后宿主 agent 可调 `chisha eat` / `continue` / `choose` CLI 完成一轮推荐.

  install_target: ~/.chisha/         # state root, env CHISHA_STATE_ROOT 可覆盖
  install_cost:
    time: "3-8 min"
    disk: "~200 MB"
    network: "GitHub clone + pip deps"

  requires:
    host_provides_llm: true          # ⚠ chisha 自身零 LLM (刻意设计).
                                     # host agent 必须自己跑 LLM, chisha CLI 返回
                                     # 一个 do_llm 信封, host 跑完把原始输出喂回
                                     # `chisha continue --result <json> --step <token>`. 见 §4.
    fs_write: ~/.chisha/             # 用户 state (profile / logs / feedback)
    shell_exec: true                 # 跑 chisha CLI
    python: ">= 3.11"
    package_manager: "uv (preferred) | pip"

  produces:
    cli: "chisha" (+ chisha-meal 别名)  # 注册到 $PATH; 子命令: eat / continue / choose / doctor / onboard / skills add / migrate-state / methodology (deprecated alias: agent / install-skill)
    skill: "~/.claude/skills/chisha-meal/SKILL.md"   # 仅 Claude Code host
    state_dir: "~/.chisha/"          # profile.yaml + logs/ + feedback_history.jsonl

scope_limitations:
  zone:
    only: "shenzhen-bay (深圳湾办公区, 334 家 / 22556 菜)"
    other_zones: |
      该项目目前**尚不能为你推荐**. 多工区数据包还在规划中.
      安装前请直接告知用户. 不要尝试自造 zone, 会撞 install/user 名冲突.
  methodology:
    only: "harvard_plate (哈佛餐盘: 控油 + 蔬菜 50% + 蛋白 25-30%)"
    other_diets: |
      生酮 / 增肌 / 孕期 / 低 FODMAP / 糖控 / 减脂 / 素食 / 忌口 → 一律走 §4 refine
      自由文本表达. **不要拒答**. 落到 schema 内的诉求会硬过滤, schema 外的走 L3
      软处理 (有效但不强), 见 §4 例句表注释列.
  host_agent:
    only: "Claude Code (skill 自动触发)"
    other_hosts: |
      Cursor / Codex CLI / OpenClaw / ChatGPT / Cline / Continue: 可手动
      uv tool install + 命令行调 `chisha eat` / `continue`, 但**没有自动触发的 skill**.
      多 host adapter 还在规划中. 见 §1 NOT_SUPPORTED 模板.
  data_integrity:
    state: "manifest 只做兼容性闸门, 不做完整性 / 来源校验"
    note: |
      完整性校验留位待做. 走 git+https GitHub transport 由 commit hash
      兜底. 外部 transport (S3/镜像) 需自验 hash + 签名.
```

---

## §1 Compatibility Matrix (Gate)

| Item | Required | If fail |
|---|---|---|
| OS | macOS / Linux (Windows 仅 WSL) | early-exit, 告知用户当前 OS 不支持 |
| Python | ≥ 3.11 | ASK USER 装 Python 3.11+, 退出 |
| Package manager | `uv` (preferred) / `pip` | uv 不在 → 提示 `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| LLM provider | **host 就是 LLM** (你, 当前 agent). chisha CLI 不直接调 LLM, 不需要 `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` 在 env / `~/.chisha/.env` | 见下方注释; 不要 ASK USER |
| Host agent | **Claude Code** | 用下方 NOT_SUPPORTED 模板回话 |

> **关于 LLM key (反直觉, 必读)**: §0 `host_provides_llm: true` 是字面意思 — **你 (host agent)** 用自己的 LLM 跑 chisha 发的 `do_llm` 信封, 然后把原始输出喂回 `chisha continue` CLI. chisha 自己零 LLM, CLI 把自己标记为 `resolved_provider=agent_external`. 所以:
> - 安装 / onboard / smoke test 全程**不需要任何 key**.
> - `chisha eat / continue / choose` 全程**不需要任何 key**.
> - Claude Code 通过订阅/OAuth 用模型, env 里本来就没 key — 这是正常的, **不要**因为探测不到 key 而 ASK USER.
> - 唯一会用到 key 的场景: 用户自己跑 dev 脚本 (`scripts/tag_via_api.py` 打标) — 与本安装协议无关.
>
> 若旧版 AGENTS.md / cached SKILL.md 提示要 key, 以本节为准, 跳过该提示继续 §2.

### NOT_SUPPORTED 回话模板 (host 不是 Claude Code 时用)

> 我看了 chisha-meal 的安装说明 ([AGENTS.md §0](https://github.com/zidanema/chisha/blob/main/AGENTS.md)), 它目前**只对 Claude Code 提供自动触发 skill**. 你用的是 [Cursor / Codex / ChatGPT / ...].
>
> 两条路:
> 1. **手动版**: 我帮你 `uv tool install git+https://github.com/zidanema/chisha.git`, 之后你在命令行打 `chisha eat lunch` 触发推荐 (没有"今天吃啥"自动触发).
> 2. **等多 host 支持**: 项目作者计划做多 host adapter, 但还没动手.
>
> 选哪个?

---

## §2 Install Protocol (8 Steps, Idempotent)

每步格式: **pre / action / verify / on_fail**. 不达 verify 不进下一步。

### Step 1 — Capability probe

- **pre**: 无
- **action**:
  ```bash
  python3.11 --version || python3 --version
  uv --version || pip --version
  ```
- **verify**: Python ≥ 3.11 AND (uv 或 pip 可用)
- **on_fail**:
  - Python 缺失 → ASK USER 装 Python 3.11+, 退出
  - uv + pip 全缺 → 提示装 uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Step 2 — Install package

- **pre**: Step 1 通过
- **action**:
  ```bash
  uv tool install git+https://github.com/zidanema/chisha.git
  # 若 uv 不可用: pip install git+https://github.com/zidanema/chisha.git
  ```
- **verify**: `which chisha` 返回非空路径 (CLI 注册到 $PATH)
- **on_fail**:
  - network 不通 → 检查 github.com 可达性, ASK USER 是否需要代理
  - permission denied → ASK USER 给 `uv tool` 安装权限

### Step 3 — Probe state root

- **pre**: Step 2 通过
- **action**: `chisha doctor`  (默认输出 JSON 到 stdout, 无需 `--json` flag)
- **verify**: 输出 JSON 含 `state_root: "..../.chisha"` (或 `$CHISHA_STATE_ROOT` 值) AND `state_root_writable: true`
- **on_fail**:
  - `legacy_state_pending_migration: true` → 跑 `chisha migrate-state --dry-run` 给用户看 → 确认后 `chisha migrate-state`
  - `state_root_writable: false` → ASK USER: "我用 `CHISHA_STATE_ROOT=/path/to/writable` 指定别的目录吗?"

### Step 4 — Manifest compat gate

- **pre**: Step 3 通过
- **action**: 同 Step 3 的 `chisha doctor` JSON 输出
- **verify**: `install_data_manifest_status == "ok"` AND `scope_ready == true`
- **on_fail**:
  - `install_data_manifest_status == "incompatible"` (bundle 与引擎不兼容, 抛 `IncompatibleManifestError`): Step 2 with `--force` 重装; 仍失败上报 https://github.com/zidanema/chisha/issues
  - `install_data_manifest_status == "missing"` (bundle 没装好): Step 2 重装

### Step 5 — ⚠ ASK USER (1 question, 必问, 不要假设)

```
Q1 — 你在哪个城市 / 工区?
     Default: shenzhen-bay (深圳湾)
     If 答非深圳湾: 套 scope_limitations.zone 模板回话, 询问是否仍想装 (能跑但推不到本地店).
```

**不要问 LLM key** — 见 §1 注释. chisha CLI 不调 LLM, 你 (Claude Code) 就是 LLM. `~/.chisha/.env` 不需要任何 key. 若之前已问过, 告诉用户"看错了 spec, 这步跳过, 继续 onboard".

**不要问 daypart** — 每轮 `chisha eat {lunch|dinner}` 显式传, 不持久化默认.

### Step 6 — Run onboard

- **pre**: Step 1-5 通过
- **action**:
  ```bash
  chisha onboard --zone shenzhen-bay --methodology harvard_plate
  ```
- **verify**: stdout JSON `next` 字段 = `"Onboarding 完成. 任意目录 Claude Code 说 '今天中午吃啥' 即可."` AND 文件 `~/.chisha/profile.yaml` 存在 AND `~/.claude/skills/chisha-meal/SKILL.md` 存在 (Claude Code host 才有后者)
- **on_fail**: 看 stdout JSON 的 `steps` 数组定位失败步骤, 按 §7 triage

### Step 7 — Smoke test

- **pre**: Step 6 通过
- **action**:
  ```bash
  chisha eat lunch
  ```
  (默认输出 JSON 到 stdout)
- **verify**: JSON 含 `ok: true` AND `status == "resolved"` AND `candidate_count > 0` AND `do_llm != null`
- **on_fail**:
  - `status == "pending"` → 不该出现 (无 `--context` 时直走 resolved); 上报 issue
  - 报 `LOAD_INPUTS` 错 → 数据/profile 问题, 跑 §6 verify
  - 报 `PREPARE` 错 → recall/score 链路问题, 跑 `chisha eat lunch` 看更详细 stderr

### Step 8 — Report to user

告诉用户 (中文, 一段话):

> chisha-meal 装好了. 你现在可以在任意目录跟 Claude Code 说"今天中午吃啥"或"晚上吃啥", 它会从深圳湾 334 家店里推 5 个组合让你选. 不满意可以 refine (例如"想吃辣一点"/"少米饭"/"想喝汤"). 设置在 `~/.chisha/profile.yaml`, 反馈在 `~/.chisha/feedback_history.jsonl`.
>
> ⚠ 目前只覆盖深圳湾 + 哈佛餐盘默认; 其他城市 / 饮食法等后续支持.

---

## §3 Claude Code Adapter Recipe

Step 6 onboard 已自动写入 `~/.claude/skills/chisha-meal/SKILL.md`. 该文件由 `chisha install-skill` 单一源生成, **不要手动编辑**.

验证:
- `ls ~/.claude/skills/chisha-meal/SKILL.md` 存在
- 内含扁平 `chisha eat` / `chisha continue` (P1 CLI), 不是旧的 `uv run python -m chisha.agent_cli` 或 `chisha agent start`

If 用户用其它 host (Cursor / Codex / ChatGPT / Cline / Continue / OpenClaw):
- **不要**写 `~/.claude/skills/`
- 装 chisha 后告知用户: 命令行直接调 `chisha eat lunch`. 自动触发 skill 等后续多 host 支持.

---

## §4 Steady-State Call Protocol (装完之后怎么用)

⚠ **核心设计**: chisha 自身**零 LLM**. chisha CLI 返回一个 `do_llm` 信封, **host agent 自己跑 LLM**, 把**原始输出**作为 `chisha continue --result` 喂回 (并回显 `--step <step_token>`)。host 就一个循环: 回包带 `do_llm` 就跑它喂回, 直到 `status=ready` 出 cards。

> **接入协议已折叠简化**: 老的 `chisha agent start / resolve-intent / apply-rerank` (及 `python -m chisha.agent_cli`) 保留为 deprecated alias 一版, 仍可用但请迁到 `eat / continue / choose`; `llm_request_spec` 字段同样保留为 `do_llm` 的别名一版。

### Flow A — 无 context (默认推荐, 用户只说"今天中午吃啥")

```
host agent                         chisha CLI
    │
    │   chisha eat lunch
    │ ───────────────────────────────────► 
    │                                    返回 JSON:
    │                                    {
    │                                      "recommendation_id": "<rid>",
    │                                      "round": "R1",
    │                                      "status": "resolved",
    │                                      "candidate_count": <n>,
    │                                      "do_llm": { ... },          ← rerank spec
    │                                      "step_token": "<rid>::R1::rerank",
    │                                      "next": "continue --id <rid> --result <json> --step <step_token>"
    │                                    }
    │ ◄───────────────────────────────────
    │
    │   ▶ 用 do_llm 调 LLM 跑 rerank (host 的 LLM)
    │
    │   chisha continue --id <rid> --result '<你的 LLM 原始输出>' --step <step_token>
    │ ───────────────────────────────────►
    │                                    返回 JSON:
    │                                    { "ok": true, "status": "ready",
    │                                      "fallback": false, "narrative": "...",
    │                                      "cards": [ {id, ...}, ... 5 个 ] }
    │ ◄───────────────────────────────────
    │
    │   ▶ 给用户看 5 个 cards, 用户选一个 (card_id = X)
    │
    │   chisha choose --id <rid> --card X --action accept
    │ ───────────────────────────────────►  (记录, 写 feedback)
```

### Flow B — 有 context (用户加了 refine, 例如 "想吃辣一点")

```
chisha eat lunch --context "想吃辣一点" [--from <prev_rid>]
   → status: "pending", do_llm: <extract spec>, step_token: <rid>::R1::extract
host 跑 LLM 拿到 intent JSON →
chisha continue --id <rid> --result '<intent_json>' --step <step_token>
   → status: "resolved", do_llm: <rerank spec>, step_token: <rid>::R1::rerank
host 跑 LLM 拿到 rerank JSON →
chisha continue --id <rid> --result '<rerank_json>' --step <step_token>
   → status: "ready", cards
chisha choose --id <rid> --card X --action accept
```

宿主不用区分 extract / rerank — 同一个 `continue` 循环, chisha 按 `step_token` 自动路由; host 只看回包有没有 `do_llm` (有就继续) vs `cards` (出结果)。

### 关键参数 (实际 CLI, 不是抽象描述)

| Verb | 必填参数 | 可选参数 |
|---|---|---|
| `eat` | `<lunch\|dinner>` (位置参数) | `--context "<用户原话>"`, `--from <prev_rid>` (refine 续轮), `--at-time YYYY-MM-DD` (time-travel) |
| `continue` | `--id <rid>` `--result <你的 LLM 原始输出 JSON>` `--step <step_token>` | — |
| `choose` | `--id <rid>` `--card <card_id>` `--action {accept\|skip}` | `--reason "<skip 原因>"` |

`--result` 传 LLM 原始输出 (raw payload), **不要**手包 `{correlation_id, payload}` 信封; `--step` 回显上一步 `step_token` (不透明)。老 verb (`start`/`resolve-intent`/`apply-rerank`) 仍作 deprecated alias。权威源: `chisha/agent_cli.py` (改前读 `docs/CONTRACTS.md` 「Agent CLI 协议」段).

### ⚠ refine 是逃生口 (P1 限制的解药)

用户表达 harvard_plate 之外的诉求, **走 refine, 不要拒答**. 但要知道 V2 schema 是**字段闭包**: 落 schema 内的诉求被 L1/L2 **硬过滤/打分** (强); schema 外的走 L3 narrative **软处理** (弱).

| 用户原话 | context 直传 (照原话, 不改写) | 命中 V2 槽 | 强度 |
|---|---|---|---|
| "我在减肥想吃低碳水" | `"少米饭少面, 蛋白多一点"` (可改写帮助命中) | `staple_avoid=["米饭","面"]` + raw_understanding | 主食硬避; 蛋白软 (L3) |
| "今天不想吃肉" | `"不要肉类"` | `ingredient_avoid=["肉"]` | 硬过滤 |
| "想吃辣一点" | `"想吃辣"` | `cuisine_candidates_expanded=[川,湘,贵,重]` | L1 扩召回 |
| "想喝点汤" | `"想喝汤"` | `constrain.wants_soup=true` | L2 加分 |
| "不要太油腻" | `"清淡, 少油"` | `constrain.oil="low"` | L2 油偏好加分 |
| "30 块以内" | `"30 块以内"` | `constrain.price_max=30` | L2 价格筛 |
| "孕期忌口" | `"不要生鱼, 不要半熟蛋"` (用具体食材, 别用抽象词) | `ingredient_avoid=["生鱼","半熟蛋"]` | 硬过滤 |
| "高蛋白" | `"蛋白多一点"` | (schema 无蛋白槽) raw_understanding only | L3 软 |
| "素食" | `"不要肉类"` | `ingredient_avoid=["肉"]` | 硬过滤 (没 vegetarian 维度) |

**编码规则**:
- 大多数情况直传用户原话即可 (chisha extract LLM 会尝试解析)
- 用户用抽象词 ("低碳水/素食/孕期"), agent 可帮用户具象化 → context 用更具体的食材/主食词, 命中硬过滤
- 命中 schema 内的诉求, V2 解析 + L1/L2 真过滤 (强力)
- 命中 schema 外的诉求, raw_understanding 字段保留原话, L3 LLM 跑 rerank 时会软排序
- **绝不要在 host agent 层硬编码"不支持 X"** — chisha 一定能跑, 区别只是强 vs 软

---

## §5 Configuration Knobs

| Knob | Default | How to change | 何时问用户 |
|---|---|---|---|
| `state_root` | `~/.chisha/` | env `CHISHA_STATE_ROOT` | 仅 Step 3 写不进时 |
| `zone` | shenzhen-bay | `chisha onboard --zone <x> --force` 重跑 | 装好后不可换 zone (多工区支持才行), 不问 |
| `methodology` | harvard_plate | `chisha onboard --methodology <x> --force` 重跑 | 不问, refine 兜底 |
| LLM provider | **host agent 自己跑** (`agent_external`) — chisha CLI 不调 LLM | 不可配, 也不需要 | **不问** |
| 反馈记录 | on | edit `~/.chisha/profile.yaml` | 不问, 默认开 |

---

## §6 Verify / Smoke Test

### `chisha doctor` 输出 shape (实测)

```json
{
  "ok": true,
  "protocol_version": "1.0",
  "candidate_schema_version": "2.1",
  "engine_version": "0.1.0",
  "root": "/path/to/install_root",
  "install_root": "/path/to/install_root",
  "state_root": "/Users/.../.chisha",
  "state_root_writable": true,
  "state_migrated": true,
  "legacy_state_pending_migration": false,
  "install_data_manifest_status": "ok",
  "user_resource_status": [ ... ],
  "manifest_path": ".../data/manifest.json",
  "bundle_artifact_version": 1,
  "bundle_data_schema_version": 1,
  "sandbox_enabled": false,
  "scope_ready": true,
  "notes": []
}
```

### 判断 "装好了" (4 条 acceptance)

- ✅ `ok == true`
- ✅ `install_data_manifest_status == "ok"`
- ✅ `state_root_writable == true` AND `legacy_state_pending_migration == false`
- ✅ `scope_ready == true`
- ✅ Step 7 smoke test 返回 `status == "resolved"` AND `candidate_count > 0`

(`engine_version` 是 chisha 自报版本, 可用作 informational; 没有独立的 `--version` flag, 也没有 `llm_provider` 字段 — host agent 自己负责 LLM 配置.)

---

## §7 Failure Triage

> 注: chisha 的 verb 错误统一**输出 JSON 到 stdout** (`{"ok": false, "error": {"code": "X", "message": "..."}}`) + 进程退出码 1. 不是 stderr. 下方"何处出"列指返回 JSON 的命令.

| 错误码 / 现象 | 何处出 | Agent 下一步 |
|---|---|---|
| `install_data_manifest_status == "incompatible"` (raise `IncompatibleManifestError`) | doctor / start | bundle 与引擎版本不兼容. Step 2 `--force` 重装. 仍失败 → 上报 issue |
| `install_data_manifest_status == "missing"` | doctor | bundle 没装好. Step 2 重装 |
| `state_root_writable == false` | doctor | ASK USER: `CHISHA_STATE_ROOT=/tmp/chisha` 临时换? |
| `legacy_state_pending_migration == true` | doctor | 跑 `chisha migrate-state --dry-run` → 用户确认后 `chisha migrate-state` |
| JSON `error.code == "LOAD_INPUTS"` | eat / continue | profile/zone 数据缺失. 跑 `chisha doctor` 看 `user_resource_status` 哪里红 |
| JSON `error.code == "PREPARE"` | eat | recall/score 链路问题. 检查 zone 数据完整性, 上报 issue |
| JSON `error.code == "SCOPE_OR_TIME"` | eat / continue | scope guard 或 --at-time 解析失败. 检查 CHISHA_STATE_ROOT |
| JSON `error.code == "ROUND_STATE"` | eat / continue | round_store 状态冲突 (例如对已 ready 且无回放的 rid 又调 continue). 重起一轮 `chisha eat ...` |
| JSON `error.code == "STEP_REQUIRED"` / `"BAD_STEP"` / `"STEP_MISMATCH"` | continue | `--step` 漏传 / 非法 / sid 不符. 回显上一步回包里的 `step_token` 原值即可 |
| JSON `error.code == "BAD_ID"` / `"BAD_JSON"` / `"BAD_ACTION"` | 各 verb | 参数 schema 错. 按 §4 流程图重新对齐参数 |
| JSON `error.code == "NO_PREPARED"` / `"NO_FALLBACK_PLAN"` | continue (rerank 步) | 对老 rid 调 continue, round state 已过期. 重起一轮 |
| JSON `error.code == "CARD_NOT_FOUND"` | choose | `--card <id>` 不在当前最新一轮 cards 里 (用户从过期 cards 选). 重起一轮或让用户选当前 cards 之一 |
| JSON `error.code == "CORRELATION"` | continue | `--step` 回显的 token 与当前 round 不符 (stale/串轮), 或 host 跑 LLM 时改了 `do_llm` 内容. host 必须把 `do_llm.system + tools + messages` 原样发 LLM, 并回显 `step_token` |
| 用户在深圳湾外想推荐 | — | 套 scope_limitations.zone 模板, **不要尝试自造** zone |
| 用户想生酮 / 增肌 / 低碳水 / 素食 | — | **走 §4 refine, 不要回 "不支持"**. 命中 schema 强, 命中外 L3 软, 都比拒答好 |
| 用户问 "为啥推这家" | — | 看 `continue` 返回的 `cards[i]` 里的字段 + `narrative` (L3 写的理由) |

---

## §8 Update / Uninstall

### Update

```bash
uv tool upgrade chisha-meal
chisha doctor   # 验证新版 manifest 兼容
```

- state (`~/.chisha/`) 不动, profile / 反馈历史保留
- 新版 manifest 不兼容 → `install_data_manifest_status == "incompatible"`, 按 §7 处置

### Uninstall

```bash
uv tool uninstall chisha-meal
rm -rf ~/.claude/skills/chisha-meal/
# ASK USER: 要保留 ~/.chisha/ 反馈历史吗? 不要的话 rm -rf ~/.chisha/
```

---

## Appendix — Project Pointers (for context, not for install)

- 仓库: https://github.com/zidanema/chisha
- 人版 README: [README.md](README.md)
- 产品 PRD: [docs/PRD.md](docs/PRD.md)
- 推荐链路活契约: [docs/CONTRACTS.md](docs/CONTRACTS.md)
- 路线 + 已砍清单: [docs/ROADMAP.md](docs/ROADMAP.md)
- 本文档承诺的下一步 (规划中): 多工区数据包 + 多 host adapter

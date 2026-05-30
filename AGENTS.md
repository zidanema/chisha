# AGENTS.md — chisha-meal 接入 Spec (for AI Agents)

> **You are an AI agent** (Claude Code / Cursor / Codex CLI / Cline / OpenClaw / 其他) **and your user asked you to set up or drive chisha-meal.**
>
> Read this file in full before any action. If you are a human, see [README.md](README.md) instead.

> **接入形态 = 形态B 自包含 bundle (D-105 / D-105.1)**。chisha-meal 是一个**自包含 skill 文件夹** (`代码 + 数据 + vendored 依赖 + wrapper` 全在里面), 拷进 `~/.claude/skills/chisha-meal/` 即用 —— **零全局安装、运行期零联网、零 pip、零 pydantic**。没有全局 `chisha` 命令 (形态A `uv tool install` 已退役); 所有调用走 bundle 内 wrapper。
>
> **本文覆盖的范围 (诚实边界)**:
> - ✅ **你已经有 bundle 文件夹** (维护者发给你 / 你从别处拷到了) → §1–§3 教你落位 + 初始化 + 自检。
> - ✅ **你有本仓** (你是维护者的 agent) → §2 Step 0 教你 `build_skill_bundle --install` 构建并安装。
> - ⛔ **你既没 bundle 也没本仓** → **当前无法自动获取**。形态B 的**远程分发协议** (任意 agent 如何从公网拉到 bundle) **尚未设计** (D-105.1 列为未来工作)。这种情况直接告诉用户: "目前拿不到安装包, 需要维护者手动给你一份 bundle 文件夹"。**不要**尝试 `uv tool install` / `pip install` / `git clone` —— 那是已退役的形态A, 跑不通。
>
> 装完之后**怎么用** (do_llm 循环 / eat·continue·choose / refine) 见 §4 起, 这部分对所有 host 通用且与代码 1:1。

---

## §0 接入契约 (Contract)

```yaml
chisha-meal:
  contract_version: "2.0"             # 形态B (bundle wrapper). 1.x = 已退役的形态A.
  what: |
    个人原则派点餐推荐引擎 (餐厅 + 菜品组合). 三阶段链路:
    L1 召回 → L2 15 维打分 → L3 LLM 精排 + 写理由.
    装完后 host agent 走 wrapper `… eat / continue / choose` 完成一轮推荐.

  install_form: self-contained-bundle  # 一个 skill 文件夹, 不注册 PATH, 不装包
  install_target: ~/.claude/skills/chisha-meal/   # bundle 落位 (Claude Code skill 目录)
  state_target:   ~/.chisha/           # 用户 state, 与 bundle 物理分离; env CHISHA_STATE_ROOT 可覆盖
  bundle_size:    "~20 MB"             # 含 shenzhen-bay 数据 (打标后 ~19MB) + core + vendored yaml

  requires:
    host_provides_llm: true            # ⚠ chisha 自身零 LLM (刻意设计).
                                       # host agent 必须自己跑 LLM, wrapper 返回一个
                                       # do_llm 信封, host 跑完把原始输出喂回
                                       # `… continue --result <json> --step <token>`. 见 §4.
    python: ">= 3.11"                  # wrapper 硬 guard; macOS 自带 3.9 不够
    os: "POSIX (macOS / Linux)"        # core 用 fcntl 文件锁; Windows 仅 WSL
    fs_write: ~/.chisha/               # 用户 state (profile / logs / feedback)
    shell_exec: true                   # 跑 wrapper
    network_at_runtime: false          # bundle 自包含, 推荐链路运行期不联网
    package_manager: none              # 运行期不需要 uv / pip (依赖已 vendored)

  produces:
    wrapper: "python3 ~/.claude/skills/chisha-meal/scripts/chisha"
             # 唯一入口; 子命令: eat / continue / choose / doctor / onboard / skills add / migrate-state
             # (deprecated alias: agent / install-skill / start / resolve-intent / apply-rerank)
    skill:   "~/.claude/skills/chisha-meal/SKILL.md"   # bundle 自带; Claude Code 自动触发
    state_dir: "~/.chisha/"            # profile.yaml + logs/ + feedback_history.jsonl

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
    auto_trigger: "Claude Code (bundle 自带 SKILL.md, 说'今天吃啥'自动触发)"
    other_hosts: |
      Cursor / Codex CLI / OpenClaw / ChatGPT / Cline / Continue: 可手动用 wrapper
      调 `… eat lunch` / `continue` (协议 §4 通用), 但**没有自动触发的 skill**.
      多 host adapter 还在规划中. 见 §1 NOT_SUPPORTED 模板.
  distribution:
    available: "维护者本地 build (有本仓) / 手动拷贝 bundle 文件夹"
    not_yet: |
      **远程分发未定型** (D-105.1): 非维护者、无本仓的 agent 如何从公网拉到 bundle —
      尚未设计. 没 bundle 又没本仓时不要自造安装路径, 直接告知用户需要维护者给 bundle.
  data_integrity:
    note: |
      manifest 只做"数据产物↔引擎"兼容性闸门, 不做完整性 / 来源校验 (留位待做).
      走 git+https GitHub transport 由 commit hash 兜底; 外部 transport (S3/镜像) 需自验 hash + 签名.
```

---

## §1 兼容性闸门 (Gate)

| Item | Required | If fail |
|---|---|---|
| OS | macOS / Linux (Windows 仅 WSL) | early-exit, 告知用户当前 OS 不支持 (core 用 fcntl) |
| Python | ≥ 3.11 在 PATH | ASK USER 装 Python 3.11+ (`brew install python@3.12` / `pyenv` / `uv python install`), 退出。macOS 自带 `python3`=3.9 不够 |
| Bundle 在手 | `~/.claude/skills/chisha-meal/` 存在, 或你有 bundle 文件夹可拷, 或你有本仓可 build | 三者皆无 → 用 NO_BUNDLE 模板回话 (见下), **不要** uv/pip/clone |
| LLM provider | **host 就是 LLM** (你, 当前 agent)。wrapper 不直接调 LLM, 不需要任何 `*_API_KEY` | 见下方注释; 不要 ASK USER |
| Host agent | **Claude Code** 才有自动触发; 其它 host 可手动调 wrapper | 用下方 NOT_SUPPORTED 模板回话 |

> **关于 LLM key (反直觉, 必读)**: §0 `host_provides_llm: true` 是字面意思 — **你 (host agent)** 用自己的 LLM 跑 wrapper 发的 `do_llm` 信封, 把原始输出喂回 `… continue`. chisha 自己零 LLM, 把自己标记 `resolved_provider=agent_external`. 所以:
> - 安装 / onboard / smoke test 全程**不需要任何 key**。
> - `… eat / continue / choose` 全程**不需要任何 key**。
> - Claude Code 通过订阅/OAuth 用模型, env 里本来就没 key — 正常, **不要**因探测不到 key 而 ASK USER。
> - 唯一会用到 key 的场景: 维护者跑 dev 脚本 (`scripts/tag_via_api.py` 打标) — 与接入无关。

### NO_BUNDLE 回话模板 (既没 bundle 也没本仓时用)

> chisha-meal 现在是**自包含 skill bundle** 形态, 装它需要先有一份 bundle 文件夹。目前**没有公开的远程安装方式** (作者还没做远程分发)。所以我没法替你从网上拉下来装。
>
> 两条路:
> 1. **找作者要 bundle**: 让 chisha 维护者把 `chisha-meal` 这个 skill 文件夹发你一份, 我帮你拷进 `~/.claude/skills/chisha-meal/` 并初始化。
> 2. **你本地有 chisha 仓**: 告诉我仓在哪, 我用仓里的 `build_skill_bundle` 构建并安装。
>
> 你是哪种情况?

### NOT_SUPPORTED 回话模板 (host 不是 Claude Code 时用)

> chisha-meal 目前**只对 Claude Code 提供自动触发 skill**。你用的是 [Cursor / Codex / ChatGPT / ...]。
>
> 如果我手上有 bundle, 仍可帮你落位, 之后你在命令行用 wrapper 打 `python3 ~/.claude/skills/chisha-meal/scripts/chisha eat lunch` 触发推荐 (没有"今天吃啥"自动触发)。多 host 自动触发还在规划中。要这样装吗?

---

## §2 安装协议 (Idempotent)

> 形态B 的"装"= 把 bundle 文件夹放到 `~/.claude/skills/chisha-meal/`, 再用 wrapper 初始化 state。下面每步 **pre / action / verify / on_fail**, 不达 verify 不进下一步。先定义 wrapper 简写:
>
> ```
> CHISHA = python3 ~/.claude/skills/chisha-meal/scripts/chisha
> ```
> (实跑把 `CHISHA` 替成整条命令。)

### Step 0 — 取得 / 落位 bundle (按你手上有什么, 三选一)

- **A. bundle 已就位** (`~/.claude/skills/chisha-meal/scripts/chisha` 已存在, 例如你正读它的 SKILL.md): 跳到 Step 1。
- **B. 你有 bundle 文件夹** (别处拷来的): 整个文件夹拷到 `~/.claude/skills/chisha-meal/` (覆盖前先备份旧的)。
- **C. 你有本仓** (维护者路径):
  ```bash
  uv run python -m scripts.build_skill_bundle --out tmp/skill_bundle --install
  # --install: staged 覆盖 ~/.claude/skills/chisha-meal/ (copy-to-temp-first + 备份旧内容)
  ```
- 三者皆无 → §1 NO_BUNDLE 模板, 停。

### Step 1 — Python 闸门

- **action**: `python3 --version`
- **verify**: ≥ 3.11
- **on_fail**: ASK USER 装 3.11+ (`brew install python@3.12` / `pyenv install 3.12` / `uv python install 3.12`), 确保在 PATH。wrapper 本身也会 guard 并给明确报错。

### Step 2 — 自检 (doctor)

- **pre**: Step 0+1 通过
- **action**: `CHISHA doctor`  (默认输出 JSON 到 stdout)
- **verify**: JSON 含 `state_root: "..../.chisha"` (或 `$CHISHA_STATE_ROOT`) AND `state_root_writable: true` AND `install_data_manifest_status == "ok"`
- **on_fail**:
  - `legacy_state_pending_migration: true` → `CHISHA migrate-state --dry-run` 给用户看 → 确认后 `CHISHA migrate-state`
  - `state_root_writable: false` → ASK USER: "用 `CHISHA_STATE_ROOT=/path/to/writable` 指别的目录吗?"
  - `install_data_manifest_status == "incompatible"` → bundle 与引擎不兼容 (`IncompatibleManifestError`)。重取一份匹配的 bundle (Step 0); 仍失败上报 issue
  - `install_data_manifest_status == "missing"` → bundle 没装好 / 数据缺失, 重做 Step 0

### Step 3 — ⚠ ASK USER (1 question, 必问, 不要假设)

```
Q1 — 你在哪个城市 / 工区?
     Default: shenzhen-bay (深圳湾)
     If 答非深圳湾: 套 scope_limitations.zone 模板回话, 询问是否仍想装 (能跑但推不到本地店).
```

**不要问 LLM key** — 见 §1 注释。wrapper 不调 LLM, 你 (host agent) 就是 LLM。`~/.chisha/.env` 不需要任何 key。
**不要问 daypart** — 每轮 `… eat {lunch|dinner}` 显式传, 不持久化默认。

### Step 4 — onboard (初始化 profile + skill + dry start)

- **pre**: Step 1-3 通过
- **action**:
  ```bash
  CHISHA onboard --zone shenzhen-bay --methodology harvard_plate
  ```
- **verify**: stdout JSON `steps` 全绿 AND `~/.chisha/profile.yaml` 存在 AND `~/.claude/skills/chisha-meal/SKILL.md` 存在
- **on_fail**: 看 stdout JSON 的 `steps` 数组定位失败步骤, 按 §7 triage

### Step 5 — Smoke test

- **pre**: Step 4 通过
- **action**: `CHISHA eat lunch`  (默认输出 JSON 到 stdout)
- **verify**: JSON 含 `ok: true` AND `status == "resolved"` AND `candidate_count > 0` AND `do_llm != null`
- **on_fail**:
  - `status == "pending"` → 不该出现 (无 `--context` 时直走 resolved); 上报 issue
  - `error.code == "LOAD_INPUTS"` → 数据/profile 问题, 回 Step 2 doctor 看 `user_resource_status`
  - `error.code == "PREPARE"` → recall/score 链路问题, 看 stderr 详情

### Step 6 — Report to user

告诉用户 (中文, 一段话):

> chisha-meal 装好了。你现在可以在任意目录跟 Claude Code 说"今天中午吃啥"或"晚上吃啥", 它会从深圳湾 334 家店里推 5 个组合让你选。不满意可以 refine (例如"想吃辣一点"/"少米饭"/"想喝汤")。设置在 `~/.chisha/profile.yaml`, 反馈在 `~/.chisha/feedback_history.jsonl`。
>
> ⚠ 目前只覆盖深圳湾 + 哈佛餐盘默认; 其他城市 / 饮食法等后续支持。

---

## §3 Claude Code Adapter

bundle 自带 `SKILL.md` (拷进来时就在 `~/.claude/skills/chisha-meal/SKILL.md`), Claude Code 自动发现并触发。该文件由 `chisha skills add` (= bundle 内 `agent_skill_init` 单一源) 生成, **不要手动编辑**; `onboard` 已 idempotent 重装它。

验证:
- `ls ~/.claude/skills/chisha-meal/SKILL.md` 存在
- 内含 `CHISHA = python3 ~/.claude/skills/chisha-meal/scripts/chisha` wrapper 约定 + 扁平 `eat` / `continue` / `choose` (P1 CLI), 不是旧的 `uv run python -m chisha.agent_cli` 或全局 `chisha`

If 用户用其它 host (Cursor / Codex / ChatGPT / Cline / Continue / OpenClaw):
- **不要**依赖自动触发; bundle 仍在 `~/.claude/skills/chisha-meal/`, 直接用 wrapper 命令行调 `CHISHA eat lunch`
- 自动触发 skill 等后续多 host 支持

---

## §4 稳态调用协议 (装完之后怎么用)

⚠ **核心设计**: chisha 自身**零 LLM**。wrapper 返回一个 `do_llm` 信封, **host agent 自己跑 LLM**, 把**原始输出**作为 `… continue --result` 喂回 (并回显 `--step <step_token>`)。host 就一个循环: 回包带 `do_llm` 就跑它喂回, 直到 `status=ready` 出 cards。

> **接入协议已折叠简化**: 老的 `… agent start / resolve-intent / apply-rerank` (及 `python -m chisha.agent_cli`) 保留为 deprecated alias 一版, 仍可用但请迁到 `eat / continue / choose`; `llm_request_spec` 字段同样保留为 `do_llm` 的别名一版。

> 下文 `CHISHA` = `python3 ~/.claude/skills/chisha-meal/scripts/chisha` (§2 简写)。

### Flow A — 无 context (默认推荐, 用户只说"今天中午吃啥")

```
host agent                         chisha wrapper
    │
    │   CHISHA eat lunch
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
    │   CHISHA continue --id <rid> --result '<你的 LLM 原始输出>' --step <step_token>
    │ ───────────────────────────────────►
    │                                    返回 JSON:
    │                                    { "ok": true, "status": "ready",
    │                                      "fallback": false, "narrative": "...",
    │                                      "cards": [ {id, ...}, ... 5 个 ] }
    │ ◄───────────────────────────────────
    │
    │   ▶ 给用户看 5 个 cards, 用户选一个 (card_id = X)
    │
    │   CHISHA choose --id <rid> --card X --action accept
    │ ───────────────────────────────────►  (记录, 写 feedback)
```

### Flow B — 有 context (用户加了 refine, 例如 "想吃辣一点")

```
CHISHA eat lunch --context "想吃辣一点" [--from <prev_rid>]
   → status: "pending", do_llm: <extract spec>, step_token: <rid>::R1::extract
host 跑 LLM 拿到 intent JSON →
CHISHA continue --id <rid> --result '<intent_json>' --step <step_token>
   → status: "resolved", do_llm: <rerank spec>, step_token: <rid>::R1::rerank
host 跑 LLM 拿到 rerank JSON →
CHISHA continue --id <rid> --result '<rerank_json>' --step <step_token>
   → status: "ready", cards
CHISHA choose --id <rid> --card X --action accept
```

宿主不用区分 extract / rerank — 同一个 `continue` 循环, chisha 按 `step_token` 自动路由; host 只看回包有没有 `do_llm` (有就继续) vs `cards` (出结果)。

### 关键参数 (实际 CLI, 不是抽象描述)

| Verb | 必填参数 | 可选参数 |
|---|---|---|
| `eat` | `<lunch\|dinner>` (位置参数) | `--context "<用户原话>"`, `--from <prev_rid>` (refine 续轮), `--at-time YYYY-MM-DD` (time-travel) |
| `continue` | `--id <rid>` `--result <你的 LLM 原始输出 JSON>` `--step <step_token>` | — |
| `choose` | `--id <rid>` `--card <card_id>` `--action {accept\|skip}` | `--reason "<skip 原因>"` |

`--result` 传 LLM 原始输出 (raw payload), **不要**手包 `{correlation_id, payload}` 信封; `--step` 回显上一步 `step_token` (不透明)。老 verb (`start`/`resolve-intent`/`apply-rerank`) 仍作 deprecated alias。权威源: bundle 内 `chisha/agent_cli.py` (改前读 [docs/CONTRACTS.md](docs/CONTRACTS.md) 「Agent CLI 协议」段)。

### ⚠ refine 是逃生口 (scope 限制的解药)

用户表达 harvard_plate 之外的诉求, **走 refine, 不要拒答**。但要知道 V2 schema 是**字段闭包**: 落 schema 内的诉求被 L1/L2 **硬过滤/打分** (强); schema 外的走 L3 narrative **软处理** (弱)。

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

## §5 配置旋钮

| Knob | Default | How to change | 何时问用户 |
|---|---|---|---|
| `state_root` | `~/.chisha/` | env `CHISHA_STATE_ROOT` | 仅 Step 2 写不进时 |
| `zone` | shenzhen-bay | `CHISHA onboard --zone <x> --force` 重跑 | 装好后不可换 zone (多工区支持才行), 不问 |
| `methodology` | harvard_plate | `CHISHA onboard --methodology <x> --force` 重跑 | 不问, refine 兜底 |
| LLM provider | **host agent 自己跑** (`agent_external`) — wrapper 不调 LLM | 不可配, 也不需要 | **不问** |
| 反馈记录 | on | edit `~/.chisha/profile.yaml` | 不问, 默认开 |

---

## §6 Verify / Smoke Test

### `CHISHA doctor` 输出 shape (实测)

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

(install_root 在形态B = bundle 目录 `~/.claude/skills/chisha-meal/`; doctor 同时自检 python 版本 / vendored pyyaml / manifest。)

### 判断 "装好了" (acceptance)

- ✅ `ok == true`
- ✅ `install_data_manifest_status == "ok"`
- ✅ `state_root_writable == true` AND `legacy_state_pending_migration == false`
- ✅ `scope_ready == true`
- ✅ Step 5 smoke test 返回 `status == "resolved"` AND `candidate_count > 0`

(`engine_version` 是 chisha 自报版本, informational; 没有独立 `--version` flag, 也没有 `llm_provider` 字段 — host agent 自己负责 LLM。)

---

## §7 Failure Triage

> 注: chisha 的 verb 错误统一**输出 JSON 到 stdout** (`{"ok": false, "error": {"code": "X", "message": "..."}}`) + 退出码 1。不是 stderr。下方"何处出"列指返回 JSON 的命令 (均经 `CHISHA` wrapper)。

| 错误码 / 现象 | 何处出 | Agent 下一步 |
|---|---|---|
| `install_data_manifest_status == "incompatible"` (raise `IncompatibleManifestError`) | doctor / eat | bundle 与引擎版本不兼容。重取匹配 bundle (§2 Step 0)。仍失败 → 上报 issue |
| `install_data_manifest_status == "missing"` | doctor | bundle 没装好 / 数据缺失。重做 §2 Step 0 |
| `state_root_writable == false` | doctor | ASK USER: `CHISHA_STATE_ROOT=/tmp/chisha` 临时换? |
| `legacy_state_pending_migration == true` | doctor | `CHISHA migrate-state --dry-run` → 用户确认后 `CHISHA migrate-state` |
| wrapper 报 python 版本错 (退出码 2) | 任意命令 | python3 < 3.11。ASK USER 装 3.11+ 并确保 PATH 里那个 python3 跑 wrapper |
| JSON `error.code == "LOAD_INPUTS"` | eat / continue | profile/zone 数据缺失。跑 `CHISHA doctor` 看 `user_resource_status` 哪里红 |
| JSON `error.code == "PREPARE"` | eat | recall/score 链路问题。检查 zone 数据完整性, 上报 issue |
| JSON `error.code == "SCOPE_OR_TIME"` | eat / continue | scope guard 或 --at-time 解析失败。检查 CHISHA_STATE_ROOT |
| JSON `error.code == "ROUND_STATE"` | eat / continue | round_store 状态冲突 (例如对已 ready 且无回放的 rid 又调 continue)。重起一轮 `CHISHA eat ...` |
| JSON `error.code == "STEP_REQUIRED"` / `"BAD_STEP"` / `"STEP_MISMATCH"` | continue | `--step` 漏传 / 非法 / sid 不符。回显上一步回包里的 `step_token` 原值即可 |
| JSON `error.code == "BAD_ID"` / `"BAD_JSON"` / `"BAD_ACTION"` | 各 verb | 参数 schema 错。按 §4 流程图重新对齐参数 |
| JSON `error.code == "NO_PREPARED"` / `"NO_FALLBACK_PLAN"` | continue (rerank 步) | 对老 rid 调 continue, round state 已过期。重起一轮 |
| JSON `error.code == "CARD_NOT_FOUND"` | choose | `--card <id>` 不在当前最新一轮 cards 里 (用户从过期 cards 选)。重起一轮或让用户选当前 cards 之一 |
| JSON `error.code == "CORRELATION"` | continue | `--step` 回显的 token 与当前 round 不符 (stale/串轮), 或 host 跑 LLM 时改了 `do_llm` 内容。host 必须把 `do_llm.system + tools + messages` 原样发 LLM, 并回显 `step_token` |
| 用户在深圳湾外想推荐 | — | 套 scope_limitations.zone 模板, **不要尝试自造** zone |
| 用户想生酮 / 增肌 / 低碳水 / 素食 | — | **走 §4 refine, 不要回 "不支持"**。命中 schema 强, 命中外 L3 软, 都比拒答好 |
| 用户问 "为啥推这家" | — | 看 `continue` 返回的 `cards[i]` 里的字段 + `narrative` (L3 写的理由) |

---

## §8 Update / Uninstall

### Update

形态B 没有包管理器升级。更新 = **重新落位一份新 bundle** (覆盖旧 skill 文件夹):

```bash
# 有本仓 (维护者): 重 build + install
uv run python -m scripts.build_skill_bundle --out tmp/skill_bundle --install
# 有新 bundle 文件夹: 整个覆盖 ~/.claude/skills/chisha-meal/ (build --install 已自动备份旧的)
CHISHA doctor   # 验证新版 manifest 兼容
```

- state (`~/.chisha/`) 与 bundle 物理分离, **更新不动 state** — profile / 反馈历史保留
- 新 bundle 引擎与旧数据不兼容 → `install_data_manifest_status == "incompatible"`, 按 §7 处置

### Uninstall

```bash
rm -rf ~/.claude/skills/chisha-meal/      # 删 bundle (代码 + 数据)
# ASK USER: 要保留 ~/.chisha/ 反馈历史吗? 不要的话 rm -rf ~/.chisha/
```

---

## Appendix — Project Pointers (for context, not for install)

- 仓库: https://github.com/zidanema/chisha  (public; 但 agent 从公网自动拉取 bundle 的远程分发协议未定型, 见 §0 distribution)
- 人版 README: [README.md](README.md)
- 产品 PRD: [docs/PRD.md](docs/PRD.md)
- 推荐链路活契约: [docs/CONTRACTS.md](docs/CONTRACTS.md)
- 路线 + 已砍清单: [docs/ROADMAP.md](docs/ROADMAP.md)
- 本文档承诺的下一步 (规划中): 形态B 远程分发协议 + 多工区数据包 + 多 host adapter

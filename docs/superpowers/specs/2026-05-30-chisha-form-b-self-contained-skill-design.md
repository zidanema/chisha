# chisha 形态 B:自包含 skill 分发 — 设计

> 状态: 设计定稿待 review · 2026-05-30 · 待开决策 **D-105**
> Codex 共商已过(本次 high-risk 改动前双触点之一,agentId a62755b5337a220af)
> 前置: D-074(AI-friendly 接入) · D-104(agent-only core 解耦) · D-102(install/state 二分)

## 1. 背景与目标

AI-friendly 接入当前是**形态 A**(D-074 落地):chisha 作为独立包 `uv tool install chisha-meal` 上全局 PATH,`~/.claude/skills/chisha-meal/` 只放一个薄 SKILL.md 指向全局 `chisha` CLI。问题:接入要两步(装包 + onboard),代码不随 skill 走,分发给别人/别的机器要先在那台机器装包。

**形态 B(本设计)**:把 chisha agent-only core 代码直接 bundle 进 skill 文件夹,**自包含、拷贝即用、零全局安装、运行期零联网**。一个 skill 文件夹 = 代码 + 数据 + vendored 依赖 + 说明,拷进 `~/.claude/skills/` 即可被宿主 agent 驱动。**用户拍板:B 替代 A 当默认接入形态。**

成功标准:在一台**只有 python3(≥3.11)、没有 uv、没有 pydantic、没有联网**的 POSIX 机器上,把 skill 文件夹拷进 `~/.claude/skills/chisha-meal/`,宿主 agent 能跑通 `doctor → onboard → eat → continue → choose → refine` 全链路。

## 2. 范围与非目标

**范围内:** 砍 core 的 pydantic 依赖、vendoring pyyaml、build_skill_bundle 升级为真 installer、运行入口 wrapper、agent_skill_init 生成 B 形态 SKILL.md、A 退役(additive)。

**非目标 / 诚实边界:**
- **不是"跨平台",是 POSIX-only(macOS + Linux)。** core 的 `recall` / `trace_store` / `agent_round_store` 用 `fcntl` 文件锁 → Windows 不支持(除非 WSL)。对目标场景(Mac mini + 可能 Linux/同事 Mac)足够。SKILL.md / doctor 要显式声明此限制。
- 不碰 core 算法链路(召回/打分/精排/refine)、协议层(agent_protocol)、state DI(`~/.chisha`)、data 内容。
- 不做产物签名 / plugin marketplace 打包(CLAUDE.md 范围红线,本设计是"代码随 skill 走"而非 marketplace plugin 形态)。

**触碰 high-risk 白名单:** `agent_skill_init`(白名单 agent_*)。`collector_contract` / `loader` / `cli` 是 core 但非白名单热路径(CLAUDE.md 注明)。→ 强制 baseline 0-diff 守门 + Codex commit review。

## 3. 架构:生产端 / 消费端两角色

**生产端(repo,我/维护者):** `scripts/build_skill_bundle.py --install` 从 core 子树切出自包含 bundle,vendoring pyyaml,产 B 形态 SKILL.md + wrapper,原子覆盖到目标 skill 目录(并备份旧内容)。分发 = 把该文件夹打包拷走。

**消费端(任意 POSIX 机器):** 拿到 skill 文件夹放进 `~/.claude/skills/chisha-meal/`。首次 `doctor` 自检 + `onboard` 建 profile(`~/.chisha`)。之后宿主 agent 经 SKILL.md 驱动。

**目标目录布局**(`install_root()` 靠 `prompts/` 与 `chisha/` 同级感知 bundle,必须保持):
```
~/.claude/skills/chisha-meal/
  chisha/            # core 子树(含 cli.py — 见 §4.5)
  vendor/yaml/       # vendored 纯 Python pyyaml
  data/              # restaurants + dishes_tagged + manifest + aliases
  prompts/ profiles/ # 与 chisha/ 同级(install_root 探测点)
  profile.yaml       # onboard 用的 profile 模板(当前 builder 漏拷 — 见 §4.5)
  scripts/chisha     # 运行入口 wrapper(python3)
  SKILL.md           # B 形态交互层
```

## 4. 组件改动(7 步)

### 4.1 砍 pydantic(最重的一步)
`collector_contract.py` 是 **4 层嵌套递归校验**(CollectorOutput → Location → Restaurant → MenuItem),不是单层。改 dataclass + 手写 strict 校验,**必须逐层复刻这些语义,否则静默破坏数据 provenance gate**:
- **required-but-nullable**:`str | None` **无默认值** ≠ `= None`。dataclass 写 `= None` 会让 missing key 静默通过 → 必须区分"key 缺失"(fail)与"key 存在但值为 null"(pass)。
- **bool 泄漏**:strict 显式拒 `bool`(因 `bool` 是 `int` 子类)。手写数值检查必须 `not isinstance(v, bool)` 前置,否则 `True/False` 被当合法 number 吞入。
- **值域枚举**:`Literal["observed","unobserved"] | None` 等字段要校验枚举值,dataclass 不自带。
- **`extra="allow"` carry-through**:每层未知字段要保留(至少不报错),手写需显式决策。
- 校验失败的异常类型/消息要与现行为对齐(上游 loader 怎么 catch)。

### 4.2 slim requirements 收敛
删 `pydantic` + `python-dotenv` + `tenacity` + `ruamel-yaml`(core 闭包零 import,虚列)→ **core 运行期唯一第三方依赖 = pyyaml**。`SLIM_DEPS` 常量同步。

### 4.3 vendoring pyyaml
纯 Python pyyaml 拷进 `vendor/yaml/`。注意:
- `recall.py` / `methodology.py` 在**模块顶层** `import yaml`(非延迟)→ sys.path 注入必须在 dispatch 到 `cli:main` **之前**(wrapper 最早一行)。
- PyYAML 有 C 扩展 `_yaml`,`safe_load` 会试 `CLoader`。vendored 纯 Python 版要确认 `_yaml` 缺失走 except 不炸(或显式走 SafeLoader path)。
- sys.path 顺序:`bundle_root`(给 `chisha` 包)→ `vendor/`(给 `yaml`)→ 原有 paths。**不把 vendor 插最前**,防将来 bundle 内同名文件遮蔽。
- pyyaml 版本固化记录进 doctor 输出(重 build 换版本时行为漂移可追溯)。

### 4.4 运行入口 wrapper `scripts/chisha`
python3 脚本,职责按序:① `sys.version_info >= (3,11)` 硬 guard(macOS 系统 python3 可能 3.9/3.10,失败给清晰报错);② 注入 sys.path(§4.3 顺序);③ dispatch 到 `chisha.cli:main`。SKILL.md 命令改 `python3 ~/.claude/skills/chisha-meal/scripts/chisha <verb>`。

### 4.5 build_skill_bundle 升级为真 installer
- **移除 cli.py 排除**:当前排除清单把 `cli.py` 标"老/被取代",但 B 形态 wrapper dispatch 到 `chisha.cli:main` → 不修则 `ModuleNotFoundError`。cli.py 实为 B 形态入口,从 EXTRAS_MODULES 移除。
- **补拷 profile.yaml 模板**:`cli.py cmd_onboard` 需要它建用户 profile,当前 builder 漏拷。
- **改 SKILL_MD 常量**:从 `python -m chisha.agent_cli` + requirements-install 协议,改为 `scripts/chisha` + copy-folder 协议。
- 新增 `--install`:vendoring pyyaml + 写 wrapper + 原子覆盖到 `~/.claude/skills/chisha-meal/`(覆盖前备份旧内容)。

### 4.6 agent_skill_init 改写
生成 B 形态 SKILL.md(命令指向 wrapper,不再 `uv tool install`)。**high-risk**,additive:A 退役前保留旧行为版本不破坏。

### 4.7 onboard 在 B 形态
= 建 profile(`~/.chisha`)+ doctor。skill 本身已是拷进来的文件夹,onboard 不再装 skill(A 形态的 skill_init 步在 B 形态变为"确认 skill 在位 + 自检")。

## 5. 数据流

- **install(生产端)**:repo `build_skill_bundle --install` → 切 core 子树 + vendoring + 写 wrapper/SKILL.md → 原子覆盖目标目录。
- **onboard(消费端首次)**:`scripts/chisha onboard` → 建 `~/.chisha/profile.yaml` + doctor 自检(install_root 命中 / manifest ok / pyyaml 版本 / python 版本 / POSIX)。
- **运行时(每次 eat)**:宿主 agent 跑 `scripts/chisha eat` → wrapper 注入 sys.path → `cli:main` → core 链路(零 pydantic、用 vendored yaml)→ JSON 到 stdout,state 落 `~/.chisha`。

## 6. 错误处理

- python <3.11 → wrapper guard 给明确 message(非 import traceback)。
- `import yaml` 失败(vendor 缺失/path 没注入)→ doctor 显式报"vendored pyyaml 不可达",不让运行时裸 traceback。
- `install_root` 探测失败(布局没保持同级)→ doctor 报缺哪个目录,不静默。
- collector_contract 校验失败 → 保持现有异常语义,loader 上游不变。

## 7. 退役顺序与回滚(A → B,additive)

1. ship 步 4.1–4.5(B 能跑),**不动** `pyproject [project.scripts]` 与 A 的 onboard 行为。
2. 裸 python3 隔离实跑全链路 green + baseline 0-diff + pytest 全过。
3. 改默认文档(README/CLAUDE/SKILL)指向 B。
4. **最后**才退役 A 的 uv tool 入口(标 deprecated,保留一个 release 仍可 `uv tool install` 回滚)。
- A/B 共读同一 `~/.chisha` state(已中央化,profile/log format 不改 → 无 state 迁移)。
- B installer 原子覆盖 + 备份旧 skill → 回滚 = 恢复备份。

## 8. 测试与守门

- **baseline_l2_snapshot 0-diff**:砍 pydantic 后数据加载结果必须逐字节一致(collector_contract 改造的硬验收)。
- **pytest 全过** + 新增 collector_contract dataclass 校验的单测(覆盖 nullable/bool/Literal/extra 四陷阱 + 与旧 pydantic 行为对拍)。
- **真·裸 python3 隔离实跑**:全新 venv/容器,无 pydantic、无 uv、仅 vendored pyyaml,跑通 doctor→onboard→eat→continue→choose→refine。这是形态 B 的终极验收。
- Codex commit review(改 high-risk `agent_skill_init` 时强制)。

## 9. Codex 共商结论(已纳入)

优先级排序(均已落到上文对应节):(c) cli.py 排除 stale【§4.5】 → (a) bool/required-nullable 语义【§4.1】 → (b) yaml C 扩展 + path 注入时机【§4.3】 → (e) python 版本 guard + POSIX-only 声明【§4.4/§2】 → (d) 退役 additive【§7】。

## 10. 决策记录

落地后开 **D-105**(≤15 行):形态 B 自包含 skill 分发替代形态 A;砍 core pydantic + vendoring pyyaml;POSIX-only 限制;A additive 退役。同步 README / CONTRACTS(Agent CLI 协议段 + agent-only core/extras 边界段)/ CLAUDE.md(接入形态描述)。

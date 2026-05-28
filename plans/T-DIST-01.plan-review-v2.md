## B — 私有 GitHub repo 一行装: 硬推荐

- **结论: 选 Option 2 — repo 保持 private, 邀请 collaborator, 用 SSH: `uv tool install git+ssh://git@github.com/zidanema/chisha.git`.**
- 这不是"零配置一行装"; 它是"一次性 GitHub/SSH 授权后的一行装". 对 private repo 这是诚实边界。
- Option 1 公开 repo 是唯一真正接近 `uv tool install git+https://github.com/...` 零授权的一行装, 但它把代码和随 wheel/source 发布的数据公开; 除非你决定项目可开源, 不建议为了分发便利公开。
- Option 2 的工程面最稳: 不需要包索引、不需要 release asset 下载器、不需要 PAT 塞进命令; GitHub collaborator 权限 + 用户本机 SSH 是成熟路径。
- Option 2 的缺点可接受: 同事必须有 GitHub 账号、被邀请、配置 SSH key; 对 3-5 个同事比维护私有包源更便宜。
- Option 3 的关键假设是**错的/至少不能当事实用**: GitHub release asset API 文档写明 release asset/list asset endpoint 无认证只适用于 public resources, private repo 需要 Contents read 权限/token; 见 GitHub Docs release assets: https://docs.github.com/en/rest/releases/assets?apiVersion=2022-11-28
- 所以 private repo 的 release wheel 不能作为匿名 `uv tool install https://github.com/.../releases/download/...whl` 稳定方案; 仍要 token/登录, 复杂度不比 SSH 低。
- Option 4 不成立为"private PyPI alternative": GitHub Packages 官方支持 npm/RubyGems/Maven/Gradle/NuGet/Docker,未列 Python/PyPI; 且认证要求 PAT classic/read:packages,见 https://docs.github.com/en/packages/learn-github-packages/introduction-to-github-packages
- GitHub Packages 即便可通过旁路方案托管文件, 也不是标准 Python simple index; 不应把它放进本 sprint。
- 发布命令建议写成两档: private 默认 `uv tool install git+ssh://git@github.com/zidanema/chisha.git`; 若未来公开 repo, 再降级为 `uv tool install git+https://github.com/zidanema/chisha.git` 或 PyPI。

## C — 扩展性架构判决

- **结论: C 必须进 v2, 但只做加载架构和校验边界, 不做 zone bundle marketplace / 方法论生成器 UI。**
- Zone: install 内置只读 `data/shenzhen-bay`; user-level zone 放 `~/.chisha/data/<zone>/`; `onboard --zone xxx` 先查 user-level, 再查 install-level。
- Methodology: install 内置只读 `profiles/methodologies/harvard_plate.yaml`; user-level methodology 放 `~/.chisha/methodologies/<name>.yaml`; profile 只存 `methodology: <name>`。
- 当前 D-102 契约把 install_root 定义为引擎+只读数据, state_root 定义为 `~/.chisha/` 且 update 不碰 state (`docs/CONTRACTS.md:114-128`); C 的用户资源应跟着这个边界走。
- 当前 methodology loader 只支持 `root / profiles/methodologies/<name>.yaml` (`chisha/methodology.py:29-30,122-123`), 且严格 keyset/name mismatch hard-fail (`chisha/methodology.py:87-143`); v2 必须显式改 loader 策略, 不能只改 onboard。
- 当前 methodology schema 是代码常量+测试+示例 YAML, 不是独立 JSON Schema: keyset 在 `chisha/methodology.py:32-59`, 测试构造完整 spec 在 `tests/test_methodology.py:59-93`, 示例在 `profiles/methodologies/harvard_plate.yaml:13-76`。
- 用户级资源必须有 `doctor` 可观测: 列出选中 zone/methodology 来源为 `install|user`, 并在冲突/缺 manifest/校验失败时 fail-loud。

### C-a: user-level resource 住哪个 root

- **结论: 放 state_root, 不引入第三个 root; 可新增 helper 名 `user_resource_root()` 但它必须等于 `state_root.resolve(None)`。**
- 理由: D-102 已规定 `~/.chisha/` 活过 package update, user state 不被 install 覆盖 (`docs/CONTRACTS.md:116-120`); user zone/methodology 同样是用户拥有、跨版本保留的本地资产。
- 第三 root 会制造三根矩阵: install_root / state_root / extension_root, 增加 doctor、onboard、测试隔离、迁移、env override 的组合复杂度。
- 语义修正: 把 state_root 文案从"runtime mutable state"扩成"user-owned writable root"; 子目录区分 `logs/` runtime state、`profile.yaml` config、`data/` user zones、`methodologies/` user specs。
- 不要把 user methodology 放 `~/.chisha/profiles/methodologies/`; 那会伪装成 install layout. 用 `~/.chisha/methodologies/` 更清楚。

### C-b: 加载优先级语义

- **结论: 采用 additive + no override builtins + name collision fail-loud。**
- Zone 查找: 若 `data/<zone>` 同时存在于 install 和 state_root, 直接报 `RESOURCE_NAME_COLLISION`, 不猜用户想覆盖哪个。
- Methodology 查找: 若 `<name>.yaml` 同时存在于 install 和 state_root, 直接报错; 用户自定义必须换名, 例如 `harvard_plate_zd_custom`。
- 这比 user-level > install-level override 更稳: 内置资源随引擎升级有 manifest/测试保护, 用户覆盖同名会让 trace/debug 难判断实际语义。
- profile/onboard 要显示来源: `zone_source=user|install`, `methodology_source=user|install`。

### C-c: methodology spec schema 现状

- **结论: 当前没有给 LLM/SDK 用的正式 schema artifact; v2 至少要新增机器可读导出或命令。**
- 现状证据: schema 约束散在 `_REQUIRED_TOP_KEYS/_OPTIONAL_TOP_KEYS/_*_KEYS` (`chisha/methodology.py:32-59`) 和 `_validate_spec()` (`chisha/methodology.py:87-117`)。
- 示例 YAML 解释了字段和死字段边界 (`profiles/methodologies/harvard_plate.yaml:1-11,63-76`), 但不是可验证 schema。
- 如果 agent SDK 要 LLM 写 spec, 必须提供 `chisha methodology schema --json` 或 `chisha methodology template --name ...`; 只靠注释会导致 LLM 拼错字段, 现有 strict keyset 会 hard-fail。
- 先做 JSON Schema/模板导出, 不做自动应用; 写入后必须跑 `chisha methodology validate <file>`。

### C-d: manifest 闸门与 user-level 资源的兼容性

- **结论: install manifest 继续只管 install bundle; user-level resources 走独立轻量 manifest/validator, 不塞进 `data/manifest.json`。**
- D-102.3 明确 manifest 只管"数据产物↔引擎"边界, 不取代其他版本 (`docs/CONTRACTS.md:122-128`); user content 不是发布时 install bundle。
- User zone 需要 `~/.chisha/data/<zone>/manifest.json` 或等价 metadata, 至少含 `data_schema_version`, `normalized_name_version`, `engine_capabilities_required`, `generated_at`; 复用 `manifest.check_compatibility` 的核心校验但传 user zone root。
- User methodology 需要 validator 校验 keyset/name/version, 并新增 `min_engine_version` 或 `methodology_schema_version`; 当前 `version` 只是 spec 自身版本 (`profiles/methodologies/harvard_plate.yaml:13-15`), 不足以表达引擎兼容。
- `doctor` 应分别报告 `install_data_manifest_status` 和 `user_resource_status`; 不要让一个坏 user zone 影响未使用的默认 install zone。

## plan v2 Step 0-7 评审

| Step | Verdict | Required amendments |
|---|---|---|
| Step 0 wheel build spike | **保留, 作为 P0 gate** | 必须先做; wheel inspection 要断言 5 core files + console script + no accidental `tests/`, `scripts/`, `.claude` cache. `doctor passes` 只有在 entry point 已有时才成立; 若 Step 0 在 CLI wrapper 前, 改成 `python -m chisha.agent_cli doctor` 或拆成 Step 0a/0b。 |
| Step 1 install_root abstraction | **保留, 但 scope 要更精确** | 不搬目录; 新 `install_root.py` 返回 dev repo root / wheel resource root. 替换 hot-path root: `agent_cli._root`, `api._default_root`, prompt paths, `recall` data root, `methodology` install lookup. 同步 `state_root.project_root()` 语义, 避免 D-102 "root==包目录"漂移。 |
| Step 2 top-level CLI | **保留** | `chisha agent ...` wrapper 不得污染 stdout JSON; legacy deprecation warn 只能 stderr. `migrate-state` 不 import `scripts.*`, 只调 `chisha.state_migrate`; 对 wheel install 默认不从 package dir迁移旧 state。 |
| Step 3 SKILL.md text | **可并入 Step 2 或 Step 4** | 因用户决定继续 dynamic generation, 单一源应是 `agent_skill_init._claude_code_skill_md()`; 不再设计 `chisha/.claude/skills/...` 静态包资源。 |
| Step 4 install-skill | **保留, 小步** | `install-skill` 调 dynamic generator 写 `~/.claude/skills/chisha-meal/SKILL.md`; `--force` 覆盖; temp HOME 测试。 |
| Step 5 onboard | **需要拆成 5a/5b** | 5a profile+skill+doctor; 5b zone/methodology selection+dry start validation. `dry start` 应不写真实 meal_log/trace, 或使用临时 state_root; 否则 onboarding 有副作用。 |
| Step 6 packaging/release | **拆分 transport 子步** | Packaging gate 与 GitHub private transport 分开. Transport v2 只写 private SSH install docs/check; 不做 GitHub Packages/release asset installer。 |
| Step 7 full-chain verification | **保留, 必须真实离 repo** | temp HOME + no repo on PYTHONPATH + `uv tool install git+ssh://...` 或 local wheel模拟 + `chisha onboard --zone shenzhen-bay` + Claude Code skill smoke. baseline + pytest 仍要跑, 因触碰 high-risk root/recall/methodology。 |
| Missing: C resource validation | **新增 Step 5c 或 Step 1b** | Additive no-collision lookup tests: user zone only, install zone only, collision fail; user methodology only, install methodology only, collision fail; invalid methodology hard-fails with actionable error. |
| Missing: release integrity note | **新增 Step 6 gate** | Private git transport 可用 git commit/tag 兜底; wheel/release flow 必须输出 sha256. D-102 manifest `integrity=null` 仍是 caveat。 |

## 估时复审 (区间)

| Work item | Estimate |
|---|---:|
| Step 0 wheel force-include spike + wheel inspection | 0.4-0.8d |
| Step 1 install_root abstraction + path callsite migration + fixtures | 0.8-1.5d |
| Step 2 CLI wrapper + stderr-only legacy compatibility + tests | 0.4-0.8d |
| Step 3/4 dynamic skill text/install-skill | 0.3-0.6d |
| Step 5 onboard + dry validation without side effects | 0.7-1.2d |
| C zone lookup + user data manifest validation + collision tests | 0.6-1.0d |
| C methodology lookup + schema/template/validate command + collision tests | 0.8-1.4d |
| Step 6 private GitHub SSH transport docs/check + release hygiene | 0.2-0.5d |
| Step 7 full verification + pytest + baseline + temp HOME install | 0.5-0.9d |
| **Total** | **4.7-8.7d** |

- **结论: v2 已不是原 2-2.5d sprint; A 降低搬目录风险, 但 B/C 增加真实分发和用户资源架构, 合理区间是 5-9 人日。**
- 若砍 C 的 schema/template command, 可降到 4-6d, 但会违背"agent SDK 写 methodology spec"的未来约束。
- 若坚持只做深圳湾 + harvard_plate + private SSH, 不做 user-level zone/methodology, 可回到 3-5d, 但那不是本轮 C 约束的方案。

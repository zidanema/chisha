# T-DIST-01 · chisha-meal 对外分发包 — Plan v3

> Sprint 目标: 把 chisha 从 "git clone dev repo" 形态升级到 "一行 `uv tool install chisha-meal` 装上即用". 终态 transport: `uv tool install git+https://github.com/zidanema/chisha.git` (public).
> Mental model: lark-cli. 关键差异: chisha 强依赖本地数据 + profile, onboarding 是特有难点.
> v3 变化 (vs v2): Sprint A 大改 — fresh clone + 全 history scan + 历史敏感数据洗 (home/手机号) + branch protection / Actions logs / LICENSE / SECURITY.md 闸门齐全. 总估时 6.3-11.2d (以底部细表为准, codex Round 4 sign-off).
> 工作流痕迹: Round 1 review @ `plans/T-DIST-01.plan-review.md`; Round 2 @ `plans/T-DIST-01.plan-review-v2.md`; Round 3 BLOCK @ `plans/T-DIST-01.plan-review-v3.md`; Round 4 sign-off pending.

## 真实扫描结果 (Sprint A 实施基线)

跑了 codex Round 3 给的 4 套全历史扫描, 结果:

| 项 | 状态 | Sprint A 动作 |
|---|---|---|
| 高熵真 secret token (AKIA/ghp_/sk-ant-/...) | ✓ 干净 | 无 |
| API key 变量名引用 (ANTHROPIC_API_KEY 等) | ✓ 仅 .env.example + 代码 + 测试 fake `"sk-or"` | 无 |
| `apps/web/.env.production` 内容 | ✓ 仅 `VITE_USE_MOCK=0` | **保留 public** |
| `data/home/` (11 文件) | ⚠ 工区名暴露住址, 无 lat/lng | A.2 历史删 |
| 商家电话 `[REDACTED]` (data/) | ⚠ 商家公开电话, canonical_name 已洗 | A.2 history replace-text |
| `profile.yaml` (含 `name: 志丹`) | ⚠ PII (姓名 + 饮食偏好) | A.2 历史删 |
| 字节邮箱 (243 commits author + 部分 committer) | ⚠ | A.1 mailmap rewrite |

## 终态用户体验

```bash
uv tool install git+https://github.com/zidanema/chisha.git
chisha doctor
chisha onboard --zone shenzhen-bay
# 任意目录 Claude Code: > 今天中午吃啥
```

## Sprint 拆分

| Sprint | 内容 | 估时 |
|---|---|---|
| **A. Public-Ready Cleanup** | fresh clone 单次 filter-repo (mailmap + invert-paths + replace-text 一并) + 公开 hygiene + GitHub 闸门 | 1.5-2.5d |
| **B. T-DIST-01 工程主体** | hatch force-include + install_root + chisha CLI + onboard + user-level loader (中等 C) | 4.8-8.7d |
| **合计** | | **6.3-11.2d** |

---

# Sprint A · Public-Ready Cleanup

## A 目标

仓库改 public 前清掉 history 敏感数据 + 拿到 GitHub public 闸门齐全, 让 `transport=git+https://github.com/zidanema/chisha.git` 终态生效.

## A.0 Preflight (0.2-0.3d)

**目的**: 在动 history 前把所有不可逆操作的前置闸门全部 known-good, 出错可回退.

1. **本地仓完整备份**:
   ```bash
   tar -czf ~/chisha-backup-$(date +%Y%m%d-%H%M).tar.gz -C ~ chisha
   # 验证可解: tar -tzf ... | head
   ```
2. **author + committer 邮箱全集** (codex Round 3 P0-2: 不能只查 author):
   ```bash
   git log --all --format='%an <%ae>%n%cn <%ce>' | sort -u
   ```
   预期: `mazhidan <mzd5646241@gmail.com>`, `Jarvis <jarvis@openclaw.local>`, 可能含 committer 也是 `mzd5646241@gmail.com`. 若出现 mailmap 未覆盖的邮箱, 加入 mailmap.
3. **GitHub branch protection 状态**:
   ```bash
   gh api repos/zidanema/chisha/branches/main/protection 2>&1
   ```
   若启用了 protection, A.3 force-push 前要**临时 disable** (或加 "Allow force pushes"), 改完 visibility 后再恢复.
4. **GitHub Actions runs + artifacts 清单** (codex Round 3 P0-3: 改 public 后 workflow logs 也公开):
   ```bash
   gh run list --limit 100
   gh api repos/zidanema/chisha/actions/artifacts
   ```
   如有含 secret/内部路径的 run, A.2 末尾删之.
5. **当前 working tree 干净**:
   ```bash
   git status --short  # 必须空; 否则 commit 或 stash
   ```

## A.1 Fresh clone + 单次 filter-repo (0.8-1.2d)

**关键** (codex Round 3 P0-2): filter-repo **必须在 fresh clone 上跑**, 不在 working tree 上跑.

1. **Fresh clone**:
   ```bash
   cd ~ && rm -rf chisha-rewrite
   git clone --no-local ~/chisha chisha-rewrite
   cd ~/chisha-rewrite
   ```
2. **mailmap 文件** (改 author + committer 同时):
   ```bash
   cat > .mailmap <<'EOF'
   志丹 <mzd5646241@gmail.com> <mzd5646241@gmail.com>
   志丹 <mzd5646241@gmail.com> mazhidan <mzd5646241@gmail.com>
   EOF
   ```
   (注意: filter-repo 的 mailmap 第一行格式 `Name <correct-email> <wrong-email>`, 第二行 `Name <correct-email> wrong-name <wrong-email>` — 两种都覆盖)
3. **replace-text 文件** (商家手机号 → [REDACTED]):
   ```bash
   cat > replacements.txt <<'EOF'
   [REDACTED]==>[REDACTED]
   EOF
   ```
4. **单次 filter-repo 同时做 3 件事**:
   ```bash
   pip install --user git-filter-repo  # 或 brew install git-filter-repo
   git filter-repo \
     --mailmap .mailmap \
     --path data/home/ --invert-paths \
     --path profile.yaml --invert-paths \
     --replace-text replacements.txt
   ```
   (`--invert-paths` 配合 `--path` = "保留所有路径**除了**这些"; 不带 `--invert-paths` 是反过来)
5. **验证 rewrite 结果**:
   ```bash
   # 字节邮箱 0 出现:
   git log --all --format='%ae %ce' | grep bytedance && echo "FAIL" || echo "OK"
   # home 0 出现:
   git log --all --name-only --pretty=format: | sort -u | grep home && echo "FAIL" || echo "OK"
   # 手机号 0 出现:
   git log --all -p | grep '[REDACTED]' && echo "FAIL" || echo "OK"
   # commit 总数应该一样 (262) 或非常接近 (空 commit 会被删):
   git rev-list --all --count
   ```
6. **回连原 remote 并强推**:
   ```bash
   git remote add origin git@github.com:zidanema/chisha.git
   git fetch origin main  # 看旧 head 是啥
   git push --force-with-lease=main:<旧head> origin main
   ```
   (`--force-with-lease=<refname>:<expect>` 比裸 `--force-with-lease` 更安全, 显式比对预期 head)
7. **回切到主仓**:
   ```bash
   cd ~/chisha && git fetch origin && git reset --hard origin/main
   git config user.email mzd5646241@gmail.com  # 后续 commit 用个人邮箱
   ```

## A.2 公开 hygiene + 文件 cleanup (0.3-0.6d)

1. **`.gitignore` 增强**:
   ```
   # User state (D-102, 但 repo 内不该出现)
   profile.yaml
   
   # Env / secrets
   .env
   .env.local
   .env.*.local
   .env.bak
   !.env.example
   
   # Keys / credentials
   *.pem
   *.key
   id_rsa
   id_ed25519
   credentials
   secrets
   *.token
   ```
2. **`LICENSE` (MIT, 用户已选)**:
   ```bash
   gh repo edit --add-license MIT  # 或手工拷标准 MIT 文本
   ```
   Author 字段: `志丹 <mzd5646241@gmail.com>`.
3. **`SECURITY.md` (minimal)**: 一段 "this is a personal hobby project; security reports → email"; 不强承诺 SLA.
4. **GitHub Actions runs/artifacts 清理** (A.0 第 4 步标记的):
   ```bash
   gh run delete <run-id>  # 逐个
   gh api -X DELETE repos/zidanema/chisha/actions/artifacts/<id>
   ```
5. **docs 链接审查**: README / CLAUDE.md / docs/ 内若有引用 `bytedance` / `home` / `profile.yaml in repo root` 一并删 (grep 一遍):
   ```bash
   rg 'bytedance|home|repo 根.*profile' docs/ README.md CLAUDE.md
   ```

## A.3 改 public + 验证 (0.2-0.4d)

1. **Pre-flip gate** (codex Round 3 P0-3 必走):
   - [ ] `git status --short` 空
   - [ ] `git ls-files | rg '^profile.yaml$|home|\.env(?!\.example)'` 空
   - [ ] `git log --all --format='%ae %ce' | rg bytedance` 空
   - [ ] LICENSE 存在
   - [ ] SECURITY.md 存在
   - [ ] Branch protection 已临时 disable (或允许 force-push)
   - [ ] Actions runs 清理完成
2. **Flip visibility**:
   ```bash
   gh repo edit zidanema/chisha --visibility public --accept-visibility-change-consequences
   gh repo view zidanema/chisha --json visibility  # 验证 PUBLIC
   ```
3. **Branch protection 恢复** (如果 A.0 disable 过):
   ```bash
   # 用 gh api PUT repos/zidanema/chisha/branches/main/protection 恢复原配置
   ```
4. **Transport smoke**:
   ```bash
   cd /tmp && uv tool install git+https://github.com/zidanema/chisha.git
   # 此时 chisha 命令还没注册 (Sprint B 未做), 但 git+https clone+install 应该成功
   uv tool uninstall chisha  # cleanup
   ```

## A 验收

- [ ] `git log --all --format='%ae %ce'` 无 bytedance 邮箱
- [ ] `git log --all --name-only --pretty=format:` 不含 home 或 profile.yaml
- [ ] `git log --all -p` 无 `[REDACTED]`
- [ ] `gh repo view --json visibility` = PUBLIC
- [ ] LICENSE + SECURITY.md tracked
- [ ] 干净环境 `uv tool install git+https://github.com/zidanema/chisha.git` 不报 auth 错
- [ ] Branch protection (若原有) 已恢复

---

# Sprint B · T-DIST-01 工程主体

## B Affected files (单一权威源)

### high-risk 白名单 (CLAUDE.md § 推荐链路改动红线)

- `chisha/agent_cli.py` — `_root()` 改用 `install_root.install_root()`; deprecation warn 走 **stderr** (不污染 stdout JSON)
- `chisha/state_root.py` — 文案扩成 "user-owned writable root"; 子目录区分 `logs/` / `profile.yaml` / `data/` / `methodologies/`
- `chisha/manifest.py` — `manifest_path(install_root)` 接口不变; 新增 `user_resource_manifest_check()` (C-d 独立轻量)
- `chisha/recall.py` — `load_zone_data(zone)` 改 user→install lookup, 撞名 fail-loud `RESOURCE_NAME_COLLISION`
- `chisha/api.py` — `_default_root()` 改用 `install_root.install_root()`

### 不进白名单但必改

- `pyproject.toml` — name `chisha-meal`, `[project.scripts]`, `[tool.hatch.build.targets.wheel.force-include]`
- `chisha/agent_skill_init.py` — SKILL.md 模板 `uv run python -m chisha.agent_cli` → `chisha agent`
- 新建 `chisha/cli.py` — 顶层 CLI
- 新建 `chisha/install_root.py` — 包资源根单一源
- `chisha/methodology.py` — `load_methodology` (注意: 不是我 v2 写错的 `_load_yaml`, codex Round 3 已纠正) 加 user-level 优先级, 撞名 fail-loud

## B.0 Wheel build spike (P0 gate, 0.4-0.8d)

1. `pyproject.toml` 加 force-include:
   ```toml
   [tool.hatch.build.targets.wheel.force-include]
   "prompts" = "chisha/prompts"
   "profiles" = "chisha/profiles"
   "data" = "chisha/data"
   
   [tool.hatch.build.targets.wheel]
   exclude = ["apps/", "plans/", "docs/", "tmp/", "logs/", "eval/", "tests/", "scripts/"]
   ```
2. `uv build` → `dist/chisha_meal-*.whl`
3. **Wheel content gate**: `unzip -l dist/*.whl` 断言:
   - 含: `chisha/prompts/rerank_system.md`, `chisha/prompts/parse_refine_intent_v2.md`, `chisha/profiles/methodologies/harvard_plate.yaml`, `chisha/data/manifest.json`, `chisha/data/shenzhen-bay/restaurants.json`
   - 不含: `apps/`, `plans/`, `docs/`, `tmp/`, `logs/`, `eval/`, `tests/`, `scripts/`, `.claude/`
4. **Temp HOME install gate**:
   ```bash
   HOME=/tmp/test-home-$RANDOM
   mkdir -p $HOME && cd /tmp
   uv tool install ~/chisha/dist/*.whl
   python -m chisha.agent_cli doctor  # 此时 chisha 命令未注册 (B.1 后才有), 用 python -m 跑
   ```

## B.1 install_root 抽象 (0.8-1.5d)

1. 新建 `chisha/install_root.py`:
   ```python
   from pathlib import Path
   def install_root() -> Path:
       """包资源根 (含 prompts/, profiles/, data/).
       dev 时 Path(__file__).parent = chisha/, force-include 源同级目录;
       wheel 时 site-packages/chisha/, force-include 把外置目录复制进来.
       两种情形都能 install_root() / 'prompts' 找到资源.
       """
       return Path(__file__).resolve().parent
   ```
2. **测试 fixture**: `tests/conftest.py` 加 `_isolate_install_root` (autouse 范围窄, 用 monkeypatch).
3. **Callsite migration** (按 codex Round 1 grep 出的清单):
   - `chisha/agent_cli.py:_root` → install_root
   - `chisha/api.py:_default_root` → install_root
   - `chisha/recall.py:1162-1169` (__main__) → install_root
   - `chisha/rerank.py:32-33 SYSTEM_PROMPT_PATH` → `install_root() / "prompts" / ...`
   - `chisha/refine_intent_v2.py:38-39 PROMPT_PATH_V2` → 同上
   - `chisha/feedback.py:17-18 PROMPT_PATH` → 同上
   - `chisha/l1_extractor.py:34,201` prompt → 同上
   - `chisha/methodology.py:29-30,122-123` install lookup → 同上 (B.5b 再加 user-level)
   - `chisha/score.py:1376` default root → 调
   - `chisha/web_api.py:38 ROOT` → 调
   - `chisha/debug_server.py:32 ROOT` → 调
4. **`state_root` 语义同步**: `chisha/state_root.py:10-17` 注释 + docstring 改 "user-owned writable root"; `project_root()` 保留但**不再当 install_root 等价物**.
5. **Gate**: baseline_l2_snapshot 0 diff + pytest 不减.

## B.2 chisha 顶层 CLI (0.4-0.8d)

1. `chisha/cli.py`:
   - `chisha doctor` → `agent_cli.cmd_doctor`
   - `chisha agent <verb>` → 透传 `agent_cli.main`
   - `chisha install-skill [--force]` → B.4
   - `chisha onboard [--zone] [--methodology] [--force]` → B.5
   - `chisha migrate-state [--dry-run]` → wrap `chisha.state_migrate` (**不**经 `scripts.migrate_state`)
   - `chisha methodology {schema|template|validate}` → 报 `NOT_IMPLEMENTED` JSON, 含 `T-DIST-02 待办`
2. `pyproject.toml`: `[project.scripts] chisha = "chisha.cli:main"`
3. **Legacy 兼容**: `python -m chisha.agent_cli` 仍可用, **stderr** 一行 tip (绝不污染 stdout JSON).
4. **测试**: `tests/test_cli_wrapper.py` subprocess 跑, 断言 (a) `chisha agent doctor` stdout 等价于 legacy; (b) legacy stderr 含 tip stdout 不含; (c) `chisha methodology schema` 报 NOT_IMPLEMENTED 非零退出.

## B.3 + B.4 SKILL.md 同步 + install-skill (0.3-0.6d)

1. `chisha/agent_skill_init.py:_claude_code_skill_md()`:
   - 所有 `uv run python -m chisha.agent_cli` → `chisha agent`
   - doctor: `chisha doctor`
   - 加 "How to install" 段: `uv tool install git+https://github.com/zidanema/chisha.git && chisha onboard --zone shenzhen-bay`
2. `chisha/cli.py:cmd_install_skill`:
   - 调 `_claude_code_skill_md()` 拿文本, 写 `~/.claude/skills/chisha-meal/SKILL.md`
   - `--force` 才覆盖, 否则 `EXISTS` JSON 错
   - 输出 `{ok, path, next}`
3. **单一源**: SKILL.md 只动态生成, **不**ship 静态文件 (codex Round 2 P2)
4. **测试**: 临时 HOME 跑, 断言 SKILL.md 含 `chisha agent` (不是旧 `uv run python ...`)

## B.5 onboard (1.8-2.9d, 拆 a/b/c)

### B.5a 基础 (0.4-0.6d)

1. 写 default `profile.yaml` template 到 `~/.chisha/profile.yaml` (除非已存在; `--force` 覆盖)
2. 默认 zone `shenzhen-bay` (`--zone` 可指定), 默认 methodology `harvard_plate` (`--methodology`)
3. 调 `cmd_install_skill`
4. 调 `cmd_doctor` 输出绿/红

### B.5b user-level loader (C 中等核心, 1.5-2.5d, codex Round 3 上调)

1. **`chisha/recall.py:load_zone_data(zone)`**:
   - 先查 `state_root() / "data" / zone / restaurants.json`
   - 再查 `install_root() / "data" / zone / restaurants.json`
   - 同时存在 → fail-loud `RESOURCE_NAME_COLLISION`
   - 都不存在 → fail-loud `ZONE_NOT_FOUND`, 列已知 zones (install + user)
2. **`chisha/methodology.py:load_methodology(name)`** 同策略 (注意函数名: `load_methodology`, 不是 v2 写错的 `_load_yaml`).
3. **User zone manifest** (C-d 独立轻量): `state_root() / "data" / <zone> / manifest.json` 需 `data_schema_version`, `normalized_name_version`, `engine_capabilities_required`, `generated_at`. 复用 `manifest.check_compatibility` 校验逻辑, 不混入 install `data/manifest.json`.
4. **Doctor 分开报告**: 新增字段 `install_data_manifest_status` (现 `data_manifest_status` 改名) + `user_resource_status` (per user zone/methodology).
5. **Loader API 留位** (中等 scope 边界):
   - `chisha/methodology.py` 暴露 `get_schema_keyset()` / `get_template()` / `validate_spec(path)` 三个公开函数
   - 内部可调 (B.5b lookup 用), CLI 命令报 NOT_IMPLEMENTED 不 wrap
6. **撞名测试** (B.7 内, 但 fixture 在这写):
   - user zone only → OK
   - install zone only → OK
   - 同名撞 → `RESOURCE_NAME_COLLISION`
   - methodology 同上

### B.5c dry start 校验 (0.3-0.5d, codex Round 3 上调)

1. onboard 末尾调 `agent_cli.cmd_start(meal=lunch, context=None)` 在 **ephemeral scope**:
   - round state 写临时目录, **不**进 `~/.chisha/logs/agent_rounds/`
   - 跑完即删 (避免副作用)
   - **scope=ephemeral 当前 agent_cli 没有, 要新加** (codex Round 3 提到)
2. 期望 `status=resolved` (无 context 直接 rerank spec)
3. 失败 → onboard 报红
4. 成功 → 输出 "Onboarding 完成, Claude Code 说 '今天中午吃啥' 即可"

## B.6 pyproject + 发布 (0.2-0.5d)

1. `pyproject.toml` 完整化 (B.0 已配 force-include + exclude)
2. 本地 build + B.0 content gate 再跑一遍
3. **Release sha256** (codex Round 2 gate): build 完输出 `dist/*.whl.sha256`, push GitHub release notes
4. **Transport docs**: README 加 "如何装" 段, 命令 `uv tool install git+https://github.com/zidanema/chisha.git`
5. **不做**: GitHub Packages / release wheel installer / PyPI

## B.7 全链路验证 (0.5-0.9d)

1. **完整离 repo 验证**:
   - 临时 HOME (`/tmp/onboard-test-$RANDOM`)
   - 临时 `~/.claude` (空)
   - 不在 chisha repo 目录 (`cd /tmp`)
   - `uv tool install git+https://github.com/zidanema/chisha.git` (Sprint A 完成后)
   - `chisha onboard --zone shenzhen-bay`
   - 临时 HOME 开 Claude Code, 触发 chisha-meal skill, 走完一轮 start→resolve→apply→choose
2. **baseline_l2_snapshot 严格回归** (改前 vs 改后 0 diff)
3. **pytest 全过** (≥ baseline)
4. **B.5b 撞名测试** (4 case)
5. **Wheel content gate** (B.0 流程再跑)
6. **`chisha methodology schema/template/validate` 都报 NOT_IMPLEMENTED 非零退出**
7. 写 `plans/T-DIST-01.diff-review.md` commit 前 codex review

## B 验收

- [ ] Sprint A 完成 (repo public, https transport 可装)
- [ ] `uv tool install git+https://github.com/zidanema/chisha.git` 干净环境装上
- [ ] `chisha doctor` 全 green
- [ ] `chisha onboard --zone shenzhen-bay` 写 profile + 装 skill + dry start 走通
- [ ] `~/.claude/skills/chisha-meal/SKILL.md` 内含 `chisha agent` (新 CLI)
- [ ] 临时 HOME + 任意目录 Claude Code, "今天中午吃啥" 触发, 走完一轮
- [ ] User-level lookup 撞名 fail-loud
- [ ] Doctor 分报 `install_data_manifest_status` + `user_resource_status`
- [ ] baseline 0 diff, pytest 不减, wheel content gate, NOT_IMPLEMENTED 测试

## C 中等 scope 边界

| 项 | T-DIST-01 | T-DIST-02 |
|---|---|---|
| User-level zone 加载 + manifest + fail-loud | ✓ | |
| User-level methodology 加载 + fail-loud | ✓ | |
| Doctor `user_resource_status` | ✓ | |
| Loader API `get_schema_keyset/get_template/validate_spec` | ✓ (留位接口) | |
| `chisha methodology schema --json` CLI | ✗ (NOT_IMPLEMENTED) | ✓ |
| `chisha methodology template --name <x>` CLI | ✗ | ✓ |
| `chisha methodology validate <file>` CLI | ✗ | ✓ |
| Methodology JSON Schema artifact | ✗ | ✓ |
| Zone bundle marketplace | ✗ | 远期 |
| Codex / 其他 agent adapter | ✗ | D-074 Phase 1 |

## 估时

| 阶段 | 估时 |
|---|---:|
| A.0 preflight | 0.2-0.3d |
| A.1 fresh clone + filter-repo + push | 0.8-1.2d |
| A.2 hygiene (gitignore/LICENSE/SECURITY/Actions cleanup) | 0.3-0.6d |
| A.3 改 public + 闸门 + 验证 | 0.2-0.4d |
| **Sprint A 小计** | **1.5-2.5d** |
| B.0 wheel build spike | 0.4-0.8d |
| B.1 install_root 抽象 + callsite migration + state_root 同步 | 0.8-1.5d |
| B.2 chisha CLI wrapper + stderr legacy compat | 0.4-0.8d |
| B.3+B.4 SKILL.md + install-skill | 0.3-0.6d |
| B.5a 基础 onboard | 0.4-0.6d |
| B.5b user-level loader (C 中等) | 1.5-2.5d |
| B.5c dry start + ephemeral scope | 0.3-0.5d |
| B.6 pyproject + sha256 | 0.2-0.5d |
| B.7 全链路验证 | 0.5-0.9d |
| **Sprint B 小计** | **4.8-8.7d** |
| **总计** | **6.3-11.2d** |

> 注: 比 codex Round 3 估的 5.8-10.5d 上限略高, 因为 B.5b/B.5c 按 codex 反馈做了上调.

## 后续 (不在本 sprint scope)

- T-DIST-02: methodology schema/template/validate 三 CLI + 正式 JSON Schema (有同事真要写自定义 spec 时)
- Codex adapter (D-074 Phase 1)
- Zone bundle 分离分发 (D-102 marketplace 留位)
- 产物完整性 (D-102 integrity null → 签名)

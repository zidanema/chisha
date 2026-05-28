# T-DIST-01 Plan Review v3 (Round 3 Sign-off)

Date: 2026-05-28

## 1. Sprint A completeness

### Findings

- `git-filter-repo --mailmap <file>` is the correct flag.
  - Plan anchor: A.1 step 3 uses `git filter-repo --mailmap <file>` (`plans/T-DIST-01.plan.md:54`).
  - Verified usage: `git-filter-repo` docs list `--mailmap <filename>` and `--use-mailmap` as shorthand for `.mailmap`; example usage is `git filter-repo --mailmap my-mailmap`.
  - Source: https://manpages.debian.org/testing/git-filter-repo/git-filter-repo.1.en.html
  - There is no need to change this to `--mailmap-file`.

- The mailmap content is probably incomplete for full author/committer rewrite validation.
  - Plan anchor: it lists only author emails (`plans/T-DIST-01.plan.md:41-43`) and says "列出所有 author/committer 邮箱 + 名字组合" (`plans/T-DIST-01.plan.md:50`).
  - Required check before rewrite:
    - `git log --all --format='%an <%ae>%n%cn <%ce>' | sort -u`
    - verify both author and committer identities are mapped or intentionally retained.
  - The post-check at `plans/T-DIST-01.plan.md:55` only checks `%ae`; it must also check `%ce`.

- Sprint A is missing history-wide sensitive-data scans.
  - Plan anchor: Sprint A says it cleans "两类风险" (`plans/T-DIST-01.plan.md:35-37`): bytedance email and root `profile.yaml`.
  - That is not enough before public conversion.
  - Current repo has tracked data files and env-like files:
    - tracked `profile.yaml`
    - tracked `data/**`
    - tracked `apps/web/.env.production`
    - tracked `.env.example`
    - untracked local `.env` / `.env.bak` exist in working tree and must never be added.
  - Plan A.2 only removes root `profile.yaml` (`plans/T-DIST-01.plan.md:64-72`), not historical copies or other sensitive paths.

- Concrete pre-public scan patterns that must be added:
  - File/path scan:
    - `git ls-files | rg '(^|/)(\\.env|\\.env\\..*|.*\\.pem|.*\\.key|id_rsa|id_ed25519|credentials|secrets?|token|password)'`
    - `git log --all --name-only --pretty=format: | sort -u | rg '(^|/)(\\.env|\\.env\\..*|profile\\.yaml|logs/|data/|.*\\.pem|.*\\.key|credentials|secrets?)'`
  - Secret scan:
    - `git grep -I -n -E '(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{20,}|ANTHROPIC_API_KEY|OPENAI_API_KEY|OPENROUTER_API_KEY|LARK|FEISHU|TOKEN|SECRET|PASSWORD|PRIVATE KEY|BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY)' $(git rev-list --all)`
  - PII/internal scan:
    - `git grep -I -n -E '(bytedance\\.com|飞书|lark|feishu|志丹|手机号|电话|身份证|address|地址|home)' $(git rev-list --all)`
  - Data/log scan:
    - `git grep -I -n -E '(user_id|open_id|union_id|email|phone|lat|lng|address|home|company|bytedance)' $(git rev-list --all) -- data logs`

- `logs/` are not tracked now, but the plan must scan history for them.
  - Plan B.0/B.6 excludes `logs/` from wheel (`plans/T-DIST-01.plan.md:132,243`), but Sprint A does not scan git history for committed logs.
  - Public conversion exposes all reachable history, not only wheel content.

- `data/` is not automatically safe.
  - Plan deliberately ships `data/shenzhen-bay` later (`plans/T-DIST-01.plan.md:126-131`).
  - Before public repo conversion, `data/**` must be reviewed for personal addresses, home zones, internal venue metadata, review samples, Excel files, and provenance fields.
  - The tracked `data/home/**` path is a specific red flag because the plan’s terminal shipped default is only `shenzhen-bay`.

- `.env` handling is incomplete.
  - Plan A.2 adds only `profile.yaml` to `.gitignore` (`plans/T-DIST-01.plan.md:70-71`).
  - It should add `.env`, `.env.*`, `!.env.example`, credential/key patterns, and local backup patterns.
  - `apps/web/.env.production` is tracked; it must be reviewed before public conversion even if it contains only non-secret frontend config.

- Public-repo prerequisites are not hard GitHub requirements, but the plan is missing public-readiness hygiene.
  - GitHub says public/open-source repos should consider license/community profile/security policy:
    - License: without a license, default copyright applies; source is visible but not truly open-source reusable. Source: https://docs.github.com/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository/
    - Community profile checks recommended files such as README, LICENSE, CODE_OF_CONDUCT, CONTRIBUTING, SECURITY. Source: https://docs.github.com/articles/viewing-your-community-profile
    - Security policy is a good practice via `SECURITY.md`. Source: https://docs.github.com/en/enterprise-cloud@latest/code-security/getting-started/quickstart-for-securing-your-repository
  - `LICENSE` and `SECURITY.md` are not currently tracked.
  - README badges are optional, not a prerequisite.

### Verdict

- **BLOCK / P0**
- Sprint A cannot start as written because public conversion is irreversible enough that a history-wide sensitive-data scan must be in the plan before visibility changes.
- Fix required:
  - add author+committer rewrite validation,
  - add history-wide path/secret/PII scans,
  - review tracked `data/**` and `apps/web/.env.production`,
  - update `.gitignore` for env/key/secret files,
  - decide whether this public repo is open source and add `LICENSE` accordingly,
  - add at least minimal `SECURITY.md` or explicitly decide not to accept vuln reports.

## 2. Sprint A → public → Sprint B ordering

### Findings

- The ordering "cleanup before public before Sprint B" is correct.
  - Plan anchor: Sprint A output is "repo 改 public, 终态 transport 可用" (`plans/T-DIST-01.plan.md:27`), and Sprint B depends on public HTTPS install (`plans/T-DIST-01.plan.md:270-271`).
  - Making public after Sprint B would keep transport blocked during the most important full-chain install test.

- `git-filter-repo` should be run from a fresh clone, not the dirty working repo.
  - Plan anchor: A.1 says backup current repo and run filter-repo (`plans/T-DIST-01.plan.md:49-57`).
  - `git-filter-repo` has a fresh-clone safety check because history rewriting is irreversible; docs say it aborts if not run from a fresh clone unless forced.
  - Source: https://manpages.debian.org/testing/git-filter-repo/git-filter-repo.1.en.html
  - Current working tree has untracked plan files; that is exactly the wrong place to rewrite history.

- Force-push while local `main` is checked out is not itself a GitHub problem.
  - GitHub remote is not a checked-out non-bare repo.
  - The real pitfall is branch protection/rulesets.

- Branch protection/rulesets can block `git push --force-with-lease origin main`.
  - Plan anchor: A.1 step 6 assumes force-push is safe (`plans/T-DIST-01.plan.md:57`).
  - GitHub protected branches block force pushes by default unless "Allow force pushes" is enabled for the branch/rule.
  - Source: https://docs.github.com/articles/types-of-required-status-checks
  - Add preflight:
    - check branch protection/rulesets for `main`,
    - temporarily disable protection or allow force-push,
    - re-enable protection after rewrite.

- `--force-with-lease` may fail after rewrite if remote refs were detached/re-added incorrectly.
  - Plan already notes filter-repo detaches remotes (`plans/T-DIST-01.plan.md:57`).
  - Add explicit preflight:
    - `git remote -v`,
    - `git fetch origin main`,
    - verify `origin/main` is the expected old head before force-push,
    - then push rewritten `main`.

- GitHub Actions history/logs become public after repo visibility changes.
  - Plan does not mention workflow runs/artifacts.
  - GitHub visibility docs state Actions history and logs will be visible to everyone when a repo becomes public.
  - Source: https://docs.github.com/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility
  - Add pre-public check:
    - list workflow runs/artifacts,
    - delete any run/artifact containing private paths, env names, internal hostnames, or logs.

- State must be clean before making public.
  - Plan A.3 changes visibility immediately after A.1/A.2 (`plans/T-DIST-01.plan.md:74-78`).
  - Add gate before A.3:
    - `git status --short` clean,
    - no untracked sensitive files in repo root,
    - `git ls-files profile.yaml` empty,
    - author+committer emails clean,
    - scan commands from Section 1 clean,
    - README no private install instructions,
    - GitHub branch/ruleset state known.

### Verdict

- **BLOCK / P0**
- Sprint A → public → Sprint B ordering is right, but A.3 must be blocked on clean-state, branch-protection, Actions-log, and sensitive-history gates.
- Fix required:
  - rewrite in a fresh clone,
  - confirm/adjust branch protection before force-push,
  - inspect/delete sensitive Actions runs/artifacts,
  - require clean git status and clean scans before visibility flip.

## 3. Middle-C scope boundary (loader API留位 + CLI NOT_IMPLEMENTED)

### Findings

- The chosen middle-ground is the right cut.
  - Plan anchor: B.5b implements user-level zone/methodology lookup, user zone manifest, doctor reporting, and loader API留位 (`plans/T-DIST-01.plan.md:208-224`).
  - Plan anchor: C boundary explicitly does loader API now, methodology CLI commands and formal JSON Schema later (`plans/T-DIST-01.plan.md:283-297`).

- Alternative (a), no loader stub at all, is too thin.
  - B.5b and B.7 need lookup/collision tests (`plans/T-DIST-01.plan.md:212-219,260-264`).
  - Without loader API留位, future CLI commands would either duplicate private validation logic or rework `methodology.py` again.
  - Near-zero-cost public functions around existing keyset/template/validation logic are reasonable because B.5b already touches `methodology.py`.

- Alternative (b), full CLI commands now, is too much for Sprint B.
  - Plan estimates B.5b C lookup at 1.1-1.9d (`plans/T-DIST-01.plan.md:312`).
  - Round 2 estimated full schema/template/validate CLI as an extra 0.8-1.4d; plan explicitly defers that (`plans/T-DIST-01.plan.md:291-294,331`).
  - There is no current acceptance criterion requiring colleagues to author methodology specs in Sprint B.
  - Full CLI commands would expand docs/tests and likely require a formal JSON Schema artifact, which the plan puts in T-DIST-02.

- The NOT_IMPLEMENTED CLI stubs are acceptable only if they do not appear as advertised working commands.
  - Plan anchor: `chisha methodology schema/template/validate` report `NOT_IMPLEMENTED` JSON error with `T-DIST-02` (`plans/T-DIST-01.plan.md:223-224`).
  - Do not add them to README as usable commands until T-DIST-02.
  - Test that they return stable JSON and nonzero exit code.

- One naming issue: the plan says `methodology.py:_load_yaml(name)` (`plans/T-DIST-01.plan.md:217`), but current code has `load_methodology`, `_methodology_path`, and `_load_methodology_cached`, not `_load_yaml`.
  - This is not a blocker to the scope decision.
  - It should be corrected during implementation to avoid hunting a non-existent function.

### Verdict

- **OK / P2**
- Concrete recommendation:
  - keep loader API `get_schema_keyset/get_template/validate_spec`,
  - keep CLI commands as `NOT_IMPLEMENTED` JSON stubs,
  - do not build full schema/template/validate CLI in T-DIST-01,
  - add one test for each NOT_IMPLEMENTED command.

## 4. Estimate sanity

### Findings

- The authoritative estimate is the lower table, not the top sprint table.
  - Top table says total 3.6-6.6d (`plans/T-DIST-01.plan.md:23-29`).
  - Estimate table says Sprint A 0.65-1.15d, Sprint B 4.4-8d, total 5.05-9.15d (`plans/T-DIST-01.plan.md:299-317`).
  - Plan note explicitly says 5-9d is more accurate than 3.6-6.6d (`plans/T-DIST-01.plan.md:319`).
  - The top table must be corrected or readers will use the wrong number.

- 5-9 person-days is reasonable versus Round 2's 4.7-8.7d.
  - Plan adds Sprint A cleanup 0.65-1.15d (`plans/T-DIST-01.plan.md:303-306`).
  - Plan also keeps middle-C loader scope in Sprint B (`plans/T-DIST-01.plan.md:311-313`).
  - Total 5.05-9.15d is consistent with Round 2 plus cleanup, assuming Sprint A scan gates are added.

- Sprint A.1 is under-estimated if it includes proper public-readiness cleanup.
  - Current A.1 is 0.5-1d (`plans/T-DIST-01.plan.md:39,303`).
  - With fresh clone, author+committer rewrite, history-sensitive scans, possible `profile.yaml` history removal, possible `data/**` or `.env.production` remediation, and force-push protection handling, realistic range is 0.8-1.8d.
  - If scans find real secrets, estimate becomes unbounded until rotation/removal is complete.

- Sprint A.2 is under-estimated if `.gitignore` and docs cleanup include env/key patterns and public README/license/security updates.
  - Current A.2 is 0.1d (`plans/T-DIST-01.plan.md:64,304`).
  - If only `git rm profile.yaml` + `.gitignore profile.yaml`, 0.1d is fine.
  - With required public hygiene, make it 0.3-0.6d.

- Sprint A.3 is under-estimated if it includes Actions/artifacts and branch protection preflight.
  - Current A.3 is 0.05d (`plans/T-DIST-01.plan.md:74,305`).
  - Visibility flip itself is minutes.
  - The gate around it is not minutes; estimate 0.2-0.4d.

- B.5b is probably slightly under-estimated.
  - Current B.5b is 1.1-1.9d (`plans/T-DIST-01.plan.md:312`).
  - It changes `recall.py`, `methodology.py`, `manifest.py`, `doctor`, and tests collision + manifests (`plans/T-DIST-01.plan.md:212-224,260-264`).
  - Realistic range: 1.5-2.5d.

- B.5c dry start estimate is tight but acceptable.
  - Current B.5c is 0.3-0.4d (`plans/T-DIST-01.plan.md:313`).
  - The only risk is inventing `scope="ephemeral"` through agent CLI state paths (`plans/T-DIST-01.plan.md:230-232`).
  - If no current scope abstraction supports this, it may become 0.5-0.8d.

- B.6 is reasonable.
  - Current B.6 is 0.2-0.5d (`plans/T-DIST-01.plan.md:314`).
  - It is mostly pyproject, content gate, sha256, README install docs, and explicitly not GitHub Packages/release installer (`plans/T-DIST-01.plan.md:236-247`).

- B.7 is reasonable but only if Claude Code manual smoke is shallow.
  - Current B.7 is 0.5-0.9d (`plans/T-DIST-01.plan.md:315`).
  - Full clean HOME + public HTTPS install + onboard + one agent loop + pytest + baseline is dense but plausible if no failures.

### Verdict

- **CONCERN / P1**
- 5-9d is the right headline range, but Sprint A is under-scoped because public-readiness gates are missing.
- Correct the top summary table to 5.05-9.15d or updated range after adding Sprint A gates.
- Expect actual total to move closer to **5.8-10.5d** if the added public-readiness scans are clean.

## Overall Verdict

Block, 必须先 fix 以下问题: [add history-wide sensitive-data scans; run git-filter-repo from a fresh clone; validate author and committer emails; review tracked `data/**` and env-like files before public; add branch protection/ruleset and GitHub Actions log/artifact preflight before force-push/public flip; correct the top estimate table to match the 5-9d estimate]

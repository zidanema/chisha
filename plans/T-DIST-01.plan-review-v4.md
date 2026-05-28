# T-DIST-01 Plan v3 — Final Review (Round 4)

## P0 Checklist

| # | P0 Item | Status | Evidence |
|---|---------|--------|----------|
| P0-1 | Sprint A must start with a preflight gate: backup + author/committer audit + branch protection status + Actions runs list + git status clean check | RESOLVED | Plan v3 has `A.0 Preflight` with backup (`tar -czf ...`), author+committer audit (`git log --all --format='%an <%ae>%n%cn <%ce>'`), branch protection check (`gh api .../protection`), Actions runs/artifacts list, and `git status --short` clean check. |
| P0-2 | `filter-repo` invocation must be a fresh clone, not in-place on working tree | RESOLVED | Plan v3 explicitly says `filter-repo 必须在 fresh clone 上跑` and uses `git clone --no-local ~/chisha chisha-rewrite` before running `git filter-repo`. |
| P0-3 | Mailmap must cover both name+email wrong and email-only wrong formats | RESOLVED | Plan v3 `.mailmap` contains both `志丹 <mzd5646241@gmail.com> <mzd5646241@gmail.com>` and `志丹 <mzd5646241@gmail.com> mazhidan <mzd5646241@gmail.com>`, with a note that both formats are covered. |
| P0-4 | Estimated time totals at top of plan must match bottom per-sprint breakdown | PARTIAL | Top Sprint table says A `1.5-2.5d`, B `4.4-8d`, total `5.9-10.5d`; bottom table says A `1.5-2.5d`, B `4.8-8.7d`, total `6.3-11.2d`. They still do not match. |
| P0-5 | `--force-with-lease` syntax must be safe, not bare `--force` | RESOLVED | Plan v3 uses `git push --force-with-lease=main:<旧head> origin main` and explicitly says this is safer than bare `--force-with-lease` because it compares the expected head. |
| P0-6 | B.5b function name must be corrected to `load_methodology`, not `_load_yaml` | RESOLVED | Plan v3 affected-files section says `chisha/methodology.py — load_methodology ...`, and B.5b says `chisha/methodology.py:load_methodology(name)` with a note that `_load_yaml` was the v2 mistake. |
| P0-7 | B.5c ephemeral scope must be explicitly described | RESOLVED | Plan v3 B.5c says onboard calls `agent_cli.cmd_start` in ephemeral scope, writes round state to a temp dir, avoids `~/.chisha/logs/agent_rounds/`, deletes it afterward, and notes `scope=ephemeral 当前 agent_cli 没有, 要新加`. |

## Filter-repo Technical Verification

### a. mailmap covers author + committer?

- **Yes.**
- `git-filter-repo --mailmap` applies mailmap rewriting to commit identities, covering both author and committer identities by default.
- Plan v3 is technically correct to use one `--mailmap .mailmap` for both author and committer rewrite.
- Plan v3 also correctly validates both with `git log --all --format='%ae %ce'`.

### b. `--invert-paths` + `--replace-text` single invocation?

- **Yes.**
- Combining path filtering and blob text replacement in one `git filter-repo` invocation is valid.
- In plan v3, `--path data/home/ --invert-paths` and `--path profile.yaml --invert-paths` remove those paths from history, while `--replace-text replacements.txt` rewrites matching blob content in the retained history.
- The wording is correct: `--invert-paths` with `--path` means keep all paths except the specified paths.

### c. `--force-with-lease=main:<old-head>` syntax?

- **Yes, with one precision note.**
- `--force-with-lease=<refname>:<expect>` is valid Git push syntax: it allows the force update only if the remote ref currently equals `<expect>`.
- In the plan command, `main:<旧head>` means "only update remote `main` if its current value is the old head observed before rewrite."
- For maximum explicitness, `--force-with-lease=refs/heads/main:<旧head> origin main` is the least ambiguous form, but plan v3's `main:<旧head>` is acceptable shorthand.

## B.5c Ephemeral Scope Assessment

- Plan v3 correctly identifies that `agent_cli` currently lacks `scope=ephemeral` and must add it.
- The 0.3-0.5d estimate is plausible if implemented narrowly: allow `cmd_start` to take an override round-state directory or dry-run context, run the no-context lunch path, assert `status=resolved`, then delete temp state.
- Simpler option: for onboard validation, call the deterministic preparation path directly instead of adding a public `agent_cli` scope.
- Recommended cut: implement an internal helper, not a user-facing `--scope ephemeral` CLI contract.
  - Example shape: `onboard` calls `prepare_candidates`/equivalent with temp state root and no persistence.
  - Keep any `ephemeral` mode private to `chisha.cli` or tests unless there is a separate product need.
- Do not skip the validation: the plan's requirement that onboard proves profile + zone + methodology can start is correct.

## Time Estimate Alignment

| | Top Table (v3) | Bottom Table (v3) | Correct Value |
|---|---:|---:|---:|
| Sprint A | 1.5-2.5d | 1.5-2.5d | 1.5-2.5d |
| Sprint B | 4.4-8d | 4.8-8.7d | 4.8-8.7d |
| Total | 5.9-10.5d | 6.3-11.2d | 6.3-11.2d |

- Arithmetic: `1.5 + 4.8 = 6.3`; `2.5 + 8.7 = 11.2`.
- The bottom per-sprint table is more detailed and should be treated as ground truth.
- The top Sprint拆分 table should be changed to:
  - Sprint A: `1.5-2.5d`
  - Sprint B: `4.8-8.7d`
  - 合计: `6.3-11.2d`
- The top prose currently says `顶部估时 5.8-10.5d`; it should also be updated to `6.3-11.2d`.

## Final Verdict

**BLOCK**

- P0-4 remains unresolved: update the top Sprint拆分 table to Sprint B `4.8-8.7d` and total `6.3-11.2d`.
- Also update the opening v3-change prose from `顶部估时 5.8-10.5d` to `顶部估时 6.3-11.2d`.
- After those two text-only fixes, all Round-3 P0s are resolved and Sprint A can start.

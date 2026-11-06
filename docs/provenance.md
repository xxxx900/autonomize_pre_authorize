# Provenance and hours

This page records who wrote what, how the work was checked, and what the git history shows about time spent.

## Who wrote what

Claude Code (model Claude Opus 5.5) wrote the code, tests, scripts, compose files, CI workflow, and docs in this repository, working from `implementation-plan.md` under the direction of the repository owner. The owner set the goal and the plan's resolved decisions (plan section 10: repo creation by Claude, HAPI reload on every start, CI in the MVP with Azure deferred, and the interpretation calls for PA-004, PA-007, and C4), and reviews the result.

The git history supports this in two ways. Run `git log --format='%an | %(trailers:key=Co-Authored-By,valueonly)'` to see both:

- Every commit has the git author `jbk37`, the owner's local git identity, because the commits were made in the owner's checkout.
- Every commit carries the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, which names Claude as co-author. No commit lacks it, including the first commit that added `implementation-plan.md`.

The history therefore does not separate human-written lines from AI-written lines inside a commit. The plan's decisions table and section 10 record decisions the owner made. The prose that states them was committed with the same trailer as everything else.

Two parts of the repository were not written in this project:

| Path | Origin |
|---|---|
| `resources/bundles/`, `resources/requests/`, `resources/policy_MP-SYN-021.json`, `resources/index.json`, `resources/README.md` | The assignment's synthetic data pack ("FDE Assignment v2 data pack"), added in 9efbad6 |
| `resources/synthea/` (not in git) | The Synthea nov2021 sample, fetched by `scripts/fetch_synthea.py` and checked against a pinned sha256 |

## How the work was checked

Every command below runs in a container. None of them takes a model's word for the result.

| Check | Command | What it proves |
|---|---|---|
| Lint, format, and unit tests (161 tests at the last commit) | `docker compose --profile test run --rm --build test` | Rules, auth, audit chain, loader, summary checks, MCP gate, and API behavior against a fake FHIR server |
| Seven supplied requests | `python -m scripts.check_seven` against the live API | Every status and route matches plan section 5 |
| Seventeen requests | `docker compose --profile eval run --rm run-eval` | Every status matches plan section 5 or the hand audit in `eval/synthea_expected.json` |
| Hand audit of ten Synthea records | `python -m eval.audit_facts`, then reading | Expected statuses written from the raw bundles before any engine run on them (commit d961864 precedes the eval runner in cef8412) |
| Agent against endpoint | `python -m scripts.check_agent` | The packet the agent gets over MCP equals the endpoint's packet for all seven requests |
| Audit chain | `GET /audit` as admin | `chain.valid` is true over every row written during the checks |
| Model measurements | `docker compose --profile eval run --rm measure` | Schema, faithfulness, forbidden-word, and latency figures in `eval/results/` |

The tests check behavior a user can observe, such as statuses, HTTP codes, audit rows, and what reaches the model. For the metformin attestation fix (9cbd356), the test was written first and seen to fail. The tests for the Synthea loader order (1e3263a) and the model warm-up (21e6c49) were seen to fail with the change removed.

## Hours

Per-phase hours are not recorded precisely. The plan asked for a time log per phase, and no log was kept. The only time record is the git author timestamps, and they show when commits were made, not when work started. Work before the first commit, such as reading the data pack and drafting the plan, does not appear at all. Phases 4, 6, 7, and 8 were built in parallel git worktrees and merged later, so their spans overlap. The phases 5 and 9 work and the two plan section 9 code items were also built in a separate worktree.

Run `git log --reverse --format='%h %ad %s' --date=format:'%m-%d %H:%M'` to rebuild this table. Times are local (UTC-6). The table assigns each commit to the phase its message names.

| Phase | Plan budget | First commit | Last commit | Commits |
|---|---|---|---|---|
| 0, 1: scaffold, FHIR server, loader | 1.0 h | 11-05 22:19 | 11-05 22:36 | 5 |
| 2: rules engine, packet model | 1.5 h | 11-05 22:22 | 11-05 22:24 | 4 |
| 3: auth, audit, logs, endpoint | 1.25 h | 11-05 22:39 | 11-05 22:40 | 3 |
| 4: safety and summary | 0.5 h | 11-05 22:44 | 11-05 23:16 | 7 |
| 6: MCP server and agent | 0.75 h | 11-05 22:42 | 11-05 23:30 | 4 |
| 7: nurse page | 0.5 h | 11-05 22:50 | 11-05 22:50 | 1 |
| 8: CI | 0.25 h | 11-05 22:53 | 11-05 22:53 | 1 |
| 5: evaluation | 1.5 h | 11-05 23:36 | 11-06 00:07 | 8 |
| Plan section 9: model warm-up, MCP refusal audit | not budgeted | 11-05 23:48 | 11-05 23:49 | 2 |
| 9: docs | 0.75 h | 11-05 23:58 | the commit that adds this page | 4 |

The commits span 11-05 22:19 to 11-06 00:13 before this page, about two hours. That span is a lower bound on elapsed time, because work before the first commit is missing. It is not a measure of effort, because worktrees ran in parallel. The 7B model measurement alone took three attempts. Twice an action outside this work stopped every container on the host, and `docker events` shows explicit stop and kill events for them.

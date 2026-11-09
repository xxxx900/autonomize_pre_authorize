---
name: verify
description: Launch an isolated copy of the PA evidence packet service (FastAPI + HAPI FHIR + Ollama + MCP, Docker Compose) and drive it over HTTP to prove behavior — evidence packets, auth refusals, audit trail, health, summary model choice, the MCP agent. Use after changing app/, mcp_server/, agent/, compose, or .env.example, or whenever a claim about this service's runtime behavior needs proof.
---

# Verify the PA evidence packet service

The product is an HTTP API (primary surface), two static browser pages that call it (`/` worksheet, `/audit/view` audit table), and an MCP server driven by a CLI agent. Every proof here goes through the real HTTP path with real bearer tokens against a real HAPI FHIR server. Nothing calls Python internals.

All commands run from the repo root in Git Bash. The helper is `.claude/skills/verify/scripts/pa-verify`; below, `V=.claude/skills/verify/scripts/pa-verify`.

## Isolation

The developer usually has their own stack running on ports 8000/8080/8001/11434 with their own `.env` and audit volume. **Never drive it.** `pa-verify` runs Compose project `pa-verify` on ports **18000** (api), **18080** (hapi), **18001** (mcp), **21434** (ollama), with tokens generated per run into `.verify/runs/<run>/verify.env`. It passes `--env-file`, so the developer's `.env` is never read. Only one `pa-verify` run can be up at a time (fixed ports); if `doctor` shows a run you did not start, ask before tearing it down.

## Launch

```sh
$V up
```

What it does: writes a run id to `.verify/current`, generates nurse/admin/MCP tokens, copies pulled models from the developer's `autonomize_pre_authorize_ollama-data` volume into `pa-verify_ollama-data` (first run only; otherwise `ollama-pull` downloads ~4 GB), then `docker compose up -d --build`. HAPI has no volume and the audit volume is fresh, so every launch starts from empty data; the `loader` service loads all bundles before `api` starts.

Ready means usable, and `up` waits for all three: `GET /ready` is 200, `ollama-pull` exited 0, and an authenticated `GET /requests/PA-001/evidence` returns 200. It prints `ready: run <id>, api http://localhost:18000, evidence <dir>`. Allow 1–3 minutes (image build, HAPI start, bundle load); it gives up after 10.

Synthea members (SYN-001..010) only load if `resources/synthea/` exists before `up` (fetch once with `docker compose --profile synthea run --rm --build fetch-synthea`). Their request forms are always on disk, so without the bundles they return 404 "member not found".

## Doctor

```sh
$V doctor
```

Read-only. Exits non-zero on any `FAIL`. Checks: containers of project `pa-verify` and their health; port 18000 is published by this project's `api`; `/ready` is 200; the admin token is accepted; **the code in the `api` container hashes the same as `app/` in the working tree** (a mismatch means you edited after `up`; run `$V down && $V up`); and prints the per-component state from `GET /health/details`. Run it first, and again whenever a result looks wrong.

## Drive

```sh
$V get <nurse|admin|wrong|none> <path> <name>   # saves <name>.status/.headers/.json, prints status + X-Request-ID
$V json <name> '<python expression over d>'     # query a saved body; d is the parsed JSON
$V logs <request_id>                            # api JSON log lines for one request, saved as evidence
$V agent <request_id> [--model <ollama tag>]    # ReAct agent over MCP, output saved
$V compose <docker compose args>                # escape hatch, already scoped to the project
$V env                                          # api URL, run id, evidence dir, env file
```

`wrong` sends a syntactically valid but unknown token; `none` sends no Authorization header. Every response carries `X-Request-ID`; the same value is the packet's `trace.trace_id`, the audit row's `request_id`, and the log line's `request_id`, so one id joins all three proofs. Feature recipes with exact paths and expected results are in [`features/`](features/README.md).

The browser pages are static HTML that call the same endpoints; drive them with the `claude-in-chrome` skill at `http://localhost:18000/` and `/audit/view`, typing the token from `$V env`'s env file. The stable handles are the element ids `token`, `picker`, `model`, `request_id`, `resource`, `action`, `outcome` and the submit buttons `Load packet` / `Show`.

## Evidence

Artifacts go to `.verify/evidence/<run>/` (git-ignored) and survive `down`. A proof is complete when it has:

- the action: the `<name>.status` line (method, path, role, HTTP status) for each call;
- the resulting state: the `<name>.json` body, queried with `$V json` for the specific fields you claim;
- the side effects: the audit row (`GET /audit?request_id=<X-Request-ID>` as admin) and the log line (`$V logs <id>`). An evidence read that is not in the audit trail, or a refusal that is not audited, is a failure even if the HTTP status was right.

Report the run id and the artifact names with your claim. Do not prove behavior with `pytest`, `TestClient`, or by calling Python functions; that is unit testing, not verification. The only mocks in this stack are none: FHIR, Ollama, and the audit store are real.

## Cleanup

```sh
$V down            # remove containers, network, and the pa-verify audit volume; keep the model copy
$V down --purge    # also remove pa-verify_ollama-data
```

`down` only touches project `pa-verify`. Never `docker compose down` without `-p pa-verify`, never kill containers by name pattern, and never remove `.verify/evidence/`. Run `down` after every failed `up` too, so ports 180xx are free for the next run.

## Proven

Last end-to-end run: 2026-11-08 (run `20261108-132059`), Docker Desktop 29.9.2 on Windows 11 with Git Bash, while the developer's own stack ran on 8000. Launch from empty data → doctor (all ok, code hash matched) → every API and agent step of [evidence packet](features/evidence-packet.md) (PA-001 complete, PA-004 conflict with form 6.0 vs record 0.7 months, PA-002 missing HbA1c, PA-006 injection inert, cited sources 200 on HAPI, PA-999 404, audit row and log line joined by request id, agent tool result) → down → evidence still on disk, developer stack untouched.

Not yet driven: the browser steps (claude-in-chrome) and the other four feature files. Their recipes come from the code and the live API outputs seen on 2026-11-08, but no one has run them as written.

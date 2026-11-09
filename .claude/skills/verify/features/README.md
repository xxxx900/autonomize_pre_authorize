# PA evidence service verification map

This directory is the maintained source for verifying the user-facing behavior of the PA evidence packet service. Read this index, then use the matching feature file as the recipe.

## Baseline preconditions

- A run started by `pa-verify up` in this session; `pa-verify doctor` exits 0 with "container code matches working tree".
- API at `http://localhost:18000`, project `pa-verify`, tokens from `.verify/runs/<run>/verify.env`.
- Supplied data loaded (PA-001..PA-007). Synthea members SYN-001..SYN-010 only if `resources/synthea/` existed before `up`.
- Never drive the developer's stack on port 8000.

## Driving conventions

- `V=.claude/skills/verify/scripts/pa-verify`. Every call goes through `$V get <role> <path> <name>`; give each call a unique `<name>`.
- Assert on fields with `$V json <name> '<expr>'`, never by eyeballing the whole body.
- Join proofs on `X-Request-ID`: packet `trace.trace_id`, audit `request_id`, log `request_id`.
- Reading `/audit` itself writes an `audit.read` row; filter by `request_id` or `resource` instead of counting all rows.
- The service is read-only against FHIR; there is no mutation to restore. The audit log is append-only by design and is reset only by `$V down`.

## Proof and skip reporting

- Capture the call (`.status`), the body (`.json`), and the side effect (audit row, log line).
- For refusals, prove both the status code and the audited row with actor `anonymous` / `unknown` and outcome `unauthenticated` / `forbidden`.
- Report an unreachable path with the command tried and the unmet precondition (for example, Synthea bundles not loaded).
- Do not report the browser page as verified through curl; they are separate entry points.

## Feature entry contract

Each feature file starts with an H1 and one paragraph, then four H2 sections in order: `Sub-features`, `How to get to it (user POV)`, `Driving it with pa-verify`, `Gotchas`.

## Features

- [Evidence packet](./evidence-packet.md): per-criterion statuses, sources, missing documents, route, summary; API, worksheet, and MCP agent entry points.
- [Auth and refusals](./auth-and-refusals.md): nurse/admin roles, 401 and 403, every refusal audited.
- [Audit trail](./audit-trail.md): one hash-chained row per call, filters, the `/audit/view` table.
- [Health and readiness](./health.md): `/health`, `/ready`, admin `/health/details` component report.
- [Summary model choice](./summary-model-choice.md): `/catalog`, `?summary_model=` allow-list, recorded model.

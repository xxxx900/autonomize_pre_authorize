# Audit trail

An admin can see who did what, when, to which request and member, with which policy version and summary model, and the outcome, without any clinical values. Rows are append-only and hash-chained, and every read of the trail reports whether the chain is intact.

## Sub-features

- `audit-row` writes one row per packet request with subject, policy version and hash, summary model, route template, status, and duration.
- `audit-filter` filters by `request_id`, `resource`, `action`, `actor`, `outcome`, `limit`.
- `audit-chain` reports `chain.valid` and rows checked over the whole log.
- `audit-view` shows the same rows as a table at `/audit/view`, newest first; clicking a row reveals its context and hashes.
- `audit-start` writes a `service.start` row with the non-secret config on every process start.

## How to get to it (user POV)

- `GET /audit?...` with the admin token.
- `/audit/view` in a browser: type the admin token, set filters, press `Show`. The worksheet's trace card links to `/audit/view#request_id=<trace id>`.

## Driving it with pa-verify

Preconditions:

- Baseline from the index; one packet fetched in this run, for example `$V get nurse /requests/PA-005/evidence pa005`.

- **Row for a packet.** With the `x-request-id` from `pa005`, run `$V get admin "/audit?request_id=<id>" pa005-audit` then `$V json pa005-audit "[d['chain'], [(e['action'], e['resource'], e['outcome'], e['context']['policy_version'], e['context']['summary']['source']) for e in d['events']]]"`. One `evidence.read` row for `PA-005`, outcome `ok`, policy `2026.1`, and `chain.valid` true.
- **No clinical values.** Run `$V json pa005-audit "sorted(d['events'][0]['context'].keys())"`. Keys are identifiers and timings only. `grep -ci "hba1c\|birth" .verify/evidence/*/pa005-audit.json` is `0`.
- **Start rows.** Run `$V get admin "/audit?action=service.start" starts` then `$V json starts "[(e['actor'], sorted(e['context']['config'])) for e in d['events']]"`. One row per process (`system` for api, `mcp-server` for mcp) with config keys and no token values.
- **Append-only.** Run `$V compose exec -T api python -c "import sqlite3; sqlite3.connect('/data/audit.db').execute('DELETE FROM audit_event')"`. It fails with `audit log is append-only`.
- **Browser table.** With claude-in-chrome, open `http://localhost:18000/audit/view#request_id=<id>`, fill `token` with the admin token, press `Show`. A banner "Hash chain intact over all N rows." and a row with action `evidence.read`, resource `PA-005`, outcome `ok`; clicking the row reveals the context JSON and both hashes.

## Gotchas

- Every `GET /audit` adds an `audit.read` row, so totals grow while you look; always filter.
- The chain check covers every row, not just the filtered ones.
- The audit volume belongs to project `pa-verify`; `$V down` wipes it, so capture proof before cleanup.
- Do not prove tamper detection by editing the live DB with the triggers dropped; `test_broken_audit_chain_marks_the_audit_log_down` covers that path.

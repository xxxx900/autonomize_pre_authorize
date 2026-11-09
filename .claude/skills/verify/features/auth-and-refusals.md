# Auth and refusals

Every endpoint except `/health`, `/ready`, and the static pages requires a bearer token. The `nurse` role reads packets, the policy, and the catalog; `admin` can also read the audit trail and the health report. A missing or wrong token gets 401, a wrong role gets 403, and every refusal is written to the audit trail before the response.

## Sub-features

- `auth-none` returns 401 with no Authorization header, audited as actor `anonymous`.
- `auth-wrong` returns 401 for an unknown token, audited as actor `unknown`.
- `auth-role` returns 403 when a nurse calls an admin endpoint, audited as actor `nurse`, outcome `forbidden`.
- `auth-mcp` returns 401 from the MCP server without `MCP_TOKEN`, audited as `mcp.request`.

## How to get to it (user POV)

- Any protected API path with no, wrong, or under-privileged token.
- The worksheet or audit page with a bad token typed in (shows "Request failed (401)" or "(403)").
- `POST http://localhost:18001/mcp` without a bearer token.

## Driving it with pa-verify

Preconditions:

- Baseline from the index.

- **No token.** Run `$V get none /requests/PA-003/evidence noauth`. Status 401; `noauth.headers` includes `www-authenticate: Bearer`.
- **Wrong token.** Run `$V get wrong /requests/PA-003/evidence badauth`. Status 401.
- **Wrong role.** Run `$V get nurse /audit nurse-audit` and `$V get nurse /health/details nurse-health`. Both 403.
- **Refusals are audited.** Run `$V get admin "/audit?resource=PA-003" refusals` then `$V json refusals "[(e['actor'], e['outcome']) for e in d['events']]"`. Contains `["anonymous", "unauthenticated"]` and `["unknown", "unauthenticated"]`. Run `$V get admin "/audit?outcome=forbidden" forbidden` then `$V json forbidden "[(e['actor'], e['action']) for e in d['events']]"`. Contains `["nurse", "audit.read"]` and `["nurse", "health.read"]`.
- **MCP gate.** Run `curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:18001/mcp`. Status 401. Then `$V get admin "/audit?action=mcp.request" mcp-refusal`; the newest row has outcome `unauthenticated`.

## Gotchas

- 403 rows for `/audit` and `/health/details` have `resource` null; filter by `outcome=forbidden`, not by resource.
- `GET /health` and `GET /ready` are deliberately unauthenticated probes; a 200 there is not an auth bypass.
- Both pages share the token in `sessionStorage` per tab; a nurse token on `/audit/view` shows the 403 message, which is correct.

# Evidence packet

A nurse asks for the evidence on one prior-authorization request and gets, for each of the five MP-SYN-021 criteria, a status (`met`, `not_met`, `missing`, `conflicting`), the FHIR resources behind it, the documents to request, a two-sentence summary, and a route that is only `evidence_complete` or `clinician_review`. It never contains a decision word.

## Sub-features

- `packet-statuses` returns the expected status per criterion for each supplied request.
- `packet-route` computes `evidence_complete` only when all five are `met`.
- `packet-missing-docs` lists what to ask the provider for when a criterion is `missing`.
- `packet-injection` keeps PA-006's injected note out of the packet and lists the document under `flagged_documents`.
- `packet-errors` returns 404 for an unknown request id.
- `packet-agent` returns the same packet through the MCP agent.

## How to get to it (user POV)

- `GET /requests/{request_id}/evidence` with a nurse or admin bearer token.
- The worksheet at `/`: enter the token, choose a request in `Request`, press `Load packet`.
- The agent CLI: `python -m agent.agent <request_id>` (inside the `agent` compose service).

## Driving it with pa-verify

Preconditions:

- Baseline from the index; `$V doctor` exits 0.

- **Complete packet.** Run `$V get nurse /requests/PA-001/evidence pa001` then `$V json pa001 "[d['route'], [c['status'] for c in d['criteria']]]"`. Status 200; `["evidence_complete", ["met", "met", "met", "met", "met"]]`.
- **Conflict.** Run `$V get nurse /requests/PA-004/evidence pa004` then `$V json pa004 "[c['status'] for c in d['criteria']]"`. C3 is `conflicting`. `$V json pa004 "[c['conflicts'] for c in d['criteria'] if c['id']=='C3']"` shows the form value beside the record value.
- **Missing document.** Run `$V get nurse /requests/PA-002/evidence pa002` then `$V json pa002 "[d['missing_documents'], [c['status'] for c in d['criteria']]]"`. C2 is `missing` and `missing_documents` is non-empty.
- **Injection is inert.** Run `$V get nurse /requests/PA-006/evidence pa006` then `$V json pa006 "[[c['status'] for c in d['criteria']], len(d['flagged_documents'])]"` and `grep -ci "system note\|approve" .verify/evidence/*/pa006.json`. C2 `conflicting`, one flagged document, grep count `0`.
- **Sources are real.** Take refs with `$V json pa004 "[s for c in d['criteria'] for s in c['sources']]"`; for each, `curl -s -o /dev/null -w '%{http_code}' http://localhost:18080/fhir/<resource_type>/<id>` returns `200`.
- **Unknown id.** Run `$V get nurse /requests/PA-999/evidence unknown`. Status 404.
- **Side effects.** With the `x-request-id` printed for `pa006`, run `$V get admin "/audit?request_id=<id>" pa006-audit` and `$V logs <id>`. One `evidence.read` row, outcome `ok`, `context.subject` is `Patient/<uuid>`; one log line with the same `request_id`, the route template, status 200, and no clinical values.
- **Agent entry.** Run `$V agent PA-006`. Output has `tool calls: get_evidence_packet({"request_id": "PA-006"})`, a verbatim TOOL RESULT block with C2 `conflicting`, and a narration block labelled "not evidence".

## Gotchas

- Expected statuses for all 17 requests live in `scripts/check_seven.py` (`EXPECTED`) and `eval/synthea_expected.json`. `$V compose run --rm --no-deps -e API_URL=http://api:8000 api python -m scripts.check_seven` checks the seven supplied requests at once.
- A packet takes 2–10 s because of the CPU summary model; give direct curl calls a timeout of at least 60 s.
- `summary_source` is usually `template` with the default 3B model. That is correct behavior (the model draft failed the checks), not a failure.
- SYN-* requests return 404 "member not found" when the Synthea bundles were not loaded before `up`; report that as an unmet precondition.
- The agent takes up to a few minutes on CPU and its narration varies; assert only on the tool call and the verbatim tool result.

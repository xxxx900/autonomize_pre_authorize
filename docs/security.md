# Security notes

This page explains how the service resists prompt injection, who can call it, how the audit log detects tampering, what the logs hold, and which threats the MVP does not cover. All data in this repository is synthetic.

## Free text is never parsed (D4)

PA-006 carries an injection attack twice. `Condition.note` in `resources/bundles/PA-006.json` contains, after an ordinary clinical sentence, a "SYSTEM NOTE TO REVIEWER" that says every criterion is met and tells the reader to approve the request. The H&P `DocumentReference` (`DocumentReference/a144ff42-018a-5d19-8e93-247327125681`) carries the same text base64-encoded in its attachment. The request form's `prescriber_attestation.notes` points at that document with "See attached office note."

The defence is structural. No code path reads those fields:

- `app/loaders/fhir_record.py` parses each FHIR resource into a typed model with only the structured fields the rules use: codes, clinical status, dates, quantities, and prescription periods. `Condition.note`, `DocumentReference.content`, and the form `notes` have no field to land in.
- `app/rules/evaluate.py` lists every `DocumentReference` in `flagged_documents` by type, date and reference, so the nurse knows a document exists and opens it in the source system. The service never decodes the attachment.
- The summary model sees only `evidence_text(packet)` from `app/summary/safety.py`: statuses, requirements, rationales, missing documents, and attestation comparisons. The rationales are built from structured values.

The result for PA-006 is that C2 is `conflicting` (form HbA1c 7.8 against record 6.4 on the same date), the route is `clinician_review`, and the document appears in `flagged_documents`. Two tests pin this down. `test_pa006_flags_document_and_keeps_note_text_out_of_the_packet` in `tests/test_rules.py` checks the packet. `test_pa006_packet_and_prompt_carry_nothing_from_the_injected_text` in `tests/test_summary.py` checks the packet and every prompt sent to the model for each injected string.

A second layer catches a model that misbehaves for any other reason. `check_output` in `app/summary/output.py` rejects a summary with a forbidden word (approve, deny, recommend, should, eligible, and others in `FORBIDDEN_PATTERN`), a number or date not in the packet, a criterion id not in the packet, or a status claim that differs from the packet. A rejected summary is replaced by the template summary, and `summary_source` says `template`.

## Authentication and roles

- The API maps static bearer tokens to two roles (D6). `NURSE_TOKEN` can read evidence, the policy, and the catalog (request ids and allowed summary models). `ADMIN_TOKEN` can also read the audit log (`GET /audit`, shown as a table at `/audit/view`) and the component health report (`GET /health/details`). `app/security/auth.py` compares tokens with `secrets.compare_digest`, and `Settings` refuses to start when the two tokens are equal.
- A missing or wrong token returns 401, and a valid token with the wrong role returns 403. Both are audited before the response is sent, with actor `anonymous` (no bearer token) or `unknown` (a bearer token that matches no role).
- The MCP server requires `MCP_TOKEN` through `BearerGate` in `mcp_server/server.py`. A refused MCP request is audited with action `mcp.request` and outcome `unauthenticated`. The gate answers before it reads the JSON-RPC body, so it cannot know which tool was requested, and the row does not claim `evidence.read`. Tool calls that pass the gate are audited with actor `mcp-agent`.
- The API authenticates to FHIR with `FHIR_AUTH_MODE`: `none` for the local HAPI, `bearer` for a static token, or `smart` for the SMART client-credentials grant. `app/clients/fhir_auth.py` caches the SMART token and refreshes it 30 seconds before it expires.
- The production replacement for the token map is Entra ID OIDC with a group-to-role mapping (D6).

## Audit log and its limits

`app/audit/store.py` writes one row per call to a SQLite table. A row holds the sequence number, UTC timestamp, actor, role, action, a per-request id, the resource (a request id such as `PA-004` or the policy id), the outcome, a `context`, the previous row's hash, and its own hash. The per-request id is the `X-Request-ID` the caller received and the packet's `trace.trace_id`, so one id joins the response, the log line, and the audit row.

The `context` (`AuditContext` in `app/domain/audit.py`) holds identifiers and timings, never clinical values:

- `subject`: the `Patient/<id>` whose record an evidence read touched, with `phi_resource_types` and `phi_resources_read`. This is the per-member access trail an accounting of disclosures needs.
- `duration_ms`, `http_route`, and `status_code`.
- `policy_version` and `policy_sha256`: which policy text produced the packet.
- `summary`: who wrote the summary (`model` or `template`), the model name, its latency, and the reason for any fallback (`rejected`, `bad_output`, `model_error`, `unreachable`, `not_configured`).
- `error`: the PHI-free failure message.
- `config`, on `service.start` rows only: the non-secret settings, policy hash, and prompt version at startup. Two consecutive start rows show what changed between deployments.

The hash is SHA-256 over all the other fields, the canonical JSON of `context`, and the previous hash, so each row commits to the whole chain before it. SQLite triggers abort any `UPDATE` or `DELETE`. `GET /audit` returns the result of `verify_chain` over every row, which reports the first broken sequence number, and the rows that match its filters: `action`, `actor`, `resource`, `outcome`, `request_id`, and `limit`.

A database created before the `context` column existed is upgraded in place on start. Old rows have no context and hash exactly as before, so their chain still verifies.

The chain detects an edit to any row and the deletion of any row except the last ones. It has these limits:

- **Tail deletion is undetectable from inside the database.** Someone who deletes the newest rows leaves a valid shorter chain. Detecting that needs the latest hash stored somewhere the attacker cannot write, for example a daily anchor of the chain head in immutable storage (D7 names Azure Blob storage with immutability).
- **A full rewrite is undetectable.** Someone with write access to the file can drop the triggers, change rows, and recompute every hash. External anchoring closes this too.
- **The API and the MCP server share one database file** on the `audit-data` volume. `BEGIN IMMEDIATE` serializes their appends, so the sequence stays gapless.

## What the logs hold

`app/ops/logs.py` writes JSON lines with an allow-list of fields: `event`, `request_id`, `route`, `method`, `status`, `duration_ms`, `component`, `state`, `latency_ms`, `summary_source`, `summary_model`, `summary_fallback`, and `outcome`. A structured field outside the list is dropped, so a clinical value passed by mistake never reaches a log line. The route is the route template (`/requests/{request_id}/evidence`), not the URL. Plain log messages carry only fixed text and exception type names, for example `{"event": "summary_fallback", "summary_fallback": "rejected"}` and `summary model warm-up done in 3.1 s`. Model output, prompts, and FHIR content are never logged.

## Threats the MVP does not cover

- **No TLS.** The stack serves plain HTTP on localhost. The deferred Azure deployment puts Caddy with HTTPS in front.
- **Shared tokens.** Every nurse uses the same token, so the audit log records a role, not a person. Tokens do not expire and have no rotation procedure.
- **No rate limiting** on the API or the MCP server.
- **The nurse page keeps the token in `sessionStorage`**, which any script running on the page can read. The page loads no third-party script.
- **The FHIR server is trusted.** The service checks that every cited resource exists, but it cannot detect a record that was altered at the source.
- **Model tags are pinned by name, not by digest.** `ollama-pull` fetches tags. The measurement files record the digest each run used, so a changed model shows up there, but nothing blocks it.
- **No check that the member is alive.** The policy has no such criterion, and the service builds an ordinary packet for a member with `Patient.deceasedDateTime`. See [decisions](decisions.md#a-deceased-member-gets-an-ordinary-packet).
- **Resource limits.** A very large patient record (tens of thousands of resources) loads slowly and can exceed `MAX_PAGES` in `app/clients/fhir_client.py`, which returns a 502.

# Prior Authorization Evidence Packet: FDE Assignment v2

This service assembles the evidence for a GLP-1 prior-authorization request against Payer A's policy MP-SYN-021. For each of the five criteria it returns `met`, `not_met`, `missing`, or `conflicting`, the FHIR resources behind that status, the documents to ask the provider for, and a two-sentence summary. **It never decides.** Deterministic Python rules compute every status. A local 3B model writes only the summary, and a summary that fails the checks is replaced by a template. `route` is only `evidence_complete` or `clinician_review`. 
Client request quote:
> "Show me what the policy needs, show me where it is in the chart, tell me what's missing, and never tell me what to decide."

Everything here is synthetic: the supplied data pack and the Synthea sample only.

**Quick start** (Docker Desktop and git; nothing else on the host):

```sh
cp .env.example .env              # set NURSE_TOKEN, ADMIN_TOKEN, MCP_TOKEN
docker compose up -d --build      # HAPI FHIR, loader, Ollama + pinned models, API, MCP server
open http://localhost:8000        # nurse worksheet; http://localhost:8000/audit/view for the audit table
```

Every command, endpoint, and check is in the [runbook](docs/runbook.md).

## Assignment items at a glance

| # | Item | Status | Primary source |
|---|---|---|---|
| 1 | FHIR R4 server, scripted repeatable load | ✅ Delivered | [`docker-compose.yml`](docker-compose.yml#L1-L20), [`scripts/load_fhir.py`](scripts/load_fhir.py) |
| 2 | `GET /requests/{id}/evidence` | ✅ Delivered | [`app/api/routes/evidence.py`](app/api/routes/evidence.py), [`app/api/pipeline.py`](app/api/pipeline.py#L83), [`app/rules/`](app/rules/) |
| 3 | MCP tools + local ReAct agent | ✅ Delivered (agent is a second front door) | [`mcp_server/server.py`](mcp_server/server.py#L92-L106), [`agent/agent.py`](agent/agent.py#L56) |
| 4 | Safety: tags, Pydantic, source check, faithfulness | ✅ Delivered | [`app/summary/`](app/summary/) |
| 5 | Evaluation: 7 supplied + 10 Synthea, hand audit | ✅ Delivered, 85/85 statuses agree | [`docs/evaluation.md`](docs/evaluation.md), [`eval/results/eval.md`](eval/results/eval.md) |
| 6 | One-page plan, week 1 and week 6, cut list, hours | ✅ Delivered | [`docs/payer-a-plan.md`](docs/payer-a-plan.md), [hours](#hours) |
| 7 | Security notes: LLM01, LLM02, local vs external | ✅ Delivered in this README | [below](#7-security-notes-owasp-llm01-and-llm02), [`docs/security.md`](docs/security.md) |
| 8 | Enterprise minimum set | ✅ Delivered; production items are in the week-six plan | [below](#8-enterprise-readiness) |

Nothing is declined. Each section below names what was cut inside an item, and why.

---

### 1. FHIR server and repeatable load

- HAPI FHIR `v8.12.0-2` in Compose ([`docker-compose.yml#L2`](docker-compose.yml#L2-L8)).
- A one-shot `loader` service ([`scripts/load_fhir.py`](scripts/load_fhir.py)) posts every transaction bundle on every `docker compose up`. It loads Synthea's shared Practitioner and Organization bundles first, because the patient bundles reference them by conditional search. HAPI has no volume, so each start begins clean and loading twice gives the same counts.
- The Synthea sample is a pinned archive with a checked SHA-256 ([`scripts/fetch_synthea.py`](scripts/fetch_synthea.py)).

### 2. Evidence endpoint

- Route: [`app/api/routes/evidence.py`](app/api/routes/evidence.py). Pipeline: [`EvidencePipeline.run`](app/api/pipeline.py#L83). It loads the form, reads the member's FHIR record, runs the rules, checks that every cited source exists, then summarizes.
- One rule file per criterion: [`c1_diagnosis.py`](app/rules/c1_diagnosis.py), [`c2_hba1c.py`](app/rules/c2_hba1c.py), [`c3_metformin.py`](app/rules/c3_metformin.py), [`c4_exclusions.py`](app/rules/c4_exclusions.py), [`c5_age.py`](app/rules/c5_age.py). They are pure functions over a parsed record, with thresholds and code lists read from the policy JSON.
- Packet shape: [`app/domain/packet.py`](app/domain/packet.py). `route` is computed from the statuses ([L77](app/domain/packet.py#L75-L81)). Forbidden words (approve, deny, authorize, should, and others) are blocked in the summary by [`FORBIDDEN_PATTERN`](app/summary/safety.py#L14).
- Where the policy text was ambiguous, the reading taken is in [`docs/decisions.md`](docs/decisions.md), for example PA-004 and PA-007.

### 3. MCP tools and agent

- Two read-only MCP tools, `get_evidence_packet` and `get_policy` ([`mcp_server/server.py#L92`](mcp_server/server.py#L92-L106)), served over streamable HTTP behind a bearer gate.
- The ReAct agent ([`agent/agent.py`](agent/agent.py#L56)) runs a local Ollama model (`qwen2.5:3b` by default, or `--model` per run). It assembles the packet by calling the tools and never sees the raw chart.
- **Which and why: the agent is a second front door, and the endpoint does not call it** (decision D3 in [`implementation-plan.md`](implementation-plan.md#2-key-design-decisions)). Both doors call the same `EvidencePipeline.run`, so they cannot disagree. [`scripts/check_agent.py`](scripts/check_agent.py) checks the agent's packet against the endpoint's for all seven requests. The endpoint stays fast and deterministic, and no LLM sits on the status path.
- Why `get_policy` is a keyed lookup and not RAG: [decisions](docs/decisions.md#the-policy-lookup-stays-a-keyed-tool-not-rag).

### 4. Safety

| Requirement | Where |
|---|---|
| Clinical data isolated from instructions, with explicit tags and a stated rule | [`SYSTEM_RULE`](app/summary/prompt.py#L8) says "use only the facts between the `<evidence>` tags". The packet goes in a separate user message inside `<evidence>` ([`build_prompt`](app/summary/prompt.py)). Free text (notes, attachments) is never parsed, so it cannot reach the prompt (D4). |
| Pydantic validation of every model output | [`SummaryOutput`](app/summary/output.py#L9) is passed to Ollama as the structured-output schema and validated on return. Packets, audit rows, and health reports are frozen Pydantic models ([`app/domain/`](app/domain/)). |
| Every cited source exists in FHIR | [`missing_sources`](app/summary/safety.py#L134) GETs each cited reference. One miss turns the response into a 502 instead of an unverified packet. |
| Summary names only facts in the evidence | [`faithfulness_problems`](app/summary/safety.py#L104) rejects any number, date, criterion id, or status claim not in the packet. [`check_output`](app/summary/output.py#L34) then falls back to the template, and `summary_source` says which one was served. |

PA-006 carries a prompt-injection attack in a `Condition.note` and in a base64 attachment. Both are inert, and two tests pin that down ([security notes](docs/security.md#free-text-is-never-parsed-d4)).

### 5. Evaluation

- Seven supplied requests plus ten Synthea patients (request date assumed **2021-11-19**, the sample's generation date). The hand audit was committed before the engine ran on them.
- **85 of 85 criterion statuses agree** with the expected values. **674 of 674 cited sources resolve**, each fetched straight from FHIR by the eval rather than trusted from the API. **17 of 17 served summaries pass** the faithfulness re-check: 5 written by the model, 12 by the template after the model draft failed a check ([results table](docs/evaluation.md#results), [raw output](eval/results/eval.md)).
- Findings, including one engine bug found and fixed and the implausible Synthea data: [docs/evaluation.md#findings](docs/evaluation.md#findings).
- Model choice, measured: `qwen2.5:7b` passes 5 of 7 packets, `llama3.2:3b` 1 of 7, and `qwen2.5:3b` 0 of 7 ([measurements](docs/evaluation.md#summary-model-measurements)). The default stays the 3B model the brief sizes for. A failed summary costs only prose, because the template takes over.

### 6. Plan for Payer A

[`docs/payer-a-plan.md`](docs/payer-a-plan.md) covers week one, week six (TLS, SSO group mapping, audit retention and legal hold, SIEM, encryption at rest, backup and restore, BAA scope), what we need from Payer A, and the cut list with reasons.

### 7. Security notes: OWASP LLM01 and LLM02

**LLM01, prompt injection.** The defence is structural, not a filter:

1. **Free text never enters the system.** [`app/loaders/fhir_record.py`](app/loaders/fhir_record.py) parses each resource into typed fields: codes, statuses, dates, and quantities. `Condition.note`, `DocumentReference` attachments, and the form's `notes` have no field to land in. Documents are listed by reference as "flagged documents", never decoded.
2. **The model decides nothing.** Statuses come from rules. The model sees only the finished packet, inside `<evidence>` tags, under a fixed system rule.
3. **Output is checked, not trusted.** Schema, forbidden words, numbers, dates, and status claims are compared with the packet. A failure falls back to the template.
4. **Tools are read-only.** The MCP server exposes two read tools. The agent's narration is printed under a "not evidence" label, separate from the verbatim tool result.

**LLM02, sensitive information disclosure (PHI boundary).**

- The packet carries the minimum the nurse needs for the five criteria. See [packet fields](#packet-fields-and-why-each-is-there).
- Logs carry no PHI by construction: an allow-list formatter ([`ALLOWED_FIELDS`](app/ops/logs.py#L8)) drops any other field. Sample line [below](#8-enterprise-readiness).
- Audit rows hold identifiers and timings, never clinical values ([`AuditContext`](app/domain/audit.py#L10)).
- Model prompts and outputs are never logged.

**Local inference compared with an external provider.** This build runs the model locally in Ollama. **PHI never leaves the compose network, and no third party needs a BAA.**

| | Local (Ollama, this build) | External provider (OpenAI-compatible API) |
|---|---|---|
| PHI boundary | Packet facts stay inside the environment Payer A controls | Packet facts cross to the vendor. This needs a BAA, zero data retention, and a region pin, and it widens the BAA scope. |
| Quality | 3B models are weak: 1 of 7 summaries accepted for the default | Much stronger summaries, and fewer template fallbacks |
| Latency and cost | About 2 to 10 s on CPU, no per-call cost, hardware to run | Fast, per-token cost, a network dependency |
| Operations | Pin by digest, patch Ollama, size the VM | Vendor model changes outside our control, and rate limits |
| Blast radius of a failure | Template fallback, packet unaffected | Same fallback, plus an outage path and a data-handling incident path |

The rules carry the safety, and the model writes only prose. So the external option buys better prose at the cost of a PHI boundary crossing. For Payer A's first deployment that trade is not worth it. A larger local model (`qwen2.5:7b`, 5 of 7 accepted) gets most of the quality gain without the boundary.

More detail, including the audit chain's limits and the threats the MVP does not cover: [`docs/security.md`](docs/security.md).

### 8. Enterprise readiness

| Control | Demo | Primary source |
|---|---|---|
| **Auth and roles** | Static token map: `nurse` reads packets, policy, and catalog. `admin` can also read `/audit` and `/health/details`. A 401 or 403 is audited before it returns. Production replacement: Entra ID OIDC with group-to-role mapping. | [`app/security/auth.py`](app/security/auth.py#L45), [`app/api/dependencies.py`](app/api/dependencies.py) |
| **Audit trail** | One append-only row per packet request: who, when, request id, member reference, policy id, version, and hash, summary model and prompt version, route, outcome, and HTTP status. No clinical values. SQLite triggers block UPDATE and DELETE, and a SHA-256 hash chain covers every row. `GET /audit?request_id=` returns it to an admin, and `/audit/view` shows it as a table. | [`app/audit/store.py`](app/audit/store.py#L26), [`app/audit/hash_chain.py`](app/audit/hash_chain.py), [`app/api/routes/admin.py`](app/api/routes/admin.py#L34), [`app/web/audit.html`](app/web/audit.html) |
| **Tamper evidence** | The hash chain detects any edit and any mid-chain delete. Tail deletion and a full rewrite need an external anchor: the chain head goes daily to WORM storage (week six). | [`docs/security.md`](docs/security.md#audit-log-and-its-limits) |
| **PHI hygiene** | JSON log lines with allow-listed fields only. | [`app/ops/logs.py`](app/ops/logs.py#L8) |
| **FHIR credentials** | `FHIR_AUTH_MODE=none`, `bearer`, or `smart` (SMART Backend Services client credentials, token cached and refreshed). Configured by environment variables. No secret in git, and every variable is documented. | [`app/clients/fhir_auth.py`](app/clients/fhir_auth.py#L31), [`app/config.py`](app/config.py#L11), [`.env.example`](.env.example) |
| **Operability** | `GET /health` (liveness) and `GET /ready` (FHIR, audit store, policy, request store) are separate. `GET /health/details` (admin) adds the model and the MCP server, with versions. Images are pinned (`hapi:v8.12.0-2`, `ollama:0.12.6`, `python:3.12-slim`), and model tags are pinned with the digest recorded in health and eval results. One command starts the stack. | [`app/api/routes/ops.py`](app/api/routes/ops.py), [`app/ops/health.py`](app/ops/health.py), [runbook](docs/runbook.md#engineer-health-check) |

A real log line from a `GET /requests/PA-004/evidence` call. It carries the request id and timing, and no member data:

```json
{"ts": "2026-11-08T18:57:42.602+00:00", "level": "INFO", "event": "request", "request_id": "78f356b3422d43ab93022d51b9ddb015", "method": "GET", "route": "/requests/{request_id}/evidence", "status": 200, "duration_ms": 12176.8}
```

The audit row for that call (`GET /audit?request_id=78f356b3…`, trimmed):

```json
{"seq": 131, "actor": "nurse", "role": "nurse", "action": "evidence.read", "resource": "PA-004", "outcome": "ok",
 "context": {"http_route": "/requests/{request_id}/evidence", "status_code": 200, "duration_ms": 12170.5,
   "subject": "Patient/cbe7cb0a-bbe9-5590-b325-609a9467084b", "phi_resource_types": ["AllergyIntolerance", "Condition", "MedicationRequest", "Observation", "Patient"],
   "policy_version": "2026.1", "policy_sha256": "d5128143…",
   "summary": {"source": "template", "model": "qwen2.5:3b-instruct-q4_K_M", "fallback": "bad_output"}},
 "prev_hash": "e9eb33b9…", "hash": "49e4b2b6…"}
```

#### Packet fields and why each is there

| Field | Why the nurse or reviewer needs it |
|---|---|
| `request_id`, `policy_id`, `policy_version`, `request_date` | Ties the packet to the form and the exact policy. Every window (90 days, age) is measured from `request_date`, not from today. |
| `criteria[].status`, `sources`, `requirement`, `rationale` | The core. Each line can be checked against the record. |
| `criteria[].missing_document`, `missing_documents` | What to ask the provider for. |
| `criteria[].conflicts` | The form value beside the record value, for `conflicting`. |
| `criteria[].policy`, `evidence`, `policy_source` | **Extra.** The policy clause and the exact FHIR fields each status read, with links to the resources. This answers "show me where it is in the chart" without a second lookup. It holds only the fields the rules used. |
| `flagged_documents`, `flagged_evidence` | **Extra.** Documents the service deliberately does not read (D4). The nurse must know they exist, because they may hold the answer. |
| `summary`, `summary_source`, `summary_prompt_version` | The two sentences, plus whether a model or the template wrote them. |
| `trace` | **Extra.** Request id and per-stage timings, with no clinical content. It joins the packet to its audit row and log line. |
| `route` | `evidence_complete` or `clinician_review` only. |

The packet never carries the member's name, address, or identifiers, and it has no top-level `patient_id`; the request id identifies the case. The one demographic value is `birthDate`, in C5's evidence, because the age criterion is computed from it and the nurse must be able to check that arithmetic. Record references appear only as FHIR resource ids.

---

## Architecture

```text
nurse page / curl ──► api (FastAPI) ──┐
                                      ├─► EvidencePipeline.run ──► HAPI FHIR (read)
agent (ReAct) ──► mcp (FastMCP) ──────┘          │  rules (pure Python) → source check
                                                 └─► Ollama (packet facts only) → checks → summary or template
            every call ──► audit.db (append-only, hash-chained)
```

Full diagrams, including where data may and may not go: [`docs/dataflow.md`](docs/dataflow.md).

| Folder | One job |
|---|---|
| [`app/domain/`](app/domain/) | Frozen Pydantic models and enums, with no I/O |
| [`app/loaders/`](app/loaders/) | Raw JSON to domain models: FHIR record, policy, request forms |
| [`app/rules/`](app/rules/) | One file per criterion, plus `evaluate.py` |
| [`app/summary/`](app/summary/) | Prompt, model call, output checks, template |
| [`app/clients/`](app/clients/) | FHIR (with auth) and Ollama HTTP clients |
| [`app/audit/`](app/audit/) | Hash chain and SQLite store |
| [`app/security/`](app/security/) | Bearer tokens and the role guard |
| [`app/ops/`](app/ops/) | JSON logs, health probes, timing |
| [`app/api/`](app/api/) | FastAPI app, the shared pipeline, routes by audience |
| [`app/web/`](app/web/) | Nurse worksheet and admin audit table (static, no innerHTML) |
| [`mcp_server/`](mcp_server/), [`agent/`](agent/) | The second front door and its ReAct client |
| [`eval/`](eval/), [`scripts/`](scripts/) | Evaluation, model measurements, loader, checks |

[`tests/test_code_shape.py`](tests/test_code_shape.py) enforces the layout: models live only in `app/domain/`, no function is defined inside another, and every function has a docstring.

## Technical decisions

- Design decisions D1 to D14 (rules, not model; free text never parsed; agent as second front door; and others): [`implementation-plan.md` §2](implementation-plan.md#2-key-design-decisions), with what changed in [`docs/plan.md`](docs/plan.md).
- Policy interpretation calls (PA-004, PA-007, C3 windows, exact codes, deceased members): [`docs/decisions.md`](docs/decisions.md).
- Summary model allow-list and dropdown, policy chosen by the request, and why the policy lookup is not RAG: [engineering decisions](docs/decisions.md#engineering-decisions).

## Hours

The plan's budget per phase and the git timestamps are in [`docs/provenance.md#hours`](docs/provenance.md#hours). Mapped to the numbered items:

| Item | Plan budget | Notes |
|---|---|---|
| 0 Requirements Analysis and Research | 4 h | Phase 0 |
| 1 FHIR and load | 0.5 h | Phases 0 and 1 |
| 2 Endpoint and rules | 0.5 h | Phase 2 |
| 3 MCP and agent | 0.5 h | Phase 6 |
| 4 Safety | 0.5 h | Phase 4 |
| 5 Evaluation | 1.5 h | Phase 5, plus three runs of the 7B measurement |
| 6 Plan | part of 1 h | Phase 9 |
| 7 Security notes | part of 0.75 h | Phase 9 |
| 8 Enterprise minimum | 2 h | Phase 3 |
| Nurse page, CI | 0.75 h | Phases 7 and 8 |

The hours are spent the most to understand the context of the requirements, who is the audience, what outcome does this system try to achieve, the current workflow, what does the end user want to see.

## Provenance

Claude Code (Claude Opus 5.5) wrote the code, tests, and docs under the repository owner's direction. The owner set the plan's decisions and reviewed the result. Every commit carries a `Co-Authored-By` trailer. The data pack and the Synthea sample are third-party synthetic data. Details and how the work was checked: [`docs/provenance.md`](docs/provenance.md).

## Document index

| Document | What it covers |
|---|---|
| [`docs/runbook.md`](docs/runbook.md) | Run the stack, call every endpoint, run every check |
| [`docs/payer-a-plan.md`](docs/payer-a-plan.md) | Item 6: week one, week six, needs, cut list |
| [`docs/security.md`](docs/security.md) | Item 7 in depth: injection, auth, audit limits, log contents, open threats |
| [`docs/evaluation.md`](docs/evaluation.md) | Item 5: results, hand audit, findings, model measurements |
| [`docs/decisions.md`](docs/decisions.md) | Policy interpretation and engineering decisions |
| [`docs/dataflow.md`](docs/dataflow.md) | Data-flow diagrams |
| [`docs/plan.md`](docs/plan.md) | What changed from the implementation plan |
| [`docs/provenance.md`](docs/provenance.md) | Who wrote what, how it was checked, hours |
| [`implementation-plan.md`](implementation-plan.md) | The original plan: decisions D1 to D9, rules spec, build order |

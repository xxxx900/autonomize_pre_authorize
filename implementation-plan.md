# Implementation Plan — Prior Authorization Evidence Packet (FDE Assignment v2)

Status: draft for review · Time box: 8 hours total (report actual hours per item)

## 1. Goal in one paragraph

Build a service that, for a GLP-1 prior authorization request, reads the request form, pulls the
member's FHIR record, and returns an evidence packet: per policy criterion a status
(`met` / `not_met` / `missing` / `conflicting`), the FHIR sources behind it, what documents to ask
the provider for, and a two-sentence summary. It never recommends or decides. The MVP runs as one
Docker Compose stack on a local Windows machine (Docker Desktop on WSL2). GitHub Actions runs lint,
tests and the 7-case eval on every push. Azure deployment is deferred until after the MVP.

## 2. Key design decisions

| # | Decision | Why |
|---|---|---|
| D1 | **Criterion statuses are computed by deterministic Python rules**, driven by the policy JSON. | Reproducible, testable, auditable. A 3–4B model should not decide whether 6.4 ≥ 7.0. |
| D2 | **The local model writes only the summary**, from the computed packet (never the raw chart). | Limits what the model can get wrong; makes faithfulness checkable. |
| D3 | **The agent is a second front door** (MCP client) to the same rules; the endpoint does not call the agent. | One source of truth for statuses; the endpoint stays fast and deterministic; the agent demonstrates tool use without being on the critical path. |
| D4 | **Free-text fields are never parsed** (`Condition.note`, `DocumentReference` attachments, form `notes`), so they cannot reach the packet or the model. Documents are listed by reference and flagged, not interpreted. | Defeats the PA-006 injection (OWASP LLM01) by construction. PA-006 carries the same injected text twice: plain in `Condition.note` and base64 in the H&P `DocumentReference`. |
| D5 | **Only structured form fields can create a `conflicting` status** (numbers, dates, codes). | Free text cannot be compared to a record reliably. |
| D6 | **Static token map for auth** (`nurse`, `admin`); production replacement is Entra ID OIDC with group→role mapping. | Allowed by the brief; 15 minutes instead of 2 hours. Issuing and validating our own tokens would need an issuer and a credential store, which an identity provider supplies later. Auth sits behind one `RoleGuard` dependency, so the swap changes how a bearer token maps to a role, not the routes. |
| D7 | **SQLite append-only audit store with a hash chain**; production: managed DB + daily anchoring of chain hashes to immutable Blob storage. | Tamper-evident with minimal infrastructure. |
| D8 | **MVP runs locally in Docker; every command runs in a container** (tests, eval, loader). The host needs only Docker Desktop and git. | One environment for dev, CI and later Azure; no host Python to drift. Azure becomes a Compose override later. |
| D9 | **Rules are pure functions over a parsed `PatientRecord`**, not over HTTP calls. `fhir_client` parses FHIR JSON into the record at the boundary. | Tests run against the supplied bundles directly, without a FHIR server. |

## 3. Architecture

```
Windows host (Docker Desktop / WSL2) ──▶ docker compose up
GitHub push ──▶ Actions: lint + tests + 7-case eval        (deploy deferred)

Docker Compose network
  hapi         hapiproject/hapi:<pinned>      :8080/fhir   FHIR R4 server, no volume (reloaded each start)
  loader       python (one-shot)              waits for /fhir/metadata, loads bundles idempotently
  ollama       ollama/ollama:<pinned>         :11434       local model; named volume for /root/.ollama
  ollama-pull  ollama/ollama (one-shot)       pulls the pinned model tags once into the volume
  api          FastAPI                        :8000        evidence endpoint, auth, audit, /health, /ready, web page
  mcp          FastMCP (same rule functions)  stdio/http   tools: get_evidence_packet, get_policy
```

Loader idempotency: supplied bundles already use `PUT Type/<id>`. Synthea bundles use `POST` with
`urn:uuid:` fullUrls; the loader rewrites each entry to `PUT Type/<uuid>` and rewrites references
to `Type/<uuid>`, so reloading converges to the same resources.

Request flow for `GET /requests/{id}/evidence`:
1. Auth: token → role; refuse + audit if missing/wrong.
2. Load request form → member reference → FHIR searches (Patient, Condition, Observation,
   MedicationRequest, AllergyIntolerance, DocumentReference).
3. Rules engine evaluates C1–C5 against the policy, then applies attestation comparison.
4. Build packet (Pydantic), compute `route`.
5. Summary: model gets the packet facts inside `<evidence>` tags + a stated rule; output validated
   by Pydantic, checked for faithfulness and forbidden words; template fallback if it fails.
6. Verify every cited source exists in FHIR (GET by id).
7. Write one audit event (no clinical values); log request id + timings only; return packet.

## 4. Repository layout

```
autonomize_pre_authorize/
  docker-compose.yml          Dockerfile                 .gitattributes (LF for *.sh)
  pyproject.toml              .env.example               README.md
  resources/                  supplied pack (synthetic), kept as delivered + synthea/ (fetched by script)
  scripts/  load_fhir.py  fetch_synthea.sh
  app/
    main.py        routes: /requests/{id}/evidence, /policy, /audit, /health, /ready, /
    config.py      pydantic-settings: every env var, documented in .env.example
    auth.py        token map → role; dependency that audits refusals
    fhir_client.py httpx; none | bearer | SMART client-credentials, by env var
    policy.py      loads policy JSON into models
    rules/         c1_diagnosis.py c2_hba1c.py c3_metformin.py c4_exclusions.py c5_age.py
                   attestation.py (conflict logic)  engine.py
    packet.py      Pydantic: CriterionResult, EvidencePacket (route enum)
    summary.py     prompt (versioned), Ollama structured output, faithfulness check, fallback
    safety.py      forbidden-word check, source-existence check
    audit.py       SQLite append-only + hash chain
    logs.py        JSON logs, allow-list of fields
    web/index.html read-only nurse worksheet
  mcp_server/server.py   agent/agent.py (ReAct loop over MCP tools)
  eval/  run_eval.py  synthea_requests/*.json  results/
  tests/ test_rules.py (7 expected outcomes) test_auth.py test_safety.py test_audit.py
  .github/workflows/  ci.yml
  docs/  plan.md  security.md  evaluation.md  decisions.md  dataflow.md (Mermaid)  provenance.md
```

## 5. Rules specification (request date from the form, never "today")

| Criterion | met | not_met | missing | conflicting (structured form field) |
|---|---|---|---|---|
| C1 Active T2DM | Condition 44054006 (or descendant), clinicalStatus active/recurrence/relapse | Present but resolved/inactive | No T2DM Condition | Form claims T2DM but the record codes a *different* diabetes type (e.g. type 1) |
| C2 HbA1c ≥ 7.0 within 90 days | Latest LOINC 4548-4 in window ≥ 7.0 | Latest in window < 7.0 | None in window | `hba1c_value`/`hba1c_date` disagree with a record result on that date |
| C3 Metformin | ≥ 90 days of RxNorm 6809 therapy in 12 months before request (authoredOn → validity end, or request date if active), OR metformin AllergyIntolerance, OR eGFR < 30 | Evidence of < 90 days and no intolerance/contraindication | No metformin record at all | `metformin_trial_months` exceeds record-supported months by > 1 |
| C4 Exclusions | No pancreatitis / MTC / MEN2 Condition, any status | Any such Condition, including resolved | (n/a: absence = met; noted as a design choice) | — |
| C5 Age ≥ 18 | birthDate → age ≥ 18 on request date | < 18 | No birthDate | — |

`route = evidence_complete` only if all five are `met`; otherwise `clinician_review`.

C3 has two different durations. The ≥ 90-day test uses therapy days *clipped* to the 12-month
window. The attestation check compares `metformin_trial_months` against the *full, unclipped*
therapy duration (days / 30.44). Using the clipped value would wrongly flip PA-001 to
`conflicting` (form 14 months vs ≈ 12 clipped; ≈ 14.6 full).

Code matching: no terminology service in the MVP, so "or descendant" is matched on the exact
listed code, or on the ingredient/display as the policy note allows.

### Expected outcomes for the seven supplied requests (become `tests/test_rules.py`)

| Request | C1 | C2 | C3 | C4 | C5 | Route | Note |
|---|---|---|---|---|---|---|---|
| PA-001 | met | met | met | met | met | evidence_complete | The one complete case |
| PA-002 | met | **missing** | met | met | met | clinician_review | Ask for HbA1c dated ≥ 2026-07-03 |
| PA-003 | met | met | **not_met** | met | met | clinician_review | 35 days of metformin |
| PA-004 | met | met | **conflicting** | met | met | clinician_review | Form 6 months vs record 21 days; intolerance documented |
| PA-005 | met | met | met | **not_met** | met | clinician_review | Resolved pancreatitis counts as history |
| PA-006 | met | **conflicting** | met | met | met | clinician_review | Form 7.8% vs record 6.4%; note with embedded instructions flagged, not used |
| PA-007 | **not_met** | met | met | met | met | clinician_review | T2DM coded resolved; implausible with current A1c + metformin |

Open interpretation points are documented with reasoning and sources in docs/decisions.md.

## 6. Build order and hour budget

Ordered by what the brief scores highest, so the most valuable parts exist even if time runs out.

| Phase | Work | Budget | Done when |
|---|---|---|---|
| 0 | WSL2 + Docker Desktop on the Windows host, git repo, GitHub remote | 0.25 h | `docker compose up` runs locally |
| 1 | FHIR server + idempotent loader (supplied bundles + Synthea sample) | 0.75 h | Load twice → resource counts unchanged |
| 2 | Rules engine + evidence endpoint + packet model | 1.5 h | All 7 expected outcomes pass in tests |
| 3 | Enterprise minimum: auth, audit, PHI-free logs, FHIR auth by env, /health, /ready, pinned versions | 1.25 h | Refused call audited; audit event returned to admin; log line shown |
| 4 | Safety + summary: tags, Pydantic, source check, faithfulness, forbidden words | 0.5 h | Bad model output is caught and falls back; PA-006 unchanged |
| 5 | Evaluation: 7 requests + 10 Synthea requests, hand audit, model measurements | 1.5 h | docs/evaluation.md with per-criterion table and findings |
| 6 | MCP tools + agent | 0.75 h | Agent produces the same packet as the endpoint via tool calls |
| 7 | Read-only nurse page | 0.5 h | Worksheet renders any packet; conflicts side by side |
| 8 | CI: lint + tests + 7-case eval on push (no deploy) | 0.25 h | Green run on GitHub |
| 9 | Docs: README, plan, security notes, diagram, provenance, hours | 0.75 h | Every numbered item delivered or declined with reason |
|   | **Total** | **≈ 7.75 h** | |

Deferred until after the MVP: Azure VM, Caddy/HTTPS, image push to GHCR, deploy workflow.

Cut order if behind: web page → agent polish (keep minimal agent) → Synthea count.

## 7. Model selection

Candidates: `qwen2.5:3b` and `llama3.2:3b` (pinned tags), CPU only, structured output.
Measure on the 7 packets × 5 runs: valid-schema rate, faithfulness-check pass rate, forbidden-word
hits, median latency. Pick on faithfulness first, latency second. Record in docs/evaluation.md.

## 8. Environment and costs

- Local host: Windows 11 Home, Ryzen 7 7800X3D (8C/16T), 32 GB RAM. Needs WSL2 + Docker Desktop.
  CPU inference for a 3B model is comfortable here. Cost: $0.
- GitHub Actions: free tier.
- Secrets: `.env` on the host only (git-ignored); nothing in the repo.
- Later (Azure): Standard_B4ms (4 vCPU, 16 GB), ≈ $0.17/h while running.

## 9. Risks

| Risk | Mitigation |
|---|---|
| HAPI memory with large Synthea bundles | Use a small Synthea sample; set JAVA_TOOL_OPTIONS; 16 GB VM |
| Slow CPU inference | 3B model, short output, warm-up call on start; template fallback |
| Synthea has few T2DM patients | Choose 10 patients deliberately (mix of diabetic and non-diabetic) and say so |
| Time overrun | Strict build order; cut list above; time log per phase |
| Panel asks about AI-written code | Provenance table; read every file before the panel |

## 10. Decisions

Resolved (2026-11-05):
- Claude creates the repo and commits as it goes. HAPI reloads on every start (no volume).
- CI stays in the MVP; Azure deploy is deferred.
- Interpretation calls stay as written in §5 (PA-007 not_met; PA-004 conflicting; C4 absence = met).

Open:
1. GitHub account/repo name for the remote (needs `gh` or a token on the host).
2. Synthea sample choice and the assumed request date for the 10 extra requests (evaluation phase).

# Plan for Payer A

One page: what ships in week one and by week six, what Payer A must provide, and what this MVP cut and why. Hours are in [provenance](provenance.md#hours).

## Week one: the MVP in Payer A's environment, read-only, synthetic data first

The goal for week one is that a UM nurse opens a real packet for a test member in Payer A's non-production environment and checks every line against the chart.

| Day | Ships | Done when |
|---|---|---|
| 1 | The compose stack on a Payer A VM inside their network, pointed at their non-production FHIR endpoint with `FHIR_AUTH_MODE=smart` | `GET /ready` is 200 against their FHIR server |
| 2 | The seven supplied requests and the 17-case eval rerun in their environment | `scripts/check_seven` and `run-eval` match the committed results |
| 3 | Code-system check on their data: their HbA1c LOINC, metformin RxNorm, and T2DM SNOMED codes compared with the policy's lists | A short list of codes the policy misses, which goes to the policy owner rather than into code |
| 4 | Five to ten of their test members, run and audited by hand with a nurse | A findings list in the shape of [the evaluation](evaluation.md#findings) |
| 5 | Nurse walkthrough on the worksheet, and a security review of the audit trail and log lines | Sign-off on the packet shape, or a change list |

Week one keeps the demo controls: static tokens, SQLite audit, and no TLS inside a private network segment. The service reads only from FHIR, and it makes no authorization decision.

## By week six: production controls

| Area | What ships |
|---|---|
| TLS and networking | TLS terminates at Payer A's ingress (or a Caddy sidecar). The API, MCP server, Ollama, and FHIR traffic stay on a private network with no public route. Ollama gets no ingress at all. |
| Identity | Entra ID (or Payer A's IdP) OIDC replaces the static token map. IdP groups map to `nurse` and `admin`, so the audit trail names a person instead of a role. The MCP server takes a client-credentials token instead of `MCP_TOKEN`. |
| Audit store | A managed Postgres table with the same hash chain. The chain head is anchored daily to immutable (WORM) storage, which closes the tail-deletion and full-rewrite gaps in [security notes](security.md#audit-log-and-its-limits). Retention follows Payer A's policy (HIPAA documentation rules suggest six years), with a legal-hold flag that suspends deletion. |
| SIEM | Audit events and JSON log lines ship to Payer A's SIEM (for example Sentinel or Splunk) over their standard forwarder. Refusals (`unauthenticated`, `forbidden`) raise alerts. |
| Encryption at rest | Managed-disk encryption for the VM, plus encryption on the audit database and its backups, with keys in Payer A's key vault. |
| Backup and restore | Nightly audit-store backup and a restore test that ends with `GET /audit` reporting `chain.valid`. |
| Model | The summary model pinned by digest, not by tag. Pick between `llama3.2:3b` and `qwen2.5:7b` from [the measurements](evaluation.md#summary-model-measurements) and the hardware Payer A provides. |
| Operations | `/health/details` wired into their monitoring, plus rate limits and a runbook for "FHIR down" (packets return 502 and the audit records it) and "model down" (template summary). |

**BAA scope.** Every component that touches member data sits inside Payer A's environment and their BAA: the API, the MCP server, the audit store, the FHIR server, and Ollama, because the summary prompt holds packet facts. Logs carry no PHI by construction ([`app/ops/logs.py`](../app/ops/logs.py)), but they still go to a SIEM inside the BAA. No external model provider is used, so no third-party BAA is needed. The trade-off is in [the README](../README.md#7-security-notes-owasp-llm01-and-llm02).

## What we need from Payer A

1. A non-production FHIR R4 endpoint and SMART Backend Services client credentials scoped to `system/*.read`.
2. The real policy text, and an owner who can answer coding questions such as descendant codes for C4 and how to treat stopped prescriptions without an end date ([decisions](decisions.md)).
3. Two or three UM nurses for one hour in week one and one hour in week six.
4. An IdP app registration with two groups, a VM (8 vCPU, 16 GB RAM is enough for a 3B model on CPU), and their SIEM and backup targets.
5. Their audit retention period and legal-hold procedure.

## What this assignment cut, and why

| Cut | Why |
|---|---|
| OIDC or JWT auth | The brief allows a static token map. OIDC needs Payer A's IdP, which is a week-six item. |
| TLS, private networking, encryption at rest, backup | These depend on Payer A's infrastructure. The stack runs on localhost only. |
| External anchoring of the audit chain | The hash chain plus append-only triggers catch edits and mid-chain deletes. Anchoring needs storage outside the demo. |
| A terminology service (descendant codes) | Exact code matching is predictable and testable. The risk is written down in [decisions](decisions.md#codes-match-exactly-without-a-terminology-service). |
| Reading free text (notes, attachments) | This is deliberate, not time-driven. Free text is the PA-006 injection path (D4). |
| More than one policy | Rules are typed to MP-SYN-021's five criteria. See [decisions](decisions.md#the-policy-is-chosen-by-the-request-not-a-dropdown). |
| Cloud deployment (Azure VM, image registry) | It is not needed to show the service working, and it is the first thing in week one. |
| Rate limiting, token rotation | These belong with the IdP work in week six. |

# Runbook

How to start the stack, call every endpoint, and run every check. All commands run in containers, so the host needs only Docker Desktop and git.

## Start the stack

1. Copy the environment file and set your own tokens:

	```sh
	cp .env.example .env
	```

	`NURSE_TOKEN`, `ADMIN_TOKEN`, and `MCP_TOKEN` are required, and the nurse and admin tokens must differ. `.env.example` documents every variable.

2. Start everything with one command:

	```sh
	docker compose up -d --build
	```

	The first start pulls the HAPI and Ollama images and the two pinned 3B models (about 4 GB). The loader then loads every bundle into HAPI. HAPI has no volume, so the loader runs again on every start.

3. Wait until the API reports ready:

	```sh
	curl http://localhost:8000/ready
	```

## Browser pages

| Page | Who | What |
|---|---|---|
| http://localhost:8000/ | nurse or admin token | The worksheet. Pick a request and a summary model, then read each criterion with its policy clause, FHIR fields, and links to the resources on HAPI. |
| http://localhost:8000/audit/view | admin token | The audit log as a table, newest first, with the hash-chain result. Filter by request id, resource, action, or outcome. Click a row to see its full context and hashes. The worksheet's trace card links here for each packet. |
| http://localhost:8000/docs | anyone | The OpenAPI reference for every endpoint. |

## Call the API

Every endpoint except `/health`, `/ready`, and the pages needs a bearer token. JSON responses are indented, so curl output is readable without `jq`.

| Endpoint | Role | What it returns |
|---|---|---|
| `GET /requests/{id}/evidence[?summary_model=]` | nurse, admin | The evidence packet |
| `GET /catalog` | nurse, admin | Request ids on disk and the allowed summary models |
| `GET /policy` | nurse, admin | The loaded policy with its file hash |
| `GET /audit?request_id=&resource=&action=&actor=&outcome=&limit=` | admin | Hash-chain check plus matching rows |
| `GET /health` | none | Liveness: `{"status": "ok"}` |
| `GET /ready` | none | Readiness of the required components; 503 when one is down |
| `GET /health/details` | admin | Every component probed, with versions and latencies |

```sh
curl -H "Authorization: Bearer $NURSE_TOKEN" http://localhost:8000/requests/PA-004/evidence
curl -H "Authorization: Bearer $NURSE_TOKEN" "http://localhost:8000/requests/PA-004/evidence?summary_model=qwen2.5:3b-instruct-q4_K_M"
curl -i http://localhost:8000/requests/PA-004/evidence               # 401, and the refusal is audited
curl -H "Authorization: Bearer $ADMIN_TOKEN" "http://localhost:8000/audit?request_id=<X-Request-ID>"
```

Every response carries an `X-Request-ID` header. The packet's `trace.trace_id`, the audit row's `request_id`, and the log line's `request_id` hold the same value.

## Engineer health check

`GET /health/details` (admin) probes each dependency and returns indented JSON:

```sh
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/health/details
```

| Component | Required | What is checked | Facts reported |
|---|---|---|---|
| `fhir` | yes | FHIR `metadata` answers | FHIR version, server software and version |
| `audit_log` | yes | A write transaction opens, and the whole hash chain verifies | Rows checked |
| `policy` | yes | The loaded policy still matches the file on disk | Policy id, version, SHA-256 |
| `request_store` | yes | The request directories exist | Form count |
| `summary_model` | no | Ollama answers, and every allowed model is pulled | Ollama version, default model, digest, loaded in memory, allowed models, any not pulled |
| `mcp` | no | The MCP server's `/health` answers | |

`state` is `down` when a required component is down, `degraded` when anything else is not up, and `up` otherwise. A degraded service still serves packets; a missing model means a template summary. Docker marks the `api` and `mcp` containers healthy from the same probes.

## Pick a model

- **Summary model:** `SUMMARY_MODEL` sets the default, and `SUMMARY_MODEL_CHOICES` (comma separated) adds the models a nurse may pick in the worksheet. Each must also be in `OLLAMA_PULL_MODELS`. Restart with `docker compose up -d` after editing `.env`.
- **Agent model:** `AGENT_MODEL`, or `--model` for one run.
- **Policy:** `POLICY_FILE` loads a re-versioned copy of the policy at start. The request form names its policy, so the policy has no dropdown. See [decisions](decisions.md#the-policy-is-chosen-by-the-request-not-a-dropdown).

## Run the checks

Lint and unit tests:

```sh
docker compose --profile test run --rm --build test
```

The seven supplied requests against the expected outcomes, with the stack running:

```sh
docker compose run --rm --no-deps -e API_URL=http://api:8000 api python -m scripts.check_seven
```

The 17-case evaluation (seven supplied plus ten Synthea requests):

```sh
docker compose --profile synthea run --rm --build fetch-synthea   # pinned Synthea sample
docker compose up -d --build                                       # reload HAPI with it
docker compose --profile eval run --rm --build run-eval            # writes eval/results/eval.{json,md}
```

The agent, and the agent compared with the endpoint for all seven requests:

```sh
docker compose --profile agent run --rm agent python -m agent.agent PA-006
docker compose --profile agent run --rm agent python -m agent.agent PA-006 --model qwen2.5:7b-instruct-q4_K_M
docker compose --profile agent run --rm -e API_URL=http://api:8000 -e NURSE_TOKEN=<nurse token> agent python -m scripts.check_agent
```

Summary model measurements (`MEASURE_OUTPUT` names the result files in `eval/results/`):

```sh
MEASURE_MODELS="llama3.2:3b-instruct-q4_K_M" MEASURE_OUTPUT=models docker compose --profile eval run --rm measure
```

## Configure

`.env.example` lists every variable with a comment. The host ports (`API_HOST_PORT`, `HAPI_HOST_PORT`, `OLLAMA_HOST_PORT`, `MCP_HOST_PORT`) let a second copy of the stack run beside the first. `FHIR_AUTH_MODE` switches FHIR access between no auth (local HAPI), a static bearer token, and SMART Backend Services client credentials.

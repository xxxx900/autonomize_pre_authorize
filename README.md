# PA evidence packet service

This service assembles evidence for a GLP-1 prior-authorization request. It reads the request form, pulls the member's FHIR R4 record, and returns an evidence packet. The packet gives each policy criterion a status (`met`, `not_met`, `missing`, or `conflicting`), the FHIR resources behind that status, the documents to ask the provider for, and a two-sentence summary.

The service never decides. It does not approve, deny, or recommend. The only routing it computes is `evidence_complete` (all five criteria `met`) or `clinician_review` (anything else), and a licensed clinician makes every determination. Deterministic Python rules compute the statuses. A local language model writes only the summary, from the finished packet. If that summary states a status, number, or date that is not in the packet, or uses a word such as "approve" or "should", the service discards it and serves a template summary.

The whole stack runs locally in Docker Compose: HAPI FHIR, a one-shot loader, Ollama, the FastAPI service, and an MCP server for agents.

## Run the stack

You need Docker Desktop and git. Every command runs in a container, so the host needs no Python.

1. Copy the environment file and set your own tokens:

	```sh
	cp .env.example .env
	```

	`NURSE_TOKEN`, `ADMIN_TOKEN`, and `MCP_TOKEN` are required, and the nurse and admin tokens must differ.

2. Start the stack:

	```sh
	docker compose up -d --build
	```

	The first start pulls the HAPI and Ollama images and the two pinned 3B models (about 4 GB). The loader then loads every bundle into HAPI. HAPI has no volume, so the loader runs again on every start.

3. Wait until the API reports ready:

	```sh
	curl http://localhost:8000/ready
	```

	The response is `{"status":"ready"}` once HAPI answers.

4. Open the nurse worksheet at http://localhost:8000, enter the nurse token, and load a request such as `PA-006`.

## Call the API

Every call needs a bearer token. Replace `$NURSE_TOKEN` and `$ADMIN_TOKEN` with the values from your `.env`.

Get the evidence packet for a request:

```sh
curl -H "Authorization: Bearer $NURSE_TOKEN" http://localhost:8000/requests/PA-004/evidence
```

Get the policy the criteria come from:

```sh
curl -H "Authorization: Bearer $NURSE_TOKEN" http://localhost:8000/policy
```

Read the audit log and its hash-chain check (admin only):

```sh
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/audit
```

A call without a valid token returns 401, and the refusal is written to the audit log:

```sh
curl -i http://localhost:8000/requests/PA-001/evidence
```

`GET /health` reports that the process is up. `GET /ready` also checks that HAPI answers.

## Run the checks

Run lint and the unit tests:

```sh
docker compose --profile test run --rm --build test
```

Check the seven supplied requests against the expected outcomes in `implementation-plan.md` section 5, with the stack running:

```sh
docker compose run --rm --no-deps -e API_URL=http://api:8000 api python -m scripts.check_seven
```

Run the 17-case evaluation (the seven supplied requests plus ten Synthea requests):

1. Fetch the pinned Synthea sample into `resources/synthea/`:

	```sh
	docker compose --profile synthea run --rm --build fetch-synthea
	```

2. Rebuild and restart the stack, so the loader image holds the Synthea bundles:

	```sh
	docker compose up -d --build
	```

3. Run the evaluation. It writes `eval/results/eval.json` and `eval/results/eval.md`:

	```sh
	docker compose --profile eval run --rm --build run-eval
	```

Ask the agent about a request. The agent calls the MCP server, which runs the same pipeline as the API:

```sh
docker compose --profile agent run --rm agent python -m agent.agent PA-006
```

Compare the agent's packet with the endpoint's packet for all seven supplied requests:

```sh
docker compose --profile agent run --rm -e API_URL=http://api:8000 -e NURSE_TOKEN=<your nurse token> agent python -m scripts.check_agent
```

Measure candidate summary models on the seven packets. `MEASURE_OUTPUT` names the result files in `eval/results/`:

```sh
MEASURE_MODELS="llama3.2:3b-instruct-q4_K_M" MEASURE_OUTPUT=models docker compose --profile eval run --rm measure
```

## Configure

`.env.example` lists every variable the stack reads, with a comment for each. The host ports (`API_HOST_PORT`, `HAPI_HOST_PORT`, `OLLAMA_HOST_PORT`, `MCP_HOST_PORT`) let you run a second copy of the stack next to the first. `SUMMARY_MODEL` picks the summary model, and `FHIR_AUTH_MODE` switches the API between no auth, a static bearer token, and SMART client credentials when you point it at another FHIR server.

## Read more

- [Plan and what changed](docs/plan.md)
- [Security notes](docs/security.md)
- [Evaluation results](docs/evaluation.md)
- [Interpretation decisions](docs/decisions.md)
- [Data flow diagrams](docs/dataflow.md)
- [Provenance and hours](docs/provenance.md)

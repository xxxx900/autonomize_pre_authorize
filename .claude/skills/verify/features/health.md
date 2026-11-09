# Health and readiness

Operators and engineers check the service three ways: liveness (`/health`, process up), readiness (`/ready`, required components only, 503 when one is down), and the admin component report (`/health/details`) that probes FHIR, the audit chain, the policy file, the request store, every allowed summary model, and the MCP server, as indented JSON.

## Sub-features

- `health-live` returns `{"status": "ok"}` without a token.
- `health-ready` lists `fhir`, `audit_log`, `policy`, `request_store`; 503 when a required one is down.
- `health-details` returns overall `state`, uptime, and per-component state, latency, detail, and facts (FHIR version, Ollama version, model digest, allowed models not pulled, chain rows checked, policy sha256, form count).
- `health-degrade` keeps `/ready` 200 when only optional components (model, MCP) are down.

## How to get to it (user POV)

- `curl http://localhost:18000/health` and `/ready`.
- `curl -H "Authorization: Bearer <admin>" http://localhost:18000/health/details`.

## Driving it with pa-verify

Preconditions:

- Baseline from the index.

- **Liveness.** Run `$V get none /health live`. 200 and body `{"status": "ok"}`, indented.
- **Readiness.** Run `$V get none /ready ready` then `$V json ready "d"`. 200, `status` `ready`, four components `up`.
- **Details.** Run `$V get admin /health/details details` then `$V json details "[d['state'], {c['component']: (c['state'], c['facts']) for c in d['components']}]"`. `state` `up`; `fhir` facts name `HAPI FHIR Server 8.12.0`; `summary_model` facts list `allowed_models` and an empty `allowed_not_pulled`; `mcp` `up`.
- **Optional component down.** Run `$V compose stop mcp`, then `$V get admin /health/details details-nomcp` and `$V get none /ready ready-nomcp`. Details `state` `degraded` with `mcp` `degraded`; `/ready` still 200. Restore with `$V compose start mcp`.
- **Required component down.** Run `$V compose stop hapi`, then `$V get none /ready ready-nofhir`. 503 with `fhir` `down`. Restore with `$V compose start hapi`, reload data with `$V compose run --rm loader` (HAPI has no volume), then `$V doctor`.

## Gotchas

- `/health/details` is admin-only by design; a nurse gets 403.
- After restarting `hapi` the data is gone until the loader runs again; packets return 404 until then.
- `summary_model` `degraded` with detail "an allowed model is not pulled" means a `SUMMARY_MODEL_CHOICES` entry is missing from the Ollama volume, not that the default model is broken.

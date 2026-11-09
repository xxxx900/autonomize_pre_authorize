# Summary model choice

A nurse can pick which local model writes the packet summary from an allow-list the operator sets (`SUMMARY_MODEL` default plus `SUMMARY_MODEL_CHOICES`). The choice is recorded in the packet and the audit row, any name outside the list is refused and audited, and every model's output passes the same safety checks or is replaced by the template.

## Sub-features

- `catalog-list` returns the request ids on disk and the summary models, default first.
- `model-pick` uses the picked model and records it in `trace.summary.model` and the audit row.
- `model-refuse` returns 422 for a model outside the allow-list and audits it.
- `model-dropdown` fills the worksheet's `Summary model` select from the catalog.

## How to get to it (user POV)

- `GET /catalog` with a nurse or admin token.
- `GET /requests/{id}/evidence?summary_model=<tag>`.
- The worksheet's `Summary model` dropdown (id `model`), filled once a token is entered.

## Driving it with pa-verify

Preconditions:

- Baseline from the index. Compose defaults give default `llama3.2:3b-instruct-q4_K_M` and choice `qwen2.5:3b-instruct-q4_K_M`, both pulled.

- **Catalog.** Run `$V get nurse /catalog catalog` then `$V json catalog "[len(d['request_ids']), d['summary_models']]"`. 17 ids (7 PA and 10 SYN forms), default llama3.2, choices llama3.2 then qwen2.5.
- **Pick a model.** Run `$V get nurse "/requests/PA-003/evidence?summary_model=qwen2.5:3b-instruct-q4_K_M" pick` then `$V json pick "d['trace']['summary']"`. `model` is `qwen2.5:3b-instruct-q4_K_M`; `source` is `model`, or `template` with a `fallback` reason. Either is correct; the proof is the recorded model.
- **Recorded in audit.** With the `x-request-id` from `pick`, run `$V get admin "/audit?request_id=<id>" pick-audit` then `$V json pick-audit "d['events'][0]['context']['summary']['model']"`. The same model name.
- **Refuse unknown model.** Run `$V get nurse "/requests/PA-003/evidence?summary_model=evil:70b" refuse`. 422, and the detail names GET /catalog. With its `x-request-id`, the audit row has outcome `error` and `context.status_code` 422.
- **Dropdown.** With claude-in-chrome on `http://localhost:18000/`, fill `token` with the nurse token and leave the field; the `model` select lists both tags with `(default)` on llama3.2, and the `picker` select lists 17 ids.

## Gotchas

- qwen2.5:3b usually falls back with `bad_output` (see `docs/evaluation.md` measurements); a template fallback is not a failure of model choice.
- Changing the allow-list means editing `SUMMARY_MODEL_CHOICES` in `.verify/runs/<run>/verify.env` and running `$V compose up -d api mcp`; the model must also be pulled into `pa-verify_ollama-data`.
- The MCP tool takes no model. The agent's own model is `--model` on `$V agent`, which is separate from the summary model.

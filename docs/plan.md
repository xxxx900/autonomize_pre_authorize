# Plan and what changed

The plan is [`implementation-plan.md`](../implementation-plan.md) at the repository root. It holds the goal, design decisions D1 to D9, the rules table, the expected outcomes for the seven supplied requests, and the build order. This page lists where the build differs from that plan and why. Each item names the commit that made the change, so `git show <hash>` gives the full reasoning.

## Design decisions that held

D1 to D9 hold as written. Deterministic rules compute every status (D1). The model sees only the finished packet (D2). The agent is a second front door and the endpoint never calls it (D3). No free-text field is parsed (D4). Only structured form fields create `conflicting` (D5). Auth is a static token map (D6). The audit log is SQLite with a hash chain (D7). Every command runs in a container (D8). Rules are pure functions over a parsed `PatientRecord` (D9).

## Changes to the code layout

- The rules live in one module, `app/rules.py`, with a `CRITERIA` registry that maps `C1` to `C5` to their functions. The plan sketched a package with one file per criterion. One file keeps the shared helpers, such as `_latest` and `_covered_days`, next to their callers.
- `app/record.py` holds the parsed record and request form. `app/fhir_client.py` turns FHIR JSON into that record at the boundary, as D9 requires.
- `app/pipeline.py` holds `PipelineError`, and `create_app` exposes one `build_packet` function that the API route and the MCP tool both call (979294a). The two front doors cannot drift apart because they share one function.
- Cited-source verification moved from a planned `app/sources.py` into `app/safety.py`, next to the forbidden-word and faithfulness checks (042bd35).

## Changes to behavior

- **Metformin days are a union of intervals** (ec14d96). Overlapping or duplicate prescriptions count once, and back-to-back renewals count as one trial.
- **D4 names every free-text field PA-006 uses** (4ac45ac). The first draft said only that free-text notes never reach the model. The revision says that `Condition.note`, `DocumentReference` attachments, and the form `notes` field are never parsed, because PA-006 carries the same injected text in two of them.
- **The packet says where its summary came from.** `summary_source` is `model` or `template`, and `summary_prompt_version` names the prompt that produced a model summary (191150d). A reviewer can tell a model sentence from a template sentence.
- **The faithfulness check reads status claims** (c966f67, cb5f1d7). The plan checked numbers, dates, and forbidden words. The 3B models also called met criteria unmet without any wrong number, so the check now maps each criterion id to the status words in its clause and rejects a claim that differs from the packet. It also requires exactly one sentence per entry.
- **A metformin attestation is compared only when every prescription has a known end** (9cbd356). The Synthea evaluation found that a stopped prescription with no end date counted as zero days and produced a false `conflicting`. See [the evaluation](evaluation.md#findings).
- **The summary model loads on API start** (21e6c49), as plan section 9 proposed. A background thread sends Ollama an empty request, so the first evidence request does not wait for the model to load.
- **A refused MCP request is audited** (c28be12), with the new action `mcp.request`. Refused API requests were already audited.

## Changes to the stack

- **The MCP server speaks streamable HTTP, not stdio** (2677278). The agent runs in its own container, so it needs a network transport. A `BearerGate` in front of the server requires `MCP_TOKEN`.
- **The `mcp` package is pinned to `>=1.12,<2`** in `pyproject.toml`, and `uv.lock` fixes the exact version at 1.30.0. The agent imports `streamable_http_client` from the 1.x client package. The git history records the pin but not a reason for it.
- **Ollama and the model pull are compose services** (6d52fae). `ollama-pull` fetches the pinned tags into a named volume once. The API reaches Ollama inside the compose network.
- **The default summary model is `llama3.2:3b-instruct-q4_K_M`.** Plan section 7 says to pick on faithfulness first. llama3.2 passed the faithfulness check on 3 of 7 packets and qwen2.5 3B on none (cb5f1d7). [The evaluation](evaluation.md#summary-model-measurements) also measures `qwen2.5:7b-instruct-q4_K_M`.
- **Synthea comes from a pinned archive.** `scripts/fetch_synthea.py` downloads the nov2021 R4 sample, checks its sha256, and copies two shared bundles and ten chosen patients into `resources/synthea/`, which git ignores (f886e2c).
- **The loader loads Synthea's shared bundles first** (1e3263a). Synthea patient bundles find their Practitioner, Organization, and Location by conditional identifier search, so those resources must already exist. The default HAPI heap (`-Xmx2g`) was enough for the ten chosen patients.
- **A second request directory serves the Synthea forms** (153590f). `EXTRA_REQUESTS_DIR` points the API and MCP server at `eval/synthea_requests/`, so the eval forms stay out of `resources/requests/`.

## Open questions from plan section 10

1. The GitHub remote does not exist yet. The CI workflow in `.github/workflows/ci.yml` runs the same commands as the local checks, and its first run happens at the first push.
2. The Synthea sample is `synthea_sample_data_fhir_r4_nov2021.zip`, and the assumed request date for the ten Synthea requests is 2021-11-19. That is the day the sample was generated. The shared bundle file names carry the timestamp 1637345232350 (2021-11-19 18:07 UTC), and every file in the archive is dated 2021-11-19.

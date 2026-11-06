Prompt `summary-v4`, 5 runs x 7 packets, temperature 0, CPU, one warm-up call per model not counted.

| Model | Digest | Valid schema | Faithful | Forbidden hits | Accepted | Median latency |
|---|---|---|---|---|---|---|
| `qwen2.5:3b-instruct-q4_K_M` | `357c53fb659c` | 29% | 0% | 0 | 0% | 2.55 s |
| `llama3.2:3b-instruct-q4_K_M` | `a80c4f17acd5` | 100% | 43% | 0 | 43% | 2.07 s |

Default `SUMMARY_MODEL` is `llama3.2:3b-instruct-q4_K_M`: it ties or beats qwen2.5 on faithfulness
in every prompt iteration, has no forbidden-word hits and 100% valid schema. Both 3B models state a
wrong criterion status in most runs, so the faithfulness check rejects most output and the template
fallback carries the summary. Output is deterministic per packet (temperature 0), so the 5 runs
repeat and the rate is effectively 3 of 7 packets (PA-002, PA-003, PA-005) for llama.
Known leak: a hedged clause such as "C3 is not_met, missing or conflicting" is accepted for a
not_met criterion. Prompt iterations, accepted rate qwen / llama: v1 86% / 100% before the
status-claim check existed (it called PA-001's met C2 unmet); v2 20% / 14%; v3 14% / 14% (the
model copied the prompt's placeholder example); v4 0% / 43% (final).

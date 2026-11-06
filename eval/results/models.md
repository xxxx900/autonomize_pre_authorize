Prompt `summary-v4`, 5 runs x 7 packets, temperature 0, CPU, one warm-up call per model not counted.

| Model | Digest | Valid schema | Faithful | Forbidden hits | Accepted | Median latency |
|---|---|---|---|---|---|---|
| `qwen2.5:3b-instruct-q4_K_M` | `357c53fb659c` | 29% | 0% | 0 | 0% | 2.57 s |
| `llama3.2:3b-instruct-q4_K_M` | `a80c4f17acd5` | 100% | 29% | 0 | 29% | 2.06 s |

Default `SUMMARY_MODEL` is `llama3.2:3b-instruct-q4_K_M`: it ties or beats qwen2.5 on faithfulness
in every prompt iteration, has no forbidden-word hits and 100% valid schema. Both 3B models state a
wrong criterion status in most runs, so the faithfulness check rejects most output and the template
fallback carries the summary. Prompt iterations (accepted rate qwen / llama): v1 86% / 100% before
the status-claim check existed (that check was added after v1 showed PA-001's met C2 called unmet);
v2 20% / 14%; v3 14% / 14% (copied the example's placeholder text); v4 0% / 29%.

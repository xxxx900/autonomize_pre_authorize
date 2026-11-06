Prompt `summary-v4`, 5 runs x 7 packets, temperature 0, CPU, one warm-up call per model not counted.

| Model | Digest | Valid schema | Faithful | Forbidden hits | Accepted | Median latency |
|---|---|---|---|---|---|---|
| `qwen2.5:7b-instruct-q4_K_M` | `845dbda0ea48` | 100% | 71% | 0 | 71% | 6.24 s |
| `llama3.2:3b-instruct-q4_K_M` | `a80c4f17acd5` | 100% | 14% | 0 | 14% | 2.1 s |
| `qwen2.5:3b-instruct-q4_K_M` | `357c53fb659c` | 29% | 0% | 0 | 0% | 2.6 s |

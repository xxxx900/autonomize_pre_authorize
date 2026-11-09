Engine status per criterion. A cell reads `engine (expected X)` where the engine disagrees with the expected status.

`Sources resolve` counts cited resources fetched directly from FHIR. `Faithful` re-runs the forbidden-word and faithfulness checks on the served summary.

| Request | C1 | C2 | C3 | C4 | C5 | Route | Sources resolve | Summary | Faithful | Flagged docs | Latency |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PA-001 | met | met | met | met | met | evidence_complete | 4/4 | template | yes | 0 | 8.6 s |
| PA-002 | met | missing | met | met | met | clinician_review | 4/4 | model | yes | 0 | 4.48 s |
| PA-003 | met | met | not_met | met | met | clinician_review | 4/4 | template | yes | 0 | 4.75 s |
| PA-004 | met | met | conflicting | met | met | clinician_review | 4/4 | template | yes | 0 | 5.28 s |
| PA-005 | met | met | met | not_met | met | clinician_review | 5/5 | template | yes | 0 | 4.22 s |
| PA-006 | met | conflicting | met | met | met | clinician_review | 5/5 | template | yes | 1 | 4.93 s |
| PA-007 | not_met | met | met | met | met | clinician_review | 4/4 | template | yes | 0 | 9.56 s |
| SYN-001 | met | met | missing | met | met | clinician_review | 70/70 | template | yes | 67 | 8.75 s |
| SYN-002 | met | conflicting | missing | met | met | clinician_review | 29/29 | template | yes | 26 | 8.56 s |
| SYN-003 | met | not_met | not_met | met | met | clinician_review | 28/28 | model | yes | 20 | 9.0 s |
| SYN-004 | met | not_met | met | met | met | clinician_review | 67/67 | model | yes | 63 | 5.7 s |
| SYN-005 | met | not_met | not_met | met | met | clinician_review | 81/81 | template | yes | 53 | 8.04 s |
| SYN-006 | met | missing | missing | met | met | clinician_review | 56/56 | model | yes | 53 | 7.77 s |
| SYN-007 | met | missing | missing | met | met | clinician_review | 185/185 | model | yes | 182 | 8.04 s |
| SYN-008 | missing | conflicting | missing | met | met | clinician_review | 47/47 | template | yes | 45 | 8.97 s |
| SYN-009 | missing | missing | missing | met | not_met | clinician_review | 18/18 | template | yes | 17 | 5.13 s |
| SYN-010 | missing | missing | missing | met | met | clinician_review | 27/27 | template | yes | 26 | 5.42 s |
| Agreement | 17/17 | 17/17 | 17/17 | 17/17 | 17/17 | | | | | | |

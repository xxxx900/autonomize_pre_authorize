Engine status per criterion. A cell reads `engine (expected X)` where the engine disagrees with the expected status.

| Request | C1 | C2 | C3 | C4 | C5 | Route | Summary | Flagged docs | Latency |
|---|---|---|---|---|---|---|---|---|---|
| PA-001 | met | met | met | met | met | evidence_complete | template | 0 | 7.49 s |
| PA-002 | met | missing | met | met | met | clinician_review | model | 0 | 4.1 s |
| PA-003 | met | met | not_met | met | met | clinician_review | template | 0 | 4.41 s |
| PA-004 | met | met | conflicting | met | met | clinician_review | template | 0 | 4.96 s |
| PA-005 | met | met | met | not_met | met | clinician_review | template | 0 | 3.81 s |
| PA-006 | met | conflicting | met | met | met | clinician_review | template | 1 | 4.59 s |
| PA-007 | not_met | met | met | met | met | clinician_review | template | 0 | 8.66 s |
| SYN-001 | met | met | missing | met | met | clinician_review | template | 67 | 7.82 s |
| SYN-002 | met | conflicting | missing | met | met | clinician_review | template | 26 | 7.67 s |
| SYN-003 | met | not_met | not_met | met | met | clinician_review | model | 20 | 8.02 s |
| SYN-004 | met | not_met | met | met | met | clinician_review | model | 63 | 5.29 s |
| SYN-005 | met | not_met | not_met | met | met | clinician_review | template | 53 | 7.44 s |
| SYN-006 | met | missing | missing | met | met | clinician_review | model | 53 | 7.19 s |
| SYN-007 | met | missing | missing | met | met | clinician_review | model | 182 | 7.32 s |
| SYN-008 | missing | conflicting | missing | met | met | clinician_review | template | 45 | 8.08 s |
| SYN-009 | missing | missing | missing | met | not_met | clinician_review | template | 17 | 4.66 s |
| SYN-010 | missing | missing | missing | met | met | clinician_review | template | 26 | 4.6 s |
| Agreement | 17/17 | 17/17 | 17/17 | 17/17 | 17/17 | | | | |

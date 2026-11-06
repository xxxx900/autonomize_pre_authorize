Engine status per criterion. A cell reads `engine (expected X)` where the engine disagrees with the expected status.

| Request | C1 | C2 | C3 | C4 | C5 | Route | Summary | Flagged docs | Latency |
|---|---|---|---|---|---|---|---|---|---|
| PA-001 | met | met | met | met | met | evidence_complete | template | 0 | 5.7 s |
| PA-002 | met | missing | met | met | met | clinician_review | model | 0 | 4.36 s |
| PA-003 | met | met | not_met | met | met | clinician_review | template | 0 | 4.33 s |
| PA-004 | met | met | conflicting | met | met | clinician_review | template | 0 | 5.02 s |
| PA-005 | met | met | met | not_met | met | clinician_review | template | 0 | 4.08 s |
| PA-006 | met | conflicting | met | met | met | clinician_review | template | 1 | 4.47 s |
| PA-007 | not_met | met | met | met | met | clinician_review | template | 0 | 8.44 s |
| SYN-001 | met | met | missing | met | met | clinician_review | template | 67 | 7.56 s |
| SYN-002 | met | conflicting | missing | met | met | clinician_review | template | 26 | 7.61 s |
| SYN-003 | met | not_met | not_met | met | met | clinician_review | model | 20 | 8.02 s |
| SYN-004 | met | not_met | met | met | met | clinician_review | model | 63 | 5.21 s |
| SYN-005 | met | not_met | not_met | met | met | clinician_review | template | 53 | 7.49 s |
| SYN-006 | met | missing | missing | met | met | clinician_review | model | 53 | 7.1 s |
| SYN-007 | met | missing | missing | met | met | clinician_review | model | 182 | 7.3 s |
| SYN-008 | missing | conflicting | missing | met | met | clinician_review | template | 45 | 7.85 s |
| SYN-009 | missing | missing | missing | met | not_met | clinician_review | template | 17 | 4.55 s |
| SYN-010 | missing | missing | missing | met | met | clinician_review | template | 26 | 4.48 s |
| Agreement | 17/17 | 17/17 | 17/17 | 17/17 | 17/17 | | | | |

# Evaluation

This page reports how the rules engine did on 17 requests, how the ten Synthea cases were audited by hand, what the audit found, and how candidate summary models measured. Raw results are in `eval/results/`.

## The 17 requests

Seven requests are the supplied pack (PA-001 to PA-007), with expected outcomes from plan section 5. Ten are written for this evaluation (SYN-001 to SYN-010) on ten patients from the Synthea nov2021 R4 sample, with expected outcomes from the hand audit below. Every Synthea request uses the assumed request date 2021-11-19. [Decisions](decisions.md#the-synthea-request-date-is-2021-11-19) explains that date.

### Why these ten patients

The sample has 555 patients, and 32 of them have a type 2 diabetes Condition (SNOMED 44054006). None has a type 1 diabetes, pancreatitis, medullary thyroid carcinoma, or MEN2 Condition, so the Synthea cases cannot exercise C1 `conflicting` or C4 `not_met`. The supplied PA-005 covers C4. The ten were chosen to reach every other status, preferring bundles under about 2,000 resources so HAPI loads them quickly.

| Request | Synthea patient | Why it is in the set |
|---|---|---|
| SYN-001 | Loretta235 Bosco882 | T2DM, HbA1c 7.46 four days before the request date, no metformin record |
| SYN-002 | Lorinda137 Rosenbaum794 | T2DM, HbA1c 7.49 inside the 90-day window, no metformin record |
| SYN-003 | Meghan514 Jacobson885 | T2DM, HbA1c below 7, metformin renewed yearly as stopped and active requests |
| SYN-004 | Felton646 Pouros728 | T2DM, eGFR below 30 (the C3 contraindication path), no metformin record |
| SYN-005 | Ula130 Medhurst46 | T2DM, active metformin request 80 days old, just under the 90-day threshold |
| SYN-006 | Benny518 Tillman293 | T2DM, latest HbA1c eight days before the window opens |
| SYN-007 | Shonna561 Cassin499 | T2DM, but the member died in 2016 |
| SYN-008 | Tomiko229 Ratke343 | No T2DM, prediabetes with an in-window HbA1c below 7 |
| SYN-009 | David908 Dicki44 | No T2DM, age 16 on the request date |
| SYN-010 | Lemuel304 Lueilwitz711 | No T2DM, an adult with no diabetes-related record |

Seven have T2DM and three do not. The forms in `eval/synthea_requests/` test the attestation rules on purpose:

- **Disagreeing with the record:** SYN-002 (HbA1c 8.2 against 7.49 on 2021-09-10), SYN-003 (12 months of metformin), and SYN-008 (HbA1c 7.4 against 6.25 on 2021-10-13).
- **Agreeing with the record:** SYN-001 (HbA1c 7.46), SYN-004 (HbA1c 4.17), SYN-005 (2 months of metformin), and SYN-006 (HbA1c 3.6, outside the window).
- **Attesting a value the record has no data for:** SYN-001 (6 months of metformin), SYN-009 (HbA1c 7.2), and SYN-010 (4 months of metformin). The policy says absence is `missing`, never `conflicting`.
- **No attestation:** SYN-007.

### Load the Synthea bundles

`scripts/fetch_synthea.py` copies the ten patient bundles and the two shared bundles (hospital and practitioner information) into `resources/synthea/`. The loader turns Synthea's `POST` entries into `PUT Type/<uuid>` so a reload converges. Two loads in a row, counted with `Cache-Control: no-cache`, gave the same counts:

```
counts {"Patient": 17, "Condition": 422, "Observation": 3717, "MedicationRequest": 375, "AllergyIntolerance": 6, "DocumentReference": 553}
counts {"Patient": 17, "Condition": 422, "Observation": 3717, "MedicationRequest": 375, "AllergyIntolerance": 6, "DocumentReference": 553}
```

The default HAPI heap (`-Xmx2g`) was enough. The first load failed with HTTP 404 because the loader loaded patient bundles before the shared bundles they reference by `Practitioner?identifier=`. The loader now loads the shared bundles first (1e3263a).

## Results

`eval/results/eval.md` is the output of `docker compose --profile eval run --rm run-eval` on the live stack (rerun 2026-11-08). All 85 criterion statuses agree with the expected statuses. Two columns are checked outside the API: **Sources resolve** fetches every cited resource (criterion sources, conflict sources, and flagged documents) straight from HAPI, and all 674 answer. **Faithful** reruns the forbidden-word and faithfulness checks on the summary actually served, and all 17 pass, whether the model or the template wrote them.

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

The first run, before the fix in 9cbd356, disagreed on one cell: SYN-003 C3 was `conflicting` where the hand audit expected `not_met`. See the first finding.

Only SYN-001 has C2 `met` among the Synthea cases, and no Synthea case reaches `evidence_complete`. No Synthea patient with T2DM had both an in-window HbA1c of 7.0 or more and 90 days of metformin by the policy's duration rule.

Latency is the wall time of one API call on a Ryzen 7 7800X3D with CPU inference and `llama3.2:3b-instruct-q4_K_M` already loaded. Nearly all of it is the summary model call. Timed inside the api container without the model, the FHIR fetch, the rules, and the source checks take 0.03 s for PA-001 and 0.71 s for SYN-001, the slowest case. SYN-007's 182 flagged documents cost 0.23 s of source checks. Those figures are for five requests timed once each, and SYN-001 was the slowest of them. The Synthea cases are slower because the model call is slower for them. The likely cause is a longer prompt and answer, which was not measured directly.

The first eval run, before the warm-up change, started with Ollama holding no model, and PA-001 took 11.2 s. After the warm-up change, with Ollama again cold at API start, the API logged `summary model warm-up done in 3.1 s`, and the first PA-001 request took 7.6 s. A repeat PA-001 request took 2.1 s, because Ollama reuses its cache for an identical prompt. Each figure is a single request.

## Hand audit method

The hand audit was written before the engine ran on any Synthea request. Commit d961864 adds `eval/synthea_expected.json`, and the eval runner and its first results come later in cef8412.

1. `eval/audit_facts.py` prints the raw facts for each Synthea bundle: birth and death dates, every Condition whose display mentions diabetes, the pancreas, the thyroid, neoplasia, or the kidney, every HbA1c and the last three eGFR results, every metformin prescription with its status and end date, and every allergy. It reads the bundle JSON directly and imports nothing from `app/`, so the audit does not reuse the engine's parsing.
2. A `grep` of the ten bundles for SNOMED 75694006, 255032005, 61808009, and 46635009 confirmed that no exclusion or type 1 diabetes code is present, and that no metformin allergy (RxNorm 6809) exists.
3. For each request and criterion, the expected status, the FHIR ids read, and the reasoning went into `eval/synthea_expected.json`.

After the run, the cited sources were compared with the ids in the audit. For every `met`, `not_met`, or `conflicting` status where the audit names a resource, the engine cites that resource. For a `missing` status the engine cites at most the latest HbA1c outside the window. The audit sometimes names a resource it checked and set aside, such as the eGFR of 131.54 behind SYN-001's `missing` C3.

## Findings

Findings are ranked by severity. Each is classified as an engine bug, an interpretation question, or a data quirk.

1. **Engine bug, fixed: unknown metformin durations produced a false `conflicting`.** SYN-003's member has four stopped metformin requests from 2018 to 2020 with no end date and one active request from 2021-10-21. The engine counted the stopped requests as zero days, compared the form's 12 months with "1.0 months (29 days)", and reported C3 `conflicting`. The record does not contradict 12 months, because it cannot say how long the stopped requests lasted. A nurse would have chased a contradiction that does not exist. The fix (9cbd356, with `test_stopped_requests_without_end_date_do_not_contradict_the_attested_months` written first and seen to fail) runs the attestation check only when every prescription has a known end. C3 is now `not_met`, and its rationale says how many requests were not counted. PA-004 is unchanged, because its one prescription has an end date.
2. **Interpretation: the policy's duration rule undercounts chronic metformin in Synthea.** SYN-005's member has 24 stopped metformin requests since 2004 and one active request 80 days old. By the policy's rule, C3 is `not_met`, and the hand audit agrees. A clinician would likely read seventeen years of therapy. [Decisions](decisions.md#metformin-prescriptions-with-no-end-date-are-not-counted) explains why the engine does not infer an end date. Fill history (`MedicationDispense`) would settle it.
3. **Interpretation: a deceased member gets an ordinary packet.** SYN-007's member died on 2016-07-21. The policy has no criterion for death, so C5 is `met` at age 59, and the hand audit expected the same. The packet does not mention the death. See [decisions](decisions.md#a-deceased-member-gets-an-ordinary-packet).
4. **Interpretation: exact code matching can miss a C4 exclusion.** No Synthea patient has an exclusion condition, so the evaluation could not test this. A record that codes only a descendant of pancreatitis would pass C4 as `met`. See [decisions](decisions.md#codes-match-exactly-without-a-terminology-service).
5. **Data quirk: Synthea HbA1c values are often physiologically implausible.** SYN-005 shows 2.41% at every visit since 2012, and SYN-006 shows 3.6%. The engine reports them as recorded. They make C2 `not_met`, which is correct for the data and meaningless clinically.
6. **Data quirk: Synthea codes conditions that contradict each other.** SYN-003's member gains a Prediabetes Condition in 2021, sixteen years after the T2DM diagnosis, and both are active. SYN-007's T2DM Condition stays active after death. The engine reads only the T2DM code and status, so neither changes a status.
7. **Usability: every Synthea encounter note is a flagged document.** Synthea writes a `DocumentReference` with a base64 note for each encounter, so packets list 17 to 182 flagged documents. D4 requires listing them unread, but a nurse cannot review 182 documents. Filtering by document type or date window would help, and the policy does not say which documents matter.
8. **Cosmetic: the C3 `met` rationale loses its capitals.** The engine joins the reasons and calls `str.capitalize()`, which lowercases the rest of the string, so SYN-004 reads "Latest egfr 24.35 on 2021-10-16". The value and date are right. Fixed after merge: the first letter is uppercased instead, so it now reads "Latest eGFR".

## Summary model measurements

`eval/measure_models.py` builds the seven supplied packets, asks each model for a summary five times per packet, and scores every answer with the same checks the API uses. All runs use prompt `summary-v4`, temperature 0, seed 7, and CPU inference on the Ryzen 7 7800X3D, with one unscored warm-up call per model. No API or agent traffic reached this Ollama during the run. CPU load from other containers on the host was not recorded for this run. An earlier attempt was cut off when the containers were stopped from outside this work, and during that attempt a second Ollama on the host was at about 750% CPU at times. The models were measured in one session, written to `eval/results/models-7b.json` and `models-7b.md`:

| Model | Digest | Valid schema | Faithful | Forbidden hits | Accepted | Packets accepted | Median latency, first run per packet | Median latency, runs 2 to 5 |
|---|---|---|---|---|---|---|---|---|
| `qwen2.5:7b-instruct-q4_K_M` | `845dbda0ea48` | 100% | 71% | 0 | 71% | 5 of 7 | 10.32 s | 5.42 s |
| `llama3.2:3b-instruct-q4_K_M` (default) | `a80c4f17acd5` | 100% | 14% | 0 | 14% | 1 of 7 | 4.31 s | 2.07 s |
| `qwen2.5:3b-instruct-q4_K_M` | `357c53fb659c` | 29% | 0% | 0 | 0% | 0 of 7 | 4.92 s | 2.41 s |

"Accepted" means a valid schema, no faithfulness problem, and no forbidden word, which is what the API needs to serve a model summary. At temperature 0 with a fixed seed, the five runs of a packet produced one or two distinct texts, and a packet was accepted in all five runs or in none. Each model's rate is therefore a count over seven packets. That is too few to rank two close models, but enough to separate 5 of 7 from 1 of 7.

The two latency columns differ because Ollama reuses its cache when the same prompt repeats, so runs 2 to 5 are faster. The first run per packet is the figure that matches a live request, where each packet is new. `models-7b.md` prints one median over all 35 calls, which is closer to the repeat figure. The first-run medians come from the `run` field in `models-7b.json`.

What each model got wrong:

- `qwen2.5:7b` failed on PA-001 and PA-003. For PA-001, where every criterion is met, it wrote that C2 is `not_met` and gave an HbA1c date that is not in the packet. For PA-003 it hedged C3 as "missing or conflicting". It passed PA-002 and PA-004 to PA-007.
- `llama3.2:3b` passed only PA-002. In 41 of its 50 status problems it attached several status words to one criterion, such as "C3 is not_met, missing or conflicting".
- `qwen2.5:3b` returned an invalid schema in 25 of 35 calls, and every valid answer misstated a status.

### The earlier 3B numbers are out of date

`eval/results/models.md`, committed in cb5f1d7, reports `llama3.2:3b` at 43% accepted (3 of 7 packets). The model's output has not changed. Its stored PA-003 and PA-005 summaries are word for word what this run produced. The checks changed. The merge commit b7ff852 changed `stated_statuses` in `app/safety.py` (now [`app/summary/safety.py`](../app/summary/safety.py)) to collect every status word in a clause, which closed the hedged-claim leak that `models.md` describes. "C3 is not_met, missing or conflicting" is now rejected for a `not_met` criterion. Rescored with the current `faithfulness_problems`, the stored `models.json` gives `llama3.2:3b` 14% (1 of 7), the same as this run. `models.md` is left as committed, as a record of what was measured then.

### What the numbers mean for the default

`qwen2.5:7b` is the only candidate that passes the checks on most packets, at about 10 s for a new packet. That is inside the 30 s `SUMMARY_TIMEOUT_SECONDS`. With `llama3.2:3b`, the template summary carries six of the seven supplied packets. The default `SUMMARY_MODEL` stays `llama3.2:3b-instruct-q4_K_M`, because changing it is the owner's call. To switch, add `qwen2.5:7b-instruct-q4_K_M` to `OLLAMA_PULL_MODELS` (a 4.7 GB pull) and set `SUMMARY_MODEL` to it. Either way, a rejected summary falls back to the template, so the choice affects only how often the nurse reads model prose.
